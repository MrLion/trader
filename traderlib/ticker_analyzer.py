#!/usr/bin/env python3
"""Shared ticker analysis module.

Extracted from entry_signals.py and paper_engine_alpaca.py to eliminate
duplicated analysis logic (Stage 2 scoring, pivot detection, stop/target
calculation, entry scoring, market conditions).
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import pytz

from traderlib import get_entry_score, get_stage2_details, calculate_ma_support_stop
from traderlib.pivot_detection import detect_pivot, PivotSignal
from traderlib.sector_resolver import SectorResolver
from traderlib.trading_exceptions import TradingExceptionHandler


@dataclass
class TickerAnalysis:
    """Complete analysis result for a single ticker."""
    ticker: str
    current: float
    stage2: int
    entry_score: float
    tier: str
    pivot: Optional[float] = None
    dist_to_pivot: Optional[float] = None
    stop: float = 0.0
    target: float = 0.0
    sector: str = 'Unknown'
    risk_pct: float = 0.0
    atr_stop: float = 0.0
    atr_risk_pct: Optional[float] = None
    ma_support_stop: Optional[float] = None
    ma_risk_pct: Optional[float] = None
    stop_type: str = 'ATR'
    ret_6m: float = 0.0
    rs_6m: float = 0.0
    atr: float = 0.0
    spy_return_6m: float = 0.0
    below_50ma: bool = False
    below_20ma: bool = False
    pivot_type: str = 'none'
    entry_mode: str = 'immediate'

    def to_dict(self) -> Dict:
        """Return analysis as a plain dict for backward compatibility."""
        return {
            'ticker': self.ticker,
            'current': self.current,
            'pivot': self.pivot,
            'stop': self.stop,
            'target': self.target,
            'sector': self.sector,
            'stage2': self.stage2,
            'entry_score': self.entry_score,
            'tier': self.tier,
            'dist_to_pivot': self.dist_to_pivot,
            'risk_pct': self.risk_pct,
            'atr_stop': self.atr_stop,
            'atr_risk_pct': self.atr_risk_pct,
            'ma_support_stop': self.ma_support_stop,
            'ma_risk_pct': self.ma_risk_pct,
            'stop_type': self.stop_type,
            'ret_6m': self.ret_6m,
            'rs_6m': self.rs_6m,
            'atr': self.atr,
            'spy_return_6m': self.spy_return_6m,
            'below_50ma': self.below_50ma,
            'below_20ma': self.below_20ma,
            'pivot_type': self.pivot_type,
            'entry_mode': self.entry_mode,
        }


class TickerAnalyzer:
    """Analyze a single ticker — price, Stage 2, pivot, stop, target, score."""

    def __init__(self, alpaca, risk_config, watchlist_path: Optional[Path] = None,
                 sector_resolver=None):
        """
        Args:
            alpaca: AlpacaClient instance
            risk_config: RiskConfig dataclass
            watchlist_path: Path to watchlist CSV (optional — if None, manual pivots are skipped)
            sector_resolver: SectorResolver instance (optional — created automatically if None)
        """
        self.alpaca = alpaca
        self.risk_config = risk_config
        self.watchlist_path = watchlist_path
        self.sector_resolver = sector_resolver or SectorResolver(watchlist_path=watchlist_path)
        self._universe_path: Optional[Path] = None
        self.spy_cache = {'date': None, 'return_6m': 0.0, 'price': None}

    def set_universe_path(self, path: Path) -> None:
        """Set universe CSV path for sector resolution."""
        self._universe_path = path

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _get_spy_return_6m(self) -> float:
        """6-month SPY return, cached per day."""
        today = datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d')
        if self.spy_cache['date'] == today:
            return self.spy_cache['return_6m']
        try:
            spy_hist = self.alpaca.get_historical_bars('SPY')
            if spy_hist is not None and len(spy_hist) >= 130:
                current = spy_hist['Close'].iloc[-1]
                past = spy_hist['Close'].iloc[-130]
                ret_6m = ((current / past) - 1) * 100
                self.spy_cache = {'date': today, 'return_6m': ret_6m, 'price': current}
                return ret_6m
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "spy_return_fetch", e,
                severity=TradingExceptionHandler.WARNING, ticker='SPY'
            )
            print(f"   ⚠️  SPY return unavailable: {e}")
        return 0.0

    def _get_current_price(self, ticker: str) -> Optional[float]:
        """Latest price from Alpaca (quote → historical fallback)."""
        try:
            price = self.alpaca.get_latest_price(ticker)
            if price:
                return price
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "get_current_price_quote", e,
                severity=TradingExceptionHandler.WARNING, ticker=ticker
            )
        try:
            hist = self.alpaca.get_historical_bars(ticker, days=5)
            if hist is not None and len(hist) > 0:
                return hist['Close'].iloc[-1]
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "get_current_price_hist", e,
                severity=TradingExceptionHandler.WARNING, ticker=ticker
            )
        return None

    def check_market_conditions(self) -> tuple:
        """Check SPY trend and VIX level.

        Returns:
            (entries_ok, spy_str, vix_str)
        """
        spy_str = 'SPY —'
        vix_str = ''

        try:
            hist = self.alpaca.get_historical_bars('SPY', days=5)
            if hist is not None and len(hist) >= 2:
                chg = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-2]) - 1) * 100
                spy_str = f"SPY {chg:+.2f}%"
                if chg < self.risk_config.market.max_spy_decline_pct:
                    return False, spy_str, vix_str
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "market_conditions", e,
                severity=TradingExceptionHandler.WARNING, ticker='SPY'
            )

        max_vix = self.risk_config.market.max_vix
        if max_vix is not None:
            try:
                import yfinance as yf
                vix_hist = yf.Ticker("^VIX").history(period="2d", auto_adjust=False)
                if not vix_hist.empty:
                    vix_current = float(vix_hist['Close'].iloc[-1])
                    vix_str = f"VIX {vix_current:.1f}"
                    if vix_current > max_vix:
                        return False, spy_str, vix_str
            except Exception as e:
                TradingExceptionHandler.log_exception(
                    "vix_fetch", e,
                    severity=TradingExceptionHandler.WARNING, ticker='^VIX'
                )
                vix_str = 'VIX unavailable (gate open)'
                print(f"   ⚠️  VIX fetch failed: {e} — volatility gate OPEN")

        return True, spy_str, vix_str

    def _load_watchlist_pivot_and_sector(self, ticker: str) -> tuple:
        """Return (pivot, sector) for ticker.

        Pivot comes from watchlist CSV if present.
        Sector comes from SectorResolver (watchlist → universe → FMP).
        """
        pivot = None
        if self.watchlist_path is not None and self.watchlist_path.exists():
            try:
                df = pd.read_csv(self.watchlist_path)
                row = df[df['Ticker'] == ticker]
                if not row.empty and 'Pivot_Price' in row.columns:
                    pv = row['Pivot_Price'].values[0]
                    if not pd.isna(pv):
                        pivot = float(pv)
            except Exception as e:
                TradingExceptionHandler.log_exception(
                    "watchlist_lookup", e,
                    severity=TradingExceptionHandler.WARNING,
                    ticker=ticker, file=str(self.watchlist_path)
                )

        sector = self.sector_resolver.resolve(ticker, self._universe_path)
        return pivot, sector

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def analyze(self, ticker: str, current_price: Optional[float] = None,
                technique: str = 'auto') -> Optional[TickerAnalysis]:
        """Full analysis for one ticker.

        Args:
            ticker: Stock symbol
            current_price: Optional pre-fetched price (e.g. from WebSocket cache)
            technique: Pivot detection technique ('auto', 'range_20d', 'vcp', 'pocket_pivot')

        Returns:
            TickerAnalysis dataclass, or None on data failure.
        """
        try:
            hist = self.alpaca.get_historical_bars(ticker)
            if hist is None or len(hist) < 30:
                bar_count = len(hist) if hist is not None else 0
                print(f"   ⏸️  {ticker}: Insufficient history ({bar_count} bars, need 30)")
                return None

            current = current_price if current_price is not None else self._get_current_price(ticker)
            if current is None:
                print(f"   ⏸️  {ticker}: Cannot get current price")
                return None

            # Stage 2 scoring
            s2_details = get_stage2_details(hist)
            stage2 = s2_details['score']
            if not s2_details.get('criteria'):
                print(f"   ⏸️  {ticker}: Stage 2 criteria missing (score={stage2})")
                return None
            below_50ma = not s2_details['criteria'].get('price_above_50ma', True)
            below_20ma = not s2_details['criteria'].get('price_above_20ma', True)

            # Pivot and sector from watchlist
            pivot, sector = self._load_watchlist_pivot_and_sector(ticker)
            pivot_type = 'manual' if pivot is not None else 'none'
            entry_mode = 'breakout' if pivot is not None else 'immediate'
            detected_signal = None

            # Automatic pivot detection when no manual pivot
            if pivot is None:
                detected_signal = detect_pivot(ticker, hist, technique=technique)
                if detected_signal is not None:
                    pivot = detected_signal.pivot_price
                    pivot_type = detected_signal.pivot_type
                    entry_mode = detected_signal.entry_mode
                else:
                    # Ultimate fallback: 20-day range high
                    pivot = float(hist['High'].tail(20).max())
                    pivot_type = 'range_20d'
                    entry_mode = 'immediate'
                    # When explicit technique requested but failed, mark it clearly
                    if technique != 'auto':
                        print(f"   ⚠️  {ticker}: {technique} pivot not found, using 20d range fallback")
                        pivot_type = technique + '_fallback'

            # 6-month return
            ret_6m = 0.0
            if len(hist) >= 130:
                ret_6m = ((current / hist['Close'].iloc[-130]) - 1) * 100

            # ATR
            try:
                high_low = hist['High'] - hist['Low']
                high_close = abs(hist['High'] - hist['Close'].shift())
                low_close = abs(hist['Low'] - hist['Close'].shift())
                tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = tr.rolling(14).mean().iloc[-1]
            except Exception as e:
                TradingExceptionHandler.log_exception(
                    "atr_calculation", e,
                    severity=TradingExceptionHandler.WARNING, ticker=ticker
                )
                print(f"   ⚠️  {ticker}: ATR calculation failed ({e}), using 2% fallback")
                atr = current * 0.02

            # Anchor stop calculation to pivot when present and below current
            # (prevents ATR stop from landing above the entry price on breakout setups)
            stop_anchor = pivot if (pivot and pivot < current) else current
            atr_stop = stop_anchor - (2 * atr)
            recent_low = hist['Low'].tail(10).min()
            stop = max(atr_stop, recent_low)
            atr_risk_pct = abs((current - atr_stop) / current) * 100 if atr_stop < current else None
            # Risk from the actual stop after recent_low override (used for scoring)
            base_risk_pct = abs((current - stop) / current) * 100 if stop < current else 999.0

            # MA Support Stop
            ma_support_stop = None
            ma_risk_pct = None
            stop_type = 'ATR'
            if self.risk_config.ma_support.enabled:
                ma_result = calculate_ma_support_stop(
                    current, s2_details,
                    buffer_pct=self.risk_config.ma_support.buffer_pct,
                    cluster_spread_pct=self.risk_config.ma_support.cluster_spread_pct,
                    min_cluster_size=self.risk_config.ma_support.min_cluster_size
                )
                if ma_result:
                    ma_support_stop = ma_result['ma_support_stop']
                    ma_risk_pct = (
                        abs((current - ma_support_stop) / current) * 100
                        if ma_support_stop < current else None
                    )

            # Use tighter (higher) stop
            if ma_support_stop and ma_support_stop > stop:
                stop = ma_support_stop
                risk_pct = ma_risk_pct
                stop_type = 'MA'
            else:
                risk_pct = base_risk_pct

            # Sanity-check bounds anchored to stop_anchor (pivot when present)
            min_stop = stop_anchor * (1 - self.risk_config.stop_loss.max_stop_distance_pct)
            max_stop = stop_anchor * (1 - self.risk_config.stop_loss.min_stop_distance_pct)

            # Technique-specific stop override (e.g. VCP stop_low, pocket pivot prior low)
            if detected_signal and detected_signal.stop_price:
                tech_stop = detected_signal.stop_price
                # Do not reject a technique stop simply for being "looser" when the
                # current ATR stop is above the pivot (which would be an invalid stop).
                atr_stop_above_pivot = pivot and stop >= pivot
                if tech_stop <= stop and not atr_stop_above_pivot:
                    print(f"   ℹ️  {ticker}: {detected_signal.pivot_type} stop {tech_stop:.2f} looser than ATR/MA stop {stop:.2f}, keeping ATR/MA")
                elif not (min_stop <= tech_stop <= max_stop):
                    print(f"   ℹ️  {ticker}: {detected_signal.pivot_type} stop {tech_stop:.2f} outside bounds [{min_stop:.2f}, {max_stop:.2f}], clamped to ATR/MA")
                else:
                    stop = tech_stop
                    risk_pct = abs((current - tech_stop) / current) * 100
                    stop_type = detected_signal.pivot_type.upper()

            # Final sanity check: clamp stop to configured min/max distance from entry
            clamped = False
            if stop > max_stop:
                stop = max_stop
                clamped = True
            elif stop < min_stop:
                stop = min_stop
                clamped = True
            if clamped and stop_type not in ('ATR', 'MA'):
                print(f"   ℹ️  {ticker}: {stop_type} stop clamped to bounds, reverting stop_type to ATR")
                stop_type = 'ATR'

            # Hard guard: for breakout entries, stop must be below pivot
            if pivot and stop >= pivot:
                stop = pivot * 0.99
                risk_pct = abs((current - stop) / current) * 100
                stop_type = 'PIVOT_FALLBACK'
                print(f"   ℹ️  {ticker}: stop was above pivot, forced to {stop:.2f} (1% below pivot)")

            # Recompute risk_pct after clamping so scoring reflects the actual stop
            risk_pct = abs((current - stop) / current) * 100 if stop < current else 999.0

            risk_per_share = current - stop
            if detected_signal and detected_signal.target_price:
                # Use technique-specific target if available (e.g. VCP 2R from pivot high)
                target = detected_signal.target_price
            elif risk_per_share > 0:
                min_r = self.risk_config.profit_target.min_r_multiple
                target = current + (risk_per_share * min_r)
            else:
                target = current * (1 + self.risk_config.profit_target.fallback_target_pct)
            target = round(target, 2)

            # dist_to_pivot
            dist_to_pivot = (
                ((pivot - current) / current) * 100 if pivot is not None else None
            )
            dist_for_scoring = dist_to_pivot if dist_to_pivot is not None else 999.0

            spy_return_6m = self._get_spy_return_6m()
            rs_6m = ret_6m - spy_return_6m

            entry_score = get_entry_score(
                stage2, risk_pct, dist_for_scoring, ret_6m, rs_6m,
                below_50ma=below_50ma, below_20ma=below_20ma
            )

            tier = (
                "Tier 1" if entry_score >= 60 and stage2 >= 8 else
                "Tier 2" if entry_score >= 40 and stage2 >= 6 else
                "Tier 3"
            )

            return TickerAnalysis(
                ticker=ticker,
                current=current,
                stage2=stage2,
                entry_score=entry_score,
                tier=tier,
                pivot=pivot,
                dist_to_pivot=dist_to_pivot,
                stop=stop,
                target=target,
                sector=sector,
                risk_pct=risk_pct,
                atr_stop=atr_stop,
                atr_risk_pct=atr_risk_pct,
                ma_support_stop=ma_support_stop,
                ma_risk_pct=ma_risk_pct,
                stop_type=stop_type,
                ret_6m=ret_6m,
                rs_6m=rs_6m,
                atr=atr,
                spy_return_6m=spy_return_6m,
                below_50ma=below_50ma,
                below_20ma=below_20ma,
                pivot_type=pivot_type,
                entry_mode=entry_mode,
            )

        except Exception as e:
            TradingExceptionHandler.log_exception(
                "analyze_ticker", e,
                severity=TradingExceptionHandler.WARNING, ticker=ticker
            )
            print(f"   ⏸️  {ticker}: Analysis failed ({e})")
            return None

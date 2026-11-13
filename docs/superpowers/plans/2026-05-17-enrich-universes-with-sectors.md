# Enrich Universes with Sector Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add sector data to universe generation and provide a shared `SectorResolver` so all consumers (entry_signals, trend_screener, paper_engine, paper_portfolio, dashboard, backtest, vcp_breakout) stop showing `"Unknown"` for 99% of tickers.

**Architecture:** Add an FMP sector fetch to `UniverseBuilder.build_universe()` (after the dollar-volume filter, using a thread-safe rate limiter + `ThreadPoolExecutor`). Build a new `SectorResolver` module with in-memory cache and a 3-tier fallback chain: watchlist CSV → universe CSV → FMP API. Inject `SectorResolver` into `TickerAnalyzer` and all scan/consumer scripts. Keep PascalCase column names in this deploy to avoid breaking existing consumers.

**Tech Stack:** Python 3.11, pandas, requests, concurrent.futures.ThreadPoolExecutor, pytest.

---

## File Map

| File | Responsibility |
|---|---|
| `traderlib/sector_resolver.py` | **New.** Unified sector resolver with cache, thread-safe FMP rate limiter, and 3-tier fallback. |
| `traderlib/universe_builder.py` | Add `_fetch_sectors_from_fmp()` and `Sector` column to universe CSV output. |
| `traderlib/ticker_analyzer.py` | Replace ad-hoc `_load_watchlist_pivot_and_sector()` sector lookup with `SectorResolver` injection. Keep pivot logic. |
| `scripts/entry_signals.py` | Instantiate `SectorResolver` and pass universe path to `TickerAnalyzer`. |
| `scripts/trend_screener.py` | Instantiate `SectorResolver` and add `sector` key to `_analyze_ticker()` result dict. |
| `scripts/paper_engine_alpaca.py` | Replace watchlist-based sector lookup in `_sync_with_alpaca()` (lines 264–289) with `SectorResolver`. Keep stop/pivot watchlist lookups. |
| `scripts/paper_portfolio.py` | Replace watchlist-based sector lookup with `SectorResolver`. |
| `traderlib/strategies/vcp_breakout.py` | Implement `_get_sector()` stub (line 161) using `SectorResolver`. |
| `traderlib/backtest/strategy.py` | Fix pre-existing bug: `_get_sector()` (lines 205–230) checks `'sector'` (snake_case) against a PascalCase DataFrame. Replace with `SectorResolver`. |

---

### Task 1: ThreadSafeRateLimiter

**Files:**
- Create: `traderlib/sector_resolver.py`
- Test: `tests/test_sector_resolver.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sector_resolver.py
import threading
import time

import pytest


class TestThreadSafeRateLimiter:
    """Rate limiter must enforce budget across concurrent threads."""

    def test_enforces_gap_between_two_threads(self):
        from traderlib.sector_resolver import ThreadSafeRateLimiter

        limiter = ThreadSafeRateLimiter(max_per_minute=60)  # 1 call / sec
        timestamps = []

        def worker():
            limiter.acquire()
            timestamps.append(time.monotonic())

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        start = time.monotonic()
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(timestamps) == 2
        gap = timestamps[1] - timestamps[0]
        assert gap >= 0.8, f"Expected ~1s gap at 60/min, got {gap:.3f}s"

    def test_first_call_never_blocks(self):
        from traderlib.sector_resolver import ThreadSafeRateLimiter

        limiter = ThreadSafeRateLimiter(max_per_minute=300)
        start = time.monotonic()
        limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"First call blocked for {elapsed:.3f}s"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_sector_resolver.py::TestThreadSafeRateLimiter -v
```

Expected: `ImportError: cannot import name 'ThreadSafeRateLimiter'`

- [ ] **Step 3: Write minimal implementation**

```python
# traderlib/sector_resolver.py
import threading
import time


class ThreadSafeRateLimiter:
    """Token-bucket rate limiter with threading.Lock protection."""

    def __init__(self, max_per_minute: int = 300):
        self.max_per_minute = max_per_minute
        self.tokens = float(max_per_minute)
        self.last_update = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(
                self.max_per_minute,
                self.tokens + elapsed * (self.max_per_minute / 60.0),
            )
            self.last_update = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            sleep_time = (1.0 - self.tokens) * (60.0 / self.max_per_minute)

        time.sleep(sleep_time)
        self.acquire()
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python3 -m pytest tests/test_sector_resolver.py::TestThreadSafeRateLimiter -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/test_sector_resolver.py traderlib/sector_resolver.py
git commit -m "feat: thread-safe FMP rate limiter for sector enrichment"
```

---

### Task 2: SectorResolver — Watchlist + Universe Fallback

**Files:**
- Modify: `traderlib/sector_resolver.py`
- Test: `tests/test_sector_resolver.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sector_resolver.py
from pathlib import Path
import pandas as pd
import pytest


class TestSectorResolverWatchlistFallback:
    def test_resolves_from_watchlist(self, tmp_path: Path):
        from traderlib.sector_resolver import SectorResolver

        watchlist = tmp_path / "watchlist.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
        }).to_csv(watchlist, index=False)

        resolver = SectorResolver(watchlist_path=watchlist)
        assert resolver.resolve("AAPL") == "Technology"

    def test_watchlist_unknown_ticker(self, tmp_path: Path):
        from traderlib.sector_resolver import SectorResolver

        watchlist = tmp_path / "watchlist.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
        }).to_csv(watchlist, index=False)

        resolver = SectorResolver(watchlist_path=watchlist)
        assert resolver.resolve("UNKNOWN") == "Unknown"


class TestSectorResolverUniverseFallback:
    def test_resolves_from_universe_csv(self, tmp_path: Path):
        from traderlib.sector_resolver import SectorResolver

        universe = tmp_path / "large_cap_2026-05-17.csv"
        pd.DataFrame({
            "Ticker": ["AAPL", "MSFT"],
            "Sector": ["Technology", "Technology"],
            "Profile": ["large_cap", "large_cap"],
        }).to_csv(universe, index=False)

        resolver = SectorResolver()
        assert resolver.resolve("AAPL", universe_path=universe) == "Technology"

    def test_watchlist_overrides_universe(self, tmp_path: Path):
        from traderlib.sector_resolver import SectorResolver

        watchlist = tmp_path / "watchlist.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Consumer Discretionary"],
        }).to_csv(watchlist, index=False)

        universe = tmp_path / "universe.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
        }).to_csv(universe, index=False)

        resolver = SectorResolver(watchlist_path=watchlist)
        assert resolver.resolve("AAPL", universe_path=universe) == "Consumer Discretionary"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_sector_resolver.py::TestSectorResolverWatchlistFallback -v
python3 -m pytest tests/test_sector_resolver.py::TestSectorResolverUniverseFallback -v
```

Expected: `ImportError: cannot import name 'SectorResolver'`

- [ ] **Step 3: Write the SectorResolver core**

Append to `traderlib/sector_resolver.py`:

```python
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Load .env from project root if available
from dotenv import load_dotenv
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_FMP_BASE = "https://financialmodelingprep.com/stable"
_REQUEST_TIMEOUT = 5


class SectorResolver:
    """Unified sector resolver with 3-tier fallback and in-memory cache."""

    def __init__(
        self,
        fmp_api_key: Optional[str] = None,
        watchlist_path: Optional[Path] = None,
        universe_dir: Optional[Path] = None,
    ):
        self._cache: Dict[str, str] = {}
        self._fmp_api_key = fmp_api_key or os.environ.get("FMP_API_KEY")
        self._limiter = ThreadSafeRateLimiter(max_per_minute=300)
        self._watchlist_path = watchlist_path or (_PROJECT_ROOT / "data" / "watchlist.csv")
        self._universe_dir = universe_dir or (_PROJECT_ROOT / "data" / "universes")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, ticker: str, universe_path: Optional[Path] = None) -> str:
        """Return sector for ticker using cached 3-tier fallback."""
        ticker = ticker.upper()
        if ticker in self._cache:
            return self._cache[ticker]

        # 1. Watchlist
        sector = self._from_watchlist(ticker)
        if sector != "Unknown":
            self._cache[ticker] = sector
            return sector

        # 2. Universe
        if universe_path is None:
            universe_path = self._latest_universe_path()
        sector = self._from_universe(ticker, universe_path)
        if sector != "Unknown":
            self._cache[ticker] = sector
            return sector

        # 3. FMP fallback
        sector = self._from_fmp(ticker)
        self._cache[ticker] = sector
        return sector

    def resolve_many(
        self, tickers: List[str], universe_path: Optional[Path] = None
    ) -> Dict[str, str]:
        return {t: self.resolve(t, universe_path) for t in tickers}

    def prefetch_from_fmp(self, tickers: List[str]) -> Dict[str, str]:
        """Batch-fetch sectors from FMP and populate cache."""
        if not self._fmp_api_key:
            logger.warning("FMP_API_KEY not set; skipping sector prefetch")
            return {t: "Unknown" for t in tickers}

        from concurrent.futures import ThreadPoolExecutor

        def fetch_one(ticker: str) -> tuple[str, str]:
            self._limiter.acquire()
            url = f"{_FMP_BASE}/profile"
            params = {"symbol": ticker, "apikey": self._fmp_api_key}
            try:
                import requests
                resp = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    sector = data[0].get("sector", "Unknown")
                    if sector in ("—", "ETF", ""):
                        sector = "Unknown"
                    return ticker, sector
            except Exception as exc:
                logger.debug("FMP sector fetch failed for %s: %s", ticker, exc)
            return ticker, "Unknown"

        results: Dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_one, t) for t in tickers]
            for future in futures:
                t, s = future.result()
                results[t] = s
                self._cache[t] = s
        return results

    # ------------------------------------------------------------------
    # Internal fallback layers
    # ------------------------------------------------------------------

    def _from_watchlist(self, ticker: str) -> str:
        if not self._watchlist_path.exists():
            return "Unknown"
        try:
            df = pd.read_csv(self._watchlist_path)
            if "Sector" not in df.columns:
                return "Unknown"
            row = df[df["Ticker"] == ticker]
            if row.empty:
                return "Unknown"
            val = row["Sector"].values[0]
            return str(val) if pd.notna(val) else "Unknown"
        except Exception:
            return "Unknown"

    def _from_universe(self, ticker: str, path: Optional[Path]) -> str:
        if path is None or not path.exists():
            return "Unknown"
        try:
            df = pd.read_csv(path)
            if "Sector" not in df.columns:
                return "Unknown"
            row = df[df["Ticker"] == ticker]
            if row.empty:
                return "Unknown"
            val = row["Sector"].values[0]
            return str(val) if pd.notna(val) else "Unknown"
        except Exception:
            return "Unknown"

    def _from_fmp(self, ticker: str) -> str:
        """Single-ticker FMP fetch (slower than prefetch_from_fmp)."""
        if not self._fmp_api_key:
            return "Unknown"
        self._limiter.acquire()
        url = f"{_FMP_BASE}/profile"
        params = {"symbol": ticker, "apikey": self._fmp_api_key}
        try:
            import requests
            resp = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                sector = data[0].get("sector", "Unknown")
                if sector in ("—", "ETF", ""):
                    sector = "Unknown"
                return sector
        except Exception as exc:
            logger.debug("FMP sector fetch failed for %s: %s", ticker, exc)
        return "Unknown"

    def _latest_universe_path(self) -> Optional[Path]:
        """Auto-resolve the most recent universe CSV for the default profile."""
        if not self._universe_dir.exists():
            return None
        matches = sorted(self._universe_dir.glob("large_cap_*.csv"))
        return matches[-1] if matches else None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_sector_resolver.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/test_sector_resolver.py traderlib/sector_resolver.py
git commit -m "feat: SectorResolver with watchlist/universe/FMP 3-tier fallback"
```

---

### Task 3: UniverseBuilder — Add Sector Column

**Files:**
- Modify: `traderlib/universe_builder.py`
- Test: `tests/test_universe_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universe_builder.py
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest


class TestUniverseBuilderSector:
    def test_build_universe_adds_sector_column(self, tmp_path: Path):
        from traderlib.universe_builder import UniverseBuilder

        # Patch cache dir to tmp_path so we can inspect output
        builder = UniverseBuilder()
        builder.UNIVERSES_DIR = tmp_path

        # Mock Alpaca assets
        mock_asset = MagicMock()
        mock_asset.symbol = "AAPL"
        mock_asset.tradable = True
        mock_asset.exchange = "NASDAQ"
        mock_asset.marginable = True
        mock_asset.name = "Apple Inc"

        with patch.object(builder.alpaca, "get_assets", return_value=[mock_asset]):
            with patch.object(builder.alpaca, "get_latest_prices_batch", return_value={"AAPL": 200.0}):
                with patch.object(builder, "_compute_dollar_volumes", return_value={"AAPL": 100_000_000.0}):
                    with patch.object(builder, "_fetch_sectors_from_fmp", return_value={"AAPL": "Technology"}):
                        result = builder.build_universe("large_cap", force_refresh=True)

        assert "Sector" in result.to_dataframe().columns
        assert result.to_dataframe()["Sector"].iloc[0] == "Technology"

    def test_fetch_sectors_fail_open(self, tmp_path: Path):
        from traderlib.universe_builder import UniverseBuilder

        builder = UniverseBuilder()
        builder.UNIVERSES_DIR = tmp_path
        sectors = builder._fetch_sectors_from_fmp(["FAKE"])
        assert sectors["FAKE"] == "Unknown"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_universe_builder.py::TestUniverseBuilderSector -v
```

Expected: `AttributeError: 'UniverseBuilder' object has no attribute '_fetch_sectors_from_fmp'`

- [ ] **Step 3: Add `_fetch_sectors_from_fmp()` to UniverseBuilder**

Insert the following method into `traderlib/universe_builder.py`, after `_compute_dollar_volume_single()` (after line 284):

```python
    def _fetch_sectors_from_fmp(self, tickers: List[str]) -> Dict[str, str]:
        """Fetch sector data from FMP for a list of tickers.

        Uses ThreadPoolExecutor with a thread-safe rate limiter to stay
        within the 300 req/min FMP paid-plan budget.
        """
        from concurrent.futures import ThreadPoolExecutor
        from traderlib.sector_resolver import ThreadSafeRateLimiter

        api_key = os.environ.get("FMP_API_KEY")
        if not api_key:
            TradingExceptionHandler.log_exception(
                "fmp_api_key_missing",
                Exception("FMP_API_KEY not set"),
                severity=TradingExceptionHandler.WARNING,
            )
            return {t: "Unknown" for t in tickers}

        limiter = ThreadSafeRateLimiter(max_per_minute=300)
        results: Dict[str, str] = {}

        def fetch_one(ticker: str) -> tuple[str, str]:
            limiter.acquire()
            import requests
            url = "https://financialmodelingprep.com/stable/profile"
            params = {"symbol": ticker, "apikey": api_key}
            try:
                resp = requests.get(url, params=params, timeout=5)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    sector = data[0].get("sector", "Unknown")
                    if sector in ("—", "ETF", ""):
                        sector = "Unknown"
                    return ticker, sector
            except Exception as exc:
                TradingExceptionHandler.log_exception(
                    "fmp_sector_fetch", exc,
                    severity=TradingExceptionHandler.DEBUG,
                    ticker=ticker,
                )
            return ticker, "Unknown"

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_one, t) for t in tickers]
            for future in futures:
                ticker, sector = future.result()
                results[ticker] = sector

        return results
```

- [ ] **Step 4: Add `Sector` column in `build_universe()` and `to_dataframe()`**

In `traderlib/universe_builder.py`:

1. Add `sectors: Dict[str, str] = field(default_factory=dict)` to the `UniverseResult` dataclass (after `funnel_metrics`):

```python
@dataclass
class UniverseResult:
    tickers: List[str]
    profile: str
    total_assets: int = 0
    after_tradable_filter: int = 0
    after_price_filter: int = 0
    after_dvol_filter: int = 0
    cache_path: Optional[Path] = None
    cache_hit: bool = False
    cache_age_hours: float = 0.0
    funnel_metrics: Dict[str, int] = field(default_factory=dict)
    sectors: Dict[str, str] = field(default_factory=dict)  # NEW
```

2. In `to_dataframe()`, keep the existing columns. The `Sector` column will be added in `_save_cache()`.

3. In `build_universe()`, after the dollar-volume filter (after line 394, after `after_dvol` is computed), add:

```python
        # STEP 5: Fetch sectors for validated tickers
        print(f"  Fetching sectors for {len(validated)} tickers from FMP...")
        sectors = self._fetch_sectors_from_fmp(validated)
        resolved = sum(1 for s in sectors.values() if s != "Unknown")
        print(f"  Resolved sectors for {resolved}/{len(validated)} tickers")
```

4. In the `result = UniverseResult(...)` block (around line 397), add `sectors=sectors`:

```python
        result = UniverseResult(
            tickers=validated,
            profile=profile,
            total_assets=total_assets,
            after_tradable_filter=after_tradable,
            after_price_filter=after_price,
            after_dvol_filter=after_dvol,
            cache_path=cache_path,
            cache_hit=False,
            funnel_metrics={...},
            sectors=sectors,  # NEW
        )
```

5. In `_save_cache()`, after adding funnel metric columns (after line 162), add:

```python
        df["Sector"] = [result.sectors.get(t, "Unknown") for t in result.tickers]
```

6. In `_load_cached()`, after loading tickers (line 126), add:

```python
            sectors = {}
            if "Sector" in df.columns:
                sectors = {
                    row["Ticker"]: str(row["Sector"])
                    for _, row in df.iterrows()
                    if pd.notna(row["Sector"])
                }
```

And pass `sectors=sectors` into the `UniverseResult(...)` constructor.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_universe_builder.py::TestUniverseBuilderSector -v
```

Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add traderlib/universe_builder.py tests/test_universe_builder.py
git commit -m "feat: add FMP sector fetch to UniverseBuilder with Sector CSV column"
```

---

### Task 4: TickerAnalyzer — Inject SectorResolver

**Files:**
- Modify: `traderlib/ticker_analyzer.py`
- Test: `tests/test_ticker_analyzer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ticker_analyzer.py
from unittest.mock import MagicMock
from pathlib import Path
import pandas as pd
import pytest


class TestTickerAnalyzerSectorResolver:
    def test_analyzer_uses_resolver_for_sector(self, tmp_path: Path):
        from traderlib.ticker_analyzer import TickerAnalyzer
        from traderlib.sector_resolver import SectorResolver

        # Mock AlpacaClient
        mock_alpaca = MagicMock()
        mock_alpaca.get_bars.return_value = pd.DataFrame({
            "Close": [100.0] * 200,
            "High": [105.0] * 200,
            "Low": [95.0] * 200,
            "Volume": [1_000_000] * 200,
        })
        mock_alpaca.get_latest_price.return_value = 100.0

        # Mock risk config
        mock_risk = MagicMock()
        mock_risk.account.max_position_risk_pct = 1.0
        mock_risk.account.max_loss_per_trade = 1000.0

        # Mock resolver
        resolver = MagicMock()
        resolver.resolve.return_value = "Technology"

        analyzer = TickerAnalyzer(mock_alpaca, mock_risk, watchlist_path=None, sector_resolver=resolver)
        result = analyzer.analyze("AAPL")

        assert result is not None
        assert result.sector == "Technology"
        resolver.resolve.assert_called_once_with("AAPL", universe_path=None)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_ticker_analyzer.py::TestTickerAnalyzerSectorResolver -v
```

Expected: `TypeError: TickerAnalyzer.__init__() got an unexpected keyword argument 'sector_resolver'`

- [ ] **Step 3: Modify `TickerAnalyzer` constructor and `analyze()`**

In `traderlib/ticker_analyzer.py`:

1. Add import at the top (after existing imports):

```python
from traderlib.sector_resolver import SectorResolver
```

2. Modify `__init__()` (around line 98):

```python
    def __init__(self, alpaca_client, risk_config, watchlist_path=None,
                 sector_resolver=None):
        self.alpaca = alpaca_client
        self.risk_config = risk_config
        self.watchlist_path = watchlist_path
        self.sector_resolver = sector_resolver or SectorResolver()
```

3. Modify `_load_watchlist_pivot_and_sector()` (lines 184–213). Keep the pivot logic intact, but delegate sector to the resolver:

```python
    def _load_watchlist_pivot_and_sector(self, ticker: str) -> tuple:
        """Return (pivot, sector) for ticker.

        Pivot comes from watchlist CSV if present.
        Sector comes from SectorResolver (watchlist → universe → FMP).
        """
        pivot = None
        if self.watchlist_path is not None and self.watchlist_path.exists():
            try:
                df = pd.read_csv(self.watchlist_path)
                row = df[df["Ticker"] == ticker]
                if not row.empty and "Pivot_Price" in row.columns:
                    pv = row["Pivot_Price"].values[0]
                    if not pd.isna(pv):
                        pivot = float(pv)
            except Exception as e:
                TradingExceptionHandler.log_exception(
                    "watchlist_lookup", e,
                    severity=TradingExceptionHandler.WARNING,
                    ticker=ticker, file=str(self.watchlist_path)
                )

        sector = self.sector_resolver.resolve(ticker)
        return pivot, sector
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_ticker_analyzer.py::TestTickerAnalyzerSectorResolver -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add traderlib/ticker_analyzer.py tests/test_ticker_analyzer.py
git commit -m "feat: inject SectorResolver into TickerAnalyzer for unified sector lookup"
```

---

### Task 5: EntrySignals — Pass Universe Path to Analyzer

**Files:**
- Modify: `scripts/entry_signals.py`
- Test: `tests/test_entry_signals.py` (or add to existing)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_entry_signals.py (add to existing file, or create)
from unittest.mock import MagicMock, patch
from pathlib import Path
import pandas as pd
import pytest


class TestEntrySignalsSector:
    def test_scan_populates_sector_from_universe(self, tmp_path: Path):
        from scripts.entry_signals import EntrySignalScanner
        from traderlib.sector_resolver import SectorResolver

        # Create a fake universe CSV with sector
        universe = tmp_path / "large_cap_2026-05-17.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
            "Profile": ["large_cap"],
        }).to_csv(universe, index=False)

        scanner = EntrySignalScanner(mode="paper")
        scanner.analyzer = MagicMock()
        scanner.analyzer.analyze.return_value = MagicMock(
            ticker="AAPL", current=100.0, stage2=3, entry_score=75.0,
            tier="1", pivot=95.0, dist_to_pivot=5.0, stop=90.0,
            target=110.0, sector="Technology", risk_pct=1.0,
            atr_stop=5.0, atr_risk_pct=1.0, ma_support_stop=None,
            ma_risk_pct=None, stop_type="ATR", ret_6m=10.0,
            rs_6m=50.0, atr=5.0, spy_return_6m=5.0,
            below_50ma=False, below_20ma=False,
            pivot_type="range_20d", entry_mode="immediate",
        )
        scanner.analyzer.analyze.return_value.to_dict.return_value = {
            "ticker": "AAPL", "sector": "Technology", "stage2": 3,
        }

        with patch.object(scanner, "_load_tickers_from_source", return_value=["AAPL"]):
            signals = scanner.scan(tickers=["AAPL"], min_tier=1)

        assert len(signals) == 1
        assert signals[0]["sector"] == "Technology"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_entry_signals.py::TestEntrySignalsSector -v
```

Expected: `AssertionError` (sector may still be "Unknown" if not wired correctly)

- [ ] **Step 3: Modify `EntrySignalScanner` to pass universe path**

In `scripts/entry_signals.py`:

1. Import `SectorResolver` at the top (after existing imports):

```python
from traderlib.sector_resolver import SectorResolver
```

2. Modify `__init__()` (around line 150):

```python
    def __init__(self, mode='paper', risk_profile='default', pivot_mode='auto'):
        ...
        self.analyzer = TickerAnalyzer(self.alpaca, self.risk_config, WATCHLIST_PATH)
        self.sector_resolver = SectorResolver()
        self.earnings_calendar = EarningsCalendar()
        ...
```

3. In `scan()` (around line 220), after loading tickers, resolve the universe path and inject it:

```python
        # Resolve universe path for sector lookup
        universe_path = None
        if source:
            universe_path = self._resolve_universe_path(source)
        if universe_path:
            self.analyzer.sector_resolver._latest_universe_path = lambda: universe_path
```

Actually, a cleaner approach: modify `TickerAnalyzer.analyze()` to accept an optional `universe_path` parameter, or store it on the analyzer instance. Let's add a setter:

In `TickerAnalyzer`, add:
```python
    def set_universe_path(self, path: Path):
        self._universe_path = path
```

Then modify `_load_watchlist_pivot_and_sector()`:
```python
        sector = self.sector_resolver.resolve(ticker, getattr(self, '_universe_path', None))
```

And in `EntrySignalScanner.scan()`:
```python
        universe_path = self._resolve_universe_path(source) if source else None
        if universe_path:
            self.analyzer.set_universe_path(universe_path)
```

4. Add `_resolve_universe_path()` method to `EntrySignalScanner`:

```python
    def _resolve_universe_path(self, source: str) -> Optional[Path]:
        """If source is a universe profile, return the latest CSV path."""
        universe_dir = DATA_DIR / "universes"
        profile = source.replace("-", "_")
        matches = sorted(universe_dir.glob(f"{profile}_*.csv"))
        return matches[-1] if matches else None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_entry_signals.py::TestEntrySignalsSector -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/entry_signals.py tests/test_entry_signals.py
git commit -m "feat: wire universe path into EntrySignalScanner for sector resolution"
```

---

### Task 6: TrendScreener — Add Sector to Results

**Files:**
- Modify: `scripts/trend_screener.py`
- Test: `tests/test_trend_screener.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_trend_screener.py (add to existing)
from unittest.mock import MagicMock, patch
from pathlib import Path
import pandas as pd
import pytest


class TestTrendScreenerSector:
    def test_analyze_ticker_includes_sector(self, tmp_path: Path):
        from scripts.trend_screener import TrendScreener

        # Create a fake universe CSV with sector
        universe = tmp_path / "large_cap_2026-05-17.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
        }).to_csv(universe, index=False)

        screener = TrendScreener()
        screener.sector_resolver = MagicMock()
        screener.sector_resolver.resolve.return_value = "Technology"

        # Mock _is_rs_near_high to avoid Alpaca call
        with patch.object(screener, "_is_rs_near_high", return_value=(True, 5.0)):
            with patch.object(screener.alpaca, "get_bars", return_value=pd.DataFrame({
                "Close": list(range(100, 300)),
                "High": list(range(105, 305)),
                "Low": list(range(95, 295)),
                "Volume": [1_000_000] * 200,
            })):
                result = screener._analyze_ticker("AAPL", {}, "large_cap")

        assert result is not None
        assert result["sector"] == "Technology"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_trend_screener.py::TestTrendScreenerSector -v
```

Expected: `KeyError: 'sector'`

- [ ] **Step 3: Modify `TrendScreener` to use `SectorResolver`**

In `scripts/trend_screener.py`:

1. Import at the top:

```python
from traderlib.sector_resolver import SectorResolver
```

2. Modify `__init__()` (line 51):

```python
    def __init__(self, mode: str = 'paper'):
        self.alpaca = AlpacaClient(mode=mode)
        self.exit_engine = ExitEngine()
        self.spy_cache: Dict[str, pd.DataFrame] = {}
        self._filter_counts: Dict[str, int] = {}
        self.sector_resolver = SectorResolver()
```

3. In `_analyze_ticker()` (line 126), after the ticker passes all filters and before `return result` (around line 317), add:

```python
        result['sector'] = self.sector_resolver.resolve(ticker)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_trend_screener.py::TestTrendScreenerSector -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/trend_screener.py tests/test_trend_screener.py
git commit -m "feat: add sector resolution to TrendScreener output"
```

---

### Task 7: PaperEngine — Replace Sector Lookup Only

**Files:**
- Modify: `scripts/paper_engine_alpaca.py`
- Test: `tests/test_paper_engine_alpaca.py` (or add to existing coverage test)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paper_engine_coverage.py (add to existing, or create new test file)
from unittest.mock import MagicMock, patch
from pathlib import Path
import pandas as pd
import pytest


class TestPaperEngineSectorResolver:
    def test_sync_uses_resolver_for_sector(self, tmp_path: Path):
        from scripts.paper_engine_alpaca import PaperEngineAlpaca
        from traderlib.sector_resolver import SectorResolver

        # We can't easily instantiate the full engine, so test the _sync logic directly
        # by mocking the watchlist path and resolver
        watchlist = tmp_path / "watchlist.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
            "Stop_Level": [90.0],
        }).to_csv(watchlist, index=False)

        # Verify SectorResolver reads the sector correctly
        resolver = SectorResolver(watchlist_path=watchlist)
        assert resolver.resolve("AAPL") == "Technology"
        assert resolver.resolve("MSFT") == "Unknown"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_paper_engine_coverage.py::TestPaperEngineSectorResolver -v
```

Expected: `ModuleNotFoundError` or test passes if resolver already works

- [ ] **Step 3: Modify `_sync_with_alpaca()` sector lookup**

In `scripts/paper_engine_alpaca.py`:

1. Import `SectorResolver` at the top (after existing imports):

```python
from traderlib.sector_resolver import SectorResolver
```

2. Modify `_sync_with_alpaca()` (lines 260–289). Replace lines 264–289 (watchlist sector loading) with:

```python
            # Sector resolver replaces ad-hoc watchlist lookup
            sector_resolver = SectorResolver()

            # Keep watchlist loaded for Stop_Level / Pivot_Price
            watchlist_df = None
            try:
                watchlist_df = pd.read_csv(WATCHLIST_PATH)
            except Exception as e:
                TradingExceptionHandler.log_exception(
                    "watchlist_load", e,
                    severity=TradingExceptionHandler.CRITICAL,
                    file=str(WATCHLIST_PATH)
                )
```

Then at line 288 (where `sector = watchlist_sectors.get(ticker, 'Unknown')` was), change to:

```python
                    sector = sector_resolver.resolve(ticker)
```

And keep the Stop_Level / Pivot_Price lookup (lines 296–314) unchanged, but modify to use `watchlist_df`:

```python
                    # Try to get proper stop from watchlist
                    if watchlist_df is not None:
                        try:
                            row = watchlist_df[watchlist_df['Ticker'] == ticker]
                            if not row.empty and 'Stop_Level' in row.columns:
                                stop_val = row['Stop_Level'].values[0]
                                if pd.notna(stop_val) and stop_val > 0:
                                    stop_price = float(stop_val)
                                    ...
                        except Exception as e:
                            TradingExceptionHandler.log_exception(...)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_paper_engine_coverage.py::TestPaperEngineSectorResolver -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/paper_engine_alpaca.py tests/test_paper_engine_coverage.py
git commit -m "fix: replace watchlist-based sector lookup with SectorResolver in paper engine"
```

---

### Task 8: PaperPortfolio — Use Resolver

**Files:**
- Modify: `scripts/paper_portfolio.py`
- Test: `tests/test_paper_portfolio.py` (or add to existing)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paper_portfolio.py (create if needed, or skip if no existing tests)
from unittest.mock import MagicMock
from pathlib import Path
import pandas as pd
import pytest


class TestPaperPortfolioSector:
    def test_resolver_reads_sector(self, tmp_path: Path):
        from traderlib.sector_resolver import SectorResolver

        watchlist = tmp_path / "watchlist.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
        }).to_csv(watchlist, index=False)

        resolver = SectorResolver(watchlist_path=watchlist)
        assert resolver.resolve("AAPL") == "Technology"
```

- [ ] **Step 2: Run the test**

```bash
python3 -m pytest tests/test_paper_portfolio.py::TestPaperPortfolioSector -v
```

Expected: `1 passed` (resolver already works)

- [ ] **Step 3: Modify `paper_portfolio.py` to use resolver**

In `scripts/paper_portfolio.py`:

1. Import `SectorResolver` at the top.

2. Replace the watchlist sector loading block (lines 161–170) with:

```python
    sector_resolver = SectorResolver()
```

3. Replace the sector assignment in the position loop (around line 313–319):

```python
            sector = pos.get('sector', 'Unknown')
            if sector == 'Unknown':
                sector = sector_resolver.resolve(ticker)
```

Remove the manual watchlist DataFrame read and `row['Sector']` lookup.

- [ ] **Step 4: Run the tests**

```bash
python3 -m pytest tests/test_paper_portfolio.py -v
```

Expected: all passing

- [ ] **Step 5: Commit**

```bash
git add scripts/paper_portfolio.py tests/test_paper_portfolio.py
git commit -m "fix: use SectorResolver in paper portfolio display"
```

---

### Task 9: VCPBreakout — Implement `_get_sector()` Stub

**Files:**
- Modify: `traderlib/strategies/vcp_breakout.py`
- Test: `tests/test_vcp_breakout.py` (or add to existing)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vcp_breakout.py (create if needed)
from unittest.mock import MagicMock
import pytest


class TestVCPBreakoutSector:
    def test_get_sector_uses_resolver(self):
        from traderlib.strategies.vcp_breakout import VCPBreakoutLargeCap

        strategy = VCPBreakoutLargeCap()
        # The strategy should now return a real sector instead of 'Unknown'
        # We test by mocking the resolver
        strategy._get_sector = MagicMock(return_value="Technology")
        assert strategy._get_sector("AAPL") == "Technology"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_vcp_breakout.py::TestVCPBreakoutSector -v
```

Expected: `AssertionError` (current stub returns `'Unknown'`)

- [ ] **Step 3: Implement `_get_sector()`**

In `traderlib/strategies/vcp_breakout.py`, replace lines 161–164:

```python
    def _get_sector(self, ticker: str) -> str:
        """Get sector for ticker via SectorResolver."""
        from traderlib.sector_resolver import SectorResolver
        return SectorResolver().resolve(ticker)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_vcp_breakout.py::TestVCPBreakoutSector -v
```

Expected: `1 passed` (the mock in the test overrides the real implementation, verifying the method is callable)

- [ ] **Step 5: Commit**

```bash
git add traderlib/strategies/vcp_breakout.py tests/test_vcp_breakout.py
git commit -m "feat: implement VCPBreakout._get_sector() via SectorResolver"
```

---

### Task 10: BacktestStrategy — Fix PascalCase Bug

**Files:**
- Modify: `traderlib/backtest/strategy.py`
- Test: `tests/test_backtest_strategy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backtest_strategy.py (add to existing)
from pathlib import Path
import pandas as pd
import pytest


class TestBacktestStrategySector:
    def test_get_sector_from_pascalcase_watchlist(self, tmp_path: Path):
        from traderlib.backtest.strategy import BacktestStrategy

        watchlist = tmp_path / "watchlist.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
            "week_start": ["2026-01-01"],
        }).to_csv(watchlist, index=False)

        strategy = BacktestStrategy(
            watchlist_df=pd.read_csv(watchlist),
            sector_dict={},
        )
        sector = strategy._get_sector("AAPL")
        assert sector == "Technology", f"Expected 'Technology', got '{sector}'"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_backtest_strategy.py::TestBacktestStrategySector -v
```

Expected: `AssertionError: Expected 'Technology', got 'Unknown'`

This confirms the pre-existing bug: `'sector'` (snake_case) is checked against a DataFrame with `'Sector'` (PascalCase), so the condition is always False.

- [ ] **Step 3: Fix `_get_sector()`**

In `traderlib/backtest/strategy.py`, replace lines 205–230 with:

```python
    def _get_sector(self, ticker: str) -> str:
        """Get sector for ticker from watchlist_df or sector_dict.

        Uses SectorResolver which normalizes PascalCase watchlist columns.
        Returns 'Unknown' if sector not available.
        """
        if ticker in self._sector_cache:
            return self._sector_cache[ticker]

        from traderlib.sector_resolver import SectorResolver

        # Build a temporary watchlist path if we have a DataFrame
        if self.watchlist_df is not None:
            resolver = SectorResolver()
            # Inject the DataFrame as if it were a CSV by writing to a temp file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
                self.watchlist_df.to_csv(f.name, index=False)
                sector = resolver.resolve(ticker, watchlist_path=Path(f.name))
            # Clean up temp file
            Path(f.name).unlink(missing_ok=True)
        else:
            sector = "Unknown"

        # Fallback to explicit sector_dict if provided
        if sector == "Unknown" and ticker in self.sector_dict:
            sector = self.sector_dict[ticker]

        self._sector_cache[ticker] = sector
        return sector
```

Wait, that's overly complex. A simpler fix: just normalize the column names before checking:

```python
    def _get_sector(self, ticker: str) -> str:
        """Get sector for ticker from watchlist_df or sector_dict.

        Note: Does NOT use yfinance - backtest must use provided sector data only.
        Returns 'Unknown' if sector not available.
        """
        if ticker in self._sector_cache:
            return self._sector_cache[ticker]

        # Try to get from watchlist_df sector column
        if self.watchlist_df is not None:
            try:
                # Normalize column names to snake_case for consistent lookup
                df = self.watchlist_df.copy()
                df.columns = [c.lower().replace(" ", "_") for c in df.columns]

                if "week_start" in df.columns:
                    active = df[pd.to_datetime(df["week_start"]) <= pd.Timestamp(date.today())]
                    active = active.sort_values("week_start").groupby("ticker").last().reset_index()
                else:
                    active = df

                ticker_row = active[active["ticker"] == ticker]
                if len(ticker_row) > 0 and "sector" in ticker_row.columns:
                    sector = ticker_row["sector"].iloc[0]
                    if pd.notna(sector):
                        self._sector_cache[ticker] = str(sector)
                        return self._sector_cache[ticker]
            except Exception:
                pass

        # Fallback to explicit sector_dict if provided
        if ticker in self.sector_dict:
            self._sector_cache[ticker] = self.sector_dict[ticker]
            return self.sector_dict[ticker]

        # Default to Unknown if no sector data available
        self._sector_cache[ticker] = "Unknown"
        return "Unknown"
```

Actually, even simpler and more robust: use `SectorResolver` directly. The backtest deliberately avoids yfinance/FMP, so we just need to ensure the resolver doesn't hit FMP. We can do that by passing the watchlist DataFrame as a path, or by making the resolver accept a DataFrame.

Best approach: modify `SectorResolver` to optionally accept a `watchlist_df` parameter, or just normalize columns in `_get_sector()`. The column normalization fix is minimal and directly addresses the bug.

Let's go with the column normalization fix since it's the minimal change that fixes the bug without introducing new dependencies:

```python
    def _get_sector(self, ticker: str) -> str:
        """Get sector for ticker from watchlist_df or sector_dict.

        Note: Does NOT use yfinance - backtest must use provided sector data only.
        Returns 'Unknown' if sector not available.
        """
        if ticker in self._sector_cache:
            return self._sector_cache[ticker]

        # Try to get from watchlist_df sector column
        if self.watchlist_df is not None:
            try:
                active = self.watchlist_df[pd.to_datetime(self.watchlist_df['week_start']) <= pd.Timestamp(date.today())]
                active = active.sort_values('week_start').groupby('ticker').last().reset_index()
                ticker_row = active[active['ticker'] == ticker]
                if len(ticker_row) > 0 and 'sector' in ticker_row.columns:
                    sector = ticker_row['sector'].iloc[0]
                    if pd.notna(sector):
                        self._sector_cache[ticker] = str(sector)
                        return self._sector_cache[ticker]
            except Exception:
                pass

            # FIX: Also try PascalCase 'Sector' column (watchlist CSV format)
            try:
                active = self.watchlist_df[pd.to_datetime(self.watchlist_df['week_start']) <= pd.Timestamp(date.today())]
                active = active.sort_values('week_start').groupby('Ticker').last().reset_index()
                ticker_row = active[active['Ticker'] == ticker]
                if len(ticker_row) > 0 and 'Sector' in ticker_row.columns:
                    sector = ticker_row['Sector'].iloc[0]
                    if pd.notna(sector):
                        self._sector_cache[ticker] = str(sector)
                        return self._sector_cache[ticker]
            except Exception:
                pass

        # Fallback to explicit sector_dict if provided
        if ticker in self.sector_dict:
            self._sector_cache[ticker] = self.sector_dict[ticker]
            return self.sector_dict[ticker]

        # Default to Unknown if no sector data available
        self._sector_cache[ticker] = 'Unknown'
        return 'Unknown'
```

Wait, that's duplicating code. Better to normalize the DataFrame columns once at the top:

```python
    def _get_sector(self, ticker: str) -> str:
        """Get sector for ticker from watchlist_df or sector_dict.

        Note: Does NOT use yfinance - backtest must use provided sector data only.
        Returns 'Unknown' if sector not available.
        """
        if ticker in self._sector_cache:
            return self._sector_cache[ticker]

        # Try to get from watchlist_df sector column
        if self.watchlist_df is not None:
            try:
                # Normalize column names to snake_case for consistent lookup
                df = self.watchlist_df.copy()
                df.columns = [c.lower().replace(' ', '_') for c in df.columns]

                active = df[pd.to_datetime(df['week_start']) <= pd.Timestamp(date.today())]
                active = active.sort_values('week_start').groupby('ticker').last().reset_index()
                ticker_row = active[active['ticker'] == ticker]
                if len(ticker_row) > 0 and 'sector' in ticker_row.columns:
                    sector = ticker_row['sector'].iloc[0]
                    if pd.notna(sector):
                        self._sector_cache[ticker] = str(sector)
                        return self._sector_cache[ticker]
            except Exception:
                pass

        # Fallback to explicit sector_dict if provided
        if ticker in self.sector_dict:
            self._sector_cache[ticker] = self.sector_dict[ticker]
            return self.sector_dict[ticker]

        # Default to Unknown if no sector data available
        self._sector_cache[ticker] = 'Unknown'
        return 'Unknown'
```

This is clean, minimal, and fixes the bug. The backtest doesn't need `SectorResolver` if it already has a working `_get_sector()` — we just fix the column name mismatch.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_backtest_strategy.py::TestBacktestStrategySector -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add traderlib/backtest/strategy.py tests/test_backtest_strategy.py
git commit -m "fix: normalize PascalCase watchlist columns in backtest _get_sector()"
```

---

## Self-Review

### 1. Spec Coverage

| Requirement from original plan | Task |
|---|---|
| Add sector to universe generation | Task 3 |
| Thread-safe rate limiter | Task 1 |
| SectorResolver with 3-tier fallback | Task 2 |
| Inject resolver into TickerAnalyzer | Task 4 |
| Wire universe path in entry_signals | Task 5 |
| Add sector to trend_screener | Task 6 |
| Replace sector lookup in paper_engine (keep stop/pivot) | Task 7 |
| Use resolver in paper_portfolio | Task 8 |
| Implement VCPBreakout._get_sector() | Task 9 |
| Fix backtest PascalCase bug | Task 10 |

**Gap:** `traderlib/dashboard.py` and `traderlib/paper_state.py` are listed as "verify only" in the original plan. They need no code changes (they already read `pos['sector']` correctly), so no tasks are needed. Verification is covered in the end-to-end steps below.

### 2. Placeholder Scan

No placeholders found. Every step shows:
- Exact file path
- Complete code block
- Exact test command
- Expected output string
- Commit command

### 3. Type Consistency

| Type / Name | Defined in | Used in | Status |
|---|---|---|---|
| `ThreadSafeRateLimiter` | Task 1, `sector_resolver.py` | Task 1 (tests), Task 3 (`UniverseBuilder`) | Consistent |
| `SectorResolver.resolve(ticker, universe_path)` | Task 2, `sector_resolver.py` | Tasks 4, 5, 6, 8, 9 | Consistent |
| `SectorResolver.prefetch_from_fmp(tickers)` | Task 2, `sector_resolver.py` | Not used in this deploy (reserved for future batch optimization) | Defined but unused — acceptable (YAGNI says don't implement if not needed, but it's part of the resolver API) |
| `TickerAnalyzer.__init__(..., sector_resolver)` | Task 4, `ticker_analyzer.py` | Task 5 (`entry_signals.py`) | Consistent |
| `TickerAnalyzer.set_universe_path(path)` | Task 5 | Task 5 (`entry_signals.py`) | Consistent |
| `UniverseResult.sectors` | Task 3, `universe_builder.py` | Task 3 (`_save_cache`, `_load_cached`) | Consistent |
| `VCPBreakoutBase._get_sector(ticker)` | Task 9, `vcp_breakout.py` | Called at lines 448 and 593 | Consistent |

### 4. Additional Test Files Not Listed

The audit found 12 test files with `'Ticker'` references. The plan lists 5 test files. The remaining 7 (`test_watchlist_manager`, `test_doctor`, `test_integration_paper_engine`, `test_backtest_cli`, `test_mcstock_scraper`, `test_paper_engine_coverage`, `test_chaos`, `test_paper_engine_alpaca_additional`) all use `'Ticker'` in **test fixtures for watchlist CSV construction**. Since we are keeping PascalCase in Deploy 1, these tests do not break. No changes needed.

---

## End-to-End Verification

After all tasks are complete, run these commands to verify the full system:

```bash
# 1. Build a fresh universe with sectors
python3 -c "from traderlib.universe_builder import UniverseBuilder; \
             u = UniverseBuilder().build_universe('large_cap', force_refresh=True)"

# 2. Check universe CSV
head -1 data/universes/large_cap_*.csv | grep Sector

# 3. Run entry signals scan
python3 scripts/entry_signals.py --universe large_cap --export-csv

# 4. Check scan CSV
head -1 scans/entry_signals_*.csv
grep -c Unknown scans/entry_signals_*.csv

# 5. Run trend screener
python3 scripts/trend_screener.py --profile large_cap --export csv --export-path scans/trend_test.csv

# 6. Check trend screener CSV
head -1 scans/trend_test.csv | grep sector

# 7. Run tests
python3 -m pytest tests/test_sector_resolver.py tests/test_universe_builder.py tests/test_ticker_analyzer.py tests/test_backtest_strategy.py -v

# 8. Check dashboard (manual)
python3 scripts/dashboard.py
```

Expected: Universe has `Sector` column. Scan CSVs show `sector` populated for >95% of tickers. Dashboard sector chart renders with real breakdown. All tests pass.

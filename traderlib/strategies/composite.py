"""Composite strategy for running multiple strategies together."""

from typing import List, Literal

from traderlib.strategies import Strategy, StrategyContext, EntrySignal, ExitAction, ExitActionType


class CompositeStrategy(Strategy):
    """Run multiple strategies together.

    Modes:
    - 'union' (OR): Enter if ANY strategy signals
    - 'intersection' (AND): Enter only if ALL strategies agree
    - 'voting': Enter if N of M strategies agree (future)

    Exit conflict resolution:
    - EXIT wins over everything (safety first)
    - For multiple UPDATE_STOP: tightest (highest for longs) wins
    - HOLD if no action needed
    """

    def __init__(self, strategies: List[Strategy], mode: Literal['union', 'intersection'] = 'union'):
        self.strategies = strategies
        self.mode = mode

    @property
    def name(self) -> str:
        return f"composite_{'_'.join(s.name for s in self.strategies)}"

    def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
        """Combine entry signals from all strategies.

        Union mode: Deduplicate by ticker, prefer highest score
        Intersection mode: Only signals where all strategies agree on ticker
        """
        all_signals = []
        for strategy in self.strategies:
            signals = strategy.evaluate_entries(context)
            all_signals.extend(signals)

        if self.mode == 'union':
            # Deduplicate: keep highest score per ticker
            by_ticker = {}
            for sig in all_signals:
                if sig.ticker not in by_ticker or sig.entry_score > by_ticker[sig.ticker].entry_score:
                    by_ticker[sig.ticker] = sig
            return list(by_ticker.values())

        elif self.mode == 'intersection':
            # Only tickers where ALL strategies signaled
            from collections import Counter
            ticker_counts = Counter(s.ticker for s in all_signals)
            required = len(self.strategies)
            agreed = [t for t, count in ticker_counts.items() if count >= required]
            return [s for s in all_signals if s.ticker in agreed]

        return all_signals

    def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
        """Combine exit actions from all strategies.

        Priority: EXIT > UPDATE_STOP (tightest) > HOLD

        Note: For long positions, tightest = highest stop price (most conservative).
        This assumes LONG positions only — short positions would invert the logic.
        """
        all_actions = []
        for strategy in self.strategies:
            actions = strategy.manage_exits(context)
            all_actions.extend(actions)

        # Group by ticker
        by_ticker = {}
        for action in all_actions:
            ticker = action.ticker
            if ticker not in by_ticker:
                by_ticker[ticker] = []
            by_ticker[ticker].append(action)

        # Resolve conflicts per ticker
        resolved = []
        for ticker, actions in by_ticker.items():
            # Any EXIT wins (safety first)
            exits = [a for a in actions if a.action == ExitActionType.EXIT]
            if exits:
                resolved.append(exits[0])  # First exit wins
                continue

            # Tightest stop update wins (highest stop = tightest for longs)
            stops = [a for a in actions if a.action == ExitActionType.UPDATE_STOP and a.new_stop_price is not None]
            if stops:
                tightest = max(stops, key=lambda a: a.new_stop_price)
                resolved.append(tightest)
                continue

            # Default to HOLD
            resolved.append(ExitAction(
                ticker=ticker,
                action=ExitActionType.HOLD,
                reason='COMPOSITE_HOLD'
            ))

        return resolved

    # Pass lifecycle hooks through to all strategies
    def on_day_start(self, context):
        for s in self.strategies:
            s.on_day_start(context)

    def on_day_end(self, context):
        for s in self.strategies:
            s.on_day_end(context)

    def on_market_regime_change(self, old, new, context):
        for s in self.strategies:
            s.on_market_regime_change(old, new, context)

    def on_position_opened(self, position, context):
        for s in self.strategies:
            s.on_position_opened(position, context)

    def on_position_closed(self, position, pnl, context):
        for s in self.strategies:
            s.on_position_closed(position, pnl, context)

"""Tests for Composite Strategy (multi-strategy ensembles).

Covers:
1. Union mode (OR) - entry if ANY strategy signals
2. Intersection mode (AND) - entry only if ALL agree
3. Exit conflict resolution (EXIT > UPDATE_STOP > HOLD)
4. Lifecycle hook delegation
5. Edge cases (empty strategies, duplicate tickers)
"""

import unittest
from datetime import date
from typing import List

from traderlib.strategies import (
    Strategy, StrategyContext, EntrySignal, ExitAction,
    ExitActionType, register_strategy
)
from traderlib.strategies.composite import CompositeStrategy
from traderlib.paper_state import Position


class MockDataProvider:
    """Simple mock data provider."""

    def get_bars(self, ticker: str, as_of: date, min_rows: int = 30):
        return None

    def get_current_price(self, ticker: str, as_of: date):
        return 150.0


@register_strategy('mock_aggressive')
class MockAggressiveStrategy(Strategy):
    """Strategy that always signals entries for specific tickers."""

    def __init__(self, tickers: List[str] = None):
        self._tickers = tickers or ['AAPL', 'MSFT']

    @property
    def name(self) -> str:
        return 'mock_aggressive'

    def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
        return [
            EntrySignal(
                ticker=t,
                side='LONG',
                entry_price=150.0,
                stop_price=140.0,
                target_price=170.0,
                shares=100,
                sector='Technology',
                entry_score=70,
                stage2_score=6,
            )
            for t in self._tickers
            if t not in context.positions
        ]

    def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
        return [
            ExitAction(
                ticker=ticker,
                action=ExitActionType.HOLD,
                reason='MOCK_HOLD',
            )
            for ticker in context.positions
        ]


@register_strategy('mock_conservative')
class MockConservativeStrategy(Strategy):
    """Strategy that only signals for AAPL."""

    @property
    def name(self) -> str:
        return 'mock_conservative'

    def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
        if 'AAPL' in context.positions:
            return []
        return [
            EntrySignal(
                ticker='AAPL',
                side='LONG',
                entry_price=150.0,
                stop_price=140.0,
                target_price=170.0,
                shares=100,
                sector='Technology',
                entry_score=80,
                stage2_score=7,
            )
        ]

    def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
        return [
            ExitAction(
                ticker=ticker,
                action=ExitActionType.HOLD,
                reason='MOCK_HOLD',
            )
            for ticker in context.positions
        ]


@register_strategy('mock_exit_trigger')
class MockExitTriggerStrategy(Strategy):
    """Strategy that always exits."""

    @property
    def name(self) -> str:
        return 'mock_exit_trigger'

    def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
        return []

    def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
        return [
            ExitAction(
                ticker=ticker,
                action=ExitActionType.EXIT,
                reason='MOCK_EXIT',
                exit_price=150.0,
            )
            for ticker in context.positions
        ]


@register_strategy('mock_stop_updater')
class MockStopUpdaterStrategy(Strategy):
    """Strategy that updates stops."""

    def __init__(self, stop_price: float = 145.0):
        self.stop_price = stop_price

    @property
    def name(self) -> str:
        return 'mock_stop_updater'

    def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
        return []

    def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
        return [
            ExitAction(
                ticker=ticker,
                action=ExitActionType.UPDATE_STOP,
                reason='MOCK_UPDATE',
                new_stop_price=self.stop_price,
                new_stop_type='TRAIL_MOCK',
            )
            for ticker in context.positions
        ]


class TestCompositeStrategyBasics(unittest.TestCase):
    """Basic composite strategy tests."""

    def setUp(self):
        self.data_provider = MockDataProvider()

    def make_context(self, positions=None):
        """Create a StrategyContext."""
        return StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions=positions or {},
            cash=100000,
            equity=100000,
        )

    def test_composite_name(self):
        """Composite name should include all sub-strategies."""
        s1 = MockAggressiveStrategy()
        s2 = MockConservativeStrategy()
        composite = CompositeStrategy([s1, s2])

        self.assertIn('mock_aggressive', composite.name)
        self.assertIn('mock_conservative', composite.name)


class TestCompositeUnionMode(unittest.TestCase):
    """Tests for union (OR) mode."""

    def setUp(self):
        self.data_provider = MockDataProvider()
        self.aggressive = MockAggressiveStrategy(tickers=['AAPL', 'MSFT', 'GOOGL'])
        self.conservative = MockConservativeStrategy()

    def make_context(self, positions=None):
        return StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions=positions or {},
            cash=100000,
            equity=100000,
        )

    def test_union_includes_all_tickers(self):
        """Union should include tickers from any strategy."""
        composite = CompositeStrategy([self.aggressive, self.conservative], mode='union')
        context = self.make_context()

        signals = composite.evaluate_entries(context)
        tickers = [s.ticker for s in signals]

        # Aggressive signals AAPL, MSFT, GOOGL; Conservative signals AAPL
        # Union should have all unique tickers
        self.assertIn('AAPL', tickers)
        self.assertIn('MSFT', tickers)
        self.assertIn('GOOGL', tickers)

    def test_union_deduplicates_by_ticker(self):
        """Union should deduplicate signals."""
        composite = CompositeStrategy([self.aggressive, self.conservative], mode='union')
        context = self.make_context()

        signals = composite.evaluate_entries(context)
        tickers = [s.ticker for s in signals]

        # AAPL appears in both strategies but should be unique
        self.assertEqual(len(tickers), len(set(tickers)))
        self.assertEqual(tickers.count('AAPL'), 1)

    def test_union_prefers_higher_score(self):
        """When deduplicating, should keep highest score signal."""
        composite = CompositeStrategy([self.aggressive, self.conservative], mode='union')
        context = self.make_context()

        signals = composite.evaluate_entries(context)
        aapl_signal = [s for s in signals if s.ticker == 'AAPL'][0]

        # Conservative has score 80, Aggressive has 70
        self.assertEqual(aapl_signal.entry_score, 80)


class TestCompositeIntersectionMode(unittest.TestCase):
    """Tests for intersection (AND) mode."""

    def setUp(self):
        self.data_provider = MockDataProvider()
        self.aggressive = MockAggressiveStrategy(tickers=['AAPL', 'MSFT'])
        self.conservative = MockConservativeStrategy()  # Only AAPL

    def make_context(self, positions=None):
        return StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions=positions or {},
            cash=100000,
            equity=100000,
        )

    def test_intersection_only_common_tickers(self):
        """Intersection should only include tickers ALL strategies agree on."""
        composite = CompositeStrategy([self.aggressive, self.conservative], mode='intersection')
        context = self.make_context()

        signals = composite.evaluate_entries(context)
        tickers = [s.ticker for s in signals]

        # Only AAPL is common to both (may appear twice - once per strategy)
        self.assertIn('AAPL', tickers)
        self.assertNotIn('MSFT', tickers)

    def test_intersection_empty_when_no_agreement(self):
        """Should return empty when strategies don't agree."""
        s1 = MockAggressiveStrategy(tickers=['MSFT'])
        s2 = MockConservativeStrategy()  # Only AAPL

        composite = CompositeStrategy([s1, s2], mode='intersection')
        context = self.make_context()

        signals = composite.evaluate_entries(context)
        self.assertEqual(len(signals), 0)


class TestCompositeExitResolution(unittest.TestCase):
    """Tests for exit action conflict resolution."""

    def setUp(self):
        self.data_provider = MockDataProvider()

    def make_context_with_position(self, ticker='AAPL'):
        position = Position(
            ticker=ticker,
            status='OPEN',
            entry_date='2024-01-15',
            entry_price=150.0,
            shares=100,
            stop_price=140.0,
            target_price=170.0,
            initial_risk=1000.0,
            sector='Technology',
            current_stop_type='HARD',
            initial_stop_price=140.0,
        )
        return StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions={ticker: position},
            cash=50000,
            equity=100000,
        )

    def test_exit_wins_over_hold(self):
        """EXIT should win over HOLD."""
        exit_strategy = MockExitTriggerStrategy()
        hold_strategy = MockConservativeStrategy()

        composite = CompositeStrategy([exit_strategy, hold_strategy])
        context = self.make_context_with_position('AAPL')

        actions = composite.manage_exits(context)
        aapl_action = [a for a in actions if a.ticker == 'AAPL'][0]

        self.assertEqual(aapl_action.action, ExitActionType.EXIT)

    def test_exit_wins_over_update_stop(self):
        """EXIT should win over UPDATE_STOP."""
        exit_strategy = MockExitTriggerStrategy()
        stop_strategy = MockStopUpdaterStrategy(stop_price=145.0)

        composite = CompositeStrategy([exit_strategy, stop_strategy])
        context = self.make_context_with_position('AAPL')

        actions = composite.manage_exits(context)
        aapl_action = [a for a in actions if a.ticker == 'AAPL'][0]

        self.assertEqual(aapl_action.action, ExitActionType.EXIT)

    def test_tightest_stop_wins(self):
        """Tightest (highest) stop should win among UPDATE_STOP actions."""
        stop_strategy1 = MockStopUpdaterStrategy(stop_price=145.0)
        stop_strategy2 = MockStopUpdaterStrategy(stop_price=148.0)  # Tighter
        hold_strategy = MockConservativeStrategy()

        composite = CompositeStrategy([stop_strategy1, stop_strategy2, hold_strategy])
        context = self.make_context_with_position('AAPL')

        actions = composite.manage_exits(context)
        aapl_action = [a for a in actions if a.ticker == 'AAPL'][0]

        self.assertEqual(aapl_action.action, ExitActionType.UPDATE_STOP)
        self.assertEqual(aapl_action.new_stop_price, 148.0)

    def test_default_to_hold(self):
        """Should default to HOLD when no action needed."""
        hold_strategy1 = MockConservativeStrategy()
        hold_strategy2 = MockConservativeStrategy()

        composite = CompositeStrategy([hold_strategy1, hold_strategy2])
        context = self.make_context_with_position('AAPL')

        actions = composite.manage_exits(context)
        aapl_action = [a for a in actions if a.ticker == 'AAPL'][0]

        self.assertEqual(aapl_action.action, ExitActionType.HOLD)


class TestCompositeEdgeCases(unittest.TestCase):
    """Edge case tests for composite strategy."""

    def setUp(self):
        self.data_provider = MockDataProvider()

    def make_context(self, positions=None):
        return StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions=positions or {},
            cash=100000,
            equity=100000,
        )

    def test_empty_strategy_list(self):
        """Should handle empty strategy list gracefully."""
        composite = CompositeStrategy([])
        context = self.make_context()

        signals = composite.evaluate_entries(context)
        self.assertEqual(len(signals), 0)

        actions = composite.manage_exits(context)
        self.assertEqual(len(actions), 0)

    def test_single_strategy(self):
        """Should work with single strategy."""
        strategy = MockAggressiveStrategy()
        composite = CompositeStrategy([strategy])
        context = self.make_context()

        signals = composite.evaluate_entries(context)
        self.assertGreater(len(signals), 0)


class TestCompositeLifecycleHooks(unittest.TestCase):
    """Tests for lifecycle hook delegation."""

    def setUp(self):
        self.data_provider = MockDataProvider()

    def make_context(self):
        return StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions={},
            cash=100000,
            equity=100000,
        )

    def test_hooks_delegate_to_all_strategies(self):
        """Lifecycle hooks should call all sub-strategies."""
        s1 = MockAggressiveStrategy()
        s2 = MockConservativeStrategy()

        # Track calls by patching
        s1.on_day_start = lambda ctx: setattr(self, 's1_start_called', True)
        s2.on_day_start = lambda ctx: setattr(self, 's2_start_called', True)

        composite = CompositeStrategy([s1, s2])
        context = self.make_context()

        self.s1_start_called = False
        self.s2_start_called = False

        composite.on_day_start(context)

        self.assertTrue(self.s1_start_called)
        self.assertTrue(self.s2_start_called)


if __name__ == '__main__':
    unittest.main()

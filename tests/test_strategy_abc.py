"""Tests for Unified Strategy ABC and Registry.

Covers:
1. Strategy ABC interface compliance
2. ExitActionType enum values
3. ExitAction dataclass
4. EntrySignal dataclass
5. StrategyContext
6. @register_strategy decorator
7. get_strategy() function
8. list_strategies() function
"""

import unittest
from datetime import date
from typing import List, Optional

import pandas as pd

from traderlib.strategies import (
    Strategy,
    StrategyContext,
    EntrySignal,
    ExitAction,
    ExitActionType,
    register_strategy,
    get_strategy,
    list_strategies,
    STRATEGY_REGISTRY,
)
from traderlib.paper_state import Position


class MockDataProvider:
    """Mock data provider for testing."""

    def get_bars(self, ticker: str, as_of: date, min_rows: int = 30) -> Optional[pd.DataFrame]:
        return None

    def get_current_price(self, ticker: str, as_of: date) -> Optional[float]:
        return 150.0


class TestExitActionType(unittest.TestCase):
    """Tests for ExitActionType enum."""

    def test_enum_values(self):
        """Should have correct enum values."""
        self.assertEqual(ExitActionType.EXIT.value, "exit")
        self.assertEqual(ExitActionType.UPDATE_STOP.value, "update_stop")
        self.assertEqual(ExitActionType.HOLD.value, "hold")

    def test_enum_comparison(self):
        """Should support equality comparison."""
        self.assertEqual(ExitActionType.EXIT, ExitActionType.EXIT)
        self.assertNotEqual(ExitActionType.EXIT, ExitActionType.HOLD)


class TestExitAction(unittest.TestCase):
    """Tests for ExitAction dataclass."""

    def test_basic_creation(self):
        """Should create ExitAction with required fields."""
        action = ExitAction(
            ticker="AAPL",
            action=ExitActionType.EXIT,
            reason="STOP_HIT",
        )

        self.assertEqual(action.ticker, "AAPL")
        self.assertEqual(action.action, ExitActionType.EXIT)
        self.assertEqual(action.reason, "STOP_HIT")

    def test_optional_fields(self):
        """Should handle optional fields."""
        action = ExitAction(
            ticker="AAPL",
            action=ExitActionType.UPDATE_STOP,
            reason="TRAIL_EMA",
            exit_price=150.0,
            r_multiple=2.5,
            new_stop_price=145.0,
            new_stop_type="TRAIL_EMA20",
        )

        self.assertEqual(action.exit_price, 150.0)
        self.assertEqual(action.r_multiple, 2.5)
        self.assertEqual(action.new_stop_price, 145.0)
        self.assertEqual(action.new_stop_type, "TRAIL_EMA20")

    def test_default_metadata(self):
        """Should have empty dict as default metadata."""
        action = ExitAction(
            ticker="AAPL",
            action=ExitActionType.HOLD,
            reason="WAITING",
        )

        self.assertEqual(action.metadata, {})


class TestEntrySignal(unittest.TestCase):
    """Tests for EntrySignal dataclass."""

    def test_default_side(self):
        """Default side should be LONG."""
        signal = EntrySignal(ticker="AAPL")
        self.assertEqual(signal.side, "LONG")

    def test_full_creation(self):
        """Should create with all fields."""
        signal = EntrySignal(
            ticker="AAPL",
            side="LONG",
            entry_price=150.0,
            stop_price=140.0,
            target_price=170.0,
            shares=100,
            sector="Technology",
            entry_score=75,
            stage2_score=6,
            metadata={"vcp_data": {"num_contractions": 3}},
        )

        self.assertEqual(signal.ticker, "AAPL")
        self.assertEqual(signal.entry_price, 150.0)
        self.assertEqual(signal.metadata["vcp_data"]["num_contractions"], 3)


class TestStrategyContext(unittest.TestCase):
    """Tests for StrategyContext."""

    def setUp(self):
        self.data_provider = MockDataProvider()

    def test_basic_creation(self):
        """Should create StrategyContext with required fields."""
        context = StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions={},
            cash=100000.0,
            equity=100000.0,
        )

        self.assertEqual(context.sim_date, date(2024, 6, 1))
        self.assertEqual(context.cash, 100000.0)
        self.assertEqual(context.equity, 100000.0)

    def test_optional_fields(self):
        """Should handle optional fields."""
        context = StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions={},
            cash=100000.0,
            equity=100000.0,
            spy_data=None,
            spy_current=450.0,
            vix_current=15.0,
            day_pnl=1000.0,
        )

        self.assertEqual(context.spy_current, 450.0)
        self.assertEqual(context.vix_current, 15.0)
        self.assertEqual(context.day_pnl, 1000.0)

    def test_default_position_dict(self):
        """Should have empty dict as default positions."""
        context = StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            cash=100000.0,
            equity=100000.0,
        )

        self.assertEqual(context.positions, {})


class TestStrategyABC(unittest.TestCase):
    """Tests for Strategy abstract base class."""

    def test_cannot_instantiate_abc(self):
        """Cannot instantiate Strategy ABC directly."""
        with self.assertRaises(TypeError):
            Strategy()

    def test_must_implement_abstract_methods(self):
        """Concrete strategy must implement abstract methods."""
        class IncompleteStrategy(Strategy):
            @property
            def name(self) -> str:
                return "incomplete"

        with self.assertRaises(TypeError):
            IncompleteStrategy()

    def test_concrete_strategy_works(self):
        """Concrete strategy with all methods should work."""
        @register_strategy("test_concrete")
        class ConcreteStrategy(Strategy):
            @property
            def name(self) -> str:
                return "test_concrete"

            def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
                return []

            def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
                return []

        strategy = ConcreteStrategy()
        self.assertEqual(strategy.name, "test_concrete")
        self.assertEqual(strategy.side, "LONG")


class TestStrategyRegistry(unittest.TestCase):
    """Tests for strategy registry."""

    def setUp(self):
        """Clear registry before each test."""
        # Save original registry
        self._original_registry = STRATEGY_REGISTRY.copy()
        STRATEGY_REGISTRY.clear()

    def tearDown(self):
        """Restore original registry."""
        STRATEGY_REGISTRY.clear()
        STRATEGY_REGISTRY.update(self._original_registry)

    def test_register_strategy_decorator(self):
        """@register_strategy should add to registry."""
        @register_strategy("test_strategy")
        class TestStrategy(Strategy):
            @property
            def name(self) -> str:
                return "test_strategy"

            def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
                return []

            def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
                return []

        self.assertIn("test_strategy", STRATEGY_REGISTRY)
        self.assertEqual(STRATEGY_REGISTRY["test_strategy"], TestStrategy)

    def test_get_strategy_existing(self):
        """get_strategy should return instance for registered strategy."""
        @register_strategy("gettable")
        class GettableStrategy(Strategy):
            @property
            def name(self) -> str:
                return "gettable"

            def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
                return []

            def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
                return []

        instance = get_strategy("gettable")
        self.assertIsNotNone(instance)
        self.assertIsInstance(instance, GettableStrategy)

    def test_get_strategy_missing(self):
        """get_strategy should return None for unregistered strategy."""
        instance = get_strategy("nonexistent")
        self.assertIsNone(instance)

    def test_list_strategies(self):
        """list_strategies should return all registered names."""
        @register_strategy("strategy_a")
        class StrategyA(Strategy):
            @property
            def name(self) -> str:
                return "strategy_a"

            def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
                return []

            def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
                return []

        @register_strategy("strategy_b")
        class StrategyB(Strategy):
            @property
            def name(self) -> str:
                return "strategy_b"

            def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
                return []

            def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
                return []

        names = list_strategies()
        self.assertIn("strategy_a", names)
        self.assertIn("strategy_b", names)

    def test_get_strategy_with_kwargs(self):
        """get_strategy should pass kwargs to constructor."""
        @register_strategy("configurable")
        class ConfigurableStrategy(Strategy):
            def __init__(self, param1: str = "default", param2: int = 0):
                self.param1 = param1
                self.param2 = param2

            @property
            def name(self) -> str:
                return "configurable"

            def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
                return []

            def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
                return []

        instance = get_strategy("configurable", param1="custom", param2=42)
        self.assertEqual(instance.param1, "custom")
        self.assertEqual(instance.param2, 42)


class TestLifecycleHooks(unittest.TestCase):
    """Tests for optional lifecycle hooks."""

    def test_hooks_are_optional(self):
        """Lifecycle hooks should have default no-op implementations."""
        @register_strategy("hooks_test")
        class HooksTestStrategy(Strategy):
            @property
            def name(self) -> str:
                return "hooks_test"

            def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
                return []

            def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
                return []

        strategy = HooksTestStrategy()
        context = StrategyContext(
            data_provider=MockDataProvider(),
            sim_date=date(2024, 6, 1),
            positions={},
            cash=100000.0,
            equity=100000.0,
        )

        # Should not raise
        strategy.on_day_start(context)
        strategy.on_day_end(context)
        strategy.on_market_regime_change("BULL", "BEAR", context)
        strategy.on_position_opened(None, context)
        strategy.on_position_closed(None, 1000.0, context)


class TestDataFrameProviderProtocol(unittest.TestCase):
    """Tests for DataFrameProvider protocol."""

    def test_protocol_methods(self):
        """DataFrameProvider should define required methods."""
        provider = MockDataProvider()

        # Should have get_bars method
        bars = provider.get_bars("AAPL", date(2024, 6, 1))
        self.assertIsNone(bars)

        # Should have get_current_price method
        price = provider.get_current_price("AAPL", date(2024, 6, 1))
        self.assertEqual(price, 150.0)


if __name__ == '__main__':
    unittest.main()

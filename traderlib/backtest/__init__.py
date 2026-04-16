"""Backtesting module for Stage 2 momentum strategy."""

from traderlib.backtest.data_provider import DataFrameProvider, AlpacaDataProvider, DictDataProvider
from traderlib.backtest.execution import ExecutionConfig, FillResult, ExecutionModel
from traderlib.backtest.state import TradeRecord, BacktestState
from traderlib.backtest.strategy import Strategy, EntrySignal, ExitDecision, Stage2MomentumStrategy
from traderlib.backtest.engine import BacktestConfig, BacktestResult, BacktestEngine, BacktestProgress
from traderlib.backtest.report import BacktestReport, BacktestReporter

__all__ = [
    'DataFrameProvider', 'AlpacaDataProvider', 'DictDataProvider',
    'ExecutionConfig', 'FillResult', 'ExecutionModel',
    'TradeRecord', 'BacktestState',
    'Strategy', 'EntrySignal', 'ExitDecision', 'Stage2MomentumStrategy',
    'BacktestConfig', 'BacktestResult', 'BacktestEngine', 'BacktestProgress',
    'BacktestReport', 'BacktestReporter',
]

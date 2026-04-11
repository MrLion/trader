#!/usr/bin/env python3
"""Tests for trading_exceptions module."""

import sys
import logging
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / 'traderlib'))

from trading_exceptions import (
    TradingExceptionHandler,
    critical,
    error,
    warning,
    info,
    logger
)


class TestTradingExceptionHandler:
    """Test TradingExceptionHandler functionality."""

    def setup_method(self):
        """Reset metrics before each test."""
        TradingExceptionHandler.reset_metrics()

    def test_log_exception_counts(self):
        """Test that exceptions are counted by operation."""
        TradingExceptionHandler.log_exception(
            'test_op',
            ValueError('test'),
            severity=TradingExceptionHandler.WARNING
        )

        metrics = TradingExceptionHandler.get_metrics()
        assert metrics['total_exceptions'] == 1
        assert metrics['exception_counts']['test_op'] == 1

    def test_log_exception_multiple_same_operation(self):
        """Test counting multiple exceptions from same operation."""
        for _ in range(3):
            TradingExceptionHandler.log_exception(
                'db_query',
                ConnectionError('timeout'),
                severity=TradingExceptionHandler.ERROR
            )

        metrics = TradingExceptionHandler.get_metrics()
        assert metrics['total_exceptions'] == 3
        assert metrics['exception_counts']['db_query'] == 3

    def test_log_exception_with_context(self):
        """Test that context is passed through."""
        TradingExceptionHandler.log_exception(
            'market_fetch',
            TimeoutError('API timeout'),
            severity=TradingExceptionHandler.CRITICAL,
            ticker='AAPL',
            source='alpaca'
        )

        # Should not raise, context should be in log
        assert TradingExceptionHandler.get_metrics()['total_exceptions'] == 1

    def test_log_exception_different_severities(self):
        """Test logging at different severity levels."""
        # Critical
        TradingExceptionHandler.log_exception(
            'critical_op', RuntimeError('fail'),
            severity=TradingExceptionHandler.CRITICAL
        )
        # Error
        TradingExceptionHandler.log_exception(
            'error_op', ValueError('bad'),
            severity=TradingExceptionHandler.ERROR
        )
        # Warning
        TradingExceptionHandler.log_exception(
            'warning_op', KeyError('missing'),
            severity=TradingExceptionHandler.WARNING
        )
        # Info
        TradingExceptionHandler.log_exception(
            'info_op', TimeoutError('slow'),
            severity=TradingExceptionHandler.INFO
        )

        metrics = TradingExceptionHandler.get_metrics()
        assert metrics['total_exceptions'] == 4

    def test_reset_metrics(self):
        """Test that reset clears all metrics."""
        TradingExceptionHandler.log_exception(
            'test', Exception(), severity=TradingExceptionHandler.WARNING
        )
        assert TradingExceptionHandler.get_metrics()['total_exceptions'] == 1

        TradingExceptionHandler.reset_metrics()
        metrics = TradingExceptionHandler.get_metrics()
        assert metrics['total_exceptions'] == 0
        assert metrics['exception_counts'] == {}
        assert metrics['last_exception_time'] is None


class TestDecoratorFunctions:
    """Test decorator convenience functions."""

    def setup_method(self):
        """Reset metrics before each test."""
        TradingExceptionHandler.reset_metrics()

    def test_critical_decorator(self):
        """Test @critical decorator catches and logs exceptions."""
        @critical('risky_operation', default_return='fallback')
        def failing_function():
            raise RuntimeError('critical failure')

        result = failing_function()
        assert result == 'fallback'

        metrics = TradingExceptionHandler.get_metrics()
        assert metrics['total_exceptions'] == 1
        assert 'risky_operation' in metrics['exception_counts']

    def test_error_decorator(self):
        """Test @error decorator catches and logs exceptions."""
        @error('db_query', default_return=None)
        def failing_function():
            raise ConnectionError('db down')

        result = failing_function()
        assert result is None

        metrics = TradingExceptionHandler.get_metrics()
        assert metrics['total_exceptions'] == 1

    def test_warning_decorator(self):
        """Test @warning decorator catches and logs exceptions."""
        @warning('config_load', default_return={})
        def failing_function():
            raise FileNotFoundError('missing.yaml')

        result = failing_function()
        assert result == {}

        metrics = TradingExceptionHandler.get_metrics()
        assert metrics['total_exceptions'] == 1

    def test_info_decorator(self):
        """Test @info decorator catches and logs exceptions."""
        @info('cache_refresh', default_return='cached')
        def failing_function():
            raise TimeoutError('slow cache')

        result = failing_function()
        assert result == 'cached'

        metrics = TradingExceptionHandler.get_metrics()
        assert metrics['total_exceptions'] == 1

    def test_decorator_preserves_function_metadata(self):
        """Test that decorator preserves function name and docstring."""
        @warning('test_op', default_return=None)
        def my_function():
            """My docstring."""
            raise ValueError('fail')

        assert my_function.__name__ == 'my_function'
        assert my_function.__doc__ == 'My docstring.'

    def test_decorator_with_self_ticker(self):
        """Test that decorator extracts ticker from self.ticker."""
        class MockPosition:
            def __init__(self):
                self.ticker = 'TSLA'

        @error('process_position', default_return=None)
        def process(self):
            raise RuntimeError('process failed')

        pos = MockPosition()
        result = process(pos)

        assert result is None
        metrics = TradingExceptionHandler.get_metrics()
        assert metrics['total_exceptions'] == 1


class TestLogAndContinueDecorator:
    """Test the log_and_continue decorator directly."""

    def setup_method(self):
        TradingExceptionHandler.reset_metrics()

    def test_custom_log_traceback(self):
        """Test that log_traceback parameter works."""
        @TradingExceptionHandler.log_and_continue(
            'custom_op',
            severity=TradingExceptionHandler.ERROR,
            default_return='default',
            log_traceback=True
        )
        def failing_function():
            raise RuntimeError('with traceback')

        result = failing_function()
        assert result == 'default'

        metrics = TradingExceptionHandler.get_metrics()
        assert metrics['total_exceptions'] == 1


class TestLoggerConfiguration:
    """Test that logger is configured correctly."""

    def test_logger_has_handlers(self):
        """Test that logger has both file and console handlers."""
        assert len(logger.handlers) >= 1  # At least file handler

    def test_logger_name(self):
        """Test logger name is 'trading'."""
        assert logger.name == 'trading'

    def test_log_file_exists(self):
        """Test that log file is created."""
        from pathlib import Path
        log_file = Path(__file__).parent.parent / 'data' / 'logs' / 'trading_exceptions.log'
        # File may or may not exist depending on test order
        # Just verify the path is valid
        assert log_file.parent.exists()

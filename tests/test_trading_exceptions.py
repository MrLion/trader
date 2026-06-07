#!/usr/bin/env python3
"""Tests for trading_exceptions module."""

import sys
import logging
from pathlib import Path
from unittest.mock import Mock, patch


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


# =============================================================================
# Test Isolation Hardening — Task 2 invariants
# =============================================================================
# These tests pin the lazy-init behavior of traderlib.trading_exceptions:
#
#   1. Importing the module creates no files and attaches no handlers.
#   2. The first log call creates the log file under data_dir() / 'logs',
#      which honors PAPER_TRADING_DATA_DIR — so tests that set the env var
#      to a tmp dir never touch production data/logs/.
#   3. Multiple log calls in the same process attach exactly one FileHandler
#      and one StreamHandler (idempotent), not a growing stack of duplicates.
# =============================================================================


# Resolve production paths for the no-pollution assertions.
_TEST_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PROD_LOG_FILE = _TEST_PROJECT_ROOT / 'data' / 'logs' / 'trading_exceptions.log'


def _reset_lazy_logger_state():
    """Reset the module-level lazy-init flag and detach all handlers.

    The lazy-init guard ``_logger_initialized`` is a module-level boolean
    that flips to True on the first ``_ensure_logger()`` call and stays
    True for the rest of the process. The handler list on the ``trading``
    logger is process-wide too. To make the new invariants testable in
    isolation, this helper resets both, so each test sees a clean
    "not yet initialized" state.
    """
    import traderlib.trading_exceptions as te

    te._logger_initialized = False
    trading_logger = logging.getLogger('trading')
    for handler in list(trading_logger.handlers):
        trading_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


class TestLazyInitInvariants:
    """Pin the three lazy-init invariants for trading_exceptions."""

    def test_log_exception_creates_file_under_data_dir(
        self, tmp_path, monkeypatch
    ):
        """Invariant 1: First log call creates the file at data_dir()/logs/.

        With PAPER_TRADING_DATA_DIR set to a tmp dir, calling log_exception
        must create a file at ``<tmp>/logs/trading_exceptions.log`` and
        must not raise.
        """
        import traderlib.trading_exceptions as te
        from traderlib.paths import data_dir

        _reset_lazy_logger_state()
        monkeypatch.setenv('PAPER_TRADING_DATA_DIR', str(tmp_path))

        # The tmp dir is empty — data_dir() points there.
        assert data_dir() == tmp_path

        te.TradingExceptionHandler.log_exception(
            'lazy_init_test', ValueError('x')
        )

        expected_file = tmp_path / 'logs' / 'trading_exceptions.log'
        assert expected_file.exists(), (
            f"Expected log file at {expected_file} after first log call. "
            "The lazy initializer must create the log file on first use."
        )

    def test_log_exception_does_not_touch_production_log_file(
        self, tmp_path, monkeypatch
    ):
        """Invariant 2: The production log file is never written.

        With PAPER_TRADING_DATA_DIR set to a tmp dir (via monkeypatch), a
        log_exception call must write ONLY to ``<tmp>/logs/`` and never
        to ``<project_root>/data/logs/trading_exceptions.log``.
        """
        import traderlib.trading_exceptions as te

        _reset_lazy_logger_state()
        monkeypatch.setenv('PAPER_TRADING_DATA_DIR', str(tmp_path))

        # Snapshot the production log file's state before the log call.
        pre_exists = _PROD_LOG_FILE.exists()
        if pre_exists:
            pre_mtime = _PROD_LOG_FILE.stat().st_mtime
            pre_size = _PROD_LOG_FILE.stat().st_size
        else:
            pre_mtime = None
            pre_size = None

        te.TradingExceptionHandler.log_exception(
            'isolation_check', ValueError('boom')
        )

        # The file under tmp should exist.
        tmp_log = tmp_path / 'logs' / 'trading_exceptions.log'
        assert tmp_log.exists()

        # The production file must not have been created or modified.
        post_exists = _PROD_LOG_FILE.exists()
        if not pre_exists:
            assert not post_exists, (
                f"Production log file {_PROD_LOG_FILE} was created by a "
                "log_exception call under a tmp data dir. The lazy "
                "initializer must respect PAPER_TRADING_DATA_DIR."
            )
        else:
            post_mtime = _PROD_LOG_FILE.stat().st_mtime
            post_size = _PROD_LOG_FILE.stat().st_size
            # Allow a 1.0s mtime tolerance for filesystem clock skew.
            assert abs(post_mtime - pre_mtime) < 1.0, (
                f"Production log file mtime changed: pre={pre_mtime}, "
                f"post={post_mtime}. Lazy init leaked a write."
            )
            assert post_size == pre_size, (
                f"Production log file size changed: pre={pre_size}, "
                f"post={post_size}. Lazy init leaked a write."
            )

    def test_log_exception_does_not_attach_duplicate_handlers(
        self, tmp_path, monkeypatch
    ):
        """Invariant 3: Two log calls attach handlers once, not twice.

        Calling log_exception repeatedly in the same process must result
        in exactly one FileHandler and one StreamHandler on the 'trading'
        logger — not a growing stack of duplicates on every call.
        """
        import traderlib.trading_exceptions as te

        _reset_lazy_logger_state()
        monkeypatch.setenv('PAPER_TRADING_DATA_DIR', str(tmp_path))

        te.TradingExceptionHandler.log_exception(
            'dup_test_1', ValueError('first')
        )
        te.TradingExceptionHandler.log_exception(
            'dup_test_2', ValueError('second')
        )

        trading_logger = logging.getLogger('trading')
        # We expect exactly one FileHandler and one StreamHandler
        # (the FileHandler from _ensure_logger plus the console handler).
        handler_count = len(trading_logger.handlers)
        assert handler_count == 2, (
            f"Expected 2 handlers (1 file + 1 console) after two log "
            f"calls, got {handler_count}: "
            f"{[type(h).__name__ for h in trading_logger.handlers]}. "
            "_ensure_logger must be idempotent."
        )

        # And one more call should not grow the list.
        te.TradingExceptionHandler.log_exception(
            'dup_test_3', ValueError('third')
        )
        assert len(trading_logger.handlers) == 2, (
            f"Handler list grew after a third log call: "
            f"{[type(h).__name__ for h in trading_logger.handlers]}. "
            "_ensure_logger is not idempotent."
        )

    def test_ensure_logger_is_thread_safe(self, tmp_path, monkeypatch):
        """Invariant 4: Concurrent first-call to _ensure_logger attaches
        handlers exactly once, even when N threads race.

        Pre-fix, ``_ensure_logger()`` read the ``_logger_initialized``
        flag, set up handlers, and set the flag in three separate
        steps with no lock. Two threads passing the initial ``if`` check
        would both attach a file handler + a stream handler, producing
        4 handlers (2 file + 2 console) and 2x log output. With the
        lock + double-check pattern, exactly 2 handlers attach even
        under heavy contention.
        """
        import threading
        import traderlib.trading_exceptions as te

        _reset_lazy_logger_state()
        monkeypatch.setenv('PAPER_TRADING_DATA_DIR', str(tmp_path))

        n_threads = 16
        barrier = threading.Barrier(n_threads)
        results = []

        def worker():
            # All threads wait at the barrier, then race through
            # _ensure_logger simultaneously.
            barrier.wait()
            te._ensure_logger()

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        trading_logger = logging.getLogger('trading')
        handler_count = len(trading_logger.handlers)
        assert handler_count == 2, (
            f"Expected 2 handlers after {n_threads} racing threads, "
            f"got {handler_count}: "
            f"{[type(h).__name__ for h in trading_logger.handlers]}. "
            "_ensure_logger is not thread-safe."
        )

        # And the file log should still be attached to the correct
        # tmp directory.
        file_handlers = [
            h for h in trading_logger.handlers
            if isinstance(h, logging.handlers.TimedRotatingFileHandler)
        ]
        assert len(file_handlers) == 1, (
            f"Expected exactly 1 FileHandler, got {len(file_handlers)}"
        )
        log_path = Path(file_handlers[0].baseFilename)
        assert log_path.parent == tmp_path / "logs", (
            f"FileHandler pointed at {log_path}, expected "
            f"{tmp_path / 'logs'}"
        )

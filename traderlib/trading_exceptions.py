#!/usr/bin/env python3
"""Structured exception handling for trading system.

In a trading system, silent exceptions are worse than loud crashes.
This module provides centralized, severity-aware exception logging.
"""

import logging
import logging.handlers
import functools
from pathlib import Path
from typing import Callable, Optional, Any, Dict
from datetime import datetime

# Log file directory - use project root relative path
PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / 'data' / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / 'trading_exceptions.log'

# Configure logger
logger = logging.getLogger('trading')
logger.setLevel(logging.INFO)

# Prevent duplicate handlers if module is reloaded
if not logger.handlers:
    # File handler with daily rotation (keep 30 days of logs)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_FILE,
        when='midnight',
        interval=1,
        backupCount=30,
        utc=False
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(file_handler)

    # Console handler (still show in terminal)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(console_handler)


class TradingExceptionHandler:
    """Centralized exception handling for trading operations.

    Every exception in a trading system is a potential money-losing bug.
    This handler ensures all exceptions are logged with appropriate severity
    and context before allowing the system to continue.
    """

    # Severity levels and their business impact
    CRITICAL = "critical"  # Could cause immediate trading losses
    ERROR = "error"      # Feature degraded but system continues
    WARNING = "warning"  # Non-critical degradation
    INFO = "info"        # Expected fallbacks

    # Metrics for observability
    _exception_counts: Dict[str, int] = {}
    _last_exception_time: Optional[datetime] = None

    @classmethod
    def log_and_continue(
        cls,
        operation: str,
        severity: str = "warning",
        default_return: Any = None,
        log_traceback: bool = False
    ):
        """Decorator to catch, log, and continue after exceptions.

        Args:
            operation: Human-readable operation name for logs
            severity: One of critical/error/warning/info
            default_return: Value to return if exception occurs
            log_traceback: Whether to include full traceback in logs
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Track metrics
                    cls._exception_counts[operation] = cls._exception_counts.get(operation, 0) + 1
                    cls._last_exception_time = datetime.now()

                    # Build context string
                    context_parts = []
                    if args:
                        # Try to get self.ticker or ticker from first arg
                        first_arg = args[0]
                        if hasattr(first_arg, 'ticker'):
                            context_parts.append(f"ticker={first_arg.ticker}")
                        elif 'ticker' in kwargs:
                            context_parts.append(f"ticker={kwargs['ticker']}")

                    context_str = f" | context: {', '.join(context_parts)}" if context_parts else ""

                    # Build log message
                    msg = f"[{operation}] {type(e).__name__}: {e}{context_str}"

                    # Log with appropriate severity
                    if severity == cls.CRITICAL:
                        logger.critical(msg, exc_info=log_traceback)
                        # TODO: Add alert/notification hook here
                    elif severity == cls.ERROR:
                        logger.error(msg, exc_info=log_traceback)
                    elif severity == cls.WARNING:
                        logger.warning(msg, exc_info=log_traceback)
                    else:
                        logger.info(msg)

                    return default_return
            return wrapper
        return decorator

    @classmethod
    def log_exception(
        cls,
        operation: str,
        exception: Exception,
        severity: str = "warning",
        **context
    ):
        """Log an exception that was already caught.

        Use this when you need custom handling but still want logging.
        """
        cls._exception_counts[operation] = cls._exception_counts.get(operation, 0) + 1
        cls._last_exception_time = datetime.now()

        context_str = f" | context: {context}" if context else ""
        msg = f"[{operation}] {type(exception).__name__}: {exception}{context_str}"

        if severity == cls.CRITICAL:
            logger.critical(msg, exc_info=True)
        elif severity == cls.ERROR:
            logger.error(msg, exc_info=True)
        elif severity == cls.WARNING:
            logger.warning(msg)
        else:
            logger.info(msg)

    @classmethod
    def log_operational(cls, operation: str, level: str = "info", **context):
        """Log an operational event (not an exception).

        Used for state transitions, sync events, and integrity checks.
        Wrapped in try/except so logging failure never crashes the engine.
        """
        try:
            context_str = f" | context: {context}" if context else ""
            msg = f"[{operation}]{context_str}"

            logger = logging.getLogger('trading')
            if level == "critical":
                logger.critical(msg)
            elif level == "error":
                logger.error(msg)
            elif level == "warning":
                logger.warning(msg)
            else:
                logger.info(msg)
        except Exception:
            pass  # Logging must never crash the engine

    @classmethod
    def get_metrics(cls) -> Dict[str, Any]:
        """Get exception metrics for monitoring/alerting."""
        return {
            'exception_counts': cls._exception_counts.copy(),
            'last_exception_time': cls._last_exception_time,
            'total_exceptions': sum(cls._exception_counts.values())
        }

    @classmethod
    def reset_metrics(cls):
        """Reset exception counters (useful for testing)."""
        cls._exception_counts.clear()
        cls._last_exception_time = None


# Convenience functions for inline usage
def critical(operation: str, default_return: Any = None):
    """Decorator for critical operations that could lose money."""
    return TradingExceptionHandler.log_and_continue(
        operation,
        severity=TradingExceptionHandler.CRITICAL,
        default_return=default_return,
        log_traceback=True
    )


def error(operation: str, default_return: Any = None):
    """Decorator for operations where failure degrades functionality."""
    return TradingExceptionHandler.log_and_continue(
        operation,
        severity=TradingExceptionHandler.ERROR,
        default_return=default_return,
        log_traceback=True
    )


def warning(operation: str, default_return: Any = None):
    """Decorator for operations where failure is acceptable."""
    return TradingExceptionHandler.log_and_continue(
        operation,
        severity=TradingExceptionHandler.WARNING,
        default_return=default_return
    )


def info(operation: str, default_return: Any = None):
    """Decorator for expected fallbacks."""
    return TradingExceptionHandler.log_and_continue(
        operation,
        severity=TradingExceptionHandler.INFO,
        default_return=default_return
    )


class APIKeyError(ValueError):
    """Raised when API keys are missing or invalid.

    EH-003: Actionable API key error message
    Follows problem+cause+fix+docs pattern for clear user guidance.
    """

    def __init__(self, provider: str = "Alpaca", details: str = ""):
        self.provider = provider

        # Problem: What went wrong
        problem = f"{provider} API keys not configured"

        # Cause: Why it happened
        cause = (
            "\n\nCAUSE:\n"
            "  The system could not find valid API credentials.\n"
            "  Tried in order (paper mode):\n"
            "    1. ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET_KEY\n"
            "    2. ALPACA_API_KEY / ALPACA_SECRET_KEY  (legacy fallback)\n"
            "  Live mode uses ALPACA_LIVE_API_KEY / ALPACA_LIVE_SECRET_KEY."
        )

        # Fix: How to resolve
        fix = (
            "\n\nFIX:\n"
            "  Run the setup wizard (recommended):\n"
            "    python3 scripts/setup_alpaca.py\n\n"
            "  Or set env vars manually in .env (project root):\n"
            "    ALPACA_PAPER_API_KEY=your_paper_api_key\n"
            "    ALPACA_PAPER_SECRET_KEY=your_paper_secret_key\n\n"
            "  Get keys at: https://app.alpaca.markets/paper"
        )

        # Docs: Where to learn more
        docs = (
            "\n\nDOCS:\n"
            "  See docs/runbooks/api_credentials.md for detailed setup instructions\n"
            "  Alpaca dashboard: https://app.alpaca.markets/paper"
        )

        message = f"{problem}{cause}{fix}{docs}"
        if details:
            message = f"{problem}: {details}{cause}{fix}{docs}"

        super().__init__(message)


class ConfigurationError(ValueError):
    """Raised when configuration is missing or invalid."""

    def __init__(self, component: str, issue: str, fix_instructions: str):
        message = (
            f"CONFIGURATION ERROR: {component}\n"
            f"\n"
            f"PROBLEM: {issue}\n"
            f"\n"
            f"FIX: {fix_instructions}"
        )
        super().__init__(message)

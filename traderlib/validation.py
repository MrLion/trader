#!/usr/bin/env python3
"""Input validation utilities for trading system.

FINDING-011: Input validation on tickers
"""

import os
import re
from typing import Optional


# NO_COLOR: Respect NO_COLOR environment variable
# https://no-color.org/
USE_COLOR = os.environ.get('NO_COLOR', '').strip() == ''

# Emoji and color constants - empty strings when NO_COLOR is set
EMOJI_CHECK = '✅' if USE_COLOR else '[OK]'
EMOJI_CROSS = '❌' if USE_COLOR else '[ERR]'
EMOJI_WARN = '⚠️'  if USE_COLOR else '[WARN]'
EMOJI_INFO = 'ℹ️'  if USE_COLOR else '[INFO]'
EMOJI_ARROW = '➡️' if USE_COLOR else '->'
EMOJI_UP = '📈' if USE_COLOR else '[UP]'
EMOJI_DOWN = '📉' if USE_COLOR else '[DOWN]'
EMOJI_CLOCK = '🕐' if USE_COLOR else '[TIME]'
EMOJI_MONEY = '💰' if USE_COLOR else '$'
EMOJI_FIRE = '🔥' if USE_COLOR else '[!]'
EMOJI_BULB = '💡' if USE_COLOR else '[TIP]'


def colorize(text: str, color: str = '') -> str:
    """Apply color codes if color is enabled.

    NO_COLOR support: Returns plain text if NO_COLOR env var is set.

    Args:
        text: Text to colorize
        color: Color name ('green', 'red', 'yellow', 'blue', 'cyan', 'magenta')

    Returns:
        Colorized text or plain text based on USE_COLOR
    """
    if not USE_COLOR:
        return text

    colors = {
        'green': '\033[32m',
        'red': '\033[31m',
        'yellow': '\033[33m',
        'blue': '\033[34m',
        'cyan': '\033[36m',
        'magenta': '\033[35m',
        'bold': '\033[1m',
        'reset': '\033[0m'
    }

    if color not in colors:
        return text

    return f"{colors[color]}{text}{colors['reset']}"


# FINDING-011: Standard ticker pattern - 1-5 uppercase letters
# Matches US equity tickers: A, AAPL, BRK.A, etc.
TICKER_PATTERN = re.compile(r'^[A-Z]{1,5}$')

# Common false positives that look like tickers but aren't
TICKER_FALSE_POSITIVES = {
    'I', 'AT', 'IF', 'IS', 'MY', 'NO', 'OF', 'TO', 'UP', 'US', 'WE',
    'AND', 'ANY', 'BUT', 'CAN', 'HAD', 'HER', 'HIM', 'HIS', 'HOW', 'ITS',
    'NEW', 'NOT', 'OLD', 'OUR', 'PUT', 'SET', 'SHE', 'THE', 'TOP',
    'TWO', 'USE', 'WAY', 'WHO', 'BEST', 'EACH', 'EVEN', 'GOOD', 'JUST',
    'LIKE', 'LONG', 'LOOK', 'MADE', 'MAKE', 'MANY', 'MOST', 'MOVE', 'MUCH',
    'ONLY', 'OVER', 'SAID', 'SOME', 'SUCH', 'TAKE', 'THAN', 'THEM', 'THEN',
    'THEY', 'TIME', 'VERY', 'WANT', 'WELL', 'WENT', 'WERE', 'WHAT', 'WHEN',
    'WITH', 'ZERO', 'ABOUT', 'AFTER', 'BACK', 'BEEN', 'BEING', 'COULD',
    'FIRST', 'GREAT', 'NEVER', 'OTHER', 'RIGHT', 'SHOULD', 'THEIR', 'THERE',
    'THESE', 'THINK', 'THREE', 'UNDER', 'WHERE', 'WHICH', 'WHILE', 'WORLD',
    'WOULD', 'YEARS', 'CRYPTO', 'STOCK', 'TRADE', 'MARKET', 'PRICE', 'SHARE',
    'FUND', 'BANK', 'CASH', 'MONEY', 'GOLD', 'FUTURE', 'OPTION', 'BOND',
    'INDEX', 'EQUITY', 'ASSET', 'RALLY', 'CRASH', 'PENNY'
}


def validate_ticker(ticker: Optional[str]) -> str:
    """Validate ticker symbol format.

    FINDING-011: Enforces strict ticker format to prevent invalid inputs
    from reaching trading engine or external APIs.

    Args:
        ticker: Ticker symbol to validate

    Returns:
        Uppercase validated ticker symbol

    Raises:
        ValueError: If ticker is invalid
    """
    if not ticker:
        raise ValueError("Ticker cannot be empty")

    ticker = ticker.strip().upper()

    if not ticker:
        raise ValueError("Ticker cannot be whitespace only")

    if not TICKER_PATTERN.match(ticker):
        raise ValueError(
            f"Invalid ticker '{ticker}'. "
            "Ticker must be 1-5 uppercase letters (e.g., AAPL, TSLA)"
        )

    if ticker in TICKER_FALSE_POSITIVES:
        raise ValueError(
            f"'{ticker}' is not a valid ticker symbol "
            "(common word, not a stock symbol)"
        )

    return ticker


def is_valid_ticker(ticker: Optional[str]) -> bool:
    """Check if ticker symbol is valid without raising exception.

    Args:
        ticker: Ticker symbol to check

    Returns:
        True if valid, False otherwise
    """
    try:
        validate_ticker(ticker)
        return True
    except ValueError:
        return False


def validate_tickers(tickers: list) -> list:
    """Validate multiple ticker symbols.

    Args:
        tickers: List of ticker symbols

    Returns:
        List of validated uppercase ticker symbols

    Raises:
        ValueError: If any ticker is invalid (with details on all invalid tickers)
    """
    if not tickers:
        return []

    errors = []
    validated = []

    for ticker in tickers:
        try:
            validated.append(validate_ticker(ticker))
        except ValueError as e:
            errors.append(str(e))

    if errors:
        raise ValueError(f"Invalid tickers found: {'; '.join(errors)}")

    return validated


if __name__ == "__main__":
    # Test validation
    test_cases = [
        ("AAPL", True),
        ("TSLA", True),
        ("aapl", True),  # Should normalize to uppercase
        ("BRK.A", False),  # Dot not allowed
        ("AAPLE", False),  # 6 chars
        ("123", False),  # Numbers not allowed
        ("A", False),  # False positive
        ("THE", False),  # Common word
        ("", False),  # Empty
        ("AAPL ", True),  # Whitespace trimmed
    ]

    print("Testing ticker validation:")
    for ticker, expected in test_cases:
        try:
            result = validate_ticker(ticker)
            passed = expected is True
            print(f"  {ticker!r:10} -> {result!r:10} {'✅' if passed else '❌'}")
        except ValueError as e:
            passed = expected is False
            print(f"  {ticker!r:10} -> ERROR      {'✅' if passed else '❌'} ({e})")

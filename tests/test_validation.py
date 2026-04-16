#!/usr/bin/env python3
"""Tests for input validation utilities.

Covers:
1. Ticker validation (format, false positives, batch)
2. NO_COLOR environment support
3. Color output functions
"""

import os
import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from traderlib.validation import (
    validate_ticker,
    is_valid_ticker,
    validate_tickers,
    colorize,
    TICKER_PATTERN,
    TICKER_FALSE_POSITIVES,
    EMOJI_CHECK,
    EMOJI_CROSS,
)


class TestTickerValidation(unittest.TestCase):
    """Test ticker symbol validation."""

    def test_valid_tickers_single_letter(self):
        """Single letter tickers (except false positives) should be valid."""
        valid_single = ['B', 'C', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'M',
                       'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W',
                       'X', 'Y', 'Z']
        for ticker in valid_single:
            result = validate_ticker(ticker)
            self.assertEqual(result, ticker)

    def test_valid_tickers_multi_letter(self):
        """Multi-letter tickers should be valid."""
        valid_tickers = ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'BRK',
                        'NVDA', 'META', 'JPM', 'V', 'JNJ']
        for ticker in valid_tickers:
            result = validate_ticker(ticker)
            self.assertEqual(result, ticker)

    def test_valid_tickers_lowercase_normalized(self):
        """Lowercase tickers should be normalized to uppercase."""
        result = validate_ticker('aapl')
        self.assertEqual(result, 'AAPL')

        result = validate_ticker('tsla')
        self.assertEqual(result, 'TSLA')

    def test_valid_tickers_whitespace_trimmed(self):
        """Whitespace should be trimmed from tickers."""
        result = validate_ticker('  AAPL  ')
        self.assertEqual(result, 'AAPL')

        result = validate_ticker('TSLA ')
        self.assertEqual(result, 'TSLA')

    def test_invalid_ticker_empty_raises_error(self):
        """Empty ticker should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            validate_ticker('')
        self.assertIn('cannot be empty', str(ctx.exception).lower())

    def test_invalid_ticker_whitespace_only_raises_error(self):
        """Whitespace-only ticker should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            validate_ticker('   ')
        self.assertIn('cannot be whitespace', str(ctx.exception).lower())

    def test_invalid_ticker_none_raises_error(self):
        """None ticker should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            validate_ticker(None)
        self.assertIn('cannot be empty', str(ctx.exception).lower())

    def test_invalid_ticker_too_long_raises_error(self):
        """Tickers longer than 5 characters should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            validate_ticker('AAPLEE')  # 6 characters
        self.assertIn('must be 1-5 uppercase letters', str(ctx.exception))

    def test_invalid_ticker_numbers_raises_error(self):
        """Tickers with numbers should raise ValueError."""
        with self.assertRaises(ValueError):
            validate_ticker('AAPL1')

        with self.assertRaises(ValueError):
            validate_ticker('123')

    def test_invalid_ticker_special_chars_raises_error(self):
        """Tickers with special characters should raise ValueError."""
        with self.assertRaises(ValueError):
            validate_ticker('BRK.A')

        with self.assertRaises(ValueError):
            validate_ticker('AAPL-B')

        with self.assertRaises(ValueError):
            validate_ticker('A@APL')

    def test_false_positive_single_letters_rejected(self):
        """Common words that look like tickers should be rejected."""
        false_positives = ['A', 'I', 'AN', 'AS', 'AT', 'BE', 'BY', 'DO', 'GO', 'HE',
                          'IF', 'IN', 'IS', 'IT', 'MY', 'NO', 'OF', 'ON', 'OR', 'SO',
                          'TO', 'UP', 'US', 'WE']
        for ticker in false_positives:
            with self.assertRaises(ValueError) as ctx:
                validate_ticker(ticker)
            self.assertIn('not a valid ticker', str(ctx.exception))

    def test_false_positive_common_words_rejected(self):
        """Common 3-letter words should be rejected."""
        false_positives = ['ALL', 'AND', 'ANY', 'ARE', 'BUT', 'CAN', 'HAD', 'HER',
                          'HIM', 'HIS', 'HOW', 'ITS', 'NEW', 'NOT', 'NOW', 'OIL',
                          'OLD', 'ONE', 'OUR', 'OUT', 'PUT', 'RUN', 'SEE', 'SET',
                          'SHE', 'THE', 'TOP', 'TWO', 'USE', 'WAY', 'WHO']
        for ticker in false_positives:
            with self.assertRaises(ValueError):
                validate_ticker(ticker)

    def test_false_positive_trading_terms_rejected(self):
        """Trading-related common words should be rejected."""
        false_positives = ['STOCK', 'TRADE', 'MARKET', 'PRICE', 'SHARE', 'FUND',
                          'BANK', 'CASH', 'MONEY', 'GOLD', 'FUTURE', 'OPTION',
                          'BOND', 'INDEX', 'EQUITY', 'ASSET', 'RALLY', 'CRASH']
        for ticker in false_positives:
            with self.assertRaises(ValueError):
                validate_ticker(ticker)


class TestIsValidTicker(unittest.TestCase):
    """Test boolean ticker validation."""

    def test_valid_ticker_returns_true(self):
        """Valid tickers should return True."""
        self.assertTrue(is_valid_ticker('AAPL'))
        self.assertTrue(is_valid_ticker('TSLA'))
        self.assertTrue(is_valid_ticker('X'))

    def test_invalid_ticker_returns_false(self):
        """Invalid tickers should return False."""
        self.assertFalse(is_valid_ticker(''))
        self.assertFalse(is_valid_ticker('AAPLEE'))  # 6 chars, too long
        self.assertFalse(is_valid_ticker('THE'))
        self.assertFalse(is_valid_ticker('A'))  # False positive
        self.assertFalse(is_valid_ticker(None))


class TestValidateTickersBatch(unittest.TestCase):
    """Test batch ticker validation."""

    def test_all_valid_tickers_returns_list(self):
        """All valid tickers should return validated list."""
        tickers = ['AAPL', 'TSLA', 'MSFT']
        result = validate_tickers(tickers)
        self.assertEqual(result, ['AAPL', 'TSLA', 'MSFT'])

    def test_lowercase_tickers_normalized(self):
        """Lowercase tickers should be normalized."""
        tickers = ['aapl', 'TSLA', 'msft']
        result = validate_tickers(tickers)
        self.assertEqual(result, ['AAPL', 'TSLA', 'MSFT'])

    def test_empty_list_returns_empty(self):
        """Empty list should return empty list."""
        result = validate_tickers([])
        self.assertEqual(result, [])

    def test_none_returns_empty(self):
        """None should return empty list."""
        result = validate_tickers(None)
        self.assertEqual(result, [])

    def test_mixed_valid_invalid_raises_error(self):
        """Mixed valid/invalid should raise with all errors."""
        tickers = ['AAPL', 'THE', 'TSLA', 'INVALID']
        with self.assertRaises(ValueError) as ctx:
            validate_tickers(tickers)
        error_msg = str(ctx.exception)
        self.assertIn('Invalid tickers found', error_msg)
        # Should include details on all invalid
        self.assertIn('THE', error_msg)

    def test_all_invalid_raises_error(self):
        """All invalid should raise ValueError."""
        tickers = ['THE', 'AND', 'AAPLE']
        with self.assertRaises(ValueError) as ctx:
            validate_tickers(tickers)
        self.assertIn('Invalid tickers found', str(ctx.exception))


class TestTickerPattern(unittest.TestCase):
    """Test the ticker regex pattern directly."""

    def test_pattern_matches_valid(self):
        """Pattern should match valid tickers."""
        valid = ['A', 'AB', 'ABC', 'ABCD', 'ABCDE']
        for ticker in valid:
            self.assertTrue(TICKER_PATTERN.match(ticker),
                           f"Pattern should match {ticker}")

    def test_pattern_rejects_invalid(self):
        """Pattern should reject invalid tickers."""
        invalid = ['', 'ABCDEF', 'abc', 'ABC1', 'AB.C', 'A-B']
        for ticker in invalid:
            self.assertIsNone(TICKER_PATTERN.match(ticker),
                             f"Pattern should reject {ticker}")


class TestColorize(unittest.TestCase):
    """Test color output functions."""

    def test_colorize_returns_plain_when_no_color(self):
        """When NO_COLOR is set, colorize should return plain text."""
        # Save original state
        original_no_color = os.environ.get('NO_COLOR')

        try:
            os.environ['NO_COLOR'] = '1'
            # Need to reimport to pick up the env var
            # Reload the module
            if 'traderlib.validation' in sys.modules:
                del sys.modules['traderlib.validation']
            from traderlib.validation import colorize as colorize_no_color

            result = colorize_no_color('test', 'green')
            self.assertEqual(result, 'test')
        finally:
            # Restore original state
            if original_no_color is None:
                os.environ.pop('NO_COLOR', None)
            else:
                os.environ['NO_COLOR'] = original_no_color

    def test_colorize_applies_color_when_enabled(self):
        """When NO_COLOR is not set, colorize should apply ANSI codes."""
        # Save original state
        original_no_color = os.environ.get('NO_COLOR')

        try:
            os.environ.pop('NO_COLOR', None)
            # Need to reimport to pick up the env var
            if 'traderlib.validation' in sys.modules:
                del sys.modules['traderlib.validation']
            from traderlib.validation import colorize as colorize_with_color

            result = colorize_with_color('test', 'green')
            self.assertIn('\033[32m', result)  # Green ANSI code
            self.assertIn('\033[0m', result)   # Reset code
            self.assertIn('test', result)
        finally:
            # Restore original state
            if original_no_color is None:
                os.environ.pop('NO_COLOR', None)
            else:
                os.environ['NO_COLOR'] = original_no_color

    def test_colorize_unknown_color_returns_plain(self):
        """Unknown color names should return plain text."""
        result = colorize('test', 'unknown_color')
        self.assertEqual(result, 'test')


class TestEmojiConstants(unittest.TestCase):
    """Test emoji constants respect NO_COLOR."""

    def test_emojis_defined(self):
        """Emoji constants should be defined."""
        # When NO_COLOR is set, these should be plain text representations
        self.assertIsNotNone(EMOJI_CHECK)
        self.assertIsNotNone(EMOJI_CROSS)


if __name__ == '__main__':
    unittest.main()

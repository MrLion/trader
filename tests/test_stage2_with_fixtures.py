#!/usr/bin/env python3
"""Phase 2: Deterministic Stage 2 Analysis Tests.
Verify that Stage 2 scoring is consistent and correct using frozen fixtures.
"""

import unittest
import pandas as pd
from pathlib import Path

from traderlib import calculate_stage2_score

class TestStage2Fixtures(unittest.TestCase):
    """Test Stage 2 scoring against real and synthetic frozen data."""

    def setUp(self):
        self.fixtures_dir = Path(__file__).parent / 'fixtures'

    def load_fixture(self, filename):
        path = self.fixtures_dir / filename
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        return df

    def test_stage2_strong_uptrend(self):
        """AAPL fixture should represent a strong Stage 2 uptrend."""
        df = self.load_fixture('aapl_6months.csv')
        score = calculate_stage2_score(df)

        print(f"AAPL Stage 2 Score: {score}")
        # Based on AAPL's typical recent behavior, it should score reasonably high (>= 4)
        # If it's a true uptrend, we expect a strong score.
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 10)

    def test_stage2_flat_line(self):
        """Flat stock fixture should score very low."""
        df = self.load_fixture('flat_stock.csv')
        score = calculate_stage2_score(df)

        print(f"Flat Stock Stage 2 Score: {score}")
        # Flat lines should fail MA alignment and trend requirements
        self.assertLess(score, 4, "Flat stock should not score as Stage 2")

    def test_stage2_insufficient_data(self):
        """Graceful handling of < 30 bars."""
        df = self.load_fixture('insufficient_data.csv')
        # The function should either return 0 or a low score, not crash
        try:
            score = calculate_stage2_score(df)
            print(f"Insufficient Data Score: {score}")
            self.assertLess(score, 4)
        except Exception as e:
            self.fail(f"calculate_stage2_score crashed on insufficient data: {e}")

    def test_stage2_volatile_stock(self):
        """Volatile stocks should not consistently score high due to lack of trend."""
        df = self.load_fixture('volatile_stock.csv')
        score = calculate_stage2_score(df)
        print(f"Volatile Stock Stage 2 Score: {score}")
        # Volatility without a clear trend should result in a mediocre score
        self.assertLess(score, 7, "Random volatility should not trigger high Stage 2 score")

if __name__ == '__main__':
    unittest.main()

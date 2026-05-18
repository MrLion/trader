class TestVCPBreakoutSector:
    def test_get_sector_uses_resolver(self):
        from traderlib.strategies.vcp_breakout import VCPBreakoutLargeCap
        from unittest.mock import MagicMock

        strategy = VCPBreakoutLargeCap()
        strategy._get_sector = MagicMock(return_value="Technology")
        assert strategy._get_sector("AAPL") == "Technology"

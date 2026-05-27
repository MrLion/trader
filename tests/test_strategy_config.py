#!/usr/bin/env python3
"""Tests for strategy_config module.

Covers:
1. load_strategy_config — existing file, missing file, invalid YAML
2. get_param — nested traversal, missing keys, intermediate non-dict, None config
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from traderlib.strategy_config import get_param, load_strategy_config


class TestLoadStrategyConfig:
    """Test load_strategy_config."""

    def test_loads_existing_yaml(self):
        with TemporaryDirectory() as td:
            config_dir = Path(td) / "config" / "strategies"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "stage2_momentum.yaml"
            config_file.write_text("""
entry:
  min_score: 70
exit:
  phase2_trail_ma: 20
""")
            # Monkey-patch the module-level _CONFIG_DIR
            import traderlib.strategy_config as sc
            original_dir = sc._CONFIG_DIR
            try:
                sc._CONFIG_DIR = config_dir
                cfg = load_strategy_config("stage2_momentum")
                assert cfg is not None
                assert cfg["entry"]["min_score"] == 70
                assert cfg["exit"]["phase2_trail_ma"] == 20
            finally:
                sc._CONFIG_DIR = original_dir

    def test_missing_file_returns_none(self):
        import traderlib.strategy_config as sc
        original_dir = sc._CONFIG_DIR
        try:
            with TemporaryDirectory() as td:
                sc._CONFIG_DIR = Path(td) / "config" / "strategies"
                result = load_strategy_config("nonexistent")
                assert result is None
        finally:
            sc._CONFIG_DIR = original_dir

    def test_invalid_yaml_returns_none(self):
        with TemporaryDirectory() as td:
            config_dir = Path(td) / "config" / "strategies"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "bad.yaml"
            config_file.write_text("not: valid: yaml: [")

            import traderlib.strategy_config as sc
            original_dir = sc._CONFIG_DIR
            try:
                sc._CONFIG_DIR = config_dir
                result = load_strategy_config("bad")
                assert result is None
            finally:
                sc._CONFIG_DIR = original_dir

    def test_empty_file_returns_empty_dict(self):
        with TemporaryDirectory() as td:
            config_dir = Path(td) / "config" / "strategies"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "empty.yaml"
            config_file.write_text("")

            import traderlib.strategy_config as sc
            original_dir = sc._CONFIG_DIR
            try:
                sc._CONFIG_DIR = config_dir
                result = load_strategy_config("empty")
                assert result == {}
            finally:
                sc._CONFIG_DIR = original_dir


class TestGetParam:
    """Test get_param nested traversal."""

    def test_nested_traversal(self):
        cfg = {"exit": {"phase2_trail_ma": 20}}
        assert get_param(cfg, "exit", "phase2_trail_ma") == 20

    def test_returns_default_on_missing_key(self):
        cfg = {"exit": {"phase2_trail_ma": 20}}
        assert get_param(cfg, "entry", "min_score", default=60) == 60

    def test_returns_default_on_intermediate_non_dict(self):
        cfg = {"exit": "not_a_dict"}
        assert get_param(cfg, "exit", "phase2_trail_ma", default=20) == 20

    def test_returns_default_when_config_is_none(self):
        assert get_param(None, "exit", "phase2_trail_ma", default=20) == 20

    def test_returns_none_default_implicitly(self):
        cfg = {"exit": {"phase2_trail_ma": 20}}
        assert get_param(cfg, "missing") is None

    def test_single_key_lookup(self):
        cfg = {"min_score": 70}
        assert get_param(cfg, "min_score") == 70

    def test_deeply_nested(self):
        cfg = {"a": {"b": {"c": {"d": 42}}}}
        assert get_param(cfg, "a", "b", "c", "d") == 42

    def test_deeply_nested_missing_returns_default(self):
        cfg = {"a": {"b": {"c": {"d": 42}}}}
        assert get_param(cfg, "a", "b", "x", "d", default=99) == 99

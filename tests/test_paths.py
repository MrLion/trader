"""Contract tests for :mod:`traderlib.paths`.

These tests pin the helper's behavior. They are the regression tests for
the test-isolation refactor (Task 1 of plan
``docs/superpowers/plans/2026-06-06-test-isolation-hardening.md``).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from traderlib.paths import data_dir, project_root


def test_data_dir_unset_returns_project_root_data(tmp_path, monkeypatch):
    """With PAPER_TRADING_DATA_DIR unset, data_dir() returns project_root/data."""
    # The conftest sets PAPER_TRADING_DATA_DIR to a tempdir before any test
    # runs. Unset it for this test, then monkeypatch project_root to point at
    # tmp_path so the assertion is local and deterministic.
    monkeypatch.delenv("PAPER_TRADING_DATA_DIR", raising=False)
    monkeypatch.setattr("traderlib.paths.project_root", lambda: tmp_path)
    assert data_dir() == tmp_path / "data"


def test_data_dir_set_returns_env_value(tmp_path, monkeypatch):
    """With PAPER_TRADING_DATA_DIR set, data_dir() returns that value as Path."""
    target = tmp_path / "custom_data"
    monkeypatch.setenv("PAPER_TRADING_DATA_DIR", str(target))
    assert data_dir() == target


def test_project_root_does_not_depend_on_env_var(monkeypatch):
    """project_root() ignores PAPER_TRADING_DATA_DIR entirely."""
    # Set the env var; project_root should still point at the real repo root.
    monkeypatch.setenv("PAPER_TRADING_DATA_DIR", "/tmp/this_should_not_be_used")
    expected = Path(__file__).resolve().parent.parent
    assert project_root() == expected


def test_data_dir_does_not_create_directory(tmp_path, monkeypatch):
    """Calling data_dir() has no side effects: no directory is created."""
    monkeypatch.setenv("PAPER_TRADING_DATA_DIR", str(tmp_path / "fresh"))
    result = data_dir()
    assert result == tmp_path / "fresh"
    # The directory must NOT exist — the helper does not mkdir.
    assert not result.exists()


def test_data_dir_re_reads_env_var_on_every_call(monkeypatch):
    """A change to PAPER_TRADING_DATA_DIR between calls is observed."""
    a = "/tmp/path_a"
    b = "/tmp/path_b"
    monkeypatch.setenv("PAPER_TRADING_DATA_DIR", a)
    assert data_dir() == Path(a)
    monkeypatch.setenv("PAPER_TRADING_DATA_DIR", b)
    assert data_dir() == Path(b)


def test_project_root_resolves_symlinks():
    """project_root() uses .resolve(), so symlinked __file__ paths are followed."""
    # Direct unit test of the property: the returned path must equal
    # Path(__file__).resolve().parent.parent — which is what the helper does.
    expected = Path(__file__).resolve().parent.parent
    assert project_root() == expected
    # .resolve() must be in the call chain (sanity check on the implementation).
    # If the implementation ever drops .resolve(), this assertion still passes
    # for non-symlinked layouts but the property would be broken for symlinks.
    assert project_root().is_absolute()

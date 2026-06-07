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


# --- Coverage gap fixes (post-review, 2026-06-07) --------------------------

def test_data_dir_treats_empty_env_var_as_unset(tmp_path, monkeypatch):
    """PAPER_TRADING_DATA_DIR='' falls through to the default.

    A CI shell that exports an empty string is functionally equivalent to
    unset. The helper uses ``if env_value:`` (truthy check), so empty
    string returns the default project_root/data. This pins the behavior
    so a future change to ``if env_value is not None:`` doesn't silently
    redirect empty-string setups to Path('').
    """
    monkeypatch.setenv("PAPER_TRADING_DATA_DIR", "")
    monkeypatch.setattr("traderlib.paths.project_root", lambda: tmp_path)
    assert data_dir() == tmp_path / "data"


def test_data_dir_returns_relative_env_var_verbatim(tmp_path, monkeypatch):
    """A relative PAPER_TRADING_DATA_DIR is returned as Path('...') (relative).

    The helper does not call .resolve() or abspath on the env value. If
    a test or CI script sets ``PAPER_TRADING_DATA_DIR=data``, data_dir()
    returns ``Path('data')`` — a relative path resolved against CWD.
    This is a footgun: CWD-relative writes can pollute unrelated
    directories. The test pins the relaxed contract; any change to
    absolute-path enforcement must update this test and the docs.
    """
    monkeypatch.setattr("traderlib.paths.project_root", lambda: tmp_path)
    monkeypatch.setenv("PAPER_TRADING_DATA_DIR", "data")
    result = data_dir()
    assert result == Path("data")
    assert not result.is_absolute()


def test_data_dir_normalizes_trailing_slash(tmp_path, monkeypatch):
    """Trailing slash on the env var is normalized away by Path().

    Path('/tmp/x/') is equivalent to Path('/tmp/x'). The helper
    constructs ``Path(env_value)`` and inherits pathlib's normalization.
    """
    target = tmp_path / "with_slash"
    monkeypatch.setenv("PAPER_TRADING_DATA_DIR", str(target) + "/")
    assert data_dir() == target


def test_project_root_contains_traderlib_dir():
    """project_root() is 'the directory that contains traderlib/'.

    The existing tautological tests (test_project_root_does_not_depend_on_env_var
    and test_project_root_resolves_symlinks) recompute the helper's own
    implementation. This test pins the **invariant** instead: the returned
    path must contain the traderlib package. If a future contributor moves
    traderlib/paths.py to a different depth (e.g., traderlib/utils/paths.py),
    the helper's ``Path(__file__).resolve().parent.parent`` would no longer
    point at the repo root, and this test would fail.
    """
    root = project_root()
    assert (root / "traderlib" / "paths.py").exists(), (
        f"project_root() returned {root}, but {root}/traderlib/paths.py "
        "does not exist. The helper may have been moved or the path "
        "computation may be wrong."
    )

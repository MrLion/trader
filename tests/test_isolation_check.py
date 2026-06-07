"""Self-tests for the conftest production-data safety net.

These tests pin the contract of :mod:`tests._isolation_check` and the
session-scope autouse fixture registered in :mod:`tests.conftest`. They
are deliberately surgical — they do NOT touch the real production
``<project_root>/data/`` tree. Instead, they patch
``_isolation_check._production_data_root`` to point at a temporary
directory, run the snapshot/diff/assert machinery, and reset the module
state between tests so each test sees a clean slate.

The four assertions mirror the four "definition of done" criteria from
Task 4 of the test-isolation hardening plan.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import tests._isolation_check as iso


def _fake_production_root(tmp_path: Path) -> Path:
    """Build a tmp_path-shaped data root for testing the safety net.

    Returns the path to the fake ``data/`` directory inside ``tmp_path``.
    The caller is expected to populate it with files before invoking
    the safety net machinery.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture(autouse=True)
def _reset_isolation_state():
    """Reset module-level snapshot state between tests.

    The conftest fixture caches the production root and snapshot at
    module level. Each self-test needs a clean slate so it can swap in
    a fake root and recapture.
    """
    iso.reset_for_testing()
    yield
    iso.reset_for_testing()


def test_snapshot_captures_current_state(tmp_path):
    """Snapshot a fake data dir and verify it records the expected files.

    Creates a few files, captures a snapshot, and asserts the snapshot
    contains entries for each file with non-empty sha256 hashes. The
    snapshot keys are POSIX-style relative paths; the metadata dicts
    have ``mtime_ns``, ``size``, and ``sha256`` keys.
    """
    root = _fake_production_root(tmp_path)
    (root / "alpha.txt").write_text("alpha")
    (root / "nested").mkdir()
    (root / "nested" / "beta.json").write_text("{}")

    with patch.object(iso, "_production_data_root", return_value=root):
        snapshot = iso._capture_snapshot()

    files = snapshot["files"]
    # The exact key form is implementation-defined, but the contents
    # should mention both files we created.
    assert "alpha.txt" in files
    assert "nested/beta.json" in files

    # Metadata contract.
    for relpath, meta in files.items():
        assert "mtime_ns" in meta
        assert "size" in meta
        assert "sha256" in meta
        assert isinstance(meta["mtime_ns"], int)
        assert meta["size"] > 0
        # Files in this test are tiny, so sha256 must be populated.
        assert meta["sha256"] is not None
        assert len(meta["sha256"]) == 64  # hex sha256 length

    # Directory listings — the root should list both files plus
    # the ``nested`` subdir.
    assert "alpha.txt" in snapshot["dirs"][""]
    assert "nested" in snapshot["dirs"][""]
    assert "beta.json" in snapshot["dirs"]["nested"]


def test_diff_detects_modified_file(tmp_path):
    """Modify a file in the fake root; assert the check reports it.

    Mirrors "the fixture fails when a test modifies a file under data/"
    from the plan. The test calls ``assert_clean_production_data`` and
    expects :class:`AssertionError` mentioning the modified file.
    """
    root = _fake_production_root(tmp_path)
    target = root / "log.txt"
    target.write_text("first line\n")

    with patch.object(iso, "_production_data_root", return_value=root):
        # Establish baseline.
        iso._capture_snapshot()
        # Modify the file: append a line.
        with target.open("a") as f:
            f.write("second line\n")

        with pytest.raises(AssertionError) as excinfo:
            iso.assert_clean_production_data()

    # The error message must mention the modified file by relpath.
    msg = str(excinfo.value)
    assert "log.txt" in msg


def test_diff_detects_new_file(tmp_path):
    """Create a new file in the fake root; assert the check reports it.

    Mirrors "the fixture fails when a test creates a new file under
    data/". The test asserts :class:`AssertionError` is raised and the
    message contains the new file's name.
    """
    root = _fake_production_root(tmp_path)
    (root / "existing.txt").write_text("hello")

    with patch.object(iso, "_production_data_root", return_value=root):
        iso._capture_snapshot()
        # Simulate a polluting test by creating a new file.
        (root / "_isolation_test_artifact.tmp").write_text("polluted")

        with pytest.raises(AssertionError) as excinfo:
            iso.assert_clean_production_data()

    msg = str(excinfo.value)
    assert "_isolation_test_artifact.tmp" in msg
    assert "NEW FILE" in msg


def test_explicit_snapshot_survives_module_cache_reset(tmp_path):
    """The conftest's explicit-snapshot path must catch pollution even
    after a self-test calls ``reset_for_testing()``.

    Reproduces the race: a test runs late in the session, calls
    ``reset_for_testing()`` (clearing the module-level cache), and then
    pollution occurs. The OLD ``assert_clean_production_data()`` would
    see the empty cache and silently no-op. The NEW signature accepts
    explicit ``snapshot`` and ``root`` parameters so the conftest's
    session-scope reference is independent of the module-level cache.
    """
    root = _fake_production_root(tmp_path)
    (root / "clean.txt").write_text("ok")

    with patch.object(iso, "_production_data_root", return_value=root):
        # Capture the way the conftest does: via the underscored helpers
        # into a local variable, NOT into the module-level cache.
        captured_snapshot = iso._compute_snapshot(root)
        captured_root = root

        # Simulate a self-test that resets the module cache after
        # session start (e.g., the last test in the session is a
        # test_isolation_check self-test).
        iso.reset_for_testing()

        # Now pollute the root.
        (root / "post_reset_pollution.tmp").write_text("x")

        # The conftest's path: pass snapshot+root explicitly. Must
        # raise even though the module-level cache is empty.
        with pytest.raises(AssertionError) as excinfo:
            iso.assert_clean_production_data(captured_snapshot, captured_root)

    msg = str(excinfo.value)
    assert "post_reset_pollution.tmp" in msg


def test_is_check_disabled_with_cli_flag():
    """is_check_disabled() reflects sys.argv membership of the flag.

    Tests both directions: with the flag present, the check is disabled.
    Without it, the check is enabled. We save and restore sys.argv so
    the test does not leak state into the rest of the suite.
    """
    original_argv = list(sys.argv)
    try:
        # Flag present.
        sys.argv = ["pytest", "tests/", "--no-isolation-check"]
        assert iso.is_check_disabled() is True

        # Flag absent.
        sys.argv = ["pytest", "tests/"]
        assert iso.is_check_disabled() is False

        # Flag present among many other args.
        sys.argv = [
            "pytest",
            "tests/",
            "-v",
            "--no-isolation-check",
            "-k",
            "test_something",
        ]
        assert iso.is_check_disabled() is True
    finally:
        sys.argv = original_argv


# --- Coverage gap fixes (post-review, 2026-06-07) --------------------------

def test_diff_detects_deleted_file(tmp_path):
    """Removing a file in the production root raises AssertionError.

    The diff machinery at _isolation_check.py:174-176 has a DELETED branch
    but no test ever exercised it. Mirrors the modified-file and new-file
    cases (which ARE tested) and pins the contract that any diff (add,
    modify, delete) raises with the file's relpath in the error message.
    """
    root = _fake_production_root(tmp_path)
    target = root / "to_delete.txt"
    target.write_text("exists")

    with patch.object(iso, "_production_data_root", return_value=root):
        iso._capture_snapshot()
        target.unlink()
        with pytest.raises(AssertionError) as excinfo:
            iso.assert_clean_production_data()

    msg = str(excinfo.value)
    assert "to_delete.txt" in msg
    assert "DELETED" in msg


def test_diff_message_includes_marker_advisory_and_data_path(tmp_path):
    """The error message must mention both opt-out mechanisms AND 'data/'.

    The header in assert_clean_production_data() is the developer-facing
    signal. If a future edit rewords the marker name or removes the
    '--no-isolation-check' advice, developer guidance silently breaks.
    This test pins the three load-bearing substrings.
    """
    root = _fake_production_root(tmp_path)
    (root / "x.txt").write_text("baseline")

    with patch.object(iso, "_production_data_root", return_value=root):
        iso._capture_snapshot()
        (root / "polluted.tmp").write_text("z")
        with pytest.raises(AssertionError) as excinfo:
            iso.assert_clean_production_data()

    msg = str(excinfo.value)
    assert "@pytest.mark.allow_production_writes" in msg, (
        f"Error message must advise the per-test marker. Got: {msg!r}"
    )
    assert "--no-isolation-check" in msg, (
        f"Error message must advise the session-level flag. Got: {msg!r}"
    )
    assert "data/" in msg, (
        f"Error message must mention the data/ path. Got: {msg!r}"
    )


def test_snapshot_with_missing_data_dir_is_noop(tmp_path):
    """Fresh-clone scenario: data/ does not exist. _compute_snapshot
    returns empty; assert_clean_production_data is a no-op (no exception).

    On a clean clone with no `data/` directory, the safety net must not
    raise on the missing-path case. _compute_snapshot handles this by
    returning {'files': {}, 'dirs': {}} for nonexistent roots.
    """
    nonexistent = tmp_path / "data_does_not_exist"
    # Explicitly DO NOT create the directory.

    with patch.object(iso, "_production_data_root", return_value=nonexistent):
        snapshot = iso._compute_snapshot(nonexistent)
        assert snapshot == {"files": {}, "dirs": {}}
        # No exception on assert — first-time runs must not be blocked.
        iso.assert_clean_production_data(snapshot, nonexistent)


@pytest.mark.allow_production_writes
def test_allow_production_writes_marker_is_recognized_by_pytest():
    """The marker must be a recognized pytest marker, not a typo.

    Pytest collects markers based on the registration in
    conftest.py:154-164. If the marker name is misspelled (in this test
    or in the registration), pytest emits ``PytestUnknownMarkWarning``
    at collection time. The absence of that warning here is the proof
    that the marker is recognized.

    **Known limitation (TODO):** the conftest's session-scope safety
    fixture does not currently check this marker — applying
    ``@pytest.mark.allow_production_writes`` to a polluting test will
    NOT prevent the session teardown from failing. The marker is
    registered and the error message advertises it, but the per-test
    opt-out is a no-op. Tracking the implementation in a follow-up:
    the conftest fixture should be function-scope (or paired with a
    function-scope fixture that reads the marker) and short-circuit on
    match. Until then, use ``--no-isolation-check`` for tests that
    intentionally touch production paths.
    """
    # This test body is intentionally empty. The assertion is the
    # absence of "PytestUnknownMarkWarning" warnings during collection,
    # which pytest emits BEFORE this body runs.
    pass

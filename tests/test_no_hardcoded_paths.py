"""Grep-as-test: pin the invariant that production code has no hardcoded paths.

This is the structural defense behind the conftest runtime safety net.
Even with all modules migrated, a future contributor can reintroduce a
hardcoded ``Path(__file__).parent.parent`` or an absolute
``/Users/mintmrlion/.openclaw/workspaces/trader/...`` path. The grep
below runs in a subprocess (so it sees the on-disk state, not any
test-time monkeypatch) and asserts the exit code is 1 (no matches).

If you find yourself wanting to add a new path pattern to the deny list
because your migration introduced one, the answer is: don't. Use
:func:`traderlib.paths.data_dir` or :func:`traderlib.paths.project_root`
instead. This test is enforcing the policy that no new hardcoded paths
land in production code.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Resolve the worktree root. The grep runs from this directory so the
# search scope is exactly ``traderlib/`` and ``scripts/`` — the union
# of all production code in this repository.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_grep(pattern: str) -> str:
    """Run ``grep -rn PATTERN traderlib/ scripts/`` and return matches.

    Uses ``grep`` directly (not the Python ``re`` module) so the test
    matches the exact string a developer would see if they ran the
    same command in a shell. The ``-n`` flag prints line numbers; the
    ``-r`` flag recurses; the ``--include='*.py'`` flag restricts the
    search to ``.py`` source files (we must skip ``__pycache__/*.pyc``
    binaries, which would otherwise match any substring in compiled
    bytecode).

    We then filter out ``sys.path.insert`` lines: those are
    ``import resolution``, not data path resolution, and the plan
    explicitly puts them out of scope. The two patterns share the
    ``Path(__file__).parent.parent`` substring, but only the
    data-path uses are a correctness problem for the test-isolation
    contract.
    """
    result = subprocess.run(
        [
            "grep",
            "-rn",
            "--include=*.py",
            pattern,
            "traderlib/",
            "scripts/",
        ],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=60,
    )
    # Exit code 1 is "no matches" — treat as empty output. Other
    # non-zero exit codes are real errors and surface below.
    if result.returncode not in (0, 1):
        raise AssertionError(
            f"grep exited with unexpected code {result.returncode}.\n"
            f"STDERR:\n{result.stderr}"
        )
    # Filter out sys.path.insert lines (out of scope for this test).
    filtered = [
        line
        for line in result.stdout.splitlines()
        if "sys.path.insert" not in line
    ]
    return "\n".join(filtered)


def test_no_relative_path_pollution_in_production_code():
    """No ``Path(__file__).parent.parent`` remains in traderlib/ or scripts/.

    This pattern was the source of the original test-isolation bug. A
    module that does ``Path(__file__).parent.parent / 'data'`` at
    import time ignores ``PAPER_TRADING_DATA_DIR`` and writes to the
    real ``<project_root>/data/`` directory, which is what we are
    auditing. ``sys.path.insert`` uses of the same pattern are
    filtered out — they affect import resolution, not data writes.
    """
    matches = _run_grep("Path(__file__).parent.parent")
    assert not matches, (
        f"Hardcoded `Path(__file__).parent.parent` was found in "
        f"production code:\n{matches}\n"
        "Replace with a call to traderlib.paths.data_dir() or "
        "traderlib.paths.project_root()."
    )


def test_no_absolute_user_path_in_production_code():
    """No absolute path to this user's home dir is hardcoded anywhere.

    Hardcoding ``/Users/mintmrlion/.openclaw/workspaces/trader/...``
    ties the codebase to one developer's machine. It also bypasses the
    env-var-based isolation contract. Every such path must be replaced
    with a helper call.
    """
    matches = _run_grep("/Users/mintmrlion/.openclaw/workspaces/trader")
    assert not matches, (
        f"Hardcoded absolute path to a developer's home directory was "
        f"found in production code:\n{matches}\n"
        "Replace with traderlib.paths.data_dir() or "
        "traderlib.paths.project_root()."
    )

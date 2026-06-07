"""Conftest safety net: snapshot the production ``data/`` tree and assert it
is unchanged at session teardown.

This module is private to the test suite. It is imported once by
``tests/conftest.py`` to wire up the session-scope autouse fixture that
guards the production data directory.

The contract is simple:

- :func:`_capture_snapshot` records a deterministic, content-aware view of
  the production ``data/`` tree at a point in time. Calling it twice in
  the same process returns the same snapshot (it is cached at module
  level).
- :func:`assert_clean_production_data` walks the tree again and returns
  a list of human-readable diff lines. If any change is detected, the
  caller (the conftest teardown) raises :class:`AssertionError` with the
  diff as the message. The check is intentionally side-effect-free; the
  caller decides what to do on a diff.

Design notes
------------

- This module intentionally does NOT use :func:`traderlib.paths.data_dir`.
  That helper honors ``PAPER_TRADING_DATA_DIR`` and points the test suite
  at a tmp dir. We want the opposite: we want to inspect the *real*
  production ``<project_root>/data/`` directory, which is what a test
  would pollute if it wrote to a hardcoded production path.
- For each file, the snapshot stores ``(relpath, mtime_ns, size,
  sha256_hex_or_None)``. ``sha256`` is computed only for files smaller
  than 1MB. For larger files we compare ``(mtime_ns, size)`` only — the
  trade-off is documented in the plan (large files in ``data/`` are
  intentional; a developer who writes 1MB+ to ``data/`` is a loud
  signal).
- For each directory, the snapshot stores the sorted listing. That lets
  us detect new files, deleted files, and new top-level subdirs.
- The module-level state (``_snapshot``) caches the snapshot so multiple
  calls in the same process see the same baseline. That makes
  ``assert_clean_production_data`` idempotent — once a test session
  fails, re-running it cannot "double-count" the diff.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Module-level state. Populated by _capture_snapshot().
_snapshot: Optional[Dict[str, object]] = None
_production_root: Optional[Path] = None

# Threshold above which we skip sha256 hashing. Picked to balance audit
# coverage with conftest cost: the trading log rotates daily, individual
# log files are well under 1MB.
_HASH_SIZE_LIMIT_BYTES = 1 * 1024 * 1024  # 1MB

# Special CLI flag recognized in sys.argv to disable the safety net.
_DISABLE_FLAG = "--no-isolation-check"


def _production_data_root() -> Path:
    """Return the production ``data/`` directory (NOT the test tmp dir).

    Computed as ``<this_file>/../../data``. This file lives in
    ``tests/_isolation_check.py``; its parent is ``tests/``; its
    grandparent is the project root.
    """
    return Path(__file__).resolve().parent.parent / "data"


def _file_fingerprint(path: Path) -> Dict[str, object]:
    """Compute the per-file snapshot record for a single file.

    Returns a dict with keys: ``mtime_ns``, ``size``, ``sha256``.
    ``sha256`` is a hex string for files < 1MB, or ``None`` for larger
    files (we fall back to mtime+size only, see module docstring).
    """
    stat = path.stat()
    size = stat.st_size
    if size < _HASH_SIZE_LIMIT_BYTES:
        h = hashlib.sha256()
        with path.open("rb") as f:
            # 64KB chunk size is a reasonable default; not tunable.
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        sha256_hex: Optional[str] = h.hexdigest()
    else:
        sha256_hex = None
    return {
        "mtime_ns": stat.st_mtime_ns,
        "size": size,
        "sha256": sha256_hex,
    }


def _compute_snapshot(root: Path) -> Dict[str, object]:
    """Walk ``root`` recursively and return a deterministic snapshot.

    The snapshot is a dict with two keys:

    - ``"files"``: ``{relpath_str: {mtime_ns, size, sha256_or_None}}``
    - ``"dirs"``: ``{relpath_str: [sorted_listing]}`` — keys are the
      relative paths to each directory, INCLUDING the empty string
      ``""`` for the root itself. The listing contains the basenames
      of all immediate children (files and subdirs), sorted.

    The root directory must exist. If it does not, the snapshot is
    empty (empty ``files`` and ``dirs`` dicts). A missing data dir is
    unusual but possible in a fresh checkout.
    """
    files: Dict[str, Dict[str, object]] = {}
    dirs: Dict[str, List[str]] = {}

    if not root.exists():
        return {"files": files, "dirs": dirs}

    # Record the root listing first (relpath "").
    dirs[""] = sorted(p.name for p in root.iterdir())

    # Stack-based walk avoids recursion depth issues on deep trees.
    stack: List[Path] = [root]
    while stack:
        current = stack.pop()
        rel_dir = current.relative_to(root).as_posix()
        for entry in sorted(current.iterdir(), key=lambda p: p.name):
            if entry.is_dir():
                rel_sub = entry.relative_to(root).as_posix()
                dirs[rel_sub] = sorted(p.name for p in entry.iterdir())
                stack.append(entry)
            else:
                # Skip non-file entries (symlinks, sockets, etc.). We are
                # only auditing regular file writes.
                if not entry.is_file():
                    continue
                rel_file = entry.relative_to(root).as_posix()
                files[rel_file] = _file_fingerprint(entry)

    return {"files": files, "dirs": dirs}


def _diff_snapshots(before: Dict[str, object], after: Dict[str, object]) -> List[str]:
    """Diff two snapshots and return a list of human-readable strings.

    Each string describes one change. The format is stable because the
    conftest teardown reports the joined diff to the developer; we
    should not gratuitously reformat these messages.

    Edge cases handled:

    - Modified file: mtime or size or sha256 changed.
    - New file: relpath present in ``after`` but not ``before``.
    - Deleted file: relpath present in ``before`` but not ``after``.
    - New top-level subdir: dir entry at relpath ``""`` listing contains
      an entry in ``after`` that was not in ``before``.
    - Deleted top-level subdir: opposite.
    - New nested subdir: any dir entry beyond ``""`` appears in ``after``
      but not ``before`` (and is reported as a new subdir at that path).
    """
    diffs: List[str] = []

    before_files: Dict[str, Dict[str, object]] = before.get("files", {})  # type: ignore[assignment]
    after_files: Dict[str, Dict[str, object]] = after.get("files", {})  # type: ignore[assignment]
    before_dirs: Dict[str, List[str]] = before.get("dirs", {})  # type: ignore[assignment]
    after_dirs: Dict[str, List[str]] = after.get("dirs", {})  # type: ignore[assignment]

    # --- File-level diffs ---
    for relpath in sorted(set(before_files) | set(after_files)):
        b = before_files.get(relpath)
        a = after_files.get(relpath)
        if b is None and a is not None:
            diffs.append(f"data/{relpath}: NEW FILE created")
            continue
        if a is None and b is not None:
            diffs.append(f"data/{relpath}: DELETED")
            continue
        # Both exist; compare.
        assert b is not None and a is not None
        size_b = b["size"]
        size_a = a["size"]
        mtime_b = b["mtime_ns"]
        mtime_a = a["mtime_ns"]
        sha_b = b["sha256"]
        sha_a = a["sha256"]
        # We describe a change as "size or mtime or sha" — pick the
        # most informative single message. If sha256 disagrees, the
        # content changed; we lead with that.
        if sha_b is not None and sha_a is not None and sha_b != sha_a:
            diffs.append(
                f"data/{relpath}: content changed (sha256 mismatch), "
                f"size {size_b} -> {size_a}"
            )
        elif size_b != size_a or mtime_b != mtime_a:
            diffs.append(
                f"data/{relpath}: mtime changed ({mtime_b} -> {mtime_a}), "
                f"size {size_b} -> {size_a}"
            )

    # --- Directory listing diffs ---
    for relpath in sorted(set(before_dirs) | set(after_dirs)):
        b = before_dirs.get(relpath)
        a = after_dirs.get(relpath)
        if b is None and a is not None:
            label = "data" if relpath == "" else f"data/{relpath}"
            diffs.append(f"{label}/: new directory created")
            continue
        if a is None and b is not None:
            label = "data" if relpath == "" else f"data/{relpath}"
            diffs.append(f"{label}/: DELETED")
            continue
        assert b is not None and a is not None
        b_set, a_set = set(b), set(a)
        for added in sorted(a_set - b_set):
            if relpath == "":
                # Top-level entry — describe as a subdir since data/
                # is reserved for production data files and any new
                # subdir is unusual enough to flag.
                diffs.append(f"data/: new top-level subdir 'data/{added}/'")
            else:
                diffs.append(f"data/{relpath}/: new entry '{added}'")
        for removed in sorted(b_set - a_set):
            if relpath == "":
                diffs.append(f"data/: removed top-level entry '{removed}'")
            else:
                diffs.append(f"data/{relpath}/: removed entry '{removed}'")

    return diffs


def _capture_snapshot() -> Dict[str, object]:
    """Capture and cache the current state of the production ``data/`` tree.

    The first call computes the snapshot. Subsequent calls return the
    same cached object — the safety net's baseline is fixed for the
    life of the process. This makes ``assert_clean_production_data``
    idempotent: re-running a failed test session does not double-count
    the diff.
    """
    global _snapshot, _production_root
    if _snapshot is None:
        _production_root = _production_data_root()
        _snapshot = _compute_snapshot(_production_root)
    return _snapshot


def assert_clean_production_data(
    snapshot: Optional[Dict[str, object]] = None,
    root: Optional[Path] = None,
) -> None:
    """Walk ``data/`` again and raise :class:`AssertionError` if changed.

    Two calling conventions:

    1. **With explicit args** (used by the session conftest): the caller
       passes the snapshot it captured at session start and the root it
       snapshotted. This decouples the conftest's baseline from the
       module-level cache, so a subsequent ``reset_for_testing()`` call
       from a self-test cannot retroactively disable the safety net.
    2. **No args** (legacy / used by self-tests): falls back to the
       module-level cache. If the cache is empty (no snapshot captured
       this process, or it was reset), this is a no-op — we do not raise
       on a missing snapshot, since ``--no-isolation-check`` is a
       legitimate way to opt out.
    """
    if snapshot is None:
        # Legacy path: use module-level cache. The cache may be None
        # (e.g., --no-isolation-check was passed, or a self-test reset
        # it after the session teardown started). Silent no-op matches
        # the documented contract.
        snapshot = _snapshot
    if root is None:
        root = _production_root
    if snapshot is None or root is None:
        return
    after = _compute_snapshot(root)
    diffs = _diff_snapshots(snapshot, after)
    if diffs:
        header = (
            "Test run modified production data/. The following changes "
            "were detected between session start and session teardown. "
            "Use @pytest.mark.allow_production_writes on tests that "
            "intentionally touch production paths, or pass "
            "--no-isolation-check to skip this check.\n"
        )
        raise AssertionError(header + "\n".join(diffs))


def is_check_disabled() -> bool:
    """Return True if the user passed ``--no-isolation-check`` to pytest.

    We check ``sys.argv`` rather than a pytest flag because the check
    fires at conftest load time, before pytest's option parsing
    completes. This is a debug hatch, not a stable contract.
    """
    return _DISABLE_FLAG in sys.argv


def reset_for_testing() -> None:
    """Clear the cached snapshot. Used by self-tests in
    ``tests/test_isolation_check.py`` to swap the production root
    between tests.
    """
    global _snapshot, _production_root
    _snapshot = None
    _production_root = None

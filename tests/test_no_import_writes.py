"""Pin the no-import-time-write invariant for :mod:`traderlib.trading_exceptions`.

This test launches a fresh Python subprocess that does nothing but
``import traderlib.trading_exceptions``. It then asserts:

1. The production ``<project_root>/data/logs/trading_exceptions.log`` was
   not created (or, if it existed before, was not modified) by the import.
2. The ``trading`` logger in the subprocess has zero handlers attached —
   the FileHandler must not be wired up at import time.

If either invariant breaks, the import is doing eager I/O to a hardcoded
production path. That is the regression Task 2 of the test-isolation
hardening plan is designed to prevent.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest


# Resolve production paths relative to the repo root (parent of ``tests/``).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROD_LOG_FILE = PROJECT_ROOT / "data" / "logs" / "trading_exceptions.log"
PROD_LOG_DIR = PROJECT_ROOT / "data" / "logs"


SUBPROCESS_SCRIPT = textwrap.dedent(
    """
    import json
    import logging
    import os
    import sys

    # Print handlers of the 'trading' logger AFTER import, then exit.
    # We emit a single JSON line so the parent test can parse it cleanly.
    import traderlib.trading_exceptions  # noqa: F401

    trading_logger = logging.getLogger('trading')
    handler_count = len(trading_logger.handlers)
    handler_types = [type(h).__name__ for h in trading_logger.handlers]
    print('IMPORT_HANDLERS_JSON=' + json.dumps({
        'handler_count': handler_count,
        'handler_types': handler_types,
        'traderlib_path': os.path.dirname(traderlib.trading_exceptions.__file__),
    }))
    sys.stdout.flush()
    """
)


def _run_subprocess_import():
    """Spawn a fresh Python interpreter that imports the module.

    We strip ``PAPER_TRADING_DATA_DIR`` and ``PAPER_TRADING_TEST_MODE`` from
    the child's environment so the child sees the same "unconfigured"
    environment that production callers see at first import.
    """
    env = os.environ.copy()
    env.pop("PAPER_TRADING_DATA_DIR", None)
    env.pop("PAPER_TRADING_TEST_MODE", None)
    # Make sure the project root is on PYTHONPATH so the import resolves.
    env["PYTHONPATH"] = (
        str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    )
    result = subprocess.run(
        [sys.executable, "-c", SUBPROCESS_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )
    return result


def _parse_subprocess_output(result: subprocess.CompletedProcess) -> dict:
    """Extract the JSON status line from the subprocess output."""
    for line in result.stdout.splitlines():
        if line.startswith("IMPORT_HANDLERS_JSON="):
            import json

            return json.loads(line[len("IMPORT_HANDLERS_JSON=") :])
    raise AssertionError(
        "Subprocess did not emit the expected status line.\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def _ensure_prod_log_dir_exists() -> None:
    """Make sure ``data/logs`` exists for the stat checks; do not touch the
    log file itself. If the dir is missing, the file is also missing, which
    is already the desired state.
    """
    PROD_LOG_DIR.mkdir(parents=True, exist_ok=True)


def test_subprocess_import_creates_no_file_handlers():
    """``import traderlib.trading_exceptions`` must attach zero handlers."""
    result = _run_subprocess_import()
    assert result.returncode == 0, (
        f"Subprocess failed (rc={result.returncode}).\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    status = _parse_subprocess_output(result)
    assert status["handler_count"] == 0, (
        f"Importing traderlib.trading_exceptions attached "
        f"{status['handler_count']} handler(s): {status['handler_types']}. "
        "The logger must be initialized lazily so that import alone creates "
        "no handlers and no files."
    )


def test_subprocess_import_does_not_touch_production_log_file():
    """Importing the module must not create or modify the production log file.

    We snapshot the file's mtime+size before the subprocess runs and
    compare after. If the file did not exist before and does not exist
    after, that is the cleanest possible outcome. If it existed, mtime and
    size must be unchanged (with a tiny tolerance to absorb sub-second
    filesystem timestamp noise).
    """
    _ensure_prod_log_dir_exists()

    pre_exists = PROD_LOG_FILE.exists()
    if pre_exists:
        pre_stat = PROD_LOG_FILE.stat()
        pre_mtime = pre_stat.st_mtime
        pre_size = pre_stat.st_size
    else:
        pre_mtime = None
        pre_size = None

    result = _run_subprocess_import()
    assert result.returncode == 0, (
        f"Subprocess failed (rc={result.returncode}).\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    # Give the filesystem a brief moment to settle timestamp updates, then
    # snapshot the post-import state.
    time.sleep(0.05)
    post_exists = PROD_LOG_FILE.exists()
    if post_exists:
        post_stat = PROD_LOG_FILE.stat()
        post_mtime = post_stat.st_mtime
        post_size = post_stat.st_size
    else:
        post_mtime = None
        post_size = None

    # If the file did not exist before, it must not exist after.
    if not pre_exists:
        assert not post_exists, (
            f"Importing traderlib.trading_exceptions created "
            f"{PROD_LOG_FILE}. The module must not write to production "
            "paths at import time."
        )
        return

    # Both states exist; mtime and size must match.
    # Allow a 1.0s tolerance on mtime to absorb filesystem clock skew.
    assert abs(post_mtime - pre_mtime) < 1.0, (
        f"Importing traderlib.trading_exceptions modified the mtime of "
        f"{PROD_LOG_FILE} (pre={pre_mtime}, post={post_mtime}). "
        "The module must not write to production paths at import time."
    )
    assert post_size == pre_size, (
        f"Importing traderlib.trading_exceptions changed the size of "
        f"{PROD_LOG_FILE} (pre={pre_size}, post={post_size}). "
        "The module must not write to production paths at import time."
    )


def test_subprocess_import_writes_no_log_directory_at_all():
    """Extra safety: the ``data/logs/`` directory listing is unchanged.

    We compare the directory listing of ``data/logs/`` before and after the
    subprocess runs. Any new file (even non-log files) added by the import
    is a hard failure. This catches the case where a future contributor
    changes the log filename but still writes to the same directory.
    """
    _ensure_prod_log_dir_exists()

    pre_listing = sorted(os.listdir(PROD_LOG_DIR)) if PROD_LOG_DIR.exists() else []

    result = _run_subprocess_import()
    assert result.returncode == 0, (
        f"Subprocess failed (rc={result.returncode}).\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    time.sleep(0.05)
    post_listing = sorted(os.listdir(PROD_LOG_DIR)) if PROD_LOG_DIR.exists() else []

    new_entries = sorted(set(post_listing) - set(pre_listing))
    assert not new_entries, (
        f"Importing traderlib.trading_exceptions added files to "
        f"{PROD_LOG_DIR}: {new_entries}. The module must not create files "
        "in production paths at import time."
    )

"""Single source of truth for filesystem paths in the trader project.

Every module that needs to know where the project root is, or where the
writable data directory lives, imports from here. Centralizing path
resolution means there is exactly one place that knows about
``PAPER_TRADING_DATA_DIR`` and the project layout.

Contract
--------
- :func:`project_root` returns the repo root. It is fixed and does not
  read any environment variable. ``Path(__file__).resolve().parent.parent``
  is used so symlinks are followed.
- :func:`data_dir` returns the writable data directory. It reads
  ``PAPER_TRADING_DATA_DIR`` on every call (no caching) and falls back
  to ``<project_root>/data`` if the env var is unset. It performs no I/O
  (no ``mkdir``); callers that need the directory to exist call
  ``data_dir().mkdir(parents=True, exist_ok=True)`` themselves.
"""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """Return the repository root (the directory containing ``traderlib/``)."""
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Return the writable data directory.

    Honors ``PAPER_TRADING_DATA_DIR`` if set, otherwise returns
    ``<project_root>/data``. The env var is read on every call so tests
    that mutate ``os.environ`` mid-run see the new value.
    """
    env_value = os.environ.get("PAPER_TRADING_DATA_DIR")
    if env_value:
        return Path(env_value)
    return project_root() / "data"

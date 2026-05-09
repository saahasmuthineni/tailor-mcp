"""
Centralized environment-variable and user-config readers.

Single point of truth for the framework's environment-derived paths
and on-disk user configuration. CLI commands, the wizard, and child
implementations all read from here so a future config-store change
(e.g. honoring XDG paths, adding a `--config-dir` CLI flag) lands in
exactly one place.

Variables:
    BIOSENSOR_CONFIG_DIR — token, user_config.json, rate_limit.json.
                           Default: ~/.tailor
    BIOSENSOR_DATA_DIR   — SQLite databases (audit, vault index,
                           per-child caches).
                           Default: $BIOSENSOR_CONFIG_DIR/data

Per-child env vars (e.g. STRAVA_STREAM_CACHE_TTL_DAYS) stay in the
child module that owns them — those are domain-specific tuning
parameters, not framework-level config.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger("tailor.config")


def config_dir() -> Path:
    """The framework's per-user config directory (tokens, user_config.json)."""
    return Path(os.environ.get("BIOSENSOR_CONFIG_DIR", Path.home() / ".tailor"))


def data_dir() -> Path:
    """The framework's per-user data directory (SQLite databases)."""
    return Path(os.environ.get("BIOSENSOR_DATA_DIR", config_dir() / "data"))


def log_dir() -> Path:
    """The framework's per-user log directory."""
    return config_dir() / "logs"


def user_config_path(directory: Path | None = None) -> Path:
    """Path to the user_config.json file under ``config_dir`` (or override)."""
    return (directory or config_dir()) / "user_config.json"


def load_user_config(directory: Path | None = None) -> dict:
    """
    Load and parse user_config.json. Returns an empty dict on any
    failure (missing file, parse error, OS error). Logs at warning
    level.

    The CLI's ``cmd_serve()`` wraps this with a louder, banner-style
    parse-error report on stderr because that is a UX requirement
    specific to the server-launch path. Other callers (children,
    wizard, status) get the quiet behavior.
    """
    path = user_config_path(directory)
    if not path.exists():
        return {}
    try:
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning(f"Could not read {path}: {exc}. Returning empty config.")
        return {}


# Convenience module-level constants. Most callers want the function
# form so the resolution happens at call time (tests can monkeypatch
# the environment), but a small number of consumers want a one-liner.
# These resolve at import time and are NOT re-read if env vars change.
CONFIG_DIR = config_dir()
DATA_DIR = data_dir()
LOG_DIR = log_dir()

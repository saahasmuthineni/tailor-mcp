"""
Running Child — Strava API Layer
=================================
OAuth token management, rate-limit awareness, and Strava API calls.
"""

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

from ...framework.middleware import _dumps, _loads

log = logging.getLogger("biosensor-mcp.running")

# Default request timeout: (connect_timeout, read_timeout) in seconds
_REQUEST_TIMEOUT = (5, 30)


def _secure_file_permissions(path: Path) -> None:
    """
    Restrict a file to owner-read-only.

    Unix: os.chmod(0o600) — removes group/world permissions.
    Windows: os.chmod() only toggles the read-only flag and does NOT apply
    Unix-style ACL bits. We use icacls instead to remove inherited permissions
    and grant access only to the current user.
    """
    if sys.platform == "win32":
        import subprocess
        username = os.environ.get("USERNAME", "")
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:F"],
            capture_output=True, check=False,
        )
    else:
        os.chmod(path, 0o600)


class StravaAPI:
    """
    OAuth token management and API calls with rate-limit awareness.

    Strava enforces:
      - 100 requests per 15-minute window
      - 1,000 requests per day

    This client tracks request timestamps and raises before hitting
    the limit, rather than waiting for a 429 response.
    """

    BASE_URL = "https://www.strava.com/api/v3"
    RATE_LIMIT_15MIN = 100
    RATE_LIMIT_DAILY = 1000

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.token_file = config_dir / "tokens.json"
        self._rate_limit_file = config_dir / "rate_limit.json"
        self._tokens = None
        self._request_timestamps: list[float] = self._load_rate_limit_timestamps()

    @property
    def tokens(self) -> dict:
        if self._tokens is None:
            if not self.token_file.exists():
                raise RuntimeError("Not authenticated. Run: biosensor-mcp setup")
            self._tokens = _loads(self.token_file.read_text())
        return self._tokens

    def _load_rate_limit_timestamps(self) -> list[float]:
        """Load persisted rate-limit timestamps, pruning entries older than 24h."""
        try:
            if self._rate_limit_file.exists():
                data = _loads(self._rate_limit_file.read_text())
                now = time.time()
                return [t for t in data if now - t < 86400]
        except (OSError, ValueError, TypeError) as exc:
            # Corrupt or unreadable rate-limit file → reset the counter but
            # warn so a user investigating surprise 429s sees a breadcrumb.
            log.warning(
                f"Could not load rate-limit timestamps from {self._rate_limit_file}: {exc}. "
                f"Counter reset; Strava limits may be closer than tracked."
            )
        return []

    def _save_rate_limit_timestamps(self) -> None:
        """Persist current rate-limit timestamps so they survive process restarts."""
        try:
            self._rate_limit_file.parent.mkdir(parents=True, exist_ok=True)
            self._rate_limit_file.write_text(_dumps(self._request_timestamps))
        except Exception as exc:
            log.warning(f"Could not persist rate-limit timestamps: {exc}")

    def _save_tokens(self, tokens: dict):
        self._tokens = tokens
        self.token_file.write_text(_dumps(tokens))
        _secure_file_permissions(self.token_file)

    def _refresh_if_needed(self):
        if time.time() >= self.tokens.get("expires_at", 0):
            log.info("Refreshing Strava access token...")
            resp = requests.post(
                "https://www.strava.com/oauth/token",
                data={
                    "client_id": self.tokens["client_id"],
                    "client_secret": self.tokens["client_secret"],
                    "grant_type": "refresh_token",
                    "refresh_token": self.tokens["refresh_token"],
                },
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            new = resp.json()
            self.tokens.update(
                {
                    "access_token": new["access_token"],
                    "refresh_token": new["refresh_token"],
                    "expires_at": new["expires_at"],
                }
            )
            self._save_tokens(self.tokens)

    def _check_rate_limit(self):
        """Raise before hitting Strava's rate limit. Timestamps are persisted
        across restarts so the counter does not reset when the process exits."""
        now = time.time()

        # 15-minute window check
        recent_15min = [t for t in self._request_timestamps if now - t < 900]
        self._request_timestamps = recent_15min
        if self.RATE_LIMIT_15MIN - len(recent_15min) <= 5:
            oldest = min(recent_15min) if recent_15min else now
            wait = int(900 - (now - oldest))
            raise RuntimeError(
                f"Approaching Strava rate limit "
                f"({len(recent_15min)}/{self.RATE_LIMIT_15MIN} "
                f"in 15min window). Try again in {wait}s."
            )

        # Daily limit check (1,000 req/day)
        daily_count = sum(1 for t in self._request_timestamps if now - t < 86400)
        if self.RATE_LIMIT_DAILY - daily_count <= 50:
            raise RuntimeError(
                f"Approaching Strava daily rate limit "
                f"({daily_count}/{self.RATE_LIMIT_DAILY} today). "
                f"Limit resets at midnight Pacific time."
            )

    def get(self, endpoint: str, **params) -> Any:
        """Make an authenticated GET request to the Strava API."""
        self._check_rate_limit()
        self._refresh_if_needed()
        headers = {"Authorization": f"Bearer {self.tokens['access_token']}"}
        resp = requests.get(
            f"{self.BASE_URL}/{endpoint}",
            headers=headers,
            params=params,
            timeout=_REQUEST_TIMEOUT,
        )
        self._request_timestamps.append(time.time())
        self._save_rate_limit_timestamps()

        if resp.status_code == 429:
            raise RuntimeError("Strava API rate limit exceeded. Try again later.")
        resp.raise_for_status()
        return resp.json()


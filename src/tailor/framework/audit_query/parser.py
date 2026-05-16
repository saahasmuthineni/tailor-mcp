"""
``since`` parameter parser for the audit_query layer.

Accepts two input shapes:

* Relative durations: ``1h`` / ``24h`` / ``7d`` / ``1w`` (case-insensitive,
  positive integers only).
* ISO 8601 timestamps: ``2026-05-16T12:00:00Z``,
  ``2026-05-16T12:00:00+00:00``, or naive ``2026-05-16T12:00:00``
  (coerced to UTC).

Rejects malformed strings, negative durations, future timestamps, and
lookback windows beyond :data:`MAX_LOOKBACK_DAYS` (90 days by default).
The cap exists as defense in depth — a researcher legitimately needing
a longer window can drop to ``sqlite3 audit.db`` directly; the LLM-
callable surface stays bounded. Reversal condition for the cap is named
in the v7.4.0 audit's NICE-TO-HAVE-2 (config-driven via
``audit_query.max_lookback_days`` in ``user_config.json``).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

#: Hard cap on the ``since`` lookback window (days). Defense in depth —
#: the layer's ToolDefinition documents this; the parser enforces it
#: independent of caller behavior.
MAX_LOOKBACK_DAYS = 90

_RELATIVE_RE = re.compile(r"^(\d+)\s*([hdw])$", re.IGNORECASE)
_UNIT_TO_DELTA = {
    "h": lambda n: timedelta(hours=n),
    "d": lambda n: timedelta(days=n),
    "w": lambda n: timedelta(weeks=n),
}


class SinceParseError(ValueError):
    """Raised when a ``since`` parameter cannot be parsed.

    Carries the original input so the audit row's ``error`` column
    and the wire envelope can both name what the caller actually sent.
    """

    def __init__(self, message: str, *, original: str) -> None:
        super().__init__(message)
        self.original = original


def parse_since(value: str, *, now: datetime | None = None) -> str:
    """Parse a ``since`` parameter into an ISO-8601 UTC timestamp string.

    The return value is in the lexicographic-safe UTC format that
    ``audit.py:_wire_default`` emits so it can be passed directly to
    ``audit_log.timestamp >= ?`` SQL comparison without timezone drift.

    Args:
        value: The raw ``since`` parameter. Must be a non-empty
            string in one of the documented forms.
        now: Optional override for the "current time" anchor used by
            the relative-form computation and the lookback cap.
            Defaults to ``datetime.now(timezone.utc)``. Test-only
            seam — production never passes this.

    Returns:
        ISO 8601 UTC timestamp string.

    Raises:
        SinceParseError: For empty input, negative durations, malformed
            strings, future timestamps, or lookback beyond
            :data:`MAX_LOOKBACK_DAYS`.
    """
    if not isinstance(value, str) or not value.strip():
        raise SinceParseError(
            "since must be a non-empty string (ISO timestamp or "
            "relative form like '1h' / '7d')",
            original=str(value),
        )

    now = now or datetime.now(timezone.utc)
    cap = now - timedelta(days=MAX_LOOKBACK_DAYS)
    stripped = value.strip()

    # ── Relative form ──
    m = _RELATIVE_RE.match(stripped)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if n <= 0:
            raise SinceParseError(
                f"since='{value}' must be a positive duration",
                original=value,
            )
        delta = _UNIT_TO_DELTA[unit](n)
        ts = now - delta
        if ts < cap:
            raise SinceParseError(
                f"since='{value}' exceeds the "
                f"{MAX_LOOKBACK_DAYS}-day lookback cap",
                original=value,
            )
        return ts.isoformat()

    # ── ISO 8601 form ──
    try:
        ts = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        raise SinceParseError(
            f"since='{value}' is not a recognised relative duration "
            f"(e.g. '1h', '7d') or ISO 8601 timestamp",
            original=value,
        ) from None

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)

    if ts > now:
        raise SinceParseError(
            f"since='{value}' is in the future; no audit rows will "
            f"match. Use a past timestamp or a relative form like '1h'.",
            original=value,
        )
    if ts < cap:
        raise SinceParseError(
            f"since='{value}' exceeds the {MAX_LOOKBACK_DAYS}-day "
            f"lookback cap (oldest accepted: {cap.isoformat()})",
            original=value,
        )

    return ts.isoformat()


__all__ = ["MAX_LOOKBACK_DAYS", "SinceParseError", "parse_since"]

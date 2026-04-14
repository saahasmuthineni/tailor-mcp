"""
Stateless analytics for the CSV directory child.

Every method is a ``@staticmethod`` — no instance state, no I/O,
independently testable with no fixtures.  This mirrors the split
enforced by both existing children (``child.py`` owns I/O and
dispatch, ``processing.py`` owns pure-function transformations).
"""

from __future__ import annotations

from datetime import datetime
from statistics import fmean, stdev


class CSVProcessing:
    """Pure-function analytics for tabular CSV data."""

    @staticmethod
    def summarize_column(values: list[float]) -> dict:
        """Per-column summary: count, mean, min, max, std.

        Returns nulls for empty input, std=0 for single-element input.
        """
        if not values:
            return {"count": 0, "mean": None, "min": None, "max": None, "std": None}
        result: dict = {
            "count": len(values),
            "mean": round(fmean(values), 3),
            "min": min(values),
            "max": max(values),
        }
        result["std"] = round(stdev(values), 3) if len(values) > 1 else 0.0
        return result

    @staticmethod
    def downsample_rows(rows: list[dict], interval: int) -> list[dict]:
        """Return every Nth row.  Raises ValueError if interval < 1."""
        if interval < 1:
            raise ValueError("interval must be >= 1")
        return rows[::interval]

    @staticmethod
    def detect_timestamp_column(headers: list[str]) -> str | None:
        """Heuristic: return the first header matching a common timestamp name."""
        candidates = {
            "timestamp", "time", "datetime", "date",
            "recorded_at", "created_at", "date_time",
        }
        for header in headers:
            if header.strip().lower() in candidates:
                return header
        return None

    @staticmethod
    def parse_timestamp(value: str, fmt: str | None = None) -> datetime | None:
        """Parse a single timestamp string.  Returns None on failure."""
        try:
            if fmt:
                return datetime.strptime(value.strip(), fmt)
            return datetime.fromisoformat(value.strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def estimate_row_tokens(row_count: int, col_count: int) -> int:
        """Heuristic token estimate: ~8 chars/cell, ~4 chars/token."""
        return row_count * col_count * 2

    @staticmethod
    def reduce_precision(value: float, decimals: int = 2) -> float:
        """Round a numeric value for Tier-3 output."""
        return round(value, decimals)

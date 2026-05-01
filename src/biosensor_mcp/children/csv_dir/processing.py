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

# Per-file metric vocabulary for csv_cohort_summary. Each metric reduces
# a column-of-values (and optional timestamps) to a single scalar before
# cohort-level aggregation. See ADR 0015.
COHORT_METRICS = (
    "mean",
    "max",
    "min",
    "std",
    "peak",          # alias of max — domain-readable for force/EMG
    "first",
    "last",
    "duration_s",            # requires timestamps; last - first
    "time_to_50pct_drop_s",  # requires timestamps; peak → first sample <= peak/2
)


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

    # ═══════════════════════════════════════════════════════════════
    # COHORT METRICS (Tier-1 cross-file aggregation, ADR 0015)
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def aggregate_metric(
        values: list[float],
        timestamps: list[datetime] | None,
        metric: str,
    ) -> float | None:
        """Reduce one column's values to a single scalar by ``metric``.

        Pure function — same inputs always produce same output. No PRNG,
        no clock reads. Per ADR 0008.

        Returns ``None`` when the metric cannot be computed (empty input,
        timestamps required but absent, ``time_to_50pct_drop_s`` never
        reached). Raises ``ValueError`` for unknown ``metric`` strings so
        the dispatch layer can surface the typo rather than silently
        returning None.
        """
        if metric not in COHORT_METRICS:
            raise ValueError(
                f"Unknown metric: {metric}. Supported: {list(COHORT_METRICS)}"
            )
        if not values:
            return None
        if metric == "mean":
            return round(fmean(values), 3)
        if metric in ("max", "peak"):
            return max(values)
        if metric == "min":
            return min(values)
        if metric == "std":
            return round(stdev(values), 3) if len(values) > 1 else 0.0
        if metric == "first":
            return values[0]
        if metric == "last":
            return values[-1]
        if metric == "duration_s":
            if not timestamps or len(timestamps) < 2:
                return None
            return round((timestamps[-1] - timestamps[0]).total_seconds(), 3)
        if metric == "time_to_50pct_drop_s":
            if not timestamps or len(timestamps) != len(values):
                return None
            peak = max(values)
            if peak <= 0:
                return None
            peak_idx = values.index(peak)
            threshold = peak * 0.5
            for i in range(peak_idx + 1, len(values)):
                if values[i] <= threshold:
                    return round(
                        (timestamps[i] - timestamps[peak_idx]).total_seconds(), 3,
                    )
            return None
        # Defensive: COHORT_METRICS membership is checked above; an
        # unhandled name is a programmer error if this branch is ever
        # reached.
        raise ValueError(f"Unhandled metric branch: {metric}")  # pragma: no cover

    @staticmethod
    def cohort_stats(per_file_values: list[float | None]) -> dict:
        """Reduce per-file scalars to cohort-level statistics.

        Drops ``None`` entries (e.g. files where the metric could not be
        computed) before aggregating; the caller sees the dropped count
        as ``n_missing``. Returns count/mean/std/min/max with ``None``
        for empty input and std=0.0 for single-sample input — same shape
        as ``summarize_column`` so the renderer can treat both uniformly.
        """
        cleaned = [v for v in per_file_values if v is not None]
        n_missing = len(per_file_values) - len(cleaned)
        if not cleaned:
            return {
                "n": 0, "n_missing": n_missing,
                "mean": None, "std": None, "min": None, "max": None,
            }
        return {
            "n": len(cleaned),
            "n_missing": n_missing,
            "mean": round(fmean(cleaned), 3),
            "std": round(stdev(cleaned), 3) if len(cleaned) > 1 else 0.0,
            "min": min(cleaned),
            "max": max(cleaned),
        }

    @staticmethod
    def force_decline_summary(
        values: list[float],
        timestamps: list[datetime] | None = None,
    ) -> dict:
        """Per-file fatigue diagnostic: peak, end, decline %, decline rate.

        Generic enough to apply to any monotonically-fatigueing column
        (force, power, EMG envelope) — the column choice and what counts
        as "fatigue" are the caller's domain question. Pure function.

        Returns a dict with at least ``peak``, ``peak_index``,
        ``end_value``, ``n_samples``, ``decline_pct_total``. When
        timestamps are supplied (length must equal ``values``), also
        returns ``peak_time_s``, ``duration_s``, ``decline_rate_per_min``,
        and ``time_to_50pct_drop_s`` (``None`` if the column never drops
        below 50% of peak).
        """
        if not values:
            return {"error": "no values"}
        peak = max(values)
        peak_idx = values.index(peak)
        end = values[-1]
        decline_pct = (
            round((peak - end) / peak * 100, 2) if peak > 0 else 0.0
        )
        result: dict = {
            "peak": round(peak, 3),
            "peak_index": peak_idx,
            "end_value": round(end, 3),
            "n_samples": len(values),
            "decline_pct_total": decline_pct,
        }
        if timestamps and len(timestamps) == len(values):
            peak_time = timestamps[peak_idx]
            t0 = timestamps[0]
            elapsed_s = (timestamps[-1] - peak_time).total_seconds()
            elapsed_min = elapsed_s / 60.0
            result["peak_time_s"] = round((peak_time - t0).total_seconds(), 3)
            result["duration_s"] = round(
                (timestamps[-1] - t0).total_seconds(), 3,
            )
            if elapsed_min > 0:
                result["decline_rate_per_min"] = round(
                    (peak - end) / elapsed_min, 3,
                )
            else:
                result["decline_rate_per_min"] = 0.0
            threshold = peak * 0.5
            time_to_50: float | None = None
            for i in range(peak_idx + 1, len(values)):
                if values[i] <= threshold:
                    time_to_50 = (timestamps[i] - peak_time).total_seconds()
                    break
            result["time_to_50pct_drop_s"] = (
                round(time_to_50, 3) if time_to_50 is not None else None
            )
        return result

    @staticmethod
    def downsample_rows(rows: list[dict], interval: int) -> list[dict]:
        """Return every Nth row.  Raises ValueError if interval < 1."""
        if interval < 1:
            raise ValueError("interval must be >= 1")
        return rows[::interval]

    @staticmethod
    def detect_timestamp_column(headers: list[str]) -> str | None:
        """Heuristic: return the first header matching a common timestamp name.

        Checks exact matches first, then substring matches for names
        like ``reading_time`` or ``event_timestamp``.
        """
        # Exact matches (highest confidence)
        exact = {
            "timestamp", "time", "datetime", "date",
            "recorded_at", "created_at", "date_time",
            "ts", "event_time", "reading_time", "sample_time",
            "start_time", "end_time", "epoch", "unix_time",
        }
        for header in headers:
            if header.strip().lower() in exact:
                return header
        # Substring matches (lower confidence)
        substrings = ("timestamp", "datetime", "date_time", "_time", "_date")
        for header in headers:
            lower = header.strip().lower()
            if any(s in lower for s in substrings):
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

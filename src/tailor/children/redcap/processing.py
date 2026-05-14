"""
Stateless analytics for the REDCap file child.

Every method is a ``@staticmethod`` — no instance state, no I/O,
no PRNG, no clock reads. Per ADR 0008.

REDCap data is record-oriented and mixes numeric and categorical
fields freely; this module's distinguishing feature vs the matlab_file
/ csv_dir processing modules is the ``summarize_field`` auto-detection
of numeric vs categorical and the ``mode`` / ``count`` additions to
``COHORT_METRICS`` for categorical aggregation.
"""

from __future__ import annotations

from collections import Counter
from statistics import fmean, stdev

# Per-field metric vocabulary for redcap_cohort_summary. Per ADR 0037:
# ``mean / max / min / std`` are numeric-only; ``first / last / mode /
# count`` apply to either kind. ``count`` is a non-null count — useful
# for "how many subjects in group A actually answered this question?"
COHORT_METRICS = (
    "mean",
    "max",
    "min",
    "std",
    "first",
    "last",
    "mode",
    "count",
)


class RedcapProcessing:
    """Pure-function analytics for REDCap record fields."""

    # ──────────────────────────────────────────────────────────────
    # Type coercion helpers
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def is_numeric_value(value) -> bool:
        """Return True if ``value`` coerces to a finite float.

        Treats ``None``, blank strings, and non-numeric strings as
        non-numeric. ``True``/``False`` coerce to 1.0/0.0 but we
        exclude them because REDCap encodes booleans as the strings
        ``"1"`` / ``"0"``; a bare Python ``True`` arriving here is
        unusual enough to be worth treating as categorical.
        """
        if value is None or isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            try:
                f = float(value)
            except (TypeError, ValueError):
                return False
            return f == f and f not in (float("inf"), float("-inf"))
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return False
            try:
                f = float(stripped)
            except ValueError:
                return False
            return f == f and f not in (float("inf"), float("-inf"))
        return False

    @staticmethod
    def coerce_numeric(values: list) -> list[float]:
        """Coerce a list of mixed values into a list of floats.

        Drops any value that is not numeric per ``is_numeric_value``.
        REDCap exports often carry blanks for unanswered questions;
        this collapses them rather than propagating NaN.
        """
        out: list[float] = []
        for v in values:
            if not RedcapProcessing.is_numeric_value(v):
                continue
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                continue
        return out

    # ──────────────────────────────────────────────────────────────
    # Per-field summary (auto-detects numeric vs categorical)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def summarize_field(values: list) -> dict:
        """Auto-detecting per-field summary.

        If every non-blank value coerces to a finite float, returns a
        numeric summary: ``{kind, count, missing, mean, std, min, max}``.
        Otherwise returns a categorical summary:
        ``{kind, count, missing, cardinality, top_values}`` where
        ``top_values`` is the 5 most common ``{value, count}`` pairs.
        """
        # Partition into present (non-blank/non-None) and missing.
        present: list = []
        missing = 0
        for v in values:
            if v is None:
                missing += 1
                continue
            if isinstance(v, str) and not v.strip():
                missing += 1
                continue
            present.append(v)

        if not present:
            return {
                "kind": "empty",
                "count": 0,
                "missing": missing,
            }

        all_numeric = all(
            RedcapProcessing.is_numeric_value(v) for v in present
        )
        if all_numeric:
            floats = [float(v) for v in present]
            result = {
                "kind": "numeric",
                "count": len(floats),
                "missing": missing,
                "mean": round(fmean(floats), 6),
                "min": min(floats),
                "max": max(floats),
            }
            result["std"] = round(stdev(floats), 6) if len(floats) > 1 else 0.0
            return result

        counter = Counter(str(v) for v in present)
        top = counter.most_common(5)
        return {
            "kind": "categorical",
            "count": len(present),
            "missing": missing,
            "cardinality": len(counter),
            "top_values": [{"value": val, "count": cnt} for val, cnt in top],
        }

    # ──────────────────────────────────────────────────────────────
    # Cohort aggregation
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def aggregate_metric(values: list, metric: str):
        """Reduce a list of field values to a single scalar by ``metric``.

        Returns ``None`` on empty input or when the metric is numeric
        but the values are categorical (or vice versa). Raises
        ``ValueError`` for an unknown metric so the dispatch layer
        surfaces the typo.

        For ``mean / max / min / std`` the input is coerced via
        ``coerce_numeric``; if no values survive coercion, returns
        ``None``.

        For ``mode``, returns the most-common string-coerced value.
        For ``count``, returns the integer count of non-blank values.
        For ``first / last``, returns the value as-is (no coercion).
        """
        if metric not in COHORT_METRICS:
            raise ValueError(
                f"Unknown metric: {metric}. Supported: {list(COHORT_METRICS)}"
            )
        if not values:
            return None

        if metric in ("mean", "max", "min", "std"):
            floats = RedcapProcessing.coerce_numeric(values)
            if not floats:
                return None
            if metric == "mean":
                return round(fmean(floats), 6)
            if metric == "max":
                return max(floats)
            if metric == "min":
                return min(floats)
            return round(stdev(floats), 6) if len(floats) > 1 else 0.0

        # Categorical-eligible metrics (these accept any value type).
        present = [
            v for v in values
            if v is not None and not (isinstance(v, str) and not v.strip())
        ]
        if not present:
            return None
        if metric == "first":
            return present[0]
        if metric == "last":
            return present[-1]
        if metric == "mode":
            counter = Counter(str(v) for v in present)
            top_value, _top_count = counter.most_common(1)[0]
            return top_value
        if metric == "count":
            return len(present)
        return None  # pragma: no cover  — guarded by COHORT_METRICS check above

    # ──────────────────────────────────────────────────────────────
    # Cohort stats (cross-group summarization of per-group scalars)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def cohort_stats(per_group_scalars: list) -> dict:
        """Aggregate a list of per-record scalars into group stats.

        If every value is numeric: ``{n, mean, std, min, max}``.
        Otherwise treats the values as categorical and returns
        ``{n, kind: "categorical", mode, cardinality}``.

        ``None`` values are filtered out before classification.
        """
        finite = [v for v in per_group_scalars if v is not None]
        if not finite:
            return {
                "n": 0, "mean": None, "std": None, "min": None, "max": None,
            }
        all_numeric = all(
            RedcapProcessing.is_numeric_value(v) for v in finite
        )
        if all_numeric:
            floats = [float(v) for v in finite]
            out: dict = {
                "n": len(floats),
                "mean": round(fmean(floats), 6),
                "min": min(floats),
                "max": max(floats),
            }
            out["std"] = round(stdev(floats), 6) if len(floats) > 1 else 0.0
            return out
        counter = Counter(str(v) for v in finite)
        top_value, _top_count = counter.most_common(1)[0]
        return {
            "n": len(finite),
            "kind": "categorical",
            "mode": top_value,
            "cardinality": len(counter),
        }

    # ──────────────────────────────────────────────────────────────
    # Instrument-completion counter (REDCap convention)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def count_instruments_completed(
        record: dict,
        instrument_completion_fields: list[str],
    ) -> int:
        """Count how many of the named ``*_complete`` fields equal "2".

        REDCap encodes per-instrument completion as a small integer in
        the field ``{instrument}_complete``: ``"0"`` = Incomplete,
        ``"1"`` = Unverified, ``"2"`` = Complete. We count only the
        Complete state because that's the only one a downstream
        researcher can rely on having reviewed values for.
        """
        count = 0
        for name in instrument_completion_fields:
            value = record.get(name)
            if value is None:
                continue
            if str(value).strip() == "2":
                count += 1
        return count

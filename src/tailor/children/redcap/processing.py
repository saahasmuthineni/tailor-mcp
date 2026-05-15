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

# Per ADR 0003 § Amendment 2026-05-15 — k-anonymity threshold default
# for small-cell suppression on aggregate count surfaces. HHS
# Statistical Disclosure Limitation baseline for CMS data. Studies
# with elevated re-identification risk (pediatric, mental health,
# rare-disease) opt up via redcap_file.small_cell_suppression_threshold
# in user_config.json.
DEFAULT_SMALL_CELL_THRESHOLD = 5

# Sentinel value placed in the ``count`` field of suppressed entries.
# Stringified so it's visibly distinct from real integer counts — an
# LLM reading the envelope cannot confuse it with a numeric count.
SUPPRESSED_VALUE_PLACEHOLDER = "<small_cell_suppressed>"
SUPPRESSED_COUNT_PLACEHOLDER = "<below_threshold>"


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
    # Small-cell suppression (ADR 0003 § Amendment 2026-05-15)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def apply_small_cell_suppression_to_top_values(
        top_values: list[dict],
        threshold: int,
    ) -> list[dict]:
        """Collapse entries with ``count < threshold`` into a single
        aggregate suppressed entry. Per ADR 0003 § Amendment 2026-05-15.

        Input shape: ``[{"value": V, "count": N}, ...]`` as produced by
        ``summarize_field`` for categorical fields. Output preserves
        every entry where ``count >= threshold`` and appends a single
        aggregate at the end of shape
        ``{"value": "<small_cell_suppressed>", "count": "<below_threshold>",
        "suppressed_count": K}`` where K is the number of distinct
        suppressed values. ``threshold`` < 2 is treated as no-op
        (returns input unchanged) — the child enforces ``>= 2`` at
        config-load time but this method defends the invariant.
        """
        if threshold < 2:
            return list(top_values)
        kept: list[dict] = []
        suppressed_count = 0
        for entry in top_values:
            try:
                count_int = int(entry.get("count"))
            except (TypeError, ValueError):
                # Defensive: a count that isn't coercible to int can't
                # be compared to the threshold; keep the entry rather
                # than silently dropping data.
                kept.append(entry)
                continue
            if count_int < threshold:
                suppressed_count += 1
            else:
                kept.append(entry)
        if suppressed_count > 0:
            kept.append({
                "value": SUPPRESSED_VALUE_PLACEHOLDER,
                "count": SUPPRESSED_COUNT_PLACEHOLDER,
                "suppressed_count": suppressed_count,
            })
        return kept

    @staticmethod
    def apply_small_cell_suppression_to_completion_counts(
        completion_counts: dict[str, int],
        threshold: int,
    ) -> dict[str, int | str]:
        """Replace below-threshold counts with the
        ``"<below_threshold>"`` sentinel while preserving the
        instrument-name keys. Per ADR 0003 § Amendment 2026-05-15.

        Input shape: ``{instrument_name: count}`` as produced by
        ``redcap_summary_report``. Output shape: same keys, but values
        below ``threshold`` are replaced with the sentinel string. The
        instrument name itself is structural metadata (not a participant
        identifier per HIPAA Safe Harbor §164.514) so it stays
        queryable; only the count is suppressed.

        This is the third small-cell surface — after ``top_values`` and
        cohort ``groups`` — and closes the
        phi-irb-risk-reviewer 2026-05-15 Lens 1 WATCH finding: a study
        with N=2 enrolled at a pilot site discloses the count directly
        through completion_counts even when the other two surfaces are
        correctly suppressed. ``threshold`` < 2 is a no-op (returns
        input unchanged).
        """
        if threshold < 2:
            return dict(completion_counts)
        out: dict[str, int | str] = {}
        for instrument, count in completion_counts.items():
            try:
                count_int = int(count)
            except (TypeError, ValueError):
                out[instrument] = count
                continue
            if count_int < threshold:
                out[instrument] = SUPPRESSED_COUNT_PLACEHOLDER
            else:
                out[instrument] = count_int
        return out

    @staticmethod
    def apply_small_cell_suppression_to_groups(
        groups: dict[str, dict],
        threshold: int,
    ) -> dict[str, dict]:
        """Collapse cohort groups with ``n < threshold`` into a single
        aggregate suppressed entry. Per ADR 0003 § Amendment 2026-05-15.

        Input shape: ``{group_key: {"n": N, ...}}`` as produced by
        ``redcap_cohort_summary``'s aggregation loop. Output preserves
        every group where ``n >= threshold`` and replaces every other
        group with one aggregate entry keyed by
        ``"<small_cell_suppressed>"`` of shape
        ``{"n": "<below_threshold>", "suppressed_group_count": K}``.
        ``threshold`` < 2 returns the input unchanged.
        """
        if threshold < 2:
            return dict(groups)
        kept: dict[str, dict] = {}
        suppressed_group_count = 0
        for group_key, group_stats in groups.items():
            try:
                n_int = int(group_stats.get("n", 0))
            except (TypeError, ValueError):
                # Defensive: an n field that isn't coercible to int can't
                # be compared; keep the group.
                kept[group_key] = group_stats
                continue
            if n_int < threshold:
                suppressed_group_count += 1
            else:
                kept[group_key] = group_stats
        if suppressed_group_count > 0:
            kept[SUPPRESSED_VALUE_PLACEHOLDER] = {
                "n": SUPPRESSED_COUNT_PLACEHOLDER,
                "suppressed_group_count": suppressed_group_count,
            }
        return kept

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

"""
Stateless analytics for the MATLAB file child.

Every method is a ``@staticmethod`` — no instance state, no I/O,
no PRNG, no clock reads. Per ADR 0008.

The numpy arrays returned by ``scipy.io.loadmat`` are unwrapped to
plain Python lists/scalars at the child boundary; this module never
imports numpy or scipy and therefore stays testable on a base install
without the ``[matlab]`` extra.
"""

from __future__ import annotations

from statistics import fmean, stdev

# Per-file metric vocabulary for matlab_cohort_summary. Mirrors csv_dir's
# COHORT_METRICS but trimmed: MATLAB variables rarely carry timestamps
# inline (they're often separate variables), so timestamp-dependent
# metrics are deferred behind a future expansion.
COHORT_METRICS = (
    "mean",
    "max",
    "min",
    "std",
    "peak",  # alias of max
    "first",
    "last",
)


class MATLABProcessing:
    """Pure-function analytics for MATLAB numeric arrays."""

    @staticmethod
    def summarize_array(values: list[float]) -> dict:
        """Per-variable summary: count, mean, std, min, max.

        Empty input returns nulls; single-element input returns std=0.
        """
        if not values:
            return {
                "count": 0,
                "mean": None,
                "std": None,
                "min": None,
                "max": None,
            }
        result: dict = {
            "count": len(values),
            "mean": round(fmean(values), 6),
            "min": min(values),
            "max": max(values),
        }
        result["std"] = round(stdev(values), 6) if len(values) > 1 else 0.0
        return result

    @staticmethod
    def aggregate_metric(values: list[float], metric: str) -> float | None:
        """Reduce a 1-D variable to a single scalar by ``metric``.

        Returns ``None`` on empty input. Raises ``ValueError`` for an
        unknown metric so the dispatch layer surfaces the typo.
        """
        if metric not in COHORT_METRICS:
            raise ValueError(
                f"Unknown metric: {metric}. Supported: {list(COHORT_METRICS)}"
            )
        if not values:
            return None
        if metric == "mean":
            return round(fmean(values), 6)
        if metric in ("max", "peak"):
            return max(values)
        if metric == "min":
            return min(values)
        if metric == "std":
            return round(stdev(values), 6) if len(values) > 1 else 0.0
        if metric == "first":
            return values[0]
        if metric == "last":
            return values[-1]
        return None  # pragma: no cover  — guarded by COHORT_METRICS check above

    @staticmethod
    def cohort_stats(per_file_scalars: list[float]) -> dict:
        """Aggregate a list of per-file scalars into n/mean/std/min/max."""
        finite = [v for v in per_file_scalars if v is not None]
        if not finite:
            return {"n": 0, "mean": None, "std": None, "min": None, "max": None}
        out: dict = {
            "n": len(finite),
            "mean": round(fmean(finite), 6),
            "min": min(finite),
            "max": max(finite),
        }
        out["std"] = round(stdev(finite), 6) if len(finite) > 1 else 0.0
        return out

    @staticmethod
    def downsample(series: list[float], interval: int) -> list[float]:
        """Return every Nth element of ``series``."""
        if interval < 1:
            raise ValueError("interval must be >= 1")
        return series[::interval]

    @staticmethod
    def reduce_precision(values: list[float], places: int) -> list[float]:
        """Round each element of ``values`` to ``places`` decimal places.

        Tier-3 raw-array output uses this to drop noise digits that would
        burn tokens without contributing analytical signal.
        """
        if places < 0:
            raise ValueError("places must be >= 0")
        return [round(v, places) for v in values]

    @staticmethod
    def describe_shape(shape: tuple[int, ...]) -> str:
        """Render a numpy shape tuple as a compact human-readable string."""
        if not shape:
            return "scalar"
        return "x".join(str(d) for d in shape)

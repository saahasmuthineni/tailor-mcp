"""
Pure-function tests for MATLABProcessing.

No scipy dependency — these run on a base install. Tests ADR 0008's
@staticmethod / no-PRNG / no-clock invariant by exercising every method
without instantiating MATLABProcessing.
"""

from __future__ import annotations

import math

import pytest

from tailor.children.matlab_file import MATLABProcessing
from tailor.children.matlab_file.processing import COHORT_METRICS


class TestSummarizeArray:
    def test_empty_returns_nulls(self):
        out = MATLABProcessing.summarize_array([])
        assert out == {
            "count": 0, "mean": None, "std": None, "min": None, "max": None,
        }

    def test_single_element_has_zero_std(self):
        out = MATLABProcessing.summarize_array([42.0])
        assert out["count"] == 1
        assert out["mean"] == 42.0
        assert out["min"] == 42.0
        assert out["max"] == 42.0
        assert out["std"] == 0.0

    def test_multi_element_summary(self):
        out = MATLABProcessing.summarize_array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert out["count"] == 5
        assert out["mean"] == 3.0
        assert out["min"] == 1.0
        assert out["max"] == 5.0
        assert math.isclose(out["std"], 1.581139, abs_tol=1e-5)


class TestAggregateMetric:
    def test_unknown_metric_raises(self):
        with pytest.raises(ValueError, match="Unknown metric"):
            MATLABProcessing.aggregate_metric([1.0, 2.0], "median")

    def test_empty_values_returns_none(self):
        assert MATLABProcessing.aggregate_metric([], "mean") is None

    def test_mean(self):
        assert MATLABProcessing.aggregate_metric([2.0, 4.0, 6.0], "mean") == 4.0

    def test_max(self):
        assert MATLABProcessing.aggregate_metric([2.0, 4.0, 6.0], "max") == 6.0

    def test_peak_is_alias_for_max(self):
        assert (
            MATLABProcessing.aggregate_metric([2.0, 4.0, 6.0], "peak")
            == MATLABProcessing.aggregate_metric([2.0, 4.0, 6.0], "max")
        )

    def test_min(self):
        assert MATLABProcessing.aggregate_metric([2.0, 4.0, 6.0], "min") == 2.0

    def test_std_zero_on_single_value(self):
        assert MATLABProcessing.aggregate_metric([5.0], "std") == 0.0

    def test_first_and_last(self):
        assert MATLABProcessing.aggregate_metric([10.0, 20.0, 30.0], "first") == 10.0
        assert MATLABProcessing.aggregate_metric([10.0, 20.0, 30.0], "last") == 30.0

    def test_all_documented_metrics_dispatch(self):
        # Defensive: every metric in COHORT_METRICS must dispatch to a real
        # branch. Catches the case where someone adds a metric to the tuple
        # but forgets the dispatch arm.
        for metric in COHORT_METRICS:
            result = MATLABProcessing.aggregate_metric([1.0, 2.0, 3.0], metric)
            assert result is not None, (
                f"Metric {metric} returned None on non-empty input"
            )


class TestCohortStats:
    def test_empty_returns_nulls(self):
        out = MATLABProcessing.cohort_stats([])
        assert out["n"] == 0
        assert out["mean"] is None

    def test_none_values_filtered_out(self):
        out = MATLABProcessing.cohort_stats([1.0, None, 3.0])  # type: ignore[list-item]
        assert out["n"] == 2
        assert out["mean"] == 2.0

    def test_multi_value_stats(self):
        out = MATLABProcessing.cohort_stats([1.0, 2.0, 3.0, 4.0, 5.0])
        assert out["n"] == 5
        assert out["mean"] == 3.0
        assert out["min"] == 1.0
        assert out["max"] == 5.0


class TestDownsample:
    def test_interval_1_returns_full_series(self):
        assert MATLABProcessing.downsample([1.0, 2.0, 3.0], 1) == [1.0, 2.0, 3.0]

    def test_interval_2_returns_every_other(self):
        assert MATLABProcessing.downsample([1.0, 2.0, 3.0, 4.0, 5.0], 2) == [1.0, 3.0, 5.0]

    def test_interval_zero_raises(self):
        with pytest.raises(ValueError, match="interval"):
            MATLABProcessing.downsample([1.0, 2.0], 0)


class TestReducePrecision:
    def test_round_to_2_decimals(self):
        assert MATLABProcessing.reduce_precision([1.2345, 2.6789], 2) == [1.23, 2.68]

    def test_negative_places_raises(self):
        with pytest.raises(ValueError, match="places"):
            MATLABProcessing.reduce_precision([1.5], -1)

    def test_zero_places_floors_to_int_floats(self):
        # round(1.5, 0) == 2.0 (banker's rounding); this just verifies
        # the call doesn't choke on places=0.
        result = MATLABProcessing.reduce_precision([1.5, 2.7], 0)
        assert all(isinstance(v, float) for v in result)


class TestDescribeShape:
    def test_scalar(self):
        assert MATLABProcessing.describe_shape(()) == "scalar"

    def test_1d(self):
        assert MATLABProcessing.describe_shape((100,)) == "100"

    def test_2d(self):
        assert MATLABProcessing.describe_shape((8, 1000)) == "8x1000"

    def test_3d(self):
        assert MATLABProcessing.describe_shape((4, 8, 1000)) == "4x8x1000"


class TestDeterminismInvariant:
    """ADR 0008 — every method is a @staticmethod pure function."""

    def test_summarize_array_is_pure(self):
        a = [1.0, 2.0, 3.0]
        first = MATLABProcessing.summarize_array(a)
        second = MATLABProcessing.summarize_array(a)
        assert first == second

    def test_aggregate_metric_is_pure(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        first = MATLABProcessing.aggregate_metric(a, "mean")
        second = MATLABProcessing.aggregate_metric(a, "mean")
        assert first == second

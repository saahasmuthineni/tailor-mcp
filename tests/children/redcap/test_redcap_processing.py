"""
Pure-function tests for RedcapProcessing.

No I/O — these run on a base install with no fixtures. Tests
ADR 0008's @staticmethod / no-PRNG / no-clock invariant by exercising
every method without instantiating RedcapProcessing.
"""

from __future__ import annotations

import math

import pytest

from tailor.children.redcap import RedcapProcessing
from tailor.children.redcap.processing import COHORT_METRICS


class TestIsNumericValue:
    def test_int_is_numeric(self):
        assert RedcapProcessing.is_numeric_value(42)

    def test_float_is_numeric(self):
        assert RedcapProcessing.is_numeric_value(3.14)

    def test_numeric_string_is_numeric(self):
        assert RedcapProcessing.is_numeric_value("2")
        assert RedcapProcessing.is_numeric_value("3.5")
        assert RedcapProcessing.is_numeric_value(" 12 ")

    def test_blank_string_is_not_numeric(self):
        assert not RedcapProcessing.is_numeric_value("")
        assert not RedcapProcessing.is_numeric_value("   ")

    def test_word_string_is_not_numeric(self):
        assert not RedcapProcessing.is_numeric_value("F")
        assert not RedcapProcessing.is_numeric_value("intervention")

    def test_none_is_not_numeric(self):
        assert not RedcapProcessing.is_numeric_value(None)

    def test_bool_is_treated_as_non_numeric(self):
        # REDCap encodes booleans as "1"/"0"; a raw Python bool here is
        # noise and we exclude it to keep summarize_field's auto-detect
        # honest.
        assert not RedcapProcessing.is_numeric_value(True)
        assert not RedcapProcessing.is_numeric_value(False)


class TestCoerceNumeric:
    def test_pure_numeric(self):
        assert RedcapProcessing.coerce_numeric([1, "2", 3.0]) == [1.0, 2.0, 3.0]

    def test_drops_blanks(self):
        assert RedcapProcessing.coerce_numeric([1, "", None, 3]) == [1.0, 3.0]

    def test_drops_words(self):
        assert RedcapProcessing.coerce_numeric([1, "intervention", 3]) == [1.0, 3.0]

    def test_empty_input(self):
        assert RedcapProcessing.coerce_numeric([]) == []


class TestSummarizeField:
    def test_empty_returns_empty_kind(self):
        out = RedcapProcessing.summarize_field([])
        assert out["kind"] == "empty"
        assert out["count"] == 0

    def test_all_missing_returns_empty_kind(self):
        out = RedcapProcessing.summarize_field([None, "", "   "])
        assert out["kind"] == "empty"
        assert out["missing"] == 3

    def test_numeric_summary(self):
        out = RedcapProcessing.summarize_field([1, 2, 3, 4, 5])
        assert out["kind"] == "numeric"
        assert out["count"] == 5
        assert out["mean"] == 3.0
        assert out["min"] == 1
        assert out["max"] == 5
        assert math.isclose(out["std"], 1.581139, abs_tol=1e-5)

    def test_numeric_with_blanks(self):
        out = RedcapProcessing.summarize_field([1, "", 2, None, 3])
        assert out["kind"] == "numeric"
        assert out["count"] == 3
        assert out["missing"] == 2

    def test_categorical_summary(self):
        out = RedcapProcessing.summarize_field(
            ["F", "M", "F", "F", "M", "O"],
        )
        assert out["kind"] == "categorical"
        assert out["count"] == 6
        assert out["cardinality"] == 3
        # F appears 3 times (top)
        assert out["top_values"][0]["value"] == "F"
        assert out["top_values"][0]["count"] == 3

    def test_categorical_top_5_cap(self):
        # 10 unique values → cardinality 10 but only 5 in top_values.
        values = [f"val_{i}" for i in range(10)]
        out = RedcapProcessing.summarize_field(values)
        assert out["cardinality"] == 10
        assert len(out["top_values"]) == 5

    def test_single_numeric_has_zero_std(self):
        out = RedcapProcessing.summarize_field([42])
        assert out["std"] == 0.0


class TestAggregateMetric:
    def test_unknown_metric_raises(self):
        with pytest.raises(ValueError, match="Unknown metric"):
            RedcapProcessing.aggregate_metric([1, 2], "median")

    def test_empty_returns_none(self):
        assert RedcapProcessing.aggregate_metric([], "mean") is None

    def test_mean(self):
        assert RedcapProcessing.aggregate_metric([2, 4, 6], "mean") == 4.0

    def test_max(self):
        assert RedcapProcessing.aggregate_metric([2, 4, 6], "max") == 6.0

    def test_min(self):
        assert RedcapProcessing.aggregate_metric([2, 4, 6], "min") == 2.0

    def test_std_zero_on_single_value(self):
        assert RedcapProcessing.aggregate_metric([5], "std") == 0.0

    def test_first_and_last(self):
        assert RedcapProcessing.aggregate_metric([10, 20, 30], "first") == 10
        assert RedcapProcessing.aggregate_metric([10, 20, 30], "last") == 30

    def test_mode_on_categorical(self):
        assert (
            RedcapProcessing.aggregate_metric(["F", "M", "F", "F", "M"], "mode")
            == "F"
        )

    def test_count_non_blank(self):
        assert RedcapProcessing.aggregate_metric([1, "", 2, None, 3], "count") == 3

    def test_numeric_metric_on_categorical_returns_none(self):
        assert RedcapProcessing.aggregate_metric(
            ["F", "M", "F"], "mean",
        ) is None

    def test_all_documented_metrics_dispatch(self):
        for metric in COHORT_METRICS:
            result = RedcapProcessing.aggregate_metric([1, 2, 3], metric)
            assert result is not None, (
                f"Metric {metric} returned None on non-empty numeric input"
            )


class TestCohortStats:
    def test_empty_returns_nulls(self):
        out = RedcapProcessing.cohort_stats([])
        assert out["n"] == 0
        assert out["mean"] is None

    def test_none_values_filtered(self):
        out = RedcapProcessing.cohort_stats([1, None, 3])
        assert out["n"] == 2
        assert out["mean"] == 2.0

    def test_numeric(self):
        out = RedcapProcessing.cohort_stats([1, 2, 3, 4, 5])
        assert out["n"] == 5
        assert out["mean"] == 3.0
        assert out["min"] == 1
        assert out["max"] == 5

    def test_categorical(self):
        out = RedcapProcessing.cohort_stats(["F", "M", "F", "F"])
        assert out["n"] == 4
        assert out["kind"] == "categorical"
        assert out["mode"] == "F"
        assert out["cardinality"] == 2


class TestCountInstrumentsCompleted:
    def test_counts_value_2(self):
        record = {
            "demographics_complete": "2",
            "phq9_complete": "2",
            "weekly_checkin_complete": "0",
        }
        out = RedcapProcessing.count_instruments_completed(
            record,
            ["demographics_complete", "phq9_complete", "weekly_checkin_complete"],
        )
        assert out == 2

    def test_handles_missing_field(self):
        record = {"demographics_complete": "2"}
        out = RedcapProcessing.count_instruments_completed(
            record, ["demographics_complete", "phq9_complete"],
        )
        assert out == 1

    def test_none_values(self):
        record = {"demographics_complete": None}
        out = RedcapProcessing.count_instruments_completed(
            record, ["demographics_complete"],
        )
        assert out == 0

    def test_unverified_status_not_counted(self):
        # "1" is REDCap "Unverified" — does not count as Complete.
        record = {"demographics_complete": "1"}
        out = RedcapProcessing.count_instruments_completed(
            record, ["demographics_complete"],
        )
        assert out == 0


class TestDeterminismInvariant:
    """ADR 0008 — every method is a @staticmethod pure function."""

    def test_summarize_field_is_pure(self):
        values = [1, 2, 3, "F"]
        first = RedcapProcessing.summarize_field(values)
        second = RedcapProcessing.summarize_field(values)
        assert first == second

    def test_aggregate_metric_is_pure(self):
        values = [1, 2, 3, 4, 5]
        first = RedcapProcessing.aggregate_metric(values, "mean")
        second = RedcapProcessing.aggregate_metric(values, "mean")
        assert first == second

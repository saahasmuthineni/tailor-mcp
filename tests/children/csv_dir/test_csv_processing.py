"""
Pure-function tests for CSVProcessing — no fixtures, no I/O.

Mirrors ``tests/children/template/test_template_processing.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tailor.children.csv_dir.processing import (
    COHORT_METRICS,
    WINDOW_METRICS,
    CSVProcessing,
)

# ═══════════════════════════════════════════════════════════════
# summarize_column
# ═══════════════════════════════════════════════════════════════


class TestSummarizeColumn:
    def test_basic_stats(self):
        result = CSVProcessing.summarize_column([1.0, 2.0, 3.0, 4.0, 5.0])
        assert result["count"] == 5
        assert result["mean"] == 3.0
        assert result["min"] == 1.0
        assert result["max"] == 5.0
        assert result["std"] > 0

    def test_empty_list_returns_nulls(self):
        result = CSVProcessing.summarize_column([])
        assert result == {"count": 0, "mean": None, "min": None, "max": None, "std": None}

    def test_single_element(self):
        result = CSVProcessing.summarize_column([42.0])
        assert result["count"] == 1
        assert result["mean"] == 42.0
        assert result["min"] == 42.0
        assert result["max"] == 42.0
        assert result["std"] == 0.0


# ═══════════════════════════════════════════════════════════════
# downsample_rows
# ═══════════════════════════════════════════════════════════════


class TestDownsampleRows:
    def test_every_2nd_row(self):
        rows = [{"a": i} for i in range(10)]
        result = CSVProcessing.downsample_rows(rows, 2)
        assert len(result) == 5
        assert result[0]["a"] == 0
        assert result[1]["a"] == 2

    def test_interval_1_returns_original(self):
        rows = [{"a": i} for i in range(5)]
        result = CSVProcessing.downsample_rows(rows, 1)
        assert result == rows

    def test_interval_less_than_1_raises(self):
        with pytest.raises(ValueError, match="interval must be >= 1"):
            CSVProcessing.downsample_rows([], 0)

    def test_empty_list(self):
        result = CSVProcessing.downsample_rows([], 5)
        assert result == []


# ═══════════════════════════════════════════════════════════════
# detect_timestamp_column
# ═══════════════════════════════════════════════════════════════


class TestDetectTimestampColumn:
    def test_finds_timestamp(self):
        assert CSVProcessing.detect_timestamp_column(["id", "timestamp", "value"]) == "timestamp"

    def test_finds_time(self):
        assert CSVProcessing.detect_timestamp_column(["id", "time", "value"]) == "time"

    def test_finds_datetime(self):
        assert CSVProcessing.detect_timestamp_column(["datetime", "val"]) == "datetime"

    def test_case_insensitive(self):
        assert CSVProcessing.detect_timestamp_column(["ID", "Timestamp", "Value"]) == "Timestamp"

    def test_finds_ts(self):
        assert CSVProcessing.detect_timestamp_column(["id", "ts", "value"]) == "ts"

    def test_finds_event_time(self):
        assert CSVProcessing.detect_timestamp_column(["id", "event_time", "value"]) == "event_time"

    def test_finds_reading_time(self):
        assert CSVProcessing.detect_timestamp_column(["reading_time", "val"]) == "reading_time"

    def test_finds_substring_match(self):
        assert CSVProcessing.detect_timestamp_column(["id", "sample_timestamp", "val"]) == "sample_timestamp"

    def test_returns_none_when_no_match(self):
        assert CSVProcessing.detect_timestamp_column(["id", "value", "measurement"]) is None


# ═══════════════════════════════════════════════════════════════
# parse_timestamp
# ═══════════════════════════════════════════════════════════════


class TestParseTimestamp:
    def test_iso_8601(self):
        result = CSVProcessing.parse_timestamp("2026-01-15T10:30:00")
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.hour == 10

    def test_iso_8601_with_timezone(self):
        result = CSVProcessing.parse_timestamp("2026-01-15T10:30:00+00:00")
        assert isinstance(result, datetime)

    def test_custom_format(self):
        result = CSVProcessing.parse_timestamp(
            "01/15/2026 10:30", fmt="%m/%d/%Y %H:%M",
        )
        assert isinstance(result, datetime)
        assert result.month == 1
        assert result.day == 15

    def test_invalid_returns_none(self):
        assert CSVProcessing.parse_timestamp("not-a-date") is None

    def test_empty_string_returns_none(self):
        assert CSVProcessing.parse_timestamp("") is None


# ═══════════════════════════════════════════════════════════════
# estimate_row_tokens
# ═══════════════════════════════════════════════════════════════


class TestEstimateRowTokens:
    def test_known_values(self):
        assert CSVProcessing.estimate_row_tokens(100, 5) == 1000

    def test_zero_rows(self):
        assert CSVProcessing.estimate_row_tokens(0, 10) == 0

    def test_zero_cols(self):
        assert CSVProcessing.estimate_row_tokens(100, 0) == 0


# ═══════════════════════════════════════════════════════════════
# reduce_precision
# ═══════════════════════════════════════════════════════════════


class TestReducePrecision:
    def test_rounds_to_2_decimals(self):
        assert CSVProcessing.reduce_precision(3.14159) == 3.14

    def test_rounds_to_custom_decimals(self):
        assert CSVProcessing.reduce_precision(3.14159, decimals=3) == 3.142

    def test_integer_input(self):
        assert CSVProcessing.reduce_precision(42.0) == 42.0


# ═══════════════════════════════════════════════════════════════
# aggregate_metric (ADR 0015 — Tier-1 cohort surface)
# ═══════════════════════════════════════════════════════════════


class TestAggregateMetric:
    """Per-file scalar reduction for cohort aggregation."""

    def test_mean(self):
        assert CSVProcessing.aggregate_metric(
            [1.0, 2.0, 3.0, 4.0, 5.0], None, "mean",
        ) == 3.0

    def test_max_and_peak_alias(self):
        values = [10.0, 50.0, 30.0, 20.0]
        assert CSVProcessing.aggregate_metric(values, None, "max") == 50.0
        assert CSVProcessing.aggregate_metric(values, None, "peak") == 50.0

    def test_min(self):
        assert CSVProcessing.aggregate_metric([5.0, 2.0, 8.0], None, "min") == 2.0

    def test_std_multi_sample(self):
        result = CSVProcessing.aggregate_metric(
            [1.0, 2.0, 3.0, 4.0, 5.0], None, "std",
        )
        assert result is not None
        assert result > 0

    def test_std_single_sample_is_zero(self):
        assert CSVProcessing.aggregate_metric([42.0], None, "std") == 0.0

    def test_first_and_last(self):
        values = [10.0, 20.0, 30.0, 40.0]
        assert CSVProcessing.aggregate_metric(values, None, "first") == 10.0
        assert CSVProcessing.aggregate_metric(values, None, "last") == 40.0

    def test_empty_returns_none(self):
        assert CSVProcessing.aggregate_metric([], None, "mean") is None

    def test_unknown_metric_raises(self):
        with pytest.raises(ValueError, match="Unknown metric"):
            CSVProcessing.aggregate_metric([1.0], None, "frobnicate")

    def test_duration_requires_timestamps(self):
        # Without timestamps duration_s returns None.
        assert CSVProcessing.aggregate_metric(
            [1.0, 2.0, 3.0], None, "duration_s",
        ) is None

    def test_duration_with_timestamps(self):
        ts = [
            datetime(2026, 1, 1, 10, 0, 0),
            datetime(2026, 1, 1, 10, 0, 30),
            datetime(2026, 1, 1, 10, 1, 0),
        ]
        result = CSVProcessing.aggregate_metric(
            [1.0, 2.0, 3.0], ts, "duration_s",
        )
        assert result == 60.0

    def test_time_to_50pct_drop_basic(self):
        # Peak 100 at index 2; first sample <= 50 at index 4 (10 seconds later).
        ts = [
            datetime(2026, 1, 1, 10, 0, i * 5) for i in range(6)
        ]
        values = [80.0, 90.0, 100.0, 70.0, 40.0, 30.0]
        result = CSVProcessing.aggregate_metric(
            values, ts, "time_to_50pct_drop_s",
        )
        # Peak at i=2 (t=10s), 40 at i=4 (t=20s) → 10 seconds.
        assert result == 10.0

    def test_time_to_50pct_drop_never_reached_returns_none(self):
        ts = [datetime(2026, 1, 1, 10, 0, i) for i in range(4)]
        # Drops only 25% — never reaches 50%.
        assert CSVProcessing.aggregate_metric(
            [100.0, 90.0, 80.0, 75.0], ts, "time_to_50pct_drop_s",
        ) is None

    def test_time_to_50pct_drop_zero_peak_returns_none(self):
        ts = [datetime(2026, 1, 1, 10, 0, i) for i in range(3)]
        assert CSVProcessing.aggregate_metric(
            [0.0, 0.0, 0.0], ts, "time_to_50pct_drop_s",
        ) is None

    def test_time_to_50pct_drop_mismatched_lengths_returns_none(self):
        ts = [datetime(2026, 1, 1, 10, 0, 0)]
        # Three values, one timestamp → can't compute.
        assert CSVProcessing.aggregate_metric(
            [100.0, 50.0, 10.0], ts, "time_to_50pct_drop_s",
        ) is None

    def test_time_to_50pct_drop_with_peak_plateau_uses_last_peak_index(self):
        # Real isometric force traces have ramp → plateau → decline.
        # Plateau lasts 4 samples (i=2..5) at peak 100; decline starts
        # at i=6, crosses 50 at i=8. Timer must measure from the LAST
        # plateau index (i=5, t=25s), not the first (i=2, t=10s).
        ts = [datetime(2026, 1, 1, 10, 0, i * 5) for i in range(10)]
        values = [60.0, 80.0, 100.0, 100.0, 100.0, 100.0, 90.0, 70.0, 40.0, 30.0]
        result = CSVProcessing.aggregate_metric(
            values, ts, "time_to_50pct_drop_s",
        )
        # i=5 → t=25s; i=8 → t=40s; delta = 15s. The buggy
        # values.index(peak) version returned 30s (i=2 → i=8).
        assert result == 15.0

    def test_cohort_metrics_constant_is_complete(self):
        # All declared metrics must be implemented; this is a contract
        # test against the COHORT_METRICS public symbol.
        for metric in COHORT_METRICS:
            # mean/max/etc accept empty input and return None
            result = CSVProcessing.aggregate_metric([], None, metric)
            assert result is None


# ═══════════════════════════════════════════════════════════════
# cohort_stats (ADR 0015)
# ═══════════════════════════════════════════════════════════════


class TestCohortStats:
    def test_basic_cohort(self):
        result = CSVProcessing.cohort_stats([10.0, 20.0, 30.0, 40.0, 50.0])
        assert result["n"] == 5
        assert result["n_missing"] == 0
        assert result["mean"] == 30.0
        assert result["min"] == 10.0
        assert result["max"] == 50.0
        assert result["std"] > 0

    def test_drops_none_entries_and_counts_missing(self):
        result = CSVProcessing.cohort_stats([10.0, None, 30.0, None, 50.0])
        assert result["n"] == 3
        assert result["n_missing"] == 2
        assert result["mean"] == 30.0

    def test_all_none_returns_zero_n_and_nulls(self):
        result = CSVProcessing.cohort_stats([None, None, None])
        assert result["n"] == 0
        assert result["n_missing"] == 3
        assert result["mean"] is None
        assert result["std"] is None

    def test_empty_list_returns_zero_n(self):
        result = CSVProcessing.cohort_stats([])
        assert result["n"] == 0
        assert result["n_missing"] == 0
        assert result["mean"] is None

    def test_single_sample_std_is_zero(self):
        result = CSVProcessing.cohort_stats([42.0])
        assert result["n"] == 1
        assert result["std"] == 0.0


# ═══════════════════════════════════════════════════════════════
# force_decline_summary (ADR 0015)
# ═══════════════════════════════════════════════════════════════


class TestForceDeclineSummary:
    def test_empty_returns_error(self):
        result = CSVProcessing.force_decline_summary([])
        assert "error" in result

    def test_basic_decline_no_timestamps(self):
        # Simple monotonic decline from 100 to 25.
        values = [100.0, 80.0, 60.0, 40.0, 25.0]
        result = CSVProcessing.force_decline_summary(values)
        assert result["peak"] == 100.0
        assert result["peak_index"] == 0
        assert result["end_value"] == 25.0
        assert result["n_samples"] == 5
        assert result["decline_pct_total"] == 75.0
        # No timestamps supplied → decline-rate fields absent.
        assert "decline_rate_per_min" not in result
        assert "time_to_50pct_drop_s" not in result

    def test_decline_with_timestamps(self):
        base = datetime(2026, 1, 1, 10, 0, 0)
        ts = [base + timedelta(seconds=i * 60) for i in range(5)]
        values = [100.0, 80.0, 60.0, 40.0, 25.0]
        result = CSVProcessing.force_decline_summary(values, ts)
        # Peak at index 0, drops to 50 between index 2 (60) and index 3 (40).
        # First sample <= 50 is at index 3, 180 seconds after peak.
        assert result["time_to_50pct_drop_s"] == 180.0
        assert result["peak_time_s"] == 0.0
        assert result["duration_s"] == 240.0
        # Total decline = 75 over 4 minutes (peak at t=0 to end at t=240s).
        assert result["decline_rate_per_min"] == round(75 / 4, 3)

    def test_peak_in_middle(self):
        # Force ramps up before fatiguing.
        values = [60.0, 80.0, 100.0, 70.0, 40.0]
        result = CSVProcessing.force_decline_summary(values)
        assert result["peak"] == 100.0
        assert result["peak_index"] == 2
        assert result["end_value"] == 40.0
        assert result["decline_pct_total"] == 60.0

    def test_no_decline_returns_zero_pct(self):
        values = [50.0, 50.0, 50.0]
        result = CSVProcessing.force_decline_summary(values)
        assert result["decline_pct_total"] == 0.0
        assert result["peak"] == result["end_value"] == 50.0

    def test_zero_peak_decline_is_zero(self):
        values = [0.0, 0.0, 0.0]
        result = CSVProcessing.force_decline_summary(values)
        assert result["decline_pct_total"] == 0.0

    def test_never_drops_to_50pct(self):
        ts = [datetime(2026, 1, 1, 10, 0, i * 10) for i in range(4)]
        values = [100.0, 90.0, 80.0, 75.0]
        result = CSVProcessing.force_decline_summary(values, ts)
        assert result["time_to_50pct_drop_s"] is None

    def test_mismatched_timestamp_length_skips_temporal_fields(self):
        # When timestamps don't match values length, decline-rate fields
        # are silently omitted rather than misreporting.
        ts = [datetime(2026, 1, 1, 10, 0, 0)]
        values = [100.0, 80.0, 60.0]
        result = CSVProcessing.force_decline_summary(values, ts)
        assert "time_to_50pct_drop_s" not in result
        assert "decline_rate_per_min" not in result
        # Non-temporal fields still computed.
        assert result["peak"] == 100.0

    def test_peak_plateau_indexes_to_last_peak_sample(self):
        # Plateau of 4 samples at peak; decline starts at i=6.
        # peak_index must reference the LAST plateau sample so that
        # decline timing measures from when fatigue actually started,
        # not from when the subject first hit peak.
        ts = [datetime(2026, 1, 1, 10, 0, i * 5) for i in range(10)]
        values = [60.0, 80.0, 100.0, 100.0, 100.0, 100.0, 90.0, 70.0, 40.0, 30.0]
        result = CSVProcessing.force_decline_summary(values, ts)
        assert result["peak"] == 100.0
        assert result["peak_index"] == 5
        # peak_time = i=5 → t=25s; first sample <= 50 = i=8 → t=40s.
        assert result["peak_time_s"] == 25.0
        assert result["time_to_50pct_drop_s"] == 15.0
        # decline_rate from peak (100) to end (30) over (45-25)=20s = 1/3 min.
        assert result["decline_rate_per_min"] == round(70 / (20 / 60), 3)

    def test_peak_plateau_unique_peak_unaffected(self):
        # Single-occurrence peak: behaviour identical to pre-fix.
        # Regression guard so the _last_peak_index helper does not shift
        # peak_index for the existing unique-peak data shape.
        ts = [datetime(2026, 1, 1, 10, 0, i * 10) for i in range(5)]
        values = [60.0, 80.0, 100.0, 70.0, 40.0]
        result = CSVProcessing.force_decline_summary(values, ts)
        assert result["peak_index"] == 2
        assert result["peak_time_s"] == 20.0


# ═══════════════════════════════════════════════════════════════
# detect_contraction_peaks (csv_synchronized_windows — demo tool)
# ═══════════════════════════════════════════════════════════════


def _burst_signal(
    n_bursts: int,
    rest: int = 6,
    burst: int = 8,
    high: float = 10.0,
    low: float = 0.0,
) -> list[float]:
    """Build a clean rest/contraction/rest signal with `n_bursts`
    identical bursts. With sample_rate_hz=10 a burst of 8 samples is
    0.8 s — comfortably above the 0.5 s min-run filter."""
    sig: list[float] = []
    for _ in range(n_bursts):
        sig += [low] * rest
        sig += [high] * burst
    sig += [low] * rest
    return sig


class TestDetectContractionPeaks:
    """Deterministic threshold + contiguous-run contraction detection."""

    def test_clean_six_burst_yields_six_ordered_reps(self):
        sig = _burst_signal(6)
        reps = CSVProcessing.detect_contraction_peaks(sig, 10.0)
        assert len(reps) == 6
        peaks = [r["peak_idx"] for r in reps]
        assert peaks == sorted(peaks), "reps must be ordered by index"
        assert len(set(peaks)) == 6, "peaks must be distinct"
        # Every rep is a well-formed inclusive span.
        for r in reps:
            assert r["onset_idx"] <= r["peak_idx"] <= r["offset_idx"]

    def test_flat_signal_yields_no_reps(self):
        assert CSVProcessing.detect_contraction_peaks([5.0] * 40, 10.0) == []

    def test_empty_signal_yields_no_reps(self):
        assert CSVProcessing.detect_contraction_peaks([], 10.0) == []

    def test_non_positive_sample_rate_yields_no_reps(self):
        assert CSVProcessing.detect_contraction_peaks([0.0, 10.0, 0.0], 0.0) == []

    def test_single_contraction_yields_one_rep(self):
        sig = _burst_signal(1)
        reps = CSVProcessing.detect_contraction_peaks(sig, 10.0)
        assert len(reps) == 1

    def test_runs_shorter_than_min_run_are_dropped(self):
        # First burst is 3 samples (0.3 s at 10 Hz — below the 0.5 s
        # / 5-sample floor); second is 8. Only the second survives.
        sig = [0.0] * 8 + [10.0] * 3 + [0.0] * 8 + [10.0] * 8 + [0.0] * 8
        reps = CSVProcessing.detect_contraction_peaks(sig, 10.0)
        assert len(reps) == 1
        # The surviving rep is the long second burst (onset >= 19).
        assert reps[0]["onset_idx"] >= 19

    def test_explicit_threshold_is_honoured(self):
        # Low burst at 18, high burst at 30. Auto threshold (40% of
        # 0..30 = 12) catches both → 2 reps; an explicit threshold of
        # 25 excludes the low burst → 1 rep.
        sig = [0.0] * 6 + [18.0] * 8 + [0.0] * 6 + [30.0] * 8 + [0.0] * 6
        auto = CSVProcessing.detect_contraction_peaks(sig, 10.0)
        assert len(auto) == 2
        explicit = CSVProcessing.detect_contraction_peaks(
            sig, 10.0, threshold=25.0,
        )
        assert len(explicit) == 1

    def test_tie_at_peak_resolves_to_last_index(self):
        # A run with a flat plateau at its maximum: peak_idx must be
        # the LAST index at the max, per _last_peak_index.
        sig = [0.0] * 8 + [5.0, 9.0, 9.0, 9.0, 5.0] + [0.0] * 8
        reps = CSVProcessing.detect_contraction_peaks(sig, 10.0)
        assert len(reps) == 1
        # The 9.0 plateau sits at indices 9, 10, 11 → last is 11.
        assert reps[0]["peak_idx"] == 11

    def test_too_close_peaks_collapse_keeping_higher(self):
        # Two bursts 12 samples apart at 10 Hz (1.2 s); min_spacing_s=2.0
        # collapses them. The second burst is taller, so it survives.
        sig = (
            [0.0] * 5 + [10.0] * 8 + [0.0] * 4 + [20.0] * 8 + [0.0] * 5
        )
        reps = CSVProcessing.detect_contraction_peaks(
            sig, 10.0, min_spacing_s=2.0,
        )
        assert len(reps) == 1
        # Surviving peak is in the taller (second) burst.
        assert sig[reps[0]["peak_idx"]] == 20.0

    def test_min_spacing_zero_keeps_all_reps(self):
        sig = _burst_signal(6)
        reps = CSVProcessing.detect_contraction_peaks(
            sig, 10.0, min_spacing_s=0.0,
        )
        assert len(reps) == 6


# ═══════════════════════════════════════════════════════════════
# window_bounds / slice_window
# ═══════════════════════════════════════════════════════════════


class TestWindowBounds:
    def test_peak_anchored_window(self):
        # 2 s lead, 3 s window at 10 Hz around peak index 100.
        start, end = CSVProcessing.window_bounds(100, 10.0, 2.0, 3.0)
        assert start == 80
        assert end == 110

    def test_window_can_run_off_the_start(self):
        start, end = CSVProcessing.window_bounds(5, 10.0, 2.0, 1.0)
        assert start == -15
        assert end == -5  # slice_window clamps these


class TestSliceWindow:
    def test_basic_half_open_slice(self):
        assert CSVProcessing.slice_window(list(range(10)), 2, 5) == [2, 3, 4]

    def test_clamps_negative_start(self):
        assert CSVProcessing.slice_window(list(range(10)), -3, 4) == [0, 1, 2, 3]

    def test_clamps_end_past_array(self):
        assert CSVProcessing.slice_window(list(range(10)), 7, 30) == [7, 8, 9]

    def test_empty_window_when_start_equals_end(self):
        assert CSVProcessing.slice_window(list(range(10)), 5, 5) == []

    def test_empty_window_entirely_past_array(self):
        assert CSVProcessing.slice_window(list(range(10)), 20, 30) == []

    def test_empty_input_array(self):
        assert CSVProcessing.slice_window([], 0, 5) == []


# ═══════════════════════════════════════════════════════════════
# channel_metric
# ═══════════════════════════════════════════════════════════════


class TestChannelMetric:
    def test_rms(self):
        # sqrt((9 + 16) / 2) = sqrt(12.5) = 3.53553... → 3.5355.
        assert CSVProcessing.channel_metric([3.0, 4.0], "rms") == 3.5355

    def test_mean(self):
        assert CSVProcessing.channel_metric([1.0, 2.0, 3.0, 4.0, 5.0], "mean") == 3.0

    def test_peak_and_max_alias(self):
        assert CSVProcessing.channel_metric([10.0, 50.0, 30.0], "peak") == 50.0
        assert CSVProcessing.channel_metric([10.0, 50.0, 30.0], "max") == 50.0

    def test_min(self):
        assert CSVProcessing.channel_metric([10.0, 50.0, 30.0], "min") == 10.0

    def test_empty_returns_none(self):
        assert CSVProcessing.channel_metric([], "rms") is None
        assert CSVProcessing.channel_metric([], "mean") is None

    def test_unknown_metric_raises(self):
        with pytest.raises(ValueError, match="Unknown channel metric"):
            CSVProcessing.channel_metric([1.0], "frobnicate")

    def test_window_metrics_constant_is_complete(self):
        # Every declared metric must be implemented and accept input.
        for metric in WINDOW_METRICS:
            result = CSVProcessing.channel_metric([2.0, 4.0, 6.0], metric)
            assert result is not None
            # And every metric returns None on empty input.
            assert CSVProcessing.channel_metric([], metric) is None

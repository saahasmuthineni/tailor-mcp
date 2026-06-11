"""
Pure-function tests for EmgCsvProcessing — no fixtures, no I/O.

Mirrors ``tests/children/csv_dir/test_csv_processing.py`` and
``tests/children/strong_motion/test_strong_motion_processing.py``.
Hand-computed expected values exercise the EMG-domain time-domain math
directly (RMS, mean activation, integrated EMG, and the
peak-vs-end-window fatigue index) per ADR 0008's deterministic-by-
construction invariant.
"""

from __future__ import annotations

import math

import pytest

from tailor.children.emg_csv.processing import EmgCsvProcessing as EMG

# ═══════════════════════════════════════════════════════════════
# rms — root-mean-square amplitude
# ═══════════════════════════════════════════════════════════════


class TestRms:
    def test_two_point_hand_computed(self):
        # sqrt((9 + 16) / 2) = sqrt(12.5) = 3.535533... → 3.5355.
        assert EMG.rms([3.0, 4.0]) == 3.5355

    def test_constant_signal_equals_value(self):
        # RMS of a constant c is c.
        assert EMG.rms([5.0, 5.0, 5.0]) == 5.0

    def test_single_value(self):
        # sqrt(7^2 / 1) = 7.
        assert EMG.rms([7.0]) == 7.0

    def test_zero_signal_is_zero(self):
        assert EMG.rms([0.0, 0.0, 0.0]) == 0.0

    def test_empty_returns_none(self):
        assert EMG.rms([]) is None

    def test_matches_math_definition(self):
        values = [1.0, 2.0, 3.0, 4.0]
        expected = round(math.sqrt(sum(v * v for v in values) / len(values)), 4)
        assert EMG.rms(values) == expected

    def test_determinism_same_input_same_output(self):
        values = [1.0, 2.0, 3.0, 4.0]
        assert EMG.rms(values) == EMG.rms(values)


# ═══════════════════════════════════════════════════════════════
# mean_activation — arithmetic mean (MAV)
# ═══════════════════════════════════════════════════════════════


class TestMeanActivation:
    def test_basic_mean(self):
        assert EMG.mean_activation([1.0, 2.0, 3.0, 4.0, 5.0]) == 3.0

    def test_single_value(self):
        assert EMG.mean_activation([42.0]) == 42.0

    def test_all_equal(self):
        assert EMG.mean_activation([7.0, 7.0, 7.0]) == 7.0

    def test_empty_returns_none(self):
        assert EMG.mean_activation([]) is None


# ═══════════════════════════════════════════════════════════════
# integrated_emg — trapezoidal ∫|envelope|·dt
# ═══════════════════════════════════════════════════════════════


class TestIntegratedEmg:
    def test_two_point_trapezoid(self):
        # 10 Hz → dt = 0.1. Trapezoid of [10, 20] = (10+20)/2 * 0.1 = 1.5.
        assert EMG.integrated_emg([10.0, 20.0], 10.0) == 1.5

    def test_constant_signal_scales_with_duration(self):
        # Trapezoid of constant c over N points = c*(N-1)*dt.
        # c=2, N=4, dt=0.5 → 2 * 3 * 0.5 = 3.0.
        assert EMG.integrated_emg([2.0, 2.0, 2.0, 2.0], 2.0) == 3.0

    def test_single_point_returns_zero(self):
        # No interval to integrate over.
        assert EMG.integrated_emg([5.0], 10.0) == 0.0

    def test_empty_returns_none(self):
        assert EMG.integrated_emg([], 10.0) is None

    def test_non_positive_sample_rate_returns_none(self):
        assert EMG.integrated_emg([1.0, 2.0], 0.0) is None
        assert EMG.integrated_emg([1.0, 2.0], -1.0) is None

    def test_zero_signal_is_zero(self):
        assert EMG.integrated_emg([0.0, 0.0, 0.0], 10.0) == 0.0


# ═══════════════════════════════════════════════════════════════
# envelope_summary — combined fatigue diagnostic
# ═══════════════════════════════════════════════════════════════


class TestEnvelopeSummary:
    def test_declining_envelope_fatigue_index(self):
        # 1 Hz sample rate so window math is easy:
        #   peak_window_ms=250 → round(0.25*1)=0 → max(1,0)=1 sample.
        #   end_window_ms=1000 → round(1.0*1)=1 → max(1,1)=1 sample.
        # values = [100, 80, 60, 40, 20]; peak 100 at index 0 (last peak).
        #   peak window: half = 1//2 = 0 → values[0:1] = [100] → mean 100.
        #   end window: 1 sample → values[4:5] = [20] → mean 20.
        #   fatigue_index = (100 - 20)/100 * 100 = 80.0.
        values = [100.0, 80.0, 60.0, 40.0, 20.0]
        result = EMG.envelope_summary(values, 1.0)
        assert result["n_samples"] == 5
        assert result["duration_s"] == 4.0  # (5-1)/1
        assert result["peak_envelope_window_mean"] == 100.0
        assert result["end_window_mean"] == 20.0
        assert result["fatigue_index_pct"] == 80.0
        # mean_activation = (100+80+60+40+20)/5 = 60.0.
        assert result["mean_activation"] == 60.0

    def test_flat_envelope_zero_fatigue_index(self):
        # All-equal envelope → peak window == end window → 0% fatigue.
        values = [50.0, 50.0, 50.0, 50.0]
        result = EMG.envelope_summary(values, 1.0)
        assert result["peak_envelope_window_mean"] == 50.0
        assert result["end_window_mean"] == 50.0
        assert result["fatigue_index_pct"] == 0.0

    def test_rms_and_iemg_threaded_through(self):
        # Confirm the summary reuses the component pure functions.
        values = [10.0, 20.0, 30.0, 40.0]
        result = EMG.envelope_summary(values, 1.0)
        assert result["rms"] == EMG.rms(values)
        assert result["integrated_emg"] == EMG.integrated_emg(values, 1.0)
        assert result["mean_activation"] == EMG.mean_activation(values)

    def test_empty_returns_error(self):
        result = EMG.envelope_summary([], 1.0)
        assert "error" in result

    def test_non_positive_sample_rate_returns_error(self):
        result = EMG.envelope_summary([1.0, 2.0], 0.0)
        assert "error" in result

    def test_single_sample(self):
        # n=1: duration (1-1)/1 = 0.0. peak window = end window = [42].
        # iEMG of single point = 0.0 per integrated_emg contract.
        result = EMG.envelope_summary([42.0], 1.0)
        assert result["n_samples"] == 1
        assert result["duration_s"] == 0.0
        assert result["peak_envelope_window_mean"] == 42.0
        assert result["end_window_mean"] == 42.0
        assert result["fatigue_index_pct"] == 0.0
        assert result["integrated_emg"] == 0.0

    def test_determinism_same_input_same_output(self):
        values = [100.0, 80.0, 60.0, 40.0, 20.0]
        assert EMG.envelope_summary(values, 1.0) == EMG.envelope_summary(
            values, 1.0,
        )


# ═══════════════════════════════════════════════════════════════
# cohort_dispersion — stdev convenience wrapper
# ═══════════════════════════════════════════════════════════════


class TestCohortDispersion:
    def test_basic_stdev(self):
        # Sample stdev of [1,2,3,4,5]: mean 3, sum sq dev 10, /(5-1)=2.5,
        # sqrt = 1.5811 → 1.5811.
        result = EMG.cohort_dispersion([1.0, 2.0, 3.0, 4.0, 5.0])
        assert result["n"] == 5
        assert result["stdev"] == 1.5811

    def test_drops_none_entries(self):
        result = EMG.cohort_dispersion([10.0, None, 30.0, None, 50.0])
        assert result["n"] == 3
        # stdev of [10, 30, 50]: mean 30, sum sq dev 800, /2 = 400,
        # sqrt = 20.0.
        assert result["stdev"] == 20.0

    def test_single_value_stdev_none(self):
        result = EMG.cohort_dispersion([42.0])
        assert result == {"n": 1, "stdev": None}

    def test_empty_returns_zero_n_none_stdev(self):
        assert EMG.cohort_dispersion([]) == {"n": 0, "stdev": None}

    def test_all_none_returns_zero_n(self):
        assert EMG.cohort_dispersion([None, None, None]) == {
            "n": 0, "stdev": None,
        }

    def test_all_equal_zero_stdev(self):
        result = EMG.cohort_dispersion([7.0, 7.0, 7.0])
        assert result["n"] == 3
        assert result["stdev"] == 0.0

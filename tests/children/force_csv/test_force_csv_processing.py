"""
Pure-function tests for ForceCsvProcessing — no fixtures, no I/O.

Mirrors ``tests/children/csv_dir/test_csv_processing.py`` and
``tests/children/strong_motion/test_strong_motion_processing.py``.
Hand-computed expected values exercise the force-domain math directly
(MVC window mean and Bland-Altman device agreement) per ADR 0008's
deterministic-by-construction invariant.
"""

from __future__ import annotations

import pytest

from tailor.children.force_csv.processing import ForceCsvProcessing as FCP

# ═══════════════════════════════════════════════════════════════
# mvc_window_mean — Sánchez-2015 250 ms-window MVC definition
# ═══════════════════════════════════════════════════════════════


class TestMvcWindowMean:
    def test_centered_window_mean(self):
        # 10 Hz → 250 ms window = round(0.25 * 10) = 2 → max(1, 2) = 2
        # samples. half = 2 // 2 = 1. Peak 100 at index 4 (last peak).
        # window = [start=3, end=4+1+1=6) → values[3:6] = [70, 100, 90].
        # mean = 260 / 3 = 86.667.
        values = [10.0, 30.0, 50.0, 70.0, 100.0, 90.0, 40.0]
        assert FCP.mvc_window_mean(values, 10.0) == 86.667

    def test_peak_at_end_clamps_window(self):
        # Peak 100 at index 4 (last element). 10 Hz → window 2, half 1.
        # start = max(0, 4-1) = 3, end = min(5, 4+1+1) = 5.
        # values[3:5] = [80, 100] → mean = 90.0.
        values = [10.0, 30.0, 50.0, 80.0, 100.0]
        assert FCP.mvc_window_mean(values, 10.0) == 90.0

    def test_uses_last_peak_index_on_plateau(self):
        # Plateau of 100 at indices 2, 3, 4. _last_peak_index → 4.
        # 10 Hz → window 2, half 1. start = 3, end = min(6, 6) = 6.
        # values[3:6] = [100, 100, 80] → mean = 93.333.
        values = [60.0, 80.0, 100.0, 100.0, 100.0, 80.0]
        assert FCP.mvc_window_mean(values, 10.0) == 93.333

    def test_single_value(self):
        # Peak 42 at index 0. half = 0. window = values[0:1] = [42].
        assert FCP.mvc_window_mean([42.0], 10.0) == 42.0

    def test_empty_returns_none(self):
        assert FCP.mvc_window_mean([], 10.0) is None

    def test_non_positive_sample_rate_returns_none(self):
        assert FCP.mvc_window_mean([1.0, 2.0, 3.0], 0.0) is None
        assert FCP.mvc_window_mean([1.0, 2.0, 3.0], -5.0) is None

    def test_custom_window_ms(self):
        # 100 Hz, 100 ms window → round(0.1 * 100) = 10 samples,
        # half = 5. Peak 100 at index 5. start = 0, end = min(11, 11)=11.
        # values[0:11] = whole list (11 elements) → mean.
        values = [float(i) for i in range(11)]  # 0..10, peak 10 at idx 10
        # Peak is 10.0 at index 10. half = 5. start = 5, end = min(11, 16)=11.
        # values[5:11] = [5,6,7,8,9,10] → mean = 45/6 = 7.5.
        assert FCP.mvc_window_mean(values, 100.0, window_ms=100.0) == 7.5

    def test_determinism_same_input_same_output(self):
        values = [10.0, 30.0, 50.0, 70.0, 100.0, 90.0, 40.0]
        first = FCP.mvc_window_mean(values, 10.0)
        second = FCP.mvc_window_mean(values, 10.0)
        assert first == second


# ═══════════════════════════════════════════════════════════════
# bland_altman — paired-device agreement (Bland & Altman 1986)
# ═══════════════════════════════════════════════════════════════


class TestBlandAltman:
    def test_five_point_paired_series_hand_computed(self):
        # A = [10, 12, 14, 16, 18], B = [8, 11, 13, 17, 19].
        # diffs (A-B) = [2, 1, 1, -1, -1] → bias = 2/5 = 0.4.
        # sample stdev: mean 0.4; squared devs
        #   [1.6^2, .6^2, .6^2, 1.4^2, 1.4^2] = [2.56,.36,.36,1.96,1.96]
        #   sum = 7.2; /(5-1) = 1.8; sqrt = 1.34164 → round 1.342.
        # upper = 0.4 + 1.96*1.341641 = 3.0296 → round 3.03.
        # lower = 0.4 - 1.96*1.341641 = -2.2296 → round -2.23.
        # means (A+B)/2 = [9, 11.5, 13.5, 16.5, 18.5].
        a = [10.0, 12.0, 14.0, 16.0, 18.0]
        b = [8.0, 11.0, 13.0, 17.0, 19.0]
        result = FCP.bland_altman(a, b)
        assert result["n_pairs"] == 5
        assert result["mean_difference"] == 0.4
        assert result["sd_difference"] == 1.342
        assert result["upper_loa"] == 3.03
        assert result["lower_loa"] == -2.23
        assert result["mean_values"] == [9.0, 11.5, 13.5, 16.5, 18.5]
        assert result["differences"] == [2.0, 1.0, 1.0, -1.0, -1.0]

    def test_perfect_agreement_zero_bias_and_loa(self):
        # Identical devices → all diffs 0 → bias 0, sd 0, loa 0.
        a = [5.0, 10.0, 15.0]
        b = [5.0, 10.0, 15.0]
        result = FCP.bland_altman(a, b)
        assert result["mean_difference"] == 0.0
        assert result["sd_difference"] == 0.0
        assert result["upper_loa"] == 0.0
        assert result["lower_loa"] == 0.0
        assert result["differences"] == [0.0, 0.0, 0.0]
        assert result["mean_values"] == [5.0, 10.0, 15.0]

    def test_constant_offset_has_zero_sd(self):
        # B is uniformly 2 below A → diffs all 2.0 → bias 2.0, sd 0.0.
        a = [10.0, 20.0, 30.0]
        b = [8.0, 18.0, 28.0]
        result = FCP.bland_altman(a, b)
        assert result["mean_difference"] == 2.0
        assert result["sd_difference"] == 0.0
        assert result["upper_loa"] == 2.0
        assert result["lower_loa"] == 2.0

    def test_minimum_two_pairs(self):
        # diffs = [1, -1] → bias 0; sample stdev sqrt((1+1)/1)=sqrt(2)
        #   = 1.41421 → 1.414. upper = 1.96*1.414214 = 2.7719 → 2.772.
        a = [11.0, 9.0]
        b = [10.0, 10.0]
        result = FCP.bland_altman(a, b)
        assert result["n_pairs"] == 2
        assert result["mean_difference"] == 0.0
        assert result["sd_difference"] == 1.414
        assert result["upper_loa"] == 2.772
        assert result["lower_loa"] == -2.772

    def test_empty_a_returns_error(self):
        result = FCP.bland_altman([], [1.0, 2.0])
        assert "error" in result

    def test_empty_b_returns_error(self):
        result = FCP.bland_altman([1.0, 2.0], [])
        assert "error" in result

    def test_both_empty_returns_error(self):
        result = FCP.bland_altman([], [])
        assert "error" in result

    def test_mismatched_lengths_returns_error(self):
        result = FCP.bland_altman([1.0, 2.0, 3.0], [1.0, 2.0])
        assert "error" in result
        assert "equal-length" in result["error"]

    def test_single_pair_returns_error(self):
        # Bland-Altman needs ≥ 2 pairs to compute SD of differences.
        result = FCP.bland_altman([1.0], [2.0])
        assert "error" in result
        assert "at least 2 pairs" in result["error"]

    def test_determinism_same_input_same_output(self):
        a = [10.0, 12.0, 14.0, 16.0, 18.0]
        b = [8.0, 11.0, 13.0, 17.0, 19.0]
        assert FCP.bland_altman(a, b) == FCP.bland_altman(a, b)

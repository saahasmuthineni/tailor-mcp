"""
Tests for StrongMotionProcessing — pure-function seismic analytics.

These exercise the engineering math directly on hand-constructed
signals, with no parsing or I/O (the child/processing split per
ADR 0008). The Arias-intensity and significant-duration cases use
closed-form hand calculations so the tests catch formula drift, not
just "it returns a number."
"""

from __future__ import annotations

import math

import pytest

from tailor.children.strong_motion.processing import (
    G_MS2,
    SA_PERIODS,
)
from tailor.children.strong_motion.processing import (
    StrongMotionProcessing as SMP,
)


class TestPeakAcceleration:
    def test_peak_is_max_absolute(self):
        assert SMP.peak_acceleration_g([0.1, -1.927, 0.5, 1.2]) == pytest.approx(1.927)

    def test_empty_returns_none(self):
        assert SMP.peak_acceleration_g([]) is None


class TestAriasIntensity:
    def test_triangular_impulse_closed_form(self):
        # a = [0, 1, 0] g, dt = 1 s.
        #   a(t)^2 in (m/s^2)^2 = [0, (9.81)^2, 0]
        #   trapezoid over 3 points = (9.81)^2
        #   Ia = pi/(2g) * (9.81)^2  ->  ~15.41 m/s
        accel_g = [0.0, 1.0, 0.0]
        dt = 1.0
        expected = (math.pi / (2.0 * G_MS2)) * (G_MS2 ** 2)
        got = SMP.arias_intensity(accel_g, dt)
        assert got == pytest.approx(expected)
        # And the bare numeric value, to catch a silent change in G.
        assert got == pytest.approx(15.4096, abs=1e-3)

    def test_constant_signal_scales_with_duration(self):
        # Trapezoid of a constant c over N points = c*(N-1)*dt.
        accel_g = [1.0, 1.0, 1.0, 1.0]
        dt = 0.5
        c = (1.0 * G_MS2) ** 2
        expected_integral = c * (len(accel_g) - 1) * dt
        expected = (math.pi / (2.0 * G_MS2)) * expected_integral
        assert SMP.arias_intensity(accel_g, dt) == pytest.approx(expected)

    def test_zero_signal_is_zero(self):
        assert SMP.arias_intensity([0.0, 0.0, 0.0], 0.01) == 0.0

    def test_degenerate_inputs_return_zero(self):
        assert SMP.arias_intensity([1.0], 0.01) == 0.0
        assert SMP.arias_intensity([1.0, 2.0], 0.0) == 0.0


class TestStrongMotionDuration:
    def test_five_ninetyfive_window_closed_form(self):
        # Quiet, then a 4-sample burst, then quiet. dt = 1 s.
        # Husid 5% crossing -> t=1.4 s, 95% crossing -> t=5.6 s,
        # significant duration = 4.2 s (hand-computed).
        accel_g = [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0]
        dt = 1.0
        assert SMP.strong_motion_duration(accel_g, dt) == pytest.approx(4.2, abs=1e-6)

    def test_zero_signal_zero_duration(self):
        assert SMP.strong_motion_duration([0.0, 0.0, 0.0], 0.01) == 0.0


class TestResponseSpectrum:
    def _impulse_signal(self) -> tuple[list[float], float]:
        # A short transient: a few non-zero samples in an otherwise
        # quiet record at 100 Hz.
        accel = [0.0, 0.5, -0.8, 1.2, -0.6, 0.3] + [0.0] * 50
        return accel, 0.01

    def test_returns_one_value_per_period(self):
        accel, dt = self._impulse_signal()
        sa = SMP.response_spectrum_sa(accel, dt)
        assert set(sa.keys()) == {f"T={p}s" for p in SA_PERIODS}

    def test_all_values_finite_and_nonnegative(self):
        accel, dt = self._impulse_signal()
        sa = SMP.response_spectrum_sa(accel, dt)
        for period, value in sa.items():
            assert math.isfinite(value), f"{period} produced non-finite Sa"
            assert value >= 0.0

    def test_nonzero_input_excites_oscillator(self):
        accel, dt = self._impulse_signal()
        sa = SMP.response_spectrum_sa(accel, dt)
        assert any(v > 0.0 for v in sa.values())

    def test_zero_input_zero_spectrum(self):
        sa = SMP.response_spectrum_sa([0.0] * 20, 0.01)
        assert all(v == 0.0 for v in sa.values())


class TestCohortStats:
    def test_basic_aggregation(self):
        stats = SMP.cohort_stats([1.0, 2.0, 3.0])
        assert stats["n"] == 3
        assert stats["mean"] == pytest.approx(2.0)
        assert stats["min"] == 1.0
        assert stats["max"] == 3.0
        assert stats["std"] > 0

    def test_single_value_std_zero(self):
        assert SMP.cohort_stats([5.0])["std"] == 0.0

    def test_empty_returns_nulls(self):
        assert SMP.cohort_stats([]) == {
            "n": 0, "mean": None, "std": None, "min": None, "max": None,
        }


class TestTraceShaping:
    def test_downsample_every_nth(self):
        assert SMP.downsample([1, 2, 3, 4, 5, 6], 2) == [1, 3, 5]

    def test_downsample_invalid_interval_raises(self):
        with pytest.raises(ValueError):
            SMP.downsample([1, 2, 3], 0)

    def test_reduce_precision(self):
        out = SMP.reduce_precision([1.23456, 2.34567], 2)
        assert out == [1.23, 2.35]

    def test_reduce_precision_negative_places_raises(self):
        with pytest.raises(ValueError):
            SMP.reduce_precision([1.0], -1)

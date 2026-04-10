"""
Tests for running-specific analytics.

These are pure functions with known inputs — the most valuable
tests in the project because the math is what users depend on.
"""

import pytest
from strava_coach.children.running.processing import RunningProcessing, haversine


class TestHRZones:
    """HR zone distribution with configurable max HR."""

    def test_default_zones(self):
        # All at 150 bpm with max_hr=200 → 75% → Zone 3
        hr = [150] * 100
        result = RunningProcessing.compute_hr_zones(hr, max_hr=200)
        assert result["zone_pct"][3] == 100.0
        assert result["avg_hr"] == 150
        assert result["max_hr_setting"] == 200

    def test_custom_max_hr(self):
        # 150 bpm with max_hr=150 → 100% → Zone 5
        hr = [150] * 100
        result = RunningProcessing.compute_hr_zones(hr, max_hr=150)
        assert result["zone_pct"][5] == 100.0

    def test_zone_boundaries(self):
        # Test each zone boundary at max_hr=200
        # Zone 1: <=60% (<=120), Zone 2: <=70% (<=140), etc.
        hr = [100, 130, 155, 185, 200]
        result = RunningProcessing.compute_hr_zones(hr, max_hr=200)
        assert result["zone_seconds"][1] == 1  # 100 → 50% → Z1
        assert result["zone_seconds"][2] == 1  # 130 → 65% → Z2
        assert result["zone_seconds"][3] == 1  # 155 → 77.5% → Z3
        assert result["zone_seconds"][4] == 1  # 185 → 92.5% → Z4
        assert result["zone_seconds"][5] == 1  # 200 → 100% → Z5

    def test_empty_data(self):
        result = RunningProcessing.compute_hr_zones([], max_hr=195)
        assert result["avg_hr"] == 0
        assert result["max_hr_observed"] == 0


class TestHRDrift:
    """HR drift: first-half vs second-half comparison."""

    def test_no_drift(self):
        hr = [150] * 200
        result = RunningProcessing.compute_hr_drift(hr)
        assert result["drift_pct"] == 0.0
        assert result["interpretation"] == "aerobic"

    def test_significant_drift(self):
        # First half: 140, second half: 170 → ~21% drift
        hr = [140] * 100 + [170] * 100
        result = RunningProcessing.compute_hr_drift(hr)
        assert result["drift_pct"] > 10
        assert result["interpretation"] == "significant drift"

    def test_moderate_drift(self):
        hr = [150] * 100 + [160] * 100
        result = RunningProcessing.compute_hr_drift(hr)
        assert 5 <= result["drift_pct"] <= 10
        assert result["interpretation"] == "moderate drift"

    def test_too_short(self):
        hr = [150] * 30
        result = RunningProcessing.compute_hr_drift(hr)
        assert result["drift_pct"] == 0
        assert "too short" in result["note"].lower()


class TestMileSplits:
    """Mile split computation from distance/time arrays."""

    def test_two_miles(self):
        # Simulate 2 miles: 1609.34m per mile, 1 meter per second
        n = 3220  # ~2 miles
        distance = [float(i) for i in range(n)]
        time_arr = list(range(n))
        splits = RunningProcessing.compute_mile_splits(distance, time_arr)
        assert len(splits) == 2  # 2 full miles (partial < 100m)
        assert splits[0]["mile"] == 1
        assert splits[1]["mile"] == 2

    def test_partial_mile(self):
        # 1.5 miles worth of distance
        n = 2414  # ~1.5 miles
        distance = [float(i) for i in range(n)]
        time_arr = list(range(n))
        splits = RunningProcessing.compute_mile_splits(distance, time_arr)
        assert len(splits) == 2  # 1 full + 1 partial
        assert "partial" in str(splits[-1]["mile"])


class TestDecoupling:
    """Aerobic decoupling analysis."""

    def test_well_coupled(self):
        # Same HR and velocity throughout → 0% decoupling
        hr = [150] * 300
        vel = [3.0] * 300
        result = RunningProcessing.compute_decoupling(hr, vel)
        assert result["decoupling_pct"] == 0.0
        assert result["interpretation"] == "well coupled"

    def test_decoupled(self):
        # HR rises while velocity drops → significant decoupling
        hr = [140] * 150 + [170] * 150
        vel = [3.5] * 150 + [2.8] * 150
        result = RunningProcessing.compute_decoupling(hr, vel)
        assert abs(result["decoupling_pct"]) > 10
        assert result["interpretation"] == "decoupled"

    def test_too_short(self):
        result = RunningProcessing.compute_decoupling([150] * 50, [3.0] * 50)
        assert "too short" in result.get("note", "").lower()


class TestEfficiencyFactor:
    def test_basic_ef(self):
        hr = [150] * 100
        vel = [3.0] * 100  # ~8:56 min/mile
        result = RunningProcessing.compute_efficiency_factor(hr, vel)
        assert result["ef"] > 0
        assert result["avg_hr"] == 150
        assert result["avg_velocity_ms"] == 3.0

    def test_empty_data(self):
        result = RunningProcessing.compute_efficiency_factor([], [])
        assert result["ef"] == 0


class TestAnomalyDetection:
    """Sensor artifact detection."""

    def test_flatline(self):
        # 60+ seconds at exactly 160 bpm
        hr = [160] * 100
        anomalies = RunningProcessing.detect_anomalies(hr, [])
        flatlines = [a for a in anomalies if a["type"] == "hr_flatline"]
        assert len(flatlines) == 1
        assert flatlines[0]["value"] == 160
        assert flatlines[0]["duration_seconds"] == 100

    def test_no_flatline_if_short(self):
        hr = [160] * 50  # Less than 60s threshold
        anomalies = RunningProcessing.detect_anomalies(hr, [])
        flatlines = [a for a in anomalies if a["type"] == "hr_flatline"]
        assert len(flatlines) == 0

    def test_spike_detection(self):
        # Normal HR then sudden jump
        hr = [150] * 10 + [190] * 10
        anomalies = RunningProcessing.detect_anomalies(hr, [])
        spikes = [a for a in anomalies if a["type"] == "hr_spike"]
        assert len(spikes) > 0
        assert spikes[0]["delta"] == 40


class TestPhaseDetection:
    def test_too_short(self):
        phases = RunningProcessing.detect_run_phases([3.0] * 50, list(range(50)))
        assert phases[0]["phase"] == "too_short"

    def test_detects_phases(self):
        # Build a run with clear phases
        vel = [2.0] * 60 + [3.0] * 300 + [4.0] * 120 + [2.0] * 60
        time_arr = list(range(len(vel)))
        phases = RunningProcessing.detect_run_phases(vel, time_arr)
        assert len(phases) >= 2  # Should detect at least easy + steady


class TestDownsampling:
    def test_10s_interval(self):
        streams = {
            "time": list(range(100)),
            "heartrate": [150 + (i % 5) for i in range(100)],
        }
        result = RunningProcessing.downsample(streams, interval=10)
        # ~10 points (0, 10, 20, ..., 90, 99)
        assert len(result["time"]) == 11
        assert result["time"][0] == 0
        assert result["time"][-1] == 99  # Always includes last

    def test_preserves_all_keys(self):
        streams = {
            "time": list(range(50)),
            "heartrate": [150] * 50,
            "velocity_smooth": [3.0] * 50,
        }
        result = RunningProcessing.downsample(streams, interval=10)
        assert set(result.keys()) == {"time", "heartrate", "velocity_smooth"}


class TestPrecisionReduction:
    def test_gps_precision(self):
        streams = {"latlng": [[42.123456789, -71.987654321]]}
        result = RunningProcessing.reduce_precision(streams)
        assert result["latlng"][0][0] == 42.12346  # 5 decimals
        assert result["latlng"][0][1] == -71.98765

    def test_velocity_precision(self):
        streams = {"velocity_smooth": [3.14159]}
        result = RunningProcessing.reduce_precision(streams)
        assert result["velocity_smooth"][0] == 3.14

    def test_altitude_integer(self):
        streams = {"altitude": [125.7]}
        result = RunningProcessing.reduce_precision(streams)
        assert result["altitude"][0] == 126
        assert isinstance(result["altitude"][0], int)

    def test_grade_preserved(self):
        # Grade at 1 decimal — protects GAP calculations
        streams = {"grade_smooth": [-2.34]}
        result = RunningProcessing.reduce_precision(streams)
        assert result["grade_smooth"][0] == -2.3

    def test_heartrate_unchanged(self):
        streams = {"heartrate": [155]}
        result = RunningProcessing.reduce_precision(streams)
        assert result["heartrate"][0] == 155


class TestStreamTokenEstimation:
    def test_estimates_nonzero(self):
        streams = {
            "time": list(range(1000)),
            "heartrate": [150] * 1000,
            "velocity_smooth": [3.0] * 1000,
        }
        tokens = RunningProcessing.estimate_stream_tokens(streams)
        assert tokens > 0

    def test_selective_reduces_cost(self):
        streams = {
            "time": list(range(1000)),
            "heartrate": [150] * 1000,
            "velocity_smooth": [3.0] * 1000,
            "latlng": [[42.0, -71.0]] * 1000,
            "altitude": [100.0] * 1000,
        }
        full = RunningProcessing.estimate_stream_tokens(streams)
        selective = RunningProcessing.estimate_stream_tokens(
            streams, requested=["heartrate"]
        )
        assert selective < full


class TestStopDetection:
    def test_detects_stop(self):
        # 50s moving, 15s stopped, 50s moving
        vel = [3.0] * 50 + [0.1] * 15 + [3.0] * 50
        time_arr = list(range(len(vel)))
        stops = RunningProcessing.detect_stops([], vel, time_arr)
        assert len(stops) == 1
        assert stops[0]["duration_seconds"] == 15

    def test_ignores_brief_pause(self):
        # 5s pause is below 10s threshold
        vel = [3.0] * 50 + [0.1] * 5 + [3.0] * 50
        time_arr = list(range(len(vel)))
        stops = RunningProcessing.detect_stops([], vel, time_arr)
        assert len(stops) == 0


class TestHaversine:
    def test_known_distance(self):
        # NYC to LA ≈ 3,944 km
        nyc = [40.7128, -74.0060]
        la = (34.0522, -118.2437)
        dist = haversine(nyc, la)
        assert 3_900_000 < dist < 4_000_000  # meters

    def test_same_point(self):
        coord = [42.0, -71.0]
        assert haversine(coord, (42.0, -71.0)) < 1  # < 1 meter

"""
Tests for vault/renderer.py — pure functions, no I/O.
"""

import pytest
from strava_coach.vault.renderer import (
    render_run_note,
    render_trend_note,
    render_compare_note,
    _aerobic_grade,
    _pace_from_velocity,
    _iso_week,
)


# ── Helpers ──

def _minimal_run_result(activity_id=12345678):
    """Minimal result dict that _handle_run_report could return."""
    return {
        "activity_id": activity_id,
        "data_points": 3600,
        "decoupling": {
            "decoupling_pct": 3.2,
            "first_half": {"avg_hr": 148, "avg_velocity": 2.8},
            "second_half": {"avg_hr": 151, "avg_velocity": 2.75},
            "interpretation": "well coupled",
        },
        "efficiency_factor": {"ef": 1.23, "avg_hr": 149, "avg_velocity_ms": 2.77},
        "hr_drift": {
            "first_half_avg": 148,
            "second_half_avg": 153,
            "drift_pct": 3.4,
            "interpretation": "aerobic",
        },
        "hr_zones": {
            "zone_seconds": {1: 60, 2: 300, 3: 2400, 4: 720, 5: 120},
            "zone_pct": {1: 1.7, 2: 8.3, 3: 66.7, 4: 20.0, 5: 3.3},
            "avg_hr": 149,
            "max_hr_observed": 172,
            "min_hr": 120,
            "max_hr_setting": 195,
        },
        "phases": [
            {"phase": "warmup", "start_time": 0, "end_time": 600, "duration_seconds": 600},
            {"phase": "steady", "start_time": 600, "end_time": 3000, "duration_seconds": 2400},
            {"phase": "cooldown", "start_time": 3000, "end_time": 3600, "duration_seconds": 600},
        ],
        "mile_splits": [
            {"mile": 1, "elapsed_seconds": 540, "pace": "9:00", "avg_velocity_ms": 2.98},
            {"mile": 2, "elapsed_seconds": 550, "pace": "9:10", "avg_velocity_ms": 2.92},
        ],
        "gap_splits": [
            {"mile": 1, "elapsed_seconds": 530, "pace": "8:50"},
            {"mile": 2, "elapsed_seconds": 545, "pace": "9:05"},
        ],
        "anomalies": [
            {"type": "hr_spike", "severity": "moderate", "description": "HR spiked at mile 1.5"},
        ],
        "note": "Computed server-side.",
    }


def _minimal_activity_data(activity_id=12345678):
    return {
        "id": activity_id,
        "name": "Morning Run",
        "start_date": "2025-04-10T07:00:00Z",
        "distance": 14800,        # ~9.2 miles
        "moving_time": 4740,      # ~79 min
        "average_heartrate": 149,
        "max_heartrate": 172,
        "total_elevation_gain": 85,
    }


# ── Unit tests: pure helpers ──

class TestHelpers:
    def test_aerobic_grade_coupled(self):
        assert _aerobic_grade(2.0) == "coupled"
        assert _aerobic_grade(-2.0) == "coupled"
        assert _aerobic_grade(4.9) == "coupled"

    def test_aerobic_grade_borderline(self):
        assert _aerobic_grade(5.0) == "borderline"
        assert _aerobic_grade(7.9) == "borderline"

    def test_aerobic_grade_decoupled(self):
        assert _aerobic_grade(8.0) == "decoupled"
        assert _aerobic_grade(15.0) == "decoupled"

    def test_pace_from_velocity_typical(self):
        # 3 m/s ≈ 8:57 /mile
        pace = _pace_from_velocity(3.0)
        assert ":" in pace
        mins, secs = pace.split(":")
        assert int(mins) == 8

    def test_pace_from_velocity_zero(self):
        assert _pace_from_velocity(0) == "--:--"

    def test_iso_week(self):
        assert _iso_week("2025-04-10") == "2025-W15"
        assert _iso_week("2025-01-01") == "2025-W01"

    def test_iso_week_bad_input(self):
        result = _iso_week("")
        assert isinstance(result, str)


# ── render_run_note ──

class TestRenderRunNote:
    def test_returns_tuple(self):
        filename, content = render_run_note(
            _minimal_run_result(), _minimal_activity_data()
        )
        assert isinstance(filename, str)
        assert isinstance(content, str)

    def test_filename_format(self):
        filename, _ = render_run_note(
            _minimal_run_result(12345678), _minimal_activity_data(12345678)
        )
        assert filename == "running/2025-04-10-activity-12345678.md"

    def test_content_starts_with_frontmatter(self):
        _, content = render_run_note(
            _minimal_run_result(), _minimal_activity_data()
        )
        assert content.startswith("---\n")

    def test_frontmatter_has_required_fields(self):
        _, content = render_run_note(
            _minimal_run_result(), _minimal_activity_data()
        )
        assert "domain: running" in content
        assert "note_type: run_report" in content
        assert "activity_id: 12345678" in content
        assert 'date: "2025-04-10"' in content
        assert 'week: "2025-W15"' in content
        assert "aerobic_grade: coupled" in content
        assert "has_coaching_notes: false" in content

    def test_frontmatter_decoupling(self):
        _, content = render_run_note(
            _minimal_run_result(), _minimal_activity_data()
        )
        assert "decoupling_pct: 3.2" in content

    def test_frontmatter_anomaly_count(self):
        _, content = render_run_note(
            _minimal_run_result(), _minimal_activity_data()
        )
        assert "anomaly_count: 1" in content
        assert "hr_spike" in content

    def test_body_contains_run_name(self):
        _, content = render_run_note(
            _minimal_run_result(), _minimal_activity_data()
        )
        assert "Morning Run" in content

    def test_body_has_coaching_notes_section(self):
        _, content = render_run_note(
            _minimal_run_result(), _minimal_activity_data()
        )
        assert "## Coaching Notes" in content

    def test_body_has_mile_splits(self):
        _, content = render_run_note(
            _minimal_run_result(), _minimal_activity_data()
        )
        assert "## Mile Splits" in content
        assert "9:00" in content

    def test_body_has_hr_zones(self):
        _, content = render_run_note(
            _minimal_run_result(), _minimal_activity_data()
        )
        assert "## HR Analysis" in content
        assert "Z3" in content

    def test_body_has_anomalies(self):
        _, content = render_run_note(
            _minimal_run_result(), _minimal_activity_data()
        )
        assert "## Anomalies" in content
        assert "hr_spike" in content

    def test_minimal_result_no_crash(self):
        """A bare-minimum result dict (missing most fields) should not raise."""
        minimal = {"activity_id": 99, "data_points": 100}
        filename, content = render_run_note(minimal, {"id": 99, "start_date": "2025-06-01"})
        assert "running/2025-06-01-activity-99.md" == filename
        assert "has_coaching_notes: false" in content

    def test_decoupled_run_grade(self):
        result = _minimal_run_result()
        result["decoupling"]["decoupling_pct"] = 12.0
        _, content = render_run_note(result, _minimal_activity_data())
        assert "aerobic_grade: decoupled" in content

    def test_tags_in_frontmatter(self):
        _, content = render_run_note(
            _minimal_run_result(), _minimal_activity_data()
        )
        assert "- running" in content
        assert "- aerobic/coupled" in content
        assert "- week/2025-W15" in content


# ── render_trend_note ──

class TestRenderTrendNote:
    def _minimal_trend_result(self):
        return {
            "date_range": {"start": "2025-03-31", "end": "2025-04-27"},
            "total_runs": 12,
            "weeks": [
                {"week": "2025-W14", "runs": 3, "total_miles": 18.4, "total_minutes": 160.0, "avg_hr": 148, "longest_run_miles": 9.2},
                {"week": "2025-W15", "runs": 4, "total_miles": 24.1, "total_minutes": 215.0, "avg_hr": 150, "longest_run_miles": 11.0},
                {"week": "2025-W16", "runs": 3, "total_miles": 20.0, "total_minutes": 175.0, "avg_hr": None, "longest_run_miles": 10.0},
                {"week": "2025-W17", "runs": 2, "total_miles": 14.0, "total_minutes": 125.0, "avg_hr": 145, "longest_run_miles": 8.0},
            ],
        }

    def test_returns_tuple(self):
        filename, content = render_trend_note(self._minimal_trend_result())
        assert isinstance(filename, str)
        assert isinstance(content, str)

    def test_filename_contains_week(self):
        filename, _ = render_trend_note(self._minimal_trend_result())
        assert filename.startswith("running/trends/")
        assert "2025-W" in filename

    def test_frontmatter_fields(self):
        _, content = render_trend_note(self._minimal_trend_result())
        assert "note_type: trend_report" in content
        assert "total_runs: 12" in content
        assert "has_coaching_notes: false" in content

    def test_body_has_weekly_table(self):
        _, content = render_trend_note(self._minimal_trend_result())
        assert "## Weekly Summary" in content
        assert "2025-W14" in content
        assert "18.4" in content

    def test_handles_null_avg_hr(self):
        """Weeks with no HR data should not crash."""
        _, content = render_trend_note(self._minimal_trend_result())
        assert "2025-W16" in content

    def test_coaching_notes_section(self):
        _, content = render_trend_note(self._minimal_trend_result())
        assert "## Coaching Notes" in content


# ── render_compare_note ──

class TestRenderCompareNote:
    def _minimal_compare_result(self):
        return {
            "comparisons": [
                {
                    "activity_id": 111,
                    "name": "Long Run A",
                    "date": "2025-04-10",
                    "distance_miles": 9.2,
                    "moving_time_min": 79.0,
                    "avg_hr": 149,
                    "max_hr": 172,
                    "hr_drift": {"drift_pct": 3.4, "interpretation": "aerobic"},
                    "decoupling": {"decoupling_pct": 3.2},
                    "efficiency_factor": {"ef": 1.23},
                },
                {
                    "activity_id": 222,
                    "name": "Long Run B",
                    "date": "2025-04-17",
                    "distance_miles": 10.1,
                    "moving_time_min": 88.0,
                    "avg_hr": 152,
                    "max_hr": 175,
                    "hr_drift": {"drift_pct": 5.1, "interpretation": "moderate drift"},
                    "decoupling": {"decoupling_pct": 6.0},
                    "efficiency_factor": {"ef": 1.19},
                },
            ]
        }

    def test_returns_tuple(self):
        filename, content = render_compare_note(self._minimal_compare_result())
        assert isinstance(filename, str)
        assert isinstance(content, str)

    def test_filename_format(self):
        filename, _ = render_compare_note(self._minimal_compare_result())
        assert filename.startswith("running/compare/")
        assert "20250410" in filename
        assert "20250417" in filename

    def test_frontmatter_fields(self):
        _, content = render_compare_note(self._minimal_compare_result())
        assert "note_type: compare_runs" in content
        assert "run_count: 2" in content
        assert "has_coaching_notes: false" in content

    def test_body_has_table(self):
        _, content = render_compare_note(self._minimal_compare_result())
        assert "## Side-by-Side Metrics" in content
        assert "9.2" in content
        assert "10.1" in content

    def test_wikilinks_in_body(self):
        _, content = render_compare_note(self._minimal_compare_result())
        assert "[[" in content
        assert "2025-04-10-activity-111" in content

    def test_coaching_notes_section(self):
        _, content = render_compare_note(self._minimal_compare_result())
        assert "## Coaching Notes" in content

    def test_empty_comparisons_no_crash(self):
        filename, content = render_compare_note({"comparisons": []})
        assert isinstance(filename, str)
        assert isinstance(content, str)

"""
Tests for vault/renderer.py — pure functions, no I/O.
"""

import pytest

from tailor.framework.vault.renderer import (
    _aerobic_grade,
    _iso_week,
    _pace_from_velocity,
    format_wikilink,
    render_compare_note,
    render_moment_note,
    render_run_note,
    render_theme_note,
    render_trend_note,
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
        assert "has_insight_notes: false" in content

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

    def test_body_has_insight_notes_section(self):
        _, content = render_run_note(
            _minimal_run_result(), _minimal_activity_data()
        )
        assert "## Insights" in content

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
        assert "has_insight_notes: false" in content

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
        assert "has_insight_notes: false" in content

    def test_body_has_weekly_table(self):
        _, content = render_trend_note(self._minimal_trend_result())
        assert "## Weekly Summary" in content
        assert "2025-W14" in content
        assert "18.4" in content

    def test_handles_null_avg_hr(self):
        """Weeks with no HR data should not crash."""
        _, content = render_trend_note(self._minimal_trend_result())
        assert "2025-W16" in content

    def test_insight_notes_section(self):
        _, content = render_trend_note(self._minimal_trend_result())
        assert "## Insights" in content


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
        assert "has_insight_notes: false" in content

    def test_body_has_table(self):
        _, content = render_compare_note(self._minimal_compare_result())
        assert "## Side-by-Side Metrics" in content
        assert "9.2" in content
        assert "10.1" in content

    def test_wikilinks_in_body(self):
        _, content = render_compare_note(self._minimal_compare_result())
        assert "[[" in content
        assert "2025-04-10-activity-111" in content

    def test_insight_notes_section(self):
        _, content = render_compare_note(self._minimal_compare_result())
        assert "## Insights" in content

    def test_empty_comparisons_no_crash(self):
        filename, content = render_compare_note({"comparisons": []})
        assert isinstance(filename, str)
        assert isinstance(content, str)


# ── format_wikilink ──

class TestFormatWikilink:
    def test_target_only(self):
        assert format_wikilink("foo") == "[[foo]]"

    def test_with_display(self):
        assert format_wikilink("foo", "Nice Foo") == "[[foo|Nice Foo]]"

    def test_empty_display_falls_back_to_target(self):
        assert format_wikilink("foo", "") == "[[foo]]"


# ── render_theme_note ──

class TestRenderThemeNote:
    def _minimal_theme(self, **overrides):
        base = {
            "slug": "dehydration-drift",
            "title": "Dehydration Drift",
            "hypothesis": "HR drifts higher on hot Tuesday runs.",
            "status": "open",
            "opened": "2026-04-01",
            "last_updated": "2026-04-10",
            "linked_runs": [12345, 67890],
            "tags": ["hydration"],
            "confidence": "medium",
        }
        base.update(overrides)
        return base

    def test_returns_tuple(self):
        filename, content = render_theme_note(self._minimal_theme())
        assert isinstance(filename, str)
        assert isinstance(content, str)

    def test_filename_format(self):
        filename, _ = render_theme_note(self._minimal_theme())
        assert filename == "themes/dehydration-drift.md"

    def test_slug_required(self):
        with pytest.raises(ValueError):
            render_theme_note({"hypothesis": "x"})

    def test_frontmatter_has_kind_theme(self):
        _, content = render_theme_note(self._minimal_theme())
        assert "kind: theme" in content
        assert "note_type: theme" in content

    def test_frontmatter_has_status(self):
        _, content = render_theme_note(self._minimal_theme(status="resolved"))
        assert 'status: "resolved"' in content

    def test_frontmatter_has_confidence(self):
        _, content = render_theme_note(self._minimal_theme(confidence="high"))
        assert 'confidence: "high"' in content

    def test_frontmatter_has_linked_runs(self):
        _, content = render_theme_note(self._minimal_theme())
        # Flow-list ints, no quotes
        assert "linked_runs: [12345, 67890]" in content

    def test_body_has_hypothesis_section(self):
        _, content = render_theme_note(self._minimal_theme())
        assert "## Hypothesis" in content
        assert "HR drifts higher" in content

    def test_body_has_evidence_section(self):
        _, content = render_theme_note(self._minimal_theme())
        assert "## Evidence" in content
        # Placeholder when no evidence yet
        assert "*(No evidence recorded yet.)*" in content

    def test_body_has_resolution_section(self):
        _, content = render_theme_note(self._minimal_theme())
        assert "## Resolution" in content
        # Open status → open resolution placeholder
        assert "*(Open" in content

    def test_resolved_status_resolution_text(self):
        _, content = render_theme_note(
            self._minimal_theme(status="resolved", resolution="Confirmed via July heat wave.")
        )
        assert "Confirmed via July heat wave." in content

    def test_linked_runs_section_has_wikilinks(self):
        _, content = render_theme_note(self._minimal_theme())
        assert "## Linked Runs" in content
        # Wikilink format: YYYY-MM-DD-activity-<id>
        assert "activity-12345" in content
        assert "[[" in content and "]]" in content

    def test_initial_evidence_string(self):
        _, content = render_theme_note(
            self._minimal_theme(evidence="Observed at mile 6 on 4/10.")
        )
        assert "### Evidence" in content
        assert "Observed at mile 6" in content

    def test_initial_evidence_list(self):
        _, content = render_theme_note(
            self._minimal_theme(evidence=["first block", "second block"])
        )
        assert "first block" in content
        assert "second block" in content

    def test_theme_tag_always_present(self):
        _, content = render_theme_note(self._minimal_theme(tags=["hydration"]))
        # Block-list entries
        assert "  - theme" in content
        assert "  - hydration" in content


# ── render_moment_note ──

class TestRenderMomentNote:
    def _minimal_moment(self, **overrides):
        base = {
            "title": "Tuesday Drift Hypothesis",
            "body": "Noticed HR climbing past mile 5 consistently on hot days.",
            "date": "2026-04-10",
            "linked_runs": [12345],
            "linked_themes": ["dehydration-drift"],
            "tags": ["observation"],
        }
        base.update(overrides)
        return base

    def test_returns_tuple(self):
        filename, content = render_moment_note(self._minimal_moment())
        assert isinstance(filename, str)
        assert isinstance(content, str)

    def test_filename_format(self):
        filename, _ = render_moment_note(self._minimal_moment())
        # moments/YYYY-MM-DD-<slug>.md
        assert filename.startswith("moments/2026-04-10-")
        assert filename.endswith(".md")

    def test_slug_derived_from_title(self):
        filename, _ = render_moment_note(self._minimal_moment())
        assert "tuesday-drift-hypothesis" in filename

    def test_explicit_slug_overrides(self):
        filename, _ = render_moment_note(self._minimal_moment(slug="custom-slug"))
        assert filename == "moments/2026-04-10-custom-slug.md"

    def test_title_required(self):
        with pytest.raises(ValueError):
            render_moment_note({"body": "x"})

    def test_body_required(self):
        with pytest.raises(ValueError):
            render_moment_note({"title": "x"})

    def test_frontmatter_has_kind_moment(self):
        _, content = render_moment_note(self._minimal_moment())
        assert "kind: moment" in content
        assert "note_type: moment" in content

    def test_frontmatter_has_date(self):
        _, content = render_moment_note(self._minimal_moment())
        assert 'date: "2026-04-10"' in content

    def test_body_contains_prose(self):
        _, content = render_moment_note(self._minimal_moment())
        assert "Noticed HR climbing past mile 5" in content

    def test_body_contains_title_heading(self):
        _, content = render_moment_note(self._minimal_moment())
        assert "# Tuesday Drift Hypothesis" in content

    def test_linked_runs_wikilinks(self):
        _, content = render_moment_note(self._minimal_moment())
        assert "## Linked Runs" in content
        assert "activity-12345" in content

    def test_linked_themes_wikilinks(self):
        _, content = render_moment_note(self._minimal_moment())
        assert "## Linked Themes" in content
        assert "[[dehydration-drift]]" in content

    def test_moment_tag_always_present(self):
        _, content = render_moment_note(self._minimal_moment(tags=["observation"]))
        assert "  - moment" in content
        assert "  - observation" in content


# ════════════════════════════════════════════════════════════════
# render_failure_mode_note (v6.1)
# ════════════════════════════════════════════════════════════════


class TestRenderFailureModeNote:
    @staticmethod
    def _minimal(**overrides):
        fm = {
            "slug": "hr-spike-misread",
            "title": "HR spike misread as fitness signal",
            "symptom": "Steep mid-run HR spike was treated as drift.",
            "diagnosis": "Sensor catchup burst from the watch.",
            "mitigation": "Apply 30s cooldown before zone classification.",
        }
        fm.update(overrides)
        return fm

    def test_filename_under_failure_modes(self):
        from tailor.framework.vault.renderer import render_failure_mode_note
        filename, _ = render_failure_mode_note(self._minimal())
        assert filename == "failure-modes/hr-spike-misread.md"

    def test_required_fields_validated(self):
        from tailor.framework.vault.renderer import render_failure_mode_note
        with pytest.raises(ValueError, match="symptom"):
            render_failure_mode_note(self._minimal(symptom=""))
        with pytest.raises(ValueError, match="diagnosis"):
            render_failure_mode_note(self._minimal(diagnosis=""))
        with pytest.raises(ValueError, match="mitigation"):
            render_failure_mode_note(self._minimal(mitigation=""))
        with pytest.raises(ValueError, match="slug"):
            render_failure_mode_note(self._minimal(slug=""))

    def test_status_must_be_in_allowed_set(self):
        from tailor.framework.vault.renderer import render_failure_mode_note
        with pytest.raises(ValueError, match="status"):
            render_failure_mode_note(self._minimal(status="bogus"))

    def test_body_contains_all_sections(self):
        from tailor.framework.vault.renderer import render_failure_mode_note
        _, content = render_failure_mode_note(self._minimal())
        assert "## Symptom" in content
        assert "## Diagnosis" in content
        assert "## Mitigation" in content
        assert "## Evidence" in content

    def test_related_section_only_when_linked(self):
        from tailor.framework.vault.renderer import render_failure_mode_note
        _, plain = render_failure_mode_note(self._minimal())
        assert "## Related" not in plain
        _, with_rel = render_failure_mode_note(
            self._minimal(related_themes=["drift"], related_subjects=["S001"])
        )
        assert "## Related" in with_rel
        assert "[[drift]]" in with_rel
        assert "S001" in with_rel

    def test_failure_mode_tag_always_present(self):
        from tailor.framework.vault.renderer import render_failure_mode_note
        _, content = render_failure_mode_note(self._minimal(tags=["alpha"]))
        assert "  - failure_mode" in content
        assert "  - alpha" in content

    def test_initial_evidence_replaces_placeholder(self):
        from tailor.framework.vault.renderer import render_failure_mode_note
        _, with_ev = render_failure_mode_note(
            self._minimal(evidence="Specific observation from 2026-04-10.")
        )
        assert "Specific observation from 2026-04-10." in with_ev
        assert "*(No evidence recorded yet.)*" not in with_ev

    def test_no_evidence_shows_placeholder(self):
        from tailor.framework.vault.renderer import render_failure_mode_note
        _, content = render_failure_mode_note(self._minimal())
        assert "*(No evidence recorded yet.)*" in content


# ════════════════════════════════════════════════════════════════
# render_dashboard_note (v6.1, ADR 0007 dual-output)
# ════════════════════════════════════════════════════════════════


class TestRenderDashboardNote:
    def test_filename_under_dashboards(self):
        from tailor.framework.vault.renderer import render_dashboard_note
        filename, _ = render_dashboard_note(
            name="open-themes",
            title="Open themes",
            description="Persistent hypotheses being tracked.",
            columns=["Theme", "Confidence"],
            rows=[["[[drift]]", "medium"]],
        )
        assert filename == "dashboards/open-themes.md"

    def test_snapshot_table_always_present(self):
        from tailor.framework.vault.renderer import render_dashboard_note
        _, content = render_dashboard_note(
            name="open-themes",
            title="Open themes",
            description="d",
            columns=["Theme", "Confidence"],
            rows=[["[[drift]]", "medium"]],
        )
        assert "## Snapshot" in content
        assert "[[drift]]" in content
        assert "| Theme | Confidence |" in content

    def test_dataview_block_optional(self):
        from tailor.framework.vault.renderer import render_dashboard_note
        _, plain = render_dashboard_note(
            name="x", title="X", description="d",
            columns=["A"], rows=[["1"]],
        )
        assert "```dataview" not in plain

        _, with_dv = render_dashboard_note(
            name="x", title="X", description="d",
            columns=["A"], rows=[["1"]],
            dataview_query="TABLE A FROM \"x\"",
        )
        assert "```dataview" in with_dv
        assert "## Snapshot" in with_dv

    def test_empty_rows_renders_placeholder(self):
        from tailor.framework.vault.renderer import render_dashboard_note
        _, content = render_dashboard_note(
            name="x", title="X", description="d",
            columns=["A"], rows=[],
        )
        assert "*(No rows.)*" in content

    def test_blank_name_rejected(self):
        from tailor.framework.vault.renderer import render_dashboard_note
        with pytest.raises(ValueError, match="name"):
            render_dashboard_note(
                name="", title="X", description="d",
                columns=["A"], rows=[],
            )

    def test_none_cell_renders_em_dash(self):
        from tailor.framework.vault.renderer import render_dashboard_note
        _, content = render_dashboard_note(
            name="x", title="X", description="d",
            columns=["A", "B"], rows=[["v1", None]],
        )
        assert "—" in content

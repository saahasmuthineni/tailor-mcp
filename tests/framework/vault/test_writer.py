"""
Tests for vault/writer.py — VaultWriter with a real temp filesystem + SQLite.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest


def _make_writer(vault_path: Path, data_dir: Path, running_storage=None):
    from biosensor_mcp.framework.vault.writer import VaultWriter
    mock_storage = running_storage or MagicMock()
    mock_storage.get_activity = MagicMock(return_value={
        "id": 12345678,
        "name": "Morning Run",
        "start_date": "2025-04-10T07:00:00Z",
        "distance": 14800,
        "moving_time": 4740,
        "average_heartrate": 149,
        "max_heartrate": 172,
    })
    return VaultWriter(
        vault_path=vault_path,
        data_dir=data_dir,
        vaultable_tools={"strava_run_report", "strava_trend_report", "strava_compare_runs"},
        max_hr=195,
    )


def _minimal_run_result(activity_id=12345678):
    return {
        "activity_id": activity_id,
        "data_points": 3600,
        "activity_name": "Morning Run",
        "start_date": "2025-04-10T13:00:00Z",
        "distance": 14800,
        "moving_time": 4740,
        "average_heartrate": 149,
        "max_heartrate": 172,
        "decoupling": {"decoupling_pct": 3.2, "interpretation": "well coupled"},
        "efficiency_factor": {"ef": 1.23},
        "hr_drift": {"drift_pct": 3.4, "interpretation": "aerobic",
                     "first_half_avg": 148, "second_half_avg": 153},
        "hr_zones": {
            "zone_seconds": {1: 60, 2: 300, 3: 2400, 4: 720, 5: 120},
            "zone_pct": {1: 1.7, 2: 8.3, 3: 66.7, 4: 20.0, 5: 3.3},
            "avg_hr": 149, "max_hr_observed": 172, "min_hr": 120, "max_hr_setting": 195,
        },
        "phases": [],
        "mile_splits": [{"mile": 1, "elapsed_seconds": 540, "pace": "9:00"}],
        "gap_splits": [],
        "anomalies": [{"type": "hr_spike", "severity": "moderate", "description": "test"}],
        "note": "Computed server-side.",
    }


def _minimal_trend_result():
    return {
        "date_range": {"start": "2025-03-31", "end": "2025-04-27"},
        "total_runs": 4,
        "weeks": [
            {"week": "2025-W15", "runs": 4, "total_miles": 24.1,
             "total_minutes": 215.0, "avg_hr": 150, "longest_run_miles": 11.0},
        ],
    }


class TestVaultWriterWriteNote:
    def test_write_run_note_creates_file(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            vault_path = Path(vault_dir)
            writer = _make_writer(vault_path, Path(data_dir))
            filename = writer.write_note("strava_run_report", _minimal_run_result())
            assert (vault_path / filename).exists()
            writer.close()

    def test_write_run_note_returns_filename(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            filename = writer.write_note("strava_run_report", _minimal_run_result())
            assert filename == "running/2025-04-10-activity-12345678.md"
            writer.close()

    def test_write_trend_note_creates_file(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            filename = writer.write_note("strava_trend_report", _minimal_trend_result())
            assert (Path(vault_dir) / filename).exists()
            writer.close()

    def test_file_contains_valid_frontmatter(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            filename = writer.write_note("strava_run_report", _minimal_run_result())
            content = (Path(vault_dir) / filename).read_text(encoding="utf-8")
            assert content.startswith("---\n")
            assert "has_insight_notes: false" in content
            writer.close()

    def test_note_indexed_in_storage(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            filename = writer.write_note("strava_run_report", _minimal_run_result())
            row = writer._storage.get_note(filename)
            assert row is not None
            assert row["note_type"] == "run_report"
            assert row["domain"] == "running"
            writer.close()

    def test_overwrite_existing_note(self):
        """Writing the same note twice should not error."""
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer.write_note("strava_run_report", _minimal_run_result())
            writer.write_note("strava_run_report", _minimal_run_result())
            row = writer._storage.get_note("running/2025-04-10-activity-12345678.md")
            assert row is not None
            writer.close()


class TestVaultWriterHook:
    def test_hook_writes_file_for_vaultable_tool(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer("running", "strava_run_report", _minimal_run_result())
            vault_path = Path(vault_dir)
            files = list(vault_path.rglob("*.md"))
            assert len(files) == 1
            writer.close()

    def test_hook_skips_non_vaultable_tool(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer("running", "strava_list_runs", {"runs": []})
            vault_path = Path(vault_dir)
            files = list(vault_path.rglob("*.md"))
            assert len(files) == 0
            writer.close()

    def test_hook_swallows_errors(self):
        """Errors in the hook must not propagate."""
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            # Pass a result that will cause a render error — bad activity_id
            bad_result = {"activity_id": None, "data_points": 0}
            # Should not raise
            writer("running", "strava_run_report", bad_result)
            writer.close()


class TestVaultWriterAppendInsightNotes:
    def test_appends_notes_to_existing_file(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            filename = writer.write_note("strava_run_report", _minimal_run_result())
            writer.append_insight_notes(filename, "Great aerobic base run. Heart rate well controlled.")
            content = (Path(vault_dir) / filename).read_text(encoding="utf-8")
            assert "Great aerobic base run" in content
            writer.close()

    def test_updates_has_insight_notes_in_frontmatter(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            filename = writer.write_note("strava_run_report", _minimal_run_result())
            writer.append_insight_notes(filename, "Test insight notes.")
            content = (Path(vault_dir) / filename).read_text(encoding="utf-8")
            assert "has_insight_notes: true" in content
            writer.close()

    def test_updates_index_has_insight_notes(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            filename = writer.write_note("strava_run_report", _minimal_run_result())
            writer.append_insight_notes(filename, "Test insight notes.")
            row = writer._storage.get_note(filename)
            assert row["has_insight_notes"] is True
            writer.close()

    def test_rejects_empty_notes(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            filename = writer.write_note("strava_run_report", _minimal_run_result())
            with pytest.raises(ValueError, match="empty"):
                writer.append_insight_notes(filename, "   ")
            writer.close()

    def test_rejects_notes_too_long(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            filename = writer.write_note("strava_run_report", _minimal_run_result())
            with pytest.raises(ValueError, match="too long"):
                writer.append_insight_notes(filename, "x" * 2001)
            writer.close()

    def test_rejects_missing_file(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            with pytest.raises(FileNotFoundError):
                writer.append_insight_notes("running/nonexistent.md", "Notes.")
            writer.close()


class TestVaultWriterPathSafety:
    def test_path_traversal_rejected(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            with pytest.raises(ValueError, match="traversal"):
                writer._safe_path("../../etc/passwd")
            writer.close()

    def test_valid_path_accepted(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            p = writer._safe_path("running/2025-04-10-activity-123.md")
            assert str(p).endswith("running/2025-04-10-activity-123.md".replace("/", "\\") if
                                   __import__("sys").platform == "win32" else
                                   "running/2025-04-10-activity-123.md")
            writer.close()


# ── Theme / Moment / Registry / Evidence ──

def _minimal_theme(**overrides):
    base = {
        "slug": "dehydration-drift",
        "title": "Dehydration Drift",
        "hypothesis": "HR drifts on hot days.",
        "status": "open",
        "opened": "2026-04-01",
        "last_updated": "2026-04-10",
        "linked_runs": [12345],
        "tags": ["hydration"],
        "confidence": "medium",
    }
    base.update(overrides)
    return base


def _minimal_moment(**overrides):
    base = {
        "title": "Aha Moment",
        "body": "Noticed HR climbs past mile 5 on hot days.",
        "date": "2026-04-10",
        "linked_runs": [12345],
        "linked_themes": ["dehydration-drift"],
        "tags": ["observation"],
    }
    base.update(overrides)
    return base


class TestVaultWriterWriteTheme:
    def test_creates_file(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            filename = writer.write_theme(_minimal_theme())
            assert filename == "themes/dehydration-drift.md"
            assert (Path(vault_dir) / filename).exists()
            writer.close()

    def test_indexed_in_storage(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer.write_theme(_minimal_theme())
            theme = writer._storage.get_theme("dehydration-drift")
            assert theme is not None
            assert theme["status"] == "open"
            writer.close()

    def test_overwrites_existing(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer.write_theme(_minimal_theme())
            writer.write_theme(_minimal_theme(status="resolved"))
            theme = writer._storage.get_theme("dehydration-drift")
            assert theme["status"] == "resolved"
            writer.close()


class TestVaultWriterWriteMoment:
    def test_creates_file(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            filename = writer.write_moment(_minimal_moment())
            assert filename.startswith("moments/2026-04-10-")
            assert (Path(vault_dir) / filename).exists()
            writer.close()

    def test_indexed_in_storage(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            filename = writer.write_moment(_minimal_moment())
            row = writer._storage.get_note(filename)
            assert row is not None
            assert row["note_type"] == "moment"
            writer.close()


class TestVaultWriterAppendThemeEvidence:
    def test_appends_evidence_block(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer.write_theme(_minimal_theme())
            writer.append_theme_evidence(
                "dehydration-drift", "First hot Tuesday: 8bpm higher at mile 6."
            )
            content = (Path(vault_dir) / "themes/dehydration-drift.md").read_text(encoding="utf-8")
            assert "First hot Tuesday" in content
            assert "### Evidence —" in content
            writer.close()

    def test_preserves_prior_evidence_blocks_in_order(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer.write_theme(_minimal_theme())
            writer.append_theme_evidence("dehydration-drift", "First observation.")
            writer.append_theme_evidence("dehydration-drift", "Second observation.")
            content = (Path(vault_dir) / "themes/dehydration-drift.md").read_text(encoding="utf-8")
            first_idx = content.find("First observation.")
            second_idx = content.find("Second observation.")
            assert first_idx != -1 and second_idx != -1
            assert first_idx < second_idx
            writer.close()

    def test_rejects_empty_evidence(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer.write_theme(_minimal_theme())
            with pytest.raises(ValueError, match="empty"):
                writer.append_theme_evidence("dehydration-drift", "   ")
            writer.close()

    def test_rejects_evidence_too_long(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer.write_theme(_minimal_theme())
            with pytest.raises(ValueError, match="too long"):
                writer.append_theme_evidence("dehydration-drift", "x" * 2001)
            writer.close()

    def test_rejects_missing_theme(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            with pytest.raises(FileNotFoundError):
                writer.append_theme_evidence("does-not-exist", "some evidence")
            writer.close()

    def test_rejects_slug_with_slash(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            with pytest.raises(ValueError, match="Invalid theme slug"):
                writer.append_theme_evidence("../etc", "evidence")
            writer.close()

    def test_inserts_before_resolution_header(self):
        """Evidence must appear above ## Resolution so the log stays chronological."""
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer.write_theme(_minimal_theme())
            writer.append_theme_evidence("dehydration-drift", "Key evidence here.")
            content = (Path(vault_dir) / "themes/dehydration-drift.md").read_text(encoding="utf-8")
            ev_idx = content.find("Key evidence here.")
            res_idx = content.find("## Resolution")
            assert ev_idx != -1 and res_idx != -1
            assert ev_idx < res_idx
            writer.close()

    def test_refreshes_last_updated_stamp(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer.write_theme(_minimal_theme(last_updated="2020-01-01"))
            writer.append_theme_evidence("dehydration-drift", "New evidence.")
            content = (Path(vault_dir) / "themes/dehydration-drift.md").read_text(encoding="utf-8")
            assert 'last_updated: "2020-01-01"' not in content
            writer.close()


class TestVaultWriterAppendThemeEvidenceProvenance:
    def test_evidence_with_provenance_renders_source_line(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer.write_theme(_minimal_theme())
            writer.append_theme_evidence(
                "dehydration-drift",
                "Mile 6: HR 8bpm higher.",
                source_tier=1,
                source_tool="strava_run_report",
                source_domain="running",
                verification="computed",
            )
            content = (Path(vault_dir) / "themes/dehydration-drift.md").read_text(encoding="utf-8")
            assert "> Source: running/strava_run_report (Tier 1)" in content
            assert "Verification: computed" in content
            writer.close()

    def test_evidence_without_provenance_no_source_line(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer.write_theme(_minimal_theme())
            writer.append_theme_evidence("dehydration-drift", "Some observation.")
            content = (Path(vault_dir) / "themes/dehydration-drift.md").read_text(encoding="utf-8")
            assert "> Source:" not in content
            writer.close()

    def test_evidence_partial_provenance(self):
        """Only tier supplied — still renders a source line without a tool label."""
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            writer.write_theme(_minimal_theme())
            writer.append_theme_evidence(
                "dehydration-drift", "Partial observation.", source_tier=2,
            )
            content = (Path(vault_dir) / "themes/dehydration-drift.md").read_text(encoding="utf-8")
            assert "> Source: Tier 2" in content
            writer.close()


class TestVaultWriterRendererRegistry:
    def test_register_custom_renderer(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))

            def custom_renderer(result: dict) -> tuple[str, str]:
                return ("custom/hello.md", "---\nkind: custom\n---\nhi")

            writer.register_renderer("custom_tool", custom_renderer)
            filename, content = writer._render("custom_tool", {})
            assert filename == "custom/hello.md"
            assert "hi" in content
            writer.close()

    def test_unknown_tool_raises(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            with pytest.raises(ValueError, match="No renderer"):
                writer._render("unknown_tool", {})
            writer.close()

    def test_seeded_renderers_present(self):
        """The registry must come pre-seeded with the core 5 renderers."""
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))
            for name in [
                "strava_run_report",
                "strava_trend_report",
                "strava_compare_runs",
                "vault_theme",
                "vault_moment",
            ]:
                assert name in writer._renderers
            writer.close()

    def test_re_register_replaces(self):
        with TemporaryDirectory() as vault_dir, TemporaryDirectory() as data_dir:
            writer = _make_writer(Path(vault_dir), Path(data_dir))

            def r1(_):
                return ("a.md", "first")

            def r2(_):
                return ("a.md", "second")

            writer.register_renderer("tool_x", r1)
            writer.register_renderer("tool_x", r2)
            _, content = writer._render("tool_x", {})
            assert content == "second"
            writer.close()

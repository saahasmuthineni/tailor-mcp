"""
Tests for vault/writer.py — VaultWriter with a real temp filesystem + SQLite.
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock


def _make_writer(vault_path: Path, data_dir: Path, running_storage=None):
    from biosensor_mcp.vault.writer import VaultWriter
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
        running_storage=mock_storage,
        vaultable_tools={"strava_run_report", "strava_trend_report", "strava_compare_runs"},
        max_hr=195,
    )


def _minimal_run_result(activity_id=12345678):
    return {
        "activity_id": activity_id,
        "data_points": 3600,
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

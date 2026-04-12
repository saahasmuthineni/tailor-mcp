"""
Tests for vault/layer.py — VaultLayer tools with real temp FS + SQLite.
"""

import asyncio
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock


def _run(coro):
    return asyncio.run(coro)


def _async_return(value):
    """Create an async function that returns a fixed value (for mocking dispatch_internal)."""
    async def _mock(*args, **kwargs):
        return value
    return _mock


def _make_running_storage_mock(activity_id=12345678):
    from datetime import datetime, timedelta, timezone
    # Use a date 4 weeks ago so it stays within any reasonable weeks_back window
    recent_date = (datetime.now(timezone.utc) - timedelta(weeks=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    mock = MagicMock()
    mock.get_activity = MagicMock(return_value={
        "id": activity_id,
        "name": "Morning Run",
        "start_date": recent_date,
        "distance": 14800,
        "moving_time": 4740,
        "average_heartrate": 149,
        "max_heartrate": 172,
    })
    mock.list_activities = MagicMock(return_value=[])
    mock.get_streams = MagicMock(return_value=None)
    return mock


def _setup_vault(vault_dir, data_dir, activity_id=12345678, backfill_config=None):
    """Create a VaultLayer and pre-write one run note."""
    from biosensor_mcp.vault.writer import VaultWriter
    from biosensor_mcp.vault.layer import VaultLayer

    vault_path = Path(vault_dir)
    data_path = Path(data_dir)
    # Still used to derive the dynamic date for test assertions
    running_storage = _make_running_storage_mock(activity_id)
    activity_date = running_storage.get_activity(activity_id)["start_date"][:10]

    writer = VaultWriter(
        vault_path=vault_path,
        data_dir=data_path,
        vaultable_tools={"strava_run_report"},
        max_hr=195,
    )

    result = {
        "activity_id": activity_id,
        "data_points": 3600,
        # Activity metadata (now embedded in result by RunningChild)
        "activity_name": "Morning Run",
        "start_date": running_storage.get_activity(activity_id)["start_date"],
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
    filename = writer.write_note("strava_run_report", result)

    layer = VaultLayer(
        vault_path=vault_path,
        vault_writer=writer,
        backfill_config=backfill_config,
    )
    return layer, writer, filename, activity_date


class TestVaultLayerMetadata:
    def test_has_seven_tools(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            assert len(layer.tool_definitions) == 7
            layer.close()

    def test_all_tools_are_tier_1(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            for tool in layer.tool_definitions:
                assert tool.tier == 1
            layer.close()

    def test_not_a_child_mcp(self):
        """VaultLayer should not inherit from ChildMCP."""
        from biosensor_mcp.framework.interfaces import ChildMCP
        from biosensor_mcp.vault.layer import VaultLayer
        assert not issubclass(VaultLayer, ChildMCP)


class TestVaultGetFitnessSummary:
    def test_returns_weekly_summary(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_get_fitness_summary", {"weeks_back": 8}))
                assert "weekly_summary" in result
                assert len(result["weekly_summary"]) >= 1
            finally:
                layer.close()

    def test_empty_vault_returns_note(self):
        from biosensor_mcp.vault.writer import VaultWriter
        from biosensor_mcp.vault.layer import VaultLayer
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            writer = VaultWriter(Path(v), Path(d), vaultable_tools=set())
            layer = VaultLayer(Path(v), writer)
            try:
                result = _run(layer.execute("vault_get_fitness_summary", {}))
                assert "note" in result
            finally:
                layer.close()


class TestVaultListNotes:
    def test_lists_existing_notes(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_list_notes", {}))
            assert result["count"] >= 1
            assert len(result["notes"]) >= 1
            layer.close()

    def test_filter_by_note_type(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_list_notes", {"note_type": "run_report"}))
            assert result["count"] >= 1
            for note in result["notes"]:
                assert note["note_type"] == "run_report"
            layer.close()

    def test_filter_has_insight_notes_false(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_list_notes", {"has_insight_notes": False}))
            assert result["count"] >= 1
            layer.close()


class TestVaultReadNote:
    def test_read_existing_note(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, filename, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_read_note", {"filename": filename}))
            assert "content" in result
            assert "has_insight_notes" in result
            assert "Morning Run" in result["content"]
            layer.close()

    def test_read_missing_note_returns_error(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_read_note", {"filename": "running/nonexistent.md"}))
            assert "error" in result
            layer.close()

    def test_path_traversal_rejected(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_read_note", {"filename": "../../etc/passwd"}))
            assert "error" in result
            layer.close()


class TestVaultSearchNotes:
    def test_search_finds_match(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_search_notes", {"query": "Morning Run"}))
            assert result["count"] >= 1
            layer.close()

    def test_search_no_match(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_search_notes", {"query": "zzz_no_match_xyz"}))
            assert result["count"] == 0
            layer.close()


class TestVaultListAnomalies:
    def test_lists_anomalous_run(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_list_anomalies", {}))
            assert result["count"] >= 1
            assert result["notes"][0]["anomaly_count"] > 0
            layer.close()

    def test_filter_by_anomaly_type_match(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_list_anomalies", {"anomaly_type": "hr_spike"}))
            assert result["count"] >= 1
            layer.close()

    def test_filter_by_anomaly_type_no_match(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_list_anomalies", {"anomaly_type": "nonexistent_type"}))
            assert result["count"] == 0
            layer.close()


class TestVaultAnnotateRun:
    def test_annotate_existing_note(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, filename, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_annotate_run", {
                "filename": filename,
                "notes": "Excellent aerobic base run. HR very well controlled.",
            }))
            assert result.get("annotated") is True
            content = (Path(v) / filename).read_text(encoding="utf-8")
            assert "Excellent aerobic base run" in content
            layer.close()

    def test_annotate_missing_note_returns_error(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_annotate_run", {
                "filename": "running/ghost.md",
                "notes": "Test",
            }))
            assert "error" in result
            layer.close()


class TestVaultBackfill:
    def test_backfill_no_router_returns_error(self):
        """Backfill without a router reference should return an error."""
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            result = _run(layer.execute("vault_backfill", {}))
            assert "error" in result
            layer.close()

    def test_backfill_no_config_returns_error(self):
        """Backfill without backfill_config should return a configuration error."""
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            # Set a router but no backfill_config
            layer._router = MagicMock()
            result = _run(layer.execute("vault_backfill", {}))
            assert "error" in result
            assert "not configured" in result["error"].lower()
            layer.close()

    def test_backfill_with_no_activities(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d, backfill_config={
                "list_tool": "strava_list_runs",
                "report_tool": "strava_run_report",
            })
            # Mock router.dispatch_internal to return empty activity list
            mock_router = MagicMock()
            mock_router.dispatch_internal = _async_return({"activities": []})
            layer._router = mock_router
            result = _run(layer.execute("vault_backfill", {}))
            assert result["written"] == 0
            layer.close()

    def test_backfill_skips_already_indexed(self):
        """Activity already in vault index should be skipped."""
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, activity_date = _setup_vault(v, d, backfill_config={
                "list_tool": "strava_list_runs",
                "report_tool": "strava_run_report",
            })
            # Mock router.dispatch_internal
            mock_router = MagicMock()
            mock_router.dispatch_internal = _async_return({"activities": [{
                "id": 12345678,
                "start_date": activity_date + "T07:00:00Z",
            }]})
            layer._router = mock_router
            result = _run(layer.execute("vault_backfill", {}))
            assert result["skipped"] >= 1
            layer.close()

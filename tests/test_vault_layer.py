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
    def test_has_expected_tools(self):
        """
        VaultLayer exposes 15 Tier-1 tools: the 7 original + 8 new
        (themes, moments, session capture, rescan, traverse).
        """
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            names = {t.name for t in layer.tool_definitions}
            assert len(layer.tool_definitions) == 15
            expected = {
                "vault_get_fitness_summary",
                "vault_list_notes",
                "vault_read_note",
                "vault_search_notes",
                "vault_list_anomalies",
                "vault_annotate_run",
                "vault_backfill",
                "vault_list_themes",
                "vault_read_theme",
                "vault_upsert_theme",
                "vault_list_moments",
                "vault_capture_moment",
                "vault_capture_session",
                "vault_rescan",
                "vault_traverse_links",
            }
            assert names == expected
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


# ══════════════════════════════════════════════════════════════════
# New tools — themes, moments, session capture, rescan, traverse
# ══════════════════════════════════════════════════════════════════

class TestVaultUpsertTheme:
    def test_creates_new_theme(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_upsert_theme", {
                    "slug": "dehydration-drift",
                    "hypothesis": "HR drifts on hot days.",
                    "confidence": "medium",
                }))
                assert result.get("created") is True
                assert result["filename"] == "themes/dehydration-drift.md"
                assert (Path(v) / "themes/dehydration-drift.md").exists()
            finally:
                layer.close()

    def test_new_theme_requires_hypothesis(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_upsert_theme", {
                    "slug": "no-hypothesis",
                }))
                assert "error" in result
                assert "hypothesis" in result["error"].lower()
            finally:
                layer.close()

    def test_update_existing_appends_evidence(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "HR drifts on hot days.",
                }))
                result = _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "evidence": "Observed again on 4/15.",
                }))
                assert result.get("created") is False
                content = (Path(v) / "themes/drift.md").read_text(encoding="utf-8")
                assert "Observed again on 4/15." in content
            finally:
                layer.close()

    def test_update_merges_status(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "HR drifts on hot days.",
                }))
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "status": "resolved",
                    "resolution": "Confirmed via heat-wave runs.",
                }))
                theme = writer._storage.get_theme("drift")
                assert theme["status"] == "resolved"
                content = (Path(v) / "themes/drift.md").read_text(encoding="utf-8")
                assert "Confirmed via heat-wave runs." in content
            finally:
                layer.close()


class TestVaultListThemes:
    def test_lists_themes(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "a", "hypothesis": "H1",
                }))
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "b", "hypothesis": "H2", "status": "resolved",
                }))
                result = _run(layer.execute("vault_list_themes", {}))
                assert result["count"] == 2
                slugs = {t["slug"] for t in result["themes"]}
                assert slugs == {"a", "b"}
            finally:
                layer.close()

    def test_filter_by_status(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "a", "hypothesis": "H1",
                }))
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "b", "hypothesis": "H2", "status": "resolved",
                }))
                result = _run(layer.execute("vault_list_themes", {"status": "open"}))
                assert result["count"] == 1
                assert result["themes"][0]["slug"] == "a"
            finally:
                layer.close()


class TestVaultReadTheme:
    def test_reads_existing(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "HR drifts on hot days.",
                }))
                result = _run(layer.execute("vault_read_theme", {"slug": "drift"}))
                assert "content" in result
                assert "HR drifts on hot days." in result["content"]
                assert result["status"] == "open"
            finally:
                layer.close()

    def test_missing_theme_returns_error(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_read_theme", {"slug": "ghost"}))
                assert "error" in result
            finally:
                layer.close()

    def test_obsidian_edit_picked_up_via_mtime(self):
        """Manually rewriting the theme file should surface via vault_read_theme."""
        import os, time
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "Original hypothesis.",
                }))
                path = Path(v) / "themes/drift.md"
                new_body = path.read_text(encoding="utf-8").replace(
                    "Original hypothesis.", "Edited in Obsidian."
                )
                path.write_text(new_body, encoding="utf-8")
                future = time.time_ns() + 10_000_000_000
                os.utime(path, ns=(future, future))

                result = _run(layer.execute("vault_read_theme", {"slug": "drift"}))
                assert "Edited in Obsidian." in result["content"]
            finally:
                layer.close()


class TestVaultCaptureMoment:
    def test_creates_moment_file(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_capture_moment", {
                    "title": "Aha",
                    "body": "Noticed drift on Tuesday.",
                    "date": "2026-04-10",
                }))
                assert result.get("captured") is True
                assert result["filename"].startswith("moments/2026-04-10-")
                assert (Path(v) / result["filename"]).exists()
            finally:
                layer.close()

    def test_requires_title_and_body(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                # ParamValidator raises → router would surface error;
                # but direct layer.execute path uses .get() and will hit
                # renderer validation. Passing empty body triggers ValueError.
                result = _run(layer.execute("vault_capture_moment", {
                    "title": "x", "body": "",
                }))
                assert "error" in result
            finally:
                layer.close()


class TestVaultListMoments:
    def test_lists_moments_with_filters(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_capture_moment", {
                    "title": "M1",
                    "body": "First moment.",
                    "date": "2026-04-05",
                    "linked_themes": ["drift"],
                }))
                _run(layer.execute("vault_capture_moment", {
                    "title": "M2",
                    "body": "Second moment.",
                    "date": "2026-04-10",
                }))

                result = _run(layer.execute("vault_list_moments", {}))
                assert result["count"] == 2

                result = _run(layer.execute("vault_list_moments", {"theme": "drift"}))
                assert result["count"] == 1
                assert result["moments"][0]["title"] == "M1"
            finally:
                layer.close()


class TestVaultCaptureSession:
    def test_writes_summary_themes_and_moments(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_capture_session", {
                    "summary": {
                        "title": "Tuesday session",
                        "body": "Worked on drift hypothesis.",
                        "date": "2026-04-10",
                    },
                    "update_themes": [
                        {"slug": "drift", "hypothesis": "Drift on hot days.",
                         "evidence": "Mile 6, 8bpm up."},
                    ],
                    "new_moments": [
                        {"title": "Sub-moment",
                         "body": "Noticed it again at mile 9.",
                         "date": "2026-04-10"},
                    ],
                }))
                assert result["summary_filename"] is not None
                assert (Path(v) / result["summary_filename"]).exists()
                assert len(result["theme_updates"]) == 1
                assert result["theme_updates"][0]["slug"] == "drift"
                assert len(result["moment_filenames"]) == 1
                assert result["errors"] == []
            finally:
                layer.close()

    def test_missing_summary_returns_error(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_capture_session", {}))
                assert "error" in result
            finally:
                layer.close()

    def test_invalid_theme_update_aggregated_in_errors(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_capture_session", {
                    "summary": {"title": "S", "body": "B"},
                    "update_themes": [{"slug": ""}],  # missing slug
                }))
                # Summary still written; theme error aggregated
                assert result["summary_filename"] is not None
                assert any("missing slug" in e.get("error", "") for e in result["errors"])
            finally:
                layer.close()


class TestVaultRescan:
    def test_rescan_reports_counts(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_rescan", {}))
                for k in ("added", "modified", "deleted", "skipped"):
                    assert k in result
            finally:
                layer.close()


class TestVaultTraverseLinks:
    def test_follows_wikilinks_out(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, filename, _date = _setup_vault(v, d)
            try:
                # Create a theme whose body links back to the run note
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": f"See [[{Path(filename).stem}]] for the canonical case.",
                    "linked_runs": [12345678],
                }))
                # depth=2 so the neighbour is added to `visited` (one hop
                # only writes edges, the next hop materialises nodes).
                result = _run(layer.execute("vault_traverse_links", {
                    "filename": "themes/drift.md",
                    "depth": 2,
                    "direction": "out",
                }))
                assert result["start"] == "themes/drift.md"
                # The outgoing edge must point at the linked run note
                assert any(
                    e["source"] == "themes/drift.md" and e["target"] == filename
                    for e in result["edges"]
                )
                # And depth=2 resolves that target as a node
                assert any(
                    n.get("filename") == filename for n in result["nodes"]
                )
            finally:
                layer.close()

    def test_missing_start_node(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_traverse_links", {
                    "filename": "themes/ghost.md",
                }))
                assert "error" in result
            finally:
                layer.close()


class TestVaultFitnessSummaryExtended:
    def test_includes_open_themes_and_recent_moments(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "Drift on hot days.",
                }))
                _run(layer.execute("vault_capture_moment", {
                    "title": "Aha",
                    "body": "Noticed drift again.",
                    "date": "2026-04-10",
                }))
                result = _run(layer.execute("vault_get_fitness_summary", {}))
                assert "open_themes" in result
                assert "recent_moments" in result
                assert any(t["slug"] == "drift" for t in result["open_themes"])
                assert any(m["title"] == "Aha" for m in result["recent_moments"])
            finally:
                layer.close()


class TestVaultListNotesKindFilter:
    def test_kind_theme_filter(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift", "hypothesis": "H",
                }))
                result = _run(layer.execute("vault_list_notes", {"kind": "theme"}))
                assert result["count"] >= 1
                for note in result["notes"]:
                    assert note["note_type"] == "theme"
            finally:
                layer.close()

    def test_kind_moment_filter(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_capture_moment", {
                    "title": "A", "body": "B", "date": "2026-04-10",
                }))
                result = _run(layer.execute("vault_list_notes", {"kind": "moment"}))
                assert result["count"] >= 1
                for note in result["notes"]:
                    assert note["note_type"] == "moment"
            finally:
                layer.close()

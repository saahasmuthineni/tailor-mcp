"""
Tests for vault/layer.py — VaultLayer tools with real temp FS + SQLite.
"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest


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
    from tailor.framework.vault.layer import VaultLayer
    from tailor.framework.vault.writer import VaultWriter

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
        VaultLayer v6.1 exposes 25 Tier-1 tools: the 22 from v6.0 plus
        three added in v6.1 — failure-mode lifecycle (log + list) and
        the dual-output dashboards refresh tool (ADR 0007).
        """
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            names = {t.name for t in layer.tool_definitions}
            assert len(layer.tool_definitions) == 25
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
                "vault_generate_snapshot",
                "vault_get_snapshot",
                "vault_inbox_add",
                "vault_inbox_list",
                "vault_inbox_drain",
                "vault_correct_evidence",
                "vault_health_check",
                "vault_log_failure_mode",
                "vault_list_failure_modes",
                "vault_refresh_dashboards",
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
        from tailor.framework.interfaces import ChildMCP
        from tailor.framework.vault.layer import VaultLayer
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
        from tailor.framework.vault.layer import VaultLayer
        from tailor.framework.vault.writer import VaultWriter
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


class TestVaultThemeLifecycle:
    def test_reframe_preserves_old_hypothesis(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "HR drifts on hot days.",
                }))
                result = _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "HR drifts on under-fueled runs.",
                }))
                assert result.get("reframed") is True
                content = (Path(v) / "themes/drift.md").read_text(encoding="utf-8")
                assert "HR drifts on hot days." in content
                assert "HR drifts on under-fueled runs." in content
            finally:
                layer.close()

    def test_reframe_writes_prior_framings_section(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "Original framing.",
                }))
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "New framing.",
                }))
                content = (Path(v) / "themes/drift.md").read_text(encoding="utf-8")
                assert "## Prior Framings" in content
                # New hypothesis should be in the Hypothesis section
                hyp_idx = content.find("## Hypothesis")
                prior_idx = content.find("## Prior Framings")
                assert hyp_idx < prior_idx
                # New hypothesis appears before Prior Framings
                new_idx = content.find("New framing.")
                old_idx = content.find("Original framing.")
                assert new_idx < prior_idx < old_idx
            finally:
                layer.close()

    def test_reframe_keeps_status_open(self):
        """status=reframed in params should normalize to 'open' in storage."""
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "Original.",
                }))
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "Different.",
                    "status": "reframed",
                }))
                theme = writer._storage.get_theme("drift")
                assert theme["status"] == "open"
            finally:
                layer.close()

    def test_thinking_entry_appended(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "Original.",
                }))
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "thinking": "Tried to correlate with weather but data is sparse.",
                }))
                content = (Path(v) / "themes/drift.md").read_text(encoding="utf-8")
                assert "### Thinking —" in content
                assert "Tried to correlate with weather" in content
            finally:
                layer.close()

    def test_thinking_entry_distinct_from_evidence(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "H",
                }))
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "evidence": "Real evidence.",
                    "thinking": "Partial thought.",
                }))
                content = (Path(v) / "themes/drift.md").read_text(encoding="utf-8")
                assert "### Evidence —" in content
                assert "### Thinking —" in content
                assert "Real evidence." in content
                assert "Partial thought." in content
            finally:
                layer.close()

    def test_resolution_folds_back_to_linked_run_note(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            # _setup_vault pre-writes a run note for activity 12345678
            layer, writer, run_filename, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "H",
                    "linked_runs": [12345678],
                }))
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "status": "resolved",
                    "resolution": "Confirmed by heat-wave runs.",
                }))
                run_content = (Path(v) / run_filename).read_text(encoding="utf-8")
                assert "> Theme [[drift]] resolved" in run_content
                assert "Confirmed by heat-wave runs." in run_content
            finally:
                layer.close()

    def test_resolution_folds_back_to_linked_theme(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "a", "hypothesis": "H1",
                }))
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "b", "hypothesis": "H2",
                    "linked_themes": ["a"],
                }))
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "b",
                    "status": "resolved",
                    "resolution": "Closed.",
                    "linked_themes": ["a"],
                }))
                a_content = (Path(v) / "themes/a.md").read_text(encoding="utf-8")
                assert "> Theme [[b]] resolved" in a_content
            finally:
                layer.close()

    def test_foldback_skips_missing_linked_notes(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "H",
                    "linked_runs": [99999999],  # does not exist
                }))
                # Should not error
                result = _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "status": "resolved",
                    "resolution": "Done.",
                }))
                assert "error" not in result
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
        import os
        import time
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

    def test_session_capture_with_divergence_in_body(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_capture_session", {
                    "summary": {
                        "title": "Tuesday session",
                        "body": "Worked on drift hypothesis.",
                        "date": "2026-04-10",
                    },
                    "divergence": "Planned to investigate fueling, ended up on HR drift.",
                }))
                assert result["summary_filename"] is not None
                content = (Path(v) / result["summary_filename"]).read_text(encoding="utf-8")
                assert "## Divergence" in content
                assert "Planned to investigate fueling" in content
            finally:
                layer.close()

    def test_session_capture_divergence_in_frontmatter(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_capture_session", {
                    "summary": {
                        "title": "T",
                        "body": "B",
                        "date": "2026-04-10",
                    },
                    "divergence": "Scope drifted.",
                }))
                content = (Path(v) / result["summary_filename"]).read_text(encoding="utf-8")
                assert "divergence:" in content.split("---")[1]  # frontmatter block
            finally:
                layer.close()

    def test_session_capture_without_divergence_unchanged(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_capture_session", {
                    "summary": {
                        "title": "S", "body": "B", "date": "2026-04-10",
                    },
                }))
                content = (Path(v) / result["summary_filename"]).read_text(encoding="utf-8")
                assert "## Divergence" not in content
                assert "divergence:" not in content.split("---")[1]
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


class TestVaultSnapshot:
    def test_generate_snapshot_creates_file(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_generate_snapshot", {}))
                assert result.get("generated") is True
                assert result["filename"] == "snapshot.md"
                assert (Path(v) / "snapshot.md").exists()
            finally:
                layer.close()

    def test_get_snapshot_returns_content(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_generate_snapshot", {}))
                result = _run(layer.execute("vault_get_snapshot", {}))
                assert result.get("snapshot_exists") is True
                assert "Vault Snapshot" in result["content"]
            finally:
                layer.close()

    def test_get_snapshot_fallback_when_no_snapshot(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_get_snapshot", {}))
                assert result.get("snapshot_exists") is False
                assert "fallback" in result
            finally:
                layer.close()

    def test_snapshot_includes_open_themes(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift", "hypothesis": "H",
                }))
                _run(layer.execute("vault_generate_snapshot", {}))
                content = (Path(v) / "snapshot.md").read_text(encoding="utf-8")
                assert "drift" in content
                assert "## Open Themes" in content
            finally:
                layer.close()

    def test_snapshot_includes_recent_moments(self):
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_capture_moment", {
                    "title": "Recent aha",
                    "body": "Noticed drift.",
                    "date": today,
                }))
                _run(layer.execute("vault_generate_snapshot", {}))
                content = (Path(v) / "snapshot.md").read_text(encoding="utf-8")
                assert "Recent aha" in content
            finally:
                layer.close()


class TestVaultHealthCheck:
    def test_health_check_returns_all_fields(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_health_check", {}))
                for key in (
                    "stale_themes",
                    "orphaned_moments",
                    "themes_without_evidence",
                    "inbox_item_count",
                    "total_notes",
                    "total_themes",
                    "total_moments",
                    "themes_by_status",
                ):
                    assert key in result
                assert set(result["themes_by_status"].keys()) == {
                    "open", "resolved", "rejected",
                }
            finally:
                layer.close()

    def test_health_check_identifies_stale_themes(self):
        """Theme with last_updated well in the past should surface as stale."""
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                # Write a theme directly with an old last_updated via writer
                writer.write_theme({
                    "slug": "ancient",
                    "hypothesis": "Old.",
                    "opened": "2020-01-01",
                    "last_updated": "2020-01-01",
                })
                result = _run(layer.execute("vault_health_check", {
                    "stale_threshold_days": 30,
                }))
                assert "ancient" in result["stale_themes"]
            finally:
                layer.close()

    def test_health_check_identifies_orphaned_moments(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                # Moment with no linked_themes → orphaned
                _run(layer.execute("vault_capture_moment", {
                    "title": "Orphan",
                    "body": "Unattached observation.",
                    "date": "2026-04-10",
                }))
                # Moment with linked_themes → not orphaned
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift", "hypothesis": "H",
                }))
                _run(layer.execute("vault_capture_moment", {
                    "title": "Attached",
                    "body": "Linked.",
                    "date": "2026-04-11",
                    "linked_themes": ["drift"],
                }))
                result = _run(layer.execute("vault_health_check", {}))
                assert len(result["orphaned_moments"]) == 1
                assert "orphan" in result["orphaned_moments"][0].lower()
            finally:
                layer.close()

    def test_health_check_counts_inbox_items(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_inbox_add", {"text": "One."}))
                _run(layer.execute("vault_inbox_add", {"text": "Two."}))
                result = _run(layer.execute("vault_health_check", {}))
                assert result["inbox_item_count"] == 2
            finally:
                layer.close()


class TestVaultCorrectEvidence:
    def _seed_theme_with_evidence(self, layer, slug="drift"):
        """Upsert a theme, append one evidence block, return its timestamp."""
        _run(layer.execute("vault_upsert_theme", {
            "slug": slug, "hypothesis": "H",
        }))
        _run(layer.execute("vault_upsert_theme", {
            "slug": slug, "evidence": "Original observation about mile 6.",
        }))
        # Pull the timestamp out of the theme file
        import re as _re
        from pathlib import Path as _Path
        content = (_Path(layer._vault_path) / f"themes/{slug}.md").read_text(encoding="utf-8")
        m = _re.search(r"### Evidence — (\S+)", content)
        return m.group(1)

    def test_correct_evidence_inserts_correction_marker(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                ts = self._seed_theme_with_evidence(layer)
                result = _run(layer.execute("vault_correct_evidence", {
                    "theme_slug": "drift",
                    "evidence_timestamp": ts,
                    "correction": "Mile 6 was actually mile 7.",
                    "corrected_by": "strava_run_report",
                }))
                assert result["corrected"] is True
                content = (Path(v) / "themes/drift.md").read_text(encoding="utf-8")
                assert "[CORRECTED" in content
                assert "Mile 6 was actually mile 7." in content
            finally:
                layer.close()

    def test_correct_evidence_preserves_original(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                ts = self._seed_theme_with_evidence(layer)
                _run(layer.execute("vault_correct_evidence", {
                    "theme_slug": "drift",
                    "evidence_timestamp": ts,
                    "correction": "The mile was different.",
                }))
                content = (Path(v) / "themes/drift.md").read_text(encoding="utf-8")
                # Original evidence still present
                assert "Original observation about mile 6." in content
            finally:
                layer.close()

    def test_correct_evidence_missing_timestamp_returns_error(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift", "hypothesis": "H",
                }))
                result = _run(layer.execute("vault_correct_evidence", {
                    "theme_slug": "drift",
                    "evidence_timestamp": "9999-01-01T00:00:00Z",
                    "correction": "Never happened.",
                }))
                assert "error" in result
            finally:
                layer.close()

    def test_correct_evidence_appends_correction_block(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                ts = self._seed_theme_with_evidence(layer)
                _run(layer.execute("vault_correct_evidence", {
                    "theme_slug": "drift",
                    "evidence_timestamp": ts,
                    "correction": "Swap X for Y.",
                }))
                content = (Path(v) / "themes/drift.md").read_text(encoding="utf-8")
                # A new evidence block tagged [correction] was added
                assert "[correction]" in content
                # There should be at least two `### Evidence` headers now
                assert content.count("### Evidence —") >= 2
            finally:
                layer.close()


class TestVaultInbox:
    def test_inbox_add_creates_file_if_missing(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_inbox_add", {
                    "text": "Odd HR spike around mile 4.",
                    "tags": ["anomaly"],
                }))
                assert result["added"] is True
                assert (Path(v) / "inbox.md").exists()
                content = (Path(v) / "inbox.md").read_text(encoding="utf-8")
                assert "Odd HR spike around mile 4." in content
                assert "#anomaly" in content
            finally:
                layer.close()

    def test_inbox_add_appends_to_existing(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_inbox_add", {"text": "First."}))
                _run(layer.execute("vault_inbox_add", {"text": "Second."}))
                content = (Path(v) / "inbox.md").read_text(encoding="utf-8")
                assert "First." in content
                assert "Second." in content
                assert content.count("- **") == 2
            finally:
                layer.close()

    def test_inbox_list_returns_parsed_items(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_inbox_add", {
                    "text": "Observation.", "tags": ["obs"],
                }))
                result = _run(layer.execute("vault_inbox_list", {}))
                assert result["count"] == 1
                assert result["items"][0]["text"] == "Observation."
                assert result["items"][0]["tags"] == ["obs"]
            finally:
                layer.close()

    def test_inbox_list_empty_file(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_inbox_list", {}))
                assert result["count"] == 0
                assert result["items"] == []
            finally:
                layer.close()

    def test_inbox_drain_moment_creates_note_and_removes(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_inbox_add", {"text": "Interesting observation."}))
                result = _run(layer.execute("vault_inbox_drain", {
                    "items": [{
                        "index": 0, "action": "moment",
                        "title": "Interesting observation",
                        "body": "Interesting observation about HR drift.",
                        "date": "2026-04-10",
                    }],
                }))
                assert result["moments_created"] == 1
                assert result["errors"] == []
                # Verify a moment file exists
                assert any(
                    p.name.startswith("2026-04-10-") for p in (Path(v) / "moments").glob("*.md")
                )
                # Verify inbox empty
                content = (Path(v) / "inbox.md").read_text(encoding="utf-8")
                assert "- **" not in content
            finally:
                layer.close()

    def test_inbox_drain_evidence_appends_and_removes(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift", "hypothesis": "HR drifts.",
                }))
                _run(layer.execute("vault_inbox_add", {"text": "Candidate evidence line."}))
                result = _run(layer.execute("vault_inbox_drain", {
                    "items": [{
                        "index": 0, "action": "evidence",
                        "theme_slug": "drift",
                    }],
                }))
                assert result["evidence_appended"] == 1
                theme_content = (Path(v) / "themes/drift.md").read_text(encoding="utf-8")
                assert "Candidate evidence line." in theme_content
            finally:
                layer.close()

    def test_inbox_drain_discard_removes(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_inbox_add", {"text": "Throwaway."}))
                result = _run(layer.execute("vault_inbox_drain", {
                    "items": [{"index": 0, "action": "discard"}],
                }))
                assert result["discarded"] == 1
                content = (Path(v) / "inbox.md").read_text(encoding="utf-8")
                assert "Throwaway." not in content
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


# ════════════════════════════════════════════════════════════════
# Correction propagation (v6.1)
# ════════════════════════════════════════════════════════════════


class TestVaultCorrectEvidencePropagation:
    """
    The propagate=True path appends a [!warning] callout to every note
    that wikilinks to the corrected theme. Append-only and idempotent
    on (theme_slug, evidence_timestamp).
    """

    @staticmethod
    def _seed_theme_with_evidence(layer):
        _run(layer.execute("vault_upsert_theme", {
            "slug": "drift",
            "hypothesis": "Late-run HR drift looks dehydration-driven.",
            "evidence": "Original observation about mile 6.",
        }))
        # Pull the timestamp for later correction
        import re as _re
        from pathlib import Path as _Path
        content = (_Path(layer._vault_path) / "themes/drift.md").read_text(encoding="utf-8")
        m = _re.search(r"### Evidence — (\S+)", content)
        return m.group(1)

    @staticmethod
    def _seed_moment_referencing(layer, slug="drift"):
        _run(layer.execute("vault_capture_moment", {
            "title": "Mile 6 oddity",
            "body": (
                f"Saw something strange around mile 6. See [[{slug}]] for the "
                "running hypothesis."
            ),
            "linked_themes": [slug],
            "date": "2026-04-10",
        }))

    def test_propagate_appends_callout_to_referencing_note(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                ts = self._seed_theme_with_evidence(layer)
                self._seed_moment_referencing(layer)
                result = _run(layer.execute("vault_correct_evidence", {
                    "theme_slug": "drift",
                    "evidence_timestamp": ts,
                    "correction": "Mile 6 was actually mile 7.",
                    "propagate": True,
                }))
                assert result["corrected"] is True
                assert len(result["propagated_to"]) >= 1
                target = result["propagated_to"][0]
                content = (Path(v) / target).read_text(encoding="utf-8")
                assert "[!warning]" in content
                assert "[CORRECTED-EV " in content
                assert "## Corrections" in content
            finally:
                layer.close()

    def test_propagate_default_false_does_not_touch_referencing(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                ts = self._seed_theme_with_evidence(layer)
                self._seed_moment_referencing(layer)
                result = _run(layer.execute("vault_correct_evidence", {
                    "theme_slug": "drift",
                    "evidence_timestamp": ts,
                    "correction": "Mile 6 was actually mile 7.",
                }))
                assert result["corrected"] is True
                assert result["propagated_to"] == []
                # The moment file is unchanged — no [!warning] block.
                moments = list((Path(v) / "moments").rglob("*.md"))
                for m in moments:
                    assert "[!warning]" not in m.read_text(encoding="utf-8")
            finally:
                layer.close()

    def test_propagate_is_idempotent(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                ts = self._seed_theme_with_evidence(layer)
                self._seed_moment_referencing(layer)
                _run(layer.execute("vault_correct_evidence", {
                    "theme_slug": "drift",
                    "evidence_timestamp": ts,
                    "correction": "First pass.",
                    "propagate": True,
                }))
                # Re-run with the same (slug, timestamp) — must not duplicate.
                _run(layer.execute("vault_correct_evidence", {
                    "theme_slug": "drift",
                    "evidence_timestamp": ts,
                    "correction": "Second pass should not duplicate marker.",
                    "propagate": True,
                }))
                # Find the moment and assert exactly one [CORRECTED-EV <ts>] marker.
                moments = list((Path(v) / "moments").rglob("*.md"))
                assert moments, "expected a moment file to exist"
                content = moments[0].read_text(encoding="utf-8")
                marker = f"[CORRECTED-EV {ts}]"
                assert content.count(marker) == 1
            finally:
                layer.close()

    def test_propagate_with_no_referencing_notes_returns_empty(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                ts = self._seed_theme_with_evidence(layer)
                # No moment seeded — nothing wikilinks to drift.
                result = _run(layer.execute("vault_correct_evidence", {
                    "theme_slug": "drift",
                    "evidence_timestamp": ts,
                    "correction": "Lone correction.",
                    "propagate": True,
                }))
                assert result["corrected"] is True
                assert result["propagated_to"] == []
            finally:
                layer.close()


# ════════════════════════════════════════════════════════════════
# Failure-mode lifecycle (v6.1)
# ════════════════════════════════════════════════════════════════


class TestVaultFailureMode:
    @staticmethod
    def _create_default(layer, **overrides):
        params = {
            "slug": "hr-spike-misread",
            "title": "HR spike misread as fitness signal",
            "symptom": "We flagged a steep HR spike as zone drift.",
            "diagnosis": "Sensor catchup burst from the watch was treated as physiology.",
            "mitigation": "Apply the 30s spike-detection cooldown before zone classification.",
        }
        params.update(overrides)
        return _run(layer.execute("vault_log_failure_mode", params))

    def test_create_writes_file_with_required_sections(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = self._create_default(layer)
                assert result.get("created") is True
                path = Path(v) / "failure-modes" / "hr-spike-misread.md"
                assert path.exists()
                content = path.read_text(encoding="utf-8")
                assert "## Symptom" in content
                assert "## Diagnosis" in content
                assert "## Mitigation" in content
                assert "## Evidence" in content
            finally:
                layer.close()

    def test_create_requires_symptom_diagnosis_mitigation(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_log_failure_mode", {
                    "slug": "incomplete-fm",
                    "title": "missing fields",
                }))
                assert "error" in result
                assert "symptom" in result["error"]
            finally:
                layer.close()

    def test_update_appends_evidence_does_not_overwrite(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                self._create_default(layer, evidence="First observation of the failure.")
                # Update with a new evidence block.
                result = _run(layer.execute("vault_log_failure_mode", {
                    "slug": "hr-spike-misread",
                    "evidence": "Second observation, different week.",
                }))
                assert result.get("updated") is True
                assert result["evidence_appended"] is True
                content = (Path(v) / "failure-modes/hr-spike-misread.md").read_text(encoding="utf-8")
                assert "First observation of the failure." in content
                assert "Second observation, different week." in content
            finally:
                layer.close()

    def test_update_status_to_mitigated(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                self._create_default(layer)
                result = _run(layer.execute("vault_log_failure_mode", {
                    "slug": "hr-spike-misread",
                    "status": "mitigated",
                }))
                assert result.get("updated") is True
                assert result["status"] == "mitigated"
                content = (Path(v) / "failure-modes/hr-spike-misread.md").read_text(encoding="utf-8")
                assert 'status: "mitigated"' in content or "status: mitigated" in content
            finally:
                layer.close()

    def test_invalid_status_returns_error(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = self._create_default(layer, status="bogus")
                assert "error" in result
            finally:
                layer.close()


class TestVaultListFailureModes:
    def test_lists_only_failure_modes(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_log_failure_mode", {
                    "slug": "fm-one",
                    "symptom": "S1", "diagnosis": "D1", "mitigation": "M1",
                }))
                _run(layer.execute("vault_log_failure_mode", {
                    "slug": "fm-two",
                    "symptom": "S2", "diagnosis": "D2", "mitigation": "M2",
                }))
                result = _run(layer.execute("vault_list_failure_modes", {}))
                slugs = {fm["slug"] for fm in result["failure_modes"]}
                assert {"fm-one", "fm-two"}.issubset(slugs)
                # No bodies returned — only summary fields.
                for fm in result["failure_modes"]:
                    assert "symptom" not in fm
                    assert "diagnosis" not in fm
            finally:
                layer.close()

    def test_filter_by_status(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_log_failure_mode", {
                    "slug": "fm-active",
                    "symptom": "S", "diagnosis": "D", "mitigation": "M",
                }))
                _run(layer.execute("vault_log_failure_mode", {
                    "slug": "fm-mitigated",
                    "symptom": "S", "diagnosis": "D", "mitigation": "M",
                    "status": "mitigated",
                }))
                active = _run(layer.execute("vault_list_failure_modes", {
                    "status": "active",
                }))
                slugs = {fm["slug"] for fm in active["failure_modes"]}
                assert "fm-active" in slugs
                assert "fm-mitigated" not in slugs
            finally:
                layer.close()


# ════════════════════════════════════════════════════════════════
# Dashboards refresh (v6.1, ADR 0007)
# ════════════════════════════════════════════════════════════════


class TestVaultRefreshDashboards:
    def test_refresh_writes_three_dashboards(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                result = _run(layer.execute("vault_refresh_dashboards", {}))
                assert result["refreshed"] is True
                names = {dash["name"] for dash in result["dashboards"]}
                assert names == {"open-themes", "active-failure-modes", "recent-moments"}
                for dash in result["dashboards"]:
                    assert (Path(v) / dash["filename"]).exists()
            finally:
                layer.close()

    def test_refresh_includes_dataview_block_by_default(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_refresh_dashboards", {}))
                content = (Path(v) / "dashboards/open-themes.md").read_text(encoding="utf-8")
                assert "```dataview" in content
                # Snapshot table is always present (ADR 0007: source-of-truth view).
                assert "## Snapshot" in content
            finally:
                layer.close()

    def test_refresh_without_dataview_keeps_snapshot(self):
        """
        ADR 0007 invariant: the snapshot is the source-of-truth view
        and must always render, even when the additive Dataview block
        is suppressed.
        """
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_refresh_dashboards", {
                    "with_dataview_blocks": False,
                }))
                content = (Path(v) / "dashboards/open-themes.md").read_text(encoding="utf-8")
                assert "```dataview" not in content
                assert "## Snapshot" in content
            finally:
                layer.close()

    def test_refresh_includes_themes_in_snapshot(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "H",
                    "confidence": "medium",
                }))
                _run(layer.execute("vault_refresh_dashboards", {}))
                content = (Path(v) / "dashboards/open-themes.md").read_text(encoding="utf-8")
                assert "[[drift]]" in content
                assert "medium" in content
            finally:
                layer.close()

    def test_refresh_includes_active_failure_modes_only(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            layer, writer, _, _date = _setup_vault(v, d)
            try:
                _run(layer.execute("vault_log_failure_mode", {
                    "slug": "fm-active",
                    "symptom": "S", "diagnosis": "D", "mitigation": "M",
                }))
                _run(layer.execute("vault_log_failure_mode", {
                    "slug": "fm-mitigated",
                    "symptom": "S", "diagnosis": "D", "mitigation": "M",
                    "status": "mitigated",
                }))
                _run(layer.execute("vault_refresh_dashboards", {}))
                content = (Path(v) / "dashboards/active-failure-modes.md").read_text(encoding="utf-8")
                assert "[[fm-active]]" in content
                assert "[[fm-mitigated]]" not in content
            finally:
                layer.close()

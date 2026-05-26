"""
v7.3.4 regression tests — demo-readiness invariants for the Senefeld /
health-researcher hot path.

Locks the behaviours the v7.3.4 cycle established after the 2026-05-16
first-real-recipient user run and the proposal-mode / mcp-protocol /
cue-card-rehearsal audits that followed. Each test guards a load-bearing
claim of the fitting-room recipient demo; a future refactor that breaks
any of these fails LOUDLY rather than silently regressing the cohort
thesis or the wow-moment surface.

Defect map (each test cites the audit-tier finding it locks):

* D1 — float-seconds timestamp fallback in ``_extract_timestamps`` so
  ``time_to_50pct_drop_s`` actually computes on the bundled HIP Lab
  fixtures (mcp-protocol-auditor verdict; would have rendered the
  cohort thesis null-on-the-wire on the science-person demo).
* D2 — ``group_field`` → ``group_by`` rename on
  ``force_cohort_summary`` + ``emg_cohort_summary`` for API parity
  with ``csv_group_summary`` (cue-card-rehearsal-auditor).
* Fix 1 — bundled ``snapshot.md`` scaffolds + is returned by
  ``vault_get_snapshot`` on the recipient demo path
  (integration-auditor F3 closure).
* Fix 1b — ``_infer_note_type`` maps ``snapshot.md`` → ``"snapshot"``
  so the rescan classifies the bundled seed coherently
  (integration-auditor F1 BLOCKING).
* Fix 2 — ``_handle_fitness_summary`` + ``_build_snapshot_payload`` no
  longer Strava-shape orientation output on a fresh non-running
  deployment (integration-auditor F3 BLOCKING).
* Fix 5 — the bundled S004 moment body carries literal "subject four"
  alongside ``S004`` so ``vault_search_notes`` finds the moment even
  if the snapshot regenerates (cue-card-rehearsal-auditor F7).
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from importlib.resources import files
from pathlib import Path

import pytest

# ──────────────────────────────────────────────────────────────────────
# Bundled-fixture invariants (no scaffold; just read the wheel resources)
# ──────────────────────────────────────────────────────────────────────


class TestBundledFixtureInvariants:
    """Invariants on what ships in the wheel under
    ``src/tailor/_fixtures/hip_lab_demo_realistic/``. These guard
    against silent removal or accidental renaming of the seed assets the
    recipient demo depends on."""

    def test_snapshot_md_is_bundled_in_wheel(self) -> None:
        """Fix 1: the seeded ``snapshot.md`` must ship inside the wheel
        under the HIP Lab realistic fixture root, so ``tailor
        fitting-room`` can copy it into the recipient's scaffolded
        target."""
        bundle_root = files("tailor._fixtures.hip_lab_demo_realistic")
        snapshot = bundle_root / "vault" / "snapshot.md"
        assert snapshot.is_file(), (
            "Expected bundled snapshot.md at "
            "_fixtures/hip_lab_demo_realistic/vault/snapshot.md — the "
            "v7.3.4 seed orientation document. If this is missing, the "
            "first-prompt orientation path regresses to the empty-vault "
            "fallback and the wow moment becomes unreachable from natural "
            "prose."
        )

    def test_snapshot_md_names_subject_four_in_literal_english(self) -> None:
        """Fix 1 + Fix 5: the bundled snapshot.md must contain the
        literal phrase 'subject four' (lowercase) so
        ``vault_search_notes(query='subject four')`` finds it. Without
        this, the recipient's natural-language prompt fails on the
        wow-moment surface even though the moment exists."""
        bundle_root = files("tailor._fixtures.hip_lab_demo_realistic")
        snapshot = bundle_root / "vault" / "snapshot.md"
        content = snapshot.read_text(encoding="utf-8")
        assert "subject four" in content.lower(), (
            "snapshot.md must include the literal phrase 'subject four' "
            "for the demo-recipient prompt path. Found content head: "
            f"{content[:200]!r}"
        )

    def test_s004_moment_body_carries_subject_four_phrasing(self) -> None:
        """Fix 5: the bundled S004 moment body must carry literal
        'subject four' so ``vault_search_notes`` finds the moment
        directly (not only via the snapshot). Durable across snapshot
        regenerate."""
        bundle_root = files("tailor._fixtures.hip_lab_demo_realistic")
        moment = bundle_root / "vault" / "moments" / (
            "2026-04-20-s004-emg-force-decoupling-suspected.md"
        )
        content = moment.read_text(encoding="utf-8")
        assert "subject four" in content.lower(), (
            "S004 moment body must include 'subject four' (lowercase) so "
            "the durable wow-moment search survives a snapshot "
            "regenerate. Without this, the snapshot is the only "
            "carrier and gets erased the first time anyone calls "
            "vault_generate_snapshot."
        )

    def test_snapshot_md_has_compatible_frontmatter(self) -> None:
        """Fix 1: the seed must declare ``domain: vault`` and
        ``note_type: snapshot`` in frontmatter so the rescan + parser
        classify it coherently."""
        bundle_root = files("tailor._fixtures.hip_lab_demo_realistic")
        snapshot = bundle_root / "vault" / "snapshot.md"
        content = snapshot.read_text(encoding="utf-8")
        assert "domain: vault" in content
        assert "note_type: snapshot" in content
        # The seed is cross-subject — must NOT declare entity_id in
        # frontmatter (integration-auditor C3 conflict guard).
        assert "entity_id" not in content.split("---", 2)[1], (
            "snapshot.md must not declare entity_id in frontmatter — "
            "the snapshot is cross-subject by construction (ADR 0009 "
            "+ integration-auditor C3)."
        )


# ──────────────────────────────────────────────────────────────────────
# Rescan classifier (Fix 1b)
# ──────────────────────────────────────────────────────────────────────


class TestRescanClassifierForSnapshot:
    """The rescan's ``_infer_note_type`` must map a bare ``snapshot.md``
    to ``note_type='snapshot'`` so the seed indexes coherently and any
    test that asserts ``kind='snapshot'`` agrees with the indexer."""

    def test_snapshot_md_infers_note_type_snapshot(self) -> None:
        from tailor.framework.vault.rescan import _infer_note_type
        assert _infer_note_type("snapshot.md") == "snapshot", (
            "rescan._infer_note_type must classify bare 'snapshot.md' "
            "as 'snapshot'. v7.3.4 / Fix 1b / integration-auditor F1 "
            "BLOCKING."
        )

    def test_other_paths_still_classify_correctly(self) -> None:
        from tailor.framework.vault.rescan import _infer_note_type
        # Sanity-check that the new branch did not break prior mappings.
        assert _infer_note_type("themes/foo.md") == "theme"
        assert _infer_note_type("moments/bar.md") == "moment"
        assert _infer_note_type("failure-modes/baz.md") == "failure_mode"
        assert _infer_note_type("dashboards/qux.md") == "dashboard"
        assert _infer_note_type("running/2026-04-20-act-1.md") == "run_report"
        assert _infer_note_type("running/trends/weekly.md") == "trend_report"
        assert _infer_note_type("orphan.md") == "unknown"


# ──────────────────────────────────────────────────────────────────────
# Fitting-room end-to-end scaffold (Fix 1 + 1b + 5 composing on disk)
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def scaffolded_target(tmp_path: Path) -> Path:
    """Run ``tailor fitting-room`` end-to-end into a tempdir. Returns
    the target dir. Skips Claude Desktop registration. Captures the
    real scaffold-and-index path so downstream assertions exercise the
    same code a Windows recipient hits."""
    from tailor.fitting_room import main as fitting_room_main
    target = tmp_path / "fr"
    rc = fitting_room_main([
        "--variant=hip-lab",
        "--target", str(target),
        "--no-claude-desktop",
    ])
    assert rc == 0, f"fitting-room scaffold returned {rc}"
    return target


class TestFittingRoomScaffoldsSnapshot:
    """End-to-end: a fresh ``tailor fitting-room`` scaffold lands the
    bundled snapshot.md on disk AND indexes it as ``note_type=snapshot``
    in ``vault.db``."""

    def test_snapshot_md_lands_in_scaffolded_vault(
        self, scaffolded_target: Path,
    ) -> None:
        snapshot = scaffolded_target / "vault" / "snapshot.md"
        assert snapshot.is_file(), (
            f"Expected scaffolded snapshot.md at {snapshot}; not found. "
            "Either fitting-room is not copying the vault/ subtree, or "
            "the bundled fixture is missing."
        )
        content = snapshot.read_text(encoding="utf-8")
        assert "subject four" in content.lower()

    def test_snapshot_md_indexed_with_snapshot_note_type(
        self, scaffolded_target: Path,
    ) -> None:
        db = scaffolded_target / "data" / "vault.db"
        assert db.is_file(), f"vault.db not found at {db}"
        conn = sqlite3.connect(db)
        try:
            row = conn.execute(
                "SELECT filename, note_type, domain FROM vault_notes "
                "WHERE filename = 'snapshot.md'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, (
            "snapshot.md was copied to disk but never indexed in "
            "vault.db. Either fitting-room is not running rescan_vault, "
            "or rescan is excluding the snapshot.md path."
        )
        filename, note_type, domain = row
        assert note_type == "snapshot", (
            f"snapshot.md indexed with note_type={note_type!r}; expected "
            "'snapshot'. v7.3.4 / Fix 1b."
        )
        assert domain == "vault"


# ──────────────────────────────────────────────────────────────────────
# D1 — float-seconds timestamp fallback on bundled HIP Lab fixtures
# ──────────────────────────────────────────────────────────────────────


class TestD1FloatSecondsTimestampFallback:
    """The bundled HIP Lab fixtures use ``t_s`` float-second offsets.
    Before v7.3.4 ``_extract_timestamps`` only recognised ISO datetime
    strings and silently returned None on these fixtures, which made
    every time-based metric (``time_to_50pct_drop_s``, ``duration_s``,
    ``decline_rate_per_min``) silently null on the cohort thesis hot
    path — the headline analytical claim for the Senefeld audience."""

    def test_force_cohort_time_to_50pct_drop_is_non_null(
        self, scaffolded_target: Path,
    ) -> None:
        from tailor.children.force_csv.child import ForceCsvChild

        os.environ["TAILOR_CONFIG_DIR"] = str(scaffolded_target)
        os.environ["TAILOR_DATA_DIR"] = str(scaffolded_target / "data")
        child = ForceCsvChild(
            config_dir=scaffolded_target,
            data_dir=scaffolded_target / "data",
        )

        async def run() -> dict:
            return await child.execute(
                "force_cohort_summary",
                {
                    "group_by": "sex",
                    "value_column": "force",
                    "metric": "time_to_50pct_drop_s",
                },
            )

        result = asyncio.run(run())
        assert "error" not in result, f"cohort call errored: {result}"
        groups = result.get("groups", {})
        assert set(groups.keys()) >= {"F", "M"}, (
            f"Expected M + F groups; got {sorted(groups.keys())}"
        )
        for sex, stats in groups.items():
            assert stats.get("n") == 8, (
                f"Expected n=8 per sex group; group {sex!r} got "
                f"{stats.get('n')} (fixtures may have drifted)"
            )
            # The pre-v7.3.4 defect: mean was None for every group on
            # the bundled fixtures because timestamps weren't extracted.
            assert stats.get("mean") is not None, (
                f"time_to_50pct_drop_s mean is None for group {sex!r}; "
                "D1 (float-seconds fallback in _extract_timestamps) "
                "regressed."
            )
            assert 0.0 < stats["mean"] < 60.0, (
                f"time_to_50pct_drop_s for group {sex!r} = "
                f"{stats['mean']}, expected a small positive value in "
                "seconds"
            )

    def test_force_summary_s004_returns_all_time_based_fields(
        self, scaffolded_target: Path,
    ) -> None:
        """Per-subject S004 fatigue diagnostic must populate every
        time-based field (D1 + D1-companion decline_pct handler key)."""
        from tailor.children.force_csv.child import ForceCsvChild

        os.environ["TAILOR_CONFIG_DIR"] = str(scaffolded_target)
        os.environ["TAILOR_DATA_DIR"] = str(scaffolded_target / "data")
        child = ForceCsvChild(
            config_dir=scaffolded_target,
            data_dir=scaffolded_target / "data",
        )

        async def run() -> dict:
            return await child.execute(
                "force_summary", {"file_id": "S004_force.csv"},
            )

        result = asyncio.run(run())
        assert "error" not in result, f"force_summary errored: {result}"
        for field in (
            "peak",
            "decline_pct",
            "decline_rate_per_min",
            "time_to_50pct_drop_s",
            "duration_s",
        ):
            assert result.get(field) is not None, (
                f"force_summary on S004 returned None for {field!r}. "
                "Composite v7.3.4 defect class — D1 (timestamps) "
                "+ D1-companion (decline_pct handler-key mismatch)."
            )

    def test_iso_datetime_success_path_still_works(self, tmp_path: Path) -> None:
        """Coverage-criticality regression guard: the v7.3.4 float-seconds
        fallback added an early-exit on the ISO-success path
        (``for/else: return parsed``). The bundled HIP Lab tests exercise
        only the float-seconds branch. A deployment that uses ISO-format
        timestamps (the original ``csv_dir`` shape, the Strava cache
        notes, any real biomedical export with a real datetime column)
        must still hit the ISO branch cleanly. Without this test the
        ISO-success arm could silently regress on a future
        ``parse_timestamp`` signature change."""
        import csv
        # Build a single ISO-timestamped force CSV in a tempdir.
        force_dir = tmp_path / "force"
        force_dir.mkdir()
        csv_path = force_dir / "S999_iso.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["t_iso", "force_N"])
            for i in range(10):
                ts = f"2026-04-20T10:00:{i:02d}"
                writer.writerow([ts, 100.0 - i * 5])
        (force_dir / "metadata.json").write_text(
            '{"S999_iso.csv": {"sex": "F", "group": "trained"}}',
            encoding="utf-8",
        )
        config_dir = tmp_path / "cfg"
        config_dir.mkdir()
        (config_dir / "user_config.json").write_text(
            '{"force_csv": {"path": "' + str(force_dir).replace("\\", "/")
            + '", "timestamp_column": "t_iso", '
            '"value_columns": {"force": "force_N"}}}',
            encoding="utf-8",
        )
        os.environ["TAILOR_CONFIG_DIR"] = str(config_dir)
        os.environ["TAILOR_DATA_DIR"] = str(tmp_path / "data")
        from tailor.children.force_csv.child import ForceCsvChild
        child = ForceCsvChild(
            config_dir=config_dir, data_dir=tmp_path / "data",
        )

        async def run() -> dict:
            return await child.execute(
                "force_summary", {"file_id": "S999_iso.csv"},
            )

        result = asyncio.run(run())
        assert "error" not in result, (
            f"force_summary on ISO-timestamped fixture errored: {result}. "
            "The v7.3.4 _extract_timestamps refactor must still hit the "
            "ISO-success path cleanly when timestamps parse as datetime."
        )
        # The ISO branch must produce non-null time-based metrics — exactly
        # the same surface the float-seconds branch produces. If only the
        # float-seconds branch worked we'd be ship-blocking real
        # deployments that use ISO timestamps.
        assert result.get("duration_s") is not None, (
            "ISO-success path must populate duration_s. Coverage "
            "regression on _extract_timestamps' for/else: return parsed "
            "arm regressed."
        )


# ──────────────────────────────────────────────────────────────────────
# D2 — parameter rename group_field → group_by
# ──────────────────────────────────────────────────────────────────────


class TestD2GroupByParameterRename:
    """Force + EMG cohort tools must accept ``group_by`` (matching
    csv_group_summary). The old ``group_field`` name must not appear
    in any ToolDefinition or param_schema — leaving it would re-create
    the API-parity drift the cue-card-rehearsal-auditor flagged."""

    def test_force_cohort_summary_declares_group_by_not_group_field(
        self,
    ) -> None:
        import os

        from tailor.children.force_csv.child import ForceCsvChild
        td = next(
            t for t in
            ForceCsvChild.__new__(ForceCsvChild).__class__.__dict__[
                "tool_definitions"
            ].fget(
                ForceCsvChild(
                    config_dir=Path(os.environ.get("TEMP", ".")),
                    data_dir=Path(os.environ.get("TEMP", ".")),
                )
            )
            if t.name == "force_cohort_summary"
        )
        assert "group_by" in td.params, (
            "force_cohort_summary must declare 'group_by' "
            "(matching csv_group_summary). v7.3.4 / D2."
        )
        assert "group_field" not in td.params, (
            "force_cohort_summary must not declare legacy 'group_field' "
            "— would re-create API-parity drift."
        )

    def test_emg_cohort_summary_declares_group_by_not_group_field(
        self,
    ) -> None:
        import os

        from tailor.children.emg_csv.child import EmgCsvChild
        td = next(
            t for t in
            EmgCsvChild(
                config_dir=Path(os.environ.get("TEMP", ".")),
                data_dir=Path(os.environ.get("TEMP", ".")),
            ).tool_definitions
            if t.name == "emg_cohort_summary"
        )
        assert "group_by" in td.params
        assert "group_field" not in td.params


# ──────────────────────────────────────────────────────────────────────
# Fix 2 — _handle_fitness_summary no longer Strava-shapes its fallback
# ──────────────────────────────────────────────────────────────────────


class TestFix2FitnessSummaryNoLongerStravaShapes:
    """When no running child is registered (HIP Lab demo case),
    _handle_fitness_summary's empty-notes fallback must NOT emit the
    'call strava_sync' remediation. The hint misleads a recipient on
    a non-running deployment into thinking the framework expects Strava
    data."""

    def test_fallback_remediation_does_not_mention_strava_sync(
        self, scaffolded_target: Path,
    ) -> None:
        from tailor.framework.vault.layer import VaultLayer
        from tailor.framework.vault.writer import VaultWriter

        os.environ["TAILOR_CONFIG_DIR"] = str(scaffolded_target)
        os.environ["TAILOR_DATA_DIR"] = str(scaffolded_target / "data")
        writer = VaultWriter(
            vault_path=scaffolded_target / "vault",
            data_dir=scaffolded_target / "data",
            vaultable_tools=set(),
        )
        layer = VaultLayer(
            vault_path=scaffolded_target / "vault",
            vault_writer=writer,
            backfill_config={
                "list_tool": "csv_list_files",
                "report_tool": "csv_summary_report",
            },
        )

        async def run() -> dict:
            return await layer.execute("vault_get_fitness_summary", {})

        result = asyncio.run(run())
        # On a HIP Lab demo scaffold there is no domain="running" data;
        # the fallback path must surface non-Strava remediation.
        note = result.get("note", "")
        assert "strava_sync" not in note, (
            "_handle_fitness_summary fallback emitted 'strava_sync' on "
            "a non-running deployment. v7.3.4 / Fix 2 / integration-"
            f"auditor F3 BLOCKING regressed. note: {note!r}"
        )

    def test_legacy_strava_branch_still_works_on_running_deployment(
        self, tmp_path: Path,
    ) -> None:
        """Coverage-criticality regression guard: the v7.3.4 rewrite of
        ``_handle_fitness_summary``'s empty-notes fallback added three
        branches — ``total_running > 0`` (legacy Strava path),
        ``non_running > 0`` (HIP Lab path), ``total_all == 0`` (empty
        vault). The HIP Lab branch is covered by the test above; this
        test covers the legacy Strava branch so a future regression on
        ``count_notes(domain='running')`` cannot silently break the
        Strava-deployment remediation surface."""
        from tailor.framework.vault.layer import VaultLayer
        from tailor.framework.vault.writer import VaultWriter

        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        (vault_path / "running").mkdir()
        # Seed an out-of-window run_report note so the date filter in
        # _handle_fitness_summary returns 0 notes for the "specified
        # period" but count_notes(domain='running') still sees > 0.
        old_run = vault_path / "running" / "2024-01-15-old-run.md"
        old_run.write_text(
            "---\n"
            "domain: running\n"
            "note_type: run_report\n"
            "date: \"2024-01-15\"\n"
            "week: \"2024-W03\"\n"
            "distance_miles: 5.0\n"
            "duration_min: 45\n"
            "avg_hr: 145\n"
            "tags: [run_report]\n"
            "---\n\n# Old run\n\nSeed for coverage on the legacy "
            "Strava branch.\n",
            encoding="utf-8",
        )

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        os.environ["TAILOR_CONFIG_DIR"] = str(tmp_path)
        os.environ["TAILOR_DATA_DIR"] = str(data_dir)
        writer = VaultWriter(
            vault_path=vault_path,
            data_dir=data_dir,
            vaultable_tools=set(),
        )
        layer = VaultLayer(
            vault_path=vault_path,
            vault_writer=writer,
            backfill_config={
                "list_tool": "strava_list_runs",
                "report_tool": "strava_run_report",
            },
        )
        from tailor.framework.vault.rescan import rescan_vault
        rescan_vault(vault_path=vault_path, storage=layer._storage)

        async def run() -> dict:
            return await layer.execute(
                "vault_get_fitness_summary", {"weeks_back": 2},
            )

        result = asyncio.run(run())
        # Legacy Strava deployment with old runs falling outside the
        # date window: total_running > 0 branch fires; remediation may
        # legitimately reference Strava sync (this branch is for actual
        # Strava deployments and the prose is correct there).
        summary = result.get("summary", "")
        assert "No run notes found in the specified period" in summary, (
            f"Expected legacy Strava-branch summary; got {summary!r}. "
            "Coverage on _handle_fitness_summary's total_running > 0 "
            "branch regressed."
        )


# ──────────────────────────────────────────────────────────────────────
# Fix 2 — snapshot renderer drops Weekly Summary when no run data
# ──────────────────────────────────────────────────────────────────────


class TestSnapshotRendererDropsEmptyWeeklySummary:
    """The renderer used to always print '## Weekly Summary (last 4
    weeks)' followed by '*(No recent run data.)*' on a HIP Lab demo
    deployment — Strava-shaping the snapshot of a non-running vault.
    v7.3.4 / Fix 2 drops the whole section when weekly_summary is
    empty."""

    def test_empty_weekly_summary_drops_section_header(self) -> None:
        from tailor.framework.vault.renderer import render_snapshot_note

        snapshot = {
            "open_themes": [],
            "recent_moments": [],
            "weekly_summary": [],
            "vault_health": {
                "notes_indexed": 2,
                "themes_open": 0,
                "themes_resolved": 0,
                "moments": 1,
                "stale_themes": [],
                "inbox_items": 0,
            },
            "warnings": [],
            "written_by": "test",
        }
        _filename, body = render_snapshot_note(snapshot)
        assert "Weekly Summary" not in body, (
            "Empty weekly_summary must drop the section header entirely "
            "on a non-running deployment. v7.3.4 / Fix 2 regressed."
        )
        assert "No recent run data" not in body
        # Negative-shape guard: render with run data still produces the
        # section so we don't break running deployments.
        snapshot["weekly_summary"] = [
            {"week": "2026-W18", "runs": 3, "total_miles": 12.5, "avg_hr": 142},
        ]
        _filename, body = render_snapshot_note(snapshot)
        assert "Weekly Summary" in body, (
            "Non-empty weekly_summary must still emit the section — "
            "the v7.3.4 fix must not break Strava-deployment "
            "regenerator output."
        )


# ──────────────────────────────────────────────────────────────────────
# End-to-end demo prompt path
# ──────────────────────────────────────────────────────────────────────


class TestDemoPromptPathEndToEnd:
    """The fitting-room recipient asks: *'what about subject four?'*
    The natural-language prompt path must lead to a vault tool call
    that returns a non-empty result. v7.3.4 closure: this works
    because (a) snapshot.md names 'subject four' in literal English
    and (b) the S004 moment body carries 'subject four' too."""

    def test_vault_search_subject_four_returns_at_least_one_hit(
        self, scaffolded_target: Path,
    ) -> None:
        from tailor.framework.vault.layer import VaultLayer
        from tailor.framework.vault.writer import VaultWriter

        os.environ["TAILOR_CONFIG_DIR"] = str(scaffolded_target)
        os.environ["TAILOR_DATA_DIR"] = str(scaffolded_target / "data")
        writer = VaultWriter(
            vault_path=scaffolded_target / "vault",
            data_dir=scaffolded_target / "data",
            vaultable_tools=set(),
        )
        layer = VaultLayer(
            vault_path=scaffolded_target / "vault",
            vault_writer=writer,
            backfill_config={
                "list_tool": "csv_list_files",
                "report_tool": "csv_summary_report",
            },
        )

        async def run(q: str) -> dict:
            return await layer.execute("vault_search_notes", {"query": q})

        # Both phrasings must work — neither should rely on the LLM
        # making the 'subject four' → 'S004' translation.
        for query in ("subject four", "S004"):
            r = asyncio.run(run(query))
            count = r.get("count", 0)
            assert count >= 1, (
                f"vault_search_notes(query={query!r}) returned "
                f"count={count} on a fresh fitting-room scaffold. "
                "The wow-moment surface is unreachable from the "
                "recipient's natural prompt. v7.3.4 / Fix 1 + Fix 5 "
                "regressed."
            )

    def test_vault_get_snapshot_returns_seeded_content(
        self, scaffolded_target: Path,
    ) -> None:
        from tailor.framework.vault.layer import VaultLayer
        from tailor.framework.vault.writer import VaultWriter

        os.environ["TAILOR_CONFIG_DIR"] = str(scaffolded_target)
        os.environ["TAILOR_DATA_DIR"] = str(scaffolded_target / "data")
        writer = VaultWriter(
            vault_path=scaffolded_target / "vault",
            data_dir=scaffolded_target / "data",
            vaultable_tools=set(),
        )
        layer = VaultLayer(
            vault_path=scaffolded_target / "vault",
            vault_writer=writer,
            backfill_config={
                "list_tool": "csv_list_files",
                "report_tool": "csv_summary_report",
            },
        )

        async def run() -> dict:
            return await layer.execute("vault_get_snapshot", {})

        snap = asyncio.run(run())
        assert snap.get("snapshot_exists") is True, (
            "vault_get_snapshot must report snapshot_exists=True on a "
            "fresh fitting-room scaffold — the seed must be present "
            "and the existence check must find it."
        )
        content = snap.get("content", "")
        assert "subject four" in content.lower(), (
            "vault_get_snapshot returned content that does not contain "
            "'subject four'. The seed orientation document is the "
            "load-bearing payload for the wow-moment recipient prompt."
        )


# ──────────────────────────────────────────────────────────────────────
# Fitting-room banner reshape — science-shaped first prompts
# ──────────────────────────────────────────────────────────────────────


class TestFittingRoomBannerNextStepIsScienceShaped:
    """The v7.3.4 banner reshape replaced the developer-shaped prompt
    'List the available Tailor tools.' with science-shaped first
    prompts that surface the cohort thesis + the wow moment + the
    audit-log inspection surface. Lock this; a future refactor that
    reverts to the developer prompt regresses the recipient's first
    impression of what Tailor is for."""

    def test_banner_surfaces_cohort_thesis_prompt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
    ) -> None:
        # The science-shaped "next step" prompts only render on the
        # claude_desktop_present + written branch of the banner — the
        # branch a real recipient hits. Monkeypatch the detection +
        # config-paths helpers to put the banner on that branch.
        fake_config = tmp_path / "claude_desktop_config.json"
        monkeypatch.setattr(
            "tailor.fitting_room._claude_desktop_config_paths",
            lambda: [fake_config],
        )
        monkeypatch.setattr(
            "tailor.fitting_room._detect_claude_desktop_presence",
            lambda: True,
        )
        from tailor.fitting_room import main as fitting_room_main
        target2 = tmp_path / "fr2"
        capsys.readouterr()
        rc = fitting_room_main([
            "--variant=hip-lab",
            "--target", str(target2),
        ])
        assert rc == 0
        out = capsys.readouterr().out
        # The three science-shaped prompts that anchor the demo:
        assert "male versus female force decline" in out.lower(), (
            "Banner must surface the cohort thesis prompt. v7.3.4 / "
            "Fix 7+8 regressed."
        )
        assert "subject four" in out.lower(), (
            "Banner must surface the wow-moment prompt. v7.3.4 / "
            "Fix 7+8 regressed."
        )
        assert "recent moments in the vault" in out.lower(), (
            "Banner must surface the durable-memory / vault-list-moments "
            "prompt. v7.3.4 / Fix 9 (post-red-team-objection-medium "
            "rewording — was 'show me the audit log' but no MCP tool "
            "queries the audit log; rewording points at a tool that "
            "actually exists). Regressed."
        )
        # The banner must NOT promise audit-log inspection from inside
        # Claude Desktop — v7.3.4 has no MCP-callable audit-query tool;
        # promising one is the aspirational-framing trap red-team
        # caught. v7.4.0 + ADR 0038 may add such a tool.
        assert "audit log" not in out.lower(), (
            "Banner reintroduced an audit-log prompt with no callable "
            "MCP surface. v7.3.4 / red-team-reviewer OBJECTION medium "
            "regressed. If v7.4.0 adds an audit-query tool, update "
            "this test invariant; do not silently re-add the prompt."
        )
        # And it must NOT surface the pre-v7.3.4 developer-shaped prompt
        # as the canonical next step.
        assert "list the available Tailor tools" not in out.lower(), (
            "Banner reverted to the pre-v7.3.4 developer-shaped prompt. "
            "The recipient first-impression surface regressed."
        )
        # The Option B tier-escalation prompt — surfaces the AI-economics
        # claim (ADR 0029) by demonstrating the cost-gate firing at this
        # deployment's 15,000-token threshold. Backed by wire verification
        # (the gate fires on bundled HIP Lab Tier-3 raw-window calls;
        # estimate ~24k tokens vs threshold 15k). v7.3.4 / Option B.
        assert "tier levels" in out.lower(), (
            "Banner must surface the tier-escalation prompt that "
            "demonstrates the AI-economics lever (ADR 0029). v7.3.4 / "
            "Option B regressed. If wire verification shows the cost "
            "gate no longer fires on bundled fixtures (e.g. cost_threshold "
            "raised, fixture size shrunk), remove this prompt rather "
            "than leaving an aspirational claim — that's the red-team "
            "OBJECTION class."
        )


class TestB2CostThresholdConfigurable:
    """Option B (v7.3.4): cost_threshold becomes operator-configurable
    from user_config.json so the fitting-room scaffold can set a
    threshold the bundled HIP Lab Tier-3 paths actually trip — making
    the AI-economics claim (ADR 0029) empirically demonstrable rather
    than aspirational. Default 35,000 preserves pre-v7.3.4 behavior on
    deployments that don't set the key."""

    def test_fitting_room_scaffold_sets_low_cost_threshold(
        self, scaffolded_target: Path,
    ) -> None:
        """The bundled fitting-room scaffold must declare cost_threshold
        below 24,000 (the empirical Tier-3 force_raw_window estimate per
        the v7.3.4 mcp-protocol-auditor wire audit) so the cost gate
        fires when a recipient probes the AI-economics tier-escalation
        prompt. If this regresses (e.g. someone restores the default
        35,000 in fitting_room._hip_lab_user_config), the Option B
        demo silently no-ops — exactly the red-team OBJECTION class."""
        ucfg_path = scaffolded_target / "user_config.json"
        ucfg = json.loads(ucfg_path.read_text(encoding="utf-8"))
        threshold = ucfg.get("cost_threshold")
        assert threshold is not None, (
            "fitting-room scaffold's user_config.json must declare "
            "cost_threshold — without it the framework default "
            "(35,000) kicks in and the cost gate doesn't fire on "
            "bundled HIP Lab Tier-3 paths. v7.3.4 / Option B."
        )
        assert isinstance(threshold, int), (
            f"cost_threshold must be an int (int-coerced by __main__); "
            f"got {type(threshold).__name__}"
        )
        assert threshold < 24_000, (
            f"cost_threshold={threshold} is at or above the empirical "
            "Tier-3 force_raw_window estimate (~24,000 tokens for one "
            "60s S004 trace per the v7.3.4 wire audit). Cost gate "
            "will not fire on the bundled scaffold — Option B regressed."
        )

    def test_main_reads_cost_threshold_with_default(self) -> None:
        """The user_config.json cost_threshold key must propagate to
        RouterMCP construction. The framework default (35,000) must
        still apply when the key is absent — backwards-compatible."""
        # Verify the contract by inspecting the source-file structure:
        # __main__.cmd_serve must (1) read _ucfg.get("cost_threshold",
        # 35_000) before instantiating RouterMCP, (2) pass the result
        # as RouterMCP(cost_threshold=...) rather than the hardcoded
        # literal that was there pre-v7.3.4.
        import inspect

        from tailor import __main__
        source = inspect.getsource(__main__.cmd_serve)
        assert '_ucfg.get("cost_threshold", 35_000)' in source, (
            "__main__.cmd_serve must read cost_threshold from user_"
            "config.json with default 35_000. v7.3.4 / Option B. "
            "If the default changes, update this test invariant; do "
            "not silently rewire to a hardcoded literal."
        )
        assert "cost_threshold=_cost_threshold" in source, (
            "RouterMCP must be constructed with the user-config-derived "
            "cost_threshold value, not a hardcoded literal."
        )

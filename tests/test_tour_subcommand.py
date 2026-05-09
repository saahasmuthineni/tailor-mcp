"""
Tests for the ``tailor tour`` subcommand.

Per ADR 0024 the tour scaffolds a live-audience walkthrough from
bundled fixtures. The load-bearing claims this suite enforces:

- Bundled fixtures actually ship in the package (sanity check on
  ``pyproject.toml`` package-data globs — without these, the wheel
  is empty of fixtures and ``tour`` errors at scaffold time).
- The scaffolder writes a ``user_config.json`` whose absolute paths
  resolve to the target dir (force_csv / emg_csv child registration
  depends on this exact shape).
- The vault index contains the S004 seed moment after scaffold (the
  cross-session-memory wow moment depends on it).
- Re-running is idempotent (recipients re-run after Claude Desktop
  drift; this must not fail).
- The Claude Desktop entry bakes ``TAILOR_CONFIG_DIR`` and
  ``TAILOR_DATA_DIR`` into the ``env`` block — this closes
  audit blocker #1 from the ADR 0024 pre-implementation pass
  (recipients never type an env var by hand).
- Pre-existing sibling MCP servers in Claude Desktop's config
  survive the merge (deep-merge invariant inherited from
  ``pilot.py``'s v6.2.1 hardening).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tailor.tour import (
    DEFAULT_VARIANT,
    VARIANTS,
    _resolve_target,
    main,
)

# ──────────────────────────────────────────────────────────────────────
# Sanity: bundled fixtures actually ship.
# ──────────────────────────────────────────────────────────────────────


class TestBundledFixtures:
    """If these fail, ``pyproject.toml`` package-data globs are wrong."""

    def test_force_csvs_present(self):
        from importlib.resources import files
        pkg = files("tailor._fixtures").joinpath(
            "hip_lab_demo_realistic", "force",
        )
        names = sorted(c.name for c in pkg.iterdir() if c.name.endswith(".csv"))
        assert len(names) == 16
        assert "S001_force.csv" in names
        assert "S004_force.csv" in names
        assert "S016_force.csv" in names

    def test_emg_csvs_present(self):
        from importlib.resources import files
        pkg = files("tailor._fixtures").joinpath(
            "hip_lab_demo_realistic", "emg",
        )
        names = sorted(c.name for c in pkg.iterdir() if c.name.endswith(".csv"))
        assert len(names) == 16

    def test_mrs_csvs_present(self):
        from importlib.resources import files
        pkg = files("tailor._fixtures").joinpath(
            "hip_lab_demo_realistic", "mrs",
        )
        names = sorted(c.name for c in pkg.iterdir() if c.name.endswith(".csv"))
        assert len(names) == 16

    def test_metadata_json_sidecars_present(self):
        from importlib.resources import files
        for sub in ("force", "emg", "mrs"):
            pkg = files("tailor._fixtures").joinpath(
                "hip_lab_demo_realistic", sub,
            )
            mj = pkg.joinpath("metadata.json")
            assert mj.is_file(), f"metadata.json missing in {sub}/"

    def test_seed_vault_moment_present(self):
        from importlib.resources import files
        moment = files("tailor._fixtures").joinpath(
            "hip_lab_demo_realistic", "vault", "moments",
            "2026-04-20-s004-emg-force-decoupling-suspected.md",
        )
        assert moment.is_file()


# ──────────────────────────────────────────────────────────────────────
# End-to-end scaffold into a temp dir.
# ──────────────────────────────────────────────────────────────────────


class TestScaffold:

    def test_scaffold_populates_all_subdirs(self, tmp_path: Path):
        target = tmp_path / "tour"
        rc = main([
            "--variant=hip-lab",
            "--no-claude-desktop",
            "--target", str(target),
        ])
        assert rc == 0
        # Force / EMG / MRS CSVs landed.
        assert (target / "force" / "S001_force.csv").is_file()
        assert (target / "force" / "S016_force.csv").is_file()
        assert (target / "emg" / "S001_emg.csv").is_file()
        assert (target / "mrs" / "S001_mrs.csv").is_file()
        # Sidecars landed.
        assert (target / "force" / "metadata.json").is_file()
        assert (target / "emg" / "metadata.json").is_file()
        assert (target / "mrs" / "metadata.json").is_file()
        # Seed moment landed.
        assert (
            target / "vault" / "moments"
            / "2026-04-20-s004-emg-force-decoupling-suspected.md"
        ).is_file()
        # Configuration + index landed.
        assert (target / "user_config.json").is_file()
        assert (target / "data" / "vault.db").is_file()

    def test_user_config_has_absolute_paths_pointing_at_target(
        self, tmp_path: Path,
    ):
        target = tmp_path / "tour"
        main([
            "--variant=hip-lab", "--no-claude-desktop",
            "--target", str(target),
        ])
        # _resolve_target canonicalises via expanduser+resolve, so the
        # written paths reflect the canonicalised form (matters on macOS
        # where /var/folders symlinks to /private/var/folders).
        resolved = target.expanduser().resolve()
        cfg = json.loads(
            (resolved / "user_config.json").read_text(encoding="utf-8")
        )
        # Force_csv / emg_csv child registration depends on this exact shape.
        assert cfg["force_csv"]["path"] == str(resolved / "force")
        assert cfg["force_csv"]["timestamp_column"] == "t_s"
        assert cfg["force_csv"]["sample_rate_hz"] == 100.0
        assert cfg["force_csv"]["value_columns"] == {"force": "force_N"}
        assert cfg["emg_csv"]["path"] == str(resolved / "emg")
        assert cfg["emg_csv"]["value_columns"] == {"envelope": "envelope_uV"}
        # MRS spectra registered through generic csv_dir child so the
        # bundled fixtures are not orphaned (v6.9.1 — "address the
        # orphans" pass).  csv_dir.value_columns shape is
        # {actual_header: human_label}, distinct from force_csv /
        # emg_csv's logical→physical alias map.
        assert cfg["csv_dir"]["path"] == str(resolved / "mrs")
        assert cfg["csv_dir"]["timestamp_column"] == "t_s"
        assert "pcr_relative" in cfg["csv_dir"]["value_columns"]
        assert "pi_relative" in cfg["csv_dir"]["value_columns"]
        assert cfg["vault_path"] == str(resolved / "vault")

    def test_vault_index_has_seed_moment(self, tmp_path: Path):
        target = tmp_path / "tour"
        main([
            "--variant=hip-lab", "--no-claude-desktop",
            "--target", str(target),
        ])
        from tailor.framework.vault.storage import VaultStorage
        storage = VaultStorage(target / "data" / "vault.db")
        try:
            notes = storage.list_notes(subject_id="S004")
            s004_moments = [
                n for n in notes
                if "s004" in (n.get("filename") or "").lower()
                and n.get("note_type") == "moment"
            ]
            assert len(s004_moments) >= 1
        finally:
            storage.close()

    def test_idempotent_rerun(self, tmp_path: Path):
        target = tmp_path / "tour"
        rc1 = main([
            "--variant=hip-lab", "--no-claude-desktop",
            "--target", str(target),
        ])
        assert rc1 == 0
        rc2 = main([
            "--variant=hip-lab", "--no-claude-desktop",
            "--target", str(target),
        ])
        # Second run "refreshes" the existing tour — no error, no clobber.
        assert rc2 == 0
        assert (target / "user_config.json").is_file()

    def test_non_empty_non_tour_target_errors_without_force(
        self, tmp_path: Path, capsys,
    ):
        """Scaffolder refuses to clobber a directory that wasn't a prior
        tour scaffold (no user_config.json present)."""
        target = tmp_path / "tour"
        target.mkdir()
        (target / "stranger_file.txt").write_text(
            "don't clobber me", encoding="utf-8",
        )
        rc = main([
            "--variant=hip-lab", "--no-claude-desktop",
            "--target", str(target),
        ])
        assert rc != 0
        # Stranger file untouched.
        assert (target / "stranger_file.txt").read_text(
            encoding="utf-8",
        ) == "don't clobber me"

    def test_force_overrides_non_tour_target_guard(self, tmp_path: Path):
        target = tmp_path / "tour"
        target.mkdir()
        (target / "stranger_file.txt").write_text("clobber me", encoding="utf-8")
        rc = main([
            "--variant=hip-lab", "--no-claude-desktop", "--force",
            "--target", str(target),
        ])
        assert rc == 0
        # Tour fixtures scaffolded successfully past the guard.
        assert (target / "force" / "S001_force.csv").is_file()

    def test_force_wipes_stale_state_from_prior_tour(self, tmp_path: Path):
        """v6.9.2 bug #3 — ``--force`` against a prior-tour target must
        actually wipe stale state, not just bypass the guard.

        Before v6.9.2, ``_copy_resource_tree`` was file-by-file
        ``shutil.copy2`` with no rmtree, so a broken scaffold could not
        be cleanly recovered via ``--force`` — the WINDOWS_QUICKSTART
        recovery instruction was a lie.
        """
        target = tmp_path / "tour"
        # First scaffold (clean tour).
        rc = main([
            "--variant=hip-lab", "--no-claude-desktop",
            "--target", str(target),
        ])
        assert rc == 0
        # Drop a stale file inside the prior-tour target as if a
        # broken scaffold had left it there.
        stale = target / "force" / "stale_from_broken_scaffold.csv"
        stale.write_text("don't survive a --force", encoding="utf-8")
        assert stale.is_file()
        # Re-run with --force — must wipe the stale file before scaffold.
        rc2 = main([
            "--variant=hip-lab", "--no-claude-desktop", "--force",
            "--target", str(target),
        ])
        assert rc2 == 0
        # Stale file is gone; canonical fixtures are present.
        assert not stale.exists()
        assert (target / "force" / "S001_force.csv").is_file()
        assert (target / "user_config.json").is_file()


# ──────────────────────────────────────────────────────────────────────
# Claude Desktop registration — auditor blocker #1 fix is load-bearing.
# ──────────────────────────────────────────────────────────────────────


class TestClaudeDesktopRegistration:

    def test_writes_entry_with_baked_env_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """The Claude Desktop entry must carry TAILOR_CONFIG_DIR and
        TAILOR_DATA_DIR in the env block — this is the entire reason
        the recipient never types an env var by hand. If this regresses,
        ``tailor serve`` reads the operator's real config (or
        none) instead of the demo, and the recipient sees no tools."""
        fake_config = tmp_path / "claude_desktop_config.json"
        monkeypatch.setattr(
            "tailor.tour._claude_desktop_config_paths",
            lambda: [fake_config],
        )
        target = tmp_path / "tour"
        rc = main(["--variant=hip-lab", "--target", str(target)])
        assert rc == 0
        assert fake_config.exists()
        cfg = json.loads(fake_config.read_text(encoding="utf-8"))
        entry = cfg["mcpServers"]["tailor-tour-hip-lab"]
        resolved = target.expanduser().resolve()
        assert entry["env"]["TAILOR_CONFIG_DIR"] == str(resolved)
        assert entry["env"]["TAILOR_DATA_DIR"] == str(resolved / "data")
        assert entry["args"] == ["-m", "tailor", "serve"]

    def test_preserves_sibling_mcp_servers_on_merge(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Inherited from pilot.py's v6.2.1 deep-merge — sibling servers
        in the recipient's pre-existing config must survive."""
        fake_config = tmp_path / "claude_desktop_config.json"
        fake_config.write_text(json.dumps({
            "mcpServers": {
                "some-other-server": {"command": "foo", "args": []},
            },
        }), encoding="utf-8")
        monkeypatch.setattr(
            "tailor.tour._claude_desktop_config_paths",
            lambda: [fake_config],
        )
        target = tmp_path / "tour"
        main(["--variant=hip-lab", "--target", str(target)])
        cfg = json.loads(fake_config.read_text(encoding="utf-8"))
        assert "some-other-server" in cfg["mcpServers"]
        assert "tailor-tour-hip-lab" in cfg["mcpServers"]

    def test_cleans_stale_biosensor_entries_before_writing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """v6.10.3 — closes the dad-2026-05-06 multi-entry trap.

        Recipient debugged via web-Claude on a v6.9.x failed-tour
        install, ending up with a bare ``tailor`` entry
        (no env block) added to claude_desktop_config.json. A
        subsequent ``tailor tour --force`` previously left
        that bare entry in place; Claude Desktop would then launch
        two MCP servers, the bare one's SetupHelpLayer leaking into
        the working-demo tool surface. Tour must clean every
        ``biosensor-*`` sibling before adding its own.
        """
        fake_config = tmp_path / "claude_desktop_config.json"
        fake_config.write_text(json.dumps({
            "mcpServers": {
                "tailor": {
                    "command": "tailor",
                    "args": ["serve"],
                },
                "biosensor-tour-old-variant": {
                    "command": "python",
                    "args": ["-m", "tailor", "serve"],
                },
                "some-other-server": {"command": "foo", "args": []},
            },
        }), encoding="utf-8")
        monkeypatch.setattr(
            "tailor.tour._claude_desktop_config_paths",
            lambda: [fake_config],
        )
        target = tmp_path / "tour"
        rc = main(["--variant=hip-lab", "--target", str(target)])
        assert rc == 0
        cfg = json.loads(fake_config.read_text(encoding="utf-8"))
        servers = cfg["mcpServers"]
        # Stale biosensor-* entries are gone.
        assert "tailor" not in servers
        assert "biosensor-tour-old-variant" not in servers
        # Fresh tour entry is present.
        assert "tailor-tour-hip-lab" in servers
        # Non-biosensor sibling MCP servers are preserved.
        assert "some-other-server" in servers
        assert servers["some-other-server"] == {
            "command": "foo", "args": [],
        }

    def test_no_op_when_only_target_entry_already_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Re-running ``tour --force`` against a clean prior tour
        scaffold must NOT mis-classify the target entry as stale and
        delete it. The cleanup is "every biosensor-* EXCEPT the one
        we're about to write" — confirms the !=server_name guard."""
        fake_config = tmp_path / "claude_desktop_config.json"
        fake_config.write_text(json.dumps({
            "mcpServers": {
                "tailor-tour-hip-lab": {
                    "command": "python",
                    "args": ["-m", "tailor", "serve"],
                    "env": {"TAILOR_CONFIG_DIR": "/old/path"},
                },
            },
        }), encoding="utf-8")
        monkeypatch.setattr(
            "tailor.tour._claude_desktop_config_paths",
            lambda: [fake_config],
        )
        target = tmp_path / "tour"
        rc = main([
            "--variant=hip-lab", "--target", str(target), "--force",
        ])
        assert rc == 0
        cfg = json.loads(fake_config.read_text(encoding="utf-8"))
        # Entry survives; env was overwritten with the new target.
        assert "tailor-tour-hip-lab" in cfg["mcpServers"]
        entry = cfg["mcpServers"]["tailor-tour-hip-lab"]
        resolved = target.expanduser().resolve()
        assert entry["env"]["TAILOR_CONFIG_DIR"] == str(resolved)

    def test_no_claude_desktop_flag_skips_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        fake_config = tmp_path / "claude_desktop_config.json"
        monkeypatch.setattr(
            "tailor.tour._claude_desktop_config_paths",
            lambda: [fake_config],
        )
        target = tmp_path / "tour"
        main([
            "--variant=hip-lab", "--no-claude-desktop",
            "--target", str(target),
        ])
        assert not fake_config.exists()

    def test_linux_no_op_when_config_paths_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """On Linux ``_claude_desktop_config_paths`` returns an empty list —
        the scaffolder must complete cleanly without raising."""
        monkeypatch.setattr(
            "tailor.tour._claude_desktop_config_paths",
            lambda: [],
        )
        target = tmp_path / "tour"
        rc = main(["--variant=hip-lab", "--target", str(target)])
        assert rc == 0


# ──────────────────────────────────────────────────────────────────────
# Variant table + target resolution.
# ──────────────────────────────────────────────────────────────────────


class TestVariantTable:

    def test_default_variant_in_variants(self):
        assert DEFAULT_VARIANT in VARIANTS

    def test_default_variant_is_hip_lab(self):
        # Named explicitly so a future variant addition that accidentally
        # changes the default is caught here.
        assert DEFAULT_VARIANT == "hip-lab"

    def test_resolve_target_default_lives_under_biosensor_demos(self):
        path = _resolve_target("hip-lab", None)
        assert path.name == "hip-lab"
        assert path.parent.name == "demos"
        assert ".tailor" in str(path)

    def test_resolve_target_honors_override(self, tmp_path: Path):
        path = _resolve_target("hip-lab", str(tmp_path / "custom"))
        assert path.resolve() == (tmp_path / "custom").resolve()

    def test_write_user_config_rejects_unknown_variant(self, tmp_path: Path):
        """Defensive raise on `_write_user_config` — guards future
        variants added to ``_VARIANT_FIXTURES`` that forget to wire a
        ``user_config`` builder branch. The argparse layer keeps real
        users from triggering this (``choices=VARIANTS``); the guard
        catches programmatic callers."""
        from tailor.tour import _write_user_config
        with pytest.raises(ValueError, match="unknown variant"):
            _write_user_config("nonexistent-variant", tmp_path)

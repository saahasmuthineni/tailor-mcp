"""
Regression tests for v6.10.4 / ADR 0026 — dual-path Claude Desktop
config-path resolution under UWP sandboxing.

Closes the recipient-onboarding failure mode named in the v6.10.4
banner: a recipient with the Microsoft Store version of Claude
Desktop runs ``biosensor-mcp tour``, sees a "successfully registered"
message, restarts the app, and finds no biosensor tools because the
registration was written to the unredirected ``%APPDATA%\\Claude\\``
path while their Store-installed Claude Desktop reads from a UWP
sandbox at ``%LOCALAPPDATA%\\Packages\\Claude_*\\LocalCache\\Roaming\\Claude\\``.

The scenarios covered map 1:1 to the eight regression scenarios named
by the v6.10.4 proposal-mode audit:

    (i)    Store-only environment
    (ii)   classic-only environment
    (iii)  both-present-and-writable
    (iv)   both-present-write-to-Store-fails-with-PermissionError
    (v)    sibling-cleanup-fires-on-every-detected-path
    (vi)   neither-present-on-fresh-install
    (vii)  Linux skips silently
    (viii) v6.10.3 multi-entry-coexistence trap reproduced across paths
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ──────────────────────────────────────────────────────────────────────
# `_claude_desktop_config_paths` helper — direct shape tests
# ──────────────────────────────────────────────────────────────────────


class TestConfigPathsHelper:

    def test_linux_returns_empty_list(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario (vii). Linux has no Claude Desktop; the helper
        returns an empty list so the registration loop is a no-op."""
        from biosensor_mcp.pilot import _claude_desktop_config_paths

        monkeypatch.setattr(sys, "platform", "linux")
        assert _claude_desktop_config_paths() == []

    def test_macos_returns_single_canonical_path(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from biosensor_mcp.pilot import _claude_desktop_config_paths

        monkeypatch.setattr(sys, "platform", "darwin")
        result = _claude_desktop_config_paths()
        assert len(result) == 1
        assert result[0].name == "claude_desktop_config.json"
        assert "Application Support" in str(result[0])
        assert "Claude" in str(result[0])

    def test_windows_classic_only_when_no_store_packages(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario (ii). Recipient has the classic Anthropic installer;
        the Store ``Packages\\Claude_*\\`` glob returns no matches; the
        helper returns the single classic path."""
        from biosensor_mcp.pilot import _claude_desktop_config_paths

        monkeypatch.setattr(sys, "platform", "win32")
        appdata = tmp_path / "Roaming"
        appdata.mkdir()
        local = tmp_path / "Local"
        local.mkdir()
        (local / "Packages").mkdir()  # exists but empty
        monkeypatch.setenv("APPDATA", str(appdata))
        monkeypatch.setenv("LOCALAPPDATA", str(local))

        result = _claude_desktop_config_paths()
        assert len(result) == 1
        assert result[0] == appdata / "Claude" / "claude_desktop_config.json"

    def test_windows_store_only_when_classic_appdata_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario (i). Recipient has only the Microsoft Store version;
        ``Packages\\Claude_<suffix>\\`` exists; the helper still includes
        the classic path (created lazily on first write) AND the Store
        sandbox path. Classic-fallback contract per ADR 0026."""
        from biosensor_mcp.pilot import _claude_desktop_config_paths

        monkeypatch.setattr(sys, "platform", "win32")
        appdata = tmp_path / "Roaming"
        appdata.mkdir()
        local = tmp_path / "Local"
        packages = local / "Packages"
        packages.mkdir(parents=True)
        store_pkg = packages / "Claude_pzs8sxrjxfjjc"
        store_pkg.mkdir()
        monkeypatch.setenv("APPDATA", str(appdata))
        monkeypatch.setenv("LOCALAPPDATA", str(local))

        result = _claude_desktop_config_paths()
        assert len(result) == 2
        classic_path = appdata / "Claude" / "claude_desktop_config.json"
        store_path = (
            store_pkg / "LocalCache" / "Roaming" / "Claude"
            / "claude_desktop_config.json"
        )
        assert classic_path in result
        assert store_path in result

    def test_windows_both_classic_and_store_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario (iii). Recipient has both variants installed
        simultaneously — both detected paths returned."""
        from biosensor_mcp.pilot import _claude_desktop_config_paths

        monkeypatch.setattr(sys, "platform", "win32")
        appdata = tmp_path / "Roaming"
        (appdata / "Claude").mkdir(parents=True)
        local = tmp_path / "Local"
        store_pkg = local / "Packages" / "Claude_pzs8sxrjxfjjc"
        store_pkg.mkdir(parents=True)
        monkeypatch.setenv("APPDATA", str(appdata))
        monkeypatch.setenv("LOCALAPPDATA", str(local))

        result = _claude_desktop_config_paths()
        assert len(result) == 2

    def test_windows_neither_packages_dir_nor_store_pkg_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario (vi). Fresh Windows install with no Claude Desktop
        of any kind — Packages\\ may not even exist. The classic path
        is still always returned (parent created lazily on first
        write)."""
        from biosensor_mcp.pilot import _claude_desktop_config_paths

        monkeypatch.setattr(sys, "platform", "win32")
        appdata = tmp_path / "Roaming"  # does not exist on disk
        local = tmp_path / "Local"  # does not exist on disk
        monkeypatch.setenv("APPDATA", str(appdata))
        monkeypatch.setenv("LOCALAPPDATA", str(local))

        result = _claude_desktop_config_paths()
        assert len(result) == 1
        assert result[0] == appdata / "Claude" / "claude_desktop_config.json"

    def test_windows_store_glob_matches_publisher_hash_drift(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ADR 0026 § "Detection by prefix-glob". The glob is
        ``Claude_*`` — survives Anthropic re-signing the package with a
        different publisher-hash suffix. Test asserts a hypothetical
        future suffix is matched."""
        from biosensor_mcp.pilot import _claude_desktop_config_paths

        monkeypatch.setattr(sys, "platform", "win32")
        appdata = tmp_path / "Roaming"
        appdata.mkdir()
        local = tmp_path / "Local"
        future_pkg = local / "Packages" / "Claude_FUTURE_HASH_xyz"
        future_pkg.mkdir(parents=True)
        monkeypatch.setenv("APPDATA", str(appdata))
        monkeypatch.setenv("LOCALAPPDATA", str(local))

        result = _claude_desktop_config_paths()
        assert any("Claude_FUTURE_HASH_xyz" in str(p) for p in result)


# ──────────────────────────────────────────────────────────────────────
# Tour `_register_with_claude_desktop` — per-path semantics
# ──────────────────────────────────────────────────────────────────────


class TestPerPathRegistration:

    def test_writes_to_every_detected_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario (iii). Both Classic and Store configs detected;
        the same biosensor-tour-hip-lab entry must appear in both."""
        from biosensor_mcp.tour import main

        classic = tmp_path / "classic" / "claude_desktop_config.json"
        classic.parent.mkdir()
        sandbox = tmp_path / "sandbox" / "claude_desktop_config.json"
        sandbox.parent.mkdir()
        monkeypatch.setattr(
            "biosensor_mcp.tour._claude_desktop_config_paths",
            lambda: [classic, sandbox],
        )

        target = tmp_path / "tour"
        rc = main(["--variant=hip-lab", "--target", str(target)])
        assert rc == 0
        assert classic.exists()
        assert sandbox.exists()
        c = json.loads(classic.read_text(encoding="utf-8"))
        s = json.loads(sandbox.read_text(encoding="utf-8"))
        assert c["mcpServers"]["biosensor-tour-hip-lab"] == \
               s["mcpServers"]["biosensor-tour-hip-lab"]

    def test_per_path_permission_error_does_not_abort_others(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario (iv). PermissionError on one path must not abort
        writes to the others. Per ADR 0026 § Per-path atomic semantics.
        """
        from biosensor_mcp.tour import main

        classic = tmp_path / "classic" / "claude_desktop_config.json"
        classic.parent.mkdir()
        sandbox = tmp_path / "sandbox" / "claude_desktop_config.json"
        sandbox.parent.mkdir()
        monkeypatch.setattr(
            "biosensor_mcp.tour._claude_desktop_config_paths",
            lambda: [classic, sandbox],
        )

        # Make the sandbox-path write blow up by replacing
        # _write_claude_config with a side-effecting wrapper that
        # raises for the sandbox path only.
        from biosensor_mcp import pilot as pilot_mod
        original = pilot_mod._write_claude_config

        def _raise_for_sandbox(path: Path, data: dict, *, with_bom: bool) -> None:
            if path == sandbox:
                raise PermissionError(
                    "[Errno 13] Permission denied: claude_desktop_config.json"
                )
            return original(path, data, with_bom=with_bom)

        monkeypatch.setattr(pilot_mod, "_write_claude_config", _raise_for_sandbox)

        target = tmp_path / "tour"
        rc = main(["--variant=hip-lab", "--target", str(target)])
        # Exit code is 0 because at least one path was written.
        assert rc == 0
        # Classic was written despite the sandbox failure.
        assert classic.exists()
        c = json.loads(classic.read_text(encoding="utf-8"))
        assert "biosensor-tour-hip-lab" in c["mcpServers"]
        # Sandbox was NOT written.
        assert not sandbox.exists()

    def test_all_paths_failing_returns_exit_code_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Per ADR 0026: exit code is 1 if every detected path failed."""
        from biosensor_mcp import pilot as pilot_mod
        from biosensor_mcp.tour import main

        classic = tmp_path / "classic" / "claude_desktop_config.json"
        classic.parent.mkdir()
        sandbox = tmp_path / "sandbox" / "claude_desktop_config.json"
        sandbox.parent.mkdir()
        monkeypatch.setattr(
            "biosensor_mcp.tour._claude_desktop_config_paths",
            lambda: [classic, sandbox],
        )

        def _always_raise(path: Path, data: dict, *, with_bom: bool) -> None:
            raise PermissionError("locked")

        monkeypatch.setattr(pilot_mod, "_write_claude_config", _always_raise)

        target = tmp_path / "tour"
        rc = main(["--variant=hip-lab", "--target", str(target)])
        assert rc == 1
        assert not classic.exists()
        assert not sandbox.exists()

    def test_sibling_cleanup_fires_on_every_detected_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario (v). The v6.10.3 sibling-cleanup invariant
        ("exactly one biosensor-* entry exists") must hold per-path.
        Both configs start with stale ``biosensor-mcp`` entries; both
        must end with only the new ``biosensor-tour-hip-lab`` entry.
        """
        from biosensor_mcp.tour import main

        classic = tmp_path / "classic" / "claude_desktop_config.json"
        classic.parent.mkdir()
        classic.write_text(json.dumps({
            "mcpServers": {
                "biosensor-mcp": {"command": "stale-classic"},
                "obsidian": {"command": "node"},
            },
        }))
        sandbox = tmp_path / "sandbox" / "claude_desktop_config.json"
        sandbox.parent.mkdir()
        sandbox.write_text(json.dumps({
            "mcpServers": {
                "biosensor-mcp": {"command": "stale-sandbox"},
                "biosensor-tour-old": {"command": "stale-tour"},
                "raycast": {"command": "raycast"},
            },
        }))
        monkeypatch.setattr(
            "biosensor_mcp.tour._claude_desktop_config_paths",
            lambda: [classic, sandbox],
        )

        target = tmp_path / "tour"
        rc = main(["--variant=hip-lab", "--target", str(target)])
        assert rc == 0
        c = json.loads(classic.read_text(encoding="utf-8"))
        s = json.loads(sandbox.read_text(encoding="utf-8"))
        # Both configs: exactly one biosensor-* entry left, the new one.
        c_bio = [k for k in c["mcpServers"] if k.startswith("biosensor-")]
        s_bio = [k for k in s["mcpServers"] if k.startswith("biosensor-")]
        assert c_bio == ["biosensor-tour-hip-lab"]
        assert s_bio == ["biosensor-tour-hip-lab"]
        # Non-biosensor siblings on both paths preserved.
        assert "obsidian" in c["mcpServers"]
        assert "raycast" in s["mcpServers"]

    def test_multi_entry_coexistence_trap_across_both_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario (viii). v6.10.3 closed the trap on a single config;
        v6.10.4 closes it across both configs. A recipient who has a
        bare ``biosensor-mcp`` (no env block) entry in BOTH the classic
        and the sandbox configs — the v6.9.x web-Claude-debugging shape
        reproduced across both — must end up with only the new
        ``biosensor-tour-hip-lab`` entry in both, no stale leftovers."""
        from biosensor_mcp.tour import main

        bare_entry = {"command": "biosensor-mcp", "args": ["serve"]}
        classic = tmp_path / "classic" / "claude_desktop_config.json"
        classic.parent.mkdir()
        classic.write_text(json.dumps({
            "mcpServers": {"biosensor-mcp": bare_entry},
        }))
        sandbox = tmp_path / "sandbox" / "claude_desktop_config.json"
        sandbox.parent.mkdir()
        sandbox.write_text(json.dumps({
            "mcpServers": {"biosensor-mcp": bare_entry},
        }))
        monkeypatch.setattr(
            "biosensor_mcp.tour._claude_desktop_config_paths",
            lambda: [classic, sandbox],
        )

        target = tmp_path / "tour"
        rc = main(["--variant=hip-lab", "--target", str(target)])
        assert rc == 0
        for cfg_path in (classic, sandbox):
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            keys = list(data["mcpServers"])
            bio_keys = [k for k in keys if k.startswith("biosensor-")]
            assert bio_keys == ["biosensor-tour-hip-lab"], (
                f"{cfg_path.name} should have exactly one biosensor-* "
                f"entry but has {bio_keys}"
            )

    def test_per_path_tmp_artifact_cleaned_on_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ADR 0026 § Per-path atomic semantics: on a per-path write
        failure, the ``.tmp`` artifact left by ``_write_claude_config``
        is unlinked to avoid clutter across debugging loops."""
        from biosensor_mcp import pilot as pilot_mod
        from biosensor_mcp.tour import main

        sandbox = tmp_path / "sandbox" / "claude_desktop_config.json"
        sandbox.parent.mkdir()
        monkeypatch.setattr(
            "biosensor_mcp.tour._claude_desktop_config_paths",
            lambda: [sandbox],
        )

        # Have _write_claude_config create the .tmp file, then raise
        # before os.replace runs — emulates a permission-denied at
        # rename time on Windows.
        def _write_then_raise(path: Path, data: dict, *, with_bom: bool) -> None:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            body = json.dumps(data, indent=2).encode("utf-8")
            if with_bom:
                body = b"\xef\xbb\xbf" + body
            tmp.write_bytes(body)
            raise PermissionError("os.replace blocked by AV scanner")

        monkeypatch.setattr(pilot_mod, "_write_claude_config", _write_then_raise)

        target = tmp_path / "tour"
        rc = main(["--variant=hip-lab", "--target", str(target)])
        assert rc == 1
        assert not sandbox.exists()
        # The .tmp artifact must have been unlinked by the per-path
        # error-handling block.
        tmp_artifact = sandbox.with_suffix(sandbox.suffix + ".tmp")
        assert not tmp_artifact.exists(), (
            f".tmp artifact {tmp_artifact} should have been cleaned up"
        )

"""
Regression tests for v6.9.2 bug #1 — uninstall orphans the tour entry —
generalised in v6.10.4 to operate per-path across every detected
Claude Desktop config (Classic + Microsoft Store sandboxes per ADR
0026).

Before v6.9.2, ``cmd_uninstall`` deleted only the literal key
``mcpServers['tailor']``. The ``tour`` subcommand registers
under ``biosensor-tour-<variant>``, so a clean uninstall left the
tour entry pointing at a removed binary, producing a red MCP
indicator in Claude Desktop after the operator did everything right.
The fix swaps the literal-key match for a ``biosensor-`` prefix
match, captured in ``_clean_claude_desktop_biosensor_entries``.

v6.10.4 widens the surface: the cleanup iterates every Claude
Desktop config path the framework can confirm on this machine, not
only the classic one. Tests here monkey-patch
``_claude_desktop_config_paths`` to point at a single tmp file so
the behaviour against one config is unchanged from the v6.9.2
contract; ``test_iterates_every_detected_config`` asserts the
v6.10.4 multi-path behaviour explicitly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tailor.__main__ import _clean_claude_desktop_biosensor_entries


def _patch_paths(monkeypatch: pytest.MonkeyPatch, paths: list[Path]) -> None:
    """Point the detection helper at a fixed list of tmp paths."""
    monkeypatch.setattr(
        "tailor.pilot._claude_desktop_config_paths",
        lambda: paths,
    )


def test_removes_pilot_wizard_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({
        "mcpServers": {
            "tailor": {"command": "x"},
        },
    }))
    _patch_paths(monkeypatch, [cfg])
    result = _clean_claude_desktop_biosensor_entries()
    assert result == {cfg: ["tailor"]}
    after = json.loads(cfg.read_text())
    assert "tailor" not in after["mcpServers"]


def test_removes_tour_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({
        "mcpServers": {
            "biosensor-tour-hip-lab": {"command": "x"},
        },
    }))
    _patch_paths(monkeypatch, [cfg])
    result = _clean_claude_desktop_biosensor_entries()
    assert result == {cfg: ["biosensor-tour-hip-lab"]}
    after = json.loads(cfg.read_text())
    assert "biosensor-tour-hip-lab" not in after["mcpServers"]


def test_removes_both_pilot_and_tour_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({
        "mcpServers": {
            "tailor": {"command": "x"},
            "biosensor-tour-hip-lab": {"command": "y"},
            "biosensor-tour-sleep": {"command": "z"},
        },
    }))
    _patch_paths(monkeypatch, [cfg])
    result = _clean_claude_desktop_biosensor_entries()
    assert set(result[cfg]) == {
        "tailor", "biosensor-tour-hip-lab", "biosensor-tour-sleep",
    }
    after = json.loads(cfg.read_text())
    assert after["mcpServers"] == {}


def test_preserves_sibling_mcp_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cleanup must not touch unrelated MCP servers."""
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({
        "mcpServers": {
            "tailor": {"command": "x"},
            "biosensor-tour-hip-lab": {"command": "y"},
            "obsidian": {"command": "node", "args": ["obsidian.js"]},
            "strava-coaching": {"command": "python"},
        },
    }))
    _patch_paths(monkeypatch, [cfg])
    result = _clean_claude_desktop_biosensor_entries()
    after = json.loads(cfg.read_text())
    assert "obsidian" in after["mcpServers"]
    assert "strava-coaching" in after["mcpServers"]
    assert after["mcpServers"]["obsidian"]["command"] == "node"
    assert set(result[cfg]) == {"tailor", "biosensor-tour-hip-lab"}


def test_no_op_when_no_biosensor_entries_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({
        "mcpServers": {"obsidian": {"command": "node"}},
    }))
    _patch_paths(monkeypatch, [cfg])
    result = _clean_claude_desktop_biosensor_entries()
    assert result == {cfg: []}
    after = json.loads(cfg.read_text())
    assert "obsidian" in after["mcpServers"]


def test_no_op_when_config_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = tmp_path / "does_not_exist.json"
    _patch_paths(monkeypatch, [cfg])
    result = _clean_claude_desktop_biosensor_entries()
    assert result == {cfg: []}


def test_handles_utf8_bom_prefix_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirrors the BOM-tolerant read path the rest of the framework
    uses — a Claude Desktop config written by a PowerShell-default
    shell carries a UTF-8 BOM, and the cleanup must still parse it.
    """
    cfg = tmp_path / "claude_desktop_config.json"
    body = json.dumps({
        "mcpServers": {"tailor": {"command": "x"}},
    })
    cfg.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    _patch_paths(monkeypatch, [cfg])
    result = _clean_claude_desktop_biosensor_entries()
    assert result == {cfg: ["tailor"]}


def test_iterates_every_detected_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v6.10.4 / ADR 0026: cleanup must run on every detected config
    path so the v6.10.3 invariant ("exactly one biosensor-* entry per
    mcpServers") generalises across both Classic and Microsoft Store
    sandbox configs.
    """
    classic = tmp_path / "classic" / "claude_desktop_config.json"
    classic.parent.mkdir()
    classic.write_text(json.dumps({
        "mcpServers": {
            "tailor": {"command": "x"},
            "obsidian": {"command": "node"},
        },
    }))
    sandbox = tmp_path / "uwp" / "claude_desktop_config.json"
    sandbox.parent.mkdir()
    sandbox.write_text(json.dumps({
        "mcpServers": {
            "biosensor-tour-hip-lab": {"command": "y"},
            "raycast": {"command": "raycast"},
        },
    }))
    _patch_paths(monkeypatch, [classic, sandbox])

    result = _clean_claude_desktop_biosensor_entries()

    assert result[classic] == ["tailor"]
    assert result[sandbox] == ["biosensor-tour-hip-lab"]
    after_classic = json.loads(classic.read_text())
    after_sandbox = json.loads(sandbox.read_text())
    assert "tailor" not in after_classic["mcpServers"]
    assert "obsidian" in after_classic["mcpServers"]
    assert "biosensor-tour-hip-lab" not in after_sandbox["mcpServers"]
    assert "raycast" in after_sandbox["mcpServers"]

"""
Regression tests for v6.9.2 bug #1 — uninstall orphans the tour entry.

Before v6.9.2, ``cmd_uninstall`` deleted only the literal key
``mcpServers['biosensor-mcp']``. The ``tour`` subcommand registers
under ``biosensor-tour-<variant>``, so a clean uninstall left the
tour entry pointing at a removed binary, producing a red MCP
indicator in Claude Desktop after the operator did everything right.

The fix swaps the literal-key match for a ``biosensor-`` prefix
match, captured in ``_clean_claude_desktop_biosensor_entries``.
"""

from __future__ import annotations

import json
from pathlib import Path

from biosensor_mcp.__main__ import _clean_claude_desktop_biosensor_entries


def test_removes_pilot_wizard_entry(tmp_path: Path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({
        "mcpServers": {
            "biosensor-mcp": {"command": "x"},
        },
    }))
    removed = _clean_claude_desktop_biosensor_entries(cfg)
    assert removed == ["biosensor-mcp"]
    after = json.loads(cfg.read_text())
    assert "biosensor-mcp" not in after["mcpServers"]


def test_removes_tour_entry(tmp_path: Path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({
        "mcpServers": {
            "biosensor-tour-hip-lab": {"command": "x"},
        },
    }))
    removed = _clean_claude_desktop_biosensor_entries(cfg)
    assert removed == ["biosensor-tour-hip-lab"]
    after = json.loads(cfg.read_text())
    assert "biosensor-tour-hip-lab" not in after["mcpServers"]


def test_removes_both_pilot_and_tour_entries(tmp_path: Path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({
        "mcpServers": {
            "biosensor-mcp": {"command": "x"},
            "biosensor-tour-hip-lab": {"command": "y"},
            "biosensor-tour-sleep": {"command": "z"},
        },
    }))
    removed = _clean_claude_desktop_biosensor_entries(cfg)
    assert set(removed) == {
        "biosensor-mcp", "biosensor-tour-hip-lab", "biosensor-tour-sleep",
    }
    after = json.loads(cfg.read_text())
    assert after["mcpServers"] == {}


def test_preserves_sibling_mcp_servers(tmp_path: Path) -> None:
    """The cleanup must not touch unrelated MCP servers."""
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({
        "mcpServers": {
            "biosensor-mcp": {"command": "x"},
            "biosensor-tour-hip-lab": {"command": "y"},
            "obsidian": {"command": "node", "args": ["obsidian.js"]},
            "strava-coaching": {"command": "python"},
        },
    }))
    removed = _clean_claude_desktop_biosensor_entries(cfg)
    after = json.loads(cfg.read_text())
    assert "obsidian" in after["mcpServers"]
    assert "strava-coaching" in after["mcpServers"]
    assert after["mcpServers"]["obsidian"]["command"] == "node"
    assert set(removed) == {"biosensor-mcp", "biosensor-tour-hip-lab"}


def test_no_op_when_no_biosensor_entries_present(tmp_path: Path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({
        "mcpServers": {"obsidian": {"command": "node"}},
    }))
    removed = _clean_claude_desktop_biosensor_entries(cfg)
    assert removed == []
    # File still has obsidian and isn't rewritten unnecessarily.
    after = json.loads(cfg.read_text())
    assert "obsidian" in after["mcpServers"]


def test_no_op_when_config_missing(tmp_path: Path) -> None:
    cfg = tmp_path / "does_not_exist.json"
    removed = _clean_claude_desktop_biosensor_entries(cfg)
    assert removed == []


def test_handles_utf8_bom_prefix_round_trip(tmp_path: Path) -> None:
    """Mirrors the BOM-tolerant read path the rest of the framework
    uses — a Claude Desktop config written by a PowerShell-default
    shell carries a UTF-8 BOM, and the cleanup must still parse it.
    """
    cfg = tmp_path / "claude_desktop_config.json"
    body = json.dumps({
        "mcpServers": {"biosensor-mcp": {"command": "x"}},
    })
    cfg.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    removed = _clean_claude_desktop_biosensor_entries(cfg)
    assert removed == ["biosensor-mcp"]

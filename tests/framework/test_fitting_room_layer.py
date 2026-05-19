"""
Tests for FittingRoomLayer (ADR 0040 — MCP-tool version of v6.9.0
fitting-room scaffolding).

Verifies the three-tool surface, the status read-only path, and the
force / no-force scaffolding semantics. Heavy integration of the
underlying scaffold path is delegated to existing
``tests/test_fitting_room_subcommand.py`` (which exercises the
``tailor.fitting_room`` library functions directly).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tailor.framework.fitting_room import FittingRoomLayer


def _run(coro):
    return asyncio.run(coro)


def test_tool_surface_is_three_tools():
    layer = FittingRoomLayer()
    names = {td.name for td in layer.tool_definitions}
    assert names == {
        "tailor_fitting_room_status",
        "tailor_fitting_room_scaffold",
        "tailor_fitting_room_index_vault",
    }


def test_variant_allowlist_restricts_to_hip_lab():
    """ADR 0040 ships hip-lab only; matlab-lab / cgm-lab variants
    arrive in future releases under separate ADRs.
    """
    layer = FittingRoomLayer()
    schema = layer.param_schemas["tailor_fitting_room_scaffold"]
    assert schema["variant"].allowed_values == ["hip-lab"]


def test_status_when_target_missing(monkeypatch, tmp_path):
    """The status tool reads filesystem state; when nothing exists,
    it reports all the expected ``exists=False`` markers.
    """
    monkeypatch.setattr(
        "tailor.framework.fitting_room.layer.Path.home",
        lambda: tmp_path,
    )
    layer = FittingRoomLayer()
    result = _run(layer.execute(
        "tailor_fitting_room_status", {"variant": "hip-lab"},
    ))
    assert result["variant"] == "hip-lab"
    assert result["exists"] is False
    assert result["user_config_exists"] is False
    assert result["vault_dir_exists"] is False


def test_scaffold_refuses_existing_target_without_force(
    monkeypatch, tmp_path,
):
    """Without ``force=True``, scaffolding into an existing target
    must refuse with TargetExists rather than silently rmtree.
    """
    monkeypatch.setattr(
        "tailor.framework.fitting_room.layer.Path.home",
        lambda: tmp_path,
    )
    # Pre-create the target so the scaffold sees an existing dir.
    target = tmp_path / ".tailor" / "demos" / "hip-lab"
    target.mkdir(parents=True)
    (target / "marker").write_text("pre-existing")

    layer = FittingRoomLayer()
    result = _run(layer.execute(
        "tailor_fitting_room_scaffold",
        {"variant": "hip-lab"},
    ))
    assert result["ok"] is False
    assert result["error_class"] == "TargetExists"
    # The pre-existing marker must still be there.
    assert (target / "marker").exists()


def test_index_vault_refuses_missing_target(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "tailor.framework.fitting_room.layer.Path.home",
        lambda: tmp_path,
    )
    layer = FittingRoomLayer()
    result = _run(layer.execute(
        "tailor_fitting_room_index_vault", {"variant": "hip-lab"},
    ))
    assert result["ok"] is False
    assert result["error_class"] == "TargetMissing"


def test_unknown_tool_returns_error():
    layer = FittingRoomLayer()
    result = _run(layer.execute("tailor_fitting_room_nope", {}))
    assert "error" in result

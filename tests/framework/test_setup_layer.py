"""
Happy-path tests for SetupLayer (ADR 0040).

The load-bearing refusal tests live in
``tests/framework/test_setup_source_allowlist.py``. This file covers:

- Tool surface (4 tools, names match ADR 0040 § Decision).
- ``tailor_setup_status`` — awaiting / configured / malformed paths.
- ``tailor_setup_detect_schema`` — CSV happy path against a bundled
  fixture-shaped tempdir.
- ``tailor_setup_confirm_schema`` — pure pass-through.
- ``tailor_setup_write_source_block`` — happy path; restart_required
  flag; force=True overwrite.
"""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path

import pytest

from tailor.framework.setup import SetupLayer


def _run(coro):
    return asyncio.run(coro)


# ──────────────────────────────────────────────────────────────────────
# Tool surface — verifies ADR 0040 § Decision names
# ──────────────────────────────────────────────────────────────────────


def test_tool_surface_has_four_tools(tmp_path):
    layer = SetupLayer(config_dir=tmp_path)
    tool_names = {td.name for td in layer.tool_definitions}
    assert tool_names == {
        "tailor_setup_status",
        "tailor_setup_detect_schema",
        "tailor_setup_confirm_schema",
        "tailor_setup_write_source_block",
    }


def test_all_tools_are_tier_1(tmp_path):
    """SetupLayer tools bypass biosensor-tier gates per ADR 0040.

    Tier 1 is consistent with VaultLayer / AuditQueryLayer; the bypass
    posture is what matters, not the tier number, but the wire surface
    advertises tier=1 to keep `tools/list` consumers honest.
    """
    layer = SetupLayer(config_dir=tmp_path)
    for td in layer.tool_definitions:
        assert td.tier == 1


# ──────────────────────────────────────────────────────────────────────
# tailor_setup_status
# ──────────────────────────────────────────────────────────────────────


def test_status_awaiting_when_no_user_config(tmp_path):
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute("tailor_setup_status", {}))
    assert result["status"] == "awaiting_setup"
    assert result["configured_sources"] == []
    assert result["user_config_exists"] is False
    assert set(result["available_source_types"]) == {
        "csv", "matlab", "redcap",
    }


def test_status_configured_when_csv_dir_present(tmp_path):
    cfg = tmp_path / "user_config.json"
    cfg.write_text(json.dumps({"csv_dir": {"path": "/some/path"}}))
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute("tailor_setup_status", {}))
    assert result["status"] == "configured"
    assert result["configured_sources"] == ["csv_dir"]


def test_status_configured_multi_source(tmp_path):
    cfg = tmp_path / "user_config.json"
    cfg.write_text(json.dumps({
        "csv_dir": {"path": "/csv"},
        "matlab_file": {"path": "/mat"},
        "redcap_file": {"path": "/redcap"},
        "max_hr": 195,  # non-source key — ignored
    }))
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute("tailor_setup_status", {}))
    assert result["status"] == "configured"
    assert set(result["configured_sources"]) == {
        "csv_dir", "matlab_file", "redcap_file",
    }


def test_status_handles_malformed_config(tmp_path):
    cfg = tmp_path / "user_config.json"
    cfg.write_text("not valid json{{{")
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute("tailor_setup_status", {}))
    assert result["status"] == "config_unreadable"


def test_status_handles_non_object_config(tmp_path):
    cfg = tmp_path / "user_config.json"
    cfg.write_text(json.dumps(["this", "is", "a", "list"]))
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute("tailor_setup_status", {}))
    assert result["status"] == "config_malformed"


# ──────────────────────────────────────────────────────────────────────
# tailor_setup_detect_schema
# ──────────────────────────────────────────────────────────────────────


def _write_csv(path: Path, rows: int = 5) -> None:
    """Write a small valid CSV for detect_schema tests."""
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "Heart rate (bpm)", "Glucose (mg/dL)"])
        for i in range(rows):
            w.writerow([f"2026-01-01T00:00:{i:02d}", 60 + i, 100 + i])


def test_detect_csv_happy_path(tmp_path):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    _write_csv(csv_dir / "P001.csv")
    _write_csv(csv_dir / "P002.csv")

    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_detect_schema",
        {"source_type": "csv", "path": str(csv_dir)},
    ))
    assert result["ok"] is True
    assert result["source_type"] == "csv"
    assert result["csv_count"] == 2
    assert "schema" in result
    assert result["schema"]["timestamp_column"] == "timestamp"


def test_detect_csv_refuses_missing_path(tmp_path):
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_detect_schema",
        {"source_type": "csv", "path": str(tmp_path / "does_not_exist")},
    ))
    assert result["ok"] is False
    assert "does not exist" in result["error"].lower()


def test_detect_csv_refuses_empty_directory(tmp_path):
    csv_dir = tmp_path / "empty"
    csv_dir.mkdir()
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_detect_schema",
        {"source_type": "csv", "path": str(csv_dir)},
    ))
    assert result["ok"] is False


def test_detect_matlab_refuses_directory_without_mat_files(tmp_path):
    mat_dir = tmp_path / "mat"
    mat_dir.mkdir()
    (mat_dir / "not_a_mat.txt").write_text("hello")

    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_detect_schema",
        {"source_type": "matlab", "path": str(mat_dir)},
    ))
    assert result["ok"] is False
    assert "no .mat files" in result["error"].lower()


def test_detect_redcap_refuses_directory_missing_required_files(tmp_path):
    redcap_dir = tmp_path / "redcap"
    redcap_dir.mkdir()

    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_detect_schema",
        {"source_type": "redcap", "path": str(redcap_dir)},
    ))
    assert result["ok"] is False


def test_detect_redcap_accepts_directory_with_records_only(tmp_path):
    """records.csv OR project_metadata.csv is enough to detect."""
    redcap_dir = tmp_path / "redcap"
    redcap_dir.mkdir()
    (redcap_dir / "records.csv").write_text("record_id\n1\n")

    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_detect_schema",
        {"source_type": "redcap", "path": str(redcap_dir)},
    ))
    assert result["ok"] is True
    assert result["schema"]["records_present"] is True
    assert result["schema"]["metadata_present"] is False


# ──────────────────────────────────────────────────────────────────────
# tailor_setup_confirm_schema
# ──────────────────────────────────────────────────────────────────────


def test_confirm_schema_pass_through(tmp_path):
    layer = SetupLayer(config_dir=tmp_path)
    schema = {"timestamp_column": "ts", "value_columns": {"hr": "HR"}}
    result = _run(layer.execute(
        "tailor_setup_confirm_schema",
        {"source_type": "csv", "path": "/tmp/x", "schema": schema},
    ))
    assert result["ok"] is True
    assert result["confirmed"] is True
    assert result["source_type"] == "csv"
    assert result["schema"] == schema


def test_confirm_schema_refuses_unknown_source_type(tmp_path):
    """Even though ParamValidator gates this in dispatch, the layer
    body checks again as defense-in-depth — a bypass-the-validator
    test harness must still see the refusal.
    """
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_confirm_schema",
        {"source_type": "edf", "path": "/tmp/x", "schema": {}},
    ))
    assert result["ok"] is False


# ──────────────────────────────────────────────────────────────────────
# tailor_setup_write_source_block — happy paths
# ──────────────────────────────────────────────────────────────────────


def test_write_happy_path_csv(tmp_path, monkeypatch):
    """Wire the write tool through pilot._write_user_config and verify
    the source_key + source_block end up at the canonical writer.
    """
    captured = {}

    def fake_write(source_key, source_block, *, force=False):
        captured["source_key"] = source_key
        captured["source_block"] = source_block
        captured["force"] = force
        return tmp_path / "user_config.json"

    monkeypatch.setattr("tailor.pilot._write_user_config", fake_write)

    layer = SetupLayer(config_dir=tmp_path)
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    result = _run(layer.execute(
        "tailor_setup_write_source_block",
        {
            "source_type": "csv",
            "path": str(csv_dir),
            "validated_schema": {
                "timestamp_column": "ts",
                "timestamp_format": "%Y-%m-%dT%H:%M:%S",
                "value_columns": {"hr": "HR"},
            },
        },
    ))

    assert result["ok"] is True
    assert result["source_key"] == "csv_dir"
    assert result["restart_required"] is True
    assert captured["source_key"] == "csv_dir"
    assert captured["source_block"]["path"] == str(csv_dir)
    assert captured["source_block"]["timestamp_column"] == "ts"
    assert captured["force"] is False


def test_write_propagates_force_flag(tmp_path, monkeypatch):
    captured = {}

    def fake_write(source_key, source_block, *, force=False):
        captured["force"] = force
        return tmp_path / "user_config.json"

    monkeypatch.setattr("tailor.pilot._write_user_config", fake_write)

    layer = SetupLayer(config_dir=tmp_path)
    _run(layer.execute(
        "tailor_setup_write_source_block",
        {
            "source_type": "csv",
            "path": str(tmp_path),
            "validated_schema": {},
            "force": True,
        },
    ))
    assert captured["force"] is True


def test_write_returns_file_exists_error_on_collision(
    tmp_path, monkeypatch,
):
    def fake_write(source_key, source_block, *, force=False):
        raise FileExistsError(f"{source_key} is already configured")

    monkeypatch.setattr("tailor.pilot._write_user_config", fake_write)

    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_write_source_block",
        {
            "source_type": "csv",
            "path": str(tmp_path),
            "validated_schema": {},
        },
    ))
    assert result["ok"] is False
    assert result["error_class"] == "FileExistsError"
    assert "remediation" in result


# ──────────────────────────────────────────────────────────────────────
# Unknown tool name — defense-in-depth
# ──────────────────────────────────────────────────────────────────────


def test_unknown_tool_returns_error(tmp_path):
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute("tailor_setup_nope", {}))
    assert "error" in result
    assert "Unknown" in result["error"]

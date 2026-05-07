"""
Tests for the ``biosensor-mcp pilot`` wizard.

Each test isolates ``BIOSENSOR_CONFIG_DIR`` and ``BIOSENSOR_DATA_DIR``
to a tmp_path so the real ~/.biosensor-mcp is never touched. Inputs
are fed via ``monkeypatch.setattr("builtins.input", ...)`` and
``sys.platform`` is patched per-test so the Claude-Desktop branch
exercises every OS path.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def isolated_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Re-import ``biosensor_mcp.config`` and ``pilot`` under tmp dirs."""
    cfg_dir = tmp_path / "biosensor"
    cfg_dir.mkdir()
    data_dir = cfg_dir / "data"
    data_dir.mkdir()
    monkeypatch.setenv("BIOSENSOR_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("BIOSENSOR_DATA_DIR", str(data_dir))
    # Force re-import so module-level CONFIG_DIR/CONFIG_PATH pick up
    # the patched env vars.
    import biosensor_mcp.config as cfg_mod
    importlib.reload(cfg_mod)
    import biosensor_mcp.pilot as pilot_mod
    importlib.reload(pilot_mod)
    return cfg_dir


@pytest.fixture
def fake_csv_dir(tmp_path: Path) -> Path:
    """Create a directory with two well-formed CSVs sharing a header."""
    d = tmp_path / "csvs"
    d.mkdir()
    header = "timestamp,Heart rate (bpm),Blood glucose (mg/dL)\n"
    for name in ("A.csv", "B.csv"):
        (d / name).write_text(
            header + "2026-04-01T00:00:00,55,90\n2026-04-01T01:00:00,57,92\n",
            encoding="utf-8",
        )
    return d


def _fake_input(answers: list[str]):
    """Return a callable that returns successive ``answers`` for ``input()``."""
    it = iter(answers)

    def _read(prompt: str = "") -> str:
        try:
            return next(it)
        except StopIteration as exc:
            raise AssertionError(
                f"Wizard asked for more input than test provided. "
                f"Last prompt: {prompt!r}"
            ) from exc

    return _read


def test_clean_run_with_bundled_fixtures(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path,
) -> None:
    """Default path: accept bundled fixtures, default schema, skip Claude Desktop."""
    import biosensor_mcp.pilot as pilot

    bundled = pilot._resolve_bundled_fixture_dir()
    assert bundled is not None, "package fixture data must ship with the wheel"

    # Force linux to skip Claude Desktop step entirely.
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "builtins.input",
        _fake_input([
            "",        # prompt 1: accept default (bundled fixtures)
            "",        # prompt 2: accept detected schema
        ]),
    )

    rc = pilot.main()
    assert rc == 0
    written = json.loads(pilot.CONFIG_PATH.read_text(encoding="utf-8"))
    assert "csv_dir" in written
    assert Path(written["csv_dir"]["path"]) == bundled
    assert written["csv_dir"]["timestamp_column"] == "timestamp"


def test_existing_user_config_refused(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path, fake_csv_dir: Path,
) -> None:
    """Wizard must prompt before overwriting an existing config and respect 'no'."""
    import biosensor_mcp.pilot as pilot

    pre_existing = {"max_hr": 195, "marker": "do_not_clobber"}
    pilot.CONFIG_PATH.write_text(json.dumps(pre_existing), encoding="utf-8")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "builtins.input",
        _fake_input([
            str(fake_csv_dir),  # prompt 1: explicit path (no bundled default)
            "",                  # prompt 2: accept detected schema
            "n",                 # overwrite? → no
        ]),
    )

    rc = pilot.main()
    assert rc == 0
    after = json.loads(pilot.CONFIG_PATH.read_text(encoding="utf-8"))
    assert after.get("marker") == "do_not_clobber"


def test_existing_claude_desktop_mcpservers_preserved(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path, tmp_path: Path,
) -> None:
    """Sibling MCP server entries must survive the round-trip."""
    import biosensor_mcp.pilot as pilot

    cd_path = tmp_path / "claude_desktop_config.json"
    pre_existing = {
        "mcpServers": {
            "obsidian": {"command": "/usr/local/bin/obsidian-mcp", "args": ["serve"]},
        },
        "otherKey": "preserved",
    }
    cd_path.write_text(json.dumps(pre_existing, indent=2), encoding="utf-8")

    monkeypatch.setattr(pilot, "_claude_desktop_config_paths", lambda: [cd_path])
    monkeypatch.setattr(
        "builtins.input",
        _fake_input([""]),  # press Enter to proceed past the quit-Claude prompt
    )

    results = pilot._register_with_claude_desktop(
        ["/usr/bin/python", "-m", "biosensor_mcp", "serve"],
    )
    assert len(results) == 1
    assert results[0].written is True
    assert results[0].path == cd_path

    out = json.loads(cd_path.read_text(encoding="utf-8"))
    assert out["mcpServers"]["obsidian"]["command"] == "/usr/local/bin/obsidian-mcp"
    assert out["mcpServers"]["biosensor-mcp"]["command"] == "/usr/bin/python"
    assert out["otherKey"] == "preserved"


def test_bom_round_trip(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path, tmp_path: Path,
) -> None:
    """A BOM-prefixed config must read cleanly and re-emit a BOM."""
    import biosensor_mcp.pilot as pilot

    cd_path = tmp_path / "claude_desktop_config.json"
    body = json.dumps({"mcpServers": {"obsidian": {"command": "x"}}}, indent=2)
    cd_path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))

    monkeypatch.setattr(pilot, "_claude_desktop_config_paths", lambda: [cd_path])
    monkeypatch.setattr("builtins.input", _fake_input([""]))

    results = pilot._register_with_claude_desktop(
        ["/usr/bin/python", "-m", "biosensor_mcp", "serve"],
    )
    assert len(results) == 1 and results[0].written

    raw = cd_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "BOM must be re-emitted"
    parsed = json.loads(raw[3:].decode("utf-8"))
    assert "biosensor-mcp" in parsed["mcpServers"]
    assert "obsidian" in parsed["mcpServers"]


def test_schema_divergence_detected(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """F1: divergent CSV headers must drop confidence to 'low' and warn."""
    import biosensor_mcp.pilot as pilot

    d = tmp_path / "diverging"
    d.mkdir()
    (d / "A.csv").write_text(
        "timestamp,heart_rate\n2026-04-01T00:00:00,55\n", encoding="utf-8",
    )
    (d / "B.csv").write_text(
        "ts,bpm\n2026-04-01T00:00:00,55\n", encoding="utf-8",
    )

    schema = pilot._autodetect_csv_schema(d)
    assert schema.confidence == "low"
    captured = capsys.readouterr().out
    assert "DIFFERENT headers" in captured


def test_smoke_check_fails_loud_on_broken_columns(
    isolated_config: Path, fake_csv_dir: Path,
) -> None:
    """F1 part 2: smoke check must verify EVERY CSV, not just file 0."""
    import biosensor_mcp.pilot as pilot

    ok, msg = pilot._smoke_check(
        fake_csv_dir,
        value_columns={"hr": "Heart rate (bpm)", "missing": "Not A Real Column"},
        timestamp_column="timestamp",
        timestamp_format="%Y-%m-%dT%H:%M:%S",
    )
    assert not ok
    assert "Not A Real Column" in msg
    assert "A.csv" in msg or "B.csv" in msg


def test_linux_skips_claude_desktop(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path,
) -> None:
    """On Linux ``_claude_desktop_config_paths`` returns an empty list and
    registration is a no-op (no Claude Desktop on this platform)."""
    import biosensor_mcp.pilot as pilot

    monkeypatch.setattr(sys, "platform", "linux")
    assert pilot._claude_desktop_config_paths() == []

    results = pilot._register_with_claude_desktop(
        ["/usr/bin/python", "-m", "biosensor_mcp", "serve"],
    )
    assert results == []


def test_cloud_sync_warning_blocks_on_no(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path, tmp_path: Path,
) -> None:
    """C3: cloud-sync container detected + user picks 'N' → exit 0, no writes."""
    import biosensor_mcp.pilot as pilot

    onedrive_dir = tmp_path / "OneDrive" / "csvs"
    onedrive_dir.mkdir(parents=True)
    (onedrive_dir / "A.csv").write_text(
        "timestamp,heart_rate\n2026-04-01T00:00:00,55\n", encoding="utf-8",
    )

    provider = pilot._check_for_cloud_sync(onedrive_dir)
    assert provider == "OneDrive"

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "builtins.input",
        _fake_input([
            str(onedrive_dir),  # prompt 1: explicit OneDrive path
            "n",                 # cloud-sync continue? → no
        ]),
    )

    rc = pilot.main()
    assert rc == 0
    assert not pilot.CONFIG_PATH.exists()


def test_keyboard_interrupt_before_write_leaves_clean(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path,
) -> None:
    """SIGINT during prompt 1 must leave no on-disk state behind."""
    import biosensor_mcp.pilot as pilot

    monkeypatch.setattr(sys, "platform", "linux")

    def _raise(prompt: str = "") -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", _raise)

    rc = pilot.main()
    assert rc == 130
    assert not pilot.CONFIG_PATH.exists()

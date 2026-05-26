"""
Tests for the ``tailor pilot`` wizard.

Each test isolates ``TAILOR_CONFIG_DIR`` and ``TAILOR_DATA_DIR``
to a tmp_path so the real ~/.tailor is never touched. Inputs
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
    """Re-import ``tailor.config`` and ``pilot`` under tmp dirs."""
    cfg_dir = tmp_path / "biosensor"
    cfg_dir.mkdir()
    data_dir = cfg_dir / "data"
    data_dir.mkdir()
    monkeypatch.setenv("TAILOR_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("TAILOR_DATA_DIR", str(data_dir))
    # Force re-import so module-level CONFIG_DIR/CONFIG_PATH pick up
    # the patched env vars.
    import tailor.config as cfg_mod
    importlib.reload(cfg_mod)
    import tailor.pilot as pilot_mod
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
    import tailor.pilot as pilot

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

    rc = pilot.main([])
    assert rc == 0
    written = json.loads(pilot.CONFIG_PATH.read_text(encoding="utf-8"))
    assert "csv_dir" in written
    assert Path(written["csv_dir"]["path"]) == bundled
    assert written["csv_dir"]["timestamp_column"] == "timestamp"


def test_pre_existing_top_level_keys_preserved_on_csv_run(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path, fake_csv_dir: Path,
) -> None:
    """v7.5 F1 closure — top-level keys that aren't a source block survive.

    The deep-merge ``_write_user_config`` preserves every top-level key
    the wizard doesn't own (``max_hr``, ``vault_path``, ``cost_threshold``,
    sibling source blocks, operator-edited fields). The pre-v7.5
    full-overwrite behaviour would have erased ``marker`` and ``max_hr``
    here. Closes the ``integration-auditor --proposal-mode`` 2026-05-18
    finding.
    """
    import tailor.pilot as pilot

    pre_existing = {"max_hr": 195, "marker": "do_not_clobber"}
    pilot.CONFIG_PATH.write_text(json.dumps(pre_existing), encoding="utf-8")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "builtins.input",
        _fake_input([
            str(fake_csv_dir),  # prompt 1: explicit path (no bundled default)
            "",                  # prompt 2: accept detected schema
        ]),
    )

    rc = pilot.main([])
    assert rc == 0
    after = json.loads(pilot.CONFIG_PATH.read_text(encoding="utf-8"))
    assert after.get("marker") == "do_not_clobber"
    assert after.get("max_hr") == 195
    assert "csv_dir" in after
    assert after["csv_dir"]["path"] == str(fake_csv_dir)


def test_existing_csv_dir_block_prompts_for_overwrite_only(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path, fake_csv_dir: Path,
) -> None:
    """When the csv_dir block already exists, wizard prompts; 'n' preserves it.

    The new prompt is specific to the conflicting source block — sibling
    keys are preserved by construction either way. Compare to the pre-v7.5
    behaviour which prompted on the presence of *any* user_config.json
    content, conflating different source axes.
    """
    import tailor.pilot as pilot

    pre_existing = {
        "csv_dir": {"path": "/old/path", "marker": "do_not_clobber"},
        "max_hr": 195,
    }
    pilot.CONFIG_PATH.write_text(json.dumps(pre_existing), encoding="utf-8")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "builtins.input",
        _fake_input([
            str(fake_csv_dir),  # prompt 1: explicit path
            "",                  # prompt 2: accept detected schema
            "n",                 # overwrite csv_dir block? → no
        ]),
    )

    rc = pilot.main([])
    assert rc == 0
    after = json.loads(pilot.CONFIG_PATH.read_text(encoding="utf-8"))
    assert after["csv_dir"].get("marker") == "do_not_clobber"
    assert after["csv_dir"]["path"] == "/old/path"
    assert after.get("max_hr") == 195


def test_existing_claude_desktop_mcpservers_preserved(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path, tmp_path: Path,
) -> None:
    """Sibling MCP server entries must survive the round-trip."""
    import tailor.pilot as pilot

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
        ["/usr/bin/python", "-m", "tailor", "serve"],
    )
    assert len(results) == 1
    assert results[0].written is True
    assert results[0].path == cd_path

    out = json.loads(cd_path.read_text(encoding="utf-8"))
    assert out["mcpServers"]["obsidian"]["command"] == "/usr/local/bin/obsidian-mcp"
    assert out["mcpServers"]["tailor"]["command"] == "/usr/bin/python"
    assert out["otherKey"] == "preserved"


def test_bom_round_trip(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path, tmp_path: Path,
) -> None:
    """A BOM-prefixed config must read cleanly and re-emit a BOM."""
    import tailor.pilot as pilot

    cd_path = tmp_path / "claude_desktop_config.json"
    body = json.dumps({"mcpServers": {"obsidian": {"command": "x"}}}, indent=2)
    cd_path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))

    monkeypatch.setattr(pilot, "_claude_desktop_config_paths", lambda: [cd_path])
    monkeypatch.setattr("builtins.input", _fake_input([""]))

    results = pilot._register_with_claude_desktop(
        ["/usr/bin/python", "-m", "tailor", "serve"],
    )
    assert len(results) == 1 and results[0].written

    raw = cd_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "BOM must be re-emitted"
    parsed = json.loads(raw[3:].decode("utf-8"))
    assert "tailor" in parsed["mcpServers"]
    assert "obsidian" in parsed["mcpServers"]


def test_schema_divergence_detected(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """F1: divergent CSV headers must drop confidence to 'low' and warn."""
    import tailor.pilot as pilot

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
    import tailor.pilot as pilot

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
    import tailor.pilot as pilot

    monkeypatch.setattr(sys, "platform", "linux")
    assert pilot._claude_desktop_config_paths() == []

    results = pilot._register_with_claude_desktop(
        ["/usr/bin/python", "-m", "tailor", "serve"],
    )
    assert results == []


def test_cloud_sync_warning_blocks_on_no(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path, tmp_path: Path,
) -> None:
    """C3: cloud-sync container detected + user picks 'N' → exit 0, no writes."""
    import tailor.pilot as pilot

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

    rc = pilot.main([])
    assert rc == 0
    assert not pilot.CONFIG_PATH.exists()


def test_keyboard_interrupt_before_write_leaves_clean(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path,
) -> None:
    """SIGINT during prompt 1 must leave no on-disk state behind."""
    import tailor.pilot as pilot

    monkeypatch.setattr(sys, "platform", "linux")

    def _raise(prompt: str = "") -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", _raise)

    rc = pilot.main([])
    assert rc == 130
    assert not pilot.CONFIG_PATH.exists()


# ──────────────────────────────────────────────────────────────────────
# v7.5 MATLAB handler — scipy-not-required regression coverage
#
# The scipy-required happy-path tests (variable enumeration, full
# wizard flow) live in tests/test_pilot_wizard_matlab.py under
# pytest.importorskip("scipy.io"). Tests here exercise the F2 (lazy
# scipy) and F6 (magic-byte HDF5) paths that DO NOT require scipy.
# ──────────────────────────────────────────────────────────────────────


def test_matlab_friendly_error_when_scipy_missing(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """F2 closure (proposal-mode auditor 2026-05-18): --source=matlab
    without scipy installed surfaces a clean install hint and exits
    with rc=1. Avoids the silent-crash trap class of v6.10.2.
    """
    import tailor.pilot as pilot

    # Block scipy.io import via the sys.modules None-sentinel
    # mechanism — Python's import system raises ModuleNotFoundError
    # when a key is present with value None.
    monkeypatch.setitem(sys.modules, "scipy", None)
    monkeypatch.setitem(sys.modules, "scipy.io", None)

    rc = pilot.main(["--source=matlab"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "scipy" in out.lower()
    assert "tailor-mcp[matlab]" in out
    assert "ERROR" in out
    # The wizard suggests the alternate source axes are still usable —
    # important for an operator who has csv_dir or redcap_file
    # configured and just wants the matlab addition to fail soft.
    assert "--source=csv" in out
    assert "--source=redcap" in out


def test_scan_mat_files_flags_hdf5_via_magic_bytes(
    isolated_config: Path, tmp_path: Path,
) -> None:
    """F6 closure: _scan_mat_files detects v7.3 HDF5 files by their
    8-byte magic signature BEFORE any scipy.io.loadmat call.

    Per ADR 0036 v7.3 is deferred; the wizard must surface them as
    a coherent group with the remediation hint rather than crashing
    the variable-enumeration loop with NotImplementedError. The
    scipy_io argument is a sentinel barfing-loadmat — if the magic-
    byte check ever fails to fire, the test fails loudly.
    """
    import tailor.pilot as pilot

    mat_dir = tmp_path / "hdf5_only"
    mat_dir.mkdir()
    (mat_dir / "A.mat").write_bytes(pilot._HDF5_MAGIC + b"\x00" * 100)
    (mat_dir / "B.mat").write_bytes(pilot._HDF5_MAGIC + b"\x00" * 100)

    class _BarfingScipyIO:
        @staticmethod
        def loadmat(*args, **kwargs):
            raise AssertionError(
                "_scan_mat_files should NOT call loadmat on HDF5 files; "
                "F6 magic-byte pre-check failed."
            )

    result = pilot._scan_mat_files(mat_dir, _BarfingScipyIO())
    assert result.total_files == 2
    assert sorted(result.hdf5_files) == ["A.mat", "B.mat"]
    assert result.variable_inventory == {}
    assert result.parse_errors == []


def test_scan_mat_files_partitions_mixed_hdf5_and_parseable(
    isolated_config: Path, tmp_path: Path,
) -> None:
    """A mixed directory correctly partitions into HDF5 (skipped via
    magic-byte) and parseable (handed to scipy.io.loadmat)."""
    import tailor.pilot as pilot

    mat_dir = tmp_path / "mixed"
    mat_dir.mkdir()
    # HDF5 v7.3
    (mat_dir / "v73.mat").write_bytes(pilot._HDF5_MAGIC + b"\x00" * 100)
    # Non-HDF5 (v5-shaped header start; scipy_io is a fake here)
    (mat_dir / "v5.mat").write_bytes(
        b"MATLAB 5.0 MAT-file" + b" " * 97 + b"\x01\x00MI" + b"\x00" * 16
    )

    class _FakeScipyIO:
        @staticmethod
        def loadmat(path, **kwargs):
            # Mimic scipy.io.loadmat: returns a dict with __header__
            # plus user variables. Our scanner filters out underscore-
            # prefixed keys.
            return {"__header__": b"...", "myvar": [1.0, 2.0, 3.0]}

    result = pilot._scan_mat_files(mat_dir, _FakeScipyIO())
    assert result.total_files == 2
    assert result.hdf5_files == ["v73.mat"]
    assert result.variable_inventory == {"v5.mat": ["myvar"]}
    assert result.parse_errors == []


def test_scan_mat_files_captures_loadmat_parse_errors(
    isolated_config: Path, tmp_path: Path,
) -> None:
    """Files that pass the magic-byte check but fail scipy.io.loadmat
    surface in parse_errors with the exception message, NOT as
    silent omissions."""
    import tailor.pilot as pilot

    mat_dir = tmp_path / "broken"
    mat_dir.mkdir()
    (mat_dir / "corrupt.mat").write_bytes(
        b"MATLAB 5.0 MAT-file" + b" " * 97 + b"\x01\x00MI" + b"\x00" * 16
    )

    class _FailingScipyIO:
        @staticmethod
        def loadmat(path, **kwargs):
            raise ValueError("corrupt header")

    result = pilot._scan_mat_files(mat_dir, _FailingScipyIO())
    assert result.total_files == 1
    assert result.hdf5_files == []
    assert result.variable_inventory == {}
    assert len(result.parse_errors) == 1
    assert result.parse_errors[0][0] == "corrupt.mat"
    assert "corrupt header" in result.parse_errors[0][1]


# ──────────────────────────────────────────────────────────────────────
# v7.5 REDCap handler — scipy-not-required regression coverage
#
# RedcapPHIScrubber is stdlib-only (csv + hashlib), so REDCap tests
# don't need a [matlab]-style importorskip. The full --source=redcap
# wizard flow lives in tests/test_pilot_wizard_redcap.py once that
# file lands; tests here cover the helper-level F1, F3, F5, F7
# invariants directly.
# ──────────────────────────────────────────────────────────────────────


def test_display_redcap_trust_root_shows_per_field_identifier_listing(
    isolated_config: Path, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The wizard's trust-root display shows every field paired with
    its identifier flag — boss decision 2026-05-18 (full listing, not
    compact summary). A flag-flip attack on project_metadata.csv is
    visible at the moment of operator confirmation; a compact
    summary would defeat the seam's purpose.
    """
    import tailor.pilot as pilot
    from tailor.children.redcap.scrubber import RedcapPHIScrubber

    metadata_path = tmp_path / "project_metadata.csv"
    metadata_path.write_text(
        "field_name,field_label,identifier\n"
        "record_id,Record ID,y\n"
        "first_name,First name,y\n"
        "age,Age,\n"
        "score,Score,\n",
        encoding="utf-8",
    )

    scrubber = RedcapPHIScrubber(metadata_path)
    pilot._display_redcap_trust_root(scrubber)

    out = capsys.readouterr().out
    # Every field surfaces — the operator can visually audit each.
    assert "record_id" in out
    assert "first_name" in out
    assert "age" in out
    assert "score" in out
    # Identifier vs non-identifier markers are visible and distinct.
    assert "[IDENTIFIER]" in out
    assert "[ok]" in out
    # The fingerprint surfaces so the operator can correlate audit
    # rows to the trust root in effect at first config.
    assert scrubber.fingerprint in out
    # Summary count surfaces.
    assert "4 fields" in out
    assert "2 flagged" in out  # record_id + first_name


def test_detect_redcap_completion_fields_finds_complete_columns(
    tmp_path: Path,
) -> None:
    """F3 partial closure (wizard side): the helper reads records.csv
    as utf-8-sig and scans the header row for columns ending in
    ``_complete`` — REDCap's per-instrument completion convention."""
    import tailor.pilot as pilot

    redcap_dir = tmp_path / "redcap"
    redcap_dir.mkdir()
    (redcap_dir / "records.csv").write_text(
        "record_id,redcap_event_name,demographics_complete,"
        "phq9_complete,age\n"
        "1,baseline,2,2,42\n",
        encoding="utf-8",
    )

    fields = pilot._detect_redcap_completion_fields(redcap_dir)
    assert fields == ["demographics_complete", "phq9_complete"]


def test_detect_redcap_completion_fields_handles_bom(
    tmp_path: Path,
) -> None:
    """F3 closure: BOM-prefixed records.csv (Excel/PowerShell round-
    trip) must NOT corrupt the first-column header. ``utf-8-sig`` on
    the open() call strips the BOM transparently.

    Without utf-8-sig, the first header would carry a literal ``\\ufeff``
    prefix — silently breaking REDCap workflows that depend on
    record_id being the canonical first-column header. v6.9.2 closed
    this exact footgun across 12 child sites; the wizard inherits
    the same posture here.
    """
    import tailor.pilot as pilot

    redcap_dir = tmp_path / "redcap"
    redcap_dir.mkdir()
    header = "record_id,redcap_event_name,demographics_complete\n"
    body = "1,baseline,2\n"
    (redcap_dir / "records.csv").write_bytes(
        b"\xef\xbb\xbf" + (header + body).encode("utf-8"),
    )

    fields = pilot._detect_redcap_completion_fields(redcap_dir)
    assert fields == ["demographics_complete"]


def test_detect_redcap_completion_fields_returns_empty_when_no_records(
    tmp_path: Path,
) -> None:
    """No records.csv → empty list. Wizard then writes the
    redcap_file block without ``instrument_completion_fields``;
    operator can hand-edit user_config.json later if needed."""
    import tailor.pilot as pilot

    redcap_dir = tmp_path / "redcap_no_records"
    redcap_dir.mkdir()
    # No records.csv — only the metadata dictionary would be present
    # in a metadata-only export.

    fields = pilot._detect_redcap_completion_fields(redcap_dir)
    assert fields == []


def test_attest_initial_audit_row_uses_auditlog_record_with_child_scrubber_id(
    isolated_config: Path, tmp_path: Path,
) -> None:
    """F5 + v7.3.2 F-A precedent: the ATTEST_INITIAL audit row carries
    ``child_scrubber_id='redcap_metadata_flags'`` AND
    ``source_metadata_fingerprint`` by going through
    ``AuditLog.record()`` — NOT a hand-rolled INSERT.

    The v7.3.2 ``cmd_redcap_reattest`` was hand-rolling INSERTs and
    left ``scrubber_id`` NULL on REATTEST rows — a direct ADR 0003
    violation that the release-pass phi-irb-risk-reviewer caught
    pre-merge. Threading through ``AuditLog.record()`` inherits the
    framework's schema, migration logic, and any future audit-column
    additions automatically.
    """
    import sqlite3

    import tailor.pilot as pilot

    redcap_dir = tmp_path / "redcap"
    redcap_dir.mkdir()
    fingerprint = "a" * 64  # synthetic SHA-256-shaped hex

    ok = pilot._write_attest_initial_audit_row(fingerprint, redcap_dir)
    assert ok is True

    from tailor.config import DATA_DIR
    conn = sqlite3.connect(DATA_DIR / "audit.db")
    cursor = conn.execute(
        "SELECT domain, tool_name, tier, outcome, scrubber_id, "
        "       child_scrubber_id, source_metadata_fingerprint, "
        "       params "
        "  FROM audit_log "
        " WHERE outcome = 'ATTEST_INITIAL'"
    )
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 1
    (
        domain, tool_name, tier, outcome,
        scrubber_id, child_scrubber_id, source_meta_fp, params_json,
    ) = rows[0]
    assert domain == "redcap_file"
    assert tool_name == "tailor_redcap_attest_initial"
    assert tier == 0
    # ATTEST_INITIAL is distinct from REATTEST: first attestation has
    # no cached fingerprint to compare against. Per F5.
    assert outcome == "ATTEST_INITIAL"
    # ADR 0003 § Amendment 2026-05-15: every REDCap row threads the
    # child scrubber identity and source fingerprint. The v7.3.2 F-A
    # bug shipped these as NULL via a hand-rolled INSERT — this
    # assertion catches any future regression to that pattern.
    # WATCH-1 closure (phi-irb-risk-reviewer 2026-05-18): the row
    # threads the framework scrubber's identity dynamically rather
    # than hardcoding "noop". Under the default DataScrubber the
    # identity IS "noop", but a subclassed framework scrubber would
    # surface its own identity here AND on the matching REATTEST row
    # — without this contract, the rows would disagree on
    # scrubber_id for the same logical event.
    from tailor.framework.security import DataScrubber
    assert scrubber_id == DataScrubber().scrubber_id
    assert child_scrubber_id == "redcap_metadata_flags"
    assert source_meta_fp == fingerprint
    # Parse params as JSON (Windows backslashes are double-escaped in
    # the on-disk string; comparing the parsed structure avoids the
    # platform-specific escaping pitfall a literal substring check
    # would carry).
    params_dict = json.loads(params_json)
    assert params_dict["action"] == "first_config_attestation"
    assert params_dict["redcap_dir"] == str(redcap_dir)
    assert params_dict["project_metadata_file"] == "project_metadata.csv"


def test_attest_initial_failure_logs_warning_does_not_crash(
    isolated_config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Audit-row failure is best-effort — surfaces a warning but does
    NOT propagate. The wizard's primary purpose is writing a usable
    config; provenance gaps are recoverable via ``tailor redcap
    reattest`` later.
    """
    import tailor.pilot as pilot
    from tailor.framework import audit as audit_mod

    class _FailingAuditLog:
        def __init__(self, *args, **kwargs):
            pass

        def record(self, *args, **kwargs):
            raise OSError("simulated disk full")

    monkeypatch.setattr(audit_mod, "AuditLog", _FailingAuditLog)

    redcap_dir = tmp_path / "redcap"
    redcap_dir.mkdir()
    ok = pilot._write_attest_initial_audit_row("a" * 64, redcap_dir)
    assert ok is False
    out = capsys.readouterr().out
    assert "[warn]" in out
    assert "ATTEST_INITIAL" in out or "audit row" in out


def test_redcap_block_write_preserves_csv_dir_sibling(
    isolated_config: Path, tmp_path: Path,
) -> None:
    """F1 closure for the REDCap path: writing the redcap_file block
    via _write_user_config preserves a pre-existing csv_dir block.
    Multi-source coexistence works for csv→redcap (the structural
    pair this v7.5 release was built to enable)."""
    import tailor.pilot as pilot

    pilot.CONFIG_PATH.write_text(
        json.dumps({
            "csv_dir": {"path": "/old/csv", "timestamp_column": "t"},
            "max_hr": 195,
        }),
        encoding="utf-8",
    )

    pilot._write_user_config(
        "redcap_file",
        {"path": str(tmp_path), "records_file": "records.csv"},
    )

    after = json.loads(pilot.CONFIG_PATH.read_text(encoding="utf-8"))
    assert "csv_dir" in after
    assert after["csv_dir"]["path"] == "/old/csv"
    assert "redcap_file" in after
    assert after["redcap_file"]["path"] == str(tmp_path)
    assert after.get("max_hr") == 195


# ──────────────────────────────────────────────────────────────────────
# v7.5 --source dispatch — argparse routes to per-source handlers
# ──────────────────────────────────────────────────────────────────────


def test_source_dispatch_routes_csv_by_default(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path,
) -> None:
    """argparse default --source is 'csv'; main([]) routes to _run_csv.

    Preserves the v6.2.1 backward-compat contract — invoking
    ``tailor pilot`` with no flags is the original CSV setup wizard.
    """
    import tailor.pilot as pilot

    calls: list[str] = []
    monkeypatch.setattr(
        pilot, "_run_csv", lambda c: (calls.append("csv"), 0)[1],
    )
    monkeypatch.setattr(
        pilot, "_run_matlab", lambda c: (calls.append("matlab"), 0)[1],
    )
    monkeypatch.setattr(
        pilot, "_run_redcap", lambda c: (calls.append("redcap"), 0)[1],
    )

    rc = pilot.main([])
    assert rc == 0
    assert calls == ["csv"]


def test_source_dispatch_routes_matlab(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path,
) -> None:
    """--source=matlab routes to _run_matlab."""
    import tailor.pilot as pilot

    calls: list[str] = []
    monkeypatch.setattr(
        pilot, "_run_csv", lambda c: (calls.append("csv"), 0)[1],
    )
    monkeypatch.setattr(
        pilot, "_run_matlab", lambda c: (calls.append("matlab"), 0)[1],
    )
    monkeypatch.setattr(
        pilot, "_run_redcap", lambda c: (calls.append("redcap"), 0)[1],
    )

    rc = pilot.main(["--source=matlab"])
    assert rc == 0
    assert calls == ["matlab"]


def test_source_dispatch_routes_redcap(
    monkeypatch: pytest.MonkeyPatch, isolated_config: Path,
) -> None:
    """--source=redcap routes to _run_redcap."""
    import tailor.pilot as pilot

    calls: list[str] = []
    monkeypatch.setattr(
        pilot, "_run_csv", lambda c: (calls.append("csv"), 0)[1],
    )
    monkeypatch.setattr(
        pilot, "_run_matlab", lambda c: (calls.append("matlab"), 0)[1],
    )
    monkeypatch.setattr(
        pilot, "_run_redcap", lambda c: (calls.append("redcap"), 0)[1],
    )

    rc = pilot.main(["--source=redcap"])
    assert rc == 0
    assert calls == ["redcap"]


def test_source_dispatch_rejects_unknown_source(
    isolated_config: Path,
) -> None:
    """argparse rejects unknown --source values with SystemExit(2)
    before any cleanup/SIGINT-handler registration runs."""
    import tailor.pilot as pilot

    with pytest.raises(SystemExit) as exc_info:
        pilot.main(["--source=junk"])
    assert exc_info.value.code == 2


# ──────────────────────────────────────────────────────────────────────
# v7.5 F1 closure — multi-source coexistence at the helper level
# ──────────────────────────────────────────────────────────────────────


def test_write_user_config_preserves_sibling_source_blocks(
    isolated_config: Path,
) -> None:
    """F1 regression — _write_user_config('matlab_file', ...) preserves a
    pre-existing 'csv_dir' block by construction.

    The multi-source coexistence invariant that motivates v7.5: when an
    operator runs the wizard for a second source axis two weeks after
    the first, the first axis's configuration MUST NOT be silently
    wiped. Pre-v7.5 the full-overwrite shape of _write_user_config would
    have eaten the csv_dir block here.
    """
    import tailor.pilot as pilot

    pilot.CONFIG_PATH.write_text(
        json.dumps({
            "csv_dir": {"path": "/csv/dir", "timestamp_column": "t"},
            "max_hr": 195,
        }),
        encoding="utf-8",
    )

    pilot._write_user_config("matlab_file", {"path": "/mat/dir"})

    after = json.loads(pilot.CONFIG_PATH.read_text(encoding="utf-8"))
    assert "csv_dir" in after
    assert after["csv_dir"]["path"] == "/csv/dir"
    assert after["csv_dir"]["timestamp_column"] == "t"
    assert "matlab_file" in after
    assert after["matlab_file"]["path"] == "/mat/dir"
    assert after.get("max_hr") == 195


def test_write_user_config_raises_on_existing_source_key_without_force(
    isolated_config: Path,
) -> None:
    """The helper raises FileExistsError when the source_key is already
    set, so the caller can prompt for confirmation. ``force=True``
    overwrites only that block; siblings are still preserved."""
    import tailor.pilot as pilot

    pilot.CONFIG_PATH.write_text(
        json.dumps({
            "csv_dir": {"path": "/old", "marker": "keep_me"},
            "matlab_file": {"path": "/mat"},
        }),
        encoding="utf-8",
    )

    with pytest.raises(FileExistsError):
        pilot._write_user_config("csv_dir", {"path": "/new"})

    # force=True overwrites csv_dir but preserves matlab_file
    pilot._write_user_config("csv_dir", {"path": "/new"}, force=True)
    after = json.loads(pilot.CONFIG_PATH.read_text(encoding="utf-8"))
    assert after["csv_dir"]["path"] == "/new"
    # csv_dir block replaced fully — 'marker' from the old block does
    # NOT leak into the new one; the merge is at top-level only.
    assert "marker" not in after["csv_dir"]
    # Sibling block survives the targeted overwrite.
    assert "matlab_file" in after
    assert after["matlab_file"]["path"] == "/mat"


def test_write_user_config_handles_bom_prefixed_existing_file(
    isolated_config: Path,
) -> None:
    """Excel/PowerShell-saved user_config.json prepends a BOM. The deep-
    merge writer reads with utf-8-sig (v6.9.2 BOM-strip precedent across
    12 child sites). Without this, the first-column header would carry a
    literal \\ufeff prefix and the existing-key check would fail to match.
    """
    import tailor.pilot as pilot

    body = json.dumps({
        "csv_dir": {"path": "/existing"},
        "max_hr": 195,
    })
    pilot.CONFIG_PATH.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))

    # csv_dir IS present (BOM-stripped on read) — FileExistsError fires.
    with pytest.raises(FileExistsError):
        pilot._write_user_config("csv_dir", {"path": "/new"})

    # And sibling key is preserved across the round-trip.
    pilot._write_user_config("matlab_file", {"path": "/mat"})
    after = json.loads(pilot.CONFIG_PATH.read_text(encoding="utf-8"))
    assert after.get("max_hr") == 195
    assert after["csv_dir"]["path"] == "/existing"
    assert after["matlab_file"]["path"] == "/mat"


def test_user_config_json_write_sites_are_canonical() -> None:
    """v7.3.1 all-call-sites-sweep rule applied to user_config.json writers.

    The deep-merge invariant only holds if every writer of
    user_config.json either:
      (a) routes through ``pilot._write_user_config`` (the canonical
          deep-merge writer that preserves sibling top-level keys), OR
      (b) lives in a documented fresh-write context where there is no
          prior content to preserve (currently ``fitting_room.py`` and
          ``demo/runner.py``, both of which write to a freshly-staged
          target directory scoped to a tempdir or rmtree'd demo dir —
          NOT the operator's persistent ~/.tailor/user_config.json).

    A NEW write site → this test fails loudly. The author must either
    route through ``_write_user_config`` or extend ``KNOWN_WRITERS``
    with a citation explaining why fresh-write semantics are correct
    in that target's context. Closes the structural class of bug
    v7.3.0's F-A VIOLATION named: a new path silently breaks an
    invariant the diff did not declare.

    AST-class detection per v7.3.2 W5 precedent — the predicate checks
    the **target** of each write call (not co-occurrence of literal +
    write-call) so functions that READ user_config.json while writing
    to a *different* file (audit.db, claude_desktop_config.json) do
    NOT false-positive. The W5 lesson: a textual-window predicate is
    a grep-class trap; AST-class enforcement is strictly stronger.
    """
    import ast
    from pathlib import Path as _Path

    src_root = _Path(__file__).resolve().parent.parent / "src" / "tailor"

    # Known canonical writers. Any addition here requires a docstring
    # in the writer explaining why fresh-write is correct for its target.
    known_writers: set[tuple[str, str]] = {
        # The deep-merge canonical writer; this is the seam.
        ("pilot.py", "_write_user_config"),
        # Writes to <demo_dir>/user_config.json after --force rmtree;
        # scoped to TAILOR_CONFIG_DIR=<demo_dir>, not the operator's
        # persistent config. ADR 0024 § "Scaffolded demo isolation".
        ("fitting_room.py", "_write_user_config"),
        # Writes to <tempdir>/config/user_config.json inside a
        # tempfile.TemporaryDirectory(prefix="tailor-demo-"). Scoped
        # to a single demo-run lifetime; the tempdir does not survive
        # the function exit. Fresh-write is correct by construction.
        ("runner.py", "_write_demo_user_config"),
    }

    def _resolves_to_user_config(
        node: ast.AST,
        names_to_check: dict[str, ast.AST],
        depth: int = 0,
    ) -> bool:
        """Does ``node`` resolve to a path that references
        ``user_config.json``?

        Recurses through BinOp (path division), Attribute (method
        chain), Call (e.g. ``path.with_suffix(...)``), and Name (via
        the local assignment map). Depth-bound on Name resolution to
        avoid pathological self-references.
        """
        if depth > 10:
            return False
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return "user_config.json" in node.value
        if isinstance(node, ast.BinOp):
            return (
                _resolves_to_user_config(node.left, names_to_check, depth + 1)
                or _resolves_to_user_config(node.right, names_to_check, depth + 1)
            )
        if isinstance(node, ast.Name):
            if node.id in names_to_check:
                return _resolves_to_user_config(
                    names_to_check[node.id], names_to_check, depth + 1,
                )
            return False
        if isinstance(node, ast.Attribute):
            return _resolves_to_user_config(node.value, names_to_check, depth + 1)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                return _resolves_to_user_config(
                    node.func.value, names_to_check, depth + 1,
                )
            return False
        return False

    def _write_call_target(call: ast.Call) -> ast.AST | None:
        """Return the AST node representing the path being written,
        or None if this Call is not a known write operation."""
        func = call.func
        if isinstance(func, ast.Attribute):
            # path.write_text(...) or path.write_bytes(...)
            if func.attr in ("write_text", "write_bytes"):
                return func.value
            # os.replace(tmp, dest) — destination is the second arg
            if func.attr == "replace" and isinstance(func.value, ast.Name):
                if func.value.id == "os" and len(call.args) >= 2:
                    return call.args[1]
        elif isinstance(func, ast.Name):
            # _atomic_write_json(path, data)
            if func.id == "_atomic_write_json" and call.args:
                return call.args[0]
        return None

    found_writers: set[tuple[str, str]] = set()

    for py_file in src_root.rglob("*.py"):
        try:
            source = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        # Collect module-level names that resolve to user_config.json
        # paths (e.g. ``CONFIG_PATH = CONFIG_DIR / "user_config.json"``).
        module_names: dict[str, ast.AST] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        module_names[tgt.id] = node.value

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            # Build the local-assignment map for this function.
            scope_names: dict[str, ast.AST] = dict(module_names)
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    for tgt in sub.targets:
                        if isinstance(tgt, ast.Name):
                            scope_names[tgt.id] = sub.value

            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                target = _write_call_target(sub)
                if target is None:
                    continue
                if _resolves_to_user_config(target, scope_names):
                    found_writers.add((py_file.name, node.name))
                    break

    unknown = found_writers - known_writers
    assert not unknown, (
        f"New user_config.json write site(s) detected: {sorted(unknown)}.\n"
        f"Either route through pilot._write_user_config (the canonical "
        f"deep-merge writer) or extend KNOWN_WRITERS in this test with "
        f"a citation explaining why fresh-write semantics are correct "
        f"for the new target. See v7.5 F1 closure."
    )
    # Sanity: the known writers MUST still be present — guards against
    # someone deleting the canonical writer without thinking.
    assert known_writers <= found_writers, (
        f"Known user_config.json writer(s) disappeared: "
        f"{sorted(known_writers - found_writers)}. Refactor either added "
        f"a new seam (update KNOWN_WRITERS) or accidentally removed the "
        f"canonical writer."
    )

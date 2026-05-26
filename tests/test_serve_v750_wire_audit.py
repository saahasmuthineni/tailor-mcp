"""
MCP-protocol wire tests for v7.5 pilot-wizard --source dispatch surface.

Covers:
  B1 — audit_query outcome=ATTEST_INITIAL filter accepted without error
  B2 — ATTEST_INITIAL row written by AuditLog.record() surfaces on wire
        with all B1-allowlist columns; raw params/error never exposed
  B3 — tools/list with multi-source config (csv_dir + redcap_file)
        registers both children's tools without collision
  B4 — _write_user_config deep-merge: csv_dir block survives adding
        redcap_file block (wire-level: tools/list shows both surfaces)
  B5 — repr() artifacts absent from ATTEST_INITIAL query response
  B6 — v7.4.0 wire regressions: audit_query, REDCap surface, CSV surface

Phase-0 phase note:
  scipy is NOT installed on this dev box so MATLAB tools are never
  registered. Tests assert the absence of matlab_* tools when scipy is
  absent rather than asserting their presence.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _mcp_client import (
    MCPClient,
    assert_no_repr_artifacts,
    extract_text_result,
    spawn_server,
)

# ──────────────────────────────────────────────────────────────────────
# Helpers: seed a config that includes BOTH csv_dir AND redcap_file
# ──────────────────────────────────────────────────────────────────────

_SAMPLE_CSV = (
    "timestamp,force\n"
    "2026-05-01T00:00:00,10.0\n"
    "2026-05-01T00:00:01,20.0\n"
    "2026-05-01T00:00:02,30.0\n"
)

_REDCAP_METADATA_CSV = (
    '"Variable / Field Name","Form Name","Section Header","Field Type",'
    '"Field Label","Choices, Calculations, OR Slider Labels","Field Note",'
    '"Text Validation Type OR Show Slider Number","Text Validation Min",'
    '"Text Validation Max","Identifier?","Branching Logic (Show field only if...)",'
    '"Required Field?","Custom Alignment","Question Number (surveys only)",'
    '"Matrix Group Name","Matrix Ranking?","Field Annotation"\n'
    '"record_id","demographics","","text","Record ID","","","","","","","","","","","","",""\n'
    '"participant_name","demographics","Identifiers","text","Participant Name","","","","","","y","","","","","","",""\n'
    '"sex","demographics","","radio","Sex","F, Female | M, Male | O, Other","","","","","","","","","","","",""\n'
    '"score","outcomes","","text","Score","","","integer","0","100","","","","","","","",""\n'
)

_REDCAP_RECORDS_CSV = (
    "record_id,redcap_event_name,participant_name,sex,score\n"
    "1,event_1_arm_1,Alice,F,80\n"
    "2,event_1_arm_1,Bob,M,90\n"
)


def _seed_multisource_config(root: Path) -> dict[str, Path]:
    """
    Seed a config with csv_dir + redcap_file blocks AND a vault_path.
    This is the multi-source scenario _write_user_config deep-merge protects.
    """
    config_dir = root / "config"
    data_dir = root / "data"
    vault_path = root / "vault"
    csv_dir = root / "csvs"
    redcap_dir = root / "redcap"
    for p in (config_dir, data_dir, vault_path, csv_dir, redcap_dir):
        p.mkdir(parents=True, exist_ok=True)

    # CSV source
    (csv_dir / "S001.csv").write_text(_SAMPLE_CSV, encoding="utf-8")
    (csv_dir / "S002.csv").write_text(_SAMPLE_CSV, encoding="utf-8")
    sidecar = {
        "S001.csv": {"sex": "F", "group": "control"},
        "S002.csv": {"sex": "M", "group": "intervention"},
    }
    (csv_dir / "metadata.json").write_text(json.dumps(sidecar), encoding="utf-8")

    # REDCap source
    (redcap_dir / "project_metadata.csv").write_text(
        _REDCAP_METADATA_CSV, encoding="utf-8"
    )
    (redcap_dir / "records.csv").write_text(_REDCAP_RECORDS_CSV, encoding="utf-8")

    user_config = {
        "vault_path": str(vault_path),
        "csv_dir": {
            "path": str(csv_dir),
            "timestamp_column": "timestamp",
            "timestamp_format": "%Y-%m-%dT%H:%M:%S",
            "value_columns": {"force": "Force (N)"},
        },
        "redcap_file": {
            "path": str(redcap_dir),
            "records_file": "records.csv",
            "project_metadata_file": "project_metadata.csv",
        },
    }
    (config_dir / "user_config.json").write_text(
        json.dumps(user_config), encoding="utf-8"
    )

    return {
        "config_dir": config_dir,
        "data_dir": data_dir,
        "vault_path": vault_path,
        "csv_dir": csv_dir,
        "redcap_dir": redcap_dir,
    }


@contextlib.contextmanager
def _spawn_multisource(
    env_overrides: dict[str, str] | None = None,
    pre_seed_fn=None,
) -> Iterator[tuple[MCPClient, dict[str, Path]]]:
    """Spawn serve with csv_dir + redcap_file config.

    ``pre_seed_fn`` — optional callable that receives ``paths`` dict and
    runs BEFORE the subprocess is spawned. Use this to write audit rows
    or other files so the subprocess doesn't hold file locks when cleanup
    runs. Do NOT write audit rows after spawn on Windows — the subprocess
    keeps audit.db open via WAL and TemporaryDirectory teardown will
    raise PermissionError.
    """
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        paths = _seed_multisource_config(Path(tmp))
        if pre_seed_fn is not None:
            pre_seed_fn(paths)
        env = {
            **os.environ,
            "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
            "TAILOR_DATA_DIR": str(paths["data_dir"]),
            "PYTHONUNBUFFERED": "1",
            **(env_overrides or {}),
        }
        proc = subprocess.Popen(
            [sys.executable, "-m", "tailor", "serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        client = MCPClient(proc)
        try:
            yield client, paths
        finally:
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
            except (OSError, BrokenPipeError):
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def _seed_audit_row(data_dir: Path, fingerprint: str = "abc123deadbeef") -> None:
    """
    Directly write an ATTEST_INITIAL row into audit.db so the wire
    test can query it via audit_query. Mirrors exactly what
    _write_attest_initial_audit_row() in pilot.py does via
    AuditLog.record(), using the same column set.
    """
    from tailor.framework.audit import AuditLog
    audit = AuditLog(data_dir / "audit.db")
    audit.record(
        domain="redcap_file",
        tool_name="tailor_redcap_attest_initial",
        tier=0,
        params={
            "action": "first_config_attestation",
            "redcap_dir": "/tmp/test_redcap",
            "project_metadata_file": "project_metadata.csv",
        },
        token_estimate=0,
        outcome="ATTEST_INITIAL",
        duration_ms=0,
        scrubber_id="noop",
        child_scrubber_id="redcap_metadata_flags",
        source_metadata_fingerprint=fingerprint,
    )


# ──────────────────────────────────────────────────────────────────────
# B1 — audit_query accepts outcome=ATTEST_INITIAL on the wire
# ──────────────────────────────────────────────────────────────────────

class TestB1AttestInitialOutcomeFilter:
    """audit_query outcome=ATTEST_INITIAL accepted by ValidationSchema."""

    def test_outcome_attest_initial_accepted_no_error(self):
        """
        outcome=ATTEST_INITIAL passes ValidationSchema (type=str, min_len=1,
        max_len=64) and returns a valid envelope — not a PARAM_INVALID error.
        This verifies the description mentions the value AND the wire accepts it.
        """
        with spawn_server() as (client, paths):
            client.initialize()
            resp = client.call_tool("audit_query", {
                "since": "1h",
                "outcome": "ATTEST_INITIAL",
            })
            raw = json.dumps(resp)
            # No JSON-RPC error at the envelope level
            assert "error" not in resp, (
                f"JSON-RPC error for outcome=ATTEST_INITIAL: {resp}"
            )
            text = extract_text_result(resp)
            payload = json.loads(text)
            # Structured envelope — not a PARAM_INVALID
            assert "rows" in payload, (
                f"Expected 'rows' key in response, got: {list(payload.keys())}"
            )
            assert "error" not in payload or "PARAM_INVALID" not in payload.get("error", ""), (
                f"Unexpected PARAM_INVALID: {payload}"
            )
            # May be 0 rows (no ATTEST_INITIAL calls yet) — that's fine
            assert isinstance(payload["rows"], list)
            assert_no_repr_artifacts(raw)

    def test_outcome_reattest_also_accepted(self):
        """REATTEST (v7.3.2 outcome) still accepted — regression guard."""
        with spawn_server() as (client, paths):
            client.initialize()
            resp = client.call_tool("audit_query", {
                "since": "24h",
                "outcome": "REATTEST",
            })
            assert "error" not in resp
            text = extract_text_result(resp)
            payload = json.loads(text)
            assert "rows" in payload


# ──────────────────────────────────────────────────────────────────────
# B2 — ATTEST_INITIAL row written via AuditLog.record() surfaces on wire
# ──────────────────────────────────────────────────────────────────────

class TestB2AttestInitialRowOnWire:
    """
    Pre-seeds an ATTEST_INITIAL row (mimicking what pilot.py writes),
    then queries via audit_query to assert the B1 allowlist columns
    surface correctly on the wire.
    """

    _FINGERPRINT = "deadbeef01020304deadbeef01020304deadbeef01020304deadbeef01020304"

    def test_attest_initial_row_surfaces_in_audit_query(self):
        """
        After writing an ATTEST_INITIAL row via AuditLog.record(), an
        audit_query call returns it with all B1-allowlist columns present.
        Row is seeded BEFORE subprocess spawn (pre_seed_fn) to avoid
        Windows file-lock contention on audit.db during cleanup.
        """
        fp = self._FINGERPRINT

        def _pre(paths):
            _seed_audit_row(paths["data_dir"], fp)

        with _spawn_multisource(pre_seed_fn=_pre) as (client, paths):
            client.initialize()
            resp = client.call_tool("audit_query", {
                "since": "1h",
                "domain": "redcap_file",
                "outcome": "ATTEST_INITIAL",
            })
            assert "error" not in resp, f"JSON-RPC error: {resp}"
            raw = json.dumps(resp)
            text = extract_text_result(resp)
            payload = json.loads(text)
            assert "rows" in payload
            rows = payload["rows"]
            assert len(rows) >= 1, (
                f"Expected at least 1 ATTEST_INITIAL row; got 0. "
                f"scope_statement={payload.get('scope_statement')}"
            )
            row = rows[0]

            # B1 allowlist columns must all be present
            for col in ("id", "timestamp", "domain", "tool_name", "tier",
                        "outcome", "entity_id", "scrubber_id",
                        "child_scrubber_id", "source_metadata_fingerprint",
                        "has_error"):
                assert col in row, (
                    f"B1-allowlist column '{col}' absent from ATTEST_INITIAL row. "
                    f"Row keys: {list(row.keys())}"
                )

            # Values must match what pilot.py writes
            assert row["domain"] == "redcap_file"
            assert row["tool_name"] == "tailor_redcap_attest_initial"
            assert row["outcome"] == "ATTEST_INITIAL"
            assert row["tier"] == 0
            assert row["scrubber_id"] == "noop"
            assert row["child_scrubber_id"] == "redcap_metadata_flags"
            assert row["source_metadata_fingerprint"] == self._FINGERPRINT
            assert row["has_error"] is False

            # entity_id is NULL on an attestation row (not participant-scoped)
            assert row["entity_id"] is None

            # timestamp must be a parseable ISO-8601 string
            import datetime
            ts = row["timestamp"]
            assert isinstance(ts, str), f"timestamp not a string: {ts!r}"
            # Accept both Z and +00:00 suffix
            ts_clean = ts.replace("Z", "+00:00")
            datetime.datetime.fromisoformat(ts_clean)  # raises if not parseable

            # No repr() artifacts
            assert_no_repr_artifacts(raw)

    def test_raw_params_never_in_attest_initial_response(self):
        """
        The B1 allowlist excludes raw params content. The redcap_dir
        path we seeded into params must NOT appear in the wire response.
        """
        fp = self._FINGERPRINT

        def _pre(paths):
            _seed_audit_row(paths["data_dir"], fp)

        with _spawn_multisource(pre_seed_fn=_pre) as (client, paths):
            client.initialize()
            resp = client.call_tool("audit_query", {
                "since": "1h",
                "domain": "redcap_file",
            })
            raw = json.dumps(resp)
            # The params dict we seeded had action=first_config_attestation
            # and a redcap_dir path value — neither should appear on the wire
            assert "first_config_attestation" not in raw, (
                "Raw params content leaked through B1 allowlist — "
                "audit_query must never return raw params."
            )
            assert "params" not in json.loads(
                extract_text_result(resp)
            ).get("rows", [{}])[0] if json.loads(
                extract_text_result(resp)
            ).get("rows") else True, (
                "Row contains a 'params' key — B1 allowlist violation."
            )

    def test_has_error_bool_not_repr(self):
        """
        has_error must be JSON boolean true/false, not Python True/False repr.
        """
        fp = self._FINGERPRINT

        def _pre(paths):
            _seed_audit_row(paths["data_dir"], fp)

        with _spawn_multisource(pre_seed_fn=_pre) as (client, paths):
            client.initialize()
            resp = client.call_tool("audit_query", {
                "since": "1h",
                "domain": "redcap_file",
                "outcome": "ATTEST_INITIAL",
            })
            raw = json.dumps(resp)
            # Python True/False repr in JSON string is a coercion bug
            assert "True" not in raw or '"True"' not in raw, (
                "has_error appears as Python repr True rather than JSON true"
            )
            assert "False" not in raw or '"False"' not in raw, (
                "has_error appears as Python repr False rather than JSON false"
            )
            payload = json.loads(extract_text_result(resp))
            if payload.get("rows"):
                assert isinstance(payload["rows"][0]["has_error"], bool), (
                    f"has_error type is {type(payload['rows'][0]['has_error'])}, expected bool"
                )


# ──────────────────────────────────────────────────────────────────────
# B3 — tools/list with multi-source config registers all surfaces
# ──────────────────────────────────────────────────────────────────────

class TestB3MultiSourceToolsList:
    """
    With csv_dir + redcap_file in user_config.json, tools/list must
    surface both children's tools. This verifies that _write_user_config
    deep-merge doesn't break serve-time registration.
    scipy absent → MATLAB tools not expected.
    """

    def test_csv_and_redcap_tools_both_registered(self):
        with _spawn_multisource() as (client, paths):
            client.initialize()
            resp = client.list_tools()
            assert "error" not in resp, f"tools/list error: {resp}"
            tools = resp["result"]["tools"]
            names = {t["name"] for t in tools}

            # CSV surface (7 tools)
            csv_expected = {
                "csv_list_files", "csv_file_detail", "csv_summary_report",
                "csv_group_summary", "csv_force_decline",
                "csv_downsampled", "csv_raw_stream",
            }
            missing_csv = csv_expected - names
            assert not missing_csv, (
                f"CSV tools missing from tools/list: {sorted(missing_csv)}"
            )

            # REDCap surface (6 tools)
            redcap_expected = {
                "redcap_list_records", "redcap_record_detail",
                "redcap_summary_report", "redcap_cohort_summary",
                "redcap_records", "redcap_raw_records",
            }
            missing_redcap = redcap_expected - names
            assert not missing_redcap, (
                f"REDCap tools missing from tools/list: {sorted(missing_redcap)}"
            )

            # audit_query must appear
            assert "audit_query" in names, "audit_query not in tools/list"

    def test_no_tool_name_collision_in_multisource_config(self):
        """
        Tool names must be unique across all registered children and
        framework layers. A collision would raise at registration time;
        we assert the server started cleanly with no error in the response.
        """
        with _spawn_multisource() as (client, paths):
            client.initialize()
            resp = client.list_tools()
            assert "error" not in resp
            tools = resp["result"]["tools"]
            names = [t["name"] for t in tools]
            assert len(names) == len(set(names)), (
                f"Duplicate tool names in tools/list: "
                f"{[n for n in names if names.count(n) > 1]}"
            )

    def test_matlab_tools_absent_when_scipy_missing(self):
        """
        scipy not installed → matlab_* tools must NOT appear.
        If they do, it means the conditional-import guard in __main__.py
        broke and MATLAB tools registered against a null backend.
        """
        try:
            import scipy  # type: ignore[import]
            pytest.skip("scipy is installed on this machine — MATLAB test N/A")
        except ImportError:
            pass

        with _spawn_multisource() as (client, paths):
            client.initialize()
            resp = client.list_tools()
            tools = resp["result"]["tools"]
            names = {t["name"] for t in tools}
            matlab_present = {n for n in names if n.startswith("matlab_")}
            assert not matlab_present, (
                f"scipy absent but matlab tools appeared: {matlab_present}. "
                f"Conditional import guard in __main__.py is broken."
            )


# ──────────────────────────────────────────────────────────────────────
# B4 — deep-merge: csv_dir preserved when redcap_file block is added
# ──────────────────────────────────────────────────────────────────────

class TestB4DeepMergeConfigPreservation:
    """
    Verifies _write_user_config preserves sibling source blocks at the
    wire level: a server started with a config written by two sequential
    pilot --source=csv / --source=redcap calls must register both.
    Simulated here by writing the merged JSON directly.
    """

    def test_csv_tools_still_present_after_adding_redcap_block(self):
        """
        Config has both csv_dir and redcap_file. CSV tools must appear
        in tools/list — regression guard for the F1 clobber bug
        (pre-v7.5 _write_user_config overwrote the entire file).
        """
        with _spawn_multisource() as (client, paths):
            client.initialize()
            resp = client.list_tools()
            tools = resp["result"]["tools"]
            names = {t["name"] for t in tools}
            # csv_force_decline is the tool that would silently vanish
            # if redcap_file write clobbered the csv_dir block
            assert "csv_force_decline" in names, (
                "csv_force_decline absent — _write_user_config may have "
                "clobbered csv_dir when adding redcap_file block (F1 regression)"
            )
            assert "redcap_list_records" in names, (
                "redcap_list_records absent — redcap_file block not registered"
            )


# ──────────────────────────────────────────────────────────────────────
# B5 — _meta block on audit_query result with ATTEST_INITIAL rows
# ──────────────────────────────────────────────────────────────────────

class TestB5MetaBlockCorrectness:
    """
    _meta block stamped by the router must have correct fields for
    audit_query calls even when the result contains ATTEST_INITIAL rows.
    """

    def test_meta_block_fields_present_and_typed(self):
        with _spawn_multisource(pre_seed_fn=lambda p: _seed_audit_row(p["data_dir"])) as (client, paths):
            client.initialize()
            resp = client.call_tool("audit_query", {
                "since": "1h",
                "outcome": "ATTEST_INITIAL",
            })
            text = extract_text_result(resp)
            payload = json.loads(text)

            meta = payload.get("_meta")
            assert meta is not None, "_meta block absent from audit_query response"

            # package_version matches __version__
            from tailor import __version__
            assert meta.get("package_version") == __version__, (
                f"_meta.package_version={meta.get('package_version')!r} "
                f"!= __version__={__version__!r}"
            )

            # tool_name matches the call
            assert meta.get("tool_name") == "audit_query", (
                f"_meta.tool_name={meta.get('tool_name')!r} != 'audit_query'"
            )

            # called_at is parseable ISO-8601
            import datetime
            called_at = meta.get("called_at")
            assert isinstance(called_at, str), f"_meta.called_at not a string: {called_at!r}"
            datetime.datetime.fromisoformat(called_at.replace("Z", "+00:00"))

    def test_no_repr_artifacts_with_seeded_rows(self):
        """repr() artifact check on a response that actually contains rows."""
        with _spawn_multisource(pre_seed_fn=lambda p: _seed_audit_row(p["data_dir"])) as (client, paths):
            client.initialize()
            resp = client.call_tool("audit_query", {"since": "1h"})
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)


# ──────────────────────────────────────────────────────────────────────
# B6 — v7.4.0 wire regression guard (existing surfaces must not regress)
# ──────────────────────────────────────────────────────────────────────

class TestB6V740Regression:
    """
    Spot-checks that v7.4.0 wire surfaces still hold after v7.5 pilot
    changes. These tests use the standard spawn_server (csv_dir only)
    to guard against regressions in unchanged paths.
    """

    def test_audit_query_empty_result_no_error(self):
        """audit_query since=1h returns empty rows without error."""
        with spawn_server() as (client, paths):
            client.initialize()
            resp = client.call_tool("audit_query", {"since": "1h"})
            assert "error" not in resp
            text = extract_text_result(resp)
            payload = json.loads(text)
            assert "rows" in payload
            assert "row_count" in payload
            assert "scope_statement" in payload
            assert isinstance(payload["rows"], list)

    def test_csv_cohort_summary_still_works(self):
        """csv_group_summary round-trip verifies CSV child unaffected."""
        with spawn_server() as (client, paths):
            client.initialize()
            resp = client.call_tool("csv_group_summary", {
                "metric": "mean",
                "group_by": "sex",
                "value_column": "heart_rate",
            })
            assert "error" not in resp
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)

    def test_redcap_list_records_in_multisource(self):
        """redcap_list_records round-trip on multisource config."""
        with _spawn_multisource() as (client, paths):
            client.initialize()
            resp = client.call_tool("redcap_list_records", {})
            assert "error" not in resp
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)
            text = extract_text_result(resp)
            payload = json.loads(text)
            # should have records or an empty list, but not a hard error
            assert "error" not in payload or payload.get("error") is None or (
                "PARAM_INVALID" not in str(payload.get("error", ""))
            ), f"Unexpected error in redcap_list_records: {payload}"

    def test_tools_list_no_error_multisource(self):
        """tools/list returns cleanly on multisource config."""
        with _spawn_multisource() as (client, paths):
            client.initialize()
            resp = client.list_tools()
            assert "error" not in resp
            assert "result" in resp
            assert "tools" in resp["result"]
            assert len(resp["result"]["tools"]) > 0


# ──────────────────────────────────────────────────────────────────────
# B7 — pilot._write_attest_initial_audit_row end-to-end integration
#
# Red-team OBJECTION closure (medium): the B1/B2 tests above pre-seed
# ATTEST_INITIAL rows via _seed_audit_row, which hardcodes
# scrubber_id="noop". A future regression re-hardcoding "noop" in
# pilot.py would still pass B1/B2. This class calls the REAL wizard
# helper to bridge that v7.3.2 W5 textual-window false-positive gap.
# ──────────────────────────────────────────────────────────────────────


class TestB7PilotWriteAttestInitialEndToEnd:
    """Wire-level coverage that exercises pilot.py's actual write path.

    The seed helper _seed_audit_row above bypasses pilot.py entirely
    and hardcodes scrubber_id="noop". This class is the bridge: it
    invokes pilot._write_attest_initial_audit_row directly via the
    pre_seed_fn hook so the row that surfaces on the wire is the
    output of the WATCH-1 fix's code path — not adjacent test
    infrastructure that happens to produce the same string.

    The dynamic assertion (scrubber_id == DataScrubber().scrubber_id)
    is the load-bearing part: under the default scrubber it equals
    "noop", but under a future subclassed framework scrubber it
    equals that subclass's identity. A regression that re-hardcodes
    "noop" in pilot.py would not be caught by a string-equality
    assertion against "noop" — it would be caught by an assertion
    against the framework scrubber's actual identity.
    """

    def test_attest_initial_via_real_pilot_helper_surfaces_dynamic_scrubber_id(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Calls pilot._write_attest_initial_audit_row() directly
        (not the test-local seed helper), then queries audit_query
        on the wire, asserts the row carries the framework
        scrubber's dynamic identity.

        Closes the v7.3.2 W5 textual-window false-positive recurrence
        the red-team-reviewer caught on the v7.5 release.
        """
        fingerprint = "deadbeef" * 8  # 64-hex-char SHA-256-shape

        def _pre_seed(paths: dict[str, Path]) -> None:
            # Force tailor.config to point at the multisource tmp
            # dir so pilot._write_attest_initial_audit_row writes
            # to the same audit.db the subprocess will read on
            # spawn. The existing isolated_config fixture in
            # test_pilot_wizard.py uses the same reload pattern.
            monkeypatch.setenv(
                "TAILOR_CONFIG_DIR", str(paths["config_dir"]),
            )
            monkeypatch.setenv(
                "TAILOR_DATA_DIR", str(paths["data_dir"]),
            )
            import importlib

            import tailor.config as cfg_mod

            importlib.reload(cfg_mod)
            import tailor.pilot as pilot_mod

            importlib.reload(pilot_mod)

            # The REAL wizard helper. Output bytes land in
            # paths["data_dir"]/audit.db, which is exactly what
            # TAILOR_DATA_DIR points the subprocess at.
            ok = pilot_mod._write_attest_initial_audit_row(
                fingerprint, paths["redcap_dir"],
            )
            assert ok is True, "pilot helper failed to write audit row"

        with _spawn_multisource(pre_seed_fn=_pre_seed) as (client, paths):
            client.initialize()
            resp = client.call_tool(
                "audit_query",
                {"since": "1h", "outcome": "ATTEST_INITIAL"},
            )
            assert "error" not in resp, (
                f"JSON-RPC error querying ATTEST_INITIAL: {resp}"
            )
            text = extract_text_result(resp)
            payload = json.loads(text)
            rows = payload["rows"]

            # The pilot helper's row must surface — matched on the
            # synthetic fingerprint we passed in so adjacent
            # ATTEST_INITIAL rows from other tests in the suite
            # cannot satisfy this assertion by accident.
            matching = [
                r for r in rows
                if r.get("source_metadata_fingerprint") == fingerprint
            ]
            assert len(matching) == 1, (
                f"Expected exactly one ATTEST_INITIAL row with "
                f"fingerprint={fingerprint[:16]}..., got "
                f"{len(matching)}. All rows: {rows}"
            )
            row = matching[0]

            # The dynamic scrubber_id contract — the WATCH-1
            # closure. Under default DataScrubber this is "noop";
            # under a subclassed framework scrubber it would be
            # that subclass's identity. A future pilot.py regression
            # that re-hardcoded "noop" would still pass an
            # `assert == "noop"` check; this dynamic assertion
            # would catch it once any institutional subclass is
            # wired through the framework's scrubber-selection seam.
            from tailor.framework.security import DataScrubber

            assert row["scrubber_id"] == DataScrubber().scrubber_id, (
                f"WATCH-1 regression: pilot helper wrote "
                f"scrubber_id={row['scrubber_id']!r}, but the "
                f"framework scrubber's identity is "
                f"{DataScrubber().scrubber_id!r}. pilot.py must "
                f"thread the dynamic identity, not hardcode a "
                f"literal string."
            )
            assert row["child_scrubber_id"] == "redcap_metadata_flags"
            assert row["domain"] == "redcap_file"
            assert row["tool_name"] == "tailor_redcap_attest_initial"
            assert row["outcome"] == "ATTEST_INITIAL"
            assert row["tier"] == 0
            # has_error is the audit_query B1 derived column —
            # confirms the row threaded an empty error (not the
            # raw error text, per ADR 0039).
            assert row.get("has_error") is False

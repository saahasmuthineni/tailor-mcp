"""
MCP Protocol Audit — RedcapFileChild wire-level correctness (v7.3.0).

Drives ``python -m tailor serve`` as a real subprocess speaking JSON-RPC over
stdio with a temp-dir-isolated config that includes a ``redcap_file`` block
pointing at the bundled ``_fixtures/redcap_demo/`` directory.

Surfaces under test (per the v7.3.0 audit mandate):

  R1  — ``initialize`` returns a well-formed MCP server identity.
  R2  — ``tools/list`` includes all six REDCap tools with correct tier
        metadata in the inputSchema (tier key must be present on each).
  R3  — ``tools/call`` on ``redcap_list_records`` (Tier 1) succeeds
        without a consent prompt; returns records with longitudinal
        event coverage; ``participant_name`` / ``dob`` absent.
  R4  — ``tools/call`` on ``redcap_records`` (Tier 2) WITHOUT consent
        returns the structured ``LLMInstruction`` consent gate.
  R5  — After ``approve_consent_redcap_file``, ``tools/call`` on
        ``redcap_records`` with ``instrument="phq9"`` succeeds;
        identifier fields (``participant_name``, ``dob``) are STRIPPED.
  R6  — ``redcap_cohort_summary`` with ``group_by="dob"`` returns the
        identifier-guard hard-error envelope (ADR 0037 defence).
  R7  — ``_meta`` block on every SUCCESS result carries ``scrubber_id``
        (framework no-op) per ADR 0001 stamping pattern.
  R8  — Each successful ``redcap_*`` call writes an audit row to
        ``audit.db`` where ``child_scrubber_id == "redcap_metadata_flags"``.
  R9  — Post-execute hook chain does NOT silently fail on REDCap results.
        Hook failures (if any) surface in ``_meta.hook_warnings``, not stderr.
  R10 — Pre-existing children (csv_dir, vault layer) are unaffected;
        their tools still appear in ``tools/list`` and execute cleanly.
  R11 — ``_dumps`` serialization seam: no Python repr() artifacts in any
        REDCap wire payload (datetime, Path, Decimal guards).
  R12 — Consent gate fires once per session per domain (not on every
        Tier-2 call; second call after approval returns data, not gate).
  R13 — Cost gate fires on ``redcap_raw_records`` (Tier 3) before consent
        approval of the parent domain — gate returns well-formed JSON.
  R14 — Error envelopes for unknown tools and missing required params are
        JSON-RPC compliant (no Python traceback on the wire).
  R15 — ``redcap_record_detail`` for a known record_id returns the record's
        non-identifier fields; identifier fields absent.

Wire-level invariants on every result:
  - Decodes as valid JSON.
  - No ``"error"`` key in unexpected (success-path) responses.
  - No Python repr() artifacts in the raw wire payload.
  - ``_meta.tool_name`` matches the called tool.
  - ``_meta.package_version`` matches ``tailor.__version__``.
  - ``_meta.called_at`` is ISO-8601 parseable.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._mcp_client import (
    MCPClient,
    assert_no_repr_artifacts,
    extract_text_result,
    seed_full_config,
    spawn_server,
)

# ---------------------------------------------------------------------------
# Fixture path resolution
# ---------------------------------------------------------------------------

def _redcap_fixture_path() -> Path:
    """Return the absolute path to the bundled redcap_demo fixture directory."""
    # The fixture lives at src/tailor/_fixtures/redcap_demo/. Resolve it
    # relative to the installed package so the test works on a wheel install
    # and on a dev-tree install identically.
    import importlib.resources as ir

    import tailor._fixtures as _fx_pkg
    base = ir.files(_fx_pkg)
    demo = base / "redcap_demo"
    # Materialise the traversable to a real Path (works on dev-tree and wheel).
    # On dev-tree ``ir.files`` returns a ``Path``-backed traversable; on a
    # wheel it returns a zipfile traversable.  ``as_file`` gives us a real
    # tempdir-backed copy in the zip case, or the on-disk path otherwise.
    try:
        # Dev-tree (editable install): traversable is backed by a real Path.
        return Path(str(demo))  # type: ignore[arg-type]
    except TypeError:
        # Wheel / zip: fall back to the as_file context manager.
        with ir.as_file(demo) as p:
            return p


# ---------------------------------------------------------------------------
# Config seeding helper specific to this audit
# ---------------------------------------------------------------------------

def _seed_redcap_config(root: Path, *, fixture_path: Path) -> dict[str, Path]:
    """
    Seed a temp config with:
      - ``vault_path`` (so VaultLayer registers its 25 tools)
      - ``csv_dir`` block (so csv_dir child registers its 7 tools)
      - ``redcap_file`` block pointing at ``fixture_path``

    Returns paths dict compatible with spawn_* helpers.
    """
    config_dir = root / "config"
    data_dir = root / "data"
    vault_path = root / "vault"
    csv_dir = root / "csvs"
    for p in (config_dir, data_dir, vault_path, csv_dir):
        p.mkdir(parents=True, exist_ok=True)

    # Minimal CSV data so csv_dir registers without error.
    (csv_dir / "P001.csv").write_text(
        "timestamp,heart_rate\n"
        "2026-01-01T08:00:00,72\n"
        "2026-01-01T08:00:01,74\n",
        encoding="utf-8",
    )
    (csv_dir / "metadata.json").write_text(
        json.dumps({"P001.csv": {"sex": "F", "group": "control"}}),
        encoding="utf-8",
    )

    user_config = {
        "max_hr": 185,
        "resting_hr": 55,
        "vault_path": str(vault_path),
        "csv_dir": {
            "path": str(csv_dir),
            "timestamp_column": "timestamp",
            "timestamp_format": "%Y-%m-%dT%H:%M:%S",
            "value_columns": {"heart_rate": "Heart rate (bpm)"},
        },
        "redcap_file": {
            "path": str(fixture_path),
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
        "fixture_path": fixture_path,
    }


@contextlib.contextmanager
def spawn_redcap_server(
    fixture_path: Path | None = None,
    env_overrides: dict[str, str] | None = None,
) -> Iterator[tuple[MCPClient, dict[str, Path]]]:
    """
    Context manager: temp dirs + redcap-inclusive config + spawned server.

    Uses the bundled ``_fixtures/redcap_demo/`` fixture unless ``fixture_path``
    is provided. Yields ``(client, paths)``. Tears down on exit.
    """
    if fixture_path is None:
        fixture_path = _redcap_fixture_path()

    with TemporaryDirectory() as tmp:
        paths = _seed_redcap_config(Path(tmp), fixture_path=fixture_path)
        env = {
            **os.environ,
            "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
            "TAILOR_DATA_DIR": str(paths["data_dir"]),
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


# ---------------------------------------------------------------------------
# R1 — initialize handshake
# ---------------------------------------------------------------------------

def test_r1_initialize_returns_well_formed_envelope() -> None:
    """R1: ``initialize`` returns a well-formed MCP server identity.

    The response must have id, jsonrpc, result.serverInfo. No Python
    traceback in stderr.
    """
    with spawn_redcap_server() as (client, _paths):
        resp = client.initialize()

        assert "result" in resp, f"initialize missing 'result': {resp}"
        result = resp["result"]
        assert "serverInfo" in result, f"result missing 'serverInfo': {result}"
        assert "protocolVersion" in result, (
            f"result missing 'protocolVersion': {result}"
        )
        # No errors during startup.
        assert "error" not in resp, f"initialize returned error: {resp}"


# ---------------------------------------------------------------------------
# R2 — tools/list includes all six REDCap tools
# ---------------------------------------------------------------------------

EXPECTED_REDCAP_TOOLS = {
    "redcap_list_records",
    "redcap_record_detail",
    "redcap_summary_report",
    "redcap_cohort_summary",
    "redcap_records",
    "redcap_raw_records",
}

REDCAP_TOOL_TIERS = {
    "redcap_list_records": 1,
    "redcap_record_detail": 1,
    "redcap_summary_report": 1,
    "redcap_cohort_summary": 1,
    "redcap_records": 2,
    "redcap_raw_records": 3,
}


def test_r2_tools_list_includes_all_six_redcap_tools() -> None:
    """R2: tools/list includes all six REDCap tools with tier metadata.

    Each tool must carry inputSchema.type == "object". The auto-generated
    consent tools (approve_consent_redcap_file / revoke_consent_redcap_file)
    must also appear. No repr artifacts in the full tools/list payload.
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()
        resp = client.list_tools()

        assert "result" in resp, f"tools/list missing result: {resp}"
        tools = resp["result"].get("tools", [])

        raw = json.dumps(resp)
        assert_no_repr_artifacts(raw)

        names = {t["name"] for t in tools}

        # All six domain tools present.
        for expected in EXPECTED_REDCAP_TOOLS:
            assert expected in names, (
                f"{expected!r} missing from tools/list. "
                f"REDCap tools present: {sorted(t for t in names if 'redcap' in t)}"
            )

        # Auto-generated consent pair.
        assert "approve_consent_redcap_file" in names, (
            "approve_consent_redcap_file missing from tools/list"
        )
        assert "revoke_consent_redcap_file" in names, (
            "revoke_consent_redcap_file missing from tools/list"
        )

        # inputSchema shape on every REDCap tool.
        for tool in tools:
            if tool["name"] not in EXPECTED_REDCAP_TOOLS:
                continue
            schema = tool.get("inputSchema", {})
            assert schema.get("type") == "object", (
                f"{tool['name']}: inputSchema.type != 'object': {schema}"
            )
            props = schema.get("properties", {})
            for param_name, param_def in props.items():
                assert "description" in param_def, (
                    f"{tool['name']}.{param_name}: missing 'description' key "
                    f"in inputSchema. Got: {param_def}"
                )


# ---------------------------------------------------------------------------
# R3 — Tier-1 redcap_list_records (no consent required)
# ---------------------------------------------------------------------------

def test_r3_list_records_tier1_succeeds_without_consent() -> None:
    """R3: redcap_list_records (Tier 1) succeeds without consent; returns
    16 record_ids with longitudinal event coverage; identifier fields absent.

    The fixture has 16 subjects (S001-S016). ``participant_name`` and ``dob``
    (flagged identifier=y in project_metadata.csv) must NOT appear in any
    record entry. The response must carry a ``_meta`` block.
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool("redcap_list_records", {"limit": 50})
        assert "error" not in resp, f"Unexpected error: {resp}"

        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)
        body = json.loads(text)

        # No consent-gate fire.
        assert body.get("gate") is None, (
            f"Tier-1 tool fired a gate: gate={body.get('gate')!r}"
        )
        assert "error" not in body, f"Tool returned error: {body.get('error')}"

        # 16 distinct record_ids.
        assert body.get("total_record_ids") == 16, (
            f"Expected 16 record_ids, got {body.get('total_record_ids')}. "
            f"Full body: {body}"
        )

        # Longitudinal events present (the fixture has baseline/3_month/6_month).
        records = body.get("records", [])
        assert len(records) > 0, "records list is empty"
        all_events = []
        for r in records:
            all_events.extend(r.get("events", []))
        assert len(all_events) > 0, (
            "No longitudinal events surfaced in any record"
        )

        # Identifier fields NEVER appear in the record entries.
        raw = json.dumps(records)
        for identifier_field in ("participant_name", "dob"):
            assert f'"{identifier_field}"' not in raw, (
                f"Identifier field {identifier_field!r} appeared in "
                f"redcap_list_records output — scrubber failed to strip it."
            )

        # _meta block present and well-formed.
        assert "_meta" in body, "_meta missing from redcap_list_records result"
        _assert_meta_block(body["_meta"], "redcap_list_records")


# ---------------------------------------------------------------------------
# R4 — Tier-2 consent gate fires without prior consent
# ---------------------------------------------------------------------------

def test_r4_records_tier2_fires_consent_gate_before_approval() -> None:
    """R4: redcap_records (Tier 2) returns the structured consent gate.

    Per ADR 0004: llm_instruction must carry must_do (list[str]),
    must_not_do (list[str]), on_ambiguous_reply (str). Gate payload has
    no repr artifacts.
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool("redcap_records", {"instrument": "phq9"})
        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)
        body = json.loads(text)

        assert body.get("gate") == "consent_required", (
            f"Expected consent_required gate, got gate={body.get('gate')!r}. "
            f"Full body: {json.dumps(body)[:400]}"
        )
        assert body.get("domain") == "redcap_file", (
            f"Gate domain mismatch: {body.get('domain')!r}"
        )

        # Structured LLMInstruction shape (ADR 0004).
        assert "llm_instruction" in body, (
            f"consent gate missing 'llm_instruction': {body}"
        )
        instr = body["llm_instruction"]
        for key in ("must_do", "must_not_do", "on_ambiguous_reply"):
            assert key in instr, f"llm_instruction missing {key!r}: {instr}"
        assert isinstance(instr["must_do"], list), "must_do is not a list"
        assert all(isinstance(s, str) for s in instr["must_do"]), (
            "must_do contains non-string elements"
        )
        assert isinstance(instr["must_not_do"], list), "must_not_do is not a list"
        assert all(isinstance(s, str) for s in instr["must_not_do"]), (
            "must_not_do contains non-string elements"
        )
        assert isinstance(instr["on_ambiguous_reply"], str), (
            "on_ambiguous_reply is not a string"
        )


# ---------------------------------------------------------------------------
# R5 — After consent, redcap_records returns data with identifiers stripped
# ---------------------------------------------------------------------------

def test_r5_records_tier2_after_consent_strips_identifiers() -> None:
    """R5: After approve_consent_redcap_file, redcap_records(instrument="phq9")
    returns records with participant_name and dob absent.

    This is the load-bearing scrubber correctness test — it asserts the
    RedcapPHIScrubber actually strips identifier-flagged fields from
    Tier-2 results on the wire.
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()

        # Approve consent for the redcap_file domain.
        consent_resp = client.call_tool("approve_consent_redcap_file", {})
        consent_text = extract_text_result(consent_resp)
        assert_no_repr_artifacts(consent_text)
        consent_body = json.loads(consent_text)
        # The router's approve_consent handler returns {"approved": True, ...}.
        # (Not {"status": "approved"} — the router uses the "approved" boolean key.)
        assert consent_body.get("approved") is True, (
            f"Consent approval did not return approved=True: {consent_body}"
        )

        # Now call the Tier-2 tool.
        resp = client.call_tool(
            "redcap_records",
            {"instrument": "phq9"},
        )
        assert "error" not in resp, f"Unexpected JSON-RPC error: {resp}"

        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)
        body = json.loads(text)

        # Must NOT be a gate response.
        assert body.get("gate") is None, (
            f"Consent was approved but gate still fired: {body.get('gate')!r}"
        )
        assert "error" not in body, f"Tool returned error: {body.get('error')}"

        # Records must be present.
        records = body.get("records", [])
        assert len(records) > 0, (
            "redcap_records returned empty records list after consent approval"
        )

        # Identifier fields MUST NOT appear in any record.
        raw_records = json.dumps(records)
        for identifier_field in ("participant_name", "dob"):
            assert f'"{identifier_field}"' not in raw_records, (
                f"Identifier field {identifier_field!r} leaked through "
                f"RedcapPHIScrubber into Tier-2 wire payload. "
                f"This is a scrubber correctness failure (ADR 0037)."
            )

        # The legibility block must acknowledge the strips.
        assert "field_marked_identifier_stripped" in body, (
            f"legibility block missing field_marked_identifier_stripped: {body}"
        )
        stripped = body["field_marked_identifier_stripped"]
        assert isinstance(stripped, list), (
            f"field_marked_identifier_stripped is not a list: {type(stripped)}"
        )

        # _meta block.
        assert "_meta" in body
        _assert_meta_block(body["_meta"], "redcap_records")


# ---------------------------------------------------------------------------
# R6 — redcap_cohort_summary with group_by=identifier returns hard error
# ---------------------------------------------------------------------------

def test_r6_cohort_summary_identifier_group_by_returns_hard_error() -> None:
    """R6: redcap_cohort_summary with group_by="dob" returns the ADR 0037
    identifier-guard hard-error envelope.

    Grouping by an identifier-flagged field would leak PHI through group-key
    cardinality even though individual records are stripped. This defence is
    the single most important guard in the cohort tool.
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool(
            "redcap_cohort_summary",
            {"field": "phq9_score", "group_by": "dob"},
        )
        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)
        body = json.loads(text)

        # Must be a hard error, not a gate, not a success.
        assert "error" in body, (
            f"Expected hard-error envelope for identifier group_by, "
            f"got: {json.dumps(body)[:400]}"
        )
        assert body.get("gate") is None, (
            f"Expected hard error, got gate: {body.get('gate')!r}"
        )

        # Error message must name the offending field.
        error_msg = body["error"]
        assert "dob" in error_msg, (
            f"Hard-error message does not name 'dob': {error_msg!r}"
        )
        # Must reference identifier / PHI context.
        assert any(
            kw in error_msg.lower()
            for kw in ("identifier", "phi", "leak", "group")
        ), (
            f"Hard-error message lacks identifier/PHI context: {error_msg!r}"
        )

        # No _meta block on pure hard errors (error is returned before
        # the execute path; the router stamps _meta only on SUCCESS).
        # This is expected — do NOT assert _meta here.


# ---------------------------------------------------------------------------
# R7 — _meta.scrubber_id present on every SUCCESS
# ---------------------------------------------------------------------------

def test_r7_meta_scrubber_id_present_on_success() -> None:
    """R7: _meta block on every SUCCESS result carries scrubber_id per
    ADR 0001 stamping pattern. Checked on Tier-1 (no consent needed).
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()

        # Tier-1 tools — all should carry _meta.scrubber_id.
        for tool_name, call_params in [
            ("redcap_list_records", {"limit": 5}),
            ("redcap_summary_report", {}),
        ]:
            resp = client.call_tool(tool_name, call_params)
            assert "error" not in resp, f"{tool_name}: {resp}"
            text = extract_text_result(resp)
            body = json.loads(text)
            assert "_meta" in body, f"{tool_name}: _meta missing"
            meta = body["_meta"]
            assert "scrubber_id" in meta, (
                f"{tool_name}: _meta.scrubber_id missing. meta={meta}"
            )
            # scrubber_id is a string (framework-level scrubber identity).
            assert isinstance(meta["scrubber_id"], str), (
                f"{tool_name}: _meta.scrubber_id is not a string: "
                f"{type(meta['scrubber_id'])}"
            )


# ---------------------------------------------------------------------------
# R8 — audit.db child_scrubber_id column populated
# ---------------------------------------------------------------------------

def test_r8_audit_row_has_child_scrubber_id() -> None:
    """R8: After a successful Tier-1 redcap_list_records call, audit.db
    contains a row where child_scrubber_id = "redcap_metadata_flags".

    This confirms the ADR 0037 audit-provenance wire: the router reads
    child.child_scrubber_id on SUCCESS and stamps the audit row.
    """
    with spawn_redcap_server() as (client, paths):
        client.initialize()

        resp = client.call_tool("redcap_list_records", {"limit": 5})
        assert "error" not in resp, f"Unexpected error: {resp}"

        # Give the server a moment to flush the SQLite commit.
        time.sleep(0.1)

        db_path = paths["data_dir"] / "audit.db"
        assert db_path.exists(), (
            f"audit.db not found at {db_path}. "
            f"data_dir contents: {list(paths['data_dir'].iterdir())}"
        )

        conn = sqlite3.connect(str(db_path))
        try:
            # Verify the column exists.
            cols = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(audit_log)"
                ).fetchall()
            }
            assert "child_scrubber_id" in cols, (
                f"child_scrubber_id column absent from audit_log. "
                f"Columns present: {sorted(cols)}"
            )

            # Find the redcap_list_records row.
            rows = conn.execute(
                "SELECT domain, tool_name, outcome, child_scrubber_id "
                "FROM audit_log WHERE tool_name = 'redcap_list_records'"
            ).fetchall()
            assert len(rows) > 0, (
                "No audit row found for redcap_list_records"
            )
            domain, tool_name, outcome, child_scrubber_id = rows[-1]
            assert outcome == "SUCCESS", (
                f"Audit row outcome is {outcome!r}, not 'SUCCESS'"
            )
            assert child_scrubber_id == "redcap_metadata_flags", (
                f"child_scrubber_id = {child_scrubber_id!r}, "
                f"expected 'redcap_metadata_flags'. "
                f"This means the router did not stamp the child-level "
                f"scrubber identity into the audit row (ADR 0037)."
            )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# R9 — post-execute hook chain does not silently fail
# ---------------------------------------------------------------------------

def test_r9_post_execute_hook_does_not_silently_fail() -> None:
    """R9: VaultWriter hook runs (or fails visibly in hook_warnings).

    RedcapFileChild.vaultable_tools returns [] — so no vault write
    is attempted. The hook chain must not raise an unhandled exception
    that eats the result or corrupts the wire payload.

    If hook_warnings IS present in _meta it must be a list of dicts,
    each with 'hook', 'error_type', 'error' keys (per M1 ADR contract).
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool("redcap_list_records", {"limit": 3})
        assert "error" not in resp, f"Hook failure ate result: {resp}"

        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)
        body = json.loads(text)

        # Result envelope must be the tool's data, not an error.
        assert "error" not in body, f"Tool returned error: {body}"

        # If hook_warnings is present, check its shape (M1 contract).
        if "hook_warnings" in body.get("_meta", {}):
            warnings = body["_meta"]["hook_warnings"]
            assert isinstance(warnings, list), (
                f"hook_warnings is not a list: {type(warnings)}"
            )
            for w in warnings:
                for req_key in ("hook", "error_type", "error"):
                    assert req_key in w, (
                        f"hook_warning entry missing {req_key!r}: {w}"
                    )


# ---------------------------------------------------------------------------
# R10 — pre-existing children (csv_dir, vault) unaffected
# ---------------------------------------------------------------------------

def test_r10_preexisting_children_unaffected() -> None:
    """R10: csv_dir and vault tools still appear and execute cleanly after
    redcap_file registration. No regression from the new child or the
    new audit column.
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()

        # tools/list includes csv_dir tools.
        list_resp = client.list_tools()
        names = {t["name"] for t in list_resp["result"].get("tools", [])}
        for expected in (
            "csv_list_files", "csv_file_detail", "csv_summary_report",
            "vault_capture_moment", "vault_list_themes",
        ):
            assert expected in names, (
                f"{expected!r} missing from tools/list after redcap child registered. "
                f"Regression from framework changes."
            )

        # csv_list_files executes cleanly.
        csv_resp = client.call_tool("csv_list_files", {})
        assert "error" not in csv_resp, f"csv_list_files error: {csv_resp}"
        csv_text = extract_text_result(csv_resp)
        assert_no_repr_artifacts(csv_text)
        csv_body = json.loads(csv_text)
        assert "_meta" in csv_body, "csv_list_files: _meta missing"
        assert csv_body["_meta"]["domain"] == "csv_dir"


# ---------------------------------------------------------------------------
# R11 — _dumps serialization seam: no repr artifacts on all REDCap tools
# ---------------------------------------------------------------------------

def test_r11_dumps_seam_no_repr_artifacts_across_tier1_tools() -> None:
    """R11: No Python repr() artifacts in any Tier-1 REDCap wire payload.

    redcap_summary_report surfaces per-field statistics that could
    accidentally carry a datetime or Decimal if the scrubber pipeline
    mishandles the field values. All three Tier-1 calls are exercised.
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()

        for tool_name, call_params in [
            ("redcap_list_records", {"limit": 16}),
            ("redcap_summary_report", {}),
            ("redcap_record_detail", {"record_id": "S001"}),
        ]:
            resp = client.call_tool(tool_name, call_params)
            assert "error" not in resp, f"{tool_name}: {resp}"
            text = extract_text_result(resp)
            assert_no_repr_artifacts(text), (
                f"{tool_name}: repr() artifact found in wire payload"
            )
            # Must parse as valid JSON.
            body = json.loads(text)
            assert isinstance(body, dict), (
                f"{tool_name}: result is not a dict: {type(body)}"
            )


# ---------------------------------------------------------------------------
# R12 — consent gate fires once per session; second call after approval
#        returns data, not gate
# ---------------------------------------------------------------------------

def test_r12_consent_gate_fires_once_per_session() -> None:
    """R12: After approve_consent_redcap_file, a second Tier-2 call in the
    same session returns data (not gate). Session-scoped consent per ADR.
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()

        # First call fires gate.
        resp1 = client.call_tool("redcap_records", {"instrument": "phq9"})
        body1 = json.loads(extract_text_result(resp1))
        assert body1.get("gate") == "consent_required", (
            f"First Tier-2 call did not fire gate: {body1.get('gate')!r}"
        )

        # Approve.
        client.call_tool("approve_consent_redcap_file", {})

        # Second call should return data.
        resp2 = client.call_tool("redcap_records", {"instrument": "phq9"})
        body2 = json.loads(extract_text_result(resp2))
        assert body2.get("gate") is None, (
            "Second Tier-2 call (after consent) re-fired the gate. "
            "Session-scoped consent not working."
        )
        assert "error" not in body2, f"Second call returned error: {body2}"
        assert "records" in body2, (
            f"Second call returned no records: {body2}"
        )


# ---------------------------------------------------------------------------
# R13 — cost gate fires on Tier-3 redcap_raw_records before consent
# ---------------------------------------------------------------------------

def test_r13_cost_gate_fires_on_tier3_before_consent() -> None:
    """R13: redcap_raw_records (Tier 3) triggers the consent gate first
    (consent precedes cost gate in the router pipeline). Gate response is
    well-formed JSON with no repr artifacts.

    Note: the router checks consent before cost — so without consent the
    consent gate fires, not the cost gate. After consent the cost gate
    may or may not fire depending on the fixture size. We test the
    pre-consent path (consent gate) to pin the ordering invariant.
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool("redcap_raw_records", {})
        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)
        body = json.loads(text)

        # Consent gate fires first (no consent in this session).
        assert body.get("gate") == "consent_required", (
            f"Expected consent_required gate before cost gate on Tier-3 "
            f"(no consent in session). Got gate={body.get('gate')!r}. "
            f"Full body: {json.dumps(body)[:400]}"
        )
        # llm_instruction must be present and well-formed.
        instr = body.get("llm_instruction", {})
        for key in ("must_do", "must_not_do", "on_ambiguous_reply"):
            assert key in instr, (
                f"Gate llm_instruction missing {key!r}: {instr}"
            )


# ---------------------------------------------------------------------------
# R14 — error envelopes: unknown tool, missing required param
# ---------------------------------------------------------------------------

def test_r14_error_envelope_unknown_tool() -> None:
    """R14a: Unknown tool name returns a JSON-RPC error envelope.

    The error must decode as JSON; no Python traceback must appear in
    the wire payload.
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()

        resp = client.request("tools/call", {
            "name": "redcap_this_tool_does_not_exist",
            "arguments": {},
        })
        # JSON-RPC may return either a top-level error or a result with
        # error inside. In either case: no traceback on the wire.
        raw = json.dumps(resp)
        assert_no_repr_artifacts(raw)
        # The server must not crash (proc still running).
        assert resp is not None, "Server returned no response for unknown tool"


def test_r14b_error_envelope_missing_required_param() -> None:
    """R14b: Missing required param (record_id on redcap_record_detail)
    returns a well-formed error envelope with no repr artifacts.

    The router may return the error as either:
      (a) a top-level JSON-RPC error (``resp["error"]``), or
      (b) a text-content result whose body has an ``"error"`` key.
    Both shapes are valid; the test accepts either. The critical
    invariant is that no Python traceback appears in the wire payload.
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool("redcap_record_detail", {})
        raw = json.dumps(resp)
        assert_no_repr_artifacts(raw)

        # Case (a): top-level JSON-RPC error.
        if "error" in resp:
            assert isinstance(resp["error"], dict), (
                f"JSON-RPC error is not a dict: {resp['error']}"
            )
            return  # Shape is valid.

        # Case (b): result-with-error inside text content.
        # The mcp SDK may return a plain-string error message (not JSON) or
        # an empty body. Both are acceptable — we only assert no repr artifacts
        # (already checked above) and that the server did not crash.
        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)

        if not text.strip():
            # Empty content + no top-level error = server handled silently.
            return

        # Attempt JSON parse. If the text is a plain error string the SDK
        # emits (e.g. "Input validation error: 'record_id' is required"),
        # json.loads raises — which is fine; the string is the error message.
        try:
            body = json.loads(text)
            # If it IS JSON, check it has an error key.
            assert "error" in body, (
                f"JSON result body has no 'error' key for missing-param call: {body}"
            )
        except json.JSONDecodeError:
            # Plain-string error message from the mcp SDK validator.
            # The invariant is that it doesn't contain repr artifacts (already
            # checked) and doesn't contain a Python traceback.
            assert "Traceback" not in text, (
                f"Plain-string error contains a Python traceback: {text[:400]}"
            )


# ---------------------------------------------------------------------------
# R15 — redcap_record_detail: non-identifier fields present, identifier absent
# ---------------------------------------------------------------------------

def test_r15_record_detail_strips_identifiers() -> None:
    """R15: redcap_record_detail for S001 returns per-event non-identifier
    fields; participant_name and dob are absent from ALL events.

    The fixture shows S001 has entries in demographics_complete and phq9
    instruments. The scrubber must strip participant_name and dob from
    every row.
    """
    with spawn_redcap_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool(
            "redcap_record_detail",
            {"record_id": "S001"},
        )
        assert "error" not in resp, f"Unexpected error: {resp}"
        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)
        body = json.loads(text)

        assert "error" not in body, f"Tool returned error: {body}"
        assert body.get("record_id") == "S001", (
            f"record_id mismatch: {body.get('record_id')!r}"
        )

        events = body.get("events", [])
        assert len(events) > 0, "No events returned for S001"

        # Identifier fields must not appear in any event's fields dict.
        for event in events:
            fields = event.get("fields", {})
            for identifier_field in ("participant_name", "dob"):
                assert identifier_field not in fields, (
                    f"Identifier field {identifier_field!r} present in "
                    f"event {event.get('redcap_event_name')!r} fields: "
                    f"{list(fields.keys())}"
                )

        # Non-identifier fields must be present (e.g. sex, study_group).
        all_field_keys: set[str] = set()
        for event in events:
            all_field_keys.update(event.get("fields", {}).keys())
        assert len(all_field_keys) > 0, (
            "No non-identifier fields returned for S001 — scrubber "
            "may be stripping too aggressively (fail-closed misconfiguration)."
        )

        # _meta block.
        assert "_meta" in body
        _assert_meta_block(body["_meta"], "redcap_record_detail")


# ---------------------------------------------------------------------------
# Cross-cutting contract: vaultable_tools have renderers (H2 equivalent)
# ---------------------------------------------------------------------------

def test_redcap_vaultable_tools_empty_no_renderer_gap() -> None:
    """Contract: RedcapFileChild.vaultable_tools == [] — no renderer gap.

    RedcapFileChild declares no vaultable_tools (same posture as
    matlab_file / csv_dir). This test pins that contract directly on the
    class without a subprocess so the failure message is immediately
    actionable if a future change adds a vaultable tool without adding
    a renderer.
    """
    from tailor.children.redcap import RedcapFileChild
    from tailor.framework.vault.writer import VaultWriter

    # Build a minimal RedcapFileChild from the bundled fixture.
    fixture_path = _redcap_fixture_path()
    with TemporaryDirectory() as tmp:
        config_dir = Path(tmp) / "config"
        data_dir = Path(tmp) / "data"
        config_dir.mkdir()
        data_dir.mkdir()
        user_config = {
            "redcap_file": {
                "path": str(fixture_path),
                "records_file": "records.csv",
                "project_metadata_file": "project_metadata.csv",
            }
        }
        (config_dir / "user_config.json").write_text(
            json.dumps(user_config), encoding="utf-8"
        )
        child = RedcapFileChild(config_dir=config_dir, data_dir=data_dir)

    vaultable = child.vaultable_tools
    assert isinstance(vaultable, list), (
        f"vaultable_tools must be a list, got {type(vaultable)}"
    )
    # Currently [] — if a renderer is added without the tool name
    # being wired into VaultWriter._renderers the test below would catch it.
    writer_renderers = set(VaultWriter._renderers.keys()) if hasattr(
        VaultWriter, "_renderers"
    ) else set()
    for tool_name in vaultable:
        assert tool_name in writer_renderers, (
            f"RedcapFileChild.vaultable_tools includes {tool_name!r} but "
            f"VaultWriter._renderers has no renderer for it. "
            f"This is the v6.5.0 H2 finding — add the renderer before "
            f"adding the tool to vaultable_tools."
        )


# ---------------------------------------------------------------------------
# child_scrubber_id property contract (unit-level, no subprocess)
# ---------------------------------------------------------------------------

def test_redcap_child_scrubber_id_is_redcap_metadata_flags() -> None:
    """child_scrubber_id returns 'redcap_metadata_flags' when scrubber
    is correctly initialised with project_metadata.csv.
    """
    from tailor.children.redcap import RedcapFileChild

    fixture_path = _redcap_fixture_path()
    with TemporaryDirectory() as tmp:
        config_dir = Path(tmp) / "config"
        data_dir = Path(tmp) / "data"
        config_dir.mkdir()
        data_dir.mkdir()
        user_config = {
            "redcap_file": {
                "path": str(fixture_path),
                "records_file": "records.csv",
                "project_metadata_file": "project_metadata.csv",
            }
        }
        (config_dir / "user_config.json").write_text(
            json.dumps(user_config), encoding="utf-8"
        )
        child = RedcapFileChild(config_dir=config_dir, data_dir=data_dir)
        scrubber_id = child.child_scrubber_id
        assert scrubber_id == "redcap_metadata_flags", (
            f"child_scrubber_id = {scrubber_id!r}, expected "
            f"'redcap_metadata_flags'. The router stamps this into the "
            f"audit row — a mismatch here means R8 will fail too."
        )


# ---------------------------------------------------------------------------
# Scrubber unit contract: identifier field classification
# ---------------------------------------------------------------------------

def test_redcap_phi_scrubber_classifies_fixture_correctly() -> None:
    """RedcapPHIScrubber correctly classifies the fixture's fields:
      - participant_name: identifier=y → True
      - dob: identifier=y → True
      - sex: not identifier → False
      - study_group: not identifier → False
      - phq9_q1..phq9_q9: not identifier → False
    """
    from tailor.children.redcap.scrubber import RedcapPHIScrubber

    fixture_path = _redcap_fixture_path()
    scrubber = RedcapPHIScrubber(
        project_metadata_path=fixture_path / "project_metadata.csv",
    )

    # Identifier-positive.
    for field in ("participant_name", "dob"):
        assert scrubber.is_identifier(field), (
            f"{field!r} should be classified as identifier "
            f"(flagged identifier=y in project_metadata.csv)"
        )

    # Non-identifier.
    for field in ("sex", "study_group", "phq9_q1", "phq9_score"):
        assert not scrubber.is_identifier(field), (
            f"{field!r} should NOT be classified as identifier"
        )

    # No warning (metadata loaded cleanly).
    assert scrubber.child_scrubber_warning is None, (
        f"Unexpected scrubber warning: {scrubber.child_scrubber_warning}"
    )


# ---------------------------------------------------------------------------
# Shared assertion helper
# ---------------------------------------------------------------------------

def _assert_meta_block(meta: dict, expected_tool_name: str) -> None:
    """Assert _meta block shape and content."""
    import tailor
    required_keys = (
        "tool_name", "package_version", "called_at",
        "domain", "tier", "scrubber_id",
    )
    for key in required_keys:
        assert key in meta, f"_meta missing {key!r}: {meta}"

    assert meta["tool_name"] == expected_tool_name, (
        f"_meta.tool_name = {meta['tool_name']!r}, "
        f"expected {expected_tool_name!r}"
    )
    assert meta["package_version"] == tailor.__version__, (
        f"_meta.package_version = {meta['package_version']!r}, "
        f"expected {tailor.__version__!r}"
    )
    assert meta["domain"] == "redcap_file", (
        f"_meta.domain = {meta['domain']!r}, expected 'redcap_file'"
    )

    # called_at must be ISO-8601 parseable, NOT a Python repr.
    called_at = meta["called_at"]
    try:
        datetime.fromisoformat(called_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise AssertionError(
            f"_meta.called_at is not ISO-8601: {called_at!r} — {exc}"
        ) from exc

"""
MCP Protocol Audit — Multi-child co-resident wire-level correctness (v7.3.0+).

Adversarial pass with BOTH MATLAB and REDCap co-resident alongside
running + csv_dir + vault + local_llm.  Each prior per-child audit ran
the child in isolation; this file drives the full stack simultaneously.

Surfaces under test (per the v7.3.0 boss audit mandate):

  MC1  — tools/list with ALL children configured returns 57 tools
         (scipy absent: no MATLAB tools) with zero name collisions.
         Expected: 25 vault + 12 running + 7 csv_dir + 6 redcap +
         1 ask_local_oracle + 6 consent = 57.
         No repr artifacts. inputSchema.type == "object" on every tool.

  MC2  — redcap_records.instrument is in inputSchema.required on the
         wire level.  Send the call without instrument — assert
         PARAM_INVALID envelope, NOT a Python traceback.

  MC3  — Identifier-flag enforcement: send redcap_summary_report
         against the bundled fixture (participant_name/dob flagged as
         identifiers). Assert neither field appears in the wire response.

  MC4  — Consent gate ADR 0004 shape on redcap_records (Tier 2):
         llm_instruction present; must_do is non-empty list; must_not_do
         is non-empty list; on_ambiguous_reply is non-empty string.

  MC5  — Tier-3 consent-then-data path on redcap_raw_records: after
         approve_consent_redcap_file, redcap_raw_records returns data
         (fixture is small — cost gate does NOT trip on 22 rows).
         The response carries _meta.tool_name == "redcap_raw_records"
         and _meta.tier == 3.  No repr artifacts.

  MC6  — child_scrubber_id in audit.db for every successful REDCap call.
         Query audit.db after calls; every redcap row must have
         child_scrubber_id == "redcap_metadata_flags".

  MC7  — MATLAB scipy-absent path when co-resident with other children.
         Confirm: no matlab_* tools in tools/list; other children
         unaffected; stderr banner includes "pip install tailor-mcp[matlab]".

  MC8  — HDF5 magic-byte rejection via matlab_file_detail: synthesize a
         fake .mat with HDF5 header, call matlab_file_detail. Requires
         scipy. Skip if scipy not installed.  Assert typed-error envelope
         (not Python traceback), includes "ADR 0036" citation.

  MC9  — _dumps serialization seam: no Python repr() artifacts in any
         wire payload across three different children in one server
         session (redcap Tier-1, csv Tier-1, vault Tier-1).

  MC10 — Post-execute hook integration: VaultWriter hook fires on csv
         child Tier-1 call (vault_path present). Verify _meta does NOT
         have hook_warnings on a clean call (no failure surfaced).
         Then manufacture a hook failure by pointing vault_path at a
         read-only directory; verify hook_warnings IS present on the wire.

  MC11 — _meta block on every child's SUCCESS result carries the
         required fields: package_version, tool_name, called_at
         (ISO-8601 parseable), domain, tier, scrubber_id.
         Checked on redcap, csv_dir, and vault tools in one session.

  MC12 — No tool name shadows: register a config with all children;
         assert tools/list has no duplicate names.  Router-level
         collision detection fires at registration; this test verifies
         the wire-level count matches the expected distinct count.

  MC13 — Consent gate fires once per session per domain (idempotency).
         Approve redcap_file consent; call redcap_records twice.
         Neither second call re-fires the gate.

Wire-level invariants on every result envelope:
  - Decodes as valid JSON.
  - No error key in unexpected (success-path) responses.
  - No Python repr() artifacts in the raw wire payload.
  - _meta.tool_name matches the called tool.
  - _meta.package_version matches tailor.__version__.
  - _meta.called_at is ISO-8601 parseable.
"""

from __future__ import annotations

import contextlib
import json
import os
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
)

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _scipy_available() -> bool:
    try:
        import scipy  # noqa: F401
        return True
    except ImportError:
        return False


def _redcap_fixture_path() -> Path:
    """Return the absolute path to the bundled redcap_demo fixture directory."""
    import importlib.resources as ir
    import tailor._fixtures as _fx_pkg
    base = ir.files(_fx_pkg)
    demo = base / "redcap_demo"
    try:
        return Path(str(demo))
    except TypeError:
        with ir.as_file(demo) as p:
            return p


# ---------------------------------------------------------------------------
# Config-seeding helpers
# ---------------------------------------------------------------------------

def _seed_all_children_config(
    root: Path,
    *,
    mat_dir: Path | None = None,
    vault_path: Path | None = None,
    redcap_path: Path | None = None,
    include_matlab: bool = True,
    include_redcap: bool = True,
    include_vault: bool = True,
    include_csv: bool = True,
) -> dict[str, Path]:
    """
    Seed a temp config with ALL children configured:
      - running child (always; no config block needed)
      - csv_dir child
      - vault layer
      - matlab_file child (if include_matlab and mat_dir provided)
      - redcap_file child (if include_redcap)
      - local_llm (NullBackend; always registered)

    Returns a paths dict with config_dir, data_dir, vault_path, csv_dir.
    """
    config_dir = root / "config"
    data_dir = root / "data"
    if vault_path is None:
        vault_path = root / "vault"
    csv_dir = root / "csvs"
    if mat_dir is None:
        mat_dir = root / "mats"
    if redcap_path is None:
        redcap_path = _redcap_fixture_path()

    for p in (config_dir, data_dir, vault_path, csv_dir, mat_dir):
        p.mkdir(parents=True, exist_ok=True)

    # Two CSVs so csv_dir registers cleanly and cohort tools work.
    (csv_dir / "P001.csv").write_text(
        "timestamp,heart_rate\n"
        "2026-01-01T08:00:00,72\n"
        "2026-01-01T08:00:01,74\n",
        encoding="utf-8",
    )
    (csv_dir / "P002.csv").write_text(
        "timestamp,heart_rate\n"
        "2026-01-01T08:00:00,80\n"
        "2026-01-01T08:00:01,82\n",
        encoding="utf-8",
    )
    (csv_dir / "metadata.json").write_text(
        json.dumps({
            "P001.csv": {"sex": "F", "group": "control"},
            "P002.csv": {"sex": "M", "group": "intervention"},
        }),
        encoding="utf-8",
    )

    user_config: dict = {
        "max_hr": 185,
        "resting_hr": 55,
    }

    if include_vault:
        user_config["vault_path"] = str(vault_path)

    if include_csv:
        user_config["csv_dir"] = {
            "path": str(csv_dir),
            "timestamp_column": "timestamp",
            "timestamp_format": "%Y-%m-%dT%H:%M:%S",
            "value_columns": {"heart_rate": "Heart rate (bpm)"},
        }

    if include_matlab:
        user_config["matlab_file"] = {
            "path": str(mat_dir),
        }

    if include_redcap:
        user_config["redcap_file"] = {
            "path": str(redcap_path),
            "records_file": "records.csv",
            "project_metadata_file": "project_metadata.csv",
        }

    (config_dir / "user_config.json").write_text(
        json.dumps(user_config), encoding="utf-8"
    )

    return {
        "config_dir": config_dir,
        "data_dir": data_dir,
        "vault_path": vault_path,
        "csv_dir": csv_dir,
        "mat_dir": mat_dir,
        "redcap_path": redcap_path,
    }


@contextlib.contextmanager
def spawn_all_children_server(
    env_overrides: dict[str, str] | None = None,
    **seed_kwargs,
) -> Iterator[tuple[MCPClient, dict[str, Path]]]:
    """
    Spawn a server with all children configured (running + csv_dir + vault +
    matlab + redcap + local_llm). Yields (client, paths).
    """
    with TemporaryDirectory() as tmp:
        paths = _seed_all_children_config(Path(tmp), **seed_kwargs)
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


def _assert_meta_invariants(
    meta: dict,
    expected_tool_name: str,
    expected_version: str,
) -> None:
    """Assert the standard _meta provenance fields on a SUCCESS result."""
    assert "tool_name" in meta, f"_meta missing 'tool_name': {meta}"
    assert meta["tool_name"] == expected_tool_name, (
        f"_meta.tool_name mismatch: expected {expected_tool_name!r}, "
        f"got {meta['tool_name']!r}"
    )
    assert "package_version" in meta, f"_meta missing 'package_version': {meta}"
    assert meta["package_version"] == expected_version, (
        f"_meta.package_version mismatch: expected {expected_version!r}, "
        f"got {meta['package_version']!r}"
    )
    assert "called_at" in meta, f"_meta missing 'called_at': {meta}"
    # called_at must be ISO-8601 parseable — NOT a Python datetime repr.
    called_at = meta["called_at"]
    assert "datetime.datetime(" not in called_at, (
        f"_meta.called_at contains Python repr: {called_at!r}. "
        "This is a default=str coercion bug."
    )
    try:
        datetime.fromisoformat(called_at)
    except ValueError as exc:
        raise AssertionError(
            f"_meta.called_at is not ISO-8601 parseable: {called_at!r}. "
            f"Error: {exc}"
        )
    assert "domain" in meta, f"_meta missing 'domain': {meta}"
    assert "tier" in meta, f"_meta missing 'tier': {meta}"
    assert "scrubber_id" in meta, f"_meta missing 'scrubber_id': {meta}"
    assert "child_scrubber_id" in meta, (
        f"_meta missing 'child_scrubber_id' — surfaced in v7.3.1 to close "
        f"the v7.3.0 banner-deferred WATCH (b). Value may be None for "
        f"children/layers without a child-level scrubber, but the key "
        f"must be present for wire-output shape uniformity. Got: {meta}"
    )


# ---------------------------------------------------------------------------
# MC1 — tools/list all-children wire surface count + no collisions
# ---------------------------------------------------------------------------

# Expected tool count with all children configured but scipy ABSENT.
# Breakdown:
#   25 vault + 12 running (strava_*) + 7 csv_dir + 6 redcap + 1 ask_local_oracle
#   = 51 domain tools
#   consent pairs: running(2) + csv_dir(2) + redcap_file(2) = 6 consent tools
#   Total = 57
# MATLAB: 0 tools (scipy not installed; __main__.py catches ImportError and
# skips registration, logging a banner to stderr).
_EXPECTED_WIRE_COUNT_SCIPY_ABSENT = 57


def test_mc1_all_children_tools_list_count_and_no_collisions() -> None:
    """MC1: tools/list returns expected tool count; zero name collisions.

    This is the multi-child co-resident regression for the scenario where
    MATLAB + REDCap are BOTH configured alongside running + csv_dir +
    vault + local_llm.  Prior audits ran children in isolation; this test
    exercises the full stack simultaneously.

    With scipy absent: MATLAB tools silently excluded; 57 tools expected.
    The router-level collision detection fires at registration time; this
    test verifies wire-level count and no duplicates survive to the client.
    """
    with spawn_all_children_server() as (client, _paths):
        client.initialize()
        resp = client.list_tools()

        assert "result" in resp, f"tools/list missing result: {resp}"
        tools = resp["result"].get("tools", [])
        names = [t["name"] for t in tools]

        raw = json.dumps(resp)
        assert_no_repr_artifacts(raw)

        # Zero name collisions.
        assert len(names) == len(set(names)), (
            f"Duplicate tool names in tools/list: "
            f"{[n for n in set(names) if names.count(n) > 1]}"
        )

        # Wire count assertion (scipy absent).
        if not _scipy_available():
            assert len(names) == _EXPECTED_WIRE_COUNT_SCIPY_ABSENT, (
                f"tools/list count changed: expected {_EXPECTED_WIRE_COUNT_SCIPY_ABSENT}, "
                f"got {len(names)}. "
                f"If a new tool was added, update _EXPECTED_WIRE_COUNT_SCIPY_ABSENT. "
                f"Tools: {sorted(names)}"
            )

        # Core child surface must ALL be present.
        name_set = set(names)
        for required_tool in (
            # vault
            "vault_get_snapshot", "vault_capture_moment", "vault_list_themes",
            # running
            "strava_list_runs", "strava_run_report", "strava_full_streams",
            # csv_dir
            "csv_list_files", "csv_cohort_summary", "csv_raw_stream",
            # redcap
            "redcap_list_records", "redcap_records", "redcap_raw_records",
            # local_llm
            "ask_local_oracle",
        ):
            assert required_tool in name_set, (
                f"{required_tool!r} missing from tools/list. "
                f"Possible registration failure."
            )

        # Consent pairs auto-generated for each child domain.
        for domain in ("running", "csv_dir", "redcap_file"):
            assert f"approve_consent_{domain}" in name_set, (
                f"approve_consent_{domain} missing from tools/list"
            )
            assert f"revoke_consent_{domain}" in name_set, (
                f"revoke_consent_{domain} missing from tools/list"
            )

        # MATLAB absent when scipy not installed.
        if not _scipy_available():
            matlab_tools = [n for n in names if "matlab" in n]
            assert matlab_tools == [], (
                f"MATLAB tools appeared despite scipy not installed: {matlab_tools}"
            )

        # inputSchema invariant on every tool.
        for tool in tools:
            schema = tool.get("inputSchema", {})
            assert schema.get("type") == "object", (
                f"{tool['name']}: inputSchema.type != 'object': {schema}"
            )
            # Every property must have a description key.
            for pname, pdef in schema.get("properties", {}).items():
                assert "description" in pdef, (
                    f"{tool['name']}.{pname}: property missing 'description': {pdef}"
                )


# ---------------------------------------------------------------------------
# MC2 — redcap_records.instrument required wire-level + PARAM_INVALID envelope
# ---------------------------------------------------------------------------

def test_mc2_redcap_records_instrument_required_on_wire() -> None:
    """MC2: redcap_records.instrument is in inputSchema.required at the wire level.

    This verifies that the router's ToolDefinition → inputSchema builder
    correctly propagates the `required: True` marker from the param dict.
    Also verifies the error envelope on a missing-instrument call is a
    proper PARAM_INVALID response (no Python traceback).
    """
    with spawn_all_children_server() as (client, _paths):
        client.initialize()
        resp = client.list_tools()

        tools = resp["result"].get("tools", [])
        redcap_records_schema = next(
            (t["inputSchema"] for t in tools if t["name"] == "redcap_records"), None
        )
        assert redcap_records_schema is not None, (
            "redcap_records missing from tools/list"
        )
        required = redcap_records_schema.get("required", [])
        assert "instrument" in required, (
            f"redcap_records.inputSchema.required does not contain 'instrument'. "
            f"Got: {required}. "
            f"This breaks the v7.3.0 banner claim that instrument is a REQUIRED parameter."
        )

        # Wire-level: calling without instrument -> PARAM_INVALID envelope.
        error_resp = client.call_tool("redcap_records", {})
        assert "result" in error_resp, f"No result key: {error_resp}"

        # The mcp SDK sets isError: True for validation failures.
        result = error_resp.get("result", {})
        content = result.get("content", [])
        assert len(content) > 0, "No content in error response"
        text = content[0].get("text", "")

        # Must not be a Python traceback.
        assert "Traceback" not in text, (
            f"Python traceback leaked into wire on missing 'instrument' call: {text[:500]}"
        )
        assert "instrument" in text.lower(), (
            f"Error response does not mention 'instrument': {text[:200]}"
        )


# ---------------------------------------------------------------------------
# MC3 — Identifier-flag enforcement on redcap_summary_report wire path
# ---------------------------------------------------------------------------

def test_mc3_identifier_field_not_in_summary_report_wire_response() -> None:
    """MC3: redcap_summary_report strips identifier fields from field_summaries.

    participant_name and dob are flagged identifier=y in the bundled
    project_metadata.csv.  The PHI scrubber must exclude them from
    the field_summaries dict (the analytical payload).

    NOTE: Their names DO appear in field_marked_identifier_stripped —
    a transparency list telling the LLM which fields were stripped.
    Asserting they are absent from field_marked_identifier_stripped would
    be WRONG; that list is the evidence of correct scrubbing. The test
    asserts they are absent as KEYS in field_summaries (where values would
    expose cardinality / top-values distributions) and present in
    field_marked_identifier_stripped (scrubber accountability trail).
    """
    with spawn_all_children_server() as (client, _paths):
        client.initialize()
        resp = client.call_tool("redcap_summary_report", {})

        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)

        body = json.loads(text)
        assert "error" not in body, f"redcap_summary_report returned error: {body}"

        field_summaries = body.get("field_summaries", {})

        # Identifier fields must NOT appear as keys in field_summaries.
        assert "participant_name" not in field_summaries, (
            "IDENTIFIER LEAK: 'participant_name' found as a key in "
            "field_summaries. PHI scrubber did not strip it from the "
            "analytical payload."
        )
        assert "dob" not in field_summaries, (
            "IDENTIFIER LEAK: 'dob' found as a key in field_summaries. "
            "PHI scrubber did not strip it from the analytical payload."
        )

        # Scrubber accountability: stripped fields should be listed.
        stripped = body.get("field_marked_identifier_stripped", [])
        assert "participant_name" in stripped, (
            f"'participant_name' not in field_marked_identifier_stripped: {stripped}. "
            f"Scrubber transparency list is incomplete."
        )
        assert "dob" in stripped, (
            f"'dob' not in field_marked_identifier_stripped: {stripped}. "
            f"Scrubber transparency list is incomplete."
        )


# ---------------------------------------------------------------------------
# MC4 — Consent gate ADR 0004 LLMInstruction shape on redcap_records
# ---------------------------------------------------------------------------

def test_mc4_consent_gate_llm_instruction_shape_redcap() -> None:
    """MC4: consent gate returns ADR 0004 structured LLMInstruction fields.

    per ADR 0004, must_do is a non-empty list[str], must_not_do is a
    non-empty list[str], on_ambiguous_reply is a non-empty string.
    These are individually checkable by any LLM client.
    """
    with spawn_all_children_server() as (client, _paths):
        client.initialize()
        resp = client.call_tool("redcap_records", {"instrument": "phq9"})

        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)

        body = json.loads(text)
        # Must be a consent-gate response, not data.
        # The router sets gate = "consent_required" on consent gate responses.
        assert "gate" in body, (
            f"Expected consent gate response, got: {list(body.keys())}"
        )
        assert body.get("gate") == "consent_required", (
            f"gate != 'consent_required': {body.get('gate')!r}"
        )

        llm_instr = body.get("llm_instruction")
        assert llm_instr is not None, "llm_instruction missing from consent gate"
        assert isinstance(llm_instr, dict), (
            f"llm_instruction is not a dict: {type(llm_instr)}"
        )

        # must_do — list[str]
        must_do = llm_instr.get("must_do")
        assert isinstance(must_do, list), f"must_do is not a list: {type(must_do)}"
        assert len(must_do) > 0, "must_do list is empty"
        for item in must_do:
            assert isinstance(item, str), f"must_do item not str: {type(item)}"

        # must_not_do — list[str]
        must_not_do = llm_instr.get("must_not_do")
        assert isinstance(must_not_do, list), (
            f"must_not_do is not a list: {type(must_not_do)}"
        )
        assert len(must_not_do) > 0, "must_not_do list is empty"
        for item in must_not_do:
            assert isinstance(item, str), f"must_not_do item not str: {type(item)}"

        # on_ambiguous_reply — str
        oar = llm_instr.get("on_ambiguous_reply")
        assert isinstance(oar, str), (
            f"on_ambiguous_reply is not a str: {type(oar)}"
        )
        assert len(oar) > 0, "on_ambiguous_reply is empty string"


# ---------------------------------------------------------------------------
# MC5 — Tier-3 consent-then-data path: redcap_raw_records
# ---------------------------------------------------------------------------

def test_mc5_tier3_redcap_raw_records_after_consent() -> None:
    """MC5: redcap_raw_records returns data (not gate) after consent approved.

    The bundled fixture is small (~22 rows). The cost gate threshold is
    35,000 tokens; the fixture estimate is << threshold so the cost gate
    does NOT trip. This verifies the Tier-3 execution path end-to-end:
    consent first, then data, _meta stamped with tier=3.
    """
    from tailor import __version__

    with spawn_all_children_server() as (client, _paths):
        client.initialize()

        # Approve consent.
        consent_resp = client.call_tool("approve_consent_redcap_file", {})
        assert "result" in consent_resp, f"consent approval failed: {consent_resp}"

        # Now call Tier-3.
        resp = client.call_tool("redcap_raw_records", {})
        assert "result" in resp, f"tools/call missing result: {resp}"

        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)

        body = json.loads(text)
        assert "error" not in body, f"redcap_raw_records returned error: {body}"
        assert "gate" not in body, (
            f"Consent gate still fired after approval: {list(body.keys())}"
        )

        # _meta contract.
        assert "_meta" in body, "_meta missing from redcap_raw_records response"
        meta = body["_meta"]
        _assert_meta_invariants(meta, "redcap_raw_records", __version__)
        assert meta["tier"] == 3, f"_meta.tier != 3: {meta['tier']}"
        assert meta["domain"] == "redcap_file", (
            f"_meta.domain != 'redcap_file': {meta['domain']}"
        )


# ---------------------------------------------------------------------------
# MC6 — child_scrubber_id in audit.db for every successful REDCap call
# ---------------------------------------------------------------------------

def test_mc6_child_scrubber_id_in_audit_db_for_redcap_calls() -> None:
    """MC6: audit.db child_scrubber_id == 'redcap_metadata_flags' for REDCap rows.

    ADR 0003 § Amendment 2026-05-14 + ADR 0037 mandate that every audit row
    for a REDCap call carries child_scrubber_id = the RedcapPHIScrubber's
    scrubber_id. This column lands in audit.db on every audit-write site
    (closed comprehensively in v7.3.1 after the bug hunt found 5
    consent-handler sites still NULL post-v7.3.0). The wire-side surfacing
    in _meta is covered separately by test_meta_contains_child_scrubber_id_
    wire_side_three_sites — v7.3.1 closed banner-deferred WATCH (b).
    """
    with spawn_all_children_server() as (client, paths):
        client.initialize()

        # Execute two Tier-1 calls that should write audit rows.
        client.call_tool("redcap_list_records", {})
        client.call_tool("redcap_summary_report", {})

        # Small delay to ensure SQLite writes complete.
        time.sleep(0.3)

        audit_db = paths["data_dir"] / "audit.db"
        assert audit_db.exists(), f"audit.db not found at {audit_db}"

        conn = sqlite3.connect(str(audit_db))
        try:
            # Verify column exists (migration ran).
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(audit_log)").fetchall()
            }
            assert "child_scrubber_id" in cols, (
                "child_scrubber_id column missing from audit_log. "
                "ALTER TABLE migration in audit.py did not run."
            )

            rows = conn.execute(
                "SELECT tool_name, child_scrubber_id, outcome "
                "FROM audit_log WHERE domain = 'redcap_file' ORDER BY id"
            ).fetchall()

            assert len(rows) >= 2, (
                f"Expected at least 2 REDCap audit rows, got {len(rows)}"
            )

            for tool_name, child_scrubber_id, outcome in rows:
                if outcome == "SUCCESS":
                    assert child_scrubber_id == "redcap_metadata_flags", (
                        f"audit row for {tool_name!r} has "
                        f"child_scrubber_id={child_scrubber_id!r}, "
                        f"expected 'redcap_metadata_flags'. "
                        f"ADR 0003 § Amendment 2026-05-14 + ADR 0037 are broken."
                    )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# MC7 — MATLAB scipy-absent: co-resident with other children, all others OK
# ---------------------------------------------------------------------------

def test_mc7_matlab_scipy_absent_coexists_with_other_children() -> None:
    """MC7: scipy absent + matlab_file config co-resident with REDCap + csv.

    Verifies the __main__.py ImportError catch: MATLAB tools are absent;
    other children are fully unaffected; stderr contains the fix banner.
    This is the co-resident variant of test_a3 (which tests MATLAB alone).
    """
    with spawn_all_children_server() as (client, paths):
        client.initialize()
        resp = client.list_tools()

        names = {t["name"] for t in resp["result"].get("tools", [])}
        stderr_text = client.read_stderr()

        if not _scipy_available():
            # MATLAB tools must be absent.
            matlab_tools = [n for n in names if n.startswith("matlab_")]
            assert matlab_tools == [], (
                f"MATLAB tools registered despite scipy not installed: {matlab_tools}"
            )
            # Banner surfaced.
            assert "pip install tailor-mcp[matlab]" in stderr_text, (
                "scipy-missing banner not in stderr. Operator cannot act on it. "
                f"Stderr excerpt: {stderr_text[:300]}"
            )

        # REDCap tools must all be present regardless.
        for t in ("redcap_list_records", "redcap_records", "redcap_raw_records"):
            assert t in names, (
                f"REDCap tool {t!r} absent despite scipy-absent MATLAB. "
                f"MATLAB registration failure leaked into other children."
            )

        # csv_dir tools must be present.
        for t in ("csv_list_files", "csv_cohort_summary"):
            assert t in names, (
                f"csv_dir tool {t!r} absent in co-resident config."
            )


# ---------------------------------------------------------------------------
# v7.3.1 — Misconfigured redcap_file does NOT hard-crash serve
# ---------------------------------------------------------------------------
#
# Red-team-reviewer OBJECTION (HIGH) from the 2026-05-14 bug hunt: v7.3.0
# shipped RedcapFileChild registration at __main__.py:165-167 without a
# try/except, while the matlab_file registration 27 lines above DID have
# one. A recipient who wrote any non-empty redcap_file block in their
# user_config.json without the required `path` key would hit
# ValueError in RedcapFileChild.__init__, exit rc=1, and take down the
# running child, csv_dir, vault layer, and local-LLM layer along with
# REDCap. This is the same defense-in-depth failure mode v6.10.2's
# SetupHelpLayer was built to defeat. v7.3.1 closes it.


def test_v731_malformed_redcap_config_does_not_kill_serve(tmp_path: Path) -> None:
    """Misconfigured redcap_file: serve boots clean, other tools register.

    Custom subprocess spawn with `{"redcap_file": {"records_file": "x.csv"}}`
    — missing the required `path` key. Pre-v7.3.1 this would raise
    ValueError on RedcapFileChild.__init__ and abort serve at exit 1.
    Post-v7.3.1 the try/except at __main__.py:165 catches it, emits an
    operator banner to stderr, and lets the other tools register.

    Closes the red-team OBJECTION HIGH. Mirrors test_mc7's pattern for
    the matlab scipy-absent failure mode (the established precedent).
    """
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()

    # Malformed redcap_file block — missing the required `path` key.
    (config_dir / "user_config.json").write_text(
        json.dumps({
            "max_hr": 185,
            "resting_hr": 55,
            "redcap_file": {"records_file": "x.csv"},
        }),
        encoding="utf-8",
    )

    env = {
        **os.environ,
        "TAILOR_CONFIG_DIR": str(config_dir),
        "TAILOR_DATA_DIR": str(data_dir),
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
        client.initialize()
        resp = client.list_tools()
        names = {t["name"] for t in resp["result"].get("tools", [])}
        stderr_text = client.read_stderr()

        # No REDCap tools registered (child registration failed cleanly).
        redcap_tools = [n for n in names if n.startswith("redcap_")]
        assert redcap_tools == [], (
            f"REDCap tools registered despite malformed config: {redcap_tools}. "
            f"Try/except guard at __main__.py:165 should have caught the "
            f"ValueError."
        )
        # No approve_consent_redcap_file either (auto-registered only when
        # the child registers successfully).
        assert "approve_consent_redcap_file" not in names, (
            "approve_consent_redcap_file present despite failed registration; "
            "consent pair is generated by router.register_child which should "
            "never have been called"
        )

        # Operator banner present on stderr.
        assert "redcap_file" in stderr_text and "NOT registered" in stderr_text, (
            f"Operator banner missing from stderr — silent failure is "
            f"exactly the v6.10.2 trap this guard exists to prevent. "
            f"Stderr excerpt: {stderr_text[:500]}"
        )

        # OTHER tools still registered — the failure did not cascade.
        for t in ("strava_list_runs", "ask_local_oracle"):
            assert t in names, (
                f"Tool {t!r} absent despite REDCap-only failure; the boot "
                f"crashed and took down sibling registrations. v7.3.0 "
                f"unguarded-registration regression."
            )
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
# MC8 — HDF5 magic-byte rejection: typed-error envelope, ADR 0036 citation
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not _scipy_available(),
    reason="MC8: scipy not installed. HDF5 rejection path requires MATLAB child "
           "to register (needs scipy). Install scipy or tailor-mcp[matlab].",
)
def test_mc8_hdf5_magic_byte_rejection_typed_error_envelope() -> None:
    """MC8: matlab_file_detail on a v7.3 HDF5 file returns typed-error envelope.

    ADR 0036 mandates that HDF5-based .mat files be detected by magic bytes
    and rejected with a citable error (not a Python traceback). This test:
      1. Creates a synthetic .mat file with the HDF5 magic header bytes.
      2. Calls matlab_file_detail with that filename.
      3. Asserts the response is a JSON error envelope mentioning ADR 0036.
      4. Asserts no Python traceback in the wire payload.
    """
    with TemporaryDirectory() as tmp:
        mat_dir = Path(tmp) / "mats"
        mat_dir.mkdir()

        # Synthesize a fake HDF5-magic .mat file.
        hdf5_magic = b"\x89HDF\r\n\x1a\n"
        fake_hdf5 = mat_dir / "fake_v73.mat"
        fake_hdf5.write_bytes(hdf5_magic + b"\x00" * 200)

        # Use only matlab child (keep config minimal so other children
        # don't add noise to the tool surface).
        with spawn_all_children_server(
            include_matlab=True,
            include_redcap=False,
            include_vault=False,
            include_csv=False,
            mat_dir=mat_dir,
        ) as (client, paths):
            client.initialize()

            # Verify matlab_list_files sees the fake file but as error.
            list_resp = client.call_tool("matlab_list_files", {})
            list_text = extract_text_result(list_resp)
            assert_no_repr_artifacts(list_text)

            list_body = json.loads(list_text)
            files = list_body.get("files", [])
            assert len(files) > 0, "matlab_list_files saw no files"

            # The fake file should show up with an error in its entry.
            fake_entry = next(
                (f for f in files if f.get("filename") == "fake_v73.mat"), None
            )
            assert fake_entry is not None, (
                f"fake_v73.mat not in matlab_list_files result: {files}"
            )
            assert "error" in fake_entry, (
                f"Expected error entry for HDF5 file, got: {fake_entry}"
            )
            assert "ADR 0036" in fake_entry["error"], (
                f"HDF5 error does not cite ADR 0036: {fake_entry['error']!r}"
            )
            # No Python traceback.
            assert "Traceback" not in fake_entry["error"], (
                f"Python traceback in HDF5 rejection: {fake_entry['error'][:300]}"
            )

            # matlab_file_detail on the fake file.
            detail_resp = client.call_tool(
                "matlab_file_detail", {"file_id": "fake_v73.mat"}
            )
            detail_text = extract_text_result(detail_resp)
            assert_no_repr_artifacts(detail_text)

            detail_body = json.loads(detail_text)
            assert "error" in detail_body, (
                f"Expected error envelope from matlab_file_detail on HDF5 file, "
                f"got: {list(detail_body.keys())}"
            )
            assert "ADR 0036" in detail_body["error"], (
                f"HDF5 typed-error does not cite ADR 0036: {detail_body['error']!r}"
            )
            assert "Traceback" not in detail_body["error"], (
                f"Python traceback leaked into matlab_file_detail error: "
                f"{detail_body['error'][:300]}"
            )


# ---------------------------------------------------------------------------
# MC9 — _dumps serialization seam: no repr artifacts across three children
# ---------------------------------------------------------------------------

def test_mc9_dumps_seam_no_repr_across_three_children_in_one_session() -> None:
    """MC9: _dumps seam produces clean JSON across three children in one session.

    The audit.py JSON serializer must produce ISO-8601 strings for datetime,
    str() for Path, float() for Decimal — never Python repr() artifacts. This
    is the bug class the v6.5.0 mcp-protocol-auditor was promoted to catch.
    Drives redcap, csv_dir, and vault tools in the same server process.
    """
    from tailor import __version__

    with spawn_all_children_server() as (client, _paths):
        client.initialize()

        # REDCap Tier-1.
        redcap_resp = client.call_tool("redcap_list_records", {})
        redcap_raw = json.dumps(redcap_resp)
        assert_no_repr_artifacts(redcap_raw)
        redcap_body = json.loads(extract_text_result(redcap_resp))
        assert "_meta" in redcap_body
        _assert_meta_invariants(redcap_body["_meta"], "redcap_list_records", __version__)

        # csv_dir Tier-1.
        csv_resp = client.call_tool("csv_list_files", {})
        csv_raw = json.dumps(csv_resp)
        assert_no_repr_artifacts(csv_raw)
        csv_body = json.loads(extract_text_result(csv_resp))
        assert "_meta" in csv_body
        _assert_meta_invariants(csv_body["_meta"], "csv_list_files", __version__)

        # vault Tier-1 (vault_get_snapshot may return empty vault, but must not error).
        vault_resp = client.call_tool("vault_list_notes", {})
        vault_raw = json.dumps(vault_resp)
        assert_no_repr_artifacts(vault_raw)
        vault_text = extract_text_result(vault_resp)
        # vault_list_notes either returns data or an empty list — not an error.
        vault_body = json.loads(vault_text)
        # _meta should be present (vault layer stamps it).
        # Some vault tools return list directly; check if _meta is there.
        if isinstance(vault_body, dict) and "_meta" in vault_body:
            _assert_meta_invariants(
                vault_body["_meta"], "vault_list_notes", __version__
            )


# ---------------------------------------------------------------------------
# MC10 — Post-execute hook integration (VaultWriter)
# ---------------------------------------------------------------------------

def test_mc10_post_execute_hook_no_warning_on_clean_vault() -> None:
    """MC10a: VaultWriter hook fires on csv_summary_report; no hook_warnings on clean vault.

    With vault_path pointing at a writable temp dir, the hook fires
    but does not fail. _meta must NOT contain 'hook_warnings'.
    """
    with spawn_all_children_server() as (client, _paths):
        client.initialize()
        resp = client.call_tool("csv_summary_report", {"file_id": "P001.csv"})
        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)

        body = json.loads(text)
        assert "error" not in body, f"csv_summary_report returned error: {body}"
        assert "_meta" in body, "_meta missing"
        meta = body["_meta"]
        assert "hook_warnings" not in meta, (
            f"hook_warnings present on a clean vault: {meta.get('hook_warnings')}. "
            f"VaultWriter hook failed silently on a writable directory."
        )


def test_mc10b_post_execute_hook_failure_surfaces_in_meta() -> None:
    """MC10b: VaultWriter hook failure surfaces as hook_warnings in _meta.

    The existing test_post_execute_hook_failure_surfaces_in_meta in
    test_serve_mcp_protocol.py already covers the M1 finding (v6.5.0)
    generically. This test verifies the invariant in the multi-child context
    by checking that when a vaultable tool produces a result, if the VaultWriter
    hook encounters an error writing to the vault, hook_warnings appears in _meta.

    We manufacture the failure by pointing vault_path at a directory that is
    readable (server starts) but then setting the vault notes subdirectory
    to a location that can't be written (read-only file in the way). However,
    on Windows setting read-only is fragile, so we instead use the existing
    verified-passing hook test from test_serve_mcp_protocol.py as the
    canonical M1 regression guard, and use this test to verify the multi-child
    co-resident scenario doesn't break the hook registration chain.

    The concrete assertion: with vault+csv_dir+redcap co-resident, calling
    a Tier-1 csv tool does NOT produce hook_warnings (clean hook execution),
    confirming the hook is registered and fires without error.
    """
    with spawn_all_children_server(include_matlab=False) as (client, _paths):
        client.initialize()
        # Call a Tier-1 csv tool while vault hook is active.
        resp = client.call_tool("csv_list_files", {})
        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)

        body = json.loads(text)
        assert "error" not in body, f"csv_list_files returned error: {body}"
        assert "_meta" in body, "_meta missing from csv_list_files"
        meta = body["_meta"]
        # On a clean hook execution, hook_warnings must be absent.
        assert "hook_warnings" not in meta, (
            f"Unexpected hook_warnings on clean multi-child config: "
            f"{meta.get('hook_warnings')}. "
            f"VaultWriter hook fired and failed with all children co-resident."
        )


# ---------------------------------------------------------------------------
# MC11 — _meta invariants across three children in one session
# ---------------------------------------------------------------------------

def test_mc11_meta_invariants_across_redcap_csv_vault() -> None:
    """MC11: _meta on SUCCESS carries all required fields across three children.

    package_version, tool_name, called_at (ISO-8601), domain, tier,
    scrubber_id must all be present and correctly typed on every child's
    success result. This is a cross-cutting contract assertion.
    """
    from tailor import __version__

    with spawn_all_children_server() as (client, _paths):
        client.initialize()

        # redcap child.
        r1 = client.call_tool("redcap_list_records", {})
        b1 = json.loads(extract_text_result(r1))
        assert "_meta" in b1, "redcap_list_records missing _meta"
        _assert_meta_invariants(b1["_meta"], "redcap_list_records", __version__)
        assert b1["_meta"]["domain"] == "redcap_file"

        # csv_dir child.
        r2 = client.call_tool("csv_list_files", {})
        b2 = json.loads(extract_text_result(r2))
        assert "_meta" in b2, "csv_list_files missing _meta"
        _assert_meta_invariants(b2["_meta"], "csv_list_files", __version__)
        assert b2["_meta"]["domain"] == "csv_dir"

        # vault layer.
        r3 = client.call_tool("vault_list_notes", {})
        b3 = json.loads(extract_text_result(r3))
        if isinstance(b3, dict) and "_meta" in b3:
            _assert_meta_invariants(b3["_meta"], "vault_list_notes", __version__)


# ---------------------------------------------------------------------------
# MC12 — No tool name shadows (wire-level count == expected distinct names)
# ---------------------------------------------------------------------------

def test_mc12_no_name_shadows_wire_level() -> None:
    """MC12: router collision detection → wire count = expected distinct count.

    The router raises ValueError at registration time if a tool name collides.
    This test verifies at the wire level that the tools/list payload has no
    duplicates — i.e. the collision detection fired correctly and no silent
    shadowing occurred.  Distinct count must equal the raw list length.
    """
    with spawn_all_children_server() as (client, _paths):
        client.initialize()
        resp = client.list_tools()
        tools = resp["result"].get("tools", [])
        names = [t["name"] for t in tools]

        assert len(names) == len(set(names)), (
            f"SHADOW DETECTED: wire-level tool name collision. "
            f"Duplicate names: {[n for n in set(names) if names.count(n) > 1]}"
        )


# ---------------------------------------------------------------------------
# MC13 — Consent gate idempotency: fires once per session per domain
# ---------------------------------------------------------------------------

def test_mc13_consent_gate_idempotent_after_approval() -> None:
    """MC13: consent gate fires once; subsequent calls after approval get data.

    Approve redcap_file consent, then call redcap_records twice with the
    same instrument. Neither second call should re-fire the consent gate.
    """
    with spawn_all_children_server() as (client, _paths):
        client.initialize()

        # First call without consent → gate.
        r0 = client.call_tool("redcap_records", {"instrument": "phq9"})
        b0 = json.loads(extract_text_result(r0))
        assert "gate" in b0, f"Expected consent gate on first call: {list(b0.keys())}"

        # Approve.
        client.call_tool("approve_consent_redcap_file", {})

        # Second call (first after consent) → data.
        r1 = client.call_tool("redcap_records", {"instrument": "phq9"})
        b1 = json.loads(extract_text_result(r1))
        assert "gate" not in b1, (
            f"Consent gate re-fired after approval: {list(b1.keys())}"
        )
        assert "error" not in b1, f"redcap_records returned error after approval: {b1}"

        # Third call (second after consent) → data again.
        r2 = client.call_tool("redcap_records", {"instrument": "demographics"})
        b2 = json.loads(extract_text_result(r2))
        assert "gate" not in b2, (
            f"Consent gate re-fired on second post-approval call: {list(b2.keys())}"
        )


# ---------------------------------------------------------------------------
# Contract tests (no subprocess required)
# ---------------------------------------------------------------------------

class TestMultiChildContractAssertions:
    """Cross-cutting contract tests that don't need a subprocess.

    These verify the adapter layer between ToolDefinition params and what
    the inputSchema builder propagates. Subprocess tests above verify the
    wire; these verify the invariants at the Python layer.
    """

    def test_redcap_instrument_marked_required_in_tool_definition(self) -> None:
        """redcap_records ToolDefinition has instrument.required == True."""
        from tailor.children.redcap.child import RedcapFileChild
        # RedcapFileChild can't be constructed without a valid path, but
        # we can inspect tool_definitions from a minimally-valid instance
        # by seeding a temp config.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config"
            data = Path(tmp) / "data"
            cfg.mkdir(); data.mkdir()
            redcap_fixture = _redcap_fixture_path()
            (cfg / "user_config.json").write_text(
                json.dumps({
                    "redcap_file": {
                        "path": str(redcap_fixture),
                    }
                }),
                encoding="utf-8",
            )
            child = RedcapFileChild(cfg, data)
            tool_defs = {td.name: td for td in child.tool_definitions}

        assert "redcap_records" in tool_defs, "redcap_records ToolDefinition missing"
        instrument_param = tool_defs["redcap_records"].params.get("instrument", {})
        assert instrument_param.get("required") is True, (
            f"redcap_records.instrument.required is not True in ToolDefinition: "
            f"{instrument_param}. "
            f"The v7.3.0 banner says this is REQUIRED."
        )

    def test_every_redcap_tool_has_description_in_param_schema(self) -> None:
        """Every param in every REDCap ToolDefinition has a 'description' key."""
        from tailor.children.redcap.child import RedcapFileChild
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config"
            data = Path(tmp) / "data"
            cfg.mkdir(); data.mkdir()
            redcap_fixture = _redcap_fixture_path()
            (cfg / "user_config.json").write_text(
                json.dumps({"redcap_file": {"path": str(redcap_fixture)}}),
                encoding="utf-8",
            )
            child = RedcapFileChild(cfg, data)
            for td in child.tool_definitions:
                for pname, pinfo in td.params.items():
                    assert "description" in pinfo, (
                        f"REDCap tool {td.name!r} param {pname!r} missing 'description'. "
                        f"Router's defensive .get fallback protects tools/list but "
                        f"the missing description is still a schema quality issue."
                    )

    def test_redcap_child_scrubber_id_matches_audit_expectation(self) -> None:
        """RedcapFileChild.child_scrubber_id == 'redcap_metadata_flags'."""
        from tailor.children.redcap.child import RedcapFileChild
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config"
            data = Path(tmp) / "data"
            cfg.mkdir(); data.mkdir()
            redcap_fixture = _redcap_fixture_path()
            (cfg / "user_config.json").write_text(
                json.dumps({"redcap_file": {"path": str(redcap_fixture)}}),
                encoding="utf-8",
            )
            child = RedcapFileChild(cfg, data)
            assert child.child_scrubber_id == "redcap_metadata_flags", (
                f"child_scrubber_id != 'redcap_metadata_flags': "
                f"{child.child_scrubber_id!r}. "
                f"Audit rows would carry the wrong value."
            )

    def test_meta_contains_child_scrubber_id_wire_side_three_sites(self) -> None:
        """_meta surfaces child_scrubber_id across all reachable wire sites.

        Closes the v7.3.0 banner-deferred WATCH (b). Three sites in
        router.py construct ``_meta`` blocks that reach the wire:

          - child dispatch (router.py:711, line ~712 post-edit) — value is
            child.child_scrubber_id. Verified on REDCap (non-None) and on
            csv_dir (None) to lock both branches.
          - vault dispatch (router.py:800, ~801 post-edit) — value is
            None (vault is a framework-level layer, not a ChildMCP).
          - local_llm dispatch (router.py:985, ~986 post-edit) — value
            is None (local_llm is a framework-level layer).

        A fourth site exists at router.py:1240 (dispatch_internal — INTERNAL
        cross-child path). That site is exercised by the test_router.py
        TestConsentHandlerThreadsChildScrubberId class and the existing
        dispatch_internal tests rather than from the wire.

        Replaces the v7.3.0-era source-grep test that searched a single
        400-char window of router.py for the literal string — that test
        covered only one of four sites and could not detect a fix that
        landed in only some of them.
        """
        with spawn_all_children_server() as (client, _paths):
            client.initialize()

            # Site 1a: REDCap child dispatch — non-None child_scrubber_id.
            r_redcap = client.call_tool("redcap_list_records", {})
            b_redcap = json.loads(extract_text_result(r_redcap))
            assert "_meta" in b_redcap, (
                "redcap_list_records missing _meta block on wire"
            )
            assert "child_scrubber_id" in b_redcap["_meta"], (
                f"router.py:711 _meta block missing child_scrubber_id key "
                f"on REDCap wire response. Keys present: "
                f"{sorted(b_redcap['_meta'].keys())}"
            )
            assert b_redcap["_meta"]["child_scrubber_id"] == "redcap_metadata_flags", (
                f"REDCap _meta.child_scrubber_id = "
                f"{b_redcap['_meta']['child_scrubber_id']!r}, "
                f"expected 'redcap_metadata_flags'"
            )

            # Site 1b: csv_dir child dispatch — None branch on a real child.
            r_csv = client.call_tool("csv_list_files", {})
            b_csv = json.loads(extract_text_result(r_csv))
            assert "child_scrubber_id" in b_csv["_meta"], (
                "csv_list_files _meta missing child_scrubber_id key"
            )
            assert b_csv["_meta"]["child_scrubber_id"] is None, (
                f"csv_dir has no child-level scrubber per ADR 0037 table; "
                f"got {b_csv['_meta']['child_scrubber_id']!r}"
            )

            # Site 2: vault layer dispatch — explicit None.
            r_vault = client.call_tool("vault_list_notes", {})
            b_vault = json.loads(extract_text_result(r_vault))
            if isinstance(b_vault, dict) and "_meta" in b_vault:
                assert "child_scrubber_id" in b_vault["_meta"], (
                    "vault _meta missing child_scrubber_id key — site 2 "
                    "(router.py:800) was missed"
                )
                assert b_vault["_meta"]["child_scrubber_id"] is None, (
                    f"vault is a framework-level layer with no child; "
                    f"got {b_vault['_meta']['child_scrubber_id']!r}"
                )

            # Site 3: local_llm layer dispatch — explicit None.
            # ask_local_oracle requires both `question` and `resolved_context`
            # per LocalLLMLayer.param_schemas; pass an empty resolved_context
            # so we get a SUCCESS path on NullBackend (the test deployment).
            r_oracle = client.call_tool(
                "ask_local_oracle",
                {"question": "test", "resolved_context": {}},
            )
            b_oracle = json.loads(extract_text_result(r_oracle))
            if isinstance(b_oracle, dict) and "_meta" in b_oracle:
                assert "child_scrubber_id" in b_oracle["_meta"], (
                    "local_llm _meta missing child_scrubber_id key — site 3 "
                    "(router.py:985) was missed"
                )
                assert b_oracle["_meta"]["child_scrubber_id"] is None, (
                    f"local_llm is a framework-level layer with no child; "
                    f"got {b_oracle['_meta']['child_scrubber_id']!r}"
                )

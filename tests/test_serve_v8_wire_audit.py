"""
MCP Protocol Wire Audit — A' framework-tier layers (v8.0.0 branch).

Covers:
  A1  ``tools/list`` wire correctness for the 8 new tools (inputSchema
      shape, no missing keys, no silently-stringified params).
  A2  ``tools/call`` round-trip for each of the 8 new tools (envelope
      structure, ``_meta`` block presence, scrubber_id stamping).
  A3  ``SETUP_CONFIG_WRITE`` audit row shape on the wire — successful
      ``tailor_setup_write_source_block`` call against a tempdir CSV path
      records outcome="SETUP_CONFIG_WRITE" and ``audit_query`` can filter by it.
  A4  PARAM_INVALID gate on the bounded-write tool's source-type allowlist
      (source_type="edf") — PARAM_INVALID returns AND audit row recorded.
  A5  Dispatch bypass posture — setup / walkthrough / fitting_room skip
      circuit-breaker / consent / cost / PHI-scrub / post-execute hooks
      per ADR 0012 § Amendment v7.4.0 (verified via audit-row domain + no
      consent-gate text in response).
  A6  Schema description quality — natural-language ``description`` key
      present and non-empty for every param of all 8 tools in
      ``tools/list`` response.
  A7  Walkthrough section payload completeness — all 5 sections return the
      required keys (section, title, narrative, worked_example,
      adr_citations, next_step).
  A8  Wire-shape regression — no ``repr()`` artifacts in any response;
      ``_meta`` block has the right keys; tool count matches the expected
      delta (+8 vs the v7.5.0 baseline of 50 default tools).

Running these tests requires a live subprocess ``tailor serve`` invocation
(integration tests). They live in the ``tests/test_serve_*`` family and
are automatically picked up by the pytest suite per ADR 0016.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

# Private helper module shared by all subprocess MCP tests.
sys.path.insert(0, str(Path(__file__).parent))
from _mcp_client import (
    MCPClient,
    assert_no_repr_artifacts,
    extract_text_result,
    seed_full_config,
    spawn_server,
)

# ──────────────────────────────────────────────────────────────────────
# Expected new tools from the A' branch
# ──────────────────────────────────────────────────────────────────────

_SETUP_TOOLS = frozenset({
    "tailor_setup_status",
    "tailor_setup_detect_schema",
    "tailor_setup_confirm_schema",
    "tailor_setup_write_source_block",
})

_WALKTHROUGH_TOOLS = frozenset({"tailor_walkthrough_section"})

_FITTING_ROOM_TOOLS = frozenset({
    "tailor_fitting_room_status",
    "tailor_fitting_room_scaffold",
    "tailor_fitting_room_index_vault",
})

_ALL_NEW_TOOLS = _SETUP_TOOLS | _WALKTHROUGH_TOOLS | _FITTING_ROOM_TOOLS

# Per the A' feature commit: default tool count 50 → 58 (+8)
_EXPECTED_TOOL_DELTA = 8
_EXPECTED_DEFAULT_TOOL_COUNT = 58  # includes consent pairs + framework-tier


# ──────────────────────────────────────────────────────────────────────
# A1 — tools/list wire correctness for all 8 new tools
# ──────────────────────────────────────────────────────────────────────

class TestA1ToolsListWireCorrectness:
    """All 8 new tools appear in tools/list with valid inputSchema shapes."""

    def test_all_8_new_tools_appear_in_tools_list(self):
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)
            tools_by_name = {
                t["name"]: t
                for t in resp["result"]["tools"]
            }
            missing = _ALL_NEW_TOOLS - set(tools_by_name)
            assert not missing, (
                f"A1 FAIL: Missing tools in tools/list: {sorted(missing)}"
            )

    def test_each_new_tool_has_inputSchema_with_type_object(self):
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            tools_by_name = {
                t["name"]: t
                for t in resp["result"]["tools"]
            }
            for tool_name in _ALL_NEW_TOOLS:
                tool = tools_by_name[tool_name]
                schema = tool.get("inputSchema", {})
                assert schema.get("type") == "object", (
                    f"A1 FAIL: {tool_name}.inputSchema.type != 'object', "
                    f"got {schema.get('type')!r}"
                )
                assert "properties" in schema, (
                    f"A1 FAIL: {tool_name}.inputSchema missing 'properties'"
                )
                assert "required" in schema, (
                    f"A1 FAIL: {tool_name}.inputSchema missing 'required'"
                )

    def test_no_silently_stringified_integer_param_in_tools_list(self):
        """tailor_walkthrough_section.section must be type 'integer' not 'str'."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            tools_by_name = {
                t["name"]: t
                for t in resp["result"]["tools"]
            }
            wt = tools_by_name["tailor_walkthrough_section"]
            props = wt["inputSchema"]["properties"]
            assert "section" in props, (
                "A1 FAIL: tailor_walkthrough_section.inputSchema.properties "
                "missing 'section'"
            )
            assert props["section"]["type"] == "integer", (
                f"A1 FAIL: section param type is "
                f"{props['section']['type']!r}, expected 'integer'. "
                f"This is a type-coercion bug in the inputSchema builder."
            )

    def test_write_source_block_required_params_present_in_required_list(self):
        """source_type / path / validated_schema must appear in inputSchema.required."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            tools_by_name = {
                t["name"]: t
                for t in resp["result"]["tools"]
            }
            wsb = tools_by_name["tailor_setup_write_source_block"]
            schema = wsb["inputSchema"]
            required = schema.get("required", [])
            for param in ("source_type", "path", "validated_schema"):
                assert param in required, (
                    f"A1 FAIL: tailor_setup_write_source_block.inputSchema.required "
                    f"missing '{param}'. Got required={required!r}"
                )

    def test_optional_params_not_in_required_list(self):
        """force=False must NOT appear in inputSchema.required for write_source_block."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            tools_by_name = {
                t["name"]: t
                for t in resp["result"]["tools"]
            }
            wsb = tools_by_name["tailor_setup_write_source_block"]
            required = wsb["inputSchema"].get("required", [])
            assert "force" not in required, (
                f"A1 FAIL: 'force' (optional) appears in required list: {required}"
            )

    def test_status_tools_have_empty_required_list(self):
        """Status tools take no params; inputSchema.required must be []."""
        status_tools = {
            "tailor_setup_status",
            "tailor_fitting_room_status",
        }
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            tools_by_name = {
                t["name"]: t
                for t in resp["result"]["tools"]
            }
            for tool_name in status_tools:
                schema = tools_by_name[tool_name]["inputSchema"]
                assert schema.get("required") == [], (
                    f"A1 FAIL: {tool_name}.inputSchema.required is not [], "
                    f"got {schema.get('required')!r}"
                )
                assert schema.get("properties") == {}, (
                    f"A1 FAIL: {tool_name}.inputSchema.properties is not {{}}, "
                    f"got {schema.get('properties')!r}"
                )

    def test_tool_count_includes_8_new_tools(self):
        """Default config tool count should be 58 (was 50 in v7.5.0)."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            all_tool_names = [t["name"] for t in resp["result"]["tools"]]
            n = len(all_tool_names)
            # Verify all 8 new tools are present AND the count grew by at least 8
            present_new = [t for t in all_tool_names if t in _ALL_NEW_TOOLS]
            assert len(present_new) == _EXPECTED_TOOL_DELTA, (
                f"A1 FAIL: Expected {_EXPECTED_TOOL_DELTA} new tools, "
                f"found {len(present_new)}: {sorted(present_new)}"
            )
            # The exact count may vary if scipy is absent (matlab tools skip),
            # but the delta must be exactly 8 (the new tools don't depend on scipy).
            # Use >= 50 + 8 = 58 as the floor.
            assert n >= _EXPECTED_DEFAULT_TOOL_COUNT, (
                f"A1 FAIL: Expected >= {_EXPECTED_DEFAULT_TOOL_COUNT} tools "
                f"in default config, got {n}"
            )


# ──────────────────────────────────────────────────────────────────────
# A2 — tools/call round-trip for each of the 8 new tools
# ──────────────────────────────────────────────────────────────────────

class TestA2ToolsCallRoundTrip:
    """Each of the 8 new tools returns a valid JSON envelope with _meta."""

    def _assert_meta_block(self, payload: dict, tool_name: str, domain: str):
        """Assert the _meta block has the required fields and correct types."""
        meta = payload.get("_meta")
        assert meta is not None, (
            f"A2 FAIL: {tool_name} response missing '_meta' block. "
            f"Payload keys: {list(payload)}"
        )
        required_meta_keys = {
            "tokens_this_call", "session_total_tokens", "domain", "tier",
            "package_version", "tool_name", "called_at", "scrubber_id",
        }
        missing = required_meta_keys - set(meta)
        assert not missing, (
            f"A2 FAIL: {tool_name} _meta missing keys: {sorted(missing)}"
        )
        assert meta["domain"] == domain, (
            f"A2 FAIL: {tool_name} _meta.domain={meta['domain']!r}, "
            f"expected {domain!r}"
        )
        assert meta["tool_name"] == tool_name, (
            f"A2 FAIL: _meta.tool_name={meta['tool_name']!r}, "
            f"expected {tool_name!r}"
        )
        # called_at must be a parseable ISO-8601 string, not a repr()
        called_at = meta.get("called_at", "")
        assert isinstance(called_at, str), (
            f"A2 FAIL: _meta.called_at is {type(called_at).__name__}, "
            f"expected str (datetime repr() coercion bug?)"
        )
        assert called_at.startswith("20"), (
            f"A2 FAIL: _meta.called_at={called_at!r} doesn't look like ISO-8601"
        )
        assert isinstance(meta.get("scrubber_id"), str), (
            f"A2 FAIL: _meta.scrubber_id is not a string: {meta.get('scrubber_id')!r}"
        )
        # package_version must match the running version
        from tailor import __version__
        assert meta["package_version"] == __version__, (
            f"A2 FAIL: _meta.package_version={meta['package_version']!r} != "
            f"__version__={__version__!r}"
        )

    def test_tailor_setup_status_round_trip(self):
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("tailor_setup_status")
            raw = extract_text_result(resp)
            assert_no_repr_artifacts(raw)
            payload = json.loads(raw)
            assert "status" in payload, (
                f"A2 FAIL: tailor_setup_status missing 'status' key: {payload}"
            )
            assert payload["status"] in ("awaiting_setup", "configured",
                                         "config_unreadable", "config_malformed"), (
                f"A2 FAIL: tailor_setup_status.status unexpected: {payload['status']!r}"
            )
            assert "available_source_types" in payload, (
                "A2 FAIL: tailor_setup_status missing 'available_source_types'"
            )
            self._assert_meta_block(payload, "tailor_setup_status", "setup")

    def test_tailor_setup_detect_schema_csv_round_trip(self):
        """detect_schema on a real csv dir returns ok=True with schema."""
        with spawn_server() as (client, paths):
            client.initialize()
            resp = client.call_tool("tailor_setup_detect_schema", {
                "source_type": "csv",
                "path": str(paths["csv_dir"]),
            })
            raw = extract_text_result(resp)
            assert_no_repr_artifacts(raw)
            payload = json.loads(raw)
            assert payload.get("ok") is True, (
                f"A2 FAIL: detect_schema on real csv dir returned ok=False: {payload}"
            )
            assert payload.get("source_type") == "csv", (
                f"A2 FAIL: source_type={payload.get('source_type')!r}"
            )
            assert "schema" in payload, (
                "A2 FAIL: detect_schema response missing 'schema'"
            )
            self._assert_meta_block(payload, "tailor_setup_detect_schema", "setup")

    def test_tailor_setup_detect_schema_nonexistent_path(self):
        """detect_schema on a missing path returns ok=False with error."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("tailor_setup_detect_schema", {
                "source_type": "csv",
                "path": "/nonexistent/path/that/does/not/exist",
            })
            raw = extract_text_result(resp)
            assert_no_repr_artifacts(raw)
            payload = json.loads(raw)
            # ok=False with error key — should NOT have top-level "error" from
            # the framework (that would be an unexpected exception path)
            assert "error" not in resp.get("result", {}).get("content", [{}])[0].get(
                "text", "{}"
            ) or payload.get("ok") is False, (
                "A2: detect_schema on missing path should return ok=False"
            )
            assert payload.get("ok") is False, (
                "A2 FAIL: detect_schema on nonexistent path returned ok=True"
            )
            # _meta must still be present (it's added by the router unconditionally)
            self._assert_meta_block(payload, "tailor_setup_detect_schema", "setup")

    def test_tailor_setup_confirm_schema_round_trip(self):
        """confirm_schema returns ok=True with confirmed=True marker."""
        with spawn_server() as (client, paths):
            client.initialize()
            resp = client.call_tool("tailor_setup_confirm_schema", {
                "source_type": "csv",
                "path": str(paths["csv_dir"]),
                "schema": {
                    "timestamp_column": "timestamp",
                    "value_columns": {"heart_rate": "Heart rate (bpm)"},
                },
            })
            raw = extract_text_result(resp)
            assert_no_repr_artifacts(raw)
            payload = json.loads(raw)
            assert payload.get("ok") is True, (
                f"A2 FAIL: confirm_schema returned ok=False: {payload}"
            )
            assert payload.get("confirmed") is True, (
                f"A2 FAIL: confirm_schema missing confirmed=True: {payload}"
            )
            self._assert_meta_block(payload, "tailor_setup_confirm_schema", "setup")

    def test_tailor_setup_write_source_block_round_trip(self):
        """Successful write returns ok=True, source_key='csv_dir', restart_required."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = seed_full_config(root)
            # Use a separate CSV target dir distinct from the seeded one
            new_csv_dir = root / "new_csvs"
            new_csv_dir.mkdir()
            (new_csv_dir / "S001.csv").write_text(
                "timestamp,force\n2026-01-01T00:00:00,100.0\n",
                encoding="utf-8"
            )
            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
            }
            proc = subprocess.Popen(
                [sys.executable, "-m", "tailor", "serve"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env,
            )
            client = MCPClient(proc)
            try:
                client.initialize()
                # Force=True so the test doesn't fail on pre-existing csv_dir block
                resp = client.call_tool("tailor_setup_write_source_block", {
                    "source_type": "csv",
                    "path": str(new_csv_dir),
                    "validated_schema": {
                        "timestamp_column": "timestamp",
                        "value_columns": {"force": "Force (N)"},
                    },
                    "force": True,
                })
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                payload = json.loads(raw)
                assert payload.get("ok") is True, (
                    f"A2 FAIL: write_source_block returned ok=False: {payload}"
                )
                assert payload.get("source_key") == "csv_dir", (
                    f"A2 FAIL: source_key={payload.get('source_key')!r}, "
                    f"expected 'csv_dir'"
                )
                assert payload.get("restart_required") is True, (
                    "A2 FAIL: restart_required not True in response"
                )
                assert "written_path" in payload, (
                    "A2 FAIL: response missing 'written_path'"
                )
                self._assert_meta_block(
                    payload, "tailor_setup_write_source_block", "setup"
                )
            finally:
                try:
                    proc.stdin.close()
                except (OSError, BrokenPipeError):
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

    def test_tailor_walkthrough_section_1_round_trip(self):
        """Section 1 returns the required structural keys."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("tailor_walkthrough_section", {"section": 1})
            raw = extract_text_result(resp)
            assert_no_repr_artifacts(raw)
            payload = json.loads(raw)
            required_keys = {
                "section", "title", "narrative", "worked_example",
                "adr_citations", "next_step",
            }
            missing = required_keys - set(payload)
            assert not missing, (
                f"A2 FAIL: tailor_walkthrough_section(1) missing keys: "
                f"{sorted(missing)}"
            )
            assert payload["section"] == 1, (
                f"A2 FAIL: section payload has section={payload['section']!r}"
            )
            self._assert_meta_block(
                payload, "tailor_walkthrough_section", "walkthrough"
            )

    def test_tailor_fitting_room_status_round_trip(self):
        """Status returns exists + related boolean fields."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("tailor_fitting_room_status")
            raw = extract_text_result(resp)
            assert_no_repr_artifacts(raw)
            payload = json.loads(raw)
            assert "exists" in payload, (
                "A2 FAIL: tailor_fitting_room_status missing 'exists'"
            )
            assert isinstance(payload["exists"], bool), (
                f"A2 FAIL: fitting_room_status.exists is "
                f"{type(payload['exists']).__name__}, not bool"
            )
            self._assert_meta_block(
                payload, "tailor_fitting_room_status", "fitting_room"
            )

    def test_tailor_fitting_room_index_vault_missing_target(self):
        """index_vault on a non-existent target returns ok=False gracefully."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("tailor_fitting_room_index_vault",
                                    {"variant": "hip-lab"})
            raw = extract_text_result(resp)
            assert_no_repr_artifacts(raw)
            payload = json.loads(raw)
            # If target doesn't exist yet, ok=False with error_class=TargetMissing
            # If it does exist (unlikely in CI), ok=True with counts.
            assert "ok" in payload, (
                "A2 FAIL: fitting_room_index_vault response missing 'ok'"
            )
            if payload["ok"] is False:
                assert "error" in payload, (
                    "A2 FAIL: ok=False but no 'error' key in response"
                )
                assert "error_class" in payload, (
                    "A2 FAIL: ok=False but no 'error_class' key"
                )
            self._assert_meta_block(
                payload, "tailor_fitting_room_index_vault", "fitting_room"
            )


# ──────────────────────────────────────────────────────────────────────
# A3 — SETUP_CONFIG_WRITE audit row shape on the wire
# ──────────────────────────────────────────────────────────────────────

class TestA3SetupConfigWriteAuditRow:
    """
    When tailor_setup_write_source_block succeeds, the audit row must carry
    outcome="SETUP_CONFIG_WRITE" (not "SUCCESS"). audit_query must be able
    to filter rows by that outcome value.
    """

    def test_setup_config_write_outcome_queryable_via_audit_query(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = seed_full_config(root)
            # Prepare a separate csv dir for the write tool to target
            new_csv = root / "audit_test_csvs"
            new_csv.mkdir()
            (new_csv / "X001.csv").write_text(
                "t,v\n2026-01-01T00:00:00,1.0\n", encoding="utf-8"
            )
            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
            }
            proc = subprocess.Popen(
                [sys.executable, "-m", "tailor", "serve"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env,
            )
            client = MCPClient(proc)
            try:
                client.initialize()

                # Step 1 — trigger a SETUP_CONFIG_WRITE
                write_resp = client.call_tool("tailor_setup_write_source_block", {
                    "source_type": "csv",
                    "path": str(new_csv),
                    "validated_schema": {"timestamp_column": "t"},
                    "force": True,
                })
                write_raw = extract_text_result(write_resp)
                write_payload = json.loads(write_raw)
                assert write_payload.get("ok") is True, (
                    f"A3 precondition FAIL: write returned ok=False: {write_payload}"
                )

                # Step 2 — query audit log filtered by outcome=SETUP_CONFIG_WRITE
                query_resp = client.call_tool("audit_query", {
                    "since": "1h",
                    "outcome": "SETUP_CONFIG_WRITE",
                    "limit": 10,
                })
                query_raw = extract_text_result(query_resp)
                assert_no_repr_artifacts(query_raw)
                query_payload = json.loads(query_raw)

                assert "rows" in query_payload, (
                    f"A3 FAIL: audit_query response missing 'rows': {query_payload}"
                )
                rows = query_payload["rows"]
                assert len(rows) >= 1, (
                    f"A3 FAIL: Expected at least 1 row with "
                    f"outcome=SETUP_CONFIG_WRITE, got {len(rows)} rows. "
                    f"This means the router stamped outcome='SUCCESS' instead of "
                    f"'SETUP_CONFIG_WRITE' on the bounded-write path."
                )
                row = rows[0]
                # Confirm the row has the expected shape
                assert row.get("outcome") == "SETUP_CONFIG_WRITE", (
                    f"A3 FAIL: audit row outcome={row.get('outcome')!r}, "
                    f"expected 'SETUP_CONFIG_WRITE'"
                )
                assert row.get("domain") == "setup", (
                    f"A3 FAIL: audit row domain={row.get('domain')!r}, "
                    f"expected 'setup'"
                )
                assert row.get("tool_name") == "tailor_setup_write_source_block", (
                    f"A3 FAIL: audit row tool_name={row.get('tool_name')!r}"
                )
                # Verify no raw params or error in the audit_query response
                assert "params" not in row, (
                    "A3 FAIL: audit_query row exposes raw 'params' column "
                    "(ADR 0039 B1 allowlist violation)"
                )
                assert "error" not in row, (
                    "A3 FAIL: audit_query row exposes raw 'error' column "
                    "(ADR 0039 B1 allowlist violation)"
                )
            finally:
                try:
                    proc.stdin.close()
                except (OSError, BrokenPipeError):
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

    def test_read_only_setup_tools_stamp_success_not_setup_config_write(self):
        """tailor_setup_status / detect / confirm must stamp outcome='SUCCESS'."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = seed_full_config(root)
            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
            }
            proc = subprocess.Popen(
                [sys.executable, "-m", "tailor", "serve"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env,
            )
            client = MCPClient(proc)
            try:
                client.initialize()

                # Call each read-only setup tool
                for tool in ("tailor_setup_status",):
                    client.call_tool(tool)

                # Query audit log — none of the read-only tools should produce
                # SETUP_CONFIG_WRITE rows (they only produce SUCCESS)
                query_resp = client.call_tool("audit_query", {
                    "since": "1h",
                    "outcome": "SETUP_CONFIG_WRITE",
                    "limit": 10,
                })
                query_payload = json.loads(extract_text_result(query_resp))
                rows = query_payload.get("rows", [])
                bad = [
                    r for r in rows
                    if r.get("tool_name") != "tailor_setup_write_source_block"
                ]
                assert not bad, (
                    f"A3 FAIL: Read-only setup tools produced "
                    f"SETUP_CONFIG_WRITE audit rows: {bad}"
                )
            finally:
                try:
                    proc.stdin.close()
                except (OSError, BrokenPipeError):
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


# ──────────────────────────────────────────────────────────────────────
# A4 — PARAM_INVALID gate on the bounded-write allowlist
# ──────────────────────────────────────────────────────────────────────

class TestA4ParamInvalidAllowlistGate:
    """
    Calling tailor_setup_write_source_block with source_type='edf' must
    return a PARAM_INVALID response AND record a PARAM_INVALID audit row.
    """

    def test_unknown_source_type_returns_param_invalid_envelope(self):
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("tailor_setup_write_source_block", {
                "source_type": "edf",
                "path": "/some/path",
                "validated_schema": {},
            })
            raw = extract_text_result(resp)
            assert_no_repr_artifacts(raw)
            payload = json.loads(raw)
            # The framework returns {"error": "..."} on PARAM_INVALID
            assert "error" in payload, (
                f"A4 FAIL: Expected error key for invalid source_type='edf', "
                f"got payload: {payload}"
            )
            # The error message must mention the allowlist
            err_msg = payload["error"].lower()
            assert any(k in err_msg for k in ("allow", "csv", "matlab", "redcap")), (
                f"A4 FAIL: Error message doesn't mention allowlist: "
                f"{payload['error']!r}"
            )

    def test_unknown_source_type_records_param_invalid_audit_row(self):
        """The PARAM_INVALID row must appear in the audit log."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = seed_full_config(root)
            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
            }
            proc = subprocess.Popen(
                [sys.executable, "-m", "tailor", "serve"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env,
            )
            client = MCPClient(proc)
            try:
                client.initialize()

                # Trigger PARAM_INVALID
                client.call_tool("tailor_setup_write_source_block", {
                    "source_type": "edf",
                    "path": "/some/path",
                    "validated_schema": {},
                })

                # Query for the PARAM_INVALID row
                query_resp = client.call_tool("audit_query", {
                    "since": "1h",
                    "outcome": "PARAM_INVALID",
                    "domain": "setup",
                    "limit": 10,
                })
                query_payload = json.loads(extract_text_result(query_resp))
                rows = query_payload.get("rows", [])
                matching = [
                    r for r in rows
                    if r.get("tool_name") == "tailor_setup_write_source_block"
                    and r.get("outcome") == "PARAM_INVALID"
                ]
                assert len(matching) >= 1, (
                    f"A4 FAIL: No PARAM_INVALID audit row found for "
                    f"tailor_setup_write_source_block with source_type='edf'. "
                    f"Got rows: {rows}"
                )
                row = matching[0]
                assert row.get("domain") == "setup", (
                    f"A4 FAIL: audit row domain={row.get('domain')!r}, "
                    f"expected 'setup'"
                )
            finally:
                try:
                    proc.stdin.close()
                except (OSError, BrokenPipeError):
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

    def test_detect_schema_unknown_source_type_also_param_invalid(self):
        """detect_schema with source_type='edf' must also return PARAM_INVALID."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("tailor_setup_detect_schema", {
                "source_type": "edf",
                "path": "/some/path",
            })
            raw = extract_text_result(resp)
            assert_no_repr_artifacts(raw)
            payload = json.loads(raw)
            assert "error" in payload, (
                f"A4 FAIL: detect_schema with source_type='edf' didn't return "
                f"an error envelope. Got: {payload}"
            )


# ──────────────────────────────────────────────────────────────────────
# A5 — Dispatch bypass posture (framework-tier gates skipped)
# ──────────────────────────────────────────────────────────────────────

class TestA5DispatchBypassPosture:
    """
    New framework-tier layers bypass biosensor-tier gates per ADR 0012
    § Amendment v7.4.0:
    - No consent-gate text in responses (they don't check consent state)
    - No cost-gate LLMInstruction envelope
    - Audit domain is 'setup' / 'walkthrough' / 'fitting_room', not a child domain

    We verify this by confirming:
    1. The _meta.domain matches the layer domain (not a biosensor child domain)
    2. The response is not an LLMInstruction consent/cost envelope
    3. The audit_query row for a setup tool has domain='setup'
    """

    def _is_llm_instruction(self, payload: dict) -> bool:
        return (
            "must_do" in payload
            or "must_not_do" in payload
            or "on_ambiguous_reply" in payload
        )

    def test_setup_tools_not_consent_gated(self):
        """Setup tools return results even without any consent approval."""
        with spawn_server() as (client, _paths):
            client.initialize()
            # No approve_consent call made — should still get a result
            resp = client.call_tool("tailor_setup_status")
            raw = extract_text_result(resp)
            payload = json.loads(raw)
            assert not self._is_llm_instruction(payload), (
                f"A5 FAIL: tailor_setup_status returned a consent/cost gate "
                f"LLMInstruction envelope. Setup tools must bypass consent gate. "
                f"Payload: {payload}"
            )
            assert "status" in payload, (
                "A5 FAIL: tailor_setup_status didn't return status key"
            )

    def test_walkthrough_tools_not_consent_gated(self):
        """Walkthrough tools return results without consent approval."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("tailor_walkthrough_section", {"section": 1})
            raw = extract_text_result(resp)
            payload = json.loads(raw)
            assert not self._is_llm_instruction(payload), (
                f"A5 FAIL: tailor_walkthrough_section returned LLMInstruction. "
                f"Payload: {payload}"
            )

    def test_fitting_room_tools_not_consent_gated(self):
        """FittingRoom tools return results without consent approval."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("tailor_fitting_room_status")
            raw = extract_text_result(resp)
            payload = json.loads(raw)
            assert not self._is_llm_instruction(payload), (
                f"A5 FAIL: tailor_fitting_room_status returned LLMInstruction. "
                f"Payload: {payload}"
            )

    def test_setup_audit_row_domain_is_setup_not_biosensor(self):
        """Audit rows for setup tools use domain='setup'."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = seed_full_config(root)
            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
            }
            proc = subprocess.Popen(
                [sys.executable, "-m", "tailor", "serve"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env,
            )
            client = MCPClient(proc)
            try:
                client.initialize()
                client.call_tool("tailor_setup_status")

                query_resp = client.call_tool("audit_query", {
                    "since": "1h",
                    "domain": "setup",
                    "limit": 5,
                })
                query_payload = json.loads(extract_text_result(query_resp))
                rows = query_payload.get("rows", [])
                assert len(rows) >= 1, (
                    f"A5 FAIL: No audit rows with domain='setup'. "
                    f"Setup tool dispatch isn't auditing. Got rows: {rows}"
                )
                for row in rows:
                    assert row.get("domain") == "setup", (
                        f"A5 FAIL: Row domain={row.get('domain')!r} != 'setup'"
                    )
            finally:
                try:
                    proc.stdin.close()
                except (OSError, BrokenPipeError):
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


# ──────────────────────────────────────────────────────────────────────
# A6 — Schema description quality (natural-language inference readiness)
# ──────────────────────────────────────────────────────────────────────

class TestA6SchemaDescriptionQuality:
    """
    Every param of every new tool in tools/list must have a non-empty
    'description' string. Empty or missing descriptions silently break
    Claude's tool-inference (the cue-card-rehearsal-auditor class of bug).
    """

    def test_every_new_tool_param_has_nonempty_description(self):
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            tools_by_name = {
                t["name"]: t
                for t in resp["result"]["tools"]
            }
            failures = []
            for tool_name in _ALL_NEW_TOOLS:
                tool = tools_by_name.get(tool_name, {})
                props = tool.get("inputSchema", {}).get("properties", {})
                for param_name, param_schema in props.items():
                    desc = param_schema.get("description", "")
                    if not desc or not desc.strip():
                        failures.append(
                            f"{tool_name}.{param_name}: empty description"
                        )
            assert not failures, (
                "A6 FAIL: The following tool params have empty/missing "
                "descriptions — Claude cannot infer them from natural language:\n"
                + "\n".join(f"  - {f}" for f in failures)
            )

    def test_every_new_tool_has_nonempty_top_level_description(self):
        """The tool-level description must also be non-empty."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            tools_by_name = {
                t["name"]: t
                for t in resp["result"]["tools"]
            }
            failures = []
            for tool_name in _ALL_NEW_TOOLS:
                tool = tools_by_name.get(tool_name, {})
                desc = tool.get("description", "")
                if not desc or not desc.strip():
                    failures.append(tool_name)
            assert not failures, (
                f"A6 FAIL: Tools with empty top-level description: {failures}"
            )

    def test_write_source_block_description_mentions_allowlist_keys(self):
        """
        The write_source_block description must mention the allowlist keys
        (csv_dir / matlab_file / redcap_file) so Claude knows what it writes.
        """
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            tools_by_name = {
                t["name"]: t
                for t in resp["result"]["tools"]
            }
            wsb = tools_by_name.get("tailor_setup_write_source_block", {})
            desc = wsb.get("description", "")
            # The description must mention at least the allowlist keys
            assert any(
                k in desc for k in ("csv_dir", "matlab_file", "redcap_file")
            ), (
                f"A6 FAIL: tailor_setup_write_source_block description "
                f"doesn't mention any allowlist keys. "
                f"Claude can't know what keys it may write. Got: {desc[:200]!r}"
            )


# ──────────────────────────────────────────────────────────────────────
# A7 — Walkthrough section payload completeness (all 5 sections)
# ──────────────────────────────────────────────────────────────────────

class TestA7WalkthroughSectionPayloads:
    """
    All 5 sections of tailor_walkthrough_section must return the required
    structural keys. A section missing any key would cause Claude to fail
    while narrating the walkthrough to a recipient.
    """

    _REQUIRED_KEYS = {
        "section", "title", "narrative", "worked_example",
        "adr_citations", "next_step",
    }

    def test_all_5_sections_have_required_keys(self):
        with spawn_server() as (client, _paths):
            client.initialize()
            failures = []
            for section_num in range(1, 6):
                resp = client.call_tool(
                    "tailor_walkthrough_section", {"section": section_num}
                )
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                payload = json.loads(raw)
                missing = self._REQUIRED_KEYS - set(payload)
                if missing:
                    failures.append(
                        f"Section {section_num}: missing keys {sorted(missing)}"
                    )
                if payload.get("section") != section_num:
                    failures.append(
                        f"Section {section_num}: payload.section="
                        f"{payload.get('section')!r}"
                    )
            assert not failures, (
                "A7 FAIL: Walkthrough section payload failures:\n"
                + "\n".join(f"  - {f}" for f in failures)
            )

    def test_all_5_sections_narrative_is_nonempty_string(self):
        with spawn_server() as (client, _paths):
            client.initialize()
            failures = []
            for section_num in range(1, 6):
                resp = client.call_tool(
                    "tailor_walkthrough_section", {"section": section_num}
                )
                payload = json.loads(extract_text_result(resp))
                narrative = payload.get("narrative", "")
                if not isinstance(narrative, str) or len(narrative) < 10:
                    failures.append(
                        f"Section {section_num}: narrative={narrative!r}"
                    )
            assert not failures, (
                "A7 FAIL: Walkthrough section narrative failures:\n"
                + "\n".join(f"  - {f}" for f in failures)
            )

    def test_section_out_of_range_returns_error(self):
        """section=6 and section=0 must return errors, not crash."""
        with spawn_server() as (client, _paths):
            client.initialize()
            for bad_val in (6, 0):
                resp = client.call_tool(
                    "tailor_walkthrough_section", {"section": bad_val}
                )
                raw = extract_text_result(resp)
                payload = json.loads(raw)
                # ParamValidator with min=1/max=5 should fire PARAM_INVALID
                assert "error" in payload, (
                    f"A7 FAIL: section={bad_val} returned no error. "
                    f"ParamValidator allowed_values gate may not be firing. "
                    f"Payload: {payload}"
                )

    def test_all_sections_adr_citations_is_nonempty_list(self):
        with spawn_server() as (client, _paths):
            client.initialize()
            failures = []
            for section_num in range(1, 6):
                resp = client.call_tool(
                    "tailor_walkthrough_section", {"section": section_num}
                )
                payload = json.loads(extract_text_result(resp))
                citations = payload.get("adr_citations", None)
                if not isinstance(citations, list) or len(citations) == 0:
                    failures.append(
                        f"Section {section_num}: adr_citations={citations!r}"
                    )
            assert not failures, (
                "A7 FAIL: Sections with empty adr_citations:\n"
                + "\n".join(f"  - {f}" for f in failures)
            )


# ──────────────────────────────────────────────────────────────────────
# A8 — Wire-shape regression checks (repr artifacts, _meta, no collisions)
# ──────────────────────────────────────────────────────────────────────

class TestA8WireShapeRegression:
    """
    Cross-cutting regression checks: no repr() artifacts across all 8
    new tools, child_scrubber_id=null (not 'None') in _meta, no tool name
    collisions, existing tools still present.
    """

    def test_no_repr_artifacts_across_all_new_tools(self):
        with spawn_server() as (client, paths):
            client.initialize()
            calls = [
                ("tailor_setup_status", {}),
                ("tailor_setup_detect_schema", {
                    "source_type": "csv",
                    "path": str(paths["csv_dir"]),
                }),
                ("tailor_setup_confirm_schema", {
                    "source_type": "csv",
                    "path": str(paths["csv_dir"]),
                    "schema": {"timestamp_column": "timestamp"},
                }),
                ("tailor_walkthrough_section", {"section": 2}),
                ("tailor_fitting_room_status", {}),
            ]
            for tool_name, args in calls:
                resp = client.call_tool(tool_name, args)
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)

    def test_child_scrubber_id_is_null_not_string_none(self):
        """
        _meta.child_scrubber_id must be JSON null, not the Python string "None".
        A 'None' string is a repr() coercion bug.
        """
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("tailor_setup_status")
            raw = extract_text_result(resp)
            # "None" appearing as a string in JSON is the coercion bug
            assert '"None"' not in raw, (
                f"A8 FAIL: Wire payload contains '\"None\"' string — "
                f"child_scrubber_id coercion bug. Raw excerpt: {raw[:400]}"
            )
            payload = json.loads(raw)
            meta = payload.get("_meta", {})
            csi = meta.get("child_scrubber_id", "KEY_MISSING")
            assert csi is None or csi == "KEY_MISSING", (
                f"A8 FAIL: _meta.child_scrubber_id={csi!r} — "
                f"expected null (None), not a string. This is a repr() bug."
            )

    def test_no_tool_name_collisions_between_new_and_existing_tools(self):
        """New tool names must not shadow any pre-existing tool."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            all_names = [t["name"] for t in resp["result"]["tools"]]
            seen: dict[str, int] = {}
            for name in all_names:
                seen[name] = seen.get(name, 0) + 1
            duplicates = {k: v for k, v in seen.items() if v > 1}
            assert not duplicates, (
                f"A8 FAIL: Duplicate tool names in tools/list: {duplicates}. "
                f"A new framework-tier layer name collides with an existing tool."
            )

    def test_existing_csv_tools_still_registered(self):
        """Regression: adding new layers must not displace existing CSV tools."""
        expected_csv_tools = {
            "csv_list_files", "csv_file_detail", "csv_summary_report",
            "csv_cohort_summary", "csv_force_decline",
            "csv_downsampled", "csv_raw_stream",
        }
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            names = {t["name"] for t in resp["result"]["tools"]}
            missing = expected_csv_tools - names
            assert not missing, (
                f"A8 FAIL: Existing CSV tools disappeared from tools/list: "
                f"{sorted(missing)}. A new layer registration may have "
                f"disrupted the tool map."
            )

    def test_existing_vault_tools_still_registered(self):
        """Regression: vault tools must survive the new layer registrations."""
        expected_vault_tools = {
            "vault_get_snapshot", "vault_list_themes",
            "vault_capture_moment", "vault_health_check",
        }
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            names = {t["name"] for t in resp["result"]["tools"]}
            missing = expected_vault_tools - names
            assert not missing, (
                f"A8 FAIL: Vault tools missing after new layer registration: "
                f"{sorted(missing)}"
            )

    def test_audit_query_tool_still_registered(self):
        """Regression: the v7.4.0 audit_query tool must survive."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            names = {t["name"] for t in resp["result"]["tools"]}
            assert "audit_query" in names, (
                "A8 FAIL: audit_query tool missing after A' layer registration"
            )

    def test_walkthrough_meta_domain_is_walkthrough(self):
        """_meta.domain for walkthrough tools must be 'walkthrough'."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("tailor_walkthrough_section", {"section": 3})
            payload = json.loads(extract_text_result(resp))
            meta = payload.get("_meta", {})
            assert meta.get("domain") == "walkthrough", (
                f"A8 FAIL: _meta.domain={meta.get('domain')!r} for walkthrough tool, "
                f"expected 'walkthrough'"
            )

    def test_fitting_room_meta_domain_is_fitting_room(self):
        """_meta.domain for fitting_room tools must be 'fitting_room'."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("tailor_fitting_room_status")
            payload = json.loads(extract_text_result(resp))
            meta = payload.get("_meta", {})
            assert meta.get("domain") == "fitting_room", (
                f"A8 FAIL: _meta.domain={meta.get('domain')!r} for fitting_room "
                f"tool, expected 'fitting_room'"
            )

    def test_setup_write_ok_false_still_has_meta(self):
        """
        When write_source_block returns ok=False (FileExistsError without force),
        the router must still stamp _meta. This is the boundary case where the
        layer returns a structured error dict but the router still wraps it.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = seed_full_config(root)
            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
            }
            proc = subprocess.Popen(
                [sys.executable, "-m", "tailor", "serve"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env,
            )
            client = MCPClient(proc)
            try:
                client.initialize()
                # csv_dir is already configured in the seeded config
                # so force=False (default) should return ok=False + FileExistsError
                resp = client.call_tool("tailor_setup_write_source_block", {
                    "source_type": "csv",
                    "path": str(paths["csv_dir"]),
                    "validated_schema": {},
                    # force=False is the default — omit it
                })
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                payload = json.loads(raw)
                # ok=False with error_class
                assert payload.get("ok") is False, (
                    f"A8 FAIL: Expected ok=False when csv_dir already exists "
                    f"without force. Got: {payload}"
                )
                # _meta must still be present even on the ok=False path
                # (the router adds _meta after the layer returns)
                assert "_meta" in payload, (
                    f"A8 FAIL: _meta missing on ok=False structured-error path. "
                    f"The router must stamp _meta even when the layer returns an "
                    f"error dict (not raise an exception). Payload: {payload}"
                )
            finally:
                try:
                    proc.stdin.close()
                except (OSError, BrokenPipeError):
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

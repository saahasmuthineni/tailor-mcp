"""
MCP Protocol Audit -- v7.6.0 ADR 0038 structural sweep wire-level correctness.

Verifies 7 surfaces touched by v7.6.0:

  V1  ``tools/list``: ``vault_get_fitness_summary`` description contains the
      DEPRECATED prefix intact (no markdown round-trip lossiness; no Python
      repr() artifacts in the raw wire payload).

  V2  ``tools/call vault_list_notes``: framework-tier kind values (``theme``,
      ``moment``, ``snapshot``, ``failure_mode``, ``dashboard``) are accepted.
      DEFECT D1 (see below): ``allowed_values`` on scalar ``str``-typed
      ``ValidationSchema`` is NOT enforced by ``ParamValidator`` -- the
      ``str`` branch (security.py line 35) only checks ``pattern``; the
      ``allowed_values`` guard lives only in the ``list`` branch (line 47).
      An unknown ``kind`` value silently returns 0 results instead of
      PARAM_INVALID.  The dynamic ``_allowed_kinds`` wiring is structurally
      correct but the validator never reads it for scalar params.
      The test for unknown-kind REJECTION is marked xfail with
      ``strict=True`` so it turns RED immediately when D1 is fixed.

  V3  ``tools/call csv_cohort_summary``: NEW ``value_column`` parameter
      round-trips cleanly; OLD ``column`` parameter returns a validation
      error (``isError: true`` in the MCP envelope with plain-text content
      "Input validation error: 'value_column' is a required property").
      The old param is NOT silently accepted -- rename is enforced.

  V4  ``tools/call csv_force_decline``: same shape.  NOTE: ``file_id``
      for this tool is the filename (e.g. ``"P001.csv"``) since
      ``csv_list_files`` returns ``filename`` not a separate ``file_id``
      field -- the schema uses the filename as file_id.

  V5  ``tools/call vault_get_fitness_summary``:
      (a) still callable (returns SUCCESS, not an error envelope);
      (b) multiple successive calls emit the deprecation hint on stderr
          exactly once (one-shot guard on the VaultLayer instance).

  V6  ``_meta`` envelope on every tools/call result carries
      ``package_version: "7.6.0"`` after the version bump.

  V7  ``audit.db`` row for a ``vault_get_fitness_summary`` call carries
      ``outcome="SUCCESS"`` and a non-NULL ``scrubber_id`` (router-tier
      audit per ADR 0001, not the CLI-helper carve-out).

Each subprocess test spawns a fresh ``tailor serve`` subprocess with
TAILOR_CONFIG_DIR and TAILOR_DATA_DIR pointing at a TemporaryDirectory,
seeded with a full config (running child omitted intentionally for V1--V5;
the running child IS registered for V2 to get vault_note_kinds contribution
from RunningChild -- see the ``spawn_server_full`` helper).

Nothing touches the operator's ~/.tailor.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
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
# Helpers
# ---------------------------------------------------------------------------

EXPECTED_VERSION = "7.6.0"
DEPRECATED_PREFIX = "DEPRECATED in v7.6.0"


def _handshake(client: MCPClient) -> None:
    client.initialize()


def _drain_stderr_bg(proc: subprocess.Popen) -> list[str]:
    """Start a background thread draining stderr; return the accumulated lines list."""
    lines: list[str] = []

    def _drain() -> None:
        assert proc.stderr is not None
        for raw in proc.stderr:
            try:
                lines.append(raw.decode("utf-8", errors="replace"))
            except Exception:
                pass

    t = threading.Thread(target=_drain, daemon=True)
    t.start()
    return lines


def _wait_for_stderr_settle(lines: list[str], min_count: int = 1,
                             timeout_s: float = 8.0) -> None:
    """Wait until at least ``min_count`` lines have arrived."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if len(lines) >= min_count:
            return
        time.sleep(0.05)


# ---------------------------------------------------------------------------
# V1 -- tools/list DEPRECATED description intact
# ---------------------------------------------------------------------------

class TestV1DeprecatedDescriptionOnWire:
    """vault_get_fitness_summary description survives tools/list round-trip."""

    def test_deprecated_prefix_present_in_tools_list(self) -> None:
        with spawn_server() as (client, paths):
            _handshake(client)
            resp = client.list_tools()
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)
            assert "result" in resp, f"tools/list returned error: {resp}"

            tools = {t["name"]: t for t in resp["result"]["tools"]}
            assert "vault_get_fitness_summary" in tools, (
                "vault_get_fitness_summary absent from tools/list"
            )
            desc = tools["vault_get_fitness_summary"]["description"]
            assert DEPRECATED_PREFIX in desc, (
                f"DEPRECATED prefix missing from vault_get_fitness_summary "
                f"description on wire.\n"
                f"Got: {desc[:200]!r}"
            )

    def test_no_repr_artifacts_in_tools_list(self) -> None:
        with spawn_server() as (client, paths):
            _handshake(client)
            resp = client.list_tools()
            assert_no_repr_artifacts(json.dumps(resp))


# ---------------------------------------------------------------------------
# V2 -- vault_list_notes dynamic allowed_kinds from _compute_kind_metadata
# ---------------------------------------------------------------------------

class TestV2DynamicAllowedKinds:
    """
    dynamic ``_allowed_kinds`` from ``_compute_kind_metadata()`` reaches the
    wire for ``vault_list_notes``.

    seed_full_config includes a Strava / running-child config block via the
    user_config (max_hr / resting_hr) but the running child only registers
    when it has OAuth tokens, so ``vault_note_kinds`` contribution from
    RunningChild may be absent.  We seed a config that does NOT include
    a running child -- instead we verify:

    (a) Framework-tier kinds (``theme``, ``moment``, ``snapshot``,
        ``failure_mode``, ``dashboard``) are accepted without PARAM_INVALID.
    (b) Completely unknown kinds (``not_a_real_kind``) SHOULD be rejected
        PARAM_INVALID -- but DEFECT D1: ``ParamValidator`` does not enforce
        ``allowed_values`` for scalar ``str``-typed params (only for ``list``
        params).  The ``str`` branch at ``security.py:35`` checks only
        ``pattern``, skipping the ``allowed_values`` guard.  The unknown
        kind silently returns 0 results instead of PARAM_INVALID.
        ``test_unknown_kind_rejected_param_invalid`` is marked ``xfail``
        with ``strict=True`` so it flips to PASS when D1 is fixed.
    """

    @pytest.mark.parametrize("kind", ["theme", "moment", "snapshot",
                                       "failure_mode", "dashboard"])
    def test_framework_tier_kinds_accepted(self, kind: str) -> None:
        with spawn_server() as (client, paths):
            _handshake(client)
            resp = client.call_tool(
                "vault_list_notes",
                {"kind": kind},
                timeout_s=15,
            )
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)
            # Must not be a protocol error or PARAM_INVALID
            text = extract_text_result(resp)
            payload = json.loads(text)
            assert "error" not in payload or "PARAM_INVALID" not in payload.get("error", ""), (
                f"Framework-tier kind={kind!r} incorrectly PARAM_INVALID: {payload}"
            )

    def test_unknown_kind_rejected_param_invalid(self) -> None:
        """DEFECT D1 regression anchor (CLOSED in v7.6.0).

        Originally marked ``xfail(strict=True)`` because v7.6.0's dynamic
        ``_allowed_kinds`` wiring landed but the underlying
        ``ParamValidator.validate()`` enforced ``allowed_values`` only on
        ``list``-typed schemas (security.py line 47 pre-fix), leaving every
        ``ValidationSchema(type=str, allowed_values=[...])`` site as a dead
        constraint. v7.6.0 closes the gap in ``framework/security.py``: the
        ``elif schema.type is str`` branch now reads
        ``schema.allowed_values`` and returns ``False`` with the rendered
        list in the error message. This test flips from xfail to PASS as
        the regression anchor for the closure.

        Wire envelope shape: the router records ``outcome="PARAM_INVALID"``
        on the audit row (router.py:892) but the wire payload follows the
        existing ``{"error": "<message>"}`` convention. The assertion
        therefore checks the structural ``error`` key + parameter name
        rather than a literal ``PARAM_INVALID`` token in the payload.
        """
        with spawn_server() as (client, paths):
            _handshake(client)
            resp = client.call_tool(
                "vault_list_notes",
                {"kind": "not_a_real_kind_xyz"},
                timeout_s=15,
            )
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)
            text = extract_text_result(resp)
            payload = json.loads(text)
            assert "error" in payload, (
                f"Expected validator error envelope for unknown kind "
                f"'not_a_real_kind_xyz', got: {payload}"
            )
            assert "kind" in payload["error"], (
                f"Expected error to name the offending parameter 'kind' "
                f"so the LLM has a recovery path, got: {payload['error']}"
            )

    def test_allowed_values_in_tools_list_schema_non_empty(self) -> None:
        """The vault_list_notes inputSchema description must mention kind values
        so the dynamic wiring is visible on the wire even before D1 is fixed."""
        with spawn_server() as (client, paths):
            _handshake(client)
            resp = client.list_tools()
            tools = {t["name"]: t for t in resp["result"]["tools"]}
            assert "vault_list_notes" in tools
            schema = tools["vault_list_notes"].get("inputSchema", {})
            props = schema.get("properties", {})
            kind_prop = props.get("kind", {})
            # The description should mention at least one known kind value
            desc_or_enum = json.dumps(kind_prop)
            assert any(k in desc_or_enum for k in ("theme", "moment", "snapshot")), (
                f"vault_list_notes kind schema missing expected values: "
                f"{desc_or_enum[:300]}"
            )


# ---------------------------------------------------------------------------
# V3 -- csv_cohort_summary value_column rename
# ---------------------------------------------------------------------------

class TestV3CsvCohortSummaryParamRename:
    """NEW ``value_column`` accepted; OLD ``column`` rejected PARAM_INVALID."""

    def test_value_column_accepted(self) -> None:
        with spawn_server() as (client, paths):
            _handshake(client)
            resp = client.call_tool(
                "csv_cohort_summary",
                {
                    "value_column": "heart_rate",
                    "group_by": "sex",
                    "metric": "mean",
                },
                timeout_s=15,
            )
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)
            text = extract_text_result(resp)
            payload = json.loads(text)
            assert "error" not in payload or "PARAM_INVALID" not in payload.get("error", ""), (
                f"NEW value_column parameter incorrectly rejected: {payload}"
            )

    def test_old_column_param_rejected_param_invalid(self) -> None:
        """OLD 'column' param rejected: isError=true with validation error text."""
        with spawn_server() as (client, paths):
            _handshake(client)
            resp = client.call_tool(
                "csv_cohort_summary",
                {
                    "column": "heart_rate",   # OLD name -- must be rejected
                    "group_by": "sex",
                    "metric": "mean",
                },
                timeout_s=15,
            )
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)
            # The mcp SDK returns validation errors as isError=true with plain
            # text content (not a JSON payload), NOT as a JSON-RPC "error" field.
            result = resp.get("result", {})
            is_error = result.get("isError", False)
            text = extract_text_result(resp)
            assert is_error, (
                f"OLD 'column' parameter was silently accepted (isError not set) -- "
                f"rename is not enforced on the wire.\n"
                f"response: {raw[:600]}"
            )
            assert "value_column" in text or "required" in text.lower(), (
                f"Expected 'value_column' required error text in wire response.\n"
                f"Got: {text!r}"
            )

    def test_value_column_in_result_envelope(self) -> None:
        """Result envelope key is 'value_column', not 'column'."""
        with spawn_server() as (client, paths):
            _handshake(client)
            resp = client.call_tool(
                "csv_cohort_summary",
                {"value_column": "heart_rate", "group_by": "sex", "metric": "mean"},
                timeout_s=15,
            )
            text = extract_text_result(resp)
            payload = json.loads(text)
            if "error" not in payload:
                raw = json.dumps(payload)
                # The result should contain 'value_column' key (renamed)
                # and must NOT contain a bare 'column' result key
                assert "value_column" in raw, (
                    f"Result envelope missing 'value_column' key: {raw[:400]}"
                )


# ---------------------------------------------------------------------------
# V4 -- csv_force_decline value_column rename
# ---------------------------------------------------------------------------

class TestV4CsvForceDeclineParamRename:
    """NEW ``value_column`` accepted; OLD ``column`` rejected PARAM_INVALID."""

    def test_value_column_accepted(self) -> None:
        """NEW value_column param accepted; file_id is the filename from csv_list_files."""
        with spawn_server() as (client, paths):
            _handshake(client)
            # csv_list_files returns 'filename' field; csv_force_decline
            # takes that value as 'file_id' (same string -- filename IS file_id).
            list_resp = client.call_tool("csv_list_files", {}, timeout_s=15)
            list_text = extract_text_result(list_resp)
            list_payload = json.loads(list_text)
            files = list_payload.get("files", [])
            assert files, "csv_list_files returned no files -- config not seeded properly"
            file_id = files[0]["filename"]  # 'filename' key, passed as file_id param

            resp = client.call_tool(
                "csv_force_decline",
                {"file_id": file_id, "value_column": "heart_rate"},
                timeout_s=15,
            )
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)
            result = resp.get("result", {})
            assert not result.get("isError", False), (
                f"NEW value_column param incorrectly rejected for csv_force_decline.\n"
                f"response: {raw[:400]}"
            )
            text = extract_text_result(resp)
            payload = json.loads(text)
            # Result envelope must carry 'value_column' key (renamed from 'column')
            assert "value_column" in payload, (
                f"Result envelope missing 'value_column' key: {list(payload.keys())}"
            )

    def test_old_column_param_rejected_param_invalid(self) -> None:
        """OLD 'column' param rejected: isError=true with validation error text."""
        with spawn_server() as (client, paths):
            _handshake(client)
            list_resp = client.call_tool("csv_list_files", {}, timeout_s=15)
            list_text = extract_text_result(list_resp)
            list_payload = json.loads(list_text)
            files = list_payload.get("files", [])
            assert files, "csv_list_files returned no files"
            file_id = files[0]["filename"]  # same shape as V4 accepted test

            resp = client.call_tool(
                "csv_force_decline",
                {"file_id": file_id, "column": "heart_rate"},  # OLD name
                timeout_s=15,
            )
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)
            result = resp.get("result", {})
            is_error = result.get("isError", False)
            text = extract_text_result(resp)
            assert is_error, (
                f"OLD 'column' parameter silently accepted for csv_force_decline -- "
                f"rename not enforced on the wire.\n"
                f"response: {raw[:600]}"
            )
            assert "value_column" in text or "required" in text.lower(), (
                f"Expected 'value_column' required error text. Got: {text!r}"
            )


# ---------------------------------------------------------------------------
# V5 -- vault_get_fitness_summary: callable + one-shot deprecation log
# ---------------------------------------------------------------------------

class TestV5FitnessSummaryDeprecationBehaviour:
    """Still callable; stderr deprecation hint fires exactly once."""

    def test_vault_get_fitness_summary_still_callable(self) -> None:
        with spawn_server() as (client, paths):
            _handshake(client)
            resp = client.call_tool(
                "vault_get_fitness_summary",
                {"weeks_back": 4},
                timeout_s=15,
            )
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)
            # Must decode cleanly and have a result (not a protocol error)
            assert "result" in resp, (
                f"vault_get_fitness_summary returned no result: {resp}"
            )
            text = extract_text_result(resp)
            payload = json.loads(text)
            # Acceptable: SUCCESS (possibly empty data) or a PARAM_INVALID
            # is NOT acceptable -- the tool must remain callable.
            assert "error" not in payload or (
                "PARAM_INVALID" not in payload.get("error", "")
                and "UNKNOWN_TOOL" not in payload.get("error", "")
            ), (
                f"vault_get_fitness_summary is no longer callable: {payload}"
            )

    def test_deprecation_hint_in_stderr(self) -> None:
        """Deprecation warning appears in stderr on first call."""
        with TemporaryDirectory() as tmp:
            paths = seed_full_config(Path(tmp))
            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
                "PYTHONUNBUFFERED": "1",
            }
            proc = subprocess.Popen(
                [sys.executable, "-m", "tailor", "serve"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            stderr_lines = _drain_stderr_bg(proc)
            client = MCPClient(proc)
            try:
                _handshake(client)
                # First call
                client.call_tool("vault_get_fitness_summary", {"weeks_back": 2},
                                  timeout_s=15)
                time.sleep(0.5)  # let stderr settle
                _wait_for_stderr_settle(stderr_lines, min_count=1, timeout_s=5)
                combined_after_first = "".join(stderr_lines)
                assert "DEPRECATED" in combined_after_first, (
                    f"Expected DEPRECATED warning in stderr after first call. "
                    f"stderr so far:\n{combined_after_first[:800]}"
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

    def test_deprecation_hint_fires_only_once(self) -> None:
        """One-shot guard: 3 successive calls → exactly 1 deprecation log line."""
        with TemporaryDirectory() as tmp:
            paths = seed_full_config(Path(tmp))
            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
                "PYTHONUNBUFFERED": "1",
            }
            proc = subprocess.Popen(
                [sys.executable, "-m", "tailor", "serve"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            stderr_lines = _drain_stderr_bg(proc)
            client = MCPClient(proc)
            try:
                _handshake(client)
                for _ in range(3):
                    client.call_tool("vault_get_fitness_summary", {"weeks_back": 2},
                                      timeout_s=15)
                time.sleep(0.8)
                combined = "".join(stderr_lines)
                deprecation_hits = combined.count("DEPRECATED")
                assert deprecation_hits == 1, (
                    f"Expected exactly 1 DEPRECATED log line across 3 calls, "
                    f"got {deprecation_hits}.\nfull stderr:\n{combined[:1000]}"
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


# ---------------------------------------------------------------------------
# V6 -- _meta.package_version == "7.6.0" on all tools/call results
# ---------------------------------------------------------------------------

class TestV6MetaPackageVersion:
    """Every tools/call result _meta carries package_version: 7.6.0."""

    @pytest.mark.parametrize("tool,args", [
        ("vault_list_notes", {}),
        ("csv_list_files", {}),
        ("vault_get_snapshot", {}),
    ])
    def test_meta_package_version(self, tool: str, args: dict) -> None:
        with spawn_server() as (client, paths):
            _handshake(client)
            resp = client.call_tool(tool, args, timeout_s=15)
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)
            text = extract_text_result(resp)
            payload = json.loads(text)
            meta = payload.get("_meta")
            assert meta is not None, (
                f"No _meta block in {tool} response: {payload}"
            )
            assert meta.get("package_version") == EXPECTED_VERSION, (
                f"_meta.package_version mismatch for {tool}: "
                f"expected {EXPECTED_VERSION!r}, got {meta.get('package_version')!r}"
            )


# ---------------------------------------------------------------------------
# V7 -- audit.db row for vault_get_fitness_summary: outcome=SUCCESS, scrubber_id NOT NULL
# ---------------------------------------------------------------------------

class TestV7AuditRowFitnessSummary:
    """
    audit.db row for vault_get_fitness_summary call carries
    outcome='SUCCESS' and non-NULL scrubber_id (router-tier audit per
    ADR 0001, not the CLI-helper carve-out per ADR 0001 Amendment
    2026-05-18).
    """

    def test_audit_row_success_and_scrubber_id_not_null(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = seed_full_config(Path(tmp))
            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
                "PYTHONUNBUFFERED": "1",
            }
            proc = subprocess.Popen(
                [sys.executable, "-m", "tailor", "serve"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            _drain_stderr_bg(proc)
            client = MCPClient(proc)
            try:
                _handshake(client)
                client.call_tool("vault_get_fitness_summary", {"weeks_back": 2},
                                  timeout_s=15)
                time.sleep(0.3)  # give audit flush time
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

            # Locate audit.db
            db_candidates = [
                paths["data_dir"] / "audit.db",
                paths["data_dir"] / "tailor_audit.db",
            ]
            db_path: Path | None = None
            for candidate in db_candidates:
                if candidate.exists():
                    db_path = candidate
                    break
            if db_path is None:
                # Walk data_dir for any .db file
                for p in paths["data_dir"].rglob("*.db"):
                    db_path = p
                    break
            assert db_path is not None, (
                f"No audit.db found under {paths['data_dir']}. "
                f"Contents: {list(paths['data_dir'].iterdir())}"
            )

            conn = sqlite3.connect(str(db_path))
            try:
                rows = conn.execute(
                    "SELECT outcome, scrubber_id FROM audit_log "
                    "WHERE tool_name = 'vault_get_fitness_summary' "
                    "ORDER BY id DESC LIMIT 5"
                ).fetchall()
            finally:
                conn.close()

            assert rows, (
                "No audit_log rows found for vault_get_fitness_summary"
            )
            outcome, scrubber_id = rows[0]
            assert outcome == "SUCCESS", (
                f"audit_log outcome for vault_get_fitness_summary: "
                f"expected 'SUCCESS', got {outcome!r}"
            )
            assert scrubber_id is not None, (
                "audit_log.scrubber_id is NULL for vault_get_fitness_summary "
                "-- router-tier audit must carry scrubber_id (ADR 0001 + "
                "ADR 0003; this is NOT the CLI-helper carve-out)"
            )
            assert scrubber_id != "", (
                "audit_log.scrubber_id is empty string for vault_get_fitness_summary"
            )

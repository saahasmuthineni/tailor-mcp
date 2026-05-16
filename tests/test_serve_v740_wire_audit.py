"""
MCP Protocol Audit -- v7.4.0 wire-level correctness for audit_query.

Verifies the framework-tier audit_query surface shipped in v7.4.0:

  A1  ``audit_query`` appears in tools/list after initialize handshake.

  A2  Calling ``audit_query`` with ``since="1h"`` returns the structured
      envelope on the wire — keys ``rows``, ``row_count``,
      ``scope_statement`` — and stamps the standard ``_meta`` block with
      ``domain="audit_query"``, ``tier=1``, and
      ``source_metadata_fingerprint`` keyword present (per the v7.4.0
      extension of the v7.3.1 all-call-sites-sweep rule).

  A3  The wire envelope never carries raw ``params`` content or raw
      ``error`` strings — the load-bearing B1 column allowlist
      invariant proven against a real subprocess. Seeds a row with
      ``record_id="MRN-WIRE-99999"`` in params and verifies it never
      egresses through any return field.

  A4  Malformed ``since`` returns a structured error envelope
      (``{"error": ..., "original_since": "garbage"}``), not a Python
      traceback or generic 500.

  A5  ``include_self=true`` default surfaces audit_query rows in their
      own response — closes the v7.4.0 audit IMPORTANT-1.

  A6  Audit DB row for the audit_query call carries
      ``outcome="SUCCESS"``, ``scrubber_id="noop"``, and explicit
      ``source_metadata_fingerprint=NULL`` (the column was threaded but
      audit_query domain has no upstream trust root).

Each subprocess test spawns a fresh subprocess with a TemporaryDirectory
config so nothing touches the operator's ~/.tailor.
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
)


# ---------------------------------------------------------------------------
# Fixtures / helpers shared across this module
# ---------------------------------------------------------------------------


def _seed_config(root: Path) -> tuple[Path, Path]:
    """Seed a minimal config — csv_dir block to satisfy
    ``_demo_blocks_absent`` so SetupHelpLayer does NOT register, plus a
    vault path so the vault layer registers (giving us domains to query
    against)."""
    config_dir = root / "config"
    data_dir = root / "data"
    vault_path = root / "vault"
    csv_dir = root / "csvs"
    for p in (config_dir, data_dir, vault_path, csv_dir):
        p.mkdir(parents=True, exist_ok=True)

    (csv_dir / "P001.csv").write_text(
        "timestamp,heart_rate\n2026-01-01T08:00:00,72\n", encoding="utf-8",
    )

    cfg = {
        "max_hr": 185,
        "resting_hr": 55,
        "vault_path": str(vault_path),
        "csv_dir": {
            "path": str(csv_dir),
            "timestamp_column": "timestamp",
            "timestamp_format": "%Y-%m-%dT%H:%M:%S",
            "value_columns": {"heart_rate": "Heart rate (bpm)"},
        },
    }
    (config_dir / "user_config.json").write_text(
        json.dumps(cfg), encoding="utf-8",
    )
    return config_dir, data_dir


def _seed_audit_row_with_phi(
    data_dir: Path,
    *,
    record_id: str = "MRN-WIRE-99999",
    error_path: str = "/home/saahas/wire-secret-path",
) -> None:
    """Insert a representative audit row carrying PHI-shaped content in
    both ``params`` and ``error`` columns. Used to prove the B1 allowlist
    holds against real subprocess wire output."""
    db_path = data_dir / "audit.db"
    # Use a brand-new connection per row insert to avoid stepping on the
    # server subprocess's WAL writer.
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO audit_log (timestamp, domain, tool_name, tier, "
            "params, token_estimate, outcome, duration_ms, error, "
            "subject_id, scrubber_id, source_metadata_fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "2026-05-16T14:00:00+00:00",
                "redcap_file",
                "redcap_record_detail",
                1,
                json.dumps({"record_id": record_id}),
                420,
                "ERROR",
                18,
                f"failure at {error_path}: cost exceeded",
                "S004",
                "noop",
                "abcd1234",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _spawn(config_dir: Path, data_dir: Path) -> subprocess.Popen:
    env = {
        **os.environ,
        "TAILOR_CONFIG_DIR": str(config_dir),
        "TAILOR_DATA_DIR": str(data_dir),
        "PYTHONUNBUFFERED": "1",
    }
    return subprocess.Popen(
        [sys.executable, "-m", "tailor", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        bufsize=0,
    )


def _start_stderr_drain(proc: subprocess.Popen) -> list[str]:
    lines: list[str] = []

    def _drain() -> None:
        assert proc.stderr is not None
        while True:
            line = proc.stderr.readline()
            if not line:
                break
            lines.append(line.decode("utf-8", errors="replace").rstrip())

    t = threading.Thread(target=_drain, daemon=True, name="stderr-drain")
    t.start()
    return lines


def _teardown(proc: subprocess.Popen) -> None:
    try:
        if proc.stdin:
            proc.stdin.close()
    except (OSError, BrokenPipeError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


# ---------------------------------------------------------------------------
# A1 — audit_query surfaces in tools/list
# ---------------------------------------------------------------------------


class TestA1AuditQueryInToolsList:

    def test_audit_query_appears_in_tools_list(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            _start_stderr_drain(proc)
            client = MCPClient(proc)
            try:
                client.initialize()
                tools_resp = client.list_tools()
                tools = tools_resp["result"]["tools"]
                tool_names = {t["name"] for t in tools}
                assert "audit_query" in tool_names, (
                    "A1 FAIL: audit_query not in tools/list. "
                    f"Got: {sorted(tool_names)}"
                )
            finally:
                _teardown(proc)


# ---------------------------------------------------------------------------
# A2 — happy-path wire envelope shape
# ---------------------------------------------------------------------------


class TestA2HappyPathEnvelope:

    def test_envelope_has_rows_count_scope(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            _start_stderr_drain(proc)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("audit_query", {"since": "1h"})
                payload = json.loads(extract_text_result(resp))
                assert "rows" in payload
                assert "row_count" in payload
                assert "scope_statement" in payload
                assert isinstance(payload["rows"], list)
                assert payload["row_count"] == len(payload["rows"])
            finally:
                _teardown(proc)

    def test_meta_block_stamped_with_audit_query_domain(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            _start_stderr_drain(proc)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("audit_query", {"since": "1h"})
                payload = json.loads(extract_text_result(resp))
                meta = payload.get("_meta", {})
                assert meta.get("domain") == "audit_query"
                assert meta.get("tier") == 1
                assert meta.get("tool_name") == "audit_query"
                # v7.3.1 all-call-sites-sweep — key must be present even
                # though value is None for audit_query domain.
                assert "source_metadata_fingerprint" in meta
                assert meta["source_metadata_fingerprint"] is None
                assert meta.get("scrubber_id") == "noop"
            finally:
                _teardown(proc)


# ---------------------------------------------------------------------------
# A3 — B1 column allowlist holds on the wire
# ---------------------------------------------------------------------------


class TestA3B1AllowlistOnWire:
    """The load-bearing IRB-stakes invariant proven against a real
    subprocess: raw params and raw error never egress through the wire."""

    def test_seeded_phi_never_appears_in_response(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            # Boot once to ensure audit.db schema exists, then seed PHI
            # row directly, then re-spawn for the query.
            warmup = _spawn(cfg, dat)
            _start_stderr_drain(warmup)
            warmup_client = MCPClient(warmup)
            try:
                warmup_client.initialize()
            finally:
                _teardown(warmup)

            _seed_audit_row_with_phi(
                dat,
                record_id="MRN-WIRE-99999",
                error_path="/home/saahas/wire-secret-path",
            )

            proc = _spawn(cfg, dat)
            _start_stderr_drain(proc)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool(
                    "audit_query",
                    {"since": "30d", "domain": "redcap_file"},
                )
                raw = extract_text_result(resp)
                # Both PHI markers must be completely absent from the
                # wire payload (text form, before JSON parsing).
                assert "MRN-WIRE-99999" not in raw, (
                    "A3 FAIL: raw params content leaked via wire. "
                    "B1 allowlist violated."
                )
                assert "wire-secret-path" not in raw
                assert "/home/" not in raw
                # And the row IS present (we don't want a vacuous pass).
                payload = json.loads(raw)
                assert payload["row_count"] >= 1
                domains = {r["domain"] for r in payload["rows"]}
                assert "redcap_file" in domains
                # has_error must be true for the seeded ERROR row.
                err_rows = [
                    r for r in payload["rows"]
                    if r["domain"] == "redcap_file"
                    and r["outcome"] == "ERROR"
                ]
                assert err_rows and err_rows[0]["has_error"] is True
            finally:
                _teardown(proc)

    def test_no_repr_artifacts(self) -> None:
        """Cross-cutting: no Python repr() artifacts in the response,
        same shape as the v7.3.2 _dumps coercion seam check."""
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            _start_stderr_drain(proc)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("audit_query", {"since": "1h"})
                assert_no_repr_artifacts(extract_text_result(resp))
            finally:
                _teardown(proc)


# ---------------------------------------------------------------------------
# A4 — Malformed since returns structured error envelope
# ---------------------------------------------------------------------------


class TestA4MalformedSinceErrorEnvelope:

    def test_garbage_since_returns_structured_error(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            _start_stderr_drain(proc)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool(
                    "audit_query", {"since": "garbage"},
                )
                payload = json.loads(extract_text_result(resp))
                assert "error" in payload
                assert "original_since" in payload
                assert payload["original_since"] == "garbage"
            finally:
                _teardown(proc)

    def test_negative_since_returns_structured_error(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            _start_stderr_drain(proc)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool(
                    "audit_query", {"since": "-1h"},
                )
                payload = json.loads(extract_text_result(resp))
                assert "error" in payload
            finally:
                _teardown(proc)


# ---------------------------------------------------------------------------
# A5 — include_self default surfaces audit_query rows
# ---------------------------------------------------------------------------


class TestA5IncludeSelfDefault:

    def test_audit_query_rows_visible_by_default(self) -> None:
        """Make at least two audit_query calls; the second should see
        the first's row in its results because include_self defaults
        to true."""
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            _start_stderr_drain(proc)
            client = MCPClient(proc)
            try:
                client.initialize()
                # First call — gets recorded
                client.call_tool("audit_query", {"since": "1h"})
                # Tiny delay so the second call's `since` window can
                # include the first call's recorded row.
                time.sleep(0.1)
                # Second call — must see the first's row
                resp = client.call_tool("audit_query", {"since": "1h"})
                payload = json.loads(extract_text_result(resp))
                tools = {r["tool_name"] for r in payload["rows"]}
                assert "audit_query" in tools, (
                    "A5 FAIL: include_self=true default did not surface "
                    f"the prior audit_query row. Tools seen: {tools}"
                )
            finally:
                _teardown(proc)

    def test_include_self_false_excludes_audit_query(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            _start_stderr_drain(proc)
            client = MCPClient(proc)
            try:
                client.initialize()
                client.call_tool("audit_query", {"since": "1h"})
                time.sleep(0.1)
                resp = client.call_tool(
                    "audit_query",
                    {"since": "1h", "include_self": False},
                )
                payload = json.loads(extract_text_result(resp))
                tools = {r["tool_name"] for r in payload["rows"]}
                assert "audit_query" not in tools
            finally:
                _teardown(proc)


# ---------------------------------------------------------------------------
# A6 — Audit DB row for audit_query carries correct provenance
# ---------------------------------------------------------------------------


class TestA6AuditRowProvenance:

    def test_audit_query_call_writes_provenance_correctly(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            _start_stderr_drain(proc)
            client = MCPClient(proc)
            try:
                client.initialize()
                client.call_tool(
                    "audit_query",
                    {"since": "1h", "subject_id": "S004"},
                )
            finally:
                _teardown(proc)

            # Inspect audit.db directly to verify the row was written
            # with the correct kwargs (subject_id threaded, scrubber_id
            # = noop, source_metadata_fingerprint = NULL).
            conn = sqlite3.connect(str(dat / "audit.db"))
            try:
                row = conn.execute(
                    "SELECT domain, tool_name, outcome, subject_id, "
                    "scrubber_id, source_metadata_fingerprint "
                    "FROM audit_log WHERE tool_name='audit_query' "
                    "ORDER BY id DESC LIMIT 1"
                ).fetchone()
            finally:
                conn.close()

            assert row is not None, (
                "A6 FAIL: no audit_query row was recorded"
            )
            domain, tool_name, outcome, sid, scrubber, fp = row
            assert domain == "audit_query"
            assert tool_name == "audit_query"
            assert outcome == "SUCCESS"
            assert sid == "S004"  # threaded through from caller params
            assert scrubber == "noop"
            assert fp is None  # column threaded but value None

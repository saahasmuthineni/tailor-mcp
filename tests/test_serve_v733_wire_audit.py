"""
MCP Protocol Audit -- v7.3.3 wire-level correctness.

Verifies the breaker-exemption refactor shipped in v7.3.3:

  B1  Five consecutive REDCap mismatch errors MUST still return the
      REDCAP_METADATA_FINGERPRINT_MISMATCH envelope on calls 4 and 5 --
      NOT a generic "Circuit open for redcap_file" envelope.  This is
      the user-visible affordance the v7.3.3 ADR 0003 amendment ratifies.

  B2  The audit DB contains 5 ERROR rows after the B1 sequence.  Each
      row must carry outcome=ERROR and a non-None source_metadata_fingerprint
      column (the boot fingerprint, since the mismatch fires before the
      successful scrub path). This confirms the breaker exemption did not
      accidentally skip audit stamping.

  B3  The initialize handshake + tools/list tool count is unchanged vs
      v7.3.2 (no schema changes introduced by the refactor; the presence
      of REDCap tools confirms the register path was unaffected).

  B4  Contract test: OperatorActionRequired.__init__ raises TypeError
      when recovery_action is empty or missing -- loud at author-time,
      not silent at call-time.  Tested in-process (no subprocess needed).

  B5  The W5 AST invariant (28 audit.record call sites; all child-tier
      sites carry source_metadata_fingerprint=) is unaffected by the
      v7.3.3 router edits.  Re-runs the same assertion class from v7.3.2
      to confirm no regression from the isinstance() additions.

Each subprocess test spawns a fresh subprocess with a TemporaryDirectory
config so nothing touches the operator's ~/.tailor.
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
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

def _redcap_fixture_path() -> Path:
    """Return the bundled redcap_demo fixture path."""
    import importlib.resources as ir

    import tailor._fixtures as _fx_pkg
    base = ir.files(_fx_pkg)
    demo = base / "redcap_demo"
    try:
        return Path(str(demo))
    except TypeError:
        import contextlib
        with ir.as_file(demo) as p:
            return p


def _seed_config_with_mismatch(
    root: Path,
    *,
    good_redcap_path: str,
    stale_redcap_path: str,
) -> tuple[Path, Path]:
    """
    Seed a config that boots against ``good_redcap_path`` (a valid REDCap
    fixture). After the server is up the test caller may swap in
    ``stale_redcap_path`` to trigger mismatch errors.

    Returns (config_dir, data_dir).
    """
    config_dir = root / "config"
    data_dir = root / "data"
    vault_path = root / "vault"
    csv_dir = root / "csvs"
    for p in (config_dir, data_dir, vault_path, csv_dir):
        p.mkdir(parents=True, exist_ok=True)

    (csv_dir / "P001.csv").write_text(
        "timestamp,heart_rate\n2026-01-01T08:00:00,72\n", encoding="utf-8"
    )
    (csv_dir / "P002.csv").write_text(
        "timestamp,heart_rate\n2026-01-01T08:00:00,80\n", encoding="utf-8"
    )
    (csv_dir / "metadata.json").write_text(
        json.dumps({
            "P001.csv": {"group": "control"},
            "P002.csv": {"group": "intervention"},
        }),
        encoding="utf-8",
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
        "redcap_file": {
            "path": good_redcap_path,
            "records_file": "records.csv",
            "project_metadata_file": "project_metadata.csv",
        },
    }
    (config_dir / "user_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return config_dir, data_dir


def _spawn(config_dir: Path, data_dir: Path) -> subprocess.Popen:
    env = {
        **os.environ,
        "TAILOR_CONFIG_DIR": str(config_dir),
        "TAILOR_DATA_DIR": str(data_dir),
        # PYTHONUNBUFFERED forces the child to flush stdout line-by-line
        # even when pytest's capture wraps the inherited file descriptors.
        # Without this, MCPClient.recv()'s readline() can block forever
        # on a response the child has written but not flushed — observed
        # under `pytest` (no -s) but not under `pytest -s` or raw subprocess
        # invocation. v7.3.2 wire tests do not hit this because they only
        # spawn one short-lived subprocess per test method; v7.3.3 B1
        # spawns via fixture and shares the proc across five tool calls,
        # which is enough to surface the buffering interaction.
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
    """
    Start a background daemon thread that continuously reads from proc.stderr.

    On Windows, the subprocess stderr pipe has a ~4KB buffer. When the
    server emits log lines (including INFO lines for OperatorActionRequired
    conditions), that buffer fills and the server blocks on its next write
    before it can return a response. Draining in a background thread
    prevents that stall. Returns the list that is appended to (for
    diagnostic inspection in failure cases).
    """
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
# B1 + B2 — Breaker-exemption wire contract
# ---------------------------------------------------------------------------

class TestB1BreakerExemptionOnWire:
    """
    B1: Five consecutive mismatch calls must all return the mismatch
    envelope, never the circuit-open envelope.

    Strategy: use the bundled fixture as the boot path; create a
    mutated copy of project_metadata.csv (one identifier flag toggled)
    so RedcapFileChild._detect_fingerprint_mismatch fires.  The config
    points the server at the mutated directory, but we seed the server
    with the ORIGINAL directory so it boots cleanly, then swap in the
    mutated path via a fresh config write and REUSE the same subprocess
    -- this mirrors the real-world "metadata file edited after serve
    started" scenario.

    Simpler alternative that avoids config re-read complexity: create
    two separate redcap directories with different metadata fingerprints,
    configure the server with one, then construct a mismatch by writing
    a ``stale_metadata.csv`` alongside the live metadata.  Easiest
    approach that is actually supported: configure the server with the
    REAL fixture path but physically write a modified metadata.csv into
    it (since the fixture is bundled, we copy it to a temp dir first).
    """

    @pytest.fixture()
    def mismatch_dirs(self, tmp_path):
        """
        Yield (good_redcap_dir, config_dir, data_dir, client, proc).

        good_redcap_dir: copy of the bundled fixture.
        After yielding, the caller may modify good_redcap_dir/project_metadata.csv
        to trigger a mismatch on the next call.
        """
        import shutil

        fixture = _redcap_fixture_path()
        redcap_dir = tmp_path / "redcap"
        shutil.copytree(str(fixture), str(redcap_dir))

        config_dir, data_dir = _seed_config_with_mismatch(
            tmp_path,
            good_redcap_path=str(redcap_dir),
            stale_redcap_path=str(redcap_dir),  # same; we mutate in-place
        )
        proc = _spawn(config_dir, data_dir)
        _start_stderr_drain(proc)  # prevent Windows 4KB pipe-buffer stall
        client = MCPClient(proc)
        try:
            # Handshake first, then corrupt the metadata
            client.initialize()
            yield client, redcap_dir, config_dir, data_dir, proc
        finally:
            _teardown(proc)

    def _corrupt_metadata(self, redcap_dir: Path) -> None:
        """Flip an existing non-identifier field to identifier in project_metadata.csv.

        The bundled fixture uses quoted CSV; identifier flags are stored as
        the literal string "y" in column index 10 (0-based).  We flip "sex"
        from non-identifier (empty string) to identifier ("y") to change the
        canonical sorted-tuple fingerprint without touching the file structure.
        """
        import csv
        import io
        meta_path = redcap_dir / "project_metadata.csv"
        content = meta_path.read_text(encoding="utf-8")

        # Parse, mutate, rewrite. Find the first row with an empty Identifier?
        # column and set it to "y".
        rows = list(csv.DictReader(io.StringIO(content)))
        fieldnames = list(csv.DictReader(io.StringIO(content)).fieldnames or [])
        mutated = False
        for row in rows:
            if row.get("Identifier?", "y") == "":
                row["Identifier?"] = "y"
                mutated = True
                break

        assert mutated, (
            "Failed to find a non-identifier field to corrupt in "
            f"{meta_path}; fixture shape may have changed."
        )

        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)
        meta_path.write_text(out.getvalue(), encoding="utf-8")

    def test_b1_five_consecutive_mismatch_calls_never_circuit_open(
        self, mismatch_dirs
    ):
        """
        B1: All 5 mismatch error envelopes contain the mismatch key,
        NOT 'Circuit open'.
        """
        client, redcap_dir, config_dir, data_dir, proc = mismatch_dirs
        self._corrupt_metadata(redcap_dir)

        errors = []
        for i in range(5):
            resp = client.call_tool("redcap_list_records", {})
            raw = extract_text_result(resp)
            assert_no_repr_artifacts(raw)
            body = json.loads(raw)
            assert "error" in body, (
                f"Call {i+1}: expected error envelope, got: {body}"
            )
            error_str = body["error"]
            errors.append(error_str)

            # Must NOT be a circuit-open envelope
            assert "Circuit open" not in error_str, (
                f"Call {i+1}: got circuit-open envelope instead of mismatch. "
                f"Breaker-exemption failed on the wire. Error: {error_str!r}"
            )
            # Must be the mismatch envelope
            assert "REDCAP_METADATA_FINGERPRINT_MISMATCH" in error_str, (
                f"Call {i+1}: expected REDCAP_METADATA_FINGERPRINT_MISMATCH, "
                f"got: {error_str!r}"
            )

        # Both fingerprints must be visible in at least one mismatch envelope
        # (64-char hex strings)
        hex64 = re.compile(r"[0-9a-f]{64}")
        matches = hex64.findall(errors[0])
        assert len(matches) >= 2, (
            f"Expected two 64-char hex fingerprints in mismatch error string, "
            f"found {len(matches)}: {errors[0]!r}"
        )

    def test_b1_call_4_and_5_still_return_mismatch_envelope(
        self, mismatch_dirs
    ):
        """
        B1 targeted: explicitly verify calls 4 and 5 (the calls that would
        be swallowed by the breaker without the exemption).
        """
        client, redcap_dir, config_dir, data_dir, proc = mismatch_dirs
        self._corrupt_metadata(redcap_dir)

        for call_num in range(1, 6):
            resp = client.call_tool("redcap_list_records", {})
            raw = extract_text_result(resp)
            body = json.loads(raw)
            error_str = body.get("error", "")

            if call_num >= 4:
                assert "REDCAP_METADATA_FINGERPRINT_MISMATCH" in error_str, (
                    f"Call {call_num}: breaker-exemption FAILED on the wire. "
                    f"Expected mismatch envelope; got: {error_str!r}"
                )
                assert "Circuit open" not in error_str, (
                    f"Call {call_num}: circuit-open envelope returned; "
                    f"breaker counted the exempt exception. "
                    f"Error: {error_str!r}"
                )

    def test_b2_audit_db_contains_5_error_rows_after_mismatch_sequence(
        self, mismatch_dirs
    ):
        """
        B2: After 5 consecutive mismatch calls, audit.db must contain
        5 rows with outcome=ERROR for domain=redcap_file, each carrying
        a non-None source_metadata_fingerprint (the boot fingerprint).
        """
        client, redcap_dir, config_dir, data_dir, proc = mismatch_dirs
        self._corrupt_metadata(redcap_dir)

        for _ in range(5):
            client.call_tool("redcap_list_records", {})

        # Flush and read the DB
        _teardown(proc)

        db_path = data_dir / "audit.db"
        assert db_path.exists(), f"audit.db not found at {db_path}"

        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                "SELECT outcome, source_metadata_fingerprint, error "
                "FROM audit_log "
                "WHERE domain='redcap_file' AND outcome='ERROR' "
                "ORDER BY id"
            ).fetchall()
        finally:
            conn.close()

        assert len(rows) >= 5, (
            f"Expected 5 ERROR rows in audit.db for redcap_file, got {len(rows)}"
        )

        hex64 = re.compile(r"^[0-9a-f]{64}$")
        for i, (outcome, fingerprint, error) in enumerate(rows[:5]):
            assert outcome == "ERROR", f"Row {i+1}: outcome={outcome!r}"
            # source_metadata_fingerprint carries the BOOT fingerprint
            assert fingerprint is not None, (
                f"Row {i+1}: source_metadata_fingerprint is NULL — "
                f"audit stamping was skipped on the exempt path"
            )
            assert hex64.match(str(fingerprint)), (
                f"Row {i+1}: source_metadata_fingerprint is not 64-char hex: "
                f"{fingerprint!r}"
            )
            assert "REDCAP_METADATA_FINGERPRINT_MISMATCH" in str(error), (
                f"Row {i+1}: error column doesn't contain mismatch key: "
                f"{error!r}"
            )


# ---------------------------------------------------------------------------
# B3 — Initialize handshake + tool count unchanged
# ---------------------------------------------------------------------------

class TestB3InitializeAndToolCount:
    """
    B3: The refactor must not change the registered tool count.
    initialize handshake must complete without error.
    """

    def test_b3_initialize_succeeds_and_tool_count_matches_v732(self, tmp_path):
        import shutil
        fixture = _redcap_fixture_path()
        redcap_dir = tmp_path / "redcap"
        shutil.copytree(str(fixture), str(redcap_dir))
        config_dir, data_dir = _seed_config_with_mismatch(
            tmp_path,
            good_redcap_path=str(redcap_dir),
            stale_redcap_path=str(redcap_dir),
        )
        proc = _spawn(config_dir, data_dir)
        _start_stderr_drain(proc)
        client = MCPClient(proc)
        try:
            init_resp = client.initialize()
            # initialize must not be an error response
            assert "error" not in init_resp, (
                f"initialize returned error: {init_resp}"
            )
            assert init_resp.get("result") is not None, (
                f"initialize returned no result: {init_resp}"
            )

            tools_resp = client.list_tools()
            assert "error" not in tools_resp, (
                f"tools/list returned error: {tools_resp}"
            )
            tools = tools_resp["result"]["tools"]
            names = {t["name"] for t in tools}

            # REDCap tools registered
            for expected in [
                "redcap_list_records", "redcap_record_detail",
                "redcap_summary_report", "redcap_cohort_summary",
                "redcap_records", "redcap_raw_records",
            ]:
                assert expected in names, (
                    f"Tool {expected!r} missing after v7.3.3 refactor"
                )

            # Tool count must match v7.3.2: 6 redcap + 7 csv + 25 vault +
            # 1 local_llm + 12 running + consent tools = same as pre-refactor.
            # We verify >= 44 (the "all children loaded" threshold from the
            # Phase-1 spec) and that no tools vanished vs the 6 we named above.
            assert len(tools) >= 44, (
                f"Tool count {len(tools)} is below the 44-tool threshold "
                f"that indicates all children registered"
            )
        finally:
            _teardown(proc)

    def test_b3_no_traceback_in_stderr_on_boot(self, tmp_path):
        """Server stderr must not contain 'Traceback' after boot.

        Uses the drain buffer (not client.read_stderr()) so it is
        compatible with _start_stderr_drain having claimed the pipe.
        """
        import shutil
        fixture = _redcap_fixture_path()
        redcap_dir = tmp_path / "redcap"
        shutil.copytree(str(fixture), str(redcap_dir))
        config_dir, data_dir = _seed_config_with_mismatch(
            tmp_path,
            good_redcap_path=str(redcap_dir),
            stale_redcap_path=str(redcap_dir),
        )
        proc = _spawn(config_dir, data_dir)
        stderr_lines = _start_stderr_drain(proc)
        client = MCPClient(proc)
        try:
            client.initialize()
            # One tool call to confirm the server is fully up and logged
            client.call_tool("csv_list_files", {})
            time.sleep(0.3)  # let any lingering log lines drain
            stderr_so_far = "\n".join(stderr_lines)
            assert "Traceback" not in stderr_so_far, (
                f"Traceback in stderr on boot:\n{stderr_so_far[:1000]}"
            )
        finally:
            _teardown(proc)


# ---------------------------------------------------------------------------
# B4 — OperatorActionRequired constructor guard (in-process)
# ---------------------------------------------------------------------------

class TestB4OperatorActionRequiredConstructorGuard:
    """
    B4: OperatorActionRequired must raise TypeError on empty / missing
    recovery_action. This is the loud-at-author-time guard that prevents
    a child author from silently defeating the breaker without providing
    a recovery affordance.
    """

    def test_b4_empty_recovery_action_raises_type_error(self):
        from tailor.framework.security import OperatorActionRequired
        with pytest.raises(TypeError, match="recovery_action"):
            OperatorActionRequired("something went wrong", recovery_action="")

    def test_b4_whitespace_only_recovery_action_raises_type_error(self):
        from tailor.framework.security import OperatorActionRequired
        with pytest.raises(TypeError, match="recovery_action"):
            OperatorActionRequired("something", recovery_action="   ")

    def test_b4_missing_recovery_action_raises_type_error(self):
        from tailor.framework.security import OperatorActionRequired
        with pytest.raises(TypeError):
            OperatorActionRequired("something")  # recovery_action not passed

    def test_b4_valid_recovery_action_succeeds(self):
        from tailor.framework.security import OperatorActionRequired
        exc = OperatorActionRequired(
            "mismatch detected",
            recovery_action="tailor redcap reattest",
        )
        assert exc.recovery_action == "tailor redcap reattest"
        assert "mismatch detected" in str(exc)

    def test_b4_redcap_mismatch_is_subclass_of_operator_action_required(self):
        from tailor.children.redcap.child import RedcapMetadataFingerprintMismatch
        from tailor.framework.security import OperatorActionRequired
        assert issubclass(RedcapMetadataFingerprintMismatch, OperatorActionRequired), (
            "RedcapMetadataFingerprintMismatch must subclass OperatorActionRequired "
            "so the router's isinstance check fires"
        )

    def test_b4_redcap_mismatch_carries_recovery_action(self):
        """Verify the reparented exception still constructs cleanly."""
        from tailor.children.redcap.child import RedcapMetadataFingerprintMismatch
        exc = RedcapMetadataFingerprintMismatch(
            fingerprint_at_boot="a" * 64,
            fingerprint_on_disk="b" * 64,
        )
        assert exc.recovery_action, "recovery_action must be non-empty"
        assert "reattest" in exc.recovery_action.lower(), (
            f"Expected 'reattest' in recovery_action; got: {exc.recovery_action!r}"
        )


# ---------------------------------------------------------------------------
# B5 — W5 AST invariant unaffected by v7.3.3 router edits
# ---------------------------------------------------------------------------

class TestB5W5AstInvariantUnchanged:
    """
    B5: Re-run the W5 AST invariant after the v7.3.3 router changes
    to confirm no regression from the isinstance() additions.

    The v7.3.3 patch added two isinstance checks in the exception
    handlers but must not remove any ``source_metadata_fingerprint=``
    kwargs from audit.record calls.  The AST walk is the only check
    that cannot be fooled by textual adjacency.
    """

    def _load_router_source(self) -> str:
        import tailor.framework.router as router_mod
        return Path(inspect.getfile(router_mod)).read_text(encoding="utf-8")

    def _find_audit_record_calls(self, source: str) -> list[ast.Call]:
        """
        Return every ``self._audit.record(...)`` call node in the AST.
        Uses ast.walk for structural, not textual, detection.
        """
        tree = ast.parse(source)
        calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr != "record":
                continue
            val = func.value
            if not isinstance(val, ast.Attribute):
                continue
            if val.attr != "_audit":
                continue
            calls.append(node)
        return calls

    def test_b5_total_audit_record_call_count_unchanged(self):
        """31 audit.record calls as of v7.4.0 (was 28 in v7.3.2/v7.3.3;
        +3 sites in _dispatch_audit_query per ADR 0012 § Amendment
        v7.4.0)."""
        source = self._load_router_source()
        calls = self._find_audit_record_calls(source)
        assert len(calls) == 31, (
            f"Expected 31 self._audit.record() calls in router.py; "
            f"found {len(calls)}. If a new framework-tier layer was "
            f"added, update this count and the W5 sweep test in "
            f"tests/test_serve_v732_wire_audit.py to match."
        )

    def test_b5_child_tier_audit_calls_carry_source_metadata_fingerprint(self):
        """
        Every audit.record call that carries child_scrubber_id= must also
        carry source_metadata_fingerprint= — this is the W5 invariant.

        The v7.3.3 patch adds isinstance checks in the same exception handlers
        as the audit calls; the fingerprint kwargs must remain intact.
        """
        source = self._load_router_source()
        calls = self._find_audit_record_calls(source)

        violations = []
        for call in calls:
            kwarg_names = {kw.arg for kw in call.keywords}
            if "child_scrubber_id" in kwarg_names:
                if "source_metadata_fingerprint" not in kwarg_names:
                    violations.append(
                        f"  Line {call.lineno}: has child_scrubber_id= "
                        f"but missing source_metadata_fingerprint="
                    )

        assert not violations, (
            "W5 invariant violated after v7.3.3 patch — "
            "audit.record() call(s) carry child_scrubber_id= "
            "but lack source_metadata_fingerprint=:\n"
            + "\n".join(violations)
        )

    def test_b5_both_exception_handler_audit_calls_carry_fingerprint(self):
        """
        The two exception handlers that gained isinstance checks in v7.3.3
        (public _dispatch at ~line 740, internal _dispatch_internal at ~line 1310)
        must both carry source_metadata_fingerprint= in their audit.record calls.

        In router.py the outcome is passed as a positional argument (5th slot,
        0-indexed), not as a keyword.  We match on positional string constants
        "ERROR" and "ERROR_INTERNAL" rather than keyword args.
        """
        source = self._load_router_source()
        calls = self._find_audit_record_calls(source)

        # The router calls: self._audit.record(domain, tool_name, tier, cleaned,
        #   0, "ERROR", duration_ms, ...)  -- outcome is args[5] (0-based).
        # We match any call whose positional args contain the literal string
        # "ERROR" or "ERROR_INTERNAL" anywhere (position-agnostic is fine here;
        # neither string appears as a keyword value in other contexts).
        error_handler_calls = []
        for call in calls:
            for arg in call.args:
                if isinstance(arg, ast.Constant) and arg.value in (
                    "ERROR", "ERROR_INTERNAL"
                ):
                    error_handler_calls.append(call)
                    break

        assert len(error_handler_calls) >= 2, (
            f"Expected at least 2 ERROR/ERROR_INTERNAL audit.record() calls "
            f"in router.py; found {len(error_handler_calls)}. "
            f"Check that the v7.3.3 patch did not change the positional "
            f"outcome argument to a keyword."
        )

        for call in error_handler_calls:
            kwarg_names = {kw.arg for kw in call.keywords}
            assert "source_metadata_fingerprint" in kwarg_names, (
                f"Line {call.lineno}: exception-handler audit.record() "
                f"call missing source_metadata_fingerprint= kwarg. "
                f"Present kwargs: {kwarg_names}"
            )

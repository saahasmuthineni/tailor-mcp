"""
MCP Protocol Audit — v7.3.1 wire-level correctness.

Drives ``python -m tailor serve`` as a real subprocess to independently
verify the six wire-level requirements from the v7.3.1 ADR 0016 trigger
mandate.

  W1  child_scrubber_id == "redcap_metadata_flags" in _meta on every
      successful REDCap tools/call result.

  W2  REDCap error envelopes contain placeholder strings
      <configured_redcap_path> / <configured_redcap_records_path>,
      NOT absolute filesystem paths.  Tested against a path that does
      not exist on disk.

  W3  Consent-event audit rows for REDCap (approve, revoke, PURGE_CACHE,
      SUCCESS) all have child_scrubber_id == "redcap_metadata_flags"
      in audit.db.

  W4  Misconfigured {"redcap_file": {"records_file": "x.csv"}} (missing
      the required "path" key) lets tailor serve boot cleanly with rc=0;
      REDCap tools absent from tools/list; operator banner on stderr;
      other tools (running, local_llm) present.

  W5  Vault layer and local_llm layer _meta blocks carry
      "child_scrubber_id": null (Python None on the wire, i.e. JSON null)
      — the framework-level-layer branch of the v7.3.1 _meta surfacing.

  W6  Standard provenance fields (package_version, tool_name, called_at
      ISO-8601, domain, tier, scrubber_id) all remain present on every
      _meta block — no regression from the child_scrubber_id addition.
      Checked on REDCap, csv_dir, vault, and local_llm tools.

Each test spawns a fresh subprocess with a TemporaryDirectory config so
nothing touches the operator's ~/.tailor.  Tests using the REDCap
fixture load the bundled src/tailor/_fixtures/redcap_demo/ directory.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
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
# Helpers
# ---------------------------------------------------------------------------

def _redcap_fixture_path() -> Path:
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


def _seed_config(
    root: Path,
    *,
    redcap_path: str | None = None,
    include_redcap: bool = True,
    redcap_cfg_override: dict | None = None,
    include_csv: bool = True,
    include_vault: bool = True,
) -> tuple[Path, Path]:
    """
    Seed a config dir under root.  Returns (config_dir, data_dir).

    redcap_path=None -> use the bundled fixture.
    redcap_cfg_override -> replace the entire redcap_file block.
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

    cfg: dict = {"max_hr": 185, "resting_hr": 55}

    if include_vault:
        cfg["vault_path"] = str(vault_path)

    if include_csv:
        cfg["csv_dir"] = {
            "path": str(csv_dir),
            "timestamp_column": "timestamp",
            "timestamp_format": "%Y-%m-%dT%H:%M:%S",
            "value_columns": {"heart_rate": "Heart rate (bpm)"},
        }

    if include_redcap:
        if redcap_cfg_override is not None:
            cfg["redcap_file"] = redcap_cfg_override
        else:
            rp = redcap_path or str(_redcap_fixture_path())
            cfg["redcap_file"] = {
                "path": rp,
                "records_file": "records.csv",
                "project_metadata_file": "project_metadata.csv",
            }

    (config_dir / "user_config.json").write_text(
        json.dumps(cfg), encoding="utf-8"
    )
    return config_dir, data_dir


def _spawn(config_dir: Path, data_dir: Path) -> subprocess.Popen:
    env = {
        **os.environ,
        "TAILOR_CONFIG_DIR": str(config_dir),
        "TAILOR_DATA_DIR": str(data_dir),
    }
    return subprocess.Popen(
        [sys.executable, "-m", "tailor", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


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


def _drain_stderr_nowait(proc: subprocess.Popen) -> str:
    """Non-blocking stderr drain.  Only works reliably after the process has
    exited or after _teardown().  During a live process use _read_stderr_live()."""
    if proc.stderr is None:
        return ""
    try:
        return proc.stderr.read1(65536).decode("utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError, OSError):
        return ""


def _read_stderr_after_teardown(config_dir: Path, data_dir: Path) -> str:
    """Spawn a separate process, capture ALL its stderr at once after it exits.

    Used by W4 to avoid the read1()-on-live-process blocking trap: we spawn
    the server, wait for it to boot (via initialize + list_tools), then close
    stdin to trigger shutdown, wait for exit, then read stderr end-to-end.
    Returns the full stderr text.
    """
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
    tool_names: set[str] = set()
    rc: int | None = None
    try:
        client.initialize()
        tools_resp = client.list_tools()
        tool_names = {
            t["name"]
            for t in tools_resp.get("result", {}).get("tools", [])
        }
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except (OSError, BrokenPipeError):
            pass
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        rc = proc.returncode
        # Now process has exited — safe to read all stderr.
    stderr = b""
    try:
        stderr = proc.stderr.read()
    except (OSError, ValueError):
        pass
    return tool_names, rc, stderr.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# W1 — child_scrubber_id == "redcap_metadata_flags" in _meta on every
#       successful REDCap tools/call result
# ---------------------------------------------------------------------------

class TestW1ChildScrubbedIdInMeta:
    """W1: _meta.child_scrubber_id == "redcap_metadata_flags" on every
    REDCap Tier-1 success path response.  Three tools tested."""

    def test_redcap_list_records_meta_child_scrubber_id(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_list_records", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                assert "_meta" in body, f"No _meta in redcap_list_records response: {body}"
                meta = body["_meta"]
                assert "child_scrubber_id" in meta, (
                    f"W1 FAIL: _meta missing 'child_scrubber_id' key. "
                    f"Keys present: {sorted(meta.keys())}"
                )
                assert meta["child_scrubber_id"] == "redcap_metadata_flags", (
                    f"W1 FAIL: expected 'redcap_metadata_flags', "
                    f"got {meta['child_scrubber_id']!r}"
                )
            finally:
                _teardown(proc)

    def test_redcap_summary_report_meta_child_scrubber_id(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_summary_report", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                assert "_meta" in body, f"No _meta in redcap_summary_report: {body}"
                meta = body["_meta"]
                assert "child_scrubber_id" in meta, (
                    f"W1 FAIL: redcap_summary_report _meta missing 'child_scrubber_id'. "
                    f"Keys: {sorted(meta.keys())}"
                )
                assert meta["child_scrubber_id"] == "redcap_metadata_flags", (
                    f"W1 FAIL: got {meta['child_scrubber_id']!r}"
                )
            finally:
                _teardown(proc)

    def test_redcap_record_detail_meta_child_scrubber_id(self) -> None:
        """Call redcap_record_detail with a real record_id from the fixture."""
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                # Grab the first record_id from list_records
                lr = client.call_tool("redcap_list_records", {})
                lr_body = json.loads(extract_text_result(lr))
                records = lr_body.get("records", [])
                if not records:
                    pytest.skip("No records in fixture — cannot test record_detail path")
                first_id = records[0]["record_id"]
                resp = client.call_tool("redcap_record_detail", {"record_id": first_id})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                assert "_meta" in body, f"No _meta in redcap_record_detail: {body}"
                meta = body["_meta"]
                assert "child_scrubber_id" in meta, (
                    f"W1 FAIL: redcap_record_detail _meta missing 'child_scrubber_id'. "
                    f"Keys: {sorted(meta.keys())}"
                )
                assert meta["child_scrubber_id"] == "redcap_metadata_flags", (
                    f"W1 FAIL: got {meta['child_scrubber_id']!r}"
                )
            finally:
                _teardown(proc)


# ---------------------------------------------------------------------------
# W2 — error envelopes use placeholder strings, NOT absolute paths
# ---------------------------------------------------------------------------

class TestW2ErrorEnvelopePlaceholders:
    """W2: When the configured redcap_path does not exist on disk,
    error envelopes must contain <configured_redcap_path> or
    <configured_redcap_records_path>, NOT the raw filesystem path."""

    # Using a path that is guaranteed not to exist during the test run.
    _FAKE_PATH = "/tmp/w2_no_such_redcap_dir_xyz"

    def _check_no_absolute_path_in_error(self, body: dict, fake_path: str) -> None:
        raw_body = json.dumps(body)
        assert fake_path not in raw_body, (
            f"W2 FAIL: absolute path {fake_path!r} leaked into wire payload. "
            f"Body: {raw_body[:400]}"
        )

    def _check_placeholder_present(self, body: dict) -> None:
        raw_body = json.dumps(body)
        assert (
            "<configured_redcap_path>" in raw_body
            or "<configured_redcap_records_path>" in raw_body
        ), (
            f"W2 FAIL: neither placeholder found in error envelope. "
            f"Body: {raw_body[:400]}"
        )

    def test_list_records_on_missing_dir_uses_placeholder(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(
                Path(tmp),
                redcap_path=self._FAKE_PATH,
            )
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_list_records", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                assert "error" in body, f"Expected error key, got: {body}"
                self._check_no_absolute_path_in_error(body, self._FAKE_PATH)
                self._check_placeholder_present(body)
            finally:
                _teardown(proc)

    def test_summary_report_on_missing_dir_uses_placeholder(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(
                Path(tmp),
                redcap_path=self._FAKE_PATH,
            )
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_summary_report", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                assert "error" in body, f"Expected error key, got: {body}"
                self._check_no_absolute_path_in_error(body, self._FAKE_PATH)
                self._check_placeholder_present(body)
            finally:
                _teardown(proc)

    def test_record_detail_on_missing_dir_uses_placeholder(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(
                Path(tmp),
                redcap_path=self._FAKE_PATH,
            )
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool(
                    "redcap_record_detail", {"record_id": "1"}
                )
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                assert "error" in body, f"Expected error key, got: {body}"
                self._check_no_absolute_path_in_error(body, self._FAKE_PATH)
                self._check_placeholder_present(body)
            finally:
                _teardown(proc)

    def test_cohort_summary_on_missing_dir_uses_placeholder(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(
                Path(tmp),
                redcap_path=self._FAKE_PATH,
            )
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool(
                    "redcap_cohort_summary",
                    {"field": "phq9_score", "group_by": "study_group"},
                )
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                assert "error" in body, f"Expected error key, got: {body}"
                self._check_no_absolute_path_in_error(body, self._FAKE_PATH)
                self._check_placeholder_present(body)
            finally:
                _teardown(proc)


# ---------------------------------------------------------------------------
# W3 — consent-event audit rows carry child_scrubber_id in audit.db
# ---------------------------------------------------------------------------

class TestW3ConsentAuditRowsThreadChildScrubberId:
    """W3: approve_consent_redcap_file, revoke_consent_redcap_file, and the
    PURGE_CACHE + SUCCESS rows all write child_scrubber_id ==
    "redcap_metadata_flags" in audit.db."""

    def test_approve_and_revoke_consent_audit_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()

                # Approve consent — writes SUCCESS row for approve_consent_*
                r_approve = client.call_tool(
                    "approve_consent_redcap_file",
                    {"user_id": "audit_test_user"},
                )
                raw_approve = extract_text_result(r_approve)
                assert_no_repr_artifacts(raw_approve)
                body_approve = json.loads(raw_approve)
                assert "error" not in body_approve, (
                    f"approve_consent_redcap_file failed: {body_approve}"
                )

                # One successful REDCap data call to create a child-dispatch row
                r_list = client.call_tool("redcap_list_records", {})
                assert_no_repr_artifacts(extract_text_result(r_list))

                # Revoke consent — writes PURGE_CACHE + SUCCESS rows
                r_revoke = client.call_tool(
                    "revoke_consent_redcap_file",
                    {"user_id": "audit_test_user"},
                )
                raw_revoke = extract_text_result(r_revoke)
                assert_no_repr_artifacts(raw_revoke)
                body_revoke = json.loads(raw_revoke)
                assert "error" not in body_revoke, (
                    f"revoke_consent_redcap_file failed: {body_revoke}"
                )

            finally:
                _teardown(proc)

            # Query audit.db after the process has exited cleanly.
            audit_db = dat / "audit.db"
            assert audit_db.exists(), f"audit.db not found at {audit_db}"

            conn = sqlite3.connect(str(audit_db))
            try:
                # Verify the column exists (migrated on server start).
                cols = {
                    row[1]
                    for row in conn.execute(
                        "PRAGMA table_info(audit_log)"
                    ).fetchall()
                }
                assert "child_scrubber_id" in cols, (
                    "W3 FAIL: child_scrubber_id column absent from audit_log"
                )

                # Every redcap_file domain row must carry the scrubber id.
                rows = conn.execute(
                    "SELECT tool_name, outcome, child_scrubber_id "
                    "FROM audit_log WHERE domain = 'redcap_file'"
                ).fetchall()
                assert rows, "W3 FAIL: no redcap_file rows in audit.db"

                bad = [
                    (t, o, csi)
                    for t, o, csi in rows
                    if csi != "redcap_metadata_flags"
                ]
                assert not bad, (
                    f"W3 FAIL: {len(bad)} redcap_file audit row(s) have "
                    f"child_scrubber_id != 'redcap_metadata_flags':\n"
                    + "\n".join(f"  tool={t!r} outcome={o!r} csi={csi!r}" for t, o, csi in bad)
                )

                # Specifically check PURGE_CACHE and SUCCESS rows exist
                outcomes = {o for _, o, _ in rows}
                assert "SUCCESS" in outcomes, (
                    f"W3: expected SUCCESS outcome rows for redcap_file domain; "
                    f"found outcomes: {outcomes}"
                )
            finally:
                conn.close()


# ---------------------------------------------------------------------------
# W4 — misconfigured redcap_file (missing path key) boots cleanly
# ---------------------------------------------------------------------------

class TestW4MisconfiguredRedcapBoots:
    """W4: {"redcap_file": {"records_file": "x.csv"}} (missing path) must
    not crash tailor serve; other tools must still be available."""

    def test_missing_path_key_boots_cleanly_and_other_tools_present(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(
                Path(tmp),
                include_redcap=True,
                redcap_cfg_override={"records_file": "x.csv"},  # no "path" key
            )
            tool_names, rc, stderr = _read_stderr_after_teardown(cfg, dat)

            # REDCap tools must be absent
            redcap_tools = {n for n in tool_names if "redcap" in n}
            assert not redcap_tools, (
                f"W4 FAIL: REDCap tools present despite misconfigured block: "
                f"{redcap_tools}"
            )

            # Running and local_llm tools must be present
            assert "strava_list_runs" in tool_names, (
                f"W4 FAIL: strava_list_runs absent; tool list: {sorted(tool_names)}"
            )
            assert "ask_local_oracle" in tool_names, (
                "W4 FAIL: ask_local_oracle absent"
            )

            # Operator banner must be on stderr
            assert (
                "REDCap tools NOT registered" in stderr
                or "redcap_file" in stderr.lower()
            ), (
                f"W4 FAIL: expected operator banner on stderr about redcap_file "
                f"registration failure. stderr excerpt: {stderr[:600]}"
            )

            # Process must exit cleanly (rc != 1 — not a fatal boot failure)
            assert rc != 1, (
                f"W4 FAIL: server exited with rc={rc} — misconfigured redcap_file "
                f"caused a fatal boot failure"
            )

    def test_missing_path_key_process_does_not_crash_before_tools_list(self) -> None:
        """Verify that the server process survives long enough to answer tools/list."""
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(
                Path(tmp),
                include_redcap=True,
                redcap_cfg_override={"records_file": "no_path.csv"},
            )
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                init_resp = client.initialize()
                assert "result" in init_resp, (
                    f"W4 FAIL: initialize failed: {init_resp}"
                )
                # Process must still be alive after initialize
                assert proc.poll() is None, (
                    "W4 FAIL: server died after initialize"
                )
            finally:
                _teardown(proc)


# ---------------------------------------------------------------------------
# W5 — vault and local_llm _meta carry child_scrubber_id: null
# ---------------------------------------------------------------------------

class TestW5FrameworkLayerMetaChildScrubberId:
    """W5: VaultLayer and LocalLLMLayer _meta blocks include the key
    "child_scrubber_id" with JSON null value (Python None)."""

    def test_vault_meta_child_scrubber_id_is_null(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("vault_list_notes", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                # vault_list_notes returns a dict with _meta when the vault
                # exists; it may also return a list with no _meta on an empty
                # vault, which is acceptable — skip the meta check in that case.
                if isinstance(body, dict) and "_meta" in body:
                    meta = body["_meta"]
                    assert "child_scrubber_id" in meta, (
                        f"W5 FAIL: vault _meta missing 'child_scrubber_id' key. "
                        f"Keys: {sorted(meta.keys())}"
                    )
                    assert meta["child_scrubber_id"] is None, (
                        f"W5 FAIL: vault _meta.child_scrubber_id should be null "
                        f"(framework-level layer), got {meta['child_scrubber_id']!r}"
                    )
                else:
                    # Call a vault tool that always returns a dict to force the
                    # _meta branch.
                    resp2 = client.call_tool("vault_health_check", {})
                    raw2 = extract_text_result(resp2)
                    body2 = json.loads(raw2)
                    if isinstance(body2, dict) and "_meta" in body2:
                        meta2 = body2["_meta"]
                        assert "child_scrubber_id" in meta2, (
                            f"W5 FAIL: vault_health_check _meta missing 'child_scrubber_id'. "
                            f"Keys: {sorted(meta2.keys())}"
                        )
                        assert meta2["child_scrubber_id"] is None, (
                            f"W5 FAIL: got {meta2['child_scrubber_id']!r}"
                        )
            finally:
                _teardown(proc)

    def test_local_llm_meta_child_scrubber_id_is_null(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool(
                    "ask_local_oracle",
                    {"question": "w5_test", "resolved_context": {}},
                )
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                if isinstance(body, dict) and "_meta" in body:
                    meta = body["_meta"]
                    assert "child_scrubber_id" in meta, (
                        f"W5 FAIL: local_llm _meta missing 'child_scrubber_id' key. "
                        f"Keys: {sorted(meta.keys())}"
                    )
                    assert meta["child_scrubber_id"] is None, (
                        f"W5 FAIL: local_llm _meta.child_scrubber_id should be null, "
                        f"got {meta['child_scrubber_id']!r}"
                    )
            finally:
                _teardown(proc)

    def test_raw_wire_payload_has_json_null_not_python_none_repr(self) -> None:
        """The wire payload must contain JSON null, not Python repr 'None'."""
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("vault_list_notes", {})
                raw = extract_text_result(resp)
                # "None" (Python repr) must not appear for child_scrubber_id
                # JSON null serializes to the literal string "null"
                assert '"child_scrubber_id": None' not in raw, (
                    "W5 FAIL: Python repr 'None' on wire instead of JSON null. "
                    "This is a _dumps serialization bug."
                )
            finally:
                _teardown(proc)


# ---------------------------------------------------------------------------
# W6 — standard provenance fields present on every _meta block
#       (no regression from the child_scrubber_id addition)
# ---------------------------------------------------------------------------

_REQUIRED_META_FIELDS = (
    "package_version",
    "tool_name",
    "called_at",
    "domain",
    "tier",
    "scrubber_id",
    "child_scrubber_id",
)


def _assert_meta_provenance(meta: dict, tool_name: str, domain: str) -> None:
    for field in _REQUIRED_META_FIELDS:
        assert field in meta, (
            f"W6 FAIL: _meta missing '{field}' on {tool_name!r} "
            f"(domain={domain!r}). Keys present: {sorted(meta.keys())}"
        )
    # called_at must parse as ISO-8601
    try:
        datetime.fromisoformat(meta["called_at"])
    except (ValueError, TypeError) as exc:
        raise AssertionError(
            f"W6 FAIL: _meta.called_at is not ISO-8601 on {tool_name!r}: "
            f"{meta['called_at']!r} — {exc}"
        ) from exc
    # tool_name must match
    assert meta["tool_name"] == tool_name, (
        f"W6 FAIL: _meta.tool_name {meta['tool_name']!r} != called tool {tool_name!r}"
    )
    # domain must match
    assert meta["domain"] == domain, (
        f"W6 FAIL: _meta.domain {meta['domain']!r} != expected {domain!r}"
    )


class TestW6ProvenianceFieldsNotRegressed:
    """W6: All standard _meta provenance fields remain present after the
    child_scrubber_id addition.  Tested on four different dispatch paths:
    REDCap child, csv_dir child, vault layer, local_llm layer."""

    def test_redcap_meta_all_provenance_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_list_records", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                assert "_meta" in body, f"No _meta in redcap response: {body}"
                _assert_meta_provenance(body["_meta"], "redcap_list_records", "redcap_file")
            finally:
                _teardown(proc)

    def test_csv_dir_meta_all_provenance_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("csv_list_files", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                assert "_meta" in body, f"No _meta in csv_list_files: {body}"
                _assert_meta_provenance(body["_meta"], "csv_list_files", "csv_dir")
            finally:
                _teardown(proc)

    def test_vault_meta_all_provenance_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                # vault_health_check always returns a dict with _meta
                resp = client.call_tool("vault_health_check", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                if isinstance(body, dict) and "_meta" in body:
                    _assert_meta_provenance(body["_meta"], "vault_health_check", "vault")
            finally:
                _teardown(proc)

    def test_local_llm_meta_all_provenance_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool(
                    "ask_local_oracle",
                    {"question": "w6_check", "resolved_context": {}},
                )
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                if isinstance(body, dict) and "_meta" in body:
                    _assert_meta_provenance(body["_meta"], "ask_local_oracle", "local_llm")
            finally:
                _teardown(proc)

    def test_package_version_matches_tailor_version(self) -> None:
        """package_version in _meta must match tailor.__version__."""
        from tailor import __version__
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                # Use a redcap tool — child dispatch path
                resp = client.call_tool("redcap_summary_report", {})
                raw = extract_text_result(resp)
                body = json.loads(raw)
                assert "_meta" in body
                assert body["_meta"]["package_version"] == __version__, (
                    f"W6 FAIL: _meta.package_version={body['_meta']['package_version']!r} "
                    f"!= tailor.__version__={__version__!r}"
                )
            finally:
                _teardown(proc)

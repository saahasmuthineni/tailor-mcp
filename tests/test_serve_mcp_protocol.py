"""
End-to-end MCP-protocol subprocess audit.

These tests drive ``python -m biosensor_mcp serve`` as a real
subprocess speaking JSON-RPC over stdio, with a fully-seeded
config (vault + csv_dir + running) so all 44+ tools register.

The bug class they exist to catch: **protocol-adapter regressions
that don't show up at the framework's internal seams**. Specifically:

  H3 — wire-coercion bugs (``default=str`` stringifying datetime /
       Path / Decimal into Python ``repr()`` artifacts).
  H4 — markdown round-trip lossiness on vault content (backticks,
       YAML, unicode).
  M1 — post-execute hook failures swallowed silently into stderr
       where Claude Desktop never sees them.
  H2 (contract) — every ``vaultable_tool`` advertised by a child
       must have a paired renderer in ``VaultWriter._renderers``.

ADR 0022 surfaces (added this audit run — v6.5.0+):
  L1 — tools/list includes ask_local_oracle with correct inputSchema.
  L2 — tools/call ask_local_oracle (NullBackend) returns structured
       OracleResponse; _meta.domain == "local_llm"; oracle provenance
       nested under _meta.oracle.
  L3 — wire serialization: OracleResponse.to_dict() is clean JSON
       with no Python repr artifacts; confidence is float not string.
  L4 — audit.db gains a row with all 5 oracle_* columns populated;
       migration is idempotent on a pre-existing db file.
  L5 — existing tools (vault, csv_dir, running) unaffected by
       local_llm layer registration.

Each test corresponds to a Phase-1 surface in the v6.5.0/v6.5.0+
mcp-protocol-auditor inventory.
"""

from __future__ import annotations

import importlib
import json
import sys

import pytest

from tests._mcp_client import (
    assert_no_repr_artifacts,
    extract_text_result,
    spawn_server,
)

# ──────────────────────────────────────────────────────────────────
# tools/call — Tier 1 happy path on the CSV directory child
# ──────────────────────────────────────────────────────────────────

def test_csv_list_files_round_trip() -> None:
    """``csv_list_files`` returns clean JSON via tools/call."""
    with spawn_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool("csv_list_files", {})
        assert "error" not in resp, resp

        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)

        body = json.loads(text)
        assert body["count"] == 2  # P001.csv + P002.csv (metadata.json excluded by *.csv glob)
        names = {f["filename"] for f in body["files"]}
        assert names == {"P001.csv", "P002.csv"}

        # _meta provenance contract
        assert "_meta" in body
        meta = body["_meta"]
        assert meta["tool_name"] == "csv_list_files"
        assert meta["domain"] == "csv_dir"
        from biosensor_mcp import __version__
        assert meta["package_version"] == __version__
        # called_at must be ISO-8601 parseable, NOT a Python repr.
        from datetime import datetime
        datetime.fromisoformat(meta["called_at"].replace("Z", "+00:00"))


def test_csv_summary_report_no_repr_in_meta() -> None:
    """csv_summary_report carries time_range datetimes — wire payload
    must not contain ``datetime.datetime(`` repr artifacts.

    This is the H3 regression: the old ``_dumps(default=str)`` would
    have stringified a stray datetime via ``repr()``. The summary
    report itself converts to .isoformat() at the child boundary;
    this test pins that contract end-to-end.
    """
    with spawn_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool(
            "csv_summary_report", {"file_id": "P001.csv"},
        )
        assert "error" not in resp, resp

        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)

        body = json.loads(text)
        assert "_meta" in body
        # time_range present and ISO-8601 (not a Python repr)
        assert "time_range" in body
        assert body["time_range"]["start"].startswith("2026-04-01")


def test_csv_force_decline_round_trip() -> None:
    """csv_force_decline (new in v6.5.0) round-trips cleanly."""
    with spawn_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool(
            "csv_force_decline",
            {"file_id": "P001.csv", "column": "heart_rate"},
        )
        assert "error" not in resp, resp

        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)

        body = json.loads(text)
        assert "_meta" in body
        assert body.get("filename") == "P001.csv"
        assert body.get("column") == "heart_rate"


def test_csv_cohort_summary_round_trip() -> None:
    """csv_cohort_summary (new in v6.5.0) round-trips cleanly with
    metadata.json sidecar."""
    with spawn_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool(
            "csv_cohort_summary",
            {"column": "heart_rate", "group_by": "sex", "metric": "mean"},
        )
        assert "error" not in resp, resp

        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)

        body = json.loads(text)
        assert "groups" in body
        # Both groups present (one CSV per sex in the seed).
        assert set(body["groups"].keys()) == {"F", "M"}


# ──────────────────────────────────────────────────────────────────
# tools/call — vault layer happy path + markdown round-trip (H4)
# ──────────────────────────────────────────────────────────────────

def test_vault_capture_and_read_round_trip_preserves_markdown() -> None:
    """Capture a moment with awkward markdown, read it back, body must
    survive byte-equal modulo cross-platform CRLF normalization.

    Awkward content: triple backticks, a fence containing YAML, and
    a unicode block (Greek letters used in scientific notation). H4
    is the bug class where the JSON envelope, the file write, or the
    file read mangles any of those.
    """
    body = (
        "Body with backticks: ```python\n"
        "print('hello \"world\"')\n"
        "```\n\n"
        "Embedded YAML:\n\n"
        "```yaml\n"
        "key: value\n"
        "list: [a, b]\n"
        "```\n\n"
        "Unicode: σ μ τ ± Δ – emoji: ⚡\n"
    )
    title = "Awkward markdown round-trip"

    with spawn_server() as (client, _paths):
        client.initialize()

        capture = client.call_tool("vault_capture_moment", {
            "title": title,
            "body": body,
        })
        assert "error" not in capture, capture
        cap_text = extract_text_result(capture)
        assert_no_repr_artifacts(cap_text)
        cap_body = json.loads(cap_text)
        assert cap_body.get("captured") is True
        filename = cap_body["filename"]

        read = client.call_tool("vault_read_note", {"filename": filename})
        assert "error" not in read, read
        read_text = extract_text_result(read)
        assert_no_repr_artifacts(read_text)
        read_body = json.loads(read_text)

        content = read_body["content"]
        # Cross-platform sanity: normalize CRLF → LF before comparing.
        normalized = content.replace("\r\n", "\n")
        # Body must appear verbatim in the rendered note.
        assert body in normalized, (
            "vault_capture_moment → vault_read_note round-trip lost "
            "characters from the body. Original:\n"
            f"{body!r}\n\nRound-tripped content:\n{content!r}"
        )
        # Title also survives intact in the H1 header line.
        assert f"# {title}" in normalized


# ──────────────────────────────────────────────────────────────────
# Error envelopes
# ──────────────────────────────────────────────────────────────────

def test_unknown_tool_returns_clean_error_envelope() -> None:
    """Unknown tool name produces a clean error payload, not a crash."""
    with spawn_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool("does_not_exist", {})
        # tools/call returns a result with text content carrying
        # ``{"error": ...}``; framework error envelope.
        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)
        body = json.loads(text)
        assert "error" in body
        assert "Unknown tool" in body["error"]


def test_invalid_params_returns_clean_error_envelope() -> None:
    """Param-validation failure returns a clean error message — either
    the mcp SDK's input-schema pre-check or the framework's own
    ``ParamValidator`` (the SDK fires first when a parameter is
    declared ``required`` in the JSON schema).

    This test pins both shapes and the load-bearing invariant: a
    missing required param produces a deterministic error string that
    names the offending field, with no Python repr artifacts and no
    crash.
    """
    with spawn_server() as (client, _paths):
        client.initialize()

        # csv_summary_report requires file_id; omit it.
        resp = client.call_tool("csv_summary_report", {})
        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)
        # The mcp SDK's own JSON-schema validator may produce a plain-
        # text "Input validation error: ..." message. Treat any
        # response that names ``file_id`` as a clean envelope.
        try:
            body = json.loads(text)
            assert "error" in body
            assert "file_id" in body["error"]
        except json.JSONDecodeError:
            assert "file_id" in text, (
                f"Expected error message naming file_id; got:\n{text}"
            )

        # Pass an out-of-pattern file_id to force the framework's own
        # ParamValidator to fire — its envelope is JSON-shaped.
        resp2 = client.call_tool(
            "csv_summary_report", {"file_id": "../escape.csv"},
        )
        text2 = extract_text_result(resp2)
        assert_no_repr_artifacts(text2)
        body2 = json.loads(text2)
        assert "error" in body2


# ──────────────────────────────────────────────────────────────────
# Consent-gate response shape (Tier 2)
# ──────────────────────────────────────────────────────────────────

def test_consent_gate_returns_structured_llm_instruction() -> None:
    """Tier-2 call without consent emits the structured gate payload.

    Pins ADR 0004: ``llm_instruction`` carries ``must_do``,
    ``must_not_do``, ``on_ambiguous_reply`` as individually-checkable
    fields, all string-typed. A free-text paragraph would not satisfy
    the audit-of-compliance contract.
    """
    with spawn_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool("csv_downsampled", {
            "file_id": "P001.csv",
            "interval": 2,
        })
        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)
        body = json.loads(text)

        assert body.get("gate") == "consent_required"
        assert body.get("domain") == "csv_dir"
        assert "llm_instruction" in body
        instr = body["llm_instruction"]
        for key in ("must_do", "must_not_do", "on_ambiguous_reply"):
            assert key in instr, f"llm_instruction missing {key!r}: {instr}"
        assert isinstance(instr["must_do"], list)
        assert all(isinstance(s, str) for s in instr["must_do"])
        assert isinstance(instr["must_not_do"], list)
        assert all(isinstance(s, str) for s in instr["must_not_do"])
        assert isinstance(instr["on_ambiguous_reply"], str)


# ──────────────────────────────────────────────────────────────────
# Wire-coercion (H3): typed default raises on unknown types
# ──────────────────────────────────────────────────────────────────

def test_wire_default_handles_known_types_no_repr() -> None:
    """Unit-level pin on the typed JSON encoder.

    The H3 fix replaced ``default=str`` with ``_wire_default``, which
    coerces datetime / date / PurePath / Decimal / set / bytes
    explicitly and raises TypeError on anything else. This test
    asserts both branches: the safe coercion path produces clean
    JSON (no Python repr), and the unsafe path raises rather than
    silently emitting ``<class 'X'>``.
    """
    from datetime import date, datetime, timezone
    from decimal import Decimal
    from pathlib import PurePosixPath

    from biosensor_mcp.framework.audit import _dumps

    payload = {
        "ts_aware": datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc),
        "ts_naive": datetime(2026, 4, 30, 12, 0, 0),  # → UTC
        "d": date(2026, 4, 30),
        "p": PurePosixPath("/tmp/example.csv"),
        "n": Decimal("3.14"),
        "s": {"a", "b", "c"},
        "b": b"hello",
    }
    encoded = _dumps(payload)
    # No Python repr artifacts anywhere on the wire.
    for artifact in (
        "datetime.datetime(", "datetime.date(",
        "PosixPath(", "WindowsPath(", "Decimal('",
    ):
        assert artifact not in encoded, (
            f"_dumps leaked {artifact!r} into wire payload: {encoded}"
        )
    decoded = json.loads(encoded)
    # orjson handles datetime/date natively (ISO-8601, never repr).
    # Stdlib fallback uses _wire_default which forces UTC on naive.
    # Both produce ISO strings starting with the date — which is what
    # matters for "no Python repr leak"; the exact tz suffix on naive
    # datetimes is encoder-dependent (orjson emits no suffix; stdlib
    # fallback stamps +00:00). Children that need wire-stable tzinfo
    # must construct timezone-aware datetimes at the boundary.
    assert decoded["ts_aware"].startswith("2026-04-30T12:00:00")
    assert decoded["ts_naive"].startswith("2026-04-30T12:00:00")
    assert decoded["d"] == "2026-04-30"
    assert decoded["p"] == "/tmp/example.csv"
    assert decoded["n"] == 3.14
    assert decoded["s"] == ["a", "b", "c"]  # sorted
    assert decoded["b"] == "hello"


def test_wire_default_raises_on_unknown_type() -> None:
    """Unknown types must raise loudly, not silently coerce via repr."""
    from biosensor_mcp.framework.audit import _dumps

    class _Mystery:
        pass

    with pytest.raises((TypeError, Exception)) as excinfo:
        _dumps({"x": _Mystery()})
    # orjson and stdlib json both raise, but with different exception
    # types. The message should at minimum name something coercion-
    # related so the framework dev knows where to look.
    msg = str(excinfo.value).lower()
    assert any(
        term in msg for term in ("not json-serializable", "type", "_mystery")
    ), f"Unhelpful error: {excinfo.value!r}"


# ──────────────────────────────────────────────────────────────────
# Vaultable-tool ↔ renderer contract (H2)
# ──────────────────────────────────────────────────────────────────

def test_every_vaultable_tool_has_renderer() -> None:
    """Contract: every tool a child marks vaultable must have a
    matching renderer in VaultWriter._renderers.

    This was the v6.5.0 H2 finding: ``CSVDirectoryChild.vaultable_tools``
    listed ``csv_summary_report`` but VaultWriter had no renderer for
    it, so every successful summary-report call when vault was enabled
    fired ``log.warning('No renderer for tool: csv_summary_report')``.
    The fix dropped it from vaultable_tools; this test pins the
    contract so the next addition can't slip past again.
    """
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from biosensor_mcp.children.csv_dir import CSVDirectoryChild
    from biosensor_mcp.children.running import RunningChild
    from biosensor_mcp.framework.vault.writer import VaultWriter

    with TemporaryDirectory() as tmp:
        config_dir = Path(tmp) / "config"
        config_dir.mkdir()
        data_dir = Path(tmp) / "data"
        vault_path = Path(tmp) / "vault"
        csv_dir_path = Path(tmp) / "csvs"
        for p in (data_dir, vault_path, csv_dir_path):
            p.mkdir()

        # Minimal csv_dir config so CSVDirectoryChild constructs.
        (config_dir / "user_config.json").write_text(
            json.dumps({"csv_dir": {"path": str(csv_dir_path)}}),
            encoding="utf-8",
        )
        (csv_dir_path / "P001.csv").write_text(
            "timestamp,value\n2026-04-01,1\n", encoding="utf-8",
        )

        running = RunningChild(config_dir=config_dir, data_dir=data_dir)
        csv_child = CSVDirectoryChild(
            config_dir=config_dir, data_dir=data_dir,
        )
        try:
            vaultable: set[str] = set()
            for child in (running, csv_child):
                vaultable.update(getattr(child, "vaultable_tools", []))

            writer = VaultWriter(
                vault_path=vault_path,
                data_dir=data_dir,
                vaultable_tools=vaultable,
            )
            try:
                renderers = set(writer._renderers.keys())
                missing = vaultable - renderers
                assert not missing, (
                    f"Children advertise vaultable tools with no "
                    f"renderer in VaultWriter._renderers: {sorted(missing)}. "
                    f"Either register a renderer in framework/vault/writer.py "
                    f"or drop the tool from the child's vaultable_tools "
                    f"property. (See v6.5.0 H2 finding.)"
                )
            finally:
                writer.close()
        finally:
            running.close()
            csv_child.close()


# ──────────────────────────────────────────────────────────────────
# Post-execute hook silence pin (M1)
# ──────────────────────────────────────────────────────────────────

def test_post_execute_hook_failure_surfaces_in_meta() -> None:
    """Hook failures must land in ``_meta.hook_warnings`` so the
    analyst can see them inside the LLM transcript — pre-v6.5.0 the
    framework swallowed them into a stderr log.warning that Claude
    Desktop never surfaces.
    """
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from biosensor_mcp.children.running import RunningChild
    from biosensor_mcp.framework.router import RouterMCP

    async def _run():
        with TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "config"
            data_dir = Path(tmp) / "data"
            config_dir.mkdir()
            data_dir.mkdir()

            router = RouterMCP("test-router", data_dir=data_dir)
            running = RunningChild(
                config_dir=config_dir, data_dir=data_dir,
            )
            router.register_child(running)

            def _broken_hook(domain: str, tool_name: str, result: dict):
                raise RuntimeError("hook broken on purpose")

            router.register_post_execute_hook(_broken_hook)

            try:
                # strava_list_runs is Tier 1, no consent gate; succeeds
                # against an empty cache returning an empty list.
                tc = await router._dispatch("strava_list_runs", {})
                assert len(tc) == 1
                payload = json.loads(tc[0].text)
                assert "_meta" in payload
                meta = payload["_meta"]
                assert "hook_warnings" in meta, (
                    "Hook failures must surface into _meta.hook_warnings "
                    f"per the v6.5.0 M1 fix. _meta was: {meta}"
                )
                warnings = meta["hook_warnings"]
                assert len(warnings) == 1
                assert warnings[0]["error_type"] == "RuntimeError"
                assert "broken on purpose" in warnings[0]["error"]
            finally:
                router.close()

    import asyncio

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────
# Audit module reload guard (orjson vs stdlib): both backends must
# present the same _wire_default contract
# ──────────────────────────────────────────────────────────────────

def test_audit_dumps_no_repr_with_stdlib_fallback(monkeypatch) -> None:
    """If orjson is unavailable at import time, the stdlib fallback
    must still apply ``_wire_default`` (not the old ``default=str``).
    """
    monkeypatch.setitem(sys.modules, "orjson", None)
    audit = importlib.reload(
        importlib.import_module("biosensor_mcp.framework.audit"),
    )
    try:
        from datetime import datetime, timezone

        encoded = audit._dumps({"ts": datetime(2026, 4, 30, tzinfo=timezone.utc)})
        assert "datetime.datetime(" not in encoded
        assert "2026-04-30" in encoded
    finally:
        # Restore the real module for downstream tests.
        sys.modules.pop("orjson", None)
        importlib.reload(
            importlib.import_module("biosensor_mcp.framework.audit"),
        )


# ──────────────────────────────────────────────────────────────────
# ADR 0022 — LocalLLMLayer / ask_local_oracle protocol surfaces
# (L1–L5, added this audit run)
# ──────────────────────────────────────────────────────────────────

def test_tools_list_includes_ask_local_oracle() -> None:
    """L1: tools/list returns ask_local_oracle with correct inputSchema.

    Covers:
    - Tool is present at all (registration didn't crash or collide).
    - inputSchema has the three documented properties: question (string,
      required), resolved_context (object, required), subject_id (string,
      optional).
    - No extra ``required`` entries that would break callers passing
      only {question, resolved_context}.
    """
    with spawn_server() as (client, _paths):
        client.initialize()
        list_resp = client.list_tools()
        tools = list_resp["result"]["tools"]
        tool_names = [t["name"] for t in tools]

        assert "ask_local_oracle" in tool_names, (
            f"ask_local_oracle not found in tools/list. "
            f"Total tools: {len(tools)}. First 10: {tool_names[:10]}"
        )

        oracle = next(t for t in tools if t["name"] == "ask_local_oracle")
        schema = oracle["inputSchema"]
        props = schema.get("properties", {})
        required = schema.get("required", [])

        # All three params present
        assert "question" in props, f"'question' missing from inputSchema: {props}"
        assert "resolved_context" in props, (
            f"'resolved_context' missing from inputSchema: {props}"
        )
        assert "subject_id" in props, (
            f"'subject_id' missing from inputSchema: {props}"
        )

        # Type fidelity
        assert props["question"]["type"] == "string"
        assert props["resolved_context"]["type"] == "object"
        assert props["subject_id"]["type"] == "string"

        # Required: question + resolved_context; subject_id is optional
        assert "question" in required
        assert "resolved_context" in required
        assert "subject_id" not in required, (
            "subject_id is optional — it must NOT be in required[]"
        )


def test_ask_local_oracle_tools_call_happy_path() -> None:
    """L2: tools/call ask_local_oracle (NullBackend) returns structured
    OracleResponse with correct _meta provenance.

    Pins:
    - _meta.domain == "local_llm"
    - _meta.tool_name == "ask_local_oracle"
    - _meta.oracle nested block present with backend/model_id/tier/prompt_hash
    - oracle.called_at is ISO-8601 parseable
    - numerical_claims populated from resolved_context
    - confidence is float (not string — H3 class)
    - No repr artifacts anywhere on the wire
    """
    from datetime import datetime

    from biosensor_mcp import __version__

    with spawn_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool("ask_local_oracle", {
            "question": "How did P003 perform on heart_rate?",
            "resolved_context": {
                "csv_force_decline": {
                    "peak": 100.0,
                    "decline_pct_total": 8.5,
                    "n_samples": 5,
                }
            },
            "subject_id": "P003",
        })

        assert "error" not in resp, f"tools/call returned error: {resp}"

        text = extract_text_result(resp)

        # L3: no repr artifacts anywhere on wire payload
        assert_no_repr_artifacts(text)

        body = json.loads(text)

        # OracleResponse shape
        assert "numerical_claims" in body, f"Missing numerical_claims: {body.keys()}"
        assert "narrative" in body
        assert "ambiguity_axes" in body
        assert "confidence" in body

        # confidence must be float, not string (H3 variant — OracleResponse dataclass)
        assert isinstance(body["confidence"], float), (
            f"confidence must be float on wire, got {type(body['confidence']).__name__}: "
            f"{body['confidence']!r}"
        )

        # _meta outer provenance
        assert "_meta" in body
        meta = body["_meta"]
        assert meta["domain"] == "local_llm", f"domain mismatch: {meta.get('domain')}"
        assert meta["tool_name"] == "ask_local_oracle"
        assert meta["tier"] == 1
        assert meta["package_version"] == __version__

        # called_at must be ISO-8601 parseable
        datetime.fromisoformat(meta["called_at"].replace("Z", "+00:00"))

        # oracle nested provenance (L2 core assertion — NullBackend)
        assert "oracle" in meta, (
            f"_meta.oracle missing — OracleResponse._meta was not preserved "
            f"under _meta.oracle. _meta keys: {list(meta.keys())}"
        )
        om = meta["oracle"]
        assert om["backend"] == "null"
        assert om["model_id"] == "null"
        assert om["tier"] == "null"
        assert "prompt_hash" in om
        # oracle.called_at is also ISO-8601
        datetime.fromisoformat(om["called_at"].replace("Z", "+00:00"))

        # numerical_claims come from resolved_context (fidelity guarantee)
        claims = body["numerical_claims"]
        assert len(claims) >= 1, "NullBackend must surface claims from resolved_context"
        claim_metrics = {c["metric"] for c in claims}
        assert "peak" in claim_metrics or "decline_pct_total" in claim_metrics, (
            f"Expected peak/decline_pct_total in claims; got: {claim_metrics}"
        )


def test_ask_local_oracle_wire_serialization_no_repr() -> None:
    """L3: OracleResponse.to_dict() → _dumps produces clean JSON.

    Verifies the dataclass serialization seam end-to-end: OracleResponse
    contains floats (confidence, NumericalClaim.value), strings, lists,
    and a nested dict (_meta). Any accidental default=str fallback on
    an unhandled type would surface as a Python repr artifact here.
    This is the H3 variant specific to the oracle pipeline.
    """
    with spawn_server() as (client, _paths):
        client.initialize()

        # Use a resolved_context with numeric types that could trip up
        # a naive JSON encoder: int, float, nested dict.
        resp = client.call_tool("ask_local_oracle", {
            "question": "Wire serialization stress test",
            "resolved_context": {
                "csv_cohort_summary": {
                    "P001": {"mean_hr": 76.0, "n": 5},
                    "P002": {"mean_hr": 86.0, "n": 5},
                }
            },
        })

        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)

        # Full JSON parse must succeed — no half-encoded payload.
        body = json.loads(text)

        # NullBackend flattens nested per-subject context;
        # claim values must be raw numbers, not strings.
        for claim in body.get("numerical_claims", []):
            val = claim["value"]
            assert isinstance(val, (int, float)), (
                f"numerical_claims[].value must be numeric on wire, "
                f"got {type(val).__name__}: {val!r}"
            )


def test_ask_local_oracle_invalid_params_returns_error_envelope() -> None:
    """L2 error path: missing required 'question' → clean error envelope.

    Pins that the local_llm dispatch pipeline's PARAM_INVALID path
    returns a JSON-encoded error, not a crash. No repr artifacts.
    """
    with spawn_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool("ask_local_oracle", {
            # resolved_context present but question absent
            "resolved_context": {"csv_force_decline": {"peak": 100.0}},
        })

        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)
        # The error may come from mcp SDK schema pre-check (plain-text "question")
        # or from framework ParamValidator (JSON {"error": "..."}).
        try:
            body = json.loads(text)
            assert "error" in body, f"Expected 'error' key in JSON envelope: {body}"
            assert "question" in body["error"].lower() or "required" in body["error"].lower(), (
                f"Error message should mention 'question' or 'required': {body['error']}"
            )
        except json.JSONDecodeError:
            # mcp SDK emits plain text for schema violations in some versions
            assert "question" in text.lower() or "required" in text.lower(), (
                f"Expected error naming 'question' or 'required'; got:\n{text}"
            )


def test_ask_local_oracle_audit_db_oracle_columns() -> None:
    """L4: After a successful ask_local_oracle call, audit.db has a row
    with all 6 oracle_* columns populated (NullBackend values).

    The ADR brief cited 5 columns; audit.py actually commits 6
    (oracle_latency_ms was added alongside the other 5 in the same
    migration block). This test pins all 6 so the contract cannot
    silently regress.

    Also verifies migration idempotency: constructing a second AuditLog
    on the same db file must not crash (ALTER TABLE IF NOT EXISTS pattern).
    """
    import sqlite3
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from tests._mcp_client import seed_full_config, spawn_server

    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        paths = seed_full_config(Path(tmp))

        import os
        env = {
            **os.environ,
            "BIOSENSOR_CONFIG_DIR": str(paths["config_dir"]),
            "BIOSENSOR_DATA_DIR": str(paths["data_dir"]),
        }

        import subprocess

        proc = subprocess.Popen(
            [sys.executable, "-m", "biosensor_mcp", "serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        from tests._mcp_client import MCPClient
        client = MCPClient(proc)
        try:
            client.initialize()

            client.call_tool("ask_local_oracle", {
                "question": "audit column test",
                "resolved_context": {
                    "csv_force_decline": {"peak": 50.0},
                },
                "subject_id": "P_audit_test",
            })

            import time
            time.sleep(0.5)  # let WAL flush
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

        audit_db = paths["data_dir"] / "audit.db"
        assert audit_db.exists(), f"audit.db not created at {audit_db}"

        with sqlite3.connect(str(audit_db)) as conn:
            # Schema check: all 6 oracle columns present
            all_cols = [
                row[1]
                for row in conn.execute("PRAGMA table_info(audit_log)").fetchall()
            ]
            expected_oracle_cols = {
                "oracle_model_id",
                "oracle_model_version_hash",
                "oracle_tier",
                "oracle_confidence",
                "oracle_prompt_hash",
                "oracle_latency_ms",
            }
            missing_cols = expected_oracle_cols - set(all_cols)
            assert not missing_cols, (
                f"Missing oracle columns in audit_log schema: {sorted(missing_cols)}"
            )

            # Row check: all 6 columns populated for NullBackend
            row = conn.execute(
                "SELECT oracle_model_id, oracle_model_version_hash, oracle_tier, "
                "oracle_confidence, oracle_prompt_hash, oracle_latency_ms "
                "FROM audit_log "
                "WHERE tool_name = 'ask_local_oracle' AND outcome = 'SUCCESS'"
            ).fetchone()
            assert row is not None, (
                "No SUCCESS row for ask_local_oracle in audit_log"
            )
            model_id, version_hash, o_tier, conf, phash, latency_ms = row
            assert model_id == "null", f"oracle_model_id expected 'null', got {model_id!r}"
            assert version_hash == "null", (
                f"oracle_model_version_hash expected 'null', got {version_hash!r}"
            )
            assert o_tier == "null", f"oracle_tier expected 'null', got {o_tier!r}"
            assert conf == 0.0, f"oracle_confidence expected 0.0, got {conf!r}"
            assert phash is not None and len(phash) == 16, (
                f"oracle_prompt_hash expected 16-char hex, got {phash!r}"
            )
            assert isinstance(latency_ms, int), (
                f"oracle_latency_ms expected int, got {type(latency_ms).__name__}: {latency_ms!r}"
            )

        # Idempotency: second AuditLog on same db must not error
        from biosensor_mcp.framework.audit import AuditLog
        audit2 = AuditLog(audit_db)
        try:
            cols2 = {
                row[1]
                for row in audit2._conn.execute("PRAGMA table_info(audit_log)").fetchall()
            }
            assert expected_oracle_cols.issubset(cols2), (
                f"Oracle cols missing after idempotent re-init: "
                f"{expected_oracle_cols - cols2}"
            )
        finally:
            audit2.close()


def test_existing_tools_unaffected_by_local_llm_layer() -> None:
    """L5: Existing vault, csv_dir, and running tools still respond
    correctly after the local_llm layer registers.

    Pins that register_local_llm_layer() doesn't corrupt _tool_map,
    introduce name collisions, or change dispatch behavior for other
    tools. Exercises one tool from each tier:
    - csv_list_files  (csv_dir, Tier 1)
    - vault_list_notes (vault, Tier 1)
    - csv_downsampled  (csv_dir, Tier 2, consent gate)
    """
    with spawn_server() as (client, _paths):
        client.initialize()

        # Tier 1 csv_dir tool
        r1 = client.call_tool("csv_list_files", {})
        t1 = extract_text_result(r1)
        assert_no_repr_artifacts(t1)
        b1 = json.loads(t1)
        assert "files" in b1, f"csv_list_files failed after local_llm layer: {b1}"
        assert b1["_meta"]["tool_name"] == "csv_list_files"

        # Vault Tier 1 tool
        r2 = client.call_tool("vault_list_notes", {})
        t2 = extract_text_result(r2)
        assert_no_repr_artifacts(t2)
        b2 = json.loads(t2)
        # vault_list_notes returns notes list (may be empty) — no error key
        assert "error" not in b2, f"vault_list_notes error after local_llm layer: {b2}"

        # Tier 2 consent gate still fires (csv_dir domain)
        r3 = client.call_tool("csv_downsampled", {"file_id": "P001.csv", "interval": 2})
        t3 = extract_text_result(r3)
        assert_no_repr_artifacts(t3)
        b3 = json.loads(t3)
        assert b3.get("gate") == "consent_required", (
            f"Consent gate should still fire on csv_downsampled: {b3}"
        )


# ──────────────────────────────────────────────────────────────────
# ADR 0023 — related_substrate + oracle_substrate_count surfaces
# S1–S4, added this audit run (v6.6.x)
# ──────────────────────────────────────────────────────────────────

def test_ask_local_oracle_related_substrate_top_level_field() -> None:
    """S1: tools/call ask_local_oracle response has related_substrate at
    top level (NOT nested under _meta).

    ADR 0023 adds OracleResponse.related_substrate; LocalLLMLayer
    populates it after backend.compose() returns. The gate-evasion
    class this test catches: the field is present in OracleResponse.to_dict()
    but a router serialization bug buries it somewhere else in the envelope.

    With NullBackend and no vault storage wired (seed_full_config seeds a
    vault_path but does NOT create vault notes), _scan_related_substrate
    returns [] (no subject themes). The test asserts:
    - related_substrate is present as a top-level key in the parsed body
    - its value is a list (may be empty)
    - if non-empty, each entry has kind/slug keys with no repr artifacts
    - No repr artifacts in the raw wire payload
    """
    with spawn_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool("ask_local_oracle", {
            "question": "substrate field present test",
            "resolved_context": {
                "csv_force_decline": {"peak": 100.0, "decline_pct_total": 5.0},
            },
            "subject_id": "P001",
        })

        assert "error" not in resp, f"tools/call error: {resp}"
        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)

        body = json.loads(text)
        assert "related_substrate" in body, (
            "related_substrate is missing from top-level tools/call response. "
            "Expected OracleResponse.to_dict() to include it at root level. "
            f"Top-level keys: {sorted(body.keys())}"
        )
        substrate = body["related_substrate"]
        assert isinstance(substrate, list), (
            f"related_substrate must be a list; got {type(substrate).__name__}: {substrate!r}"
        )
        # Validate entry shape when non-empty (no repr, has kind+slug)
        for entry in substrate:
            assert isinstance(entry, dict), (
                f"related_substrate entry must be dict; got {type(entry).__name__}: {entry!r}"
            )
            assert "kind" in entry, f"substrate entry missing 'kind': {entry}"
            assert "slug" in entry, f"substrate entry missing 'slug': {entry}"
            # No Python repr artifacts in any entry field value
            for v in entry.values():
                if isinstance(v, str):
                    assert_no_repr_artifacts(v)


def test_ask_local_oracle_related_substrate_no_repr_artifacts() -> None:
    """S2: Wire serialization of related_substrate entries is clean JSON.

    Substrate entries carry {kind, slug, title, subject_id, status,
    last_updated} — all str or None. The _dumps seam must not coerce
    None values into 'None' strings via default=str, and must not
    produce Python repr on any field.

    With NullBackend this exercises the to_dict() → _dumps → JSON-RPC
    round-trip for the related_substrate list, even when it is empty.
    A non-empty list would require vault notes; the test exercises the
    wire serialization path regardless of vault state.
    """
    with spawn_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool("ask_local_oracle", {
            "question": "serialization stress: substrate with nested dicts",
            "resolved_context": {
                "csv_cohort_summary": {
                    "groups": {
                        "F": {"mean": 76.0, "n": 5},
                        "M": {"mean": 86.0, "n": 5},
                    }
                }
            },
        })

        text = extract_text_result(resp)
        # Full raw payload must not have any Python repr
        assert_no_repr_artifacts(text)

        body = json.loads(text)
        substrate = body.get("related_substrate", [])
        assert isinstance(substrate, list)

        # Verify None fields serialized as JSON null (not "None" string).
        # The _dumps contract for None → JSON null (not the string "None")
        # cannot be tested purely from the parsed dict (None and null both
        # decode to None). Check the raw bytes for the "None" string in
        # positions that carry substrate field values.
        # NullBackend with no vault → substrate is []; no None fields.
        # If substrate is non-empty from vault: assert no "\"None\"" literals.
        for entry in substrate:
            for key, val in entry.items():
                if val is None:
                    # The raw wire should have null at this position, not "None"
                    # We can't pinpoint the exact byte offset, but the repr
                    # artifact check (assert_no_repr_artifacts on full text)
                    # already catches the default=str path.
                    pass
                elif isinstance(val, str):
                    assert val != "None", (
                        f"substrate entry[{key!r}] = 'None' (string) — "
                        "this is a default=str coercion bug: None was "
                        f"converted to the string 'None' instead of JSON null. Entry: {entry}"
                    )


def test_oracle_substrate_count_audit_column_present_and_correct() -> None:
    """S3: audit.db gains oracle_substrate_count column after ADR 0023
    migration; value is 0 for NullBackend (no vault notes seeded).

    Also verifies migration idempotency: a second AuditLog on the same
    db must not raise on the ALTER TABLE oracle_substrate_count step.

    Covers gate-evasion class 4 from the audit brief:
    'if a deployment had a v6.6.0 audit.db with the prior 6 oracle
    columns, does the v6.6.x ALTER TABLE add oracle_substrate_count
    cleanly without breaking on existing rows?'
    """
    import os
    import sqlite3
    import subprocess
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from tests._mcp_client import MCPClient, seed_full_config

    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        paths = seed_full_config(Path(tmp))
        env = {
            **os.environ,
            "BIOSENSOR_CONFIG_DIR": str(paths["config_dir"]),
            "BIOSENSOR_DATA_DIR": str(paths["data_dir"]),
        }

        proc = subprocess.Popen(
            [sys.executable, "-m", "biosensor_mcp", "serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        client = MCPClient(proc)
        try:
            client.initialize()
            client.call_tool("ask_local_oracle", {
                "question": "substrate count audit test",
                "resolved_context": {"csv_force_decline": {"peak": 60.0}},
                "subject_id": "P_sc_test",
            })
            import time
            time.sleep(0.5)
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

        audit_db = paths["data_dir"] / "audit.db"
        assert audit_db.exists(), f"audit.db not found at {audit_db}"

        with sqlite3.connect(str(audit_db)) as conn:
            all_cols = [
                row[1]
                for row in conn.execute("PRAGMA table_info(audit_log)").fetchall()
            ]
            assert "oracle_substrate_count" in all_cols, (
                f"oracle_substrate_count column missing from audit_log schema. "
                f"Columns present: {[c for c in all_cols if 'oracle' in c]}"
            )

            row = conn.execute(
                "SELECT oracle_substrate_count FROM audit_log "
                "WHERE tool_name = 'ask_local_oracle' AND outcome = 'SUCCESS'"
            ).fetchone()
            assert row is not None, "No SUCCESS oracle row in audit_log"
            count_val = row[0]
            # NullBackend with no vault notes seeded → substrate scan
            # returns [] → oracle_substrate_count == 0
            assert count_val == 0, (
                f"Expected oracle_substrate_count=0 for NullBackend with "
                f"no vault notes; got {count_val!r}"
            )

        # Idempotency: second AuditLog init on same file must not crash
        from biosensor_mcp.framework.audit import AuditLog
        audit2 = AuditLog(audit_db)
        try:
            cols2 = {
                row[1]
                for row in audit2._conn.execute(
                    "PRAGMA table_info(audit_log)"
                ).fetchall()
            }
            assert "oracle_substrate_count" in cols2, (
                "oracle_substrate_count missing after idempotent AuditLog re-init"
            )
        finally:
            audit2.close()


def test_vault_writer_storage_property_accessible() -> None:
    """S4: VaultWriter.storage property is accessible without error
    (ADR 0023 adds it; this is a new public API surface).

    The gate-evasion class: if storage is a @property that returns
    a thread-local object, accessing it from a test thread (simulating
    the router's async dispatch path) must not raise AttributeError or
    expose a closed connection.

    This test does NOT use a subprocess; it wires VaultWriter directly
    to verify the property contract at the Python level.
    """
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from biosensor_mcp.framework.vault.writer import VaultWriter

    with TemporaryDirectory() as tmp:
        vault_path = Path(tmp) / "vault"
        data_dir = Path(tmp) / "data"
        vault_path.mkdir()
        data_dir.mkdir()

        writer = VaultWriter(
            vault_path=vault_path,
            data_dir=data_dir,
            vaultable_tools=set(),
        )
        try:
            storage = writer.storage
            assert storage is not None, (
                "VaultWriter.storage returned None — "
                "LocalLLMLayer._vault_storage will silently skip substrate scan"
            )
            # Must be the VaultStorage type (import by name to avoid circular)
            assert hasattr(storage, "list_themes"), (
                f"VaultWriter.storage does not have list_themes; "
                f"got type {type(storage).__name__}. "
                "LocalLLMLayer._scan_related_substrate calls list_themes."
            )
            assert hasattr(storage, "list_notes"), (
                f"VaultWriter.storage does not have list_notes; "
                f"got type {type(storage).__name__}. "
                "LocalLLMLayer._scan_related_substrate calls list_notes."
            )
        finally:
            writer.close()


def test_tools_list_ask_local_oracle_description_contains_related_substrate() -> None:
    """S5: Schema drift check — tools/list description for ask_local_oracle
    mentions 'related_substrate' (the ADR 0023 addition).

    The gate-evasion class: the tool description was updated in
    LocalLLMLayer.tool_definitions but the wire-level tools/list endpoint
    could still serve a stale cached version. This test drives the live
    subprocess and asserts the description flowing over the wire contains
    the new field name so schema drift is caught end-to-end.
    """
    with spawn_server() as (client, _paths):
        client.initialize()
        list_resp = client.list_tools()
        tools = list_resp["result"]["tools"]
        oracle = next(
            (t for t in tools if t["name"] == "ask_local_oracle"), None
        )
        assert oracle is not None, "ask_local_oracle missing from tools/list"

        desc = oracle.get("description", "")
        assert "related_substrate" in desc, (
            "tools/list description for ask_local_oracle does not mention "
            "'related_substrate' — ADR 0023 description update was either "
            f"not merged into tool_definitions or not reaching the wire. "
            f"Actual description: {desc[:300]!r}"
        )


# ──────────────────────────────────────────────────────────────────
# ADR 0023 PR2 — next_best_calls + unresolved_intent wire surfaces
# G1–G4, added this audit run (v6.7.x)
# ──────────────────────────────────────────────────────────────────

def test_tools_list_description_mentions_all_three_cooperation_fields() -> None:
    """G1: tools/list description for ask_local_oracle mentions all three
    cooperation-loop fields over the wire.

    S5 only checked 'related_substrate' (ADR 0023 PR1). PR2 adds
    next_best_calls and unresolved_intent to the tool description.
    This test pins the full cooperation-loop teaching in the description
    flowing over the wire so a future description rollback is caught
    end-to-end, not just at the Python unit-test level.

    The gate-evasion class: unit tests on LocalLLMLayer.tool_definitions
    pass against the in-process description string; this test drives the
    subprocess so a stale compiled .pyc or an import error in layer.py
    would also surface here.
    """
    with spawn_server() as (client, _paths):
        client.initialize()
        list_resp = client.list_tools()
        assert "error" not in list_resp, (
            f"tools/list returned a JSON-RPC error — longer description "
            f"may have triggered a schema validation failure: {list_resp}"
        )

        tools = list_resp["result"]["tools"]
        oracle = next(
            (t for t in tools if t["name"] == "ask_local_oracle"), None
        )
        assert oracle is not None, "ask_local_oracle missing from tools/list"

        # No JSON-RPC error in the envelope means the longer description
        # did not break the mcp SDK's own schema validation.
        assert "error" not in list_resp, (
            "tools/list returned error after PR2 description update"
        )

        desc = oracle.get("description", "")
        # All three cooperation-loop field names must appear in the
        # description that flows over the wire.
        for field_name in ("related_substrate", "next_best_calls", "unresolved_intent"):
            assert field_name in desc, (
                f"tools/list description for ask_local_oracle is missing "
                f"'{field_name}' — PR2 description update not reaching the "
                f"wire. Actual description (first 400 chars): {desc[:400]!r}"
            )

        # The split rule must also reach the wire so hosted Claude learns
        # the distinction between fetching data and asking the analyst.
        # "iterate" or "re-invoke" teaches the cooperation loop pattern.
        assert (
            "iterate" in desc.lower() or "re-invoke" in desc.lower()
        ), (
            "tools/list description for ask_local_oracle is missing the "
            "iteration framing ('iterate' or 're-invoke') — hosted Claude "
            f"will read the response as a one-shot terminal answer. "
            f"Description: {desc[:400]!r}"
        )


def test_ask_local_oracle_response_has_gap_reasoning_fields_at_top_level() -> None:
    """G2: tools/call ask_local_oracle (NullBackend) response contains
    next_best_calls and unresolved_intent as top-level keys in the
    parsed payload.

    The gate-evasion class: OracleResponse.to_dict() emits both fields,
    but a router serialization bug or a merger of oracle._meta into the
    outer _meta block could bury them at a non-top-level path. This test
    pins the top-level position end-to-end through the subprocess.

    With NullBackend both fields default to [] — the test asserts
    presence and correct type, not content.
    """
    with spawn_server() as (client, _paths):
        client.initialize()

        resp = client.call_tool("ask_local_oracle", {
            "question": "PR2 gap-reasoning field presence test",
            "resolved_context": {
                "csv_force_decline": {
                    "peak": 120.0,
                    "decline_pct_total": 15.0,
                    "n_samples": 5,
                },
            },
            "subject_id": "P003",
        })

        assert "error" not in resp, f"tools/call returned error: {resp}"
        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)

        body = json.loads(text)

        # next_best_calls — top-level, list type
        assert "next_best_calls" in body, (
            "next_best_calls is missing from the top-level tools/call "
            "response. Expected OracleResponse.to_dict() to include it "
            "at root level. Top-level keys: "
            f"{sorted(body.keys())}"
        )
        nbc = body["next_best_calls"]
        assert isinstance(nbc, list), (
            f"next_best_calls must be a list on the wire; "
            f"got {type(nbc).__name__}: {nbc!r}"
        )

        # unresolved_intent — top-level, list type
        assert "unresolved_intent" in body, (
            "unresolved_intent is missing from the top-level tools/call "
            "response. Expected OracleResponse.to_dict() to include it "
            "at root level. Top-level keys: "
            f"{sorted(body.keys())}"
        )
        ui = body["unresolved_intent"]
        assert isinstance(ui, list), (
            f"unresolved_intent must be a list on the wire; "
            f"got {type(ui).__name__}: {ui!r}"
        )

        # NullBackend emits empty lists — confirm the empty-list contract
        # is stable (populated values come only from a real LLM backend).
        assert nbc == [], (
            f"NullBackend must emit next_best_calls=[] (no LLM in loop); "
            f"got: {nbc!r}"
        )
        assert ui == [], (
            f"NullBackend must emit unresolved_intent=[] (no LLM in loop); "
            f"got: {ui!r}"
        )

        # The fields must NOT appear nested inside _meta.
        meta = body.get("_meta", {})
        assert "next_best_calls" not in meta, (
            "next_best_calls was buried inside _meta instead of at top level"
        )
        assert "unresolved_intent" not in meta, (
            "unresolved_intent was buried inside _meta instead of at top level"
        )


def test_gap_reasoning_fields_wire_serialization_no_repr() -> None:
    """G3: _dumps serialization of next_best_calls and unresolved_intent
    produces clean JSON — no Python repr() artifacts, no silent
    default=str coercion of list types into strings.

    The gate-evasion class: list[str] is natively serializable by both
    orjson and stdlib json, BUT a stale default=str coercion in _dumps
    would turn a list into its repr "['csv_force_decline']" rather than
    a JSON array. This test exercises the full round-trip including
    a non-empty list to distinguish "empty list serializes fine" from
    "list with content serializes fine".

    NullBackend always returns []. We call to_dict() directly to inject
    non-empty lists and then _dumps them, mirroring exactly what the
    router's dispatch path does when an OllamaBackend returns results.
    """
    from biosensor_mcp.framework.audit import _dumps
    from biosensor_mcp.framework.local_llm.oracle import (
        OracleMeta,
        OracleResponse,
    )

    meta = OracleMeta(
        model_id="llama3.1:8b",
        model_version_hash="abc12345",
        tier="guardian",
        latency_ms=423,
        prompt_hash="f1e2d3c4",
        called_at="2026-05-03T12:00:00+00:00",
        processing_calls=["csv_force_decline"],
        backend="ollama",
    )
    resp = OracleResponse(
        numerical_claims=[],
        narrative="P003 showed a 15% decline.",
        ambiguity_axes=["Which muscle group is primary?"],
        confidence=0.72,
        next_best_calls=["csv_cohort_summary", "csv_force_decline"],
        unresolved_intent=["Which group does P003 belong to?"],
        meta=meta,
    )

    d = resp.to_dict()
    # Serialize via the same path the router uses.
    encoded = _dumps(d)

    # No Python repr artifacts anywhere.
    assert_no_repr_artifacts(encoded)

    # The two new list fields must appear as JSON arrays, not stringified
    # Python reprs. The smoking-gun signature of the bug would be the
    # literal string "['csv_cohort_summary'" appearing in the wire payload.
    assert "['csv_cohort_summary'" not in encoded, (
        "next_best_calls was serialized as a Python repr string instead "
        "of a JSON array — this is a default=str coercion bug. "
        f"Wire payload excerpt: {encoded[:400]}"
    )
    assert "['Which group" not in encoded, (
        "unresolved_intent was serialized as a Python repr string instead "
        "of a JSON array — this is a default=str coercion bug. "
        f"Wire payload excerpt: {encoded[:400]}"
    )

    # Full round-trip: parse back and verify structural integrity.
    decoded = json.loads(encoded)
    assert decoded["next_best_calls"] == [
        "csv_cohort_summary", "csv_force_decline",
    ], (
        f"next_best_calls round-trip failed: {decoded['next_best_calls']!r}"
    )
    assert decoded["unresolved_intent"] == [
        "Which group does P003 belong to?",
    ], (
        f"unresolved_intent round-trip failed: {decoded['unresolved_intent']!r}"
    )
    # Verify the values are genuine JSON arrays in the raw encoded string.
    assert '"next_best_calls": ["csv_cohort_summary"' in encoded or \
           '"next_best_calls":["csv_cohort_summary"' in encoded, (
        "next_best_calls not serialized as a JSON array in raw wire bytes. "
        f"Wire payload: {encoded[:400]}"
    )


def test_tools_list_no_json_rpc_error_after_description_expansion() -> None:
    """G4: tools/list returns no JSON-RPC error after the PR2 description
    expansion and parses without error.

    The gate-evasion class: the mcp SDK validates tool inputSchema and
    description length at registration time in some versions. A description
    that exceeds an undocumented length limit, or a malformed description
    string (e.g. unmatched quotes, control characters), could produce a
    JSON-RPC error envelope in the tools/list response without crashing
    the server. This test pins the clean-parse invariant for the full
    longer description added in PR2.

    Specifically checks:
    - No "error" key at the JSON-RPC envelope level.
    - tools/list result decodes as valid JSON.
    - ask_local_oracle appears in the tool list (not silently dropped on
      registration error).
    - The raw tools/list payload contains no Python repr artifacts
      (guards against the description field itself being repr()'d into
      the schema emission path).
    """
    with spawn_server() as (client, _paths):
        client.initialize()
        list_resp = client.list_tools()

        # JSON-RPC envelope must not carry an error.
        assert "error" not in list_resp, (
            f"tools/list returned a JSON-RPC error after PR2 description "
            f"expansion. This may mean the mcp SDK rejected the longer "
            f"description at registration time. Error: {list_resp.get('error')}"
        )
        assert "result" in list_resp, (
            f"tools/list response has no 'result' key: {list_resp}"
        )

        # Raw payload must contain no Python repr artifacts.
        raw = json.dumps(list_resp)
        assert_no_repr_artifacts(raw)

        # ask_local_oracle must still be in the list (not silently dropped).
        tools = list_resp["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "ask_local_oracle" in names, (
            f"ask_local_oracle missing from tools/list after PR2 description "
            f"expansion — it may have been silently dropped on registration. "
            f"Tool count: {len(tools)}"
        )


# ──────────────────────────────────────────────────────────────────
# v6.9.0 regression tests — tour subcommand isolation
# ──────────────────────────────────────────────────────────────────


def test_v690_tour_subcommand_not_exposed_as_mcp_tool() -> None:
    """V690-T1: the new ``biosensor-mcp tour`` CLI subcommand must not
    appear as an MCP tool in tools/list.

    Adjacent risk: the v6.9.0 dispatch-table addition in ``__main__.py``
    (``"tour": cmd_tour``) could in theory leak into the router's tool
    registry if ``cmd_tour`` were called at import time or if the
    dispatch table were iterated by a tool-registration path.

    This test drives tools/list end-to-end and asserts no ``tour``-named
    or ``cmd_tour``-named entry is present. It is the subprocess-level
    regression for the startup-isolation invariant.
    """
    with spawn_server() as (client, _paths):
        client.initialize()
        resp = client.list_tools()
        assert "error" not in resp, f"tools/list error: {resp}"
        names = {t["name"] for t in resp["result"]["tools"]}
        assert "tour" not in names, (
            "tour appeared as an MCP tool — cmd_tour dispatch leaked into "
            "the router's tool registry."
        )
        assert "cmd_tour" not in names, (
            "cmd_tour appeared as an MCP tool — dispatch table iterated "
            "by tool-registration path."
        )
        # No repr artifacts from the new dispatch entry.
        assert_no_repr_artifacts(json.dumps(resp))


def test_v690_tool_count_unchanged_at_49() -> None:
    """V690-T2: tools/list count is 49 with full config loaded (unchanged
    from v6.8.x — tour adds no new MCP tools).

    Expected composition (full config: running + csv_dir + vault + local_llm):
      25 vault + 12 running + 7 csv_dir + 1 ask_local_oracle
      + 4 auto-generated consent tools (approve/revoke × running/csv_dir)
      = 49

    If this count changes, it means a tool was added or removed without
    a corresponding CLAUDE.md tool-surface update. The template child is
    not registered in the test config (opt-in requires explicit config key),
    so its 3 tools are excluded from the wire count.
    """
    with spawn_server() as (client, _paths):
        client.initialize()
        resp = client.list_tools()
        assert "error" not in resp, f"tools/list error: {resp}"
        tools = resp["result"]["tools"]
        n = len(tools)
        assert n == 49, (
            f"tools/list count changed: expected 49, got {n}. "
            f"If a new tool was added, update CLAUDE.md tool-surface table "
            f"and change this assertion to the new expected count. "
            f"Current tools: {sorted(t['name'] for t in tools)}"
        )


def test_v690_serve_startup_meta_version_stamp() -> None:
    """V690-T3: a Tier-1 tool call returns _meta.package_version matching __version__.

    This is the end-to-end version-stamp regression: the version in
    ``__init__.py`` must propagate through the router's _meta block to
    the wire payload. A mismatch here means the installed package and
    the running code are out of sync.

    The assertion compares against ``__version__`` (read at test time)
    rather than a hardcoded string, so this test does not go stale on
    every version bump. v6.9.1 found a hardcoded ``"6.9.0"`` literal
    here that silently broke release-shipper's post-bump merge gate.
    """
    from biosensor_mcp import __version__

    with spawn_server() as (client, _paths):
        client.initialize()
        resp = client.call_tool("csv_list_files", {})
        assert "error" not in resp
        text = extract_text_result(resp)
        assert_no_repr_artifacts(text)
        body = json.loads(text)
        assert "_meta" in body
        meta = body["_meta"]
        assert meta["package_version"] == __version__, (
            f"_meta.package_version {meta['package_version']!r} != "
            f"__version__ {__version__!r} — version bump not wired through."
        )

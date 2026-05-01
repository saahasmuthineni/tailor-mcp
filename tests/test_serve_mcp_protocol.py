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

Each test corresponds to a Phase-1 surface in the v6.5.0
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

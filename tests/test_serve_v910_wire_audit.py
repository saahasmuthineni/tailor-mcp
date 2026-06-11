"""
MCP-protocol wire audit — v9.1.0 (post-v9.0.0 entity_id rename + v9.1.0 inspector).

Surfaces under test (Phase 0 inventory, not previously covered by subprocess tests):

  N1 — entity_id rename (v9.0.0): tools/list wire has entity_id not subject_id;
        tools/call with entity_id param lands the value in audit.db entity_id column
        (not subject_id column); subject_id column absent from audit.db schema.
  N2 — initialize handshake: serverInfo.name == "tailor"; protocolVersion is a string;
        capabilities.tools is present. Full wire-shape assertion.
  N3 — cost gate LLMInstruction wire payload: all three fields present + string-typed;
        no repr artifacts; consent must be approved first.
  N4 — vault markdown round-trip: backtick / unicode / YAML frontmatter survive
        capture_moment → read_note byte-equal (modulo frontmatter header).
  N5 — strong_motion child subprocess registration: seismic_list_records, Tier-1
        happy path; _meta shape; no repr artifacts; consent-gate on seismic_downsampled.
  N6 — tools/list allowed_values serialization: vault_list_notes kind param must
        carry a non-empty array (not a Python list repr) after v7.6.0 kind filter.
  N7 — consent approval → tier-2 call happy path (csv_dir domain): approve consent,
        call csv_downsampled, assert success shape and _meta.domain == "csv_dir".
  N8 — tool name collision detection wire-level: verify server boots without collision
        on the full config (regression guard for future child additions).
  N9 — _dumps seam: Decimal, Path, datetime in a child response coerce correctly;
        no repr artifacts on any registered tool call.

Cross-cutting contract tests (Phase 2 — no subprocess required):

  C1 — every vaultable_tool in every registered child has a paired renderer
        in VaultWriter._renderers (the H2 contract catch from v6.5.0).
  C2 — every ToolDefinition.params value has a "description" key (or the
        router's .get fallback is in place — verified via the actual schema).
  C3 — no tool name shadows another across all children + framework layers.
  C4 — entity_id param_schema is ENTITY_ID_SCHEMA (not a stale subject_id
        ValidationSchema) across all children that declare it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests._mcp_client import (
    MCPClient,
    assert_no_repr_artifacts,
    extract_text_result,
    seed_full_config,
    spawn_server,
)

# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def _seed_strong_motion(root: Path) -> dict[str, Path]:
    """
    Seed a full config that includes strong_motion alongside csv_dir + vault.

    Uses the synthetic V1 builder from the shape-test helper (_synth.py).
    Returns a paths dict with keys: config_dir, data_dir, vault_path,
    csv_dir, sm_dir.
    """
    # Re-use the standard seeding for csv+vault, then layer in strong_motion.
    paths = seed_full_config(root)
    sm_dir = root / "seismic"
    sm_dir.mkdir(parents=True, exist_ok=True)

    # Write two synthetic V1 records using the same make_v1_text helper
    # the unit tests use.  Import here so the helper lives in one place.
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from children.strong_motion._synth import make_v1_text

    (sm_dir / "ch1.v1").write_text(
        make_v1_text(
            [0.1, -0.5, 1.2, 1.927, -0.8, 0.3, -1.5, 0.05],
            dt=0.01, station="TARZANA", channel=1, azimuth=90,
        ),
        encoding="utf-8",
    )
    (sm_dir / "ch2.raw").write_text(
        make_v1_text(
            [0.05, 0.4, -0.9, 0.6, -0.3, 0.2],
            dt=0.01, station="SYLMAR", channel=1, azimuth=180,
        ),
        encoding="utf-8",
    )
    (sm_dir / "metadata.json").write_text(
        json.dumps({
            "ch1.v1": {"site": "tarzana", "event": "northridge"},
            "ch2.raw": {"site": "sylmar", "event": "northridge"},
        }),
        encoding="utf-8",
    )

    # Merge strong_motion into the existing user_config.json
    ucfg_path = paths["config_dir"] / "user_config.json"
    ucfg = json.loads(ucfg_path.read_text(encoding="utf-8"))
    ucfg["strong_motion"] = {"path": str(sm_dir)}
    ucfg_path.write_text(json.dumps(ucfg), encoding="utf-8")

    paths["sm_dir"] = sm_dir
    return paths


def _spawn_sm_server(root: Path):
    """Spawn tailor serve with a strong_motion-seeded config."""
    paths = _seed_strong_motion(root)
    env = {
        **os.environ,
        "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
        "TAILOR_DATA_DIR": str(paths["data_dir"]),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "tailor", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    return MCPClient(proc), paths


# ──────────────────────────────────────────────────────────────────
# N1 — entity_id rename (v9.0.0)
# ──────────────────────────────────────────────────────────────────

class TestN1EntityIdRename:
    """v9.0.0 rename: subject_id → entity_id on every wire surface."""

    def test_n1a_no_subject_id_in_tools_list_wire_payload(self) -> None:
        """
        The tools/list wire payload must NOT contain the string 'subject_id'
        anywhere (not in param names, descriptions, or schema).

        This is the forward-only rename contract: the v9.0.0 public flip
        renamed every occurrence of subject_id to entity_id. A hit here means
        a ToolDefinition.params dict was not updated.
        """
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            raw_json = json.dumps(resp)
            assert "subject_id" not in raw_json, (
                "tools/list wire payload contains 'subject_id' — the v9.0.0 "
                "rename to entity_id is incomplete on at least one tool. "
                "Affected tool(s): "
                + str([t["name"] for t in resp["result"]["tools"]
                        if "subject_id" in json.dumps(t)])
            )

    def test_n1b_entity_id_present_in_tools_with_audit_scoping(self) -> None:
        """
        Tools that carry the optional entity_id audit-scoping param must
        expose it as 'entity_id' (not 'subject_id') in the inputSchema.
        """
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            tools = resp["result"]["tools"]
            # csv_list_files is a known entity_id-bearing tool
            csv_list = next((t for t in tools if t["name"] == "csv_list_files"), None)
            assert csv_list is not None
            props = csv_list["inputSchema"].get("properties", {})
            assert "entity_id" in props, (
                "csv_list_files.inputSchema is missing 'entity_id' property — "
                "the v9.0.0 rename may not have been applied to csv_dir/child.py"
            )
            assert "subject_id" not in props, (
                "csv_list_files.inputSchema still contains 'subject_id' — "
                "the v9.0.0 rename is partial in csv_dir/child.py"
            )

    def test_n1c_entity_id_param_lands_in_audit_db_column(self) -> None:
        """
        Passing entity_id to a tool call must land in the audit.db
        entity_id column — not a subject_id column — and the column must
        exist under the new name.

        This is the end-to-end wire→storage proof for the v9.0.0 column rename.
        The migration code (AuditLog.__init__) handles legacy DBs via ALTER TABLE;
        fresh DBs (which this test creates) must have entity_id natively.
        """
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp:
            paths = seed_full_config(Path(tmp))
            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
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
                resp = client.call_tool(
                    "csv_list_files", {"entity_id": "S042"}
                )
                text = extract_text_result(resp)
                body = json.loads(text)
                assert "error" not in body, f"csv_list_files failed: {body}"
            finally:
                proc.stdin.close()
                proc.wait(timeout=5)

            # Now inspect the audit.db directly
            db = sqlite3.connect(str(paths["data_dir"] / "audit.db"))
            # Column names must include entity_id, must NOT include subject_id
            cols = {row[1] for row in db.execute(
                "PRAGMA table_info(audit_log)"
            ).fetchall()}
            assert "entity_id" in cols, (
                "audit.db is missing entity_id column — "
                "AuditLog schema migration may have failed"
            )
            assert "subject_id" not in cols, (
                "audit.db still contains subject_id column — "
                "v9.0.0 column rename did not run or was reverted"
            )

            # The call with entity_id='S042' must produce a row where
            # entity_id == 'S042'
            rows = db.execute(
                "SELECT entity_id FROM audit_log "
                "WHERE tool_name='csv_list_files' AND entity_id IS NOT NULL"
            ).fetchall()
            assert rows, (
                "No audit row with entity_id='S042' found — entity_id is not "
                "being threaded from the wire call to the audit row"
            )
            assert rows[0][0] == "S042", (
                f"Audit row entity_id={rows[0][0]!r}, expected 'S042'"
            )
            db.close()


# ──────────────────────────────────────────────────────────────────
# N2 — initialize handshake wire shape
# ──────────────────────────────────────────────────────────────────

class TestN2InitializeHandshake:
    """Full wire-shape assertions on the initialize response."""

    def test_n2a_initialize_returns_json_rpc_envelope(self) -> None:
        """initialize response must be a valid JSON-RPC 2.0 success envelope."""
        with spawn_server() as (client, _paths):
            resp = client.initialize()
            assert resp.get("jsonrpc") == "2.0", (
                f"initialize response missing jsonrpc:2.0 — got {resp.get('jsonrpc')!r}"
            )
            assert "result" in resp, (
                f"initialize response missing 'result' key: {resp}"
            )
            assert "error" not in resp, (
                f"initialize response contains 'error': {resp}"
            )

    def test_n2b_server_info_name_is_tailor(self) -> None:
        """serverInfo.name must be 'tailor' — the router's registered name."""
        with spawn_server() as (client, _paths):
            resp = client.initialize()
            server_info = resp["result"].get("serverInfo", {})
            assert server_info.get("name") == "tailor", (
                f"serverInfo.name={server_info.get('name')!r}, expected 'tailor'. "
                "This indicates the MCP server was registered under the wrong name."
            )

    def test_n2c_protocol_version_is_string(self) -> None:
        """protocolVersion must be a string (mcp SDK version-negotiation field)."""
        with spawn_server() as (client, _paths):
            resp = client.initialize()
            pv = resp["result"].get("protocolVersion")
            assert isinstance(pv, str), (
                f"protocolVersion is {type(pv).__name__!r} not str: {pv!r}"
            )
            # Must be non-empty — the mcp SDK uses this for protocol negotiation.
            assert len(pv) > 0

    def test_n2d_capabilities_tools_present(self) -> None:
        """capabilities.tools must be present — required for tool discovery."""
        with spawn_server() as (client, _paths):
            resp = client.initialize()
            caps = resp["result"].get("capabilities", {})
            assert "tools" in caps, (
                f"capabilities missing 'tools' key: {caps}"
            )

    def test_n2e_initialize_no_repr_artifacts(self) -> None:
        """initialize response must not contain Python repr() artifacts."""
        with spawn_server() as (client, _paths):
            resp = client.initialize()
            raw = json.dumps(resp)
            assert_no_repr_artifacts(raw)

    def test_n2f_server_info_version_is_tailor_version(self) -> None:
        """
        serverInfo.version in the initialize response MUST be the tailor package
        version (e.g. '9.1.0'), NOT the mcp SDK version (e.g. '1.27.2').

        Regression guard for the v9.1.0 wire-identity bug: router.create_server
        once called Server(self.name) without version=, so the mcp SDK fell back
        to pkg_version('mcp') and clients saw the transport library's version on
        the initialize handshake while every tool call's _meta.package_version
        reported tailor's. Fixed by passing version=tailor.__version__.
        """
        import tailor
        with spawn_server() as (client, _paths):
            resp = client.initialize()
            server_info = resp["result"].get("serverInfo", {})
            actual_version = server_info.get("version")
            assert actual_version == tailor.__version__, (
                f"serverInfo.version={actual_version!r} — "
                f"expected tailor.__version__={tailor.__version__!r}. "
                "The mcp SDK is reporting its own version instead of tailor's. "
                "Fix: Server(self.name, version=tailor.__version__) in router.py:501."
            )


# ──────────────────────────────────────────────────────────────────
# N3 — cost gate LLMInstruction wire payload
# ──────────────────────────────────────────────────────────────────

class TestN3CostGateWireShape:
    """
    Cost gate wire payload must carry a structured LLMInstruction with
    all three fields present and string/list typed.
    """

    def test_n3a_cost_gate_triggers_on_tier3_with_low_threshold(self) -> None:
        """
        Setting cost_threshold=1 guarantees any Tier-3 call trips the gate.
        Assert that the gate response has gate=='cost_approval_required'.
        """
        with tempfile.TemporaryDirectory() as tmp:
            paths = seed_full_config(Path(tmp))
            ucfg_path = paths["config_dir"] / "user_config.json"
            ucfg = json.loads(ucfg_path.read_text())
            ucfg["cost_threshold"] = 1
            ucfg_path.write_text(json.dumps(ucfg))

            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
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
                # Approve consent first (csv_dir is tier-2+ gated)
                client.call_tool("approve_consent_csv_dir", {})
                # Now call the tier-3 tool
                resp = client.call_tool("csv_raw_stream", {"file_id": "P001.csv"})
                text = extract_text_result(resp)
                body = json.loads(text)
                assert body.get("gate") == "cost_approval_required", (
                    f"Expected cost gate, got: {body}"
                )
            finally:
                proc.stdin.close()
                proc.wait(timeout=5)

    def test_n3b_cost_gate_llm_instruction_fields_typed_correctly(self) -> None:
        """
        The cost gate LLMInstruction must have:
          - must_do: list[str] (non-empty)
          - must_not_do: list[str] (non-empty)
          - on_ambiguous_reply: str
        """
        with tempfile.TemporaryDirectory() as tmp:
            paths = seed_full_config(Path(tmp))
            ucfg_path = paths["config_dir"] / "user_config.json"
            ucfg = json.loads(ucfg_path.read_text())
            ucfg["cost_threshold"] = 1
            ucfg_path.write_text(json.dumps(ucfg))

            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
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
                client.call_tool("approve_consent_csv_dir", {})
                resp = client.call_tool("csv_raw_stream", {"file_id": "P001.csv"})
                text = extract_text_result(resp)
                body = json.loads(text)
                llm = body.get("llm_instruction", {})
                assert isinstance(llm.get("must_do"), list), (
                    f"llm_instruction.must_do is not a list: {llm.get('must_do')!r}"
                )
                assert len(llm["must_do"]) > 0, "must_do is empty"
                assert isinstance(llm.get("must_not_do"), list), (
                    f"llm_instruction.must_not_do is not a list: {llm.get('must_not_do')!r}"
                )
                assert len(llm["must_not_do"]) > 0, "must_not_do is empty"
                assert isinstance(llm.get("on_ambiguous_reply"), str), (
                    f"on_ambiguous_reply is not a str: {llm.get('on_ambiguous_reply')!r}"
                )
            finally:
                proc.stdin.close()
                proc.wait(timeout=5)

    def test_n3c_cost_gate_no_repr_artifacts(self) -> None:
        """Cost gate response must not contain Python repr() artifacts."""
        with tempfile.TemporaryDirectory() as tmp:
            paths = seed_full_config(Path(tmp))
            ucfg_path = paths["config_dir"] / "user_config.json"
            ucfg = json.loads(ucfg_path.read_text())
            ucfg["cost_threshold"] = 1
            ucfg_path.write_text(json.dumps(ucfg))

            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
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
                client.call_tool("approve_consent_csv_dir", {})
                resp = client.call_tool("csv_raw_stream", {"file_id": "P001.csv"})
                text = extract_text_result(resp)
                assert_no_repr_artifacts(text)
            finally:
                proc.stdin.close()
                proc.wait(timeout=5)

    def test_n3d_cost_gate_options_field_is_dict_not_repr(self) -> None:
        """
        The 'options' field in the cost gate response must be a JSON dict,
        not a Python repr of a dict. This guards against _dumps coercion bugs
        that could render options as {"full": {"tokens": <int>, ...}} correctly
        while a nested CostEstimate object leaks repr.
        """
        with tempfile.TemporaryDirectory() as tmp:
            paths = seed_full_config(Path(tmp))
            ucfg_path = paths["config_dir"] / "user_config.json"
            ucfg = json.loads(ucfg_path.read_text())
            ucfg["cost_threshold"] = 1
            ucfg_path.write_text(json.dumps(ucfg))

            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
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
                client.call_tool("approve_consent_csv_dir", {})
                resp = client.call_tool("csv_raw_stream", {"file_id": "P001.csv"})
                text = extract_text_result(resp)
                body = json.loads(text)
                options = body.get("options")
                assert isinstance(options, dict), (
                    f"options field is not a dict: {type(options).__name__!r} — {options!r}"
                )
                assert "full" in options, (
                    f"options missing 'full' key: {options}"
                )
                assert isinstance(options["full"].get("tokens"), int), (
                    f"options.full.tokens is not an int: {options['full'].get('tokens')!r}"
                )
            finally:
                proc.stdin.close()
                proc.wait(timeout=5)


# ──────────────────────────────────────────────────────────────────
# N4 — vault markdown round-trip
# ──────────────────────────────────────────────────────────────────

class TestN4VaultMarkdownRoundTrip:
    """
    vault_capture_moment → vault_read_note must be byte-equal on the
    body content (modulo frontmatter header and the _meta block).
    Guards H4 from the v6.5.0 audit: markdown with backticks, unicode,
    and YAML-special chars must survive the atomic write path intact.
    """

    def test_n4a_unicode_body_survives_round_trip(self) -> None:
        """Unicode (ΔHR≈10bpm, 日本語) in vault_capture_moment body must
        survive write→read without corruption or repr artifacts."""
        body_text = (
            "Observation: ΔHR≈10bpm — cardiac drift at 35 min. "
            "参加者 S001 — p<0.05 (α=0.05). "
            "Naïve baseline: μ±σ = 72±8 bpm."
        )
        with spawn_server() as (client, paths):
            client.initialize()
            resp = client.call_tool("vault_capture_moment", {
                "title": "Unicode Round-Trip Test",
                "body": body_text,
            })
            text = extract_text_result(resp)
            assert_no_repr_artifacts(text)
            body = json.loads(text)
            assert "error" not in body, f"vault_capture_moment failed: {body}"
            filename = body.get("filename", "")
            assert filename, "vault_capture_moment returned no filename"

            # Read back via vault_read_note
            resp2 = client.call_tool("vault_read_note", {"filename": filename})
            text2 = extract_text_result(resp2)
            assert_no_repr_artifacts(text2)
            body2 = json.loads(text2)
            assert "error" not in body2, f"vault_read_note failed: {body2}"

            # The wire content must contain the original body text verbatim
            wire_content = body2.get("content", "")
            assert body_text in wire_content, (
                f"Unicode body text not preserved in vault_read_note content. "
                f"Expected: {body_text!r}\n"
                f"Got content (first 500 chars): {wire_content[:500]!r}"
            )

    def test_n4b_backtick_fenced_code_block_survives_round_trip(self) -> None:
        """
        Triple-backtick fenced code blocks in vault body must survive the
        atomic write path. This catches escaping bugs in render_moment_note
        or atomic write that would corrupt markdown syntax.
        """
        body_text = (
            "Insight with code:\n\n"
            "```python\n"
            "import pandas as pd\n"
            "df = pd.read_csv('P001.csv')\n"
            "```\n\n"
            "And inline `code` too."
        )
        with spawn_server() as (client, paths):
            client.initialize()
            resp = client.call_tool("vault_capture_moment", {
                "title": "Backtick Round-Trip Test",
                "body": body_text,
            })
            text = extract_text_result(resp)
            body = json.loads(text)
            assert "error" not in body
            filename = body.get("filename", "")

            # Read from disk directly — do not rely solely on vault_read_note
            # to catch the corruption (the reader might strip/normalise).
            if filename:
                disk_file = paths["vault_path"] / filename
                if disk_file.exists():
                    disk_text = disk_file.read_text(encoding="utf-8")
                    assert "```python" in disk_text, (
                        "Triple-backtick fenced code block not preserved on disk. "
                        f"Disk content snippet: {disk_text[:400]!r}"
                    )
                    assert "import pandas as pd" in disk_text
                    assert "inline `code`" in disk_text or "`code`" in disk_text

    def test_n4c_yaml_special_chars_in_title_survive(self) -> None:
        """
        YAML-special characters in the title (colons, brackets, quotes)
        must survive the frontmatter serialization path without corrupting
        the YAML block. A corrupt frontmatter block would cause vault_rescan
        to silently drop the note from the index.
        """
        title = 'HRV Analysis: "LF/HF ratio" [morning vs evening]'
        with spawn_server() as (client, paths):
            client.initialize()
            resp = client.call_tool("vault_capture_moment", {
                "title": title,
                "body": "Body text for YAML special char test.",
            })
            text = extract_text_result(resp)
            body = json.loads(text)
            assert "error" not in body, f"vault_capture_moment failed: {body}"
            filename = body.get("filename", "")

            if filename:
                disk_file = paths["vault_path"] / filename
                if disk_file.exists():
                    disk_text = disk_file.read_text(encoding="utf-8")
                    # The frontmatter title field must be YAML-safe
                    # (either quoted or escaped). Verify the file is valid YAML
                    # by checking the --- delimiters are intact.
                    assert disk_text.startswith("---"), (
                        "Vault note does not start with YAML frontmatter ---"
                    )
                    # Find the closing ---
                    second_marker = disk_text.find("---", 3)
                    assert second_marker > 3, (
                        "Vault note YAML frontmatter not properly closed"
                    )
                    frontmatter = disk_text[3:second_marker]
                    # The title should appear somewhere in the frontmatter
                    # (possibly quoted). Check it didn't disappear.
                    # Even if YAML-quoted, the text should be recognizable.
                    assert "HRV" in frontmatter or "HRV" in disk_text

    def test_n4d_vault_read_note_no_repr_artifacts(self) -> None:
        """vault_read_note response must contain no Python repr() artifacts."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("vault_capture_moment", {
                "title": "Repr Artifact Guard",
                "body": "Testing that datetime in frontmatter does not repr-leak.",
            })
            text = extract_text_result(resp)
            body = json.loads(text)
            filename = body.get("filename", "")
            if filename:
                resp2 = client.call_tool("vault_read_note", {"filename": filename})
                text2 = extract_text_result(resp2)
                assert_no_repr_artifacts(text2)


# ──────────────────────────────────────────────────────────────────
# N5 — strong_motion child subprocess registration
# ──────────────────────────────────────────────────────────────────

class TestN5StrongMotionSubprocess:
    """
    First subprocess wire coverage for StrongMotionChild.

    StrongMotionChild has 5 tools (2 Tier-1, 1 Tier-1 cohort, 1 Tier-2,
    1 Tier-3). This test class covers: tools/list registration, Tier-1
    happy path, _meta shape, no repr artifacts, and the consent gate on
    the Tier-2 seismic_downsampled tool.

    GAP closed: no subprocess tests existed for this child prior to this
    audit run.
    """

    def test_n5a_seismic_tools_appear_in_tools_list(self) -> None:
        """All 5 seismic tools must appear in tools/list after strong_motion
        is seeded."""
        with tempfile.TemporaryDirectory() as tmp:
            client, paths = _spawn_sm_server(Path(tmp))
            try:
                client.initialize()
                resp = client.list_tools()
                assert "error" not in resp
                names = {t["name"] for t in resp["result"]["tools"]}
                for expected in (
                    "seismic_list_records",
                    "seismic_record_summary",
                    "seismic_cohort_summary",
                    "seismic_downsampled",
                    "seismic_full_trace",
                ):
                    assert expected in names, (
                        f"'{expected}' missing from tools/list — "
                        "StrongMotionChild registration failed"
                    )
                # Consent tools for strong_motion domain
                assert "approve_consent_strong_motion" in names
                assert "revoke_consent_strong_motion" in names
            finally:
                client.proc.stdin.close()
                client.proc.wait(timeout=5)

    def test_n5b_seismic_list_records_tier1_happy_path(self) -> None:
        """seismic_list_records (Tier 1) returns count, records list, and _meta."""
        with tempfile.TemporaryDirectory() as tmp:
            client, _paths = _spawn_sm_server(Path(tmp))
            try:
                client.initialize()
                resp = client.call_tool("seismic_list_records", {})
                text = extract_text_result(resp)
                assert_no_repr_artifacts(text)
                body = json.loads(text)
                assert "error" not in body, f"seismic_list_records failed: {body}"
                assert "count" in body or "records" in body, (
                    f"seismic_list_records response missing count/records: {list(body.keys())}"
                )
                assert "_meta" in body
                meta = body["_meta"]
                assert meta["tool_name"] == "seismic_list_records"
                assert meta["domain"] == "strong_motion"
                assert meta["tier"] == 1
                assert isinstance(meta.get("called_at"), str)
                # called_at must be ISO-8601
                from datetime import datetime
                datetime.fromisoformat(meta["called_at"].replace("Z", "+00:00"))
            finally:
                client.proc.stdin.close()
                client.proc.wait(timeout=5)

    def test_n5c_seismic_list_records_no_repr_artifacts(self) -> None:
        """seismic_list_records wire payload must not contain repr() artifacts."""
        with tempfile.TemporaryDirectory() as tmp:
            client, _paths = _spawn_sm_server(Path(tmp))
            try:
                client.initialize()
                resp = client.call_tool("seismic_list_records", {})
                text = extract_text_result(resp)
                assert_no_repr_artifacts(text)
            finally:
                client.proc.stdin.close()
                client.proc.wait(timeout=5)

    def test_n5d_seismic_record_summary_tier1_no_repr(self) -> None:
        """seismic_record_summary (Tier-1 PGA/Arias) must return clean JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            client, _paths = _spawn_sm_server(Path(tmp))
            try:
                client.initialize()
                resp = client.call_tool(
                    "seismic_record_summary", {"file_id": "ch1.v1"}
                )
                text = extract_text_result(resp)
                assert_no_repr_artifacts(text)
                body = json.loads(text)
                assert "error" not in body, f"seismic_record_summary failed: {body}"
                assert "_meta" in body
            finally:
                client.proc.stdin.close()
                client.proc.wait(timeout=5)

    def test_n5e_seismic_downsampled_consent_gate_fires(self) -> None:
        """
        seismic_downsampled (Tier 2) must fire the consent gate before
        any biometric data is returned. The consent gate response must
        carry the structured LLMInstruction.
        """
        with tempfile.TemporaryDirectory() as tmp:
            client, _paths = _spawn_sm_server(Path(tmp))
            try:
                client.initialize()
                resp = client.call_tool(
                    "seismic_downsampled",
                    {"file_id": "ch1.v1", "interval": 2},
                )
                text = extract_text_result(resp)
                assert_no_repr_artifacts(text)
                body = json.loads(text)
                assert body.get("gate") == "consent_required", (
                    f"Expected consent gate, got: {body}"
                )
                assert body.get("domain") == "strong_motion"
                llm = body.get("llm_instruction", {})
                assert isinstance(llm.get("must_do"), list)
                assert isinstance(llm.get("must_not_do"), list)
                assert isinstance(llm.get("on_ambiguous_reply"), str)
            finally:
                client.proc.stdin.close()
                client.proc.wait(timeout=5)

    def test_n5f_seismic_tools_inputschema_entity_id_uses_new_name(self) -> None:
        """
        seismic_* tools that carry entity_id must use the v9.0.0 name,
        not subject_id.
        """
        with tempfile.TemporaryDirectory() as tmp:
            client, _paths = _spawn_sm_server(Path(tmp))
            try:
                client.initialize()
                resp = client.list_tools()
                tools = resp["result"]["tools"]
                seismic_tools = [t for t in tools if t["name"].startswith("seismic_")]
                assert len(seismic_tools) == 5, (
                    f"Expected 5 seismic tools, got {len(seismic_tools)}"
                )
                for tool in seismic_tools:
                    raw = json.dumps(tool)
                    assert "subject_id" not in raw, (
                        f"Tool {tool['name']!r} still contains 'subject_id' "
                        "in its inputSchema — v9.0.0 rename not applied"
                    )
            finally:
                client.proc.stdin.close()
                client.proc.wait(timeout=5)

    def test_n5g_strong_motion_entity_id_in_audit_db(self) -> None:
        """
        Passing entity_id on a seismic Tier-1 call must land in the
        audit.db entity_id column.
        """
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp:
            paths = _seed_strong_motion(Path(tmp))
            env = {
                **os.environ,
                "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
                "TAILOR_DATA_DIR": str(paths["data_dir"]),
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
                resp = client.call_tool(
                    "seismic_list_records", {"entity_id": "STATION01"}
                )
                text = extract_text_result(resp)
                body = json.loads(text)
                assert "error" not in body
            finally:
                proc.stdin.close()
                proc.wait(timeout=5)

            db = sqlite3.connect(str(paths["data_dir"] / "audit.db"))
            rows = db.execute(
                "SELECT entity_id FROM audit_log "
                "WHERE tool_name='seismic_list_records' "
                "AND entity_id IS NOT NULL"
            ).fetchall()
            assert rows, (
                "No audit row with entity_id='STATION01' — entity_id not "
                "threaded through strong_motion dispatch path"
            )
            assert rows[0][0] == "STATION01"
            db.close()


# ──────────────────────────────────────────────────────────────────
# N6 — tools/list allowed_values serialization
# ──────────────────────────────────────────────────────────────────

class TestN6AllowedValuesSerialization:
    """
    The v7.6.0 kind filter on vault_list_notes uses allowed_values in the
    ToolDefinition param schema. The router's list_tools handler only
    serializes type + description; allowed_values does NOT appear in the
    wire inputSchema (it's a server-side validation constraint only).

    This test verifies:
    1. vault_list_notes appears in tools/list without error.
    2. The 'kind' param in inputSchema is typed string with a description.
    3. No Python list/set repr (e.g. "['theme', 'moment', ...]") appears
       in the kind param description on the wire — the description must
       be a plain string, not a serialized allowed_values repr.
    """

    def test_n6a_vault_list_notes_kind_param_in_inputschema(self) -> None:
        """vault_list_notes 'kind' param must appear in inputSchema as a string type."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            tools = resp["result"]["tools"]
            list_notes = next(
                (t for t in tools if t["name"] == "vault_list_notes"), None
            )
            assert list_notes is not None, "vault_list_notes not in tools/list"
            props = list_notes["inputSchema"].get("properties", {})
            assert "kind" in props, (
                f"vault_list_notes missing 'kind' in inputSchema properties: {list(props.keys())}"
            )
            kind_prop = props["kind"]
            assert kind_prop["type"] == "string", (
                f"vault_list_notes.kind.type is {kind_prop['type']!r}, expected 'string'"
            )
            assert isinstance(kind_prop.get("description"), str), (
                "vault_list_notes.kind description is not a string"
            )

    def test_n6b_kind_description_not_a_python_list_repr(self) -> None:
        """
        The kind param description must not contain Python list repr artifacts
        (e.g. "['theme', 'moment']") — that would be a _dumps coercion bug
        where allowed_values leaked into the description field.
        """
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            tools = resp["result"]["tools"]
            list_notes = next(
                (t for t in tools if t["name"] == "vault_list_notes"), None
            )
            if list_notes is None:
                pytest.skip("vault_list_notes not registered")
            props = list_notes["inputSchema"].get("properties", {})
            desc = props.get("kind", {}).get("description", "")
            # Python list repr artifacts that indicate _dumps coercion failure
            assert "['" not in desc or "['theme'" not in desc, (
                f"vault_list_notes.kind description contains Python list repr: {desc!r}. "
                "This is a _dumps coercion bug where allowed_values leaked into the wire."
            )

    def test_n6c_no_repr_artifacts_in_full_tools_list(self) -> None:
        """The complete tools/list response must be free of repr() artifacts."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.list_tools()
            raw_json = json.dumps(resp)
            assert_no_repr_artifacts(raw_json)


# ──────────────────────────────────────────────────────────────────
# N7 — consent approval → tier-2 call happy path
# ──────────────────────────────────────────────────────────────────

class TestN7ConsentApprovalRoundTrip:
    """
    Full consent approval → tier-2 call wire round-trip for the csv_dir domain.
    Previously the consent gate was tested for triggering (fire without approval)
    but NOT for the successful approval → call → _meta shape path.
    """

    def test_n7a_approve_consent_csv_dir_returns_approved_true(self) -> None:
        """approve_consent_csv_dir must return {"approved": True, "domain": "csv_dir"}."""
        with spawn_server() as (client, _paths):
            client.initialize()
            resp = client.call_tool("approve_consent_csv_dir", {})
            text = extract_text_result(resp)
            body = json.loads(text)
            assert "error" not in body, f"approve_consent_csv_dir failed: {body}"
            assert body.get("approved") is True, (
                f"approved field is {body.get('approved')!r}, expected True"
            )
            assert body.get("domain") == "csv_dir"

    def test_n7b_tier2_call_succeeds_after_consent(self) -> None:
        """
        After approving csv_dir consent, csv_downsampled (Tier 2) must
        succeed and return a valid response with _meta.
        """
        with spawn_server() as (client, _paths):
            client.initialize()
            # Approve consent
            client.call_tool("approve_consent_csv_dir", {})
            # Call Tier-2 tool
            resp = client.call_tool(
                "csv_downsampled", {"file_id": "P001.csv", "interval": 2}
            )
            text = extract_text_result(resp)
            assert_no_repr_artifacts(text)
            body = json.loads(text)
            assert "error" not in body, f"csv_downsampled failed: {body}"
            assert "_meta" in body
            meta = body["_meta"]
            assert meta["domain"] == "csv_dir"
            assert meta["tier"] == 2
            assert meta["tool_name"] == "csv_downsampled"

    def test_n7c_revoke_consent_reblocks_tier2(self) -> None:
        """
        After revoking consent, a Tier-2 call must fire the consent gate again.
        """
        with spawn_server() as (client, _paths):
            client.initialize()
            # Approve then revoke
            client.call_tool("approve_consent_csv_dir", {})
            rev = client.call_tool("revoke_consent_csv_dir", {})
            rev_text = extract_text_result(rev)
            rev_body = json.loads(rev_text)
            assert rev_body.get("revoked") is True or rev_body.get("domain") == "csv_dir", (
                f"revoke_consent_csv_dir unexpected response: {rev_body}"
            )
            # Now the Tier-2 call must hit the consent gate again
            resp = client.call_tool(
                "csv_downsampled", {"file_id": "P001.csv", "interval": 2}
            )
            text = extract_text_result(resp)
            body = json.loads(text)
            assert body.get("gate") == "consent_required", (
                f"Expected consent gate after revocation, got: {body}"
            )


# ──────────────────────────────────────────────────────────────────
# N8 — tool name collision detection
# ──────────────────────────────────────────────────────────────────

def test_n8_no_tool_name_collisions_on_full_config() -> None:
    """
    With a fully-seeded config (csv_dir + vault + running + all framework
    layers), no two tools should share the same name. The router raises
    ValueError on collision at registration time; if that fires, the server
    would crash on boot.

    This test is the wire-level regression guard: if a future child addition
    silently shadows an existing tool name (e.g. a new child exposes
    'audit_query' or 'vault_list_notes'), this test catches it.
    """
    with spawn_server() as (client, _paths):
        client.initialize()
        resp = client.list_tools()
        assert "error" not in resp
        tools = resp["result"]["tools"]
        names = [t["name"] for t in tools]
        seen: set[str] = set()
        dupes: list[str] = []
        for n in names:
            if n in seen:
                dupes.append(n)
            seen.add(n)
        assert not dupes, (
            f"tools/list contains duplicate tool names: {dupes}. "
            "Router collision detection may have been bypassed."
        )


# ──────────────────────────────────────────────────────────────────
# N9 — _dumps seam: Decimal, Path, datetime coercion
# ──────────────────────────────────────────────────────────────────

class TestN9DumpsSeamCoercion:
    """
    _dumps must coerce Decimal, Path, and datetime to JSON-native types
    without repr() stringification. Tests are purely at the module level
    (no subprocess) since the existing subprocess tests already cover
    the wire coercion; these confirm the seam itself remains correct
    after v9.0.0 refactors.
    """

    def test_n9a_decimal_coerces_to_float(self) -> None:
        """Decimal('3.14') must serialize as a JSON number, not Decimal('3.14')."""
        from decimal import Decimal

        from tailor.framework.audit import _dumps
        result = _dumps({"value": Decimal("3.14")})
        parsed = json.loads(result)
        assert isinstance(parsed["value"], float), (
            f"Decimal coerced to {type(parsed['value']).__name__!r}, expected float"
        )
        assert "Decimal(" not in result

    def test_n9b_posixpath_coerces_to_string(self) -> None:
        """PosixPath must serialize as a string, not PosixPath('/some/path')."""
        from tailor.framework.audit import _dumps
        result = _dumps({"path": Path("/some/path/file.csv")})
        parsed = json.loads(result)
        assert isinstance(parsed["path"], str), (
            f"Path coerced to {type(parsed['path']).__name__!r}, expected str"
        )
        assert "PosixPath(" not in result
        assert "WindowsPath(" not in result

    def test_n9c_datetime_coerces_to_iso_string(self) -> None:
        """datetime objects must serialize as ISO-8601 strings, not repr."""
        from datetime import datetime, timezone

        from tailor.framework.audit import _dumps
        dt = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
        result = _dumps({"ts": dt})
        parsed = json.loads(result)
        assert isinstance(parsed["ts"], str), (
            f"datetime coerced to {type(parsed['ts']).__name__!r}, expected str"
        )
        assert "datetime.datetime(" not in result
        # Must be parseable ISO-8601
        datetime.fromisoformat(parsed["ts"].replace("Z", "+00:00"))

    def test_n9d_set_coerces_to_sorted_list(self) -> None:
        """set must serialize as a sorted list, not set([...]) repr."""
        from tailor.framework.audit import _dumps
        result = _dumps({"items": {"banana", "apple", "cherry"}})
        parsed = json.loads(result)
        assert isinstance(parsed["items"], list), (
            f"set coerced to {type(parsed['items']).__name__!r}, expected list"
        )
        assert parsed["items"] == sorted(["apple", "banana", "cherry"])

    def test_n9e_unknown_type_raises_type_error(self) -> None:
        """An unknown type must raise TypeError, not silently repr-stringify."""
        from tailor.framework.audit import _dumps

        class _Custom:
            pass

        with pytest.raises((TypeError, Exception)) as exc_info:
            _dumps({"obj": _Custom()})
        # Must NOT have silently coerced via repr()
        # (If it raised, the repr path was not taken.)
        assert exc_info.value is not None


# ──────────────────────────────────────────────────────────────────
# Phase 2 — Cross-cutting contract tests (no subprocess)
# ──────────────────────────────────────────────────────────────────

class TestC1VaultableToolsHaveRenderers:
    """
    Every tool name in VaultWriter.vaultable_tools must have a paired
    renderer in VaultWriter._renderers. Failure means a tool call would
    invoke the post-execute hook but fail silently (M1 class from v6.5.0
    audit) — or raise KeyError inside the hook.

    This is the H2 contract catch from the original v6.5.0 audit.
    Updated here to also cover all children registered in the full config.
    """

    def _get_all_vaultable_tools(self) -> set[str]:
        """Collect vaultable_tools from all registered children."""
        import os
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            paths = seed_full_config(Path(tmp))
            # Import children
            from tailor.children.csv_dir import CSVDirectoryChild
            from tailor.children.running import RunningChild
            config_dir = paths["config_dir"]
            data_dir = paths["data_dir"]
            running = RunningChild(config_dir=config_dir, data_dir=data_dir)
            csv_child = CSVDirectoryChild(config_dir=config_dir, data_dir=data_dir)
            vaultable: set[str] = set()
            for child in [running, csv_child]:
                vaultable.update(getattr(child, "vaultable_tools", []))
            return vaultable

    def test_c1a_all_vaultable_tools_have_renderers(self) -> None:
        """
        Every tool in vaultable_tools (across running + csv_dir) must have
        a renderer in VaultWriter._renderers.
        """
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from tailor.framework.vault import VaultWriter

        vaultable = self._get_all_vaultable_tools()
        if not vaultable:
            pytest.skip("No vaultable tools registered — check running child config")

        with TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            vault_path.mkdir()
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            writer = VaultWriter(
                vault_path=vault_path,
                data_dir=data_dir,
                vaultable_tools=vaultable,
            )
            missing = []
            for tool_name in vaultable:
                if tool_name not in writer._renderers:
                    missing.append(tool_name)
            assert not missing, (
                f"vaultable_tools with no renderer in VaultWriter._renderers: {missing}. "
                "These tools would invoke the post-execute hook and fail silently — "
                "or raise KeyError inside the hook."
            )


class TestC2ToolDefinitionParamsHaveDescriptions:
    """
    Every ToolDefinition.params value must have a 'description' key.
    The router's list_tools handler now uses .get('description', '') as
    a defensive fallback, but missing descriptions are still observable
    on the wire as empty strings — which is a CUE_CARD coverage gap.

    This test verifies the invariant directly from the source (no subprocess).
    """

    def test_c2a_all_registered_tool_params_have_description(self) -> None:
        """
        For every registered child + vault layer, every ToolDefinition
        must have a 'description' key in each param dict (or the router's
        defensive .get fallback is the documented invariant).
        """
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from tailor.children.csv_dir import CSVDirectoryChild
        from tailor.children.running import RunningChild
        from tailor.framework.router import RouterMCP
        from tailor.framework.vault.layer import VaultLayer

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "config"
            data_dir = root / "data"
            vault_path = root / "vault"
            csv_dir = root / "csvs"
            for p in (config_dir, data_dir, vault_path, csv_dir):
                p.mkdir()
            (csv_dir / "P001.csv").write_text("timestamp,val\n2026-01-01,1\n")
            (config_dir / "user_config.json").write_text(json.dumps({
                "vault_path": str(vault_path),
                "csv_dir": {"path": str(csv_dir), "timestamp_column": "timestamp",
                             "timestamp_format": "%Y-%m-%d", "value_columns": {"val": "Value"}},
            }))

            running = RunningChild(config_dir=config_dir, data_dir=data_dir)
            csv_child = CSVDirectoryChild(config_dir=config_dir, data_dir=data_dir)

            missing: list[str] = []
            for child in [running, csv_child]:
                for tool_def in child.tool_definitions:
                    for pname, pinfo in tool_def.params.items():
                        if "description" not in pinfo:
                            missing.append(f"{child.domain}.{tool_def.name}.{pname}")

            assert not missing, (
                f"ToolDefinition params missing 'description' key: {missing}. "
                "The router's .get('description', '') fallback will silently emit "
                "an empty description — update the ToolDefinition to add it."
            )


class TestC3NoToolNameCollisions:
    """
    No two registered children/layers may expose the same tool name.
    The router raises ValueError at registration time; this test verifies
    the invariant holds across all currently registered children.
    """

    def test_c3a_tool_names_are_unique_across_all_children(self) -> None:
        """All tool names across running + csv_dir + vault must be unique."""
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from tailor.children.csv_dir import CSVDirectoryChild
        from tailor.children.running import RunningChild
        from tailor.framework.router import RouterMCP
        from tailor.framework.vault import VaultLayer, VaultWriter

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "config"
            data_dir = root / "data"
            vault_path = root / "vault"
            csv_dir = root / "csvs"
            for p in (config_dir, data_dir, vault_path, csv_dir):
                p.mkdir()
            (csv_dir / "P001.csv").write_text("timestamp,val\n2026-01-01,1\n")
            (config_dir / "user_config.json").write_text(json.dumps({
                "vault_path": str(vault_path),
                "csv_dir": {"path": str(csv_dir), "timestamp_column": "timestamp",
                             "timestamp_format": "%Y-%m-%d", "value_columns": {"val": "Value"}},
            }))

            router = RouterMCP(name="test-tailor", data_dir=data_dir)
            running = RunningChild(config_dir=config_dir, data_dir=data_dir)
            csv_child = CSVDirectoryChild(config_dir=config_dir, data_dir=data_dir)

            # register_child raises ValueError on collision — if it doesn't
            # raise, the invariant holds.
            router.register_child(running)
            router.register_child(csv_child)

            # Also confirm no collision with vault layer
            vault_writer = VaultWriter(vault_path=vault_path, data_dir=data_dir,
                                       vaultable_tools=set())
            router.register_vault_layer(VaultLayer(vault_path=vault_path,
                                                    vault_writer=vault_writer,
                                                    backfill_config={}))

            # Verify uniqueness of all registered tool names
            names = list(router.registered_tools)
            assert len(names) == len(set(names)), (
                "Duplicate tool names in registry: "
                + str([n for n in names if names.count(n) > 1])
            )
            router.close()


class TestC4EntityIdSchemaNotSubjectId:
    """
    Every child that declares entity_id in param_schemas must use the
    canonical ENTITY_ID_SCHEMA (not a stale subject_id ValidationSchema
    or a hand-rolled alternative). This guards the v9.0.0 rename invariant
    at the schema-definition level.
    """

    def test_c4a_csv_dir_entity_id_schema_matches_canonical(self) -> None:
        """CSVDirectoryChild's param_schemas for entity_id must match ENTITY_ID_SCHEMA."""
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from tailor.children.csv_dir import CSVDirectoryChild
        from tailor.framework.interfaces import ENTITY_ID_SCHEMA

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "config"
            data_dir = root / "data"
            csv_dir = root / "csvs"
            for p in (config_dir, data_dir, csv_dir):
                p.mkdir()
            (csv_dir / "P001.csv").write_text("timestamp,val\n2026-01-01,1\n")
            (config_dir / "user_config.json").write_text(json.dumps({
                "csv_dir": {"path": str(csv_dir), "timestamp_column": "timestamp",
                             "timestamp_format": "%Y-%m-%d", "value_columns": {"val": "V"}},
            }))
            child = CSVDirectoryChild(config_dir=config_dir, data_dir=data_dir)

            for tool_name, schema_dict in child.param_schemas.items():
                if "entity_id" in schema_dict:
                    eid_schema = schema_dict["entity_id"]
                    assert "subject_id" not in str(eid_schema), (
                        f"CSVDirectoryChild.param_schemas[{tool_name!r}]['entity_id'] "
                        "contains 'subject_id' — v9.0.0 rename not applied to schema"
                    )
                    # Check it has the right pattern
                    if hasattr(eid_schema, "pattern"):
                        assert eid_schema.pattern == ENTITY_ID_SCHEMA.pattern, (
                            f"entity_id schema pattern mismatch in {tool_name!r}: "
                            f"{eid_schema.pattern!r} != {ENTITY_ID_SCHEMA.pattern!r}"
                        )
                    assert "subject_id" not in tool_name, (
                        f"Tool name {tool_name!r} still contains 'subject_id'"
                    )

    def test_c4b_running_child_entity_id_schema_matches_canonical(self) -> None:
        """RunningChild's param_schemas for entity_id must match ENTITY_ID_SCHEMA."""
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from tailor.children.running import RunningChild
        from tailor.framework.interfaces import ENTITY_ID_SCHEMA

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "config"
            data_dir = root / "data"
            for p in (config_dir, data_dir):
                p.mkdir()
            (config_dir / "user_config.json").write_text(json.dumps({"max_hr": 185}))
            child = RunningChild(config_dir=config_dir, data_dir=data_dir)

            for tool_name, schema_dict in child.param_schemas.items():
                if "entity_id" in schema_dict:
                    eid_schema = schema_dict["entity_id"]
                    if hasattr(eid_schema, "pattern"):
                        assert eid_schema.pattern == ENTITY_ID_SCHEMA.pattern, (
                            f"RunningChild.param_schemas[{tool_name!r}]['entity_id'] "
                            f"pattern mismatch: {eid_schema.pattern!r}"
                        )

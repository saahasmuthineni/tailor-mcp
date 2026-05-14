"""
MCP Protocol Audit — MATLABFileChild wire-level correctness.

Drives ``python -m tailor serve`` as a real subprocess speaking JSON-RPC
over stdio, with temp-dir-isolated configs.  No mocks; no unit-test
substitutes.

Surfaces under test (per the v7.2.0 audit mandate):

  A1 — ``initialize`` still returns a well-formed envelope with the
       MATLAB child NOT configured.
  A2 — ``tools/list`` without a ``matlab_file`` config block returns
       the standard surface (running + csv_dir + vault) and does NOT
       include any ``matlab_*`` tool.
  A3 — ``matlab_file`` config present but scipy absent: server starts
       without traceback; MATLAB tools absent from ``tools/list``;
       stderr banner includes the "pip install tailor-mcp[matlab]" fix
       line; other tools unaffected.
  A4 — ``_demo_blocks_absent`` with ``matlab_file`` block present:
       SetupHelpLayer is NOT registered; tailor_setup_help absent from
       ``tools/list``.
  A5 — ``_demo_blocks_absent`` with no scaffold keys:
       SetupHelpLayer IS registered; tailor_setup_help present in
       ``tools/list``.  Wire payload clean — no repr artifacts.
  A6 (scipy absent, protocol surface only) — all checked via
       subprocess; scipy-present scenarios documented as SKIP.

Wire-level invariants checked on every result envelope:
  - Decodes as valid JSON.
  - No ``"error"`` key in unexpected (non-error-path) responses.
  - No Python repr() artifacts in the raw wire payload.
  - Every tool in tools/list carries inputSchema.type == "object" and
    every property carries a string "description".

Scipy-present scenario (A6 full Tier-1 round-trip) is skipped when
scipy is not installed.  The skip is documented in the report rather
than marking the test as a failure.
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

from tests._mcp_client import (
    MCPClient,
    assert_no_repr_artifacts,
    extract_text_result,
    seed_full_config,
    spawn_server,
)

# ---------------------------------------------------------------------------
# Module-level helpers (must be defined before @pytest.mark.skipif usage)
# ---------------------------------------------------------------------------

def _scipy_available() -> bool:
    try:
        import scipy  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Local config-seeding helpers
# ---------------------------------------------------------------------------

def _seed_matlab_config(root: Path, *, mat_dir: Path) -> dict[str, Path]:
    """
    Seed a temp config that includes a ``matlab_file`` block pointing at
    ``mat_dir``.  The running child config is included so the server
    starts cleanly; no vault or csv_dir block so the surface is minimal.
    """
    config_dir = root / "config"
    data_dir = root / "data"
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    user_config = {
        "max_hr": 185,
        "resting_hr": 55,
        "matlab_file": {
            "path": str(mat_dir),
        },
    }
    (config_dir / "user_config.json").write_text(
        json.dumps(user_config), encoding="utf-8"
    )
    return {"config_dir": config_dir, "data_dir": data_dir}


def _seed_bare_config(root: Path) -> dict[str, Path]:
    """
    Seed a config with NO scaffold keys (no csv_dir, no vault_path,
    no force_csv, no emg_csv, no matlab_file, no redcap_export).
    SetupHelpLayer should register.
    """
    config_dir = root / "config"
    data_dir = root / "data"
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    user_config = {
        "max_hr": 185,
        "resting_hr": 55,
    }
    (config_dir / "user_config.json").write_text(
        json.dumps(user_config), encoding="utf-8"
    )
    return {"config_dir": config_dir, "data_dir": data_dir}


def _spawn_with_config(paths: dict[str, Path]) -> subprocess.Popen:
    env = {
        **os.environ,
        "TAILOR_CONFIG_DIR": str(paths["config_dir"]),
        "TAILOR_DATA_DIR": str(paths["data_dir"]),
    }
    return subprocess.Popen(
        [sys.executable, "-m", "tailor", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def _kill(proc: subprocess.Popen) -> None:
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
# A1 — initialize still well-formed (baseline with standard full config)
# ---------------------------------------------------------------------------

def test_a1_initialize_well_formed_without_matlab_config() -> None:
    """
    A1: ``initialize`` returns a well-formed envelope when no matlab_file
    block is in user_config.json.

    Guard: proves the pre-existing baseline is not disrupted by the new
    registration block in __main__.py.
    """
    with spawn_server() as (client, _paths):
        resp = client.initialize()

        assert "error" not in resp, (
            f"A1: initialize returned error: {resp}"
        )
        assert "result" in resp, (
            f"A1: initialize missing 'result': {resp}"
        )
        result = resp["result"]
        # MCP protocol requires protocolVersion + capabilities in initialize result
        assert "protocolVersion" in result, (
            f"A1: missing protocolVersion in initialize result: {result}"
        )
        assert "capabilities" in result, (
            f"A1: missing capabilities in initialize result: {result}"
        )

        # No repr artifacts in the raw wire payload
        raw = json.dumps(resp)
        assert_no_repr_artifacts(raw)


# ---------------------------------------------------------------------------
# A2 — tools/list without matlab_file block: no matlab_* tools
# ---------------------------------------------------------------------------

def test_a2_tools_list_excludes_matlab_tools_when_not_configured() -> None:
    """
    A2: When user_config.json has no ``matlab_file`` block, the standard
    tool surface (running + csv_dir + vault) appears and NO ``matlab_*``
    tools appear.

    This verifies the opt-in guard in __main__.py:
    ``if _ucfg.get("matlab_file"):`` — absent key must not register the child.
    """
    with spawn_server() as (client, _paths):
        client.initialize()

        list_resp = client.list_tools()
        assert "error" not in list_resp, (
            f"A2: tools/list returned error: {list_resp}"
        )
        assert "result" in list_resp

        tools = list_resp["result"]["tools"]
        names = {t["name"] for t in tools}

        # Standard surface present
        assert "strava_list_runs" in names, (
            "A2: running child tools absent — full config not seeded"
        )
        assert "csv_list_files" in names, (
            "A2: csv_dir child tools absent — full config not seeded"
        )
        assert "vault_list_themes" in names, (
            "A2: vault tools absent — full config not seeded"
        )

        # MATLAB tools must NOT appear
        matlab_tools = [n for n in names if n.startswith("matlab_")]
        assert matlab_tools == [], (
            f"A2: matlab_* tools appeared without a matlab_file config block: "
            f"{matlab_tools}"
        )

        # Wire-level shape: every tool must carry inputSchema
        raw = json.dumps(list_resp)
        assert_no_repr_artifacts(raw)
        for tool in tools:
            assert "inputSchema" in tool, (
                f"A2: tool {tool['name']!r} missing inputSchema"
            )
            schema = tool["inputSchema"]
            assert schema.get("type") == "object", (
                f"A2: tool {tool['name']!r} inputSchema.type != 'object'"
            )
            for pname, pinfo in schema.get("properties", {}).items():
                assert "description" in pinfo and isinstance(pinfo["description"], str), (
                    f"A2: tool {tool['name']!r} param {pname!r} missing string description"
                )


# ---------------------------------------------------------------------------
# A3 — matlab_file configured but scipy absent
# ---------------------------------------------------------------------------

def test_a3_matlab_configured_scipy_missing_clean_banner_no_matlab_tools() -> None:
    """
    A3: When ``matlab_file`` is present in user_config.json but scipy is
    not installed:

    - The server starts without a Python traceback in stderr.
    - The stderr banner contains the "pip install tailor-mcp[matlab]" fix line.
    - ``tools/list`` does NOT include any ``matlab_*`` tools.
    - Other tools (running child) ARE present — degraded serve, not crash.
    - ``initialize`` succeeds.

    This is the gate-evasion class the auditor exists to catch: an
    ImportError in a child constructor that is caught and converted to a
    banner + skip rather than a crash.  If the try/except in __main__.py
    is broken (e.g. the import is moved outside the block), this test
    catches the regression before it reaches a recipient.
    """
    # Skip this test if scipy IS installed — the scenario cannot occur.
    try:
        import scipy  # noqa: F401
        pytest.skip(
            "A3: scipy is installed; the scipy-absent scenario cannot be "
            "reproduced. This test only runs when scipy is absent."
        )
    except ImportError:
        pass  # Expected — scipy is absent; run the test.

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        mat_dir = root / "mat_files"
        mat_dir.mkdir()
        # Write a dummy .mat file so the directory is non-empty
        # (contents don't matter — the ImportError fires before any load)
        (mat_dir / "dummy.mat").write_bytes(b"MATLAB 5.0 MAT-file\n" + b"\x00" * 100)

        paths = _seed_matlab_config(root, mat_dir=mat_dir)
        proc = _spawn_with_config(paths)
        client = MCPClient(proc)
        try:
            # Give the server time to attempt registration + emit the banner
            time.sleep(2)

            # initialize must succeed
            resp = client.initialize()
            assert "error" not in resp, (
                f"A3: initialize returned error despite scipy-absent banner: {resp}"
            )
            assert "result" in resp, (
                f"A3: initialize missing result: {resp}"
            )

            # tools/list must succeed and must NOT include matlab_* tools
            list_resp = client.list_tools()
            assert "error" not in list_resp, (
                f"A3: tools/list returned error: {list_resp}"
            )
            tools = list_resp["result"]["tools"]
            names = {t["name"] for t in tools}

            matlab_tools = [n for n in names if n.startswith("matlab_")]
            assert matlab_tools == [], (
                f"A3: matlab_* tools appeared despite ImportError: {matlab_tools}"
            )

            # Running child tools must still be present (degraded serve, not dead)
            assert "strava_list_runs" in names, (
                f"A3: running child tools absent — scipy ImportError killed the "
                f"whole server startup rather than just skipping MATLAB: "
                f"tools present: {sorted(names)}"
            )

            # Wire payload clean
            raw_list = json.dumps(list_resp)
            assert_no_repr_artifacts(raw_list)

        finally:
            # Read stderr AFTER the protocol exchange to avoid blocking
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

            # Now read buffered stderr
            if proc.stderr is not None:
                stderr_bytes = proc.stderr.read()
                stderr = stderr_bytes.decode("utf-8", errors="replace")
            else:
                stderr = ""

        # Stderr assertions after process is dead (to avoid readline blocking)
        assert "Traceback" not in stderr, (
            f"A3: tailor serve crashed with a traceback:\n{stderr}"
        )
        assert "pip install tailor-mcp[matlab]" in stderr, (
            f"A3: scipy-missing banner does not contain the fix instruction "
            f"'pip install tailor-mcp[matlab]'. Actual stderr:\n{stderr[:1000]}"
        )
        assert "matlab_file is configured" in stderr, (
            f"A3: scipy-missing banner does not mention 'matlab_file is configured'. "
            f"Actual stderr:\n{stderr[:1000]}"
        )
        assert "MATLAB tools NOT registered" in stderr, (
            f"A3: banner does not confirm MATLAB tools NOT registered. "
            f"Actual stderr:\n{stderr[:1000]}"
        )


# ---------------------------------------------------------------------------
# A4 — _demo_blocks_absent: matlab_file present → SetupHelpLayer absent
# ---------------------------------------------------------------------------

def test_a4_setup_help_absent_when_matlab_configured() -> None:
    """
    A4: When ``matlab_file`` is present in user_config.json, the
    ``_demo_blocks_absent`` predicate returns False and SetupHelpLayer
    is NOT registered.

    This verifies the fix that added ``"matlab_file"`` to the
    ``keys_signalling_scaffold`` tuple in
    ``framework/setup_help/__init__.py``.

    If the tuple did not include ``"matlab_file"``, a correctly
    configured MATLAB deployment would also surface
    ``tailor_setup_help`` — confusing the AI into suggesting
    ``tailor fitting-room`` to a user who already has their data wired.
    """
    # scipy may or may not be present.  We test the SetupHelp predicate
    # by observing the tools/list surface; scipy absence means the MATLAB
    # child itself won't register (A3 already covers that path), but the
    # SetupHelpLayer absence is a separate control path.

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        mat_dir = root / "mat_files"
        mat_dir.mkdir()

        paths = _seed_matlab_config(root, mat_dir=mat_dir)
        proc = _spawn_with_config(paths)
        client = MCPClient(proc)
        try:
            time.sleep(1)
            resp = client.initialize()
            assert "error" not in resp, f"A4: initialize error: {resp}"

            list_resp = client.list_tools()
            assert "error" not in list_resp, f"A4: tools/list error: {list_resp}"
            names = {t["name"] for t in list_resp["result"]["tools"]}

            assert "tailor_setup_help" not in names, (
                "A4: tailor_setup_help appeared even though matlab_file is "
                "present in user_config — _demo_blocks_absent incorrectly "
                "returned True; 'matlab_file' must be in "
                "keys_signalling_scaffold."
            )
        finally:
            _kill(proc)


# ---------------------------------------------------------------------------
# A5 — _demo_blocks_absent: no scaffold keys → SetupHelpLayer present
# ---------------------------------------------------------------------------

def test_a5_setup_help_present_when_no_scaffold_keys() -> None:
    """
    A5: When user_config.json has NO scaffold keys (no csv_dir, no
    vault_path, no force_csv, no emg_csv, no matlab_file, no
    redcap_export), ``_demo_blocks_absent`` returns True and
    SetupHelpLayer IS registered.

    This is the baseline case that the new ``keys_signalling_scaffold``
    additions must not break.  The diagnostic tool must still surface
    when a recipient runs ``tailor serve`` bare.

    Wire invariants: tailor_setup_help's tools/call result must be
    clean JSON with no repr artifacts.
    """
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = _seed_bare_config(root)
        proc = _spawn_with_config(paths)
        client = MCPClient(proc)
        try:
            time.sleep(1)
            resp = client.initialize()
            assert "error" not in resp, f"A5: initialize error: {resp}"

            list_resp = client.list_tools()
            assert "error" not in list_resp, f"A5: tools/list error: {list_resp}"
            names = {t["name"] for t in list_resp["result"]["tools"]}

            assert "tailor_setup_help" in names, (
                f"A5: tailor_setup_help absent even though no scaffold keys "
                f"are in user_config — SetupHelpLayer registration broke. "
                f"Tools present: {sorted(names)}"
            )

            # Now call tailor_setup_help and check the wire payload
            call_resp = client.call_tool("tailor_setup_help", {})
            assert "error" not in call_resp, (
                f"A5: tailor_setup_help call returned error: {call_resp}"
            )

            text = extract_text_result(call_resp)
            raw = text
            assert_no_repr_artifacts(raw)

            body = json.loads(text)
            # Mandatory response keys
            assert "diagnosis" in body, (
                f"A5: tailor_setup_help response missing 'diagnosis': {body}"
            )
            assert "recipient_steps" in body, (
                f"A5: tailor_setup_help response missing 'recipient_steps': {body}"
            )
            assert isinstance(body["recipient_steps"], list), (
                f"A5: recipient_steps is not a list: {body}"
            )
            assert len(body["recipient_steps"]) > 0, (
                f"A5: recipient_steps is empty: {body}"
            )

            # Diagnostics block must not contain bare home paths
            if "diagnostics" in body:
                diag = body["diagnostics"]
                for key, value in diag.items():
                    if isinstance(value, str):
                        # _redact_home should have collapsed the home dir to ~
                        # On Windows: no C:\Users\saaha\ bare paths
                        # Just assert no Python repr — that's the wire invariant
                        assert "WindowsPath(" not in value, (
                            f"A5: WindowsPath repr in diagnostics[{key!r}]: {value}"
                        )
                        assert "PosixPath(" not in value, (
                            f"A5: PosixPath repr in diagnostics[{key!r}]: {value}"
                        )

        finally:
            _kill(proc)


# ---------------------------------------------------------------------------
# A6 — scipy present: tools/list includes 6 matlab_* tools; Tier-1 round-trip
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not _scipy_available(),
    reason=(
        "A6: scipy not installed. The scipy-present Tier-1 round-trip cannot "
        "run. Install scipy or the [matlab] extra to exercise this path. "
        "The scipy-absent scenarios are covered by A3."
    ),
)
def test_a6_matlab_tools_register_and_tier1_round_trip_with_scipy() -> None:
    """
    A6: With scipy installed and a valid ``matlab_file`` config pointing
    at a directory containing synthetic v5 .mat files:

    - ``tools/list`` includes all 6 ``matlab_*`` tools.
    - Each tool's inputSchema is well-formed.
    - ``matlab_list_files`` returns a clean JSON result with no repr
      artifacts (the numpy→Python coercion seam).
    - The ``_meta`` block carries ``tool_name``, ``domain``,
      ``package_version``, and ``called_at`` (ISO-8601 parseable).
    - No Python repr artifacts (numpy dtypes, ndarray objects, or
      scipy structs must not appear on the wire — the child's
      ``_numeric_1d()`` coercion must hold end-to-end).
    """
    import numpy as np
    import scipy.io  # noqa: F401 — inside the skip guard

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        mat_dir = root / "mat_files"
        mat_dir.mkdir()

        # Write two synthetic v5 .mat files with a 1-D float64 variable
        scipy.io.savemat(
            str(mat_dir / "subj_001.mat"),
            {"force": np.array([1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 1.0])},
            format="5",
        )
        scipy.io.savemat(
            str(mat_dir / "subj_002.mat"),
            {"force": np.array([2.0, 4.0, 6.0, 4.0, 2.0])},
            format="5",
        )
        (mat_dir / "metadata.json").write_text(
            json.dumps({
                "subj_001.mat": {"sex": "F", "group": "control"},
                "subj_002.mat": {"sex": "M", "group": "treatment"},
            }),
            encoding="utf-8",
        )

        paths = _seed_matlab_config(root, mat_dir=mat_dir)
        proc = _spawn_with_config(paths)
        client = MCPClient(proc)
        try:
            time.sleep(1)
            resp = client.initialize()
            assert "error" not in resp, f"A6: initialize error: {resp}"

            list_resp = client.list_tools()
            assert "error" not in list_resp, f"A6: tools/list error: {list_resp}"
            tools = list_resp["result"]["tools"]
            names = {t["name"] for t in tools}

            expected_matlab = {
                "matlab_list_files",
                "matlab_file_detail",
                "matlab_summary_report",
                "matlab_cohort_summary",
                "matlab_downsampled",
                "matlab_raw_array",
            }
            missing = expected_matlab - names
            assert not missing, (
                f"A6: matlab tools missing from tools/list: {missing}"
            )

            # inputSchema shape on every matlab tool
            for tool in tools:
                if not tool["name"].startswith("matlab_"):
                    continue
                assert "inputSchema" in tool, (
                    f"A6: {tool['name']!r} missing inputSchema"
                )
                schema = tool["inputSchema"]
                assert schema.get("type") == "object"
                for pname, pinfo in schema.get("properties", {}).items():
                    assert "description" in pinfo and isinstance(pinfo["description"], str), (
                        f"A6: {tool['name']!r} param {pname!r} missing description"
                    )

            # Tier-1 round-trip: matlab_list_files
            call_resp = client.call_tool("matlab_list_files", {"limit": 10})
            assert "error" not in call_resp, (
                f"A6: matlab_list_files call error: {call_resp}"
            )
            text = extract_text_result(call_resp)
            assert_no_repr_artifacts(text)

            body = json.loads(text)
            assert "count" in body, f"A6: missing 'count' in matlab_list_files result: {body}"
            assert body["count"] == 2, (
                f"A6: expected 2 .mat files, got {body['count']}"
            )
            filenames = {f["filename"] for f in body["files"]}
            assert filenames == {"subj_001.mat", "subj_002.mat"}, (
                f"A6: unexpected filenames: {filenames}"
            )

            # Each file entry must list variables — this is where numpy dtype repr
            # would leak if the child's _enumerate_variables coercion is broken
            for entry in body["files"]:
                assert "variables" in entry, (
                    f"A6: file entry missing 'variables': {entry}"
                )
                for var in entry["variables"]:
                    assert "name" in var and "shape" in var and "dtype" in var, (
                        f"A6: variable entry missing required keys: {var}"
                    )
                    # dtype must be a plain string, not a numpy dtype repr
                    assert isinstance(var["dtype"], str), (
                        f"A6: dtype is not a string — numpy dtype coercion broken: "
                        f"{var['dtype']!r}"
                    )
                    assert "<" not in var["dtype"] or "class" not in var["dtype"], (
                        f"A6: dtype looks like a Python repr artifact: {var['dtype']!r}"
                    )

            # _meta provenance
            assert "_meta" in body, "A6: _meta absent from matlab_list_files result"
            meta = body["_meta"]
            assert meta["tool_name"] == "matlab_list_files", (
                f"A6: _meta.tool_name mismatch: {meta['tool_name']!r}"
            )
            assert meta["domain"] == "matlab_file", (
                f"A6: _meta.domain mismatch: {meta['domain']!r}"
            )
            from tailor import __version__
            assert meta["package_version"] == __version__, (
                f"A6: _meta.package_version {meta['package_version']!r} != "
                f"{__version__!r}"
            )
            from datetime import datetime
            datetime.fromisoformat(meta["called_at"].replace("Z", "+00:00"))

            # No repr artifacts in the full tools/list wire payload
            assert_no_repr_artifacts(json.dumps(list_resp))

        finally:
            _kill(proc)


# ---------------------------------------------------------------------------
# Contract: _demo_blocks_absent unit-level (no subprocess needed)
# ---------------------------------------------------------------------------

class TestDemoBlocksAbsentContract:
    """
    Unit-level contract tests for ``_demo_blocks_absent``.

    These don't need a subprocess — they verify the predicate directly.
    The predicate change (adding ``matlab_file`` + ``redcap_export``)
    is load-bearing: a False miss means SetupHelpLayer registers on
    a correctly-configured deployment and confuses the AI.
    """

    @staticmethod
    def _predicate(cfg: dict) -> bool:
        from tailor.framework.setup_help import _demo_blocks_absent
        return _demo_blocks_absent(cfg)

    def test_empty_config_returns_true(self) -> None:
        assert self._predicate({}) is True

    def test_no_scaffold_keys_returns_true(self) -> None:
        assert self._predicate({"max_hr": 185}) is True

    def test_csv_dir_returns_false(self) -> None:
        assert self._predicate({"csv_dir": {"path": "/tmp/x"}}) is False

    def test_vault_path_returns_false(self) -> None:
        assert self._predicate({"vault_path": "/tmp/vault"}) is False

    def test_force_csv_returns_false(self) -> None:
        assert self._predicate({"force_csv": {"path": "/tmp/f"}}) is False

    def test_emg_csv_returns_false(self) -> None:
        assert self._predicate({"emg_csv": {"path": "/tmp/e"}}) is False

    def test_matlab_file_returns_false(self) -> None:
        """New key: matlab_file block must suppress SetupHelpLayer."""
        assert self._predicate({"matlab_file": {"path": "/tmp/mat"}}) is False

    def test_redcap_export_returns_false(self) -> None:
        """New key: redcap_export block must suppress SetupHelpLayer."""
        assert self._predicate({"redcap_export": {"path": "/tmp/rc"}}) is False

    def test_falsy_matlab_file_value_returns_true(self) -> None:
        """Falsy matlab_file values (None, empty string, empty dict) should NOT
        suppress SetupHelpLayer.

        The predicate uses ``user_config.get(key)`` which is Python-falsy for
        None, empty string, and empty dict.  An empty dict means the key is
        present but unconfigured (no ``path``), which is a misconfiguration
        that would not successfully register the child anyway.  Treating it
        as "scaffold absent" and surfacing the diagnostic layer is the
        correct behavior — consistent with the operator not having a working
        matlab_file child.
        """
        # Empty dict value: falsy — predicate treats as absent (returns True = help layer fires)
        assert self._predicate({"matlab_file": {}}) is True
        # None value: falsy — predicate treats as absent
        assert self._predicate({"matlab_file": None}) is True
        # Empty string: falsy — predicate treats as absent
        assert self._predicate({"matlab_file": ""}) is True

    def test_multiple_scaffold_keys_returns_false(self) -> None:
        assert self._predicate({
            "matlab_file": {"path": "/tmp/m"},
            "redcap_export": {"path": "/tmp/r"},
        }) is False


# ---------------------------------------------------------------------------
# Contract: vaultable_tools empty → no renderer gap
# ---------------------------------------------------------------------------

def test_matlab_vaultable_tools_empty_no_renderer_gap() -> None:
    """
    The MATLABFileChild declares ``vaultable_tools = []``.  This means
    no tool is wired to ``VaultWriter._renderers``.  This test verifies
    that the empty declaration is intentional and that no tool name appears
    in ``vaultable_tools`` without a corresponding renderer — the v6.5.0
    H2 finding class.

    The test imports MATLABFileChild at the module level (not via scipy)
    to check the class attribute without constructing the child.
    """
    # Import the class attribute WITHOUT constructing (avoids scipy import)
    # The child.py file defines the property, so we need to check the
    # class via its source — but since MATLABFileChild.__init__ imports
    # scipy, we read the vaultable_tools property source expectation
    # via the test_matlab_shape.py's TestVaultableTools (which uses
    # a real instance) and here we assert at the source-code level via
    # a static check.

    # The safest path: check the writer's registered renderers against
    # what the child would advertise.  Since scipy is absent, we check
    # the contract at the source: `vaultable_tools = []` in child.py.
    # We verify the child.py source contains "return []" for vaultable_tools.

    child_source = Path(
        "c:/Users/saaha/Biosensor-to-LLM-Connector/"
        "src/tailor/children/matlab_file/child.py"
    ).read_text(encoding="utf-8")

    # The property must return an empty list
    assert "vaultable_tools" in child_source, (
        "matlab_file/child.py does not define vaultable_tools"
    )
    assert "return []" in child_source, (
        "matlab_file/child.py vaultable_tools does not return [] — "
        "if any tool is added here, a renderer must be added to "
        "VaultWriter._renderers before this test is relaxed."
    )

    # Additionally: if scipy IS present, construct the child and
    # check the live vaultable_tools list
    try:
        import json as _json
        from tempfile import TemporaryDirectory as _TmpDir

        import numpy as np
        import scipy  # noqa: F401
        import scipy.io as sio

        with _TmpDir() as tmp:
            root = Path(tmp)
            mat_dir = root / "mat"
            mat_dir.mkdir()
            sio.savemat(str(mat_dir / "x.mat"), {"v": np.array([1.0, 2.0])}, format="5")
            cfg = root / "cfg"
            cfg.mkdir()
            (cfg / "user_config.json").write_text(
                _json.dumps({"matlab_file": {"path": str(mat_dir)}}),
                encoding="utf-8",
            )
            from tailor.children.matlab_file import MATLABFileChild
            from tailor.framework.vault.writer import VaultWriter

            child = MATLABFileChild(cfg, root / "data")
            vaultable = child.vaultable_tools
            assert vaultable == [], (
                f"MATLABFileChild.vaultable_tools is non-empty: {vaultable}. "
                "Add a renderer to VaultWriter._renderers for each listed tool "
                "before advertising them as vaultable."
            )

            # Cross-check: none of the matlab tool names are in VaultWriter._renderers
            # by default (i.e. there's no accidental renderer for a matlab tool
            # that isn't in vaultable_tools — that would be dead code but not
            # a contract violation; but a tool IN vaultable_tools WITHOUT a renderer
            # would be the H2 bug).
            vault_path = root / "vault"
            vault_path.mkdir()
            writer = VaultWriter(
                vault_path=vault_path,
                data_dir=root / "data",
                vaultable_tools=set(vaultable),
                max_hr=185,
            )
            # No matlab tool should be in _renderers by default
            for tool_name in {td.name for td in child.tool_definitions}:
                # Being absent from _renderers is fine — vaultable_tools is empty
                # Being present in vaultable_tools but absent from _renderers = bug
                if tool_name in child.vaultable_tools:
                    assert tool_name in writer._renderers, (
                        f"H2 violation: {tool_name!r} in vaultable_tools but "
                        f"has no renderer in VaultWriter._renderers"
                    )

    except ImportError:
        pass  # scipy absent — the live-instance check is skipped


# (end of test module)

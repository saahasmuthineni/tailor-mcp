"""
Subprocess startup smoke tests for ``biosensor-mcp serve``.

The existing CLI smoke test in ci-gate-runner only exercises
``biosensor-mcp --help``, which never reaches the stdio server's
``Server.run()`` call. Real ship-blocker bugs in v6.5.0 surfaced
only when a real MCP client tried to connect:

1. ``router.run()`` was calling ``Server.run(read, write)`` against
   the mcp 1.27.0 API which requires a third
   ``initialization_options`` argument — TypeError on every connect.
2. Two vault tools (``vault_list_moments``, ``vault_capture_moment``)
   shipped with params missing the ``"description"`` key, and the
   router's tools/list handler accessed ``pinfo["description"]``
   unconditionally — KeyError on every ``tools/list`` request.

Neither was caught by pytest, ruff, the security probe, or the CLI
``--help`` smoke. The first surfaced when a real client opened stdio;
the second surfaced when a real client requested tools/list.

These tests close the gate-evasion class by spawning the framework
as a real subprocess, speaking JSON-RPC over stdio, and asserting
the round-trip returns clean responses.

History note (v6.5.0 mcp-protocol-auditor pass): the prior version
of ``test_serve_tools_list_round_trip`` seeded an *empty* config
dir — which means ``cmd_serve`` skipped vault registration and
csv_dir registration entirely, and only the running child's tools
were enumerated. The bug it claimed to regress (vault tools missing
``description``) was not actually exercised by the test. Fixed by
seeding a full config via ``tests/_mcp_client.py::seed_full_config``
so all 44+ tools (running + csv_dir + vault) load on startup.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from tests._mcp_client import seed_full_config, spawn_server


def test_serve_starts_without_traceback() -> None:
    """`biosensor-mcp serve` reaches the stdio read loop and exits
    cleanly when stdin is closed.

    Regression for the v6.5.0 missing-`initialization_options` bug
    (router.py:983 was calling `Server.run(read, write)` against the
    mcp 1.27.0 API which requires a third `initialization_options`
    argument). The TypeError surfaced as `Server disconnected` in
    Claude Desktop while CI showed green.
    """
    with TemporaryDirectory() as tmp:
        # Full config — same shape as the round-trip tests use, so
        # this also catches construction-time errors when vault and
        # csv_dir are wired up. An empty config skips both branches.
        paths = seed_full_config(Path(tmp))

        env = {
            **os.environ,
            "BIOSENSOR_CONFIG_DIR": str(paths["config_dir"]),
            "BIOSENSOR_DATA_DIR": str(paths["data_dir"]),
        }

        proc = subprocess.run(
            [sys.executable, "-m", "biosensor_mcp", "serve"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=env,
            timeout=20,
        )

        stderr = proc.stderr.decode("utf-8", errors="replace")

        assert "Traceback" not in stderr, (
            "biosensor-mcp serve crashed before reaching the read "
            f"loop. stderr:\n{stderr}"
        )
        assert "TypeError" not in stderr, (
            "biosensor-mcp serve hit a TypeError — most likely an "
            f"mcp-SDK signature drift. stderr:\n{stderr}"
        )
        # The router logs an init banner before stdio_server() opens;
        # if that's absent, the framework didn't even reach init.
        assert "Router MCP" in stderr, (
            "biosensor-mcp serve never logged its init banner — the "
            f"framework didn't reach router construction. stderr:\n{stderr}"
        )
        # With the full config seeded, vault + csv_dir must register;
        # otherwise this test would slide back into theatre.
        assert "Registered child 'csv_dir'" in stderr, (
            "csv_dir child did not register — full-config seeding broke. "
            f"stderr:\n{stderr}"
        )
        assert "Registered vault layer" in stderr, (
            "vault layer did not register — full-config seeding broke. "
            f"stderr:\n{stderr}"
        )


def test_serve_tools_list_round_trip() -> None:
    """`tools/list` answers cleanly with running + csv_dir + vault tools loaded.

    Regression for the v6.5.0 missing-`description` bug (vault/layer.py
    shipped two tools with params lacking `"description"`, and the
    router's tools/list handler accessed `pinfo["description"]`
    unconditionally — KeyError surfaced as a JSON-RPC error response on
    every tools/list request).

    The prior version of this test seeded an empty config dir, which
    meant vault never registered — so the bug it claimed to regress
    was never actually exercised. Fixed in the v6.5.0 mcp-protocol-
    auditor pass by switching to the full-config seeding helper.
    """
    with spawn_server() as (client, _paths):
        init_response = client.initialize()
        assert "error" not in init_response, (
            f"`initialize` returned an error: {init_response}"
        )

        list_response = client.list_tools()
        assert "error" not in list_response, (
            f"`tools/list` returned an error: {list_response}"
        )
        assert "result" in list_response
        tools = list_response["result"]["tools"]
        assert len(tools) > 0, "tools/list returned an empty list"

        names = {t["name"] for t in tools}
        # Running child tools (always registered).
        assert "strava_list_runs" in names
        # csv_dir child tools — proves opt-in csv_dir wired up.
        assert "csv_list_files" in names
        assert "csv_summary_report" in names
        assert "csv_cohort_summary" in names
        # Vault layer tools — proves vault path wired up. These are
        # the two whose `description` fields previously broke
        # tools/list with a KeyError.
        assert "vault_list_moments" in names
        assert "vault_capture_moment" in names

        # Every tool must declare an input schema. A missing schema
        # surfaces only when a real client requests tools/list.
        for tool in tools:
            assert "inputSchema" in tool, (
                f"Tool {tool['name']!r} missing inputSchema"
            )
            schema = tool["inputSchema"]
            assert schema["type"] == "object"
            for pname, pinfo in schema.get("properties", {}).items():
                # Description must be a string (possibly empty per
                # router's defensive .get fallback) — never absent.
                assert "description" in pinfo, (
                    f"Tool {tool['name']!r} param {pname!r} "
                    f"missing description in tools/list response"
                )
                assert isinstance(pinfo["description"], str)

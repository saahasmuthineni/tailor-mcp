"""
Shared subprocess MCP-client helpers for protocol-audit tests.

These helpers spawn ``python -m biosensor_mcp serve`` as a real
subprocess, speak JSON-RPC over stdio, and return parsed responses.
They are the substrate for ``tests/test_serve_*`` tests; the helpers
themselves intentionally do nothing protocol-validating — that's the
test's job.

This module is private to the test suite (``_mcp_client``); update
it freely between audit runs but do not break any existing helper
signature without first updating every caller.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

# ──────────────────────────────────────────────────────────────────
# Environment / config seeding
# ──────────────────────────────────────────────────────────────────

# A tiny synthetic CSV: 3 columns × 5 rows with a numeric column the
# Tier-1 tools (csv_summary_report, csv_force_decline) reduce cleanly.
_SAMPLE_CSV_A = (
    "timestamp,heart_rate,glucose\n"
    "2026-04-01T08:00:00,72,95\n"
    "2026-04-01T08:00:01,74,96\n"
    "2026-04-01T08:00:02,76,97\n"
    "2026-04-01T08:00:03,78,98\n"
    "2026-04-01T08:00:04,80,99\n"
)
_SAMPLE_CSV_B = (
    "timestamp,heart_rate,glucose\n"
    "2026-04-01T08:00:00,82,101\n"
    "2026-04-01T08:00:01,84,102\n"
    "2026-04-01T08:00:02,86,103\n"
    "2026-04-01T08:00:03,88,104\n"
    "2026-04-01T08:00:04,90,105\n"
)


def seed_full_config(root: Path) -> dict[str, Path]:
    """
    Seed a real, complete config under ``root`` so ``serve`` registers
    the running child + csv_dir child + vault layer (44+ tools loaded).

    An empty config dir is theatre — most tools never register.

    Returns paths the test may want to assert against:
      ``config_dir``, ``data_dir``, ``vault_path``, ``csv_dir``.
    """
    config_dir = root / "config"
    data_dir = root / "data"
    vault_path = root / "vault"
    csv_dir = root / "csvs"
    for p in (config_dir, data_dir, vault_path, csv_dir):
        p.mkdir(parents=True, exist_ok=True)

    # Two CSVs so cohort tools have something to scan.
    (csv_dir / "P001.csv").write_text(_SAMPLE_CSV_A, encoding="utf-8")
    (csv_dir / "P002.csv").write_text(_SAMPLE_CSV_B, encoding="utf-8")

    # Sidecar so csv_cohort_summary is callable end-to-end.
    sidecar = {
        "P001.csv": {"sex": "F", "group": "control"},
        "P002.csv": {"sex": "M", "group": "intervention"},
    }
    (csv_dir / "metadata.json").write_text(
        json.dumps(sidecar), encoding="utf-8"
    )

    user_config = {
        "max_hr": 185,
        "resting_hr": 55,
        "vault_path": str(vault_path),
        "csv_dir": {
            "path": str(csv_dir),
            "timestamp_column": "timestamp",
            "timestamp_format": "%Y-%m-%dT%H:%M:%S",
            "value_columns": {
                "heart_rate": "Heart rate (bpm)",
                "glucose": "Blood glucose (mg/dL)",
            },
        },
    }
    (config_dir / "user_config.json").write_text(
        json.dumps(user_config), encoding="utf-8"
    )

    return {
        "config_dir": config_dir,
        "data_dir": data_dir,
        "vault_path": vault_path,
        "csv_dir": csv_dir,
    }


# ──────────────────────────────────────────────────────────────────
# Subprocess driver
# ──────────────────────────────────────────────────────────────────

class MCPClient:
    """
    Thin JSON-RPC stdio driver around the ``biosensor-mcp serve``
    subprocess. Newline-delimited per-message JSON. The mcp 1.27 SDK
    emits responses one-per-line on stdout; logs go to stderr.
    """

    def __init__(self, proc: subprocess.Popen):
        self._proc = proc
        self._next_id = 1

    @property
    def proc(self) -> subprocess.Popen:
        return self._proc

    def send(self, message: dict) -> None:
        """Send one JSON-RPC message + newline."""
        line = (json.dumps(message) + "\n").encode("utf-8")
        assert self._proc.stdin is not None
        self._proc.stdin.write(line)
        self._proc.stdin.flush()

    def recv(self, timeout_s: float = 10.0) -> dict | None:
        """Read one newline-delimited JSON-RPC message from stdout."""
        deadline = time.time() + timeout_s
        assert self._proc.stdout is not None
        while time.time() < deadline:
            line = self._proc.stdout.readline()
            if line:
                try:
                    return json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    # Partial / log line — keep reading.
                    continue
            if self._proc.poll() is not None:
                return None
            time.sleep(0.02)
        return None

    def request(self, method: str, params: dict | None = None,
                timeout_s: float = 10.0) -> dict:
        """Send a request, await the matching response by id."""
        rid = self._next_id
        self._next_id += 1
        self.send({
            "jsonrpc": "2.0",
            "id": rid,
            "method": method,
            "params": params or {},
        })
        # The server may emit notifications between request/response
        # in some flows; loop until we see our id.
        while True:
            msg = self.recv(timeout_s=timeout_s)
            if msg is None:
                raise RuntimeError(
                    f"No response for {method!r} within {timeout_s}s. "
                    f"stderr:\n{self.read_stderr()}"
                )
            if msg.get("id") == rid:
                return msg
            # Otherwise it's an unsolicited notification or a stale
            # response — keep waiting.

    def notify(self, method: str, params: dict | None = None) -> None:
        self.send({
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        })

    def initialize(self) -> dict:
        """Run the MCP handshake. Returns the initialize response."""
        resp = self.request("initialize", {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "protocol-audit", "version": "0.0"},
        })
        self.notify("notifications/initialized")
        return resp

    def call_tool(self, name: str, arguments: dict | None = None,
                  timeout_s: float = 15.0) -> dict:
        """Issue tools/call and return the parsed JSON-RPC envelope."""
        return self.request("tools/call", {
            "name": name,
            "arguments": arguments or {},
        }, timeout_s=timeout_s)

    def list_tools(self, timeout_s: float = 10.0) -> dict:
        return self.request("tools/list", {}, timeout_s=timeout_s)

    def read_stderr(self) -> str:
        """Drain whatever's currently buffered on stderr."""
        if self._proc.stderr is None:
            return ""
        try:
            self._proc.stderr.flush()
        except Exception:
            pass
        # Best-effort non-blocking read: if the process is still
        # running, this may block briefly. Tests that call this
        # are usually already in a failure path.
        try:
            return self._proc.stderr.read1(65536).decode(  # type: ignore[attr-defined]
                "utf-8", errors="replace"
            )
        except (AttributeError, ValueError):
            return ""


@contextlib.contextmanager
def spawn_server(env_overrides: dict[str, str] | None = None,
                 ) -> Iterator[tuple[MCPClient, dict[str, Path]]]:
    """
    Context manager: temp dirs + seeded full config + spawned server.

    Yields ``(client, paths)`` where ``paths`` is the dict returned
    by ``seed_full_config``. Tears down the subprocess on exit.
    """
    with TemporaryDirectory() as tmp:
        paths = seed_full_config(Path(tmp))
        env = {
            **os.environ,
            "BIOSENSOR_CONFIG_DIR": str(paths["config_dir"]),
            "BIOSENSOR_DATA_DIR": str(paths["data_dir"]),
            **(env_overrides or {}),
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
            yield client, paths
        finally:
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


# ──────────────────────────────────────────────────────────────────
# Wire-payload assertions
# ──────────────────────────────────────────────────────────────────

# Python ``repr()`` artifacts that should NEVER appear in the JSON
# wire payload. Each is a smoking gun for a ``default=str`` coercion
# bug in the JSON serializer (see audit.py:43).
_REPR_ARTIFACTS = (
    "datetime.datetime(",
    "datetime.date(",
    "PosixPath(",
    "WindowsPath(",
    "Decimal('",
    "<class '",
    "<function ",
    "<bound method ",
)


def assert_no_repr_artifacts(payload: str) -> None:
    """
    Fail if the raw wire payload contains any Python ``repr()`` artifact.
    These leak through ``json.dumps(..., default=str)`` when the result
    contains datetime / Path / Decimal / type / function objects.
    """
    for artifact in _REPR_ARTIFACTS:
        assert artifact not in payload, (
            f"Wire payload contains Python repr() artifact {artifact!r} — "
            f"this is a default=str coercion bug in the JSON serializer "
            f"(see audit.py:43-44 / 53-54). Payload excerpt:\n"
            f"{payload[:600]}"
        )


def extract_text_result(call_response: dict) -> str:
    """
    Return the inner text payload from a ``tools/call`` envelope.
    The mcp SDK wraps results in ``result.content[*].text``; we
    concatenate all text parts.
    """
    assert "result" in call_response, (
        f"tools/call returned no result: {call_response}"
    )
    content = call_response["result"].get("content", [])
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text", ""))
    return "".join(parts)

"""
Rehearsal driver for the csv_synchronized_windows demo.

Spawns ``python -m tailor serve`` as a real subprocess against an
isolated temp config pointed at the generated ten-subject cohort,
speaks MCP JSON-RPC over stdio exactly the way Claude Desktop does,
and exercises the demo's hot path end-to-end:

  1. tools/list  — serve boots, csv_synchronized_windows is exposed
  2. csv_synchronized_windows {lead_s:10, window_s:5}  — Phase 1
     cohort: every subject, every epoch, the [peak-10s, peak-5s]
     window Chunyu's analysis uses. The per-subject table is read
     for the QC finding — does any subject's quad (vastus) recruitment
     climb? (One planted "cheater" should stand out.)
  3. csv_synchronized_windows {file_id=...}  — a single recording
  4. csv_synchronized_windows {anchor_column bad}  — an off-script error
  5. csv_list_files {}  — the wider csv_dir suite, free

Run it after generate.py; the transcript is exactly what Claude
Desktop will drive. The temp config never touches a real ~/.tailor.

    python examples/hip_lab_demo/labchart_sync/generate.py
    python examples/hip_lab_demo/labchart_sync/rehearse.py

Demo-grade work on the feature/csv-synchronized-windows branch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).parent
DATA_DIR = (HERE / "data").resolve()

# Chunyu's analysis window: 10 s before the contraction peak, 5 s long.
LEAD_S = 10.0
WINDOW_S = 5.0
# A subject whose vastus (quad) RMS climbs more than this across the
# 7 epochs is compensating — the "cheating" the QC screens for.
CHEAT_THRESHOLD_PCT = 25.0


# ── Minimal MCP stdio client (self-contained — no test-tree import) ──

class _MCP:
    """Newline-delimited JSON-RPC 2.0 driver over a serve subprocess."""

    def __init__(self, proc: subprocess.Popen):
        self._proc = proc
        self._id = 0

    def _send(self, msg: dict) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write((json.dumps(msg) + "\n").encode())
        self._proc.stdin.flush()

    def _recv(self, timeout_s: float = 25.0) -> dict | None:
        deadline = time.time() + timeout_s
        assert self._proc.stdout is not None
        while time.time() < deadline:
            line = self._proc.stdout.readline()
            if line:
                try:
                    return json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
            if self._proc.poll() is not None:
                return None
            time.sleep(0.02)
        return None

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid,
                    "method": method, "params": params or {}})
        while True:
            msg = self._recv()
            if msg is None:
                raise RuntimeError(f"no response to {method!r}")
            if msg.get("id") == rid:
                return msg

    def notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": {}})

    def initialize(self) -> None:
        self.request("initialize", {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "labchart-rehearse", "version": "0.0"},
        })
        self.notify("notifications/initialized")

    def call(self, name: str, arguments: dict | None = None) -> dict:
        """Issue tools/call; return the parsed inner result dict."""
        resp = self.request("tools/call",
                             {"name": name, "arguments": arguments or {}})
        result = resp.get("result", {})
        text = "".join(
            part.get("text", "")
            for part in result.get("content", [])
            if isinstance(part, dict) and part.get("type") == "text"
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"_raw": text}


def _line(char: str = "-") -> None:
    print(char * 70)


def _window_rms(epoch: dict, channel: str) -> float:
    """RMS of one channel inside the [peak-10s, peak-5s] window."""
    return epoch["window"]["channels"][channel]["value"]


def main() -> int:
    if not DATA_DIR.is_dir() or not list(DATA_DIR.glob("S*.csv")):
        print(f"[FAIL] no cohort data at {DATA_DIR}")
        print("       run generate.py first.")
        return 1

    with TemporaryDirectory() as tmp:
        config_dir = Path(tmp) / "config"
        data_dir = Path(tmp) / "data"
        config_dir.mkdir()
        data_dir.mkdir()
        (config_dir / "user_config.json").write_text(json.dumps({
            "csv_dir": {
                "path": str(DATA_DIR),
                "timestamp_column": "t_s",
                "value_columns": {
                    "torque": "Torque (N.m)",
                    "gastroc_lat": "Gastrocnemius lateralis EMG (uV)",
                    "gastroc_med": "Gastrocnemius medialis EMG (uV)",
                    "vastus_lat": "Vastus lateralis EMG (uV)",
                    "vastus_med": "Vastus medialis EMG (uV)",
                },
            },
        }), encoding="utf-8")

        env = {
            **os.environ,
            "TAILOR_CONFIG_DIR": str(config_dir),
            "TAILOR_DATA_DIR": str(data_dir),
        }
        proc = subprocess.Popen(
            [sys.executable, "-m", "tailor", "serve"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env,
        )
        rc = 0
        try:
            mcp = _MCP(proc)
            mcp.initialize()

            # 1. tools/list — serve booted, tool exposed.
            _line("=")
            print("STEP 1  tools/list  (serve boots; tool is on the wire)")
            _line("=")
            tools = mcp.request("tools/list")["result"]["tools"]
            names = sorted(t["name"] for t in tools)
            present = "csv_synchronized_windows" in names
            print(f"  serve booted; {len(names)} tools registered")
            print(f"  csv_synchronized_windows present: "
                  f"{'[OK]' if present else '[FAIL]'}")
            if not present:
                return 1

            # 2. Phase 1 — the cohort headline, one call.
            _line("=")
            print("STEP 2  Phase 1 headline")
            print('        "run the contraction extraction across all ten')
            print('         recordings"  (window: 10 s before peak, 5 s long)')
            _line("=")
            t0 = time.time()
            cohort = mcp.call("csv_synchronized_windows",
                              {"lead_s": LEAD_S, "window_s": WINDOW_S})
            dt = time.time() - t0
            sc = cohort.get("subject_count")
            print(f"  subject_count: {sc}   (wire round-trip {dt:.2f}s)")
            print(f"  {'subject':<11}{'epochs':>7}{'gastroc_lat RMS':>20}"
                  f"{'vastus_lat RMS':>20}{'quad':>9}")
            print(f"  {'':<11}{'':>7}{'epoch 1 -> 7':>20}"
                  f"{'epoch 1 -> 7':>20}{'rise':>9}")
            flagged = []
            all_seven = True
            for name in sorted(cohort.get("subjects", {})):
                s = cohort["subjects"][name]
                eps = s["epochs"]
                if s["epoch_count"] != 7:
                    all_seven = False
                gl1, gl7 = _window_rms(eps[0], "gastroc_lat"), _window_rms(eps[-1], "gastroc_lat")
                vl1, vl7 = _window_rms(eps[0], "vastus_lat"), _window_rms(eps[-1], "vastus_lat")
                rise = (vl7 - vl1) / vl1 * 100.0
                flag = "  <== CHEAT" if rise > CHEAT_THRESHOLD_PCT else ""
                if flag:
                    flagged.append(name)
                print(f"  {name:<11}{s['epoch_count']:>7}"
                      f"{gl1:>9.1f} ->{gl7:>7.1f}"
                      f"{vl1:>9.1f} ->{vl7:>7.1f}"
                      f"{rise:>+8.0f}%{flag}")
            print(f"  every subject -> 7 epochs: {'[OK]' if all_seven else '[FAIL]'}")
            print("  READING THE TABLE: gastroc (target) RMS climbs for every")
            print("  subject -- the protocol fatigued the right muscle. Quad")
            print("  RMS stays flat -- EXCEPT one subject whose quad recruitment")
            print("  climbs: that participant compensated. That is the QC")
            print("  finding the analysis exists to make.")
            print(f"  compensation flagged: {flagged or 'none'}")
            if sc != 10 or not all_seven or len(flagged) != 1:
                rc = 1

            # 3. Single recording — the flagged subject.
            target = flagged[0] if flagged else "S001.csv"
            _line("=")
            print(f"STEP 3  off-script: drill into {target}")
            _line("=")
            one = mcp.call("csv_synchronized_windows",
                           {"file_id": target,
                            "lead_s": LEAD_S, "window_s": WINDOW_S})
            print(f"  {target} -> epoch_count={one.get('epoch_count')}  "
                  f"sample_rate={one.get('sample_rate_hz')} Hz")
            print(f"  {'epoch':>6}{'vastus_lat RMS':>18}{'gastroc_lat RMS':>18}")
            for ep in one["epochs"]:
                print(f"  {ep['epoch']:>6}"
                      f"{_window_rms(ep, 'vastus_lat'):>18.1f}"
                      f"{_window_rms(ep, 'gastroc_lat'):>18.1f}")

            # 4. Off-script error path — a channel that does not exist.
            _line("=")
            print("STEP 4  off-script: a channel that does not exist")
            _line("=")
            bad = mcp.call("csv_synchronized_windows",
                           {"file_id": "S001.csv", "anchor_column": "soleus"})
            err = bad.get("error", "")
            clean = "error" in bad and "soleus" in err
            print(f"  result: {err[:130]}")
            print(f"  fails with a clear message: {'[OK]' if clean else '[FAIL]'}")
            if not clean:
                rc = 1

            # 5. The wider csv_dir suite is live on the same data, free.
            _line("=")
            print("STEP 5  the whole csv_dir suite works on this data, free")
            _line("=")
            listing = mcp.call("csv_list_files", {})
            print(f"  csv_list_files -> {listing.get('count')} recordings "
                  f"visible to all 8 csv_dir tools")

            _line("=")
            print(f"REHEARSAL {'PASSED' if rc == 0 else 'FAILED'}")
            _line("=")
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
        return rc


if __name__ == "__main__":
    sys.exit(main())

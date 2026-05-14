"""
Windows-recipient resilience regression tests.

The 2026-05-06 max-debug-hunt found two demo blockers that every
existing gate (pytest, ruff, security probe, CLI smoke) passed cleanly:

* ``cmd_status`` printed a U+2192 arrow that crashes ``UnicodeEncodeError``
  under Windows PowerShell 5's cp1252 stdout. Linux UTF-8 stdout missed it.
* ``cmd_status`` ran ``SELECT COUNT(*) FROM activities`` without a try/except,
  crashing on any fresh ``tailor tour`` install (the data dir gets
  created with an empty SQLite file before the Strava child has populated
  any tables).

The fixes:
* ``__main__.py:_make_cli_stdout_resilient()`` reconfigures both stdout
  and stderr with ``errors='replace'`` so any future non-cp1252 glyph
  degrades to ``?`` rather than aborts the command.
* ``cmd_status`` arrow replaced with ASCII ``->``; ``pilot.py`` arrow
  replaced with ASCII ``<-``.
* ``cmd_status`` activities/streams SELECT wrapped in try/except, mirroring
  the audit-log SELECT block at line 370.

These tests guard the regressions. The static-encoding guard is the most
load-bearing: a future arrow / checkmark / bullet sneaking back into a
``print()`` call would re-create the same gate-evading bug.
"""

from __future__ import annotations

import io
import re
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import tailor.__main__ as cli

SRC_ROOT = Path(__file__).parent.parent / "src" / "tailor"


def _user_facing_print_lines(path: Path) -> list[tuple[int, str]]:
    """Lines that look like ``print(...)`` statements — the user-facing
    CLI surface. We filter to top-level prints, not docstrings or comments."""
    text = path.read_text(encoding="utf-8")
    out: list[tuple[int, str]] = []
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if "print(" in line:
            out.append((n, line))
    return out


# ─── Static guard: no non-cp1252 char in any print() ──────────────────


class TestNoNonCp1252InCliPrints:
    """If a ``print(...)`` call contains a character cp1252 cannot encode,
    that print will raise ``UnicodeEncodeError`` on Windows PowerShell 5,
    aborting the command for any recipient on that platform.

    This guard scans the five user-facing print-bearing CLI modules
    (``__main__.py``, ``pilot.py``, ``wizard.py``, ``tour.py``, and
    ``demo/runner.py``) and asserts every ``print()`` line round-trips
    through cp1252 encoding. Children have zero ``print()`` calls
    (they emit through the MCP wire, not stdout) and framework modules
    have zero — so the parametrize is the complete user-facing surface.
    """

    @pytest.mark.parametrize(
        "src_path",
        [
            SRC_ROOT / "__main__.py",
            SRC_ROOT / "pilot.py",
            SRC_ROOT / "wizard.py",
            SRC_ROOT / "tour.py",
            SRC_ROOT / "demo" / "runner.py",
        ],
        ids=["main", "pilot", "wizard", "tour", "demo_runner"],
    )
    def test_print_lines_encode_to_cp1252(self, src_path: Path):
        offenders: list[str] = []
        for n, line in _user_facing_print_lines(src_path):
            try:
                line.encode("cp1252")
            except UnicodeEncodeError as exc:
                bad_chars = sorted({line[i] for i in range(len(line))
                                    if line[i].encode("utf-8")
                                    and not _is_cp1252_safe(line[i])})
                offenders.append(
                    f"  {src_path.name}:{n} cannot cp1252-encode "
                    f"(bad chars: {bad_chars}, error: {exc})\n    {line.strip()}"
                )
        assert not offenders, (
            "Non-cp1252 chars in user-facing CLI print() — Windows "
            "PowerShell 5 recipients will UnicodeEncodeError-crash:\n"
            + "\n".join(offenders)
        )


def _is_cp1252_safe(ch: str) -> bool:
    try:
        ch.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


# ─── _make_cli_stdout_resilient survives missing reconfigure ──────────


class TestStdoutReconfigureHelper:
    """The helper must survive streams without a ``.reconfigure`` method
    (e.g. pytest's capture wrappers, in-memory ``StringIO`` in tests,
    or environments where the C-level stream isn't a TextIOWrapper)."""

    def test_helper_survives_stream_without_reconfigure(self):
        fake_stream = io.StringIO()
        assert not hasattr(fake_stream, "reconfigure")
        with patch.object(sys, "stdout", fake_stream):
            with patch.object(sys, "stderr", fake_stream):
                cli._make_cli_stdout_resilient()

    def test_helper_swallows_oserror_from_reconfigure(self):
        class BrokenStream:
            def reconfigure(self, **kwargs):
                raise OSError("simulated platform-specific failure")
        broken = BrokenStream()
        with patch.object(sys, "stdout", broken):
            with patch.object(sys, "stderr", broken):
                cli._make_cli_stdout_resilient()

    def test_helper_called_from_main_entrypoint(self):
        """Otherwise the recipient never benefits."""
        src = (SRC_ROOT / "__main__.py").read_text(encoding="utf-8")
        # main() is at end of file; match either next top-level def OR EOF.
        match = re.search(
            r"^def main\(\):(.*?)(?=^def |^if __name__|\Z)",
            src,
            re.MULTILINE | re.DOTALL,
        )
        assert match, "could not find def main() body"
        body = match.group(1)
        assert "_make_cli_stdout_resilient()" in body, (
            "main() must call _make_cli_stdout_resilient() at entry "
            "or recipient cp1252 consoles still crash"
        )


# ─── cmd_status survives missing activities table ─────────────────────


class TestCmdStatusOnFreshTourInstall:
    """``tailor fitting-room`` (renamed from ``tailor tour`` in v7.1.0
    per ADR 0035) creates the data dir but no Strava tables. A recipient
    running ``tailor status`` next must not crash on the
    activities/streams SELECT against an empty SQLite file."""

    def test_cmd_status_does_not_crash_when_activities_table_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        config_dir = tmp_path / "config"
        data_dir = tmp_path / "data"
        config_dir.mkdir()
        data_dir.mkdir()
        # Simulate fresh-tour-install activities.db: file exists, no tables.
        sqlite3.connect(str(data_dir / "activities.db")).close()

        monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(cli, "DATA_DIR", data_dir)

        cli.cmd_status()

        captured = capsys.readouterr().out
        assert "Tables not yet created" in captured, (
            "Status should print a friendly message instead of "
            "aborting on missing-activities-table:\n" + captured
        )

    def test_cmd_status_still_reports_counts_when_tables_exist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        """Don't accidentally regress the happy path."""
        config_dir = tmp_path / "config"
        data_dir = tmp_path / "data"
        config_dir.mkdir()
        data_dir.mkdir()
        db = data_dir / "activities.db"
        with sqlite3.connect(str(db)) as conn:
            conn.execute("CREATE TABLE activities (id INTEGER)")
            conn.execute("CREATE TABLE streams (id INTEGER)")
            conn.execute("INSERT INTO activities VALUES (1)")
            conn.execute("INSERT INTO activities VALUES (2)")
            conn.execute("INSERT INTO streams VALUES (1)")

        monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(cli, "DATA_DIR", data_dir)
        cli.cmd_status()
        captured = capsys.readouterr().out
        assert "Cached activities: 2" in captured
        assert "Cached streams: 1" in captured

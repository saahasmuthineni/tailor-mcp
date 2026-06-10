"""
Inspector export tests — `tailor inspect --export` end to end.

The subprocess test drives the real CLI (`python -m tailor inspect
--export ...`) so the seventh verb's argparse wiring is exercised the
way a recipient would hit it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tailor.inspector.server import export_page


def test_export_page_writes_self_contained_file(
    populated_data_dir: Path, tmp_path: Path, capsys,
) -> None:
    out = tmp_path / "page.html"
    rc = export_page(populated_data_dir, out)
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>")
    # Self-contained: no external fetches of any kind.
    for marker in ("http://", "https://", "<script", "src=", "@import"):
        assert marker not in text
    # Static export carries no auto-refresh.
    assert 'http-equiv="refresh"' not in text
    # Retention note printed (operator-managed retention, ADR 0043).
    captured = capsys.readouterr()
    assert "yours to manage" in captured.out


def test_cli_export_subprocess_exit_0(
    populated_data_dir: Path, tmp_path: Path,
) -> None:
    out = tmp_path / "exported.html"
    env = {
        **os.environ,
        "TAILOR_CONFIG_DIR": str(tmp_path / "cfg"),
        "TAILOR_DATA_DIR": str(populated_data_dir),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "tailor", "inspect", "--export", str(out)],
        capture_output=True, env=env, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr.decode()
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert "READ-ONLY" in body
    assert "Gate activity" in body


def test_cli_export_empty_data_dir_exit_0(tmp_path: Path) -> None:
    """Acceptance criterion 1: honest empty states, exit 0."""
    out = tmp_path / "empty.html"
    env = {
        **os.environ,
        "TAILOR_CONFIG_DIR": str(tmp_path / "cfg"),
        "TAILOR_DATA_DIR": str(tmp_path / "data"),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "tailor", "inspect", "--export", str(out)],
        capture_output=True, env=env, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr.decode()
    assert "No audit database yet" in out.read_text(encoding="utf-8")


def test_cli_help_lists_inspect(tmp_path: Path) -> None:
    """The seventh verb is discoverable from `tailor --help`."""
    env = {
        **os.environ,
        "TAILOR_CONFIG_DIR": str(tmp_path / "cfg"),
        "TAILOR_DATA_DIR": str(tmp_path / "data"),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "tailor", "--help"],
        capture_output=True, env=env, timeout=60,
    )
    assert proc.returncode == 0
    # Windows drives this subprocess with a cp1252 stdout and the help
    # docstring carries non-ASCII (e.g. the ADR section sign), so a
    # strict UTF-8 decode raises. The assertion target is ASCII;
    # replacement-decode is lossless for it.
    out = proc.stdout.decode("utf-8", errors="replace")
    assert "inspect" in out

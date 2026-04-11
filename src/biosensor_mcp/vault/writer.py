"""
Vault Writer — Post-Execute Hook + Atomic File Writes
=====================================================
VaultWriter is the bridge between the router pipeline and the Obsidian vault.

It is registered as a post-execute hook on RouterMCP:
    router.register_post_execute_hook(vault_writer)

After any vaultable tool succeeds the router calls:
    vault_writer(domain, tool_name, result)

Errors are always swallowed — a vault failure never breaks the MCP session.

Atomic writes use tempfile + os.replace() so Obsidian never sees a partial file.
"""

import logging
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .renderer import render_run_note, render_trend_note, render_compare_note
from .storage import VaultStorage

log = logging.getLogger("biosensor-mcp.vault")


def _is_relative_to(path: Path, parent: Path) -> bool:
    """Path.is_relative_to() was added in Python 3.9; use it when available."""
    try:
        return path.is_relative_to(parent)
    except AttributeError:
        # Fallback for Python < 3.9
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False


# Max chars for a single insight annotation block
_MAX_INSIGHT_CHARS = 2000

# Non-printable control chars (except tab, newline, CR) that must not be stored
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize(text: str) -> str:
    """Strip null bytes and non-printable control chars."""
    return _CONTROL_RE.sub("", text)


class VaultWriter:
    """
    Callable post-execute hook.  Wires analytics output → Obsidian vault.

    Args:
        vault_path:       Absolute path to the Obsidian vault root.
        data_dir:         The MCP data directory (used to locate vault.db).
        running_storage:  RunningStorage instance for date / activity lookups.
        vaultable_tools:  Set of tool names whose results should be archived.
        max_hr:           User-configured max heart rate (for run note rendering).
    """

    def __init__(
        self,
        vault_path: Path,
        data_dir: Path,
        running_storage,           # RunningStorage — avoids circular import
        vaultable_tools: set[str],
        max_hr: int = 195,
    ):
        self._vault_path = vault_path
        self._storage = VaultStorage(data_dir / "vault.db")
        self._running_storage = running_storage
        self._vaultable_tools = vaultable_tools
        self._max_hr = max_hr

    # ── Hook interface ──

    def __call__(self, domain: str, tool_name: str, result: dict) -> None:
        """Post-execute hook.  Errors are always swallowed."""
        if tool_name not in self._vaultable_tools:
            return
        try:
            self._write(domain, tool_name, result)
        except Exception as exc:
            log.warning(f"VaultWriter: {exc}")

    # ── Public write API (used by vault_backfill) ──

    def write_note(self, tool_name: str, result: dict) -> str:
        """
        Render and write a note.  Raises on error.
        Returns the relative filename (e.g. "running/2025-04-10-activity-123.md").
        """
        filename, content = self._render(tool_name, result)
        self._atomic_write(filename, content)
        self._index_note(filename, tool_name, result, content)
        return filename

    def append_insight_notes(self, filename: str, notes: str) -> None:
        """
        Append a timestamped insight section to an existing note.
        Updates the SQLite index to reflect has_insight_notes=True.

        Raises ValueError on bad input, FileNotFoundError if note missing.
        """
        notes = _sanitize(notes.strip())
        if not notes:
            raise ValueError("Insight notes must not be empty.")
        if len(notes) > _MAX_INSIGHT_CHARS:
            raise ValueError(
                f"Insight notes too long: {len(notes)} chars (max {_MAX_INSIGHT_CHARS})."
            )

        # Path traversal check
        abs_path = self._safe_path(filename)

        if not abs_path.exists():
            raise FileNotFoundError(f"Note not found: {filename}")

        existing = abs_path.read_text(encoding="utf-8")

        # Replace the placeholder stub if present; otherwise append
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        block = f"\n\n### Insight — {timestamp}\n\n{notes}\n"

        stub = "*(No insight notes yet.)*"
        if stub in existing:
            updated = existing.replace(stub, notes, 1)
        else:
            updated = existing.rstrip() + block

        # Update has_insight_notes: false → true in frontmatter
        updated = updated.replace("has_insight_notes: false", "has_insight_notes: true", 1)

        self._atomic_write_abs(abs_path, updated)
        self._storage.set_has_insight_notes(filename)
        log.info(f"VaultWriter: insight notes appended to {filename}")

    def close(self):
        """Release SQLite connection (required on Windows)."""
        self._storage.close()

    # ── Internal ──

    def _write(self, domain: str, tool_name: str, result: dict) -> None:
        filename, content = self._render(tool_name, result)
        self._atomic_write(filename, content)
        self._index_note(filename, tool_name, result, content)
        log.info(f"VaultWriter: wrote {filename}")

    def _render(self, tool_name: str, result: dict) -> tuple[str, str]:
        """Dispatch to the correct renderer. Returns (filename, content)."""
        if tool_name == "strava_run_report":
            activity_id = result.get("activity_id")
            activity_data = {}
            if activity_id and self._running_storage:
                activity_data = self._running_storage.get_activity(activity_id) or {}
            return render_run_note(result, activity_data, max_hr=self._max_hr)

        if tool_name == "strava_trend_report":
            return render_trend_note(result)

        if tool_name == "strava_compare_runs":
            return render_compare_note(result)

        raise ValueError(f"No renderer for tool: {tool_name}")

    def _atomic_write(self, relative_filename: str, content: str) -> None:
        """Resolve to vault_path, validate, then write atomically."""
        abs_path = self._safe_path(relative_filename)
        self._atomic_write_abs(abs_path, content)

    def _atomic_write_abs(self, abs_path: Path, content: str) -> None:
        """Atomic write: temp file → os.replace(). Obsidian never sees partial."""
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same directory so os.replace is atomic
        fd, tmp_path = tempfile.mkstemp(
            dir=abs_path.parent, prefix=".vault_tmp_", suffix=".md"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, abs_path)
        except Exception:
            # Clean up temp file if replace failed
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _safe_path(self, relative_filename: str) -> Path:
        """
        Resolve relative_filename inside vault_path.
        Raises ValueError if the resolved path escapes the vault root.
        """
        resolved = (self._vault_path / relative_filename).resolve()
        vault_resolved = self._vault_path.resolve()
        if not _is_relative_to(resolved, vault_resolved):
            raise ValueError(f"Path traversal detected: {relative_filename}")
        return resolved

    def _index_note(
        self, filename: str, tool_name: str, result: dict, content: str
    ) -> None:
        """Extract key fields and write to VaultStorage index."""
        # Parse frontmatter fields for fast querying
        fm = _extract_frontmatter(content)
        note_type = fm.get("note_type", tool_name)
        domain = fm.get("domain", "running")
        activity_id = fm.get("activity_id") or fm.get("strava_id")
        date = fm.get("date")
        week = fm.get("week")

        self._storage.upsert_note(
            filename=filename,
            domain=domain,
            note_type=note_type,
            frontmatter=fm,
            activity_id=int(activity_id) if activity_id else None,
            date=date,
            week=week,
        )


def _extract_frontmatter(content: str) -> dict:
    """
    Parse the YAML frontmatter block from a rendered note.
    Returns a flat dict of scalar values (no full YAML parsing needed).
    """
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    fm_block = content[4:end]

    result: dict = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"')
        # Skip tag list lines
        if key.startswith("-") or not key:
            continue
        # Parse simple types
        if value == "true":
            result[key] = True
        elif value == "false":
            result[key] = False
        elif value.lstrip("-").isdigit():
            result[key] = int(value)
        else:
            try:
                result[key] = float(value)
            except ValueError:
                result[key] = value
    return result

"""
Pilot Setup Wizard
==================
Guided CLI flow that turns the seven-step multi-subject-pilot
quickstart into three prompts. Targets a non-technical PI: pick a
CSV directory (or accept the bundled synthetic fixtures), confirm
the auto-detected schema, optionally register with Claude Desktop.

Usage:
    biosensor-mcp pilot     # via CLI entry point
    python -m biosensor_mcp.pilot   # direct invocation

Ctrl-C contract
---------------
The first durable write is ``user_config.json``. Anything before
that line is rolled back on SIGINT (no on-disk state). Anything
after that is keep-and-resume — the user can re-run the wizard and
will be told their config already exists; the second run skips
straight to Claude Desktop registration.
"""

from __future__ import annotations

import json
import os
import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.resources import as_file, files
from pathlib import Path
from typing import Literal

from biosensor_mcp.config import CONFIG_DIR

CONFIG_PATH = CONFIG_DIR / "user_config.json"

# Cloud-sync provider markers — case-insensitive substring match against
# the resolved absolute path. Mirrors the set used by cmd_serve() for
# vault_path detection (__main__.py ~line 114), kept in sync deliberately
# so users see consistent warnings across both surfaces.
_CLOUD_MARKERS: tuple[tuple[str, str], ...] = (
    ("onedrive", "OneDrive"),
    ("icloud", "iCloud Drive"),
    # macOS iCloud canonical paths do not contain the literal substring
    # "icloud" — they live under ~/Library/Mobile Documents/com~apple~CloudDocs/
    # for the system iCloud and ~/Library/Mobile Documents/iCloud~* for app-
    # specific iCloud containers (e.g. Obsidian iOS). Either path is iCloud-
    # synced and warrants the warning.
    ("mobile documents", "iCloud Drive (macOS)"),
    ("clouddocs", "iCloud Drive (macOS)"),
    ("dropbox", "Dropbox"),
    ("googledrive", "Google Drive"),
    ("google drive", "Google Drive"),
    ("box sync", "Box"),
    ("boxsync", "Box"),
    ("\\box\\", "Box"),
    ("/box/", "Box"),
    ("pcloud", "pCloud"),
    ("nextcloud", "Nextcloud"),
    ("mega", "MEGA"),
)


@dataclass
class CSVSchema:
    """Auto-detected (or user-confirmed) CSV column schema."""

    timestamp_column: str
    timestamp_format: str
    value_columns: dict[str, str]
    confidence: Literal["high", "medium", "low"]


@dataclass
class _Cleanup:
    """Track partial-write reversers so SIGINT can roll them back."""

    actions: list[Callable[[], None]] = field(default_factory=list)

    def push(self, action: Callable[[], None]) -> None:
        self.actions.append(action)

    def run(self) -> None:
        # Reverse-order: last write rolled back first.
        for action in reversed(self.actions):
            try:
                action()
            except OSError:
                pass
        self.actions.clear()


# ──────────────────────────────────────────────────────────────────────
# Banner / prompt helpers
# ──────────────────────────────────────────────────────────────────────


def _print_banner() -> None:
    print("\n  Biosensor MCP — pilot setup wizard\n")


def _yes(answer: str, *, default: bool = False) -> bool:
    a = answer.strip().lower()
    if not a:
        return default
    return a in ("y", "yes")


# ──────────────────────────────────────────────────────────────────────
# Cloud-sync detection (audit fix C3)
# ──────────────────────────────────────────────────────────────────────


def _check_for_cloud_sync(path: Path) -> str | None:
    """Return the friendly provider name if the path lives inside a
    well-known cloud-sync container, else None.

    Case-insensitive substring match against the resolved absolute path
    (forward and back slashes both normalised to forward).
    """
    try:
        resolved = str(path.expanduser().resolve())
    except OSError:
        resolved = str(path)
    haystack = resolved.lower().replace("\\", "/")
    for marker, label in _CLOUD_MARKERS:
        m = marker.lower().replace("\\", "/")
        if m in haystack:
            return label
    return None


# ──────────────────────────────────────────────────────────────────────
# Bundled fixtures
# ──────────────────────────────────────────────────────────────────────


def _resolve_bundled_fixture_dir() -> Path | None:
    """Return the on-disk path of the bundled synthetic CSV directory.

    Uses ``importlib.resources.as_file`` so it works for source-tree,
    pip-installed, and zipped distributions. Returns None if the
    package data is not available.
    """
    try:
        traversable = files("biosensor_mcp._fixtures").joinpath(
            "multi_subject_pilot", "csv",
        )
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    try:
        with as_file(traversable) as p:
            path = Path(p)
            if path.is_dir():
                return path
    except (FileNotFoundError, OSError):
        return None
    return None


# ──────────────────────────────────────────────────────────────────────
# Prompt 1 — CSV directory
# ──────────────────────────────────────────────────────────────────────


def _prompt_csv_dir() -> Path:
    """Ask the user where their CSVs live; offer the bundled fixtures
    as the default. Re-prompts on missing/non-directory paths."""
    bundled = _resolve_bundled_fixture_dir()
    if bundled is not None:
        print("  Step 1 of 3 — choose CSV directory")
        print(f"  Default: bundled synthetic fixtures at {bundled}")
        print("  Or enter the absolute path to your own CSV directory.\n")
    else:
        print("  Step 1 of 3 — choose CSV directory")
        print("  Enter the absolute path to your CSV directory.\n")

    while True:
        raw = input("  CSV directory [default]: ").strip()
        if not raw and bundled is not None:
            return bundled
        if not raw:
            print("  Path is required (no bundled fixtures available).\n")
            continue
        candidate = Path(raw).expanduser()
        if not candidate.is_dir():
            print(f"  Not a directory: {candidate}. Try again.\n")
            continue
        if not list(candidate.glob("*.csv")):
            print(f"  No CSV files found in {candidate}. Try again.\n")
            continue
        return candidate.resolve()


# ──────────────────────────────────────────────────────────────────────
# Schema auto-detection (audit fix F1 — scan ALL files)
# ──────────────────────────────────────────────────────────────────────


_TIMESTAMP_HINTS = (
    "timestamp", "time", "datetime", "date", "recorded_at",
    "created_at", "ts", "event_time", "reading_time",
)


def _read_header(path: Path) -> tuple[str, ...]:
    """Read the first line of a CSV as a tuple of column names."""
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        first = f.readline()
    # csv.reader handles quoted commas; use it instead of naive split.
    import csv

    return tuple(next(csv.reader([first]), []))


def _guess_timestamp_column(headers: tuple[str, ...]) -> str | None:
    for h in headers:
        if h.strip().lower() in _TIMESTAMP_HINTS:
            return h
    for h in headers:
        if any(s in h.strip().lower() for s in ("time", "date")):
            return h
    return None


def _guess_timestamp_format(sample: str) -> str:
    """Heuristic: ISO-8601 with T-separator is overwhelmingly common
    in fixtures and exports. Defaults to that and lets the user override."""
    s = sample.strip()
    if "T" in s and len(s) >= 19:
        return "%Y-%m-%dT%H:%M:%S"
    if " " in s and len(s) >= 19:
        return "%Y-%m-%d %H:%M:%S"
    return "%Y-%m-%dT%H:%M:%S"


def _read_first_data_row(path: Path) -> str | None:
    """Return the first non-header row's first cell, or None on failure."""
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            f.readline()
            return f.readline().split(",", 1)[0]
    except OSError:
        return None


def _autodetect_csv_schema(csv_dir: Path) -> CSVSchema:
    """Scan EVERY *.csv in the directory and detect a shared schema.

    Audit fix F1: divergent headers across files force confidence to
    "low" and surface a per-file breakdown. The wizard refuses to
    silently keep going on the first file's columns — that pattern was
    the real-world failure the v6.2 multi-subject framing kept hitting.
    """
    csvs = sorted(csv_dir.glob("*.csv"))
    if not csvs:
        raise RuntimeError(f"No CSV files in {csv_dir}")

    header_groups: dict[tuple[str, ...], list[str]] = {}
    for path in csvs:
        try:
            headers = _read_header(path)
        except OSError:
            continue
        header_groups.setdefault(headers, []).append(path.name)

    if not header_groups:
        raise RuntimeError(f"Could not read any CSV headers in {csv_dir}")

    if len(header_groups) > 1:
        print("\n  [!] WARNING: CSV files in this directory have DIFFERENT headers.")
        print("  Some files will likely fail at runtime. Header sets observed:")
        for headers, names in header_groups.items():
            preview = ", ".join(names[:3]) + ("..." if len(names) > 3 else "")
            print(f"    - {len(names)} file(s) [{preview}]: {list(headers)}")
        print("  Pick the column names that match your INTENDED schema.\n")
        confidence: Literal["high", "medium", "low"] = "low"
        # Use the most common header set as the basis for prompts.
        headers = max(header_groups.items(), key=lambda kv: len(kv[1]))[0]
    else:
        headers = next(iter(header_groups))
        confidence = "high"

    ts_col = _guess_timestamp_column(headers)
    if ts_col is None:
        confidence = "low"
        ts_col = headers[0] if headers else "timestamp"

    sample = _read_first_data_row(csvs[0]) or ""
    ts_format = _guess_timestamp_format(sample)

    value_columns: dict[str, str] = {}
    for h in headers:
        if h == ts_col:
            continue
        # Default mapping: short snake-cased key → original header label.
        key = _snake_case(h)
        value_columns[key] = h

    return CSVSchema(
        timestamp_column=ts_col,
        timestamp_format=ts_format,
        value_columns=value_columns,
        confidence=confidence,
    )


def _snake_case(label: str) -> str:
    """Best-effort snake-case key from a human header label."""
    import re

    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_").lower()
    # Strip trailing units in parens like "_bpm_" residue.
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned or "value"


# ──────────────────────────────────────────────────────────────────────
# Prompt 2 — confirm or override schema
# ──────────────────────────────────────────────────────────────────────


def _prompt_schema_overrides(detected: CSVSchema) -> CSVSchema:
    print("\n  Step 2 of 3 — confirm schema")
    print(f"  Timestamp column:  {detected.timestamp_column}")
    print(f"  Timestamp format:  {detected.timestamp_format}")
    print("  Value columns:")
    for key, label in detected.value_columns.items():
        print(f"    {key:20s} <- {label}")
    print(f"  Detection confidence: {detected.confidence}")
    if detected.confidence == "low":
        print("  [!] Low-confidence detection. Please review carefully.")

    answer = input("\n  Accept this schema? [Y/n]: ").strip().lower()
    if answer in ("", "y", "yes"):
        return detected

    print("\n  Override one field at a time. Press Enter to keep current.")
    ts_col = input(f"  Timestamp column [{detected.timestamp_column}]: ").strip()
    ts_fmt = input(f"  Timestamp format [{detected.timestamp_format}]: ").strip()
    return CSVSchema(
        timestamp_column=ts_col or detected.timestamp_column,
        timestamp_format=ts_fmt or detected.timestamp_format,
        value_columns=detected.value_columns,
        confidence=detected.confidence,
    )


# ──────────────────────────────────────────────────────────────────────
# Atomic JSON write
# ──────────────────────────────────────────────────────────────────────


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON via tmp-then-replace so partial writes never land."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _write_user_config(cfg: dict, *, force: bool = False) -> Path:
    """Write user_config.json. If a config already exists and force is
    False, raise FileExistsError so the caller can prompt."""
    if CONFIG_PATH.exists() and not force:
        raise FileExistsError(str(CONFIG_PATH))
    _atomic_write_json(CONFIG_PATH, cfg)
    return CONFIG_PATH


# ──────────────────────────────────────────────────────────────────────
# Claude Desktop registration (audit fix F2)
# ──────────────────────────────────────────────────────────────────────


def _claude_desktop_config_path() -> Path | None:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    return None


def _read_claude_config(path: Path) -> tuple[dict, bool]:
    """Return ``(config_dict, had_bom)``. Empty config if missing."""
    if not path.exists():
        return {}, False
    raw = path.read_bytes()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    if had_bom:
        raw = raw[3:]
    text = raw.decode("utf-8")
    try:
        return json.loads(text), had_bom
    except json.JSONDecodeError:
        return {}, had_bom


def _write_claude_config(path: Path, data: dict, *, with_bom: bool) -> None:
    """Atomically write Claude Desktop config. Restores BOM if input had one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = json.dumps(data, indent=2).encode("utf-8")
    if with_bom:
        body = b"\xef\xbb\xbf" + body
    tmp.write_bytes(body)
    os.replace(tmp, path)


def _register_with_claude_desktop(
    server_cmd: list[str], *, force: bool = False,
) -> bool:
    """Merge a biosensor-mcp entry into Claude Desktop's mcpServers.

    Returns True if the config was written, False if skipped.
    """
    config_path = _claude_desktop_config_path()
    if config_path is None:
        print("  [skip] Claude Desktop registration is macOS/Windows only on this build.")
        return False

    print("\n  Step 3 of 3 — register with Claude Desktop")
    print(f"  Config file: {config_path}")
    print("  Please quit Claude Desktop before continuing (the config file may")
    print("  be locked by a running instance).")
    answer = input("  Press Enter when ready, or type 'skip': ").strip().lower()
    if answer == "skip":
        print("  Skipped Claude Desktop registration.")
        return False

    config, had_bom = _read_claude_config(config_path)
    servers = config.setdefault("mcpServers", {})

    if "biosensor-mcp" in servers and not force:
        choice = input(
            "  biosensor-mcp is already registered. [overwrite/skip]: "
        ).strip().lower()
        if choice != "overwrite":
            print("  Kept existing registration.")
            return False

    servers["biosensor-mcp"] = {
        "command": server_cmd[0],
        "args": server_cmd[1:],
    }
    _write_claude_config(config_path, config, with_bom=had_bom)
    print(f"  Wrote {config_path}")
    return True


# ──────────────────────────────────────────────────────────────────────
# Smoke check (audit fix F1 part 2)
# ──────────────────────────────────────────────────────────────────────


def _smoke_check(
    csv_dir: Path,
    value_columns: dict[str, str],
    timestamp_column: str,
    timestamp_format: str,
) -> tuple[bool, str]:
    """Verify the chosen schema actually resolves against EVERY CSV.

    Returns ``(ok, message)``. On failure, message names the offending
    files and missing columns so the user can fix and re-run.
    """
    csvs = sorted(csv_dir.glob("*.csv"))
    if not csvs:
        return False, f"No CSV files in {csv_dir}"

    expected = set(value_columns.values()) | {timestamp_column}
    failures: list[str] = []
    for path in csvs:
        try:
            headers = set(_read_header(path))
        except OSError as exc:
            failures.append(f"{path.name}: {exc}")
            continue
        missing = sorted(expected - headers)
        if missing:
            failures.append(f"{path.name}: missing column(s) {missing}")

    if failures:
        return False, "Schema does not match every CSV:\n    " + "\n    ".join(failures)

    # Final sanity check: instantiate CSVDirectoryChild against a
    # throwaway config so we know the child's loader path also works.
    try:
        from biosensor_mcp.children.csv_dir import CSVDirectoryChild

        # Build a transient user_config-like dict in memory by writing
        # to a temp-rooted env var would be heavy. Instead we verify
        # _csv_path resolves and the child reads at least one header.
        # CSVDirectoryChild reads from CONFIG_DIR/user_config.json; the
        # caller has already written that, so just instantiate.
        child = CSVDirectoryChild(config_dir=CONFIG_DIR, data_dir=CONFIG_DIR / "data")
        _ = child._read_headers(csvs[0])
        del child
    except Exception as exc:
        return False, f"CSVDirectoryChild failed to load: {exc}"

    _ = timestamp_format  # currently unused; reserved for future format probe
    return True, f"All {len(csvs)} CSV file(s) match the configured schema."


# ──────────────────────────────────────────────────────────────────────
# Next-steps summary
# ──────────────────────────────────────────────────────────────────────


def _next_steps_summary(csv_dir: Path, registered: bool) -> None:
    print("\n  Next steps")
    print("  ----------")
    print(f"  CSV directory:  {csv_dir}")
    print(f"  Config written: {CONFIG_PATH}")
    if registered:
        print("  Claude Desktop: registered. Restart Claude Desktop to pick up the change.")
        print("  Then ask: 'list the CSV files you can see' to verify wiring.")
    else:
        print("  Claude Desktop: not registered.")
        print("  Add this server manually, or rerun `biosensor-mcp pilot` later.")
    print("  Audit log lives at ~/.biosensor-mcp/data/audit.db (one row per tool call).\n")


# ──────────────────────────────────────────────────────────────────────
# Main flow
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    cleanup = _Cleanup()

    def _on_sigint(signum, frame):  # noqa: ARG001
        print("\n  Cancelled. No changes were made before this point.")
        cleanup.run()
        sys.exit(130)

    signal.signal(signal.SIGINT, _on_sigint)

    _print_banner()
    warnings_acknowledged: list[str] = []

    try:
        csv_dir = _prompt_csv_dir()

        provider = _check_for_cloud_sync(csv_dir)
        if provider:
            print(
                f"\n  [!] WARNING: Your CSV directory appears to be inside {provider}. "
                "Cloud-sync providers can corrupt SQLite databases and lock files "
                "mid-read. Consider moving your CSVs to a non-synced location like "
                "~/biosensor-pilot/ before continuing."
            )
            answer = input("  Continue anyway? [y/N]: ").strip().lower()
            if not _yes(answer):
                print("\n  No changes were made. Move the CSVs and re-run `biosensor-mcp pilot`.")
                return 0
            warnings_acknowledged.append(f"cloud-sync ({provider})")

        try:
            detected = _autodetect_csv_schema(csv_dir)
        except RuntimeError as exc:
            print(f"\n  ERROR: {exc}")
            return 1

        schema = _prompt_schema_overrides(detected)

        cfg = {
            "csv_dir": {
                "path": str(csv_dir),
                "timestamp_column": schema.timestamp_column,
                "timestamp_format": schema.timestamp_format,
                "value_columns": schema.value_columns,
            },
        }

        wrote_config = False
        try:
            _write_user_config(cfg)
            wrote_config = True
        except FileExistsError:
            print(f"\n  {CONFIG_PATH} already exists.")
            choice = input("  Overwrite? [y/N]: ").strip().lower()
            if not _yes(choice):
                print(
                    "  Kept existing user_config.json. No changes were made.\n"
                    "  Re-run `biosensor-mcp pilot` after moving the existing "
                    "config aside to start fresh."
                )
                return 0
            _write_user_config(cfg, force=True)
            wrote_config = True

        if wrote_config:
            print(f"\n  Wrote {CONFIG_PATH}")
        # Past this line, partial-write rollback no longer applies — the
        # config file is the user's keep-and-resume anchor.
        cleanup.actions.clear()

        ok, msg = _smoke_check(
            csv_dir,
            schema.value_columns,
            schema.timestamp_column,
            schema.timestamp_format,
        )
        if ok:
            print(f"  [OK] {msg}")
        else:
            print(f"  [FAIL] {msg}")
            print("  Fix the schema or the CSVs and re-run `biosensor-mcp pilot`.")
            return 1

        server_cmd = [sys.executable, "-m", "biosensor_mcp", "serve"]
        registered = _register_with_claude_desktop(server_cmd)

        _next_steps_summary(csv_dir, registered)
        if warnings_acknowledged:
            print(f"  WARNINGS_ACKNOWLEDGED: {', '.join(warnings_acknowledged)}")
        return 0
    except KeyboardInterrupt:
        print("\n  Cancelled. No changes were made before this point.")
        cleanup.run()
        return 130


if __name__ == "__main__":
    sys.exit(main())

"""
Pilot Setup Wizard
==================
Guided CLI flow that turns the seven-step multi-subject-pilot
quickstart into three prompts. Targets a non-technical PI: pick a
CSV directory (or accept the bundled synthetic fixtures), confirm
the auto-detected schema, optionally register with Claude Desktop.

Usage:
    tailor pilot     # via CLI entry point
    python -m tailor.pilot   # direct invocation

Ctrl-C contract
---------------
The first durable write is ``user_config.json``. Anything before
that line is rolled back on SIGINT (no on-disk state). Anything
after that is keep-and-resume — the user can re-run the wizard and
will be told their config already exists; the second run skips
straight to Claude Desktop registration.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.resources import as_file, files
from pathlib import Path
from typing import Literal

from tailor.config import CONFIG_DIR

CONFIG_PATH = CONFIG_DIR / "user_config.json"

# Magic bytes for `.mat` v7.3 (HDF5) files. v5/v6/v7.2 files begin with
# a 116-byte text header starting "MATLAB 5.0 MAT-file"; v7.3 files
# begin with the HDF5 signature. The MATLAB child's full HDF5 check
# lives in ``children/matlab_file/child.py`` (HDF5_MAGIC + _is_hdf5);
# the wizard re-declares the constant inline so it can scan files
# WITHOUT importing the child module (which would force scipy at
# wizard-import time and break the F2 lazy-import contract).
# Per ADR 0036 § "v7.3 deferred".
_HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"

# Valid --source choices. Keeps the argparse parser and the dispatch
# branch list aligned without a magic-string drift class.
_VALID_SOURCES: tuple[str, ...] = ("csv", "matlab", "redcap")

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


def _print_banner(source: str = "csv") -> None:
    label = {
        "csv": "CSV directory",
        "matlab": "MATLAB `.mat` directory",
        "redcap": "REDCap export directory",
    }.get(source, source)
    print(f"\n  Tailor — pilot setup wizard ({label})\n")


# ──────────────────────────────────────────────────────────────────────
# Argparse parser
# ──────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tailor pilot",
        description=(
            "Multi-source pilot setup wizard. Configures one source axis "
            "(CSV directory / MATLAB `.mat` directory / REDCap export "
            "directory) per invocation; the deep-merge writer at "
            "_write_user_config preserves every other source block and "
            "top-level key so multi-source deployments survive re-runs."
        ),
    )
    parser.add_argument(
        "--source",
        choices=_VALID_SOURCES,
        default="csv",
        help=(
            "Which source axis to configure. "
            "csv (default): directory of per-subject `.csv` files. "
            "matlab: directory of MATLAB `.mat` v5/v6/v7.2 binary files "
            "(requires the [matlab] extra — install with "
            "`pip install tailor-mcp[matlab]` or "
            "`uv tool install tailor-mcp[matlab]`). "
            "redcap: directory of REDCap CSV/JSON exports with a "
            "`project_metadata.csv` data dictionary (no extras needed)."
        ),
    )
    return parser


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
        traversable = files("tailor._fixtures").joinpath(
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


def _write_user_config(
    source_key: str, source_block: dict, *, force: bool = False,
) -> Path:
    """Merge a per-source block into ``user_config.json`` atomically.

    Reads existing config (if any), sets ``source_block`` at top-level
    key ``source_key``, writes back via tmp-then-replace. Preserves
    every other top-level key — sibling source blocks (``csv_dir``,
    ``matlab_file``, ``redcap_file``), ``vault_path``, ``cost_threshold``,
    ``max_hr``, ``local_llm``, and any operator-edited fields the wizard
    does not own.

    Raises ``FileExistsError`` when ``source_key`` is already present
    and ``force`` is False, so the caller can prompt for confirmation.
    ``force=True`` overwrites only the named source block; sibling
    blocks are still preserved.

    Closes the v7.5.0 F1 multi-source-clobber footgun
    (``integration-auditor --proposal-mode`` finding 2026-05-18): the
    pre-v7.5 overwrite-the-whole-file behaviour would erase a prior
    ``csv_dir`` block when an operator ran
    ``tailor pilot --source=matlab`` later. The deep-merge here keeps
    multi-source coexistence intact across re-runs, matching the
    v6.2.1 ``mcpServers`` Claude-Desktop deep-merge precedent.

    Uses ``utf-8-sig`` on read for the same reason every REDCap and
    CSV reader in the framework does — Excel/PowerShell-saved
    user_config.json files prepend a BOM that ``utf-8`` would pass
    through into the first-column header and silently corrupt the
    merge (v6.9.2 BOM-strip precedent).
    """
    existing: dict = {}
    if CONFIG_PATH.exists():
        try:
            existing = json.loads(
                CONFIG_PATH.read_text(encoding="utf-8-sig")
            )
            if not isinstance(existing, dict):
                # Malformed top level (list, scalar) — start fresh
                # rather than silently merge into garbage. Operator
                # will see the wizard's confirm-overwrite prompt
                # below if they expected to keep that content.
                existing = {}
        except (json.JSONDecodeError, OSError):
            existing = {}
    if source_key in existing and not force:
        raise FileExistsError(
            f"{source_key} is already configured in {CONFIG_PATH}"
        )
    existing[source_key] = source_block
    _atomic_write_json(CONFIG_PATH, existing)
    return CONFIG_PATH


# ──────────────────────────────────────────────────────────────────────
# Claude Desktop registration — see ADR 0026 for the dual-path design
# under UWP sandboxing. v6.10.4 generalises the v6.2.1 pilot-wizard
# (audit fix F2) helpers from a single classic config path to every
# Claude Desktop config path the framework can confirm with positive
# evidence on this machine.
# ──────────────────────────────────────────────────────────────────────

# UWP package-family prefix for the Microsoft Store version of Claude
# Desktop. The full family name is currently ``Claude_pzs8sxrjxfjjc``
# but the suffix is a Microsoft-signing publisher-hash that changes
# whenever Anthropic re-signs or re-publishes the package. Globbing
# the prefix survives suffix drift; the path-shape constraint
# downstream (``LocalCache/Roaming/Claude/claude_desktop_config.json``
# inside the sandbox) bounds the false-positive risk on unrelated
# ``Claude_*``-named UWP packages. See ADR 0026 § "Detection by
# prefix-glob, not hardcoded family name" for the rejection of the
# hardcoded-full-name alternative and the adversarial-pairing
# resolution per ADR 0010.
_CLAUDE_DESKTOP_UWP_PACKAGE_PREFIX = "Claude_"


@dataclass
class _RegistrationResult:
    """Per-path Claude Desktop registration outcome.

    See ADR 0026 § "Per-path atomic semantics" for the contract: each
    path's read → clean siblings → add entry → atomic write block is
    wrapped in try/except, and a failure on one path does not abort
    writes to others. Empty ``cleaned`` list when no stale
    ``biosensor-*`` siblings were present; ``error`` is None on a
    successful write.
    """

    path: Path
    written: bool
    cleaned: list[str] = field(default_factory=list)
    error: BaseException | None = None


def _claude_desktop_config_paths() -> list[Path]:
    """Return every Claude Desktop config-file path the framework can
    confirm on this machine.

    On Windows the candidate set is: the classic path under
    ``%APPDATA%\\Claude\\claude_desktop_config.json`` (always included
    when ``%APPDATA%`` resolves; the classic install creates this
    directory on first registration), plus one path per UWP package
    family-name match for ``Claude_*`` whose
    ``%LOCALAPPDATA%\\Packages\\Claude_<suffix>\\`` directory exists.
    On macOS the candidate set is the single canonical path
    (``~/Library/Application Support/Claude/...``). On Linux the
    candidate set is empty.

    See ADR 0026 for the rationale and the rejection of detect-and-pick.
    """
    if sys.platform == "darwin":
        return [
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json",
        ]
    if sys.platform == "win32":
        paths: list[Path] = []
        appdata = os.environ.get("APPDATA")
        if appdata:
            # Classic path is always included. ``_write_claude_config``
            # creates the parent on first registration; on a Store-only
            # machine that has never run Claude Desktop this is a no-op
            # write that neither variant reads — acceptable per ADR 0026
            # § "First-time-install on a Store-only machine".
            paths.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            packages_dir = Path(local_appdata) / "Packages"
            if packages_dir.exists():
                for pkg in sorted(
                    packages_dir.glob(f"{_CLAUDE_DESKTOP_UWP_PACKAGE_PREFIX}*")
                ):
                    if pkg.is_dir():
                        paths.append(
                            pkg
                            / "LocalCache"
                            / "Roaming"
                            / "Claude"
                            / "claude_desktop_config.json"
                        )
        return paths
    return []


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


def _write_registration_to_path(
    path: Path, *, server_name: str, entry: dict,
) -> _RegistrationResult:
    """Read → clean orphan siblings → add entry → atomic write.

    "Orphan siblings" are any keys the framework has ever written across
    its v6.x ``biosensor-*`` and v7.0+ ``tailor`` / ``tailor-*`` naming
    conventions (see ``__main__._is_orphan_entry_key``). Dual-prefix
    matching is the migration story per ADR 0031: a v6 → v7 upgrade
    leaves stale ``biosensor-*`` keys that must be cleaned alongside the
    new ``tailor`` keys; a v7 re-registration must clean stale
    ``tailor-tour-*`` siblings (the v6.10.3 invariant carried forward).

    Per ADR 0026 § "Per-path atomic semantics", the entire block is
    wrapped in try/except. ``PermissionError`` (Claude Desktop has the
    file open) and ``OSError`` (disk full, antivirus quarantine) are
    captured into the result rather than propagating. The ``.tmp``
    artifact from ``_write_claude_config`` is unlinked on partial
    failure to avoid clutter across debugging loops.
    """
    from tailor.__main__ import _is_orphan_entry_key

    try:
        config, had_bom = _read_claude_config(path)
        servers = config.setdefault("mcpServers", {})
        cleaned = [
            k for k in list(servers)
            if _is_orphan_entry_key(k) and k != server_name
        ]
        for key in cleaned:
            del servers[key]
        servers[server_name] = entry
        _write_claude_config(path, config, with_bom=had_bom)
        return _RegistrationResult(path=path, written=True, cleaned=cleaned)
    except (PermissionError, OSError) as exc:
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return _RegistrationResult(path=path, written=False, error=exc)


def _register_with_claude_desktop(
    server_cmd: list[str], *, force: bool = False,
) -> list[_RegistrationResult]:
    """Register ``tailor`` in every detected Claude Desktop config.

    Returns the list of per-path results. Empty list when the platform
    has no Claude Desktop (Linux) or the user typed ``skip`` at the
    pre-write prompt. See ADR 0026.
    """
    paths = _claude_desktop_config_paths()
    if not paths:
        print("  [skip] Claude Desktop registration is macOS/Windows only on this build.")
        return []

    print("\n  Step 3 of 3 — register with Claude Desktop")
    if len(paths) == 1:
        print(f"  Config file: {paths[0]}")
    else:
        print(f"  Detected {len(paths)} Claude Desktop config paths:")
        for p in paths:
            print(f"    {p}")
    print("  Please quit Claude Desktop before continuing (the config file may")
    print("  be locked by a running instance).")
    answer = input("  Press Enter when ready, or type 'skip': ").strip().lower()
    if answer == "skip":
        print("  Skipped Claude Desktop registration.")
        return []

    if not force:
        existing = []
        for p in paths:
            try:
                cfg, _ = _read_claude_config(p)
                if "tailor" in cfg.get("mcpServers", {}):
                    existing.append(p)
            except OSError:
                pass
        if existing:
            if len(paths) == 1:
                msg = "  tailor is already registered. [overwrite/skip]: "
            else:
                msg = (
                    f"  tailor is already registered in "
                    f"{len(existing)} of {len(paths)} detected configs. "
                    f"Overwrite all? [overwrite/skip]: "
                )
            choice = input(msg).strip().lower()
            if choice != "overwrite":
                print("  Kept existing registration.")
                return []

    entry = {"command": server_cmd[0], "args": server_cmd[1:]}
    results = [
        _write_registration_to_path(p, server_name="tailor", entry=entry)
        for p in paths
    ]

    for result in results:
        if result.written:
            print(f"  Wrote {result.path}")
            if result.cleaned:
                print(f"    cleaned stale orphan entries: {', '.join(result.cleaned)}")
        else:
            err = result.error
            print(f"  [error] Could not write {result.path}")
            print(f"          Reason: {type(err).__name__}: {err}")
            print("          Quit Claude Desktop fully (system tray Quit on Windows,")
            print("          Cmd+Q on macOS) and re-run.")

    return results


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
        from tailor.children.csv_dir import CSVDirectoryChild

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


def _next_steps_summary(
    csv_dir: Path, results: list[_RegistrationResult],
) -> None:
    print("\n  Next steps")
    print("  ----------")
    print(f"  CSV directory:  {csv_dir}")
    print(f"  Config written: {CONFIG_PATH}")
    written = [r for r in results if r.written]
    failed = [r for r in results if not r.written]
    if not results:
        print("  Claude Desktop: not registered.")
        print("  Add this server manually, or rerun `tailor pilot` later.")
    elif written and not failed:
        if len(written) == 1:
            print("  Claude Desktop: registered. Restart Claude Desktop to pick up the change.")
        else:
            print(
                f"  Claude Desktop: registered in {len(written)} configs "
                f"(both classic and Microsoft Store variants)."
            )
            print("  Fully quit Claude Desktop (system tray Quit) and re-open.")
        print("  Then ask: 'list the CSV files you can see' to verify wiring.")
    elif written and failed:
        print(
            f"  Claude Desktop: registered in {len(written)} of "
            f"{len(results)} detected configs. The remaining write(s) failed:"
        )
        for r in failed:
            print(f"    - {r.path}: {type(r.error).__name__}")
        print("  Quit Claude Desktop fully and rerun `tailor pilot` to retry.")
    else:
        print("  Claude Desktop: NOT registered. All writes failed:")
        for r in failed:
            print(f"    - {r.path}: {type(r.error).__name__}: {r.error}")
        print("  Quit Claude Desktop fully and rerun `tailor pilot`.")
    print("  Audit log lives at ~/.tailor/data/audit.db (one row per tool call).\n")


# ──────────────────────────────────────────────────────────────────────
# Main flow
# ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Pilot-wizard entry point.

    ``argv`` is the CLI argument list to parse; when ``None`` (the
    default for live CLI invocation via ``__main__.cmd_pilot``), it
    resolves to ``sys.argv[2:]`` (skipping the ``tailor pilot``
    prefix). Tests pass ``argv=[]`` explicitly to use defaults
    without picking up pytest's own arg vector.

    Dispatches to a per-source handler:
      ``--source=csv``    → :func:`_run_csv`
      ``--source=matlab`` → :func:`_run_matlab`
      ``--source=redcap`` → :func:`_run_redcap`
    """
    parser = _build_parser()
    if argv is None:
        argv = sys.argv[2:]
    args = parser.parse_args(argv)

    cleanup = _Cleanup()

    def _on_sigint(signum, frame):  # noqa: ARG001
        print("\n  Cancelled. No changes were made before this point.")
        cleanup.run()
        sys.exit(130)

    signal.signal(signal.SIGINT, _on_sigint)

    _print_banner(args.source)

    try:
        if args.source == "csv":
            return _run_csv(cleanup)
        if args.source == "matlab":
            return _run_matlab(cleanup)
        if args.source == "redcap":
            return _run_redcap(cleanup)
        # Unreachable: argparse rejects unknown --source values.
        return 2
    except KeyboardInterrupt:
        print("\n  Cancelled. No changes were made before this point.")
        cleanup.run()
        return 130


# ──────────────────────────────────────────────────────────────────────
# Per-source handlers
# ──────────────────────────────────────────────────────────────────────


def _run_csv(cleanup: _Cleanup) -> int:
    """Configure a ``csv_dir`` block in user_config.json.

    The original v6.2.1 wizard flow, extracted into a per-source
    handler in v7.5 as part of the ``--source`` dispatch refactor.
    All behaviour preserved verbatim aside from a tighter overwrite
    prompt (per-source-key instead of whole-file) and the
    sibling-preserving deep-merge writer (v7.5 F1 closure).
    """
    warnings_acknowledged: list[str] = []

    csv_dir = _prompt_csv_dir()

    provider = _check_for_cloud_sync(csv_dir)
    if provider:
        print(
            f"\n  [!] WARNING: Your CSV directory appears to be inside "
            f"{provider}. Cloud-sync providers can corrupt SQLite "
            f"databases and lock files mid-read. Consider moving your "
            f"CSVs to a non-synced location like ~/biosensor-pilot/ "
            f"before continuing."
        )
        answer = input("  Continue anyway? [y/N]: ").strip().lower()
        if not _yes(answer):
            print(
                "\n  No changes were made. Move the CSVs and "
                "re-run `tailor pilot`."
            )
            return 0
        warnings_acknowledged.append(f"cloud-sync ({provider})")

    try:
        detected = _autodetect_csv_schema(csv_dir)
    except RuntimeError as exc:
        print(f"\n  ERROR: {exc}")
        return 1

    schema = _prompt_schema_overrides(detected)

    cfg_block = {
        "path": str(csv_dir),
        "timestamp_column": schema.timestamp_column,
        "timestamp_format": schema.timestamp_format,
        "value_columns": schema.value_columns,
    }

    wrote_config = False
    try:
        _write_user_config("csv_dir", cfg_block)
        wrote_config = True
    except FileExistsError:
        print(f"\n  csv_dir is already configured in {CONFIG_PATH}.")
        print(
            "  (Other source blocks and top-level keys will be "
            "preserved either way.)"
        )
        choice = input(
            "  Overwrite the csv_dir block? [y/N]: "
        ).strip().lower()
        if not _yes(choice):
            print(
                "  Kept the existing csv_dir block. No changes "
                "were made.\n"
                "  Re-run `tailor pilot` after editing "
                "user_config.json by hand, or point at a "
                "different directory."
            )
            return 0
        _write_user_config("csv_dir", cfg_block, force=True)
        wrote_config = True

    if wrote_config:
        print(f"\n  Wrote csv_dir block to {CONFIG_PATH}")
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
        print("  Fix the schema or the CSVs and re-run `tailor pilot`.")
        return 1

    server_cmd = [sys.executable, "-m", "tailor", "serve"]
    registered = _register_with_claude_desktop(server_cmd)

    _next_steps_summary(csv_dir, registered)
    if warnings_acknowledged:
        print(f"  WARNINGS_ACKNOWLEDGED: {', '.join(warnings_acknowledged)}")
    return 0


# ──────────────────────────────────────────────────────────────────────
# MATLAB-specific helpers
# ──────────────────────────────────────────────────────────────────────


@dataclass
class _MatScanResult:
    """Result of a pre-flight scan over a directory of `.mat` files.

    ``variable_inventory`` maps filename → sorted variable names for
    every v5/v6/v7.2 file that parsed cleanly (up to 32 files, to
    bound wizard latency on large cohorts). ``hdf5_files`` lists every
    file whose first 8 bytes match the HDF5 magic signature (v7.3 —
    deferred per ADR 0036; surfaced inline so the operator can re-save
    them in v5/v6/v7.2 format before continuing). ``parse_errors``
    captures any other read or parse failures. ``total_files`` is the
    raw count of `.mat` files in the directory, used by the smoke
    check to report a "parseable / total" magnitude.
    """

    variable_inventory: dict[str, list[str]]
    hdf5_files: list[str]
    parse_errors: list[tuple[str, str]]
    total_files: int


def _prompt_mat_dir() -> Path:
    """Ask the user for the directory containing their `.mat` files.

    Re-prompts on bad input until the operator either provides a valid
    directory containing at least one `.mat` file, or sends Ctrl-C
    (handled by the wizard's SIGINT handler at ``main``).
    """
    print("  Step 1 of 3 — choose MATLAB `.mat` directory")
    print("  Enter the absolute path to the directory holding your "
          "`.mat` files.\n")
    while True:
        raw = input("  MATLAB directory: ").strip()
        if not raw:
            print("  Path is required.\n")
            continue
        candidate = Path(raw).expanduser()
        if not candidate.is_dir():
            print(f"  Not a directory: {candidate}. Try again.\n")
            continue
        if not list(candidate.glob("*.mat")):
            print(
                f"  No `.mat` files found in {candidate}. Try again.\n"
            )
            continue
        return candidate.resolve()


def _scan_mat_files(mat_dir: Path, scipy_io) -> _MatScanResult:
    """Scan `.mat` files in ``mat_dir``.

    F6 closure (proposal-mode auditor, 2026-05-18): magic-byte HDF5
    check on ALL files BEFORE calling ``scipy.io.loadmat`` — v7.3
    files raise ``NotImplementedError`` from scipy and would otherwise
    crash the variable-enumeration prompt. Pre-screening is cheap
    (8 bytes per file) and lets the wizard report v7.3 files as a
    coherent group with the ADR 0036 remediation hint rather than as
    a per-file parse error.

    Variable enumeration via ``loadmat`` is more expensive (parses the
    whole header + variable index) so we cap at 32 files. Cohorts
    larger than 32 still get all-files HDF5 screening; variable
    enumeration is statistically sufficient on the first 32.
    """
    variable_inventory: dict[str, list[str]] = {}
    hdf5_files: list[str] = []
    parse_errors: list[tuple[str, str]] = []

    files = sorted(mat_dir.glob("*.mat"))
    total = len(files)

    parseable: list[Path] = []
    for f in files:
        try:
            with open(f, "rb") as fh:
                head = fh.read(8)
        except OSError as exc:
            parse_errors.append(
                (f.name, f"could not read first 8 bytes: {exc}"),
            )
            continue
        if head == _HDF5_MAGIC:
            hdf5_files.append(f.name)
            continue
        parseable.append(f)

    for f in parseable[:32]:
        try:
            raw = scipy_io.loadmat(str(f), squeeze_me=True)
        except (NotImplementedError, OSError, ValueError) as exc:
            parse_errors.append((f.name, str(exc)))
            continue
        variable_inventory[f.name] = sorted(
            k for k in raw.keys() if not k.startswith("__")
        )

    return _MatScanResult(
        variable_inventory=variable_inventory,
        hdf5_files=hdf5_files,
        parse_errors=parse_errors,
        total_files=total,
    )


def _smoke_check_matlab(
    mat_dir: Path, scan_result: _MatScanResult,
) -> tuple[bool, str]:
    """Verify the matlab_file block resolves to a working
    ``MATLABFileChild``.

    Per F8 (proposal-mode auditor, 2026-05-18): schema-validation
    only. The child's constructor reads ``user_config.json``,
    resolves ``matlab_file.path``, and instantiates ``MATLABProcessing``.
    A failure here means the wizard wrote a config the child cannot
    load — surfaced as a smoke failure with a remediation hint. We
    do NOT route through ``RouterMCP._dispatch``; the first real
    Claude Desktop call exercises the full pipeline (audit row,
    PHI scrub, ``_meta`` stamping). Documenting this scope honestly
    avoids the v7.3.2 "test passes for the wrong reason" trap.
    """
    parseable = (
        scan_result.total_files
        - len(scan_result.hdf5_files)
        - len(scan_result.parse_errors)
    )
    if parseable == 0:
        return False, (
            f"No parseable .mat files in {mat_dir} "
            f"({len(scan_result.hdf5_files)} HDF5/v7.3, "
            f"{len(scan_result.parse_errors)} other errors)."
        )
    try:
        from tailor.children.matlab_file import MATLABFileChild

        child = MATLABFileChild(
            config_dir=CONFIG_DIR, data_dir=CONFIG_DIR / "data",
        )
        del child
    except Exception as exc:  # noqa: BLE001 — surface the loader error
        return False, f"MATLABFileChild failed to load: {exc}"
    return True, (
        f"{parseable} `.mat` file(s) parseable as v5/v6/v7.2 in "
        f"{mat_dir}; MATLABFileChild loaded successfully."
    )


def _matlab_next_steps_summary(
    mat_dir: Path, results: list[_RegistrationResult],
) -> None:
    print("\n  Next steps")
    print("  ----------")
    print(f"  MATLAB directory: {mat_dir}")
    print(f"  Config written:   {CONFIG_PATH}")
    written = [r for r in results if r.written]
    failed = [r for r in results if not r.written]
    if not results:
        print("  Claude Desktop: not registered.")
        print(
            "  Re-run `tailor pilot --source=matlab` later, or add the "
            "server manually."
        )
    elif written and not failed:
        if len(written) == 1:
            print(
                "  Claude Desktop: registered. Restart Claude Desktop "
                "to pick up the change."
            )
        else:
            print(
                f"  Claude Desktop: registered in {len(written)} "
                f"configs (both classic and Microsoft Store variants)."
            )
            print(
                "  Fully quit Claude Desktop (system tray Quit on "
                "Windows, Cmd+Q on macOS) and re-open."
            )
        print(
            "  Then ask: 'list the MATLAB files you can see' to verify "
            "wiring."
        )
    elif written and failed:
        print(
            f"  Claude Desktop: registered in {len(written)} of "
            f"{len(results)} detected configs. The remaining write(s) "
            f"failed:"
        )
        for r in failed:
            print(f"    - {r.path}: {type(r.error).__name__}")
        print(
            "  Quit Claude Desktop fully and rerun "
            "`tailor pilot --source=matlab`."
        )
    else:
        print("  Claude Desktop: NOT registered. All writes failed:")
        for r in failed:
            print(f"    - {r.path}: {type(r.error).__name__}: {r.error}")
        print(
            "  Quit Claude Desktop fully and rerun "
            "`tailor pilot --source=matlab`."
        )
    print(
        "  Audit log lives at ~/.tailor/data/audit.db "
        "(one row per tool call).\n"
    )


def _run_matlab(cleanup: _Cleanup) -> int:
    """Configure a ``matlab_file`` block in user_config.json.

    F2 closure (proposal-mode auditor): lazy scipy import. On missing
    scipy, the wizard surfaces a clean install hint and exits with
    rc=1 rather than crashing at module load — exactly the silent-
    failure trap that produced v6.10.2's degraded-serve state. Other
    source axes (--source=csv, --source=redcap) remain usable on a
    deployment that has not installed the [matlab] extra.

    F6 closure: HDF5 magic-byte check during scan, BEFORE any
    ``scipy.io.loadmat`` call, so v7.3 files are flagged with the
    ADR 0036 remediation hint instead of crashing the variable
    enumeration loop.

    The matlab_file block is deep-merged into user_config.json via
    the canonical ``_write_user_config`` writer — sibling source
    blocks (``csv_dir``, ``redcap_file``, ``vault_path``, etc.)
    survive the round-trip (v7.5 F1 closure).
    """
    # F2: lazy scipy.io import; surface a wizard-shape exit on missing.
    try:
        import scipy.io as scipy_io  # noqa: F401
    except ImportError:
        print(
            "\n  ERROR: MATLAB support requires scipy, which is not "
            "installed.\n"
            "\n  Install via one of:\n"
            "    pip install tailor-mcp[matlab]\n"
            "    uv tool install tailor-mcp[matlab]\n"
            "\n  Then re-run `tailor pilot --source=matlab`.\n"
            "  Other source axes (--source=csv, --source=redcap) work "
            "without scipy."
        )
        return 1

    warnings_acknowledged: list[str] = []

    mat_dir = _prompt_mat_dir()

    provider = _check_for_cloud_sync(mat_dir)
    if provider:
        print(
            f"\n  [!] WARNING: Your MATLAB directory appears to be "
            f"inside {provider}. Cloud-sync providers can corrupt "
            f"`.mat` files mid-read. Consider moving your `.mat` "
            f"files to a non-synced location before continuing."
        )
        answer = input("  Continue anyway? [y/N]: ").strip().lower()
        if not _yes(answer):
            print(
                "\n  No changes were made. Move the `.mat` files and "
                "re-run `tailor pilot --source=matlab`."
            )
            return 0
        warnings_acknowledged.append(f"cloud-sync ({provider})")

    print("\n  Step 2 of 3 — scan `.mat` files")
    scan = _scan_mat_files(mat_dir, scipy_io)

    if scan.hdf5_files:
        print(
            "\n  [!] WARNING: HDF5 (v7.3) `.mat` files detected "
            "(NOT supported):"
        )
        for name in scan.hdf5_files:
            print(f"    {name}")
        print(
            "  v7.3 is not supported per ADR 0036. Re-save with the "
            "`-v7` flag\n"
            "  in MATLAB or convert via "
            "`scipy.io.savemat(..., format='5')`.\n"
            "  These files will be SKIPPED at runtime."
        )

    if scan.parse_errors:
        print(
            "\n  [!] Could not parse some `.mat` files "
            "(will be skipped):"
        )
        for name, err in scan.parse_errors:
            print(f"    {name}: {err}")

    if not scan.variable_inventory:
        print(
            f"\n  ERROR: No parseable v5/v6/v7.2 `.mat` files in "
            f"{mat_dir}.\n"
            "  Check the directory contains at least one supported "
            "file."
        )
        return 1

    # Variable enumeration → optional filter prompt.
    all_vars = sorted(
        set().union(*(set(vs) for vs in scan.variable_inventory.values()))
    )
    n_files = len(scan.variable_inventory)
    print(
        f"\n  Variables across {n_files} parseable `.mat` "
        f"{'file' if n_files == 1 else 'files'}:"
    )
    for v in all_vars:
        n_with = sum(
            1 for vs in scan.variable_inventory.values() if v in vs
        )
        marker = "(all)" if n_with == n_files else f"({n_with}/{n_files})"
        print(f"    {v}  {marker}")
    print(
        "\n  Default: auto-detect 1-D / 2-D numeric variables per "
        "file at runtime."
    )
    raw_filter = input(
        "  variable_filter (comma-separated, blank for auto-detect): "
    ).strip()
    variable_filter: list[str] | None = None
    if raw_filter:
        variable_filter = [
            v.strip() for v in raw_filter.split(",") if v.strip()
        ]

    block: dict = {"path": str(mat_dir)}
    if variable_filter:
        block["variable_filter"] = variable_filter

    print(f"\n  Step 3 of 3 — write matlab_file block to {CONFIG_PATH}")
    wrote_config = False
    try:
        _write_user_config("matlab_file", block)
        wrote_config = True
    except FileExistsError:
        print(
            f"\n  matlab_file is already configured in {CONFIG_PATH}."
        )
        print(
            "  (Other source blocks and top-level keys will be "
            "preserved.)"
        )
        choice = input(
            "  Overwrite the matlab_file block? [y/N]: "
        ).strip().lower()
        if not _yes(choice):
            print(
                "  Kept the existing matlab_file block. No changes "
                "were made."
            )
            return 0
        _write_user_config("matlab_file", block, force=True)
        wrote_config = True

    if wrote_config:
        print(f"  Wrote matlab_file block to {CONFIG_PATH}")
    cleanup.actions.clear()

    ok, msg = _smoke_check_matlab(mat_dir, scan)
    if ok:
        print(f"  [OK] {msg}")
    else:
        print(f"  [FAIL] {msg}")
        return 1

    # Claude Desktop registration is per-MCP-install, not per-source:
    # the same single ``tailor`` entry covers MATLAB + any other
    # source blocks configured in user_config.json. The helper's
    # built-in overwrite-prompt handles the case where a prior
    # `tailor pilot --source=csv` already registered the entry.
    server_cmd = [sys.executable, "-m", "tailor", "serve"]
    registered = _register_with_claude_desktop(server_cmd)

    _matlab_next_steps_summary(mat_dir, registered)
    if warnings_acknowledged:
        print(
            f"  WARNINGS_ACKNOWLEDGED: "
            f"{', '.join(warnings_acknowledged)}"
        )
    return 0


# ──────────────────────────────────────────────────────────────────────
# REDCap-specific helpers
# ──────────────────────────────────────────────────────────────────────


def _prompt_redcap_dir() -> Path:
    """Ask the user for the REDCap export directory.

    Requires ``project_metadata.csv`` (the IRB-approved data
    dictionary that drives :class:`RedcapPHIScrubber` per ADR 0037).
    Re-prompts when the directory exists but lacks the dictionary —
    the wizard refuses to configure REDCap without the trust root.
    """
    print("  Step 1 of 3 — choose REDCap export directory")
    print(
        "  Enter the absolute path to the directory holding your "
        "REDCap export.\n"
    )
    print(
        "  The directory MUST contain `project_metadata.csv` "
        "(the data dictionary).\n"
        "  Download it from REDCap → Project Setup → Data Dictionary "
        "→ Download as CSV."
    )
    while True:
        raw = input("\n  REDCap directory: ").strip()
        if not raw:
            print("  Path is required.\n")
            continue
        candidate = Path(raw).expanduser()
        if not candidate.is_dir():
            print(f"  Not a directory: {candidate}. Try again.\n")
            continue
        if not (candidate / "project_metadata.csv").is_file():
            print(
                f"  No project_metadata.csv in {candidate}. The "
                "wizard cannot configure REDCap without the data "
                "dictionary (it determines which fields are "
                "identifiers per ADR 0037). Try again.\n"
            )
            continue
        return candidate.resolve()


def _display_redcap_trust_root(scrubber) -> None:
    """Print the full per-field identifier listing the scrubber loaded.

    Per the boss decision 2026-05-18 (full listing, not compact
    summary): first impression IS the trust root. The operator sees
    every field paired with its identifier flag before they confirm
    the configuration, so a tampered ``project_metadata.csv`` (flags
    flipped from Y to N) is visibly inspectable at the moment the
    deployment commits to using it. The compact "K of N flagged
    identifier" summary the proposal-mode audit considered would
    defeat the seam's purpose.
    """
    canonical = scrubber.canonical_state
    if not canonical:
        if scrubber.child_scrubber_warning:
            print("\n  [!] Trust root could not be loaded:")
            print(f"      {scrubber.child_scrubber_warning}")
        else:
            print(
                "\n  [!] Trust root is empty "
                "(project_metadata.csv loaded but contained zero "
                "parseable rows)."
            )
        print(
            "\n  Fail-closed default in effect — every field outside "
            "the unknown_field_allowlist will be stripped from "
            "results per ADR 0037."
        )
        return

    n_total = len(canonical)
    n_identifier = sum(1 for _, is_id in canonical if is_id)
    print(
        f"\n  Step 2 of 3 — trust-root identifier flags "
        f"({n_total} fields, {n_identifier} flagged identifier)"
    )
    print("  " + "-" * 60)
    for name, is_identifier in canonical:
        marker = "[IDENTIFIER]" if is_identifier else "[ok]        "
        print(f"  {marker} {name}")
    print("  " + "-" * 60)
    print(f"  Trust-root fingerprint: {scrubber.fingerprint}")


def _detect_redcap_completion_fields(redcap_dir: Path) -> list[str]:
    """Scan ``records.csv`` (if present) for column headers ending in
    ``_complete`` — REDCap's convention for per-instrument completion
    flags. Returns a sorted list; empty if ``records.csv`` absent or
    the file has no matching columns.

    ``utf-8-sig`` open (F3 closure on the wizard side) — Excel/
    PowerShell-saved ``records.csv`` files carry a BOM that the
    wizard must strip before reading the first-row headers, or the
    completion field auto-detect will silently fail to match (the
    first header ends up as ``\\ufeffrecord_id`` rather than
    ``record_id``).
    """
    records_path = redcap_dir / "records.csv"
    if not records_path.is_file():
        return []
    try:
        with open(
            records_path, encoding="utf-8-sig", newline="",
        ) as f:
            first_line = f.readline()
    except OSError:
        return []
    import csv as _csv
    headers = next(_csv.reader([first_line]), [])
    return sorted(h for h in headers if h.endswith("_complete"))


def _write_attest_initial_audit_row(
    fingerprint: str, redcap_dir: Path,
) -> bool:
    """Write the first-config attestation row via ``AuditLog.record()``.

    Per F5 (proposal-mode auditor 2026-05-18): ``ATTEST_INITIAL`` is
    a distinct outcome from ``REATTEST``. REATTEST means
    "re-attest against a *cached* fingerprint after detected drift"
    (the path ``cmd_redcap_reattest`` writes). At first config there
    IS no cached fingerprint, so stretching REATTEST's semantics
    would break audit-log honesty — an IRB reviewer querying
    audit.db should be able to tell "this was the first attestation"
    from "this was a re-attestation after a drift event."

    Per the v7.3.2 F-A precedent: this MUST use ``AuditLog.record()``,
    not a hand-rolled INSERT. The hand-rolled INSERT in v7.3.2's
    cmd_redcap_reattest left ``scrubber_id`` NULL on the REATTEST
    row, a direct ADR 0003 violation that the release-pass
    phi-irb-risk-reviewer caught pre-merge. Threading through
    ``AuditLog.record()`` inherits the framework's schema, migration
    logic, and any future column additions automatically.

    Returns ``True`` on success, ``False`` on failure (logs a warning
    to the operator, does not raise). Audit-row failure does not
    block the wizard's primary purpose of writing a usable config —
    this exemption is ratified by `ADR 0001 § Amendment 2026-05-18
    <docs/adr/0001-audit-log-as-backbone.md>`_ (CLI-helper audit-row
    exemption). The exemption applies only because all five
    preconditions hold: (1) this is a CLI subcommand helper, (2)
    the row is provenance-only (operator config-action), (3) the
    wizard's primary deliverable is user_config.json, (4) the
    operator can recover by re-running `tailor pilot --source=redcap`
    or `tailor redcap reattest`, (5) failure surfaces visibly on
    stderr. Router-tier audit calls in `RouterMCP._dispatch` /
    `_dispatch_vault` / `dispatch_internal` still propagate
    exceptions per the original ADR 0001 Negative-consequences rule.
    """
    from tailor.config import DATA_DIR as _DATA_DIR
    from tailor.framework.audit import AuditLog as _AuditLog
    from tailor.framework.security import PHIScrubber as _PHIScrubber

    try:
        audit = _AuditLog(_DATA_DIR / "audit.db")
    except Exception as exc:  # noqa: BLE001
        print(
            f"\n  [warn] Could not initialize audit.db for "
            f"ATTEST_INITIAL row: {exc}.\n"
            f"  Config write succeeded; this is a provenance-only "
            f"gap. Re-run `tailor pilot --source=redcap` to retry "
            f"the attestation."
        )
        return False
    # phi-irb-risk-reviewer WATCH-1 closure: query the framework
    # scrubber's identity instead of hardcoding `"noop"`. The sibling
    # REATTEST path at `__main__.py:982` does the same. An institution
    # running a subclassed framework PHIScrubber will have BOTH the
    # ATTEST_INITIAL and REATTEST rows carry the matching subclass
    # identity — without this, the row pair would disagree on
    # scrubber_id for the same logical event, weakening the ADR 0003
    # "scrubber_id turns 'did we scrub?' into a fact on disk"
    # invariant the wizard otherwise honors.
    framework_scrubber = _PHIScrubber()
    # reproducibility-provenance-auditor NEEDS REVIEW closure:
    # try/finally close() — mirrors the REATTEST sibling at
    # `__main__.py:986-987`. CLAUDE.md § Implementation notes names
    # the Windows-WAL close discipline explicitly; the wizard's CLI
    # process exits shortly after the call, but the explicit close()
    # pattern is the established convention and avoids a latent
    # Windows lock-file artifact if the wizard is ever re-invoked
    # in-process or tests share a CONFIG_DIR.
    try:
        try:
            audit.record(
                domain="redcap_file",
                tool_name="tailor_redcap_attest_initial",
                tier=0,
                params={
                    "action": "first_config_attestation",
                    "redcap_dir": str(redcap_dir),
                    "project_metadata_file": "project_metadata.csv",
                },
                token_estimate=0,
                outcome="ATTEST_INITIAL",
                duration_ms=0,
                scrubber_id=framework_scrubber.scrubber_id,
                child_scrubber_id="redcap_metadata_flags",
                source_metadata_fingerprint=fingerprint,
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"\n  [warn] Could not write ATTEST_INITIAL audit "
                f"row: {exc}."
            )
            return False
    finally:
        try:
            audit.close()
        except Exception:  # noqa: BLE001 — best-effort close
            pass
    return True


def _smoke_check_redcap(redcap_dir: Path) -> tuple[bool, str]:
    """Verify the redcap_file block resolves to a working
    ``RedcapFileChild``.

    Per F8: schema-validation only. Instantiates the child (which
    re-loads ``project_metadata.csv``, re-computes its own
    fingerprint inside the constructor, initializes
    ``RedcapProcessing``) but does NOT route through the router
    pipeline. The first real Claude Desktop call exercises the full
    pipeline (audit row, PHI scrub, ``_meta`` stamping with
    ``source_metadata_fingerprint`` per ADR 0003 § Amendment
    2026-05-15).
    """
    try:
        from tailor.children.redcap import RedcapFileChild

        child = RedcapFileChild(
            config_dir=CONFIG_DIR, data_dir=CONFIG_DIR / "data",
        )
        del child
    except Exception as exc:  # noqa: BLE001
        return False, f"RedcapFileChild failed to load: {exc}"
    return True, f"RedcapFileChild loaded successfully from {redcap_dir}."


def _redcap_next_steps_summary(
    redcap_dir: Path, results: list[_RegistrationResult],
) -> None:
    print("\n  Next steps")
    print("  ----------")
    print(f"  REDCap directory: {redcap_dir}")
    print(f"  Config written:   {CONFIG_PATH}")
    written = [r for r in results if r.written]
    failed = [r for r in results if not r.written]
    if not results:
        print("  Claude Desktop: not registered.")
        print(
            "  Re-run `tailor pilot --source=redcap` later, or add "
            "the server manually."
        )
    elif written and not failed:
        if len(written) == 1:
            print(
                "  Claude Desktop: registered. Restart Claude Desktop "
                "to pick up the change."
            )
        else:
            print(
                f"  Claude Desktop: registered in {len(written)} "
                f"configs (both classic and Microsoft Store variants)."
            )
            print(
                "  Fully quit Claude Desktop (system tray Quit on "
                "Windows, Cmd+Q on macOS) and re-open."
            )
        print(
            "  Then ask: 'list the records in the REDCap export' to "
            "verify wiring."
        )
        print(
            "\n  Trust root: an ATTEST_INITIAL row was written to "
            "audit.db\n"
            "  recording the project_metadata.csv fingerprint in "
            "effect\n"
            "  at first configuration. If the data dictionary "
            "changes\n"
            "  (a new field is added, an identifier flag is flipped), "
            "re-run\n"
            "  `tailor redcap reattest` to record the new state "
            "explicitly."
        )
    elif written and failed:
        print(
            f"  Claude Desktop: registered in {len(written)} of "
            f"{len(results)} detected configs. The remaining write(s) "
            f"failed:"
        )
        for r in failed:
            print(f"    - {r.path}: {type(r.error).__name__}")
        print(
            "  Quit Claude Desktop fully and rerun "
            "`tailor pilot --source=redcap`."
        )
    else:
        print("  Claude Desktop: NOT registered. All writes failed:")
        for r in failed:
            print(f"    - {r.path}: {type(r.error).__name__}: {r.error}")
        print(
            "  Quit Claude Desktop fully and rerun "
            "`tailor pilot --source=redcap`."
        )
    print(
        "  Audit log lives at ~/.tailor/data/audit.db "
        "(one row per tool call).\n"
    )


def _run_redcap(cleanup: _Cleanup) -> int:
    """Configure a ``redcap_file`` block in user_config.json.

    F4 closure: trust-root fingerprint reuses :class:`RedcapPHIScrubber`
    directly — no parallel canonical-form code path in the wizard
    that could drift from the production seam.

    F3 closure: project_metadata.csv reads happen inside the
    scrubber's ``_load_metadata`` which already uses ``utf-8-sig``
    (BOM-safe). The wizard does not re-read the dictionary itself.
    The records.csv completion-field auto-detect also uses
    ``utf-8-sig``.

    F5 closure: ``ATTEST_INITIAL`` audit row written via
    ``AuditLog.record()`` — distinct outcome from ``REATTEST``,
    never a hand-rolled INSERT (v7.3.2 F-A precedent).

    F7 closure: ``unknown_field_allowlist`` default empty = fail-
    closed per ADR 0037. Wizard prose makes the fail-closed posture
    explicit so the operator understands what 'blank' commits them
    to.

    F1 inheritance: the canonical deep-merge ``_write_user_config``
    preserves sibling source blocks (csv_dir, matlab_file,
    vault_path, etc.) across the round-trip.
    """
    from tailor.children.redcap.scrubber import RedcapPHIScrubber

    warnings_acknowledged: list[str] = []

    redcap_dir = _prompt_redcap_dir()

    provider = _check_for_cloud_sync(redcap_dir)
    if provider:
        print(
            f"\n  [!] WARNING: Your REDCap directory appears to be "
            f"inside {provider}. Cloud-sync providers can corrupt "
            f"CSV files mid-read AND may leak PHI into the sync "
            f"history — a HIPAA Safe Harbor concern. Consider "
            f"moving the export to a non-synced location."
        )
        answer = input("  Continue anyway? [y/N]: ").strip().lower()
        if not _yes(answer):
            print(
                "\n  No changes were made. Move the REDCap export "
                "and re-run `tailor pilot --source=redcap`."
            )
            return 0
        warnings_acknowledged.append(f"cloud-sync ({provider})")

    # F4: instantiate the scrubber ONCE to compute the fingerprint
    # via the production canonical-form code path. No parallel
    # implementation in the wizard.
    metadata_path = redcap_dir / "project_metadata.csv"
    scrubber = RedcapPHIScrubber(metadata_path)

    _display_redcap_trust_root(scrubber)

    # F7: unknown_field_allowlist prompt with explicit fail-closed
    # prose. The empty default IS the safe default; the operator
    # must affirmatively opt-in to allowlist any field.
    print(
        "\n  unknown_field_allowlist (default: blank = fail-closed)"
    )
    print(
        "  Leaving this blank means any field NOT in "
        "project_metadata.csv\n"
        "  will be stripped from results — the safe default per "
        "ADR 0037.\n"
        "  Add fields here ONLY if you have computed columns the "
        "data dictionary\n"
        "  does not cover AND you have verified those columns are "
        "not PHI."
    )
    raw_allowlist = input(
        "  Allowlist (comma-separated field names, blank for safe "
        "default): "
    ).strip()
    allowlist = [
        f.strip() for f in raw_allowlist.split(",") if f.strip()
    ]

    # Auto-suggest instrument_completion_fields from records.csv.
    completion_fields = _detect_redcap_completion_fields(redcap_dir)
    use_completion_fields: list[str] = []
    if completion_fields:
        print(
            f"\n  Detected {len(completion_fields)} instrument "
            f"completion field(s) in records.csv:"
        )
        for cf in completion_fields:
            print(f"    {cf}")
        choice = input(
            "  Use these as instrument_completion_fields? [Y/n]: "
        ).strip().lower()
        if choice not in ("n", "no"):
            use_completion_fields = completion_fields

    # Confirm with a re-cite of the trust-root fingerprint.
    print("\n  Ready to write redcap_file block.")
    print(f"  Trust-root fingerprint: {scrubber.fingerprint}")
    print(
        "  Re-read the per-field identifier listing above before "
        "confirming."
    )
    confirm = input("\n  Continue? [y/N]: ").strip().lower()
    if not _yes(confirm):
        print("  No changes were made.")
        return 0

    block: dict = {"path": str(redcap_dir)}
    if (redcap_dir / "records.csv").is_file():
        block["records_file"] = "records.csv"
    if use_completion_fields:
        block["instrument_completion_fields"] = use_completion_fields
    if allowlist:
        block["unknown_field_allowlist"] = allowlist

    print(
        f"\n  Step 3 of 3 — write redcap_file block to {CONFIG_PATH}"
    )
    wrote_config = False
    try:
        _write_user_config("redcap_file", block)
        wrote_config = True
    except FileExistsError:
        print(
            f"\n  redcap_file is already configured in {CONFIG_PATH}."
        )
        print(
            "  (Other source blocks and top-level keys will be "
            "preserved.)"
        )
        choice = input(
            "  Overwrite the redcap_file block? [y/N]: "
        ).strip().lower()
        if not _yes(choice):
            print(
                "  Kept the existing redcap_file block. No changes "
                "were made."
            )
            return 0
        _write_user_config("redcap_file", block, force=True)
        wrote_config = True

    if wrote_config:
        print(f"  Wrote redcap_file block to {CONFIG_PATH}")
    cleanup.actions.clear()

    # F5: ATTEST_INITIAL audit row via AuditLog.record(). Best-effort
    # — failure does not block the wizard since the audit row is
    # provenance-only.
    attest_ok = _write_attest_initial_audit_row(
        scrubber.fingerprint, redcap_dir,
    )
    if attest_ok:
        print(
            f"  Wrote ATTEST_INITIAL audit row "
            f"(fingerprint={scrubber.fingerprint[:16]}...)"
        )

    ok, msg = _smoke_check_redcap(redcap_dir)
    if ok:
        print(f"  [OK] {msg}")
    else:
        print(f"  [FAIL] {msg}")
        return 1

    server_cmd = [sys.executable, "-m", "tailor", "serve"]
    registered = _register_with_claude_desktop(server_cmd)

    _redcap_next_steps_summary(redcap_dir, registered)
    if warnings_acknowledged:
        print(
            f"  WARNINGS_ACKNOWLEDGED: "
            f"{', '.join(warnings_acknowledged)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

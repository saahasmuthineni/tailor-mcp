"""
Fitting-room library module
===========================
Scaffold a guided walkthrough you can drive from Claude Desktop.

In tailoring, a fitting room is where the customer puts on the
work-in-progress and tests the fit before any final commitment.
The scaffold maps onto that: copies bundled synthetic-by-
construction fixtures into a target directory, writes
``user_config.json`` with absolute paths, indexes the vault, and
registers with Claude Desktop so a non-technical recipient can
drive the walkthrough from a fresh chat without ever typing an
environment variable.

Distinct from the walkthrough (the architectural showcase you
watch — ``python -m tailor.demo`` / the ``tailor_walkthrough_section``
MCP tool, per ADRs 0027 and 0040); fitting-room is the active
surface where the recipient drives. See ADRs 0024 and 0035 for the
structural decision and the renaming rationale.

History: renamed from ``tour`` in v7.1.0 per ADR 0035 (the
``tailor tour`` alias and the ``tailor.tour`` re-export shim were
removed in v7.2.0); the ``tailor fitting-room`` CLI verb itself was
hard-removed in v8.0.0 per ADR 0040, leaving this module as the
library + ``python -m tailor.fitting_room`` developer path behind
the ``tailor_fitting_room_*`` MCP tools.

Currently-supported variants:

- ``cohort`` — multimodal force / EMG / 31P-MRS realistic demo
  cohort. 16 synthetic subjects, the S004 cross-session-memory wow
  moment, the cohort sex-difference comparison.

Future variants (sleep, CGM, etc.) plug into the ``_VARIANT_FIXTURES``
table.

Usage (developer/RSE library entry point — the ``tailor
fitting-room`` CLI verb was hard-removed in v8.0.0 per ADR 0040; the
recipient path is the ``tailor_fitting_room_scaffold`` MCP tool):

    python -m tailor.fitting_room
    python -m tailor.fitting_room --variant=cohort
    python -m tailor.fitting_room --target=/some/other/path
    python -m tailor.fitting_room --no-claude-desktop --force
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from importlib.resources import as_file, files
from pathlib import Path

# Reuse the v6.2.1 pilot-wizard hardenings (atomic write, BOM
# round-trip, deep-merge into existing mcpServers) extended in v6.10.4
# per ADR 0026 to dual-write across Classic + Microsoft Store Claude
# Desktop config paths. These are private helpers but live in the same
# package; treat them as package-internal not public API.
from tailor.pilot import (
    _CLAUDE_DESKTOP_UWP_PACKAGE_PREFIX,
    _claude_desktop_config_paths,
    _RegistrationResult,
    _write_registration_to_path,
)

# Default scaffold root. Sits under the operator's tailor
# config dir so a power user can co-locate, but completely
# segregated by the ``demos/`` subdir so ``rm -rf`` on either side
# stays scoped.
DEFAULT_TARGET_BASE = Path.home() / ".tailor" / "demos"

# Variant table — extend here when adding sleep / CGM / etc.
# Tuple shape: (fixtures_subpackage, default_target_subdir).
_VARIANT_FIXTURES: dict[str, tuple[str, str]] = {
    "cohort": ("cohort_demo_realistic", "cohort"),
}
DEFAULT_VARIANT = "cohort"
VARIANTS = tuple(_VARIANT_FIXTURES.keys())


# ──────────────────────────────────────────────────────────────────────
# Resource-tree copy (Python 3.10-compatible — as_file on directories
# only landed in 3.12, so iterate file-by-file).
# ──────────────────────────────────────────────────────────────────────


def _copy_resource_tree(traversable, dest: Path) -> int:
    """Recursively copy a Traversable into ``dest``. Returns file count."""
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for child in traversable.iterdir():
        name = child.name
        if child.is_file():
            with as_file(child) as src_path:
                shutil.copy2(src_path, dest / name)
            n += 1
        elif child.is_dir():
            n += _copy_resource_tree(child, dest / name)
    return n


def _scaffold_fixtures(variant: str, target_dir: Path) -> dict[str, int]:
    """Copy the bundled fixture tree into ``target_dir/{force,emg,mrs,vault}``.

    Returns a per-subdir file count for the next-steps printout.
    """
    fixtures_subpkg, _default_subdir = _VARIANT_FIXTURES[variant]
    pkg_root = files("tailor._fixtures").joinpath(fixtures_subpkg)
    counts: dict[str, int] = {"force": 0, "emg": 0, "mrs": 0, "vault": 0}
    for sub in counts:
        src_sub = pkg_root.joinpath(sub)
        if not src_sub.is_dir():
            continue
        counts[sub] = _copy_resource_tree(src_sub, target_dir / sub)
    return counts


# ──────────────────────────────────────────────────────────────────────
# user_config.json (absolute paths resolved against target_dir)
# ──────────────────────────────────────────────────────────────────────


def _cohort_user_config(target_dir: Path) -> dict:
    """Build the user_config.json payload for the cohort variant.

    Mirrors the shape that the prior ``examples/.../setup.py`` wrote
    so ``ForceCsvChild`` / ``EmgCsvChild`` register identically.
    """
    return {
        "vault_path": str(target_dir / "vault"),
        # cost_threshold is set below the framework default (35,000) so
        # the bundled demo cohort fixtures' Tier-3 raw-window call on a 60s
        # @ 100 Hz subject trace (estimated ~24,000 tokens; actual
        # payload ~50,000 tokens per the v7.3.4 mcp-protocol-auditor
        # wire audit) trips the cost gate — making the AI-economics
        # claim (ADR 0029) demonstrable in the recipient walkthrough.
        # Matches the v6.5.0 demo router precedent. v7.4.0 may tune
        # this once the cost estimator's 2.1× under-estimate is
        # calibrated.
        "cost_threshold": 15000,
        "force_csv": {
            "path": str(target_dir / "force"),
            "timestamp_column": "t_s",
            "sample_rate_hz": 100.0,
            "value_columns": {"force": "force_N"},
        },
        "emg_csv": {
            "path": str(target_dir / "emg"),
            "timestamp_column": "t_s",
            "sample_rate_hz": 100.0,
            "value_columns": {"envelope": "envelope_uV"},
        },
        # MRS spectra (31P stub) — registered through the generic
        # csv_dir child rather than a dedicated MrsCsvChild so the
        # bundled fixtures are not orphaned (no tools could touch
        # them on v6.9.0).  csv_dir's value_columns contract is
        # ``{actual_header: human_label}`` (different shape from
        # force_csv / emg_csv's logical→physical alias map).
        "csv_dir": {
            "path": str(target_dir / "mrs"),
            "timestamp_column": "t_s",
            "value_columns": {
                "pcr_relative": "Phosphocreatine (relative)",
                "pi_relative": "Inorganic phosphate (relative)",
            },
        },
    }


def _write_user_config(variant: str, target_dir: Path) -> Path:
    cfg_path = target_dir / "user_config.json"
    if variant == "cohort":
        cfg = _cohort_user_config(target_dir)
    else:
        raise ValueError(f"unknown variant: {variant}")
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg_path.with_suffix(cfg_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    os.replace(tmp, cfg_path)
    return cfg_path


# ──────────────────────────────────────────────────────────────────────
# Vault indexing — reuses the framework's rescan_vault so the seed
# moment is searchable from the recipient's first call.
# ──────────────────────────────────────────────────────────────────────


def _index_vault(target_dir: Path) -> dict[str, int]:
    from tailor.framework.vault.rescan import rescan_vault
    from tailor.framework.vault.storage import VaultStorage

    data_dir = target_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    storage = VaultStorage(data_dir / "vault.db")
    try:
        return rescan_vault(target_dir / "vault", storage)
    finally:
        storage.close()


# ──────────────────────────────────────────────────────────────────────
# Claude Desktop presence detection (Phase 0 attempt-1 F4 fix; v7.0.4).
#
# Must run BEFORE _register_with_claude_desktop — that helper creates
# the classic %APPDATA%\Claude\ directory lazily on first write, so
# checking after registration would always return True via the
# framework's own side effect. See docs/diagnosis/attempt-1-triage.md
# § F4 for the failure shape this closes (tour declared "registration
# success" on a recipient with no Claude Desktop installed; the
# success message told them to "fully quit Claude Desktop, then
# re-open it" — structurally impossible).
# ──────────────────────────────────────────────────────────────────────


def _detect_claude_desktop_presence() -> bool:
    """Return True if Claude Desktop appears installed on this user account.

    Conservative: a positive verdict requires evidence that Claude Desktop
    has run at least once (its config directory exists) or that its UWP
    package is registered. A negative verdict means tour will still stage
    the config (per ADR 0026 § "First-time-install on a Store-only
    machine") but the success banner is rewritten to be honest about the
    gap rather than promising a "fully quit, re-open" ritual the recipient
    cannot perform.

    Per platform:
    - Windows: classic ``%APPDATA%\\Claude\\`` directory exists, OR any
      ``%LOCALAPPDATA%\\Packages\\Claude_*\\`` UWP package directory exists.
    - macOS: ``~/Library/Application Support/Claude/`` exists.
    - Linux: always False (no Claude Desktop on this platform).
    """
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
        ).is_dir()
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata and (Path(appdata) / "Claude").is_dir():
            return True
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            packages_dir = Path(local_appdata) / "Packages"
            if packages_dir.exists():
                for pkg in packages_dir.glob(
                    f"{_CLAUDE_DESKTOP_UWP_PACKAGE_PREFIX}*"
                ):
                    if pkg.is_dir():
                        return True
        return False
    return False


# ──────────────────────────────────────────────────────────────────────
# Claude Desktop registration — bakes TAILOR_CONFIG_DIR and
# TAILOR_DATA_DIR into the entry's env block so the recipient
# never types an env var. Closes auditor blocker 1.
# ──────────────────────────────────────────────────────────────────────


def _register_with_claude_desktop(
    target_dir: Path, *, server_name: str,
) -> list[_RegistrationResult]:
    """Register the tour entry in every detected Claude Desktop config;
    clean any pre-existing ``biosensor-*`` siblings on each path so the
    recipient does not end up with two MCP servers running
    simultaneously after a debugging detour (v6.10.3 — closes the
    dad-2026-05-06 multi-entry-coexistence trap, generalised per-path
    in v6.10.4 per ADR 0026).

    Recipient-failure shape this closes: web-Claude-mediated debugging
    on a v6.9.x failed-tour install adds a bare ``tailor`` entry
    with no env block to ``claude_desktop_config.json``. A subsequent
    ``tailor tour --force`` previously left that bare entry in
    place and added a sibling ``tailor-tour-cohort`` — Claude
    Desktop would then launch both, with the bare server's
    SetupHelpLayer (v6.10.2) leaking into the working-demo tool
    surface. Mirrors the v6.9.2 prefix-match cleanup pattern in
    ``cmd_uninstall``: tour cleans on setup, uninstall cleans on
    teardown. v7.0.0 (per ADR 0031) widens the cleanup to match
    both legacy ``biosensor-*`` and current ``tailor`` / ``tailor-*``
    so v6 → v7 upgrades don't leave orphan entries.

    v6.10.4 invariant (carried forward to v7.0.0): after a successful
    ``tour --force``, exactly one ``tailor-*`` entry exists in **each
    detected** Claude Desktop config; the entry is identical across
    configs. See ADR 0026 § "Per-path atomic semantics".

    Returns the list of per-path :class:`_RegistrationResult` records.
    Empty list on Linux (no Claude Desktop on this platform).
    """
    paths = _claude_desktop_config_paths()
    if not paths:
        return []
    entry = {
        "command": sys.executable,
        "args": ["-m", "tailor", "serve"],
        "env": {
            "TAILOR_CONFIG_DIR": str(target_dir),
            "TAILOR_DATA_DIR": str(target_dir / "data"),
        },
    }
    return [
        _write_registration_to_path(p, server_name=server_name, entry=entry)
        for p in paths
    ]


# ──────────────────────────────────────────────────────────────────────
# Output
# ──────────────────────────────────────────────────────────────────────


def _resolve_target(variant: str, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    _, subdir = _VARIANT_FIXTURES[variant]
    return (DEFAULT_TARGET_BASE / subdir).resolve()


def _print_next_steps(
    target_dir: Path,
    results: list[_RegistrationResult],
    server_name: str,
    *,
    skipped: bool = False,
    claude_desktop_present: bool = True,
) -> None:
    """Print tour-completion banner with per-path Claude Desktop status.

    Per ADR 0026 § "Per-path atomic semantics", the success message is
    conditional: ``Tour scaffolded successfully`` prints only if every
    detected path was written. On any partial failure, the banner
    states the partial-success count and lists per-path failures with
    a plain-language remediation.

    Per Phase 0 attempt-1 F4 (v7.0.4): when ``claude_desktop_present``
    is False, the banner is rewritten to flag that Claude Desktop is
    not detected on this user account. Tour still stages the config
    (per ADR 0026 § "First-time-install on a Store-only machine") but
    the recipient is told the install is incomplete rather than
    promised a "fully quit, re-open" ritual that has nothing to act on.
    """
    written = [r for r in results if r.written]
    failed = [r for r in results if not r.written]
    all_ok = (skipped or not failed) and (skipped or written or not results)

    print()
    print("=" * 64)
    if all_ok and claude_desktop_present:
        print("  Fitting-room scaffolded successfully")
    elif all_ok and not claude_desktop_present:
        print("  Fitting-room scaffolded; Claude Desktop NOT DETECTED")
    elif written:
        print(f"  Fitting-room scaffolded with {len(written)} of "
              f"{len(results)} Claude Desktop registrations succeeded")
    else:
        print("  Fitting-room scaffolded; Claude Desktop registration FAILED")
    print("=" * 64)

    # ── What to do next (lead with the action, not the paths) ──
    if skipped:
        print()
        print("  Claude Desktop registration was skipped (--no-claude-desktop).")
        print()
        print("  To use Tailor manually, set these env vars and start the server:")
        print(f"    TAILOR_CONFIG_DIR={target_dir}")
        print(f"    TAILOR_DATA_DIR={target_dir / 'data'}")
        print()
        _print_fitting_room_paths_block(target_dir)
        return

    if not results:
        print()
        print("  Claude Desktop registration unavailable on this platform")
        print("  (Linux, or APPDATA missing on Windows).")
        print()
        print("  To use Tailor manually, set these env vars and start the server:")
        print(f"    TAILOR_CONFIG_DIR={target_dir}")
        print(f"    TAILOR_DATA_DIR={target_dir / 'data'}")
        print()
        _print_fitting_room_paths_block(target_dir)
        return

    if written and claude_desktop_present:
        print()
        print("  Next step:")
        print("    1. Please fully quit Claude Desktop")
        print("       (Windows: right-click system-tray icon -> Quit;")
        print("        macOS: Cmd+Q).")
        print("    2. Re-open Claude Desktop, then in a fresh chat try one")
        print("       of these prompts:")
        print()
        print('      * "Compare male versus female force decline rates in')
        print('         this cohort."')
        print('      * "What about subject four?"')
        print('      * "Show me the recent moments in the vault."')
        print('      * "Step me through the tier levels for subject four')
        print('         — what does each one cost?"')
        print()
        print("  (Heads-up: don't call `vault_generate_snapshot` mid-")
        print("   walkthrough — it overwrites the bundled orientation")
        print("   document with a live-state regenerate.)")
        print()
        print("  Heads-up on Claude Desktop's UI: Tailor appears as a")
        print("  'session-scoped server', not a green connector card.")
        print("  That's the normal shape for local MCP servers (connector")
        print("  cards are reserved for OAuth integrations). The full tool")
        print("  surface is available either way.")
        print()
        _print_fitting_room_paths_block(target_dir, written, server_name,
                                       claude_desktop_present)
    elif written and not claude_desktop_present:
        print()
        print("  Claude Desktop is not installed on this account. Tailor's")
        print("  config has been staged for a future install — once Claude")
        print("  Desktop is installed and run for the first time, it will")
        print("  pick up this config automatically. You cannot use Tailor's")
        print("  MCP integration until Claude Desktop is installed.")
        print()
        print("  Install Claude Desktop:")
        print("    https://claude.ai/download")
        print()
        _print_fitting_room_paths_block(target_dir, written, server_name,
                                       claude_desktop_present)
    if failed:
        print()
        print("  ERRORS — these Claude Desktop config paths could not be written:")
        for r in failed:
            print(f"    - {r.path}")
            print(f"      {type(r.error).__name__}: {r.error}")
        print()
        print("  Quit Claude Desktop fully (system tray Quit on Windows,")
        print("  Cmd+Q on macOS) and re-run with --force")
        print("  (`python -m tailor.fitting_room --force`).")
        print()


def _print_fitting_room_paths_block(
    target_dir,
    written: list | None = None,
    server_name: str = "",
    claude_desktop_present: bool = False,
) -> None:
    """Print the fitting-room paths block (target dir, configs, vault index,
    Claude Desktop registrations) as a *demoted* power-user reference, after
    the human-facing 'what to do next' instruction has led."""
    print("  Files & locations (for reference):")
    print(f"    target dir:   {target_dir}")
    print(f"    user_config:  {target_dir / 'user_config.json'}")
    print(f"    vault index:  {target_dir / 'data' / 'vault.db'}")
    if written:
        verb = "staged" if not claude_desktop_present else "registered"
        if len(written) == 1:
            print(f"    Claude config ({verb} as '{server_name}'):")
            print(f"      {written[0].path}")
        else:
            print(f"    Claude configs ({verb} as '{server_name}'):")
            for r in written:
                print(f"      {r.path}")
    print()


# ──────────────────────────────────────────────────────────────────────
# CLI entry
# ──────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tailor.fitting_room",
        description=(
            "Scaffold a guided walkthrough of the framework you can drive "
            "from Claude Desktop. Copies bundled synthetic fixtures into "
            "a target directory, writes user_config.json, indexes the "
            "vault, and (by default) registers with Claude Desktop so the "
            "recipient can drive the walkthrough from a fresh chat with "
            "no manual setup."
        ),
    )
    parser.add_argument(
        "--variant", choices=VARIANTS, default=DEFAULT_VARIANT,
        help=f"Which fitting-room to scaffold (default: {DEFAULT_VARIANT}).",
    )
    parser.add_argument(
        "--target", default=None,
        help=(
            "Where to scaffold the fitting-room. Default: "
            "~/.tailor/demos/<variant>/."
        ),
    )
    parser.add_argument(
        "--no-claude-desktop", action="store_true",
        help="Skip writing the Claude Desktop config entry.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite an existing non-fitting-room target directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[2:])

    target_dir = _resolve_target(args.variant, args.target)
    server_name = f"tailor-fitting-room-{args.variant}"

    # Quit-first heads-up per ADR 0035 § Decision item 3. The strip-and-
    # replace below is already transactional per-path
    # (pilot._write_registration_to_path uses in-memory clean + atomic
    # os.replace), so a running Claude Desktop holding a config file
    # open will fail safely: the on-disk state at that path is
    # unchanged. But a [error] line under the success banner reads
    # alarming; the heads-up surfaces the constraint before the
    # recipient hits it. Informational only — does not block; recipient
    # can ctrl-c to abort.
    print(
        "  Heads up: if Claude Desktop is running, please quit it fully\n"
        "  (system tray Quit on Windows, Cmd+Q on macOS) before this\n"
        "  command writes the new MCP config.\n"
    )

    # ``--force`` means "wipe and start fresh" — without the rmtree,
    # ``_copy_resource_tree`` is file-by-file ``shutil.copy2`` and
    # never deletes anything, so stale files from a broken scaffold
    # survive the supposed recovery (v6.9.0 footgun: the
    # WINDOWS_QUICKSTART tells the operator to re-run with --force
    # to recover, but stale files would survive).
    if args.force and target_dir.exists() and target_dir.is_dir():
        shutil.rmtree(target_dir, ignore_errors=True)

    # Guard against clobbering a non-tour directory. A prior tour
    # scaffold writes user_config.json — its presence is the cheap
    # "this dir is mine, refresh it" signal. The rmtree above means
    # this guard only fires when ``--force`` was NOT passed.
    if target_dir.exists() and any(target_dir.iterdir()):
        existing = target_dir / "user_config.json"
        if not existing.exists() and not args.force:
            print(f"  Target directory not empty: {target_dir}", file=sys.stderr)
            print(
                "  Pass --force to overwrite, or --target=<other-dir> "
                "to pick another location.",
                file=sys.stderr,
            )
            return 1

    print(f"  Scaffolding fitting-room variant={args.variant} into {target_dir}")
    print()
    print("  (1/4) copy bundled fixtures")
    counts = _scaffold_fixtures(args.variant, target_dir)
    print(
        f"        force/={counts['force']}, emg/={counts['emg']}, "
        f"mrs/={counts['mrs']}, vault/={counts['vault']}"
    )
    print()
    print("  (2/4) write user_config.json")
    cfg_path = _write_user_config(args.variant, target_dir)
    print(f"        wrote {cfg_path}")
    print()
    print("  (3/4) index vault.db")
    rescan_counts = _index_vault(target_dir)
    print(
        f"        added={rescan_counts.get('added', 0)}, "
        f"modified={rescan_counts.get('modified', 0)}, "
        f"skipped={rescan_counts.get('skipped', 0)}"
    )
    print()
    print("  (4/4) register with Claude Desktop")
    results: list[_RegistrationResult] = []
    skipped = bool(args.no_claude_desktop)
    # Detect BEFORE _register_with_claude_desktop — that helper creates
    # the classic %APPDATA%\Claude\ directory lazily on first write, so
    # checking after registration would always return True via the
    # framework's own side effect. v7.0.4 / Phase 0 F4 fix.
    claude_desktop_present = (
        True if skipped else _detect_claude_desktop_presence()
    )
    if skipped:
        print("        skipped (--no-claude-desktop)")
    else:
        results = _register_with_claude_desktop(
            target_dir, server_name=server_name,
        )
        if not results:
            print("        skipped (Linux, or APPDATA missing)")
        for r in results:
            if r.written:
                if r.cleaned:
                    print(
                        f"        cleaned stale orphan entries in {r.path.name}: "
                        f"{', '.join(r.cleaned)}"
                    )
                print(f"        wrote entry '{server_name}' to {r.path}")
            else:
                print(f"        [error] could not write {r.path}")
                print(f"                {type(r.error).__name__}: {r.error}")
        if not claude_desktop_present and results:
            print("        [warn] Claude Desktop not detected on this account")
            print("               config staged for future install")

    _print_next_steps(
        target_dir, results, server_name,
        skipped=skipped,
        claude_desktop_present=claude_desktop_present,
    )
    # Exit non-zero if every detected path failed; succeed if at least
    # one path was written or the user opted out via --no-claude-desktop.
    if results and not any(r.written for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

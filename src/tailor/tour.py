"""
Tour subcommand
===============
Scaffold a guided framework walkthrough from bundled fixtures.

The tour pattern is the framework's audience-walkthrough surface
— distinct from ``tailor demo``, which is a researcher
first-look that drives the same bundled HIP Lab fixtures through
``CSVDirectoryChild.execute()`` in a tempdir without writing
anything durable (per ADR 0027). A tour copies the same fixtures
into a target
directory, writes ``user_config.json`` with absolute paths,
indexes the vault, and registers with Claude Desktop so a
non-technical recipient can run the walkthrough from a fresh chat
without ever typing an environment variable. See ADR 0024 for
the structural decision and the wheel-distribution rationale.

Currently-supported variants:

- ``hip-lab`` — multimodal force / EMG / 31P-MRS HIP-Lab realistic
  demo. 16 synthetic subjects, the S004 cross-session-memory wow
  moment, the cohort sex-difference comparison.

Future variants (sleep, CGM, etc.) plug into the ``_VARIANT_FIXTURES``
table.

Usage:
    tailor tour
    tailor tour --variant=hip-lab
    tailor tour --target=/some/other/path
    tailor tour --no-claude-desktop --force
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
    "hip-lab": ("hip_lab_demo_realistic", "hip-lab"),
}
DEFAULT_VARIANT = "hip-lab"
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


def _hip_lab_user_config(target_dir: Path) -> dict:
    """Build the user_config.json payload for the hip-lab variant.

    Mirrors the shape that the prior ``examples/.../setup.py`` wrote
    so ``ForceCsvChild`` / ``EmgCsvChild`` register identically.
    """
    return {
        "vault_path": str(target_dir / "vault"),
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
    if variant == "hip-lab":
        cfg = _hip_lab_user_config(target_dir)
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
    place and added a sibling ``biosensor-tour-hip-lab`` — Claude
    Desktop would then launch both, with the bare server's
    SetupHelpLayer (v6.10.2) leaking into the working-demo tool
    surface. Mirrors the v6.9.2 prefix-match cleanup pattern in
    ``cmd_uninstall``: tour cleans on setup, uninstall cleans on
    teardown.

    v6.10.4 invariant: after a successful ``tour --force``, exactly
    one ``biosensor-*`` entry exists in **each detected** Claude
    Desktop config; the entry is identical across configs. See ADR
    0026 § "Per-path atomic semantics".

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
) -> None:
    """Print tour-completion banner with per-path Claude Desktop status.

    Per ADR 0026 § "Per-path atomic semantics", the success message is
    conditional: ``Tour scaffolded successfully`` prints only if every
    detected path was written. On any partial failure, the banner
    states the partial-success count and lists per-path failures with
    a plain-language remediation.
    """
    written = [r for r in results if r.written]
    failed = [r for r in results if not r.written]
    all_ok = (skipped or not failed) and (skipped or written or not results)

    print()
    print("=" * 64)
    if all_ok:
        print("  Tour scaffolded successfully")
    elif written:
        print(f"  Tour scaffolded with {len(written)} of {len(results)} "
              f"Claude Desktop registrations succeeded")
    else:
        print("  Tour scaffolded; Claude Desktop registration FAILED")
    print("=" * 64)
    print(f"  Target dir:     {target_dir}")
    print(f"  user_config:    {target_dir / 'user_config.json'}")
    print(f"  vault index:    {target_dir / 'data' / 'vault.db'}")

    if skipped:
        print("  Claude Desktop: not registered (--no-claude-desktop)")
        print(f"  Manual env vars: TAILOR_CONFIG_DIR={target_dir}")
        print(f"                   TAILOR_DATA_DIR={target_dir / 'data'}")
        print()
        return

    if not results:
        print("  Claude Desktop: not registered (Linux, or APPDATA missing)")
        print(f"  Manual env vars: TAILOR_CONFIG_DIR={target_dir}")
        print(f"                   TAILOR_DATA_DIR={target_dir / 'data'}")
        print()
        return

    if written:
        if len(written) == 1:
            print(f"  Claude Desktop: registered as '{server_name}' in")
            print(f"                  {written[0].path}")
        else:
            print(f"  Claude Desktop: registered as '{server_name}' in:")
            for r in written:
                print(f"                  {r.path}")
    if failed:
        print()
        print("  ERRORS — these Claude Desktop config paths could not be written:")
        for r in failed:
            print(f"    - {r.path}")
            print(f"      {type(r.error).__name__}: {r.error}")
        print()
        print("  Quit Claude Desktop fully (system tray Quit on Windows,")
        print("  Cmd+Q on macOS) and re-run `tailor tour --force`.")
    print()
    if written:
        print("  Next: fully quit Claude Desktop (system tray Quit on Windows,")
        print("        Cmd+Q on macOS), then re-open it. Try this prompt:")
        print()
        print('    "List the available biosensor MCP tools."')
    print()


# ──────────────────────────────────────────────────────────────────────
# CLI entry
# ──────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tailor tour",
        description=(
            "Scaffold a guided walkthrough of the framework. Copies "
            "bundled synthetic fixtures into a target directory, writes "
            "user_config.json, indexes the vault, and (by default) "
            "registers with Claude Desktop so the recipient can run "
            "the walkthrough from a fresh chat with no manual setup."
        ),
    )
    parser.add_argument(
        "--variant", choices=VARIANTS, default=DEFAULT_VARIANT,
        help=f"Which tour to scaffold (default: {DEFAULT_VARIANT}).",
    )
    parser.add_argument(
        "--target", default=None,
        help=(
            "Where to scaffold the tour. Default: "
            "~/.tailor/demos/<variant>/."
        ),
    )
    parser.add_argument(
        "--no-claude-desktop", action="store_true",
        help="Skip writing the Claude Desktop config entry.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite an existing non-tour target directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[2:])

    target_dir = _resolve_target(args.variant, args.target)
    server_name = f"biosensor-tour-{args.variant}"

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

    print(f"  Scaffolding tour variant={args.variant} into {target_dir}")
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
                        f"        cleaned stale biosensor-* in {r.path.name}: "
                        f"{', '.join(r.cleaned)}"
                    )
                print(f"        wrote entry '{server_name}' to {r.path}")
            else:
                print(f"        [error] could not write {r.path}")
                print(f"                {type(r.error).__name__}: {r.error}")

    _print_next_steps(target_dir, results, server_name, skipped=skipped)
    # Exit non-zero if every detected path failed; succeed if at least
    # one path was written or the user opted out via --no-claude-desktop.
    if results and not any(r.written for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

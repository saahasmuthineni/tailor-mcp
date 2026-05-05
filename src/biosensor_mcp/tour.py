"""
Tour subcommand
===============
Scaffold a guided framework walkthrough from bundled fixtures.

The tour pattern is the framework's live-audience demo path —
distinct from ``biosensor-mcp demo`` (operator self-verification
on synthetic running-data; deferred rename to ``verify`` per
ROADMAP). A tour copies bundled synthetic fixtures into a target
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
    biosensor-mcp tour
    biosensor-mcp tour --variant=hip-lab
    biosensor-mcp tour --target=/some/other/path
    biosensor-mcp tour --no-claude-desktop --force
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
# round-trip, deep-merge into existing mcpServers). These are
# private helpers but live in the same package; treat them as
# package-internal not public API.
from biosensor_mcp.pilot import (
    _claude_desktop_config_path,
    _read_claude_config,
    _write_claude_config,
)

# Default scaffold root. Sits under the operator's biosensor-mcp
# config dir so a power user can co-locate, but completely
# segregated by the ``demos/`` subdir so ``rm -rf`` on either side
# stays scoped.
DEFAULT_TARGET_BASE = Path.home() / ".biosensor-mcp" / "demos"

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
    pkg_root = files("biosensor_mcp._fixtures").joinpath(fixtures_subpkg)
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
    from biosensor_mcp.framework.vault.rescan import rescan_vault
    from biosensor_mcp.framework.vault.storage import VaultStorage

    data_dir = target_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    storage = VaultStorage(data_dir / "vault.db")
    try:
        return rescan_vault(target_dir / "vault", storage)
    finally:
        storage.close()


# ──────────────────────────────────────────────────────────────────────
# Claude Desktop registration — bakes BIOSENSOR_CONFIG_DIR and
# BIOSENSOR_DATA_DIR into the entry's env block so the recipient
# never types an env var. Closes auditor blocker 1.
# ──────────────────────────────────────────────────────────────────────


def _register_with_claude_desktop(
    target_dir: Path, *, server_name: str,
) -> Path | None:
    config_path = _claude_desktop_config_path()
    if config_path is None:
        return None  # Linux build — no Claude Desktop on this platform
    config, had_bom = _read_claude_config(config_path)
    servers = config.setdefault("mcpServers", {})
    servers[server_name] = {
        "command": sys.executable,
        "args": ["-m", "biosensor_mcp", "serve"],
        "env": {
            "BIOSENSOR_CONFIG_DIR": str(target_dir),
            "BIOSENSOR_DATA_DIR": str(target_dir / "data"),
        },
    }
    _write_claude_config(config_path, config, with_bom=had_bom)
    return config_path


# ──────────────────────────────────────────────────────────────────────
# Output
# ──────────────────────────────────────────────────────────────────────


def _resolve_target(variant: str, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    _, subdir = _VARIANT_FIXTURES[variant]
    return (DEFAULT_TARGET_BASE / subdir).resolve()


def _print_next_steps(
    target_dir: Path, claude_config: Path | None, server_name: str,
) -> None:
    print()
    print("=" * 64)
    print("  Tour scaffolded successfully")
    print("=" * 64)
    print(f"  Target dir:     {target_dir}")
    print(f"  user_config:    {target_dir / 'user_config.json'}")
    print(f"  vault index:    {target_dir / 'data' / 'vault.db'}")
    if claude_config is not None:
        print(f"  Claude Desktop: registered as '{server_name}' in")
        print(f"                  {claude_config}")
        print()
        print("  Next: fully quit Claude Desktop (system tray Quit on Windows,")
        print("        Cmd+Q on macOS), then re-open it. Try this prompt:")
        print()
        print('    "List the available biosensor MCP tools."')
    else:
        print("  Claude Desktop: not registered")
        print(f"  Manual env vars: BIOSENSOR_CONFIG_DIR={target_dir}")
        print(f"                   BIOSENSOR_DATA_DIR={target_dir / 'data'}")
    print()


# ──────────────────────────────────────────────────────────────────────
# CLI entry
# ──────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="biosensor-mcp tour",
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
            "~/.biosensor-mcp/demos/<variant>/."
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

    # Guard against clobbering a non-tour directory. A prior tour
    # scaffold writes user_config.json — its presence is the cheap
    # "this dir is mine, refresh it" signal.
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
    claude_config: Path | None = None
    if args.no_claude_desktop:
        print("        skipped (--no-claude-desktop)")
    else:
        claude_config = _register_with_claude_desktop(
            target_dir, server_name=server_name,
        )
        if claude_config is not None:
            print(f"        wrote entry '{server_name}' to {claude_config}")
        else:
            print("        skipped (Linux, or APPDATA missing)")

    _print_next_steps(target_dir, claude_config, server_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())

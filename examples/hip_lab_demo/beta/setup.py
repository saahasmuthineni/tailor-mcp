"""
One-shot scaffolder for the HIP Lab demo (variant β).

Resolves absolute paths to this directory's csv/ and vault/ folders,
writes user_config.json, ensures the synthetic CSVs and metadata
sidecar exist (delegating to generate.py), and lays down the
pre-populated vault directory with the S004 EMG/force-decoupling seed
moment from "two weeks earlier" that the cross-session vault wow
moment depends on.

Idempotent. Re-running is safe — overwrites user_config.json with
the current absolute paths, regenerates the CSVs deterministically,
and rewrites the seed moment file. Useful when the directory has
been moved or renamed.

The framework reads user_config.json from $TAILOR_CONFIG_DIR
(default: ~/.tailor). The demo isolates by setting
TAILOR_CONFIG_DIR to this directory at runtime — no clobber to
the operator's real config:

    TAILOR_CONFIG_DIR=examples/hip_lab_demo/beta tailor serve

Usage:
    python examples/hip_lab_demo/beta/setup.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()
CSV_DIR = HERE / "csv"
VAULT_DIR = HERE / "vault"
MOMENTS_DIR = VAULT_DIR / "moments"
USER_CONFIG = HERE / "user_config.json"
GENERATE_SCRIPT = HERE / "generate.py"
SEED_MOMENT_PATH = MOMENTS_DIR / "2026-04-16-s004-emg-force-decoupling-suspected.md"

# The seed moment is dated 2026-04-16 — "two weeks earlier" relative to
# the demo's intended walkthrough date (2026-04-30). The wow moment is
# the LLM surfacing this when asked about S004 in the fresh session.
SEED_MOMENT_BODY = """\
---
domain: vault
note_type: moment
kind: moment
title: "S004 — atypical EMG/force decoupling under fatigue"
slug: "s004-emg-force-decoupling-suspected"
date: "2026-04-16"
linked_runs: []
linked_themes: []
subject_id: "S004"
generated_at: "2026-04-16T15:42:00Z"
tags:
  - moment
  - fatigue
  - emg-force-decoupling
  - sex-differences
---

# S004 — atypical EMG/force decoupling under fatigue

Reviewed S004's pilot trial today. The force trace looks typical for
a trained female subject in this protocol — peak around 140 N at
50 % MVC, decline rate ~3 % / min, time-to-failure right at the
female-cohort median. Nothing notable on the surface.

What stands out is the EMG envelope: it runs visibly above the
female-cohort baseline even in the early contractions, well before
fatigue should drive central-drive compensation. By the second half
of her trial the envelope is sitting at ~150 % of the cohort norm
while her force is on track for a normal failure point.

This is the EMG/force decoupling pattern Hunter & Senefeld 2024
flagged in the *J Physiol* review — high motor-unit recruitment
without commensurate force production, suggesting the central
nervous system is working harder per Newton of output. In
trained subjects this can mean recent overreaching, an undisclosed
upper-extremity issue, or a neural-fatigue substrate that hasn't
recovered from a prior session.

Worth flagging in her next session: ask about training load over
the past 7 days, and watch whether the EMG/force ratio normalises
on a fresh testing day. If it persists, this might be a single-
subject finding worth a closer look — the sex-differences fatigue
literature has hints in this direction but the published evidence
on individual-level decoupling is thin.

## Action

- Capture S004's training-load self-report at next session.
- Re-run the same protocol on a different day; compare EMG envelope
  trajectory.
- If the pattern repeats, this becomes a candidate for a single-
  subject case-study or a methods note on EMG/force-ratio
  reliability under fatigue.
"""


def _ensure_csvs() -> None:
    """Run generate.py if csv/ is empty or missing."""
    metadata_path = CSV_DIR / "metadata.json"
    if metadata_path.is_file() and any(CSV_DIR.glob("*.csv")):
        print(f"  csv/ already populated ({sum(1 for _ in CSV_DIR.glob('*.csv'))} files)")
        return
    print(f"  csv/ empty — running generate.py")
    result = subprocess.run(
        [sys.executable, str(GENERATE_SCRIPT)],
        check=True,
    )
    if result.returncode != 0:
        raise SystemExit("generate.py failed")


def _write_user_config() -> None:
    """Write user_config.json with absolute paths to this directory's
    csv/ and vault/."""
    config = {
        "vault_path": str(VAULT_DIR),
        "csv_dir": {
            "path": str(CSV_DIR),
            "timestamp_column": "timestamp",
            "timestamp_format": "%Y-%m-%dT%H:%M:%S",
            "value_columns": {
                "force_N": "Isometric force (N)",
                "emg_envelope_uV": "Surface EMG envelope (μV, post-rectification)",
                "hr_bpm": "Heart rate (bpm)",
                "rpe": "Rating of perceived exertion (Borg 6-20)",
            },
        },
    }
    USER_CONFIG.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote {USER_CONFIG.name}")


def _write_seed_moment() -> None:
    """Lay down the pre-populated S004 EMG/force-decoupling moment."""
    MOMENTS_DIR.mkdir(parents=True, exist_ok=True)
    SEED_MOMENT_PATH.write_text(SEED_MOMENT_BODY, encoding="utf-8")
    print(f"  wrote vault/{SEED_MOMENT_PATH.relative_to(VAULT_DIR)}")


def _index_vault() -> None:
    """Populate vault.db from the on-disk vault.

    The seed moment is written directly to the filesystem (rather than
    through VaultWriter, which would index-as-it-writes), so the SQLite
    index would otherwise stay empty until a user invoked vault_rescan
    inside the running server. Calling rescan_vault here closes that
    gap so the demo's Wow 2 prompt finds the seed on first run.
    """
    from tailor.framework.vault.rescan import rescan_vault
    from tailor.framework.vault.storage import VaultStorage

    data_dir = HERE / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    storage = VaultStorage(data_dir / "vault.db")
    try:
        counts = rescan_vault(VAULT_DIR, storage)
        added = counts.get("added", 0)
        modified = counts.get("modified", 0)
        skipped = counts.get("skipped", 0)
        deleted = counts.get("deleted", 0)
        print(
            f"  indexed vault.db: {added} added, {modified} modified, "
            f"{skipped} skipped, {deleted} deleted"
        )
    finally:
        storage.close()


def main() -> None:
    print(f"Setting up HIP Lab demo (variant beta) at {HERE}")
    print()
    print("(1/4) ensure synthetic CSVs + metadata.json exist")
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_csvs()
    print()
    print("(2/4) write user_config.json")
    _write_user_config()
    print()
    print("(3/4) seed the demo vault")
    _write_seed_moment()
    print()
    print("(4/4) index vault.db so the seed moment is searchable")
    _index_vault()
    print()
    print("Done. Next:")
    print()
    print(f"  TAILOR_CONFIG_DIR={HERE} tailor serve")
    print()
    print(
        "Or register the demo with Claude Desktop using the snippet in "
        "README.md (Wiring up Claude Desktop)."
    )


if __name__ == "__main__":
    main()

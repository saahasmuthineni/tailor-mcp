"""
One-shot scaffolder for the HIP Lab demo (variant *realistic*).

Resolves absolute paths to this directory's force/, emg/, mrs/ and
vault/ folders, writes user_config.json, ensures the synthetic CSVs
exist (delegating to generate.py), lays down the pre-populated
vault directory with the S004 EMG/force-decoupling seed moment from
"two weeks earlier" that the cross-session vault wow moment depends
on, and indexes the vault.db so the seed moment is searchable.

Idempotent. Re-running is safe — overwrites user_config.json with
current absolute paths, regenerates the CSVs deterministically, and
rewrites the seed moment file. Useful when the directory has been
moved or renamed.

The framework reads user_config.json from $BIOSENSOR_CONFIG_DIR
(default: ~/.biosensor-mcp). The demo isolates by setting
BIOSENSOR_CONFIG_DIR to this directory at runtime — no clobber to
the operator's real config:

    BIOSENSOR_CONFIG_DIR=examples/hip_lab_demo/realistic biosensor-mcp serve

Usage:
    python examples/hip_lab_demo/realistic/setup.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()
FORCE_DIR = HERE / "force"
EMG_DIR = HERE / "emg"
MRS_DIR = HERE / "mrs"
VAULT_DIR = HERE / "vault"
MOMENTS_DIR = VAULT_DIR / "moments"
USER_CONFIG = HERE / "user_config.json"
GENERATE_SCRIPT = HERE / "generate.py"
SEED_MOMENT_PATH = MOMENTS_DIR / "2026-04-20-s004-emg-force-decoupling-suspected.md"

# The seed moment is dated 2026-04-20 — "two weeks earlier" relative
# to the demo's intended walkthrough date (2026-05-04+, off-blueprint
# detour). The wow moment is the LLM surfacing this when asked about
# S004 in the fresh session.
SEED_MOMENT_BODY = """\
---
domain: vault
note_type: moment
kind: moment
title: "S004 — atypical EMG/force decoupling under fatigue"
slug: "s004-emg-force-decoupling-suspected"
date: "2026-04-20"
linked_runs: []
linked_themes: []
subject_id: "S004"
generated_at: "2026-04-20T15:42:00Z"
tags:
  - moment
  - fatigue
  - emg-force-decoupling
  - sex-differences
  - multimodal
---

# S004 — atypical EMG/force decoupling under fatigue

Reviewed S004's last trial. Force trace looks typical for a trained
female subject in this protocol — peak around 230 N at 30 % MVC
sustained, decline rate sits in the female-cohort middle band, the
MVC probes step down at expected fatigue rates. Nothing notable on
the force side alone.

What stands out is the EMG envelope amplitude. S004's peak envelope
window sits around 240 µV — well above the rest of the female
cohort, whose peak envelopes group in the 150–205 µV range.
Notably the *shape* of her fatigue isn't unusual — peak-to-end
fatigue index lands in the cohort-typical 58–60 % band, same as
most other subjects.  The unusual signal is the absolute amplitude,
not the decline rate; her force production tracks an ordinary
failure profile through all of it.

This is the EMG/force decoupling pattern Hunter & Senefeld 2024
flagged in the *J Physiol* review — high motor-unit recruitment
without commensurate force production, suggesting the central
nervous system is working harder per Newton of output. In trained
subjects this can mean recent overreaching, an undisclosed
upper-extremity issue, or a neural-fatigue substrate that hasn't
recovered from a prior session.

Worth flagging in her next session: ask about training load over
the past 7 days, watch whether the EMG amplitude normalises on a
fresh testing day. If it persists, this might be a single-subject
finding worth a closer look — the sex-differences fatigue
literature has hints in this direction but the published evidence
on individual-level decoupling is thin.

## Action

- Capture S004's training-load self-report at next session.
- Re-run the same protocol on a different day; compare EMG envelope
  amplitude trajectory.
- If the pattern repeats, this becomes a candidate for a single-
  subject case study or a methods note on EMG/force-ratio
  reliability under fatigue.
- Once an mrs_csv child is wired, look for a paired PCr depletion
  signature — if PCr depletes faster than the cohort norm despite
  ordinary force output, the decoupling is metabolic-cost-side.
"""


def _ensure_csvs() -> None:
    """Run generate.py if any of force/, emg/, mrs/ is empty."""
    has_force = FORCE_DIR.is_dir() and any(FORCE_DIR.glob("*.csv"))
    has_emg = EMG_DIR.is_dir() and any(EMG_DIR.glob("*.csv"))
    has_mrs = MRS_DIR.is_dir() and any(MRS_DIR.glob("*.csv"))
    if has_force and has_emg and has_mrs:
        n_force = sum(1 for _ in FORCE_DIR.glob("*.csv"))
        n_emg = sum(1 for _ in EMG_DIR.glob("*.csv"))
        n_mrs = sum(1 for _ in MRS_DIR.glob("*.csv"))
        print(
            f"  csvs already populated "
            f"(force={n_force}, emg={n_emg}, mrs={n_mrs})"
        )
        return
    print("  one or more modality dirs empty — running generate.py")
    result = subprocess.run(
        [sys.executable, str(GENERATE_SCRIPT)],
        check=True,
    )
    if result.returncode != 0:
        raise SystemExit("generate.py failed")


def _write_user_config() -> None:
    """Write user_config.json with absolute paths to this directory's
    force/, emg/, and vault/."""
    config = {
        "vault_path": str(VAULT_DIR),
        "force_csv": {
            "path": str(FORCE_DIR),
            "timestamp_column": "t_s",
            "sample_rate_hz": 100.0,
            "value_columns": {"force": "force_N"},
        },
        "emg_csv": {
            "path": str(EMG_DIR),
            "timestamp_column": "t_s",
            "sample_rate_hz": 100.0,
            "value_columns": {"envelope": "envelope_uV"},
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

    The seed moment is written directly to the filesystem (rather
    than through VaultWriter, which would index-as-it-writes), so
    the SQLite index would otherwise stay empty until a user invoked
    vault_rescan inside the running server. Calling rescan_vault here
    closes that gap so the demo's "wow moment" search lands on first
    run.
    """
    from biosensor_mcp.framework.vault.rescan import rescan_vault
    from biosensor_mcp.framework.vault.storage import VaultStorage

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
    print(f"Setting up HIP Lab demo (variant realistic) at {HERE}")
    print()
    print("(1/4) ensure synthetic multimodal CSVs exist")
    for d in (FORCE_DIR, EMG_DIR, MRS_DIR):
        d.mkdir(parents=True, exist_ok=True)
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
    print(f"  BIOSENSOR_CONFIG_DIR={HERE} biosensor-mcp serve")
    print()
    print(
        "Or register the demo with Claude Desktop using the snippet "
        "in README.md (Wiring up Claude Desktop)."
    )


if __name__ == "__main__":
    main()

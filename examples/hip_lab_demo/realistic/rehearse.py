"""
rehearse.py — non-interactive end-to-end check of the HIP Lab demo
realistic walkthrough.

Calls each tool the demo's 7-step walkthrough exercises, prints the
key numbers, and checks them against the expected ranges from
CUE_CARD.md.  Designed to run BEFORE the meeting, on the demo
laptop, with no Claude in the loop:

    python examples/hip_lab_demo/realistic/rehearse.py

Exit code 0 = every check green, demo is rehearsal-ready.  Non-zero
= at least one check failed; the failure mode is identified before
the meeting, not during.

Per-child execute() bypasses the router (no consent/cost/audit), so
this rehearsal exercises the analytical correctness of each tool —
the same numbers Claude will see when it calls the same tools at
meeting time.  Audit-log behaviour (step 6 of the walkthrough) is
verified in the live demo, not here.

The bridge between step 4 (fresh emg_envelope_summary on S004) and
step 5 (vault search surfacing the prior 2026-04-20 moment) is on
PEAK AMPLITUDE (~238 µV vs the seed moment's "around 240 µV"),
NOT on fatigue_index_pct.  The 2026-05-04 sanity check found that
S004's fatigue_index_pct sits at the cohort median — a fatigue
physiologist would catch any "this is unusually steep" framing.
The fixture's deliberate signal is amplitude elevation; the bridge
must point at it.  Step 4b enforces the cohort-relativity claim
(S004 strictly above all other female peaks, ratio >= 1.20 vs the
other-female mean) so that future drift in generate.py can't
silently flatten the demo's wow.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Callable

# Reconfigure stdout/stderr to UTF-8 so the rehearsal output renders
# the same on cp1252 Windows terminals (the default demo-laptop
# situation) as it does on macOS/Linux.  Without this, em-dashes and
# inequality glyphs can either crash the encoder or render as `?`.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent.resolve()
DATA_DIR = HERE / "data"
CONFIG_DIR = HERE  # user_config.json lives next to this file


def _check(
    label: str,
    actual: Any,
    predicate: Callable[[Any], bool],
    expected_desc: str,
) -> bool:
    ok = predicate(actual)
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {label}")
    print(f"         actual:   {actual!r}")
    print(f"         expected: {expected_desc}")
    return ok


def _section(title: str) -> None:
    print()
    print(f"[{title}]")


async def main() -> int:
    if not (HERE / "user_config.json").exists():
        print("user_config.json missing — run `python setup.py` first.")
        return 2

    # Match what the live demo does: BIOSENSOR_CONFIG_DIR isolates
    # the demo from the operator's real config.
    os.environ["BIOSENSOR_CONFIG_DIR"] = str(CONFIG_DIR)
    os.environ["BIOSENSOR_DATA_DIR"] = str(DATA_DIR)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Late imports so a missing user_config.json fails fast above
    # rather than as an obscure import-time error.
    from biosensor_mcp.children.emg_csv import EmgCsvChild
    from biosensor_mcp.children.force_csv import ForceCsvChild
    from biosensor_mcp.framework.vault.storage import VaultStorage

    force = ForceCsvChild(CONFIG_DIR, DATA_DIR)
    emg = EmgCsvChild(CONFIG_DIR, DATA_DIR)

    results: list[bool] = []

    print("=" * 64)
    print(" HIP Lab demo — REHEARSAL (realistic variant)")
    print(f" Config dir: {CONFIG_DIR}")
    print(f" Data dir:   {DATA_DIR}")
    print("=" * 64)

    # --Step 2 — cohort sex difference ────────────────────────────
    _section("Step 2 — force_cohort_summary group_field=sex metric=max")
    r = await force.execute("force_cohort_summary", {
        "group_field": "sex",
        "value_column": "force_N",
        "metric": "max",
    })
    if "error" in r:
        results.append(_check(
            "force_cohort_summary call ok",
            f"ERROR: {r['error']}",
            lambda _: False,
            "no error",
        ))
    else:
        groups = r.get("groups", {})
        f_mean = groups.get("F", {}).get("mean")
        m_mean = groups.get("M", {}).get("mean")
        results.append(_check(
            "F cohort peak ~200 N", f_mean,
            lambda x: x is not None and 180 <= x <= 230,
            "180-230",
        ))
        results.append(_check(
            "M cohort peak ~276 N", m_mean,
            lambda x: x is not None and 250 <= x <= 320,
            "250-320",
        ))
        results.append(_check(
            "M peak > F peak (sex difference visible)",
            (m_mean, f_mean),
            lambda pair: (
                pair[0] is not None and pair[1] is not None and pair[0] > pair[1]
            ),
            "M cohort mean > F cohort mean",
        ))

    # --Step 3 — S004 force summary ───────────────────────────────
    _section("Step 3 — force_summary file_id=S004_force.csv")
    r = await force.execute("force_summary", {"file_id": "S004_force.csv"})
    if "error" in r:
        results.append(_check(
            "force_summary call ok",
            f"ERROR: {r['error']}",
            lambda _: False,
            "no error",
        ))
    else:
        peak = r.get("peak")
        mvc = r.get("mvc_window_mean_250ms")
        results.append(_check(
            "S004 force peak ~229 N", peak,
            lambda x: x is not None and 200 <= x <= 260,
            "200-260",
        ))
        results.append(_check(
            "S004 MVC window mean ~226 N", mvc,
            lambda x: x is not None and 200 <= x <= 260,
            "200-260",
        ))

    # --Step 4 — S004 EMG envelope summary ────────────────────────
    _section("Step 4 — emg_envelope_summary file_id=S004_emg.csv")
    r = await emg.execute("emg_envelope_summary", {"file_id": "S004_emg.csv"})
    if "error" in r:
        results.append(_check(
            "emg_envelope_summary call ok",
            f"ERROR: {r['error']}",
            lambda _: False,
            "no error",
        ))
    else:
        s004_peak = r.get("peak_envelope_window_mean")
        results.append(_check(
            "S004 peak_envelope_window_mean ~238 uV (the bridge number)",
            s004_peak,
            lambda x: x is not None and 220 <= x <= 260,
            "220-260 uV (bridges to seed-moment 'around 240 uV')",
        ))

    # Cohort-relativity check: S004's peak must be meaningfully
    # above the rest of the female cohort.  This catches future
    # drift in generate.py that might flatten S004's deliberately-
    # engineered amplitude elevation — without this check, the
    # demo's wow could silently devolve into "S004 peak == cohort
    # median" again, which is the failure mode the 2026-05-04
    # sanity check caught.
    _section("Step 4b — female cohort relativity (S004 vs other 7 F subjects)")
    female_ids = ["S001", "S003", "S004", "S006", "S008", "S010", "S013", "S015"]
    other_female_peaks: list[float] = []
    s004_peak_for_check: float | None = None
    for sid in female_ids:
        rr = await emg.execute("emg_envelope_summary", {"file_id": f"{sid}_emg.csv"})
        peak = rr.get("peak_envelope_window_mean")
        if peak is None:
            continue
        if sid == "S004":
            s004_peak_for_check = peak
        else:
            other_female_peaks.append(peak)
    if s004_peak_for_check is not None and other_female_peaks:
        cohort_mean = sum(other_female_peaks) / len(other_female_peaks)
        cohort_max = max(other_female_peaks)
        ratio_to_mean = s004_peak_for_check / cohort_mean
        results.append(_check(
            "S004 peak >= 1.20x other-female cohort mean (deliberate signal)",
            f"S004={s004_peak_for_check:.1f}, "
            f"cohort_mean={cohort_mean:.1f}, ratio={ratio_to_mean:.3f}",
            lambda _: ratio_to_mean >= 1.20,
            "ratio >= 1.20 (else S004 is not the outlier the demo claims)",
        ))
        results.append(_check(
            "S004 peak is the maximum across the female cohort",
            f"S004={s004_peak_for_check:.1f}, "
            f"max_of_other_females={cohort_max:.1f}",
            lambda _: s004_peak_for_check > cohort_max,
            "S004 strictly greater than every other female peak",
        ))
    else:
        results.append(_check(
            "female cohort data loaded",
            f"missing — S004={s004_peak_for_check}, "
            f"others_count={len(other_female_peaks)}",
            lambda _: False,
            "S004 peak + at least one other female peak",
        ))

    # --Step 5 — vault search surfaces seed moment ────────────────
    _section("Step 5 — vault list_notes subject_id=S004")
    storage = VaultStorage(DATA_DIR / "vault.db")
    try:
        notes = storage.list_notes(subject_id="S004")
        s004_moments = [
            n for n in notes
            if "s004" in (n.get("filename") or "").lower()
            and n.get("note_type") == "moment"
        ]
        results.append(_check(
            "S004 seed moment indexed in vault.db",
            f"{len(s004_moments)} hit(s): "
            f"{[n.get('filename') for n in s004_moments]}",
            lambda _: len(s004_moments) >= 1,
            ">= 1 moment file with 'S004' in filename",
        ))

        # Verify the on-disk seed moment file contains the bridge
        # phrasing.  Bridge is on PEAK AMPLITUDE (~240 uV), not
        # fatigue index — the 2026-05-04 sanity check showed
        # fatigue_index_pct is cohort-typical, so claiming it as the
        # wow signal would be physiologically false.  See
        # docstring of this script.
        seed_path = (
            HERE / "vault" / "moments"
            / "2026-04-20-s004-emg-force-decoupling-suspected.md"
        )
        if seed_path.exists():
            body = seed_path.read_text(encoding="utf-8")
            has_bridge_phrase = "around 240" in body
            has_cohort_range = "150" in body and "205" in body
            has_no_false_decline_claim = "close to 60 percent" not in body
            results.append(_check(
                "seed moment contains the ~240 uV peak-amplitude bridge",
                f"around_240={has_bridge_phrase}, "
                f"cohort_150_205={has_cohort_range}",
                lambda _: has_bridge_phrase and has_cohort_range,
                "seed moment names 'around 240' AND the 150-205 cohort range",
            ))
            results.append(_check(
                "seed moment does NOT make the false 'close to 60% decline' claim",
                "absent" if has_no_false_decline_claim else "PRESENT (regression!)",
                lambda x: x == "absent",
                "fatigue-index framing must not be the wow signal",
            ))
        else:
            results.append(_check(
                "seed moment file exists",
                f"NOT FOUND: {seed_path}",
                lambda _: False,
                f"{seed_path} present",
            ))
    finally:
        storage.close()

    # --Step 6 — audit log structural check ───────────────────────
    _section("Step 6 — audit.db structural check")
    audit_db = DATA_DIR / "audit.db"
    print(
        f"         audit.db {'exists' if audit_db.exists() else 'will be created on first router call'}: "
        f"{audit_db}"
    )
    print(
        "         (rehearse.py calls children directly, bypassing the router — "
        "actual audit rows will land during the live walkthrough.)"
    )

    # --Cleanup ───────────────────────────────────────────────────
    force.close()
    emg.close()

    # --Summary ───────────────────────────────────────────────────
    print()
    print("=" * 64)
    n_pass = sum(results)
    n_total = len(results)
    if n_pass == n_total:
        print(f" REHEARSAL: ALL {n_total} CHECKS PASSED — demo is rehearsal-ready.")
        print(" Open a fresh Claude Desktop chat and walk CUE_CARD.md.")
        return 0
    else:
        print(
            f" REHEARSAL: {n_pass}/{n_total} checks passed — "
            f"{n_total - n_pass} FAIL line(s) above."
        )
        print(" Fix before the meeting.  See README → Fallback table.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

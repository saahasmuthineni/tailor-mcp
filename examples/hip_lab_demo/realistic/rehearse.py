"""
rehearse.py — non-interactive end-to-end check of the HIP Lab
fitting-room realistic walkthrough.

Scaffolds a fresh fitting-room into a temp directory, calls each
tool the walkthrough exercises, asserts the bridge numbers and the
cross-session-memory invariant, and exits 0 on green. No state
lands outside the temp dir — the dev's ~/.tailor/ is
untouched.

Usage:
    python examples/hip_lab_demo/realistic/rehearse.py

Exit code 0 = every check green, the fitting-room is rehearsal-ready.
Non-zero = at least one check failed; the failure mode is named
on the FAIL line(s) above the summary.

The bridge between step 4 (fresh emg_envelope_summary on S004) and
step 5 (vault search surfacing the prior 2026-04-20 moment) is on
PEAK AMPLITUDE (~238 µV vs the seed moment's "around 240 µV"), NOT
on fatigue_index_pct. The 2026-05-04 sanity check found that S004's
fatigue_index_pct sits at the cohort median — a fatigue physiologist
would catch any "this is unusually steep" framing. The fixture's
deliberate signal is amplitude elevation; the bridge must point at
it. Step 4b enforces the cohort-relativity claim (S004 strictly
above all other female peaks, ratio >= 1.20 vs the other-female
mean) so future drift in generate.py can't silently flatten the
demo's wow.

Per ADR 0024 the fitting-room fixtures live in the bundled package
tree (``src/tailor/_fixtures/hip_lab_demo_realistic/``); this script
scaffolds them into a temp dir via ``tailor.tour`` (the v6.9.0 module
path retained as a re-export shim through v7.1.x per ADR 0035; the
canonical module is now ``tailor.fitting_room``) the same way mom or
Senefeld would in a real install. That makes the rehearsal exercise
the *recipient* code path, not a back-channel.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Reconfigure stdout/stderr to UTF-8 so the rehearsal output renders
# the same on cp1252 Windows terminals (the default demo-laptop
# situation) as it does on macOS/Linux. Without this, em-dashes and
# inequality glyphs can either crash the encoder or render as `?`.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


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


async def _run_checks(target: Path) -> int:
    # Match what the live fitting-room does — set env vars so the
    # children's config.py reads from the temp scaffold rather than
    # the dev's real ~/.tailor/.
    os.environ["TAILOR_CONFIG_DIR"] = str(target)
    os.environ["TAILOR_DATA_DIR"] = str(target / "data")

    # Late imports so the fitting-room scaffold (which set up
    # user_config.json) runs before child config-load.
    from tailor.children.emg_csv import EmgCsvChild
    from tailor.children.force_csv import ForceCsvChild
    from tailor.framework.vault.storage import VaultStorage

    force = ForceCsvChild(target, target / "data")
    emg = EmgCsvChild(target, target / "data")

    results: list[bool] = []

    print()
    print("=" * 64)
    print(" HIP Lab fitting-room — REHEARSAL (variant=hip-lab)")
    print(f" Target dir: {target}")
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

    # Cohort-relativity check: S004's peak must be meaningfully above
    # the rest of the female cohort. This catches future drift in
    # generate.py that might flatten S004's deliberately-engineered
    # amplitude elevation — without this check, the demo's wow could
    # silently devolve into "S004 peak == cohort median" again.
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
    storage = VaultStorage(target / "data" / "vault.db")
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

        seed_path = (
            target / "vault" / "moments"
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

    # --Cleanup ───────────────────────────────────────────────────
    force.close()
    emg.close()

    # --Summary ───────────────────────────────────────────────────
    print()
    print("=" * 64)
    n_pass = sum(results)
    n_total = len(results)
    if n_pass == n_total:
        print(
            f" REHEARSAL: ALL {n_total} CHECKS PASSED — fitting-room is "
            f"rehearsal-ready."
        )
        print(" Open a fresh Claude Desktop chat and walk CUE_CARD.md.")
        return 0
    else:
        print(
            f" REHEARSAL: {n_pass}/{n_total} checks passed — "
            f"{n_total - n_pass} FAIL line(s) above."
        )
        print(" Fix before the meeting. See README -> Fallback table.")
        return 1


async def main() -> int:
    with tempfile.TemporaryDirectory(prefix="biosensor_tour_rehearse_") as tmp:
        target = Path(tmp) / "hip-lab"

        # Scaffold a fresh fitting-room into the temp dir.
        # --no-claude-desktop so the dev's Claude Desktop config
        # stays untouched.
        # NOTE: ``tailor.tour`` is the v6.9.0 module path retained as
        # a re-export shim through v7.1.x per ADR 0035; canonical
        # module is now ``tailor.fitting_room``. Import flips in
        # v7.2.0 when the shim retires.
        from tailor.tour import main as tour_main
        rc = tour_main([
            "--variant=hip-lab",
            "--no-claude-desktop",
            "--target", str(target),
        ])
        if rc != 0:
            print(f"fitting-room scaffold failed (rc={rc})")
            return rc

        return await _run_checks(target)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

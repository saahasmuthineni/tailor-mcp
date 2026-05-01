"""
Generate synthetic per-subject CSVs for the HIP Lab demo (variant β).

Sixteen subjects (8 M, 8 F) performing an intermittent isometric handgrip
task at 50% MVC (6 s contraction / 4 s rest) to volitional failure.
Per-second sampling: ``timestamp, force_N, emg_envelope_uV, hr_bpm, rpe``.
RPE is sparse — sampled every 30 s to mirror Borg-scale collection
practice; the column reads NaN-like (empty string) on intermediate rows
and surfaces as ~3.3 % completeness in ``csv_summary_report``. That is
correct, not a broken file (see README "Lampshades" section).

Calibration grounded in the Hunter & Senefeld 2024 *J Physiol* paper on
sex differences in human performance and the wider literature on
submaximal isometric fatigue. Female subjects: lower MVC, longer
time-to-failure, shallower decline rate. Male subjects: higher MVC,
shorter TTF, steeper decline. Group overlap is intentional so the
cohort comparison reads as real data rather than stat-shopped fake;
the t-test for sex difference at n=8 per arm is positive but not
overwhelming, which is what real fatigue data of this shape produces.

Subject S004 is given a deliberate EMG/force decoupling: her EMG
envelope runs ~45 % above the female-cohort baseline while her force
trace tracks normally for her sex/age. The pre-populated vault seed
moment from "two weeks earlier" flags this — the cross-session memory
wow moment is the LLM surfacing that prior moment alongside fresh
altitude-decrement data on the same subject.

Reproducible: seeded ``random.Random(20260418)``. Per ADR 0008 the
seeded-PRNG-off-the-analytical-path exception applies — this is fixture
data, not framework or child processing. Re-running this script
overwrites the CSVs deterministically.

Usage:
    python examples/hip_lab_demo/beta/generate.py
"""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

# Single seeded RNG; advanced deterministically per subject in ID order.
_RNG = random.Random(20260418)

HERE = Path(__file__).parent
OUT = HERE / "csv"

# Protocol parameters
CONTRACTION_S = 6
REST_S = 4
RPE_INTERVAL_S = 30
START_TIME = datetime(2026, 4, 18, 9, 30, 0)

# Pre-assigned sex per subject ID — intermixed so a casual look at the
# filename order does not telegraph the grouping. 8 F + 8 M = 16.
SUBJECT_SEX: dict[int, str] = {
    1: "F", 2: "M", 3: "F", 4: "F", 5: "M", 6: "F", 7: "M", 8: "F",
    9: "M", 10: "F", 11: "F", 12: "M", 13: "M", 14: "F", 15: "M", 16: "M",
}
assert sum(1 for v in SUBJECT_SEX.values() if v == "F") == 8
assert sum(1 for v in SUBJECT_SEX.values() if v == "M") == 8


def make_subject(idx: int) -> dict:
    """Pre-randomized parameters for one subject. Advances the RNG."""
    sex = SUBJECT_SEX[idx]
    if sex == "F":
        mvc = round(_RNG.uniform(255, 320), 1)             # N — handgrip MVC
        ttf_s = max(420, int(round(_RNG.gauss(720, 90))))  # ~12 min median
        decline = round(_RNG.uniform(2.5, 4.0), 2)         # %/min — shallower
        age = _RNG.randint(22, 32)
        training = round(_RNG.uniform(2, 6), 1)
    else:
        mvc = round(_RNG.uniform(420, 540), 1)
        ttf_s = max(300, int(round(_RNG.gauss(440, 80))))  # ~7 min median
        decline = round(_RNG.uniform(3.5, 5.5), 2)         # %/min — steeper
        age = _RNG.randint(22, 35)
        training = round(_RNG.uniform(3, 9), 1)
    return {
        "id": f"S{idx:03d}",
        "sex": sex,
        "age": age,
        "training_h_per_wk": training,
        "max_force_baseline_N": mvc,
        "_ttf_s": ttf_s,
        "_decline_pct_per_min": decline,
    }


def generate_rows(subject: dict) -> list[dict]:
    """One subject's per-second CSV rows from t=0 to t=TTF inclusive."""
    mvc = subject["max_force_baseline_N"]
    target = 0.50 * mvc                                     # 50% MVC
    ttf_s = subject["_ttf_s"]
    decline_per_s = subject["_decline_pct_per_min"] / 100 / 60
    is_s004 = subject["id"] == "S004"

    rows: list[dict] = []
    for t in range(ttf_s + 1):
        cycle_pos = t % (CONTRACTION_S + REST_S)
        is_contracting = cycle_pos < CONTRACTION_S
        # Fatigue floor at 0.4 — no subject is allowed to drop below 40%
        # of their starting target before failure cuts the recording.
        fatigue_factor = max(0.4, 1.0 - t * decline_per_s)

        if is_contracting:
            within_decay = 1.0 - 0.02 * cycle_pos
            force = target * fatigue_factor * within_decay
            force += _RNG.gauss(0, mvc * 0.012)
            emg_baseline = 50 + (t / max(1, ttf_s)) * 200
            emg = emg_baseline + _RNG.gauss(0, 12)
            if is_s004:
                emg *= 1.45  # S004 EMG/force decoupling (the demo seed)
        else:
            force = mvc * 0.025 + _RNG.gauss(0, mvc * 0.004)
            emg = 5 + _RNG.gauss(0, 1.5)

        force = max(0.0, force)
        emg = max(0.0, emg)

        hr_base = 75 + (t / max(1, ttf_s)) * 50
        hr = hr_base + _RNG.gauss(0, 2.5)
        if subject["sex"] == "M":
            hr -= 2
        hr = max(60.0, min(200.0, hr))

        if t > 0 and t % RPE_INTERVAL_S == 0:
            rpe_target = 9 + (t / max(1, ttf_s)) * 10
            rpe_int = max(6, min(20, int(round(rpe_target + _RNG.gauss(0, 0.5)))))
            rpe_str = str(rpe_int)
        else:
            rpe_str = ""

        ts = (START_TIME + timedelta(seconds=t)).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append({
            "timestamp": ts,
            "force_N": round(force, 2),
            "emg_envelope_uV": round(emg, 2),
            "hr_bpm": round(hr, 1),
            "rpe": rpe_str,
        })
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # Literal fieldnames list — ADR 0008 determinism: do not rely on
    # dict iteration order across CPython versions.
    fieldnames = ["timestamp", "force_N", "emg_envelope_uV", "hr_bpm", "rpe"]
    metadata: dict[str, dict] = {}

    for i in range(1, 17):
        subject = make_subject(i)
        rows = generate_rows(subject)
        path = OUT / f"{subject['id']}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        metadata[f"{subject['id']}.csv"] = {
            "subject_id": subject["id"],
            "sex": subject["sex"],
            "age": subject["age"],
            "training_h_per_wk": subject["training_h_per_wk"],
            "max_force_baseline_N": subject["max_force_baseline_N"],
        }
        print(
            f"  {subject['id']} ({subject['sex']}, age {subject['age']}): "
            f"TTF={subject['_ttf_s']}s, "
            f"decline={subject['_decline_pct_per_min']}%/min, "
            f"{len(rows)} rows -> {path.name}"
        )

    meta_path = OUT / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"\n  metadata.json: {len(metadata)} subjects -> {meta_path}")


if __name__ == "__main__":
    main()

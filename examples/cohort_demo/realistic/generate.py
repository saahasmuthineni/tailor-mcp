"""
Generate synthetic per-subject paired multimodal data for the
demo cohort (variant *realistic*).

Sixteen subjects (8 M, 8 F) performing a HYBRID isometric protocol
designed to surface the multimodal-composition demo argument:

  60 s sustained 30%-MVC contraction
    + brief MVC probes at t = 15 s, 30 s, 45 s, 60 s (3 s each)

The protocol shape is informed by Hunter & Senefeld 2024 (*J Physiol*
602.17, sex differences in human performance — intermittent isometric
to volitional failure) compressed for demo: real 30% MVC sustained
contractions take 3-5 minutes to fatigue in untrained subjects; this
demo uses steeper-than-real fatigue rates so visible decline happens
within 60 s and a reader can read one trial in ~30 s.

Three paired streams per subject:

- ``force/<SUBJ>_force.csv`` — isometric force trace, 100 Hz
- ``emg/<SUBJ>_emg.csv`` — surface EMG rectified envelope, 100 Hz
- ``mrs/<SUBJ>_mrs.csv`` — 31P-MRS PCr/Pi trajectory, 0.05 Hz
  (one sample every 20 s; stub format — no mrs_csv child exists
  yet, the file ships to demonstrate the multimodal storyline)

All three streams share ``subject_id`` keying so the analyst can
query *"show me S004's force decline alongside their EMG fatigue
progression and PCr depletion across this trial"* once force_csv
and emg_csv are registered.  This is the framework's existing
``dispatch_internal`` cross-child seam realised in fixture data.

Sex differences are encoded honestly per the literature shape —
Female subjects: lower MVC, longer time to amplitude collapse,
shallower force-decline rate, faster EMG amplitude rise (recruitment
to compensate).  Male subjects: higher MVC, steeper decline.  Group
overlap is intentional so cohort comparison reads as real data.

Subject S004 is given a deliberate EMG/force decoupling — her EMG
envelope rises ~45 % above the female-cohort baseline while her
force trace tracks normally for sex/age.  This is the "wow moment"
the beta variant also seeds, ported here because the multimodal
flavor makes the decoupling more visible (force_csv shows normal
decline; emg_csv shows abnormal recruitment).

Reproducible: seeded ``random.Random(20260504)`` (off-blueprint
detour date).  Per ADR 0008 the seeded-PRNG-off-the-analytical-path
exception applies via the ``examples/**/generate.py`` glob — this
is fixture data, not framework or child processing.

Usage:
    python examples/cohort_demo/realistic/generate.py
"""

from __future__ import annotations

import csv
import json
import math
import random
from pathlib import Path

# Single seeded RNG; advanced deterministically per subject in ID order.
_RNG = random.Random(20260504)

HERE = Path(__file__).parent
# Generated fixtures live in the package's bundled-fixtures tree so they
# ship inside the wheel. Per ADR 0024 the generator stays out of the
# wheel (examples/**/generate.py); only the generated CSVs + sidecars
# vendor in. Re-running this script overwrites the bundled tree.
PACKAGE_FIXTURES = (
    HERE.parents[2]
    / "src" / "tailor" / "_fixtures" / "cohort_demo_realistic"
)
FORCE_DIR = PACKAGE_FIXTURES / "force"
EMG_DIR = PACKAGE_FIXTURES / "emg"
MRS_DIR = PACKAGE_FIXTURES / "mrs"

# ─── Protocol parameters ───────────────────────────────────────────
SAMPLE_RATE_HZ = 100.0           # force + EMG rate
TRIAL_S = 60.0                   # sustained contraction duration
N_SAMPLES = int(TRIAL_S * SAMPLE_RATE_HZ)  # 6000
MRS_RATE_HZ = 0.05               # 1 sample per 20 s
N_MRS = int(TRIAL_S * MRS_RATE_HZ) + 1     # 4 samples (t=0,20,40,60)
PROBE_TIMES_S = [15.0, 30.0, 45.0, 60.0]
PROBE_DURATION_S = 2.0           # probe lasts 2s, ramp + hold

# Pre-assigned sex per subject ID — intermixed so a casual look at
# the filename order doesn't telegraph the grouping.
SUBJECT_SEX: dict[int, str] = {
    1: "F", 2: "M", 3: "F", 4: "F", 5: "M", 6: "F", 7: "M", 8: "F",
    9: "M", 10: "F", 11: "M", 12: "M", 13: "F", 14: "M", 15: "F", 16: "M",
}

# Group assignment (control vs intervention) — split orthogonally to
# sex so the cohort comparisons can intersect group × sex.
SUBJECT_GROUP: dict[int, str] = {
    1: "control", 2: "control", 3: "control", 4: "control",
    5: "control", 6: "control", 7: "control", 8: "control",
    9: "intervention", 10: "intervention", 11: "intervention",
    12: "intervention", 13: "intervention", 14: "intervention",
    15: "intervention", 16: "intervention",
}

# Sex-baseline MVC ranges (Newtons).  Calibrated to plantarflexor /
# handgrip handedness magnitudes Hunter & Senefeld 2024 cite —
# female cohort lower mean, both with within-group spread.
MVC_RANGE_F = (180.0, 240.0)     # N
MVC_RANGE_M = (260.0, 360.0)     # N

# Sex-baseline EMG envelope amplitude (μV, after rectification +
# low-pass to 100 Hz).  Same shape as MVC — broadly similar with
# moderate within-group spread.
EMG_BASELINE_F = (45.0, 75.0)    # μV
EMG_BASELINE_M = (55.0, 90.0)    # μV

# Decline rate per sex (fraction of MVC lost per 60s).  Female
# cohort declines slower per the literature.
DECLINE_PCT_F = (0.18, 0.30)     # 18-30% decline at 60s
DECLINE_PCT_M = (0.28, 0.42)     # 28-42% decline at 60s

# EMG amplitude trajectory: rises during fatigue (motor-unit
# recruitment compensation) before eventually falling at
# task failure.  Within the 60s window, expected to rise.
EMG_RISE_PCT_F = (0.10, 0.25)
EMG_RISE_PCT_M = (0.05, 0.20)

# S004's deliberate decoupling: EMG rises 45% above her baseline
# but force tracks normally for her sex/age.
S004_EMG_DECOUPLING_PCT = 0.45


def _round(v: float, n: int = 3) -> float:
    return round(v, n)


def _force_at(
    t: float, mvc: float, decline_frac: float, noise_amp: float,
) -> float:
    """Force at time t under sustained 30% MVC + intermittent probes.

    Sustained baseline: 30% MVC × (1 − decline_frac × t/TRIAL_S).
    During a probe window, force ramps up to current MVC capacity
    (which is itself fatigued) for PROBE_DURATION_S seconds.
    """
    # Current fatigued MVC (decreases linearly with t).
    fatigued_mvc = mvc * (1.0 - decline_frac * (t / TRIAL_S))
    sustained_target = 0.30 * fatigued_mvc

    # Check if t is inside any probe window.
    for probe_t in PROBE_TIMES_S:
        if probe_t <= t < probe_t + PROBE_DURATION_S:
            # Triangular: ramp up over first half, hold/decline second.
            phase = (t - probe_t) / PROBE_DURATION_S
            ramp = min(phase * 2.0, 1.0)
            target = sustained_target + ramp * (fatigued_mvc - sustained_target)
            return target + _RNG.uniform(-noise_amp, noise_amp)

    return sustained_target + _RNG.uniform(-noise_amp, noise_amp)


def _emg_at(
    t: float, baseline: float, rise_frac: float, noise_amp: float,
    decoupling_factor: float,
) -> float:
    """EMG envelope at time t.

    Baseline rises from baseline_uv to baseline_uv * (1 + rise_frac)
    over TRIAL_S, with brief amplitude bursts during MVC probes
    (motor-unit recruitment for the maximal effort).
    """
    # Sustained envelope (slowly rising).
    sustained = baseline * (1.0 + rise_frac * (t / TRIAL_S))
    sustained *= decoupling_factor

    # Probe boosts EMG amplitude transiently.
    for probe_t in PROBE_TIMES_S:
        if probe_t <= t < probe_t + PROBE_DURATION_S:
            phase = (t - probe_t) / PROBE_DURATION_S
            ramp = min(phase * 2.0, 1.0)
            return sustained * (1.0 + 1.5 * ramp) + _RNG.uniform(
                -noise_amp, noise_amp,
            )

    # Normal noise outside probes.
    noise = _RNG.uniform(-noise_amp, noise_amp)
    # Add a small high-frequency jitter to make envelope look real.
    jitter = 0.08 * baseline * math.sin(2 * math.pi * 0.7 * t)
    return max(0.0, sustained + noise + jitter)


def _mrs_pcr_at(t: float, decline_frac: float) -> float:
    """31P-MRS PCr concentration (relative units).

    Resting baseline is 1.0; PCr depletes monotonically under
    sustained contraction toward an asymptote ~ (1 − 1.5 × decline_frac).
    Real MRS lineshape is more complex; this is a stub that mimics
    the trajectory shape relevant for the multimodal storyline.
    """
    asymptote = 1.0 - 1.5 * decline_frac
    asymptote = max(0.20, asymptote)
    # Exponential approach to asymptote with τ ≈ TRIAL_S/2.
    tau = TRIAL_S / 2.0
    return asymptote + (1.0 - asymptote) * math.exp(-t / tau)


def _mrs_pi_at(pcr: float) -> float:
    """31P-MRS Pi (inorganic phosphate) — rises as PCr falls.

    Coupled by phosphocreatine-shuttle stoichiometry; in resting
    state Pi/PCr ≈ 0.1, depletion roughly conserves total phosphate.
    """
    return max(0.0, 1.1 - pcr)


def write_force_csv(subject_id: int, sex: str, mvc: float, decline_frac: float):
    fname = FORCE_DIR / f"S{subject_id:03d}_force.csv"
    noise_amp = mvc * 0.015  # ~1.5% of MVC
    with open(fname, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["t_s", "force_N"])
        for i in range(N_SAMPLES):
            t = i / SAMPLE_RATE_HZ
            v = _force_at(t, mvc, decline_frac, noise_amp)
            writer.writerow([f"{t:.3f}", f"{_round(v):.3f}"])


def write_emg_csv(
    subject_id: int, sex: str, baseline: float, rise_frac: float,
    decoupling_factor: float,
):
    fname = EMG_DIR / f"S{subject_id:03d}_emg.csv"
    noise_amp = baseline * 0.10
    with open(fname, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["t_s", "envelope_uV"])
        for i in range(N_SAMPLES):
            t = i / SAMPLE_RATE_HZ
            v = _emg_at(t, baseline, rise_frac, noise_amp, decoupling_factor)
            writer.writerow([f"{t:.3f}", f"{_round(v, 4):.4f}"])


def write_mrs_csv(subject_id: int, sex: str, decline_frac: float):
    """Single-format MRS stub.  No mrs_csv child exists yet —
    the file ships to demonstrate the multimodal storyline only."""
    fname = MRS_DIR / f"S{subject_id:03d}_mrs.csv"
    with open(fname, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["t_s", "pcr_relative", "pi_relative"])
        for i in range(N_MRS):
            t = i * (1.0 / MRS_RATE_HZ)  # 0, 20, 40, 60
            pcr = _mrs_pcr_at(t, decline_frac)
            pi = _mrs_pi_at(pcr)
            writer.writerow([f"{t:.1f}", f"{pcr:.4f}", f"{pi:.4f}"])


def main():
    for d in (FORCE_DIR, EMG_DIR, MRS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    force_metadata: dict[str, dict] = {}
    emg_metadata: dict[str, dict] = {}
    mrs_metadata: dict[str, dict] = {}

    for subject_id in range(1, 17):
        sex = SUBJECT_SEX[subject_id]
        group = SUBJECT_GROUP[subject_id]
        if sex == "F":
            mvc = _RNG.uniform(*MVC_RANGE_F)
            emg_baseline = _RNG.uniform(*EMG_BASELINE_F)
            decline_frac = _RNG.uniform(*DECLINE_PCT_F)
            rise_frac = _RNG.uniform(*EMG_RISE_PCT_F)
        else:
            mvc = _RNG.uniform(*MVC_RANGE_M)
            emg_baseline = _RNG.uniform(*EMG_BASELINE_M)
            decline_frac = _RNG.uniform(*DECLINE_PCT_M)
            rise_frac = _RNG.uniform(*EMG_RISE_PCT_M)

        # S004 EMG/force decoupling: her EMG runs above baseline,
        # her force tracks normally for sex/age.
        decoupling_factor = (
            1.0 + S004_EMG_DECOUPLING_PCT if subject_id == 4 else 1.0
        )

        write_force_csv(subject_id, sex, mvc, decline_frac)
        write_emg_csv(
            subject_id, sex, emg_baseline, rise_frac, decoupling_factor,
        )
        write_mrs_csv(subject_id, sex, decline_frac)

        sid_str = f"S{subject_id:03d}"
        force_metadata[f"{sid_str}_force.csv"] = {
            "entity_id": sid_str,
            "sex": sex,
            "group": group,
            "trial_protocol": "30pct_MVC_sustained_60s_with_4probes",
            "baseline_mvc_N": _round(mvc, 1),
        }
        emg_metadata[f"{sid_str}_emg.csv"] = {
            "entity_id": sid_str,
            "sex": sex,
            "group": group,
            "trial_protocol": "30pct_MVC_sustained_60s_with_4probes",
            "envelope_baseline_uV": _round(emg_baseline, 1),
        }
        mrs_metadata[f"{sid_str}_mrs.csv"] = {
            "entity_id": sid_str,
            "sex": sex,
            "group": group,
            "modality": "31P_MRS_stub",
        }

        # Console line for visibility when re-running.  ASCII-only
        # so Windows cp1252 consoles don't crash; CSVs are UTF-8.
        print(
            f"S{subject_id:03d} ({sex}, {group}): "
            f"MVC={mvc:6.1f} N, decline={decline_frac:.0%}, "
            f"EMG baseline={emg_baseline:5.1f} uV, rise={rise_frac:.0%}"
            + ("  [EMG/force DECOUPLING]" if subject_id == 4 else "")
        )

    # Write metadata.json sidecars (ADR 0015 schema).
    (FORCE_DIR / "metadata.json").write_text(
        json.dumps(force_metadata, indent=2), encoding="utf-8",
    )
    (EMG_DIR / "metadata.json").write_text(
        json.dumps(emg_metadata, indent=2), encoding="utf-8",
    )
    (MRS_DIR / "metadata.json").write_text(
        json.dumps(mrs_metadata, indent=2), encoding="utf-8",
    )
    print("\nWrote 16 subjects x 3 modalities into the bundled-fixtures tree")
    print(f"  package fixtures: {PACKAGE_FIXTURES}")
    print(f"    force/  -> {FORCE_DIR}")
    print(f"    emg/    -> {EMG_DIR}")
    print(f"    mrs/    -> {MRS_DIR}")
    print()
    print("The next tailor_fitting_room_scaffold call (or rehearse.py)")
    print("will pick up the regenerated fixtures from this location.")


if __name__ == "__main__":
    main()

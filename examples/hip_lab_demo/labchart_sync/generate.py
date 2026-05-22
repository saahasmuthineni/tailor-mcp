"""
Generate a synthetic ten-subject cohort for the csv_synchronized_windows
demo, modelled on Chunyu's real LabChart contraction-extraction workflow
(established by the 2026-05 lab-day recon).

THE REAL WORKFLOW (recon-grounded)
----------------------------------
Each recording is a multi-channel LabChart file on one shared clock:

    t_s, torque, gastroc_lat, gastroc_med, vastus_lat, vastus_med

- ``torque``        — isometric torque; the contraction anchor channel
- ``gastroc_lat`` / ``gastroc_med`` — gastrocnemius EMG (lateral/medial).
  This is the **target** muscle group: the protocol is built to fatigue
  it, so its EMG amplitude is *expected* to climb across the protocol
  (motor-unit recruitment compensating for fatiguing fibres).
- ``vastus_lat`` / ``vastus_med``   — vastus (quadriceps) EMG. This is
  the **watch-list**: the quads should stay quiet. Quad EMG climbing
  across the protocol means the participant is "cheating" — recruiting
  the quads to spare the fatiguing gastroc. Catching that is the whole
  point of the analysis.

One **epoch** is one submaximal contraction; there are **7 per
participant**. The analyst finds, per epoch, the peak of the
contraction, takes a window 10 s to 5 s before that peak, and pulls
the RMS-EMG of each muscle plus the mean torque — by hand, into a
LabChart Data Pad, then into an Excel template. csv_synchronized_windows
collapses that loop.

WHAT IS A SYNTHETIC ESTIMATE (vs. recon-fact)
---------------------------------------------
Recon-fact: 5 channels + roles, 7 epochs, the [peak-10s, peak-5s]
window, RMS-for-EMG / mean-for-torque, the QC purpose.

Estimate (pending one real export from Chunyu's computer): the sample
rate (100 Hz here), the contraction duration (~28 s sustained holds
here), and the exact channel-name strings LabChart writes. None of
these are load-bearing — csv_synchronized_windows is detection-
threshold based and channel-name aliased, so the real file slots in
with a user_config.json edit, not a rebuild.

THE PLANTED FINDING
-------------------
Nine subjects are "clean": gastroc recruitment climbs across the 7
epochs (healthy fatiguing target), quad recruitment stays flat. ONE
subject is a "cheater": their quad (vastus) recruitment climbs across
the protocol — the compensation pattern. The demo exists to surface
that subject, so the tool is seen doing the QC, not just the
extraction. The cheater's identity is printed to the console only —
it is NOT in the data or the metadata sidecar.

Reproducible: seeded ``random.Random(20260522)``. This generator lives
under ``examples/`` — ADR 0008's no-PRNG-in-processing rule applies to
``children/*/processing.py``, not to fixture generators.

Usage:
    python examples/hip_lab_demo/labchart_sync/generate.py
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"

_RNG = random.Random(20260522)

# ─── Recording / protocol parameters ───────────────────────────────
N_SUBJECTS = 10
SAMPLE_RATE_HZ = 100.0          # synthetic estimate — real rate TBC
N_EPOCHS = 7                    # recon-fact: 7 contractions/participant
LEAD_IN_S = 8.0
RAMP_S = 3.0                    # contraction ramp up / down
CONTRACTION_S = 28.0            # 3 ramp + 22 hold + 3 ramp (estimate)
REST_S = 14.0
DURATION_S = LEAD_IN_S + N_EPOCHS * (CONTRACTION_S + REST_S)
N_SAMPLES = int(DURATION_S * SAMPLE_RATE_HZ)

# Exactly one subject is the planted "cheater" (quad compensation).
CHEATER_SUBJECT = 7

# ─── Per-subject signal parameters ─────────────────────────────────
MVC_RANGE = (160.0, 340.0)              # N.m
SUBMAX_FRACTION = 0.30                  # 30%-MVC submaximal target
REST_TORQUE = 2.0
REST_EMG_UV = 5.0

# EMG envelope amplitude during a contraction (uV).
GASTROC_AMP_RANGE = (90.0, 210.0)       # target muscle — substantial
VASTUS_AMP_RANGE = (20.0, 45.0)         # watch-list — low (quads quiet)

# Across-epoch recruitment trend (epoch 1 -> epoch 7), as a fraction.
GASTROC_RISE_RANGE = (0.22, 0.55)       # target fatigues -> recruits
VASTUS_CLEAN_TREND_RANGE = (-0.05, 0.12)  # clean subject: ~flat
VASTUS_CHEAT_RISE_RANGE = (0.35, 0.55)  # cheater: quad recruitment climbs


def _epoch_starts() -> list[float]:
    return [
        LEAD_IN_S + k * (CONTRACTION_S + REST_S) for k in range(N_EPOCHS)
    ]


def _contraction_weight(tl: float) -> float:
    """Envelope weight 0..1 within one contraction (local time ``tl``).

    Ramp up, a shallow mid-hold dome (so the torque peak is well-defined
    and lands mid-contraction — which keeps the [peak-10s, peak-5s]
    window inside the hold), then ramp down.
    """
    if tl < RAMP_S:
        return tl / RAMP_S
    if tl > CONTRACTION_S - RAMP_S:
        return max(0.0, (CONTRACTION_S - tl) / RAMP_S)
    # Hold: shallow dome, apex at the hold midpoint.
    hold_mid = CONTRACTION_S / 2.0
    half = (CONTRACTION_S - 2 * RAMP_S) / 2.0
    return 1.0 - 0.12 * ((tl - hold_mid) / half) ** 2


def _hold_progress(tl: float) -> float:
    """0..1 progress through the hold phase (0 outside the hold)."""
    if tl <= RAMP_S or tl >= CONTRACTION_S - RAMP_S:
        return 0.0
    return (tl - RAMP_S) / (CONTRACTION_S - 2 * RAMP_S)


def _write_subject(subject_id: int) -> dict:
    sid = f"S{subject_id:03d}"
    is_cheater = subject_id == CHEATER_SUBJECT

    mvc = _RNG.uniform(*MVC_RANGE)
    torque_target = SUBMAX_FRACTION * mvc
    gastroc_amp = _RNG.uniform(*GASTROC_AMP_RANGE)
    vastus_amp = _RNG.uniform(*VASTUS_AMP_RANGE)
    gastroc_rise = _RNG.uniform(*GASTROC_RISE_RANGE)
    if is_cheater:
        vastus_trend = _RNG.uniform(*VASTUS_CHEAT_RISE_RANGE)
    else:
        vastus_trend = _RNG.uniform(*VASTUS_CLEAN_TREND_RANGE)

    # Lateral / medial heads share the muscle's story; amplitudes differ.
    gl_amp, gm_amp = gastroc_amp, gastroc_amp * _RNG.uniform(0.70, 0.95)
    vl_amp, vm_amp = vastus_amp, vastus_amp * _RNG.uniform(0.75, 1.0)

    torque_noise = torque_target * 0.02
    starts = _epoch_starts()

    def _epoch_factor(k: int, rise: float) -> float:
        # Linear trend across the N_EPOCHS contractions.
        return 1.0 + rise * (k / (N_EPOCHS - 1))

    path = DATA_DIR / f"{sid}.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "t_s", "torque", "gastroc_lat", "gastroc_med",
            "vastus_lat", "vastus_med",
        ])
        for i in range(N_SAMPLES):
            t = i / SAMPLE_RATE_HZ

            epoch_k = -1
            tl = 0.0
            for k, start in enumerate(starts):
                if start <= t < start + CONTRACTION_S:
                    epoch_k, tl = k, t - start
                    break

            if epoch_k >= 0:
                w = _contraction_weight(tl)
                # Mild within-hold EMG creep on the fatiguing target.
                creep = 1.0 + 0.08 * _hold_progress(tl)
                g_fac = _epoch_factor(epoch_k, gastroc_rise) * creep
                v_fac = _epoch_factor(epoch_k, vastus_trend)
                torque = REST_TORQUE + w * torque_target
                gl = REST_EMG_UV + w * gl_amp * g_fac
                gm = REST_EMG_UV + w * gm_amp * g_fac
                vl = REST_EMG_UV + w * vl_amp * v_fac
                vm = REST_EMG_UV + w * vm_amp * v_fac
            else:
                torque, gl, gm, vl, vm = (
                    REST_TORQUE, REST_EMG_UV, REST_EMG_UV,
                    REST_EMG_UV, REST_EMG_UV,
                )

            torque += _RNG.uniform(-torque_noise, torque_noise)
            gl += _RNG.uniform(-0.09 * gl_amp, 0.09 * gl_amp)
            gm += _RNG.uniform(-0.09 * gm_amp, 0.09 * gm_amp)
            vl += _RNG.uniform(-0.09 * vl_amp, 0.09 * vl_amp)
            vm += _RNG.uniform(-0.09 * vm_amp, 0.09 * vm_amp)

            writer.writerow([
                f"{t:.3f}",
                f"{max(0.0, torque):.4f}",
                f"{max(0.0, gl):.4f}",
                f"{max(0.0, gm):.4f}",
                f"{max(0.0, vl):.4f}",
                f"{max(0.0, vm):.4f}",
            ])

    tag = "  [CHEATER - quad compensation]" if is_cheater else ""
    print(
        f"  {sid}: MVC={mvc:6.1f}  torque_target={torque_target:6.1f}  "
        f"gastroc_amp={gastroc_amp:6.1f}uV rise={gastroc_rise:+.0%}  "
        f"vastus_amp={vastus_amp:5.1f}uV trend={vastus_trend:+.0%}{tag}"
    )
    return {
        "subject_id": sid,
        "mvc_Nm": round(mvc, 1),
        "submax_target_Nm": round(torque_target, 1),
        "protocol": "isometric_submaximal_7_epochs",
        "n_epochs_designed": N_EPOCHS,
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(
        f"Generating {N_SUBJECTS} synthetic recordings "
        f"({SAMPLE_RATE_HZ:.0f} Hz, {N_EPOCHS} epochs, "
        f"~{DURATION_S:.0f}s each)"
    )
    metadata: dict[str, dict] = {}
    for subject_id in range(1, N_SUBJECTS + 1):
        metadata[f"S{subject_id:03d}.csv"] = _write_subject(subject_id)

    # metadata.json sidecar (ADR 0015 schema). Note: it deliberately
    # does NOT mark the cheater — the demo discovers that from the EMG.
    (DATA_DIR / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8",
    )

    # Copy-paste-ready csv_dir config block. The value_columns labels
    # are readable names; the keys match the synthetic CSV headers.
    # When Chunyu's real export arrives, the keys change to whatever
    # LabChart actually wrote — a one-line edit, no code change.
    sample_config = {
        "csv_dir": {
            "path": str(DATA_DIR).replace("\\", "/"),
            "timestamp_column": "t_s",
            "value_columns": {
                "torque": "Torque (N.m)",
                "gastroc_lat": "Gastrocnemius lateralis EMG (uV)",
                "gastroc_med": "Gastrocnemius medialis EMG (uV)",
                "vastus_lat": "Vastus lateralis EMG (uV)",
                "vastus_med": "Vastus medialis EMG (uV)",
            },
        },
    }
    (HERE / "user_config.sample.json").write_text(
        json.dumps(sample_config, indent=2), encoding="utf-8",
    )

    print()
    print(f"Wrote {N_SUBJECTS} recordings + metadata.json -> {DATA_DIR}")
    print(f"Sample csv_dir config -> {HERE / 'user_config.sample.json'}")
    print(
        f"\nPlanted finding (console-only, not in any data file): "
        f"S{CHEATER_SUBJECT:03d} is the cheater - watch its vastus "
        f"(quad) RMS climb across the 7 epochs while the clean "
        f"subjects' stays flat."
    )


if __name__ == "__main__":
    main()

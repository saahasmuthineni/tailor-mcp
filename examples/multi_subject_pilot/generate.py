"""
Generate synthetic multi-subject CSV data for the multi-subject pilot
quickstart guide.

Three fake participants (P001, P002, P003), three days each, hourly
heart-rate + blood-glucose rows. Plausible diurnal patterns (lower
overnight HR, post-meal glucose excursions at 8am/12pm/6pm) and one
deliberate "anomaly" per participant so the LLM has something to find.

Reproducible: seeded ``random.Random(42)``. Per ADR 0008 the seeded-
PRNG-off-the-analytical-path exception applies — this is fixture data,
not framework or child processing. Re-running this script overwrites
the CSVs deterministically.

Usage:
    python examples/multi_subject_pilot/generate.py
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path


_RNG = random.Random(42)
HERE = Path(__file__).parent
# Canonical fixture home is inside the package so they ship in the wheel
# and `importlib.resources` can find them in any install shape (source,
# pip, uv tool, PyInstaller). See ADR forthcoming or pyproject.toml.
REPO_ROOT = HERE.parent.parent
OUT = REPO_ROOT / "src" / "tailor" / "_fixtures" / "multi_subject_pilot" / "csv"


# ── Per-participant baselines ──

PARTICIPANTS: list[dict] = [
    {
        "id": "P001",
        "resting_hr": 56,
        "fasting_glucose": 92,
        "anomaly_hour": 14,  # day 2, 2pm — glucose spike (missed insulin?)
    },
    {
        "id": "P002",
        "resting_hr": 64,
        "fasting_glucose": 108,
        "anomaly_hour": 38,  # day 2, late night — HR spike (poor sleep?)
    },
    {
        "id": "P003",
        "resting_hr": 72,
        "fasting_glucose": 88,
        "anomaly_hour": 60,  # day 3, noon — combined HR+glucose
    },
]

# 3 days × 24 hours = 72 timepoints per participant
HOURS = 72
START = datetime(2026, 4, 1, 0, 0, 0)


def _diurnal_hr(hour_of_day: int, resting: int) -> int:
    """Plausible HR pattern: low overnight, peak in afternoon."""
    if hour_of_day < 6:
        base = resting - 4  # deep-sleep dip
    elif hour_of_day < 9:
        base = resting + 8  # morning ramp
    elif hour_of_day < 17:
        base = resting + 12  # daytime baseline
    elif hour_of_day < 22:
        base = resting + 6  # evening wind-down
    else:
        base = resting - 2  # bedtime
    jitter = _RNG.randint(-3, 3)
    return base + jitter


def _diurnal_glucose(hour_of_day: int, fasting: int) -> int:
    """Plausible glucose pattern: post-meal excursions at 8/12/18."""
    base = fasting
    # Decay back to fasting between meals
    excursion = 0
    if 8 <= hour_of_day <= 10:
        excursion = 35 - 12 * (hour_of_day - 8)
    elif 12 <= hour_of_day <= 14:
        excursion = 42 - 14 * (hour_of_day - 12)
    elif 18 <= hour_of_day <= 21:
        excursion = 38 - 10 * (hour_of_day - 18)
    jitter = _RNG.randint(-4, 4)
    return max(70, base + excursion + jitter)


def _generate_participant(p: dict) -> list[dict]:
    rows: list[dict] = []
    for h in range(HOURS):
        ts = START + timedelta(hours=h)
        hour_of_day = ts.hour
        hr = _diurnal_hr(hour_of_day, p["resting_hr"])
        glu = _diurnal_glucose(hour_of_day, p["fasting_glucose"])

        # Inject the participant's anomaly
        if h == p["anomaly_hour"]:
            if "P001" in p["id"]:
                glu += 80  # major glucose spike
            elif "P002" in p["id"]:
                hr += 35  # nighttime tachycardia
            elif "P003" in p["id"]:
                hr += 25
                glu += 50

        rows.append({
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S"),
            "Heart rate (bpm)": hr,
            "Blood glucose (mg/dL)": glu,
        })
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fieldnames = ["timestamp", "Heart rate (bpm)", "Blood glucose (mg/dL)"]

    for p in PARTICIPANTS:
        path = OUT / f"{p['id']}.csv"
        rows = _generate_participant(p)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {len(rows)} rows -> {path.relative_to(REPO_ROOT)}")

    # Also emit a portable user_config.example.json with a placeholder
    # path. The recommended path is `tailor pilot`, which writes
    # this file for the user; this artifact remains as a manual fallback.
    cfg_path = HERE / "user_config.example.json"
    cfg = (
        "{\n"
        '  "csv_dir": {\n'
        '    "path": "<REPO_ROOT>/src/tailor/_fixtures/multi_subject_pilot/csv",\n'
        '    "timestamp_column": "timestamp",\n'
        '    "timestamp_format": "%Y-%m-%dT%H:%M:%S",\n'
        '    "value_columns": {\n'
        '      "heart_rate": "Heart rate (bpm)",\n'
        '      "glucose": "Blood glucose (mg/dL)"\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    cfg_path.write_text(cfg, encoding="utf-8")
    print(f"wrote {cfg_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()

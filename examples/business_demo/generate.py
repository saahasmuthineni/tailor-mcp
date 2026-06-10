"""
Generate synthetic retail-operations CSV data for the business demo.

Twelve stores (6 north region, 6 south region; mall and street formats
in both), 90 days of daily rows each: revenue, transaction count,
average basket. The south region trends upward over the quarter, the
north region trends slightly downward, weekends carry an uplift, and
one store (store_N03) has a two-week closure mid-quarter so the LLM
has an anomaly to find.

This demo exists so the first non-health worked example a visitor
meets is business-shaped: the generic ``csv_dir`` child answers
cross-store questions ("which region is doing better?") entirely
server-side — no sales rows ever enter LLM context.

Reproducible: seeded ``random.Random(20260610)``. Per ADR 0008 the
seeded-PRNG-off-the-analytical-path exception applies — this is
fixture data, not framework or child processing. Re-running this
script overwrites the CSVs deterministically.

Usage:
    python examples/business_demo/generate.py
"""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

_RNG = random.Random(20260610)
HERE = Path(__file__).parent
OUT = HERE / "csv"

START = datetime(2026, 1, 5)  # a Monday
DAYS = 90

# Anomaly: store_N03 closed for a water-main break, days 41-54
# inclusive (zero-indexed from START). Skeleton online fulfilment
# keeps ~8% of normal revenue flowing.
CLOSURE_STORE = "store_N03"
CLOSURE_DAYS = range(41, 55)
CLOSURE_REVENUE_FACTOR = 0.08

# Per-store baselines. Mall stores carry higher revenue and larger
# baskets than street stores; the regional trend is the cohort-level
# signal the demo's group-summary question surfaces.
#   region trend: south grows ~+0.35%/day, north declines ~-0.20%/day
STORES: list[dict] = [
    {"id": "store_N01", "region": "north", "format": "mall", "base": 16800.0, "basket": 54.0},
    {"id": "store_N02", "region": "north", "format": "mall", "base": 14900.0, "basket": 51.0},
    {"id": "store_N03", "region": "north", "format": "mall", "base": 15600.0, "basket": 52.5},
    {"id": "store_N04", "region": "north", "format": "street", "base": 8900.0, "basket": 32.0},
    {"id": "store_N05", "region": "north", "format": "street", "base": 7600.0, "basket": 30.0},
    {"id": "store_N06", "region": "north", "format": "street", "base": 8200.0, "basket": 31.5},
    {"id": "store_S01", "region": "south", "format": "mall", "base": 15200.0, "basket": 53.0},
    {"id": "store_S02", "region": "south", "format": "mall", "base": 17400.0, "basket": 55.5},
    {"id": "store_S03", "region": "south", "format": "mall", "base": 14100.0, "basket": 50.0},
    {"id": "store_S04", "region": "south", "format": "street", "base": 9400.0, "basket": 33.0},
    {"id": "store_S05", "region": "south", "format": "street", "base": 7100.0, "basket": 29.5},
    {"id": "store_S06", "region": "south", "format": "street", "base": 8700.0, "basket": 31.0},
]

REGION_DAILY_TREND = {"north": -0.0020, "south": 0.0035}
WEEKEND_UPLIFT = 1.35


def _daily_revenue(store: dict, day: int, date: datetime) -> float:
    trend = (1.0 + REGION_DAILY_TREND[store["region"]]) ** day
    weekend = WEEKEND_UPLIFT if date.weekday() >= 5 else 1.0
    noise = _RNG.uniform(0.94, 1.06)
    revenue = store["base"] * trend * weekend * noise
    if store["id"] == CLOSURE_STORE and day in CLOSURE_DAYS:
        revenue *= CLOSURE_REVENUE_FACTOR
    return round(revenue, 2)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    for store in STORES:
        path = OUT / f"{store['id']}.csv"
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["timestamp", "daily_revenue", "transactions", "avg_basket"]
            )
            for day in range(DAYS):
                date = START + timedelta(days=day)
                revenue = _daily_revenue(store, day, date)
                basket = round(store["basket"] * _RNG.uniform(0.96, 1.04), 2)
                transactions = max(1, round(revenue / basket))
                writer.writerow(
                    [
                        date.strftime("%Y-%m-%dT%H:%M:%S"),
                        f"{revenue:.2f}",
                        transactions,
                        f"{basket:.2f}",
                    ]
                )
        print(f"wrote {path}")

    metadata = {
        f"{store['id']}.csv": {
            "region": store["region"],
            "format": store["format"],
        }
        for store in STORES
    }
    metadata_path = OUT / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"wrote {metadata_path}")


if __name__ == "__main__":
    main()

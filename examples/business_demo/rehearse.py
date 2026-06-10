"""
Non-interactive end-to-end check for the business demo (no Claude in
the loop).

Instantiates the generic ``csv_dir`` child directly against
``examples/business_demo/csv/`` via a throwaway config dir, calls each
tool the walkthrough exercises, and prints PASS / FAIL per assertion.
Exit code 0 = demo is rehearsal-ready; non-zero = at least one number
drifted from CUE_CARD.md's expected ranges, identifying the failure
before a live demo rather than during.

Your real ``~/.tailor/`` directory stays untouched — the script
scaffolds its own temp config dir and tears it down on exit.

Usage:
    python examples/business_demo/rehearse.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from tailor.children.csv_dir import CSVDirectoryChild  # noqa: E402

CSV_DIR = HERE / "csv"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


async def main() -> int:
    if not CSV_DIR.is_dir():
        print(
            "fixtures missing — run "
            "`python examples/business_demo/generate.py` first"
        )
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp) / "config"
        data_dir = Path(tmp) / "data"
        config_dir.mkdir()
        data_dir.mkdir()
        (config_dir / "user_config.json").write_text(
            json.dumps(
                {
                    "csv_dir": {
                        "path": str(CSV_DIR),
                        "timestamp_column": "timestamp",
                        "timestamp_format": "%Y-%m-%dT%H:%M:%S",
                        "value_columns": {
                            "daily_revenue": "Daily revenue (USD)",
                            "transactions": "Transactions (count)",
                            "avg_basket": "Average basket (USD)",
                        },
                    }
                }
            )
        )

        child = CSVDirectoryChild(config_dir, data_dir)

        # ── Step: list files ──
        listing = await child.execute("csv_list_files", {"limit": 20})
        files = listing.get("files", [])
        check("csv_list_files returns 12 stores", len(files) == 12,
              f"got {len(files)}")

        # ── Step: revenue by region (the headline question) ──
        by_region = await child.execute(
            "csv_group_summary",
            {"value_column": "daily_revenue", "group_by": "region",
             "metric": "mean"},
        )
        groups = by_region.get("groups", {})
        north = groups.get("north", {})
        south = groups.get("south", {})
        check("group_summary has north + south groups",
              bool(north) and bool(south))
        check("n=6 per region",
              north.get("n") == 6 and south.get("n") == 6,
              f"north n={north.get('n')}, south n={south.get('n')}")
        if north.get("mean") and south.get("mean"):
            check(
                "south mean daily revenue > north (regional trend visible)",
                south["mean"] > north["mean"],
                f"south={south['mean']:.0f}, north={north['mean']:.0f}",
            )
            print(
                f"      cue-card numbers: north mean ≈ {north['mean']:.0f}, "
                f"south mean ≈ {south['mean']:.0f}"
            )

        # ── Step: peak revenue by format ──
        by_format = await child.execute(
            "csv_group_summary",
            {"value_column": "daily_revenue", "group_by": "format",
             "metric": "max"},
        )
        fgroups = by_format.get("groups", {})
        mall = fgroups.get("mall", {})
        street = fgroups.get("street", {})
        check("group_summary has mall + street groups",
              bool(mall) and bool(street))
        if mall.get("mean") and street.get("mean"):
            check(
                "mall peak revenue > street peak revenue",
                mall["mean"] > street["mean"],
                f"mall={mall['mean']:.0f}, street={street['mean']:.0f}",
            )
            print(
                f"      cue-card numbers: mall mean-of-peaks ≈ "
                f"{mall['mean']:.0f}, street ≈ {street['mean']:.0f}"
            )

        # ── Step: the anomaly store ──
        report = await child.execute(
            "csv_summary_report", {"file_id": "store_N03.csv"}
        )
        cols = report.get("column_summaries", {})
        rev = cols.get("daily_revenue", {})
        check("store_N03 summary_report has daily_revenue stats",
              bool(rev))
        if rev.get("min") is not None and rev.get("mean") is not None:
            # The two-week closure drags min to ~8% of normal trading,
            # far below anything a weekday/weekend split explains.
            check(
                "closure visible: min daily revenue < 25% of mean",
                rev["min"] < 0.25 * rev["mean"],
                f"min={rev['min']:.0f}, mean={rev['mean']:.0f}",
            )
            print(
                f"      cue-card numbers: store_N03 mean ≈ "
                f"{rev['mean']:.0f}, min ≈ {rev['min']:.0f}"
            )

        # ── Step: comparison store (healthy sibling) ──
        sibling = await child.execute(
            "csv_summary_report", {"file_id": "store_N01.csv"}
        )
        srev = sibling.get("column_summaries", {}).get("daily_revenue", {})
        if srev.get("min") is not None and srev.get("mean") is not None:
            check(
                "healthy store min stays above 50% of mean",
                srev["min"] > 0.5 * srev["mean"],
                f"min={srev['min']:.0f}, mean={srev['mean']:.0f}",
            )

    print()
    if FAILURES:
        print(f"{len(FAILURES)} assertion(s) failed: {FAILURES}")
        return 1
    print("business demo rehearsal: all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""
Demo runner — researcher first-look against the bundled HIP Lab
realistic cohort fixtures.

Per ADR 0027, ``biosensor-mcp demo`` is a researcher first-look,
not operator self-verification: when a PI or RSE runs it cold,
they should see the cohort-comparison thesis the framework is
built around — not the Strava-shaped worked example whose framing
explicitly warns against treating it as canonical.

Implementation:
    - Copy bundled ``_fixtures/hip_lab_demo_realistic/force/`` into
      a tempdir (16 synthetic subjects + ``metadata.json`` sidecar).
    - Write a tempdir-scoped ``user_config.json`` with a ``csv_dir``
      block pointing at the staged force fixtures.
    - Instantiate ``CSVDirectoryChild`` and exercise the Tier-1
      cohort tools (``csv_cohort_summary`` and ``csv_force_decline``)
      via ``child.execute()``.
    - Print result envelopes with framing prose that names the
      thesis explicitly.

The synthetic-Strava ``sample_data.py`` module is preserved per
ADR 0008 § Alternatives (PRNG-removal explicitly rejected) — it
remains importable for the test at
``tests/framework/test_router.py:1054`` and the worked-example
notebook, but is no longer the demo's data source.

Usage:
    biosensor-mcp demo
    python -m biosensor_mcp demo
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from importlib.resources import as_file, files
from pathlib import Path

# Subject CSV used for the per-file force-decline diagnostic. Bundled
# in the HIP Lab realistic fixture set; pinned so re-runs of `demo`
# produce bit-identical output (ADR 0008 deterministic-by-construction
# applies to the processing layer; pinning the input file extends the
# reproducibility property to the demo surface).
_REPRESENTATIVE_FILE = "S001_force.csv"


def _stage_force_fixtures(dest: Path) -> int:
    """Copy bundled HIP Lab ``force/`` subtree into ``dest``.

    Returns the count of files copied (CSVs + ``metadata.json`` sidecar).
    Mirrors ``tour.py``'s ``_copy_resource_tree`` shape — file-by-file
    iteration so Python 3.10/3.11 work (``as_file`` on directories
    only landed in 3.12).
    """
    pkg_root = files("biosensor_mcp._fixtures.hip_lab_demo_realistic.force")
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for child in pkg_root.iterdir():
        if child.is_file():
            with as_file(child) as src_path:
                shutil.copy2(src_path, dest / child.name)
            n += 1
    return n


def _write_demo_user_config(config_dir: Path, force_dir: Path) -> None:
    """Write a minimal ``user_config.json`` so ``CSVDirectoryChild``
    registers against the staged force fixtures.

    Uses the ``csv_dir`` block shape (different from the
    ``force_csv`` / ``emg_csv`` shape that ``tour`` writes) — the
    demo only exercises the generic CSV cohort tools, so the
    simpler block is sufficient.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "user_config.json").write_text(
        json.dumps(
            {
                "csv_dir": {
                    "path": str(force_dir),
                    "timestamp_column": "t_s",
                    "value_columns": {"force_N": "Force (N)"},
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _print_call(tool_name: str, params: dict, result: dict) -> None:
    """Print a single demo call's envelope with a separator banner."""
    print(f"--- {tool_name}({json.dumps(params)}) ---")
    print(json.dumps(result, indent=2, default=str))
    print()


def run_demo() -> None:
    """Researcher first-look — exercise CSV cohort tools against
    bundled HIP Lab fixtures."""
    print("Biosensor MCP — Demo")
    print("=" * 64)
    print(
        "HIP Lab realistic cohort fixture: 16 synthetic subjects on an"
    )
    print(
        "isometric task to volitional failure, with a metadata.json"
    )
    print(
        "sidecar carrying group / sex / baseline_mvc per subject. The"
    )
    print(
        "calls below run server-side via CSVDirectoryChild.execute();"
    )
    print(
        "raw force traces never enter the LLM context."
    )
    print()

    with tempfile.TemporaryDirectory(prefix="biosensor-demo-") as tmpdir:
        tmp_root = Path(tmpdir)
        config_dir = tmp_root / "config"
        data_dir = tmp_root / "data"
        force_dir = tmp_root / "force"
        data_dir.mkdir(parents=True, exist_ok=True)

        n_files = _stage_force_fixtures(force_dir)
        _write_demo_user_config(config_dir, force_dir)
        print(
            f"Loaded {n_files} files from "
            f"biosensor_mcp._fixtures.hip_lab_demo_realistic.force "
            f"into a tempdir."
        )
        print()

        from biosensor_mcp.children.csv_dir import CSVDirectoryChild

        child = CSVDirectoryChild(config_dir=config_dir, data_dir=data_dir)
        try:
            calls: list[tuple[str, dict]] = [
                # Peak force grouped by sex — the load-bearing cohort
                # comparison the HIP Lab realistic fixture is designed
                # to demonstrate (cf. Hunter & Senefeld 2024 sex-
                # differences-in-performance thesis cited in
                # examples/hip_lab_demo/realistic/README.md).
                (
                    "csv_cohort_summary",
                    {
                        "column": "force_N",
                        "group_by": "sex",
                        "metric": "max",
                    },
                ),
                # Same surface, different grouping field — shows the
                # metadata-sidecar pattern (ADR 0015) generalising
                # across whatever fields the analyst has tagged.
                (
                    "csv_cohort_summary",
                    {
                        "column": "force_N",
                        "group_by": "group",
                        "metric": "max",
                    },
                ),
                # Per-file fatigue diagnostic on a pinned subject —
                # demonstrates the v6.5.0 csv_force_decline tool.
                (
                    "csv_force_decline",
                    {
                        "file_id": _REPRESENTATIVE_FILE,
                        "column": "force_N",
                    },
                ),
            ]
            for tool_name, params in calls:
                result = asyncio.run(child.execute(tool_name, params))
                _print_call(tool_name, params, result)
        finally:
            child.close()

    print("=" * 64)
    print("Demo complete.")
    print()
    print(
        "The numbers above were computed server-side from the bundled"
    )
    print(
        "CSVs and emitted as Tier-1 result envelopes (no raw force"
    )
    print(
        "traces in the printed output)."
    )
    print()
    print(
        "Reproducibility check: re-run `biosensor-mcp demo` and"
    )
    print(
        "compare. Output should be bit-identical (ADR 0008:"
    )
    print(
        "deterministic-by-construction processing). If it isn't, the"
    )
    print(
        "install or the bundled fixtures have drifted."
    )
    print()
    print(
        "What this demo does NOT exercise: the router's audit-log"
    )
    print(
        "and _meta provenance pipeline (ADR 0001), the consent /"
    )
    print(
        "cost gates (ADR 0004 / 0005), and the PHI-scrubber seam"
    )
    print(
        "(ADR 0003). Those wrap every tool call in a Claude Desktop"
    )
    print(
        "deployment but live above the child layer this demo drives"
    )
    print(
        "directly. Run `biosensor-mcp tour` to scaffold the same"
    )
    print(
        "fixtures into a durable directory + register with Claude"
    )
    print(
        "Desktop, then issue the same tool inputs through the full"
    )
    print(
        "router-mediated path."
    )

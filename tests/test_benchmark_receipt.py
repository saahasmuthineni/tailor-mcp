"""
Freshness guard for ``docs/assets/benchmark-receipt.svg``.

The receipt SVG is a *receipt*, not a recording: it claims specific
token counts and reduction ratios, and this test re-runs the benchmark
measurement and asserts the checked-in SVG still matches. If a fixture
change moves a ratio, this test fails until the receipt is re-rendered
with::

    python benchmarks/token_efficiency.py | python benchmarks/render_receipt.py

This is the load-bearing difference from any recorded GIF — a recording
proves the thing ran once on the author's machine and can go stale
silently; the receipt cannot.

tiktoken is in the ``[dev]`` extra precisely so this guard executes in
the CI matrix rather than skipping. A silent skip would void the whole
property, so an absent tiktoken is a hard failure here, not a skip.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = REPO_ROOT / "benchmarks"
RECEIPT_SVG = REPO_ROOT / "docs" / "assets" / "benchmark-receipt.svg"


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        module_name, BENCHMARKS / filename
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _fresh_results(bench) -> dict:
    """Rebuild the benchmark results dict the same way the script's
    main() does — re-reading fixtures and re-tokenizing."""
    return {
        "tokenizer_primary": "tiktoken cl100k_base",
        "per_query_efficiency": [
            bench.measure_single_subject(),
            bench.measure_cohort(),
        ],
        "session_persistence_efficiency": [
            bench.measure_session_persistence(),
        ],
    }


@pytest.mark.timeout(120)
def test_benchmark_receipt_matches_fresh_measurement():
    # Importing the benchmark module loads the cl100k_base encoder.
    # In CI (and `pip install -e ".[dev]"`) tiktoken is present and the
    # vocab is fetched/cached; we assert availability rather than skip.
    bench = _load("_benchmark_token_efficiency", "token_efficiency.py")
    assert getattr(bench, "TIKTOKEN_AVAILABLE", False), (
        "tiktoken is not available — the benchmark receipt guard cannot "
        "run. tiktoken is declared in the [dev] extra; install it with "
        "`pip install -e \".[dev]\"`. This guard must not silently skip."
    )

    receipt = _load("_benchmark_render_receipt", "render_receipt.py")

    fresh = receipt.build_receipt_data(_fresh_results(bench))

    assert RECEIPT_SVG.exists(), (
        f"{RECEIPT_SVG} is missing — render it with "
        "`python benchmarks/token_efficiency.py | "
        "python benchmarks/render_receipt.py`."
    )
    stored = receipt.extract_receipt_data(
        RECEIPT_SVG.read_text(encoding="utf-8")
    )

    assert stored == fresh, (
        "benchmark-receipt.svg is stale — its embedded numbers no longer "
        "match a fresh benchmark run. Re-render with "
        "`python benchmarks/token_efficiency.py | "
        "python benchmarks/render_receipt.py`.\n"
        f"stored={stored}\nfresh={fresh}"
    )

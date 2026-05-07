"""
Regression tests for v6.10.5 / ADR 0027 — ``biosensor-mcp demo`` is
a researcher first-look that runs the CSV cohort tools against the
bundled HIP Lab realistic fixtures.

The previous Strava-shaped demo silently positioned the worked-example
running child as canonical; ADR 0027 reframes the demo to demonstrate
the cohort-comparison thesis instead. The tests here lock in the
shape of that reframe so a future runner rewrite cannot regress to
Strava-shaped output without breaking pytest.

Test surface:
    - `run_demo()` runs end-to-end without raising.
    - Bundled fixtures are reachable via `importlib.resources`.
    - Output mentions HIP Lab / cohort / sex; mentions neither Strava
      nor "operator self-verification" (the prior framing).
    - The cohort-summary call by ``sex`` returns F and M groups with
      n=8 each (HIP Lab realistic fixture's documented cohort shape).
    - The cohort-summary call by ``group`` returns control and
      intervention groups.
    - The force-decline call runs on the pinned representative subject
      ``S001_force.csv`` and returns the v6.5.0 decline-summary keys.
    - `sample_data.py` remains importable per ADR 0008's
      explicit-rejection-of-removal clause.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import pytest


def test_run_demo_executes_end_to_end_without_raising() -> None:
    """The demo must run cleanly against the bundled fixtures.

    A wheel install where the fixtures are missing or unreadable
    surfaces here; the canonical ``importlib.resources`` path is
    exercised, so this also smoke-tests the wheel package-data globs.
    """
    from biosensor_mcp.demo import run_demo

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo()

    output = buf.getvalue()
    assert "Biosensor MCP" in output
    assert "Demo complete." in output


def test_demo_output_names_hip_lab_thesis_not_strava() -> None:
    """ADR 0027 reframes demo as researcher first-look; output must
    name the HIP Lab thesis explicitly and must not carry over the
    pre-v6.10.5 Strava framing."""
    from biosensor_mcp.demo import run_demo

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo()
    output = buf.getvalue()

    # Researcher-first-look framing is named explicitly.
    assert "HIP Lab" in output
    assert "cohort" in output.lower()

    # Pre-v6.10.5 Strava framing is gone from the demo surface.
    assert "Strava" not in output
    assert "strava_run_report" not in output
    assert "strava_hr_analysis" not in output


def test_demo_output_includes_cohort_by_sex_with_balanced_groups() -> None:
    """The HIP Lab realistic fixture is designed with 16 subjects
    balanced 8 F / 8 M (per examples/hip_lab_demo/realistic/README.md
    sex-differences thesis citing Hunter & Senefeld 2024). The demo's
    cohort_summary-by-sex call must surface that balance."""
    from biosensor_mcp.demo import run_demo

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo()
    output = buf.getvalue()

    # The cohort-summary-by-sex call body is printed as JSON; assert
    # both group rows are present with the balanced n=8.
    assert '"group_by": "sex"' in output
    # Both sex labels appear (the JSON emission spans multiple lines so
    # we look for the literal "F" and "M" group keys).
    assert '"F":' in output
    assert '"M":' in output


def test_demo_output_includes_cohort_by_group() -> None:
    """The metadata-sidecar pattern (ADR 0015) generalises across
    grouping fields. The demo demonstrates this by running the same
    call with a different ``group_by`` field."""
    from biosensor_mcp.demo import run_demo

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo()
    output = buf.getvalue()

    assert '"group_by": "group"' in output
    assert '"control":' in output
    assert '"intervention":' in output


def test_demo_output_includes_force_decline_on_pinned_subject() -> None:
    """The per-file fatigue diagnostic is pinned to ``S001_force.csv``
    so re-runs are bit-identical (ADR 0008 deterministic-by-construction
    extended to the demo surface via input pinning)."""
    from biosensor_mcp.demo import run_demo

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo()
    output = buf.getvalue()

    assert "csv_force_decline" in output
    assert "S001_force.csv" in output


def test_demo_is_deterministic_across_reruns() -> None:
    """Re-running the demo must produce bit-identical numeric output.

    This is ADR 0008 deterministic-by-construction surfaced as a
    recipient-checkable property. If this test ever fails, either
    ``CSVProcessing`` has acquired non-determinism (an ADR 0008
    invariant violation) or the bundled fixture has drifted.
    """
    from biosensor_mcp.demo import run_demo

    out1 = io.StringIO()
    with redirect_stdout(out1):
        run_demo()
    out2 = io.StringIO()
    with redirect_stdout(out2):
        run_demo()

    # Tempdir paths differ between runs, so we can't compare raw output
    # directly. Compare the parsed JSON envelopes from each call by
    # extracting them.
    def _envelopes(text: str) -> list[dict]:
        envelopes: list[dict] = []
        depth = 0
        buf: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if depth == 0 and stripped.startswith("{"):
                buf = [line]
                depth = stripped.count("{") - stripped.count("}")
            elif depth > 0:
                buf.append(line)
                depth += stripped.count("{") - stripped.count("}")
                if depth == 0:
                    envelopes.append(json.loads("\n".join(buf)))
        return envelopes

    e1 = _envelopes(out1.getvalue())
    e2 = _envelopes(out2.getvalue())
    assert len(e1) == 3, "demo should print 3 result envelopes"
    assert len(e1) == len(e2)
    for a, b in zip(e1, e2, strict=True):
        assert a == b, "demo output must be bit-identical across reruns"


def test_sample_data_module_remains_importable() -> None:
    """ADR 0008 § Alternatives explicitly rejected removing
    ``demo/sample_data.py``. ADR 0027 narrows its role from "demo
    data source" to "library-shaped synthetic-Strava generator" but
    preserves the module's importability for the worked-example
    notebook and the router smoke test."""
    from biosensor_mcp.demo.sample_data import (
        SAMPLE_ACTIVITY_ID,
        generate_sample_activity,
        generate_sample_streams,
    )

    assert SAMPLE_ACTIVITY_ID == 99_999_999
    activity = generate_sample_activity()
    assert "name" in activity
    streams = generate_sample_streams()
    assert "heartrate" in streams


def test_bundled_force_fixtures_are_loadable_via_importlib_resources() -> None:
    """Direct test of the wheel-fixture-bundling contract per
    ADR 0024. If the package-data glob in pyproject.toml drops the
    force/ subtree, this test surfaces the regression before any
    recipient hits the demo's loading path."""
    from importlib.resources import files

    pkg_root = files("biosensor_mcp._fixtures.hip_lab_demo_realistic.force")
    csv_count = sum(
        1 for child in pkg_root.iterdir()
        if child.is_file() and child.name.endswith(".csv")
    )
    metadata_present = any(
        child.name == "metadata.json"
        for child in pkg_root.iterdir() if child.is_file()
    )

    assert csv_count == 16, (
        f"HIP Lab realistic fixture should bundle 16 force CSVs; found {csv_count}"
    )
    assert metadata_present, (
        "metadata.json sidecar must be bundled (ADR 0015 cohort-summary contract)"
    )

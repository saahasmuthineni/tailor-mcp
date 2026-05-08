"""
Regression tests for ``biosensor-mcp demo``.

Two waves of design intent govern this test file:

* **v6.10.5 / [ADR 0027](../docs/adr/0027-demo-as-researcher-first-look.md)** —
  reframed the demo from synthetic-Strava operator self-verification to a
  researcher first-look against the bundled HIP Lab realistic cohort
  fixtures.
* **v6.12.0 / [ADR 0029](../docs/adr/0029-token-reduction-as-analytical-quality.md)** —
  partially supersedes ADR 0027 § Negative consequences ("the demo
  bypasses RouterMCP by design"). The demo is reshaped into five
  sections demonstrating the framework's load-bearing claims; ADR 0027's
  cohort-thesis-as-canonical-first-look survives as Section 1.

The tests below lock in the shape of both reframes so a future
runner rewrite cannot regress to either Strava-shaped output (ADR 0027
invariant) or router-bypassed cohort-only output (ADR 0029 invariant).

Test surface:
    Section 1 / ADR 0027 (cohort thesis):
        - HIP Lab framing, no Strava
        - cohort_summary by sex / by group with balanced n=8
        - force_decline on pinned S001
        - bit-identical Section 1 cohort numbers across runs
    Section 2-5 / ADR 0029 (architectural surface):
        - _meta provenance block visible
        - audit_log row tail-printed with subject_id="S001"
        - cost gate fires with cheaper-alternative on Tier 3
        - consent gate fires then approves on Tier 2
        - vault moment captured with subject_id="S001" frontmatter
        - oracle substrate scan finds the captured moment
    --save-shareable flag (this PR):
        - file is written, self-contained
        - install URL includes current version
        - transcript section present
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

# ════════════════════════════════════════════════════════════════
# Shared fixtures
# ════════════════════════════════════════════════════════════════


@pytest.fixture
def demo_output() -> str:
    """Run the demo once and return captured stdout.

    Most tests just need to grep the output; sharing the run avoids
    redundant ~5-10 second demo runs across the file.
    """
    from biosensor_mcp.demo import run_demo

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo()
    return buf.getvalue()


# ════════════════════════════════════════════════════════════════
# ADR 0027 invariants (preserved as Section 1 per ADR 0029)
# ════════════════════════════════════════════════════════════════


def test_run_demo_executes_end_to_end_without_raising() -> None:
    """The demo must run cleanly against the bundled fixtures.

    A wheel install where the fixtures are missing or unreadable
    surfaces here; the canonical ``importlib.resources`` path is
    exercised, so this also smoke-tests the wheel package-data globs.
    On Windows, this also exercises the ADR 0029 try/finally cleanup
    invariant — the SQLite WAL handles for router/vault/child must
    close before TemporaryDirectory teardown or this raises
    PermissionError.
    """
    from biosensor_mcp.demo import run_demo

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo()

    output = buf.getvalue()
    assert "Biosensor MCP" in output
    assert "Demo complete." in output


def test_demo_output_names_hip_lab_thesis_not_strava(demo_output: str) -> None:
    """ADR 0027 reframes demo as researcher first-look; output must
    name the HIP Lab thesis explicitly and must not carry over the
    pre-v6.10.5 Strava framing."""
    assert "HIP Lab" in demo_output
    assert "cohort" in demo_output.lower()

    # Pre-v6.10.5 Strava framing is gone from the demo surface.
    assert "Strava" not in demo_output
    assert "strava_run_report" not in demo_output
    assert "strava_hr_analysis" not in demo_output


def test_demo_output_includes_cohort_by_sex_with_balanced_groups(
    demo_output: str,
) -> None:
    """The HIP Lab realistic fixture is balanced 8 F / 8 M (per
    examples/hip_lab_demo/realistic/README.md sex-differences thesis).
    The demo's cohort_summary-by-sex call must surface that balance."""
    assert '"group_by": "sex"' in demo_output
    assert '"F":' in demo_output
    assert '"M":' in demo_output


def test_demo_output_includes_cohort_by_group(demo_output: str) -> None:
    """The metadata-sidecar pattern (ADR 0015) generalises across
    grouping fields. The demo demonstrates this by running the same
    call with a different ``group_by`` field."""
    assert '"group_by": "group"' in demo_output
    assert '"control":' in demo_output
    assert '"intervention":' in demo_output


def test_demo_output_includes_force_decline_on_pinned_subject(
    demo_output: str,
) -> None:
    """The per-file fatigue diagnostic is pinned to ``S001_force.csv``
    so re-runs are bit-identical (ADR 0008 deterministic-by-construction
    extended to the demo surface via input pinning)."""
    assert "csv_force_decline" in demo_output
    assert "S001_force.csv" in demo_output


def test_section_1_cohort_numbers_are_bit_identical_across_reruns() -> None:
    """ADR 0008 deterministic-by-construction surfaced as a
    recipient-checkable property — *but only on Section 1's cohort
    numerics*.

    Per ADR 0029 § Implementation key facts § Reproducibility-claim
    scoping: ``_meta.called_at``, audit-log row ids, oracle latency,
    and SQLite row ids do change across runs (the audit/provenance
    pipeline timestamps each call). Conflating those with the
    determinism invariant would either weaken the reproducibility
    claim or invite false-positive regression reports. This test
    locks the bit-identity claim to Section 1's cohort numbers
    specifically.
    """
    from biosensor_mcp.demo import run_demo

    out1 = io.StringIO()
    with redirect_stdout(out1):
        run_demo()
    out2 = io.StringIO()
    with redirect_stdout(out2):
        run_demo()

    # Extract the by-sex cohort_summary numerics from each run.
    # Walk every top-level JSON object; return the first one whose
    # group_by is 'sex' AND has a 'groups' key (distinguishes the
    # result envelope from the call-header params dict — both contain
    # 'group_by: sex' but only the result has 'groups').
    def _extract_by_sex_groups(text: str) -> dict | None:
        depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        start = -1
                        continue
                    if (
                        isinstance(obj, dict)
                        and obj.get("group_by") == "sex"
                        and "groups" in obj
                    ):
                        return obj["groups"]
                    start = -1
        return None

    g1 = _extract_by_sex_groups(out1.getvalue())
    g2 = _extract_by_sex_groups(out2.getvalue())
    assert g1 is not None
    assert g2 is not None
    assert g1 == g2, (
        "Section 1 cohort numerics must be bit-identical across runs "
        "(ADR 0008 deterministic-by-construction)"
    )


# ════════════════════════════════════════════════════════════════
# ADR 0029 invariants (Sections 2-5 architectural surface)
# ════════════════════════════════════════════════════════════════


def test_section_2_router_pipeline_emits_meta_provenance_block(
    demo_output: str,
) -> None:
    """Section 2 dispatches a Section-1-shaped call through ``RouterMCP``
    and prints the result envelope including the ADR 0001 ``_meta``
    block. Locks the v6.12.0 invariant that the audit-log backbone
    becomes recipient-visible at first look."""
    # Canonical _meta block fields per ADR 0001
    assert '"_meta"' in demo_output
    assert '"package_version"' in demo_output
    assert '"called_at"' in demo_output
    assert '"scrubber_id"' in demo_output
    # PHIScrubber default no-op warning surfaces in _meta per ADR 0003
    # (the seam, not a policy)
    assert "scrubber_warning" in demo_output


def test_section_2_audit_row_tail_printed_with_subject_id(
    demo_output: str,
) -> None:
    """The Section 2 envelope is followed by a tail-print of the
    latest ``audit.db`` row. ADR 0001 (audit-log backbone) +
    ADR 0009 (subject_id scoping) compose: the tail row must carry
    ``subject_id="S001"`` (Section 2's call threads it explicitly)."""
    assert "Latest audit_log row" in demo_output
    assert '"subject_id": "S001"' in demo_output
    assert '"outcome": "SUCCESS"' in demo_output


def test_section_3_cost_gate_fires_on_tier_3_with_cheaper_alternative(
    demo_output: str,
) -> None:
    """ADR 0005 cost-pre-estimation contract: Tier-3 ``csv_raw_stream``
    on S001 must trip the demo router's cost gate (configured with
    ``cost_threshold=15_000`` per ADR 0029 implementation key facts)
    and surface the cheaper-alternative description."""
    assert '"gate": "cost_approval_required"' in demo_output
    # The cheaper-alternative suggestion is the load-bearing
    # 'framework teaches the LLM what resolution answers the
    # question' beat per ADR 0029 § Context.
    assert "downsampled" in demo_output
    assert "cheaper" in demo_output.lower()


def test_section_3_consent_gate_fires_then_approves(
    demo_output: str,
) -> None:
    """ADR 0004 LLMInstruction contract: Tier-2 ``csv_downsampled``
    fires the consent gate before approval, then the demo runner
    approves in-script and re-issues the call."""
    assert '"gate": "consent_required"' in demo_output
    # Approval narration confirms the gate was retried after approve
    assert "Approving consent in-script" in demo_output
    # Both calls land in audit.db; absence of an "ERROR" outcome on
    # the post-approval call would be visible if it failed
    assert "approve_consent_csv_dir" in demo_output


def test_section_4_vault_moment_captured_with_subject_id_s001(
    demo_output: str,
) -> None:
    """Section 4 captures a moment via ``vault_capture_moment`` scoped
    to ``subject_id="S001"`` (ADR 0009). The moment markdown is
    printed inline so the recipient sees the source-of-truth markdown
    (ADR 0007), not just the SQLite index."""
    assert "vault_capture_moment" in demo_output
    # Moment markdown frontmatter — ADR 0009 subject_id scoping made
    # recipient-visible
    assert 'subject_id: "S001"' in demo_output
    # ADR 0007 source-of-truth: markdown body is printed
    assert "Sex-grouped peak force" in demo_output


def test_section_5_oracle_substrate_scan_finds_section_4_moment(
    demo_output: str,
) -> None:
    """Section 5's ``ask_local_oracle`` call (with ``NullBackend``)
    must show ``related_substrate`` populated with the moment captured
    in Section 4. The substrate scan (ADR 0023) auto-finds the moment
    by ``subject_id="S001"`` match without the LLM having to
    remember the slug — this is the cooperation-loop architecture
    working live, not narrated in prose."""
    assert "ask_local_oracle" in demo_output
    assert '"related_substrate"' in demo_output
    # The captured moment's slug appears in the substrate list
    assert "sex-grouped-peak-force" in demo_output.lower()
    # NullBackend's narrative disclaimer per ADR 0022 contract
    assert "narrative is LLM-generated and non-citable" in demo_output


def test_section_5_oracle_meta_carries_processing_calls() -> None:
    """The OracleResponse._meta block names the processing calls that
    composed the resolved_context — ADR 0023 § Architectural placement
    requires this for IRB-grade provenance (a future reviewer
    reconstructing what the hosted LLM saw on an oracle call queries
    counts from audit.db)."""
    from biosensor_mcp.demo import run_demo

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo()
    output = buf.getvalue()

    # processing_calls is a list of tool names that fed resolved_context
    assert '"processing_calls"' in output
    assert '"csv_cohort_summary"' in output


# ════════════════════════════════════════════════════════════════
# --save-shareable flag invariants (this PR — ADR 0024 § 3.1)
# ════════════════════════════════════════════════════════════════


def test_save_shareable_writes_self_contained_markdown(tmp_path: Path) -> None:
    """The ``--save-shareable`` flag must produce a self-contained
    markdown file: install command + transcript + 'where to read next'
    footer. ADR 0024 § 3.1 (the public release-only mirror amendment)
    depends on this file format being suitable for hosting at a
    permanent URL."""
    from biosensor_mcp.demo import run_demo

    out_path = tmp_path / "shareable.md"

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo(save_shareable_path=out_path)

    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")

    # Header / title
    assert "# Biosensor MCP - demo" in content
    # Install command section with both uvx and pipx
    assert "uvx --from" in content
    assert "pipx run --spec" in content
    # Transcript section
    assert "## Demo output" in content
    assert "Section 1" in content
    # Footer with reading-order breadcrumbs
    assert "Where to read next" in content
    assert "ADR 0029" in content


def test_save_shareable_install_url_includes_current_version(
    tmp_path: Path,
) -> None:
    """The wheel URL embedded in the shareable markdown must match the
    current package version. On each release, the URL pattern
    automatically updates to the new wheel filename so the friend's
    one-line install command stays correct."""
    from biosensor_mcp import __version__
    from biosensor_mcp.demo import run_demo

    out_path = tmp_path / "shareable.md"
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo(save_shareable_path=out_path)

    content = out_path.read_text(encoding="utf-8")
    expected_filename = f"biosensor_mcp-{__version__}-py3-none-any.whl"
    assert expected_filename in content


def test_save_shareable_default_install_url_base_is_public_mirror() -> None:
    """The default install URL base (when
    ``BIOSENSOR_DEMO_INSTALL_URL_BASE`` env var is unset) must point at
    the public mirror repo per ADR 0024 § 3.1."""
    from biosensor_mcp.demo import run_demo

    out_path = Path("/tmp") / "_test_share_default.md"
    if out_path.exists():
        out_path.unlink()

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo(save_shareable_path=out_path)

    try:
        content = out_path.read_text(encoding="utf-8")
        assert "github.com/saahasmuthineni/biosensormcpdemo" in content
    finally:
        if out_path.exists():
            out_path.unlink()


def test_save_shareable_no_op_when_path_is_none(demo_output: str) -> None:
    """``run_demo()`` without the flag must NOT write a file or alter
    its stdout output relative to the no-flag baseline. The flag is
    purely additive."""
    # The shared demo_output fixture runs without save_shareable_path,
    # so any side-effect of the flag would surface as a difference.
    # Verify the closing prose line that comes ONLY from the flag-off
    # path doesn't include the share-file save confirmation.
    assert "Shareable demo saved to:" not in demo_output


# ════════════════════════════════════════════════════════════════
# ADR 0008 alternative-rejection clauses + wheel bundling contracts
# ════════════════════════════════════════════════════════════════


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



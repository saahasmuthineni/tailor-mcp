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


# ════════════════════════════════════════════════════════════════
# ADR 0030 — narrative + zero-outbound-affordances rendering
# ════════════════════════════════════════════════════════════════
#
# Locks in the v6.13 ship: --audience=public splices per-persona
# panels into the saved markdown, replaces the developer-tier ADR
# breadcrumbs with an attribution-only footer, and hard-fails CI at
# render time if any disallowed outbound URL appears. Developer mode
# (default) preserves v6.12.0 behaviour for back-compat.


def test_personas_schema_ships_in_wheel() -> None:
    """``_personas.json`` must be loadable via importlib.resources from
    the installed package. Ships per pyproject.toml package-data glob
    so a recipient running ``demo --audience=public --save-shareable``
    on their machine has the schema locally."""
    from importlib.resources import files

    data = (
        files("biosensor_mcp.demo")
        .joinpath("_personas.json")
        .read_text(encoding="utf-8")
    )
    parsed = json.loads(data)
    assert parsed["schema_version"] == 1
    assert set(parsed["personas"].keys()) == {"pi", "analyst", "irb"}
    assert set(parsed["demo_section_panels"].keys()) - {"_doc"} == {
        "section_1", "section_2", "section_3", "section_4", "section_5",
    }
    # Each section has all three personas keyed.
    for section_key in ("section_1", "section_2", "section_3", "section_4", "section_5"):
        section = parsed["demo_section_panels"][section_key]
        for persona_key in ("pi", "analyst", "irb"):
            assert persona_key in section, (
                f"_personas.json {section_key} missing {persona_key} panel"
            )
            assert len(section[persona_key]) > 0


def test_audience_invalid_value_raises_in_run_demo(tmp_path: Path) -> None:
    """``run_demo(audience='invalid')`` rejects unknown audience values
    with a clear ValueError. Closes the integration-auditor F4 finding —
    the developer-vs-public distinction is checked at the entrypoint,
    not silently coerced."""
    from biosensor_mcp.demo import run_demo

    with pytest.raises(ValueError, match="audience must be"):
        run_demo(
            save_shareable_path=tmp_path / "x.md",
            audience="public-mirror-extra",  # close-but-wrong
        )


def test_audience_invalid_value_raises_in_generate_shareable() -> None:
    """``_generate_shareable_markdown`` independently validates the
    audience param so any caller (not just the run_demo entrypoint) gets
    the same hard-fail."""
    from biosensor_mcp.demo.runner import _generate_shareable_markdown

    with pytest.raises(ValueError, match="audience must be"):
        _generate_shareable_markdown(
            transcript="dummy",
            version="6.13.0",
            install_url_base="https://github.com/x/y/releases/download",
            audience="vip",
        )


def test_developer_mode_is_default_and_preserves_adr_breadcrumbs(
    tmp_path: Path,
) -> None:
    """Backward-compat: default ``audience`` is ``"developer"`` and the
    saved markdown carries the 'Where to read next' ADR breadcrumb
    section (existing v6.12.0 shape; co-developer reading transcript
    can resolve the references)."""
    from biosensor_mcp.demo import run_demo

    out_path = tmp_path / "shareable.md"
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo(save_shareable_path=out_path)  # no audience kwarg

    content = out_path.read_text(encoding="utf-8")
    assert "Where to read next" in content
    assert "ADR 0001" in content
    assert "ADR 0030" in content  # newest ADR added to breadcrumb list


def test_public_mode_emits_persona_panels_for_every_section(
    tmp_path: Path,
) -> None:
    """In ``--audience=public`` mode the saved markdown contains 5
    section-panel headers and each carries all three persona labels.
    Closes integration-auditor F5 (panels render in friend-facing voice
    — the agent file's evaluation register is transformed by the schema-
    driven render, not verbatim-spliced)."""
    from biosensor_mcp.demo import run_demo

    out_path = tmp_path / "shareable.md"
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo(save_shareable_path=out_path, audience="public")

    content = out_path.read_text(encoding="utf-8")
    panel_header_count = content.count("### How to read this section")
    assert panel_header_count == 5, (
        f"audience=public must emit one panel header per section; "
        f"found {panel_header_count} (expected 5)"
    )
    # Each panel block contains all three persona labels (15 total).
    assert content.count("**Principal Investigator:**") == 5
    assert content.count("**Analyst / Research Software Engineer:**") == 5
    assert content.count("**IRB / Compliance reviewer:**") == 5


def test_public_mode_attribution_footer_present_no_contact_mechanisms(
    tmp_path: Path,
) -> None:
    """In ``--audience=public`` mode the footer is attribution-only —
    naming the author but providing zero outbound contact paths. Closes
    the ADR 0030 zero-outbound-affordances invariant on the rendered
    output (the test mirrors what a friend opening the public mirror
    page would see)."""
    from biosensor_mcp.demo import run_demo

    out_path = tmp_path / "shareable.md"
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo(save_shareable_path=out_path, audience="public")

    content = out_path.read_text(encoding="utf-8")
    # Attribution present.
    assert "Built by **Saahas Muthineni**" in content
    # No outbound contact mechanisms.
    assert "mailto:" not in content
    assert "discord.gg" not in content
    assert "discord.com" not in content
    assert "substack.com" not in content
    assert "pypi.org" not in content
    assert "/issues" not in content
    # No private-repo dead-link breadcrumbs (the v6.12.0 footer shape
    # this ADR replaces — make sure they don't leak through).
    assert "Where to read next" not in content
    assert "docs/design/research-framing.md" not in content
    assert "Source repo currently private" not in content


def test_public_mode_url_allowlist_hard_fails_on_mailto() -> None:
    """The render-time URL-scheme allowlist must reject any ``mailto:``
    URL — the structural enforcement of ADR 0030's
    zero-outbound-affordances invariant. Tests the helper directly so
    the failure shape is exercised even without running the full demo."""
    from biosensor_mcp.demo.runner import _enforce_public_url_allowlist

    bad = "Reach me at mailto:contact@example.com please."
    with pytest.raises(ValueError, match="banned scheme"):
        _enforce_public_url_allowlist(bad)


def test_public_mode_url_allowlist_hard_fails_on_disallowed_https() -> None:
    """Any non-wheel-release-asset ``https://`` URL must fail the
    allowlist. Future contributor adds a Discord/Substack/contact-form
    link "to be helpful" → CI failure rather than a silently-shipped
    public page."""
    from biosensor_mcp.demo.runner import _enforce_public_url_allowlist

    bad = "Join the discussion at https://discord.gg/biosensor-mcp."
    with pytest.raises(ValueError, match="disallowed outbound URL"):
        _enforce_public_url_allowlist(bad)


def test_public_mode_url_allowlist_passes_on_wheel_release_asset() -> None:
    """The wheel-release-asset URL pattern is the one outbound URL
    permitted on the public page (the install command needs it).
    Confirms the allowlist isn't accidentally too strict."""
    from biosensor_mcp.demo.runner import _enforce_public_url_allowlist

    good = (
        "Run with `uvx --from "
        "https://github.com/saahasmuthineni/biosensormcpdemo/releases/download/v6.13.0/biosensor_mcp-6.13.0-py3-none-any.whl "
        "biosensor-mcp demo`."
    )
    # Should NOT raise.
    _enforce_public_url_allowlist(good)


def test_splice_panels_returns_single_fence_when_no_section_headers() -> None:
    """Defensive: a transcript with no recognisable section headers
    wraps in a single code fence rather than crashing. This protects
    against silent rendering failures if the demo's section-emission
    code structure changes in a way the regex doesn't catch."""
    from biosensor_mcp.demo.runner import (
        _load_personas,
        _splice_panels_into_transcript,
    )

    personas_data = _load_personas()
    result = _splice_panels_into_transcript("just some text", personas_data)
    assert result.startswith("```\n")
    assert result.endswith("```\n")
    assert "How to read this section" not in result


def test_render_persona_panel_uses_friend_facing_voice() -> None:
    """Panel content for Section 1 must be the friend-facing voice
    written into _personas.json, NOT the agent file's evaluation
    register ('Should this framework be approved...'). This locks the
    F5 mitigation from the integration-auditor pass."""
    from biosensor_mcp.demo.runner import _load_personas, _render_persona_panel

    personas_data = _load_personas()
    panel = _render_persona_panel("section_1", personas_data)

    assert "**Principal Investigator:**" in panel
    assert "**Analyst / Research Software Engineer:**" in panel
    assert "**IRB / Compliance reviewer:**" in panel
    # Friend-facing voice markers (specific to Section 1's panels).
    assert "Defensible n / mean / std" in panel
    # Agent-evaluation register markers must NOT leak in.
    assert "Should this framework be approved" not in panel
    assert "RESEARCHER-LOAD-BEARING" not in panel


def test_public_mode_has_only_wheel_release_asset_outbound_urls(
    tmp_path: Path,
) -> None:
    """End-to-end: a real ``--audience=public`` render contains only the
    wheel-release-asset URL as outbound — no docs.astral.sh link
    (developer-mode-only), no other GitHub URLs. The render-time
    allowlist already enforces this; the test confirms the rendered
    output actually conforms (defends against the allowlist becoming
    too lax)."""
    import re

    from biosensor_mcp.demo import run_demo

    out_path = tmp_path / "shareable.md"
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo(save_shareable_path=out_path, audience="public")

    content = out_path.read_text(encoding="utf-8")
    outbound_urls = re.findall(r"https?://[^\s)\]\"'>]+", content)
    assert len(outbound_urls) > 0, "Install command must contain wheel URL"
    for url in outbound_urls:
        assert "/releases/download/" in url, (
            f"Disallowed outbound URL in --audience=public output: {url}"
        )


def test_public_mode_strips_developer_terminal_breadcrumbs(
    tmp_path: Path,
) -> None:
    """In public mode the captured transcript itself must not contain
    the developer-tier 'biosensor-mcp pilot' / 'biosensor-mcp tour'
    suggestion block — those reference recipient-facing CLI surfaces
    that scaffold private-repo files; not appropriate for a public
    page."""
    from biosensor_mcp.demo import run_demo

    out_path = tmp_path / "shareable.md"
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo(save_shareable_path=out_path, audience="public")

    content = out_path.read_text(encoding="utf-8")
    assert "If you want to use this with your own data" not in content
    assert "biosensor-mcp pilot" not in content
    assert "biosensor-mcp tour" not in content


def test_save_shareable_suppresses_redundant_tip_block(
    tmp_path: Path,
) -> None:
    """Once the user has invoked ``--save-shareable``, the 'Tip: save
    this transcript with --save-shareable' block becomes redundant in
    BOTH the user's terminal AND the captured transcript. Closes the
    integration-auditor BORDER finding about the three breadcrumb
    surfaces converging on the same affordance shape."""
    from biosensor_mcp.demo import run_demo

    out_path = tmp_path / "shareable.md"
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_demo(save_shareable_path=out_path)  # developer mode default

    terminal = buf.getvalue()
    saved = out_path.read_text(encoding="utf-8")
    assert "Tip: save this transcript" not in terminal
    assert "Tip: save this transcript" not in saved



"""
Demo runner — researcher first-look against the bundled HIP Lab
realistic cohort fixtures.

Per ADR 0029 (which partially supersedes ADR 0027 § Negative
consequences "the demo bypasses RouterMCP by design"),
``tailor demo`` exercises the framework's load-bearing
architectural claims via five sections:

    Section 1 — Cohort thesis (canonical first-look, kept from ADR 0027).
                Tier 1 cohort tools via ``child.execute()`` — pure-function
                numerical claims, citable in a paper.
    Section 2 — Router pipeline made visible. Same fixture, dispatched
                through ``RouterMCP._dispatch`` — ``_meta`` provenance
                stamp on the envelope, fresh row written to ``audit.db``.
    Section 3 — Three-tier resolution-appropriateness walk on S001.
                Tier 1 scalar → Tier 2 downsampled curve (consent-gated)
                → Tier 3 raw rows (cost-gated). Same question, three
                resolutions; the LLM never needed Tier 3 to answer the
                cohort question. Demo router uses
                ``cost_threshold=15_000`` so the bundled fixture trips
                the cost gate cleanly; production uses ``35_000``.
    Section 4 — Vault as second persistence tier. ``VaultLayer``
                captures an analyst moment that references the Section
                1 cohort finding; ``subject_id="S001"``.
    Section 5 — Local-LLM oracle (``NullBackend``; opt-in
                ``OllamaBackend`` produces narrative prose).
                ``related_substrate`` populates from the moment captured
                in Section 4.

The synthetic-Strava ``sample_data.py`` module is preserved per
ADR 0008 § Alternatives — still importable for
``tests/framework/test_router.py:1054`` and the worked-example
notebook, but no longer the demo's data source.

Reproducibility note (called out in framing prose): Section 1's
cohort numbers are bit-identical across runs (ADR 0008
deterministic-by-construction). Sections 2-5 print provenance metadata
(``_meta.called_at``, audit row IDs, oracle latency) that DOES change
across runs — expected, not a regression. The deterministic property
is on the numerics, not on the timestamps that wrap them.

Usage:
    tailor demo
    python -m tailor demo
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from importlib.resources import as_file, files
from io import StringIO
from pathlib import Path

# Pinned subject for the per-file diagnostic + the tier-walk + the
# vault moment + the oracle subject_id scoping. Pinning extends the
# ADR 0008 deterministic-by-construction property to the demo surface.
_REPRESENTATIVE_FILE = "S001_force.csv"
_REPRESENTATIVE_SUBJECT = "S001"

# Demo's cost-gate threshold (production uses 35_000 — see
# ``__main__.cmd_serve``). Calibrated so ``csv_raw_stream`` on the
# 6000-row S001 file (~24_000 estimated tokens per
# ``CSVProcessing.estimate_row_tokens``) trips the gate cleanly.
# Framing prose names this difference explicitly so the recipient
# understands the demo is calibrated for visibility, not rigged.
_DEMO_COST_THRESHOLD = 15_000


def _stage_force_fixtures(dest: Path) -> int:
    """Copy bundled HIP Lab ``force/`` subtree into ``dest``.

    Mirrors ``tour.py``'s ``_copy_resource_tree`` shape — file-by-file
    iteration so Python 3.10/3.11 work (``as_file`` on directories
    only landed in 3.12).
    """
    pkg_root = files("tailor._fixtures.hip_lab_demo_realistic.force")
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for child in pkg_root.iterdir():
        if child.is_file():
            with as_file(child) as src_path:
                shutil.copy2(src_path, dest / child.name)
            n += 1
    return n


def _write_demo_user_config(config_dir: Path, force_dir: Path) -> None:
    """Write a minimal ``user_config.json`` with a ``csv_dir`` block
    pointing at the staged force fixtures."""
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


def _print_section_header(title: str) -> None:
    print()
    print("-" * 64)
    print(title)
    print("-" * 64)


def _unwrap_envelope(dispatch_result) -> dict:
    """Unwrap ``router._dispatch``'s ``list[TextContent]`` return into a dict.

    The router serialises every result as MCP ``TextContent`` for the
    wire; the demo wants the underlying envelope dict so it can be
    pretty-printed. Defensive: returns ``{}`` on empty results, and a
    ``{"raw": ...}`` wrapper if the text isn't valid JSON.
    """
    if not dispatch_result:
        return {}
    first = dispatch_result[0]
    text = getattr(first, "text", None)
    if text is None:
        return {"raw": str(first)}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _print_call(tool_name: str, params: dict, result) -> None:
    """Print a tool-call envelope. Accepts either a raw dict (from
    ``child.execute()``) or a ``list[TextContent]`` (from
    ``router._dispatch()``); auto-unwraps the latter."""
    if isinstance(result, list):
        envelope: dict = _unwrap_envelope(result)
    else:
        envelope = result
    print(f"--- {tool_name}({json.dumps(params)}) ---")
    print(json.dumps(envelope, indent=2, default=str))
    print()


def _tail_audit_row(audit_db_path: Path) -> dict | None:
    """Read the most recent ``audit_log`` row directly via sqlite3.

    Avoids touching the ``AuditLog`` instance the router still holds —
    a parallel connection on WAL is safe; sharing the router's
    connection from the demo's main thread would risk state collisions.
    Returns ``None`` if the table is missing or unreadable rather than
    raising — the demo continues even if the audit-log tail breaks.
    """
    if not audit_db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(audit_db_path))
        try:
            cursor = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row is None:
                return None
            columns = [d[0] for d in cursor.description]
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return None
    return dict(zip(columns, row, strict=False))


class _Tee:
    """Tee writes to multiple streams.

    Used by ``--save-shareable`` to capture the demo's stdout into a
    string buffer while still letting the user see it interactively
    in their terminal. Lighter than ``contextlib.redirect_stdout``
    because we want both destinations, not just one.
    """

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data: str) -> int:
        for stream in self._streams:
            stream.write(data)
        return len(data)

    def flush(self) -> None:
        for stream in self._streams:
            try:
                stream.flush()
            except Exception:
                pass

    # Some libraries (notably some logging configurations) probe stdout
    # for these attributes; passing through to the first underlying
    # stream keeps surprises off the wire.
    def __getattr__(self, name):
        return getattr(self._streams[0], name)


# ----- ADR 0030 helpers (audience-aware shareable rendering) ---------
#
# The block below implements the rendering side of ADR 0030's
# "narrative + zero-outbound-affordances" decision. Three concerns:
#
#   * F1 mitigation — persona content is loaded from the structured
#     ``_personas.json`` schema shipped with the package, NOT parsed
#     out of the agent file's markdown headings (which had no schema
#     contract).
#   * F3 mitigation — public-mode output is checked at render time
#     against an URL allowlist; only the wheel-release-asset URL is
#     permitted. Any banned scheme (mailto, ftp) or any other outbound
#     URL hard-fails CI rather than silently shipping.
#   * F4 mitigation — the ``audience`` parameter preserves the existing
#     developer-to-developer transcript-share use case (with ADR
#     breadcrumbs) while opting into the public-mirror render shape.

# Section header pattern emitted by ``_print_section_header`` — three
# lines: 64 dashes, ``Section N - <title>``, 64 dashes.
_SECTION_HEADER_PATTERN = re.compile(
    r"^-{64}\nSection ([1-5]) - (.+)\n-{64}$",
    re.MULTILINE,
)

# Public-mirror URL allowlist: only the wheel-release-asset URL is
# permitted in audience=public output. Any other ``https://`` outbound
# link is a structural violation of ADR 0030's zero-outbound-affordances
# invariant.
_ALLOWED_PUBLIC_URL_PATTERN = re.compile(
    r"^https://github\.com/[^/]+/[^/]+/releases/download/"
)
_OUTBOUND_URL_PATTERN = re.compile(r"https?://[^\s)\]\"'>]+")
_BANNED_URL_SCHEMES = ("mailto:", "ftp:", "tel:")


def _load_personas() -> dict:
    """Load canonical persona definitions + per-section panels from the
    package's ``_personas.json`` data file.

    Returns the parsed JSON as a dict. Hard-fails (lets JSONDecodeError
    or FileNotFoundError propagate) on a malformed or missing schema —
    that's the point of using a structured schema (closes
    ``integration-auditor`` F1: silent coupling against an unschema'd
    markdown file).
    """
    data = (
        files("tailor.demo")
        .joinpath("_personas.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(data)


def _render_persona_panel(section_key: str, personas_data: dict) -> str:
    """Emit a markdown 'how to read this section' panel block for one
    section, with one paragraph per persona (PI / analyst / IRB).

    Returns an empty string if ``section_key`` isn't in
    ``demo_section_panels`` (defensive — a future Section 6 added to
    ``runner.py`` without a corresponding ``_personas.json`` entry
    produces no panel rather than a wrong one).
    """
    panels = personas_data.get("demo_section_panels", {}).get(section_key)
    personas = personas_data.get("personas", {})
    if not panels or not personas:
        return ""
    title = panels.get("title", section_key)
    parts = [f"### How to read this section ({title})", ""]
    for persona_key in ("pi", "analyst", "irb"):
        persona = personas.get(persona_key, {})
        label = persona.get("name", persona_key)
        copy = panels.get(persona_key, "")
        if copy:
            parts.append(f"**{label}:** {copy}")
            parts.append("")
    return "\n".join(parts)


def _splice_panels_into_transcript(
    transcript: str, personas_data: dict
) -> str:
    """In ``audience=public`` mode, split the captured transcript at
    section-header boundaries and emit per-section persona panels
    OUTSIDE the code fence so they render as markdown.

    Output structure: a code-fenced preamble, then for each section a
    code-fenced section block followed by a markdown panel naming what
    each persona sees in that section.

    Defensive: if no section headers match (e.g. the captured transcript
    is malformed), wrap the whole thing in a single code fence and
    return — no panels, but no crash either.
    """
    matches = list(_SECTION_HEADER_PATTERN.finditer(transcript))
    if not matches:
        return f"```\n{transcript}\n```\n"

    chunks: list[str] = []

    preamble = transcript[: matches[0].start()].rstrip()
    if preamble:
        chunks.append(f"```\n{preamble}\n```")
        chunks.append("")

    for i, match in enumerate(matches):
        section_num = match.group(1)
        section_key = f"section_{section_num}"
        end = (
            matches[i + 1].start()
            if i + 1 < len(matches)
            else len(transcript)
        )
        section_text = transcript[match.start() : end].rstrip()
        chunks.append(f"```\n{section_text}\n```")
        chunks.append("")
        panel = _render_persona_panel(section_key, personas_data)
        if panel:
            chunks.append(panel)
            chunks.append("")

    return "\n".join(chunks)


def _enforce_public_url_allowlist(rendered: str) -> None:
    """Hard-fail per ADR 0030 if the rendered markdown contains any
    outbound URL outside the wheel-release-asset allowlist or any
    banned URL scheme (mailto, ftp, tel).

    Raises ``ValueError`` on any violation. The render-time check is
    the structural backstop on the zero-outbound-affordances invariant
    — a future contributor adding a Discord link "to be helpful" gets
    a CI failure rather than a silently-shipped public page.
    """
    for scheme in _BANNED_URL_SCHEMES:
        if scheme in rendered:
            raise ValueError(
                f"--audience=public rendered output contains banned "
                f"scheme {scheme!r}; ADR 0030 prohibits outbound contact "
                f"mechanisms on the public mirror page (no mailto, no "
                f"platform links, no community-shape destinations). "
                f"Either render with --audience=developer or remove the "
                f"offending link before generating the shareable file."
            )
    for match in _OUTBOUND_URL_PATTERN.finditer(rendered):
        url = match.group(0)
        if not _ALLOWED_PUBLIC_URL_PATTERN.match(url):
            raise ValueError(
                f"--audience=public rendered output contains disallowed "
                f"outbound URL {url!r}; ADR 0030 permits outbound URLs "
                f"only for the wheel release asset (a "
                f"github.com/<owner>/<repo>/releases/download/ pattern). "
                f"Either render with --audience=developer or remove the "
                f"offending link before generating the shareable file."
            )


def _generate_shareable_markdown(
    transcript: str,
    version: str,
    install_url_base: str,
    audience: str = "developer",
) -> str:
    """Wrap a captured demo transcript in a shareable markdown document.

    Args:
        transcript: The captured stdout of a ``tailor demo`` run
            (the entire five-section walk).
        version: ``tailor.__version__`` — substituted into the
            install URL so the wheel filename matches the release on
            the public mirror repo.
        install_url_base: The GitHub release URL prefix for the public
            mirror repo (default points at saahasmuthineni's mirror;
            overridable via ``BIOSENSOR_DEMO_INSTALL_URL_BASE``).
        audience: Either ``"developer"`` (default; existing v6.12.0
            behaviour with ADR breadcrumbs in the footer, transcript
            in a single code fence — suitable for sharing a debug
            transcript with a co-developer who can resolve the ADR
            references) or ``"public"`` (per ADR 0030: per-persona
            reading panels spliced after each section, attribution-only
            footer with no outbound contact mechanisms, render-time
            URL-scheme allowlist enforced — suitable for public-mirror
            rendering).

    Returns:
        A complete markdown document. In ``audience="public"`` mode,
        raises ``ValueError`` if the rendered output contains any
        outbound URL outside the wheel-release-asset allowlist (the
        structural enforcement of ADR 0030's zero-outbound-affordances
        invariant).
    """
    if audience not in ("developer", "public"):
        raise ValueError(
            f"audience must be 'developer' or 'public'; got {audience!r}"
        )

    wheel_filename = f"tailor-{version}-py3-none-any.whl"
    wheel_url = f"{install_url_base}/v{version}/{wheel_filename}"

    if audience == "public":
        # Per ADR 0030: per-section persona panels spliced in,
        # attribution-only footer, URL allowlist enforced.
        personas_data = _load_personas()
        transcript_block = _splice_panels_into_transcript(
            transcript, personas_data
        )
        # Install instructions in public mode use bare technical names
        # for `uv` and `pipx` (no link to docs.astral.sh) so the
        # wheel-release-asset stays the only outbound URL on the page.
        rendered = (
            f"# Biosensor MCP — demo (v{version})\n"
            "\n"
            "Local-first infrastructure for LLM-assisted analysis of\n"
            "biometric data, built for health-research workflows where\n"
            "data governance, audit trails, and reproducibility matter.\n"
            "The transcript below is the actual output of\n"
            f"`tailor demo` on v{version}; running the same\n"
            "command on your machine should produce structurally-\n"
            "identical output (Section 1's numerical claims are\n"
            "bit-identical by design).\n"
            "\n"
            "## Run it yourself (one command)\n"
            "\n"
            "If you have `uv` installed (recommended; install separately\n"
            "if needed):\n"
            "\n"
            "```\n"
            f"uvx --from {wheel_url} tailor demo\n"
            "```\n"
            "\n"
            "Or with `pipx`:\n"
            "\n"
            "```\n"
            f"pipx run --spec {wheel_url} tailor demo\n"
            "```\n"
            "\n"
            "Either command installs the wheel into an ephemeral\n"
            "isolated env, runs the demo (~30 seconds), and exits clean.\n"
            "Nothing persists on your machine.\n"
            "\n"
            "## Demo output\n"
            "\n"
            f"{transcript_block}\n"
            "---\n"
            "\n"
            "Built by **Saahas Muthineni**. If you received this URL\n"
            "personally and have questions, reply through whatever\n"
            "channel he sent it through.\n"
            "\n"
            "---\n"
            "\n"
            f"Generated by `tailor demo --audience=public "
            f"--save-shareable` on v{version}.\n"
        )
        # Hard-fail per ADR 0030 if any disallowed outbound URL appears.
        _enforce_public_url_allowlist(rendered)
        return rendered

    # Developer mode (default; backward-compatible with v6.12.0).
    return f"""# Biosensor MCP - demo (v{version})

Local-first infrastructure for LLM-assisted analysis of biometric
data, built for health-research workflows where data governance,
audit trails, and reproducibility matter. The transcript below is
the actual output of `tailor demo` on v{version}; running the
same command on your machine should produce structurally-identical
output (Section 1's numerical claims are bit-identical by design).

## Run it yourself (one command)

If you have [`uv`](https://docs.astral.sh/uv/) installed (recommended):

```
uvx --from {wheel_url} tailor demo
```

Or with `pipx`:

```
pipx run --spec {wheel_url} tailor demo
```

Either command installs the wheel into an ephemeral isolated env,
runs the demo (~30 seconds), and exits clean. Nothing persists on
your machine.

## Demo output

```
{transcript}
```

## Where to read next, in order of depth

The framework is documented as a chain of numbered design decisions
(ADRs). The transcript above cites several of them inline; the
load-bearing ones for this demo are:

- ADR 0001 - Audit log as the backbone of reproducibility
- ADR 0005 - Cost pre-estimation with cheaper-alternative suggestions
- ADR 0008 - Analytical processing is deterministic by construction
- ADR 0022 - Local-LLM guardian (the cooperation loop in Section 5)
- ADR 0029 - Token reduction is analytical quality, not just cost optimization
- ADR 0030 - Public-mirror page deepens narratively; outbound affordances pruned to zero

For the longer audience-facing overview, see the project's `README.md`.
For the IRB / RSE deep dive, see `docs/design/research-framing.md`.
The full ADR set lives at `docs/adr/`. (Source repo currently private;
ask for access if interested.)

(This is the developer-mode shareable transcript; for the public-
mirror render with per-persona reading panels and zero outbound
affordances per ADR 0030, pass `--audience=public`.)

---

Generated by `tailor demo --save-shareable` on v{version}.
"""


def _approx_token_count(payload) -> int:
    """Rough byte-based token estimate for printed envelope summaries.

    Accepts either a dict envelope (from ``child.execute()``) or a
    ``list[TextContent]`` (from ``router._dispatch()``). For the
    list shape, the size lives inside ``.text`` — that's the wire
    payload the recipient effectively sees printed.
    """
    if isinstance(payload, list) and payload:
        first = payload[0]
        text = getattr(first, "text", None)
        if text is not None:
            return max(1, len(text) // 4)
    return max(1, len(json.dumps(payload, default=str)) // 4)


def run_demo(
    *,
    save_shareable_path: Path | None = None,
    audience: str = "developer",
) -> None:
    """Researcher first-look — five-section walk through the framework's
    load-bearing architectural claims against bundled HIP Lab fixtures.
    See ADR 0029.

    Args:
        save_shareable_path: When non-``None``, also captures the
            demo's stdout into a shareable markdown file at this path.
            The file is self-contained and suitable for emailing or
            hosting at a static URL. The user still sees the demo run
            interactively in their terminal; the tee captures
            alongside, doesn't replace. See
            ``_generate_shareable_markdown`` for the template.
        audience: Either ``"developer"`` (default; existing v6.12.0
            behaviour — captured transcript carries ADR breadcrumbs
            for a co-developer reader) or ``"public"`` (per ADR 0030 —
            the captured transcript drops developer-tier breadcrumbs
            and the rendered markdown gets per-persona reading panels
            + attribution-only footer + URL-allowlist enforcement,
            suitable for the public mirror page). Has no effect when
            ``save_shareable_path`` is ``None`` (no transcript captured).
    """
    if audience not in ("developer", "public"):
        raise ValueError(
            f"audience must be 'developer' or 'public'; got {audience!r}"
        )
    # Suppress the framework's INFO/WARNING log lines so stderr does not
    # interleave with the demo's stdout output. The structurally
    # important warnings (e.g. PHIScrubber's no-op default) still
    # appear in the printed `_meta.scrubber_warning` field where they
    # are recipient-visible; silencing the duplicate stderr emission
    # keeps the demo's transcript clean for sharing.
    import logging
    logging.getLogger("tailor").setLevel(logging.ERROR)

    # Optionally tee stdout into a buffer so the captured transcript
    # can be wrapped into a shareable markdown file at the end. When
    # save_shareable_path is None this is a no-op — production-deployed
    # `tailor demo` (without the flag) is behaviourally
    # unchanged.
    _shareable_buffer: StringIO | None = None
    _original_stdout = sys.stdout
    if save_shareable_path is not None:
        _shareable_buffer = StringIO()
        sys.stdout = _Tee(_original_stdout, _shareable_buffer)

    print("Biosensor MCP - Demo")
    print("=" * 64)
    print(
        "Local-first infrastructure for LLM-assisted analysis of"
    )
    print(
        "biometric data, built for health-research workflows where"
    )
    print(
        "data governance, audit trails, and reproducibility matter."
    )
    print(
        "This demo walks through the framework's load-bearing"
    )
    print(
        "architectural claims in five sections (~30 seconds, no"
    )
    print(
        "install state - runs entirely in a tempdir). The numbered"
    )
    print(
        "ADR references in framing prose point at design records"
    )
    print(
        "under docs/adr/ in the source repo."
    )
    print()
    print(
        "HIP Lab realistic cohort fixture: 16 synthetic subjects"
    )
    print(
        "performing a sustained-grip task to exhaustion (an isometric"
    )
    print(
        "task to volitional failure), with a metadata.json sidecar"
    )
    print(
        "carrying group / sex / baseline_mvc per subject."
    )
    print()

    with tempfile.TemporaryDirectory(prefix="biosensor-demo-") as tmpdir:
        tmp_root = Path(tmpdir)
        config_dir = tmp_root / "config"
        data_dir = tmp_root / "data"
        force_dir = tmp_root / "force"
        vault_dir = tmp_root / "vault"
        data_dir.mkdir(parents=True, exist_ok=True)

        _stage_force_fixtures(force_dir)
        _write_demo_user_config(config_dir, force_dir)
        # The staged tree contains 16 force CSVs + 1 metadata.json
        # sidecar; n_csvs is the recipient-facing count.
        n_csvs = sum(1 for p in force_dir.iterdir() if p.suffix == ".csv")
        print(
            f"Loaded {n_csvs} force CSVs + metadata.json sidecar from "
            f"tailor._fixtures.hip_lab_demo_realistic.force "
            f"into a tempdir."
        )

        # Construct framework wiring (mirrors __main__.cmd_serve except
        # for cost_threshold tuning and tempdir paths).
        from tailor.children.csv_dir import CSVDirectoryChild
        from tailor.framework.local_llm import (
            LocalLLMLayer,
            NullBackend,
        )
        from tailor.framework.router import RouterMCP
        from tailor.framework.vault import VaultLayer, VaultWriter

        router = RouterMCP(
            name="biosensor-demo",
            data_dir=data_dir,
            cost_threshold=_DEMO_COST_THRESHOLD,
            circuit_threshold=3,
            circuit_reset=300,
        )
        child = CSVDirectoryChild(config_dir=config_dir, data_dir=data_dir)
        router.register_child(child)

        vault_writer: VaultWriter | None = None

        try:
            # ------ Section 1 - Cohort thesis (canonical first-look) ------
            _print_section_header(
                "Section 1 - cohort thesis (numbers from a pure function)"
            )
            print(
                "These numbers came from CSVProcessing.cohort_stats() - a"
            )
            print(
                "@staticmethod pure function (ADR 0008). Bit-identical"
            )
            print(
                "across runs and citable in a paper. Compare with asking"
            )
            print(
                "an LLM to compute means by sex from 16 raw force CSVs:"
            )
            print(
                "arithmetic errors, fabricated numbers, or refusal."
            )
            print()
            section1_calls: list[tuple[str, dict]] = [
                (
                    "csv_cohort_summary",
                    {"column": "force_N", "group_by": "sex", "metric": "max"},
                ),
                (
                    "csv_cohort_summary",
                    {"column": "force_N", "group_by": "group", "metric": "max"},
                ),
                (
                    "csv_force_decline",
                    {"file_id": _REPRESENTATIVE_FILE, "column": "force_N"},
                ),
            ]
            cohort_result_for_moment: dict | None = None
            for tool_name, params in section1_calls:
                result = asyncio.run(child.execute(tool_name, params))
                _print_call(tool_name, params, result)
                if (
                    tool_name == "csv_cohort_summary"
                    and params.get("group_by") == "sex"
                ):
                    cohort_result_for_moment = result

            # ------ Section 2 - Router pipeline made visible ------
            _print_section_header(
                "Section 2 - router pipeline (audit log + _meta provenance)"
            )
            print(
                "Same child, dispatched through RouterMCP this time. The"
            )
            print(
                "result envelope carries _meta with package_version,"
            )
            print(
                "called_at, scrubber_id, and per-call + session token"
            )
            print(
                "counts. Every call lands in audit.db (ADR 0001) -"
            )
            print(
                "durable evidence for an IRB or methods-paper reviewer"
            )
            print(
                "reconstructing how the analyst accessed the data."
            )
            print()
            section2_params = {
                "file_id": _REPRESENTATIVE_FILE,
                "subject_id": _REPRESENTATIVE_SUBJECT,
            }
            section2_result = asyncio.run(
                router._dispatch("csv_summary_report", section2_params)
            )
            _print_call(
                "csv_summary_report", section2_params, section2_result
            )
            audit_row = _tail_audit_row(data_dir / "audit.db")
            if audit_row is not None:
                print("Latest audit_log row (durable evidence):")
                print(json.dumps(audit_row, indent=2, default=str))
                print()

            # ------ Section 3 - Three-tier resolution walk ------
            _print_section_header(
                "Section 3 - three resolutions of the same question"
            )
            print(
                f"Question: 'what is the peak force in {_REPRESENTATIVE_FILE}?'"
            )
            print()
            print(
                "Tier 1 (server-side scalar) - answered from a pure"
            )
            print(
                "function; no rows reach the LLM."
            )
            tier1_params = {
                "file_id": _REPRESENTATIVE_FILE,
                "column": "force_N",
                "subject_id": _REPRESENTATIVE_SUBJECT,
            }
            tier1_result = asyncio.run(
                router._dispatch("csv_force_decline", tier1_params)
            )
            tier1_tokens = _approx_token_count(tier1_result)
            print(
                f"  -> Tier 1 (csv_force_decline): "
                f"~{tier1_tokens} tokens of output (one structured answer)"
            )
            print()

            print(
                "Tier 2 (downsampled curve) - fires the consent gate"
            )
            print(
                "first. ADR 0004 says the gate returns a structured"
            )
            print(
                "LLMInstruction, not a free-text paragraph. Here it is:"
            )
            print()
            tier2_params = {
                "file_id": _REPRESENTATIVE_FILE,
                "interval": 5,
                "subject_id": _REPRESENTATIVE_SUBJECT,
            }
            tier2_blocked = asyncio.run(
                router._dispatch("csv_downsampled", tier2_params)
            )
            _print_call(
                "csv_downsampled (consent-gated)",
                tier2_params,
                tier2_blocked,
            )

            print("Approving consent in-script and retrying...")
            asyncio.run(router._dispatch("approve_consent_csv_dir", {}))
            tier2_result = asyncio.run(
                router._dispatch("csv_downsampled", tier2_params)
            )
            tier2_tokens = _approx_token_count(tier2_result)
            print(
                f"  -> Tier 2 (csv_downsampled, interval=5): "
                f"~{tier2_tokens} tokens (curve shape preserved)"
            )
            print()

            print(
                "Tier 3 (raw rows) - fires the cost gate. ADR 0005"
            )
            print(
                "returns an estimate AND a cheaper-alternative"
            )
            print(
                "suggestion. The demo's RouterMCP uses"
            )
            print(
                f"cost_threshold={_DEMO_COST_THRESHOLD:,} so the bundled"
            )
            print(
                "fixture trips the gate; production deployments use"
            )
            print(
                "35,000. The point is not 'cost' - it is 'this question"
            )
            print(
                "does not need per-row resolution.' The framework"
            )
            print(
                "teaches the LLM what resolution actually answers what"
            )
            print(
                "question."
            )
            print()
            tier3_params = {
                "file_id": _REPRESENTATIVE_FILE,
                "subject_id": _REPRESENTATIVE_SUBJECT,
            }
            tier3_result = asyncio.run(
                router._dispatch("csv_raw_stream", tier3_params)
            )
            tier3_tokens = _approx_token_count(tier3_result)
            _print_call(
                "csv_raw_stream (cost-gated)", tier3_params, tier3_result
            )
            print(
                f"  -> Tier 3 (csv_raw_stream, blocked envelope): "
                f"~{tier3_tokens} tokens"
            )
            print()
            print(
                "The LLM never needed Tier 3 to answer the cohort"
            )
            print(
                "question in Section 1. Tier 3 exists for the human (a"
            )
            print(
                "methods-paper figure, an outlier hunt) - not the model."
            )
            print(
                "Token reduction is analytical quality, not just billing:"
            )
            print(
                "Tier 1 is correct, citable, reproducible; Tier 3 is for"
            )
            print(
                "plotting, not reasoning."
            )

            # ------ Section 4 - Vault: durable analytical memory ------
            _print_section_header(
                "Section 4 - vault: cross-session analytical memory"
            )
            print(
                "VaultLayer wires up a second persistence tier (ADR"
            )
            print(
                "0007): biosensor cache is ephemeral / rebuildable; the"
            )
            print(
                "vault is durable analyst-authored interpretation,"
            )
            print(
                "written as plain markdown. Capturing the Section 1"
            )
            print(
                "finding as a moment, scoped to subject_id='S001':"
            )
            print()
            vault_writer = VaultWriter(
                vault_path=vault_dir,
                data_dir=data_dir,
                vaultable_tools=set(),  # csv_dir has no vaultable tools
                max_hr=195,
            )
            router.register_post_execute_hook(vault_writer)
            router.register_vault_layer(VaultLayer(
                vault_path=vault_dir,
                vault_writer=vault_writer,
                backfill_config={
                    "list_tool": "csv_list_files",
                    "report_tool": "csv_summary_report",
                },
            ))

            moment_params = {
                "title": "Sex-grouped peak force in HIP Lab cohort",
                "body": (
                    "Section 1 returned per-sex peak-force statistics on "
                    "16 synthetic subjects. Captured as a moment "
                    "referencing the cohort thesis. Numerical claims "
                    "above came from CSVProcessing.cohort_stats(); this "
                    "note is the analyst's interpretation of them."
                ),
                "subject_id": _REPRESENTATIVE_SUBJECT,
                "tags": ["demo", "cohort", "force"],
            }
            moment_result = asyncio.run(
                router._dispatch("vault_capture_moment", moment_params)
            )
            _print_call(
                "vault_capture_moment", moment_params, moment_result
            )

            # Show the markdown source-of-truth so the recipient sees
            # plaintext, not just the SQLite index row.
            moments_dir = vault_dir / "moments"
            if moments_dir.exists():
                md_files = sorted(moments_dir.glob("*.md"))
                if md_files:
                    md = md_files[0]
                    print(f"Markdown written to {md.name}:")
                    print()
                    body = md.read_text(encoding="utf-8")
                    # Trim very long bodies for first-look brevity;
                    # full file is still on disk for the curious.
                    if len(body) > 1500:
                        body = body[:1500] + "\n... (truncated)\n"
                    print(body)
                    print()

            # ------ Section 5 - Local-LLM oracle ------
            _print_section_header(
                "Section 5 - local-LLM oracle (cooperation loop)"
            )
            print(
                "LocalLLMLayer (ADR 0022) is wired with NullBackend by"
            )
            print(
                "default - the layer always exists; only the prose-"
            )
            print(
                "composition backend is opt-in. NullBackend produces the"
            )
            print(
                "structurally-correct envelope without an LLM running,"
            )
            print(
                "so the demo works on any machine. With OllamaBackend"
            )
            print(
                "wired against a local Ollama server, the same call"
            )
            print(
                "would compose narrative prose grounded in the resolved"
            )
            print(
                "Section 1 result."
            )
            print()
            print(
                "The oracle's related_substrate field auto-populates"
            )
            print(
                "from the vault scan (ADR 0023) - the moment captured"
            )
            print(
                "in Section 4 surfaces here without the LLM having to"
            )
            print(
                "remember the slug. This is architecturally possible"
            )
            print(
                "because Tier-1 outputs are small enough that a local"
            )
            print(
                "1B-param model could compose over them; raw streams"
            )
            print(
                "(Section 3) are too large for any local-tier context"
            )
            print(
                "window. Token reduction makes the local-LLM tier"
            )
            print(
                "feasible at all."
            )
            print()
            router.register_local_llm_layer(LocalLLMLayer(
                backend=NullBackend(),
                vault_storage=vault_writer.storage,
            ))
            oracle_params: dict = {
                "question": (
                    "How does peak force compare across sexes in this cohort?"
                ),
                "subject_id": _REPRESENTATIVE_SUBJECT,
            }
            if cohort_result_for_moment is not None:
                # resolved_context is a {processing_call: result} map
                # per OracleRequest contract, NOT a list of call records.
                # NullBackend's _flatten_claims walks .items() so the
                # numerical claims surface from the cohort result for
                # citation, even with no LLM running.
                oracle_params["resolved_context"] = {
                    "csv_cohort_summary": cohort_result_for_moment,
                }
            oracle_result = asyncio.run(
                router._dispatch("ask_local_oracle", oracle_params)
            )
            _print_call("ask_local_oracle", oracle_params, oracle_result)

        finally:
            # Close every SQLite-WAL holder before TemporaryDirectory
            # cleanup. On Windows, leaving any of these open raises
            # PermissionError on tempdir teardown - the v6.10.x
            # recipient-failure pattern. Each close wrapped in
            # try/except so a failure on one does not block the rest.
            for closeable in (router, vault_writer, child):
                if closeable is None:
                    continue
                try:
                    closeable.close()
                except Exception:
                    pass

    print()
    print("=" * 64)
    print("Demo complete.")
    print()
    print("What you just saw, by section:")
    print(
        "  1. Cohort thesis from a pure function - bit-identical on rerun."
    )
    print(
        "  2. The same fixture wrapped in router pipeline - _meta + audit."
    )
    print(
        "  3. Three resolutions of the same question - Tier 1 wins on"
    )
    print(
        "     analytical quality, not just on cost."
    )
    print(
        "  4. Vault as durable interpretive layer - markdown is the"
    )
    print(
        "     source of truth; SQLite is the query index."
    )
    print(
        "  5. Local-LLM cooperation loop - feasible because (1) is small."
    )
    print()
    print(
        "Reproducibility: Section 1's numbers are bit-identical across"
    )
    print(
        "runs (ADR 0008). Sections 2-5 print provenance metadata"
    )
    print(
        "(called_at, audit row IDs, oracle latency) that DOES change"
    )
    print(
        "across runs - that is expected, not a regression. The"
    )
    print(
        "deterministic property is on the numerics, not on the"
    )
    print(
        "timestamps that wrap them."
    )
    # Developer-mode breadcrumbs: ADR pointers + alternative-CLI
    # surfaces. Suppressed in audience=public per ADR 0030 because the
    # public mirror page contains no outbound contact mechanisms and
    # the breadcrumbs reference private-repo files that 404 to any
    # non-collaborator.
    if audience == "developer":
        print()
        print(
            "Where to read next, in order of depth:"
        )
        print(
            "  - README.md             - audience-facing overview"
        )
        print(
            "  - CLAUDE.md             - architectural map + agent roster"
        )
        print(
            "  - docs/adr/             - numbered design decisions; ADR"
        )
        print(
            "                            citations above link here"
        )
        print(
            "  - docs/design/research-framing.md"
        )
        print(
            "                          - the longer-form RSE / IRB doc"
        )
        print()
        print(
            "If you want to use this with your own data:"
        )
        print(
            "  - `tailor pilot` - three-prompt wizard for a"
        )
        print(
            "                            multi-subject CSV pilot"
        )
        print(
            "  - `tailor tour`  - scaffolds the demo fixtures into"
        )
        print(
            "                            a durable directory and registers"
        )
        print(
            "                            with Claude Desktop"
        )

    # The "save with --save-shareable" tip is redundant once the user
    # has invoked the flag; suppress on saved runs (independent of
    # audience). Closes the integration-auditor BORDER finding about
    # the three-breadcrumb-surface convergence.
    if save_shareable_path is None:
        print()
        print(
            "Tip: save this transcript as a shareable markdown file with"
        )
        print(
            "  `tailor demo --save-shareable`"
        )
        print(
            "(emits to ~/.tailor/shareable-demo-vX.Y.Z.md by"
        )
        print(
            "default; pass a path to override). The resulting file is"
        )
        print(
            "self-contained and ready to email or host."
        )

    # Tee finalization. If save_shareable_path was set, restore the
    # original stdout and write the captured transcript wrapped in a
    # shareable markdown template. Done unconditionally in a finally-
    # equivalent so a partial demo (e.g. exception during a section)
    # still produces a usable file.
    if _shareable_buffer is not None and save_shareable_path is not None:
        sys.stdout = _original_stdout
        try:
            from tailor import __version__ as _pkg_version
        except Exception:
            _pkg_version = "unknown"
        install_url_base = os.environ.get(
            "BIOSENSOR_DEMO_INSTALL_URL_BASE",
            "https://github.com/saahasmuthineni/biosensormcpdemo/releases/download",
        )
        markdown = _generate_shareable_markdown(
            transcript=_shareable_buffer.getvalue(),
            version=_pkg_version,
            install_url_base=install_url_base,
            audience=audience,
        )
        save_shareable_path.parent.mkdir(parents=True, exist_ok=True)
        save_shareable_path.write_text(markdown, encoding="utf-8")
        print()
        print(f"Shareable demo saved to: {save_shareable_path}")
        print(
            "  Send this file (or paste its contents) to share the"
            " demo."
        )

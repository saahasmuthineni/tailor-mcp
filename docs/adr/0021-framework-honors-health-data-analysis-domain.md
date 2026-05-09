# ADR 0021: Project domain is health data analysis; framework must architecturally reflect that

- **Status:** Proposed
- **Date:** 2026-05-01
- **Related:** [ADR 0003 (PHI scrubber as seam)](0003-phi-scrubber-seam.md), [ADR 0007 (Rendering-layers policy)](0007-rendering-layers-policy.md), [ADR 0011 (Promotion policy)](0011-promotion-policy.md), [ADR 0014 (Coverage criticality invariant)](0014-coverage-criticality-invariant.md), [ADR 0017 (ADR weigher and autonomous-session cap)](0017-adr-weigher-and-autonomous-session-cap.md), [CLAUDE.md § What This Project Is](../../CLAUDE.md#what-this-project-is)

## Context

The boss's framing for this project, stated verbatim on 2026-05-01:
*"the health data part is load bearing, not the actual implementation
on how I used it for my run analysis. So the domain should be health
data analysis not running analysis."* The framework's stated audience is
health researchers — academic medical centers, mHealth labs,
sleep / CGM / cardiology groups — and the running child is one worked
example used to dogfood the `ChildMCP` extension pattern. That framing
already lives in [CLAUDE.md § What This Project Is](../../CLAUDE.md#what-this-project-is)
and in [`children/__init__.py`](../../src/tailor/children/__init__.py)'s
"children are the extension point" docstring.

The code does not honor that framing. The framework's vault layer,
renderer dispatch, domain inference, and one Tier-1 vault tool are
hardcoded to the running child. An `integration-auditor` proposal-mode
pass on a `git mv children/running/ → examples/` (the obvious move that
the framing prescribes) returned `REVISE` with thirteen blocking items
and five silent regressions if shipped without prep work. The coupling
sites are concrete and locatable:

- The vault writer's renderer dispatch table at
  [`framework/vault/writer.py`](../../src/tailor/framework/vault/writer.py)
  (the `self._renderers` dict in `VaultWriter.__init__`) seeds three
  hardcoded `strava_*` keys (`strava_run_report`, `strava_trend_report`,
  `strava_compare_runs`) — the framework's main rendering surface
  is named after the worked example.
- Three `strava_`-specific renderer functions in
  [`framework/vault/renderer.py`](../../src/tailor/framework/vault/renderer.py)
  — `render_run_note`, `render_trend_note`, `render_compare_note`,
  plus the activity-detail glue around them — live in framework code
  rather than in the running child's package.
- Hardcoded `domain="running"` queries in
  [`framework/vault/layer.py`](../../src/tailor/framework/vault/layer.py)
  at three call sites (lines 1100, 1731, 2125), plus the
  `_handle_fitness_summary` handler at line 1052 which is the
  vault's only running-specific orientation tool, plus
  `_domain_for_kind` at line 2798 which encodes a fixed kind→domain
  map. The framework's vault dispatch literally assumes "fitness"
  is the canonical domain and "running" is its store.
- Filesystem-layout running inference plus a `strava_id` frontmatter
  fallback in
  [`framework/vault/rescan.py`](../../src/tailor/framework/vault/rescan.py)
  (around line 162 for the domain inference, line 164 for the
  `strava_id` legacy-key fallback). The framework's index revalidator
  carries domain knowledge of one specific child.

CLAUDE.md's "running is a worked example, not canonical" claim has
been retroactive framing — the doc was rewritten ahead of the code.
The framing-vs-code gap is the failure mode this ADR addresses. If the
project ships a CGM child, a sleep child, an EDF reader, or a FHIR
ingester to the framework as it stands, each one re-discovers the same
coupling, and each one ships its own ad-hoc workaround for the
`vault_get_fitness_summary` blind spot. The architectural commitment
either becomes load-bearing or it does not.

The question this ADR answers: *what does it mean, structurally, for
the framework to be a health-data-analysis substrate rather than a
running-analysis app, and what is the project committing to in order
to make the code match the framing?*

## Decision

The framework's domain is health data analysis. The vault layer,
renderer dispatch, domain inference, and tool surface treat domains
and tool names as opaque strings — no special-case handling for any
specific child. v7.0.0 is a decouple-prep release cycle, not a
feature cycle. The actual `git mv` of `children/running/` →
`examples/` ships in v8.0.0, after the four coupling sites named in
Context have been decoupled and a synthetic-child replacement covers
the integration-test surface that running's tests currently provide.

Plain-language commitments the framework makes:

- **Renderer dispatch becomes a registration API.** `VaultWriter`
  exposes a `register_renderer(tool_name, renderer)` method; children
  register their own renderers at framework startup. The seed dict
  in `VaultWriter.__init__` ships empty by default. The three
  `render_run_note` / `render_trend_note` / `render_compare_note`
  functions move into `children/running/` as part of running's
  example-package self-containment.
- **Domain inference is per-child-declared.** The
  `_domain_for_kind` map in `framework/vault/layer.py` and the
  filesystem-layout heuristics in `framework/vault/rescan.py`
  consult a registration surface that each child populates with the
  `(kind → domain)` and `(filename-pattern → domain)` claims it
  owns. Running's claims move with the example; the framework keeps
  the registration mechanism.
- **`vault_get_fitness_summary` either becomes generic or moves to
  the example.** The chosen shape is the boss's call at v7.0.0
  scoping time. Two viable shapes, both compatible with this ADR: a
  generic `vault_get_domain_summary(domain: str)` framework tool
  that takes the domain as a parameter, or a running-example tool
  living in `children/running/` that the example registers when
  loaded. The decision belongs in v7.0.0 scoping, not in this ADR.
- **`framework/vault/` carries no string literals naming any specific
  child.** A grep of `framework/vault/` for `strava_` or
  `domain="running"` after v7.0.0 returns zero results. This is the
  observable invariant a future contributor checks to verify
  *"did the decouple cycle finish?"* without re-reading the ADRs.
- **The audit row schema and `_meta` provenance contracts are
  unchanged.** [ADR 0001](0001-audit-log-as-backbone.md) and
  [ADR 0009](0009-vault-subject-keying.md) bind the framework's
  durability and reproducibility claims to fields that already
  treat `domain` as an opaque string. The decouple cycle does not
  reshape those contracts; it removes the framework's accidental
  knowledge of one domain's value.

Concrete cycle shape:

- **v7.0.0 — decouple-prep cycle.** No researcher-visible feature
  work. The four coupling sites listed in Context are decoupled,
  the renderer-registration API ships, the domain-inference
  registration surface ships, the `vault_get_fitness_summary`
  reshape lands in whichever of the two shapes the boss picks,
  and a synthetic `ChildMCP` replacement covers the integration-test
  surface running's tests currently carry per
  [ADR 0014](0014-coverage-criticality-invariant.md)'s HIGH-region
  rule on `framework/vault/layer.py`.
- **v8.0.0 — `git mv children/running/ → examples/`.** The mv ships
  only after v7.0.0's invariants hold. Running keeps its tests, its
  twelve tools, and its own renderer registration. The
  `__main__.py` `cmd_serve` registration site for running becomes
  optional — running registers if its config is present, the
  framework runs without it otherwise.
- **No PR-level pre-commitment.** The architectural commitment is
  *"framework must become honestly domain-agnostic in v7.0.0."*
  PR sequencing inside that cycle is implementation detail and
  belongs to the main session and the relevant specialists at
  scope time.

This ADR's promotion grounding cites
[ADR 0011](0011-promotion-policy.md). The structural argument is
that ADR 0011's bar — "structural argument plus severity grounding
plus per-agent maintenance estimate" — applies symmetrically to the
*removal* of major framework components, not only to the addition of
specialists. The severity grounding is that future child authors
(CGM, sleep, ECG, EDF, FHIR) re-discover the same coupling and ship
ad-hoc workarounds; each workaround compounds the
[CLAUDE.md § What This Project Is](../../CLAUDE.md#what-this-project-is)
framing-vs-code drift. The per-cycle maintenance estimate is one
release cycle of researcher-non-visible plumbing; the value is one
honest framing of what the framework is.

This ADR also extends [ADR 0007](0007-rendering-layers-policy.md)'s
separation-of-concerns logic to renderer dispatch. ADR 0007 ruled
that the source-of-truth markdown is plain and AI-readable, with
plugin-enhanced views additive. The same separation principle
applies one level up: the framework owns the dispatch mechanism,
children own the renderer content. ADR 0007 governs *what* a
rendered note looks like; this ADR governs *who registers the
renderer*.

This ADR's filing went through `adr-weigher`
([ADR 0017](0017-adr-weigher-and-autonomous-session-cap.md)) and
returned `PASS`. The weigher's caveat noted the ADR 0007 cite
needed phrasing as *"extends 0007's separation-of-concerns logic"*
rather than direct application — the Decision section above carries
that phrasing.

Reversal condition: if v8.0.0's `git mv` is abandoned and the
project re-frames as fitness-research-with-CSV-side-door (Branch 2
in the synthesis below), this ADR is superseded.
[CLAUDE.md § What This Project Is](../../CLAUDE.md#what-this-project-is)
is rewritten in the same change to drop the health-data-analysis
framing and name running as the canonical domain, with CGM / sleep /
ECG / EDF / FHIR explicitly removed from the project's stated
audience. The escape hatch is named here so future contributors know
which doc surface moves if the architectural commitment is
reversed; silent reversal — keeping CLAUDE.md's framing while
abandoning the decouple — is the failure mode this clause exists to
prevent.

## Consequences

**Positive.**

- The CLAUDE.md framing matches the code. A reviewer who reads
  *"the running child is one worked example of the ChildMCP
  pattern... it is not the canonical use case"* and then greps
  `framework/vault/` for `strava_` finds zero results, instead of
  finding a renderer dispatch table named after the example.
- Future child authors (CGM, sleep, ECG, EDF, FHIR) get a clean
  extension surface. A new child registers its own renderers and
  domain claims at startup, and the framework's vault layer
  orchestrates without knowing which child is registered. The
  copyable-template promise of `children/template/` becomes
  honest at the framework boundary.
- `researcher-utility-reviewer`'s three personas (PI, analyst/RSE,
  IRB reviewer) get an honest answer to *"what domain does this
  framework cover?"* The current answer is "fitness research with
  a CSV side door"; the post-v8.0.0 answer is "health data
  analysis with running as the worked-example child." The first
  answer narrows the project's stated audience; the second matches
  it.
- `vault_get_fitness_summary`'s reshape removes the framework's
  most visible domain-narrowing tool. Whichever of the two shapes
  the v7.0.0 cycle picks, the post-cycle framework no longer has a
  Tier-1 tool whose name implies a specific health-data sub-domain.
- The escape hatch is named in the reversal condition. If the
  project decides at v7.0.0 scoping that the cycle is too costly
  and Branch 2 (embrace the coupling, narrow the framing) is the
  right call, the doc surface that moves is enumerated here. Branch
  2 is not lost — it is named, scoped, and conditioned on a
  superseding ADR that rewrites CLAUDE.md in the same change.

**Negative.**

- One full version cycle (v7.0.0) ships with no new researcher-
  visible features. The `researcher-utility-reviewer` will likely
  return `NEUTRAL` or `RESEARCHER-NOISE` on the cycle as a whole —
  the cycle's value is structural, not researcher-facing. This is
  the cost the ADR makes explicit; a release cycle on plumbing is
  the price of making the framing honest, and the alternative
  (Branch 3 — defer) costs more by accumulating coupling.
- Engineering time during v7.0.0 goes to four named coupling sites
  and one synthetic-child replacement. No new analytical tools, no
  new vault features, no new compliance backstops ship in that
  cycle. Boss-facing reports during v7.0.0 will read as engineering
  hygiene rather than research utility, and the
  `boss-report-auditor` second-translator pass per
  [ADR 0010](0010-adversarial-pairing.md) catches any drift toward
  marketing the cycle as researcher utility.
- v8.0.0's `git mv` is a load-bearing breaking change for any
  external repo that imports
  `tailor.children.running` directly. The path becomes
  `tailor.examples.running` (or equivalent). The cycle's
  release notes carry the migration path, and the project commits
  no compatibility shim — the rename is the load-bearing signal
  that running is an example, and a shim would re-create the
  framing-vs-code gap this ADR exists to close.

**Neutral.**

- Existing v6.x running notes in users' vaults continue to render
  correctly. v8.0.0 ships running-as-example with its own renderer
  registration; the markdown frontmatter and filenames are
  unchanged; `vault_rescan` continues to revalidate the same notes
  against the same SQLite index. No markdown-rewrite migration is
  required for users.
- The `framework/security.py` PHI-scrubbing seam per
  [ADR 0003](0003-phi-scrubber-seam.md) is unchanged. Running's
  GPS coarsening (currently in `children/running/processing.py`)
  remains where it is; under the post-v8.0.0 shape, a future
  `SafeHarborScrubber` subclass per [ADR 0003](0003-phi-scrubber-seam.md)
  is the natural home for cross-domain PHI policy, and the
  example's local coarsening is one citation against that subclass.
  This ADR does not pre-commit to that subclass; it names the
  natural downstream resolution.
- The audit log per
  [ADR 0001](0001-audit-log-as-backbone.md) and the `subject_id`
  propagation per [ADR 0009](0009-vault-subject-keying.md) are
  unchanged. Both treat `domain` as an opaque string already; the
  decouple cycle removes the framework's *other* code paths that
  do not.
- The criticality map in
  [ADR 0014](0014-coverage-criticality-invariant.md) is unchanged.
  `framework/vault/layer.py` remains HIGH; the decouple work
  cannot ship CRITICAL or HIGH coverage regressions, and the
  synthetic-child replacement for running's integration-test
  coverage is part of v7.0.0 scope precisely because of that
  rule.

## Alternatives considered

**Branch 2 — embrace the coupling, rewrite the framing.** The
project re-frames as fitness-research-with-CSV-side-door. Running
becomes the canonical domain; the CSV directory child is named as
a side door for cohort questions; CGM, sleep, ECG, EDF, and FHIR
roadmap items either drop or become explicitly vault-bypassing.
[CLAUDE.md § What This Project Is](../../CLAUDE.md#what-this-project-is)
is rewritten to drop the health-data-analysis framing. Rejected
because it abandons the project's stated audience — health
researchers at academic medical centers per CLAUDE.md's "What This
Project Is" — in favour of a narrower thing the substrate
accidentally became. The framing has been the load-bearing claim
since the v6.x banner sequence; abandoning it for code-shape
convenience is the wrong direction. The escape hatch remains named
in this ADR's reversal condition for the case where a future
session concludes that v7.0.0's cost outweighs the framing
commitment, but this ADR's filing is the bet that the framing is
worth honoring.

**Branch 3 — doc-reframe-only as interim, defer the structural
call.** Roughly two hours of CLAUDE.md edits would re-soften the
framing ("the running implementation is one current focus, with
generalization deferred") without any code change. The four
coupling sites stay where they are; the framework continues to
ship with `strava_*` keys hardcoded into its renderer dispatch.
Rejected because it kicks the same decision into a future session
under worse conditions. Each cycle that ships with the coupling
intact accumulates more code that depends on the running-named
surface (each new release banner, each new CSV cohort tool that
quotes `csv_*` patterns alongside `strava_*` patterns, each new
vault tool that special-cases "fitness"). The decouple gets harder
each cycle, not easier. Branch 3 is the choice that produces a
project whose framing the code never honors and whose CLAUDE.md
gets rewritten every six months to match the latest accretion.

**Direct `git mv` without a prep cycle.** The fastest shape — one
PR, one cycle, one banner. The `integration-auditor` returned
`REVISE` on this exact proposal with thirteen blocking items and
five silent regressions: `vault_get_fitness_summary` returns empty
forever (its hardcoded `domain="running"` query finds no rows
under the new layout), `vault_backfill` no-ops silently (its
`backfill_config` contract assumes the running tool names are
registered), `vault_get_snapshot`'s weekly summary block goes
blank, the running child's contract tests `ImportError` from their
old import paths, and the `tailor demo` subcommand
`ImportError`s the same way. Rejected as architecturally dishonest
— it pretends the coupling does not exist, ships five silent
regressions to users to make a point about framing, and forces the
project to either roll back to v6.x or paper over the regressions
with hot-fixes that re-create the coupling under different names.
The decouple cycle (v7.0.0) and the rename cycle (v8.0.0) are two
separate releases for a structural reason: the first establishes
the invariants the second relies on. Collapsing them ships the
rename without the invariants and recreates the integration-auditor
findings as runtime bugs in users' deployments.

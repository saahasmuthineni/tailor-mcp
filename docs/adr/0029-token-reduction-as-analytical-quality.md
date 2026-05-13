# ADR 0029: Token reduction is analytical quality, not just cost optimization; the demo demonstrates the architecture, not only the cohort thesis

- **Status:** Accepted (flipped from Proposed on 2026-05-08 when v6.12.0 shipped)
- **Amended:** 2026-05-12 — § AI economics as umbrella claim
- **Date:** 2026-05-07
- **Partially supersedes:** [ADR 0027 (Demo as researcher first-look)](0027-demo-as-researcher-first-look.md) — § Negative consequences "the demo bypasses RouterMCP by design" (lines 174-193) and the framing-prose contract that names `_meta` in prose because the demo doesn't exercise the router. ADR 0027's central claim — cohort thesis as canonical first-look, no Strava data — is preserved.
- **Related:** [ADR 0001 (Audit log is the backbone)](0001-audit-log-as-backbone.md), [ADR 0005 (Cost pre-estimation)](0005-cost-pre-estimation.md), [ADR 0008 (Deterministic-by-construction processing)](0008-deterministic-by-construction-processing.md), [ADR 0015 (Tier-1 cohort surface)](0015-tier-1-cohort-surface-and-metadata-sidecar.md), [ADR 0022 (Local-LLM guardian)](0022-local-llm-guardian.md), [ADR 0023 (Local-LLM cooperation loop)](0023-local-llm-cooperation-loop.md), [ADR 0028 (Recipient-install validation)](0028-recipient-install-validation-as-release-gate.md), [CLAUDE.md § Three-Tier Access Model](../../CLAUDE.md#three-tier-access-model)

## Context

[ADR 0027](0027-demo-as-researcher-first-look.md) reshaped
`tailor demo` from synthetic-Strava operator self-verification
into a researcher first-look against the bundled HIP Lab realistic
cohort fixtures. The reframe was correct on its central claim — the
cohort-comparison thesis is the canonical use case CLAUDE.md names —
and it shipped in v6.10.5 with the implementation now at
[`demo/runner.py`](../../src/tailor/demo/runner.py). The demo's
output is two `csv_cohort_summary` calls and one `csv_force_decline`
call against `S001_force.csv`, framed by closing prose that names
ADR 0001 / 0003 / 0004 / 0005 as *"what this demo does NOT exercise."*

That framing is honest about its scope and structurally incomplete on
its own terms. The demo demonstrates *one* of the framework's
load-bearing claims — that deterministic Tier-1 processing answers
cohort questions without raw streams entering the LLM context — and
deliberately bypasses the rest. The router pipeline, the three-tier
access model, the vault layer, and the local-LLM guardian
([ADRs 0001](0001-audit-log-as-backbone.md) /
[0005](0005-cost-pre-estimation.md) /
[0022](0022-local-llm-guardian.md) /
[0023](0023-local-llm-cooperation-loop.md)) are visible only by
running `tailor tour` and exercising tool inputs through Claude
Desktop. A PI or RSE running `tailor demo` cold sees the cohort
thesis but does not see the architectural depth that makes the cohort
thesis trustworthy in a research-software context.

The deeper structural observation that motivates this ADR: **token
reduction is the load-bearing claim, and the cohort thesis is one
expression of it.** The framework's three-tier access model (CLAUDE.md
§ "Three-Tier Access Model") describes token counts of 200–1,500 at
Tier 1, 3,000–7,000 at Tier 2, and 25,000–60,000 at Tier 3 on the
running-child worked example. The conventional reading is that token
reduction is cost optimization — fewer tokens means cheaper API calls.
That reading sells the architecture short. Token reduction has
*analytical-quality* consequences distinct from cost:

1. **Pre-computed numbers eliminate a class of LLM hallucination.**
   When `csv_cohort_summary` returns means and standard deviations
   grouped by sex, the numbers come from
   [`CSVProcessing.cohort_stats`](../../src/tailor/children/csv_dir/processing.py)
   — a `@staticmethod` pure function under the
   [ADR 0008](0008-deterministic-by-construction-processing.md)
   determinism invariant. They are correct by construction. An LLM
   asked to compute *"mean peak by sex"* from 16 raw force CSVs would
   either fabricate plausible-but-wrong numbers, get the arithmetic
   wrong on the long-context input, or refuse. Tier 1 makes the answer
   trustworthy in a way Tier 3 structurally cannot.
2. **Context-window concentration lets the LLM actually reason.** A
   60-minute per-second running stream collapses from ~60,000 tokens
   of raw heart-rate / pace / GPS samples (Tier 3 in CLAUDE.md's
   running-child table) into ~800 tokens of structured numerical
   claims via `strava_run_report` (Tier 1). The "lost in the middle"
   attention-degradation pattern on long inputs is documented in the
   long-context-LLM literature; a model holding 800 tokens of dense
   structured numbers can synthesize across them in a way the same
   model staring at 60,000 tokens of raw HR cannot.
3. **Reproducibility cascades from determinism.** ADR 0001
   (audit-log backbone) and ADR 0008 (deterministic-by-construction)
   compose into a specific property: an analytical claim that ends up
   in a paper can be re-derived by re-running the same tool with the
   same params. That property holds *because* the numbers came from
   pure functions, not from an LLM looking at a stream. Token
   reduction is the structural prerequisite for citable provenance.
4. **Local-LLM cooperation is architecturally possible only because
   of token reduction.** ADR 0022's hallucination-prevention invariant
   (*numbers come from `processing.py`, prose comes from the local
   LLM*) works because the local-LLM tier (1B–14B parameter models)
   has a much smaller context window than hosted Claude. If the
   cohort surface emitted full streams, the local oracle could not
   fit them. Token reduction is what lets the
   [ADR 0022](0022-local-llm-guardian.md) framing-claim — *no
   biometric streams ever leave the analyst's machine* — hold under
   opt-in.
5. **The cost gate's `has_cheaper_alternative` is analytical
   guidance, not just billing.** ADR 0005's pre-estimation contract
   carries a `has_cheaper_alternative` field
   ([`framework/interfaces.py:50`](../../src/tailor/framework/interfaces.py))
   populated by every Tier-3 child estimator with descriptions like
   *"csv_downsampled (every 5th row) — preserves trends, ~80% cheaper"*
   ([`children/csv_dir/child.py:466-469`](../../src/tailor/children/csv_dir/child.py)).
   That string is **the framework teaching the LLM what resolution
   actually answers what question.** Drift detection does not need
   per-second resolution. The cost gate is a
   resolution-appropriateness signal embedded in the architecture, not
   only a token meter.

A demo whose output demonstrates only consequence (3) — and only the
deterministic-numerics half of (3) — leaves the other four invisible
at first look. The first impression a recipient forms about *what
this framework is for* is shaped by what `tailor demo` shows.
Per ADR 0027 itself: *"the first impression a recipient forms about
what this tool does is load-bearing."*

The question this ADR answers: *given that token reduction is the
load-bearing claim and the demo is the recipient's first-look surface,
what reshapes `tailor demo` to demonstrate the architecture
without losing ADR 0027's correct insistence that the cohort thesis
leads?*

## Decision

`tailor demo` is reshaped to demonstrate the framework's
load-bearing claims via five structured sections, all against the
bundled HIP Lab realistic fixtures. Section 1 (the cohort thesis) is
the canonical lead-in; Sections 2 through 5 demonstrate, in order, the
router pipeline made visible, a three-tier resolution-appropriateness
walk on the same question, the vault as the second persistence tier,
and the local-LLM oracle with `NullBackend`. ADR 0027's
first-impression-shaping concern is preserved — the cohort thesis is
what the recipient sees first — and the demo additionally exercises
the architecture that makes the cohort thesis trustworthy.

The rule, plain English: token reduction *is* analytical quality, and
the demo is the recipient's first-look at what that means. Section 1
shows the cohort answer; Sections 2–5 show why the framework is
shaped the way it is — provenance on the wire, resolution gates that
guide rather than meter, durable cross-session memory, and a local
oracle whose feasibility ground is the same token budget the cohort
tools enforce.

Concrete mechanism:

- **Section 1 — cohort thesis (ADR 0027 preserved).** Two
  `csv_cohort_summary` calls (peak force grouped by `sex`, peak force
  grouped by `group`) and one `csv_force_decline` on `S001_force.csv`,
  the same shape `demo/runner.py` ships in v6.10.5. The output is the
  result envelope `CSVDirectoryChild.execute()` returns. The framing
  prose makes the cohort-thesis claim explicit: *"these numbers came
  from a pure function over the bundled CSVs; the raw streams were
  never tokenised."*
- **Section 2 — router pipeline made visible.** The same
  `csv_cohort_summary(group_by="sex")` call from Section 1 is
  re-issued through a `RouterMCP` instance constructed for the demo.
  The printed output is the full router envelope including the
  `_meta` block stamped per ADR 0001 (`package_version`, `tool_name`,
  `called_at`, `domain`, `tier`, `scrubber_id`, per-call and session
  token counts) and the `audit.db` row id the audit-log backbone
  wrote synchronously before the result returned. Framing prose names
  what the recipient is looking at: *"the same numbers, now with the
  provenance every Claude Desktop tool call carries."*
- **Section 3 — three-tier resolution-appropriateness walk.** The
  same analytical question (*"how does S001's force trace decline
  over the trial?"*) is answered three ways: Tier 1 via
  `csv_force_decline` (~200 tokens, peak / decline % / time-to-50%),
  Tier 2 via `csv_downsampled` at every-5th-row decimation (~5,000
  tokens, curve shape preserved), and Tier 3 via `csv_raw_stream`
  with cost-gate refusal. The Tier-3 call trips the cost gate cleanly
  and the printed output is the `LLMInstruction` envelope per
  [ADR 0004](0004-structured-llm-instruction.md), including the
  `has_cheaper_alternative` cheaper-alternative description from
  [`children/csv_dir/child.py:466-469`](../../src/tailor/children/csv_dir/child.py).
  Framing prose names the load-bearing observation: *"the cost gate
  is the framework telling the LLM what resolution actually answers
  this question. Drift detection does not need per-second resolution."*
- **Section 4 — vault as durable memory.** A `VaultLayer` is wired
  with a tempdir vault path, the post-execute writer hook is
  registered (only at this section, not earlier), and a moment is
  captured via `vault_capture_moment` scoped to `subject_id="S001"`.
  The runner reads the resulting markdown file off disk and prints
  it inline so the recipient sees the source-of-truth markdown
  directly (the SQLite vault index that future `vault_search_notes`
  / `vault_list_notes` calls would query is populated as a side
  effect of the same write but not surfaced in this demo's output —
  Section 5's substrate scan is what exercises the index path
  recipient-visibly). The framing prose names the second persistence tier (CLAUDE.md § "Two
  persistence tiers, architecturally distinct") and the markdown
  source-of-truth contract from [ADR 0007](0007-rendering-layers-policy.md):
  *"`activities.db` is rebuildable; `vault/*.md` is the canonical
  record. The same data the LLM accesses through vault tools is
  visible to the analyst in Obsidian."*
- **Section 5 — local-LLM oracle with NullBackend.** A
  `LocalLLMLayer` is wired with `NullBackend` and the vault storage
  injected per ADR 0023. An `ask_local_oracle` call is issued scoped
  to `subject_id="S001"` with the Section 1 cohort-summary result as
  `resolved_context`. The printed `OracleResponse` shows
  `numerical_claims` (extracted from the resolved context, not
  composed by an LLM), `narrative=""` (NullBackend default), and
  `related_substrate` populated with the moment captured in
  Section 4. The framing prose names ADR 0022 / ADR 0023's
  feasibility ground: *"the local oracle's token budget is what
  cohort summaries fit inside; raw streams would not."*

### Implementation key facts

The following resolutions land with the implementation; they are
recorded here because each closes a defect surfaced during the
proposal-mode audit and would otherwise erode on next refactor.

- **Cost gate threshold tuning.** The demo's `RouterMCP` instance is
  constructed with `cost_threshold=15_000`. Production at
  [`__main__.py:58`](../../src/tailor/__main__.py) uses
  35,000 per ADR 0005. S001's raw stream estimates at ~24,000 tokens
  — at the production threshold it falls through silently; at the
  demo threshold it trips the gate cleanly so the recipient sees the
  cost-gate envelope and the cheaper-alternative suggestion. Framing
  prose names the threshold difference explicitly so the recipient
  understands the demo is calibrated for visibility, not rigged.
- **Vault writer hook ordering.** The post-execute writer hook is
  registered only at Section 4 (vault demonstration), not at
  Section 2 (router pipeline visible). Section 2's printed envelope
  is the clean router shape, not a writer-touched one. Order is
  load-bearing for the recipient's mental model.
- **`subject_id` threading.** All Section 4 and Section 5 calls
  thread `subject_id="S001"` so
  [`LocalLLMLayer._scan_related_substrate`](../../src/tailor/framework/local_llm/layer.py)
  finds the moment captured in Section 4 via the SQLite query under
  ADR 0009's IS-NULL-or-match filter. Without this, NullBackend
  returns `related_substrate=[]` and the headline beat in Section 5
  lands empty.
- **Windows tempdir cleanup.** A `try/finally` block closes the
  router, the vault writer, the child, and the local-LLM-layer
  storage before `tempfile.TemporaryDirectory` exits. This is the
  recipient-failure pattern the v6.10.x quartet repeatedly produced
  (see [ADR 0028](0028-recipient-install-validation-as-release-gate.md)
  § Context for the failure history); the demo cannot ship without
  it. SQLite WAL connections must be explicitly closed before
  process exit on Windows or the tempdir cleanup raises a
  `PermissionError` (CLAUDE.md § "Implementation notes" names the
  same constraint for `router.close()` in tests).
- **Reproducibility-claim scoping.** The closing prose's
  *"re-run for bit-identical numbers"* claim is scoped to
  **Section 1 cohort numbers only**. `_meta.called_at`, audit-log
  row ids, `oracle_latency_ms`, and SQLite row ids do change across
  runs — that is expected behaviour, not regression. The framing
  distinguishes *deterministic numerics* (ADR 0008 invariant) from
  *provenance metadata that timestamps each call* (ADR 0001
  audit-row contract). Conflating them would either weaken the
  reproducibility claim or invite a false-positive regression report
  from a recipient who diffs two demo runs and sees timestamps
  differ.

### Reversal condition

If recipient-feedback evidence shows the longer demo plants *"this is
a complicated framework"* instead of *"this has a clear analytical
thesis with deep architectural support,"* the demo reshapes back
toward Section-1-only with Sections 2–5 moved to a separate
`tailor showcase` subcommand. ADR 0027 § Alternatives rejected
the two-demo-subcommand split on *"which is canonical?"* grounds; that
rejection holds *unless* the unified demo demonstrably damages
first-impression formation. The reversal condition is the named
escape hatch, not an active concern at draft time — Status: Proposed
acknowledges that the evidence supporting it does not yet exist.

### Status pathway

`Status: Proposed` at draft time. Flips to `Accepted` when v6.12.0
ships with the reshaped demo and the
[`recipient-install-validator`](../../.claude/agents/recipient-install-validator.md)
in-guest Step 6 assertion list updates to cover the five-section
demo output (per the agent's boss-authorization clause for assertion-
list updates). The reversal condition references recipient-feedback
evidence that does not yet exist; Proposed is the honest status
pending that evidence.

## Amendment 2026-05-12 — AI economics as umbrella claim

This ADR's original framing — *token reduction is analytical
quality, not just cost optimization* — was correct as far as it
went and structurally incomplete on its own terms. The "not just"
clause preserved cost optimization as a real co-benefit, but the
title's emphasis on *analytical quality* alone admitted a downstream
drift: the CLAUDE.md compression of this ADR into § "Problems this
is built against" rendered it as *"Token efficiency is a useful
side effect of computing summaries server-side. It is not the
headline."* That sentence went further than this ADR did — it
demoted token efficiency from "a co-benefit alongside analytical
quality" to "side effect, not headline" — and the README hero
clause inherited the demotion downstream. The boss flagged the
drift on 2026-05-12 in a conceptual session.

The structural correction: **AI economics is the umbrella claim,
and analytical quality is one of three faces of it.** The three
faces share a single mechanism (Tier-1 server-side computation
returns the answer, not the data) and produce three distinct
properties:

1. **Analytical quality** — pre-computed numbers from
   `@staticmethod` pure functions under the ADR 0008 determinism
   invariant. Original consequence-bullet (1) above, unchanged.
2. **Cognitive amplification** — freed context window goes to
   reasoning over the analyst's prior Wardrobe, the audit log,
   and the current question, rather than to holding raw streams
   the LLM must re-aggregate. The "lost in the middle" attention
   degradation pattern on long inputs (consequence-bullet (2)
   above) restated as a *cognitive budget* property: token-per-
   question is simultaneously a cost lever and a cognition lever
   because both are bounded by the same underlying scalar.
3. **Cost-per-question** — token-per-question collapses by 1–2
   orders of magnitude on most analytical questions. For an
   academic medical center running daily analyst interactions
   against a longitudinal cohort, this is the difference between
   sustainable grant-funded usage and one-off-supplement-required
   usage. Not vendor-economics; deployment-economics.

The win compounds with the AI ecosystem rather than eroding with
cheaper models: as per-token cost falls, AI gets deployed against
larger substrates (whole codebases, whole EHRs, whole archives),
and the per-question context-budget problem gets harder, not
easier. Token reduction under the Tier-1 server-side computation
pattern is what keeps AI tractable at scale.

The umbrella naming also makes ADR 0029's claim properly
**recipe-general** rather than recipe-specific. CLAUDE.md § "What
This Project Is" already names the framework as data-agnostic and
use-case-agnostic — the cognitive amplification + cost-per-
question win is the same property whether the deployment recipe is
health research (the worked example), clinical workflows, knowledge
work over a personal archive, or creative-archive curation. The
researcher-cost framing surfaced in the boss's 2026-05-12 prompt
is the umbrella claim observed through the academic-medical-center
lens, not a separate benefit.

### Doc-truth cascade

This amendment authorizes three downstream edits, landed in the
same patch (v7.0.11):

1. **CLAUDE.md § "Problems this is built against"** — fourth named
   problem ("AI economics") added; the "Token efficiency is a
   useful side effect…not the headline" sentence deleted.
2. **README.md hero clause** — extended to lead with concrete-
   dollar framing ($200/month → $2/month) and to name the AI-
   context-budget property so the recipient's first-paragraph
   impression includes the AI-economics claim alongside data
   governance and reproducibility.
3. **`src/tailor/demo/runner.py` Section 3 framing prose +
   closing summary** — *"analytical quality, not just billing"*
   sharpened to *"analytical quality AND AI economics — the same
   lever from two angles."* The Section 3 token-count printouts
   (already shipped in v6.12.0) are the visible math behind the
   umbrella claim.

### Reversal condition (amendment)

If recipient feedback shows the AI-economics framing makes the
project sound *vendor-economics-shaped* or *cost-optimization-
shaped* to a research audience (the original reason the framing
was demoted), the umbrella claim retreats and analytical quality
returns to the lead. The reversal condition is the named escape
hatch and does not yet apply — the demotion was the wrong
correction, but a future overcorrection in the opposite direction
is the symmetric risk this clause guards against.

## Consequences

### Positive

- **Token reduction is realised by feature, not by argument.** The
  case for the three-tier model becomes load-bearing in the running
  demo rather than only in CLAUDE.md and ADR 0005. A recipient
  running `tailor demo` sees the cost gate doing structural
  work (resolution-appropriateness guidance) before they read a
  single ADR.
- **The architecture's depth is visible at first look without
  losing ADR 0027's lead.** Section 1 preserves the cohort thesis as
  the canonical opening; Sections 2–5 demonstrate the
  router / cost-gate / vault / local-LLM machinery the cohort thesis
  rests on. A PI's first-impression model becomes *"cohort-research
  framework with deterministic processing, citable provenance,
  resolution-appropriate access tiers, durable analytical memory,
  and a local-LLM seam"* rather than *"cohort calculator over CSVs."*
- **ADR 0001's surface becomes recipient-visible.** The audit-log
  backbone is the framework's most load-bearing single feature for
  research use; under ADR 0027 it lived only in framing prose
  ("what this demo does NOT exercise"). Under this ADR it appears
  in Section 2's printed `_meta` block and audit-row id. A recipient
  who reads ADR 0001 after running the demo recognises the surface
  rather than meeting it for the first time.
- **The IRB-relevant properties get a recipient-checkable
  demonstration.** Sections 2–5 collectively exercise the
  ADRs the framework's research-credibility claims rest on:
  ADR 0001 (audit log), ADR 0005 (cost pre-estimation), ADR 0008
  (determinism), ADR 0022 (local-LLM guardian), ADR 0023
  (cooperation loop). An IRB reviewer running the demo before
  reading the framing documents sees the architecture exercised on
  synthetic-by-construction fixtures — a verifiable demonstration,
  not a marketing claim.
- **NullBackend earns its keep visibly.** Section 5's
  NullBackend-with-substrate-scan output is the cleanest possible
  proof that ADR 0023's substrate-vision asymmetry — *the local
  layer reads the vault, hosted Claude structurally cannot* — works
  without any LLM in the loop. ADR 0023 § Decision § Architectural
  placement names this as *"the cleanest possible proof that the
  scan belongs to the layer and not to the backend"*; the demo now
  shows it.

### Negative

- **The demo grows from ~3 calls / ~80 lines of framing prose to
  ~10 calls across 5 sections** (Section 1: 3 child-direct calls;
  Section 2: 1 router call + audit-row tail-print; Section 3: 4
  router calls including the consent-blocked retry pair; Section 4:
  1 router call + markdown print; Section 5: 1 router call).
  Recipient cold-run time grows from under a second to roughly 10-30
  seconds. Acceptable on absolute terms, but the longer surface
  plants more for the recipient to track.
  Mitigation: each section's framing prose opens with one sentence
  naming what it shows, so a recipient skimming output reads the
  thesis even if they skip the envelopes.
- **The cost-threshold tuning (15,000 vs production 35,000) is a
  demo-specific calibration.** A future recipient who reads
  CLAUDE.md § "Three-Tier Access Model" and then runs the demo
  could be confused by the apparent disagreement. Mitigated by
  framing prose at Section 3 naming the threshold difference
  explicitly: *"the demo lowers the cost threshold to 15,000
  tokens so the gate trips on this fixture; production deployments
  use 35,000."*
- **Section 5 depends on Section 4 having captured a moment.** If
  the vault wiring fails silently in Section 4, Section 5's
  `related_substrate` lands empty and the demo's headline beat is
  invisible. Mitigation: the implementation asserts the
  `vault_search_notes` retrieval in Section 4 succeeded before
  Section 5 issues `ask_local_oracle`; on failure it prints a
  short error and skips Section 5 with an explanatory line rather
  than emitting a misleading empty `related_substrate`.
- **The Windows tempdir cleanup pattern is more complex than the
  v6.10.5 demo.** Five distinct components (router, child, vault
  writer, local-LLM layer, vault storage) need explicit close
  ordering. A future maintainer who adds a sixth component to the
  demo and forgets to add it to the `try/finally` block produces
  a Windows-only `PermissionError` on tempdir cleanup. Mitigated
  by a regression test that asserts a clean tempdir cleanup on
  Windows (the
  [`recipient-install-validator`](../../.claude/agents/recipient-install-validator.md)
  in-guest Step 6 also exercises the cleanup path on Win 11).
- **`Status: Proposed` ships in production output.** Until v6.12.0
  ships and the reversal condition is judged unmet, the ADR's
  Status sits visible in `docs/adr/0029-...md`. A reader who only
  scans Status flags could read this as undecided. Mitigated by the
  Status-pathway block above and by the reversal-condition prose
  naming the specific evidence that would flip status either way.

### Neutral

- **ADR 0027's central claim is preserved, not reversed.** The
  cohort thesis as canonical first-look stands; the no-Strava-in-
  demo invariant stands; the bundled HIP Lab realistic fixtures
  remain the demo's data source. What changes is the demo's
  surface area, not its lead.
- **ADR 0008's determinism boundary is unchanged.** The demo
  sections that exercise non-deterministic surfaces (audit-row
  timestamps in Section 2, oracle latency in Section 5) are
  outside the processing layer. The reproducibility-claim scoping
  in § Implementation key facts makes the boundary explicit rather
  than amending it.
- **`demo/sample_data.py` remains untouched.** ADR 0008
  § Alternatives explicitly rejected removing the synthetic-Strava
  PRNG; ADR 0027 preserved the module under that rejection; this
  ADR inherits the preservation. The module remains importable
  from `tailor.demo.sample_data` for the test at
  [`tests/framework/test_router.py:1054`](../../tests/framework/test_router.py)
  and the worked-example notebook.
- **The recipient-install-validator's in-guest assertion list
  updates in the same patch.** Per
  [ADR 0028](0028-recipient-install-validation-as-release-gate.md)
  § Decision the validator's Step 6 exercises `tailor demo`;
  the assertion list extends to cover the five-section output
  shape. The agent's boss-authorization clause for assertion-list
  updates ([`recipient-install-validator.md:22 / :111 / :174`](../../.claude/agents/recipient-install-validator.md))
  is the mechanism — no separate ADR for the assertion update.
- **The `docs/assets/demo.svg` orphan named in
  [ADR 0027](0027-demo-as-researcher-first-look.md) §
  Negative consequences was removed in the v6.12.x cleanup pass.**
  That asset depicted the pre-v6.10.5 Strava-shaped demo, was not
  embedded anywhere, and was on no recipient first-look path. The
  cleanup took the "remove the orphan" branch of ADR 0027's named
  fork; replacement with a HIP Lab cohort visualization remains an
  open creative item, separate from the v6.12.0 reshape.

## Alternatives considered

**Keep `tailor demo` Section-1-only; add a separate
`tailor showcase` subcommand for Sections 2–5.** Considered
seriously. Two subcommands let each surface optimise for one job —
demo for cohort first-look, showcase for architectural depth — and
preserves ADR 0027's framing exactly. Rejected on the same grounds
ADR 0027 § Alternatives rejected the parallel `demo` / `demo-csv`
split: two surfaces force the recipient to know which one to run,
and *"which is canonical?"* is the question the single-demo answer
eliminates. ADR 0027's concern about first-impression formation is
honoured by Section 1's lead position, not by hiding the
architecture behind a second subcommand the recipient may never
discover. Named explicitly in the reversal condition above as the
escape hatch if recipient-feedback evidence flips the trade.

**Add Sections 2–5 as opt-in flags on the existing demo (e.g.
`--show-router`, `--show-vault`).** Considered. Flag-driven surface
preserves the v6.10.5 default exactly while admitting the deeper
demonstration for recipients who want it. Rejected on
discoverability grounds: a recipient running `tailor demo`
cold for the first time does not know which flags exist or that the
deeper architecture is available. The first-look surface is by
definition the surface a recipient sees without flag knowledge; if
the architecture matters, it has to be visible at default. The
flag-driven shape is the wrong mechanism for a load-bearing
demonstration.

**Keep the v6.10.5 demo as-is and add the architectural
demonstrations to `tailor tour` instead.** Considered. Tour
already scaffolds durable state and registers with Claude Desktop;
extending it to print router envelopes and oracle responses inline
would put the architecture demonstration on the durable-install path.
Rejected on idempotency-contract grounds. Tour's job per
[ADR 0024](0024-wheel-distributed-tour-and-fixture-bundling.md) is to
scaffold the recipient's filesystem and register with Claude
Desktop, not to print analytical output. Conflating the two would
make tour heavier and demo lighter — the opposite of where their
respective recipient-perspective jobs sit. Demo runs in a tempdir and
prints; tour writes to the recipient's home and registers. Different
idempotency contracts, different audiences, different costs.

**Spawn a real Claude Desktop subprocess inside the demo and
execute the prompts end-to-end.** Considered. A real-Claude-in-the-
loop demo would exercise the prose-to-schema inference layer the
[`cue-card-rehearsal-auditor`](../../.claude/agents/cue-card-rehearsal-auditor.md)
already gates on, and would produce the most realistic possible
recipient experience. Rejected on the same grounds ADR 0025 §
Alternatives rejected the parallel proposal: a release artifact
that *requires* a hosted-LLM round-trip contradicts the framing
claim in ADRs 0022 and 0023 that hosted LLMs are the wrong home for
participant biometric data. The demo is the artifact through which
that claim is communicated; coupling it to a hosted-LLM dependency
the framework deliberately avoids would undercut the demo's own
thesis. The five-section structure with `NullBackend` preserves the
local-first posture and demonstrates the architecture without the
hosted-LLM round-trip.

**Drop Section 5 (local-LLM oracle) for v1; add it later.**
Considered. Section 5 is the most architecturally novel of the
five and depends on Section 4's vault wiring; landing the four-
section demo first would simplify the v6.12.0 implementation and
defer the local-LLM-tier demonstration to v6.13.x. Rejected because
Section 5 is the load-bearing demonstration of why ADR 0022's
framing claim — *no biometric streams ever leave the analyst's
machine* — has architectural ground. NullBackend with the substrate
scan is the cleanest possible proof of the asymmetry argument; a
demo that elides it leaves the local-LLM seam invisible at first
look. The implementation cost of Section 5 is bounded — the
NullBackend contract is already shipped, the vault scan is already
shipped, and the demo's job is to wire them together once. The
deferral would save implementation hours at the cost of making the
demo's most architecturally distinctive section invisible until a
later release.

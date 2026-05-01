# ADR 0022: Local LLM is framework-tier infrastructure; numbers come from deterministic processing, prose comes from the local LLM

- **Status:** Proposed
- **Date:** 2026-05-01
- **Related:** [ADR 0003 (PHI scrubber as seam)](0003-phi-scrubber-seam.md), [ADR 0005 (Cost pre-estimation)](0005-cost-pre-estimation.md), [ADR 0007 (Rendering-layers policy)](0007-rendering-layers-policy.md), [ADR 0008 (Deterministic by construction)](0008-deterministic-by-construction-processing.md), [ADR 0010 (Adversarial pairing)](0010-adversarial-pairing.md), [ADR 0014 (Coverage criticality invariant)](0014-coverage-criticality-invariant.md), [ADR 0015 (Tier-1 cohort surface)](0015-tier-1-cohort-surface-and-metadata-sidecar.md), [CLAUDE.md § Architecture](../../CLAUDE.md#architecture)

## Context

The framework's pitch is *behavioural rules live server-side, not in the
LLM* (CLAUDE.md § Architecture). Tier-1 server-computed reports
([ADR 0015](0015-tier-1-cohort-surface-and-metadata-sidecar.md)),
deterministic-by-construction processing ([ADR 0008](0008-deterministic-by-construction-processing.md)),
and the audit-log backbone ([ADR 0001](0001-audit-log-as-backbone.md))
are the structural responses to that pitch on the data side. On the
*reasoning* side — the LLM that composes natural-language analysis over
those server-computed numbers — there is currently no architectural
seam at all. The framework hands deterministic outputs to whatever
hosted LLM the analyst has connected via MCP, and trusts the LLM to
neither fabricate citable numbers nor drift the framing of an
ambiguous research question into a single confident answer.

That trust is structurally weak in two directions. First, hosted LLMs
have a documented failure mode of producing fluent prose that grounds
nominally on a tool result but invents adjacent numerical claims the
tool did not return ("the male cohort's mean was 247 N, *roughly 18%
higher than female*" — when the tool returned per-group means but no
between-group ratio). The framework's `_meta` provenance stamps the
tool call but not the prose composed over the result. Second, the
framework's privacy claim is currently *no biometric streams enter the
LLM context at Tier 1* — true on the wire, but the qualifier *at Tier
1* is doing real work. Tier-2 and Tier-3 calls do send streams to the
hosted LLM, and an institution whose IRB or DUA forbids any raw
biometric data leaving institutional infrastructure has no path to
those tiers under the current architecture.

A local LLM running on the analyst's machine addresses both. The
fabrication failure is reduced if the LLM that composes the narrative
is structurally constrained to compose over an already-resolved tool
result, with a typed contract separating citable numbers from
non-citable prose. The privacy claim strengthens from *no streams
enter the LLM context at Tier 1* to *no streams leave the analyst's
machine, ever, at any tier — including to hosted LLMs* — provided the
local LLM mediates the tool-call surface. Both moves are
architectural, not implementation: they reshape where the reasoning
boundary sits relative to the wire boundary.

The question this ADR answers: *what is the smallest framework-tier
seam that admits a local LLM as a guardian over the tool-call surface
without violating [ADR 0008](0008-deterministic-by-construction-processing.md),
without forcing existing deployments to install a model, and without
collapsing the citable-vs-non-citable boundary the framework's
research-credibility claims depend on?*

## Decision

A new framework-tier layer, `LocalLLMLayer`, registers with the router
parallel to `VaultLayer`. It exposes one tool, `ask_local_oracle`,
that returns a structured `OracleResponse` carrying deterministic
numerical claims composed over by an LLM-generated narrative. Ollama
is the default backend; the layer ships with a `NullBackend` so
existing deployments are behaviourally unchanged after this lands.

The rule, plain English first: *numbers come from `processing.py`,
prose comes from the local LLM, and the contract enforces the
boundary.* The local LLM never replaces a deterministic processing
function; it composes a narrative over the result of one or more such
functions. The `OracleResponse` schema separates the citable surface
(`numerical_claims`, each grounded back to a deterministic call via
`_meta`) from the non-citable surface (`narrative`, free-text and
labelled non-citable in `_meta`).

Concrete mechanism:

- **New module `framework/local_llm/`** parallel to `framework/vault/`.
  Contains `LocalLLMLayer` (the framework-tier registration object),
  the `OracleBackend` protocol, `NullBackend` and `OllamaBackend`
  implementations, and the `OracleResponse` / `NumericalClaim` /
  `OracleMeta` typed dataclasses.
- **Router registration via `register_local_llm_layer()`**, parallel
  to the existing `register_vault_layer()` (`framework/router.py:155`).
  The new layer skips the biosensor-tier gates (consent, cost, circuit
  breaker, PHI scrubber) for the same reason `VaultLayer` does today
  per [ADR 0012](0012-vault-phi-scrubber-bypass.md): the layer does
  not move participant biometric data — it composes prose over data
  the analyst has already cleared via the existing tier model. Param
  validation and audit still apply.
- **`ask_local_oracle` is the only tool the layer exposes in v0.** It
  takes a question, the resolved processing-call result(s), and the
  optional `subject_id` per [ADR 0009](0009-vault-subject-keying.md).
  It returns an `OracleResponse`. The framework — not the LLM —
  pre-resolves the deterministic processing call(s) the question
  requires and threads the resolved result into the local LLM's
  prompt. *Resolved-context tool-calling* is the load-bearing
  architectural choice: the LLM does not call tools; the framework
  calls tools and gives the LLM the resolved context to compose over.
- **The `OracleResponse` contract is typed and audited.** Fields:
  - `numerical_claims: list[NumericalClaim]` — each claim grounds back
    to a deterministic processing call via its own `_meta` field;
    numerical values come from `processing.py`, never from the LLM.
  - `narrative: str` — LLM-generated one-paragraph composition;
    explicitly labelled non-citable in `_meta`.
  - `ambiguity_axes: list[str]` — research-question disambiguation
    axes the LLM detected (empty when none); when non-empty, hosted
    Claude is required by system-prompt convention to surface the
    axis as a question to the user rather than collapse it to a
    single answer.
  - `confidence: float` — 0.0 to 1.0; below threshold (~0.4) hosted
    Claude should escalate to *consult streams directly* framing.
  - `_meta: OracleMeta` — provenance: `model_id`, `model_version_hash`,
    `tier`, `latency_ms`, `prompt_hash`, `called_at` (UTC),
    `processing_calls` (list of deterministic functions invoked).
- **New audit-log row category for oracle calls** captures
  `model_id`, `model_version_hash`, latency, confidence, tier
  (`scout` / `sentinel` / `guardian` / `titan`), and prompt hash.
  [ADR 0001](0001-audit-log-as-backbone.md)'s backbone invariant
  holds; the oracle call is one more row category alongside the
  existing tool-call and consent-handler rows.
- **Default posture is `NullBackend`**, which returns an explicit
  *local-LLM disabled* response with no narrative. Existing
  deployments after this ADR lands behave identically to deployments
  before it. Opt-in via `user_config.json`:
  ```json
  {"local_llm": {"backend": "ollama", "model": "llama3.1:8b", "tier": "guardian"}}
  ```
- **Phase 0 v0 scope.** Oracle mediation lands on **two tools only**:
  `csv_cohort_summary` and `csv_force_decline` — the cohort surface
  per [ADR 0015](0015-tier-1-cohort-surface-and-metadata-sidecar.md),
  the IRB-most-sensitive and smallest scope. The other 45 framework
  tools are unchanged in v0. Migration of the rest is incremental,
  follow-up ADRs.

### Tier table

The layer ships with four named tiers. The architectural commitment
is that *cited numerical claims are identical across tiers* (they
come from deterministic processing). What varies across tiers is
narrative quality, ambiguity-axis detection, and refusal calibration
— never the cited numbers.

| Tier | Codename | Model | RAM (loaded) | Hardware floor |
|---|---|---|---|---|
| Lite | **Scout** | `llama3.2:1b` | ~1.2 GB | 4 GB laptop |
| Conservation | **Sentinel** | `phi3.5:3.8b` | ~3 GB | 8 GB laptop |
| Balanced (default) | **Guardian** | `llama3.1:8b` | ~6 GB | 16 GB laptop |
| Power | **Titan** | `qwen2.5:14b` | ~10 GB | 32 GB workstation |

A study running on a 4 GB laptop and one running on a 32 GB workstation
get the same numbers in their reports. The narrative composition over
those numbers is more nuanced on Titan than on Scout; the
ambiguity-axis detector catches more axes on Titan than on Scout. The
framework's research-credibility surface (citable claims, audit-log
provenance) is unchanged across tiers.

### The ADR 0008 boundary

[ADR 0008](0008-deterministic-by-construction-processing.md) holds
unchanged: every method on `RunningProcessing`, `CSVProcessing`, and
`TemplateProcessing` remains a `@staticmethod` pure function with no
PRNG and no clock reads. The local LLM **never replaces** these
methods — it **calls them** via the resolved-context pattern. The
boundary this ADR draws:

- *Numbers come from `processing.py`* — citable, reproducible,
  deterministic. The same Tier-1 call with the same inputs returns
  the same numbers across machines and across LLM tiers. ADR 0008's
  invariant holds.
- *Prose comes from the local LLM* — labelled non-citable in
  `_meta.narrative_citability = false`. A future contributor reading
  the schema cannot mistake the narrative for a citable claim because
  the contract says so explicitly.
- *The `OracleResponse` contract enforces the separation by schema*,
  not by review. `numerical_claims` carry `_meta` provenance back to
  deterministic calls; `narrative` is free-text and labelled. A
  reviewer auditing whether a manuscript's number was framework-cited
  or LLM-fabricated reads the response shape, not the prose.

### Framing-claim amendment

Today's framing claim, repeated across CLAUDE.md, README.md, and
`docs/design/research-framing.md`, is *no biometric streams enter the
LLM context at Tier 1*. The qualifier *at Tier 1* exists because
Tier-2 and Tier-3 calls send streams to the hosted LLM by design. After
this ADR lands and the local-LLM layer is opted in, the claim
strengthens to *no biometric streams leave the analyst's machine,
ever, at any tier — including to hosted LLMs.* The hosted LLM sees
narrative composed over numbers, not the underlying streams.

This is a categorical strengthening of the privacy claim. CLAUDE.md
§ Architecture, README.md § Three-Tier Access Model, and
`docs/design/research-framing.md` need amendment in the same release
to surface the strengthening as conditional on the local-LLM layer
being opted in. The amendment unblocks deployments where institutional
policy forbids any raw biometric data leaving institutional
infrastructure (a real, common AMC posture).

### Three failure modes

The local-LLM-as-guardian shape introduces three named failure modes
the contract must address explicitly. Each lands as a mitigation in
the v0 implementation, not as a deferred concern.

1. **Collusion** — both LLMs (local and hosted) agree on something
   wrong; the consensus *feels* validated to the user. Mitigation:
   the local LLM verifies claims against *deterministic processing
   output*, never against hosted-LLM agreement. Agreement between the
   two LLMs is **not** validation. Only agreement between an LLM
   claim and a deterministic computation is. The
   `numerical_claims[].verified_against_processing_call` field on
   each claim records which deterministic call grounds it; an
   un-grounded claim is non-citable by construction.

2. **Confusion** — the LLMs disagree but the user lacks the technical
   context to arbitrate. Mitigation: the `ambiguity_axes` field
   translates disagreement into research-question prompts the user
   *can* answer ("are you asking about peak force or sustained force
   over the trial?"), never *which AI is right?* The hosted LLM's
   system-prompt convention requires it to surface non-empty
   `ambiguity_axes` as questions to the user rather than collapse them.

3. **Bypass** — the user pressures the system to skip the local LLM
   ("just send it to Claude, I trust them"). Mitigation:
   refusal-as-redirection. The local LLM never blocks the user's
   workflow; it offers an alternative path ("the cohort summary I can
   compose locally; if you want the full streams to Claude, that's
   Tier 2 with the consent gate"). Same architectural shape as the
   existing consent gate per
   [ADR 0004](0004-structured-llm-instruction.md): the gate produces
   a structured instruction, not a paragraph.

### Phase 0 v0 scope

- Skeleton + `NullBackend` + `OllamaBackend`.
- `ask_local_oracle` tool registered at framework tier.
- Oracle-mediation on **two tools only**: `csv_cohort_summary` and
  `csv_force_decline` — the cohort surface
  ([ADR 0015](0015-tier-1-cohort-surface-and-metadata-sidecar.md)),
  IRB-most-sensitive, smallest scope, newest tools.
- Optional posture: defaults to `NullBackend`; opt-in via
  `user_config.json` → `{"local_llm": {"backend": "ollama", "model":
  "llama3.1:8b", "tier": "guardian"}}`.
- 45 other tools unchanged.

### Explicitly out of scope

The following are named here as follow-up work, not deferred-with-no-record:

- Verifier behaviour on hosted-LLM responses (separate session).
- Sanitiser / proxy mode (separate session).
- Conductor-mode toggle (`streamlined | balanced | strict`) — separate
  session, requires UX-surface decisions.
- Citation-grounding enforcement on manuscript drafts (separate ADR).
- Migration of the remaining 45 tools to oracle mediation —
  incremental, follow-up sessions.
- IRB-facing threat-model update for local-LLM prompt-injection
  attack surface (separate session).
- Performance characterisation (cold-start, GPU vs CPU paths) —
  separate session.

### Cost-gate posture and ADR 0005

[ADR 0005](0005-cost-pre-estimation.md)'s pre-estimation does not
apply to local-LLM calls: there is no token cost to a hosted service.
Cost is wall-clock + CPU + RAM. A future ADR will define
local-resource gating; this ADR explicitly defers that gate and notes
the deferral. The cost-gate behaviour for the **deterministic
processing calls** the local LLM composes over is unchanged — those
calls flow through the existing Tier-1/2/3 cost gate per ADR 0005.

### Criticality classification

Per [ADR 0014](0014-coverage-criticality-invariant.md), this ADR
declares the criticality classification of the new code regions in
the same change:

- **`framework/local_llm/layer.py:LocalLLMLayer`** — **CRITICAL**.
  Router-adjacent registration, audit-log-row-category-emitter, and
  the entry point through which the framing-claim amendment lives or
  dies. Newly-uncovered code on this path after a diff is
  `COVERAGE REGRESSION` per ADR 0014.
- **`framework/local_llm/backends/*.py`** — **HIGH**. Backend
  implementations including `OllamaBackend` and `NullBackend`. The
  no-op default backend is the *behaviourally-unchanged for existing
  deployments* guarantee; a regression there is a regression on the
  ADR's central commitment.
- **`framework/local_llm/contract.py:OracleResponse` and the typed
  dataclasses** — **HIGH**. Schema declaration paths per ADR 0014.
  The ADR 0008 boundary is enforced by the schema; coverage on the
  schema-validation paths is HIGH.
- **`framework/router.py:register_local_llm_layer`** — inherits the
  router's existing CRITICAL classification under ADR 0014.

The `coverage-criticality-mapper` agent prompt cites this ADR's
classification on subsequent diffs touching these regions.

## Consequences

**Positive.**

- The framework's privacy claim strengthens categorically when the
  layer is opted in: from *no streams at Tier 1* to *no streams ever,
  at any tier, including to hosted LLMs*. Institutional deployments
  whose IRB or DUA forbid any raw biometric data leaving institutional
  infrastructure gain a path that did not exist under the prior
  architecture.
- The citable-vs-non-citable boundary the project's research-
  credibility claims depend on becomes contract-enforced rather than
  reviewer-enforced. A reviewer auditing a manuscript can read the
  `OracleResponse` shape and tell which claims grounded on
  deterministic processing and which were LLM prose. ADR 0008's
  invariant gains a downstream contract that mirrors it.
- The four-tier model (Scout / Sentinel / Guardian / Titan) admits
  the project's heterogeneous hardware reality (a PI on a 4 GB
  laptop, an analyst on a 32 GB workstation) without forking the
  architecture. The cited numbers are tier-invariant by construction;
  what varies is the quality of prose composition over those numbers.
- The default `NullBackend` posture means the ADR is behaviourally a
  no-op for every deployment that does not opt in. Existing
  deployments after this ADR lands behave identically to deployments
  before it — the optional posture is the load-bearing concession to
  not breaking working installations.
- Resolved-context tool-calling addresses the LLM-fabrication failure
  mode at the schema level. The local LLM cannot drift the
  numerical-claims surface because the framework pre-resolves the
  deterministic calls; the LLM composes prose, the framework records
  the numbers.

**Negative.**

- The framework gains a new framework-tier module (`framework/local_llm/`)
  with backend dependencies. Every backend added (Ollama in v0,
  llama-cpp / vLLM / others later) is a maintenance surface. The
  protocol-shape under [ADR 0020](0020-typed-protocols-for-cross-component-seams.md)
  is the mitigation — the `OracleBackend` typed protocol bounds the
  surface area each backend must implement.
- The framing-claim amendment requires synchronised edits across
  CLAUDE.md, README.md, and `docs/design/research-framing.md`. The
  amendment is conditional (*when the local-LLM layer is opted in*),
  which is a fragile shape — a reader skimming for the privacy claim
  may pick up the strengthened version and miss the conditional. The
  `code-vs-roadmap-drift-auditor` agent's existing remit covers the
  ongoing truthfulness audit.
- ADR 0005 cost-gating does not extend to local-LLM resource use.
  Wall-clock, CPU, and RAM are not gated in v0. A pathological
  prompt against the Titan tier on a 16 GB laptop can swap the
  machine without any framework gate firing. Acceptable in v0
  because the layer is opt-in and the hardware floor is documented;
  a future ADR formalises local-resource gating.
- The v0 scope (oracle mediation on two tools) is intentionally
  narrow but the contract surface is the full architecture. A future
  reviewer asking *"why does the framework have a `LocalLLMLayer`
  that mediates only two tools?"* gets the answer in this ADR's
  Phase-0-scope section, but the asymmetry between the contract
  surface and the wired-up tool count is a real cost until the
  follow-up sessions land.

**Neutral.**

- [ADR 0001](0001-audit-log-as-backbone.md)'s audit-log backbone is
  unchanged. The new oracle-call row category is one more row shape
  alongside the existing tool-call and consent-handler categories.
  The schema migration is `ALTER TABLE` for the new fields
  (`model_id`, `model_version_hash`, `confidence`, `prompt_hash`,
  `tier`), the same shape as the [ADR 0002](0002-subject-id-scoping.md)
  migration.
- [ADR 0007](0007-rendering-layers-policy.md)'s dual-output pattern
  applies here by analogy: deterministic processing output is the
  source of truth (the snapshot fallback in ADR 0007 terms); the LLM
  narrative is the additive layer (the Dataview live-query block in
  ADR 0007 terms), labelled non-citable. A reader without the local
  LLM still gets the citable claims; the narrative is the additive
  composition over them.
- [ADR 0010](0010-adversarial-pairing.md)'s adversarial-pairing
  precedent is the design lineage. The LLM-to-LLM contract pattern is
  the structural import of adversarial pairing applied at runtime
  (local LLM as guardian, hosted LLM as composer) rather than at
  agent-dispatch time. The same architectural argument that makes
  adversarial pairing work for agent verdicts makes the local-LLM
  guardian work for tool-call mediation: when one LLM's prompt is
  *compose this prose well* and another's is *verify the claim
  against deterministic ground truth*, the same model class produces
  different outputs.
- [ADR 0012](0012-vault-phi-scrubber-bypass.md)'s framework-tier
  bypass precedent applies. The local-LLM layer skips the
  biosensor-tier gates for the same reason the vault layer does: it
  is not a biosensor data source. Param validation and audit still
  apply.

## Alternatives considered

**Local LLM as a child, not as framework-tier infrastructure.** Folding
the local LLM into the `ChildMCP` shape would put it under the
biosensor-tier gates (consent, cost, circuit breaker, PHI scrubber).
Rejected. The local LLM is not a biosensor data source. It composes
prose over data the analyst has already cleared via the existing
tier model. Subjecting an oracle call to the consent gate misframes
what the gate gates — biometric-data access, not narrative composition
over already-released results. The same argument
[ADR 0012](0012-vault-phi-scrubber-bypass.md) made for the vault layer
applies here: framework-tier infrastructure that does not move
biometric data registers via `register_*_layer()`, not as a child.

**Local LLM calls deterministic processing directly (LLM-as-tool-caller).**
The conventional MCP-tool-calling shape has the LLM choose which tools
to call and pass the parameters. Rejected. That shape inverts the
load-bearing architectural choice: it makes the LLM the resolver of
the deterministic-processing call, which means a fabrication or
parameter-drift bug in the LLM corrupts the citable surface. The
resolved-context pattern keeps the framework as the resolver — the
LLM composes prose over a resolved result it did not choose. The
fabrication failure mode is bounded at the schema level rather than
at prompt-engineering quality.

**Hosted LLM only; no local LLM.** Rejected on two grounds. First,
the privacy-claim strengthening (no streams ever leaving the
analyst's machine) is unavailable without a local composer.
Institutional deployments whose IRB forbids streams leaving
institutional infrastructure have no path under the hosted-only
architecture. Second, the LLM-fabrication failure mode is harder to
bound when the same LLM both chooses tool calls and composes prose
over results — there is no second LLM whose narrower remit
(*compose over this resolved result*) constrains the fabrication
surface. The
[ADR 0010](0010-adversarial-pairing.md) precedent — pairing two
narrow-remit LLMs produces dissent the broad-remit LLM does not —
applies to the runtime architecture exactly as it applies to the
agent roster.

**Single-tier model (no Scout / Sentinel / Guardian / Titan
gradation).** A single model posture would simplify the
configuration surface. Rejected because the project's deployment
reality is heterogeneous: a PI laptop running a study workflow, an
analyst's workstation crunching cohort questions, a teaching demo on
modest hardware. A single-tier model either prices out the low-end
deployments (model too large) or under-serves the high-end ones
(narrative quality too low). The four-tier gradation admits the
heterogeneity without forking the architecture; the
*cited-numbers-are-tier-invariant* commitment keeps the research-
credibility surface unchanged across tiers.

**Inline narrative in existing tool results — no separate
`ask_local_oracle`.** A simpler shape would have each existing tool
produce both numbers and narrative in its existing response.
Rejected. That shape couples narrative composition to every tool's
result schema and forces the local-LLM dependency on every
deployment that wants any tool to return prose. The separate
`ask_local_oracle` surface preserves the optional posture (existing
tools return their existing schemas; oracle mediation is a separate
opt-in call) and keeps the citable-vs-non-citable boundary at the
tool-surface level rather than smearing it across every existing
result.

**Mediation across all 47 tools at v0.** Rejected on scope grounds.
The cohort surface
([ADR 0015](0015-tier-1-cohort-surface-and-metadata-sidecar.md)) is
the IRB-most-sensitive and smallest scope; landing oracle mediation
there first lets the contract bake against a real demand-driven case
rather than across the full surface speculatively. Migrating the
other 45 tools is incremental work that benefits from production
feedback on the v0 contract. The phase-0 scope is a deliberate
calibration; a future ADR per migration wave records the decision to
extend coverage.

**Default-on local LLM (`OllamaBackend` as the default backend, not
`NullBackend`).** Rejected on the *existing-deployments-unchanged*
commitment. A default-on posture would require every existing
deployment to install Ollama and pull a model on first run after the
ADR lands, breaking installations on machines without the hardware
floor. The
[ADR 0003](0003-phi-scrubber-seam.md) precedent — *ship the seam with
a no-op default; institution/operator opts in to a real backend* — is
the load-bearing analogy. The default `NullBackend` is to oracle
mediation what the default no-op `PHIScrubber` is to PHI policy: the
seam is shipped, the policy is the deployer's choice.

# ADR 0025: Cue-card rehearsal as a release-time gate; the cue card is a load-bearing artifact

- **Status:** Proposed
- **Date:** 2026-05-06
- **Related:** [ADR 0008 (Deterministic by construction)](0008-deterministic-by-construction-processing.md), [ADR 0010 (Adversarial pairing)](0010-adversarial-pairing.md), [ADR 0011 (Promotion policy)](0011-promotion-policy.md), [ADR 0014 (Coverage criticality)](0014-coverage-criticality-invariant.md), [ADR 0016 (MCP-protocol auditor)](0016-mcp-protocol-auditor.md), [ROADMAP.md § Shipped in v6.9.1 / v6.9.2](../../ROADMAP.md), [CLAUDE.md § Workflow: manager mode](../../CLAUDE.md#workflow-manager-mode)

## Context

The framework ships with a one-page cue card at
[`examples/hip_lab_demo/realistic/CUE_CARD.md`](../../examples/hip_lab_demo/realistic/CUE_CARD.md)
that scripts a seven-step audience walkthrough — the operator reads
prose prompts to a fresh Claude Desktop, Claude infers which tool to
call and what parameters to pass, the framework returns a result, the
operator narrates the wow moment. The cue card is the demo's wire
format. It is also, structurally, the artifact at which prose-to-
schema inference is exercised end-to-end against the live framework.

The v6.9.0 release passed the full seven-agent gate stack —
`ci-gate-runner` SHIPPABLE (818/818 pytest, ruff clean, security probe
76/76, CLI smoke PASS), `mcp-protocol-auditor` PROTOCOL OK (49 tools
on the wire, three new subprocess regression tests),
`reproducibility-provenance-auditor` CLEAN, `researcher-utility-
reviewer` ALIGNED, `phi-irb-risk-reviewer` WATCH → CLOSED, `coverage-
criticality-mapper` REVIEW, `red-team-reviewer` NO OBJECTION FOUND —
and shipped a Step 2 cohort prompt that returned 16 silent
`column not found` load_errors against the `force_cohort_summary`
tool. The boss surfaced the failure on the demo run by reading the
prompt aloud to Claude exactly as written. Two patch releases in one
week (v6.9.1 fixing the alias-resolution path at
[`force_csv/child.py:1083-1098`](../../src/tailor/children/force_csv/child.py),
v6.9.2 hardening the BOM and uninstall paths) closed the immediate
bugs. The class of bug remains live: any future cue-card prompt that
names a column, tool, or filter the schema does not literally accept
fails the same way.

The failure is invisible to gates that measure structural envelope
correctness without inspecting payload semantics. The dad-prompt
failure was *visible* in the response payload — `load_errors: [...]`
is a populated field, not a silent return — but no gate in the prior
roster knew which prose-to-schema pairs to drive, only which JSON-RPC
envelopes to assert against. `mcp-protocol-auditor` could in principle
parse `load_errors`, but its remit per
[ADR 0016](0016-mcp-protocol-auditor.md) is wire-level correctness on
*supplied* tool/param pairs — schema keys, type coercion, markdown
round-trip, post-execute hook surfacing. It does not own which prompts
the cue card poses or whether those prompts can be answered by the
framework's tool surface as configured. `pytest` cannot assert on it
either: the inference happens inside an LLM, not inside Python.
`coverage-criticality-mapper` and `reproducibility-provenance-auditor`
operate on diffs and in-process artifacts. Demo-before-commit
(Protocol 5) catches it the way it caught the v6.5.0 protocol-adapter
bugs — at the boss's interface, after the gate stack has signed off.

The structural argument matches [ADR 0016](0016-mcp-protocol-auditor.md)'s
exactly: the surface where the framework's behavioural claims meet a
real client is structurally distinct from the abstractions the in-
process gates audit. The protocol-adapter surface meets a real client
on the wire. The cue-card surface meets a real client through prose-
driven inference. Neither is exhaustively reachable from the other.

The question this ADR answers: *what is the smallest structural seam
that gives the framework a prose-to-schema inference gate without
reshaping the existing roster, and where does that seam fire?*

## Decision

A new specialist, `cue-card-rehearsal-auditor`, owns prose-to-schema
inference correctness across cue-card prompts. The agent reads the
cue card's prompts and the framework's `ToolDefinition` schemas from
source, simulates the inference Claude Desktop would perform on each
prompt, and emits per-prompt verdicts. The cue card is promoted from
a one-off demo aid to a load-bearing release artifact — a recognition
of what it has already become, not a new commitment.

The rule, plain English: every release is gated on a fresh
`cue-card-rehearsal-auditor` run against the release working tree.
Any cue-card prompt that the agent cannot map to a working tool/param
pair is a release-blocker until the cue card or the schema is fixed.
Prose-driven inference belongs to a prose-driven gate; in-process and
wire-level gates do not substitute.

Concrete mechanism:

- **`.claude/agents/cue-card-rehearsal-auditor.md`** (model: opus,
  tools: Read / Grep / Glob — read-only by construction) is the
  specialist's prompt. Its remit: glob cue cards under
  `examples/**/CUE_CARD.md`, parse the walkthrough table's prompt
  column, read every registered child's `tool_definitions` and
  `param_schemas` from source, and for each prompt emit one of four
  verdicts: `PASS` (the prompt maps cleanly to one tool with valid
  params), `WRONG-TOOL` (the prompt names or implies a tool that
  does not exist or whose schema rejects the implied params),
  `WRONG-PARAMS` (the prompt names a tool that exists but with a
  parameter value the schema rejects — the v6.9.0 footgun class),
  `AMBIGUOUS` (multiple tools could plausibly match; Claude's choice
  is not deterministic from prose alone).
- **PASS verdicts are medium-signal; WRONG verdicts are blocking.**
  The asymmetry is load-bearing for the agent's value and is named in
  the agent's prompt as text. The agent's reasoning model is not a
  fresh Claude with tools attached, so PASS is presumption-of-
  correctness, not proof. False-positive WRONG is cheap — re-examine
  the schema and either fix it, fix the cue-card prose, or annotate
  the prompt as deliberately exercising a recovery-row scenario.
  False-negative PASS is exactly what v6.9.0 had. The agent is
  calibrated to err toward WRONG.
- **The cue card is the load-bearing artifact.** Recovery prompts at
  [`examples/hip_lab_demo/realistic/CUE_CARD.md:55-68`](../../examples/hip_lab_demo/realistic/CUE_CARD.md)
  encode the failure class explicitly — Variant-B and Variant-C rows
  added in v6.9.1 anticipate both "Claude guessed wrong column" and
  "Claude guessed wrong tool." The cue card is no longer a
  presentation aid the operator may revise freely; changes to its
  prompt column are diffs the gate fires on. Edits that drift a
  prompt away from a working tool/param pair are caught by the agent
  on the next release, and the recovery-prompt rows that document
  known footgun classes are the agent's known-good lookup table for
  what the framework deliberately does *not* yet round-trip.
- **Firing triggers.** The agent fires mandatory before every release
  — `release-shipper` invokes it pre-tag and refuses to bump version
  on a `WRONG-TOOL` or `WRONG-PARAMS` verdict. It fires on-demand
  whenever the cue card's prompt column or any registered child's
  schema changes. The cadence matches `mcp-protocol-auditor`'s
  per-release trigger established in
  [ADR 0016](0016-mcp-protocol-auditor.md).
- **Adversarial pairing.** A confident PASS-on-every-prompt verdict
  against non-trivial work pairs with `red-team-reviewer` per
  [ADR 0010](0010-adversarial-pairing.md). The dissent does not have
  to win; it has to be visible. The agent's prompt carries the
  uniform "Refuse on conflict with codebase ground truth" Tier-2
  rule and the BORDER NOTES side-channel.
- **Promotion grounding.** The agent lands under
  [ADR 0011](0011-promotion-policy.md)'s structural-argument rule.
  Structural argument: the cue-card surface is the address at which
  prose-driven inference meets the framework's tool surface, and no
  existing specialist drives that surface.
  `mcp-protocol-auditor` audits supplied tool/param pairs;
  `researcher-utility-reviewer` audits artifacts through persona
  lenses; neither owns the prose-to-schema inference layer. Severity
  grounding: two patch releases in one week (v6.9.1 / v6.9.2 per
  [ROADMAP.md lines 29-41](../../ROADMAP.md)) shipped from this
  exact failure class against a green seven-agent gate. Maintenance
  estimate: one run per release plus on-demand runs after cue-card
  or schema changes — well below the per-agent fire-frequency the
  existing roster carries.
- **Bundled landing.** The ADR, the agent prompt, and the agent's
  first-run dogfood evidence land in one PR, mirroring
  [ADR 0016](0016-mcp-protocol-auditor.md)'s bootstrap precedent. The
  recursive use is the demonstration: the agent's reason for existing
  is the exact gap its first run must close. A future contributor
  reading this ADR finds the agent prompt, the verdict shape, and the
  v6.9.0-pre-fix dogfood evidence as one coherent landing.

Reversal condition is a named validation step: the specialist's
first-run dogfood must produce a *non-PASS* verdict on the cue card's
Step 2 prompt at
[`CUE_CARD.md:38`](../../examples/hip_lab_demo/realistic/CUE_CARD.md).
The verdict's shape depends on which codebase the audit runs against,
because the v6.9.1 fix landed in the *handler* — not the *schema
description* — so the schema's `value_column` prose is identical
between v6.9.0 and v6.10.0:

- Against v6.9.0's pre-resolver codebase (before
  [`force_csv/child.py:1083-1098`](../../src/tailor/children/force_csv/child.py)),
  the prompt's plausible inference (`value_column="force"`) fails
  end-to-end with 16 `column not found` load_errors — the agent must
  return `WRONG-PARAMS`.
- Against v6.10.0's post-resolver codebase, the same inference
  succeeds at runtime because the handler-side alias resolver
  compensates, but the schema's prose remains under-specified — the
  agent must return `AMBIGUOUS` (per the explicit anti-pattern
  guidance in the agent prompt: *"treating a handler-side resolver as
  a schema-side fix"* keeps the verdict at AMBIGUOUS, not PASS).

Either verdict shape satisfies the reversal condition because both
demonstrate the agent caught the schema's under-specification at the
prose layer where the v6.9.0 incident occurred. **Only `PASS` would
mean the agent reached past the schema into the handler and defeated
the gate's purpose** — that outcome rolls the ADR back rather than
landing a placebo gate. The validation step matches
[ADR 0016](0016-mcp-protocol-auditor.md)'s precedent — its first run
on v6.5.0 fixed all five protocol-adapter ship-blockers; this ADR
binds itself to the same evidentiary bar with the codebase-dependent
verdict refinement made explicit.

## First-run dogfood evidence

The agent's first invocation against the v6.10.0 working tree
produced the verdict shape the reversal condition specifies. Run via
`general-purpose` with the agent prompt as inline context, since the
new specialist's prompt at
[`.claude/agents/cue-card-rehearsal-auditor.md`](../../.claude/agents/cue-card-rehearsal-auditor.md)
becomes natively dispatchable only after a session restart. Verbatim
from the report:

```
=== CUE CARD REHEARSAL ===
Cue card: examples/hip_lab_demo/realistic/CUE_CARD.md
Inventoried prompts: 7 (4 tool-call, 3 frame)
Schemas in scope: ~50 ToolDefinitions across 5 children + framework

--- STATIC PRE-PASS ---
Tool: force_cohort_summary, Param: value_column — UNDER-SPECIFIED —
  description "Column to reduce per file" (force_csv/child.py:459-462)
  has no example value, no discovery-tool hint, no default, no
  allowed_values. Identifier-shaped string param failing all four
  signals.
Tool: emg_cohort_summary, Param: value_column — UNDER-SPECIFIED —
  same shape as force sibling at emg_csv/child.py:420-423.
(Other identifier params: PASS — discovery hints, defaults, or named
examples present.)

--- PER-PROMPT VERDICTS ---
Step 2: AMBIGUOUS
   Inferred call: force_cohort_summary(group_field="sex",
                                       value_column="force",
                                       metric="max")
   Expected:      ... value_column="force_N" ...
   Reasoning:     Tool name italicised in prompt pins selection.
                  metric=max verbatim. group_field="sex" reachable
                  from "grouped by sex" + named example in description
                  (force_csv/child.py:456). value_column has nothing
                  to lean on; description "Column to reduce per file"
                  carries no example, hint, default, or allowed_values.
                  Operator's prose is "peak isometric force" — fresh
                  Claude pattern-matches "force" as the natural-
                  language column token. Handler-side alias resolver
                  at force_csv/child.py:1098-1100 maps "force" →
                  "force_N", so the call SUCCEEDS in v6.10.0. But
                  Claude does not see the handler. Per anti-pattern
                  guidance ("treating a handler-side resolver as a
                  schema-side fix"), this remains AMBIGUOUS.
Step 3: PASS — file_id discoverable via force_list_files in same
   tools/list snapshot; force_column has named default.
Step 4: PASS — same shape as Step 3 against emg_csv.
Step 5: PASS — vault_search_notes query is semantic-string, not
   identifier-shaped; multiple plausible queries all surface the
   target moment.

--- AGGREGATE VERDICT ---
REVIEW

--- BORDER NOTES ---
emg_csv/child.py:420-423 — emg_cohort_summary value_column under-
  specified in same shape as force sibling.
force_csv/child.py:1083-1089 — handler-side resolver closes the
  runtime symptom but not the inference-instability gap; a future
  tool copying the cohort_summary pattern without the resolver
  reproduces the failure.
CUE_CARD.md:65-66 — recovery prompts for v6.9.0 footguns remain
  accurate as Claude-version-fragility hedges; operator decides
  whether to retain them as defensive armor.
```

The reversal condition holds: the agent caught the schema's under-
specification at the prose layer (`AMBIGUOUS` on Step 2) without
reaching past the schema into the handler. Aggregate verdict
`REVIEW` is non-blocking — the agent surfaces the schema-quality
work for the next pass without halting v6.10.0's release. The
BORDER NOTES name two follow-on items (the EMG sibling shares the
same defect; the recovery-prompt rows are operator-decided) that the
main session integrates rather than the agent fixing.

## Consequences

**Positive.**

- The framework's prose-to-schema inference surface gains a gate at
  the address where the inference actually happens. Every cue-card
  prompt is a contract claim that the operator can read aloud and
  Claude can answer through the framework; the agent makes that
  contract auditable.
- The bug class v6.9.0 / v6.9.1 / v6.9.2 named is structurally
  addressed, not patched. Schema-rejection on a prose-implied
  parameter, tool-existence drift between cue card and registered
  children, and ambiguous-tool prompts all share the property that
  they are invisible to gates that audit JSON-RPC envelopes or
  in-process artifacts. A specialist that reads the cue card and the
  schemas together catches them by construction.
- Demo-before-commit (Protocol 5) is no longer the project's earliest
  prose-driven signal. The boss's first encounter with a cue-card
  ship-blocker stops being the gate; the agent fires before the demo
  and the demo becomes confirmation rather than discovery. The
  precedent matches [ADR 0016](0016-mcp-protocol-auditor.md) exactly
  — Protocol 5 is the boss's interface to the system, not a gate the
  system applies to itself.
- The cue card's promotion to load-bearing artifact is descriptive,
  not aspirational. The recovery-prompt rows added in v6.9.1
  ([`CUE_CARD.md:64-66`](../../examples/hip_lab_demo/realistic/CUE_CARD.md))
  already encode the failure class explicitly; v6.9.2's BOM and
  uninstall fixes already track to cue-card flow integrity. This ADR
  recognises what the artifact has already become rather than
  introducing a new commitment.
- The agent composes cleanly with the existing roster.
  `mcp-protocol-auditor` continues to own supplied tool/param wire
  correctness; the new agent owns which tool/param pairs the cue
  card's prose can plausibly produce. `red-team-reviewer` pairs
  with the new agent's confident verdicts. No existing specialist's
  remit shrinks.

**Negative.**

- The agent's reasoning is heuristic on the prose side. A future cue-
  card prompt that uses idiom or analogy ("show me what dropped off")
  is harder to map to a tool than a prompt that names the tool
  literally ("call `force_cohort_summary`"). The agent budgets for
  this by emitting `AMBIGUOUS` on prompts where multiple tools could
  match; an `AMBIGUOUS` verdict is a hint to the cue-card author to
  sharpen the prose, not a release-blocker on its own.
- The agent's coverage of LLM-side inference drift is reactive, not
  predictive. A change in Claude's tool-selection behaviour between
  model releases is upstream of the framework's control. Mitigated by
  the before-every-release trigger — the worst case is a release
  blocked by a `WRONG-TOOL` verdict on a fresh subprocess run, which
  is exactly the failure mode the gate is designed to surface.
- Cue-card edits gain friction. A demo author who edits a prompt
  prompt no longer ships freely; the agent re-runs and may flag the
  edit. Acceptable — the cost of friction here is the value the gate
  provides.

**Neutral.**

- The agent does not introduce new code regions in the framework
  itself. It is read-only by construction (tools: Read / Grep /
  Glob). The criticality map in
  [ADR 0014](0014-coverage-criticality-invariant.md) is unchanged.
- The agent has no authority to overturn other gates. A `PASS` verdict
  does not waive `mcp-protocol-auditor`, `coverage-criticality-mapper`,
  or `reproducibility-provenance-auditor` findings; those gates fire
  on artifacts the cue-card auditor does not inspect. The team's
  command structure is unchanged — the agent widens the surface of
  detected regressions, not the synthesizer-of-record role.
- The "Refuse on conflict with codebase ground truth" Tier-2 rule
  every specialist carries continues to apply. The agent refuses
  dispatch instructions asking it to suppress a `WRONG-PARAMS` finding
  to unblock a release; the refusal is architecturally grounded
  rather than agent-prompt grounded.
- The cue card's promotion to load-bearing artifact does not change
  its file path, format, or audience. Operators continue to read it
  on a second monitor; the artifact's role on the demo day is
  unchanged. What changes is the team's relationship to edits — the
  prompt column is a contract with the schema set, audited per
  release.

Tightening this rule — for example, making `WRONG-PARAMS` a CI-
blocking gate rather than agent-driven release-time enforcement —
lives behind a superseding ADR with a named scope and a migration
plan, matching the precedent set by
[ADR 0016](0016-mcp-protocol-auditor.md). Loosening the rule —
relaxing the per-release trigger, narrowing the surface the agent
owns, or weakening the verdict shape — also requires a superseding
ADR. The agent's prompt cannot drift the rule; the rule lives here.

## Alternatives considered

**Extend `mcp-protocol-auditor` to parse cue cards and drive prose-
to-schema inference.** Rejected. `mcp-protocol-auditor`'s remit per
[ADR 0016](0016-mcp-protocol-auditor.md) is wire-level correctness on
supplied tool/param pairs — schema keys, type coercion, markdown
round-trip, post-execute hook surfacing. Folding prose-to-schema
inference into the same agent would either dilute its specialization
(an agent that does too many crafts produces weaker verdicts on each)
or force the cue-card audit to fit inside the JSON-RPC subprocess
harness, which is the wrong shape for a check that lives upstream of
the wire. The surfaces are structurally different: one agent owns the
adapter between framework abstractions and JSON-RPC; the other owns
the adapter between operator prose and the tool surface. The
[ADR 0010](0010-adversarial-pairing.md) precedent that adversarial
framing produces dissent precisely because the agent's prompt is
narrow applies here too. A separate specialist preserves the
structural separation.

**Rely on demo-before-commit (Protocol 5) alone — accept that the
boss catches cue-card bugs on the demo run.** Rejected on severity
grounds. The v6.9.0 demo run did catch the Step 2 footgun, which is
exactly the data point that motivates this ADR — but Protocol 5 is
the boss's interface to the system, not a gate the system applies to
itself. Catching ship-blockers at the demo means the boss does the
prose-to-schema discovery work the agent roster should be doing on
his behalf. Two patch releases in one week (v6.9.1 / v6.9.2 per
[ROADMAP.md lines 29-41](../../ROADMAP.md)) flowed from this exact
failure class against a green seven-agent gate stack. The structural
argument named in [ADR 0011](0011-promotion-policy.md) — specialists
land before the third incident on severity-dominant cases — applies
directly here, and matches the same severity grounding
[ADR 0016](0016-mcp-protocol-auditor.md) used to reject the parallel
proposal at v6.5.0.

**Marker-based pytest tests — `@pytest.mark.cuecard` on a parameterised
prompt-to-tool mapping.** Rejected. The failure is in LLM-prose-to-
schema inference, which is not a thing pytest can assert. Marker-
based tests require a test author to name the expected tool and
params for each prompt — the same work the cue-card author already
did when writing the prompt — and then assert the framework accepts
them. That asserts the schema is internally consistent with the
test's expectation, which is upstream of the question the gate
exists to answer: *will Claude infer the right call from this
prose?* A pytest assertion cannot answer that without an LLM in
the loop, at which point the test has become the agent and pays
agent-shape costs for test-shape value. The cue-card-rehearsal-
auditor is the right grain.

**Spawn a real Claude Desktop subprocess on every release and replay
the cue card against it.** Rejected on engineering-cost and
provenance grounds. A real-Claude-in-the-loop gate would couple the
release process to a hosted-LLM dependency the project deliberately
avoids — the framing claim in
[ADR 0022](0022-local-llm-guardian.md) and
[ADR 0023](0023-local-llm-cooperation-loop.md) is that hosted LLMs
are the wrong home for participant biometric data, and the cue-card
demo is the artifact through which that claim is communicated. A
release gate that *requires* a hosted-LLM round-trip to sign off
contradicts the framing it is meant to validate. The static-analysis
shape (an agent reading prose and schemas, not a real Claude
inferring tool calls) preserves the project's local-first posture
and is sufficient for the failure class the v6.9.0 incident
demonstrated.

## v6.11.x amendments — enforcement mechanism

The original ADR 0025 wording said the agent is *"mandatory pre-tag trigger via `release-shipper`."* That phrasing implied the release tool itself enforced the gate, but `release-shipper.md` as of v6.11.0 did not reference this agent at all; the gate fired only when the main session in release prep "remembered" to spawn it. The 2026-05-08 cross-ADR review closes this gap.

The actual enforcement is **attestation-required at release-shipper pre-flight**:

- `release-shipper.md` § "Pre-tag gate composition" inspects `git diff --name-only main...HEAD` against this agent's trigger globs (`CUE_CARD.md`; `children/**/child.py`; `framework/vault/layer.py`; `framework/local_llm/layer.py`; any file declaring `ToolDefinition` schemas).
- If any trigger matches and the caller has not passed `--gates-confirmed=cue-card-rehearsal:<verdict>`, release-shipper hard-refuses with the same shape as the dirty-working-tree refusal.
- The verdict string is recorded verbatim in the release commit body (`## Pre-tag gates attested`). release-shipper does not parse verdict semantics — the boss is the authority on whether the verdict is acceptable. A deliberately-false attestation becomes a deliberately-false statement in the durable audit record.

**Why attestation rather than inline re-spawn.** The agent runs in seconds, but most releases do not touch its trigger globs. Re-spawning unconditionally would waste runtime; not re-spawning at all would recreate the convention-only gap. Attestation makes the convention auditable at the cost of one flag, while letting the boss run the gate at any point during release prep — not specifically at release-shipper invocation. The cost-vs-frequency tradeoff per [ADR 0011](0011-promotion-policy.md) is the load-bearing argument for the policy choice.

The original "mandatory pre-tag trigger" wording stands on the record; the v6.11.x amendment refines what *triggered* means mechanically (file-touched trigger map in `release-shipper.md`) and what *mandatory* means mechanically (attestation hard-refusal). The structural argument (schemas under-specified for prompt-driven inference is the failure class) is unchanged.

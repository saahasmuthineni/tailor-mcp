# ADR 0019: The cost gate binds on every tier whose ToolDefinition advertises a non-zero token range

- **Status:** Proposed
- **Date:** 2026-05-01
- **Related:** [ADR 0005 (Cost pre-estimation)](0005-cost-pre-estimation.md), [ADR 0014 (Coverage criticality invariant)](0014-coverage-criticality-invariant.md), [ADR 0001 (Audit log is the backbone)](0001-audit-log-as-backbone.md), [CLAUDE.md § Three-Tier Access Model](../../CLAUDE.md#three-tier-access-model), [CLAUDE.md § Security Pipeline](../../CLAUDE.md#security-pipeline-cheapest-first)

## Context

[ADR 0005](0005-cost-pre-estimation.md) names the cost gate as a
pre-execution check: `CostGate` calls the child's `estimate_cost()`
before dispatching the tool, gates on the estimate, and fails closed
if the estimator itself raises. The decision section reads as if
pre-estimation binds uniformly across the framework. The implementation
does not.

Every shipped child returns `CostEstimate(tokens=0)` for any tool
other than the Tier-3 stream pull. In `children/running/child.py:529-530`,
`estimate_cost` checks `if tool_name != "strava_full_streams"` and
returns zero. `children/csv_dir/child.py:431-433` does the same for
`csv_raw_stream`, and `children/template/child.py:329-330` does the
same for `example_raw_stream`. The cost gate compares estimated tokens
against the 35,000-token threshold (`framework/cost.py:43-44`); a
`tokens=0` return means `should_gate` is always False, so the gate
silently skips for every Tier-1 and Tier-2 tool.

This is fine for Tier 1, where the documented token ranges are 200 to
1,500 (per [CLAUDE.md § Three-Tier Access Model](../../CLAUDE.md#three-tier-access-model))
and even pessimistic real values stay an order of magnitude below the
threshold. It is structurally incomplete for Tier 2. The
`strava_downsampled_streams` ToolDefinition advertises "3000-7000
tokens" and the equivalent `csv_downsampled` and `example_downsampled`
ToolDefinitions advertise the same range. ADR 0014 names ToolDefinitions
as part of the declared contract — the schema declaration is a HIGH
region. Today, the contract a Tier-2 tool's ToolDefinition publishes
about its own cost is unenforced: the consent gate fires, the call
proceeds, and the Tier-2 payload reaches the LLM regardless of whether
the actual token count matches the advertised range. A Tier-2 tool
that ships a regression doubling its real token count produces no
signal at the gate boundary; the audit log records the call, but the
gate the architecture claims protects against runaway cost on the
Tier-2 surface is a no-op.

This is not a near-miss. The 3,000-7,000 advertised range sits
~10x below the gate's 35,000 threshold even at the upper bound, so
the gate would not have fired today even if `estimate_cost` returned
a true non-zero estimate. The structural question the ADR must
answer is therefore not "what is the actual cost overrun risk
today" — it is "what does ADR 0005 mean by *pre-estimation* on every
tier where the ToolDefinition advertises a non-trivial range, and
what does a child author owe the framework in that signature?"

The question this ADR answers: *does ADR 0005's pre-estimation rule
bind only on Tier 3 (where the gate currently fires) or on every
tier whose ToolDefinition advertises a non-trivial token range, and
how is the rule made auditable so a future regression on a Tier-2
estimator surfaces at the contract boundary rather than as a silent
overrun?*

## Decision

The cost gate binds on every tier whose ToolDefinition advertises a
non-zero token range. A child's `estimate_cost()` must return a
non-zero `CostEstimate` for every tool whose call would actually
consume tokens of the order its ToolDefinition advertises. Returning
`CostEstimate(tokens=0)` is permitted only for tools whose worst-case
real cost is below the framework's "negligible" floor (currently
1,500 tokens, the upper bound of the Tier-1 documented range).

The threshold at which the gate *fires* is unchanged at 35,000 tokens
and remains tuning, not architecture. What this ADR codifies is the
*estimator-required* invariant: the gate's input must be a true
estimate of the call's token cost on every tier that publishes a
non-trivial range, regardless of whether the threshold would have
fired on that estimate. The estimate is the contract; the threshold
is the policy applied to the contract.

Concrete mechanism:

- Every child's `estimate_cost(tool_name, params)` returns a
  `CostEstimate` whose `tokens` field reflects the call's actual
  expected cost. The shortcut "return 0 for any tool that isn't
  Tier 3" is removed wherever the Tier-2 tool's ToolDefinition
  advertises a token range above the negligible floor.
- A child author who deliberately wants the gate to skip a non-Tier-3
  tool (because the call's real cost is below the negligible floor,
  or because consent is the load-bearing gate and cost is genuinely
  not a concern) declares that intent per-tool with a docstring on
  the `estimate_cost` branch citing this ADR. Silent zero-returns on
  tools that advertise non-trivial ranges are out of contract.
- The estimator-required invariant is enforced at PR time by
  `reproducibility-provenance-auditor` (whose existing remit covers
  ADR 0005 fail-closed correctness). The auditor's prompt gains a
  per-tool check: every ToolDefinition with a non-trivial advertised
  token range must have a non-zero `estimate_cost` branch in the
  child's `estimate_cost` body, or a per-tool docstring justifying
  the zero-return.
- ADR 0014's criticality map continues to classify
  `framework/cost.py` `CostGate` and the fail-closed estimator
  branch as CRITICAL. This ADR adds an implicit HIGH classification
  on the per-child `estimate_cost` body: a regression that drops a
  Tier-2 estimator branch to `tokens=0` is a `COVERAGE REGRESSION`
  on the same bar as a regression in the gate itself, because the
  gate's correctness depends on the estimator's input.

The implementation work — wiring up Tier-2 estimators across
`children/running/child.py`, `children/csv_dir/child.py`, and
`children/template/child.py`, plus any future child — is a separate
downstream issue list. This ADR records the rule; the rule's
application across the existing children lands as a follow-up under
its own version-bump tracking.

Reversal condition: the rule loosens (e.g. "Tier-3 only, Tier-2
estimators are advisory") only via a superseding ADR. Tightening
(e.g. "non-zero estimators required on every tier including Tier-1")
is also a superseding ADR — the negligible-floor exemption is part
of the contract, not an implementation accident.

## Consequences

**Positive.**

- ADR 0005's pre-estimation claim becomes structurally complete
  across the tier surface the framework actually publishes. The
  Tier-2 contract a ToolDefinition advertises is no longer
  unenforced; the gate's input is a true estimate on every tier
  that declares a non-trivial range.
- The estimator-required invariant turns the cost gate into a
  symmetric mirror of the consent gate. ADR 0005's "fail closed on
  estimator error" guarantee composes with this ADR's "estimator
  must be non-zero on non-trivial tiers": the gate cannot silently
  no-op either by an estimator failure (ADR 0005) or by an estimator
  shortcut (this ADR).
- Tier-2 regressions that double or quintuple a tool's real token
  count surface at the estimator boundary instead of as silent
  payload growth. The audit log captures the actual cost trend, and
  drift between estimator and reality shows up as the gate firing
  on calls that previously passed — a visible signal rather than a
  governance bypass.
- The rule is auditable at PR time without a CI plumbing change.
  `reproducibility-provenance-auditor` already runs on diffs
  touching `framework/` and `children/*/processing.py`; extending
  its remit by one per-tool check is the smallest enforcement
  surface that closes the gap.
- ADR 0014's criticality map gains a citable home for the per-child
  `estimate_cost` body. A future contributor reshaping
  `estimate_cost` in any child finds the rule in this ADR rather
  than re-deriving it from the gate's behavior.

**Negative.**

- Every existing child's `estimate_cost` body must be revised to
  add a Tier-2 branch. This is real implementation work — three
  children in-tree today, plus any out-of-tree children built
  against the ChildMCP extension point. Mitigated by the rule
  being scoped to "tiers that advertise a non-trivial range":
  children whose Tier-2 tools genuinely return below the
  negligible floor are exempt with a docstring.
- Tier-2 estimators add a second per-tool code path that must
  stay in sync with the execution path. ADR 0005 already named
  this cost for Tier-3 tools; this ADR extends the same cost to
  Tier-2. The mitigation is identical: tests assert estimate /
  actual within a tolerance for representative payloads.
- Children that ship a Tier-2 tool without an estimator before
  this ADR ships will need one before their next non-trivial diff
  lands. This is a deliberate friction the same shape as ADR 0005's
  "brand-new Tier-3 tools without an estimator need one written
  before they ship."

**Neutral.**

- The 35,000-token threshold is unchanged. Whether a Tier-2
  call's real cost crosses the threshold is a tuning question, not
  an architectural one; this ADR codifies the rule that the
  threshold's input is a true estimate, not the threshold's
  numeric value.
- The negligible-floor exemption (1,500 tokens, the Tier-1 upper
  bound) is calibrated against the current tier model. A future
  re-tuning of the Tier-1 / Tier-2 split would adjust the
  negligible floor in the same change without amending this ADR;
  the rule is "tools whose advertised range is above the
  negligible floor" rather than a fixed numeric cutoff.
- Existing Tier-1 tools (`strava_run_report`, `csv_summary_report`,
  the per-file Tier-1 tools, vault tools) continue to return
  `tokens=0` correctly. Their advertised ranges sit at or below
  the negligible floor, and the rule exempts them. This ADR does
  not retroactively flag Tier-1 tools as out of contract.
- The "Refuse on conflict with codebase ground truth" Tier-2 rule
  every specialist carries continues to apply.
  `reproducibility-provenance-auditor` already refuses dispatch
  instructions that ask it to suppress an ADR 0005 fail-closed
  finding; this ADR extends the same refusal to Tier-2
  estimator-required findings.

## Alternatives considered

**(a) Wire estimators on every Tier ≥2 tool (the chosen rule, scoped
to non-trivial advertised ranges).** This ADR's decision. Most
defensive of the four candidates: the estimator-required invariant
binds wherever the ToolDefinition publishes a contract about cost.
Scoped by the negligible-floor exemption so Tier-1 tools whose real
cost is genuinely below the threshold are not forced into ceremonial
estimator code that would itself become a maintenance surface. The
auditor's per-tool check is the smallest enforcement that closes the
gap without a CI plumbing change.

**(b) Amend ADR 0005 to "Tier-3 only" and downgrade the
ToolDefinition token ranges to advisory-not-enforced.** Rejected.
This is the most permissive option and matches the implementation as
shipped, but it weakens the architectural claim the framework makes
to its researchers. The Tier model's load-bearing claim is that data
minimization is a technical implementation, not a recommendation
([CLAUDE.md § Three-Tier Access Model](../../CLAUDE.md#three-tier-access-model)).
Demoting Tier-2 cost contracts to advisory undermines that claim:
ToolDefinitions become marketing rather than enforced contracts, and
a future Tier-2 regression has no architectural surface to fail
against. The rule "the schema is a contract" (per ADR 0014's HIGH
classification on schema declaration) cannot hold if the
ToolDefinitions' cost ranges are simultaneously declared and
unenforced.

**(c) Add a `cost_estimator_required` flag on `ToolDefinition`
itself, defaulting to required for Tier ≥ 2.** Rejected as
over-mechanized. The flag would be a per-tool boolean carried in
every ToolDefinition declaration, the absence of which would itself
become the new failure mode (a child author forgets to set the
flag and the rule silently exempts the tool). The structural
problem is not that the rule is unrepresented in code; it is that
the rule is unrepresented in architecture. An ADR that names the
rule and an auditor that enforces it covers the same surface
without adding a per-tool boolean that future children must
remember to set. This option would be the right shape if the rule
needed runtime introspection (e.g. the router itself enforced
estimator presence), but the runtime check is unnecessary — the
gate already calls `estimate_cost`, the question is what
`estimate_cost` is required to return.

**(d) Leave as-is and document the gap in CLAUDE.md.** Rejected.
This is the status quo, and the status quo is exactly the failure
mode this ADR exists to address. A documented gap in CLAUDE.md is
not auditable: a future contributor reading
[ADR 0005](0005-cost-pre-estimation.md) finds the pre-estimation
rule and reasonably assumes it binds across the tier surface, then
discovers the Tier-2 estimators return zero only by reading the
implementation. The drift between the architectural record and the
shipped behaviour is the case that justifies a new ADR rather than
a CLAUDE.md note. ADR 0011's precedent applies: load-bearing rules
belong in ADRs even when an existing doc currently references them.

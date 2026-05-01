# ADR 0017: ADR weigher gates premature-ADR drift in autonomous sessions

- **Status:** Accepted
- **Date:** 2026-05-01
- **Related:** [ADR 0010 (adversarial pairing)](0010-adversarial-pairing.md), [ADR 0011 (promotion policy)](0011-promotion-policy.md), [ADR 0014 (coverage-criticality invariant)](0014-coverage-criticality-invariant.md), [CLAUDE.md § Workflow: manager mode](../../CLAUDE.md#workflow-manager-mode), [docs/design/operating-model.md](../design/operating-model.md)

## Context

Manager mode (the boss's default working style) increasingly involves autonomous overnight sessions in which the main session runs audits, applies tier-1 fixes, and files ADRs without per-action boss review. The audit-and-fix loop is reversible — fixes land on a branch and the boss reviews the PR with coffee. Filing ADRs is qualitatively different. ADRs are durable, they encode commitments, and future ADRs cite them. A poorly-shaped ADR shipped overnight establishes precedent that later contributors lean on.

The first audit batch of the autonomous-session pattern surfaced ten candidate ADRs from a single overnight pass. Several were genuine architectural decisions (e.g., cross-tier GPS precision asymmetry, post-execute hook signature drift). Several others were bugs masquerading as decisions ("`csv_force_decline` returns an error key the handler doesn't check") or implementation details one tier below the architectural level ("OAuth refresh race in `strava_api.py`"). Without a quality gate, the main session's incentive — facing a non-zero per-ADR token cost and a bias toward producing visible artifacts — is to lower the bar and file all ten.

[ADR 0011](0011-promotion-policy.md) named the analogous failure for specialists: a frequency-based promotion rule under-weights severity and lets architecturally-codified holes go un-defended; the structural-argument override prevents premature roster bloat. ADRs face the symmetric failure: a "this looked architectural in the moment" rule under-weights whether the decision actually has downstream code commitments and lets bug-shaped findings get filed as architectural records. The bar must distinguish "ADR-worthy" from "fix it directly" before the main session drafts.

The architectural precedent is established. [ADR 0010](0010-adversarial-pairing.md) shipped two specialists (`boss-report-auditor`, `red-team-reviewer`) whose entire job is to gate other agents' confident verdicts before they propagate downstream. The same pattern applies one tier up: specialists exist to gate the main session's confident verdicts before they reach the boss-facing record.

Concurrent with this gating, the autonomous-session shape needs a per-session cap on ADRs filed without boss review. A cap of one or two is too tight for a productive overnight; an uncapped session can flood the ADR space. The boss's instruction during the v6.5.0-to-overnight planning was *"raise the limit a bit"* — paired with the gate, the cap can be raised to a number where the gate is the binding constraint, not the cap.

The question this ADR answers: *what gate prevents an autonomous session from filing ADRs that should have been bug-fixes or that should have waited for boss input, and how many ADRs may a single autonomous session file once the gate is in place?*

## Decision

`adr-weigher` ships as a specialist under `.claude/agents/adr-weigher.md`. The autonomous-session ADR cap is six per session, with `adr-weigher` as the binding quality constraint.

The rule, plain English first: every candidate ADR surfaced during an autonomous session is weighed by `adr-weigher` before `adr-drafter` is invoked. The weigher returns one of four verdicts — `PASS` (file as ADR), `REJECT-NOT-ADR-WORTHY` (this is a bug, test gap, or implementation detail; route it to the promotion memo or fix it directly), `DEFER-NEEDS-BOSS-INPUT` (decision-shaped but the answer is the boss's call, not the main session's), or `INSUFFICIENT-INPUT` (the candidate cannot be weighed without one focused clarification). Only `PASS` verdicts proceed to drafting.

Concrete mechanism:

- The weigher's prompt scores each candidate against five criteria, all listed in `.claude/agents/adr-weigher.md`: decision-shaped (not bug-shaped), reversal-changes-downstream-code, WHY-non-obvious to future contributors, cites-prior-ADRs (extends or contradicts), and severity-of-getting-it-wrong. A `PASS` requires at least four of five to hold; severity-dominant candidates clear with weaker support on the other four (mirrors [ADR 0011](0011-promotion-policy.md)'s severity-grounding rule).
- The weigher is read-only: it does not draft the ADR, number it, or commit anything. The verdict is the deliverable.
- Autonomous-session ADR cap: six ADRs per session, filed only with `PASS` verdicts. The cap is high enough that productive sessions are not throttled by it; the gate is the binding constraint.
- A session that reaches six `PASS` verdicts and the weigher returns a seventh `PASS` is itself a signal — surface it in the morning briefing as a cap-collision so the boss can decide whether to widen the cap or hold the seventh for next session.
- Subsequent boss-driven sessions are not capped — the cap exists to limit autonomous drift, not to constrain the boss's deliberate ADR work.
- `code-vs-roadmap-drift-auditor` reads ADRs filed under autonomous sessions on its existing cadence and flags any whose content the codebase no longer supports — the same backstop ADR 0011 named for the specialist roster.

This ADR's own filing satisfies its rule. The boss requested the weigher and the cap-raise during the overnight 2026-05-01 planning conversation. Each criterion holds: decision-shaped (the rule could have been "no specialists at all gate ADR creation"); reversal-changes-code (removing the weigher requires deleting the agent file and removing every cite of this ADR); WHY-non-obvious (a future contributor reading the agent roster will reasonably ask why the team has a specialist for ADR creation when `adr-drafter` already exists); cites prior ADRs (0010 and 0011 directly); severity (filing a bad ADR establishes durable precedent — medium-to-high cost asymmetry).

## Consequences

**Positive.**

- ADRs filed during autonomous sessions clear an explicit quality bar before they reach the boss-facing record. Premature-ADR drift becomes visible (REJECT and DEFER verdicts in the morning briefing) rather than silent.
- The bug-vs-decision distinction becomes a first-class output of the audit pipeline. Findings that surface as candidate ADRs but score `REJECT-NOT-ADR-WORTHY` are routed to the promotion memo or fixed directly, both of which are cheaper than retracting an ADR later.
- The boss's overnight-session input cost is reduced without losing input on the architectural questions where it actually matters. `DEFER-NEEDS-BOSS-INPUT` verdicts list themselves in the morning briefing as decisions the boss owns; he answers them with coffee, the next session files them.
- The six-ADR cap matches the ADR-creation rate the project has sustained on boss-driven sessions (v6.5.0 shipped two ADRs, v6.4.x shipped four across multiple sessions). An autonomous session that legitimately produces six well-shaped ADRs is doing the work of a productive boss-driven sprint; one that produces zero is correctly low-yield rather than artificially throttled.
- The weigher's read-only scope keeps it cheap. It reads ADRs, CLAUDE.md, and cited evidence file:lines; it produces a verdict. No write surface, no commit surface, no drafting overhead.

**Negative.**

- The weigher is one more agent in the roster, contributing to the agent-management overhead [ADR 0011](0011-promotion-policy.md) named as a real cost. The mitigation is that the weigher fires only during ADR-creation flows; its per-session activation is bounded by the candidate-ADR queue, which is itself bounded.
- Severity calibration is softer than the criteria 1–4 rules. A skilled prompt-writer could justify a high-severity score on a candidate that does not actually carry the severity. Mitigated by the requirement that the severity claim cite a specific surface (HIPAA section, ADR clause, audit-completeness invariant) — a fabricated severity claim is auditable.
- The six-ADR cap is calibrated against the current project shape. If the team adopts substantially more aggressive autonomous-session work, the cap will become the binding constraint and need re-tuning. Treat as a tuned parameter, not a rule.

**Neutral.**

- `adr-drafter`'s scope is unchanged — it still drafts ADRs from a 1–3 sentence concept. The weigher gates which concepts reach the drafter, not how the drafter writes them.
- The CLAUDE.md specialist roster gains one row for `adr-weigher`. Future ADR-creation flows in autonomous sessions cite this ADR in their batch summaries.
- `code-vs-roadmap-drift-auditor`'s remit grows by one cadence target: it now also reads recent ADRs against codebase ground truth, not only roadmap claims. This expansion is consistent with the agent's existing description.

## Alternatives considered

**No gate, just the cap (boss's first instruction shape).** The boss's literal instruction during the planning conversation was *"raise the limit a bit"* — a numeric cap with no quality gate. The cap alone is a count discipline, not a quality discipline; it limits how many bad ADRs land per session but does nothing to filter them. The weigher converts the cap from a hard number into a quality envelope, which matches what the boss actually wanted (the literal instruction was a proxy for the underlying intent: ADRs filed overnight should be at least as good as ADRs filed during boss-driven sessions). Rejected as under-engineered.

**Hard rule "no ADRs in autonomous sessions; queue them all for boss review."** Symmetric over-engineering. The boss specifically authorized autonomous ADR creation in the planning conversation; queueing every candidate for his review reverses that authorization and turns autonomous sessions into ticket-generation sessions. The high-confidence ADRs (cohort-tool extensions, defensive backstops on already-codified invariants) are exactly the cases where autonomous filing is on-the-rails; the gate exists to filter the low-confidence ones, not to block the whole class. Rejected.

**Weigher inside `adr-drafter` (single agent, longer prompt).** Folding the weighing logic into the existing drafter would reduce the agent count by one. Rejected because the two cognitive shapes are different — drafting is generative ("write the ADR in this voice"), weighing is adversarial ("this should not be an ADR"). [ADR 0010](0010-adversarial-pairing.md)'s precedent: when the agent's prompt is "do this craft well," default LLM behavior is confirmation; when the agent's prompt is "find a flaw or refuse it," the same model produces dissent. Pairing them is the import. Folding them collapses the gate the pairing produces.

**Weigh against an ADR-quality rubric in the main session itself, no new specialist.** The main session is the entity being gated. Gating with the same entity is the structural sycophancy gap [ADR 0010](0010-adversarial-pairing.md) named: the translator and the judge of the translation cannot be the same actor and produce honest output. Rejected for the same reason `boss-report-auditor` exists.

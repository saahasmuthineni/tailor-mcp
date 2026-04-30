# ADR 0010: Adversarial pairing — dissent is a seam, not a hope

- **Status:** Accepted
- **Date:** 2026-04-30
- **Related:** [ADR 0003 (PHI scrubber as seam)](0003-phi-scrubber-seam.md), [ADR 0007 (rendering layers policy)](0007-rendering-layers-policy.md), [CLAUDE.md § Boss-architect protocols](../../CLAUDE.md#boss-architect-protocols-tier-1--main-session-discipline), [docs/design/operating-model.md](../design/operating-model.md)

## Context

The team is two-tier: the boss (a non-technical conceptual architect) talks to the main session, and the main session dispatches specialist agents under `.claude/agents/`. The boss cannot read raw agent outputs and cannot detect main-session sycophancy himself; that asymmetry is documented in [docs/design/operating-model.md](../design/operating-model.md) and is the reason the five Tier-1 boss-architect protocols exist in CLAUDE.md.

The protocols (intent → options, pre-implementation audit, plain-language framing, conflict pushback, demo-before-commit) are correctly scoped — they describe what the main session must do at the boss-facing boundary. They are also self-policed. There is no peer to flag a drift. Protocol 4 (mandatory conflict pushback) names the load-bearing failure mode: if a month passes with no pushback, that is not evidence the main session has been right — it is evidence the rule has quietly collapsed. The structural backstop named in CLAUDE.md ("periodically have a strategy specialist re-read recent boss-facing reports") is correct in shape but reactive, and it does not address the second structural gap: the team is **stateless**.

Every agent dispatch starts cold. No agent sees another agent's output. The main session is the only integrating intelligence across multi-agent dispatches, which means it is simultaneously the translator of agent findings into boss-facing reports *and* the judge of whether that translation is honest. Both load-bearing roles live in the same constrained entity. Default LLM behaviour on "review this" is confirmation; on "find a flaw or prove there isn't one" the same model produces dissent. The lever available is the prompt — adversarial framing, by another agent, with the prior output as input.

The question this ADR answers: *how does the team make dissent visible without giving any agent authority to overrule another?*

## Decision

The team adopts adversarial pairing as a structural seam, not an aspiration. Two new specialist agents render dissent that the main session must integrate explicitly, and every agent prompt gains a side-channel for cross-cutting observations outside its primary scope.

The rule, plain English: on non-trivial work (same definition as CLAUDE.md protocol 2), the main session dispatches `boss-report-auditor` after drafting any boss-facing report and before sending it to the boss; and dispatches `red-team-reviewer` against any confident upstream verdict (PASS / Justified / SHIPPABLE / high-confidence root cause) from another agent. Both new agents must produce either an explicit dissent with cited evidence or an explicit "none found" with evidence of having actually looked. Bare assertions without evidence are forbidden.

Concrete mechanism:

- **`.claude/agents/boss-report-auditor.md`** (model: opus). Inputs: the verbatim raw agent findings and the main session's draft boss-facing report. It is the *second translator* — it audits the first translator's rendering against the source. Verdicts: `SHIP AS-IS`, `REVISE`, `RECONSIDER`. The hard rule is that "no objection found" is forbidden without cited evidence of which findings were checked against which sentences in the draft. The agent does not edit the draft and does not talk to the boss; it returns gaps the main session uses to revise.
- **`.claude/agents/red-team-reviewer.md`** (model: opus). Inputs: the upstream agent's name and its verbatim full report. Verdicts: `OBJECTION` (with cited evidence) or `NO OBJECTION FOUND` (with cited evidence of where it looked). Adversarial framings differ per upstream agent — `ci-gate-runner` PASS verdicts are attacked on coverage, `integration-auditor` Justified deletions are attacked on whether the replacement actually covers the deleted contract, `triage-debugger` high-confidence root causes are attacked on the most cheaply ruled-out alternate hypothesis, and so on. The agent has no authority to overturn; it makes dissent visible and the main session integrates it.
- **`## BORDER NOTES (cross-cutting observations)`** is added to all eight existing agent prompts (`ci-gate-runner`, `integration-auditor`, `vault-smoke-validator`, `release-shipper`, `adr-drafter`, `triage-debugger`, `code-vs-roadmap-drift-auditor`, `roadmap-framing-auditor`) and to both new agents. It is a flagging-not-investigating side-channel: an agent that notices something outside its primary scope writes one paragraph naming the observation and the agent best suited to investigate, then returns to its assigned job. The main session reads BORDER NOTES alongside the primary report.
- **CLAUDE.md** documents the new agents in the `## Workflow: manager mode` table and adds a `### Tier-2 adversarial backstops` sub-section under `## Boss-architect protocols` describing when each new agent fires. (This ADR is the architectural record; the CLAUDE.md edits are part of the same change.)

## Consequences

**Positive.**

- The single point of failure in synthesis (the main session as both translator and judge) is now paired against an explicit second translator at the boss-facing boundary and an explicit adversary at the agent-output boundary. Sycophancy on either path produces an artifact a third party can review later — the absence of a `boss-report-auditor` invocation on a non-trivial change is itself an audit signal.
- Dissent is forced to be evidenced. The hard rule that "no objection found" requires citations of where the agent looked turns the cheap pass-through into a structural impossibility. An agent that wants to confirm must do the work of demonstrating it tried to dissent.
- BORDER NOTES gives every specialist a low-friction way to surface cross-cutting observations without expanding its scope. Observations that previously fell on the floor — because the agent that noticed them wasn't the agent assigned to investigate them — now have a designated side-channel.
- The pattern composes cleanly with the existing five Tier-1 protocols. Protocol 3 (plain-language framing) gains `boss-report-auditor` as its mechanical backstop. Protocol 4 (conflict pushback) gains `red-team-reviewer` as its per-verdict backstop. The protocols still describe the rule; the agents make adherence verifiable.
- Adopting "red team" as a substrate for stateless LLM agents — rather than a human practice transplanted as policy — produces an artifact (the red-team report) that lives at the same address as the original verdict, which is exactly where a later reviewer will look.

**Negative.**

- Every non-trivial dispatch now carries two extra agent invocations. Token cost and wall-clock latency grow correspondingly. Mitigated by the "non-trivial" gate matching protocol 2's definition (typo fixes and one-line refactors skip both new agents) and by `red-team-reviewer` firing only on *confident* upstream verdicts, not on every output.
- The new agents can produce false dissent — an `OBJECTION` that the main session correctly judges to be a non-issue. The cost is a round of integration where the main session names why the objection doesn't bind. This is the intended cost; the alternative (silent suppression of real objections) is the failure mode the seam exists to prevent.

**Neutral.**

- The agents have no authority to overturn upstream verdicts. The main session remains the synthesizer of record and the boss remains the decision-maker. Adversarial pairing widens the surface of visible dissent without changing the team's command structure.
- The "Refuse on conflict with codebase ground truth" Tier-2 hard rule that the v6.1.1 release added to the eight existing agents is also present in both new agents. The team's anti-sycophancy backstop is now uniform across all ten specialists.
- The BORDER NOTES section is additive — it appears before the existing `## Hard rules` section in each prompt and does not change any existing rule. Agents that have nothing cross-cutting to report omit the section entirely.

## Alternatives considered

**External human review.** A trusted outside reviewer reads main-session transcripts on a cadence and flags suppressed conflicts. Effective in principle and a useful audit shape over the long term, but it lives outside the system the boss can reliably summon. An in-system seam is what makes the backstop available on every non-trivial change rather than only on the changes that happen to fall in a review window. External review remains a complementary practice; it is not the structural fix.

**Self-prompted adversarial pass on the main session.** The main session, after drafting a report or receiving a verdict, prompts itself to "now find the strongest objection." Cheaper than a new agent and easy to add as a CLAUDE.md rule. Rejected because it is exactly the failure mode this ADR exists to address — the constrained entity is the same entity policing itself. The structural problem of a single integrating intelligence does not dissolve by asking that intelligence to wear two hats in sequence.

**Voting agents.** Have N agents render verdicts on the same artifact and majority-vote. Rejected on substrate grounds: the team's specialists are intentionally non-interchangeable. `ci-gate-runner` knows about pytest and ruff; `integration-auditor` knows about diff-vs-base loss/gain analysis; `vault-smoke-validator` knows about temp-vault end-to-end behaviour. Majority-vote dilutes specialization and rewards consensus over correctness. Adversarial pairing preserves specialization and adds dissent on top.

**Inter-agent direct messaging.** Let agents argue with each other across dispatches, sharing context and refining positions. Rejected because it would require persistent state across stateless agent calls — large engineering lift for marginal gain. The same effect is achieved by re-dispatching with the prior output as input, which is exactly what `red-team-reviewer`'s contract specifies. The constraint that each dispatch starts cold is not a bug to route around; it is a property that keeps each agent's output independently auditable.

**Promote dissent into the existing agents' rubrics.** Add a "what would a critic say?" section to every agent prompt. Rejected for the same reason as the self-prompted pass — the entity producing the verdict is a poor reviewer of its own verdict. Specialization works because the agent's framing is aligned with its job. Asking an agent to also be its own critic adds load without adding the structural separation that makes dissent reliable.

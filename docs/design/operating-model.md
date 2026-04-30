# Operating model — boss-architect + agent team

This document captures **how the team works**, who the boss is, and what protocols govern the interface between the boss and the rest of the system. It complements [CLAUDE.md](../../CLAUDE.md), which contains the executable rules; this file holds the philosophy those rules are derived from.

This is an internal-facing document. It is the source-of-truth reference for future agent prompts, future CLAUDE.md edits, and any session that needs to understand why the protocols are shaped the way they are.

## The boss

The project has one human: a non-technical conceptual architect. He decides what the project is, what it should become, what serves health researchers, and which trade-offs are acceptable. He does not write code. He does not write technical prompts. He does not dispatch agents directly. He does not need to remember which specialist does what.

The implications for the system:

- He cannot audit a technical prompt that the team produces. If the team's prompt is wrong, he has no fallback.
- He cannot evaluate code quality directly. He depends on audit agents and their verdicts.
- He cannot detect sycophancy by reading code. A plausible-sounding but wrong output cannot be caught by him alone.
- He cannot remember every prior ADR or every shipped behaviour. The team is his memory.

The system has to compensate for all four of these without taking conceptual authority away from him.

## The two-tier architecture

There are two tiers of communication, with sharply different shapes:

```
+-------------------------------------------+
| Tier 1 — boss-facing                      |
|   Boss  <->  Claude Code main session     |
|   Plain language. Decision-shaped.        |
|   Conceptual. Vague intent in;            |
|   plain-language decisions out.           |
+--------------------|----------------------+
                     |
                     |  (the main session manages
                     |   the team on the boss's behalf)
                     |
+--------------------|----------------------+
| Tier 2 — internal infrastructure          |
|   Main session  <->  specialist agents    |
|   Technical. Prompt-shaped.               |
|   Dispatch-driven. Invisible to the boss  |
|   unless the main session surfaces it.    |
+-------------------------------------------+
```

**Tier 1** is the only tier the boss sees. It is conceptual, plain-language, and decision-shaped. The boss states intent; the main session translates, dispatches, integrates, pushes back, and surfaces decisions for the boss to make.

**Tier 2** is internal. The main session manages the agent roster — picks which specialists to dispatch, in what order, with what prompts. The boss does not see Tier 2 unless the main session decides a finding is decision-shaped enough to surface. The agent roster can be expanded, retired, renamed, or refactored entirely without changing anything the boss interacts with.

This means: agent prompts are private infrastructure. CLAUDE.md is the contract that governs the public interface (the main session). Most behavioural rules that protect the boss live in CLAUDE.md, not in agent prompts.

## What the main session does on the boss's behalf

The main session has five named responsibilities, each codified as a protocol in [CLAUDE.md § Boss-architect protocols](../../CLAUDE.md):

1. **Translation of vague intent into options.** When the boss says "make this better," the main session returns 2–3 product-shaped options for him to choose between. Pure vague-intent never goes directly to code.
2. **Pre-implementation defensive imagining.** Once an option is picked, the main session runs a "what could go wrong with this plan?" pass before any code is written. Catches misalignment when revising is cheap.
3. **Plain-language decision-framing on every boss-facing report.** No raw technical reports for the boss; every finding is re-cast as "here is the decision in front of you."
4. **Anti-sycophancy and mandatory conflict pushback.** When the boss's intent conflicts with prior decisions (ADRs, CLAUDE.md, ROADMAP, shipped behaviour), the main session surfaces the conflict instead of silently picking a side. The default LLM mode is to agree; the main session must resist that default.
5. **Demo-before-commit on non-trivial work.** Misalignment detection moves earlier — to a demo or walkthrough — rather than waiting for PR merge to discover the boss wanted something different.

The exact triggers, formats, and escape hatches for each protocol are in CLAUDE.md.

## What the agent roster is for (boss-facing summary)

The boss does not need to remember any of these. The main session knows. This section is here so a curious boss *can* read it — and so future contributors understand the shape of the team.

In plain terms:

- **vault-smoke-validator** — runs an end-to-end test of the analyst's notes-vault behaviour against a temp copy. Catches things pytest can't reach.
- **ci-gate-runner** — runs all the local-CI checks (tests, linter, security probe, command-line smoke) and reports verdicts. Read-only — never modifies anything.
- **integration-auditor** — before merging a branch, this looks at what's being *removed* (not what's being added) and flags anything load-bearing being quietly deleted. Default-skeptical lens.
- **release-shipper** — handles the mechanical work of shipping a feature: version bump, changelog, commit, push, PR. Only mutates main after the boss explicitly says "ship it."
- **adr-drafter** — drafts a numbered Architecture Decision Record matching the existing voice, when a non-obvious decision needs a permanent record.
- **triage-debugger** — diagnoses a single failure (test, runtime, audit finding) and reports root cause + suggested fix without applying it. Spawnable by other agents.
- **code-vs-roadmap-drift-auditor** — read-only audit of whether the docs (ROADMAP, CLAUDE.md, ADRs, README) still match the code. Single purpose: "is the project's documentation true?"
- **roadmap-framing-auditor** — given a one-paragraph framing of who the project is for, returns KEEP / RESHAPE / KILL verdicts on each roadmap item under that framing. Strategic, not technical.

When new specialists are needed, they land in `.claude/agents/` per the "promote at 3+ uses" rule (the same kind of work showing up in 3+ sessions). Until then, the work is inlined or handled by the closest existing specialist.

## Persistence and memory

The team is stateless. Every agent dispatch starts cold; agents do not remember prior runs. The main session is ephemeral within a single conversation — it remembers what was just discussed but not prior sessions.

Persistence lives in five places:

- **CLAUDE.md** — the contract that governs the main session, including all five Tier-1 protocols
- **ADRs** under `docs/adr/` — load-bearing architectural decisions with full context
- **ROADMAP.md** — explicit deferred work with effort/impact triage
- **README.md and `docs/design/*.md`** — outside-facing framing
- **Git history** — the long-term audit trail; commit messages and PR descriptions carry the *why* of each change

When CLAUDE.md drifts from code, agents flag it but do not fix it. When ADRs become out of date, the boss revises. The text artifacts are the institutional memory; everything else is recomputable.

## Why these particular protocols (heritage of each)

The five protocols are not invented from scratch. Each is grafted from a historical engineering team that succeeded with non-technical leadership, then re-derived for this substrate (single human + stateless agentic specialists + persistent text artifacts):

- **Protocol 1 (intent → options)** comes from the Macintosh team's iteration loop and id Software's Carmack/Romero pattern. Vague intent never went directly to code; it was always translated into 2–3 implementation options for critique first.
- **Protocol 2 (pre-implementation audit)** comes from Margaret Hamilton's work on the Apollo Guidance Computer. Defensive imagining ran *before* code was written, against the plan rather than the implementation.
- **Protocol 3 (plain-language decision-framing)** comes from Bell Labs' corridor principle — value was created when researchers explained their work across disciplines. The translation was the leverage, not the underlying finding.
- **Protocol 4 (anti-sycophancy / conflict pushback)** comes from Fred Brooks' insistence that conceptual integrity required an architect who refused to let implementations drift from the architecture, plus an LLM-specific patch for the default-to-agree failure mode.
- **Protocol 5 (demo-before-commit)** comes from the Mac team's iteration loop — feedback ran on demos, not on shipped product.

None of these is mimicry. The model is its own thing; the protocols are concept-grafts that fit *this* substrate, not templates copied from those teams.

## How the model evolves

The system should expand by adding protocols and specialists when patterns harden, not by making the model bigger for its own sake. The "promote at 3+ uses" bar (CLAUDE.md, manager mode) is the canonical filter: new agents land only when the same kind of work has appeared in 3+ sessions.

A good change to this model is one that:

- Removes a place where the boss has to do technical work he can't actually do
- Adds a designed-in check on a failure the boss cannot detect himself
- Reduces the cognitive load of any boss-facing decision
- Catches a pattern of misalignment between the boss's vision and the shipped reality

A bad change to this model is one that:

- Adds technical surface the boss has to learn or remember
- Adds an agent because "another team had something similar"
- Imposes a process step that doesn't pay for itself in caught misalignment
- Increases the team's size without a 3+-use signal

## The most important failure mode to watch for

A non-technical boss cannot detect main-session sycophancy by reading the conversation. If the main session never pushes back, it could mean the boss has been right every time (unlikely over a meaningful period) or that protocol 4 has quietly collapsed. The structural backstop is to periodically have a strategy specialist re-read recent boss-facing reports and check whether the main session surfaced the conflicts it should have.

This is Brooks' "conceptual integrity requires a single architect" *plus* an LLM-specific patch: the architect cannot be sycophantic, a non-technical architect cannot detect sycophancy, so build a watchdog that audits the architect.

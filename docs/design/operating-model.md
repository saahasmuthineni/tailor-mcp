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
- **integration-auditor** — before merging a branch, this looks at what's being *removed* (not what's being added) and flags anything load-bearing being quietly deleted. Default-skeptical lens. Optional `--proposal-mode` for pre-implementation defensive imagining; optional `--invariant=schema-drift` for new ChildMCP / param_schema PR-time validation against ADR 0002.
- **release-shipper** — handles the mechanical work of shipping a feature: version bump, changelog, commit, push, PR. Only mutates main after the boss explicitly says "ship it."
- **adr-drafter** — drafts a numbered Architecture Decision Record matching the existing voice, when a non-obvious decision needs a permanent record.
- **triage-debugger** — diagnoses a single failure (test, runtime, audit finding) and reports root cause + suggested fix without applying it. Spawnable by other agents.
- **code-vs-roadmap-drift-auditor** — read-only audit of whether the docs (ROADMAP, CLAUDE.md, ADRs, README) still match the code. Single purpose: "is the project's documentation true?" Also audits the deferred-roster table below on a cadence and flags rows whose promotion triggers have fired.
- **roadmap-framing-auditor** — given a one-paragraph framing of who the project is for, returns KEEP / RESHAPE / KILL verdicts on each roadmap item under that framing. Strategic, not technical.
- **boss-report-auditor** — second translator. Reads the main session's draft boss-facing report alongside the raw findings before the boss sees the report; flags suppressions, softenings, omissions, tone slips. Tier-2 anti-sycophancy backstop on protocol 3 (ADR 0010).
- **red-team-reviewer** — adversarial pairing on confident upstream verdicts (PASS / Justified / SHIPPABLE / "high confidence" root cause). Returns a cited objection or NO OBJECTION FOUND with evidence of having looked. Makes dissent visible rather than implicit (ADR 0010).
- **researcher-utility-reviewer** — reads any non-trivial artifact through three baked-in personas (PI, analyst/RSE, IRB reviewer) and renders per-persona verdicts. Catches the failure mode where the team builds for engineering elegance instead of researcher utility — the project's stated north star (ADR 0011).
- **coverage-criticality-mapper** — extends ci-gate-runner's coverage report with criticality classification anchored on ADR-cited regions. Newly-uncovered code in CRITICAL or HIGH = COVERAGE REGRESSION regardless of overall percentage.
- **reproducibility-provenance-auditor** — audits diffs against the determinism / audit-completeness / `_meta` / `subject_id` invariants in ADRs 0001 / 0002 / 0003 / 0008. Closes the ADR 0008 "enforced by review at PR time" gap.
- **phi-irb-risk-reviewer** — hostile-IRB-committee lens on code changes. Six threat-model lenses (Safe Harbor, consent scope, audit completeness, scrubber asymmetry, subject_id integrity, retention) yield NO RISK / WATCH / VIOLATION verdicts.

When new specialists are needed, they land in `.claude/agents/` per [ADR 0011 — promotion-policy](../adr/0011-promotion-policy.md): structural argument grounded in the project's stated goal + severity grounding (cost-of-absence) + per-agent maintenance estimate. Frequency-based 3+-uses is the fallback signal in the absence of a structural argument. The previous policy ("3+ uses on this project") is the global default in `~/.claude/CLAUDE.md` and is overridden project-locally because research substrates have severity asymmetries (PHI / IRB / reproducibility) the generic rule under-weights.

## Deferred roster (parked candidates)

The roster grows under ADR 0011's criteria; below are the candidates the team has identified but not yet built. Each carries a named promotion trigger — the concrete signal that lifts the row across the bar. `code-vs-roadmap-drift-auditor` audits this table on a cadence and flags any row whose trigger has fired without the role being promoted.

| Role | Gap | Promotion trigger | Effort |
|---|---|---|---|
| `researcher-onboarding-friction-reporter` | No agent walks the PI/RSE/analyst journey through README → install → setup → first analysis | Onboarding friction surfaces in 3+ user-feedback sessions, OR new ChildMCP lands without a wizard, OR boss requests a journey audit | S |
| `doc-example-freshness-auditor` | No agent runs the multi-subject pilot fixtures or doc walkthroughs end-to-end | Pilot quickstart breaks once in real use, OR `docs/guides/*.md` drift caught at PR time, OR fixtures need re-running for next ADR | S |
| `deployment-shape-advisor` (Path A vs Path B) | No agent advises on local-first vs Anthropic Managed Agents per `docs/design/managed-agents-compat.md` | User asks "should I use Managed Agents for use-case X?" 3+ times, OR a real institutional deployment is being scoped | M |
| `researcher-journey-runner` (combined onboarding + doc-freshness) | Combined role — if onboarding-friction promotes, build as one agent rather than two; reuses `researcher-utility-reviewer`'s persona definitions | Promotion of either onboarding-friction-reporter OR doc-example-freshness-auditor triggers this combined shape instead of two separate agents | S-M |
| post-execution result-scrubbing audit | No agent verifies the ADR 0003 scrubber asymmetry (vault path skips scrubbing by design) holds as the codebase evolves | A real PHI-scrubber subclass lands AND has a non-trivial scrubbing policy | XS |
| internal cross-child dispatch safety | Vault backfill calls children via the internal path, bypassing some router gates; no agent audits this | Vault backfill grows beyond its current shape, OR cross-child dispatch fails once at runtime | XS |

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

The system should expand by adding protocols and specialists when patterns harden, not by making the model bigger for its own sake. The promotion policy is codified in [ADR 0011 — promotion-policy](../adr/0011-promotion-policy.md): a specialist lands when a structural argument grounds it in the project's stated goal AND the maintenance cost over its expected fire-frequency is justified. Severity asymmetries (high cost-of-absence — PHI / IRB / reproducibility) override frequency thresholds. Frequency-based 3+-uses (the global default in `~/.claude/CLAUDE.md`) is the fallback signal in the absence of a structural argument, not the only signal.

A good change to this model is one that:

- Removes a place where the boss has to do technical work he can't actually do
- Adds a designed-in check on a failure the boss cannot detect himself
- Reduces the cognitive load of any boss-facing decision
- Catches a pattern of misalignment between the boss's vision and the shipped reality
- Closes a codified hole — an architectural invariant a current ADR has named but no agent enforces

A bad change to this model is one that:

- Adds technical surface the boss has to learn or remember
- Adds an agent because "another team had something similar"
- Imposes a process step that doesn't pay for itself in caught misalignment
- Adds a specialist whose maintenance cost over its expected fire-frequency exceeds the cost of *not* having it (per ADR 0011's per-agent calculus)
- Adds a specialist that overlaps an existing one rather than reshaping the existing one (the integration-auditor `--invariant=schema-drift` reshape is the precedent for this pattern)

## The most important failure mode to watch for

A non-technical boss cannot detect main-session sycophancy by reading the conversation. If the main session never pushes back, it could mean the boss has been right every time (unlikely over a meaningful period) or that protocol 4 has quietly collapsed. The structural backstop is to periodically have a strategy specialist re-read recent boss-facing reports and check whether the main session surfaced the conflicts it should have.

This is Brooks' "conceptual integrity requires a single architect" *plus* an LLM-specific patch: the architect cannot be sycophantic, a non-technical architect cannot detect sycophancy, so build a watchdog that audits the architect.

# ADR 0011: Specialist promotion is governed by structural argument and severity, not frequency alone

- **Status:** Accepted
- **Date:** 2026-04-30
- **Related:** [ADR 0003 (PHI scrubber as seam)](0003-phi-scrubber-seam.md), [ADR 0008 (deterministic by construction)](0008-deterministic-by-construction-processing.md), [ADR 0010 (adversarial pairing)](0010-adversarial-pairing.md), [CLAUDE.md § Workflow: manager mode](../../CLAUDE.md#workflow-manager-mode), [docs/design/operating-model.md § How the model evolves](../design/operating-model.md#how-the-model-evolves)

## Context

The team's rule for adding new specialists to `.claude/agents/` is inherited from the global Claude Code conventions in `~/.claude/CLAUDE.md` (manager mode): *"if the same kind of work shows up in 3+ sessions on the same project, that's the bar for promoting it to a checked-in agent."* The project's CLAUDE.md restates this bar in [§ Workflow: manager mode](../../CLAUDE.md#workflow-manager-mode), and `docs/design/operating-model.md` § "How the model evolves" treats it as the canonical filter.

The rule is correctly calibrated for premature-abstraction defense on generic projects. On this project — research-software infrastructure intended for IRB-governed clinical workflows — it under-weights three properties of the substrate.

First, **severity asymmetries**. A PHI leak, an IRB violation, or a reproducibility failure in a published analysis costs orders of magnitude more than a researcher-utility miss. A frequency-based bar fails closed against severity: an event that has happened zero times because it would be catastrophic if it happened once cannot accumulate three sessions of evidence before a specialist exists to prevent it. The rule, as written, gates the cheap defense behind the expensive failure.

Second, **architecturally codified holes**. [ADR 0008](0008-deterministic-by-construction-processing.md) explicitly states that the deterministic-processing invariant is *"enforced by review at PR time"* — a sentence that names a reviewer the project does not have. The architecture has identified the seam and not filled it. A frequency rule says the seam must wait for three failures. The architecture says the seam must exist now or [ADR 0008](0008-deterministic-by-construction-processing.md) is partly aspirational. Similar holes exist around [ADR 0003](0003-phi-scrubber-seam.md): the seam ships with a no-op default and the architecture assumes deployers will subclass, but the project has no agent that audits whether a deployment's wiring actually does so.

Third, **self-precedent**. [ADR 0010 (adversarial pairing)](0010-adversarial-pairing.md) shipped two new specialists (`boss-report-auditor` and `red-team-reviewer`) on a single-session structural-argument diagnosis, not three sessions of accumulated evidence. The team already operates with structural-argument as a valid override of the frequency rule. The rule on the page disagrees with the rule in practice. Either the precedent is undocumented (and future contributors will re-derive the frequency rule), or the rule on the page must change.

The question this ADR answers: *what bar does a candidate specialist actually have to clear, and how does the project distinguish a structural-argument promotion from premature roster bloat?*

## Decision

Specialist additions to `.claude/agents/` and reshapes of existing agents land via three combined signals, evaluated together:

1. A **documented structural argument** grounded in the project's stated goal ([CLAUDE.md § What This Project Is](../../CLAUDE.md#what-this-project-is)). The argument names which load-bearing claim the project makes that the candidate agent defends, and why no existing specialist defends it.
2. A **severity grounding** stating the cost-of-absence — what the project loses on the first incident the agent would have caught. Severity is asymmetric: a PHI leak, an IRB violation, a published-analysis reproducibility failure, or a documented invariant going un-enforced are all severity-dominant cases that override frequency thresholds.
3. A **per-agent maintenance estimate** that pays for itself over the agent's expected fire-frequency. An agent that fires once a year on a catastrophic-cost event clears the bar; an agent that fires three times a session on cosmetic findings does not, regardless of frequency.

Frequency-based 3+-uses remains the default signal **in the absence** of a structural argument. It is not the only signal. The frequency rule catches "same work repeating" patterns; the structural-argument rule catches "named hole in the architecture" patterns. Both filter against premature abstraction.

Concrete mechanism:

- This ADR (`docs/adr/0011-promotion-policy.md`) is the architectural record of the rule.
- [CLAUDE.md § Workflow: manager mode](../../CLAUDE.md#workflow-manager-mode) carries a one-line reference noting that the project-local rule overrides the global "promote at 3+ uses" default and points at this ADR. The general conventions in `~/.claude/CLAUDE.md` are unchanged — the override is project-specific.
- `docs/design/operating-model.md` § "How the model evolves" cites this ADR and gains a "## Deferred roster (parked candidates)" sub-section. Each parked candidate carries a documented promotion trigger — the structural argument it would clear if a specific event fired.
- `code-vs-roadmap-drift-auditor` audits the deferred roster on a cadence and flags any row whose promotion trigger has fired without the agent having been promoted. Drift on the roster is a documentation-truthfulness signal, which is that agent's existing remit.
- Future agent additions cite this ADR in their CLAUDE.md table-row addition or in their own prompt's frontmatter `description`. An agent landing without a citation is a signal the rule has quietly collapsed.

The four v6.3.0 specialist additions are the precedent application. Each is documented with its structural argument, severity grounding, and frequency rating:

- **`researcher-utility-reviewer`** — structural argument: defends [CLAUDE.md § What This Project Is](../../CLAUDE.md#what-this-project-is)'s "built for health research workflows" claim against drift toward developer-aesthetic features. Frequency: would have crossed 3+-uses on its own.
- **`coverage-criticality-mapper`** — structural argument: identifies which untested code paths are load-bearing for IRB-grade audit claims, distinguishing them from cosmetic gaps. Frequency: would have crossed 3+-uses on its own.
- **`reproducibility-provenance-auditor`** — structural argument: fills the named hole in [ADR 0008](0008-deterministic-by-construction-processing.md) ("enforced by review at PR time"). Severity grounding: a non-deterministic processing path that ships silently invalidates every published analysis using it. Frequency: zero, because the invariant has held by code-review accident; the hole is structural.
- **`phi-irb-risk-reviewer`** — structural argument: audits whether deployments wire the [ADR 0003](0003-phi-scrubber-seam.md) seam past the no-op default before they touch real PHI, and surfaces IRB-relevant risks the boss-architect cannot evaluate himself. Severity grounding: a single PHI leak ends the project's research credibility. Frequency: zero, because the project has not yet onboarded a real deployment; the hole is structural.

Two of the four picks (`researcher-utility-reviewer`, `coverage-criticality-mapper`) would have crossed the old frequency bar on their own. The other two (`reproducibility-provenance-auditor`, `phi-irb-risk-reviewer`) cross only on severity asymmetry. This split is the load-bearing demonstration of why the rule changed: a frequency-only rule lands two of the four agents and silently leaves the other two un-built, with the architecture's own holes un-defended.

## Consequences

**Positive.**

- The rule on the page now matches the rule in practice. The [ADR 0010](0010-adversarial-pairing.md) precedent (specialists landing on structural argument) is documented rather than implicit, and future contributors get a citable reason to do the same instead of re-deriving the frequency rule.
- Architecturally codified holes get filled when the architecture identifies them, not after the third incident. [ADR 0008](0008-deterministic-by-construction-processing.md)'s "enforced by review at PR time" stops being aspirational the moment `reproducibility-provenance-auditor` ships.
- Severity asymmetries are made explicit in promotion decisions. A candidate agent's case is evaluated against cost-of-absence, not just incident count, which matches how a research-substrate project actually accumulates risk.
- The discipline against unjustified roster bloat is preserved. Frequency-based 3+-uses remains the default signal; the override requires a documented structural argument that future readers can audit. An agent landing without either signal is visibly unjustified.
- Parked candidates carry promotion triggers, and those triggers are auditable. `code-vs-roadmap-drift-auditor`'s cadence catches the case where a trigger has fired without the agent being promoted — a structural backstop against the rule quietly collapsing.

**Negative.**

- Structural arguments are softer than incident counts. A contributor can construct a plausible-sounding structural argument for an agent that does not actually defend a load-bearing claim. Mitigated by the requirement that the argument cite a specific clause in CLAUDE.md, an ADR, or `docs/design/operating-model.md` — a rejected structural argument names which clause it failed to ground in.
- The rule adds a small documentation burden to every specialist addition: each new agent must carry a structural argument, severity grounding, and maintenance estimate. Acceptable because the alternative (silent precedent without a written rule) is the failure mode this ADR exists to address.

**Neutral.**

- The override is project-specific. Generic projects without research-substrate severity asymmetries are well-served by the original "promote at 3+ uses" rule, and `~/.claude/CLAUDE.md` is unchanged. The boundary between global and project-local rules is preserved.
- The rule does not retroactively re-evaluate the existing eight specialists. They remain in place under whatever bar they originally cleared. The new rule applies to additions and reshapes from this point forward.
- The "Refuse on conflict with codebase ground truth" Tier-2 rule that the existing roster carries continues to apply. Future specialists landed under this ADR carry it as well — the anti-sycophancy backstop is uniform across the roster regardless of which promotion bar a specialist cleared. The four specialists this ADR ushers in (`researcher-utility-reviewer`, `coverage-criticality-mapper`, `reproducibility-provenance-auditor`, `phi-irb-risk-reviewer`) carry the rule from their first commit; the count-agnostic phrasing here is deliberate so the claim does not drift as the roster grows.

## Alternatives considered

**Keep the global rule unchanged.** Rejected because severity asymmetries inherent to research substrates demand specialists land before the third incident. The frequency-based rule fails closed against severity in a way that costs more than the rule saves: a PHI-leak audit agent that does not exist because the leak has not happened yet is exactly the failure the rule produces. The discipline against premature abstraction is real, but it is not the only discipline the project owes itself.

**Make this a global rule change in `~/.claude/CLAUDE.md`.** Rejected because the rule is project-specific. Generic projects without research-substrate severity asymmetries are well-served by the original frequency rule, and most projects do not have architecturally codified holes of the [ADR 0003](0003-phi-scrubber-seam.md) / [ADR 0008](0008-deterministic-by-construction-processing.md) shape. Carrying the project-specific calibration into the global default would import a more nuanced rule into projects that do not need it, which is its own form of premature abstraction.

**Drop the rule entirely — accept any specialist a contributor proposes.** Rejected because the discipline against unjustified roster bloat is real on a one-person hobby-shaped project. Removing the rule entirely loses the filter; replacing it with a more nuanced rule preserves the filter while widening the bar to admit the structural-argument case.

**Defer the codification — operate ad hoc on the alternate rule without an ADR.** Rejected because the alternate rule diverges from the global default in a way future contributors and future Claude sessions will not detect. Without an ADR, the rule is invisible: a future session reads `~/.claude/CLAUDE.md` and the project's CLAUDE.md, finds the frequency bar, and either re-derives it from first principles or lets the project drift back to it by entropy. The [ADR 0010](0010-adversarial-pairing.md) precedent becomes a one-off rather than a documented pattern. Codification is the structural patch; ad-hoc operation is exactly the failure mode this ADR exists to prevent.

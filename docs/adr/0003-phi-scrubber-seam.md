# ADR 0003: PHI scrubbing is a seam, not a policy

- **Status:** Accepted
- **Date:** 2026-04-13
- **Related:** [ROADMAP.md § Real PHI-scrubbing implementations](../../ROADMAP.md#real-phi-scrubbing-implementations-behind-the-phiscrubber-slot), saahasmuthineni/biosensor-to-llm-middleware#14

## Context

"Strip PHI before results leave the router" sounds like a framework-
level feature. It is not — at least, not in the sense that the
framework can define what *PHI* means.

The HIPAA Safe Harbor method lists 18 identifiers. The Expert
Determination method allows context-dependent judgements. Research
studies with IRB approvals carve out their own policies that may be
more permissive (for a limited data set) or more restrictive (for
pediatric populations, mental health data, re-identification-risky
linkages). What counts as PHI in a Dexcom CGM trial is not what
counts as PHI in a FHIR bundle containing medication histories.

If the framework ships with a default PHI-scrubbing implementation:

- Deployers trust it, and get it wrong in ways the framework can't
  anticipate.
- The framework becomes a de-facto compliance vendor, which it is
  emphatically not.
- Updates to the default scrubber become a coordination problem
  across every deployment.

If the framework ships with *no* PHI-scrubbing hook:

- Every deployer reinvents the wiring. Worse, some deployers skip it
  because "it's not in the framework."
- The audit log cannot distinguish "scrubber ran" from "no scrubber
  configured" — a misconfigured deployment looks identical to a
  correctly-configured one.

## Decision

Ship a **seam**, not a policy.

- `PHIScrubber` is a class in `framework.security` (formerly
  `framework.middleware`) with a single method, `scrub(result) -> result`.
- The default implementation is a no-op. It is documented as a no-op.
- The default emits a **one-time warning on first construction** so a
  misconfigured deployment surfaces loudly in stderr on startup.
- `PHIScrubber` exposes a `scrubber_id` property — `"noop"` for the
  default, the subclass name otherwise — which is recorded in audit
  rows (or queryable per-install) so a reviewer can distinguish
  audit rows produced under a real policy from rows produced under
  the no-op default.
- The router instantiates one `PHIScrubber` at construction time and
  calls `.scrub()` on every successful child result in `_dispatch()`
  and `dispatch_internal()`, before the token estimate and audit row
  are finalized.
- `.scrub()` is **not** invoked on the vault-dispatch path —
  `_dispatch_vault()` handles analyst notes, which are metadata, not
  participant biometric data. The vault tier has its own governance
  story (see [CLAUDE.md § Two persistence tiers](../../CLAUDE.md#architecture)).

Institutions subclass `PHIScrubber` and wire their subclass into the
router at construction time when they have an IRB-approved policy.
An example subclass (issue #14) will live under `examples/`, not in
the framework, to make the subclassing pattern discoverable without
blessing any particular policy.

## Consequences

**Positive.**

- The framework stays agnostic to a question it has no authority to
  answer.
- Deployers who don't have a policy yet get a loud, repeatable
  signal that nothing is being scrubbed.
- Deployers who have a policy get a clean extension point and a
  single hook location (`_dispatch()` + `dispatch_internal()`).
- `scrubber_id` in audit rows turns a "did we scrub?" question into
  a fact on disk, not a configuration-inspection exercise.

**Negative.**

- A deployer who ignores the warning runs in production with no
  scrubbing and valid-looking audit rows. Mitigation: the `noop`
  value for `scrubber_id` is preserved in rows, so retrospective
  analysis can flag misconfigured periods.
- Contributors may propose adding "safe harbor" defaults to the
  framework. The answer is no — those belong in `examples/` or in a
  downstream package.

**Neutral.**

- The seam is in the security pipeline, not in each child. This
  means a scrubber is applied uniformly across data sources, but it
  also means the scrubber needs to understand the shape of every
  child's output. Subclasses will typically dispatch by `domain`.

## Alternatives considered

- **Ship a HIPAA-Safe-Harbor default scrubber.** Rejected. The
  framework cannot make blanket compliance claims, and a wrong
  default is worse than no default.
- **Make PHI scrubbing per-child, not pipeline-level.** Rejected —
  cross-cutting concerns live in the router. Per-child scrubbers
  would drift in coverage and invariants.
- **Require a scrubber at construction time (no default).** Rejected
  — breaks demo and single-subject workflows where there is no PHI
  to scrub. The warning-on-first-use pattern is the compromise.

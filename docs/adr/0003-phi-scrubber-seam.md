# ADR 0003: PHI scrubbing is a seam, not a policy

- **Status:** Accepted
- **Date:** 2026-04-13
- **Related:** [ROADMAP.md § Real PHI-scrubbing implementations](../../ROADMAP.md#real-phi-scrubbing-implementations-behind-the-phiscrubber-slot), saahasmuthineni/tailor-mcp#14

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

## Amendment 2026-05-14 — Child-level structured-PHI seam (parallel to the framework-level seam)

Triggered by [ADR 0037 — RedcapFileChild scope](0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md), which introduces the first **child-level** PHI-scrubbing seam in the framework.

### The new seam

A child whose data source carries IRB-approved structured PHI annotations (REDCap's `project_metadata.csv` `identifier=yes/no` flags; future candidates: FHIR resource-type taxonomy, EDF channel metadata) ships its own scrubber under `src/tailor/children/<domain>/scrubber.py` and invokes it **inside the child's `execute()`** before returning. The framework-level seam this ADR ratified continues to wrap every child's result post-return.

### Why a parallel seam and not a framework-level dispatch

The framework cannot generically answer *"what counts as PHI"* — that was this ADR's original load-bearing argument, and it is unchanged. What changes is that for some data sources, the IRB has answered the question per-field in a structured input the child can read deterministically. The framework still ships no policy; the child ships a **policy-aware-by-input** scrubber.

Two seams, two distinct concerns:

| Seam | Owned by | Scrubs based on | Default | Examples |
|------|----------|-----------------|---------|----------|
| Framework-level (this ADR) | `framework/security.py` `PHIScrubber` | Cross-domain pattern matchers (regex, heuristic, NLP) | No-op with one-time warning | Institutional subclass with regex for MRNs across all domains |
| Child-level (ADR 0037) | `children/<domain>/scrubber.py` | Domain-specific structured input from the source | No child-level scrubber unless declared by per-domain ADR | `RedcapPHIScrubber` reading `project_metadata.csv` `identifier=yes/no` flags |

The seams are complementary. A deployment that subclasses the framework-level scrubber for cross-domain regex scrubbing AND installs the REDCap child gets both — the child scrubs REDCap-specific identifier fields first inside `execute()`, then the framework's institutional regex scrubber runs on the already-domain-scrubbed result.

### Audit-row provenance

ADR 0037 adds a new `child_scrubber_id` column to `audit_log`. The original `scrubber_id` column continues to record the framework-level scrubber's identity. Both columns let an IRB reviewer distinguish:

- **Misconfigured deployment:** `scrubber_id="noop"` AND `child_scrubber_id IS NULL` — neither seam ran a real policy.
- **Child-level structured scrubber only:** `scrubber_id="noop"` AND `child_scrubber_id="redcap_metadata_flags"` — the framework still didn't scrub; the child did, per the IRB-approved structured input.
- **Both seams active:** `scrubber_id="<institutional subclass>"` AND `child_scrubber_id="redcap_metadata_flags"` — both layers ran.

### Promotion condition

Per [ADR 0011](0011-promotion-policy.md), if a **third** structured-PHI child wants the child-level seam (FHIR is the likely next candidate; EDF channel-metadata-driven scrubbing is the second), that is the structural-argument signal to promote the child-level pattern into a framework-level registry (`router.register_phi_scrubber(domain, scrubber)`). Two domains is *"happens to repeat"*; three domains is a pattern worth abstracting. Until then, the parallel seam stays the architectural shape — each child wires its own scrubber; the framework holds the line at *"ship seams, not policies."*

### What is unchanged

The framework-level scrubber seam codified by this ADR's Decision section is preserved verbatim. The no-op default still emits its one-time warning on first construction. The `scrubber_warning` field continues to surface in `_meta` for the no-op deployment. This ADR's original load-bearing claim — *the framework cannot define what PHI means generically* — is the same claim today. The new child-level seam is policy-**aware-by-input**, not policy-baked-in; the framework's authority boundary is unchanged.

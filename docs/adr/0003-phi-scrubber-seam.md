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

## Amendment 2026-05-15 — Trust-root attestation seam + small-cell suppression posture

Triggered by the v7.3.0 release banner's WATCH (a) and (c) findings deferred from v7.3.1 and addressed in v7.3.2.

### The two concerns this amendment ratifies

**Trust-root attestation seam.** A child-level scrubber that reads a structured input from disk (the v7.3.0 amendment's case) inherits the trust-root of that input. For `RedcapPHIScrubber` the trust root is `project_metadata.csv` and its `identifier=yes/no` flags. A tampered metadata file with every flag flipped from `Y` to `N` would render the scrubber a no-op — the existing seam has no cryptographic provenance recording *which state* of the trust root was in force when the scrubber ran. This amendment ships the seam that records it. It is **not** a tamper-prevention mechanism (the framework cannot prevent the operator from editing a file on their own machine); it is a **tamper-attribution** mechanism (an IRB auditor reconstructing what state was in force for a given call queries the fingerprint by hash, not by trust).

**Small-cell suppression posture.** A child-level scrubber that emits aggregate sample-count surfaces (REDCap's `top_values`, REDCap's `cohort_summary` group counts; future EDF channel-occupancy counts; FHIR resource-cardinality counts) can re-identify on low-cardinality non-identifier-flagged fields even when the identifier seam is correctly configured. A study with N=3 sites discloses site-level identity through cohort group counts directly. The framework ships **k-anonymity threshold suppression** as a seam, with a default-with-warning posture matching ADR 0003's existing scrubber-warning pattern.

### The trust-root fingerprint seam — decision

- Every child-level scrubber that reads a structured metadata input from disk exposes a **`fingerprint` property**. The property returns a hex string (SHA-256) computed at scrubber construction time over a **canonical-form** rendering of the loaded metadata, not the raw file bytes.
- "Canonical form" means a deterministic serialization of the *semantically-loadbearing* content the scrubber actually relies on — for `RedcapPHIScrubber`, sorted `(field_name, identifier_flag)` tuples joined by a fixed separator and UTF-8 encoded. Whitespace, BOM markers, CRLF/LF flips, and column reordering do **not** trip the fingerprint; flag flips and field additions/removals do.
- The framework adds a new `audit_log.source_metadata_fingerprint TEXT` column (domain-agnostic naming — `project_metadata_fingerprint` would be REDCap-specific and the seam generalizes to future children) plus an index `idx_audit_source_metadata_fingerprint`. NULL on non-child-scrubber dispatch paths and on children that ship no child-level scrubber.
- Stamped on every audit row produced by a child whose scrubber exposes a `fingerprint` property — the value is the fingerprint **at the moment the call executed**, not at consent-grant time. Boot-time attestation: the fingerprint is established when the operator configured the metadata file before launching `tailor serve`. The framework does not require explicit consent-time fingerprint stamping; Tier-1 REDCap tools are not consent-gated per ADR 0037, so a consent-only stamping site has no anchor on a fresh install.
- Surfaced in result `_meta.source_metadata_fingerprint` on the wire so the LLM transcript carries the trust-root identity at the moment of disclosure. NULL on non-child-scrubber dispatch paths to preserve the all-call-sites-sweep rule the v7.3.1 banner codified.
- **Forward-only mismatch policy.** A scrubber whose `fingerprint` at call time differs from its `fingerprint` at scrubber construction is structurally impossible by the design above (the scrubber's fingerprint is computed once at construction and cached); the relevant question is what happens when the on-disk file diverges from the scrubber's cached state. Children that want to detect this re-read the file on every `execute()` and compare; on mismatch they emit a typed error envelope, fail-closed, and do **not** auto-revoke consent or auto-purge the cache (ADR 0013's revocation flow is operator action). Prior calls' data remains in the LLM transcript — the framework cannot un-send bytes; the audit log carries both fingerprints so an IRB reviewer can correlate.
- **Operator recovery is an attestation ritual.** The framework provides one CLI surface per child that ships this seam — e.g. `tailor redcap reattest` — which prints (a) the cached fingerprint (the most recent value stamped in `audit_log.source_metadata_fingerprint` for this child's domain), (b) the new fingerprint computed from the current on-disk file, (c) a structured listing of the current trust-root state field-by-field with the identifier flag on each, prompts the operator to confirm, and re-stamps the audit log with the new fingerprint on `y`. The listing is the trust-affording artifact: a tamper attempt that flipped every flag to `N` is visibly displayed before the operator confirms; a legitimate edit (new instrument added mid-enrollment) is visibly displayed before the operator confirms; the framework refuses to silently update the fingerprint to match the new file. The framework does **not** store the cached canonical-form state (only the fingerprint hash) — a field-by-field historical diff is not available by design, the storage cost is deliberately not paid; the current-state listing plus the cached-vs-new fingerprint transition is the attestation surface.

### The small-cell suppression posture — decision

- Every child-level scrubber that ships aggregate count surfaces (`top_values`, `cohort_summary` group counts, future analogues) accepts an optional `small_cell_suppression_threshold: int` config (in the child's `user_config.json` block — e.g. `redcap_file.small_cell_suppression_threshold`).
- The framework ships **k=5** as the default (HHS Statistical Disclosure Limitation baseline for CMS data). Validated `≥ 2` to refuse a permissive k=1 misconfiguration; refused at config-load time, not call time.
- Entries below the threshold are collapsed into a single replacement entry of shape `{value: "<small_cell_suppressed>", count: "<below_threshold>", suppressed_count: N}` where N is the number of distinct suppressed values. The replacement shape is consistent across surfaces so an LLM consumer (or human IRB reviewer) sees the same structural signal whether reading `top_values` or cohort `groups`.
- Surfaced at the top level of the child's result envelope as `small_cell_suppression_threshold` so IRB transcript review sees the deployment-time setting visibly. A sibling `small_cell_warning` field surfaces on every result envelope **when the framework default k=5 is in force** rather than an explicit operator setting — same intent as ADR 0003's `_meta.scrubber_warning` for the no-op framework scrubber, but landed at the top of the child envelope alongside other child-level legibility fields (`unknown_field_count`, `field_marked_identifier_stripped`) because the threshold is a child-domain setting the router does not own. Studies that need k=10 / k=11 (pediatric, mental health, rare-disease populations) opt up in `user_config.json`; the warning makes the default-in-force state visible at the point of disclosure rather than buried in a startup log.

### Consequences

**Positive.**

- An IRB auditor reconstructing "which calls ran under which state of the trust root" queries the fingerprint column by hash — a one-line SQL question with a cryptographic answer.
- Tamper attempts on `project_metadata.csv` (the trust root for the entire `RedcapPHIScrubber`) are visible at the attestation surface (`tailor redcap reattest`'s diff print) before the operator confirms.
- The seam generalizes — future children with structured metadata inputs (FHIR profile descriptors, EDF channel manifests, vendor sensor calibration sidecars) inherit the trust-root pattern without re-deciding it.
- Small-cell suppression turns a class of statistical re-identification risk (low-cardinality non-identifier-flagged fields) into a deployment-visible config rather than an institutional implementation detail.
- The default-with-warning posture matches the framework's existing pattern: ship a safe-enough default so deployments work out-of-the-box, surface the default-in-force state in every result envelope so reviewers see it.

**Negative.**

- A legitimate operator edit to `project_metadata.csv` mid-enrollment requires running `tailor redcap reattest`. This is friction the framework adds; the alternative (silent acceptance of any change) defeats the seam.
- The fingerprint primitive is cryptographic provenance, not tamper *prevention*. An operator with write access to the metadata file can always re-attest after tampering. The seam is honest about what it can do (attribution) vs. what it cannot (prevention).
- Framework-default k=5 is a policy choice for the threshold-below-which-to-suppress decision. The default-with-warning posture is the compromise: ship a HHS-grounded default for first-run usability; surface the default-in-force state visibly so the IRB knows the setting was not explicitly attested.

**Neutral.**

- The new audit column is one of several added across the v7.x cycle (`scrubber_id`, `child_scrubber_id`, oracle-tier columns). Each is NULL on dispatch paths it does not apply to; the audit table's column count grows but per-row sparseness stays consistent.

### Promotion condition

Per [ADR 0011](0011-promotion-policy.md): if a **third** child-level scrubber wants the trust-root fingerprint seam (FHIR profile-descriptor-driven scrubbing is the likely next candidate; EDF channel-metadata-driven scrubbing is the second), that is the signal to promote the seam into a `ChildMCP` abstract method (`child_scrubber_fingerprint -> str | None`) and a framework registry — same shape as the [ADR 0013](0013-cache-only-purge-on-consent-revocation.md) promotion of `purge_cache`. Until then, the seam stays per-child wired-by-child — each child whose scrubber exposes a `fingerprint` property has its `child.child_scrubber_fingerprint` read by the router at dispatch time and threaded through the audit row.

### Workshop-vs-lifestyle invariant adherence

Per [ADR 0033](0033-complete-tailor-metaphor-workshop-side.md): the fingerprint primitive is **workshop-shaped** — the tailor records cryptographically which bolt of fabric came from which mill at what state, not whether the fabric was fashionable. The reattest ritual is a workshop ritual — the tailor and the customer confirm together what the fabric is before stitching. Vocabulary stays in the workshop register; the always-forbidden list (Table 5 of `docs/design/tailor-vocabulary.md`) is unaffected.

### What is unchanged

ADR 0003's original load-bearing claim — *the framework cannot define what PHI means generically* — is the same claim today. The 2026-05-14 amendment's child-level scrubber seam is preserved verbatim. The trust-root fingerprint primitive is policy-aware-by-input (the IRB attested to `project_metadata.csv` at protocol creation; the fingerprint records the state of that attestation); small-cell suppression is policy-aware-by-config (the operator sets the threshold per their IRB's k-anonymity guidance). The framework's authority boundary is unchanged.

---

## Amendment 2026-05-15 — Typed-exception taxonomy (`OperatorActionRequired`)

Triggered by the v7.3.2 release banner's two BORDER NOTES deferred from the red-team-reviewer pass and addressed in v7.3.3.

### What this amends

The 2026-05-15 trust-root-attestation amendment above introduces `RedcapMetadataFingerprintMismatch` as a typed exception raised when `project_metadata.csv` drifts since boot. The amendment named the *recovery* path (`tailor redcap reattest`) but did not name the *circuit-breaker interaction* that hides the recovery hint behind a generic "Circuit open" envelope after three consecutive mismatches in 300 seconds. v7.3.3 closes the gap by introducing a *typed-exception taxonomy* that generalizes beyond REDCap.

### The class of failure this amendment names

The framework's `CircuitBreaker` exists to back off external systems that are *flaky* (transient network failures, rate-limit bursts, intermittent upstream errors). Some legitimate runtime conditions are structurally different: the *system* is fine; the *operator* must take an out-of-band action — re-attest a trust root, rotate a credential, restart a process, edit a config — before subsequent calls can succeed. Counting these conditions toward the breaker is a taxonomy mismatch: it hides the recovery affordance behind a generic envelope for the next 5 minutes, exactly the window the operator most needs guidance.

The same mistake at the *catching* side is the v7.3.3 B2 finding: a blanket `except Exception` in a child's `_detect_fingerprint_mismatch()` swallows both "the metadata file became unreadable since boot" (legitimate runtime drift) and "the scrubber constructor's signature changed in a refactor" (programmer bug) under the same handler, silently disabling the mismatch-detection path. The two failures share a shape: *the wrong exception class is being treated as shorthand for a situation*.

### Decision

- New marker class `framework.security.OperatorActionRequired(Exception)`. Exported from `framework/__init__.py`. Co-located with `CircuitBreaker` (the component whose behavior it modifies) for readability — a contributor reading `CircuitBreaker.record_failure` to ask "what trips this?" sees the exemption contract adjacent.
- Constructor takes a keyword-only `recovery_action: str` argument and validates it is a non-empty, non-whitespace string at construction time. A subclass author who cannot name a remediation command gets a `TypeError` at construction, not silent runtime defeat. The required attribute is the misuse guard: misclassification (a child author marking an upstream-flaky exception as `OperatorActionRequired` and thereby disabling the breaker for paths that legitimately need it) becomes a constructor error rather than a silent invariant break.
- Children that already raise typed exceptions for operator-action conditions inherit from `OperatorActionRequired` and pass their remediation command up the `recovery_action` channel. v7.3.3 reparents `RedcapMetadataFingerprintMismatch` (`recovery_action="tailor redcap reattest"`); future children with the same shape (FHIR scope-expired, EDF channel-manifest drift, vendor calibration mismatch) inherit the contract without re-deciding it.
- The router's exception handler at both dispatch sites (`_dispatch` public path and `dispatch_internal` cross-child path) skips `CircuitBreaker.record_failure` when `isinstance(exc, OperatorActionRequired)`. The audit row still records `outcome=ERROR` with the full provenance kwargs (`scrubber_id`, `child_scrubber_id`, `source_metadata_fingerprint`, `subject_id`) — the exemption is breaker-only, not audit-only. The wire error envelope still carries the exception's `str()` so the LLM transcript shows the recovery hint.
- Children that need to *detect* an operator-action condition by speculative work (e.g. `RedcapFileChild._detect_fingerprint_mismatch` constructing a candidate `RedcapPHIScrubber` to compare fingerprints) do **not** wrap the speculative work in a blanket `except Exception`. If the speculative construction has no documented raise surface, no try/except is added; future programmer-error exceptions propagate through the router's exception handler rather than silently disabling detection. The B2 fix at `children/redcap/child.py:_detect_fingerprint_mismatch` drops the previously-wrapped try/except for exactly this reason — `RedcapPHIScrubber.__init__` already handles its documented failure classes internally and raises essentially nothing on bad input; the previous defensive wrapper caught only `TypeError` from signature changes, which is precisely the class that must propagate.

### Consequences

**Positive.**

- The recovery affordance stays reachable. An operator who hits three consecutive mismatches — e.g. by running `tailor redcap reattest` while a Claude Desktop session is mid-call — sees the `tailor redcap reattest` hint on call N+1, not a 5-minute generic-envelope window.
- The seam generalizes across children. The next child whose execute path legitimately needs to signal "operator must act" inherits the breaker exemption + the wire-envelope contract by raising a subclass; no per-child router edits, no per-child reasoning about which exception classes the breaker should ignore.
- Misclassification fails loudly. A child author who reaches for `OperatorActionRequired` for an *upstream-flaky* exception either provides a sensible `recovery_action` (and the operator gets a working hint on the next call) or cannot provide one and is forced to re-examine the classification. The required attribute is the contract enforcement.
- The all-call-sites-sweep invariant (v7.3.1) extends naturally: the audit row carries the same provenance kwargs on the exempt path, so the AST-class W5 contract test continues to enforce one rule across both `record_failure`-counted and `record_failure`-exempt exception classes.

**Negative.**

- One new public API class. Downstream child-authors who already define typed exceptions can opt in by changing the parent class; the marker is additive and does not break existing children.
- A child author who deliberately misclassifies (passes a syntactically valid `recovery_action` that is operationally bogus) defeats the breaker for that path. The constructor cannot validate that the named command actually exists; the contract is honor-bound the same way the `ADR 0003` PHI-scrubber seam is. Future tightening would require the marker class to verify the command resolves via the CLI registry, which is a level of self-knowledge the framework does not currently maintain.

**Neutral.**

- The marker class lives in `framework/security.py` next to `CircuitBreaker` rather than `framework/interfaces.py` next to `ChildMCP`. The semantically honest home is the file that defines the *behavior* the class modifies; the alternative placement was considered and rejected during proposal-mode audit.

### Reversal condition

If a future child raises `OperatorActionRequired` for a transient state that *should* trip a breaker — e.g. an upstream API saying "re-authenticate" where the right behavior is back-off-then-retry rather than recovery-hint-always-reachable — the class hierarchy needs a finer split (`OperatorActionRequired` vs `OperatorActionRequiredTransient`). The split would land in a superseding amendment naming the specific child and the specific re-authentication semantics that drove the requirement.

If the misclassification-as-non-issue holds across the next three child additions (FHIR + EDF + vendor sensor), retire the misuse-guard `recovery_action` requirement to a recommended-but-not-enforced docstring convention — same shape as ADR 0011's reversal condition for the promotion bar.

### Promotion condition

Per [ADR 0011](0011-promotion-policy.md): if a **second** child outside REDCap raises `OperatorActionRequired` as part of normal operation, the seam is generalized enough to belong in `framework/interfaces.py` next to `ChildMCP` rather than in `framework/security.py`. Until then, the marker stays in `security.py` because its only consumer is the router's breaker exemption logic.

### Workshop-vs-lifestyle invariant adherence

Per [ADR 0033](0033-complete-tailor-metaphor-workshop-side.md): the marker class is **workshop-shaped** — the tailor distinguishes "the mill (upstream API) is having a bad day" (breaker territory) from "the customer (operator) needs to bring fresh fabric" (recovery-hint territory). The vocabulary stays in the workshop register; `recovery_action` names a workshop ritual, not a lifestyle suggestion.

### What is unchanged

ADR 0003's original PHI-scrubber-seam claim, the 2026-05-14 child-level scrubber amendment, the 2026-05-15 trust-root-attestation amendment, and the small-cell-suppression posture are all preserved verbatim. The typed-exception taxonomy is additive to the router's existing exception-handling shape; the audit-row provenance, the wire-error-envelope shape, and the post-execute-hook contract are unchanged.

# ADR 0018: Cross-tier GPS precision asymmetry — does Safe Harbor apply uniformly, or does consent substitute?

- **Status:** Proposed
- **Date:** 2026-05-01
- **Related:** [ADR 0003 (PHI scrubber as seam)](0003-phi-scrubber-seam.md), [ADR 0011 (promotion policy — severity grounding)](0011-promotion-policy.md), [ADR 0012 (vault PHI-scrubber bypass)](0012-vault-phi-scrubber-bypass.md), [CLAUDE.md § Three-Tier Access Model](../../CLAUDE.md#three-tier-access-model)

## Context

The v6.3.1 hygiene pass hardened the Tier-1 surface against a residence-triangulation re-identification path. `strava_stop_analysis` at [`children/running/processing.py:544-558`](../../src/tailor/children/running/processing.py) coarsens stop GPS to 3 decimals (~111 m), buckets `distance_from_home_m` to 100 m, and drops the `near_home` boolean — the inline comment at line 545-549 cites HIPAA Safe Harbor §164.514(b)(2)(i)(B) and frames the change as closing a re-identification path on the unconsented surface.

The same comment also names the asymmetry without recording a position on it: *"The full-precision stream is available behind the Tier-2 consent gate via `strava_downsampled_streams`."* Tier-2 and Tier-3 do not coarsen GPS. Both `_handle_downsampled_streams` ([`children/running/child.py:918`](../../src/tailor/children/running/child.py)) and `_handle_full_streams` ([`children/running/child.py:941`](../../src/tailor/children/running/child.py)) route through `RunningProcessing.reduce_precision` at [`children/running/processing.py:45`](../../src/tailor/children/running/processing.py), which keeps `latlng` at 5 decimals (~1.1 m — residence-precision, finer than consumer GPS hardware actually resolves).

The operational consequence is that the same `activity_id`, escalated past the consent gate, exposes residence-precision GPS that the Tier-1 surface was hardened to suppress. An analyst running `strava_stop_analysis` and then `strava_downsampled_streams` against the same activity sees coarsened stop locations in the first call and full-precision GPS streams (which include the same stops) in the second. The Tier-1 hardening is bypassable by one consent click on the same activity.

This is not a bug in either tier in isolation. Each tier is internally consistent. The asymmetry is between them, and it reflects two unreconciled readings of what Safe Harbor de-identification means under a tiered access model:

- **Reading A — uniform Safe Harbor.** Safe Harbor §164.514(b)(2)(i)(B) sets a content-shape floor: precise residence-derivable geographic data must be suppressed regardless of who is reading it. Consent does not lift the floor; it gates *additional* data on top of an already-de-identified baseline. Under this reading, every tier coarsens GPS to 3 decimals.
- **Reading B — consent-as-shield.** Safe Harbor sets the floor for *unconsented* data flows. Once a participant has granted explicit biometric consent for a domain, the data is no longer governed by Safe Harbor's de-identification clause but by the consent scope itself. Consent substitutes for de-identification at Tier 2 and above. Under this reading, Tier-1 coarsens; Tier 2 and Tier 3 deliver the precision the analyst consented to see.

The shipped code reflects neither reading explicitly. It reflects the temporal sequence of two changes — the v6.3.1 Tier-1 hardening landed without revisiting the Tier-2/3 reducer — and the comment at line 549 is the artifact of that gap rather than a recorded position. ADR 0003's seam does not police this case: the PHI-scrubber operates on result content uniformly across tiers and does not encode a tier-aware precision policy.

The question this ADR answers: *does HIPAA Safe Harbor de-identification apply uniformly across tiers (require coarsening at every tier, with consent layered on top), or only at the unconsented Tier-1 surface (with consent at Tier 2 substituting as the shield)?* This ADR is **Proposed** until the boss picks a reading. On acceptance, the picked reading is amended into the Decision section and an implementation issue is filed.

## Decision

The boss must pick one of two readings. The ADR ships in **Proposed** status precisely because the code reflects an unconsidered asymmetry rather than a recorded position; collapsing the question silently — by patching the code one way without an ADR, or by leaving the asymmetry in place without naming it — is exactly the failure mode this ADR exists to prevent.

The two readings are stated below in plain English. Each names what changes in the code, what changes in the deployment story, and what each reading commits the project to defending in front of an IRB.

**Reading A — uniform Safe Harbor across tiers.**

Safe Harbor §164.514(b)(2)(i)(B) is a content-shape floor. Every tier coarsens GPS to 3 decimals (~111 m) regardless of consent. Consent at Tier 2 widens the *kinds* of data the analyst sees (HR streams, pace streams, downsampled GPS at coarser temporal resolution); it does not restore residence-precision spatial data. Tier-3 escalation widens *temporal* resolution (per-second sampling) but inherits the same spatial floor.

- `RunningProcessing.reduce_precision` at [`children/running/processing.py:45`](../../src/tailor/children/running/processing.py) is amended: the `latlng` reducer rounds to 3 decimals, not 5.
- The `_handle_downsampled_streams` and `_handle_full_streams` paths inherit the change without further edits — both already route through `reduce_precision`.
- The Tier-1 `strava_stop_analysis` coarsening at [`processing.py:544-558`](../../src/tailor/children/running/processing.py) is preserved as-is; the comment at line 549 is amended to remove the *"available behind the Tier-2 consent gate"* clause, since that is no longer true.
- Three-Tier Access Model documentation in CLAUDE.md gains a sentence: *"GPS coordinates are coarsened to 3 decimals (~111 m) at every tier per HIPAA Safe Harbor §164.514(b)(2)(i)(B); consent at Tier 2 widens the kinds and temporal resolution of streams the analyst sees, not the spatial precision of geographic data."*
- The IRB-facing claim the project commits to defending: *"This framework de-identifies residence-precision GPS at every access tier. Consent does not unmask the residence."*

**Reading B — consent-as-shield at Tier 2 and above.**

Safe Harbor governs the unconsented surface only. Tier-1 coarsens GPS to 3 decimals as a Safe Harbor floor for tools the analyst can call without explicit biometric consent. Tier 2 and Tier 3 require explicit biometric consent for the domain (`approve_consent_running`), and once granted, the consent scope itself is the governance instrument — not the de-identification clause. Residence-precision GPS at Tier 2 and Tier 3 is permitted, because the participant has explicitly consented to the analyst seeing it.

- `RunningProcessing.reduce_precision` is unchanged. GPS at Tier 2 and Tier 3 stays at 5 decimals.
- `RunningChild.consent_info` at [`children/running/child.py`](../../src/tailor/children/running/child.py) is amended to name GPS precision in the consent prompt: the consent text must say *"residence-precision GPS coordinates"* explicitly so the participant's consent covers what the data actually is. Hidden precision behind a generic "GPS data" label is not informed consent.
- A regression test asserts that the consent-gate's `LLMInstruction` for the running domain mentions GPS at residence precision in `must_do` or in a documented data-types list — drift from this wording is a test failure.
- The comment at [`processing.py:549`](../../src/tailor/children/running/processing.py) is amended to a one-line link to this ADR's Reading B paragraph rather than a passing aside.
- Three-Tier Access Model documentation in CLAUDE.md gains a sentence: *"GPS coordinates are coarsened to 3 decimals at Tier 1 per HIPAA Safe Harbor §164.514(b)(2)(i)(B). At Tier 2 and Tier 3, residence-precision GPS is delivered because the participant has granted explicit biometric consent for the running domain (`approve_consent_running`); the consent scope substitutes for the Safe Harbor floor."*
- The IRB-facing claim the project commits to defending: *"This framework de-identifies residence-precision GPS on the unconsented surface. Consent for the running domain explicitly covers residence-precision GPS, and the consent text says so."*

**Mechanism — what changes regardless of which reading wins.**

- This ADR is the architectural record. On acceptance, the chosen reading is moved out of the conditional framing above and into a single-reading Decision section; the un-chosen reading is moved into Alternatives considered with one paragraph naming why it lost.
- An implementation issue is filed citing the chosen reading and the line numbers above. The implementation lands in a follow-up patch release with a `phi-irb-risk-reviewer` invocation specifically tasked against the picked reading.
- A test is added that locks the picked reading in. Under Reading A, the test asserts `reduce_precision` rounds `latlng` to 3 decimals. Under Reading B, the test asserts the consent prompt for the running domain names residence-precision GPS in plain text.
- The comment at [`processing.py:545-549`](../../src/tailor/children/running/processing.py) is rewritten in either case so that no future contributor reads it as a recorded position when it currently reads as an artifact of the temporal gap between two changes.

## Consequences

**Positive.**

- The asymmetry stops being silent. A reviewer reading the codebase finds the cross-tier policy named in an ADR rather than inferred from a comment that names the gap without taking a position. The governance-gap failure mode — *"the IRB asks why Tier 1 coarsens and Tier 2 doesn't, and the team has no answer"* — is closed regardless of which reading wins.
- The IRB-facing claim becomes citable. The project's Safe Harbor posture is currently a sentence in `docs/design/research-framing.md` and a comment in `processing.py`; after this ADR lands in Accepted status, the posture is one paragraph with an ADR number a reviewer can cite.
- ADR 0003's seam gains a tier-policy companion. The PHI-scrubber operates on content uniformly; this ADR records the policy that operates on tiers. A contributor adding a third axis (e.g. timestamp precision under different consent scopes) has a template for how to document the decision.
- `phi-irb-risk-reviewer` gains a citable anchor for cross-tier precision questions. The agent's six-lens audit currently treats Safe Harbor as an unconsented-surface concern by default; ADR 0018 widens the question and gives the agent a place to point when reviewing future child changes.

**Negative.**

- Reading A reduces analyst utility on a small but real class of analysis. Mapping a long run with stops at coffee shops, drinking fountains, and traffic lights at 3-decimal precision smears the stops together at the ~111 m scale; an analyst studying within-route pacing patterns loses fidelity they currently have at Tier 2. Mitigated by the fact that the analytical questions Tier 2 most often answers (HR drift, decoupling, pace splits) do not depend on residence-precision GPS.
- Reading B requires the consent prompt to explicitly name residence-precision GPS in language a participant can understand, and a regression test to lock that wording in. Drift from that wording — a refactor that genericises *"residence-precision GPS coordinates"* back to *"GPS data"* — silently breaks the consent-as-shield argument. Mitigated by the regression test, but the test is necessary; without it the reading is not defensible.
- Either reading commits the project to a position that a future child (a CGM child with location-stamped meal markers, an EDF child with home-monitoring metadata) must be reviewed against. The reading is not running-domain-specific even though the trigger was. Acceptable because the alternative is per-child re-derivation of the same question.

**Neutral.**

- This ADR does not change runtime behaviour at the moment it lands; the implementation follows after the boss picks a reading. The Proposed status is the load-bearing part — the boss is making a substantive call, not rubber-stamping a shipped change.
- The ADR is scoped to GPS precision under the running child. The same shape question (a Tier-1 hardening that does not propagate to Tier 2/3) could exist for other content types — Strava activity titles, CSV file paths, vault evidence blocks — but those cases are out of scope for this ADR and would need their own records if they surface.
- ADR 0008's deterministic-by-construction invariant is unaffected. Both readings preserve `reduce_precision` as a `@staticmethod` pure function; only the rounding constant changes (Reading A) or the constant is preserved (Reading B). The reproducibility-provenance auditor's invariant holds either way.
- ADR 0009's `subject_id` propagation is unaffected. Subject scoping continues to flow through audit rows regardless of which reading wins.

## Alternatives considered

**Uniform 3-decimal coarsening across all tiers (Reading A as the only option).** This is the most defensive reading and the one a hostile IRB committee would most readily approve. It is presented in the Decision section as one of two readings the boss picks between, not as an alternative, because the project's stated audience includes IRB-friction-sensitive deployments where the defensive choice may be the right one. Listing it here would duplicate the Decision section.

**Consent-as-shield as the only option (Reading B as the only option).** Same reason. Reading B is the de-facto current state of the code; recording it as the chosen reading is a coherent position provided the consent prompt is amended to name residence-precision GPS explicitly. It is in the Decision section, not here, because the boss's decision is between A and B — the alternatives below are options that are *not* on the table.

**Tier-binding precision via consent metadata.** A third reading: the consent prompt for the running domain accepts a precision parameter (e.g. `gps_precision: "residence" | "neighborhood" | "city"`), and the analyst's call into Tier 2 or Tier 3 is gated against the precision the participant consented to. This is the most flexible option and matches how some IRB-governed deployments think about graded consent in practice. Rejected for this ADR because (a) it adds a configuration surface to a question that currently has two clean readings, (b) it requires consent-prompt UI work the project does not yet have a model for, and (c) it defers the load-bearing question — at every precision level the participant could grant, the same Safe Harbor question recurs (does the floor apply uniformly, or does consent substitute?). The flexible option does not answer the question; it relocates it. If the project later adopts graded consent, the ADR that codifies it can supersede this one.

**Escalate residence-precision Tier-2 calls to Tier 3.** Move `strava_downsampled_streams` from Tier 2 to Tier 3 so that residence-precision GPS requires both consent *and* explicit cost approval, not just consent. Rejected because Tier 3 is a token-cost gate, not a precision-sensitivity gate. Adding cost-approval friction to a question about geographic precision conflates two unrelated concerns and pollutes the tier model. The three-tier access model in CLAUDE.md is grounded on token cost (Tier 1: free; Tier 2: consent for visualization-grade streams; Tier 3: consent + cost for per-timestamp streams), not on PHI sensitivity. Re-grounding it on PHI sensitivity would require redefining all three tiers across all children — much larger lift than the asymmetry warrants, and one that breaks ADR 0005's pre-estimation framing.

**Defer the decision until a real deployment surfaces an IRB objection.** Rejected on the same severity-grounding reasoning as ADR 0011 § Context: a reading that has zero incidents because the framework has zero real deployments cannot accumulate the three-session evidence base a frequency-bar would demand. The project's first real deployment is the worst possible time to discover the team has not picked a reading. The boss reads this ADR with coffee; the IRB reviewer reads the deployment under deadline pressure. Codification now is the cheap version of the conversation.

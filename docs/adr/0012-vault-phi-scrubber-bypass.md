# ADR 0012: Vault dispatch bypasses the PHI-scrubber seam — invariants and reversal conditions

- **Status:** Accepted
- **Date:** 2026-04-30
- **Related:** [ADR 0003 (PHI-scrubber seam)](0003-phi-scrubber-seam.md), [ADR 0007 (Rendering-layers policy)](0007-rendering-layers-policy.md), [ADR 0009 (Vault subject-keying)](0009-vault-subject-keying.md), [CLAUDE.md § Architecture](../../CLAUDE.md#architecture)

## Context

ADR 0003 established `PHIScrubber.scrub()` as a seam in the router's
security pipeline: every successful biosensor-child result passes
through it before tokens are counted and the audit row is finalized.
ADR 0003 also noted, in passing, that `_dispatch_vault()` does not
invoke the scrubber — vault tools handle analyst notes, which are
metadata, not participant biometric data. That sentence is correct,
but it lives inside the parent ADR as a one-line aside. The actual
codebase carries a stronger asymmetry: `_dispatch()` calls
`self._phi_scrubber.scrub(result)` at
[`router.py:519-520`](../../src/biosensor_mcp/framework/router.py),
and `_dispatch_vault()` deliberately does not, with a docstring
comment at [`router.py:582-592`](../../src/biosensor_mcp/framework/router.py)
listing four things skipped "by design" — circuit breaker, consent
gate, cost gate, post-execute hooks — but not naming the
PHI-scrubber bypass at all.

This is a governance gap. A future contributor extending vault
dispatch reads the comment, sees four named skips, and has no way to
know that a fifth skip is also load-bearing. The hygiene-pass review
on v6.3.1 surfaced exactly this risk: the bypass is correct under
present invariants but invisible at the place where someone would
break it. ADR 0003 asserts the bypass without grounding the
*invariants it depends on* or naming the *conditions under which it
would have to reverse*.

The vault tier handles three categories of content: analyst-typed
prose (theme bodies, moment descriptions, inbox lines, failure-mode
diagnoses), structured frontmatter the framework writes (subject_id,
status, timestamps, slugs), and rendered-from-index summaries
(snapshots, dashboards, evidence blocks derived from prior
biosensor-tier tool calls that have **already** passed through the
scrubber on their way out). None of these categories contains a raw
biometric stream. The vault never reads from a Strava API response
or a CSV row directly — it only ever stores what the analyst typed
or what a biosensor-tier tool already returned.

The question this ADR answers: *under what invariants is the
PHI-scrubber bypass on the vault-dispatch path correct, and what
future change would force the bypass to be reconsidered?*

## Decision

The router's `_dispatch_vault()` path does not invoke the
PHI-scrubber, and this is a deliberate architectural choice grounded
on a named invariant rather than an oversight. The bypass holds for
exactly as long as the invariant holds.

- **Invariant.** Vault tools never accept raw biosensor stream
  content as input, and never write raw biosensor stream content
  into a vault note. Vault inputs are limited to (a) analyst-authored
  text, (b) structured parameters validated against
  `VaultLayer.param_schemas`, and (c) summaries derived from prior
  biosensor-tier tool results that have already passed through the
  scrubber via `_dispatch()` at
  [`router.py:519-520`](../../src/biosensor_mcp/framework/router.py).
- **Why the bypass is correct under the invariant.** PHI scrubbing
  is a content-shape concern — the scrubber exists to sanitise raw
  participant data on its way out of a child. Analyst notes are not
  raw participant data; subjecting them to a scrubber written for
  HR streams or CGM rows would either be a no-op (default scrubber)
  or actively wrong (an institutional subclass that strips fields
  the analyst deliberately recorded as part of their analytical
  reasoning).
- **Audit visibility is preserved.** The vault-dispatch path still
  records `scrubber_id` on every audit row and stamps it into the
  `_meta` block of every successful result
  ([`router.py:619`](../../src/biosensor_mcp/framework/router.py),
  [`router.py:631`](../../src/biosensor_mcp/framework/router.py)).
  A reviewer reading the audit log can distinguish a vault row from
  a child row, and can confirm that the scrubber configuration on
  the deployment was the same one in effect for the biosensor calls
  that produced the evidence the vault stores.
- **The bypass is documented in code at the dispatch site.** The
  `_dispatch_vault()` docstring at
  [`router.py:581-592`](../../src/biosensor_mcp/framework/router.py)
  is amended to name the PHI-scrubber bypass alongside the four
  existing named skips, with a one-line link to this ADR. Future
  contributors reading the dispatch path see the asymmetry called
  out, not implied.
- **Reversal condition.** If a future vault tool ever ingests a
  Tier-2 or Tier-3 biosensor stream verbatim into a vault note —
  bypassing the biosensor-child `execute()` path that ordinarily
  routes such payloads through the scrubber — the invariant breaks
  and this ADR must be revisited before the tool ships. Two concrete
  shapes that would trigger reversal: a `vault_attach_stream` tool
  that copies raw `strava_full_streams` output into a moment, or any
  vault writer that reads from a child's local cache (e.g.
  `activities.db`) without going through the child's tier-gated
  tools.

## Consequences

**Positive.**

- The bypass is now first-class: a contributor reading the dispatch
  path or grepping for `phi_scrubber` finds the decision recorded in
  an ADR rather than inferred from absence. The governance-gap
  failure mode — "someone reverses this without realising it's
  load-bearing" — is closed.
- The invariant is named in one sentence that any future PR can be
  audited against: *vault inputs are not raw biosensor streams.*
  Reviewers do not have to re-derive the reasoning each time.
- `phi-irb-risk-reviewer` and `reproducibility-provenance-auditor`
  both gain a citable anchor for the vault-dispatch case. Where the
  hostile-IRB lens previously had to defer to ADR 0003's aside, it
  can now cite ADR 0012's reversal-condition list directly.
- The audit-log story stays uniform: every row carries
  `scrubber_id`, regardless of whether the scrubber actually ran on
  the result. A reviewer reconstructing a deployment's PHI posture
  reads one column on every row, not two cases by domain.

**Negative.**

- The vault-dispatch path is now coupled by reference to a named
  invariant. A vault tool whose author misjudges whether their
  inputs are "raw stream content" can ship a violation that the
  bypass silently permits. Mitigated by listing the two concrete
  reversal shapes in the Decision section above so the
  pattern-match is unambiguous; further mitigated by
  `phi-irb-risk-reviewer`'s six-lens audit firing on any change
  touching `framework/vault/`.
- The ADR records a constraint on a future tool that does not yet
  exist. A reader can reasonably ask whether this is over-engineering
  for a hypothetical case. The defence: the constraint is cheap to
  state and the failure mode is silent — a vault tool that ingests
  a raw stream without re-routing through child execute leaves no
  audit signal that scrubbing was skipped, because the row's
  `scrubber_id` looks normal. Naming the reversal condition before
  the tool exists is what makes the future review possible.

**Neutral.**

- This ADR does not change runtime behaviour. The bypass already
  ships in v6.3.0 and earlier; ADR 0012 makes its grounding
  explicit. The accompanying docstring amendment to
  `_dispatch_vault()` is the only code change in scope.
- The bypass is one of five things `_dispatch_vault()` skips
  relative to `_dispatch()`. The other four (circuit breaker,
  consent gate, cost gate, post-execute hooks) have their own
  rationales documented inline. ADR 0012 covers only the scrubber
  case because it is the one with a non-obvious failure mode and
  cross-ADR dependencies; the other four are operationally obvious
  (vault tools are local, metadata-only, Tier 1, and write to the
  vault themselves so a recursive post-execute hook would loop).
- ADR 0007's source-of-truth invariant is unaffected. Vault notes
  remain plain markdown regardless of scrubber behaviour, because
  the scrubber operates on the dict result returned to the LLM
  client, not on what the writer persists to disk.
- ADR 0009's subject-keying contract is unaffected. `subject_id`
  flows through `_dispatch_vault()` to audit and frontmatter
  exactly as before.

## Alternatives considered

**Run the PHI-scrubber on vault results too, for symmetry.**
Rejected. A scrubber configured for biosensor child output is the
wrong tool for analyst notes — at best a no-op, at worst destructive
of analytical content the analyst deliberately recorded. Symmetry
for its own sake is not a governance benefit; it would force
institutional subclassers to reason about two unrelated content
shapes with one method, and would invite scrubbers that strip
subject identifiers from analyst-written prose where the analyst
*intended* the identifier to appear.

**Make the bypass a configuration flag with a default.** Rejected.
A flag implies the answer is deployment-dependent. It is not — the
bypass is correct under a structural invariant about what vault
inputs *are*, not under a deployment policy. A flag would invite
deployers to flip it without understanding the invariant, and would
add a configuration surface to a question that has one right answer
for the framework's current scope.

**Leave the decision in ADR 0003's one-line aside.** Rejected. The
hygiene-pass review found the gap precisely because the aside is
not where a contributor extending vault dispatch would look. ADR
0003 is about the seam's design; the bypass on the vault path is a
separate decision that depends on a separate invariant (vault
inputs are not raw streams) and has a separate reversal condition
(a future vault tool that ingests a raw stream). Two decisions, two
ADRs — the same shape ADR 0009 took relative to ADR 0002's deferred
question.

**Defer until a vault tool actually proposes ingesting a raw
stream.** Rejected. The reversal condition is the load-bearing part:
naming it now is what allows a future PR to be reviewed against the
constraint, rather than against a memory of what someone meant in
ADR 0003. Deferral would re-create the original governance gap on
a different timeline.

# ADR 0012: Framework-tier dispatch bypasses the PHI-scrubber seam — invariants and reversal conditions

- **Status:** Accepted (originally vault-only; extended in v6.10.2 to cover local_llm + setup_help; extended in v7.4.0 to cover audit_query)
- **Date:** 2026-04-30 (original); 2026-05-06 (v6.10.2 amendment extending to LocalLLMLayer + SetupHelpLayer); 2026-05-16 (v7.4.0 amendment extending to AuditQueryLayer)
- **Related:** [ADR 0001 (Audit log as backbone)](0001-audit-log-as-backbone.md), [ADR 0003 (PHI-scrubber seam)](0003-phi-scrubber-seam.md), [ADR 0007 (Rendering-layers policy)](0007-rendering-layers-policy.md), [ADR 0009 (Vault subject-keying)](0009-vault-subject-keying.md), [ADR 0022 (Local-LLM guardian)](0022-local-llm-guardian.md), [ADR 0039 (Audit log queryable under column allowlist)](0039-audit-log-is-llm-queryable-under-column-allowlist.md), [CLAUDE.md § Architecture](../../CLAUDE.md#architecture)

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
[`router.py:519-520`](../../src/tailor/framework/router.py),
and `_dispatch_vault()` deliberately does not, with a docstring
comment at [`router.py:582-592`](../../src/tailor/framework/router.py)
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
  [`router.py:519-520`](../../src/tailor/framework/router.py).
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
  ([`router.py:619`](../../src/tailor/framework/router.py),
  [`router.py:631`](../../src/tailor/framework/router.py)).
  A reviewer reading the audit log can distinguish a vault row from
  a child row, and can confirm that the scrubber configuration on
  the deployment was the same one in effect for the biosensor calls
  that produced the evidence the vault stores.
- **The bypass is documented in code at the dispatch site.** The
  `_dispatch_vault()` docstring at
  [`router.py:581-592`](../../src/tailor/framework/router.py)
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

## Amendment — v6.10.2 (2026-05-06): extension to LocalLLMLayer and SetupHelpLayer

The v6.10.2 release added a third framework-tier dispatch path
(`_dispatch_setup_help`) that also skips the PHI-scrubber. The
v6.10.2 phi-irb-risk-reviewer pass surfaced a Lens 4 finding: ADR 0012
named only the vault case, but at the time of the v6.10.2 audit
two additional framework-tier paths bypassed the scrubber —
`_dispatch_local_llm` (added v6.6.0 per ADR 0022) and the new
`_dispatch_setup_help`. The asymmetry is now a *pattern*, not a
one-off, and the ADR 0012 reversal-condition discipline must extend
to it.

The vault-specific invariant in the original Decision section above
is preserved. Two additional invariants — one per new layer —
ground the bypass on those paths under the same shape:

- **LocalLLMLayer invariant.** The local-LLM layer never writes raw
  biosensor stream content into its `OracleResponse`. Numerical
  claims surfaced in the response are flattened from
  `resolved_context` — a dict whose values came from biosensor-tier
  Tier-1 tool calls that **already** passed through the scrubber on
  their way out of the originating child. Narrative prose is
  LLM-generated and explicitly labelled non-citable in `_meta.oracle`;
  it is the operator's responsibility to configure a backend whose
  prompt template instructs the model not to invent identifiers.
  ADR 0022 § "Hallucination-prevention invariant" formalises the
  numerical-claims-must-trace-to-resolved_context property; this ADR
  amendment grounds the scrubber bypass on the same invariant.
- **SetupHelpLayer invariant.** The setup-help layer accepts no
  parameters (the param schema is empty by construction, enforced at
  [`framework/setup_help/__init__.py`](../../src/tailor/framework/setup_help/__init__.py))
  and returns only static recipient instructions plus server-state
  diagnostics. No biosensor stream content ever enters or exits the
  layer. Filesystem paths surfaced in the diagnostic block are
  home-redacted via `_redact_home` so the recipient's OS username
  does not egress to the LLM client (closes the v6.10.2 phi-irb
  Lens 1 finding under HIPAA Safe Harbor §164.514(b)(2)(i)(R)).

**Why each bypass is correct under its invariant.** Same shape as the
vault case: the scrubber is a content-shape concern designed for raw
biosensor streams. The local-LLM layer's outputs are
already-scrubbed numerical claims plus non-citable narrative; the
setup-help layer's outputs are constants and server-state. Running
the scrubber on either would be a no-op under the default scrubber
or actively wrong under an institutional subclass that rewrites
field names.

**Audit visibility is preserved on all three paths.** Every audit
row from `_dispatch_vault`, `_dispatch_local_llm`, and
`_dispatch_setup_help` records `scrubber_id`, parallel to the
biosensor-child path. The audit log carries a uniform
PHI-configuration-attestation column regardless of whether the
scrubber actually ran on the result. A reviewer reconstructing a
deployment's PHI posture reads one column on every row.

**Reversal conditions for the two new paths.**

- *LocalLLMLayer reversal.* If a future backend or layer modification
  surfaces raw biosensor stream content in the response (for example,
  by attaching the originating Tier-2/Tier-3 stream payload as
  evidence in `resolved_context` and echoing it verbatim into
  `narrative`), the invariant breaks and ADR 0012 must be revisited
  before the change ships. Concrete shape that would trigger
  reversal: a `resolved_context` entry whose value is a Tier-3 stream
  dict from `strava_full_streams` or `csv_raw_stream` written into
  the response without going through the originating child's
  scrubber.
- *SetupHelpLayer reversal.* If the diagnostic block ever surfaces
  the contents (rather than mere existence / sizes / paths) of any
  user-config file, vault note, or audit row, the invariant breaks.
  The current implementation surfaces only existence flags, paths
  (home-redacted), and env-var references; expanding the diagnostic
  to echo a user_config.json body verbatim, for example, would route
  participant-adjacent content through a layer with no scrubber.

The discipline is: a fourth framework-tier layer added in a future
release that bypasses the scrubber must amend this ADR with its own
invariant + reversal-condition section, in the same shape as the
v6.6.0 / v6.10.2 amendments. The asymmetry must remain visible at
the dispatch site (each `_dispatch_<layer>` docstring names the
bypass as a "skipped by design" item) and grounded here.

## Amendment — v7.4.0 (2026-05-16): extension to AuditQueryLayer

The v7.4.0 release adds the fourth framework-tier dispatch path
(`_dispatch_audit_query`) that also skips the PHI-scrubber. The
v7.4.0 work is the closure of the v7.3.4 banner-named audit-log-
over-promise gap: before this layer the recipient prompt "Show me
what just happened in the audit log" had no MCP tool to land on, and
v7.3.4 reworded the fitting-room banner to vault-list-moments as a
stopgap. The new layer is the structural fix; the bypass discipline
that ADR 0012 codified for vault / local_llm / setup_help extends to
it under the standing discipline named in the v6.10.2 amendment's
final paragraph above.

Per [ADR 0039](0039-audit-log-is-llm-queryable-under-column-allowlist.md),
the surfacing decision itself (audit log becomes LLM-queryable) lives
in a sibling ADR. This amendment ratifies *the bypass invariant for
the new layer* — why running the PHI scrubber on the layer's response
would be wrong — and the reversal condition under which the
amendment would have to revisit.

- **AuditQueryLayer invariant.** The audit-query layer returns a
  fixed *column allowlist* — id, timestamp, domain, tool_name, tier,
  token_estimate, outcome, duration_ms, subject_id, scrubber_id,
  child_scrubber_id, source_metadata_fingerprint, plus a derived
  `has_error: bool`. The raw `params` and `error` columns from
  `audit_log` are NEVER surfaced; the error column is reduced to
  `has_error` so the v7.3.1 path-redaction posture (raw on-disk
  paths in legacy rows) stays intact and the framework
  PHIScrubber's no-op default (ADR 0003) cannot leak via the
  surface. The allowlist is enforced by explicit SELECT in
  `AuditLog.query()` at
  [`framework/audit.py`](../../src/tailor/framework/audit.py) — never
  `SELECT *` — so a future ALTER TABLE adding a sensitive column does
  not silently re-egress to the LLM.

**Why the bypass is correct under this invariant.** Same shape as the
prior three cases: the scrubber is a content-shape concern designed
for raw biosensor streams. The audit-query layer's outputs are
framework-emitted structured metadata (column names, enums, fixed-
shape timestamps, pseudonymous subject ids per ADR 0009, scrubber
identity strings). Running the no-op default scrubber would be a
no-op; running an institutional subclass that rewrites field names
would corrupt the IRB-grade query response without any privacy
benefit (no biosensor content is present to scrub).

**Audit visibility is preserved on this path.** Every audit row from
`_dispatch_audit_query` records `scrubber_id="noop"` plus the full
v7.3.2 W5 invariant kwargs (`source_metadata_fingerprint=None`,
threaded explicitly at every PARAM_INVALID / SUCCESS / ERROR site —
extends the v7.3.1 all-call-sites-sweep rule to the new dispatch
path; updated AST-class contract at
[`tests/test_serve_v732_wire_audit.py::TestW5AllCallSitesSweep`](../../tests/test_serve_v732_wire_audit.py)
locks the invariant at 31 audit-record sites / 6 _meta stamping
sites). `subject_id` passes through from caller params so an
audit-query call scoped to S004 stamps that row's `subject_id="S004"`
— the audit-query call itself participates in the same subject
trail it queries against.

**Reversal conditions for the audit-query path.**

- *Trust-violating reversal.* If a deployment surfaces real PHI
  through the column allowlist — e.g., a future child writes PHI
  into the `tool_name` or `domain` column directly (the validator
  guards `subject_id` with the ADR 0009 pattern but does not guard
  other columns), or a child stores MRN-shaped values in
  `subject_id` despite the pseudonym contract — the invariant
  breaks and ADR 0012 must be revisited. Concrete shape that would
  trigger reversal: an audit row written with `tool_name=<MRN
  embedded>` or `subject_id=<MRN>`. Test coverage at
  [`tests/test_serve_v740_wire_audit.py::TestA3B1AllowlistOnWire`](../../tests/test_serve_v740_wire_audit.py)
  exercises the seeded-PHI-in-params path; analogous coverage would
  need to extend if children start writing PHI into other columns.
- *Escalation reversal (the more likely path).* If a real researcher
  need surfaces for raw `params`/`error` content in the LLM
  transcript, ADR 0039 (the sibling decision) is superseded with B2
  (per-row scrubber on params/error analogous to `RedcapPHIScrubber`)
  or B3 (B1 default + opt-in raw flag). When that supersession lands,
  this ADR 0012 amendment must extend with the per-row scrubber's
  invariant — the bypass shape changes (scrubber runs on
  params/error before egress) and the allowlist alone no longer
  carries the safety claim.

The standing discipline persists: a fifth framework-tier layer added
in a future release that bypasses the scrubber must amend this ADR
with its own invariant + reversal-condition section, in the same
shape as the v6.6.0 / v6.10.2 / v7.4.0 amendments.

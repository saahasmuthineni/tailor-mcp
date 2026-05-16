# ADR 0039: Audit log is LLM-queryable under a column allowlist

- **Status:** Accepted
- **Date:** 2026-05-16
- **Related:** [ADR 0001 (Audit log is the backbone)](0001-audit-log-as-backbone.md), [ADR 0003 (PHI-scrubber seam)](0003-phi-scrubber-seam.md), [ADR 0009 (Vault subject-keying)](0009-vault-subject-keying.md), [ADR 0012 (Framework-tier PHI-scrubber bypass)](0012-vault-phi-scrubber-bypass.md), [ADR 0029 (Token reduction as analytical quality)](0029-token-reduction-as-analytical-quality.md)

## Context

ADR 0001 codified the audit log as the framework's trust root: every
tool call lands in `audit_log` with timestamp, domain, tool, tier,
parameters, token estimate, outcome, latency, optional error, and an
optional `subject_id`. The argument was reproducibility-shaped — a
durable record of how an analyst accessed participant data, queryable
by an IRB reviewer months after the fact.

Through v7.3.x the audit log was queryable only via shell. The
recipient who wanted to ask "what just happened?" had to drop to
`sqlite3 audit.db` or `tailor status`; the LLM transcript could not
reach the ledger. v7.3.4 caught this gap red-team-style: the bundled
`tailor fitting-room` banner originally carried a prompt — "Show me
what just happened in the audit log" — that had no MCP tool to land
on. The prompt was reworded as a v7.3.4 closure and the v7.4.0 queue
gained "the new `audit_query` tool" as its top item.

Surfacing audit rows to the LLM is not a free move. Three columns on
`audit_log` are IRB-stakes: `params` (a JSON blob the framework
constructs from caller arguments — `subject_id`, file paths, search
strings, instrument names), `error` (a free-text column the router
writes on exception paths — pre-v7.3.1 deployments may carry raw
on-disk paths verbatim), and any future column an `ALTER TABLE` adds.
ADR 0003 names the framework-level PHI-scrubber as no-op by default;
trusting it to re-scrub at egress time would be wishful thinking on
any deployment whose institution has not subclassed `PHIScrubber`.
The v7.3.2 small-cell-suppression work taught the same lesson on the
REDCap surface: a re-egress path that does not own its own
sanitisation discipline becomes the highest-leverage re-identification
vector in the system, exactly the surface the audit log is meant to
*record* attacks against, not *participate in*.

Two design shapes were on the table for the v7.4.0 release. *B1* —
return a fixed allowlist of structured columns, with the error column
collapsed to a `has_error` boolean. *B2* — build a per-row
`AuditQueryScrubber` analogous to the child-level seam ADR 0003 §
Amendment 2026-05-14 introduced for REDCap, scrubbing `params` and
`error` before egress so a researcher can see what specifically
failed without leaving the LLM transcript. The pre-implementation
audit on v7.4.0 returned a BLOCKING finding against B2 unbundled with
B1: a new scrubber class plus the ADR that grounds its invariants is
~3 days of work the framework has no real researcher need for yet,
and the v7.3.x cadence has earned the project the right to ship the
narrow decision first and supersede later when the demand surfaces.

The question this ADR answers: *what shape is `audit_query` allowed
to take, and what future researcher need would force the shape to be
reconsidered?*

## Decision

The framework exposes a fourth framework-tier layer — `AuditQueryLayer`
— that surfaces the audit log to the LLM under a column allowlist.
The allowlist is the *replacement* for content-shape scrubbing on this
egress path, grounded on the observation that `audit_query` returns
framework-emitted structured metadata, not biosensor stream content.

- **One tool, one shape.** `AuditQueryLayer` registers a single MCP
  tool, `audit_query`, alongside `VaultLayer` / `LocalLLMLayer` /
  `SetupHelpLayer`. The layer skips the biosensor-tier security
  pipeline (consent, cost, circuit breaker, PHI-scrub seam) per the
  ADR 0012 § Amendment v7.4.0 invariant — same pattern as the three
  framework-tier layers that preceded it.
- **The allowlist.** `AuditLog.query()` at
  [`framework/audit.py:362-368`](../../src/tailor/framework/audit.py)
  surfaces twelve structured columns: `id`, `timestamp`, `domain`,
  `tool_name`, `tier`, `token_estimate`, `outcome`, `duration_ms`,
  `subject_id`, `scrubber_id`, `child_scrubber_id`,
  `source_metadata_fingerprint`. A derived `has_error: bool` is
  computed from the `error` column at SELECT time. The raw `params`
  JSON and the raw `error` string are never returned.
- **Allowlist is enforced by explicit SELECT.** The SQL at
  [`framework/audit.py:432-438`](../../src/tailor/framework/audit.py)
  is `SELECT id, timestamp, domain, ... FROM audit_log` — never
  `SELECT *`. A future `ALTER TABLE` adding a sensitive column does
  not silently widen the response shape; it stays invisible to
  `audit_query` until a maintainer edits `_QUERY_COLUMNS` and accepts
  the egress decision in code review. This is the structural
  enforcement that makes the allowlist load-bearing rather than
  documentary.
- **Subject filter honors ADR 0009.** The `subject_id` query
  parameter applies an `IS NULL OR subject_id = ?` filter, so
  framework-tier rows that wrote NULL (vault, local_llm, setup_help,
  `audit_query` itself) stay visible alongside the requested
  subject's rows. The same convention vault list/search tools have
  carried since v6.2.0.
- **The tool's own usage is visible by default.** `include_self`
  defaults to `True`, so a row written by an `audit_query` call shows
  up on the next `audit_query` call. The recursion is intentional —
  ADR 0001's "every tool call is recorded" claim is structurally
  weaker if `audit_query` rows live in a blind spot only reachable by
  shell. An LLM that wants to ignore self-referential rows passes
  `include_self=False`.
- **Result-size budget is bounded.** `limit` is clamped to 100 (the
  `_MAX_QUERY_LIMIT` constant) and defaults to 50. Structured-column
  rows at limit=50 land at ~5-15k tokens, well inside the
  operator-configurable `cost_threshold` per
  [ADR 0029](0029-token-reduction-as-analytical-quality.md). The
  layer does not carry its own cost gate; the budget lives in the
  column shape and the row cap.
- **Reversal condition (the unlikely case).** If a deployment
  surfaces real PHI through the column allowlist — a child writes
  PHI into `tool_name` or `domain` directly, or `subject_id` is
  misused to carry MRN-shaped strings rather than pseudonyms — this
  ADR retracts and `audit_query` reverts to shell-only access. The
  test for "did this happen" is content inspection of the columns
  themselves, not a behaviour change in `AuditQueryLayer`.
- **Escalation condition (the likelier case).** If a beachhead lab
  files a feature request for raw `params` or `error` content
  surfaced through the LLM-callable path — e.g. "I want to ask
  Claude to triage what specifically failed on row 4729 without
  copying SQL output back into the chat" — this ADR is superseded by
  a follow-up that ships B2 (per-row scrubber) or B3 (B1 default +
  opt-in raw flag). The path is named here so a future PR has the
  decision shape on file rather than having to relitigate the
  allowlist-vs-scrubber argument from scratch.

## Consequences

**Positive.**

- The IRB-facing claim "every action Tailor took is queryable"
  strengthens from *queryable-by-someone-with-shell-access* to
  *queryable-by-the-LLM-the-researcher-is-already-talking-to*. The
  v7.3.4 banner's deferred-item line ("the queue carries the new
  `audit_query` tool as the top v7.4.0 item") closes; the
  fitting-room scaffold can revert to the original "Show me what
  just happened in the audit log" prompt the v7.3.4 red-team pass
  reworded around the missing tool.
- The egress posture is *structural*, not *configurational*. A
  contributor cannot widen the response shape by editing a config
  file or flipping a flag; they have to edit `_QUERY_COLUMNS` in
  source, which puts the decision through code review where the
  per-column IRB argument can be made explicitly. The same shape
  ADR 0008's "enforced by review at PR time" invariant takes —
  cheap to state, expensive to violate silently.
- The four-layer framework-tier pattern is now uniform. Each layer
  (`VaultLayer`, `LocalLLMLayer`, `SetupHelpLayer`, `AuditQueryLayer`)
  bypasses the security pipeline under an invariant named in
  [ADR 0012](0012-vault-phi-scrubber-bypass.md). A future fifth
  layer must amend ADR 0012 with its own invariant + reversal
  condition in the same shape — the discipline ADR 0012 already
  carries.
- Wire-level and unit-level coverage lock the invariant. The 32
  unit tests in `tests/framework/test_v74_audit_query.py` seed rows
  carrying `MRN-12345` and `/home/saahas/secret/path` strings into
  `params` and `error` and assert they never appear in the response.
  The 10 subprocess wire tests in `tests/test_serve_v740_wire_audit.py`
  prove the same property against a real `tailor serve` JSON-RPC
  subprocess. The AST-class contract test in
  `tests/test_serve_v732_wire_audit.py::TestW5AllCallSitesSweep`
  updates to the new audit-record-site and `_meta` stamping counts
  so a future regression on either is a structural test failure,
  not a documentation drift.

**Negative.**

- Researchers who need full `error` string content — the v7.3.1
  hardening reduced these to redacted placeholders on new rows, but
  legacy databases predating v7.3.1 may still carry raw on-disk
  paths — still drop to shell `sqlite3 audit.db` or `tailor status`.
  The affordance gap is documented; B2/B3 is the named path to close
  it when researcher demand makes the cost worth paying.
- The recursion (`audit_query` calls record `audit_query` rows that
  the next call surfaces) can confuse an LLM that scans the result
  set for "real" rows. Mitigated by the `include_self=False`
  parameter and by the audit row's own `tool_name="audit_query"`
  being trivially filterable; not mitigated structurally because the
  ADR 0001 invariant (every call is recorded) wins over surface
  cleanliness.

**Neutral.**

- The four-layer bypass pattern is now the framework's standing
  shape for "framework-emitted structured metadata reaches the LLM."
  Future contributors who want to add a new framework-tier surface
  read ADR 0012 to learn what invariant they must name and read this
  ADR to learn what egress-shape discipline the project applies to
  metadata that names other framework activity.
- The allowlist's column choice is not load-bearing on the
  allowlist *mechanism*. Adding `latency_ms` or
  `oracle_substrate_count` to `_QUERY_COLUMNS` in a future release
  is an edit reviewers handle column-by-column; the structural
  argument that explicit-SELECT is the enforcement does not move.
- ADR 0009's IS-NULL-or-match filter is now applied at four call
  sites (`vault_list_themes`, `vault_list_notes`,
  `vault_search_notes`, and now `audit_query`). The convention is
  stable enough to extract to a shared helper in a future hygiene
  pass; this ADR does not require it.

## Alternatives considered

**B2 — per-row `AuditQueryScrubber` analogous to `RedcapPHIScrubber`.**
Rejected for v7.4.0; named as the escalation path above. The B2 design
would scrub `params` and `error` content per row before egress, the
same shape ADR 0003 § Amendment 2026-05-14 introduced for REDCap's
structured-PHI seam. The argument against B2 is not that it is wrong
— it is the right move once a beachhead lab needs raw error content
in the LLM transcript — but that shipping it unbundled with B1 adds
~3 days of work (new scrubber class, new ADR for the seam, regression
tests on the scrubber's `params`/`error` content-shape decisions) for
a researcher need the project has no evidence of yet. The v7.4.0
ladder is "ship the narrow decision, supersede when the demand
surfaces"; the explicit reversal/escalation conditions above are what
make the supersession path cheap.

**B3 — B1 default + opt-in `include_raw_params=true` flag that
triggers B2's scrubber.** Rejected for the same reason as B2 plus the
policy-fork complexity. A flag that switches between two egress shapes
invites deployers to flip it without understanding the invariant that
each shape depends on, and it forks the per-tool surface area
(`audit_query` has one response shape today; B3 gives it two).
ADR 0012 makes the same argument against making the vault-bypass a
configurable flag: "the bypass is correct under a structural invariant
about what vault inputs *are*, not under a deployment policy."

**Do nothing — keep audit log shell-only.** Rejected. The status quo
through v7.3.4. The v7.3.4 banner closed the over-promise red-team
caught (the fitting-room prompt with no tool to land on), but the
underlying gap stayed: the IRB-facing trust-root claim of ADR 0001 is
structurally weaker if "queryable" requires shell access. The
researcher who wants to ask "what just happened?" without leaving
their LLM is a load-bearing use case for the project's stated north
star, not a nice-to-have.

**Expose `audit_log` via `VaultLayer` (as a new vault tool).**
Rejected. The audit log is the *Ledger* per
[ADR 0033](0033-complete-tailor-metaphor-workshop-side.md), not the
*Wardrobe*. The two persistence tiers were deliberately split on the
metaphor side (the tailor's record of work vs the customer's
collection) precisely because their invariants differ: vault inputs
are analyst-authored prose under ADR 0012's "not raw streams"
invariant; audit rows are framework-emitted structured metadata under
this ADR's column-allowlist invariant. Folding `audit_query` into
`VaultLayer` would couple two surfaces whose reversal conditions are
unrelated, and would force `VaultLayer`'s 26th tool to argue against
a different invariant than the other 25. A separate layer is the
honest shape.

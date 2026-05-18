# ADR 0001: Audit log is the backbone

- **Status:** Accepted
- **Date:** 2026-04-13
- **Related:** [ADR 0002 (`subject_id` scoping)](0002-subject-id-scoping.md), [ADR 0003 (PHI scrubber)](0003-phi-scrubber-seam.md)

## Context

This framework serves health research workflows — academic medical
centers, mHealth labs, sleep/CGM/cardiology groups. In that context, the
most important question a reviewer (IRB, PI, auditor, a future RSE
inheriting the codebase) can ask is *how did an LLM actually access
participant data?*

Chat-window LLM interactions don't leave a durable trace. A transcript
is by-model, by-vendor, and typically ephemeral. "Trust the transcript"
is not a defensible reproducibility story, and it's not a defensible
governance story either.

The framework needs a single, durable, append-only record of every
action the router took on participant data — something that survives
the LLM client, survives the analyst's session, and can be handed to a
reviewer without editing.

## Decision

Every tool call lands in `audit.db` as exactly one row, written from
`AuditLog.record()` inside the router pipeline. The row carries:

- UTC timestamp
- `domain` (which child), `tool`, `tier`
- Parameters (serialized, truncated at 50 KB)
- Token estimate
- Outcome (`OK` / `ERROR_*` / `BLOCKED_*`)
- Latency in milliseconds
- Optional error detail
- Optional `subject_id` (see [ADR 0002](0002-subject-id-scoping.md))

The audit log is written **before** any post-execute hooks run, and
**before** any result leaves the router. Every dispatch path —
`_dispatch()`, `_dispatch_vault()`, `dispatch_internal()` — records
through the same `AuditLog`.

## Consequences

**Positive.**

- One file (`audit.db`) is the canonical "what happened" record. It
  can be attached to a manuscript, inspected by an IRB, or replayed
  offline.
- Every middleware decision is visible: a consent block shows up as
  `CONSENT_REQUIRED`, a cost block as `COST_APPROVAL_REQUIRED`, a
  validation failure as `PARAM_INVALID`. Compliance is auditable from
  the row list alone.
- Future work (provenance hashing, deterministic replay) retrofits
  cleanly — the `_meta` stamps on results give a forward path, and
  the audit row is the anchor they hash against.

**Negative.**

- The router cannot be bypassed cheaply. Children must not execute
  their own side-effecting operations outside the dispatch path, or
  the audit log lies. The `dispatch_internal()` path exists
  specifically to keep cross-child calls inside the pipeline.
- Audit rows grow. A heavy analyst session produces thousands. The
  50 KB param-size cap prevents a pathological caller from bloating
  the DB, but long-term archival is the deployer's responsibility.
- Errors in `AuditLog.record()` cannot fail silently — a missing row
  is worse than a failed call. Callers must propagate exceptions.

**Neutral.**

- `audit.db` schema migrations happen in-place via `ALTER TABLE` on
  open. Legacy audit databases remain readable.

## Alternatives considered

- **Structured logs + external aggregator (e.g. OTel).** Rejected for
  a local-first tool: the point is that nothing leaves the machine by
  default. Emitting to a collector re-introduces the governance
  question the framework is designed to answer.
- **Audit only on failure.** Rejected. Successful accesses to
  participant data are exactly what a reviewer needs to see.
- **Audit in the child, not the router.** Rejected. Cross-cutting
  concerns belong in the router by design; per-child audit would
  drift in schema and enforcement.

## Amendment 2026-05-18 — CLI-helper audit-row exemption

**Context.** The v7.5 pilot-wizard release introduced a new audit-row
write site outside the router-tier dispatch path:
`pilot._write_attest_initial_audit_row()` writes an `ATTEST_INITIAL`
row at first REDCap configuration to provenance the trust-root
fingerprint the deployment was first attested against (per
[ADR 0003 § Amendment 2026-05-15](0003-phi-scrubber-seam.md)). The
phi-irb-risk-reviewer release gate caught a doc-vs-code tension: the
wizard's helper catches `AuditLog.record()` exceptions, surfaces a
stderr warning, and continues — directly contradicting the
**Negative consequences** clause above ("Errors in `AuditLog.record()`
cannot fail silently — a missing row is worse than a failed call.
Callers must propagate exceptions").

The boss-architect decision (2026-05-18) chose the option (a) path —
ratify the wizard exemption explicitly — over option (b) refuse to
commit a config the wizard could not audit. This section codifies
that decision.

**Decision.** The "callers must propagate" rule in the Negative
consequences clause applies to **router-tier audit calls** — every
audit row landed by `RouterMCP._dispatch()`,
`RouterMCP._dispatch_vault()`, or `RouterMCP.dispatch_internal()`
must propagate `AuditLog.record()` exceptions, no exceptions. That
is the rule the original ADR was written to enforce.

**CLI-helper audit-row writes are exempt** under a narrow set of
preconditions, all of which must hold:

1. The write site is a CLI subcommand helper (operator-action
   provenance), not a tool-call audit row.
2. The audit row is **provenance-only** — it records that an
   operator action occurred and what trust-root state it occurred
   against. It does NOT record a tool call, a participant-data
   access, or a consent state change.
3. The CLI-helper's **primary purpose** is something else (writing
   a config file, registering Claude Desktop, attesting a trust
   root). The audit row is supplementary, not the deliverable.
4. The failure recovery path is **operator-reachable** — re-running
   the CLI subcommand (or a sibling `reattest` ritual) writes a
   fresh audit row that captures the same provenance. The window
   of missing-row state is bounded by the operator's next
   invocation.
5. The helper surfaces the failure to **stderr in plain language**
   so the operator can act on it; silent return is forbidden.

The shipped reference implementation is
`src/tailor/pilot.py::_write_attest_initial_audit_row`. The
`__main__.py::cmd_redcap_reattest` REATTEST sibling propagates
exceptions per the original rule because it runs as an
operator-confirmation ritual where audit-row failure means the
ritual itself didn't durably complete — different shape than
first-config best-effort provenance.

**What this does NOT permit.**

- A router-tier dispatch path swallowing audit exceptions. The
  original Negative consequences clause applies unchanged.
- A child's `execute()` writing its own provenance rows
  best-effort. Cross-cutting audit belongs in the router.
- A future CLI subcommand that audits a *participant-data access*
  best-effort. The exemption is for operator actions only.

**Reversal condition.** If a second non-tool-call audit site
adopts the best-effort pattern (e.g. a future `tailor matlab
reattest` ritual, a fitting-room post-scaffold attestation, a
vault-snapshot operator action), the exemption pattern is no
longer a one-off — it should be promoted to a framework primitive
(`AuditLog.record_best_effort()` or similar) with explicit
opt-in, and the exemption codified there rather than re-stated
per-helper. Same shape as ADR 0013's
"third-domain-promotes-to-framework-registry" precedent.

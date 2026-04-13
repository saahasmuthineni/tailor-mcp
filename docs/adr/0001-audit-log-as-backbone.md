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

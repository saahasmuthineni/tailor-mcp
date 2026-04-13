# ADR 0002: `subject_id` as first-class audit column, optional on calls

- **Status:** Accepted
- **Date:** 2026-04-13
- **Related:** [ADR 0001 (Audit log)](0001-audit-log-as-backbone.md), [ROADMAP.md § Per-subject parameter scoping](../../ROADMAP.md#per-subject-parameter-scoping-on-existing-tools), saahasmuthineni/biosensor-to-llm-middleware#13

## Context

Multi-participant studies need to answer "which participant's data was
this tool call about?" at the audit-row level. Without per-subject
scoping, the audit log is a correct but coarse record — an IRB
reviewer cannot slice it by participant to verify consent boundaries
were respected.

At the same time, forcing `subject_id` as a required parameter on
every tool would:

1. Break single-subject and demo use cases (one analyst, their own
   data).
2. Require every existing child to declare it in `param_schemas`
   before the column is useful anywhere — a coordinated migration
   across children.
3. Commit the framework to a particular answer for "how does the
   vault key notes by subject?" which is a real design question, not
   a trivial threading exercise.

The tension: make per-subject scoping first-class in the audit log
without blocking the rest of the framework on a coordinated schema
migration of every child.

## Decision

`subject_id` is a **first-class column on `audit_log`** and a
**first-class extraction step in the router**, but **optional at the
call site**.

Specifically:

- `audit_log.subject_id` is a nullable `TEXT` column. Legacy databases
  migrate on open via `ALTER TABLE`, mirroring the pattern
  `VaultStorage` uses for `mtime_ns`.
- The router's `_coerce_subject_id()` helper extracts `subject_id`
  from incoming parameters if present, and threads it through
  `_dispatch()`, `_dispatch_vault()`, and `dispatch_internal()` to
  every `AuditLog.record()` call.
- Children are **not yet required** to declare `subject_id` in their
  `param_schemas`. When they do (roadmap item; see
  saahasmuthineni/biosensor-to-llm-middleware#13), the column is ready
  and no further router work is needed.

## Consequences

**Positive.**

- Audit rows can be scoped by participant today, as long as callers
  pass `subject_id`.
- The param-validator's keep-unknown-kwargs behavior means callers
  can already pass `subject_id` and have it land in the audit row,
  even before children declare it in `param_schemas`.
- When children adopt the declared schema entry, no router changes
  are required — the wiring already exists.

**Negative.**

- Until children declare `subject_id` in `param_schemas`, LLM clients
  have no discovery path for it. The column is populated only when a
  caller happens to pass it.
- Audit-log slicing by subject is best-effort until every relevant
  tool declares the parameter. Multi-subject studies should treat the
  schema adoption (issue #13) as a prerequisite.

**Neutral.**

- The vault layer receives `subject_id` through the same threading
  pattern. How the vault *organizes* notes by subject is deliberately
  deferred — tracked on the roadmap as its own design question.

## Alternatives considered

- **Require `subject_id` on every tool call from day one.** Rejected
  — forces single-subject and demo use cases to pass a synthetic
  value, and commits to a vault-keying answer prematurely.
- **Skip the column; use a separate `subject_audit` table.** Rejected
  — doubles the write path and means queries "what did the router do
  on behalf of P042?" require joins. The nullable column is simpler
  and cheaper.
- **Infer `subject_id` from the calling LLM session.** Rejected —
  inference is the wrong direction for a governance record. The
  caller should state the subject explicitly.

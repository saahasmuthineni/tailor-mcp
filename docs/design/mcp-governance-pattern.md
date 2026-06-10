# A governance pattern for MCP servers

*Tiered access, enforced gates, and an audit trail for AI-to-private-data
connections. Pattern description with Tailor as the reference
implementation — written so you can adopt the pattern without adopting
Tailor.*

---

## The problem

MCP makes it one afternoon's work to hand an LLM live access to data
that matters: a client database, a research cohort, a document archive,
a financial export. The protocol specifies *how* tools are called. It
deliberately says nothing about three questions every serious
deployment hits within a week:

1. **Resolution** — does the model need the raw rows, or the answer?
   Most MCP servers return whatever the underlying API returns. Raw
   data in context is expensive, crowds out reasoning, and — for
   sensitive sources — is itself the leak.
2. **Escalation** — when the model *does* need higher-resolution data,
   who approves that, and where is the approval enforced? A system
   prompt that says "ask before reading raw records" is a suggestion.
   The model can ignore it; a different client will ignore it; a
   jailbreak will ignore it.
3. **Reconstruction** — three weeks later, can anyone say exactly what
   the AI accessed, with what parameters, and what came back? Chat
   transcripts are not an audit trail: they're client-side, deletable,
   and incomplete (they show the conversation, not the calls).

The pattern below answers all three **server-side**, so that
enforcement is identical for every MCP client — Claude Desktop, Cline,
a future agent, a hostile one. The principle the whole pattern hangs
on:

> **Behavioral rules live in the server, not in the LLM.** Anything
> enforced by prompt is advisory. Anything enforced in the dispatch
> path is structural.

---

## The pattern

### 1. Declare a tier on every tool

Every tool declares an integer tier as part of its definition:

| Tier | Returns | Gate |
|---|---|---|
| **1** | Server-computed summaries — statistics, reports, trends. The *answer*, not the data. | None |
| **2** | Reduced-resolution data — downsampled streams, single-collection slices. | Explicit user consent, session-scoped, revocable |
| **3** | Full-resolution raw data. | Consent **and** a pre-execution cost approval |

The tier is data minimization made executable: "at what resolution
does this question actually need the data?" Most analytical questions
are answerable at Tier 1, which means most sessions move zero raw
records into the model's context. That has a privacy consequence and
an economics consequence at the same time — a Tier-1 summary is
typically two to three orders of magnitude smaller than the raw
stream it summarizes, and for cohort-scale questions the raw stream
often does not fit in any context window at all.

*Reference implementation:* `ToolDefinition(name, tier, description,
params)` in [`framework/interfaces.py`](../../src/tailor/framework/interfaces.py);
the tier table in any shipped child.

### 2. Run a fixed gate pipeline on every dispatch, cheapest first

The router owns one dispatch path. Every tool call traverses it in
order, and each stage can refuse before the next spends anything:

```
validate params → circuit breaker → consent gate (tier ≥ 2)
  → cost gate (tier ≥ 3) → execute → scrub → audit + provenance stamp
```

- **Parameter validation** — typed schemas (type, range, pattern,
  allowlist) checked before any work. Reject malformed input at the
  door; never let "the model passed a weird string" reach your data
  layer.
- **Circuit breaker** — N consecutive failures in a domain blocks
  that domain for a cooldown window. An LLM in a retry loop is a
  denial-of-service engine against your own backend; the breaker
  caps the blast radius.
- **Consent gate** — per-domain, session-scoped, revocable. Tier-2+
  calls in an unconsented domain return a structured refusal (see
  § 3), not the data. Consent is granted by a human turning it on,
  not by the model asking nicely.
- **Cost gate** — Tier-3 calls are pre-estimated from *metadata*
  (row counts, point counts), never by loading the payload. Estimates
  above the threshold return a refusal carrying the estimate, a
  human-readable comparison ("~44× a typical call"), and the cheaper
  alternative tool if one exists. Estimator failures fail **closed**.
- **Scrubbing seam** — a hook between execution and return where an
  institutional redaction policy runs. Critically: the default is an
  explicit, *loud* no-op — every result carries a warning that no
  scrubbing policy is configured, so a misconfigured deployment is
  visible in every single response rather than silently unprotected.
- **Audit + provenance** — see § 4 and § 5.

The ordering is an economics statement: validation is free, the
breaker is a dict lookup, consent is a dict lookup, cost estimation
is metadata-only — all the cheap refusals happen before the expensive
work, and the expensive work happens before anything irreversible.

*Reference implementation:* the dispatch path in
[`framework/router.py`](../../src/tailor/framework/router.py); gate
classes in [`framework/security.py`](../../src/tailor/framework/security.py)
and [`framework/cost.py`](../../src/tailor/framework/cost.py).

### 3. Refuse in a structured, machine-parseable shape

When a gate refuses, the response is not a free-text scolding — it's
a JSON object with individually checkable fields: what the model
**must do** (surface the consent question to the human, verbatim),
what it **must not do** (proceed, paraphrase the data request away,
answer from prior knowledge), and what to do **on an ambiguous
reply**. Free-text instructions degrade across clients and model
generations; structured instructions survive both, and an auditor can
verify compliance field by field.

*Reference implementation:* `LLMInstruction` in
[`framework/interfaces.py`](../../src/tailor/framework/interfaces.py).

### 4. Log every call to a durable, queryable audit log

Every dispatch — success, refusal, error — lands as a row in a local
SQLite database: timestamp, domain, tool, tier, parameters
(truncated), token estimate, outcome, latency, optional error,
optional entity scope, and the identifier of the scrubbing policy
that ran. Append-only, survives the session, queryable with plain
SQL.

Two design choices carry most of the value:

- **Entity scoping.** Calls can carry an optional `entity_id` — *whose*
  data this call is about (a study participant, a client, a patient,
  an account). The router threads it into every audit row, which is
  what turns "the AI accessed the database 400 times" into "here are
  the 12 calls that touched client X," — the question a review board,
  a client, or a regulator actually asks.
- **Outcome taxonomy.** Refusals are distinguishable from errors, and
  operator-action conditions (credential expired, re-attestation
  needed) are distinguishable from bugs — as typed outcomes, not
  string-matched log lines. `SELECT * FROM audit_log WHERE
  outcome='CONSENT_REFUSED'` is a one-line compliance query.

The audit log is the pattern's backbone. If you adopt only one piece,
adopt this one: it converts "trust me" into "query it."

*Reference implementation:* [`framework/audit.py`](../../src/tailor/framework/audit.py);
schema documented in [ADR 0001](../adr/0001-audit-log-as-backbone.md)
and [ADR 0002](../adr/0002-subject-id-scoping.md).

### 5. Stamp provenance on every result

Every successful result carries a `_meta` block: package version,
tool name, UTC timestamp, domain, tier, scrubbing-policy identifier,
and per-call + session token counts. If a number from an AI-assisted
analysis ends up in a report, a paper, or a decision, the `_meta`
block is the minimum needed to say where it came from and re-derive
it. Pair it with deterministic server-side computation (pure
functions, no clock or PRNG in the analytical path) and the same call
reproduces the same number on any machine.

*Reference implementation:* `_meta` stamping in
[`framework/router.py`](../../src/tailor/framework/router.py);
determinism invariant in [ADR 0008](../adr/0008-deterministic-by-construction-processing.md).

### 6. Make data sources plugins, governance infrastructure

The data-source extension point implements a small contract — domain
name, tool definitions with tiers, parameter schemas, an executor, a
cost estimator, a consent description — and inherits the entire
pipeline. The author of a new source writes zero lines of consent,
audit, validation, or cost logic, and *cannot opt out of them*:
dispatch belongs to the router. Governance you can forget to add is
governance that will eventually be missing; in this shape it is
structurally always present.

*Reference implementation:* the `ChildMCP` ABC in
[`framework/interfaces.py`](../../src/tailor/framework/interfaces.py);
[`children/template/`](../../src/tailor/children/template/) is a
runnable skeleton.

---

## What the pattern does not solve

Honesty about scope, because a governance pattern that oversells is
self-defeating:

- **It does not make the LLM trustworthy.** It makes the LLM's *access*
  bounded and observable. A model can still misread a summary or
  hallucinate a number in its narrative; deterministic provenance
  stamps make that detectable, not impossible.
- **It is not access control between humans.** Consent is
  session-scoped and machine-local — the pattern assumes the person
  at the keyboard is authorized on that machine. Multi-user authn/z
  is a separate layer.
- **The scrubbing seam is a seam, not a policy.** Redaction policy is
  institution-specific by nature; the pattern's contribution is making
  *absence of a policy* loud rather than silent.
- **A local audit log is as durable as the disk it's on.** Tamper
  evidence and off-machine retention are deployment concerns the
  pattern leaves to the operator.

---

## Adopting the pattern without adopting Tailor

The pieces are deliberately separable, in rough order of
value-per-effort:

1. **Audit log** — a SQLite table and one write per dispatch. An
   afternoon's work; transforms what you can claim about your server.
2. **Tiers + a consent gate** — an integer on each tool definition and
   a dict lookup in your dispatch path, plus a structured refusal
   shape.
3. **Cost pre-estimation** — metadata-based estimates with fail-closed
   semantics on Tier-3 tools.
4. **Provenance stamps** — a `_meta` dict appended to every result.
5. **Circuit breaker, scrubbing seam, entity scoping** — as your
   deployment's stakes grow.

Tailor itself is AGPL-3.0-or-later and structured exactly this way —
[`framework/`](../../src/tailor/framework/) is the governance engine,
[`children/`](../../src/tailor/children/) are the data sources. If
your use case fits a local-first Python MCP server, the shortest path
is registering a child rather than rebuilding the engine. If it
doesn't, this document is the spec; the test suite
([`tests/framework/`](../../tests/framework/)) doubles as a
behavioral reference for the edge cases prose leaves out — gate
ordering under failure, refusal envelope shapes, audit completeness
under error paths.

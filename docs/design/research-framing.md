# Biosensor MCP — Research Framing

This document is written for health researchers, research-software
engineers, and reviewers evaluating whether this project is appropriate
infrastructure for a study that involves LLM-assisted analysis of
high-frequency biometric data. It is the longer-form companion to the
README and is meant to be readable end-to-end in about ten minutes.

## The governance problem with hosted LLMs

The appeal of using a modern LLM as an analytical assistant for
biometric data is obvious: an analyst can ask a natural-language
question, get a coherent summary, and iterate. The problem is that the
most capable LLMs are hosted services, and hosted services are the
wrong home for participant biometric data. Pasting raw continuous
glucose traces, ECG strips, sleep staging outputs, or wearable streams
into a web chat is typically against institutional policy, frequently
against applicable law (HIPAA in the United States, equivalent regimes
in other jurisdictions), and in all cases leaves no defensible trace of
what was accessed, by whom, on what date, and for what question.

The workarounds research groups reach for — manually truncating
streams, summarizing by hand, or skipping LLM-assisted analysis
entirely — are either leaky, labor-intensive, or both. Biosensor MCP
is a local-first alternative: the server runs on a workstation next to
the data, the LLM client communicates with it over MCP, and only
server-computed summaries cross the boundary between the analyst's
machine and the model. Raw per-timestamp streams never leave the
device.

## Data minimization, made executable

IRBs increasingly ask protocol authors to justify not only which data
is accessed but at what resolution. The three-tier access model in
this framework makes that question structural rather than aspirational.

Every tool exposed by a child declares an access tier at registration:

- **Tier 1** returns server-computed analytical reports only. For the
  running example that means HR-zone distributions, drift, decoupling,
  efficiency factor, anomaly counts, mile splits. Tier 1 never
  releases per-timestamp sensor data.
- **Tier 2** returns downsampled streams (e.g. one sample every 10–30
  seconds) suitable for visualization. Tier 2 is gated by per-domain
  biometric consent that is session-scoped and revocable.
- **Tier 3** returns per-timestamp streams with precision reduction.
  Tier 3 is gated by consent *and* by a pre-execution cost gate; the
  router asks the child for a token estimate before anything is
  computed and presents the user with the raw-vs-downsampled choice if
  the estimate exceeds a threshold.

Most analytical questions are answerable at Tier 1. The gate
structure is the protocol text made executable: an analyst cannot
quietly escalate from summary to full stream without the router
presenting the decision, writing the row, and requiring explicit
reply.

## The audit log as IRB and reproducibility evidence

Every tool call — successful, blocked, failed — is persisted to a
SQLite `audit.db` file next to the server's data directory. Each row
carries the timestamp, the domain, the tool name, the access tier,
the parameters (JSON), a pre-execution token estimate, the outcome
(SUCCESS / PARAM\_INVALID / CIRCUIT\_OPEN / CONSENT\_BLOCKED /
COST\_GATE\_TRIGGERED / ERROR / and their internal-dispatch variants),
the latency in milliseconds, an optional error message, and — as of
the research-framing release — an optional `subject_id` extracted
from the call parameters.

The audit row is intended to be evidence that survives the analysis.
Attach the file to a protocol amendment. Drop it into a replication
package alongside the derived metrics. Query it when a reviewer asks
how an analyst arrived at a figure six months later. The schema is
deliberately stable and the database is a single file inspectable
with any SQL tool.

Two implementation notes worth flagging for reviewers. First, the
router writes the audit row regardless of what the LLM client
requests — the LLM cannot bypass logging. Second, the `subject_id`
column is nullable and children are free to ignore it; the column
exists so studies that want participant-scoped traces can have them,
not so that every call must be scoped.

## Provenance on every result

Every successful tool result carries a `_meta` block that stamps, at
minimum, the package version, the tool name, and a UTC timestamp of
when the call was made. The same block appears on direct LLM-facing
calls, on vault-layer calls, and on internal cross-child dispatches
(used by vault backfill). If an analytical number ends up in a paper,
the code version and moment that produced it are recoverable from the
metadata that travelled alongside it.

This is the minimum-viable version of analytical provenance. Full
content-hashed provenance — raw-data hash fanning out through
intermediate-state hashes to a final derived metric — is tracked as
roadmap work. The `_meta` stamps are intended to make retrofitting
full hashing a localized change rather than a cross-cutting one.

## The vault layer — longitudinal analytical memory

Analytical reasoning in research does not fit inside one session.
Hypotheses evolve across months; observations about a participant
made in one session are exactly the context the next analyst needs in
the next session. The vault layer is the framework-level response to
that gap.

It exposes two durable object types on top of an Obsidian vault and a
query-optimization SQLite index:

- **Themes** are persistent research questions or hypotheses
  (\"cooldown HR is elevated in participants on medication X\") with
  an append-only evidence log. Evidence blocks are never rewritten;
  they accumulate over the life of the study.
- **Moments** are timestamped observations worth remembering, each
  linkable to specific participants, themes, or prior run-level
  reports.

The vault is opinionated about being durable. Markdown files in the
Obsidian vault are the source of truth; the SQLite index is rebuilt
from them on demand. Manual edits made in Obsidian are surfaced on
next read via mtime revalidation. A new analyst joining the project
can read the open themes and the recent moments as their first
session step and pick up the thread without digging through
notebooks.

## What is NOT yet built

This document is also a commitment to be honest about the gaps.
Tracked in [ROADMAP.md](../ROADMAP.md):

- **Real PHI scrubbing implementations** behind the `PHIScrubber`
  slot. The slot exists; the implementations do not. The framework
  deliberately does not guess what PHI means in a given study.
- **Deterministic replay** with seed control as an audited entry-
  point flag, paired with content-hashed provenance. The analytical
  layer is already PRNG-free and stateless by construction
  (ADR 0008); the residual is the small router-level flag stamped
  in `_meta` so reviewers can confirm a re-run was produced under
  the invariant. Deferred jointly with provenance hashing because
  the flag without the hash is cosmetic.
- **Full provenance hashing** on derived metrics. The `_meta` stamps
  ship today; content-hashed provenance chains do not.
- **Multi-analyst attribution on vault notes.** The vault currently
  assumes a single analyst per workstation.
- **A vault-freeze operation** that snapshots vault state for a
  manuscript submission, including the exact audit rows and code
  version the figures came from.
- **Worked-example notebook** against a published analytical question
  on a public dataset.
- **Evaluation harness** for measuring gate compliance, scope drift,
  and vault-recall accuracy across different LLM clients.

## Target deployment shape (v6.2)

The roadmap above is long, and not every item is equally load-bearing
for every kind of user. The v6.2 development cycle is anchored to a
specific deployment shape — the lightest version of an institutional
deployment — so that effort goes into the gaps that actually block
that shape from running, rather than into items that matter only for
larger or more ambitious uses.

The picture: a friendly academic lab, one principal investigator and
one analyst, a study with five-to-twenty participants, light IRB
review. The lab wants to clone the repo, ingest its participants'
biometric data (some via a vendor API like Strava, some via CSV
exports from a sleep tracker or a CGM logger), have analytical
conversations with an LLM that respect governance boundaries, and
accumulate durable analytical memory across sessions and analysts'
working days. The lab is not a clinical site, is not yet preparing a
manuscript submission, has only one analyst at a time touching the
vault, and is not handling data sensitive enough to demand an
institutional Safe-Harbor scrubber on day one.

Under that shape, the items most worth shipping are the ones that
make the system actually *true* to its existing claims for one
participant scaled out to twenty: per-subject scoping on the vault
layer (so notes and themes can be organized by participant), an
honest accounting of which deterministic-replay properties the system
already has via its stateless static analytics, and any drift between
documented governance behavior and the audit-table reality. The items
deferred past v6.2 are the ones that materially raise the deployment
ceiling — multi-analyst attribution, vault-freeze for manuscript
submission, content-hashed provenance, the evaluation harness, the
public-dataset worked example — but that the framing above does not
yet need.

## Consent withdrawal under this profile

Consent withdrawal under the v6.2 deployment shape is treated as
**cessation of further data collection plus removal of cached
participant biometric data on the analyst's machine** — not as
full erasure of every derivative analytical artifact. When a
participant withdraws, the framework's `revoke_consent_*` tool
synchronously deletes the cache rows that hold raw biometric data
(per-stream samples, fetched activity rows, and equivalents in
each child's storage layer) and refuses to flip consent state if
that deletion fails. Analyst-authored notes, theme bodies, and
evidence blocks created lawfully under the prior consent survive
withdrawal in the same posture an analyst's working notebook
would: they are work product, not raw participant data. ADR 0013
codifies the cache-only purge mechanism that enforces this; ADR
0009's append-only vault invariants govern the analytical-memory
side.

A study whose IRB language reads *"withdrawal removes all
derivative records"* rather than *"withdrawal stops further data
collection"* — for instance, a clinical-grade or GDPR-strict
study — would need to reconsider both ADRs and pair revocation
with full vault erasure. The framework provides the seam (the
reversal condition named in ADR 0013) but does not pre-empt that
decision: the cache-only-vs-full-erasure call is a study-specific
IRB question, not a framework-level default.

## Other framings explicitly out of scope today

Two larger framings remain open and will be addressed in a later
cycle: a fuller institutional deployment (multiple labs, multi-analyst
studies, real Safe-Harbor scrubbing, manuscript submission), and a
personal-use framing where the same infrastructure is treated as a
craft tool for a single participant analyzing their own data. Neither
is the v6.2 target; both are explicitly on the table for v6.3 and
beyond.

## Scope limit

This is research infrastructure. It is not a clinical decision
support system, it has not been validated against any regulatory
framework that governs patient-facing tools, and any analytical
output it produces still requires human validation before it informs
decisions. The intent is to make LLM-assisted exploration of
biometric data safer, more auditable, and more reproducible — not to
replace analyst judgment.

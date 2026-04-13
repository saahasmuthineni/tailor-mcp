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
- **Per-subject scoping as an explicit tool parameter** on existing
  children. The audit log captures `subject_id` when supplied, but
  the running child's tools do not yet accept it, and the vault layer
  does not yet key notes by subject.
- **Deterministic replay** with seed control. Many analytical
  functions touch pseudo-randomness (anomaly sampling, downsampling
  variants). Deterministic mode is a dedicated piece of work.
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

## Scope limit

This is research infrastructure. It is not a clinical decision
support system, it has not been validated against any regulatory
framework that governs patient-facing tools, and any analytical
output it produces still requires human validation before it informs
decisions. The intent is to make LLM-assisted exploration of
biometric data safer, more auditable, and more reproducible — not to
replace analyst judgment.

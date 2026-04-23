# ADR 0006: Vault Overhaul (v6) — Longitudinal Research Tool

- **Status:** Accepted
- **Date:** 2026-04-23
- **Related:** ADR 0001 (audit log backbone), ADR 0004 (structured LLM instruction)

## Context

Through v5 the vault layer was a correct but shallow store: each tool
wrote a note, and `vault_get_fitness_summary` scanned the index for a
new session.  In practice the analytical lifecycle was missing several
shapes that research sessions kept inventing ad-hoc:

- **Orientation friction at session start.** Reading every open theme
  and recent moment to "get back in context" burned tokens and
  attention before the analyst asked their first substantive question.
- **Thinking vs. evidence was collapsed.** A session often made partial
  progress that wasn't a settled observation and wasn't a formal
  resolution.  There was nowhere to put it except inside an evidence
  block, which made evidence logs noisier and less trustable.
- **Hypothesis drift went unrecorded.** When the framing of a theme
  shifted — same phenomenon, new explanation — v5 either overwrote the
  old hypothesis or asked the analyst to write a new theme.  The first
  loses the trail; the second fragments it.
- **Evidence had no provenance.** A block read "Mile 6 HR 8bpm higher"
  with no indication of whether the number came from a computed
  report, a downsampled stream, or unverified recall.  Reviewers
  couldn't audit derivations.
- **Half-formed observations had no home.** The fastest place to
  capture "weird thing happened around mile 4" during analysis was
  either (a) a full moment note (too much friction), (b) chat (lost at
  session end), or (c) a scratch section inside an existing note
  (hard to find later).
- **Errors couldn't be marked as such.** If a later analysis
  contradicted an earlier evidence block, the append-only log had no
  way to flag the earlier block as superseded without deleting it
  (which the invariant forbids).
- **Sessions that diverged from their goal left no record of the
  divergence.** "I set out to study fueling but ended up on HR drift"
  is a real research trajectory; v5 only recorded the destination.
- **Vault maintenance state was invisible.**  Stale themes, orphaned
  moments, unprocessed inbox items, and themes still open without any
  evidence accumulated without any tool surfacing them.

Most of these gaps correspond to well-known patterns from personal
knowledge-management practice — compressed state snapshots, inbox
staging, lifecycle transitions that preserve history, correction
records, orphan audits.  v6 ports them into the middleware so the
vault can serve as a longitudinal research tool, not just a note
archive.

## Decision

The vault layer gains seven governance features, all implemented
inside `biosensor_mcp.framework.vault` and surfaced as Tier-1 tools
that skip the biosensor-tier gates (consent, cost, circuit breaker,
PHI-scrub).  Only parameter validation and audit apply — identical to
every other vault tool.

1. **Snapshot pair** (`vault_generate_snapshot`, `vault_get_snapshot`).
   A single compressed `snapshot.md` at the vault root becomes the
   "call this first" orientation artifact.  Built from live storage at
   write time; read cheaply at session start.

2. **Theme lifecycle enrichment.**
   - A `reframed` status value on `vault_upsert_theme` signals
     hypothesis drift.  The handler detects reframes automatically when
     a new hypothesis differs from the one on disk; the prior framing
     is preserved under a `## Prior Framings` section, the body's
     `## Hypothesis` is replaced, and status persists as `open`
     (reframed is a transitional event, not a terminal state).
   - A `thinking` parameter appends a `### Thinking — TIMESTAMP` block
     in the evidence section — visually distinct from settled evidence
     but stored in the same log so it travels with the theme.
   - Fold-back on resolution: when a theme reaches `resolved` or
     `rejected`, linked run and theme notes receive a one-line
     `> Theme [[slug]] resolved: …` annotation.  Best-effort; missing
     links are skipped silently.

3. **Evidence provenance.**  Optional `evidence_source_tier`,
   `evidence_source_tool`, `evidence_source_domain`, and
   `evidence_verification` parameters on `vault_upsert_theme` stamp
   new evidence blocks with a `> Source: …` blockquote.  When none are
   supplied the block renders exactly as in v5.

4. **Inbox trio** (`vault_inbox_add`, `vault_inbox_list`,
   `vault_inbox_drain`).  A single `inbox.md` at the vault root, one
   line per item, timestamped.  Bulk drain promotes items to moments,
   theme evidence, or discards them in one audited call.

5. **Session divergence.**  An optional `divergence` parameter on
   `vault_capture_session` records the goal-vs-actual gap for the
   session.  Rendered as a `## Divergence` section on the summary
   moment and mirrored into frontmatter for search.

6. **Analytical corrections** (`vault_correct_evidence`).  Inserts a
   `[CORRECTED <ts>]` blockquote after a specific evidence block's
   header and appends a new evidence block tagged `[correction]`
   logging what changed.  The original block is never rewritten or
   deleted; the append-only invariant holds.

7. **Health check** (`vault_health_check`).  Returns stale themes,
   orphaned moments, themes without evidence, inbox depth, and counts
   by status.  Used at session end to decide what to tidy up.

No biosensor-tier code changes.  No new dependencies.  The bump from
v5 → v6 is carried by the vault surface and the version string.

## Consequences

**Positive.**
- Session orientation becomes cheap: one `vault_get_snapshot` reads one
  file instead of iterating the index.
- Analytical reasoning is traceable end-to-end: original evidence +
  provenance + corrections + reframes + resolutions + fold-backs are
  all recoverable from the markdown alone, without the SQLite index.
- Inbox turns chat-window observations into vault-resident items
  without forcing premature categorisation.
- Governance signals (stale themes, orphaned moments) are explicit and
  queryable rather than implicit.

**Negative.**
- The vault surface went from 15 tools to 22.  More to learn for the
  LLM client — mitigated by snapshot + health check collapsing most of
  the "where am I" questions into one or two calls.
- Reframe detection depends on comparing a new hypothesis string to
  the one currently on disk.  Trivially different whitespace or
  wording will register as a reframe; this is deliberate (false
  positives are cheap — they just write an extra Prior Framings entry)
  but worth being explicit about.
- Fold-back writes to linked notes, which means a status flip can
  cascade into several file updates.  All are best-effort and
  idempotent (the marker string is checked before insertion).

**Neutral.**
- The markdown-as-source-of-truth principle holds: every new feature
  stores its state in `.md` files.  `vault.db` remains a query-
  optimisation index.
- Thinking blocks and evidence blocks are stored in the same section
  but distinguishable by their H3 prefix (`### Thinking —` vs
  `### Evidence —`).  Obsidian renders them consistently; downstream
  parsers that want only settled evidence can filter on the header.

## Alternatives considered

- **Ship snapshot only; defer the rest.**  The snapshot alone is a
  clear orientation win, but most of the pain came from the missing
  lifecycle shapes (reframing, thinking, correction).  Shipping just
  the snapshot would have been a cosmetic improvement over v5.
- **Put inbox items into moments from the start.**  Rejected: the
  capture-then-decide split is the whole point.  Forcing each
  observation through the moment renderer makes the fast path as slow
  as the slow path.
- **Store provenance as a separate index table instead of inline in
  the evidence block.**  Rejected: markdown-as-source-of-truth.  The
  blockquote lives next to the evidence it describes, and the SQLite
  index stays a mirror.
- **Make reframe an explicit tool (`vault_reframe_theme`) instead of
  auto-detecting inside `vault_upsert_theme`.**  Rejected: most
  callers won't know ahead of time that they're reframing.  Detection
  on hypothesis mismatch is the right default; passing
  `status="reframed"` explicitly is still accepted for clients that
  want to be loud about it.
- **Correction rewrites the old evidence block.**  Rejected outright:
  violates the append-only evidence invariant that makes the log
  auditable.  The `[CORRECTED]` blockquote + new `[correction]` block
  preserves every byte of the original while making the supersession
  visible in both the reader's flow and the log's chronology.

# ADR 0007: Rendering layers — source-of-truth markdown is plain; plugin views are additive

- **Status:** Accepted
- **Date:** 2026-04-29
- **Related:** [ADR 0006 (vault overhaul v6)](0006-vault-overhaul-v6.md), [ADR 0001 (audit log backbone)](0001-audit-log-as-backbone.md)

## Context

The vault layer ships markdown as its source of truth (see ADR 0006:
*"Markdown files are the source of truth; vault.db is a query-
optimization index"*). In practice the vault is also opened in
Obsidian, where community plugins (Dataview, Templater, Periodic
Notes, Calendar, Charts, Tasks) add live-query views, calendar
panes, scheduled-note auto-creation, and other rendering
conveniences that researchers and analysts have come to expect.

Two kinds of pressure show up over time:

- **Useful patterns from a personal Obsidian vault** (live aggregate
  dashboards, calendar-driven daily/weekly notes, frontmatter-derived
  tables) are tempting to lift into VaultLayer. Some of them — the
  dashboard ones — would meaningfully improve research utility.
- **The project has explicitly said "Obsidian-compatible, not
  Obsidian-coupled."** That phrasing is not actionable on its own:
  it doesn't tell a contributor evaluating a specific plugin
  whether to ship integration with it, ship around it, or refuse it.

A more concrete question is: *what is the project's policy on
markdown that contains plugin-specific syntax?* The answer
determines whether features like a Dataview-backed dashboard, a
Templater-instantiated note class, or a Charts-rendered metric
panel can ship as part of the vault layer at all.

The existing v6 evidence-correction feature (`vault_correct_evidence`)
already touches this question implicitly: the markdown it writes uses
plain Obsidian callout syntax (`> [!warning]`), which renders specially
in Obsidian but degrades gracefully to a quoted line in any plain
markdown renderer. That worked by accident. ADR 0007 makes the
underlying policy explicit so subsequent decisions are not accidents.

## Decision

The vault layer adopts the following policy. It applies to every
file the framework writes into the vault and every helper tool that
materialises content (snapshots, dashboards, indexes).

1. **Source-of-truth markdown is plain and AI-readable.** Every
   primary note class — themes, moments, runs, snapshots, inboxes,
   failure modes, dashboards, anything else the framework emits —
   must be valid CommonMark / GFM. It must render correctly (text
   intact, no leftover template tokens, no broken syntax) in any
   editor that opens the file: Obsidian, VS Code, GitHub, plain
   `cat`. The same content must be parseable by an LLM reading the
   markdown as a tool result.

2. **Rendering layers are optional and additive.** Plugin-enhanced
   views (Dataview live queries, Templater dynamic templates,
   Calendar pane, Charts) may be layered on top of the source-of-
   truth content. They are valid additions when they meet *both*
   of the conditions in (3).

3. **Plugin syntax that leaks into vault content must ship a
   snapshot fallback maintained by the framework.** Concretely:

   - If a feature embeds a plugin-evaluated block (e.g. a
     ```` ```dataview ```` query) inside a note that the framework
     writes, the same note must contain a materialised plain-
     markdown snapshot of the rendered result, refreshed by a
     framework tool, with a `last_updated` timestamp visible.
   - Both views must read from the same underlying source — the
     SQLite index over the markdown vault — so they cannot
     disagree about anything except freshness.
   - Templates used internally by the framework to instantiate new
     notes must produce plain markdown after instantiation. Plugin
     template engines (e.g. Templater) that leave evaluated tokens
     in the output are not used by the framework's own write paths.
   - Templates intended for human use via Obsidian (placed in
     `templates/`) may use plugin syntax, since Templater
     evaluates them at instantiation time and the resulting note
     is plain markdown.

4. **Discoverability:** the policy is referenced in
   [CLAUDE.md](../../CLAUDE.md) and applies to all future vault
   tools. Pull requests that add plugin-coupled rendering without a
   snapshot fallback are rejected on principle, not on a per-PR
   judgement call.

## Consequences

**Positive.**

- Contributors get a single rule to evaluate plugin-related
  proposals against: *"is the source markdown plain and AI-readable
  without the plugin?"* Yes → fine. No → ship a snapshot fallback,
  or don't ship.
- Researchers using Obsidian get plugin-enhanced views where they
  add value (live dashboards, calendar pane).
- Researchers using a plain markdown editor — VS Code, Vim, mobile
  browser, GitHub — see the same content correctly. The vault
  remains usable across the full range of analyst tooling.
- The LLM reading vault notes via `vault_read_note` /
  `vault_search_notes` always sees the materialised content, never
  an unevaluated plugin token. This preserves the project's
  client-agnostic governance claim — vault outputs do not require
  a specific Obsidian plugin to be interpretable.
- The dual-output discipline pairs cleanly with the existing
  architecture: `vault.db` is already the materialised query layer,
  so writing snapshot tables back into markdown reuses the same
  queries that drive the SQLite index.

**Negative.**

- Dual-output features carry a small synchronisation cost: a
  refresh tool must update the snapshot, and the snapshot can
  become stale relative to the live query. Mitigated by the
  required `last_updated` timestamp and `vault_health_check`
  surfacing snapshots older than a configurable threshold.
- Feature surface grows by a small constant per dual-output
  feature (one materialise function, one refresh tool entry).
  Acceptable because the alternative is either (a) no plugin
  features at all, or (b) plugin features that break for non-
  Obsidian users.

**Neutral.**

- The policy doesn't take a position on which plugins are *worth*
  shipping integration for. That's still a per-feature decision
  driven by research utility. The policy only constrains *how*
  integration is shipped if it is shipped.
- Existing v6 features all comply with this policy already. The
  `vault_correct_evidence` callouts are plain markdown that
  Obsidian renders specially; the snapshot, theme, moment, and
  inbox renderers emit only standard markdown. ADR 0007 codifies
  what the codebase was already doing, and unblocks new features
  (notably `vault_refresh_dashboards`) that need an explicit
  policy to land cleanly.

## Alternatives considered

- **Forbid plugin syntax outright.** Rejected. Some plugin
  features (Dataview live queries over evolving theme/moment data)
  are genuinely better UX in Obsidian than any static rendering
  the framework can provide. Forbidding them gives up that
  utility for no gain. The dual-output requirement preserves the
  benefit while preventing the breakage.
- **Embrace plugins fully — make Obsidian + a specific plugin set
  the assumed deployment.** Rejected on the v5 reframe grounds:
  the project is research infrastructure, not "one analyst's
  Obsidian setup, productized." A research group that doesn't
  install Dataview should still see correct content.
- **Per-feature decisions with no overarching policy.** Rejected:
  every plugin question becomes a re-litigation of the same
  ground. A documented policy turns repeated debates into
  one-time review against the rule.
- **Maintain snapshots in the SQLite index only, not back in
  markdown.** Rejected on the source-of-truth invariant. The
  markdown vault must be self-describing — handing a researcher
  the directory should give them the full analytical record
  without needing the SQLite database. Materialising back into
  markdown preserves that property.
- **Generate plugin syntax dynamically when a tool result is
  served, so the markdown on disk stays plain.** Rejected because
  the *source* of the rendered view is the markdown the user
  edits in Obsidian, not a tool result. Dynamic generation would
  diverge the LLM's view from the analyst's view, which is
  exactly what dual-output prevents.

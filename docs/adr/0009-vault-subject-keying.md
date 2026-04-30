# ADR 0009: Vault subject-keying — optional frontmatter, set-once, with cross-subject preserved

- **Status:** Accepted
- **Date:** 2026-04-29
- **Related:** [ADR 0002 (`subject_id` audit-scoping)](0002-subject-id-scoping.md), [ADR 0006 (Vault overhaul v6)](0006-vault-overhaul-v6.md), [ADR 0007 (Rendering layers policy)](0007-rendering-layers-policy.md), [ROADMAP.md § Per-subject parameter scoping on vault tools](../../ROADMAP.md#per-subject-parameter-scoping-on-vault-tools), [docs/design/research-framing.md](../design/research-framing.md)

## Context

ADR 0002 made `subject_id` a first-class audit column and threaded it
through the router, including `_dispatch_vault()`. That ADR
deliberately deferred *vault* subject-keying as "an open design
question" — how should themes, moments, and failure-mode notes
organise by participant when the same vault serves a multi-subject
study? At the time the deferral was correct: the framework had no
worked multi-subject pilot, and committing to a vault layout would
have been guessing.

The 2026-04-29 `integration-auditor` review of the multi-subject
pilot framing showed why the deferral cannot continue. By week 3 of
a 10-participant study running against a single shared vault, two
failure modes are observable:

- A theme like `themes/hr-drift-on-long-runs.md` accumulates
  evidence blocks from multiple participants in the same markdown
  file with no per-block attribution. The append-only invariant
  preserves the chronology but not the subject. A reviewer reading
  the file three months later cannot tell whose drift the third
  evidence block describes.
- `vault_search_notes` returns hits across every participant
  indistinguishably. An analyst asking "what have we learned about
  P004?" gets cohort-wide results back, with the subject filtering
  pushed to the human eye.

Both failures were silent in single-subject use (the implicit subject
was always the same), and both surface immediately at the
multi-subject scale that v6.2's research-framing document now
locks in: 5–20 participants, light IRB, one lab.

The constraint shape:

1. The vault has existing notes from v6.0 and v6.1 deployments with
   no `subject_id` frontmatter. Back-compat must hold.
2. Some hypotheses are genuinely cohort-level ("does pre-run
   carbohydrate timing affect HR drift across the cohort?"). Forcing
   every theme to claim a single subject is the wrong default.
3. The router already extracts `subject_id` from arguments and threads
   it to audit ([`router.py:572-630`](../../src/biosensor_mcp/framework/router.py)).
   All 25 vault tools now declare `subject_id` in their `param_schemas`
   (Phase B of v6.2). The renderer and the SQLite index are the layers
   that have not yet been taught.
4. ADR 0002's own neutral consequence states: *"How the vault
   organizes notes by subject is deliberately deferred — tracked on
   the roadmap as its own design question."* That deferral is the
   slot this ADR fills.

The question this ADR answers: *what is the lightest change to the
vault layer that closes the multi-subject failure mode without
overcommitting to v6.3+ shapes (multi-analyst attribution,
manuscript-freeze export, full provenance hashing)?*

## Decision

Vault notes carry an **optional, set-once `subject_id` in
frontmatter**. Evidence and moment renderers stamp the subject of
the call that wrote them. The SQLite index gains a nullable
`subject_id` column on `vault_notes` and filters search/list queries
by subject when one is provided, keeping cross-subject and legacy
notes visible.

Concretely:

- **Themes are subject-scoped optionally.** `vault_upsert_theme`
  accepts an optional `subject_id`. When present, it stamps the
  theme's frontmatter (`subject_id: "P004"`). When absent, the theme
  is cross-subject — the implicit semantics of every existing v6.1
  theme. A theme's subject is **set-once**: the first call that
  passes a non-null `subject_id` claims the theme; subsequent calls
  passing the same value are idempotent; a call passing a *different*
  value raises an error and writes nothing. Promoting a cross-subject
  theme to subject-scoped is permitted; reassigning a scoped theme
  to a different subject is not, by design.
- **Evidence blocks carry the subject of their writing call.** When
  a `vault_upsert_theme` call provides `subject_id`, the appended
  evidence block's metadata line gets a `subject:` field. Existing
  blocks with no subject line are read as "subject unspecified",
  preserving the historical record without rewriting markdown.
- **Moments carry the subject of their writing call.**
  `vault_capture_moment` accepts optional `subject_id`. When
  present, the renderer stamps the moment's frontmatter and the
  rendered body. Same back-compat rule.
- **`vault_notes` gains a nullable `subject_id` column.** Migration
  on open via `ALTER TABLE` if the column is absent — the same
  pattern `audit_log` used for `subject_id` and `scrubber_id`
  ([`audit.py:107-118`](../../src/biosensor_mcp/framework/audit.py)).
  Backfill happens lazily on the next `vault_rescan`, which already
  parses frontmatter on every note it touches.
- **Search and list filter on subject when one is provided.**
  `vault_search_notes`, `vault_list_notes`, `vault_list_themes`,
  `vault_list_moments`, and `vault_list_failure_modes` accept an
  optional `subject_id`. When present, the query returns rows where
  `vault_notes.subject_id = ?` **OR** `vault_notes.subject_id IS
  NULL`. The `IS NULL` branch is deliberate — it keeps cross-subject
  themes (cohort hypotheses) and v6.1-era legacy notes visible to a
  subject-filtered query, because both are relevant to a session
  about that participant. When `subject_id` is absent, the query
  returns every row, matching current behaviour.
- **`vault_correct_evidence` propagation stamps the subject.** With
  `propagate=True`, the `[!warning]` callouts already appended to
  every wikilinking note gain the subject in the callout text:
  `> [!warning] Corrected evidence for P004 — see ...`. The
  propagation set is *not* filtered by subject in v6.2 — the warning
  surfaces on every linker, scoped or otherwise. Subject-aware
  propagation filtering is a v6.3 refinement.
- **Failure modes already declare `related_subjects`.**
  `vault_log_failure_mode` accepts a `related_subjects` list
  parameter. This ADR records that surface as the failure-mode side
  of the same subject-keying story — no schema change to the tool;
  the index column is what makes the list queryable.

The renderer and storage layers — currently subject-agnostic — are
the implementation surface this ADR authorises:

- `framework/vault/renderer.py` gains `subject_id` parameters on
  the theme, moment, and evidence-block render paths.
- `framework/vault/storage.py` adds the nullable column, the
  migration, and `subject_id`-aware query variants on the
  list/search methods.
- `framework/vault/parser.py` reads the new frontmatter key when
  `vault_rescan` revalidates the index.
- `framework/vault/layer.py` plumbs the parameter from the validated
  call into the writer and the index update, and enforces the
  set-once invariant on `vault_upsert_theme`.

What this ADR does **not** authorise — explicitly out of scope for
v6.2, tracked separately on ROADMAP:

- Subject-aware search ranking (rows matching the requested subject
  weighted above `IS NULL` rows).
- Cross-subject theme aggregation (a tool that surfaces "themes
  open across ≥3 subjects").
- Multi-analyst attribution interaction with subjects (whose call,
  about whose participant, written into which note).
- Vault-freeze export-by-subject (manuscript-time IRB-friendly
  bundles).

## Consequences

**Positive.**

- The week-3 multi-subject failure mode the proposal-mode auditor
  named is closed without rewriting any existing v6.1 vaults. Legacy
  notes remain readable, queryable, and visible to subject-filtered
  searches.
- An analyst running a session for P004 can pass `subject_id="P004"`
  to `vault_search_notes` and see only P004-scoped results plus
  cohort-level themes, without the framework guessing what
  cross-subject means.
- Evidence provenance (ADR 0006) and subject attribution compose
  cleanly: an evidence block already carries `> Source: …`; v6.2
  adds a `subject:` field on the same metadata line. Both are part
  of the audit trail that makes a derivation re-checkable months
  later.
- The set-once rule on theme subject prevents the most likely
  misuse — a script accidentally reassigning P003's theme to P007
  and quietly losing the prior scope.
- The `IS NULL` branch in filtered queries means the framework
  treats unscoped notes as cohort-relevant by default, which is the
  correct semantics for cross-subject hypotheses and the only safe
  semantics for legacy notes.

**Negative.**

- Two notes can describe overlapping observations on different
  participants without the framework noticing. A theme called
  `hr-drift` scoped to P004 and another `hr-drift-cohort` left
  unscoped will both surface on a P004-filtered query — by design,
  but a sloppy analyst could create the same hypothesis twice
  under two different scopes. Mitigated by `vault_health_check`
  growing a "themes with similar slugs across scope boundaries"
  signal in v6.3.
- The set-once rule produces a hard error on subject reassignment.
  An analyst who genuinely needs to retarget a theme must open a
  new theme and reframe-link the old one. This is the right
  default — silent reassignment is the failure mode the rule
  prevents — but it adds friction to a recovery path.
- Lazy backfill on `vault_rescan` means the index lags reality
  until the next rescan completes. A subject-filtered query
  immediately after a v6.2 upgrade may miss notes whose frontmatter
  was already correct but whose index row hasn't been refreshed.
  Acceptable: rescan is cheap, and the upgrade path documents the
  step.

**Neutral.**

- The vault stays flat by frontmatter, not by directory. A theme
  about P004 lives at `themes/hr-drift-on-long-runs.md`, not
  `themes/P004/hr-drift-on-long-runs.md`. Wikilinks, slugs, and
  cross-references continue to work without subject-aware path
  resolution.
- The `subject_id` regex from ADR 0002
  (`^[A-Za-z0-9_\-]{1,64}$`) is reused unchanged. Vault tools
  validate against the same shared schema running tools already use.
- ADR 0007's rendering-layers policy holds: every change is plain
  markdown that renders correctly in any editor. The `subject:`
  metadata line, the warning callout text, and the frontmatter key
  are all source-of-truth content with no plugin dependency.
- ADR 0006's append-only evidence invariant holds. New blocks
  carry `subject:`; old blocks are not rewritten.

## Alternatives considered

**Mandatory `subject_id` on every theme and moment.** Rejected. It
breaks back-compat with every v6.0 and v6.1 vault in the wild —
existing themes have no subject and are not safely defaultable to
one. It also forces cohort-level hypotheses ("does pre-run carb
timing affect drift across the cohort?") into a synthetic scope
value like `subject_id="cohort"`, which is exactly the kind of
sentinel that ADR 0002 rejected for `audit_log`. Optional
frontmatter with explicit cross-subject semantics handles both
cases without a special string.

**Hash-based subject keys for pseudonymisation.** Rejected. A
content-addressed scheme (e.g. `subject_id = sha256(participant_id +
study_salt)`) would commit the framework to a particular IRB
workflow for identifier pseudonymisation. That is the IRB's
decision, not the framework's. The regex from ADR 0002 already
permits `P004`, `SUBJ-001`, `subj_042`, and any hashed token a
researcher cares to compute upstream. Pushing the format down into
the framework is scope creep that buys no governance the IRB hasn't
already approved.

**Per-subject vault subdirectories.** Rejected. Routing P004's
notes into `themes/P004/`, P007's into `themes/P007/`, and
cohort-level work into `themes/cohort/` looks orderly but breaks
the case it should serve. A cross-subject hypothesis comparing
drift across the cohort has no natural home — `themes/cohort/`
is a different sentinel from "no subject scope," and the directory
layout forces the analyst to commit to one before the hypothesis
has settled. It also breaks every existing wikilink in v6.1
vaults at upgrade time. The vault stays flat; subject is a
frontmatter field, not a path component.

**Defer entirely to v6.3.** Rejected. The proposal-mode auditor
named the unattributed-evidence accumulation as the load-bearing
failure mode for the v6.2 multi-subject pilot framing. Deferring
the decision means the v6.2 pilot ships with the failure mode
present and observable; an analyst running a 10-participant study
in v6.2 hits the silent-cross-subject-search problem in week 3 of
their first study. The lightweight resolution this ADR specifies
fits inside v6.2 and unblocks the pilot. The genuinely deferred
items (search ranking, cross-subject aggregation, multi-analyst
attribution, freeze-by-subject) are tracked separately on ROADMAP
and remain v6.3+.

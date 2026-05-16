# ADR 0038: Vault layer is data-source-agnostic

- **Status:** Proposed
- **Date:** 2026-05-16
- **Related:** [ADR 0007 (Rendering-layers policy)](0007-rendering-layers-policy.md), [ADR 0008 (Deterministic-by-construction processing)](0008-deterministic-by-construction-processing.md), [ADR 0009 (Vault subject-keying)](0009-vault-subject-keying.md), [ADR 0011 (Promotion policy)](0011-promotion-policy.md), [ADR 0024 (Wheel-distributed tour and fixture bundling)](0024-wheel-distributed-tour-and-fixture-bundling.md), [ADR 0025 (Cue-card rehearsal as release gate)](0025-cue-card-rehearsal-as-release-gate.md), [ADR 0027 (Demo as researcher first-look)](0027-demo-as-researcher-first-look.md), [ADR 0029 (Token reduction as analytical quality)](0029-token-reduction-as-analytical-quality.md)

## Context

[ADR 0027](0027-demo-as-researcher-first-look.md) (2026-05-06, v6.10.5)
reframed `tailor demo` from synthetic-Strava operator self-verification
to a researcher first-look against the bundled HIP Lab fixtures. That
ADR's reshape was complete for the *demo data layer*: `demo/runner.py`
was rewritten, `_fixtures/hip_lab_demo_realistic/` shipped, the
synthetic-Strava `sample_data.py` was preserved under
[ADR 0008](0008-deterministic-by-construction-processing.md)
§ Alternatives but no longer fed the demo.

ADR 0027 did **not** extend the reshape to the **vault layer**. Vault
tool descriptions, internal helpers, fallback paths, and the snapshot
regenerator continued to treat the running child as the canonical
biosensor user — a v3-era assumption from a time when the running
child was the only registered child. That assumption no longer holds.
`csv_dir`, `matlab_file`, `redcap_file`, `force_csv`, and `emg_csv`
have all landed as children of equal standing since
[ADR 0015](0015-tier-1-cohort-surface-and-metadata-sidecar.md) and the
v7.2 / v7.3 source-axis releases. The vault layer's user-visible
surfaces drifted behind that change without anyone noticing, because
none of the orientation paths are exercised on the boss's dev box —
the boss runs against a Strava-shaped vault every session, and the
orientation tools produce sensible output for that case.

On 2026-05-16, a first-real-recipient hand-driven run on Windows +
Claude Desktop against the HIP Lab demo surfaced the drift. The
orientation layer leaks Strava-shaped framing at three concrete sites
that a science recipient with no running child registered would hit
on first contact:

1. **`vault_get_snapshot` fallback.** When `snapshot.md` is absent
   (every fresh deployment except the bundled tour fixture's), the
   tool falls back to `vault_get_fitness_summary`, which counts only
   `domain="running"` notes for `total_notes_in_vault` and emits a
   remediation hint that names `strava_sync`. A HIP Lab deployment
   with 16 force-CSV subjects and zero running activities sees
   `total_notes_in_vault: 0` and is told to "call strava_sync" — a
   command the deployment cannot run, in a child it has not
   registered.
2. **Snapshot renderer "Weekly Summary" section.** The renderer
   always emits a `## Weekly Summary (last 4 weeks)` header. On a
   non-running deployment the body is `*(No recent run data.)*` —
   the section header itself plants the assumption that "weekly
   running summary" is what a vault is for, contradicting the
   project's stated source-agnostic framing.
3. **Tool descriptions.** Several `VaultLayer.tool_definitions`
   strings name Strava-specific surfaces as if they are canonical:
   `vault_get_fitness_summary`'s description ends with the
   parenthetical *"no Strava sync needed"* — the negation gives
   Strava conceptual primacy on a non-running deployment.
   `vault_list_notes`'s description mentions *"themes and moments
   alongside run/trend/compare notes"* without acknowledging that a
   `redcap_file`-only or `force_csv`-only deployment has no such
   notes. `evidence_source_tool` and `evidence_source_domain`
   example lists name only `'strava_run_report'` and `'running'`.

A read-only [`cue-card-rehearsal-auditor`](../../.claude/agents/cue-card-rehearsal-auditor.md)
audit (per [ADR 0025](0025-cue-card-rehearsal-as-release-gate.md))
identified 20+ Strava/running-coupled sites in `framework/vault/layer.py`
alone. The demo hot-path above is a subset.

This ADR answers the question: *what does the vault layer assume
about which biosensor child is registered, and what should it
assume?*

## Decision

The vault layer (`framework/vault/`) holds **what the user knows
about the question**, regardless of which biosensor or non-biosensor
child supplied the source data. A registered running child is one
valid composition; a registered `force_csv` + `emg_csv` + `mrs`
triple is another; a registered `redcap_file` child is another; an
analytical-notes-only vault with no biosensor children registered
at all is also valid. Vault tool descriptions, internal helpers,
fallback paths, and orientation rendering must be data-source-agnostic
— they may name a specific child as an example, but they must not
embed the assumption that any particular child is canonical or
always-present.

The rule, plain English: a tool description that says *"no Strava
sync needed"* gives Strava conceptual primacy on a non-running demo.
The negation is the assumption. Drop it.

Concrete mechanism, landing across two releases:

**v7.3.4 — partial closure on the demo hot-path:**

- `_handle_fitness_summary`'s empty-notes fallback is rewritten to
  surface non-Strava remediation when no running child is registered.
  It reports a cross-domain note count (not just `domain="running"`),
  uses a "Vault is empty" framing on fresh deployments, and points at
  `vault_get_snapshot` / `vault_list_moments` instead of `strava_sync`.
- The snapshot renderer drops the `## Weekly Summary (last 4 weeks)`
  section header entirely when `weekly_summary` is empty. The previous
  shape was: always render the header, body `*(No recent run data.)*`.
  The new shape: render nothing.
- `vault_get_fitness_summary`'s description loses the *"no Strava
  sync needed"* parenthetical and is reframed as *"weekly aggregate
  table for any registered biosensor children"* with a pointer to
  the v7.3.4 snapshot-first orientation flow.
- `vault_list_notes`'s description swaps *"themes and moments
  alongside run/trend/compare notes"* for *"themes, moments, failure
  modes, dashboards, and (when a biosensor child is registered)
  per-activity reports like run / trend / compare notes."*
- `evidence_source_tool`'s example list widens from
  `'strava_run_report'` to
  `'force_cohort_summary', 'csv_summary_report', 'strava_run_report'`.
- `evidence_source_domain`'s example list widens from `'running'` to
  `'force_csv', 'csv_dir', 'redcap_file', 'running'`.

**v7.4.0 — structural sweep of the remaining ~20 sites:**

- The class-level constant `("run_report", "trend_report", "compare_runs")`
  at the top of `VaultLayer` (currently the assumed canonical kind list)
  is derived from registered children rather than hardcoded.
- `_kind_to_domain` (currently hardcodes `run_report → running`) is
  generalised, or its inverse responsibility is moved to the children
  themselves.
- Backfill config defaults that name `strava_list_runs` /
  `strava_run_report` at the top-level wiring become callable indirections
  rather than hardcoded names. These are load-bearing (the wiring site
  in `__main__.py` per [ADR 0024](0024-wheel-distributed-tour-and-fixture-bundling.md)
  already passes them as `backfill_config`); the v7.4.0 work removes
  the *defaults*, not the indirection.
- Internal helpers using `domain="running"` queries in non-fallback
  paths (e.g. `_build_snapshot_payload`'s Strava-deployment branch)
  become data-source-aware rather than data-source-assumed.
- The asymmetric param-validation strictness across `csv_cohort_summary`
  (runtime-pinned `allowed_values`) vs `force_cohort_summary` /
  `emg_cohort_summary` (free-form `str`) is reconciled — the
  cue-card-rehearsal-auditor named this as queued v7.4.0 work.
- The `value_column` vs `column` API-parity asymmetry across
  `force_cohort_summary` / `emg_cohort_summary` (use `value_column`)
  and `csv_cohort_summary` (uses `column`) is reconciled. v7.3.4
  closed the parallel `group_field` ↔ `group_by` asymmetry; this is
  the remaining half.
- The two competing "call first" orientation tools —
  `vault_get_fitness_summary` and `vault_get_snapshot` — collapse to
  one canonical orientation surface. The current state is a v6.0-era
  surface that has been silently superseded by v6.1's snapshot but
  never retired.

The v7.4.0 work is named explicitly here so the partial closure
v7.3.4 ships does not drift indefinitely. v7.4.0's cycle accepts
this ADR (or revises it under recipient evidence per the reversal
condition below) on full implementation; v7.3.4 lands the partial
closure plus this ADR as the visible commitment.

## Consequences

### Positive

- The orientation layer matches the project's stated framing. A
  recipient running the HIP Lab demo for the first time no longer
  sees a Strava-shaped fallback that contradicts CLAUDE.md
  § "What This Project Is" — the demo and the orientation layer
  agree on what the framework is for.
- The vault layer's invariant is now nameable. A future contributor
  proposing a new vault tool can evaluate it against one rule:
  *"would this description make sense to a recipient with no
  running child registered?"* — the same shape as
  [ADR 0007](0007-rendering-layers-policy.md)'s plain-markdown rule.
- The AI-economics claim ([ADR 0029](0029-token-reduction-as-analytical-quality.md))
  is honoured at the orientation surface. A Strava-shaped fallback
  on a HIP Lab deployment misleads the LLM about what the analyst's
  Wardrobe contains, which costs context budget on every subsequent
  call as the LLM works around the wrong frame.
- The cue-card-rehearsal-auditor ([ADR 0025](0025-cue-card-rehearsal-as-release-gate.md))
  has a concrete invariant to enforce on every future vault-layer
  diff: tool descriptions must not name a child-specific tool or
  domain as canonical. The gate that surfaced this drift becomes a
  recurring backstop, not a one-time catch.
- The reshape [ADR 0027](0027-demo-as-researcher-first-look.md)
  started is completed. The demo data layer was sweep-clean in
  v6.10.5; the vault layer carries the same property after v7.4.0.

### Negative

- The v7.4.0 sweep touches code that is currently green and ships
  output the boss reads daily — a regression risk on the
  Strava-shaped deployment that the cue-card-rehearsal-auditor's
  per-prompt rehearsal is the primary defence against. Every v7.4.0
  PR touching `framework/vault/layer.py` requires the gate to
  rehearse both a Strava-shaped vault and a non-running vault and
  pass on both.
- Two release boundaries (v7.3.4 partial, v7.4.0 structural) means
  the codebase carries an in-between state where some tool
  descriptions are data-source-agnostic and others are not. The
  v7.3.4 banner names this explicitly and links to this ADR so a
  reader who notices the asymmetry has the closing date.
- Deriving the canonical kind list from registered children (rather
  than the current hardcoded `("run_report", "trend_report", "compare_runs")`)
  expands the `ChildMCP` contract surface. A child that wants its
  per-activity reports to participate in the vault's snapshot
  rendering would need to declare them. Mitigated by keeping the
  v7.4.0 design backwards-compatible — a child that declares
  nothing inherits empty defaults; the running child is the
  reference implementation.

### Neutral

- The vault subject-keying invariants from
  [ADR 0009](0009-vault-subject-keying.md) are unchanged. The
  data-source-agnostic property applies to *which child supplied
  the underlying data* and not to *which subject the call was about*;
  subject-keying continues to thread through every vault tool's
  `subject_id` parameter regardless of which biosensor child wrote
  the source note.
- The seeded snapshot.md bundled with the HIP Lab tour fixtures
  ships under [ADR 0007](0007-rendering-layers-policy.md)'s
  source-of-truth-markdown rule (plain markdown, AI-readable, no
  plugin tokens) and is synthetic-by-construction per
  [ADR 0024](0024-wheel-distributed-tour-and-fixture-bundling.md)'s
  precondition. No change to either invariant.
- The deterministic-by-construction permit-list in
  [ADR 0008](0008-deterministic-by-construction-processing.md)
  already names the vault renderer's clock-read seam; the renderer
  changes in v7.3.4 + v7.4.0 do not add new clock reads or new
  PRNG calls. No amendment to ADR 0008 is required.
- The promotion bar for new vault-layer assumptions is now
  agent-enforced. The cue-card-rehearsal-auditor's per-prompt PASS /
  WRONG-TOOL / WRONG-PARAMS / AMBIGUOUS verdicts on a deliberately
  non-running deployment fixture replace any per-PR debate over
  whether a description is "too Strava-shaped."

## Reversal condition

If a future external contributor or operator can demonstrate that
data-source-agnostic vault tool descriptions are *harder* to
understand for a recipient than child-specific descriptions —
e.g. a beachhead lab evaluation finds that *"weekly aggregate
table for any registered biosensor child"* is more confusing than
*"weekly run summary"* — retire this invariant and revert to a
child-specific naming scheme keyed on the most-commonly-registered
child for a given deployment.

The reversal needs at least one piece of recipient evidence (a
user study, a real recipient complaint, or a researcher feedback
note) — not just a maintainer's intuition. Same shape as
[ADR 0011](0011-promotion-policy.md)'s reversal-condition pattern:
the structural argument lands on evidence, the rollback requires
counter-evidence.

## Alternatives considered

**Sweep the vault layer in a single v7.4.0 release, no v7.3.4
partial closure.** Rejected. The 2026-05-16 first-real-recipient
run produced a finding the boss elevated specifically because a
science recipient was hitting the Strava-shaped fallback on a HIP
Lab demo right then. A two-cycle wait for the structural sweep
would leave the demo hot-path broken for every recipient in that
window. The partial closure ships the four concrete demo-path
sites where the drift is recipient-visible; the structural sweep
follows behind because the remaining ~20 sites are not on the
demo hot-path and the sweep risk is non-trivial.

**Defer the structural sweep indefinitely; ship only the v7.3.4
partial closure.** Rejected. Partial closures without a named
completion cycle are how
[ADR 0027](0027-demo-as-researcher-first-look.md)'s reshape
stopped at the demo layer for half a year. This ADR exists
specifically to make the v7.4.0 scope a visible commitment rather
than a drift-prone aspiration. The "Done in v7.3.4 / Queued for
v7.4.0" split in the Decision section above is structural, not
prose-cosmetic.

**Refactor the vault layer so the running child is registered as
the canonical example child by default.** Rejected. The structural
argument behind this ADR is that *no child is canonical* — the
running child is a worked example, per CLAUDE.md's explicit
framing. Naming it canonical-by-default in code would re-encode
the very assumption this ADR removes.

**Add a per-child registration hook that lets each child declare
its own vault-layer description fragments (canonical-domain
prose, canonical-tool prose, example evidence sources).** Rejected
for v7.3.4 / v7.4.0; reconsiderable later. The hook would
generalise the data-source-agnostic property into a registration
contract, which is the right shape if a third axis of customisation
emerges. v7.4.0 ships the simpler intervention (description prose
that names children only as examples, never as defaults) and waits
for the third structural pressure before promoting to a hook —
same shape as [ADR 0011](0011-promotion-policy.md)'s promotion bar.

**Drop the v6.0-era `vault_get_fitness_summary` tool entirely;
keep only `vault_get_snapshot`.** Considered for the v7.4.0 sweep;
deferred. `vault_get_fitness_summary` is the older orientation
surface and predates the snapshot pattern by a full minor version.
The right move is collapsing the two competing "call first" tools,
but the collapse needs a deprecation cycle to avoid breaking
external cue cards that may still name the older tool. v7.4.0
adds the deprecation hint; a future v7.5.x removes the tool.

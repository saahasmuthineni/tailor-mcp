# ADR 0034: Retire `tailor migrate` — the v6 → v7 migration population was empirically zero

- **Status:** Accepted
- **Date:** 2026-05-12
- **Supersedes (in part):** [ADR 0031 (Project rename to Tailor + Wardrobe)](0031-rename-to-tailor-and-wardrobe.md) — the v6 → v7 migration mechanism retires (`tailor migrate` subcommand, the startup warning, the `_legacy_config_dir` helper). The rename decisions themselves (display name *Tailor*, PyPI `tailor-mcp`, Python import `tailor`, CLI command `tailor`, `~/.tailor/` config dir, `TAILOR_*` env vars, dual-prefix Claude Desktop cleanup) are retained
- **Related:**
  - [ADR 0028 (Recipient-install validation as a release-time gate)](0028-recipient-install-validation-as-release-gate.md) — the validator's empirical falsification, combined with the v6.10.x patch quartet's fresh-install-only failure surface, is the cumulative evidence that no v6 install ever escaped the dev box into the wild
  - [ADR 0032 (Retire the public-mirror distribution path)](0032-retire-public-mirror-distribution.md) — the wheel-by-email distribution reshape that makes every future install a fresh install of a current wheel; there is no upgrade path that requires data migration through Phase 1
  - [ADR 0033 (Complete the Tailor metaphor on the workshop side)](0033-complete-tailor-metaphor-workshop-side.md) — the other v7.0.x retirement of a v7.0.0 invariant; same supersede-in-part pattern this ADR follows
  - [CLAUDE.md § v7.0.8 banner](../../CLAUDE.md) — Phase 0 closure on the lenient read; names the cumulative empirical record this ADR cites

## Context

[ADR 0031](0031-rename-to-tailor-and-wardrobe.md) shipped the v7.0.0
rename on 2026-05-08. Among its load-bearing decisions was a migration
story: a `tailor migrate` CLI subcommand that copies the v6.x default
config directory `~/.biosensor-mcp/` to the v7 location `~/.tailor/`
non-destructively, paired with a one-line startup warning emitted on
every `tailor` invocation when the legacy directory exists and the new
one is absent or empty. ADR 0031 § "Migration story" and §
"Filesystem migration" jointly codified the mechanism. The subcommand
and the warning shipped together as scaffolding for an existing v6
user population that would, the reasoning went, want to upgrade
without losing tokens, configs, audit logs, vault state, or child
caches.

At v7.0.0 ship time the existence of that population was hypothesised,
not measured. The framework had been actively developed under the
*Biosensor MCP* name through v6.13.0 and had been the subject of an
extensive recipient-install push (v6.10.x patch quartet, v6.11.0
recipient-install-validator, v6.11.x hardening). The recipient-install
work generated evidence about the *recipient* path; it did not
generate evidence either way about whether any of those recipients
ended up with a durable v6 install they would later upgrade. The
migration mechanism was defensible scaffolding under that uncertainty.

The four-week empirical record from v7.0.0 ship through 2026-05-12
collapses the uncertainty in one direction:

1. **The v6.10.x patch quartet** (cp1252 glyphs, SetupHelpLayer +
   RECIPIENT_README, sibling-cleanup, dual-path Claude Desktop config)
   all surfaced fresh-install failures, not migration failures. Each
   bug required recipient state the dev machine could not reach by
   construction; in every case the recipient state was that of a
   user installing the wheel from scratch, not upgrading from a prior
   version. The pattern across [ADR 0028](0028-recipient-install-validation-as-release-gate.md)
   § Context is recipient-cold-install across the board.
2. **The v6.11.0 `recipient-install-validator`** was the team's
   structural answer to closing the wheel-to-stranger-machine seam.
   Project memory records that its second wild run silently parked
   past every named timeout — the agent went quiet rather than
   reporting; the prose hardenings (halt-on-exit, watcher discipline,
   progress emission) did not survive contact with the failure mode.
   The validator's falsification is not a v6 → v7 finding, but it is
   evidence that the team did not at any point successfully provision
   a wheel-installed v6 environment that would later need to migrate.
3. **The 2026-05-09 self-driven Windows install** of v7.0.0 ran on
   the project author's own machine. A fresh Windows user account is
   not a recipient by the ADR 0028 definition; it tests the install
   path against the author's own environment.
4. **The 2026-05-12 macOS install** was the first true outside-recipient
   event in the project's history (a friend, the author watching
   only). It was a clean install from a current wheel onto a machine
   with no prior Tailor or Biosensor MCP state.

No reported install, attempted install, debugged install, or
fresh-install bug across the entire empirical record describes a
machine that had `~/.biosensor-mcp/` present and was attempting to
upgrade to `~/.tailor/`. The population the migration mechanism was
scaffolded for has zero observed members.

The smoking-gun evidence is internal to the mechanism itself. On
2026-05-12 the author needed to relocate the dev box's own
`~/.biosensor-mcp/` to `~/.tailor/` and discovered that `cmd_migrate`
copies the directory tree but never rewrites the absolute paths
embedded inside the copied JSON config files — neither the Claude
Desktop config block (which contains an absolute path to the Python
interpreter and to `TAILOR_CONFIG_DIR`) nor `user_config.json` (which
contains absolute paths for `csv_dir.path` and `vault_path` on the
pilot wizard's output). The author patched the gap by hand on the
dev box. If the subcommand had ever run for a real v6 recipient, the
gap would have produced a broken Claude Desktop start (the wrong
interpreter path) and a wizard that pointed at the wrong CSV
directory. Neither failure has been reported because the subcommand
has never been invoked outside the project author's own machine.

[ADR 0032](0032-retire-public-mirror-distribution.md) reshaped
distribution to wheel-by-email through Phase 1, with GitHub Pages on
the source repo deferred to Phase 2 PyPI publication. Under that
distribution shape, every install through the rest of Phase 1 is a
fresh install of a current wheel — there is no version-upgrade path
that crosses a major-version boundary because every recipient
receives the current wheel for their first install. The migration
mechanism's intended population (existing v6 users) is structurally
out of scope for the distribution channel that actually exists.

The structural question this ADR answers: *given that the migration
mechanism is scaffolding for a population the team has spent four
weeks unsuccessfully trying to find, what is the smallest correct
disposition of that scaffolding?*

## Decision

Retire `tailor migrate` and its associated startup warning entirely
in v7.0.9. The plain-English rule: defensive code for a population
the team has decided is empty is worse than no code — it offers a
hypothetical recipient confidence in a workflow that has never been
validated end-to-end, and the path-rewrite gap surfaced 2026-05-12
means that even an honestly-rewritten warning would still point a
recipient at a workflow that produces a broken Claude Desktop start.

The mechanism, in concrete terms:

- **Delete `cmd_migrate`** from [`src/tailor/__main__.py`](../../src/tailor/__main__.py).
  The function and its docstring (which cites ADR 0031 § "Filesystem
  migration") both retire. The `migrate` entry in the subcommand
  dispatch dict retires alongside the function.
- **Delete `_emit_legacy_migration_warning_if_applicable`** from the
  same file. The function's call site at the top of `main()` retires
  with it. A `tailor` invocation on a machine where `~/.biosensor-mcp/`
  happens to exist no longer emits any breadcrumb; the legacy directory
  is treated as inert filesystem state the framework does not see.
- **Delete `_legacy_config_dir`** from the same file. The helper's
  only two consumers were `cmd_migrate` and the warning function; both
  retire in this same change. Verified by inspection that no other
  call site reads from it.
- **Remove the `tailor migrate` row** from the module docstring at
  the top of [`__main__.py`](../../src/tailor/__main__.py) so the
  `tailor --help` surface no longer advertises the command.

The retirement is total, not partial. The boss-architect's framing
on 2026-05-12 was *"drop entirely"* over *"rewrite the warning
text."* The grounds: a rewritten warning ("manual rename does not
rewrite embedded paths; fresh install recommended") would still
gesture at a workflow that has never been validated by any
recipient, and the workflow's path-rewrite gap means that any
recipient who follows it ends up with the same broken Claude
Desktop start the dev box hit on 2026-05-12. There is no honest
text to put in the warning that points at a working workflow,
because there is no working workflow.

## Consequences

### Positive

- **The CLI surface no longer carries scaffolding for an
  empirically empty population.** `tailor --help` becomes shorter by
  one row; new users see a coherent surface with no commands whose
  documented purpose is *"recover from an upgrade scenario nobody
  has ever encountered."*
- **The framework no longer makes a load-bearing claim it cannot
  honour.** ADR 0031 § "Migration story" describes a path-preserving,
  non-destructive upgrade. The 2026-05-12 path-rewrite finding
  showed that the actual implementation does not preserve paths.
  Retirement closes the gap between the claim and the implementation
  by retiring the claim, which is the correct disposition when the
  population the claim was made for has zero members.
- **Phase 1 housekeeping advances by exactly its stated purpose.**
  [CLAUDE.md § v7.0.8 banner](../../CLAUDE.md) names *"ship-quality
  housekeeping"* as Phase 1's frame; retiring scaffolding for
  problems that do not exist is exactly that work. The retirement
  is the highest-leverage Phase 1 deliverable per the v7.0.8 banner's
  framing.
- **A future contributor reading git history sees the v6 → v7
  narrative grounded in ADR 0031 and superseded in part by ADR 0034.**
  The supersede-in-part chain makes the retirement reasoning durable
  rather than locating it only in commit messages or release notes.
  The contributor cannot reintroduce a migration mechanism by
  accident; the population-accounting argument is codified.
- **The `_legacy_config_dir` helper retires with its consumers.**
  Dead code does not accumulate. The retirement is clean rather than
  surgical.

### Negative

- **Reversal cost is non-trivial if a real v6 install surfaces.**
  Restoring `cmd_migrate` is a code-revert; restoring it correctly
  requires also fixing the path-rewrite gap (rewriting absolute
  interpreter paths in the copied Claude Desktop config block and
  absolute data paths in the copied `user_config.json`). In the
  meantime, the affected recipient has no in-framework path to
  upgrade: they would have to manually `mv ~/.biosensor-mcp
  ~/.tailor` and then hand-edit their Claude Desktop config and
  `user_config.json` to update embedded paths — the same hand-patch
  the project author applied on 2026-05-12. This cost is accepted on
  the empirical grounds that no such recipient has been observed and
  the distribution channel through Phase 1 does not produce one by
  construction.
- **The startup warning's removal means no breadcrumb on a system
  that does happen to have `~/.biosensor-mcp/` present.** A
  hypothetical recipient who installed a v6 wheel through some path
  the team did not record (e.g. a side-loaded wheel from before
  ADR 0032's distribution reshape) and now installs v7 would see no
  framework-side indication that their old directory exists. They
  would discover it only by inspecting their home directory by hand.
  Mitigation: that recipient is the same hypothetical zero-member
  population this ADR is structured around; the absence of a
  breadcrumb is consistent with the population-accounting argument.
- **The v7.0.0 banner in [CLAUDE.md](../../CLAUDE.md) continues to
  describe `tailor migrate` as load-bearing in that release.** Banner
  entries are dated historical records of what each release shipped,
  and rewriting them would falsify that record. A reader who scrolls
  top-to-bottom through the banner stack encounters the v7.0.0
  migrate paragraph and then learns from the v7.0.9 banner that the
  subcommand retired. The forward-cite path is present but indirect.
  Mitigation: the same pattern holds for [ADR 0030](0030-public-mirror-narrative-and-affordance-depth.md)
  banner / [ADR 0032](0032-retire-public-mirror-distribution.md)
  banner and [ADR 0031](0031-rename-to-tailor-and-wardrobe.md) banner
  / [ADR 0033](0033-complete-tailor-metaphor-workshop-side.md)
  banner — banner-stacking is the project's established convention
  for retirement.

### Neutral

- **No `src/` API changes beyond the CLI command removal.** No
  router, security pipeline, ChildMCP, vault, or audit changes. The
  ADR 0031 architectural rename (package directory, env vars, config
  paths, Claude Desktop key prefixes) is untouched; only the
  upgrade-path scaffolding retires.
- **No test changes beyond removal of any `cmd_migrate` /
  `_emit_legacy_migration_warning_if_applicable` regression tests
  that exist.** The corresponding tests retire alongside the code
  they exercise; nothing else in the suite assumes the migration
  mechanism is present.
- **[CHANGELOG.md](../../CHANGELOG.md) and the [ROADMAP.md](../../ROADMAP.md)
  § Shipped historical entries stay untouched.** Per the rename ADR's
  § "Historical preservation" convention, dated artifacts describing
  past state are preserved as written. The retirement is captured in
  forward-going documentation (this ADR, the v7.0.9 CLAUDE.md banner,
  a single-line forward-cite at the relevant ROADMAP shipped row).
- **The v7.0.0 dual-prefix Claude Desktop cleanup logic survives.**
  `_clean_claude_desktop_orphan_entries` and `_is_orphan_entry_key`
  match both legacy `biosensor-*` and current `tailor` / `tailor-*`
  keys; that matcher is independently load-bearing on `tailor tour`
  and `tailor uninstall` and is not affected by this retirement. A
  future fresh install on a machine that somehow has a legacy
  Claude Desktop entry still has that entry cleaned by the existing
  cleanup ritual.

## Alternatives considered

**Keep the subcommand and fix the path-rewrite gap.** The
straight-line *"finish the v7.0.0 work that ADR 0031 started"*
option. Rejected because building a feature for a population that
has zero observed members inverts the cost / benefit calculation.
The engineering hours required to correctly rewrite absolute paths
across the two relevant JSON files (Claude Desktop config block,
`user_config.json`) plus the test surface (every shape of
absolute-path embedding the wizard or tour can produce) are
non-trivial. Those hours are better spent on Phase 1 deliverables
that meet actual users. The fix would close a gap that has never
caused a recipient failure because no recipient has ever traversed
the mechanism.

**Keep the subcommand and document the path-rewrite gap.** Same
empirical objection as the previous alternative, with a second
problem layered on: documentation for a zero-population workflow
ages into stale noise. Future contributors reading the docs spend
time evaluating whether the documented gap is still real, whether
it applies to whatever change they are making, whether the workflow
should be tested in their PR. The maintenance overhead of
documentation accumulates linearly with project lifetime; the
benefit (a workflow nobody runs has accurate caveats) does not.

**Drop the subcommand but keep the warning with its original
text.** The minimally-intrusive option. Rejected because the
warning would actively point at a removed command (`Run \`tailor
migrate\``) — a strictly-worse end state than dropping both. A
recipient seeing the warning would type `tailor migrate`, receive
an error about an unknown subcommand, and end up in a worse
position than if they had not seen the warning. *"Lie loudly"* is
the failure mode the warning would land on.

**Drop the subcommand and rewrite the warning to acknowledge the
path-rewrite gap.** The honest-warning option: a single stderr line
explaining that the framework's automatic migration has retired,
that a manual `mv ~/.biosensor-mcp ~/.tailor` will not rewrite
absolute paths embedded in Claude Desktop config or
`user_config.json`, and that a fresh install is recommended.
Rejected per the boss-architect's 2026-05-12 directive: defensive
code for a zero-population is worse than no code. An honest warning
still leaves the recipient with a workflow nobody has validated.
The recipient who runs the manual `mv`, then runs `tailor serve`,
gets a broken Claude Desktop start; the warning will have pointed
them at the failure rather than away from it. Dropping the warning
is cleaner because it acknowledges the structural fact that there
is no workflow to point at.

**Keep both, defer retirement until Phase 2 PyPI publish.** The
*"wait until the obsolescence is forced"* option, structurally
similar to the alternative ADR 0032 considered and rejected for the
public mirror. Rejected on parallel grounds: Phase 1's stated
purpose is ship-quality housekeeping per the v7.0.8 banner;
removing scaffolding for problems that do not exist is exactly the
Phase 1 work. Deferral propagates the misleading surface (the
documented `tailor migrate` workflow) through every Phase 1
deliverable that follows and into Phase 2 itself. The deferred
option also accumulates the *"do we still need this?"* tax on every
release through the deferral window; retirement at v7.0.9 closes
the tax immediately.

## Reversal conditions

This ADR can be revisited (or superseded) under any of the
following conditions:

1. **A real v6 install in the wild requests an upgrade path.** Any
   credible signal — a recipient install report, a community issue,
   an email from a user who installed a v6 wheel before ADR 0032's
   distribution reshape and now wants to move to v7 — collapses the
   zero-population finding this ADR is grounded in. Under reversal:
   restore `cmd_migrate` from git history AND fix the path-rewrite
   gap before re-shipping. The original subcommand without the gap
   fix is not a safe restoration; it would land the affected
   recipient in the same broken-Claude-Desktop-start state the dev
   box hit on 2026-05-12.
2. **A future deployment recipe ships that introduces its own
   data-shape migration.** If a later ChildMCP or framework
   component introduces durable on-disk state that needs migration
   across a major-version boundary, the migration mechanism this
   ADR retired may be the wrong shape to revive — that recipe's
   migration needs are domain-specific, not the v6 → v7 directory
   relocation this ADR scoped. A superseding ADR would name the new
   migration shape on its own terms.

The reversal conditions are deliberately *not* *"a contributor
thinks the migration mechanism is useful in principle."* Principle
arguments for migration scaffolding were what carried the
mechanism into v7.0.0 in the first place; the empirical record
since then is what the retirement is grounded in. A future revival
needs empirical grounding of its own.

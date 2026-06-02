# ADR 0035: CLI rename — walkthrough + fitting-room, and the recipient-experience-shaped naming principle

- **Status:** Accepted
- **Date:** 2026-05-14
- **Supersedes (in part):**
  - [ADR 0024 (Wheel-distributed tour and fixture bundling)](0024-wheel-distributed-tour-and-fixture-bundling.md) — the `tour` CLI verb retires (`tour` → `fitting-room`). The substance ADR 0024 codified — wheel-distributed scaffolding into Claude Desktop, the synthetic-by-construction precondition for bundled fixtures, the package-data globs — is retained without change.
  - [ADR 0027 (Demo as researcher first-look)](0027-demo-as-researcher-first-look.md) — the `demo` CLI verb retires (`demo` → `walkthrough`). The substance ADR 0027 codified — five-section architectural showcase, cohort thesis as Section 1, bundled demo cohort fixtures, no Strava data — is retained without change.
- **Partially superseded by:**
  - [ADR 0040 (Bounded setup-time conductor surface)](0040-bounded-setup-time-conductor-surface.md) (v8.0.0, 2026-05-19) — both CLI verbs this ADR introduced (`tailor walkthrough`, `tailor fitting-room`) were **hard-removed** in v8.0.0 with no deprecation shim, replaced by the `WalkthroughLayer` and `FittingRoomLayer` MCP tools. The recipient-experience-shaped naming *principle* this ADR established is retained and applied to the MCP tool names; only the CLI surface was retired.
- **Related:**
  - [ADR 0026 (Claude Desktop config dual-path)](0026-claude-desktop-config-dual-path.md) — the `_is_orphan_entry_key` matcher's `tailor-*` prefix already covers `tailor-fitting-room-*`. ADR 0026 receives a 2026-05-14 amendment footer confirming the scope.
  - [ADR 0031 (Project rename to Tailor + Wardrobe)](0031-rename-to-tailor-and-wardrobe.md) — parent of the rename pattern; v7.0.0 set the precedent that public-API verb names get a major or minor bump and a one-cycle deprecation shim.
  - [ADR 0033 (Complete the Tailor metaphor on the workshop side)](0033-complete-tailor-metaphor-workshop-side.md) — the workshop-vs-lifestyle invariant this ADR strengthens with two recipient-facing surface entries, one Table 5 addition, and one Table 6 removal.
  - [ADR 0011 (Promotion policy)](0011-promotion-policy.md) — the structural-argument + severity reasoning this ADR's principle scope-carve-out borrows.
  - [`docs/design/tailor-vocabulary.md`](../design/tailor-vocabulary.md) — receives the cascade edits enumerated in § Decision item 5.

## Context

The CLI surface that recipients touch has, since v6.9.0, included two
verbs whose colloquial English meanings overlap: `tailor demo` (a
five-section architectural showcase that prints to the terminal, per
[ADR 0027](0027-demo-as-researcher-first-look.md)) and `tailor tour`
(a one-shot scaffold of bundled demo cohort fixtures into Claude Desktop
plus the recipient's vault directory, per
[ADR 0024](0024-wheel-distributed-tour-and-fixture-bundling.md)).
A friend hearing *"run `tailor demo` then `tailor tour`"* has no
mental model for why both commands exist, which to type first, or how
they differ. Both words read as colloquial synonyms — passive viewing
of something the system already prepared.

The 2026-05-12 macOS install was the first true outside-recipient
event in the project's history (project memory; v7.0.8 banner). The
recipient successfully drove the full Tailor → Claude Desktop pipeline
end-to-end. The verbs did not block that install. They did, however,
surface as the next ergonomic friction in the boss-architect's
2026-05-13 follow-up conversation: *both verbs describe what the
system is making, not what the recipient is doing.* The recipient is
two different things across those commands — a viewer in the terminal
during `demo`, an active driver in Claude Desktop during `tour` — and
the existing names hide that distinction.

A second pressure landed in the same conversation. The main session
proposed `tailor showcase` as a rename candidate without consulting
[`tailor-vocabulary.md`](../design/tailor-vocabulary.md). The vocab
file's Table 5 (line 127) lists *showcase* explicitly under *forbidden
in lifestyle-register usage*. The near-miss surfaced a structural
gap: the canonical reference file
[ADR 0033](0033-complete-tailor-metaphor-workshop-side.md) committed
the project to was not being consulted on naming proposals.
Strengthening that reference — by promoting two new entries (`closet`
to always-forbidden, `fitting-room` to recipient-facing-surface) and
retiring one weak-beat — is part of the work this ADR does, because
the same near-miss will recur on every future CLI proposal until the
file's load-bearing role is reinforced.

The window of cheapness is small and known. The repo is private; the
recipient population is fewer than ten friends-by-construction; the
landing page lives in a separate repo (`saahasmuthineni/tailor-mcp-landing`)
and is editable in a single pass; no published artifacts cite the CLI
verbs. The public-flip is deferred under the three-condition trigger
codified in the v7.0.13 banner — beachhead lab, launch-narrative
artifacts, boss-decides-public-scrutiny. After that flip, every CLI
verb becomes a permanent commitment with downstream citation cost.
The window for cheap renames is *now*; the cost climbs sharply once
any of the three trigger conditions fires.

The question this ADR answers: *what is the smallest verb-and-vocab
commitment that makes the recipient-facing CLI surface honest about
what the recipient is doing, codifies the naming principle so the
next proposal does not have to re-derive it, and strengthens the
vocab file's load-bearing role on every future naming decision?*

## Decision

Rename two recipient-facing CLI verbs, codify the recipient-experience-shaped
naming principle scoped to the recipient-evaluation class, and amend
the workshop-vocabulary file with three enumerated entries.

The plain-English rule: CLI commands that a recipient runs to
*evaluate Tailor* are named after **what the recipient is doing**,
not what the system is making. CLI commands that a recipient runs as
*operator* (system operations on their own deployment) are
grandfathered — `serve`, `status`, `uninstall`, `setup`, `pilot`
retain their existing names. The principle applies prospectively to
new commands in the recipient-evaluation class.

### 1. CLI verb renames (one-cycle deprecation shim)

- `tailor demo` → **`tailor walkthrough`**. Five-section architectural
  showcase that prints to the terminal. The new verb is deliberately
  metaphor-neutral: a walkthrough is what the recipient does when
  reading or watching something step-by-step, and the demo's existing
  shape (Tailor calling itself to demonstrate the architecture) is
  pre-metaphor first-look — the recipient has not yet acquired the
  workshop register. The name does not stake the recipient's first
  impression on metaphor-acquisition.
- `tailor tour` → **`tailor fitting-room`**. One-shot scaffold of
  bundled fixtures into Claude Desktop plus vault directory. The new
  verb sits in the workshop register: a fitting room in tailoring is
  where the customer drives the trying-on; pinning, marking, and
  adjusting work-in-progress all happen there. The recipient is
  actively trying on what the framework has produced for them — the
  surface is production-side, not display-side.

The old commands remain functional in v7.1.0 with a stderr
deprecation hint routing to the new names. The shim retires in
v7.2.0 (one cycle). The shim cost is one branch in the dispatch dict
per old verb and one print() call; the recipient-friction cost of
removing the shim immediately is higher than the year-of-deprecation
maintenance cost.

### 2. Module file rename (one-cycle compatibility shim)

- `git mv src/tailor/tour.py src/tailor/fitting_room.py` — history-preserving.
- Rename the public entry-point symbol `tour_main()` →
  `fitting_room_main()`.
- `src/tailor/tour.py` is retained as a one-line re-export shim
  through v7.1.0:
  `from tailor.fitting_room import fitting_room_main as tour_main`.
  Two callers depend on the old import path —
  [`examples/cohort_demo/realistic/setup.py`](../../examples/cohort_demo/realistic/setup.py)
  and [`examples/cohort_demo/realistic/rehearse.py`](../../examples/cohort_demo/realistic/rehearse.py).
  Both are updated to the new import in v7.2.0 alongside the shim's
  removal.
- The `src/tailor/demo/` Python package directory is **not** renamed
  in this release. The package directory is internal Python
  structure, not recipient-facing surface; renaming it would expand
  the diff without recipient-visible benefit on the same cycle that
  retires the `demo` verb. The rename is deferred as known-debt to
  v7.2.0 cleanup or beyond.

### 3. Claude Desktop registration key transition

- New key: `tailor-fitting-room-cohort` (preserves the existing
  `tailor-<verb>-<variant>` shape that ADR 0024 set).
- The `_is_orphan_entry_key` matcher at `src/tailor/__main__.py`
  already strips every `tailor-*` sibling per
  [ADR 0026](0026-claude-desktop-config-dual-path.md)'s amended
  contract. The new key falls under the existing matcher without
  source change.
- **Transactional per-path semantics are added** on the strip-and-replace
  path. The strip step (remove the v7.0.x `tailor-tour-cohort`
  entry from a Claude Desktop config) and the write step (add the new
  `tailor-fitting-room-cohort` entry) are wrapped so that either
  both happen on a given path or neither does. No half-stripped state
  is allowed. The failure scenario this closes: a running Claude
  Desktop holds the Store sandbox config open, the strip succeeds,
  the write fails on a permission error, and the recipient's running
  Claude Desktop now holds zero Tailor entries. The v6.10.4 dual-path
  contract from ADR 0026 (per-path atomic semantics; partial failure
  on one path does not abort writes to others) is preserved and
  extended.
- **A quit-first prompt is added to the `fitting-room` happy-path
  output**, not only the failure-recovery tail. During the
  v7.0.x → v7.1.0 transition window, recipients with a running Claude
  Desktop holding the Store sandbox open are the most likely failure
  shape. The prompt fires *before* the strip-and-replace runs, on the
  happy path, so recipients see it whether or not the operation will
  hit an open-file collision.

### 4. Recipient-experience-shaped naming principle (scoped)

CLI commands fall into two classes for naming purposes:

- **Recipient-evaluation class**: commands a recipient runs to
  evaluate Tailor or to try it on. Today: `walkthrough` and
  `fitting-room`. Future additions in this class are named after
  what the recipient is doing, in workshop register where the
  metaphor reads naturally, with the lifestyle-register check
  (Table 5) applied on every proposal.
- **Operator class**: commands a recipient runs as operator of their
  own deployment — system operations on a deployment they already
  have. Today: `serve`, `status`, `uninstall`, `setup`, `pilot`. The
  recipient-experience-shaped principle applies less cleanly here —
  these are operations on the system, not on the recipient's
  experience of it. `pilot` in particular is precedented in
  research-domain CLI vocabulary (REDCap pilots, pilot-study
  registrations) and would cost more recognition than it gains by
  rename. Operator-class verbs are explicitly grandfathered.

The principle gates future additions in the recipient-evaluation
class. It does not retroactively rename operator-class verbs and
does not bind every command Tailor will ever ship.

### 5. Vocab-doc edits (enumerated per `tailor-vocabulary.md` § How this file updates)

Per the vocab file's § *How this file updates* contract, ADRs that
change the vocab doc must enumerate the table-level edits explicitly.
Three edits:

- **Table 5 (workshop-vs-lifestyle invariant) — ADD one row** under
  *always forbidden*: **`closet`**. Domestic-lifestyle register
  dominant; rejected for `tailor tour` rename in v7.1.0 in favour of
  `fitting-room`; the compound `closet tour` is the influencer-content
  phrase (consumption-side display); also adjacency-confusing with
  the load-bearing Wardrobe noun. The codification means future
  proposals like `tailor wardrobe-tour` or `tailor closet-walk` are
  reviewable in seconds against a written rule.
- **Table 6 (weak beats and retroactive drops) — REMOVE the
  `Fitting` row** at lines 152–153. The compound `fitting-room` is
  promoted to a CLI command name per § *Recipient-facing surfaces*
  below; *Fitting* is no longer a weak-beat informal-prose word.
  Leaving the row would double-list the word across two tables (a
  weak beat in Table 6 and a recipient-facing surface below), which
  is the drift class the vocab file's enumeration discipline exists
  to prevent.
- **NEW top-level section `## Recipient-facing surfaces`** between
  Table 6 and § *How this file updates*. The section names
  `walkthrough` (deliberately pre-metaphor) and `fitting-room`
  (workshop-register, recipient drives the trying-on); enumerates
  the recipient-evaluation-class scope and the operator-class
  grandfathered list (`serve`, `status`, `uninstall`, `setup`,
  `pilot`); states the recipient-experience-shaped naming principle
  in one paragraph; cross-references this ADR for full rationale.

### 6. ADR amendments

- **[ADR 0024](0024-wheel-distributed-tour-and-fixture-bundling.md)** —
  status flipped to `Superseded in part by [ADR 0035]` with a
  forward-cite at the top. The `tour` verb retires; the substance
  (wheel-distributed scaffolding, synthetic-by-construction
  precondition, package-data globs, dual-write semantics inherited
  from `pilot.py`) is retained.
- **[ADR 0027](0027-demo-as-researcher-first-look.md)** — same
  treatment. The `demo` verb retires; the substance
  (five-section showcase, cohort thesis as Section 1, no Strava
  data, bundled demo cohort fixtures, ADR 0008 deterministic processing
  invariant) is retained.
- **[ADR 0026](0026-claude-desktop-config-dual-path.md)** — a
  2026-05-14 amendment footer is appended confirming that the
  `_is_orphan_entry_key` matcher's `tailor-*` prefix covers both
  v7.0 `tailor-tour-*` and v7.1 `tailor-fitting-room-*` keys
  without further amendment. The matcher's contract is unchanged;
  the amendment records that the new key fell under the existing
  scope by design.

### 7. Out-of-scope locks (deliberate non-changes)

Three things this ADR explicitly does **not** change, each named
because the change-shape invites accidental scope creep:

- **`tailor walkthrough`'s section-header strings** (e.g.
  `"Section 1 - cohort thesis"`,
  `"Section 2 - router pipeline visibility"`) are unchanged. They
  are internal print() output, not CLI verbs, and
  `recipient-install-validator` hardcodes them as PASS/FAIL string
  matches at
  [`.claude/agents/recipient-install-validator.md:111`](../../.claude/agents/recipient-install-validator.md).
  Changing them in the same cycle as the verb rename would silently
  recouple a previously-decoupled assertion contract.
- **The `src/tailor/demo/` Python package directory name** is
  unchanged on this cycle, as named in § Decision item 2. The
  rename is known-debt for v7.2.0 cleanup or later.
- **Operator-class CLI verbs** (`serve`, `status`, `uninstall`,
  `setup`, `pilot`) are unchanged per § Decision item 4. Renaming
  them is out of scope; a future ADR that proposes such a rename
  would need to either argue the recipient-experience principle
  extends into the operator class, or carve out a separate
  principle for that class.

## Consequences

### Positive

- **The workshop-metaphor identity extends to the recipient-facing
  CLI surface.** [ADR 0031](0031-rename-to-tailor-and-wardrobe.md)
  introduced *Tailor* and *Wardrobe* as the user-facing aggregate
  nouns; [ADR 0033](0033-complete-tailor-metaphor-workshop-side.md)
  codified the workshop-vs-lifestyle invariant on prose surfaces.
  This ADR closes the gap between those decisions and the verbs
  recipients actually type. A recipient running `tailor fitting-room`
  encounters the workshop register at the moment of first action,
  not only on the prose surfaces.
- **The Table 5 always-forbidden list gains `closet`**, codifying a
  near-miss rejection as a written rule. The next contributor
  proposing `tailor wardrobe-tour` or `tailor closet-walk` is
  reviewable in seconds against the written list rather than against
  taste-level review. The same enforceability story
  [ADR 0033](0033-complete-tailor-metaphor-workshop-side.md) made
  for `couture` / `atelier` / `boutique` extends one row.
- **The recipient-experience-shaped naming principle is codified.**
  The main session was demonstrably not applying this principle
  before this conversation — `tailor showcase` was proposed without
  vocab-doc consultation; the `demo` / `tour` overlap had stood for
  the entire v6.x cycle without surfacing as a naming problem.
  Codifying the principle, scoped to the recipient-evaluation class,
  gates future drift on the same axis. The next CLI proposal in
  this class is reviewable against the written principle rather
  than against taste.
- **Existing recipients on v7.0.x continue to work** through the
  v7.1.0 cycle. The deprecation-hint stderr emission is the signal
  channel; the old verbs remain functional. A recipient who
  installed in v7.0.x and types `tailor demo` sees the hint and
  learns the new verb in one keystroke. The breaking change is
  deferred to v7.2.0, by which point every recipient has had a full
  cycle of hints.
- **Transactional per-path semantics on the strip-and-replace path
  close the v6.10.x-shape failure scenario before any recipient
  hits it.** The failure mode (running Claude Desktop holds the
  config open, strip succeeds, write fails, zero entries remain)
  was not surfaced by any reported recipient install — the
  v7.0.x → v7.1.0 transition window is when it would have first
  appeared, because the strip-and-replace path is only exercised
  on a key rename. Adding the transactional semantics before the
  rename ships is structurally cheaper than discovering the failure
  mode in a recipient's hands.
- **The quit-first prompt on the happy path moves recipient
  awareness earlier.** Pre-v7.1.0, the prompt fired only on the
  failure-recovery tail — recipients who hit the failure mode saw
  it; recipients who would have hit it but happened to have Claude
  Desktop quit already never saw it. The happy-path emission means
  every v7.0.x → v7.1.0 recipient hears the quit-first instruction
  at the moment it matters.

### Negative

- **External doc references to `tailor demo` and `tailor tour` go
  stale on a one-cycle clock.** The landing page at
  `saahasmuthineni/tailor-mcp-landing` (separate repo) needs a
  parallel update. Any prior friend-shared transcripts (Drive links,
  Obsidian moments captured pre-v7.1.0, the in-vault rehearsal
  artifacts in `examples/cohort_demo/beta/`) cite the old verbs;
  rewriting them would falsify dated artifacts per
  [ADR 0031](0031-rename-to-tailor-and-wardrobe.md) § Historical
  preservation. The drift is bounded — recipients of stale
  transcripts hit the deprecation hint and discover the new verb —
  but the drift is real.
- **v7.0.x recipients see a one-time `removed v7.0.x entry as part
  of v7.1.0 verb rename` message** on their first `tailor
  fitting-room` invocation. Not a regression; the
  `_clean_claude_desktop_orphan_entries` matcher is doing exactly
  what its ADR 0026 contract says it does. But it is a moment of
  cognitive friction for recipients who did not follow the rename
  closely.
- **v7.2.0 is now a breaking version.** Removing the deprecation
  aliases retires two CLI verbs; the release banner must call this
  out explicitly. The communication cost is bounded (release notes
  + CLAUDE.md banner) but not zero. A recipient who installed in
  v7.0.x, never upgraded through v7.1.x, and jumps directly to
  v7.2.0 sees `tailor demo: unknown command` rather than the
  deprecation hint. The structural mitigation is one cycle of hints
  in v7.1.0; the residual gap is recipients who skip that cycle
  entirely.
- **`docs/guides/demo.tape` (asciinema/vhs recording source) embeds
  the old verb in a string-typed command.** The `.tape` file is a
  one-line edit, but the regenerated GIF asset itself remains
  orphan-debt of the same shape called out in the v6.10.5 banner.
  The asset is not on the recipient first-look path; queued for
  the same future doc-pass as that prior asset.
- **The `recipient-install-validator` hardcoded section-header
  string match at line 111 of its prompt remains a coupling between
  the validator and the demo's internal print output.** This ADR
  does not improve that coupling; § Decision item 7 explicitly
  defers the cleanup. The coupling does not get worse; it does not
  get better either. The structural patch is on the deferred-roster
  per ADR 0011.

### Neutral

- **Deprecation-hint emissions add minor stderr noise** to v7.0.x-alias-using
  recipients. Intentional and bounded; retires in v7.2.0.
- **ADR count: 34 → 35.**
- **SemVer minor bump.** The CLI command names are part of the
  public API by the SemVer reading the project has consistently
  applied; a rename with a one-cycle deprecation shim is a minor
  bump, the shim's removal in v7.2.0 is a separate minor bump (the
  shim's removal is not by itself a major change — the affected
  surface had a cycle of warning).
- **No router, security pipeline, ChildMCP, vault, audit, or
  local-LLM changes.** The rename is recipient-CLI-surface and
  vocab-doc only. The framework-tier components are untouched.
- **The first deployment recipe (demo cohort researcher first-look)
  is unchanged.** Bundled fixtures, the five-section showcase
  shape, the cohort thesis as Section 1, the runner's output, the
  tour scaffold — all preserved. Only the verbs change.

## Reversal conditions

This ADR can be revisited (or superseded) under any of the following
conditions:

1. **Recipient feedback shows the new verbs cause more confusion
   than the old verbs.** Operationalised: more than three distinct
   recipients ask *"where's `tailor demo`?"* or *"what does
   `walkthrough` do?"* via any back-channel within the two months
   following v7.1.0 ship. A counter-ADR reverts to `demo` and
   `tour`. The deprecation-hint stderr emission is the signal
   channel — every old-alias invocation prints the new verb — so
   the failure shape is *"recipients ignore the hint"* not
   *"recipients could not find the new verb."* If the failure
   shape is the former, the rename did not earn its cost.
2. **The workshop-metaphor identity itself retires.** A future ADR
   that supersedes [ADR 0033](0033-complete-tailor-metaphor-workshop-side.md)
   and chooses a different metaphor register would retire
   `fitting-room` alongside it. The metaphor-neutral `walkthrough`
   is independently defensible and would survive a metaphor
   change; `fitting-room` is bound to the workshop register and
   retires with it.
3. **The recipient-evaluation / operator class split proves
   unstable in practice.** If a future command's class membership
   is genuinely ambiguous (a recipient runs it sometimes to
   evaluate, sometimes as operator), the principle is revised in a
   superseding ADR rather than stretched. The split is a clean
   carve-out today (`walkthrough` / `fitting-room` are
   unambiguously evaluation; `serve` / `status` / `uninstall` /
   `setup` / `pilot` are unambiguously operator); the reversal
   condition exists because future additions may not be.

The reversal conditions are deliberately *not* *"a contributor
prefers different verbs"* or *"the vocabulary feels imperfect."*
The same reasoning [ADR 0033](0033-complete-tailor-metaphor-workshop-side.md)
named on its own reversal section applies: metaphor and CLI-verb
choices are always partly arbitrary; once chosen and shipped, the
project stabilises around them. Reversing them again carries a
cost (recipient re-learning, doc cascade, deprecation cycles) that
is only worth paying for one of the structural conditions above.

## Alternatives considered

**`tailor playground`** — rejected because the bundled-fixtures
synthetic-by-construction commitment from
[ADR 0024](0024-wheel-distributed-tour-and-fixture-bundling.md)
means the scope is *"a curated set of synthetic-cohort demos to
drive"*, not *"a freeform sandbox."* The name would over-promise
relative to what the command will ever do under that precondition.
A recipient hearing *"run `tailor playground`"* would form a
mental model of freeform exploration that the bundled-fixtures
scaffold cannot deliver. *Playground* describes a different shape
of tool.

**`tailor closet-tour`** — rejected on
[ADR 0033](0033-complete-tailor-metaphor-workshop-side.md)
lifestyle-register grounds. The phrase comes from influencer
content (*"come on a closet tour with me"*); it is consumption-side
display vocabulary; it is also adjacency-confusing with the
load-bearing *Wardrobe* noun. The rejection is codified by the
Table 5 always-forbidden addition this ADR commits to.

**`tailor muslin`** — considered seriously. A muslin in tailoring
is a rough prototype garment made from synthetic-by-construction
cheap fabric, used to check fit before cutting real material; the
metaphor maps onto the bundled-fixtures scaffold with unusual
precision (synthetic-by-construction in both domains). Rejected
because the metaphor describes *the object the framework produces*,
not *the recipient's experience of using it*. The recipient-experience-shaped
principle prefers `fitting-room` (where the recipient tries on
what has been made) over `muslin` (what the system has made for
them to try). Tailored noun for the next time a metaphor candidate
is architecturally exact but experientially clinical.

**`tailor showcase`** — would have violated Table 5 line 127 of
[`docs/design/tailor-vocabulary.md`](../design/tailor-vocabulary.md)
(*showcase — avoid — almost always lifestyle*). The main session
proposed it without consulting the vocab doc; the near-miss is
disclosed here as evidence that the vocab-doc edits in this ADR
(strengthening Table 5, adding the recipient-facing-surfaces
section) are not aesthetic. They are load-bearing because the
canonical reference file was not being consulted on every naming
proposal, and the structural patch is to make consultation cheaper
than re-deriving each rejection from scratch.

**Collapse `demo` and `tour` into one command.** Rejected because
they prove different things. The walkthrough deterministically
exercises all five architectural claims (cohort thesis, router
pipeline, three-tier resolution, vault, local-LLM oracle) by
Tailor calling itself. The fitting-room proves the integration
against an unknown external Claude Desktop driver, which exercises
only whatever calls that specific Claude session chooses. Both
proofs are recipient-visible; neither subsumes the other. The
first wild-recipient install (macOS, 2026-05-12) demonstrated
this — the recipient saw the five demo sections AND drove a
separate cohort call through Claude Desktop; collapsing the
surfaces would have dropped one proof on the same cycle that the
remaining surface had to carry both stories.

**Keep current names indefinitely.** Rejected because the
colloquial-English overlap of *demo* and *tour* is itself a
recipient-confusion risk. A friend hearing *"run `tailor demo`
then `tailor tour`"* has no a-priori mental model for why both
exist or which to type first. The new names carry the distinction
in their etymology — passive watching (walkthrough) vs. active
trying-on (fitting-room) — and remove a recurring explanatory
burden that the boss-architect has carried in every recipient
hand-off to date.

**Rename all CLI commands to recipient-experience-shaped verbs.**
Rejected as overreach. Operator-class commands (`serve`, `status`,
`uninstall`, `setup`) are system operations the recipient is
also-the-operator for; they do not benefit from experience-shaped
naming. `pilot` is precedented in research-domain CLI vocabulary
and would cost more recognition than it gains. Scoping the
principle to the recipient-evaluation class is the load-bearing
carve-out — the principle has to be narrow enough to apply
cleanly, or it will be applied inconsistently and lose its
gating value.

**A network-based version-currency check on startup.** Came up in
the refinement conversation that led to this ADR (the *"how does
a recipient know they are on the current verbs?"* question), and
rejected on Tailor's implicit no-outbound-network invariant. Even
a benign PyPI metadata fetch crosses a recipient-trust line: for a
tool whose distinguishing claim is *"no data leaves your machine"*,
a phone-home check (even for benign metadata) compromises the
posture. The version-currency story is instead handled by
recommending `uvx --from tailor-mcp tailor walkthrough` in
recipient-facing docs (ephemeral environment, always-latest by
construction) for the look-only case, and a `tailor status`
printed line naming the upgrade command (`uv tool upgrade
tailor-mcp`) for persistent installs. The rejection is referenced
here because the network-call invariant and the workshop-vs-lifestyle
posture both refuse external coupling — the same structural
register this ADR strengthens.

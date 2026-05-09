# ADR 0032: Retire the public-mirror distribution path; wheel-handoff supersedes through Phase 1; Pages-on-source-repo at Phase 2 PyPI publish

- **Status:** Accepted (mirror archived 2026-05-09 via `gh repo archive saahasmuthineni/biosensormcpdemo --yes`; the repo is read-only and the legacy `https://saahasmuthineni.github.io/biosensormcpdemo/` URL still resolves so prior friend-shares continue to work)
- **Date:** 2026-05-09
- **Supersedes:** [ADR 0030 (Public-mirror narrative + zero-outbound-affordances)](0030-public-mirror-narrative-and-affordance-depth.md) — partially. The public-mirror distribution-shape decision is retired; the zero-outbound-affordances rendering invariant is explicitly retained and now governs wheel-handoff friend-share output instead of the Pages mirror.
- **Related:**
  - [ADR 0024 (Wheel-distributed tour and fixture bundling)](0024-wheel-distributed-tour-and-fixture-bundling.md) — § 3.1 amended: the public-mirror carve-out alongside Drive/email is removed; wheel-by-email becomes the sole friend-shareable channel through Phase 1
  - [ADR 0027 (Demo as researcher first-look)](0027-demo-as-researcher-first-look.md) — `tailor demo --audience=public --save-shareable` continues to render the per-persona-panel markdown; the output is now consumed locally rather than uploaded
  - [ADR 0031 (Project rename to Tailor + Wardrobe)](0031-rename-to-tailor-and-wardrobe.md) — Phase 1 of the project's lifecycle; the wheel-handoff window this ADR defines closes when ADR 0031's Phase 2 PyPI commitment ships
  - [ROADMAP.md § Phase 2 — Public-launch readiness](../../ROADMAP.md) — the *"Publish to PyPI as `tailor-mcp`"* and *"Make the GitHub repo public"* deliverables together establish the reversal condition under which this ADR becomes structurally moot

## Context

[ADR 0030](0030-public-mirror-narrative-and-affordance-depth.md) shipped
on 2026-05-08 with a public release-only GitHub mirror at
`saahasmuthineni/biosensormcpdemo`, a GitHub Pages render of the
five-section demo transcript with per-persona interpretation panels, and
a `release-shipper` extension that uploaded each release's wheel as a
public release asset on the mirror. The mirror existed to solve one
specific friction: a friend-shareable URL while the source repo at
`saahasmuthineni/Biosensor-to-LLM-Connector` (now `tailor-mcp` per
[ADR 0031](0031-rename-to-tailor-and-wardrobe.md) § Migration story
closeout) stays private. GitHub Pages cannot serve from a private repo
on the free plan, so a separate public repo was the structural
workaround that made the friend-share URL possible.

The mirror is interim infrastructure scheduled for its own obsolescence.
[ROADMAP.md § Phase 2](../../ROADMAP.md) commits to *"Publish to PyPI
as `tailor-mcp`"* and *"Make the GitHub repo public"* together — the
combination eliminates both reasons the mirror exists. PyPI removes the
hand-delivered-wheel friction; a public source repo can serve its own
GitHub Pages directly. ADR 0030 named PyPI publication as Alternative 1
and as the carve-out's reversal condition, acknowledging that the
mirror's purpose was bridging the gap until Phase 2 lands.

A second observation surfaced on 2026-05-09: through Phase 1 (current
phase, ~10-evaluator friend-share scope per project memory's
*"friend-shareable distribution philosophy"*), the wheel-by-email
channel that ADR 0024 § 3.1 already names alongside the mirror is
sufficient on its own. A friend who receives a wheel by email can run
`uv tool install <wheel>` and `tailor demo --audience=public
--save-shareable transcript.md` locally, getting the same per-persona-
panel curated markdown ADR 0030 designed — just rendered on their own
machine instead of viewed through GitHub Pages. The mirror provides one
affordance the wheel does not: a URL the friend can open without
running anything. That affordance's value is bounded by the same
friend-share scope ADR 0024 § 3.1 already constrains; for ~10 evaluators
who receive a personal email containing the wheel, a separate Pages URL
is redundant convenience rather than a load-bearing channel.

The boss-architect surfaced this on 2026-05-09: *"the public mirror is
unneeded at this point since I can just send a wheel file from the
private repo to anyone up until phase 1 when the pages become
unnecessary anyways."* The structural argument — interim infrastructure
that's now redundant ahead of its own scheduled obsolescence — is
strong enough to retire the mirror immediately rather than wait for
Phase 2 to do it implicitly.

ADR 0030 bundled two decisions together: the public-mirror
distribution-shape decision AND the zero-outbound-affordances rendering
invariant. The structural question this ADR answers: *with the
distribution-shape decision retired, does the rendering invariant
survive — and if so, what does it now govern?*

## Decision

Retire the public-mirror distribution path. Wheel-handoff via personal
email supersedes through Phase 1; GitHub Pages on the now-public source
repo at Phase 2 PyPI publish supersedes from there. Archive the mirror
repo (already executed 2026-05-09) rather than delete it so prior
friend-shares with the legacy URL continue to resolve. The
zero-outbound-affordances rendering invariant defined in ADR 0030 is
**explicitly retained** and now governs wheel-handoff render output
rather than the retired Pages mirror.

The rule, plain English: ADR 0030 was two decisions in one file. ADR
0032 retires the first decision (the mirror as a distribution channel)
and keeps the second decision (the render shape — zero outbound URLs
except the wheel-release-asset, per-persona panels, attribution-only
footer). The render code at [`src/tailor/demo/runner.py:236-364`](../../src/tailor/demo/runner.py)
stays untouched; the same rendered markdown that was uploaded to the
mirror is now emailed to the friend or opened locally in their Obsidian
preview.

### What is retired

- **The mirror repo as an active distribution channel.** No new releases
  upload wheels to `saahasmuthineni/biosensormcpdemo`. The `release-shipper`
  agent's mirror-upload extension is removed from the per-release ritual.
- **The GitHub Pages render path.** The Pages site at
  `https://saahasmuthineni.github.io/biosensormcpdemo/` continues to
  serve the v6.13.0 snapshot (archived state) but receives no further
  updates. New friend-shares route through email rather than the URL.
- **The mirror as a release asset host.** Wheels for v7.0.0 forward are
  attached to releases on the source repo (now public-renamed-but-still-
  private at `saahasmuthineni/tailor-mcp` per ADR 0031 closeout) or
  delivered as direct attachments by email. The mirror's Releases page
  preserves v6.11.x–v6.13.0 wheels under archived state.
- **The `tailor demo --save-shareable` upload-to-mirror pathway.** The
  CLI flag still produces a self-contained markdown file; the
  `share-the-demo.md` checklist's *"upload to mirror"* steps become
  *"attach to email"* steps. No code change is required — the flag
  always wrote a local file and never auto-uploaded.

### What is retained

ADR 0030's second decision — the zero-outbound-affordances rendering
invariant — is load-bearing on its own and survives the
distribution-shape retirement. The invariant now serves wheel-handoff
friend-share output:

- **The render-time URL allowlist at [`src/tailor/demo/runner.py:336-365`](../../src/tailor/demo/runner.py)
  stays in place.** The `_enforce_public_url_allowlist` function
  hard-fails CI if any `--audience=public` rendered output contains an
  outbound URL outside the wheel-release-asset pattern, or any banned
  scheme (`mailto:`, `ftp:`, `tel:`). A future contributor adding a
  Discord link, a contact form, or a Substack signup to the public-mode
  template gets a CI failure rather than a quietly-shipped page (or
  email attachment) that violates the friend-share scope.
- **The per-persona panel schema at [`src/tailor/demo/_personas.json`](../../src/tailor/demo/_personas.json)
  stays single-sourced.** The PI / analyst / IRB-reviewer panels render
  the same way they did under ADR 0030; they are now rendered into
  markdown that gets emailed rather than uploaded.
- **The `--audience=public` flag on `tailor demo` stays a public API.**
  ADR 0030's render shape is now the recommended shape for any
  friend-share output — local-rendered or otherwise. The flag's
  semantics are unchanged; only its consumption pattern shifts.
- **The attribution-only footer copy stays.** *"Built by Saahas
  Muthineni. If you received this URL personally and have questions,
  reply through the channel he sent it through."* applies symmetrically
  to email attachments — the friend received the wheel through a
  personal channel and can reply through the same channel.

The structural argument for retention: ADR 0030's second decision was
*"the render shape commits to zero outbound contact mechanisms because
every legitimate recipient already has a back-channel by carve-out
construction."* That argument is independent of where the rendered
output is hosted. It applies to a Pages URL the friend opens; it
applies to a markdown file the friend opens locally; it applies to any
future hosting shape. Removing the invariant alongside the distribution
channel would re-open the surface area to a future contributor adding
*"to be helpful"* affordances — exactly the failure mode ADR 0030
codified the invariant against.

### Already executed

- **`gh repo archive saahasmuthineni/biosensormcpdemo --yes`** ran on
  2026-05-09. The mirror is read-only; pushes are rejected; existing
  releases and Pages content remain visible. The legacy URL
  `https://saahasmuthineni.github.io/biosensormcpdemo/` still resolves
  and renders the v6.13.0 snapshot, so any friend-share email already
  in flight or any previously-shared link continues to work
  indefinitely. Archive is reversible at any time via the GitHub web
  UI's *"Unarchive repository"* button — ADR 0032 takes advantage of
  that reversibility as part of its reversal-condition design.

## Consequences

### Positive

- **The maintenance overhead of two repos is gone.** Through Phase 1
  there is one source of truth (the source repo) and one distribution
  channel (wheel-by-email). The `release-shipper` ritual loses the
  mirror-upload step; the `share-the-demo.md` checklist drops the
  upload sub-procedure. The `recipient-install-validator` no longer
  has two install-URL-base values to track.
- **The friend-share scope is structurally tighter.** A Pages URL is
  technically reachable by anyone who receives the link; an email
  attachment is reachable only by the email recipient. The
  ~10-evaluator threshold ADR 0024 § 3.1 names becomes harder to
  violate accidentally — forwarding an email is more deliberate than
  forwarding a URL, and the recipient has to actively install the
  wheel before they see anything.
- **The Phase 2 transition is cleaner.** When PyPI publication and
  source-repo-public land together per ROADMAP § Phase 2, GitHub Pages
  on the source repo becomes possible without a parallel mirror to
  retire. The Phase 2 work is *"flip a switch on the source repo"*
  rather than *"retire one channel and stand up another."* Phase 2's
  scope is reduced.
- **The zero-outbound-affordances invariant generalises.** Under ADR
  0030 the invariant was implicitly *"on the public mirror page."*
  Under this ADR it is *"on any `--audience=public` rendered output,
  wherever consumed."* A future contributor cannot weaken the
  invariant by arguing *"this isn't the mirror"* — the render-time
  URL allowlist enforces the invariant at render time, not at upload
  time.
- **The legacy URL still resolves under archive.** Friend-shares
  already in flight via the Pages URL continue to work. Recipients
  who bookmarked the URL months ago still see the v6.13.0 snapshot.
  The retirement is graceful rather than abrupt.

### Negative

- **One affordance is lost: the friend cannot preview the demo
  without installing the wheel first.** Under ADR 0030 a friend
  could open the URL and read the transcript + persona panels
  before deciding whether to install. Under ADR 0032 they install
  first and render locally. For technically-comfortable friends
  (the friend-shareable scope's actual audience per project memory)
  the install step is a 30-second `uv tool install` plus a one-line
  `tailor demo` invocation; the cost is real but bounded. For
  friends who would have read the page but never installed, that
  audience is now filtered out — which is consistent with the
  carve-out's structural commitment that the recipient already has
  a back-channel and is engaged enough to act on the share.
- **The mirror could be reactivated by a future contributor without
  noticing this ADR.** Archive is reversible from the GitHub web UI
  with no code change required. A future contributor who finds the
  archived repo, unarchives it, and resumes uploads would not trip
  any code-level guard. Mitigation: this ADR is the structural
  record; the `code-vs-roadmap-drift-auditor` and the next
  `release-shipper` revision both should treat
  `saahasmuthineni/biosensormcpdemo` as an archived asset and flag
  any reference to it as a doc-truth violation.
- **The render-time URL allowlist now governs an output type whose
  consumption is harder to validate.** Under ADR 0030 a Pages render
  was visible to the boss after upload, so a regression in the
  allowlist would have been spotted at the next visual check. Under
  ADR 0032 the rendered markdown gets emailed — there is no
  equivalent visual checkpoint. Mitigation: the allowlist is
  enforced at render time (CI hard-fail), not at upload time, so
  the regression surface is closed structurally rather than
  visually.

### Neutral

- **ADR 0024 § 3.1's three reversal conditions stand unchanged.**
  Source repo stays private through Phase 1; bundled bytes stay
  synthetic by construction per ADR 0024 § 4; recipient set stays
  handful-sized at the existing ~10-evaluator threshold. ADR 0032
  removes one of the two channels § 3.1 named (the mirror); the
  remaining channel (Drive/email) is sufficient for the
  handful-recipient scope.
- **The ADR 0030 file remains a citable historical record.** It is
  not deleted or rewritten; the *Status* line is the only change
  needed (Accepted → Superseded by ADR 0032 (in part); the
  zero-outbound-affordances invariant is retained). The structural
  argument for the invariant lives in ADR 0030's *Decision*
  section; this ADR cites it rather than restating it.
- **The `share-the-demo.md` checklist needs an update pass.** The
  *"create the mirror repo"* and *"upload wheel to mirror release"*
  steps are obsolete; the *"render with `--audience=public
  --save-shareable`, attach to email"* steps replace them. That
  edit is queued for the same patch that lands this ADR rather
  than blocking ADR acceptance.

## Alternatives considered

**Keep the mirror through Phase 1 and rename it for brand
coherence.** The Path B option from the
boss-architect-vs-main-session conversation that preceded this
ADR — rename `biosensormcpdemo` to `tailor-mcp-demo` (or similar)
to match the v7.0.0 rename, keep the mirror active until Phase 2
naturally retires it. Rejected because: the brand-coherence
benefit does not justify the maintenance overhead of two repos
through Phase 1 when wheel-handoff already serves the
~10-evaluator scope. The boss-architect's framing on 2026-05-09
— *"the public mirror is unneeded at this point since I can just
send a wheel file"* — names the structural redundancy directly.
A renamed mirror is the same channel with new branding; the
underlying redundancy is unchanged.

**Delete the mirror outright instead of archiving.** Considered
and rejected on reversibility and continuity grounds. Archive is
reversible at any time via the GitHub web UI; delete is
irreversible. Friend-shares already in flight via the legacy
`https://saahasmuthineni.github.io/biosensormcpdemo/` URL
continue to resolve under archive but break under delete —
recipients who bookmarked the URL months ago would see a 404 with
no breadcrumb. The cost of archive over delete is essentially
zero (read-only repos do not appear in active search results, do
not consume meaningful storage, and do not signal active
maintenance); the benefit is the preservation of every existing
friend-share link in its existing shape.

**Retire the entire `--audience=public` render path too — remove
`_personas.json`, the URL-allowlist test, and `--save-shareable`.**
Considered and rejected on the load-bearingness of the
zero-outbound-affordances invariant. The render code at
[`src/tailor/demo/runner.py:236-364`](../../src/tailor/demo/runner.py)
serves wheel-handoff friend-share equally well; removal would
force re-derivation if the same render shape is wanted later
(which Phase 2 ROADMAP commitments suggest it will be). The
per-persona panels are independently load-bearing on the friend's
first-look experience per ADR 0030's *Positive consequences*; the
URL allowlist is the structural enforcement on the friend-share
scope per ADR 0030's *Decision* fourth bullet. Removing them
together with the mirror conflates *"the mirror is retired"* with
*"the render shape is unwanted,"* which are different decisions.

**Defer retirement to Phase 2 — keep the mirror active until PyPI
publication makes it implicitly obsolete.** Considered and
rejected on the boss-architect's stated framing. Phase 2 is
~3 months out per ROADMAP; the maintenance overhead of two repos
through that window is real (every release ritual, every
recipient-install validation, every share-the-demo iteration
touches both surfaces). Retirement at 2026-05-09 closes the
overhead immediately and brings the Phase 2 transition into a
cleaner shape (one channel goes public rather than one channel
retiring while another stands up). The deferred-retirement option
trades known immediate overhead for hypothetical
*"what if we need it before Phase 2?"* optionality — the
structural argument the boss-architect supplied
(*"unneeded at this point"*) is direct evidence that the
optionality has no realised demand.

## Reversal conditions

This ADR can be revisited (or superseded) under any of the
following conditions:

1. **Phase 1 audience widens beyond friend-shareable before Phase
   2 PyPI publication ships.** If the boss-architect decides to
   open the friend-share scope to ~10+ evaluators ahead of the
   ROADMAP's Phase 2 commitment (e.g. a workshop demo, a
   conference share, a public discoverability move), the mirror
   can be unarchived via one button-click on the GitHub web UI.
   The Pages render resumes serving immediately; the
   `release-shipper` mirror-upload extension is restored from git
   history. The reversal is operationally cheap precisely because
   archive (rather than delete) was chosen.
2. **The source repo is flipped public ahead of Phase 2 PyPI
   publish.** If the source repo at `saahasmuthineni/tailor-mcp`
   is made public for any reason (early ROADMAP § Phase 2
   sequencing, a contributor-onboarding pass, an IRB submission
   that benefits from public source visibility), GitHub Pages on
   the source repo becomes available directly and ADR 0032
   becomes structurally obsolete — there is no longer a *"private
   source, public Pages"* gap for any mirror to bridge. The ADR
   is superseded rather than reversed in this case; the render
   shape (which is what survives) continues serving Pages on the
   source repo.
3. **The zero-outbound-affordances invariant is intentionally
   weakened.** If a future ADR explicitly opts into community-shape
   distribution (issue tracker, Discord, public roadmap, mailto
   button, contact form) per ADR 0030's reversal condition, the
   render-time URL allowlist relaxes accordingly. ADR 0032 retains
   the invariant on the assumption that the friend-share scope
   remains in place; a deliberate scope expansion is the
   structural condition under which the invariant should be
   revisited.

The reversal conditions are deliberately *not* *"a friend asks for
a URL to share."* That request is the failure shape this ADR
exists to filter — a friend-share scope that quietly accumulates
"just one more" recipients past the ~10-evaluator threshold is
exactly what ADR 0024 § 3.1's handful-recipient invariant exists
to prevent. The wheel-by-email channel preserves the
handful-recipient bound by construction; reverting to the mirror
to satisfy a single friend's URL request would erode the bound
the same way mixed-regime affordance additions would have under
ADR 0030.

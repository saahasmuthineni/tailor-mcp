# ADR 0030: Public-mirror page deepens narratively; outbound affordances pruned to zero (recipient already has a back-channel by carve-out construction)

- **Status:** **Superseded in part by [ADR 0032](0032-retire-public-mirror-distribution.md)** (flipped 2026-05-09). The public-mirror distribution-shape decision (the mirror repo at `saahasmuthineni/biosensormcpdemo` as an active distribution channel + the GitHub Pages render path + the `release-shipper` mirror-upload extension) is retired; wheel-handoff via personal email supersedes through Phase 1 + GitHub Pages on the now-public source repo at Phase 2 PyPI publish supersedes from there. The **zero-outbound-affordances rendering invariant** defined below is **explicitly retained** by ADR 0032 and now governs wheel-handoff render output rather than the retired Pages mirror — the render-time URL allowlist at `src/tailor/demo/runner.py:336-365`, the per-persona panel schema at `src/tailor/demo/_personas.json`, the `--audience=public` flag, and the attribution-only footer copy all stay in place. *(Original status, preserved for historical record: Accepted, flipped 2026-05-08 after the live page at `https://saahasmuthineni.github.io/biosensormcpdemo/` was verified to match all four commitments — version pin v6.13.0, 5 sections × 3 persona panels = 15 labels, attribution-only footer, zero outbound URLs except the wheel-release asset. Mirror archived 2026-05-09 via `gh repo archive`; URL still resolves with the v6.13.0 snapshot for in-flight friend-shares.)*
- **Date:** 2026-05-08
- **Related:** [ADR 0024 (Wheel-distributed tour and fixture bundling)](0024-wheel-distributed-tour-and-fixture-bundling.md) — § 3.1 carve-out being extended, § 4 synthetic-by-construction precondition inherited unchanged, Alternative 1 PyPI escalation path the reversal condition references; [ADR 0011 (Promotion policy)](0011-promotion-policy.md) — structural-argument framing for cross-surface persona reuse; [ADR 0027 (Demo as researcher first-look)](0027-demo-as-researcher-first-look.md) — the demo this page renders; [`.claude/agents/researcher-utility-reviewer.md` § Personas](../../.claude/agents/researcher-utility-reviewer.md) — canonical PI / analyst / IRB-reviewer definitions the per-persona panels reuse verbatim

## Context

[ADR 0024 § 3.1](0024-wheel-distributed-tour-and-fixture-bundling.md)
landed in v6.11.1 as an amendment to the v6.9.0 distribution model: a
public release-only GitHub mirror at `saahasmuthineni/biosensormcpdemo`
hosting (a) versioned wheel files as release assets and (b) a GitHub
Pages-rendered shareable demo transcript. The carve-out exists for one
use case — *"send a CS-grad-shaped friend the demo via one URL; let
them evaluate without clone, account, or env-setup ritual."* Three
reversal conditions guard the carve-out: source repo stays private,
bundled bytes stay synthetic by construction, recipient set stays
handful-sized.

v6.12.0 shipped two days later: `tailor demo` reshaped from a
three-call cohort first-look into the five-section architectural
showcase per [ADR 0029](0029-token-reduction-as-analytical-quality.md),
and `--save-shareable [PATH]` added as the CLI seam that produces the
markdown the public mirror renders. The boss-architect reviewed the
live page on 2026-05-08 and surfaced two structural problems with
what shipped:

1. **The transcript-as-page is a raw envelope dump.** A friend who
   opens the URL sees five sections of result-envelope JSON and
   framing prose, with no scaffolding for how to read it. The PI / RSE
   / IRB-reviewer audiences the framework targets each look at the
   same transcript through different jobs (defensible audit trail vs.
   schema clarity vs. PHI handling correctness — see the
   [canonical persona definitions](../../.claude/agents/researcher-utility-reviewer.md))
   and the page does not surface that. The first impression is
   *"complicated technical output"* rather than *"interpretive
   walkthrough of an architecture."*
2. **The footer breadcrumbs point at private-repo files that 404.**
   The current page's breadcrumb list links `README.md`, `CLAUDE.md`,
   `docs/design/research-framing.md`, and several ADRs as
   "for more, see…" pointers. Every one of those links 404s for any
   reader without source-repo collaborator access — i.e. exactly the
   audience the public mirror exists to reach. The breadcrumbs are
   structurally undeliverable on the public surface they live on.

The boss-architect made an explicit dispatch choice: deepen the page
rather than sharpen-the-minimum (kill breadcrumbs, ship transcript-
only). The deepening commits to one new axis — narrative depth
(per-persona reading guides) — and resolves the broken-breadcrumb
problem by *pruning* outbound affordances entirely rather than
replacing them with new ones. The structural argument the
boss-architect supplied on 2026-05-08 (after `integration-auditor`
flagged that the originally-proposed three-mailto footer would scrape
his personal email onto a search-indexed public surface): ADR 0024
§ 3.1's friend-shaped recipient already has a back-channel to the
author by the carve-out's own construction (the URL is sent
personally, not discovered cold), so the page does not need to provide
one. Author attribution stays; outbound contact does not. Feature
depth (e.g. wiring a real Ollama backend into Section 5) is
deliberately deferred as a separate follow-up.

The structural question this ADR answers: *what shape does the
narrative surface take, and what is the page allowed to send a visitor
to, given that ADR 0024 § 3.1's handful-recipient invariant must
remain self-enforcing on the page itself?*

## Decision

The public mirror page deepens along **narrative depth**
(per-persona reading guides over the existing demo transcript) and
resolves the broken-breadcrumb problem by **pruning outbound
affordances to zero** under one new invariant that makes ADR 0024
§ 3.1's handful-recipient reversal condition self-enforcing on the
page itself: **the public mirror page contains no outbound contact
mechanism; it attributes authorship but does not invite contact,
because every legitimate recipient under ADR 0024 § 3.1 already has
a back-channel to the author by carve-out construction.**

The rule, plain English: the page interprets the transcript through
the project's three baked-in audiences and gives the visitor zero
outbound destinations — no email, no form, no social handle, no
platform link, no community-shape signup. Naming the author
preserves attribution; not providing contact preserves the
handful-recipient invariant intrinsically. The visitor reached the
page through a personal channel from the author and can leave the
same way.

Concrete mechanism:

- **Narrative axis — per-persona interpretation panels adjacent to
  each demo section.** The `--save-shareable` markdown rendering
  emits, beside each of the five demo sections, three short
  interpretation panels — one each from the PI, analyst/RSE, and
  IRB-reviewer perspectives. Each panel is two to four sentences
  naming what the persona sees in that section. Section 1 (cohort
  thesis): *PI* — *"defensible n / mean / std for a paper, no LLM in
  the numerics path"*; *analyst* — *"the metadata sidecar shape that
  REDCap and Frictionless both accept"*; *IRB* — *"raw streams never
  enter LLM context; ADR 0008 determinism is what makes the claim
  hold."* Section 2 (router pipeline) through Section 5 (local-LLM
  oracle) get analogous panels keyed to what each persona's job
  surfaces in that section's envelope.
- **Persona definitions stay in their canonical home; the page
  references them.** The panels reuse the PI / analyst / IRB-reviewer
  definitions from
  [`.claude/agents/researcher-utility-reviewer.md` § Personas](../../.claude/agents/researcher-utility-reviewer.md)
  verbatim rather than re-defining them inline on the page. If those
  personas evolve later, the public mirror inherits the change on the
  next release rather than drifting into a parallel definition. The
  agent file is not a public-facing artifact, so the page's panels
  copy the persona name and the *"cares about"* line into rendered
  markdown rather than linking — but the source-of-truth pointer is
  recorded in the rendering code so a future maintainer knows where
  to update.
- **Affordance pruning — outbound contact mechanisms are removed
  entirely.** The footer becomes a single attribution line —
  *"Built by Saahas Muthineni. If you received this URL personally
  and have questions, reply through the channel he sent it through."*
  — and nothing else. No mailto links, no contact form, no social
  handles, no platform links, no GitHub Issues pointer, no Discord,
  no Substack signup, no PyPI handoff. The current breadcrumb list
  (private-repo `README.md`, `CLAUDE.md`, design docs, ADRs) is
  removed entirely. The structural argument: ADR 0024 § 3.1's
  carve-out is defined by the recipient receiving the URL personally
  from the author, which means by carve-out construction the
  recipient already has the author's contact through whatever channel
  delivered the URL. A page-side affordance would (a) duplicate a
  contact channel the recipient already has and (b) silently invite
  recipients who *don't* have a back-channel — i.e. exactly the
  recipient shape the carve-out's handful-recipient condition
  forbids.
- **New invariant — zero outbound contact mechanisms on the public
  mirror.** *"The public mirror page contains no outbound contact
  mechanism: no mailto, no contact form, no social handle, no
  platform link, no community-shape destination (Discord, Slack,
  GitHub Issues, Substack, etc.). Outbound URLs in the rendered page
  are permitted only for the wheel release asset that the install
  command requires (a `github.com/<owner>/<repo>/releases/download/`
  pattern). The page attributes authorship but does not provide a
  contact path; recipients are presumed to already have a
  back-channel to the author by ADR 0024 § 3.1's carve-out
  construction."* The invariant is enforced both by review at PR
  time on every change to the public mirror's `README.md` template
  or rendering code, and structurally by a render-time URL-scheme
  allowlist that hard-fails CI if the rendered output contains any
  outbound URL outside the wheel-release-asset pattern. This makes
  ADR 0024 § 3.1's handful-recipient reversal condition self-enforcing
  on the page itself — a page that contains no outbound contact
  destinations cannot accidentally route past handful-shaped
  recipients no matter how widely the URL itself spreads.
- **Inherited invariants from ADR 0024 § 3.1, listed explicitly so
  this ADR cannot weaken them by silence.** (1) Source repo stays
  private — the page exposes no source code, no ADRs, no design docs,
  no CLAUDE.md. (2) Bundled bytes stay synthetic by construction per
  ADR 0024 § 4 — the wheel hosted as a release asset on the public
  mirror is the same wheel the Drive/email path ships, with the same
  HIP Lab realistic fixtures generated from `random.Random(20260504)`
  on fictitious subject IDs. (3) Recipient set stays handful-sized
  at the existing ~10-evaluator threshold operationalised in
  [`share-the-demo.md` § "When NOT to share publicly"](../guides/share-the-demo.md) —
  the zero-outbound-affordances invariant above operationalises this
  on the page itself by ensuring the page cannot route any visitor to
  a contact channel they don't already have through the carve-out.
  This ADR does not raise § 3.1's recipient ceiling; it makes the
  ceiling harder to violate accidentally.

### Reversal condition

> *"The public mirror reverses the zero-outbound-affordances rule
> when (a) the recipient set crosses the ADR 0024 § 3.1 handful
> threshold and PyPI publication becomes the right answer per
> Alternative 1, OR (b) the boss explicitly opts into community-shape
> distribution (issue tracker, Discord, public roadmap, mailto button,
> contact form) with a written reversal note that supersedes this
> ADR."*

The reversal is binary by design: the page either contains zero
outbound contact mechanisms (this ADR's regime) or contains them
under a superseding ADR's regime. A mixed regime — adding one mailto
button "to be helpful" or one Discord link "to see how it goes" —
is the failure shape this ADR exists to prevent, because mixed
regimes are how scale-presuming surfaces silently accumulate past
the handful threshold.

### Status pathway

`Status: Proposed` at draft time. v6.13.0 shipped 2026-05-08 with the
persona-panel rendering, the attribution-only footer, the render-time
URL-scheme allowlist, and the structured `_personas.json` schema. The
boss-architect verified the live page at
`https://saahasmuthineni.github.io/biosensormcpdemo/` matches all four
commitments (15 persona labels = 5 sections × 3, attribution footer
present, zero outbound URLs except the wheel-release asset, version
pin v6.13.0). Status: Accepted.

## Consequences

### Positive

- **The friend's first impression is interpretive, not raw.** A
  visitor who opens the URL sees five demo sections each annotated by
  three short persona panels naming *what to look at*. The page now
  teaches how to read the transcript rather than handing over a
  transcript and a hope. PI-shaped readers see the audit-trail
  argument; RSE-shaped readers see the schema-clarity argument;
  IRB-shaped readers see the consent / determinism / scrubber-seam
  argument — each adjacent to the section that demonstrates it.
- **The dead-link breadcrumb problem is resolved at root, not
  patched.** The current footer's private-repo breadcrumbs all 404
  for any non-collaborator. Rather than replacing them with new
  outbound affordances (which would scrape the boss-architect's
  personal email onto a search-indexed public surface indefinitely
  per `integration-auditor`'s 2026-05-08 finding F2), the new footer
  prunes them entirely. The page's job is the transcript +
  interpretation; the visitor's contact path back to the author is
  whatever channel delivered the URL. This eliminates the symptom
  (broken links) without introducing a new failure mode (scrapable
  contact information indexed by search engines indefinitely).
- **ADR 0024 § 3.1's handful-recipient reversal condition becomes
  self-enforcing on the page itself.** The handful-recipient invariant
  previously rested on operator vigilance (*"don't share too widely"*).
  Under this ADR the page's own structural shape enforces the
  invariant intrinsically — there is no contact mechanism on the page
  that an arbitrary visitor could use, so the recipient pool is
  bounded structurally to people who already have the author's
  contact through the channel that delivered the URL. § 3.1's PyPI
  escalation review still triggers at the existing ~10-evaluator
  threshold; this ADR does not raise that ceiling, it makes the
  ceiling harder to violate accidentally.
- **Persona definitions stay single-sourced.** The page's panels read
  from the same canonical persona definitions that
  `phi-irb-risk-reviewer`, `researcher-utility-reviewer`, and the
  team's audit pipeline already use. A future revision to the
  persona definitions propagates to the public mirror on the next
  release rather than requiring parallel updates.

### Negative

- **The per-release ritual gets longer.** Each release now needs the
  persona panels rendered (three short paragraphs per section × five
  sections = fifteen panels). The `release-shipper` agent's
  public-mirror extension picks up the rendering as a build step.
  The attribution-only footer is a static template line that updates
  only when the boss-architect's name or attribution preference
  changes — substantially less maintenance than the originally-
  proposed multi-mailto footer would have required.
- **The public surface widens by one new content type (persona
  interpretation prose).** The previously-considered second new
  content type (human-contact affordance copy) was pruned entirely
  under the zero-outbound-affordances invariant. Persona
  interpretation panels remain a new place a future contributor
  could accidentally leak something — a reference to a real
  participant, a project-internal codename, a not-yet-ready feature
  claim. Mitigation: the persona-panel rendering reads from a
  structured single-sourced schema (parsed and validated at render
  time, version-pinned) rather than letting prose accumulate by hand
  or relying on best-effort markdown-section parsing of an agent
  file with no schema contract — closes `integration-auditor`'s F1
  finding. New failure mode under the affordance-pruning approach:
  a future contributor adds a contact link "to be helpful" — the
  render-time URL-scheme allowlist hard-fails CI if any
  non-allowlisted outbound URL appears in the rendered output,
  closing the failure mode structurally rather than relying on
  reviewer vigilance.
- **Feature depth is deferred, not addressed.** Section 5 of the demo
  exercises `ask_local_oracle` with `NullBackend`, which surfaces the
  architecture cleanly but does not give the friend a real LLM-
  composed narrative response. A follow-up release that wires a real
  Ollama backend into the demo would let the friend see the
  cooperation-loop output end-to-end. That work is named here as
  out-of-scope for this ADR and queued under a future ADR.

### Neutral

- **The public mirror's `README.md` becomes more complex.** The
  template grows from a transcript-and-breadcrumbs shape to a
  transcript-with-panels-and-attribution shape. A future
  `release-shipper` automation pass on the public-mirror extension
  will need to handle persona-panel rendering as a build step;
  current automation only handles transcript splicing.
- **ADR 0024 § 3.1's three reversal conditions stand unchanged.**
  Source repo stays private; bundled bytes stay synthetic by
  construction; recipient set stays handful-sized at the existing
  ~10-evaluator threshold operationalised in `share-the-demo.md`'s
  *"When NOT to share publicly"* section. This ADR adds a fourth
  invariant (zero outbound affordances on the public mirror) that
  is upstream of the handful-recipient condition — it makes the
  condition harder to violate accidentally rather than replacing or
  relaxing it.
- **The `docs/guides/share-the-demo.md` checklist updates separately.**
  The boss-side public-mirror setup ritual that landed in v6.12.0
  needs an extension naming the per-release verification step for the
  new rendering output (panel count check, no-outbound-URL assertion
  against the wheel-release-asset allowlist, attribution footer
  present, no contact information leaked). That edit is queued for
  the same patch that lands the rendering implementation, not this
  ADR.

## Alternatives considered

**Sharper minimum — keep the page transcript-only and just kill the
dead breadcrumbs.** Considered. Removing the broken breadcrumbs
without adding anything would resolve the 404 surface immediately and
preserve the v6.12.0 page shape exactly. Rejected because the boss-
architect explicitly chose to broaden rather than sharpen, and
because dead breadcrumbs are a symptom of a deeper *"what is the
page for?"* question. A page whose only job is to host a transcript
dump misses the per-persona interpretive layer that makes the
transcript legible to its actual audience. The sharper-minimum path
addresses the bug without addressing what the bug exposes.

**Human-contact-only mailto affordances — replace the dead-link
breadcrumbs with three pre-filled mailto links to the boss-architect's
email** (the originally-proposed approach in the 2026-05-08 first-pass
draft of this ADR before `integration-auditor`'s REVISE verdict
surfaced the structural problems). Considered and rejected on two
compounding arguments. (1) Operational: the only available email is
a personal Gmail handle whose exposure on a search-indexed public
GitHub Pages page is irreversible — once scraped into spam-list
databases, the handle cannot be unscraped, and the boss-architect
declined to commit a personal email to that surface. (2) Structural,
which is the load-bearing reason: ADR 0024 § 3.1's carve-out is
defined by the recipient receiving the URL personally from the
author, which means by carve-out construction the recipient already
has the author's contact through the channel that delivered the URL.
A page-side mailto would (a) duplicate an existing channel for
legitimate recipients and (b) create a new on-ramp for illegitimate
ones (cold-discovered visitors), exactly the recipient shape the
handful-recipient reversal condition forbids. The
*"my email doesn't need to go there; this demo should only work for
people who know me personally; my name is enough"* framing the
boss-architect supplied on 2026-05-08 made this rejection structural
rather than merely operational — the page should not invite a shape
of recipient the carve-out was never sized for.

**Feature depth — wire a real Ollama backend into Section 5 so the
friend sees a real LLM-composed narrative response.** Considered and
deferred, not rejected. Wiring a real backend would give the friend
the cooperation-loop output end-to-end and demonstrate ADR 0023's
prose-from-LLM / numbers-from-processing seam at first look. Deferred
because it is a meaningfully larger change (real Ollama dependency on
the demo path, model-download UX, latency considerations on the
shareable transcript) and because the narrative + affordance axes
this ADR commits to are independently load-bearing on the v6.12.0
page's reviewed shape. Named here as a future-ADR follow-up so the
deferral is recorded rather than dropped.

**Community-shape distribution — add Discord, public issue tracker,
public roadmap as the affordance set.** Considered. A Discord channel
or public issue tracker would let the friend file feedback
asynchronously without an email round-trip; a public roadmap would
let the friend see what is shipping next. Rejected on the
handful-recipient reversal condition. Discord, issue trackers, and
public roadmaps are scale-presuming surfaces — each implicitly
commits the project to engaging with a recipient population larger
than ADR 0024 § 3.1 contemplates, and each one's failure mode is
that the project quietly accumulates a community-shape obligation it
did not choose. The new invariant carves these out explicitly so that
adding any of them later requires a written reversal note that
supersedes this ADR.

**Direct amendment to ADR 0024 § 3.1 — fold the persona panels and
the affordance-pruning rule into the existing carve-out section
instead of writing a new ADR.** Considered. The narrative deepening +
affordance pruning is conceptually a continuation of § 3.1's work,
and amending § 3.1 in place would keep the public-mirror policy in
one findable section. Rejected on the structural argument that
ADR 0024 § 3.1 is already an amendment (added 2026-05-07 to the
2026-05-04 core ADR), and stacking a second amendment with its own
new invariant would bury that invariant two layers deep — the
zero-outbound-affordances rule needs to be findable on its own, not
as a sub-clause of a sub-clause. The same precedent applies as
[ADR 0026 splitting from ADR 0024](0026-claude-desktop-config-dual-path.md):
when an extension introduces a load-bearing new invariant rather than
refining an existing one, a separate ADR is the structurally honest
home.

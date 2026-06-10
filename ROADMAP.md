# Roadmap

Tailor is a *personal AI server with research-grade trust* — a
local-first MCP framework that lets any MCP-speaking LLM work with
your data, with every action audited and every result reproducible. The
identity stabilised at v7.0.0 ([ADR 0031](docs/adr/0031-rename-to-tailor-and-wardrobe.md));
this roadmap describes how Tailor moves from "researcher first-look on
a hand-delivered wheel" to canonical *personal AI server* over the
next several years.

The roadmap has two halves. **Phases 0, 1, and 2** are scheduled —
concrete deliverables with rough windows because the work is in arm's
reach and sequencing matters. **Phases 3, 4, and 5** are
direction-oriented — what Tailor is aiming at, with triggering
conditions instead of dates, because committing to schedules past six
months out is more cosmetic than honest.

**Phase 0 was the binding constraint and the most important honesty in
this document — and on 2026-05-12 it closed** under the lenient read
of its exit criterion (one Windows + one macOS install proven
cross-OS; see v7.0.8 § Shipped and the Phase 0 section below). For the
entire v6.x cycle and the first half of v7.x, no version of Tailor (or
its predecessors under the *Biosensor MCP* name) had been successfully
installed end-to-end on a machine that wasn't the project author's;
every prior external send produced a degraded or failed install
state, and until that changed every later-phase item was
castle-on-sand. The roadmap structure reflects this history:
install-path validation is the first phase; what was previously
labelled *"Phase 0 — ship-quality v7.0.0"* is now Phase 1, with every
other phase shifted accordingly.

Health-research workflows remain the first deployment recipe shipped
end-to-end. They are not the platform's identity. Future deployment
recipes (knowledge work, clinical, household, creative archives)
compose on the same engine.

## What the platform automates, end-to-end

The framework's lived experience for the user-as-analyst is a
four-link automation chain:

| Link | Component | Who built it |
|---|---|---|
| 1 | Hardware capture (e.g. Apple Watch records on start/stop) | Consumer-hardware vendor |
| 2 | Cloud auto-upstream (e.g. watchOS → Strava cloud, automatic) | Vendor + platform |
| 3 | MCP pull-and-cache (e.g. `strava_sync` → SQLite cache) | The framework |
| 4 | LLM analysis (router → child → tool → result) | The framework |

Links 1 and 2 are off-the-shelf consumer-hardware automation the
framework relies on but does not own. Link 3 is the framework's
last-mile closure (the running child since v3, generalised in
Phase 4). Link 4 is the router pipeline. **Each link is a potential
silent failure mode** — the audit log records Link 3 but not Links
1, 2, or the chain-as-a-whole. A static-only adopter (cohort CSVs in
a directory) experiences only Links 3 + 4; a live-data adopter
experiences all four. Phase 4 names both shapes directly and adds
the missing combination workflow that the platform's actual power
lives in.

## At a glance

| Phase | Status | Defining question at exit |
|---|---|---|
| **Phase 0 — Install-path validation** | Closed 2026-05-12 (lenient read; macOS install witnessed clean by boss) | Can two outside recipients on different OSes install Tailor end-to-end without the project author touching their machine? |
| **Phase 1 — Ship-quality housekeeping** | Closed 2026-05-12 (per v7.0.10 § Shipped — all four deliverables landed) | Do the docs and identity match the install path that actually works? |
| **Phase 2 — Public-launch readiness** | Near-complete (repo public + PyPI live; contribution-infra + merge-gate + dual-AI review shipped in the 05-26→05-29 burst; only the Apple Silicon recipe remains open — and the *loud* launch is deliberately held, see Phase 3) | If a stranger discovers Tailor cold, can they find, install, and start trusting it in under 30 minutes? |
| **Phase 3 — Beachhead proof + public launch** | Direction (Direction A beachhead **shelved** 2026-05-28; Direction B launch narrative parked under quiet-launch posture) | Has one real research lab used Tailor on real data, cited it in a paper, and would they recommend it? |
| **Phase 4 — Platform-shape proof** | Direction | Can a stranger use Tailor with their own data — live or static — and combine the two via any MCP client of their choice? |
| **Phase 5 — Category formation** | Direction | Do strangers know what *"personal AI server"* means, and do they think of Tailor when they think of it? |

Items not in a phase live in [Held](#held-items-revisit-when-the-trigger-fires) (waiting for a triggering condition), [Killed](#killed-items-with-rationale) (explicitly not doing), or [Shipped](#shipped-chronological) (history).

---

## Phase 0 — Install-path validation *(closed 2026-05-12; lenient read on the two-outside-recipients exit criterion — see v7.0.8 § Shipped)*

**Closure note (2026-05-12)**: Phase 0 closed under the lenient read of
its exit criterion. The 2026-05-09 Windows install (self-driven
diagnosis on a fresh `tailor-recipient` user account against Microsoft
Store Claude Desktop) proved the technical install path; the
2026-05-12 macOS install (a friend ran the wheel install and `tailor
tour` on their own Mac with the boss watching only) proved the
recipient-experience path. The strict read of the exit criterion — two
clean outside-recipient installs with the project author untouched at
every step — remains open and is being satisfied opportunistically.
Boss made the closure call on 2026-05-12 per v7.0.8 § Shipped. The
pre-closure framing below is retained as the historical record of what
Phase 0 looked like before it closed; the PATCH-not-RESTRUCTURE
verdict (see v7.0.4 § Shipped) is the diagnosis-bound deliverable's
historical answer.

*Pre-closure framing (retained as historical record):*

For the entire v6.x cycle and the first half of v7.x, no version of
Tailor (or its predecessors under the *Biosensor MCP* name) had ever
been successfully installed end-to-end on a machine that wasn't the
project author's. The v6.10.x patch quartet (cp1252, dual-path Claude
Desktop, sibling cleanup, Microsoft Store sandbox), the v6.11.0
`recipient-install-validator` (silent-parked on its second wild run
per project memory; falsified), and the v6.13.0 demo polish all
composed on top of *"the framework runs on the user's machine"* — a
baseline assumption that was empirically not yet true outside the
project author's own dev environment until the 2026-05-09 + 2026-05-12
install pair landed.

Phase 0 was the discovery and resolution work that made that
assumption honestly true for two external recipients. The phase had no
fixed window because its duration was diagnosis-bound: it could have
been days (visible bugs that fix cleanly) or weeks
(architecture-level rework — single-binary executable, Docker
container, one-shot installer). Both outcomes were valid; Phase 0 was
the work that revealed which.

| Deliverable | Why it matters |
|---|---|
| **Diagnose what's actually breaking installs.** Pick a fresh VM or a colleague's clean machine; walk through the install ritual exactly as documented; log every friction point with timestamps. *Do not fix anything yet — diagnose first.* | The v6.10.x patch quartet was reactive — each visible bug got fixed and the install still didn't work. That suggests the surface bugs aren't the actual binding constraint. Diagnosis precedes patches. |
| **Decide whether the current install architecture is achievable for non-developers.** After diagnosis, decide: patch the existing `uv tool install + tailor tour + Claude Desktop restart` ritual, or restructure (single-binary executable via PyInstaller / Nuitka; Docker container; one-shot installer that drives Claude Desktop config programmatically). | Determines whether Phase 0 is *days of bug fixes* or *weeks of rearchitecting*. Conflating them is what produced the patch quartet without solving the underlying problem. |
| **Prove install works on ONE outside fresh machine.** Whatever architecture survives diagnosis, the success criterion is: the chosen machine completes install end-to-end, demo runs, vault writes, Claude Desktop sees the tools — without the project author touching the recipient machine at any step. | This is the binding constraint. Without it, every roadmap item past this phase is castle-on-sand. |
| **Prove install works on a SECOND outside fresh machine, different OS.** Reproducibility is the test. One install success could be lucky (machine state, network conditions, undocumented step the recipient happened to know); two consecutive successes on different machines and different OSes is the property the project has never had. | Phase 0's exit criterion is *reproducibility*, not *one-time success*. |

**Phase 0 exit criterion**: two consecutive fresh-machine installs by
outside parties on different OSes succeed end-to-end without
intervention from the project author. *Until this is achieved, no
Phase 1+ work ships publicly* — public action without working installs
amplifies the failure rather than the project.

---

## Phase 1 — Ship-quality housekeeping *(closed 2026-05-12)*

Once Phase 0 produces a reliably-working install path, the
housekeeping work that was previously labelled *"ship-quality v7.0.0"*
lands honestly. These deliverables clean up artifacts of v7.0.0's
shipping shape — some of which were over-engineered for a population
that turned out not to exist (notably `tailor migrate`, which migrates
from a v6 install state no external machine has ever held).

| Deliverable | Effort | Why it matters |
|---|---|---|
| ~~**Rename GitHub repo** `Biosensor-to-LLM-Connector` → `tailor-mcp`~~ — **landed 2026-05-10** as a doc-truth pass closing the [ADR 0031 § Negative consequences](docs/adr/0031-rename-to-tailor-and-wardrobe.md) known-debt entry; auto-redirect preserves any existing clones. To be filed in § Shipped at the next version bump. | — | — |
| ~~**Remove `tailor migrate` subcommand + draft ADR 0034**~~ — **landed 2026-05-12 in v7.0.9** ([ADR 0034](docs/adr/0034-retire-tailor-migrate-subcommand.md)). Subcommand + startup warning both retired; v6 population was empirically zero. ROADMAP originally said "ADR 0032" but 0032 was taken by [ADR 0032 (Retire public-mirror distribution)](docs/adr/0032-retire-public-mirror-distribution.md) on v7.0.6 — the migration ADR is 0034. To be filed in § Shipped at the next version bump. | — | — |
| ~~**Update README install commands** to reflect the install path that survived Phase 0~~ — **landed 2026-05-12 in v7.0.10**. Six framing callouts and table rows updated to reflect Phase 0 lenient-read closure; anchor fix for four `#phase-0--install-path-validation` refs repointed to `#at-a-glance`; ADR count refreshed 31 → 34. All four Phase 1 deliverables now landed; Phase 2 unblocks. | — | — |
| ~~**Update v7.0.0 banner in CLAUDE.md** to reflect post-migrate-removal state~~ — **superseded by the banner-stacking convention** established since v6.11.1: a new v7.0.9 banner stacks above v7.0.8; v7.0.0's banner is left intact as the running record of what that release actually shipped. Banner-stacking is the load-bearing convention; rewriting prior banners breaks cross-checking against `CHANGELOG.md`. | — | — |

**Phase 1 exit criterion**: docs and identity match the install path
that actually works, the repo is publicly discoverable under its real
name, and the project's surface area no longer carries scaffolding for
problems that don't actually exist.

---

## Phase 2 — Public-launch readiness *(after Phase 1 → ~3 months)*

Phase 2 closes the gates between *"private repo, hand-delivered wheel"*
and *"publicly discoverable, pip-installable OSS framework."* Each
deliverable removes a structural friction that would otherwise meet
strangers at the door.

| Deliverable | Effort | Why it matters |
|---|---|---|
| ~~**Publish to PyPI as `tailor-mcp`**~~ — **Shipped in v7.0.13 (2026-05-13)** | — | The canonical install path named in [ADR 0031](docs/adr/0031-rename-to-tailor-and-wardrobe.md) ("when published") landed; `uv tool install tailor-mcp` is the install command. Closes the hand-delivered-wheel gap. |
| ~~**Make the GitHub repo public**~~ — **Done 2026-05-27.** Repo flipped to public ahead of the original three-condition trigger: with the beachhead lab shelved (2026-05-28) condition 1 will not fire, and condition 2 (launch narrative) is parked under the quiet-launch posture, so only condition 3 (boss decides) remained — and the boss made that call. The flip is **mechanical-only**: the repo is discoverable and the wheel/source is inspectable, but there is deliberately **no loud launch** (no HN/Reddit/blog distribution) — see Phase 3 Direction B. To be filed in § Shipped at the next version bump. | — | The original three-condition trigger is retired as moot; see [§ Held items](#held-items-revisit-when-the-trigger-fires). |
| ~~**Promote `vocabulary-drift-auditor` agent (reshape of retired `counter-programming-invariant-auditor`)**~~ — **KILLED in Phase 2 planning 2026-05-12** ([§ Killed](#vocabulary-drift-auditor-specialist--killed)). [ADR 0033 § Negative consequences](docs/adr/0033-complete-tailor-metaphor-workshop-side.md) explicitly delegated vocabulary drift to `code-vs-roadmap-drift-auditor`'s existing remit and stated *"does not need a new specialist."* Applied to [ADR 0011](docs/adr/0011-promotion-policy.md)'s three criteria: structural argument is weak (register/taxonomy detection is distinguishable from fact-checking, but the architect ADR already named the seam holder), severity is low (identity-cost, not safety-cost), and the always-forbidden six-word list is grep-enforceable in principle. A pytest invariant for the always-forbidden six was prototyped during planning and deliberately not landed; Table 5 enforcement is PR review per ADR 0033 § Negative consequences' original delegation. | — | — |
| ~~**First-time-user setup pass**~~ — **first end-to-end pass landed in v7.3.4 (2026-05-16)**. 2026-05-16 first real outside-recipient walkthrough (Windows + Claude Desktop, non-technical friend) drove five closures: cohort thesis hot path (D1+D1-companion), API parity (D2), vault de-Strava (F3), bundled `snapshot.md` orientation fixture, AI-economics demonstration via configurable `cost_threshold`. See [Shipped in v7.3.4](#shipped-in-v734-2026-05-16). Continuation work queued for v7.4.0 (ADR 0038 full sweep, `audit_query` tool, `value_column`↔`column` API parity, cost-estimator calibration). | — | — |
| **Apple Silicon reference deployment recipe** | 1 week | Document the *"Tailor on a Mac mini"* recipe for newcomers — recommended hardware tier (M4 24GB minimum), bundled local LLM (Llama 3.1 8B via MLX), always-on LaunchAgent setup, troubleshooting. Decides what *"AI-optimized computer"* means concretely for v1. |
| ~~**CONTRIBUTING + community machinery**~~ — **landed 2026-05-27** (PR #123): CI workflow, child-contribution guide, code of conduct, PR/issue templates. To be filed in § Shipped at the next version bump. | — | — |

**Phase 2 exit criterion**: a stranger who hears about Tailor through a
blog post or HN thread can complete `pip install tailor-mcp →
tailor pilot → working demo` in under 30 minutes, on either a Mac mini
or their daily-driver machine, without reading source code.

---

## Phase 3 — Beachhead proof + public launch *(direction)*

Phase 3 is about turning private architecture into public reputation.
The platform is real; the trust narrative needs evidence. Two
parallel directions:

**Direction A — land a real research lab using Tailor on real data.**
**Shelved 2026-05-28** — not being pursued in the current launch push
(not killed; revisitable). A prospective beachhead-lab partnership
remains the seed if it reopens. The consequence of shelving: the launch
narrative (Direction B) can no longer lean on a "real lab uses it"
testimonial and must stand on the architecture, the trust moat, and the
benchmark numbers instead. Success, if reopened, looks like one PI
running an actual analysis through `tailor` on their lab's own data,
citing the framework in a methods section, and being willing to be
referenced in launch materials. A second beachhead lab was previously
named as a parallel fallback.

**Direction B — ship the launch narrative.** The artifacts that get
distributed everywhere a stranger might discover Tailor:

- A long-form launch post — *"Why we built a Tailor for your AI's
  Wardrobe"* or similar — that defines Wardrobe in the first
  paragraph (counter-programming), lands the trust moat in the second,
  names the beachhead use case in the third, points at the public repo
  + PyPI in the fourth. ~1500 words.
- An honest comparison artifact against Khoj / Open WebUI /
  AnythingLLM — *"What changes when governance is structural."* The
  honest comparison post does more work than any ad copy.
- A conference talk in the beachhead tribe (kinesiology / biomech /
  RSE / mHealth). The talk pays for itself in adoption signal.
- Distribution to HN, r/selfhosted, r/LocalLLaMA, Mastodon, conference
  adjacency posts — all in the same week as the launch post, so the
  signal compounds.

**Trust-moat strengtheners that ship in this phase as launch-narrative
content**:

- [Provenance hashing on derived metrics](#provenance-hashing-on-derived-metrics) — closes the [ADR 0008](docs/adr/0008-deterministic-by-construction-processing.md) residual gap; lands well in the launch narrative ("every published number traces to exact bytes").
- [Vault-freeze for manuscript submission](#vault-freeze-for-manuscript-submission) — ships when the beachhead lab needs it for an actual submission.

**Direction-level exit criterion**: one real research lab has used
Tailor on real data, the launch post is live, and the trust narrative
has been pressure-tested by strangers (some of whom disagreed with it
publicly — that's the test that the narrative holds).

---

## Phase 4 — Platform-shape proof *(direction)*

Phase 4 turns the platform vision into a property. Today, *"any data
source, any MCP-speaking LLM"* is a claim the architecture supports
but the shipped recipes do not yet demonstrate. Six directional moves
close the gap. Direction D — combination workflows — is the
load-bearing one: it answers *"what is Tailor for?"* in a way the
other five cannot in isolation.

**Direction A — generalise the live-ingestion pattern.** The running
child encodes a five-piece live-platform pattern (OAuth wizard +
rate-limited API client + SQLite cache + on-demand sync tool +
three-tier access). That pattern has not been generalised beyond
Strava since v3. Ship one non-Strava live-biometric child as the
proof — strongest candidates by adopter pull are Oura Cloud, Dexcom
Clarity, and Apple Health Cloud / HealthKit. The pick is driven by
Phase 3 beachhead-tribe demand. The structural lesson: *the
ingestion-automation pattern is reusable, not Strava-specific* —
which the codebase has implied since v4 but never demonstrated.

**Direction B — one non-biometric flagship child.** The smallest move
that makes data-agnostic a property, not a claim. Notes (Apple Notes,
Obsidian, plaintext), calendar (CalDAV, Google Calendar), email (IMAP,
Gmail), or photos (vision-indexed) are the natural candidates. The
pick is shaped by which beachhead tribe pulls hardest after Phase 3 —
if researchers ask for it, calendar; if knowledge workers ask, notes;
if quantified-self users ask, photos. The structural lesson: *"Tailor
isn't biometric infrastructure"* lands the moment one non-biometric
child works.

**Direction C — first-class ingestion-automation surface.** The
`ChildMCP` contract today is request/response only — there is no
slot for *"data arrived; ingest it"* or *"sync this every N
minutes."* The user-experienced *"press start on the watch, ask
Claude later"* loop relies on Links 1 and 2 (consumer-hardware
upstream) being silently always-on; the framework cannot make the
same claim about Link 3, which only fires when an LLM tool call
triggers it. New framework-level `IngestionLayer` parallel to
`VaultLayer` and `LocalLLMLayer`, plus push-mode support on the
`ChildMCP` contract. Owns scheduled background re-sync (cron /
launchd / LaunchAgent), webhook reception, file-watcher ingestion,
and the iOS-Shortcuts → local-endpoint bridge. Architectural
prerequisite for Direction A's live children to run continuously
rather than on-demand.

**Direction D — combination workflows: static + live.** *The*
load-bearing platform-shape claim. Live children supply *current
state* (your latest run, recovery, glucose trace); static children
supply *reference distribution* (cohort baselines, published
datasets, prior analyses). Neither half answers the natural
analytical question — *"where do I land in the cohort distribution
on this metric?"* — alone; both halves plus the LLM reasoning
across them via the router's existing `dispatch_internal()`
cross-child seam do. The ChildMCP plurality the framework has
shipped since v4 is half the claim; the realised combination
workflow is the other half. One reference workflow ships in this
direction, likely *"compare my morning run to the demo cohort
distribution"* — pairs the running child (live) with the bundled
demo cohort `csv_dir` cohort fixtures (static) through
`dispatch_internal()`, exposed as a first-class tool
(`compare_me_to_cohort` or similar) and as a new section in a
future demo reshape. The demo cohort fixtures + Strava are already
half-built in the codebase; what is missing is the workflow
surface that names them as a combination, not as two unrelated
children.

**Direction E — one non-Claude MCP client integration.** The smallest
move that makes plug-and-play a property, not a claim. Cline (VSCode
extension, MCP-native) and Goose (Block's open-source MCP client) are
the strongest candidates because they're MCP-native and active. A
documented end-to-end run — install Tailor, install Cline, ask a
question, see the response come from Tailor — closes the *"works with
any MCP-speaking LLM"* gap.

**Direction F — framework visibility surfaces.** Two interlocking
pieces:

- **Web UI dashboard / live inspector** — framework visibility.
  **Partially shipped (Stage 1) per [ADR 0043](docs/adr/0043-read-only-inspector-not-application.md):**
  `tailor inspect` serves a read-only localhost page (gate activity,
  recent audit rows, consent timeline derived from audit events,
  scrubber posture, token estimates, vault index counts) plus
  `--export` for a static artifact. Deliberately *not* shipped from
  the original sketch: live consent state (in-memory in the server;
  rendered as derived-from-audit instead), the vault graph, and any
  ambient always-on surface — Stages 2–3 of the ADR 0043 invocation
  ladder are designed, trigger-gated, and not built. Non-technical
  adopters need a *"what's it doing"* surface; IRB reviewers and
  co-PIs need inspect-without-querying-SQLite.
- **Data-quality surface for messy real-world data** — real biometric
  data is messier than synthetic. The framework computes statistics on
  whatever loads, with no flag for *"this subject's data is suspect
  because X."* A QA layer that scores data quality per subject and
  surfaces structured warnings makes the framework actually trustworthy
  on real-world dirty data, not just synthetic fixtures. This is also
  where the *"everything is synthetic by construction"* precondition
  starts to break the moment a real adopter loads real data.

**Trust-moat extensions that ship in this phase**:

- [Deterministic mode + seed control](#deterministic-mode-and-provenance-hashing) — bundled with provenance hashing because the cosmetic flag is pointless alone.
- [LLM-client evaluation harness](#llm-client-evaluation-harness) — measures the plug-and-play claim; promoted from the previous roadmap because it becomes *the* measurement infrastructure for cross-client governance.

**Direction-level exit criterion**: a stranger could use Tailor with
their own live data (run, sleep, glucose, recovery — Direction A) AND
their own static data (notes, calendar, photos, cohort CSVs —
Direction B), combine the two through a workflow like
*compare-me-to-cohort* (Direction D), with ingestion happening in the
background not just on-demand (Direction C), and ask the question in
Cline / Goose / a local-Ollama-fronted client (Direction E). When
that loop works end-to-end, *platform-shape* stops being a claim.

---

## Phase 5 — Category formation *(direction)*

Phase 5 is the longest horizon and the most aspirational. It assumes
Phase 4 succeeded — platform-shape is proven, plug-and-play works,
one non-biometric child shipped. The question becomes: *do strangers
know what category Tailor is in, and is Tailor canonical in that
category?*

**Direction A — tribe-2 and tribe-3 adoption.** The trust narrative
established by researchers (Phase 3) earns adoption from clinicians,
therapists, lawyers, journalists — professionals dealing with sensitive
data who can't put it in the cloud. Each tribe has slightly different
ingest needs (clinical notes, case files, source documents) but the
trust moat is identical. Each new tribe adopting validates the
platform framing for the next.

**Direction B — community contribution.** Strangers contribute their
own children — for data sources nobody on the team has ever worked
with. The plugin contract has to be public-stranger-friendly enough
that contributing a child is a 30-minute experience for a casual
outside developer, not a 4-hour journey through internal abstractions.
The structural test: a child contributed by someone who has never met
the maintainer.

**Direction C — multi-user / household deployment recipe.** The
*"AI-optimized computer for a family"* deployment shape per the v7.0
strategic conversation. Networked MCP transport (SSE / HTTP), real
authn / authz, per-user vault scoping, mobile companion (iOS Shortcuts
integration at minimum). This is genuinely product-shaped engineering
and only makes sense once the single-user framework is canonical.

**Trust-moat work that lands as the category solidifies**:

- [Real PHI-scrubbing implementations](#real-phi-scrubbing-implementations) — institutional-policy-shaped; ships when a real institutional adopter brings their policy.
- [PHI sidecar-schema validator](#phi-sidecar-schema-validator) — pairs with real PHI-scrubbing.
- [New ChildMCPs (CGM, sleep, ECG, EDF, FHIR)](#new-childmcps-for-research-relevant-data-sources) — research-shaped children. CGM is most natural; could be promoted to Phase 4 if it doubles as a non-research demo (continuous-glucose tracking for the quantified-self tribe).

**Direction-level exit criterion**: when someone says *"personal AI
server"* in a developer or quantified-self context, *Tailor* is one of
the first names mentioned. The category exists in stranger vocabulary
and Tailor is canonical-shaped within it.

---

## Held items (revisit when the trigger fires)

These items are out of scope for active phases but kept on the radar
with explicit triggering conditions. When the trigger fires, the item
gets promoted into the next applicable phase.

### Make the GitHub repo public — FIRED 2026-05-27 (trigger retired)

**This item has fired; retained here as the record of how the decision
was actually made versus how it was originally gated.** The repo is
public as of 2026-05-27. To be filed in § Shipped at the next version
bump.

The original gate (below) required ALL three of: (1) a beachhead lab
using Tailor on real data, (2) launch-narrative artifacts drafted, (3)
boss decides he wants public scrutiny. The flip happened with only
condition 3 met, and the gate is now **retired as moot**:

- **Condition 1 will not fire** — the beachhead lab is shelved
  (2026-05-28; see Phase 3 Direction A).
- **Condition 2 is parked** — the launch narrative is deliberately not
  being drafted under the quiet-launch posture.
- **Condition 3 fired** — the boss made the public-flip call.

The load-bearing reframe: the repo being public is **mechanical-only**,
decoupled from the *loud launch*. Going public (discoverable, source +
governance trail inspectable) and going loud (HN / Reddit / blog
distribution) are now two separate decisions; the first is done, the
second is held. The original three-condition gate conflated them.

*Original context (retained as historical record):* v7.0.13 split the
Phase 2 "PyPI publish + repo public-flip" bundle into two separable
decisions because they answer different questions. PyPI answers a
tooling question (*"is there a frictionless install path?"*) — YES.
Repo public-flip answered an audience question (*"is the trust
narrative going out into the world?"*) — at the time, NOT YET. The
landing page at
[saahasmuthineni.github.io/tailor-mcp-landing](https://saahasmuthineni.github.io/tailor-mcp-landing/)
served the *"invited evaluation"* framing for visitors without a
back-channel.

**Pre-flip safety pass that should still run before any future history
exposure:** `integration-auditor --proposal-mode` over the repo to
confirm no commit-message or file content an incognito visitor
shouldn't see leaked into history — worth running now if it was not run
before the flip, since the repo is already live.

### Real PHI-scrubbing implementations

`DataScrubber.scrub()` ships today as a documented no-op seam. The
roadmap items are institutional-policy-specific implementations:
transforms that drop or hash identifying fields before results leave
the router, bound to the specific shape of a CGM child, a sleep child,
a FHIR-bundle child, etc. As of v6.2 the `scrubber_id` is recorded in
audit-log column + `_meta` block; v6.3.1 surfaces the no-op warning
into every successful result. See [ADR 0003](docs/adr/0003-phi-scrubber-seam.md).

**Trigger**: a real institutional adopter brings an IRB-approved
policy that needs wiring. Earlier than that, the seam is the right
shape; the implementation is institutional-specific work that cannot
be done speculatively.

### New ChildMCPs for research-relevant data sources

Each is a candidate worked-example child for a research group that
doesn't want to start from scratch:

- **CGM child** against OhioT1DM or the Jaeb Diabetes Research Center's public datasets — time-in-range, glycemic variability, meal-response curves, nocturnal hypoglycemia flagging.
- **Sleep child** against PhysioNet's Sleep-EDF — stage durations, efficiency, latency, fragmentation indices, REM/NREM structure.
- **ECG child** against MIT-BIH — rhythm classification, HRV windows, QT intervals, beat-level anomaly flagging.
- **EDF file child** — direct ingestion of European Data Format recordings common in sleep and EEG research.
- **FHIR bundle child** — ingestion of FHIR bundles for lab values, medication histories, or vitals.

A `children/template/` skeleton already ships with three Tier-1 tools,
one Tier-2, one Tier-3, every abstract method stubbed, param schemas
illustrated, and `entity_id` wired throughout. New children fork from
`src/tailor/children/template/` rather than reading the running child
end-to-end.

**Trigger**: Phase 5 by default; CGM specifically can promote to
Phase 4 if it doubles as a non-research platform-shape demo (e.g. a
quantified-self user wants their own glucose data in their Wardrobe).

### Live-platform consumer-biometric children (paired with static counterparts)

The Strava child is the worked example of the OAuth-API +
rate-limited API client + SQLite-cache + tier-model pattern — the
project's first shipped child and the first link of code the
framework owns in the four-link automation chain (see *What the
platform automates, end-to-end* above). The held items below name
live consumer-biometric platforms paired with the static children
they combine with per Phase 4 Direction D. Each live candidate is
justified by the static counterpart it composes with through
`dispatch_internal()`, not by live-for-live's-sake.

| Live child | Static counterpart on roadmap | Combination workflow it enables |
|---|---|---|
| **Apple Health Cloud / HealthKit** | EDF (sleep), FHIR (vitals), csv_dir (cohort exports) | Personal multi-modal record vs published reference distribution |
| **Dexcom Clarity / Libre View / Nightscout** | OhioT1DM static CGM child | Live glucose vs published-cohort distribution |
| **Oura Cloud** | Sleep-EDF (PhysioNet) static sleep child | Live sleep architecture vs cohort norms |
| **Whoop** (webhook-capable) | — (exercises Direction C push-mode) | Recovery trajectory vs prior personal baseline |
| **Garmin / Polar / Fitbit** | csv_dir (cohort exports), running-child Strava complement | Multi-platform watch coverage vs lab-collected cohort |

**Trigger**: Phase 4 Directions A and D ship together — each new live
child is justified by the static counterpart it combines with. Apple
Health specifically pairs with Direction C shipping (HealthKit
ingestion is push-mode-shaped via iOS Shortcuts). Promotion order is
shaped by Phase 3 beachhead-tribe demand; the table is a menu of
viable picks, not a sequence. A future ADR records the architectural
commitments (audit-log scope on Link 3 only; combination as
first-class workflow shape) when the first real combination workflow
ships or a second live child lands — until then the roadmap holds
the commitment without codifying it.

### Per-analyst attribution on vault evidence blocks

Evidence blocks on theme notes are timestamped but unattributed. In
multi-analyst studies, *"who recorded this observation"* is
load-bearing context. Vault-writer parameter for analyst identity,
threaded through to evidence-block frontmatter and rendered in the
Obsidian view, is the clean version.

**Trigger**: a multi-analyst lab actually adopts Tailor and the
ambiguity matters in practice. Until then, single-analyst is the
working assumption.

### Vault-freeze for manuscript submission

A tool or CLI command that snapshots the vault state (markdown files,
index rows, associated audit rows, exact code version running at
snapshot time) into a single archive suitable for attaching to a
manuscript submission.

**Trigger**: a beachhead lab needs it for an actual submission. Likely
Phase 3 with a beachhead-lab partnership. Could ship earlier if a
different research adopter requests it first.

### Worked-example notebook v2 against a published analytical question

A first-pass notebook ships at [docs/guides/worked-example.ipynb](docs/guides/worked-example.ipynb).
What's deferred is a second notebook against a *public dataset*
answering a *published analytical question* — demonstrates the
framework on a reference result an outside reviewer can check, rather
than synthetic data.

**Trigger**: best paired with whichever non-Strava research child
lands first (CGM with OhioT1DM, or Sleep with PhysioNet Sleep-EDF, are
the natural anchors).

### Provenance hashing on derived metrics

The `_meta` block stamps package version, tool name, and call
timestamp today. The full version is a hash chain from raw-data input
through intermediate processing stages to each derived metric — so a
paper reviewer can trace every published number to exact code version
and exact input bytes that produced it.

**Trigger**: targets Phase 3 as launch-narrative content (*"every
published number traces to exact bytes"* is a strong trust signal).
Bundles with deterministic mode below.

### Deterministic mode and provenance hashing

Per [ADR 0008](docs/adr/0008-deterministic-by-construction-processing.md),
no analytical function in `framework/` or any `children/*/processing.py`
touches PRNG, reads a clock, or holds module state — every method is
a `@staticmethod` pure function. Same Tier-1 call returns the same
numbers across machines without any runtime flag.

What remains: a router-level `deterministic_mode` flag stamped into
`_meta`, paired with content-hashed provenance (above) so a reviewer
can confirm a result was produced under the invariant. The flag is
cosmetic without the hash; ADR 0008 commits to deferring as joint
work with provenance-hashing.

**Trigger**: ships with provenance hashing in Phase 3 / 4.

### LLM-client evaluation harness

Different LLM clients (Claude Desktop, Claude API directly, third-
party MCP clients) vary in how they handle consent and cost gate
prompts. An evaluation harness that replays scripted analytical
conversations through different clients and measures gate compliance,
scope drift, and vault-recall accuracy makes the *"client-agnostic
governance"* claim measurable.

**Trigger**: Phase 4 — becomes the measurement infrastructure for
plug-and-play once the first non-Claude integration ships.

### PHI sidecar-schema validator

[ADR 0015](docs/adr/0015-tier-1-cohort-surface-and-metadata-sidecar.md)
documents that the `metadata.json` sidecar sits *out-of-band* of the
[ADR 0003](docs/adr/0003-phi-scrubber-seam.md) PHI-scrubber seam. A
deployer can pack HIPAA Safe Harbor §164.514(b)(2) identifiers (full
DOB, full ZIP at 5-digit, MRN, full name) into the sidecar and the
framework will not police it. Fix: a `csv_dir.metadata_schema` config
knob declaring allowed / denied field names, enforced at child init,
fail-closed.

**Trigger**: bundles with real PHI-scrubbing work (Phase 5 default).

---

## Killed items (with rationale)

Items that were on the prior roadmap and are explicitly *not* being
done. Listed with kill rationale so a future contributor reading the
roadmap understands why the item disappeared rather than assuming it
was forgotten.

### CLI UX rename `setup` → `setup-strava` — KILLED

The previous roadmap deferred this on doc-churn grounds. Under the
v7.0.0 platform-vision identity, the rename is the wrong shape: as
more children land, Strava becomes one of many domain-specific OAuth
flows, and the right pattern is *"each child owns its own
domain-specific setup if needed"* — not a top-level `setup-strava`.
The structural answer is that `tailor setup` will eventually be
deprecated entirely as Strava-specific, with each child wiring its own
auth subcommand if needed. Re-evaluate only if Strava remains the only
OAuth-bearing child after Phase 4.

### Pre-existing `csv_dir` HIGH-region coverage debt — KILLED as roadmap entry

The 34 lines of pre-existing test debt in `csv_dir/child.py` are
engineering hygiene, not roadmap-shaped. A roadmap entry implies
strategic decision; coverage debt is a *do-it-during-the-next-hygiene-
pass* item. The [`coverage-criticality-mapper`](.claude/agents/coverage-criticality-mapper.md)
agent surfaces it on every diff that touches the file; that's the
right enforcement seam, not a roadmap line. Will be closed
opportunistically when other work touches that surface.

### `vocabulary-drift-auditor` specialist — KILLED

In Phase 2 planning on 2026-05-12, the candidate specialist was
evaluated against [ADR 0011](docs/adr/0011-promotion-policy.md)'s
three criteria — structural argument, severity grounding, and
maintenance-vs-frequency. The verdict was *not promote*.

The decisive evidence is [ADR 0033 § Negative consequences](docs/adr/0033-complete-tailor-metaphor-workshop-side.md):
*"The vocabulary file is a new documentation surface that must stay in
sync with the code and the ADRs. Drift between `tailor-vocabulary.md`,
the shipped code, and the ADR set is now a class of bug. Mitigated by
the existing `code-vs-roadmap-drift-auditor` remit — the file is
treated as documentation under that agent's existing scope and does
not need a new specialist."* The Phase 2 ROADMAP row was authored
either before or in the same change as ADR 0033 and the conflict was
not reconciled at the time. The retirement honors the architect ADR.

Applying ADR 0011 explicitly:

- **Structural argument** — *weak.* Register and taxonomy detection
  (Tables 1–4) are distinguishable from `code-vs-roadmap-drift-auditor`'s
  fact-checking remit, but the architect ADR already named the seam
  holder. A new specialist would silently override ADR 0033.
- **Severity grounding** — *low.* Cost-of-absence is workshop register
  collapsing, which lands in [ADR 0033 § Reversal conditions](docs/adr/0033-complete-tailor-metaphor-workshop-side.md)
  not a PHI / IRB / reproducibility incident. This is the opposite end
  of the severity spectrum from the four v6.3.0 promotions ADR 0011
  exemplified.
- **Maintenance vs frequency** — *not the binding constraint.* Even
  at low maintenance and medium-to-high fire frequency, criteria 1 and
  2 already gate the promotion.

Both portions of Table 5 — the always-forbidden six (couture,
couturier, atelier, boutique, runway, showroom) and the
lifestyle-register-only nine (collection, look, style, trend,
designer, outfit, brand, aesthetic, showcase) — are owned by PR
review per ADR 0033 § Negative consequences' original delegation. A
pytest invariant for the always-forbidden six was prototyped during
Phase 2 planning and deliberately not landed; the call was that a
mechanical floor was not worth the maintenance cost on a rule whose
violation has never occurred and whose enforcement seam ADR 0033 had
already named.

Re-evaluate only if recipient evidence of consistent workshop-register
collapse accumulates — that is the same trigger ADR 0033 § Reversal
conditions 1 names for the entire metaphor identity, and the agent
would land as part of the broader vocabulary-amending change rather
than as an isolated promotion.

### Legacy `demo` → `verify` rename — KILLED in v6.10.5 per ADR 0027

(Preserved here from the prior ROADMAP for historical continuity.)

The deferred rename is no longer the right move. v6.10.5 reframed
`tailor demo` from operator-self-verification to **researcher
first-look** per [ADR 0027](docs/adr/0027-demo-as-researcher-first-look.md).
A researcher-first-look surface should not be called `verify`; the
`verify` framing presupposed the operator-self-verification job the
demo no longer does. The `tour` vs `demo` distinction is now: `tour`
is the audience walkthrough that scaffolds durable state and registers
Claude Desktop; `demo` is the cold first-look that runs cohort tools
against the same bundled fixtures in a tempdir and writes nothing.

---

## Shipped (chronological)

History of the project's shipped releases. Preserved verbatim from
prior roadmap revisions per the same historical-preservation principle
[ADR 0031](docs/adr/0031-rename-to-tailor-and-wardrobe.md) applies to
`CHANGELOG.md` — these entries describe past state and rewriting them
would falsify the historical record.

### Shipped in v9.0.2 (2026-06-02)

- **Public-surface name scrub** — a collaborating lab's name, a co-author's
  name, and a PI's name (except the allowed "Hunter & Senefeld 2024, J Physiol"
  citation) removed from the public repo and the shipped wheel. Three internal
  pitch artifacts git-removed from a lab-named subdirectory of `examples/`.
  No API or behavior change.
- **Fixture and variant renames** — bundled `_fixtures` demo directory renamed
  to `cohort_demo_realistic`; fitting-room demo variant renamed to `cohort`
  (server id `tailor-fitting-room-cohort`, path `demos/cohort`); `examples/`
  directory renamed from lab-named to `examples/cohort_demo/`. All generic
  "demo cohort" / "cohort demo" naming throughout.
- **Benchmark sync** — `benchmarks/token_efficiency.md` and
  `benchmarks/token_efficiency.py` updated to current fixture layout;
  session-resume ratio corrected to **318.2x** (per-query 657.6x / 938.2x
  unchanged).

### Shipped in the public-launch burst (2026-05-26 → 2026-05-29)

The § Shipped log previously stopped at v7.6.0; v8.0.0, v9.0.0, and the
post-flip surface-hardening burst are recorded here. Full per-release
detail for v8.0.0 and v9.0.0 lives in the stacked CLAUDE.md banners
(preserved as the canonical release record per the banner-stacking
convention); this section is the catch-up summary.

- **v8.0.0 (2026-05-19)** — recipient-experience MCP-offload (ADR 0040): three new framework-tier layers (`SetupLayer` / `WalkthroughLayer` / `FittingRoomLayer`); four CLI commands hard-removed (`walkthrough` / `fitting-room` / `tour` / `demo`). Recipients now drive setup through Claude Desktop chat, not the terminal. See CLAUDE.md v8.0.0 banner.
- **v9.0.0 (2026-05-26)** — public-flip preparation: domain-agnostic rename (`PHIScrubber` → `DataScrubber`, `subject_id` → `entity_id`, `csv_cohort_summary` → `csv_group_summary`) with backward-compat on durable state; license Apache-2.0 → **AGPL-3.0-or-later**; reproducible token-efficiency benchmark (657×–938× per query, 318× session persistence) backing ADR 0029. See CLAUDE.md v9.0.0 banner.
- **Repo flipped private → public (2026-05-27)** — the mechanical visibility change. Ahead of the original three-condition trigger; see [§ Held items](#held-items-revisit-when-the-trigger-fires) for why the trigger is retired. **The flip is public-discovery only; the *loud* launch (coordinated channel announcements) is deliberately held** — see Phase 3.
- **Public-surface hardening (PRs #107–#136)** — five-blocker pre-flip closure (#108: CI badge, ruff, AGPL contributor licensing, ROADMAP status, notebook vocabulary); CHANGELOG back-filled v7.x→v9.0.0 (#119); README compressed + reordered for first-time visitors (#120); README/PyPI honesty pass — benchmark numbers corrected, badges reframed, README_PYPI rewritten for v9 (#125–#132); `CITATION.cff` (#109); `FUNDING.yml` sponsor button (#119); domain-agnostic issue templates (#112); social preview card (#122); tAIlor wordmark fix (#121).
- **Contribution infrastructure (#123)** — `.github/workflows/ci.yml` (ruff + pytest matrix, Python 3.10/3.11/3.12), `CONTRIBUTING_CHILD.md` (L2 child-authoring guide), `CODE_OF_CONDUCT.md`. **CI is now live (GitHub Actions re-enabled)** — the earlier "Actions disabled, merge via `gh pr merge --admin`" posture is retired.
- **Merge gate on `main` (#133 + #135 + branch protection)** — 9 required CI checks + an unattended Claude PR review (silent regressions / ADR conflicts / description-vs-diff honesty) + Gemini Code Assist as an independent second reviewer (different lens: correctness / SQLite-WAL / determinism) + a PR-template "Intent" gate. Activation of the two AI reviewers is pending app-install + OAuth-secret. Admin-merge bypass still permitted but no longer the routine path.
- **First organic external contribution** — PR #130 (Notion MCP stub from a non-maintainer) opened 2026-05-28; the public surface is already drawing strangers.

### Shipped in v7.6.0 (2026-05-19)

- **ADR 0038 structural sweep complete** — vault layer is data-source-agnostic. Closes the commitment v7.3.4 partial-closed and v7.4.0 / v7.5.0 deferred. See [Shipped in v7.6.0 banner in CLAUDE.md](CLAUDE.md) for the seven sub-item closure detail.
- **`ChildMCP.vault_note_kinds` optional property** — child-owned declaration of which vault note kinds the child contributes (default `()`). Running child is the worked example, returning `("run_report", "trend_report", "compare_runs")`. ADR 0038 § Amendment 2026-05-19 option (a) — backward-compatible by construction.
- **`VaultLayer._compute_kind_metadata()` at registration time** — `_ALLOWED_KINDS` module constant retired; replaced by `_FRAMEWORK_KIND_BASE` (framework-tier only) + instance `_allowed_kinds` unioned from registered children. Module-level `_domain_for_kind` migrates to `VaultLayer._domain_for_kind`.
- **`column → value_column` API parity** — `csv_cohort_summary` and `csv_force_decline` rename `column` to match `force_cohort_summary` / `emg_cohort_summary`. Param schema + handler + tool description + result envelope key updated. No deprecation alias under the 2026-05-19 → 2026-05-20 pre-outreach window per the v7.3.4 `group_field → group_by` precedent. Fallback if merge slips: v7.6.1 patch ships the alias.
- **`vault_get_fitness_summary` deprecation hint** — ToolDefinition description gains `DEPRECATED in v7.6.0` prefix; one-shot `log.warning` on first call per VaultLayer instance. Audit row unchanged. Named removal trigger per ADR 0038 § Amendment 2026-05-19 sub-item 7 (cue-card-zero + zero-third-party-dependency, same shape as ADR 0036 beachhead-lab pattern).
- **Internal helpers data-source-aware** — `_handle_fitness_summary` derives `strava_sync` / `strava_run_report` from `self._backfill_config` (new `sync_tool` key in `__main__.py`'s wiring) with generic fallback. `_build_snapshot_payload`'s weekly running summary query gated on `"run_report" in self._kind_to_domain_map` (closes auditor's I2).
- **AST-class invariant test** — `tests/framework/vault/test_v76_vault_is_data_source_agnostic.py` parallel to v7.5.0's `test_user_config_json_write_sites_are_canonical`. Walks `framework/vault/layer.py` AST and asserts four invariants (allowlisted `domain="running"` sites; `strava_*` literals only at backfill_config-derived sites; `_ALLOWED_KINDS` module constant gone; module-level `_domain_for_kind` gone). AST-class detection per v7.3.2 W5 lesson.
- **Behavioral contract test** — `tests/framework/vault/test_v76_vault_note_kinds_contract.py` covers default `vault_note_kinds`, RunningChild override, `_compute_kind_metadata` extension, dynamic `vault_list_notes` kind schema, one-shot deprecation log idempotency.
- **Doc fan-out** — `docs/guides/build-your-own-child.md` gains "Optional vault contribution" section naming the `vault_note_kinds` property; CLAUDE.md "Orientation & browse" table flags `vault_get_fitness_summary` as deprecated; ADR 0038 § Amendment 2026-05-19 ratified inline with B1/B2-timing/B3/I1/I4/N3 closures cited.
- **Pre-implementation gates** — `integration-auditor --proposal-mode` REVISE → PROCEED after amendment; 3 BLOCKING + 4 IMPORTANT + 3 prior-decision conflicts closed in the ADR amendment + the implementation pass.

### Shipped in v7.5.0 (2026-05-18)

- **`tailor pilot --source={csv,matlab,redcap}` argparse dispatch** — PI with mixed-modal data can configure CSV, MATLAB, and REDCap sources through the same wizard, one command per source. No-arg `tailor pilot` keeps the v6.2.1 CSV-default backward-compat behaviour.
- **F1 deep-merge `_write_user_config` with AST-class all-call-sites-sweep regression** — multi-source coexistence by construction; re-running `tailor pilot --source=matlab` after `tailor pilot --source=csv` preserves the `csv_dir` block. AST-class enforcement test at `tests/test_pilot_wizard.py::test_user_config_json_write_sites_are_canonical` closes the grep-class false-positive trap.
- **MATLAB handler** — lazy `scipy.io` import with friendly install hint and rc=1 on missing scipy (F2); HDF5 magic-byte check per file before `scipy.io.loadmat` (F6, per ADR 0036); variable inventory across first 32 parseable files drives optional `variable_filter` prompt.
- **REDCap handler** — `RedcapPHIScrubber.fingerprint` reuse (F4, no parallel canonical-form implementation drift); `utf-8-sig` BOM-safe reads per v6.9.2 precedent; full per-field identifier listing display at first config; fail-closed `unknown_field_allowlist` with explicit wizard prose (F7); `ATTEST_INITIAL` audit row via `AuditLog.record()` (NOT hand-rolled INSERT — v7.3.2 F-A precedent).
- **New `ATTEST_INITIAL` audit outcome** — distinct from `REATTEST`; threads `child_scrubber_id="redcap_metadata_flags"` and `source_metadata_fingerprint=<sha256>` so IRB reviewers can reconstruct trust-root state at first configuration. `audit_query` outcome-filter description updated with `ATTEST_INITIAL` in common-values list.
- **L1/L2 onboarding-surface split codified** — new `docs/guides/build-your-own-child.md` (RSE-shaped L2 path: copy → rename → four abstract surfaces → register); CLAUDE.md § "Adding a New ChildMCP" gains L1/L2 split paragraphs + ADR 0022 conductor-mode argument as load-bearing WHY against wizard-child MCP surface and LocalLLMLayer-folded wizard alternatives.
- **ADR 0001 § Amendment 2026-05-18** — CLI-helper audit-row exemption: narrow five-precondition carve-out for operator-action provenance rows (CLI subcommand helper; provenance-only row; primary purpose is something else; operator-reachable recovery; stderr surface on failure). Closes WATCH-3.
- **23 net new pytest tests in `test_pilot_wizard.py`** — F1 multi-source helper + dispatch + MATLAB scipy-missing / HDF5 magic-byte / scan partition + REDCap fingerprint reuse / ATTEST_INITIAL audit row / completion-field detection / BOM round-trip + AST-class all-call-sites-sweep.
- **16 net new pytest tests in `test_serve_v750_wire_audit.py`** — 15 from mcp-protocol-auditor side-effect (B1–B6) + 1 B7 red-team OBJECTION closure (`TestB7PilotWriteAttestInitialEndToEnd` asserts `scrubber_id == PHIScrubber().scrubber_id` dynamically).
- **Documentation** — `docs/guides/multi-subject-pilot.md` § "Source axes"; `README.md` pilot wizard table + install-command block; `__main__.py` pilot summary line updated for multi-source dispatch.

### Shipped in v7.4.0 (2026-05-16)

- **New `audit_query` MCP tool** — closes the v7.3.4 audit-log-over-promise gap (the fitting-room banner prompt "Show me what just happened in the audit log" now has an MCP tool to land on). The audit log is now LLM-queryable under a B1 column allowlist (12 columns + 1 derived `has_error`); raw `params` and raw `error` content never egress. `AuditLog.query()` uses explicit `SELECT`, never `SELECT *`, with `limit=100` hard cap.
- **ADR 0039 (NEW, Accepted)** — "audit log is LLM-queryable under column allowlist"; codifies the B1 allowlist construction argument and the bypass-design rationale for `AuditQueryLayer` as a fourth framework-tier layer. Cites ADRs 0001 / 0002 / 0003 / 0009 / 0012 / 0022.
- **ADR 0012 § Amendment v7.4.0** — fourth framework-tier bypass entry for `AuditQueryLayer`.
- Net-new tests: 42 (32 unit + 10 subprocess wire). Tool surface: 49 → 50. Minor bump.
- Gates: ci-gate-runner SHIPPABLE (1360/1360 pytest, ruff clean, 76/76 probe, CLI smoke). mcp-protocol-auditor PROTOCOL OK. integration-auditor REVISE (pre-implementation) → all BLOCKING + IMPORTANT closed before code. adr-weigher PASS. red-team-reviewer NO OBJECTION FOUND.

### Shipped in v7.3.4 (2026-05-16)

Phase 2 first-time-user setup pass — first end-to-end pass. The 2026-05-16 first real outside-recipient walkthrough (Windows + Claude Desktop, non-technical friend) produced 5 findings that drove four scope-shape escalations over the session: narrow S004 fix → beachhead-lab-ready expansion → γ scope-box (meeting flexes, ship-quality binds) → Option B (AI-economics demonstration). Three pre-implementation gates returned non-PASS verdicts; every ship-blocker closed before any code was written. Closes the Phase 2 first-time-user setup pass deliverable first opened at v7.0.13's PyPI publish (2026-05-13) and unblocked at the Phase 0 closure (2026-05-12).

- **Cohort thesis hot path (D1 + D1-companion).** `_extract_timestamps` in `force_csv/child.py` + `emg_csv/child.py` gains float-seconds fallback for bundled demo cohort 100 Hz fixtures. Wire-verified: F=65.3 N / M=87.6 N mean; S004 peak=229 N / `time_to_50pct_drop_s` non-null. Handler key-mismatch (`decline_pct` vs `decline_pct_total`) closed in the same pass; S004 `decline_pct=76.1%`.
- **API parity (D2).** `force_cohort_summary` + `emg_cohort_summary` parameter renamed `group_field` → `group_by` across ToolDefinition, param_schema, handler, and result-dict key. `value_column` ↔ `column` asymmetry deferred to v7.4.0 (wider refactor).
- **Vault layer de-Strava — F3 closure.** `_handle_fitness_summary` + `renderer.py` conditional Weekly Summary section + `_infer_note_type` maps `snapshot.md` → `"snapshot"` kind + `_ALLOWED_KINDS` updated. Vault layer is now data-source-agnostic on the demo hot path — structural invariant codified in ADR 0038 Proposed.
- **Bundled `snapshot.md` fixture.** Pre-seeded orientation document ships in the wheel under `_fixtures/cohort_demo_realistic/vault/`. Includes "## Token cost shape" with wire-audit-verified tier numbers (Tier 1 ~310 tokens · Tier 2 ~6,750 · Tier 3 ~50,000 actual / ~24,000 pre-execution estimate). ADR 0024 synthetic-by-construction precondition honored.
- **Option B — AI-economics demonstration (ADR 0029).** `cost_threshold` operator-configurable from `user_config.json` (default `35_000` preserved; backwards-compatible). `tailor fitting-room` scaffold writes `cost_threshold: 15000` so the cost gate fires demonstrably on bundled fixtures. Fifth banner prompt + "## Token cost shape" section in `snapshot.md` ground the AI-economics claim in audit-verified numbers. Cost-estimator 2.1× under-estimate queued for v7.4.0 calibration.
- **Schema description sweeps (D5, D6, D7).** `value_column`, `group_by`, and `SUBJECT_ID_PARAM_DOC` descriptions gain literal examples and semantic distinctions (biosensor-tier audit-only vs vault-tier filter per ADR 0009).
- **Recipient ergonomics.** README per-OS uv install one-liner table. Fitting-room banner reshaped: single "Next step" leads, three science-shaped prompts, paths demoted to labeled "Files & locations" block. Regenerate-warning added per F3 structural lesson.
- **[ADR 0038](docs/adr/0038-vault-layer-is-data-source-agnostic.md) (NEW, Proposed)** codifies "vault layer is data-source-agnostic" structural invariant. v7.3.4 ships partial closure (demo hot path); v7.4.0 ships the full sweep. ADR 0027 gains forward-cite footer.
- **21 net-new tests** (1297 prior → 1318 total) in `tests/test_v734_demo_readiness.py` — regression tests for all D1/D2/D5/D6/D7/F1/F3 closures.
- **Release-pass gates:** ci-gate SHIPPABLE (1318/1318 pytest, 3 scipy-conditional skips, ruff clean, 76/76 probe, CLI smoke). mcp-protocol-auditor PROTOCOL OK (120/120 wire tests). reproducibility-provenance-auditor CLEAN. vault-smoke-validator SHIPPABLE. phi-irb-risk-reviewer NO RISK all 6 lenses. researcher-utility-reviewer ALIGNED (PI LOAD-BEARING HIGH). coverage-criticality-mapper REGRESSION → CLOSED. red-team-reviewer OBJECTION (medium) → CLOSED (audit-log over-promise banner reword).

### Shipped in v7.3.3 (2026-05-15)

Closes the two red-team BORDER NOTES the v7.3.2 banner explicitly deferred — both addressed under a single structural argument (typed-exception taxonomy) rather than two point-fixes.

- **[ADR 0003 § Amendment 2026-05-15 § Typed-exception taxonomy](docs/adr/0003-phi-scrubber-seam.md) (NEW)** ratifies the contract. Marker class `framework.security.OperatorActionRequired(Exception)` co-located with `CircuitBreaker` (the component whose behavior it modifies). Constructor takes a keyword-only `recovery_action: str` argument validated as non-empty at construction time — the required attribute is the *misuse guard*: a child author who marks an upstream-flaky exception as `OperatorActionRequired` (defeating the breaker for paths that legitimately need it) either provides a sensible remediation command or cannot construct the exception at all. Reversal condition named — `OperatorActionRequired` vs `OperatorActionRequiredTransient` split if a future child needs a transient-state variant that should trip a breaker.
- **Router exemption — both dispatch sites (B1 closure).** `isinstance(e, OperatorActionRequired)` check at `framework/router.py` `_dispatch` exception handler AND `dispatch_internal` exception handler. The audit row still records `outcome=ERROR` / `outcome=ERROR_INTERNAL` with the v7.3.1 W5 invariant kwargs (`subject_id`, `scrubber_id`, `child_scrubber_id`, `source_metadata_fingerprint`). Exemption is breaker-only, not audit-only. Proposal-mode audit caught a critical defect in the initial plan that named only the public dispatch site — a future cross-child REDCap call (oracle tool, vault backfill path) would have tripped the breaker through the internal path while the public path left it closed.
- **`RedcapMetadataFingerprintMismatch` reparented to `OperatorActionRequired`** with `recovery_action="tailor redcap reattest"`. v7.3.2 invariants preserved verbatim (both fingerprints in `str(exc)`, no absolute on-disk path, "ADR 0003" citation present).
- **B2 closure — drop the defensive try/except entirely in `children/redcap/child.py:_detect_fingerprint_mismatch`.** Proposal-mode audit caught a load-bearing reality check: the initial plan proposed to narrow `except Exception` to `(OSError, ValueError, UnicodeDecodeError, csv.Error)`, but `RedcapPHIScrubber._load_metadata` already swallows exactly those classes internally and returns instead of raising. The proposed narrowing would have been a no-op against current behavior; the only exception class it would have caught was `TypeError` from a future signature change — which is precisely the class that must propagate. The shipped fix drops the try/except entirely; future programmer errors propagate through the router's exception handler rather than silently disabling mismatch detection.
- **31 net new tests** (1266 prior → 1297 total): 16 in new `tests/framework/test_v733_operator_action_required.py` covering T1 marker-class construction contract (6), T2 public-dispatch exemption (2), T3 internal-dispatch exemption parity (1), T4 audit-row provenance on exempt path (1), T5 RuntimeError-still-trips-breaker regression guard (1), T6 REDCap mismatch inheritance contract lock (2), T7 AST contract on `_detect_fingerprint_mismatch` (no bare `except Exception`, locks B2 fix posture; closes phi-irb-risk-reviewer BORDER NOTE) (1), T8 stderr-byte-budget invariant on the OperatorActionRequired path (2, closes the red-team-reviewer F-G OBJECTION); 14 in `tests/test_serve_v733_wire_audit.py` (added by mcp-protocol-auditor as audit side effect, parallel to v7.3.2's pattern — B1 5-call wire sequence, B2 audit-DB-shape, B3 initialize handshake, B4 OperatorActionRequired constructor guard, B5 W5 AST invariant unchanged); 1 in `tests/children/redcap/test_redcap_shape.py` (`test_signature_change_in_scrubber_propagates_loudly` simulates future signature change via monkey-patch, asserts TypeError propagates rather than being absorbed).
- **Proposal-mode audit returned REVISE on the initial plan — 2 BLOCKING + 4 IMPORTANT closed pre-implementation.** B1 (dual-dispatch-site miss). B2 (no-op narrowing). I1 (marker-class placement: `framework/security.py` adjacent to `CircuitBreaker` for semantic honesty vs initial-plan `framework/interfaces.py`). I2 (three missing audit-invariant test cases — exempt-path outcome stamp + W5 kwarg threading + consent-revocation orthogonality named in ADR). I3 (`outcome="ERROR_INTERNAL"` shape covered in T3). I4 (semantics named in amendment: breaker exemption is per-exception-instance; consent state orthogonal; subject_id propagation unchanged).
- **Most-likely-misbehaviour-path adopted into the design** — the required `recovery_action` attribute makes future misclassification a *loud constructor error* rather than a *silent runtime defeat*. Same shape as v7.3.2's W5 AST-class contract test replacing the grep-class one: turn structural failure modes into compile/construct-time errors rather than runtime drift.
- **Red-team-reviewer caught a fifth defect all four upstream specialists missed (F-G closure pre-ship).** Adversarial pairing on the four upstream confident verdicts returned **OBJECTION (medium)**: the B1 wire test passed because the test harness runs a background daemon thread (`_start_stderr_drain`) that actively drains the server's stderr; production (Claude Desktop) does not run such a thread; after ~8 OperatorActionRequired events the Windows OS pipe buffer (4KB) fills with `log.info` lines, the server stalls on its next write, stdin blocks, and the recovery affordance disappears — the exact failure class v7.3.3 was meant to close, reachable by a different path. Same structural shape as v7.3.2's W5 grep-vs-AST catch. **F-G fix**: silence the router's logger output entirely for `OperatorActionRequired` at both exception handlers — audit row + wire envelope already carry the full event + recovery hint. Removing the byte source eliminates the failure mode rather than reducing its severity (structurally stronger than the earlier "log.info instead of log.error + exc_info" mitigation). Two T8 regression tests lock the closure (10-call zero-log-records assertion + RuntimeError-still-logs guard).
- No public API breaks; no router-pipeline / security-pipeline / vault-layer / CLI architecture changes beyond the additive marker class, the symmetric isinstance check at the two exception handlers, and the silenced logger output on the exempt path. Patch bump per v7.3.1 / v7.3.2 precedent.

### Shipped in v7.3.2 (2026-05-15)

Closes the two remaining v7.3.0 WATCH findings deferred from v7.3.1: (a) `project_metadata.csv` trust-root attestation seam and (c) small-cell suppression posture for aggregate count surfaces.

- **[ADR 0003 § Amendment 2026-05-15](docs/adr/0003-phi-scrubber-seam.md) (NEW)** ratifies both seams. Lands inside ADR 0003 (not 0037) because the trust-root fingerprint primitive generalises across children — a future EDF / FHIR / vendor-sensor metadata input inherits it. Reversal condition named — promotion to a `ChildMCP` abstract method + framework registry on the third domain that wants the seam, matching ADR 0013's precedent.
- **Trust-root fingerprint primitive** — `RedcapPHIScrubber.fingerprint` computes SHA-256 over a canonical-form rendering of sorted `(field_name, identifier_flag)` tuples at scrubber construction. The canonical-form distinction is load-bearing: Excel/PowerShell BOM/CRLF/whitespace round-trips do NOT trip; flag flips and field additions/removals DO. Empty-state (missing metadata) produces a deterministic fingerprint over the empty string. `canonical_state` property exposes the sorted view for the reattest CLI.
- **`audit_log.source_metadata_fingerprint TEXT` column + `idx_audit_source_metadata_fingerprint` index** — domain-agnostic naming (not `project_metadata_fingerprint`) so future EDF / FHIR / vendor-sensor children inherit the seam without column renames. `ALTER TABLE` migration on legacy audit DBs, same pattern as v7.3.0's `child_scrubber_id` migration.
- **Threaded across 19 audit-call sites + 5 `_meta` blocks** in `framework/router.py` (`_dispatch` × 8, `dispatch_internal` × 8, 3 consent handlers). REDCap dispatch paths thread `child.child_source_metadata_fingerprint`; vault / local_llm / setup_help paths set `None` per the all-call-sites-sweep rule from v7.3.1. New `ChildMCP.child_source_metadata_fingerprint` interface property (default `None`) — `RedcapFileChild` overrides; no breaking change for csv_dir / matlab_file / running / template.
- **`RedcapFileChild` fingerprint-mismatch detection at `execute()`** — re-reads `project_metadata.csv` on every call, compares against the scrubber's cached fingerprint; on drift returns typed `REDCAP_METADATA_FINGERPRINT_MISMATCH` error envelope. Forward-only policy: consent stays granted, no auto cache-purge (the framework cannot un-send bytes already returned). Error envelope points operator at `tailor redcap reattest` for recovery; absolute paths are not leaked.
- **New `tailor redcap reattest` CLI subcommand** — prints cached fingerprint, new fingerprint, and a sorted field-by-field listing of the current trust-root state with each field's identifier flag. On `y`, writes a `REATTEST` audit row carrying the new fingerprint. Operator must restart `tailor serve` for the running server to load the new attestation. Same-fingerprint short-circuits with exit 0 and no prompt. Error paths cover missing user_config.json / missing `redcap_file` block / missing project_metadata.csv with rc=1.
- **`RedcapProcessing.apply_small_cell_suppression_to_top_values` + `apply_small_cell_suppression_to_groups`** static helpers (per ADR 0008 `@staticmethod` invariant). Below-threshold entries collapse into one aggregate entry shaped `{value: "<small_cell_suppressed>", count: "<below_threshold>", suppressed_count: K}` for top_values and `{n: "<below_threshold>", suppressed_group_count: K}` for groups. Applied to BOTH `redcap_summary_report` `top_values` AND `redcap_cohort_summary` `groups` per the auditor's F4 finding (cohort group-count is the higher-leverage re-identification surface). Default k=5 (HHS SDL baseline); configurable via `redcap_file.small_cell_suppression_threshold`; validated `>= 2` at config-load time so k=1 is refused with `ValueError` rather than silently disabling suppression.
- **`small_cell_suppression_threshold` + `small_cell_warning` envelope fields** — surfaced at the top level of every result envelope where suppression was applied. Warning fires when the framework default is in force rather than an explicit operator setting (parallels v6.3.1's `scrubber_warning` pattern). Studies with elevated re-identification risk (pediatric, mental health, rare-disease) opt up to k=10/k=11 via user_config.json.
- **49 net new tests** (1187 prior → 1236 total): 21 fingerprint / canonical-state scrubber tests (canonical-form invariant under BOM/CRLF/row-reorder, sensitivity to flag flip + field addition/removal, allowlist exclusion from fingerprint, empty-state determinism); 13 small-cell processing tests (helpers on both surfaces, threshold boundaries, defensive non-int counts); 12 mismatch + handler shape tests (mismatch on every tool, no path leakage in error envelope, deleted-metadata is NOT mismatch, k=1 config rejected, default-warning surface); 12 reattest CLI tests (audit row written on confirm, none on abort, listing shows flag state, fingerprints printed, no-prior-attestation framing, same-fingerprint short-circuit, three error paths, subcommand dispatch).
- **Proposal-mode audit caught 3 BLOCKING + 3 IMPORTANT pre-implementation.** F1 (consent-time-only fingerprint stamping would leave Tier-1 unanchored — Tier-1 REDCap is not consent-gated per ADR 0037) → resolved as boot-time stamping (D1). F2 (`_meta` threading across all 5 sites) → addressed by domain-conditional value. F3 (raw-byte hash false-positives on Excel BOM) → addressed by canonical-form sorted tuples (D5). C1 (auto-revoke vs forward-only on mismatch) → resolved as forward-only (D2). C2 (REDCap-specific vs domain-agnostic column name) → resolved as `source_metadata_fingerprint` + ADR 0003 § Amendment placement (D4). C3 (k=5 default vs required-config) → resolved as default-with-warning (D7).
- Patch bump per v7.3.1 precedent — additive `_meta` fields + additive audit column + new failure-class error envelope + additive CLI subcommand. No public API breaks; no router / security / cost-gate architectural changes beyond the additive column and the additive interface property.

**Release-pass fix cascade — 2 VIOLATIONs + 2 WATCH findings closed pre-merge:**

- **(F-A VIOLATION)** `phi-irb-risk-reviewer` + `reproducibility-provenance-auditor` independently flagged `cmd_redcap_reattest` hand-rolling a raw `sqlite3.INSERT` into `audit_log` instead of calling `AuditLog.record()` — left `scrubber_id` NULL on the REATTEST row, breaking ADR 0003's "scrubber_id turns 'did we scrub?' into a fact on disk" invariant. The v7.3.1 all-call-sites-sweep rule fired on router sites but didn't cover CLI hand-rolled INSERTs. Rewrote to use `AuditLog.record()`; inherits full schema + migration logic + `scrubber_id="noop"` default. Same defect class as v7.3.0 banner-claim falsification 1 — caught structurally rather than by post-ship inspection.
- **(F-B VIOLATION)** Mismatch path was returning a dict-with-error-key from `RedcapFileChild.execute()` instead of raising. Router's exception handler never fired, so audit row was stamped `outcome="SUCCESS"` with boot-time fingerprint while the on-disk fingerprint lived only in the wire transcript. ADR 0003 § Amendment 2026-05-15's promise "the audit log carries both fingerprints" was unhonored as shipped. Switched to raising new `RedcapMetadataFingerprintMismatch` typed exception with both fingerprints as attributes and in `str(exc)`; router's existing handler records `outcome=ERROR` with the error column queryable via `WHERE error LIKE 'REDCAP_METADATA_FINGERPRINT_MISMATCH:%'`.
- **(F-C WATCH)** Small-cell suppression was applied to `top_values` + cohort `groups` but `completion_counts` (the third aggregate count surface, `{instrument: count}`) was left unsuppressed. Added `RedcapProcessing.apply_small_cell_suppression_to_completion_counts` static helper + wired into `_handle_summary_report`. Replaces below-threshold counts with the `"<below_threshold>"` sentinel while preserving the instrument-name key (structural metadata, not a participant identifier).
- **(F-D WATCH)** Added a 4th retention-category paragraph to `docs/design/research-framing.md` naming trust-root attestation rows alongside biometric cache, analyst notes, and oracle audit rows. IRB submissions citing Tailor against a REDCap protocol now have doc text to point at for the mismatch-disclosure question.
- New `RedcapMetadataFingerprintMismatch` exception class exported from `tailor.children.redcap`; 30 fix-pass tests added (1187 prior + 79 net new = 1266 total). 1 router-side test verifies mismatch lands as `outcome=ERROR_INTERNAL` with both fingerprints in the error column. CLI reattest test strengthened to assert `scrubber_id == "noop"` (closing the NULL-on-REATTEST defect by test).

**Red-team-reviewer caught a fifth defect all four upstream specialists missed (F-E + F-F closure):**

- **(F-E + F-F MEDIUM OBJECTION)** The first-pass "28/0 audit-record-site invariant closure" claim was factually wrong — actual count was 26/2 (vault SUCCESS at `router.py:803` + setup_help SUCCESS at `router.py:1092` lacked the explicit `source_metadata_fingerprint=` kwarg). The W5 contract test was passing for the wrong reason: its 25-line textual-window scan was picking up the field name out of the adjacent `_meta` block dict literal that follows each dispatch path's SUCCESS audit. Behaviorally the wire and DB were unaffected (`AuditLog.record()` defaults the kwarg to None) but the v7.3.1 banner's all-call-sites-sweep rule had a structural teeth-gap exactly where v7.3.2 claimed it had teeth. **F-E** adds explicit kwargs at the two missed sites. **F-F** rewrites W5 with AST-based detection — `ast.walk` finds every `self._audit.record()` call node, inspects ONLY its `node.keywords` list, cannot be fooled by textual adjacency. W5 enforcement class is now AST-class rather than grep-class — strictly stronger than the v7.3.1 banner mandated. This is the ADR 0010 (adversarial pairing) earning-its-keep moment: the dissent layer caught the failure mode that all four confirmation-shaped specialists missed.
- **Red-team BORDER NOTES recorded for v7.3.3:**
  - Circuit-breaker interaction with mismatch failures (3 mismatches in 300s trips the circuit; LLM loses recovery-hint visibility for 5 min). Not exercised by any test.
  - Blanket `except Exception: return None` in `_detect_fingerprint_mismatch` swallows every exception from `RedcapPHIScrubber.__init__` — could silently disable mismatch detection under a future refactor.
- Total tests after F-E + F-F: 1266/1266 (no test count change — F-E and F-F are surgical kwarg additions + an AST rewrite of the existing W5 test).

### Shipped in v7.3.1 (2026-05-15)

- **Commit 1/8 — `child_scrubber_id` threaded into consent-handler audit rows** (`framework/router.py:1281, 1334, 1359, 1395, 1401`): 5 missed sites from the v7.3.0 banner claim; VIOLATION-class (banner-claim falsification 1). 5 new unit tests + wire-side verifier `TestW3ConsentAuditRowsThreadChildScrubberId`.
- **Commit 2/8 — `child_scrubber_id` surfaced in `_meta` across 4 dispatch sites** (child dispatch:711, vault layer:801, local_llm layer:986, dispatch_internal:1240); WATCH (b) closure from v7.3.0 banner.
- **Commit 3/8 — PHI Safe Harbor path-placeholder surface reduction** (`redcap/child.py` 11 sites + `redcap/scrubber.py` 3 sites): raw filesystem paths → `<configured_redcap_path>` placeholders in LLM transcript + audit error column; full paths retained in stderr `log.warning` only. HIPAA Safe Harbor §164.514(b)(2)(i)(B + R).
- **Commit 4/8 — REDCap registration guard** (`__main__.py`): try/except wrapper mirrors matlab pattern; malformed `redcap_file` config no longer aborts `tailor serve` rc=1; VIOLATION-class (banner-claim falsification 2). Subprocess regression test + wire-side `TestW4MisconfiguredRedcapBoots`.
- **Commit 5/8 — `setup_help/__init__.py:221` typo fix** `"redcap_export"` → `"redcap_file"`: inverse-v6.10.2 trap where SetupHelpLayer was firing on working REDCap deployments. HIGH severity.
- **Commit 6/8 — 18 v7.3.1 wire-level regression tests** in `tests/test_serve_v731_wire_audit.py`: W1 (audit row schema), W2 (child_scrubber_id non-null), W3 (consent audit threading), W4 (misconfigured REDCap boots), W5 (path placeholder in error), W6 (child_scrubber_id in _meta).
- **Commit 7/8 — `setup_help` `_meta` site (5/5) + `RedcapPHIScrubber._load_metadata` 3 failure-mode tests + REDCap vault-writer registration**: setup_help site discovered by boss-report-auditor G8 while auditing the v7.3.1 banner draft; concrete evidence option-2 structural closure works. REDCap child added to vault writer `_registered` list closing BORDER NOTE asymmetry.
- **Commit 8/8 — phi-irb-risk-reviewer prompt extended with Step 1.5 all-call-sites sweep rule**: structural gate-composition gap closure (option 2). When a diff adds a new `audit_log` column, `_meta` field, `ChildMCP` property, or other shared-invariant change, auditor must grep every existing call site and verify each untouched site either correctly inherits the default or threads the new value. Reversal condition named.

**Deferred to v7.3.2:**
- PHI WATCH items 1–8 (project_metadata.csv trust-root hash-stamp; small-cell suppression threshold for redcap_summary_report top_values; consent-handler audit `child_scrubber_id` back-fill migration for pre-v7.3.1 audit DBs; redcap_cohort_summary group-key cardinality suppression; redcap_records instrument boundary enforcement test; ADR 0037 retention-category documentation; redcap_raw_records cost-gate calibration)
- Doc-truth items (ROADMAP at-a-glance table REDCap row; README source-agnostic claim update for v7.3.1 fixes)
- Coverage debt (dispatch_internal error-path coverage; setup_help _meta site coverage; RedcapPHIScrubber edge-case coverage)
- Integration [S3] finding (redcap_cohort_summary cross-event grouping ambiguity)
- Reproducibility NEEDS REVIEW items (redcap_processing stateless verification; scrubber determinism attestation)

### Shipped in v7.3.0 (2026-05-14)

- **New `src/tailor/children/redcap/` package — `RedcapFileChild`** (Move 3 / Part 2 per [ADR 0037](docs/adr/0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md)) exposes six tools across all three tiers, matching the csv_dir / matlab_file shape: `redcap_list_records`, `redcap_record_detail`, `redcap_summary_report`, `redcap_cohort_summary` (Tier 1); `redcap_records` (Tier 2 — `instrument` is a required parameter per the R2 ratified decision, not optional); `redcap_raw_records` (Tier 3). Cohort surface ships in v1 using the ADR 0015 `metadata.json` sidecar pattern unchanged. Opt-in via `redcap_file` block in `user_config.json`; default deployments behaviourally unchanged. Stdlib-only — no new optional extras (contrast with v7.2.0's `[matlab]` extra); lean three-dep base install posture preserved.
- **Three demonstrated source-axis shapes ship in the framework** — CSV (csv_dir, v6.5.0+) / MATLAB (matlab_file, v7.2.0) / REDCap (redcap, v7.3.0).
- **New [ADR 0037](docs/adr/0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md)** — codifies REDCap CSV-export-directory-only scope; live REDCap REST API support deferred behind a future superseding ADR with named reversal condition (first real-world deployment target identifies live-API as the load-bearing path). Same scope-bound posture as ADR 0036's HDF5 deferral.
- **[ADR 0003 § Amendment 2026-05-14](docs/adr/0003-phi-scrubber-seam.md) — child-level PHI scrubber seam** parallel to the framework-level seam. `RedcapPHIScrubber` reads per-field `identifier` flags from `project_metadata.csv` and scrubs flagged fields inside `RedcapFileChild.execute()` before the result returns to the framework-level seam. The identifier flags structurally answer the question ADR 0003 declined to answer generically — *which fields are PHI?* — for this source axis.
- **New `audit_log.child_scrubber_id` column** — records the child's internal scrubber identity (`"redcap_metadata_flags"` for REDCap; NULL for csv_dir / matlab_file / running which inherit the ABC default). Threaded on every child-related audit row per the existing `scrubber_id` stamping convention; legacy audit DBs migrate via `ALTER TABLE`.
- **Bundled fix pass closed 2 HIGH PHI/IRB VIOLATIONs + 1 red-team coverage OBJECTION pre-ship** — `phi-irb-risk-reviewer` caught (a) cohort guards using `is_known_identifier` (returns `False` for unknown fields, bypassing the fail-closed defense ADR 0037 codified), fixed by predicate swap to `is_identifier`; (b) failure rows leaving `child_scrubber_id` NULL on the dispatch path, fixed by stamping at row-construction time. `red-team-reviewer` caught coverage gap on audit-row threading + legacy-DB migration, closed by 3 new tests. All landed in a single bundled fix pass before this version shipped. [ADR 0010](docs/adr/0010-adversarial-pairing.md) (adversarial pairing) is the structural reason the gate caught these pre-ship.
- **3 WATCH findings deferred to v7.3.1** (institutional-clarification, not VIOLATIONs): `project_metadata.csv` tampering hash; `_meta` block carries `child_scrubber_id`; `top_values` disclosure on permissively-allowlisted low-cardinality fields.

### Shipped in v7.2.0 (2026-05-14)

- **New `src/tailor/children/matlab_file/` package — `MATLABFileChild`** exposes six tools across all three tiers, matching the csv_dir shape: `matlab_list_files`, `matlab_file_detail`, `matlab_summary_report`, `matlab_cohort_summary` (Tier 1); `matlab_downsampled` (Tier 2); `matlab_raw_array` (Tier 3). Cohort surface ships in v1 (not deferred) using the ADR 0015 `metadata.json` sidecar pattern unchanged. Opt-in via `matlab_file` block in `user_config.json`; default deployments behaviourally unchanged.
- **New [ADR 0036](docs/adr/0036-matlab-child-scope-v72-only-with-deferred-hdf5.md)** — codifies `.mat` v5/v6/v7.2-only scope via `scipy` as an optional extra (`pip install tailor-mcp[matlab]`); v7.3 HDF5-based `.mat` detected by magic bytes and rejected with a typed-error envelope citing the ADR. Reversal condition: first beachhead lab hits the v7.3 gap.
- **Move 3 / Part 1 closed** — MATLAB child is the second non-CSV source axis demonstrated by the v7.1.1 source-agnostic claim. Move 3 / Part 2 (REDCap existence-proof child) held for v7.3.0 fresh-session build; REDCap PHI-defense posture ratified in memory.
- **Deprecation-removal target for `tailor tour` / `tailor demo` aliases bumped** from v7.2.0 to a future minor (v7.2.0 scope was re-aimed at Move 3 / MATLAB child; CLI cleanup is unrelated work).

### Shipped in v7.1.1 (2026-05-14)

- **Source-agnostic positioning (Move 1 of 3)** — `README.md` hero and `README_PYPI.md` intro gain a parallel bold-led clause naming the source-agnostic axis (`ChildMCP` extension point; REDCap / EDF / FHIR / vendor sensor exports as held-item examples; 10-100× cost-per-question tie-back). Closes the cold-landing messaging gap where a reader sees CSV fixtures + Strava and concludes Tailor is a CSV tool. AI-economics slots 1+2 preserved at parity. `integration-auditor --proposal-mode` REVISE → resolved (3 IMPORTANT findings addressed pre-edit). Workshop-vs-lifestyle invariant per ADR 0033 + ADR 0035 Table 5 verified clean.

### Shipped in v7.1.0 (2026-05-14)

- **CLI rename: `tailor demo` → `tailor walkthrough`, `tailor tour` → `tailor fitting-room`** — recipient-experience-shaped verbs replacing the internal-framing names. One-cycle deprecation shims preserve the old verbs with stderr hints; removed in v7.2.0. New `tailor fitting-room` heads-up prompts recipient to quit Claude Desktop before MCP config write. Default `--save-shareable` filename updated to `shareable-walkthrough-vX.Y.Z.md`.
- **ADR 0035** (NEW, ~370 lines) — codifies the CLI rename, recipient-experience-shaped naming principle, recipient-evaluation-class scope, operator-class grandfathered list, and the vocab-doc update mandate. Amends ADR 0024, ADR 0026, ADR 0027 (CLI verb name only; substance retained).
- **`docs/design/tailor-vocabulary.md`** — `closet` added to always-forbidden (Table 5); `Fitting` removed from weak beats (promoted to CLI name); new "Recipient-facing surfaces" section.
- **Structural**: `src/tailor/tour.py` → `src/tailor/fitting_room.py` via `git mv`; one-line re-export shim for backwards compatibility until v7.2.0. Server-name `tailor-tour-{variant}` → `tailor-fitting-room-{variant}`. Setup_help dict fields renamed. `tests/test_tour_subcommand.py` → `tests/test_fitting_room_subcommand.py`; NEW `tests/test_cli_deprecation_hints.py`; 22+ assertion sites updated.
- **Phase 2 deliverable reshaped**: "First-time-user setup pass" row updated to reference `tailor walkthrough` (new canonical verb).

### Shipped in v7.0.13 (2026-05-13)

- **PyPI publish** — `tailor-mcp` live at pypi.org/project/tailor-mcp/7.0.13/; canonical install is `uv tool install tailor-mcp`. GitHub Pages landing page at saahasmuthineni.github.io/tailor-mcp-landing. Repo public-flip deferred under three-condition trigger. `README_PYPI.md` authored for PyPI rendering; ADR 0030 URL allowlist tightened via Amendment 2026-05-13; demo runner install-URL emission swapped to PyPI commands. PEP 639 license migration. Bundled-fixture citation softened to literature-form.

### Shipped in v7.0.12 (2026-05-12)

- **Phase 2 pre-flip doc-truth sweep** — reversible half of the PyPI publish + repo public-flip pair. Governed by `integration-auditor --proposal-mode` REVISE (10 findings). Deleted `install.ps1` + `install.sh` (zombie legacy curl-pipe scripts; `uv tool install` is the post-Phase-0 path). Fixed stale `biosensor-to-llm-middleware` URLs in `.github/SECURITY.md`, `CONTRIBUTING.md`, and ADRs 0002/0003. Scrubbed hardcoded boss-machine paths in `docs/diagnosis/phase-0-diagnosis-kit.md`. Updated `WINDOWS_QUICKSTART.md` install framing from Python + pip to uv + `uv tool install`. Re-pointed `runner.py` default `install_url_base` from archived mirror to `tailor-mcp` Releases per [ADR 0032](docs/adr/0032-retire-public-mirror-distribution-path.md). Removed CI badge from README (Actions disabled). Added synthetic-by-construction callout per ADR 0024. Updated ROADMAP Phase 2 `vocabulary-drift-auditor` § Killed entry.
- **Four boss-decisions ratified**: D1 (v7.0.12/v7.0.13 split); D2 (delete install scripts, not rewrite); D3 (CONTRIBUTING.md tone = Phase-3 debt); D4 (CI badge remove).

### Shipped in v7.0.11 (2026-05-12)

- **AI economics restored as top-billed framing** — [ADR 0029](docs/adr/0029-token-reduction-as-analytical-quality.md) amended (2026-05-12) to name **AI economics** as the umbrella claim with three faces: analytical quality, cognitive amplification, and cost-per-question. The three are the same architectural lever — structured answers instead of raw streams. Reversal condition named explicitly (two independent benchmarks showing comparable frontier-model performance on raw-stream vs. structured-summary context at sub-10k-token loads).
- **CLAUDE.md § "Problems this is built against" gains 4th entry** — "AI economics" added as Problem 4 citing ADR 0029 (Amended). The "Token efficiency is a useful side effect… not the headline" demotion sentence (introduced in the v6.12.0 banner) deleted. The demotion was a doc-drift downstream of what ADR 0029 actually decided.
- **README hero clause updated** — Bold lead ends with "…and turns a $200/month AI bill into a $2/month one while making the AI materially better at your question." New bold sentence explains the mechanism: structured answers → context goes to reasoning over the question, prior work, audit trail, not data-parsing.
- **demo runner.py Section 3 + closing summary sharpened** — "analytical quality, not just billing" / "Tier 1 wins on analytical quality, not just on cost" → "analytical quality AND AI economics (cost-per-question and context-per-question are the same lever)". Prose-only changes inside `print()` calls; no logic changes.
- Gates: ci-gate-runner SHIPPABLE (946/946 pytest, ruff clean, 76/76 probe, CLI smoke clean). mcp-protocol-auditor NOT TRIGGERED. cue-card-rehearsal-auditor NOT TRIGGERED. recipient-install-validator SKIPPED (runner.py in trigger globs but edit is print()-call prose only; v6.11.x falsification grounds the opt-in skip).

### Shipped in v7.0.10 (2026-05-12)

- **README install-path framing aligned with Phase 0 closure** — Six framing callouts and table rows that described Phase 0 as active and no outside install as succeeded are updated to reflect the 2026-05-12 macOS outside-recipient install ratified by v7.0.8. The install commands themselves (`uv tool install git+...tailor-mcp.git` + `tailor tour`) were already correct post-rename; the stale framing was the editorial claim around them.
- **ROADMAP preamble + Phase 0 section body swept** — In-scope expansion after release-shipper's BORDER NOTE flagged that v7.0.8's status-flip pass had touched the at-a-glance table and the Phase 0 header but missed two stale present-tense blocks: the preamble at lines 18-26 (*"Phase 0 is the binding constraint … has been successfully installed"*) and the Phase 0 section opener at lines 73-89 (*"Empirically, no version of Tailor … has ever been"*). Both repeated the same defect: present-tense assertions of pre-2026-05-12 state. Both rewritten as past-tense historical framing with a closure callout at the top of the Phase 0 section. The pre-closure prose is retained as historical record (the v6.x → v7.x install-failure narrative is load-bearing context); the present-tense claims are flipped. Demonstrates a pattern: status flips that touch headers and tables also need to sweep the explanatory prose buried below the fold.
- **Lenient-vs-strict-read distinction surfaced explicitly** — The 30-second quickstart callout, Status bullet, and Phase 0 closure callout all now name both reads: the lenient read (cross-OS, one Windows + one macOS install proven) closed Phase 0; the strict read (two installs by uninvolved third parties, project author untouched at every step) remains open and is being satisfied opportunistically.
- **Anchor stability fix** — Four README cross-references to the Phase 0 ROADMAP header repointed from `#phase-0--install-path-validation-active-duration-tbd-by-diagnosis` (which rewrites when a `*(closed…)*` suffix is appended) to `#at-a-glance` (stable). Demonstrates a pattern: section anchors that carry status annotations in their text are fragile cross-reference targets; the at-a-glance table's anchor is the stable entry point.
- **ADR count refreshed** — Further reading footer: `31 ADRs as of v7.0.2` → `34 ADRs as of v7.0.9` (ADRs 0032, 0033, 0034 landed since v7.0.2; verified by counting `docs/adr/` files).
- **Phase 1 fully closed** — All four Phase 1 deliverables landed (repo rename v7.0.5, `tailor migrate` retirement v7.0.9, README framing v7.0.10, banner-stacking superseded). Phase 2 — Public-launch readiness — unblocks.
- Gates: ci-gate-runner SHIPPABLE (940/940 pytest, ruff clean, 76/76 probe, CLI smoke clean). mcp-protocol-auditor NOT TRIGGERED. cue-card-rehearsal-auditor NOT TRIGGERED. recipient-install-validator SKIPPED (README.md and ROADMAP.md not in ADR 0028 trigger globs; v6.11.x falsification grounds the skip).

### Shipped in v7.0.9 (2026-05-12)

- **`tailor migrate` retired** — `cmd_migrate`, `_emit_legacy_migration_warning_if_applicable`, and `_legacy_config_dir` deleted from `src/tailor/__main__.py` per [ADR 0034](docs/adr/0034-retire-tailor-migrate-subcommand.md) (NEW, Accepted). The subcommand scaffolded a migration path for a v6 user population that was empirically zero.
- **[ADR 0034](docs/adr/0034-retire-tailor-migrate-subcommand.md) NEW, Accepted** — grounds the retirement in the empirical record: no successful external v6 install across the v6.10.x patch quartet, the v6.11.x falsified recipient-install-validator, the 2026-05-09 self-driven Windows install, or the 2026-05-12 first true outside-recipient macOS install.
- **[ADR 0031](docs/adr/0031-rename-to-tailor-and-wardrobe.md) amended** — status now lists Superseded in part by ADR 0033 AND ADR 0034; migration story blockquote and negative-consequence sub-bullet added; naming decisions and workshop-metaphor invariant retained.
- **Collateral cleanup** — `README.md` migrate row removed; `ROADMAP.md` Phase 1 struckthrough rows updated; v7.0.0 Shipped entry forward-cited to ADR 0034; `docs/diagnosis/phase-0-diagnosis-kit.md` Expected list updated.
- Gates: ci-gate-runner SHIPPABLE (940/940 pytest, ruff clean, 76/76 probe, CLI smoke clean). mcp-protocol-auditor NOT TRIGGERED. cue-card-rehearsal-auditor NOT TRIGGERED. recipient-install-validator SKIPPED (pure deletion in `__main__.py`; v6.11.x falsification + 2026-05-12 macOS recipient install are the empirical substitute).

### Shipped in v7.0.8 (2026-05-12)

- **Phase 0 closed** — Install-path validation closes under the lenient read of the exit criterion. 2026-05-09 Windows (self-driven, fresh user account) proved the technical install path on Windows-Store-Claude; 2026-05-12 macOS (first true outside recipient, friend installed, boss watched) proved the recipient-experience path. Exit intent — uninvolved third parties can install Tailor — is satisfied. Boss made the closure call after protocol-4 conflict was surfaced.
- **Phase 1 unblocked** — Ship-quality housekeeping is now active (~2 weeks). Highest-leverage deliverable: `tailor migrate` removal (scaffolding for a v6 user population that turned out to be zero).
- **ROADMAP.md Phase 0 / Phase 1 status rows + section headers updated** — at-a-glance table and section headers reflect the phase flip.

### Shipped in v7.0.7 (2026-05-12)

- **[ADR 0033](docs/adr/0033-complete-tailor-metaphor-workshop-side.md) NEW, Accepted** — completes the Tailor metaphor on the workshop side; retires the counter-programming invariant from ADR 0031 and replaces it with a positive workshop-shaped metaphor identity + narrow-forbid list enforceable by grep.
- **[ADR 0031](docs/adr/0031-rename-to-tailor-and-wardrobe.md) amended** — status flipped Accepted → Superseded in part by ADR 0033; naming decisions retained; counter-programming invariant retired.
- **Wardrobe / Ledger split** — Audit history bullet moved from the Wardrobe list to a new sibling Ledger paragraph in `CLAUDE.md` § Your Wardrobe and `README.md` § Your Wardrobe; directory structure (`framework/audit.db` outside `framework/vault/`) already reflected this split before the terminology did.
- **New [`docs/design/tailor-vocabulary.md`](docs/design/tailor-vocabulary.md)** — normative reference with six locked vocabulary tables: 7 structural nouns, 12 relational verbs, service hierarchy, audience model, workshop-vs-lifestyle invariant, weak beats.
- **ROADMAP.md Phase 2 row reshaped** — `counter-programming-invariant-auditor` → `vocabulary-drift-auditor` with explicit ADR 0033 retirement record.
- Gates: ci-gate-runner SHIPPABLE (940/940 pytest, ruff clean, 76/76 probe, CLI smoke). mcp-protocol-auditor NOT TRIGGERED. cue-card-rehearsal-auditor NOT TRIGGERED. recipient-install-validator SKIPPED (no trigger-glob paths touched; v6.11.x falsification grounds the skip).

### Shipped in v7.0.6 (2026-05-09)

- **[ADR 0032](docs/adr/0032-retire-public-mirror-distribution.md) NEW, Accepted** — retires the public-mirror distribution path from ADR 0030 + ADR 0024 § 3.1; wheel-handoff via personal email supersedes through Phase 1; GitHub Pages on source repo supersedes from Phase 2 PyPI publish onward.
- **Mirror archived:** `saahasmuthineni/biosensormcpdemo` archived via `gh repo archive` on 2026-05-09; legacy URL resolves with v6.13.0 snapshot for in-flight friend-shares; reversible via GitHub web UI at any time.
- **ADR 0030 status flip** — Accepted → Superseded by ADR 0032 (in part); zero-outbound-affordances render invariant retained in full (URL allowlist at `src/tailor/demo/runner.py:336-365`, `_personas.json`, `--audience=public` flag, attribution-only footer).
- **ADR 0024 § 3.1 retirement closeout footer** — distribution carve-out section closed out with retirement note citing ADR 0032.
- **`docs/guides/share-the-demo.md` rewritten** — wheel-by-email path replaces the public-mirror ritual; per-recipient wheel build + `uv tool install` command documented.
- Gates: ci-gate-runner SHIPPABLE (940/940 pytest, ruff clean, 76/76 probe, CLI smoke). mcp-protocol-auditor NOT TRIGGERED. cue-card-rehearsal-auditor NOT TRIGGERED. recipient-install-validator SKIPPED (no trigger-glob paths touched; v6.11.x falsification grounds the skip).

### Shipped in v7.0.5 (2026-05-10)

- GitHub repo renamed `Biosensor-to-LLM-Connector` → `tailor-mcp` (GitHub
  auto-redirect preserves existing clones). Closes the [ADR 0031](docs/adr/0031-rename-to-tailor-and-wardrobe.md)
  § Negative consequences known-debt entry.
- Codebase doc-truth pass: Project URLs (`pyproject.toml`), CI badge + install
  commands + clone instructions (`README.md`), install command (`CLAUDE.md`,
  `docs/guides/multi-subject-pilot.md`, `docs/diagnosis/phase-0-diagnosis-kit.md`
  A6), issues URL (`docs/external-review.md`), example path
  (`examples/cohort_demo/beta/README.md`), ADR URL + known-debt closeout
  (`docs/adr/0031-rename-to-tailor-and-wardrobe.md`).
- Phase 1 strikethrough row updated with "landed 2026-05-10" annotation.
- Vault project-folder cross-link updated out-of-band via Obsidian MCP.
- No `src/` changes; no test changes; no public API changes. Patch bump.

### Shipped in v7.0.4 (2026-05-10)

Phase 0 deliverable 2 patch (preliminary verdict: PATCH not RESTRUCTURE
per the 2026-05-09 self-driven diagnosis). Closes the four findings
the two attempts surfaced against `tailor tour` and the diagnosis kit.
Single-file framework change, three doc/kit changes, seven new
regression tests.

- **F4 (architectural — `tour.py`)**: `tailor tour` now detects Claude
  Desktop presence BEFORE registration. New
  `_detect_claude_desktop_presence()` checks the classic config dir on
  Windows + every UWP `Claude_*` package dir + the macOS Application
  Support dir; Linux always returns False. When absent, the success
  banner says `Tour scaffolded; Claude Desktop NOT DETECTED` with an
  install pointer instead of the misleading `"fully quit Claude
  Desktop, then re-open it"` ritual the recipient cannot perform. Tour
  still stages the config (per [ADR 0026](docs/adr/0026-dual-path-claude-desktop-config.md)
  § "First-time-install on a Store-only machine") so a future Claude
  Desktop install picks it up automatically; the verb in the banner
  shifts from `registered as ...` to `staged as ...`.
- **F5 (documentation — `tour.py` + `README.md`)**: tour-success
  message and a new README "What success looks like" subsection both
  preempt the visual-asymmetry confusion attempt 2 surfaced — Claude
  Desktop renders local MCP servers as a "session-scoped server" in
  prose rather than a green-card connector. Tailor cannot change
  Claude Desktop's UI; both surfaces now name the rendering as the
  normal local-MCP shape, not a degraded install.
- **F2 (kit-instrument — `phase-0-diagnosis-kit.md`)**: per-command
  `Tee-Object -Append` advice promoted from the deeper-buried capture
  protocol section into the install-checklist itself, inline at every
  `tailor` invocation (A7 / A8 / A9 / A13). Closes the PowerShell-5.1
  transcript-gap workaround that was only discoverable post-hoc on
  attempts 1 + 2.
- **F3 (documentation — `README.md`)**: Prerequisites split into
  recipient-install (uv + Claude Desktop; Python on `PATH` *not*
  required — uv provisions its own) vs. developer-install (Python
  3.10+). Closes the attempt-1 friction where `python --version`
  returning command-not-found read as a hard prerequisite failure
  even though `uv tool install` succeeded immediately afterward.

Naming-collision fix: the 2026-05-09 vault snapshot referred to the
deferred `_extract_timestamps` paired-iteration helper bug as "F4",
colliding with Phase 0's structured F1–F5 finding labels. Renamed the
legacy item to `_extract_timestamps` paired-iteration helper (the
v6.10.1 banner already used "Bug 4", not "F4"). Phase 0 F1–F5 stays
canonical.

Version sync: `__init__.py` was `6.13.0` while `pyproject.toml` was
`7.0.0` (drift from the v7.0.0 rename's mechanical pass). Both now
read `7.0.4`.

Gates: pytest +7 new regression tests across
`TestClaudeDesktopPresenceDetection`,
`TestSuccessBannerHonestyOnAbsentClaudeDesktop`, and
`TestConnectorVsServerFraming`. No router/security/child/vault
architecture changes; no public API changes; patch bump.
mcp-protocol-auditor NOT TRIGGERED (no framework/router/security/vault
paths touched). recipient-install-validator SKIPPED — v1 falsified
per project memory; the 2026-05-09 self-driven diagnosis is the
empirical substitute on this round.

### Shipped in v7.0.0 (2026-05-08)

Project rename: `Biosensor MCP` → **Tailor**. The first major version
bump in the project's history. PyPI `tailor-mcp`; Python import +
CLI `tailor`; config dir `~/.tailor/`; env vars `TAILOR_*`. New
user-facing engine word **Wardrobe** for what the framework holds on
the user's behalf (themes / moments / evidence / failure modes /
audit history / source data) — replaces the working term *substrate*.
New `tailor migrate` subcommand for non-destructive v6 → v7
filesystem upgrade (retired in v7.0.9 — see
[ADR 0034](docs/adr/0034-retire-tailor-migrate-subcommand.md)). Dual-prefix Claude Desktop cleanup (`biosensor-*`
+ `tailor` / `tailor-*`) so v6 → v7 doesn't leave orphan entries.
Counter-programming invariant per [ADR 0031](docs/adr/0031-rename-to-tailor-and-wardrobe.md):
visual language stays non-fashion, onboarding copy redirects the
literal-clothing read, content shown in any "your Wardrobe" view is
visibly diverse from first impression. Three ADR forward-cites added
(0024 / 0026 / 0028) to keep the install / registration / migration
story discoverable from existing ADRs. Internal architectural
identifiers (`framework/`, `vault/`, `audit.db`, `RouterMCP`,
`VaultLayer`, `ChildMCP`) preserved — they describe the architecture,
not the project's identity. Domain-term language ("biosensor children",
"biosensor-tier gates", "biosensor data") preserved — describes the
data domain, which the framework still handles. Historical files
(`CHANGELOG.md` pre-v7.0.0 entries, `docs/reports/*-2026-05-01.md`,
the 2026-05-05 vault moment) preserved verbatim — they describe past
state under the old name. Major bump because package import name,
CLI command, env vars, default paths, and Claude Desktop registration
keys all changed; every existing v6 install needs the new install
command + a one-time migration. Gates: 930/930 pytest, ruff clean,
76/76 probe, CLI smoke clean. mcp-protocol-auditor NOT TRIGGERED (no
behavioural paths touched, only naming). recipient-install-validator
SKIPPED per the v6.11.x silent-park falsification documented in
project memory — operator hand-validation is the v7.0.0 backstop.
ADR 0031 codifies the rename, the Wardrobe naming decision, the
counter-programming invariant, the migration story, six alternatives
considered, and four reversal conditions.

### Shipped in v6.13.0 (2026-05-08)

- ADR 0030 NEW: *"Public-mirror narrative and zero-outbound-affordances"* — codifies the `--audience=public` rendering contract, the URL allowlist hard-fail seam, and the attribution-only footer pattern. Cites ADRs 0011 / 0024 / 0027 and the researcher-utility-reviewer persona definitions. Status: Proposed → shipped.
- `--audience=developer|public` CLI flag on `tailor demo`: public mode splices per-persona panels (PI / analyst / IRB) after each of the 5 demo sections and applies zero-outbound-affordances (attribution-only footer, render-time URL-allowlist hard-fail).
- `src/tailor/demo/_personas.json`: new canonical single-source schema for persona definitions + per-section panel content — closes the F1 finding from integration-auditor (personas were split across researcher-utility-reviewer agent and inline runner logic).
- `docs/guides/share-the-demo.md` updated: per-release ritual now uses `--audience=public`; verify checklist updated for panel count + URL-allowlist behaviour.
- +12 tests (909 → 921+). ci-gate-runner PASS: 923/923 pytest, ruff clean, 76/76 probe, CLI smoke clean. Minor bump.

### Shipped in v6.12.0 (2026-05-08)

- `tailor demo` reshaped from 3-call cohort first-look into 5-section architectural showcase per ADR 0029 (NEW). Sections 2–5 exercise router pipeline visibility, three-tier resolution model, vault durable persistence, and local-LLM oracle substrate scan — in sequence, using the same bundled demo cohort S001 fixture throughout.
- New `--save-shareable [PATH]` CLI flag: tees demo stdout into a self-contained markdown file (install command + transcript + breadcrumb footer), suitable for emailing or static hosting.
- ADR 0029 NEW: *"Token reduction is analytical quality, not just cost optimization; the demo demonstrates the architecture, not only the cohort thesis."* Partially supersedes ADR 0027 § Negative consequences.
- ADR 0024 § 3.1 amended: public release-only mirror at `saahasmuthineni/biosensormcpdemo` (GitHub Pages `https://saahasmuthineni.github.io/biosensormcpdemo/` verified live) codified as a friend-shareable distribution carve-out alongside Drive/email channel.
- ADR 0027 header amended with "Partially superseded by ADR 0029" forward-cite.
- `recipient-install-validator` Step 6 assertion list updated for the new five-section demo output.
- New `docs/guides/share-the-demo.md`: boss-side checklist for the public-mirror setup ritual (one-time + per-release).
- +11 tests (898 → 909): Sections 2–5 demo coverage + `--save-shareable` invariants. Gates: 909/909 pytest, ruff clean, 76/76 probe, CLI smoke PASS. Minor bump.

### Shipped in v6.11.1 (2026-05-07)

- `recipient-install-validator` operational hardening: halt-on-exit semantics (non-zero guest exit code fails the gate), structured progress emission, and watcher discipline for Windows Defender / AV interference — ADR 0028 v6.11.x amendments.
- `release-shipper` Pre-tag gate composition: tiered policy implementing mandatory `ci-gate-runner`, attestation-required `mcp-protocol-auditor` + `cue-card-rehearsal-auditor` (skippable with `--gates-confirmed`), and heavyweight opt-in `recipient-install-validator` (skippable with `--full-validate`).
- ADR 0016 (`mcp-protocol-auditor`) enforcement amendment: release-shipper attestation replaces prior "mandatory before every release" prose as the binding enforcement mechanism.
- ADR 0025 (`cue-card-rehearsal-auditor`) enforcement amendment: same pattern as ADR 0016 — release-shipper attestation replaces prose-only mandate.
- ADR 0028 (`recipient-install-validator`) mandate-refinement section: operational hardening + tiered-gate mandate codified as v6.11.x amendment.
- Pure governance/team-shape patch release. No `src/` changes, no `tests/` changes, no router/security/child/vault/CLI architecture changes. Gates: 898/898 pytest, ruff clean, 76/76 probe, CLI smoke PASS.

### Shipped in v6.11.0 (2026-05-07)

- New `recipient-install-validator` specialist provisioned via VirtualBox + Vagrant. Provisions a clean Windows 11 base box, installs the freshly-built wheel via the documented recipient command, runs `tailor tour`, and validates end-to-end against the wheel-installed package — catching the failure class that produced the v6.10.1–v6.10.4 patch quartet (bugs invisible to host-side gates running against the dev tree).
- Gate is mandatory + file-touched-gated. Fires when any of `tour.py`, `pilot.py`, `__main__.py`, `wizard.py`, `pyproject.toml` package-data globs, or `_fixtures/**` changes. Composes with `ci-gate-runner` at the `release-shipper` boundary.
- ADR 0028 codifies the structural argument under ADR 0011's promotion policy, eight-step install-ritual assertion list, `boot_timeout=1800s` (empirically validated on Win 11 Home with `VirtualMachinePlatform = Enabled`), and six alternatives considered + rejected.
- Accepted v1 gap named explicitly: no Claude Desktop pre-installed in base image; ADR 0026 dual-write logic exercised by mocked host tests but not in-guest. v2 escalation path named in ADR 0028.
- Pure governance/team-shape release. No `src/` changes, no `tests/` changes, no router/security/child/vault/CLI architecture changes.

### Shipped in v6.10.5 (2026-05-07)

- `tailor demo` reframed from synthetic-Strava operator self-verification to bundled demo cohort fixtures researcher first-look per [ADR 0027](docs/adr/0027-demo-as-researcher-first-look.md). Closes the drift between CLAUDE.md's stated framing ("Strava is a worked example, not the canonical use case") and the demo's actual behavior across the entire v6.x cycle.
- `demo/runner.py` rewritten: instantiates `CSVDirectoryChild`, exercises `csv_cohort_summary` (by sex, by group) + `csv_force_decline` on pinned subject S001 against bundled `_fixtures/cohort_demo_realistic/force/`. Output is the real result envelope shape; the router / audit / consent-gate path is explicitly out-of-scope with a pointer to `tailor tour`.
- `demo/sample_data.py` preserved untouched per ADR 0008 § Alternatives.
- Deferred `demo` → `verify` rename KILLED: a researcher-first-look surface should not be called `verify`. ROADMAP item rewritten as KILLED with explanation. ADR 0024 deferral paragraph updated to name the kill.
- Doc-truth drift cleanup (9 sites caught by `red-team-reviewer` adversarial pass per ADR 0010): README.md ×3, CONTRIBUTING.md, tour.py module docstring, ROADMAP.md ×2, docs/guides/claude-desktop-demo.md ×2. Known debt: `docs/assets/demo.svg` orphan asset queued for future doc-pass per ADR 0027 § Negative consequences (resolved in the post-v6.13.0 cleanup pass — orphan removed; replacement demo cohort visualization remains an open creative item).
- ADR 0027 NEW: researcher-first-look framing, trade-off vs RouterMCP path, named negative consequences.
- +8 tests in `tests/test_demo_runner.py` (890 → 898): end-to-end run, output-mentions-cohort-not-Strava, balanced-by-sex cohort (F+M n=8, Hunter & Senefeld 2024 sex-differences thesis), cohort-by-group, force-decline-on-S001, deterministic-across-reruns (ADR 0008 surfaced as recipient-checkable property), sample_data importability, bundled-fixture loadability.
- Gates: 898/898 pytest, ruff clean, 76/76 probe, CLI smoke PASS. Patch bump.

### Shipped in v6.10.4 (2026-05-06)

- Dual-path Claude Desktop config resolution closes the Microsoft Store / Classic install mismatch on Windows. `_claude_desktop_config_path() -> Path | None` refactored to `_claude_desktop_config_paths() -> list[Path]`; Windows now writes to both the classic `%APPDATA%\Claude\` path and any matching UWP sandbox path (`%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\`). Recipient who sees "successfully registered" but no biosensor tools is now routed correctly regardless of which Claude Desktop distribution they installed.
- New `_RegistrationResult` dataclass + `_write_registration_to_path` helper with per-path atomic semantics: read → clean siblings → add entry → atomic write. PermissionError on one path does not abort writes to others; exit code 1 only if every path failed; `.tmp` artifacts unlinked on partial failure.
- `cmd_status` reframed to surface human-readable recovery instructions instead of engineering jargon.
- Three duplicated platform-conditional Windows branches in `__main__.py` collapsed into the shared helper.
- ADR 0026 NEW (cites ADRs 0010 / 0014 / 0024); ADR 0024 amended with historical-context framing at two references to the now-refactored singular helper.
- CUE_CARD.md: two new recovery rows for the dual-path surface (partial-write and Store-version-no-tools-after-launch).
- +14 regression tests (890 total): 13 in `test_dual_path_registration.py` covering 8 audit-named scenarios; 1 in `test_uninstall_cleanup.py` for cross-config iteration.
- Invariant locked: after a successful `tour --force`, exactly one `biosensor-*` entry exists in EACH detected Claude Desktop config; the entry is identical across configs.
- Structural lesson: the write site must enumerate all paths the reader will ever check — not just the canonical path from official docs. UWP sandbox redirection is silent and invisible from the writer side without prefix-glob enumeration.

### Shipped in v6.10.3 (2026-05-06)

- Tour cleans sibling `biosensor-*` entries from `claude_desktop_config.json` before adding its own. Closes the multi-entry coexistence trap: a recipient who had a stale bare `tailor` entry (written by web-Claude during a failed v6.9.x install) would end up with two MCP servers after `tour --force`, leaking `tailor_setup_help` into the working-demo state. Symmetric with v6.9.2's prefix-match cleanup in `cmd_uninstall` — uninstall cleans on teardown, tour cleans on setup.
- `_register_with_claude_desktop` return type changed from `Path | None` to `tuple[Path | None, list[str]]`; `tour_main` prints cleaned entries when non-empty.
- +2 regression tests: `test_cleans_stale_biosensor_entries_before_writing`, `test_no_op_when_only_target_entry_already_present`.
- Structural lesson: the tour-write site must be symmetric with uninstall in its handling of `biosensor-*` siblings. Same shape as v6.9.2's prefix-match-uninstall loop closure.

### Shipped in v6.10.2 (2026-05-06)

- `SetupHelpLayer` — new framework-tier layer (parallel to `LocalLLMLayer` per ADR 0022 shape) registered conditionally when `_demo_blocks_absent()` detects no `csv_dir` blocks in `user_config.json`. Surfaces a single diagnostic tool (`setup_help_get_status`) that routes an external Claude to `tailor tour`; invisible on configured deployments (SH7 wire-test confirms). `_redact_home()` strips HIPAA Safe Harbor §164.514(b)(2)(i)(R) address components before surfacing on the wire. 16 unit tests (trigger predicate, layer surface, redaction, dispatch, audit-row provenance). 7 new subprocess wire-tests SH1-SH7 added by mcp-protocol-auditor.
- `RECIPIENT_README.md` bundled in the wheel (`pyproject.toml` `*.md` glob added to package-data). An external Claude inspecting the .whl now discovers `tailor tour` as the recovery path without source-code archaeology — the structural lesson from dad's transcript.
- ADR 0012 amended: Decision section extended to all three framework-tier PHI-scrubber bypass sites (vault + local_llm + setup_help) with per-layer invariants and reversal conditions. Closes phi-irb-risk-reviewer Lens 4 finding.
- CUE_CARD.md recovery row added for the "tool list shows only ask_local_oracle + strava_list_runs" symptom.
- Tool surface: 50 when degraded (setup_help visible), 49 when scaffolded (baseline unchanged). Patch bump.
- Structural lesson: an external Claude inspecting the wheel must be able to discover `tailor tour` without source-code archaeology. `SetupHelpLayer` is the in-chat fallback when wheel-inspection fails.

### Shipped in v6.10.1 (2026-05-06)

- Fixed four Windows recipient demo blockers found during direct `tailor tour` testing on Windows 11 PowerShell cp1252: Bug 1 (`→` → `->` in `cmd_status`), Bug 2 (OperationalError guard around Strava-tier SELECT on fresh tour install), Bug 3 (`←` → `<-` in `pilot.py`), Bug 5 (unicode glyphs `❌`/`✅` → `[X]`/`[OK]` in `wizard.py`).
- New private `_make_cli_stdout_resilient()` in `__main__.py`: reconfigures sys.stdout/sys.stderr with `errors='replace'` so future non-cp1252 glyphs degrade to `?` rather than crashing. 3-layer defense: static glyph removal + runtime reconfigure + static guard test suite.
- +17 regression tests (851 total): 10 in `test_cli_windows_resilience.py` (5 parametrized static-guard, 3 stdout-helper, 2 fresh-tour-install); +8 subprocess tour-path MCP wire tests in `test_serve_mcp_protocol.py` covering previously-untested force_csv + emg_csv wire surface.
- Bug 4 (`_extract_timestamps` paired-iteration refactor) deferred to v6.11.0: red-team-reviewer HIGH OBJECTION — minimal fix produced 40% systematic error in `time_to_50pct_drop_s` on mixed-defect CSVs via silent index-misalignment. ADR 0010 adversarial pairing demonstrably caught this. No API changes; patch bump.

### Shipped in v6.10.0 (2026-05-06)

- `cue-card-rehearsal-auditor` specialist promoted per [ADR 0025](docs/adr/0025-cue-card-rehearsal-as-release-gate.md). Read-only agent (opus model, tools: Read/Grep/Glob) audits cue-card prompts against ToolDefinition schemas and emits per-prompt verdicts (PASS / WRONG-TOOL / WRONG-PARAMS / AMBIGUOUS). Closes the structural class of failure responsible for both v6.9.1 and v6.9.2: schemas whose envelope passes structural gates but silently fails when Claude infers parameters from operator prose. Mandatory pre-tag trigger wired into `release-shipper`.
- ADR 0025 cites ADRs 0008, 0010, 0011, 0014, 0016. First-run dogfood evidence included: REVIEW aggregate, AMBIGUOUS verdict on Step 2 cohort prompt demonstrates the gate fires on real under-specification without false-positiving on structural envelope correctness. Deferred (named in ROADMAP): `emg_cohort_summary.value_column` schema hygiene; CUE_CARD.md v6.9.0-footgun recovery row retention decision (boss-decision item).
- Same governance/team-shape release shape as v6.3.0 (no framework code changes); 834/834 pytest, ruff clean, 76/76 probe, CLI smoke PASS. Minor bump.

### Shipped in v6.9.2 (2026-05-06)

- Hardened `cmd_uninstall` to prefix-match `biosensor-` so `biosensor-tour-<variant>` orphan Claude Desktop entries are cleaned alongside `tailor`; extracted `_clean_claude_desktop_biosensor_entries()` helper (7 new tests in `test_uninstall_cleanup.py`).
- Switched all CSV-open and JSON-sidecar reads in `force_csv` (3 sites), `emg_csv` (3 sites), and `csv_dir` (6 sites) from `utf-8` to `utf-8-sig` for transparent BOM stripping — Excel- / PowerShell-saved data would otherwise silently corrupt first-column header lookups and sidecar filename matches (`TestBomTransparency` in each shape suite, +4 tests).
- Fixed `tour --force` to `rmtree` the target dir before scaffolding so a broken scaffold can be recovered as `WINDOWS_QUICKSTART` documents (+1 test in `test_tour_subcommand.py`).
- +12 regression tests total; 834 pass. Bug fixes only; patch bump.

### Shipped in v6.9.1 (2026-05-06)

- Fixed cohort-handler logical→physical column-alias resolution in `force_csv` and `emg_csv` children. `_handle_cohort_summary` now maps `value_columns` logical alias names to physical CSV header names before metric dispatch, closing the v6.9.0 first-prompt-failure footgun (16 silent `column not found` load_errors when Claude guessed the logical name from operator prose).
- Registered the 16 bundled 31P-MRS CSVs in the `tour` scaffolding output. The files were bundled in the wheel but `user_config.json` had no `csv_dir` block for `mrs/`; they were unreachable via any tool until this fix.
- 6 new regression tests: `TestCohortSummaryAliasResolution` (2 tests) in `force_csv` and `emg_csv` shape suites; updated user_config-shape assertion in `test_tour_subcommand.py`.
- `CUE_CARD.md` sharpened: Variant-C recovery steps clarified; Variant-B rows added for `force_cohort_summary` / `emg_cohort_summary` tools.

### Shipped in v6.9.0 (2026-05-04)

- Wheel-distributed `tailor tour` CLI subcommand ([ADR 0024](docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md)). Scaffolds the demo cohort realistic demo from bundled wheel fixtures into `~/.tailor/demos/cohort/`; copies 48 CSVs + 3 metadata sidecars + 1 seed vault moment via `importlib.resources`; writes `user_config.json` with absolute paths; merges Claude Desktop config — recipient never types an env var. Flags: `--variant`, `--target`, `--no-claude-desktop`, `--force`. Inherits `pilot.py`'s atomic-write + BOM round-trip + deep-merge hardenings.
- Demo cohort realistic fixtures bundled into the wheel. Migrated from `examples/cohort_demo/realistic/` to `src/tailor/_fixtures/cohort_demo_realistic/`; `pyproject.toml` package-data globs extended. Distribution: pre-built wheel via Drive/email; no PyPI publish; wheel size 1.26 MB (budget 10 MB).
- ADR 0024 codifies synthetic-by-construction precondition — bundling permitted only for bytes that are synthetic by construction; real or de-identified cohort data require a superseding ADR.
- `examples/cohort_demo/realistic/setup.py` preserved as thin shim delegating to `tour_main()`; `rehearse.py` rewritten to rehearse the recipient code path against a temp dir; `WINDOWS_QUICKSTART.md` becomes a fully wheel-driven recipient guide.
- Deferred (named in ROADMAP): legacy `tailor demo` → `verify` rename (subsequently *killed* in v6.10.5 per [ADR 0027](docs/adr/0027-demo-as-researcher-first-look.md) — `demo` is now a researcher first-look, not operator self-verification, so the `verify` rename became the wrong move); PyPI publish path when recipient set crosses ~10.
- 23 new tests (20 `test_tour_subcommand.py` + 3 subprocess `test_serve_mcp_protocol.py`); 818/818 passed. 7-agent release pass clean.

### Shipped in v6.8.1 (2026-05-03)

- C3 peak-tie systematic bias fix in `csv_dir/processing.py`. New `_last_peak_index` module-level helper scans values from the end backward; applied at both call sites (`aggregate_metric` for `time_to_50pct_drop_s`, `force_decline_summary` for `peak_index`). Eliminates the systematic inflation of `time_to_50pct_drop_s` on isometric force traces with ramp → plateau → decline shape: participants with longer plateau holds received larger positive bias, creating a between-groups confound for `csv_cohort_summary` comparisons. Three new regression tests closing the plateau / unique-peak regression paths. 676 → 679 tests; 85% coverage; `processing.py` at 99%. No architecture changes; patch bump.

### Shipped in v6.8.0 (2026-05-03)

- Local-LLM cooperation-loop pattern, PR2 (LLM-driven gap reasoning). [ADR 0023](docs/adr/0023-local-llm-cooperation-loop.md). New `OracleResponse.next_best_calls` and `OracleResponse.unresolved_intent` fields completing the cooperation-loop contract; `OllamaBackend` JSON-mode prompt extension with defensive list-coercion; `NullBackend` empty-default inheritance by construction; `ask_local_oracle` tool description rewritten to teach hosted Claude the multi-pass cooperation loop; two new `audit_log` columns (`oracle_next_best_calls_count`, `oracle_unresolved_intent_count`) by symmetry with PR1's `oracle_substrate_count`. ADR 0023 amended: § Audit-log columns names all three, § Negative consequences token-estimate corrected (~290 measured vs ~2500 estimated), § Neutral consequences PR1/PR2 ADR 0012 distinction added. Operator guide: "Important precision — gap-reasoning egress" subsection added. Research-framing § Consent withdrawal: oracle audit rows named as third retention category. 15 new regression tests (12 PR2 contract/parser/fallback + 3 audit-column) + 4 subprocess tests from mcp-protocol-auditor; 676/676 pass. Coverage 85%. 7-agent release pass clean (all WATCH/OBJECTION findings addressed before ship). No new tools — `ask_local_oracle` gains response fields only.

### Shipped in v6.7.0 (2026-05-03)

- Local-LLM cooperation-loop pattern, PR1 (substrate-vision asymmetry made executable). [ADR 0023](docs/adr/0023-local-llm-cooperation-loop.md). New `OracleResponse.related_substrate` field; new `audit_log.oracle_substrate_count` column; new public `VaultWriter.storage` property; `(kind, slug)` substrate dedup; `substrate_scan_warning` parallel to `scrubber_warning` for swallowed VaultStorage exceptions; `_collect_subjects` scalar-filtered to mirror `_flatten_claims`. 26 new regression tests; 657/657 pass. 7-agent release pass clean. Operator guide gains substrate-metadata-egress + Path-A-vs-B warnings.

### Shipped in v6.6.0 (2026-05-01)

Local-LLM guardian release. SemVer minor bump — public API additions
only, no breaking changes.

- Added `framework/local_llm/` — a new framework-tier component (parallel
  to `framework/vault/`) providing an `ask_local_oracle` tool that enables
  a local LLM to compose structured natural-language responses over
  deterministic processing output. Numbers from `processing.py`; prose from
  the local LLM; `OracleResponse` schema enforces the separation.
- `LocalLLMBackend` ABC with `NullBackend` (no-op default; existing
  deployments behaviorally unchanged) and `OllamaBackend` (Ollama on
  `localhost:11434`, JSON-mode HTTP). Opt-in via `local_llm` block in
  `user_config.json`.
- Four named tiers: Scout (`llama3.2:1b`) / Sentinel (`phi3.5:3.8b`) /
  Guardian (`llama3.1:8b`) / Titan (`qwen2.5:14b`). Cited numerical claims
  identical across tiers; only the prose model differs.
- Six new `oracle_*` columns on `audit_log` for IRB-grade provenance
  (model, tier, backend, backend_latency_ms, oracle_latency_ms, claim_count).
- `router.register_local_llm_layer()` hook; layer bypasses consent/cost/
  circuit-breaker/PHI-scrub gates (same pattern as `VaultLayer`).
- [ADR 0022](docs/adr/0022-local-llm-guardian.md) (Proposed); ADR 0008
  amended to extend permit-list to name new backend files.
- Operator guide: `docs/guides/local-llm-guardian.md`.
- Total tool surface: 48 (was 47).
- 37 new regression tests; full suite 632/632.

Deferred (ADR 0022 § "Out of scope"): verifier behavior on hosted-LLM
responses, sanitizer/proxy mode, conductor-mode toggle, citation-grounding
enforcement, migration of remaining 45 tools to oracle mediation, IRB
prompt-injection threat-model update, performance characterization,
pilot-wizard tier-detection, real Ollama end-to-end smoke.

### Shipped in v6.5.0 (2026-04-30)

Tier-1 cohort surface release. SemVer minor bump — public API
additions only, no breaking changes. CSV directory child surface
widens from 5 to 7 tools.

- **Two new Tier-1 tools on the CSV directory child** —
  `csv_cohort_summary` (cross-file aggregation by metadata-sidecar
  group; returns per-group n/mean/std/min/max plus subjects-per-group)
  and `csv_force_decline` (per-file fatigue diagnostic; peak, decline %,
  decline rate per minute, time-to-50%-drop). Both Tier 1 — no
  consent gate, no cost gate, no rows in LLM context.
- **`COHORT_METRICS` vocabulary** — `mean`, `max` (alias `peak`),
  `min`, `std`, `first`, `last`, `duration_s`, `time_to_50pct_drop_s`.
  Non-parametric threshold-crossing fatigue diagnostic; explicit
  curve-fitting (exponential τ, polynomial) deferred per ADR 0015
  Alternatives.
- **Metadata sidecar pattern** — optional `<csv_dir>/metadata.json`
  with schema `{filename: {field: value}}`, required by
  `csv_cohort_summary`, ignored by every other tool. Matches
  REDCap / DataCite / Frictionless Data packaging conventions.
- **46 new regression tests** — 28 pure-function tests for
  `aggregate_metric` (15), `cohort_stats` (5), `force_decline_summary`
  (8); 18 handler/branch tests covering both new tools plus every
  fail-closed path coverage-criticality-mapper flagged on the v6.5.0
  build (sidecar JSONDecodeError + malformed-entry, csv-dir-not-found
  guard, MAX_COHORT_FILES cap, missing-group-field surface, per-file
  load_errors path, unknown-metric defensive double-check, force-
  decline OSError-on-read, `_extract_timestamps` no-timestamp-col +
  parse-failure). 576/576 tests pass.
- **ADR 0015 — Tier-1 cohort surface + metadata sidecar.** Codifies
  the cohort surface and the sidecar pattern; cites ADRs 0001 / 0002 /
  0008 / 0009 / 0014. Includes a Criticality classification section
  per ADR 0014: new processing methods are MEDIUM, new child
  handlers are HIGH.
- **`examples/cohort_demo/` walkthrough** — proof-of-concept
  against a synthetic 16-subject (8M / 8F) intermittent isometric task
  to volitional failure. Sized to mimic the active research thread
  of Senefeld + Hunter (*J Physiol* 2024, sex differences in human
  performance). Three scripted wow moments demonstrate (1) cohort
  comparison at Tier 1 with no streams in LLM context, (2) vault
  cross-session memory surfacing a prior subject-keyed moment alongside
  fresh data, (3) audit-log export as IRB continuing-review evidence.
- **4-backstop release pass** (ADR 0010 / 0011) — red-team-reviewer,
  reproducibility-provenance-auditor, phi-irb-risk-reviewer,
  researcher-utility-reviewer; vault-smoke-validator on the demo
  seed-moment vault.
- **Framework startup fix + new serve-subprocess smoke test** —
  Demo-before-commit (Protocol 5) caught a TypeError in
  `framework/router.py:983` that all automated gates missed:
  `Server.run(read, write)` was missing the third
  `initialization_options` argument required by mcp 1.27.0. Fix is
  one line (`server.create_initialization_options()`). New
  `tests/test_serve_startup_smoke.py` runs `tailor serve` as
  a subprocess with closed stdin and asserts no traceback — closes
  the gate-evasion class for upstream-mcp-SDK signature drift. The
  CLI `--help` smoke test does not exercise stdio_server, so this
  bug shipped past every specialist's PASS verdict and only
  surfaced when a real MCP client tried to connect. 577/577 tests
  pass (was 576).

### Shipped in v6.4.1 (2026-04-30)

Coverage-hardening patch closing four CRITICAL untested regions. No
public API changes. 526/526 tests pass; package coverage 84% (was 82%).

- **16 new regression tests** — `TestDispatchInternalProvenance` expanded
  with 11 tests covering all error branches on the internal dispatch path
  (PARAM_INVALID_INTERNAL, CIRCUIT_OPEN_INTERNAL, CONSENT_BLOCKED_INTERNAL,
  COST_ESTIMATE_ERROR_INTERNAL, COST_GATE_INTERNAL, ERROR_INTERNAL,
  vault-tool-rejection, PHI-scrub seam, subject_id propagation); 1 test
  for cost-estimator fail-closed on the public path; 1 test for
  unknown-domain revocation guard; 1 orjson stdlib fallback test via
  `sys.modules` patching; 2 vault writer atomic-write cleanup tests
  covering both failure paths; 1 schema test for `vault_search_notes`
  `kind` parameter.
- **ADR 0014** — Coverage criticality is an invariant: newly-uncovered
  CRITICAL or HIGH code is a COVERAGE REGRESSION regardless of overall
  percentage. CRITICAL taxonomy maps to ADRs 0001 / 0003 / 0005 / 0009 /
  0012 / 0013; enforcement is agent-driven at PR time.
- **`vault_search_notes` ToolDefinition** — surfaces canonical `kind`
  parameter alongside legacy `note_type` alias; closes v6.3.0
  drift-auditor finding.
- **4-backstop release pass** — red-team OBJECTION on two findings
  remediated; researcher-utility-reviewer ALIGNED with caveat;
  boss-report-auditor REVISE remediated; reproducibility-provenance-auditor
  CLEAN.

### Shipped in v6.4.0 (2026-04-30)

Cache-only purge on consent revocation. SemVer minor bump (breaking:
`ChildMCP.purge_cache` is now a mandatory abstract method). No router
pipeline, security-pipeline, or vault-layer architecture changes beyond
the revocation-handler rewrite.

- **New abstract method `ChildMCP.purge_cache(*, force: bool = False) -> dict`** —
  mandatory on all children; explicit rejection of the ADR 0003 default-no-op
  trap. Returns `{rows_purged, tables_touched, preserved, errors}`.
- **Router revocation handler rewrite** — `_handle_consent_revocation`
  runs purge-before-revoke synchronously; purge failure aborts revocation
  with consent intact and a `PURGE_FAILED` audit row unless `force_revoke=True`.
- **Paired `PURGE_CACHE` audit row** — every successful revocation writes a
  `PURGE_CACHE` row carrying `scrubber_id`, `force_revoke`, and the child's
  full `purge_result` dict; closes the red-team / phi-irb audit-row provenance
  gap caught on the release-time backstop pass.
- **RunningChild** — deletes `streams` + `activities` tables; preserves
  `stop_labels` (analyst-authored interpretation, not biometric data).
- **CSVDirectoryChild and TemplateChild** — return citable no-op dicts.
- **6 new regression tests** — `TestPurgeCacheOnConsentRevocation` (5) and
  `TestRunningChildPurgeBiometricCache` (1); full suite 510/510.
- **ADR 0013** — Cache-only purge on consent revocation; cites ADRs 0001 /
  0003 / 0009 / 0012; names single-account-per-domain limitation.
- **`docs/design/research-framing.md`** — new "Consent withdrawal under this
  profile" section codifying the IRB-profile language ADR 0013 cites.
- **4-backstop release pass** (ADR 0010 / ADR 0011) — red-team, researcher-
  utility, phi-irb-risk-reviewer, reproducibility-provenance-auditor; 3 found
  gaps, 2 fixed before ship, 1 documented as known limitation.
- **Closes Lens 6 retention WATCH** from v6.3.0 hygiene-pass hall-of-fame
  team expansion.

### Shipped in v6.3.1 (2026-04-30)

Hygiene-pass patch release. Three IRB-blocking VIOLATIONS patched with
regression tests; documentation drift corrected; ADR 0012 added; ADR
0008 permit-list amended. No router, security-pipeline, child, or
vault-layer architecture changes.

- **VIOLATION: consent-row `scrubber_id` absent** — `framework/router.py`
  consent-handler audit rows (approve and revoke paths) now carry
  `scrubber_id` per ADR 0003. Regression test in `tests/framework/test_router.py`.
- **VIOLATION: Tier-1 GPS re-identification path** — `strava_stop_analysis`
  coarsens GPS to 3 decimal places (~111 m), drops the `near_home`
  boolean, and buckets `distance_from_home_m` to 100 m — closes the
  HIPAA Safe Harbor §164.514(b)(2)(i)(B) triangulation path. Regression
  test in `tests/children/running/test_processing.py`.
- **VIOLATION: `PHIScrubber` warning swallowed by Claude Desktop** —
  `framework/security.py` new `scrubber_warning` property; three
  `_meta` stamping sites in `framework/router.py` inject the warning
  into the LLM transcript so misconfigured deployments are visible
  regardless of deployment shape.
- **8 new regression tests** (total 504 = 496 + 8).
- **ADR 0012** — Vault dispatch bypasses the PHI-scrubber seam: records
  the previously inline-only "Skipped by design" decision with named
  invariants and reversal conditions; cites ADRs 0003 / 0007 / 0009.
- **ADR 0008 amended** — clock-read permit-list widened to name
  `vault/renderer.py`, `vault/layer.py`, `vault/storage.py` per
  v6.3.0 BORDER NOTES drift two compliance auditors independently
  flagged.
- **Documentation drift fixed** — README.md (four actively-false
  claims, broken anchor, `_meta` example version, "What's next" table);
  CLAUDE.md (file-structure block, tool count, agent count, roster
  table); `vault/layer.py:137-140` (`vault_list_notes` kind-filter now
  lists all 7 allowed values).

### Shipped in v6.3.0 (2026-04-30)

Hall-of-fame team-expansion release. Governance / team-shape only — no
router, security-pipeline, child, vault-layer, or CLI architecture
changes. The release ships four new specialist agents, one integration-
auditor reshape, two new ADRs, and several process hard-rails.

- **4 new specialist agents** land per ADR 0011's promotion policy
  (`researcher-utility-reviewer`, `coverage-criticality-mapper`,
  `reproducibility-provenance-auditor`, `phi-irb-risk-reviewer`).
- **`integration-auditor` reshape** — gains optional
  `--invariant=schema-drift` mode for new-ChildMCP / `param_schema`
  PR-time validation against ADR 0002. Per ADR 0011, this folds into
  an existing agent rather than spawning a fifth new specialist.
- **Adversarial pairing restored and codified** — `boss-report-auditor`
  and `red-team-reviewer` rows + Tier-2 adversarial backstops
  sub-section added to CLAUDE.md. ADR 0010 makes this a permanent
  structural requirement, not an easily-overwritten banner detail.
- **BORDER NOTES side-channel** added across all 10 specialist prompts.
- **ADR 0010** (adversarial-pairing pattern — second-translator +
  adversarial-verdict structure).
- **ADR 0011** (promotion-policy override — project-local structural-
  argument + severity + cost-vs-frequency bar; frequency-based "3+ uses"
  is the fallback; four picks split 2/2 across old vs new bar).
- **`release-shipper` hard-fail on dirty working tree** — new pre-flight
  rail with `--include-pending=<file>:<reason>` opt-in restricted to a
  governance-shape allowlist; reasons must cite ADR/PR/issue or contain
  ≥5 words; trail dual-recorded in release commit body + banner summary.

### Shipped in v6.2.1 (2026-04-29)

The pilot-wizard release. Closes the install-and-configure friction for
non-technical PIs by collapsing the seven-step multi-subject pilot
quickstart into two terminal commands and three prompts. No router,
security-pipeline, child, or vault-layer architecture changes.

- **`tailor pilot` CLI subcommand** (`src/tailor/pilot.py`) —
  three-prompt wizard: auto-detects CSV schema across all files in the
  directory, writes `user_config.json` atomically, optionally registers
  with Claude Desktop on Win/macOS (skipped on Linux), runs an end-to-end
  smoke check against every CSV file.
- **F1 — full-directory smoke check** — wizard scans every CSV in the
  directory, not just the alphabetically first one. Closes the
  "P001 looks fine, P004 breaks at runtime" failure mode named by the
  audit.
- **F2 — atomic Claude Desktop config write** — `os.replace` + BOM
  round-trip + deep-merge into existing `mcpServers`. Preserves sibling
  MCP servers; asks user to quit Claude Desktop first to avoid clobbering
  an open config.
- **C3 — cloud-sync warning on `csv_dir.path`** — mirrors the existing
  `vault_path` warning for OneDrive, iCloud, Dropbox, Box, Google Drive,
  pCloud, Nextcloud, and MEGA.
- **Synthetic CSV fixtures moved into package** — P001/P002/P003 moved
  from `examples/multi_subject_pilot/csv/` to
  `src/tailor/_fixtures/multi_subject_pilot/csv/`. pyproject.toml
  `package-data` globs `_fixtures/**/*.csv`. Wheel install and source-tree
  work identically.
- **`docs/guides/multi-subject-pilot.md` rewritten** — `tailor pilot`
  is now the primary path; manual setup demoted to advanced fallback.
  Install command updated to `uv tool install git+...`.
- **9 new tests** in `tests/test_pilot_wizard.py`; full suite 496/496 green.
- **Deferred: `setup` → `setup-strava` rename** — disambiguation currently
  handled in `--help` text; re-evaluate when external doc references
  stabilise (see ROADMAP entry below).

### Shipped in v6.2.0 (2026-04-29)

The pilot-ready release. Closes the multi-subject vault failure mode
the proposal-mode auditor named for the v6.2 framing (a friendly
academic lab, one PI + one analyst, 5–20 participants, light IRB).
Also closes two latent governance-claim doc-lies the drift audit
surfaced. No router or security-pipeline architecture changes;
existing v6.1 vaults upgrade in place via lazy rescan.

- **[ADR 0009 — Vault subject-keying](docs/adr/0009-vault-subject-keying.md)** —
  resolves the design question ADR 0002 deliberately deferred. Themes
  carry an optional, set-once `subject_id` in frontmatter; evidence
  and moments stamp the subject of their writing call; search and
  list queries filter by subject when one is provided, with cross-
  subject themes and v6.1-era legacy notes preserved via the IS-NULL
  branch.
- **`subject_id` on all 25 vault tools** — surfaced in `param_schemas`
  and rendered in tool listings so LLM clients discover the
  parameter via `list_tools`. Storage-layer migrations
  (`vault_notes.subject_id`, `vault_themes.subject_id`) follow the
  same `ALTER TABLE` pattern `audit_log` used.
- **[ADR 0008 — Analytical processing is deterministic by construction](docs/adr/0008-deterministic-by-construction-processing.md)** —
  records the invariant the codebase already shipped: every method on
  `RunningProcessing`, `CSVProcessing`, and `TemplateProcessing` is a
  `@staticmethod` pure function with no PRNG and no clock reads. Names
  the residual scope on the deterministic-mode roadmap entry (the
  audited-flag-plus-provenance-hash pairing).
- **`scrubber_id` in audit-log column + `_meta` block** — closes the
  ADR 0003 doc-lie. The property existed on `PHIScrubber` since v5;
  v6.2 wires the value into a new `audit_log.scrubber_id` column and
  stamps it on every `_meta` block so a misconfigured `noop`
  deployment is visibly distinguishable from one running an
  institutional subclass.
- **`SUBJECT_ID_SCHEMA` promotion to `framework.interfaces`** —
  removes the triplicated `ValidationSchema` declarations across the
  three child modules. Children re-export via existing imports;
  vault layer references the framework-level constant directly.
- **[Multi-subject pilot quickstart](docs/guides/multi-subject-pilot.md)** —
  PI-facing walkthrough from `git clone` to a working multi-subject
  vault in roughly fifteen minutes. Bundled
  `examples/multi_subject_pilot/` with three synthetic-participant
  CSV fixtures, a deterministic regenerator script, a portable
  `user_config.example.json`, and a directory README pointing back
  at the guide.
- **Locked v6.2 deployment-shape framing in
  [`docs/design/research-framing.md`](docs/design/research-framing.md)** —
  names the target shape (Camp A-light) and explicitly defers the
  fuller institutional and personal-craft framings to v6.3+.

### Shipped in v6.1.1 (2026-04-29)

Docs and governance release. No Python code touched; no router, security,
child, vault, or CLI changes.

- **Boss-architect protocols in CLAUDE.md** — five Tier-1 rules governing
  the main session at the boss-facing boundary: intent → options before
  dispatch, pre-implementation audit on non-trivial work, plain-language
  decision-framing on every boss-facing report, anti-sycophancy and
  mandatory conflict pushback, demo-before-commit. Plus a "failure modes to
  watch" callout naming main-session sycophancy as the structural risk the
  boss cannot self-detect.
- **[docs/design/operating-model.md](docs/design/operating-model.md)** —
  two-tier architecture memo covering the boss ↔ main-session ↔
  specialist-agent hierarchy, heritage citations (PARC / Bell Labs / Apollo
  / Mac team / Brooks), and the agent roster in plain terms.
- **Agent hard rule — Refuse on conflict with codebase ground truth** — all
  8 agent prompts gain a Tier-2 anti-sycophancy backstop tailored per agent
  (e.g. adr-drafter refuses to draft an ADR contradicting an accepted ADR;
  integration-auditor refuses to classify a clearly-suspicious deletion as
  Justified without evidence).
- **integration-auditor `--proposal-mode`** — new Mode B for
  pre-implementation defensive imagining on a proposal description rather
  than a diff. Own pre-flight, evaluation procedure, and report format.

### Shipped in v6.1.0 (2026-04-29)

The vault layer gained dual-output rendering policy plus three new
tools that round out the analytical-memory model. No router, security,
or child changes.

- **[ADR 0007 — Rendering-layers policy](docs/adr/0007-rendering-layers-policy.md)** —
  source-of-truth markdown stays plain and AI-readable; plugin-enhanced
  views (Dataview, Templater) are additive only. Framework-emitted
  notes that include plugin syntax must ship a snapshot fallback so
  the same content renders for any reader.
- **`vault_refresh_dashboards`** — materialises `dashboards/open-themes.md`,
  `active-failure-modes.md`, and `recent-moments.md` from the live
  SQLite index. Each dashboard ships an always-rendered snapshot table
  plus an optional Dataview live-query block above it. Reference
  implementation of ADR 0007 dual-output.
- **Failure-mode lifecycle** — `vault_log_failure_mode` and
  `vault_list_failure_modes` add the "how we got it wrong" counterpart
  to themes. Symptom / diagnosis / mitigation are body-only and set on
  creation; metadata (status, related_themes, related_subjects, tags)
  updates in place to preserve the append-only evidence log.
- **Correction propagation** — `vault_correct_evidence` gained a
  `propagate=true` mode that appends a `[!warning]` callout to every
  note that wikilinks to the corrected theme. Idempotent on the
  `(theme_slug, evidence_timestamp)` pair, so re-running the same
  correction never duplicates markers.
- **[docs/design/managed-agents-compat.md](docs/design/managed-agents-compat.md)** —
  positions Tailor relative to Anthropic Managed Agents over
  network MCP. Path A (local-first orchestration, default) vs Path B
  (Managed Agent calling the local router); both preserve the same
  governance pipeline.

### Shipped in v6.0 (2026-04-23)

The vault overhaul ported seven governance features from personal
knowledge-management practice into the VaultLayer; these items are no
longer on the roadmap and are documented in
[ADR 0006](docs/adr/0006-vault-overhaul-v6.md) and the v6.0 CHANGELOG
entry:

- **Vault snapshot** — compressed `snapshot.md` state note
  (`vault_generate_snapshot` + `vault_get_snapshot`).
- **Vault inbox** — low-friction capture pipeline
  (`vault_inbox_add` / `_list` / `_drain`).
- **Vault health check** — diagnostic sweep over stale themes,
  orphaned moments, and unprocessed inbox items.
- **Evidence provenance** — source tier / tool / domain / verification
  stamped on evidence blocks.
- **Theme lifecycle enrichment** — reframing with prior-framings
  preservation, thinking entries distinct from evidence, and
  fold-back of resolutions onto linked notes.
- **Analytical corrections** — `vault_correct_evidence` marks
  superseded blocks without rewriting them.
- **Session divergence** — optional `divergence` field on
  `vault_capture_session` recording goal-vs-actual.

---

## Contributing

These items are roadmap-level, not ticketed. If one of them is the
reason you showed up, open a discussion or issue on GitHub first —
several have real design questions worth talking through before code.

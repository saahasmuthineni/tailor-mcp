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
| **Phase 1 — Ship-quality housekeeping** | Active (~2 weeks) | Do the docs and identity match the install path that actually works? |
| **Phase 2 — Public-launch readiness** | Queued (after Phase 1 → ~3 months) | If a stranger discovers Tailor cold, can they find, install, and start trusting it in under 30 minutes? |
| **Phase 3 — Beachhead proof + public launch** | Direction | Has one real research lab used Tailor on real data, cited it in a paper, and would they recommend it? |
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

## Phase 1 — Ship-quality housekeeping *(active; ~2 weeks)*

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
| **Make the GitHub repo public** — **Held under three-condition trigger** (see [§ Held items](#held-items-revisit-when-the-trigger-fires)) | 30 min once triggered | Without this, the trust narrative ("look at the audit log; look at the ADRs; look at the determinism invariants") cannot establish itself in OSS culture. **v7.0.13 unbundled this from the PyPI-publish row** because PyPI is a tooling question (frictionless install — at YES) and public-flip is an audience question (trust narrative going public — at NOT YET); the honest shipping shape matches that. |
| ~~**Promote `vocabulary-drift-auditor` agent (reshape of retired `counter-programming-invariant-auditor`)**~~ — **KILLED in Phase 2 planning 2026-05-12** ([§ Killed](#vocabulary-drift-auditor-specialist--killed)). [ADR 0033 § Negative consequences](docs/adr/0033-complete-tailor-metaphor-workshop-side.md) explicitly delegated vocabulary drift to `code-vs-roadmap-drift-auditor`'s existing remit and stated *"does not need a new specialist."* Applied to [ADR 0011](docs/adr/0011-promotion-policy.md)'s three criteria: structural argument is weak (register/taxonomy detection is distinguishable from fact-checking, but the architect ADR already named the seam holder), severity is low (identity-cost, not safety-cost), and the always-forbidden six-word list is grep-enforceable in principle. A pytest invariant for the always-forbidden six was prototyped during planning and deliberately not landed; Table 5 enforcement is PR review per ADR 0033 § Negative consequences' original delegation. | — | — |
| **First-time-user setup pass** | 1 week | Walk through `tailor pilot` and `tailor walkthrough` cold, in someone else's hands, with attention to the friction points an early adopter would hit. README, error messages, and onboarding copy revised against the friction surfaced. |
| **Apple Silicon reference deployment recipe** | 1 week | Document the *"Tailor on a Mac mini"* recipe for newcomers — recommended hardware tier (M4 24GB minimum), bundled local LLM (Llama 3.1 8B via MLX), always-on LaunchAgent setup, troubleshooting. Decides what *"AI-optimized computer"* means concretely for v1. |
| **CONTRIBUTING + community machinery** | 2 days | Issue templates for bug / feature / child contribution; PR template; child contribution guide; code of conduct beyond defaults. Without this, public-launch contributions hit unstructured chaos. |

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
The Senefeld thread (per project memory, the off-blueprint detour built
realistic-rate child ahead of the meeting) is the seed. Success looks
like one PI running an actual analysis through `tailor` on their lab's
own data, citing the framework in a methods section, and being willing
to be referenced in launch materials. A second beachhead lab is worth
seeking in parallel as a fallback.

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
direction, likely *"compare my morning run to the HIP Lab cohort
distribution"* — pairs the running child (live) with the bundled
HIP Lab `csv_dir` cohort fixtures (static) through
`dispatch_internal()`, exposed as a first-class tool
(`compare_me_to_cohort` or similar) and as a new section in a
future demo reshape. The HIP Lab fixtures + Strava are already
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

- **Web UI dashboard / live inspector** — framework visibility. A
  `localhost:8000` dashboard showing live audit log, current consent
  state, vault graph, last 10 analyses. Non-technical adopters need a
  *"what's it doing"* surface; IRB reviewers and co-PIs need
  inspect-without-querying-SQLite.
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

### Make the GitHub repo public

v7.0.13 split the original Phase 2 "PyPI publish + repo public-flip"
bundle into two separable decisions because they answer different
questions. PyPI answers a tooling question (*"is there a frictionless
install path?"*) — the project is at YES on it. Repo public-flip
answers an audience question (*"is the trust narrative going out into
the world?"*) — the project is at NOT YET. The honest posture as of
v7.0.13: source code is inspectable via the wheel on PyPI (anyone can
`pip download tailor-mcp` and unpack the .whl); the project's full
governance trail (ADRs, ROADMAP, design notes) stays private until a
deliberate public-flip decision. The landing page at
[saahasmuthineni.github.io/tailor-mcp-landing](https://saahasmuthineni.github.io/tailor-mcp-landing/)
serves the *"invited evaluation"* framing as the public interface for
visitors who don't yet have a back-channel.

**Trigger**: ALL three conditions must fire:

1. **Beachhead lab using Tailor on real data** (Phase 3 Direction A
   succeeds — public scrutiny becomes a real artifact to point at,
   not an abstract claim).
2. **Launch-narrative artifacts drafted** (Phase 3 Direction B's
   long-form launch post + honest comparison artifacts exist in
   publish-ready form; trust-receipts and discovery moment co-locate
   in time).
3. **Boss separately decides he wants public scrutiny** (readiness ≠
   pursuit; per project memory the boss-architect's framing is that
   Tailor is a life-project with foundational-tool ambitions, not a
   startup launch funnel — the decision to open the repo is
   independent of all technical readiness, requiring bandwidth to
   triage drive-by issues and patience for public criticism).

When all three fire, the public-flip is mechanical (~30 minutes of
repo-settings operation) plus a doc-truth pass over commit history to
confirm nothing private leaked into history. `integration-auditor
--proposal-mode` should fire on a planned public-flip diff before the
visibility-change to surface any commit-message or file content an
incognito visitor shouldn't see.

### Real PHI-scrubbing implementations

`PHIScrubber.scrub()` ships today as a documented no-op seam. The
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
illustrated, and `subject_id` wired throughout. New children fork from
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
Phase 3 with the Senefeld partnership. Could ship earlier if a
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
  (`examples/hip_lab_demo/beta/README.md`), ADR URL + known-debt closeout
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

- `tailor demo` reshaped from 3-call cohort first-look into 5-section architectural showcase per ADR 0029 (NEW). Sections 2–5 exercise router pipeline visibility, three-tier resolution model, vault durable persistence, and local-LLM oracle substrate scan — in sequence, using the same bundled HIP Lab S001 fixture throughout.
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

- `tailor demo` reframed from synthetic-Strava operator self-verification to bundled HIP Lab cohort fixtures researcher first-look per [ADR 0027](docs/adr/0027-demo-as-researcher-first-look.md). Closes the drift between CLAUDE.md's stated framing ("Strava is a worked example, not the canonical use case") and the demo's actual behavior across the entire v6.x cycle.
- `demo/runner.py` rewritten: instantiates `CSVDirectoryChild`, exercises `csv_cohort_summary` (by sex, by group) + `csv_force_decline` on pinned subject S001 against bundled `_fixtures/hip_lab_demo_realistic/force/`. Output is the real result envelope shape; the router / audit / consent-gate path is explicitly out-of-scope with a pointer to `tailor tour`.
- `demo/sample_data.py` preserved untouched per ADR 0008 § Alternatives.
- Deferred `demo` → `verify` rename KILLED: a researcher-first-look surface should not be called `verify`. ROADMAP item rewritten as KILLED with explanation. ADR 0024 deferral paragraph updated to name the kill.
- Doc-truth drift cleanup (9 sites caught by `red-team-reviewer` adversarial pass per ADR 0010): README.md ×3, CONTRIBUTING.md, tour.py module docstring, ROADMAP.md ×2, docs/guides/claude-desktop-demo.md ×2. Known debt: `docs/assets/demo.svg` orphan asset queued for future doc-pass per ADR 0027 § Negative consequences (resolved in the post-v6.13.0 cleanup pass — orphan removed; replacement HIP Lab cohort visualization remains an open creative item).
- ADR 0027 NEW: researcher-first-look framing, trade-off vs RouterMCP path, named negative consequences.
- +8 tests in `tests/test_demo_runner.py` (890 → 898): end-to-end run, output-mentions-HIP-Lab-not-Strava, balanced-by-sex cohort (F+M n=8, Hunter & Senefeld 2024 sex-differences thesis), cohort-by-group, force-decline-on-S001, deterministic-across-reruns (ADR 0008 surfaced as recipient-checkable property), sample_data importability, bundled-fixture loadability.
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

- Wheel-distributed `tailor tour` CLI subcommand ([ADR 0024](docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md)). Scaffolds the HIP Lab realistic demo from bundled wheel fixtures into `~/.tailor/demos/hip-lab/`; copies 48 CSVs + 3 metadata sidecars + 1 seed vault moment via `importlib.resources`; writes `user_config.json` with absolute paths; merges Claude Desktop config — recipient never types an env var. Flags: `--variant`, `--target`, `--no-claude-desktop`, `--force`. Inherits `pilot.py`'s atomic-write + BOM round-trip + deep-merge hardenings.
- HIP Lab realistic fixtures bundled into the wheel. Migrated from `examples/hip_lab_demo/realistic/` to `src/tailor/_fixtures/hip_lab_demo_realistic/`; `pyproject.toml` package-data globs extended. Distribution: pre-built wheel via Drive/email; no PyPI publish; wheel size 1.26 MB (budget 10 MB).
- ADR 0024 codifies synthetic-by-construction precondition — bundling permitted only for bytes that are synthetic by construction; real or de-identified cohort data require a superseding ADR.
- `examples/hip_lab_demo/realistic/setup.py` preserved as thin shim delegating to `tour_main()`; `rehearse.py` rewritten to rehearse the recipient code path against a temp dir; `WINDOWS_QUICKSTART.md` becomes a fully wheel-driven recipient guide.
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
- **`examples/hip_lab_demo/` walkthrough** — proof-of-concept
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

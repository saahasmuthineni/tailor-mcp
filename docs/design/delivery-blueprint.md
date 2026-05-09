# Tailor — Delivery Blueprint

> **Status**: Working plan as of 2026-05-03. Revised from a v1
> "GitHub repo → research-ready deliverable" framing after grounding
> in actual project context (HIP Lab via Senefeld; Camp A working
> framing; v6.8.0 cooperation-loop infrastructure shipped).
> The plan's load-bearing claim: **delivery success means a real
> research group runs at least one real analysis against real
> participant data and would say yes if asked to keep using it.**
> Code-complete and docs-complete are necessary intermediates,
> not the finish line.

## What this document is for

Companion to [research-framing.md](research-framing.md) and
[operating-model.md](operating-model.md). Where research-framing
is the *what* and *why*, this document is the *how* and *when* —
the phased plan from "framework infrastructure exists" to "a
named lab is using it." It exists because the prior planning
artifacts treated "a lab" as a hypothetical adopter; in practice
the lab has a name (HIP Lab at UIUC under Dr. Jonathon Senefeld)
and most of the planning logic changes once that's true.

The audience is the project's main session and the boss-architect.
A reviewer evaluating the project's research credibility should
read [research-framing.md](research-framing.md) first; this
document is operational.

## Anchoring assumptions

Five framing decisions were settled before this plan was drafted.
They constrain everything below; revisiting any of them implies
revising the blueprint.

1. **Camp A working framing** — institutional / lab-facing rather
   than personal-data-owner / hobby-craft. The product serves PIs,
   analysts, and IRB committees. The Strava worked-example child
   is retained for teaching value but is not the canonical use
   case. Rationale: the existing CSV directory child, vault layer,
   audit log, PHI scrubber seam, and ADRs 0009 / 0012 / 0013 are
   all built for Camp A; the demo β at
   `examples/hip_lab_demo/beta/` is shaped to a Camp A use case;
   the boss's framing in the 2026-05-03 thread settles a fork
   that had been silently deferred since v6.2.

2. **Pilot lab is HIP Lab via Senefeld** — not cold outreach.
   The relationship pre-exists; an MS-advising conversation is in
   flight. The blueprint assumes Saahas is moving into a lab role
   (undergrad → MS in Ex Phys at UIUC HK department, Spring 2027
   intake). MCP is positioned as a **side capability brought to
   the role**, not as a standalone product seeking adoption.

3. **Local-LLM guardian (Ollama) stays in v1 deployment.** The
   v6.6 → v6.8 cooperation-loop work is a load-bearing
   demonstration of the framework's core architectural claim
   (deterministic numbers + LLM-quality reasoning, neither
   leaking biometric streams to hosted Claude). Stripping it
   would weaken the pitch.

4. **Project mode is focused-effort, hobby in capacity terms.**
   Realistic active development time: ~10–15 hours per week,
   Claude-assisted. This is not a full-time research-software
   engineering project; it is an evening / weekend craft project
   with real ambition.

5. **End-state framing is hybrid** — both (a) HIP Lab actually
   uses the tool, and (b) the repo + IRB-shaped artifacts +
   public-dataset notebook are public-quality enough that an
   unrelated PI could adopt cold. (a) is the primary; (b) is the
   credibility-building artifact set that supports both the (a)
   pitch and Saahas's MS / career applications independently.

## Phase 0 — Pre-meeting work (what can ship before Senefeld replies)

The critical path is gated on a single email reply from Dr.
Senefeld (12 days overdue as of 2026-05-03). The pre-meeting
work is independent of that reply and produces artifacts that
either serve the meeting or have standalone value if the meeting
slips.

### 0.a Demo β credibility hardening

The demo β at `examples/hip_lab_demo/beta/` is the meeting's
tangible artifact. Its three "wow moments" (Tier-1 cohort
comparison in ~1 k tokens; vault-as-cross-session-memory
surfacing the pre-seeded S004 EMG / force-decoupling moment;
audit-log reconstructed from `_meta` provenance stamps) were
verified end-to-end. Before the next demo touch:

- **C3 peak-tie systematic bias fix** — `_last_peak_index`
  helper added to [csv_dir/processing.py](../../src/tailor/children/csv_dir/processing.py),
  applied to both `aggregate_metric` and `force_decline_summary`.
  Three regression tests added. Demo β data has no peak ties so
  numerical output is unchanged on this dataset, but the fix
  matters the moment any real isometric force trace is loaded.
  *Status: shipped 2026-05-03.*
- **Fresh-chat protocol** for any Senefeld-facing demo — the
  v6.5.0 walkthrough caught conversation-history pollution
  ("Chunyu's thesis" leaked from prior chat, not from the
  framework). Codified in `examples/hip_lab_demo/beta/README.md`
  § "Walk this in a fresh chat."

### 0.b Leave-behind artifacts

A live walkthrough lands once and leaves nothing behind. Two
secondary artifacts close that gap:

- **5-minute screen-recorded video** with voiceover, structured
  around the three wow moments. Format: unlisted YouTube link or
  attached `.mp4`. Lets Senefeld re-watch and forward to one
  colleague. Production cost: ~2 hours including retakes.
- **One-page summary** mapped to the IRB-coordinator question
  shape (what data enters; what leaves the machine; what is
  retained; what is purged on consent revocation). Plain language
  with one technical block. Production cost: ~30 minutes draft
  plus boss review.

PyInstaller bundling and an end-user-runnable zip are explicitly
deferred — both increase install friction without materially
changing the meeting outcome.

### 0.c Vault decision-log entry

The Camp A commitment from §1 of this document is recorded in
the Obsidian vault at
`projects/mcp-middleware/decisions/camp-a-commitment.md` so the
v6.2-era fork is not silently re-litigated in the next session.

## Phase 1 — Senefeld meeting and lab-role scoping

This phase fires the moment Senefeld replies and a meeting is
scheduled. It is calendar-bound; nothing in §2+ can begin until
this phase resolves.

The meeting is not about MCP. It is about the lab role:
December graduation timing, Spring MS in Ex Phys advising, study
involvement, project ownership, and rec letter. MCP is a
**side capability** mentioned in passing — coding capability as
a sidenote per the 2026-04-21 follow-up email. The demo is shown
only if Senefeld asks or there is natural opening.

Outputs of this phase:

- Lab role agreement (or refusal); MS advising decision; named
  study Saahas joins (if any); IRB-protocol amendment timing.
- Whether MCP becomes a tool the lab will pilot, or stays a
  personal portfolio piece. Both outcomes are usable; only the
  first triggers Phase 2+.

If Senefeld declines on advising or lab role: §2+ pivot toward
the (b) end-state — public-quality artifacts without a named
pilot. The work is not wasted; the deliverable shape changes
from "HIP Lab uses this for a real study" to "credible repo +
notebook adoptable by an unrelated PI."

## Phase 2 — Data child for the actual lab data shape

Conditional on Phase 1 producing a real-data pilot. HIP Lab
runs isometric handgrip / force / EMG protocols (Hunter & Senefeld
2024, *J Physiol*). Likely real data shape:

- Force from a load cell at 1–2 kHz raw (BIOPAC, Delsys, or
  similar);
- Surface EMG at 1–2 kHz raw plus rectified envelope at lower
  rate;
- Multi-channel (multiple muscles per subject);
- Output formats: MATLAB `.mat` (Delsys Trigno default), CSV
  exports from an internal pipeline, or proprietary BIOPAC
  `.acq` files.

Branch on what the lab actually exports:

- **CSV exports** — [csv_dir child](../../src/tailor/children/csv_dir/)
  handles this with metadata sidecar configuration. Effort: 2–3
  days, mostly schema mapping. The synthetic demo β already
  validates this path on the 1 Hz envelope shape; real data will
  need confirmation that 1–2 kHz raw rates work within Tier-1
  token budgets (likely require pre-aggregation or downsampling
  in the child's ingest path).
- **`.mat` files** — new child from
  [`children/template/`](../../src/tailor/children/template/),
  using `scipy.io.loadmat`. Effort: 3–4 days with Claude
  assistance, including shape-contract tests.
- **`.acq` files** — same pattern, using `bioread` or `wfdb`.
  Effort: 4–5 days, vendor format quirks likely.

Mandatory regardless of branch: real `purge_cache()`
implementation (no template no-op stub), shape-contract tests
adapted from `tests/children/template/`, and registration in
[__main__.py](../../src/tailor/__main__.py) with
cloud-sync warning surface.

Gates: `ci-gate-runner` SHIPPABLE +
`integration-auditor --invariant=schema-drift` clean +
`mcp-protocol-auditor` PROTOCOL OK. The new child must be tested
against one real file from HIP Lab, not synthetic.

## Phase 3 — Lab-specific PHI scrubber

Conditional on Phase 2. The default `PHIScrubber` is a no-op by
design (ADR 0003). HIP Lab data needs an institutional subclass.

The scope is broader than field-name dropping:

1. **Direct identifiers** — HIPAA Safe Harbor §164.514(b)(2)
   fields. Drop or one-way hash.
2. **Quasi-identifiers** — timestamps coarsened to date-only or
   week-of-study; demographics bucketed; small cells suppressed.
3. **Pattern quasi-identifiers** — measurement-timing patterns
   that re-identify (e.g. shift workers); decision per-study with
   the PI.
4. **Sidecar schema validator** — `csv_dir.metadata_schema`
   config knob fail-closing on denied field names. Closes the
   open ROADMAP item.
5. **Distinct `scrubber_id`** — per ADR 0003, every audit row
   must provably reflect a real scrubber rather than the no-op
   default. The `scrubber_warning` seam (v6.3.1) makes
   misconfiguration loud.

Gate: `phi-irb-risk-reviewer` returns NO RISK or closed WATCH on
all six lenses. `red-team-reviewer` runs against the PASS verdict
— the v6.3.1 GPS-coarsening fix is precedent that a PHI verdict
can ship a re-identification path without adversarial pairing.

## Phase 4 — IRB-template fillable sections + operational runbook

Conditional on Phases 2 and 3. Two artifacts.

### 4.a IRB-template fillable sections

Most IRB committees use institutional templates rather than
free-form documentation. Produce sections that map onto the
lab's IRB template fields:

- **Data flow** — one-page diagram. What enters, what leaves
  the machine, what is retained, retention period, purge
  conditions. Sources: ADRs 0001 / 0003 / 0009 / 0012 / 0013
  collapsed to non-engineer-readable prose.
- **Consent language** — tier-by-tier mapping. What the
  participant consents to at each tier; how revocation works;
  what is preserved (vault notes per ADR 0013) versus purged
  (cached biometric data).
- **Audit-trail example** — annotated `audit.db` dump showing
  what an IRB coordinator sees when asking "who accessed P004's
  data on what date." Includes the `oracle_*` provenance columns
  (v6.6+) and the cooperation-loop columns (v6.7+).
- **Deployment requirements checklist** — PHI scrubber subclass
  installed; `scrubber_id` distinct from default; vault path off
  cloud sync; Ollama tier documented (if used); storage capacity
  sized for retention.

### 4.b Operational runbook

What Phase 4.a's IRB sections do not cover and what IRBs will
ask about:

- Server crashes mid-session — audit log durability, recovery
  steps;
- `audit.db` filling disk — rotation policy or sized cap;
- Vault corruption — recovery from filesystem source-of-truth
  (markdown is canonical; `vault.db` is a rebuildable index);
- Ollama unreachable — NullBackend fallback per ADR 0022, what
  the analyst sees;
- Analyst hand-off — who has the keys, what survives departure.

Gate: a non-engineer (PI or IRB coordinator) reads both artifacts
and answers the institution's standard data-governance checklist
without asking the developer. Tested against an actual person.

## Phase 5 — Vault-freeze for replication packaging

Conditional on Phases 2 and 3 only — independent of Phase 4.

Builds a `tailor freeze` CLI subcommand (or `vault_freeze`
tool) producing a `.zip` containing:

- Vault markdown files plus frontmatter (verbatim copy);
- `audit.db` filtered to the freeze timestamp;
- `user_config.json` snapshot — the configuration that produced
  the analysis (without this, the freeze is not reproducible);
- Package version plus child version pins (read from
  `__init__.py`);
- Manifest of all `subject_id`s in audit rows;
- SHA-256 hash file over every contents entry (tamper-evidence);
- `freeze_meta.json` with timestamp, package version,
  `scrubber_id`, and analyst's note on what the freeze
  represents;
- An audit row recording the freeze itself (per ADR 0001 the
  freeze is itself a tool call).

Gate: a person with no Python installed opens the zip on a
different machine, reads the manifest, and answers "which version
of the framework, which scrubber, which subjects, what time
range." Tested against the actual lab analyst.

Effort: 3–5 days with Claude assistance.

## Phase 6 — Public-dataset credibility notebook

Independent of Phases 2 / 3 / 5. Can run in parallel with Phase 1
calendar-wait.

The deliverable is **not** "reproduce a published figure." Most
published analyses do not release code; reproduction is a
research engagement, not a deliverable. The deliverable is
**recover the dataset's own documented descriptive statistics**
end-to-end through the framework's tier model.

Candidate datasets:

- **OhioT1DM** (CGM) — freely downloadable after DUA signing
  (1–3 weeks). Per-subject time-in-range, glucose variability,
  postprandial response baselines are documented.
- **PhysioNet Sleep-EDF** — open, sleep-stage distribution
  baselines documented. Some subsets require credentialing.

The notebook demonstrates: ingest → Tier-1 analysis →
vault cross-session memory → audit log scoping by `subject_id`
→ freeze snapshot. Output numbers must match the dataset's
published reference within tolerance.

Gate: an unrelated researcher in the target domain runs the
notebook end-to-end and the Tier-1 numbers reproduce documented
descriptive statistics.

Effort: 1–2 weeks calendar (DUA acquisition + notebook
development).

## Phase 7 — Pilot deployment to HIP Lab

Conditional on Phases 1 through 4 (5 and 6 strongly recommended
for credibility but not blocking).

1. Install on the analyst's machine — in person or screen-share.
   `uv tool install` is fine for confident users; painful for
   clinical-data analysts.
2. Configure `user_config.json` with the lab's PHI scrubber,
   real `csv_dir.path`, real `vault_path`.
3. Walk through one real analysis session — the analyst drives,
   you observe and patch live.
4. Document every issue encountered.
5. Schedule a five-day check-in. Most issues surface in days
   2–5 of unsupervised use.

Gate: the analyst runs one full session unsupervised end-to-end
(ingest → Tier-1 report → vault note → freeze) and reports back
without help.

## Phase 8 — In-use validation (the actual end-state gate)

Four-week observation period. Two hours per week of Saahas's
time, mostly passive.

- Does the analyst use the tool weekly without prompting?
- Do they hit blockers that did not surface in Phase 7?
- Does the PI cite an artifact (vault note, audit row, freeze)
  in any conversation?
- Does the analyst ask for any tool that does not exist?

After four weeks: structured retrospective with PI plus analyst.
Three questions:

- Would you keep using it if I disappeared tomorrow?
- What is the one thing that would make you stop?
- What is the one thing missing that would make this 2× as
  useful?

This is the only gate that validates *researcher utility* as the
project's stated north star ([ADR 0011 § Personas](../adr/0011-promotion-policy.md)).
Everything before this is necessary infrastructure; this is the
proof.

## Dependency map

```
Phase 0 (pre-meeting work)              ← in flight; produces meeting artifacts
    ║                                       and survives meeting slip
    ║  parallel with:
    ║  Phase 6a: public-dataset DUA acquisition (1–3 weeks calendar)
    ║
    ▼
Phase 1 (Senefeld meeting + lab role)   ← gates everything below
    │                                       calendar-bound on email reply
    │
    ├── Phase 2 (data child for HIP Lab's actual shape)
    │       └── Phase 3 (lab-specific PHI scrubber)
    │               ├── Phase 4 (IRB sections + runbook)  ┐
    │               ├── Phase 5 (vault-freeze)            │ parallel
    │               └── Phase 6b (notebook on already-DUA'd data) ┘
    │                       └── Phase 7 (HIP Lab pilot install)
    │                               └── Phase 8 (4-week observation)
    │
    └── (if Phase 1 forks to refusal: pivot to public-quality
         artifacts only — Phases 5 + 6 + adapted 4 produce a
         credible (b)-shaped end-state without a named pilot)
```

## Calendar estimate

- **Phase 0**: 2 weeks active work, in flight; produces artifacts
  that bank value if the meeting slips.
- **Phase 1**: gated on email reply (overdue); meeting + role
  scoping ~1–2 weeks calendar from the reply itself.
- **Phases 2–7 active development with Claude assistance**:
  ~5–7 weeks active work spread across IRB / data-access /
  back-and-forth calendar that does not compress.
- **Phase 8 observation**: 4 weeks calendar, mostly passive.

**Total realistic calendar**: 2.5–3.5 months from Senefeld's
reply landing.

The single largest determinant of total elapsed time is not
development velocity. It is the IRB-protocol amendment / DUA
acquisition cycle, which runs at academic-medicine pace
regardless of how much Claude accelerates the code.

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Senefeld's reply does not come, or declines on advising | Medium | Phase 6 (public-dataset notebook) banks credibility independent of HIP Lab. Pivot to (b)-shaped end-state. |
| Real lab data has undocumented schema quirks | High | Phase 2 begins with reading one real file before coding (`integration-auditor --proposal-mode` on the plan). |
| IRB pushback requires architectural changes to the framework | Medium | `phi-irb-risk-reviewer` + `red-team-reviewer` adversarial pairing in Phase 3 surfaces the most likely objections before submission. |
| Ollama does not run on the analyst's hardware | Medium | `NullBackend` is the safe default per ADR 0022. The cooperation-loop fields degrade to empty lists; deterministic Tier-1 numbers and vault tools work without Ollama. Document tier requirements in deployment checklist. |
| Storage exceeds scope (esp. high-rate force / EMG) | Medium | Phase 0 sizing pass against one real file; document retention/archive policy in Phase 4.b runbook. |
| Analyst stops using the tool after Phase 7 | High (the actual end-state failure mode) | Phase 8 observation period is the only structural detector; build in the four-week check-in by default. |
| Saahas's MS application or career timeline forces premature ship | Low–Medium | The (b)-shaped artifacts (notebook + IRB sections + freeze) are themselves portfolio-cite-able even without (a) landing. The blueprint is structured so that each phase produces standalone value. |

## Boss decisions still in queue (parked, not blocking this blueprint)

These are flagged in the Obsidian vault snapshot as queued
decisions, distinct from this blueprint's scope. They are listed
here for completeness so they do not silently drift.

| Decision | Severity | Impact on this blueprint |
|----------|----------|-------------------------|
| ADR 0018 reading (uniform Safe Harbor vs consent-as-shield) | HIGH, IRB-relevant | Directly shapes Phase 3 PHI scrubber scope. Worth resolving before Phase 3 begins. |
| ADR 0019 reading (cost-gate Tier binding) | MEDIUM | Engineering hygiene; no Phase impact. |
| ADR 0020 reading (typed Protocols) | MEDIUM | Engineering hygiene; no Phase impact. |
| ADR 0021 reading (framework-honors-health-data-analysis-domain) | TBD | Likely framing-shaped; possibly affects Phase 4.a IRB framing. |
| ADR 0022 flip-to-Accepted timing | — | Local-LLM guardian; flip should follow first real Ollama deployment in Phase 7. |
| ADR 0023 flip-to-Accepted timing | — | Cooperation loop; PR2 effectiveness telemetry from Phase 7+ is the natural signal. |
| Framework concurrency model | DEFERed | Multi-analyst future; not blocking single-analyst pilot. |

## Out of scope for this blueprint

- Camp B (personal-data-owner) deliverables — explicit deferral.
- The remaining v6.6.0 v0 deferred items per ADR 0022 § "Out of
  scope" (verifier mode, sanitizer / proxy mode, conductor-mode
  toggle, citation-grounding enforcement, migration of all 45
  remaining tools to oracle mediation, IRB threat model for
  prompt-injection, performance characterization, pilot-wizard
  tier-detection, real-Ollama end-to-end smoke). All speculative
  product expansions; revisit if Phase 8 surfaces concrete demand.
- Multi-participant child contract widening (single-account-per-domain
  YAGNI'd in v6.4.0; revisit when first multi-participant child
  surfaces).

## Revision discipline

This document is the working plan, not a permanent record. Revise
when:

- A phase resolves (mark complete; record what shipped).
- An anchoring assumption from §1 changes (note the change, surface
  the affected phases).
- A risk materialises (note the realisation; describe the
  mitigation actually used).

The Obsidian vault entry at
`projects/mcp-middleware/delivery-blueprint.md` mirrors this file
for cross-session memory. They drift if neither is touched —
treat the repo file as canonical and the vault entry as a
weekly-refreshed mirror.

# HIP Lab demo — *realistic* variant (multimodal)

> **Off-blueprint Senefeld-meeting detour.**  Built for a live
> walkthrough at the next HIP Lab meeting if Dr. Senefeld
> expresses interest.  See project memory
> `project_off_blueprint_detour_2026_05_04`.

This variant ships **paired multimodal fixture data** to demonstrate
the framework's existing cross-child composition seam — one node
per data source (`force_csv`, `emg_csv`, future `mrs_*`), all keyed
on shared `subject_id` per ADR 0009, all logged to one `audit.db`
per ADR 0001.  The demo argument: *each modality is its own
ChildMCP; framework infrastructure already composes them.*

As of v6.9.0 (per [ADR 0024](../../../docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md))
the demo's fixtures live in the package's bundled-fixtures tree
(`src/tailor/_fixtures/hip_lab_demo_realistic/`) and ship
inside the wheel.  A non-technical recipient (PI, family member,
collaborator at another institution) can run the entire walkthrough
from a pre-built wheel sent via Drive or email — no GitHub access,
no source clone, no env-var-by-hand.  See
[WINDOWS_QUICKSTART.md](WINDOWS_QUICKSTART.md) for that path.

---

## TL;DR (in-repo developer)

```bash
# Non-interactive end-to-end check (no Claude in the loop).
# Scaffolds a fresh tour into a temp dir and asserts the bridge
# numbers; cleans up on exit.
python examples/hip_lab_demo/realistic/rehearse.py

# Live demo path: scaffold + register with Claude Desktop in one shot.
tailor tour
```

Then walk Senefeld through the
[**Walkthrough script**](#walkthrough-script-meeting-time-510-min)
below — or for live use, print [`CUE_CARD.md`](CUE_CARD.md), which
collapses the walkthrough to one page.

To regenerate the bundled fixtures after a `generate.py` change:

```bash
python examples/hip_lab_demo/realistic/generate.py
```

`generate.py` writes directly into the package's
`_fixtures/hip_lab_demo_realistic/` tree, so the next
`tailor tour` (or `pip install`-built wheel) picks up the
regenerated fixtures with no further plumbing.

---

## Pre-meeting setup (do BEFORE the meeting — 5 min)

Run this once on the laptop you'll demo from. Idempotent, safe to
re-run.

### 1. Rehearse end-to-end (no Claude in the loop)

```bash
python examples/hip_lab_demo/realistic/rehearse.py
```

Calls each tool the walkthrough exercises and prints PASS / FAIL
per assertion — most importantly the *bridge number* (S004's
`peak_envelope_window_mean` should land around 238 µV to match the
prior vault note's "around 240 µV").  Exit code 0 = demo is
rehearsal-ready; non-zero = at least one number drifted from
[`CUE_CARD.md`](CUE_CARD.md)'s expected ranges, identifying the
failure before the meeting rather than during.

Rehearse scaffolds its own temp tour and tears it down on exit, so
your `~/.tailor/` directory stays untouched. Re-run any time
`generate.py`, the seed moment, or the tour module changes.

### 2. Scaffold the live tour and register with Claude Desktop

```bash
tailor tour
```

This one command:

- Copies bundled fixtures into `~/.tailor/demos/hip-lab/`
- Writes `user_config.json` with absolute paths
- Indexes the seed vault moment into `data/vault.db`
- **Writes a Claude Desktop entry that bakes
  `TAILOR_CONFIG_DIR` and `TAILOR_DATA_DIR` into the
  `env` block** — the recipient never types an env var by hand

Output ends with a "Tour scaffolded successfully" banner naming
the target dir, the Claude Desktop config path, and the entry
name (`biosensor-tour-hip-lab`).

Pass `--force` to refresh after a regen of the bundled fixtures.
Pass `--no-claude-desktop` for headless / CI use.

### 3. Restart Claude Desktop

Fully quit (system-tray → Quit on Windows; ⌘Q on macOS), then
re-open. The new MCP server appears under the entry name above.

### 4. Verify it loaded

In a fresh Claude Desktop chat, type:

> *"List the available Tailor tools."*

You should see ~55 tools across `force_csv`, `emg_csv`, `vault_*`,
`strava_*` (Strava is the worked-example child; loads but errors
without OAuth — ignore for this demo), and `ask_local_oracle`.

If `force_csv` or `emg_csv` is missing, run `tailor tour
--force` to rewrite the user_config and restart Claude Desktop.

---

## Walkthrough script (meeting time — 5–10 min)

Read these prompts to Senefeld out loud or paste them into
Claude Desktop.  Each step has a "what to point out" line —
that's what makes the demo land.

### Step 1 — Set the frame (30 s)

> "This is a synthetic-data demo so I can show the *framework*
> without using any real participant data.  Sixteen subjects on
> a hybrid isometric protocol — 30% MVC sustained for 60 seconds
> with brief MVC probes every 15 seconds.  The shape is informed
> by the Hunter and Senefeld 2024 *J Physiol* sex-differences
> paper.  Three streams per subject — force, EMG envelope, and
> a 31P-MRS PCr/Pi stub.  All three streams keyed on shared
> subject_id."

**What to point out:** the multimodal storyline matches what HIP
Lab is actually building toward (custom MR-conditional dynamometer
+ EMG + 31P-MRS).

### Step 2 — Show the cohort sex difference (1 min)

Paste to Claude Desktop:

> *"Summarize peak isometric force across the cohort, grouped by
> sex.  Use the force_cohort_summary tool with metric=max."*

Expected response (Claude calls `force_cohort_summary` with
`group_field=sex, value_column=force_N, metric=max`):

> "Cohort summary by sex:
> - F (n=8): mean peak ≈ 200 N, range ≈ 180–240 N
> - M (n=8): mean peak ≈ 276 N, range ≈ 260–360 N"

**What to point out:** *"This call reduced 96,000 force samples
to two summary rows.  None of the raw samples ever entered the
LLM context — the framework's Tier 1 ran the reduction
server-side, then handed Claude the eight numbers it needed.
Same call against real data; same numbers."*

### Step 3 — Show the per-subject force summary for S004 (1 min)

> *"Run force_summary on S004's trial."*

Expected response:

> "S004 force_summary:
> - peak: 229.3 N
> - mvc_window_mean_250ms: 226.0 N (Sánchez-2015 250 ms window)
> - sample_rate_hz: 100.0
> - duration_s: 60.0"

**What to point out:** *"The Sánchez-2015 MVC window definition is
publication-aligned — mean over a 250 ms window centered on the
peak, not the instantaneous peak.  That's the definition Wang and
Senefeld 2026 use in the dyno-validation work.  Window math runs
server-side; the framework hands the LLM one number."*

### Step 4 — Show the EMG envelope summary for S004 (1 min)

> *"Now run emg_envelope_summary on S004's EMG trial."*

Expected response:

> "S004 emg_envelope_summary:
> - peak_envelope_window_mean: 238 µV
> - end_window_mean: 97 µV
> - **fatigue_index_pct: 59.4 %**
> - rms: 107 µV
> - integrated_emg: 6097 µV·s
> - sample_rate_hz: 100.0
> - duration_s: 60.0"

**What to point out:** *"S004's peak envelope window is sitting at
~238 µV — well above where the rest of the female cohort peaks,
which group in the 150–205 µV range.  Her fatigue index of 59.4 %
is cohort-typical; the unusual signal is the absolute amplitude,
not the decline rate.  Hold this peak — we're about to find out
it isn't new."*

### Step 5 — The cross-session-memory wow moment (1.5 min)

> *"Search the vault for any prior notes about subject S004."*

Expected response (Claude calls `vault_search_notes` with
`query=S004` or `subject_id=S004`):

> "I found one moment dated 2026-04-20 titled *S004 — atypical
> EMG/force decoupling under fatigue*.  The note flags S004's
> peak envelope window sitting **around 240 µV** — well above
> the rest of the female cohort, whose peak envelopes group
> in the 150–205 µV range.  The fresh emg_envelope_summary
> just returned peak_envelope_window_mean of **238 µV** — same
> elevated amplitude, two weeks later.  The note explicitly
> notes that S004's *fatigue index* is cohort-typical — the
> unusual signal is the absolute amplitude, not the decline
> rate.  It suggests overreaching, an undisclosed upper-
> extremity issue, or unrecovered neural fatigue, and recommends
> a training-load self-report and a re-run on a fresh day."

**What to point out (this is the headline moment):** *"Two weeks
ago, the analyst flagged S004's peak EMG envelope around 240 µV —
well above the rest of the female cohort.  The fresh
emg_envelope_summary just returned 238 µV.  Same subject, same
elevated amplitude, two weeks apart.  The framework didn't pull
this from a vector embedding or fuzzy match — it pulled it
because the analyst keyed the note on subject_id=S004 two weeks
ago, and the fresh emg_envelope_summary call carried subject_id=
S004 too.  Both calls landed in the same audit.db, same subject_id
column.  An IRB reviewer two months from now can reconstruct
exactly what I asked, what numbers I got, and what prior context
the LLM surfaced."*

### Step 6 — Show the audit log (30 s)

If Senefeld is interested in the IRB story, run:

> *"How many calls have been logged to the audit log this session,
> and what subject_ids have been queried?"*

Claude can answer from its session memory or via a status-style
inspection.  Or open the audit DB directly:

```bash
sqlite3 ~/.tailor/demos/hip-lab/data/audit.db \
  "SELECT tool_name, subject_id, called_at FROM audit_log ORDER BY id DESC LIMIT 10;"
```

**What to point out:** *"Every tool call lands here — timestamp,
domain, tool, tier, parameters, token estimate, outcome, latency,
optional subject_id.  Durable evidence for IRB reviewers, for
co-authors re-running the analysis, for participants asking what
their data was used for."*

### Step 7 — Close (30 s)

> *"That's the demo.  The framework is local-first, the streams
> never leave the analyst's machine for Tier 1 calls, the audit
> log is the IRB-grade backbone, and the vault is the
> longitudinal memory layer.  Multimodal composition isn't a new
> feature — it's the existing infrastructure working when each
> data source is its own ChildMCP keyed on shared subject_id."*

---

## The three wow moments (memorize these)

1. **Cohort summary reduces 96,000 raw samples to 2 numbers
   server-side**, no biometric data enters the LLM context.
2. **Cross-session memory** — a vault note from "two weeks
   earlier" surfaces alongside fresh data on the same subject,
   keyed on `subject_id`.
3. **The audit log records every call** — tool, parameters,
   subject, outcome — IRB-grade reconstruction.

---

## Fallback if something fails live

| What breaks | What to do |
|---|---|
| Claude Desktop doesn't see the tools | Restart Claude Desktop fully (system-tray Quit, then re-open). If still missing, run `tailor tour --force` and restart again. |
| `force_csv` returns "directory not found" | Re-run `tailor tour --force` — re-writes user_config.json with current absolute paths. |
| Vault search returns nothing | The vault.db wasn't indexed — `tailor tour --force` re-runs the indexing step. The seed moment file lives at `~/.tailor/demos/hip-lab/vault/moments/2026-04-20-s004-emg-force-decoupling-suspected.md` if you want to confirm it exists. |
| `force_summary.decline_pct` returns null | Known limitation — use `peak` and `mvc_window_mean_250ms` instead.  Don't acknowledge this gap proactively; if Senefeld asks, see [Pre-armed answers](#pre-armed-answers-if-senefeld-asks) below. |
| You can't remember what to say | Read the **Walkthrough script** above straight off the page — every step has a "what to point out" line. |

---

## Pre-armed answers if Senefeld asks

Three follow-up questions are most likely.  Each has a physiologically-
honest scripted answer below — read it straight off the page, no
improvisation needed.  None of these answers requires admitting a
defect; they all frame the gap as a deliberate design choice with a
defensible follow-on.

### Q1 — *"What does her force decline look like over the trial?"*

> "Force decline on a hybrid sustained-plus-probes protocol like
> this isn't monotone — the MVC probes every 15 seconds interrupt
> the decline, so a single decline-pct number isn't the right
> reduction shape.  The principled view is peak-of-each-MVC-probe
> over time, which we'd build as a small follow-on tool — a
> hybrid-protocol-aware decline helper.  For today, the headline
> on the force side is peak and the Sánchez 250 ms MVC window —
> 229 N and 226 N for S004, both well-defined under hybrid
> protocols.  The EMG fatigue index is the cleaner cohort-
> comparable number on this fixture."

**What to point out:** *"That's a real follow-on — not a hidden
limitation.  The framework's pure-function processing layer means
adding a new reducer is a 50-line pull request, not a
re-architecture."*

### Q2 — *"What are the cohort-level decline norms?"*

> "Cohort norms here are still being established — n=8 per arm
> with intentional within-group overlap means this fixture is
> dimensioned for demo-storytelling fidelity, not publication-
> grade inference.  On real data the same `force_cohort_summary`
> call would aggregate however many subjects you'd loaded, by
> any sidecar field — sex, age band, training status, intervention
> arm.  Same call, same shape, real numbers."

**What to point out:** *"This is exactly the call HIP Lab would
run on a 16-subject pilot once the dyno-validation work
publishes — drop the CSVs in a directory, write a 4-line
metadata.json sidecar, run one tool call."*

### Q3 — *"How does this differ when you point it at real data?"*

> "Same code path, same calls, same numbers.  The framework is
> data-source-agnostic at Tier 1 — `force_csv`, `emg_csv`, future
> `mrs_csv` are sibling ChildMCPs that all hit the same router
> pipeline: param validation, consent gate, cost gate, audit log,
> `_meta` provenance stamp.  The fixture's only synthetic
> property is the numbers themselves; everything else — file
> layout, metadata sidecar, subject_id keying, vault notes — is
> exactly what a real study would look like."

**What to point out:** *"There's no demo-mode path through the
code.  The fixture is just CSV files; the framework can't tell
synthetic from real."*

---

## Claude weather — recovery prompts

Live demos die more often on LLM variance than on tool errors.
Claude can be terse, skip a tool call, hallucinate a number, or
reach for the wrong tool.  None of those are framework defects —
they're prompt-cadence issues.  Each row below is a prompt you can
paste verbatim to recover, no improvisation needed.  These also
appear (one-line summaries) in [`CUE_CARD.md`](CUE_CARD.md) for
live use.

### Symptom: Claude answered without calling a tool

This is the most common drift mode.  Claude has prior training-data
priors about isometric force traces and EMG and may answer from
those rather than calling the actual MCP tool.

> *"Please call the actual MCP tool — I want to see the numbers
> come from the framework, not from your prior knowledge."*

If it persists, name the tool: *"Use force_summary on
S004_force.csv and read the numbers from the tool output."*

### Symptom: Claude was terse, didn't connect step 5 back to step 4

The wow moment requires Claude to bridge the fresh
`peak_envelope_window_mean` (step 4) to the prior vault note (step
5).  If Claude just retrieves the note and stops, prompt the bridge:

> *"Compare the peak_envelope_window_mean you just returned in
> step 4 against the peak amplitude the prior vault note describes.
> Same number?"*

### Symptom: Claude hallucinated a number

Round-tripping numbers through the LLM's narrative occasionally
produces a value that doesn't match the tool output.  The recovery
is to demand a re-read:

> *"What's the exact number the tool returned?  Read it directly
> from the tool output — don't paraphrase."*

### Symptom: Claude reached for the wrong tool family

Two failure shapes:
- *csv_cohort_summary instead of force_cohort_summary* — Claude
  defaults to the generic CSV child rather than the dedicated
  `force_csv` child.
- *strava_* tools — Strava is loaded but unauthenticated; its
  tools error.  Claude may try one anyway.

Recovery:

> *"Use force_cohort_summary, not csv_cohort_summary.  force_csv
> is the dedicated child for force data in this demo."*

### Symptom: Claude stripped the subject_id prefix

Sometimes Claude reads "S004" as "subject 4" and passes
`subject_id=4` or omits it entirely.  ADR 0009 keys notes on the
literal string, so this breaks the wow moment.

> *"The subject_id is the literal string S004 — please use it
> verbatim in the subject_id parameter."*

### Symptom: Vault search returns nothing

This is an operator action, not a Claude prompt — `vault.db`
wasn't indexed when the tour scaffolded.  Exit the chat, run
`tailor tour --force`, restart the demo from step 1.

---

## What's here

```
examples/hip_lab_demo/realistic/        # Dev-side scaffolding
  generate.py             Seeded synthetic generator (random.Random(20260504))
                          — writes into the package's bundled-fixtures
                          tree (see below), not into this directory
  rehearse.py             Non-interactive end-to-end check; scaffolds a
                          fresh tour into a temp dir and asserts bridge
                          numbers
  README.md               This file
  CUE_CARD.md             One-page printable cue card for live use
  WINDOWS_QUICKSTART.md   Standalone Windows quickstart for non-technical
                          recipients (mom, Senefeld) — wheel-install path

src/tailor/_fixtures/hip_lab_demo_realistic/   # Bundled fixtures
                                                       # (ship in the wheel
                                                       # per ADR 0024)
  force/                  Load-cell force traces, 100 Hz × 60 s
    metadata.json         ADR 0015 sidecar (subject_id, sex, group, baseline_mvc_N)
    S001_force.csv … S016_force.csv
  emg/                    Surface-EMG envelope, 100 Hz × 60 s
    metadata.json         ADR 0015 sidecar (subject_id, sex, group, envelope_baseline_uV)
    S001_emg.csv … S016_emg.csv
  mrs/                    31P-MRS PCr/Pi stub, 0.05 Hz × 60 s
    metadata.json         ADR 0015 sidecar (subject_id, sex, group, modality)
    S001_mrs.csv … S016_mrs.csv
  vault/moments/          Pre-seeded analytical vault
    2026-04-20-s004-emg-force-decoupling-suspected.md
```

**Total bundled in wheel:** 48 CSVs + 3 sidecars + 1 seed moment ≈ 3 MB.

## Subject composition

- 16 subjects, 8 F / 8 M intermixed by ID
- 8 control, 8 intervention (orthogonal to sex so cohort
  comparisons can intersect group × sex)
- Female cohort: lower MVC (180–240 N), shallower decline rate
- Male cohort: higher MVC (260–360 N), steeper decline
- Group overlap is intentional so cohort comparisons read as
  real data, not stat-shopped fixtures
- **Subject S004** has a deliberate EMG/force decoupling — her EMG
  envelope runs ~45 % above the female-cohort baseline while her
  force trace tracks normally.  This is the headline wow moment.

## Reproducibility

Every CSV under `_fixtures/hip_lab_demo_realistic/` regenerates
deterministically from `generate.py` — `random.Random(20260504)`
is the seed; re-running overwrites all 48 files in place.  Per
ADR 0008 the seeded-PRNG-off-the-analytical-path exception applies
via the `examples/**/generate.py` glob — generators stay out of
the wheel; only their generated artifacts ship (codified in
[ADR 0024](../../../docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md)).

## Status

- `force_csv` and `emg_csv` children: **registered in `__main__.py`
  conditionally** — load when their respective blocks are present
  in `user_config.json`.  The off-blueprint posture has shifted
  from "unregistered until meeting outcome known" to "registered
  conditionally so the demo works at the meeting; full integration
  into the delivery blueprint happens after the meeting outcome
  is known."
- `mrs_*` child: **not built** — MRS files ship as storyline
  scaffolding only.

## Known limitations

- **`force_summary.decline_pct` and `time_to_50pct_drop_s` return
  `None` on this fixture** because the `csv_dir`-inherited
  `force_decline_summary` helper is designed for monotone-decline
  shapes (matching the β variant) and the realistic fixture's
  hybrid sustained+probes shape interrupts monotone decline.  The
  values that DO work end-to-end on this fixture: `peak`,
  `mvc_window_mean_250ms` (Sánchez 250 ms window),
  `force_cohort_summary`, and on the EMG side every field of
  `emg_envelope_summary` including `fatigue_index_pct`.  A hybrid-
  protocol-aware decline helper is a defensible follow-on.
- **The MRS files have no reading child** — a future `mrs_csv`
  child would consume them.  They ship to demonstrate the
  storyline.
- **Sex-difference cohort means are not statistically powered** —
  n=8 per arm with intentional within-group overlap.  Synthesis
  is for demo-storytelling fidelity, not publication-grade
  inference.

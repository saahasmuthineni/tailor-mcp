# HIP Lab demo — cue card (realistic variant)

**One page.  Print it, or keep it on a second monitor.**

> **Before starting:** open a *fresh* Claude Desktop chat — no prior
> conversation history with HIP Lab, S004, biosensors, or the vault.
> Prior history pollutes the demo (snapshot warning under
> `LLM conversation-history pollution`).

---

## Headline numbers — memorize these (S004)

| Quantity | Value |
|---|---|
| Force peak | **229 N** |
| Force MVC window mean (Sánchez 250 ms) | **226 N** |
| EMG peak envelope window — **the bridge number** | **≈ 238 µV** |
| EMG peak — rest of female cohort | 150–205 µV (S004 is the outlier) |
| EMG fatigue_index_pct | 59.4 % — *cohort-typical, NOT the wow* |
| Cohort peak (force) — F (n=8) / M (n=8) | **≈ 200 N / ≈ 276 N** |
| Prior vault note | **2026-04-20** — flags S004 EMG peak ~240 µV |

**The bridge** is steps 4 → 5: the fresh
`peak_envelope_window_mean: 238 µV` matches the prior note's
"around 240 µV."  Same elevated peak, two weeks apart,
subject_id-keyed.  *Don't lean on `fatigue_index_pct` — it's
cohort-typical and a fatigue physiologist will catch any "this is
unusually steep" framing.*

---

## Walkthrough — 7 steps, ~6 minutes

| # | What you say or paste | Expected key result + what to point out |
|---|---|---|
| **1** | "Synthetic-data demo.  16 subjects, hybrid isometric protocol — 30 % MVC sustained 60 s with MVC probes every 15 s.  Three streams per subject (force, EMG envelope, MRS stub) keyed on shared subject_id." | *(frame only — no tool call)* Multimodal storyline matches HIP Lab's MR-conditional dyno + EMG + 31P-MRS direction. |
| **2** | *"Summarize peak isometric force across the cohort, grouped by sex.  Use force_cohort_summary with metric=max."* | F ≈ 200 N, M ≈ 276 N.  **"96,000 force samples reduced to 2 numbers server-side.  None of the raw samples entered the LLM context."** |
| **3** | *"Run force_summary on S004's trial."* | peak: 229 N, mvc_window_mean_250ms: 226 N.  **"Sánchez-2015 250 ms window — publication-aligned definition runs server-side; LLM gets one number."** |
| **4** | *"Now run emg_envelope_summary on S004's EMG trial."* | **peak_envelope_window_mean ≈ 238 µV** (vs cohort 150–205 µV).  fatigue_index_pct 59.4 % is cohort-typical.  **"The peak amplitude is the unusual signal — well above the female cohort.  Hold this peak — we're about to find out it isn't new."** |
| **5** | *"Search the vault for any prior notes about subject S004."* | 2026-04-20 moment surfaces flagging **peak ~240 µV**.  **"Same elevated peak amplitude, two weeks apart.  238 µV fresh, ~240 µV in the prior note.  subject_id-keyed retrieval, not vector embedding.  Both calls land in the same audit.db with subject_id=S004."**  *(headline moment)* |
| **6** | *"How many calls have been logged this session, and what subject_ids?"*  Or open `audit.db` directly. | ≥ 5 rows, subject_ids include S004.  **"Every call: timestamp, tool, subject, outcome, latency.  IRB-grade backbone."** |
| **7** | "Local-first, streams stay on the machine for Tier 1, audit log is IRB-grade, vault is longitudinal memory.  Multimodal composition is existing infrastructure — each modality is its own ChildMCP keyed on shared subject_id." | *(close — no tool call)* |

---

## Three wow moments

1. **Cohort summary reduces 96,000 raw samples to 2 numbers server-side.**  No streams entered the LLM context. *(step 2)*
2. **The same elevated EMG peak, two weeks apart.**  Prior note flags S004's peak around 240 µV; fresh tool call returns 238 µV.  Surfaced because the analyst keyed her note on subject_id=S004 — not vector embedding. *(steps 4 → 5)*
3. **Every call is in the audit log** — tool, parameters, subject, outcome. *(step 6)*

---

## Claude weather — recovery prompts

If Claude's behaviour drifts, say or paste one of these.  None require admitting a defect.

| Symptom | Recovery prompt |
|---|---|
| Claude answered without calling a tool | *"Please call the MCP tool — I want to see the numbers come from the framework, not from your prior knowledge."* |
| Claude was terse, didn't connect step 5 back to step 4 | *"Compare the peak_envelope_window_mean you just returned against the prior vault note from 2026-04-20.  Same number?"* |
| Claude hallucinated a number | *"What's the exact number the tool returned?  Read it directly from the tool output."* |
| Claude reached for `csv_cohort_summary` (returns MRS spectra, not force) | *"Wrong child — `csv_cohort_summary` operates on the MRS stream. Re-run with `force_cohort_summary` against the force data."* |
| `force_cohort_summary` returned 16 `column not found` load_errors | *(v6.9.0 footgun — fixed in v6.9.1; recovery prompt for older builds:)* *"Use `value_column='force_N'` (literal CSV header), not `'force'`. Or call `force_list_files` first to confirm headers."* |
| Same on `emg_cohort_summary` | *"Use `value_column='envelope_uV'` (literal CSV header), not `'envelope'`. Or call `emg_list_files` first."* |
| Claude listed S004 as "subject 4" or stripped the prefix | *"The subject_id is the literal string S004 — please use it verbatim in the subject_id parameter."* |
| Vault search returns nothing | *(operator action — exit chat)* Re-run `tailor tour --force`; vault.db wasn't indexed. |
| Tool list shows only `ask_local_oracle` + `strava_list_runs` (no force_*, emg_*, vault_*) | *(v6.9.x recipient footgun — fixed structurally in v6.10.2)* The recipient landed at a bare `tailor serve` without scaffolding. Ask Claude to *"call tailor_setup_help"* — it returns terminal-step instructions. Or skip the chat and run `tailor tour` from a terminal, then quit-and-reopen Claude Desktop. |
| `tour` reports "Tour scaffolded with N of M Claude Desktop registrations succeeded" | *(v6.10.4 partial-write surface)* One config path was written, the other failed. Most likely cause: Claude Desktop is still running and locks the config file. *(operator action — exit chat)* Fully quit Claude Desktop via the system tray (Quit, not close-window), then re-run `tailor tour --force`. |
| Claude Desktop installed from the Microsoft Store, no Tailor tools after `tour` + restart | *(v6.10.4 — Microsoft Store recipient path)* The Store version of Claude Desktop reads its config from a UWP-sandboxed path. If the recipient's first `tour` run happened before the Store app was ever launched (the sandbox dir doesn't exist until first launch), the entry only landed in the classic config. Have them launch Claude Desktop once, then re-run `python -m tailor tour --force` (or `tailor tour --force` if PATH is configured) from the same terminal. |

---

## Pre-armed answers if Senefeld asks (lead lines only)

Full scripts in [README → "Pre-armed answers if Senefeld asks"](README.md#pre-armed-answers-if-senefeld-asks).

| Question | Lead line |
|---|---|
| *"What does her force decline look like?"* | "Hybrid protocol interrupts monotone decline.  Principled view is peak-of-each-MVC-probe over time — a small follow-on tool, not a hidden limitation." |
| *"What are the cohort-level decline norms?"* | "n=8 per arm is dimensioned for demo fidelity, not publication inference.  Same call works on real data — `force_cohort_summary` aggregates by any sidecar field." |
| *"How does this differ on real data?"* | "Same code path, same calls, same numbers.  The fixture is just CSV files; the framework can't tell synthetic from real." |

---

*Last updated: 2026-05-04 (off-blueprint Senefeld-meeting detour).
Run `python rehearse.py` for a non-interactive end-to-end check
that all the numbers above match the current fixture.*

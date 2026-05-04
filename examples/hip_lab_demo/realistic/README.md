# HIP Lab demo — *realistic* variant (multimodal)

> **Off-blueprint Senefeld-meeting detour, 2026-05-04.**
> See project memory `project_off_blueprint_detour_2026_05_04`.

This variant ships **paired multimodal fixture data** to demonstrate
the framework's existing cross-child composition seam — one node per
data source (`force_csv`, `emg_csv`, future `mrs_*`), all keyed on
shared `subject_id` per ADR 0009, all logged to one `audit.db` per
ADR 0001.

The β variant ships everything in a single combined CSV per subject
(csv_dir-shape — heart rate + force + EMG envelope + RPE in one
file).  This *realistic* variant separates the streams the way real
lab equipment exports them, so the demo argument *"each modality is
its own ChildMCP"* lands honestly.

## What's here

```
realistic/
  generate.py             Seeded synthetic generator (random.Random(20260504))
  force/                  Load-cell force traces, 100 Hz × 60 s
    metadata.json         ADR 0015 sidecar (sex, group, baseline_mvc_N)
    S001_force.csv … S016_force.csv
  emg/                    Surface-EMG envelope, 100 Hz × 60 s
    metadata.json         ADR 0015 sidecar (sex, group, envelope_baseline_uV)
    S001_emg.csv … S016_emg.csv
  mrs/                    31P-MRS PCr / Pi stub, 0.05 Hz × 60 s
    metadata.json         ADR 0015 sidecar (sex, group, modality)
    S001_mrs.csv … S016_mrs.csv
```

**Total:** 16 subjects × 3 modalities = 48 CSVs ≈ 3 MB.

## Protocol

Hybrid isometric design — 60 s sustained contraction at 30 % MVC,
with brief MVC probes at t = 15 s, 30 s, 45 s, 60 s (3 s each).  The
shape is informed by Hunter & Senefeld 2024 (*J Physiol* 602.17,
sex differences in human performance) compressed for demo timing —
real 30 % MVC sustained contractions take 3–5 minutes to fatigue;
these traces use steeper-than-real fatigue rates so visible decline
happens within 60 s.

## Subject composition

- 16 subjects, 8 F / 8 M intermixed by ID
- 8 control, 8 intervention (orthogonal to sex so cohort
  comparisons can intersect group × sex)
- Female cohort: lower MVC (180–240 N), longer time to amplitude
  collapse, shallower decline rate (18–30 % at 60 s)
- Male cohort: higher MVC (260–360 N), steeper decline (28–42 %)
- Group overlap is intentional so cohort comparisons read as real
  data, not stat-shopped fixtures
- **Subject S004** is given a deliberate EMG/force decoupling — her
  EMG envelope runs ~45 % above the female-cohort baseline while her
  force trace tracks normally.  This is the "wow moment" — `force_csv`
  shows normal decline; `emg_csv` shows abnormal recruitment

## Demo storyline (preview — Phase 5 will expand)

```
analyst> show me S004's force decline alongside her EMG fatigue
         progression and PCr depletion across this trial

→ force_summary (file_id=S004_force.csv) — server-computed peak,
  Sánchez-2015 250 ms MVC window mean, time-to-50pct-drop, decline %
→ emg_envelope_summary (file_id=S004_emg.csv) — RMS, MAV, iEMG,
  fatigue index (peak window vs end window)
→ [mrs_csv child not yet wired — file ships to demonstrate the
   storyline only]

All three calls keyed on subject_id="S004", all three rows landed
in the SAME audit.db with the SAME subject_id column, all three
results carry the same _meta provenance stamp.  The analyst sees
multimodal composition; the IRB sees one auditable trail.
```

## Reproducibility

Every CSV in this directory is regenerable from `generate.py` —
`random.Random(20260504)` is the seed, and re-running the script
overwrites all 48 files deterministically.  Per ADR 0008 the
seeded-PRNG-off-the-analytical-path exception applies via the
`examples/**/generate.py` glob.

## Status

- `force_csv` and `emg_csv` children: **landed but not registered**
  in `__main__.py` (off-blueprint posture; resolves back into the
  delivery blueprint after the Senefeld-meeting outcome is known)
- `mrs_*` child: **not built** — MRS files ship as storyline
  scaffolding only
- Demo wiring (user_config.json, walkthrough script): **Phase 5
  follow-on**

## Known limitations

- `force_summary.decline_pct` and `time_to_50pct_drop_s` return
  `None` on this fixture because the `csv_dir`-inherited
  `force_decline_summary` helper is designed for monotone-decline
  shapes (matching the β variant) and the realistic fixture's
  hybrid sustained+probes shape interrupts monotone decline.  The
  values that DO work end-to-end on this fixture: `peak`,
  `mvc_window_mean_250ms` (Sánchez 250 ms window), `force_cohort_summary`,
  and on the EMG side every field of `emg_envelope_summary`
  including `fatigue_index_pct`.  A hybrid-protocol-aware decline
  helper is a defensible follow-on.
- The MRS files have no reading child — a future `mrs_csv` child
  would consume them.  They ship to demonstrate the storyline.

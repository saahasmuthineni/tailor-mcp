# Tailor for the LabChart contraction-extraction workflow

> A captured before/after walkthrough — the demo's **no-wiring-risk
> floor**: it makes the whole case with no live software in the room.
> Every number below is real output from `csv_synchronized_windows`
> run against the synthetic ten-subject cohort (`rehearse.py`, wire
> round-trip ~1.9 s).
>
> The synthetic cohort is modelled on the real workflow established in
> the lab. Structure (5 channels, roles, 7 epochs, the window rule, the
> metrics) is recon-fact; protocol *timing* and the exact channel names
> are reasoned estimates that the first real recording confirms.

## The workflow this is about

Each LabChart recording carries five channels on one shared clock:

- **torque** — isometric torque, the contraction anchor
- **gastroc_lat / gastroc_med** — gastrocnemius EMG. The **target**:
  the protocol is built to fatigue it.
- **vastus_lat / vastus_med** — vastus (quadriceps) EMG. The
  **watch-list**: the quads should stay quiet. Quad recruitment
  climbing means the participant is "cheating" — recruiting the quads
  to spare the fatiguing gastroc.

One recording holds **7 contractions** ("epochs"). Today, per subject,
the analysis loop is by hand:

1. Find the peak of each contraction; take the window 10 s to 5 s
   before it.
2. Read off the RMS-EMG of all four muscles and the mean torque, in
   that window, for **each** of the 7 epochs.
3. Transcribe via the LabChart Data Pad into an Excel template.
4. The template charts each muscle's recruitment across the protocol.

The chart answers one question: **did the protocol fatigue the right
muscle, and did the participant cheat?** Across a cohort, that loop is
hours — and every value is hand-copied, so every value is a chance to
mis-transcribe.

## Before → after

| | By hand (today) | With Tailor |
|---|---|---|
| Find each contraction in 5 channels | eyeball, per subject | one prompt, all subjects |
| Window + read RMS-EMG ×4, mean torque | manual, per epoch | computed by the tool |
| Assemble the per-epoch table | typed into Excel | returned as one table |
| Ten subjects × 7 epochs × 5 channels | hours | **~2 seconds** |
| Consistency across subjects | depends on the analyst | one deterministic method, audit-logged |
| Spot the cheater | scan ~70 contractions by eye | read one column |

## The captured run — Phase 1

One sentence to Claude Desktop — Tailor calls `csv_synchronized_windows`
once, across all ten recordings, with the analysis window
(10 s before each peak, 5 s long). One table back:

```
subject   epochs   gastroc_lat RMS      vastus_lat RMS     quad
                    epoch 1 -> 7         epoch 1 -> 7       rise
S001.csv     7      202.7 ->  291.3      33.6 ->   35.2      +5%
S002.csv     7      179.3 ->  264.1      40.2 ->   40.7      +1%
S003.csv     7      192.9 ->  265.8      40.3 ->   39.9      -1%
S004.csv     7      153.3 ->  204.1      46.9 ->   51.6     +10%
S005.csv     7      121.0 ->  170.9      35.6 ->   36.1      +1%
S006.csv     7      140.2 ->  200.9      46.4 ->   50.7      +9%
S007.csv     7      133.0 ->  182.4      38.3 ->   51.0     +33%
S008.csv     7      149.6 ->  196.1      39.5 ->   41.2      +4%
S009.csv     7      140.4 ->  198.8      32.8 ->   32.6      -1%
S010.csv     7      180.7 ->  274.5      40.7 ->   40.1      -1%
```

(The full result carries every epoch's onset / peak / offset / duration
and all four EMG channels plus torque — the table above is a readable
slice.)

**There is a finding in that table — and it is the finding the analysis
exists to make.** Read the columns:

- **gastroc_lat RMS climbs in every subject** (epoch 1 → 7). The target
  muscle fatigued and recruited harder to hold the same torque — the
  protocol worked, on all ten.
- **vastus_lat RMS stays flat** — +5%, +1%, −1%, … — for nine subjects.
  The quads stayed out of it. Clean.
- **S007 is the exception: quad recruitment +33%.** That participant
  compensated — recruited the quads to spare the fatiguing gastroc.
  That is "cheating," and it is exactly what the analysis screens for.

Drilling into S007 (one more prompt) shows the compensation as a clean
climb across the protocol — not noise:

```
S007.csv   epoch    vastus_lat RMS    gastroc_lat RMS
              1          38.3             133.0
              2          40.2             141.2
              4          44.8             158.5
              7          51.0             182.4
```

A reviewer scanning ten subjects by hand might catch S007. A reviewer
scanning *seventy contractions* across a real cohort might not. Tailor
surfaced it as a side effect of removing the drudgery.

## Why this is not "the script again" — *(optional framing)*

> *Include this only if you choose to invoke the earlier MATLAB-script
> episode directly. The demo stands without it.*

A bespoke script that automates **one part** of a pipeline forces an
all-or-nothing: to keep the analysis consistent you must apply it
everywhere, and writing / maintaining / extending a script to cover
everything costs more *total* effort than the by-hand way. Tailor
answers that point for point:

| Objection to a partial script | What Tailor is instead |
|---|---|
| It is **your code** to write, debug, maintain. | An existing general tool. You extend its reach by **asking**, not coding. |
| "Apply it everywhere" is the expensive part. | "Everywhere" is one prompt — *all ten subjects* is the headline above. |
| It covers one slice; the rest stays by hand. | It runs the whole loop — detection → windowed table → chart-ready output. |
| Consistency depends on you re-applying it. | One deterministic method, applied identically, in the audit log. |

## Honest scope

Tailor replaces the **data-wrangling loop** — extraction through a
chart-ready per-epoch table — completely. It does **not** do the
scientific analysis: defining a contraction, choosing the window,
deciding what compensation means. That stays the analyst's.

**The drudgery loop, completely. The science, yours.**

## The window rule — and a second thing Tailor unlocks

The current window — 5 s, starting 10 s before the peak — is, by both
the lab's and Chunyu's own account, a *crude* rule: anything more
sophisticated is too much hand-labour at scale (7 contractions × who
knows how many participants). So the window isn't a method anyone would
defend — it is a **compromise the labour forced**.

That means Tailor does more than save time. The window is just two
parameters (`lead_s`, `window_s`). Once extraction is free, a *cleaner*
windowing rule is a one-line experiment, not a re-code. **"The drudgery,
gone" and "a better analysis is now affordable" are the same lever.**

## A supporting property — why a scientist can trust the numbers

The numbers come from a deterministic function — the tool *computed*
them; they are not an AI guess. Claude Desktop shows the tool call.
Re-running the same recording yields the identical result. The call is
in the audit log. That is *why* a scientist believes the result — and
the same property is what makes consistency across subjects automatic.

## Phase 2 — the analyst's own recording

A raw LabChart text export carries a header preamble a generic CSV
reader chokes on. `labchart_to_csv.py` is the safety net: it finds the
numeric data block by *shape*, recovers the channel names, ensures a
time column, and writes a clean CSV — verified against four fabricated
export variants plus an end-to-end check. The cleaned file drops into
the demo directory as one more recording, and `csv_synchronized_windows`
runs on it. Even Tailor reading his file and reporting its five channels
is a real "it touched my data" moment; the full per-epoch extraction is
the clincher.

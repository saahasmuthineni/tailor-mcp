# labchart_sync — demo runbook (operator)

The `csv_synchronized_windows` demo for Chunyu's LabChart contraction-
extraction workflow. **Demo-grade work on the `feature/csv-synchronized-
windows` branch — not merged to main, no release, no ADR.**

For the *case the demo makes* (before/after, the captured cohort table,
the QC finding, the three-way comparison), see **[DEMO.md](DEMO.md)** —
that file is the shareable, no-wiring-risk floor.

## The workflow this models (from the lab-day recon)

Five channels per recording on a shared clock: **torque** + four EMG —
**gastroc_lat / gastroc_med** (the target muscle, meant to fatigue) and
**vastus_lat / vastus_med** (the quad watch-list, should stay quiet). 7
contractions ("epochs") per subject. Per epoch the analyst windows
`[peak − 10 s, peak − 5 s]` and reads RMS-EMG ×4 + mean torque → Data
Pad → Excel template → a motor-recruitment QC chart, per subject.

What is recon-fact vs. estimate: the **structure** (channels, roles, 7
epochs, the window rule, the metrics) is fact. The **protocol timing**
(sample rate, contraction duration) and the **exact channel-name
strings** are reasoned estimates — the synthetic data is labelled as
such, and the real file slots in with a config edit, not a rebuild.

## What is in this folder

| File | Purpose |
|---|---|
| `generate.py` | Writes the synthetic ten-subject cohort into `data/` + a `user_config.sample.json`. |
| `data/` | Generated recordings (`S001.csv`..`S010.csv`) + `metadata.json`. Created by `generate.py`. |
| `labchart_to_csv.py` | Phase-2 normalizer for a raw LabChart text export. `--selftest` runs the fabricated-input checks. |
| `rehearse.py` | Spawns `tailor serve` and drives the demo hot path over the wire — rehearsal + subprocess smoke. |
| `DEMO.md` | The shareable before/after artifact. |
| `user_config.sample.json` | A ready-to-use 5-channel `csv_dir` config block. Created by `generate.py`. |

## The planted finding — operator, know this

The synthetic cohort has one **"cheater": S007.** Its vastus (quad)
recruitment climbs ~+33% across the 7 epochs while the other nine stay
flat — the compensation pattern the QC screens for. Every subject's
gastroc climbs (the target fatiguing normally). This is in the EMG data
only — *not* in `metadata.json`. If Chunyu doesn't spot S007 himself,
steer him there: "which subject's quad recruitment climbs?"

## One-time setup

```powershell
# 1. From the repo root, on the feature branch, install dev deps.
pip install -e ".[dev]"

# 2. Generate the synthetic cohort.
python examples/hip_lab_demo/labchart_sync/generate.py

# 3. Rehearse — spawns the server and runs Phase 1 + off-script + an
#    error path end-to-end. The transcript is what Claude Desktop will
#    drive; it should end with REHEARSAL PASSED.
python examples/hip_lab_demo/labchart_sync/rehearse.py
```

## Wiring it into Claude Desktop (`tailor-demo`)

Use an **isolated** config dir so the demo never touches a real
`~/.tailor`:

```powershell
$demo = "examples\hip_lab_demo\labchart_sync\demo_env"
New-Item -ItemType Directory -Force "$demo\config", "$demo\data" | Out-Null
Copy-Item "examples\hip_lab_demo\labchart_sync\user_config.sample.json" `
          "$demo\config\user_config.json"
python -c "import sys; print(sys.executable)"   # the interpreter to use
```

Quit Claude Desktop **fully**, then add an `mcpServers` entry to
`%APPDATA%\Claude\claude_desktop_config.json` (absolute paths; the
interpreter printed above):

```json
{
  "mcpServers": {
    "tailor-demo": {
      "command": "<the python printed above>",
      "args": ["-m", "tailor", "serve"],
      "env": {
        "TAILOR_CONFIG_DIR": "<repo>\\examples\\hip_lab_demo\\labchart_sync\\demo_env\\config",
        "TAILOR_DATA_DIR":   "<repo>\\examples\\hip_lab_demo\\labchart_sync\\demo_env\\data"
      }
    }
  }
}
```

Restart Claude Desktop. The server registers as a session-scoped MCP
server (rendered in prose, not a green connector card — that is the
normal local-MCP shape, not a degraded install).

## Phase 1 — the headline

> *"Run the contraction extraction across all ten recordings — for each
> contraction, window it from 10 seconds before the peak, 5 seconds
> long."*

then read the table for the QC finding:

> *"Which subject's vastus (quad) recruitment climbs across the
> protocol? Chart gastroc vs vastus RMS across the epochs."*

Ten subjects × 7 epochs × 5 channels — hours by hand — come back in one
call, and S007's compensation is one column to read.

## Off-script — things to try

The data is varied per subject, so these return real answers:

- *"Drill into S007 — show vastus RMS for each of its 7 epochs."*
  (A clean monotonic climb — the compensation signature.)
- *"Did the protocol fatigue the gastroc in every subject?"*
  (Yes — gastroc RMS climbs epoch 1 → 7 for all ten.)
- *"Run it on S003 only."* / *"...with a tighter threshold."*
- *"Try a different window — 6 seconds before the peak, 3 seconds long."*
  (The window is just two parameters — a cleaner rule is one prompt.)
- Ask for a muscle or subject that does not exist — it should fail with
  a clear message, not a crash.

## Phase 2 — Chunyu's own recording

1. Chunyu exports one real LabChart recording — comma-delimited if
   offered, time column included, header/comments minimal.
2. Normalize it (handles the LabChart header preamble):
   ```
   python examples/hip_lab_demo/labchart_sync/labchart_to_csv.py recording.txt demo_env\config\...\data\S011.csv
   ```
3. Confirm the channel names the normalizer recovered, and — if they
   differ from the synthetic ones — edit `value_columns` in
   `user_config.json` to match (the keys are the real CSV headers; this
   is a one-line edit, no code change). Restart Claude Desktop.
4. *"Run the contraction extraction on S011"* — tune `threshold` /
   `anchor_column` live if detection needs it.

Graceful degradation — any of these is a real "it touched my data"
moment: Tailor reads + summarises the file -> detects his contractions
-> full per-epoch extraction. Phase 1 already meets the demo's bar, so a
Phase-2 stumble is a live tuning moment, not a failure.

## If short on time — cut order

1. 5 synthetic subjects instead of 10 (`N_SUBJECTS` in `generate.py`).
2. Drop the optional `metadata.json`.
3. Phase 2 minimal tier only — Tailor reads + summarises the file.
4. Drop the live demo; **[DEMO.md](DEMO.md)** carries the case alone.

## Fallback

If live Claude Desktop wiring misbehaves, run `rehearse.py` from a
terminal — it drives the identical wire path and prints the same
result, including the S007 finding. And `DEMO.md` makes the whole case
with no software in the room.

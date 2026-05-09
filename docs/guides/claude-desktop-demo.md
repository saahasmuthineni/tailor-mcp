# Recording recipe: Claude Desktop demo GIF

This documents how to produce `docs/claude-desktop-demo.gif` — a short screencap of Claude Desktop answering a biosensor question with a visible token-cost badge.

## Setup

1. **Window size:** 1280x800 (Retina/HiDPI), zoom 100%
2. **Data source:** Run `tailor tour` first (ADR 0024) — scaffolds the bundled HIP Lab synthetic fixtures and registers a sandboxed MCP server entry with Claude Desktop. Strictly synthetic data; never use real participant data when recording GIFs.
3. **Ensure tailor is connected** in Claude Desktop (check via `tailor status`)

## Prompt script

1. Start with a fresh Claude Desktop conversation
2. Type: **"How was my last run?"**
3. Wait for the full response to render (run report with zones, splits, drift, efficiency)
4. Briefly pan over the token-cost badge (should show ~800 tokens)
5. Hold for 1–2 seconds on the completed response

## Recording

**macOS:** Cmd+Shift+5 → record selected area around Claude Desktop window
**Windows:** Xbox Game Bar (Win+G) → Capture → Record
**Linux:** `peek` or `kooha` for screen recording

**Duration target:** 5–10 seconds, loop-friendly (start and end on idle UI state)

## Post-processing

Convert MP4 to GIF:
```bash
# Using gifski (best quality, install via: cargo install gifski)
gifski --fps 15 --width 900 -o docs/claude-desktop-demo.gif input.mp4

# Alternative: ffmpeg
ffmpeg -i input.mp4 -vf "fps=15,scale=900:-1:flags=lanczos" -loop 0 docs/claude-desktop-demo.gif
```

## Constraints

- **File size:** < 3 MB (larger image area than terminal GIF)
- **Privacy:** Tour-scaffolded synthetic fixtures only — no real participant data, no real Strava activity names, no real biometric streams
- **Looping:** GIF should look natural when looping (start and end in similar UI state)

## Current placeholder

Until a real recording is available, [`docs/assets/claude-desktop-demo.svg`](../assets/claude-desktop-demo.svg) provides a static mockup of the same interaction for the README.

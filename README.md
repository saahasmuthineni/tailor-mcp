# Biosensor-to-LLM Optimization — Strava Running Coach

[![CI](https://github.com/saahasmuthineni/strava-run-coach/actions/workflows/ci.yml/badge.svg)](https://github.com/saahasmuthineni/strava-run-coach/actions/workflows/ci.yml)

An MCP server that gives Claude Desktop the ability to analyze your running data from Strava with scientific precision, while keeping your biometric data private and token costs minimal.

## What This Does

Once installed, you can talk to Claude naturally about your runs:

- "Analyze my last run" — gets HR zones, pace splits, decoupling, efficiency factor
- "Compare my last 3 long runs" — side-by-side performance trends
- "Show me my training volume this month" — weekly mileage, avg HR, progression
- "Where did I stop and what was I doing?" — GPS-detected stops with labels

All analysis happens **server-side** on your machine. Claude only sees computed summaries (~800 tokens), not your raw per-second biometric data (~200,000 tokens). That's a **99.6% reduction** in data exposure.

## Quick Install (5 minutes)

### Prerequisites

- **Python 3.10+** installed ([python.org/downloads](https://python.org/downloads))
- **Claude Desktop** installed ([claude.ai/download](https://claude.ai/download))
- **Strava account** with an API app ([strava.com/settings/api](https://strava.com/settings/api))

### Step 1: Create a Strava API App (if you don't have one)

1. Go to [strava.com/settings/api](https://www.strava.com/settings/api)
2. Create an app with any name
3. Set the callback domain to `localhost`
4. Note your **Client ID** and **Client Secret**

### Step 2: Run the Installer

**Mac / Linux** — open Terminal:
```bash
curl -sSL https://raw.githubusercontent.com/saahasmuthineni/strava-run-coach/main/install.sh | bash
```

**Windows** — open PowerShell:
```powershell
irm https://raw.githubusercontent.com/saahasmuthineni/strava-run-coach/main/install.ps1 | iex
```

The installer will:
1. Create a Python virtual environment
2. Install dependencies
3. Open your browser for Strava OAuth authorization
4. Register the MCP server with Claude Desktop

### Step 3: Restart Claude Desktop

Close and reopen Claude Desktop. You'll see the Strava tools available. Start chatting about your runs!

## Architecture

```
Claude Desktop ←→ Parent Router (security pipeline) ←→ Running Child (Strava)
                       │
                       ├── Parameter validation
                       ├── Circuit breaker (auto-block on API failures)
                       ├── Biometric consent gate (per-session, revocable)
                       ├── Cost gate (warns before expensive operations)
                       └── Audit log (every call logged)
```

### Three-Tier Access Model

| Tier | What Claude Sees | Tokens | Gate |
|------|-----------------|--------|------|
| 1 — Free | Server-computed reports (splits, zones, drift) | 200-1,500 | None |
| 2 — Gated | Downsampled streams at 10-15s intervals | 3,000-7,000 | Biometric consent |
| 3 — Cost | Per-second streams with precision reduction | 25,000-60,000 | Consent + cost approval |

## Available Tools

| Tool | What It Does | ~Tokens |
|------|-------------|---------|
| `strava_run_report` | Full run analysis: decoupling, EF, drift, GAP splits | ~800 |
| `strava_trend_report` | Weekly volume, pace, HR trends | ~600 |
| `strava_compare_runs` | Side-by-side comparison of 2-5 runs | ~1,500 |
| `strava_hr_analysis` | Zone distribution, drift, anomalies | ~300 |
| `strava_pace_analysis` | Mile splits, run/walk classification | ~300 |
| `strava_stop_analysis` | Pause detection with GPS locations | ~200 |
| `strava_downsampled_streams` | HR, pace, GPS at 5-30s intervals | 3,000-7,000 |
| `strava_full_streams` | Per-second data (selective streams) | 25,000-60,000 |

## Obsidian Vault Integration (Optional)

If you use [Obsidian](https://obsidian.md/), Claude can automatically write run analysis notes into your vault and read them back in future sessions — giving it a persistent memory of your training history across conversations.

**What it does:**
- After each `strava_run_report`, a markdown note is written to your vault with YAML frontmatter (date, distance, HR, decoupling, efficiency factor, anomaly flags, Obsidian tags)
- In a new session, Claude reads vault notes instead of re-syncing Strava — no extra API calls
- Claude can annotate notes with coaching insights that persist across sessions

**Vault tools:**

| Tool | What It Does |
|------|-------------|
| `vault_get_fitness_summary` | 8-week aggregate snapshot — start every session here |
| `vault_list_notes` | Browse notes by date, type, or coaching status |
| `vault_read_note` | Read the full body of a specific run note |
| `vault_search_notes` | Full-text search across all notes |
| `vault_list_anomalies` | Find runs with sensor issues |
| `vault_annotate_run` | Save coaching insights back to a note |
| `vault_backfill` | Generate notes for all cached historical runs |

**Setup:** Add `vault_path` to `~/.strava-coach/user_config.json`:
```json
{
  "max_hr": 185,
  "resting_hr": 52,
  "vault_path": "/path/to/your/obsidian/vault"
}
```

> **Privacy note:** If your vault is inside a cloud-synced folder (iCloud, OneDrive, Dropbox), computed fitness data will be uploaded to that service. The server will warn you if it detects a cloud path.

## Customize

Create `~/.strava-coach/user_config.json`:
```json
{
  "max_hr": 185,
  "resting_hr": 52
}
```

## Commands

```
strava-coach status    — Check everything is working
strava-coach setup     — Re-run OAuth setup
strava-coach uninstall — Clean removal
```

## Troubleshooting

**"Not authenticated" error:** Run `strava-coach setup` to redo OAuth.

**Tools not showing in Claude:** Make sure you restarted Claude Desktop after install.

**Rate limit warning:** Strava allows 100 requests per 15 minutes. The server tracks this and warns you before hitting the limit.

## License

MIT

# Biosensor → LLM Middleware

[![CI](https://github.com/saahasmuthineni/biosensor-to-llm-middleware/actions/workflows/ci.yml/badge.svg)](https://github.com/saahasmuthineni/biosensor-to-llm-middleware/actions/workflows/ci.yml)
[![Python 3.10 | 3.11 | 3.12](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

A framework for piping high-frequency biosensor data into LLM context windows efficiently, privately, and cheaply. Raw biometric streams are compressed server-side before any data reaches the model.

**Reference implementation:** Strava running data → Claude Desktop via MCP.

---

## The Problem

High-frequency biosensor data and LLMs are a bad match out of the box:

| Data source | Raw size | Direct cost | After this framework |
|-------------|----------|-------------|----------------------|
| 15-mile run (8 stream types, 1Hz) | ~200,000 tokens | ~$60/month | ~800 tokens (~$0.02) |
| CGM trace (glucose, 5-min intervals) | ~10,000 tokens/day | — | ~200 tokens |
| Sleep staging (per-epoch) | ~5,000 tokens/night | — | ~150 tokens |

Server-side analytics compute what the LLM actually needs — zones, splits, trends, anomalies — and return only the summary. **99.6% token reduction** in the running example. Raw per-second data never leaves the machine.

---

## Architecture

```mermaid
flowchart TD
    Client["Any LLM Client\n(Claude Desktop, API, etc.)"]
    Client --> Router

    subgraph Router["RouterMCP — Security Pipeline"]
        direction TB
        L1["1 · ParamValidator\nType / Range / Pattern"] --> L2["2 · CircuitBreaker\n3 failures → 5 min block"]
        L2 --> L3["3 · ConsentGate\nPer-domain · Session-scoped"]
        L3 --> L4["4 · CostGate\nPre-estimate · Gate > 35k tokens"]
        L4 --> L5["5 · AuditLog + TokenLedger\nSQLite · Cumulative spend"]
    end

    Router --> Children

    subgraph Children["Child MCPs — Domain Analytics"]
        Running["RunningChild\n(Strava)"]
        CGM["CGMChild\n(future)"]
        Sleep["SleepChild\n(future)"]
    end

    Running -.-> Vault["VaultChild\n(Obsidian)"]
```

The router owns all cross-cutting concerns. Children own domain logic. Any LLM client gets identical security enforcement — behavioral rules live server-side, not in prompts.

### Security Pipeline

| Layer | Component | Purpose |
|-------|-----------|---------|
| 1 | `ParamValidator` | Type/range/pattern checks — reject before any work |
| 2 | `CircuitBreaker` | Block domain after 3 consecutive failures; auto-reset after 5 min |
| 3 | `ConsentGate` | Per-domain biometric consent, session-scoped, revocable |
| 4 | `CostGate` | Pre-estimate tokens before execution; gate if > 35,000 tokens |
| 5 | `AuditLog` + `TokenLedger` | Every call logged to SQLite; cumulative session spend |

### Three-Tier Access Model

| Tier | What the LLM Sees | Tokens | Gate |
|------|------------------|--------|------|
| 1 — Free | Server-computed reports (zones, splits, trends, anomalies) | 200–1,500 | None |
| 2 — Consent | Downsampled streams at 5–30s intervals | 3,000–7,000 | Biometric consent |
| 3 — Cost | Per-second streams with precision reduction | 25,000–60,000 | Consent + cost approval |

~90% of questions are answered at Tier 1. Zero raw biometric data leaves the machine.

---

## Building Your Own Child

Implement 4 abstract methods and register with the router:

```python
from biosensor_mcp.framework import ChildMCP, ToolDefinition, CostEstimate, ValidationSchema, ConsentInfo

class CGMChild(ChildMCP):
    @property
    def domain(self) -> str: return "cgm"

    @property
    def display_name(self) -> str: return "Glucose (Dexcom)"

    @property
    def consent_info(self) -> ConsentInfo:
        return ConsentInfo(
            data_types=["glucose levels", "meal markers"],
            purpose="glycemic analysis and trends",
        )

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [ToolDefinition("cgm_daily_report", 1, "Time-in-range, variability, meal response", {...})]

    @property
    def param_schemas(self) -> dict: ...

    async def execute(self, tool_name: str, params: dict) -> dict: ...

    async def estimate_cost(self, tool_name: str, params: dict) -> CostEstimate: ...

# Register in __main__.py cmd_serve():
router.register_child(CGMChild(config_dir, data_dir))
# Router auto-generates approve_consent_cgm + revoke_consent_cgm
```

The router handles consent prompting, cost gating, circuit breaking, audit logging, and token tracking automatically. The child only implements domain analytics.

**Other biosensor domains this pattern applies to:**
- CGM (Dexcom, Libre) — time-in-range, glycemic variability, meal response curves
- Sleep (Oura, Whoop) — stage duration, efficiency, latency, fragmentation
- ECG (Apple Watch, Kardia) — rhythm classification, HRV, QT intervals
- Lab results — trend analysis, reference range flags, longitudinal comparison

---

## Working Example: Strava Running + Claude Desktop

The reference implementation connects Strava running data to Claude Desktop via MCP. Twelve running tools across three tiers, plus seven vault tools for persistent analytical memory in Obsidian.

### Prerequisites

- Python 3.10+
- Claude Desktop
- Strava account with an API app ([strava.com/settings/api](https://www.strava.com/settings/api)) — set callback domain to `localhost`

### Install

**Mac / Linux:**
```bash
curl -sSL https://raw.githubusercontent.com/saahasmuthineni/biosensor-to-llm-middleware/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/saahasmuthineni/biosensor-to-llm-middleware/main/install.ps1 | iex
```

Restart Claude Desktop after install. Then ask Claude to sync and analyze your runs.

### Running Tools

| Tool | Tier | What It Does | ~Tokens |
|------|------|-------------|---------|
| `strava_sync` | 1 | Pull recent activities from Strava into local cache | ~50 |
| `strava_list_runs` | 1 | List recent runs with summary stats | ~400 |
| `strava_activity_detail` | 1 | Full details for a single activity | ~200 |
| `strava_run_report` | 1 | Full run analysis: decoupling, EF, drift, phases, GAP splits | ~800 |
| `strava_trend_report` | 1 | Weekly volume, pace, HR trends | ~600 |
| `strava_compare_runs` | 1 | Side-by-side comparison of 2–5 runs | ~1,500 |
| `strava_hr_analysis` | 1 | Zone distribution, drift, anomalies | ~300 |
| `strava_pace_analysis` | 1 | Mile splits, run/walk classification | ~300 |
| `strava_stop_analysis` | 1 | Pause detection with GPS locations | ~200 |
| `strava_label_stop` | 1 | Persist stop labels across sessions (e.g. "Gel 1/3") | ~50 |
| `strava_downsampled_streams` | 2 | HR, pace, GPS at 5–30s intervals | 3,000–7,000 |
| `strava_full_streams` | 3 | Per-second data with selective stream filtering | 25,000–60,000 |

<details>
<summary>Example: strava_run_report response (~800 tokens)</summary>

```json
{
  "activity_id": 12345678,
  "data_points": 5420,
  "decoupling": {
    "decoupling_pct": 4.2,
    "first_half": {"avg_hr": 152, "avg_velocity": 2.95},
    "second_half": {"avg_hr": 159, "avg_velocity": 2.88},
    "interpretation": "well coupled"
  },
  "efficiency_factor": {"ef": 1.34, "avg_hr": 155, "avg_velocity_ms": 2.91},
  "hr_drift": {
    "first_half_avg": 152,
    "second_half_avg": 159,
    "drift_pct": 4.6,
    "interpretation": "aerobic"
  },
  "hr_zones": {
    "zone_seconds": {1: 114, 2: 996, 3: 2833, 4: 1344, 5: 133},
    "zone_pct": {1: 2.1, 2: 18.4, 3: 52.3, 4: 24.8, 5: 2.4},
    "avg_hr": 156,
    "max_hr_observed": 178,
    "max_hr_setting": 185
  },
  "mile_splits": [
    {"mile": 1, "elapsed_seconds": 552, "pace": "9:12", "avg_velocity_ms": 2.91},
    {"mile": 2, "elapsed_seconds": 540, "pace": "9:00", "avg_velocity_ms": 2.98}
  ],
  "anomalies": [],
  "note": "Full report computed server-side from per-second data. Raw streams not transmitted."
}
```

</details>

### Obsidian Vault (Optional)

Claude can write run notes into an Obsidian vault and read them back in future sessions — persistent analytical memory across conversations.

Add `vault_path` to `~/.biosensor-mcp/user_config.json`:
```json
{
  "max_hr": 185,
  "resting_hr": 52,
  "vault_path": "/path/to/your/obsidian/vault"
}
```

| Vault Tool | What It Does |
|------------|-------------|
| `vault_get_fitness_summary` | 8-week aggregate snapshot — orient at session start |
| `vault_list_notes` | Browse notes by date, type, or insight status |
| `vault_read_note` | Read full body of a specific run note |
| `vault_search_notes` | Full-text search across all notes |
| `vault_list_anomalies` | Find runs with detected anomalies (HR spikes, etc.) |
| `vault_annotate_run` | Save analytical insights back to a note |
| `vault_backfill` | Generate notes for all cached historical runs |

<details>
<summary>Example: vault run note (Obsidian markdown)</summary>

```markdown
---
domain: running
note_type: run_report
activity_id: 12345678
date: "2026-04-10"
week: "2026-W15"
distance_miles: 10.12
duration_min: 87.3
avg_hr: 156
max_hr_observed: 178
decoupling_pct: 4.2
efficiency_factor: 1.34
hr_drift_pct: 4.6
aerobic_grade: coupled
anomaly_count: 0
tags:
  - running
  - aerobic/coupled
  - week/2026-W15
---

# Thursday Recovery Run

## Summary

| Field | Value |
|-------|-------|
| Date | 2026-04-10 |
| Distance | 10.12 mi |
| Duration | 87.3 min |
| Avg HR | 156 bpm |
| Aerobic Grade | coupled |
| Decoupling | 4.2% |
| Efficiency Factor | 1.34 |
| HR Drift | 4.6% |

## HR Analysis

Avg HR: **156 bpm** · Max: **178 bpm** · Setting: 185 bpm

| Zone | % Time | Seconds |
|------|--------|---------|
| Z1 | 2.1% | 114 |
| Z2 | 18.4% | 996 |
| Z3 | 52.3% | 2833 |
| Z4 | 24.8% | 1344 |
| Z5 | 2.4% | 133 |

## Insights

*(No insight notes yet.)*
```

</details>

> **Privacy:** If your vault is in a cloud-synced folder (iCloud, OneDrive, Dropbox), the server warns you and computed analytics will be uploaded. Use a local path to keep data on-device.

### Customize

`~/.biosensor-mcp/user_config.json`:
```json
{
  "max_hr": 185,
  "resting_hr": 52,
  "home_lat": 42.360,
  "home_lng": -71.058
}
```

### Commands

```
biosensor-mcp status     — Check configuration and connectivity
biosensor-mcp setup      — Re-run Strava OAuth setup
biosensor-mcp uninstall  — Clean removal
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `status` shows token expired | Run `biosensor-mcp setup` to re-authenticate. Tokens auto-refresh on use, but the refresh token itself can expire after 6 months of inactivity. |
| Claude says "consent is required" | This is expected — biometric consent is session-scoped and resets each conversation. Approve once per session. |
| Tool returns "No stream data available" | Run `strava_sync` first to pull activities into the local cache. Some activities (treadmill) may lack GPS streams. |
| Windows: "address already in use" during OAuth | The setup wizard uses port 8899. Close any process using that port, or restart and retry. |
| Cost gate triggered unexpectedly | Only `strava_full_streams` triggers the cost gate (>35,000 tokens). Use `strava_downsampled_streams` for visualization — it's ~85% cheaper. |

---

## Further Reading

See [docs/design-context.pdf](docs/design-context.pdf) for the original design context document.

---

## License

Apache-2.0

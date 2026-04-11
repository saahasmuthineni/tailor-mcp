# Biosensor → LLM Middleware

[![CI](https://github.com/saahasmuthineni/biosensor-to-llm-middleware/actions/workflows/ci.yml/badge.svg)](https://github.com/saahasmuthineni/biosensor-to-llm-middleware/actions/workflows/ci.yml)

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

```
Any LLM Client (Claude Desktop, API, etc.)
        ↓
  RouterMCP  ←  security pipeline (5 layers, cheapest first)
        ↓
  ChildMCP   ←  domain-specific analytics + data access
  (Running | CGM | Sleep | ECG | ...)
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

The reference implementation connects Strava running data to Claude Desktop via MCP. Thirteen tools across three tiers, with an optional Obsidian vault for persistent coaching memory.

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
| `strava_run_report` | 1 | Full run analysis: decoupling, EF, drift, phases, GAP splits | ~800 |
| `strava_trend_report` | 1 | Weekly volume, pace, HR trends | ~600 |
| `strava_compare_runs` | 1 | Side-by-side comparison of 2–5 runs | ~1,500 |
| `strava_hr_analysis` | 1 | Zone distribution, drift, anomalies | ~300 |
| `strava_pace_analysis` | 1 | Mile splits, run/walk classification | ~300 |
| `strava_stop_analysis` | 1 | Pause detection with GPS locations | ~200 |
| `strava_downsampled_streams` | 2 | HR, pace, GPS at 5–30s intervals | 3,000–7,000 |
| `strava_full_streams` | 3 | Per-second data with selective stream filtering | 25,000–60,000 |

### Obsidian Vault (Optional)

Claude can write run notes into an Obsidian vault and read them back in future sessions — persistent coaching memory across conversations.

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
| `vault_list_notes` | Browse notes by date, type, or coaching status |
| `vault_read_note` | Read full body of a specific run note |
| `vault_search_notes` | Full-text search across all notes |
| `vault_list_anomalies` | Find runs with detected anomalies (HR spikes, etc.) |
| `vault_annotate_run` | Save coaching insights back to a note |
| `vault_backfill` | Generate notes for all cached historical runs |

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

## License

MIT

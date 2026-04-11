# CLAUDE.md — Biosensor-to-LLM Optimization

## What This Project Is

A **reference implementation** for efficiently piping high-frequency biosensor data (HR, GPS, pace, altitude, glucose, SpO2) into LLM context windows without blowing token budgets or leaking sensitive biometric data.

Strava running data is the proving ground. The architecture generalises to any biosensor pipeline: CGM, sleep staging, ECG, lab results.

**This is NOT a Strava coaching product.** The domain is illustrative; the framework is the deliverable.

## The Core Problem Solved

A 15-mile run generates ~8,600 per-second data points across 8 stream types, serialising to ~200,000 tokens. Sending that to Claude for every question costs ~$60/month and is a privacy risk. Server-side computation reduces this to ~800 tokens (~$0.02) — 99.6% reduction.

## Architecture

```
Claude Desktop <--> RouterMCP (validate → circuit break → consent → cost → audit)
                         |
                    ChildMCP (domain-specific execution)
                  e.g. RunningChild, CGMChild (future), SleepChild (future)
```

**Key principle**: Behavioral rules (consent gates, cost gates, access tiers) live server-side, not in the LLM. Any LLM client gets identical enforcement.

## File Structure

```
src/strava_coach/
  __init__.py              # Package metadata (v4.0.0)
  __main__.py              # CLI: serve | setup | status | uninstall | --help
  wizard.py                # OAuth setup wizard (localhost callback server)
  framework/
    __init__.py            # Public API exports
    interfaces.py          # ChildMCP ABC, ToolDefinition, CostEstimate,
                           #   ValidationSchema, ConsentInfo, ConsentScope,
                           #   CostContext, LLMInstruction
    router.py              # RouterMCP — security pipeline + dispatch
    middleware.py          # CircuitBreaker, ConsentGate, CostGate,
                           #   AuditLog, TokenLedger, ParamValidator
    storage.py             # BaseStorage — thread-safe SQLite with WAL
  children/
    running/
      __init__.py          # Exports RunningChild
      child.py             # RunningChild(ChildMCP) — 13 tools, 3 tiers
      processing.py        # RunningProcessing — stateless analytics
      strava_api.py        # OAuth + rate-limited Strava API client
  vault/
    __init__.py            # Exports VaultWriter, VaultChild
    child.py               # VaultChild(ChildMCP) — 7 read/write tools
    writer.py              # Post-execute hook; atomic file writes → Obsidian
    renderer.py            # Pure markdown generation (run/trend/compare notes)
    storage.py             # VaultStorage — SQLite index of vault notes

tests/
  test_processing.py       # Pure-function analytics tests (no I/O)
  test_middleware.py       # Framework security component tests
  test_router.py           # Router pipeline integration tests (mock child)
  test_vault_child.py      # VaultChild handler tests
  test_vault_renderer.py   # Markdown renderer tests
  test_vault_writer.py     # VaultWriter atomic write + frontmatter tests
  probe.py                 # Ad-hoc local exploration (not in CI)
```

## Security Pipeline (5 Layers, Cheapest First)

| Layer | Class | Purpose |
|-------|-------|---------|
| 1 | `ParamValidator` | Type/range/pattern checks — reject before any work |
| 2 | `CircuitBreaker` | Block domain after 3 consecutive failures; auto-reset after 5 min |
| 3 | `ConsentGate` | Per-domain biometric consent, session-scoped, revocable |
| 4 | `CostGate` | Pre-estimate tokens before execution; gate if > 35,000 tokens |
| 5 | `AuditLog` + `TokenLedger` | Every call logged to SQLite; cumulative session spend |

## Three-Tier Access Model

| Tier | What Claude Sees | Tokens | Gate |
|------|-----------------|--------|------|
| 1 — Free | Server-computed reports (splits, zones, drift, decoupling, EF, trends) | 200–1,500 | None |
| 2 — Consent | Downsampled streams at 10–15s for visualisation | 3,000–7,000 | Biometric consent |
| 3 — Cost | Per-second streams with precision reduction | 25,000–60,000 | Consent + cost approval |

~90% of questions are answered at Tier 1 with zero raw biometric data leaving the machine.

## Running Child — 13 Tools

| Tool | Tier | Description |
|------|------|-------------|
| `strava_sync` | 1 | Pull recent activities from Strava into local cache |
| `strava_list_runs` | 1 | List recent runs with summary stats |
| `strava_activity_detail` | 1 | Single-activity overview |
| `strava_hr_analysis` | 1 | Zone distribution, drift, anomalies |
| `strava_pace_analysis` | 1 | Mile splits, run/walk classification |
| `strava_stop_analysis` | 1 | Pause detection with GPS + saved labels |
| `strava_label_stop` | 1 | Persist stop label to SQLite |
| `strava_run_report` | 1 | Comprehensive: decoupling, EF, drift, phases, GAP |
| `strava_trend_report` | 1 | Rolling weekly volume, avg pace, avg HR |
| `strava_compare_runs` | 1 | Side-by-side comparison of 2–5 runs |
| `strava_downsampled_streams` | 2 | HR, pace, GPS at 10–15s intervals |
| `strava_full_streams` | 3 | Per-second data with precision reduction |

## Running and Testing

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run tests
pytest -v

# CLI smoke test
strava-coach --help

# OAuth setup
strava-coach setup

# Start MCP server
strava-coach serve
```

## Key Design Decisions

**Structured `LLMInstruction` over freeform strings**: Consent and cost gates return a JSON object with individually checkable `must_do`, `must_not_do`, and `on_ambiguous_reply` fields — not a free-text paragraph. Makes compliance auditable.

**Pre-estimation not post-billing**: `CostGate` calls `child.estimate_cost()` before execution using stream metadata (point counts), never the full payload. No wasted compute on rejected requests.

**Grade precision at 1 decimal**: GAP calculation uses `cost = 1 + 0.03 * grade%`. Rounding grade to integer introduces ~3% split error. All other numerics are reduced more aggressively.

**0.5 m/s stop threshold**: 0.3 m/s was too aggressive (flagged slow shuffles at end of hard efforts). 0.5 m/s (~1.8 km/h) is the designed "completely stopped" signal.

**Spike detection 30-second cooldown**: A single Apple Watch sensor catchup burst can generate dozens of overlapping anomaly entries without the cooldown.

**orjson with stdlib fallback**: `_dumps`/`_loads` wrappers in `middleware.py` are transparent to all consumers.

**`router.close()` on Windows**: SQLite WAL connections must be explicitly closed before the process exits on Windows. Call `router.close()` in tests and server shutdown to release file locks.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `STRAVA_CONFIG_DIR` | `~/.strava-coach` | Token, user config, rate limit files |
| `STRAVA_DATA_DIR` | `~/.strava-coach/data` | SQLite databases |
| `STRAVA_STREAM_CACHE_TTL_DAYS` | `7` | Stream cache eviction |

User config at `~/.strava-coach/user_config.json`:
```json
{ "max_hr": 185, "resting_hr": 55, "home_coords": [42.360, -71.058] }
```

## Claude Desktop Integration

```json
{
  "mcpServers": {
    "strava-coaching": {
      "command": "~/.strava-coach/venv/bin/python",
      "args": ["-m", "strava_coach", "serve"],
      "env": {
        "STRAVA_CONFIG_DIR": "~/.strava-coach",
        "STRAVA_DATA_DIR": "~/.strava-coach/data"
      }
    }
  }
}
```

## Adding a New Biosensor Child

Implement 4 abstract items and register:

```python
from strava_coach.framework import ChildMCP, ToolDefinition, CostEstimate, ValidationSchema, ConsentInfo

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
        return [ToolDefinition("cgm_daily_report", 1, "Time-in-range, variability", {...})]

    @property
    def param_schemas(self) -> dict: ...

    async def execute(self, tool_name, params) -> dict: ...

    async def estimate_cost(self, tool_name, params) -> CostEstimate: ...

# In __main__.py cmd_serve():
router.register_child(CGMChild(config_dir, data_dir))
# Router auto-generates approve_consent_cgm + revoke_consent_cgm
```

## CI

`.github/workflows/ci.yml` runs on push/PR to `main` across Ubuntu, Windows, macOS × Python 3.10/3.11/3.12. Steps: install deps → `pytest -v` → `strava-coach --help`.

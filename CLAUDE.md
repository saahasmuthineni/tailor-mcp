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
                         |                 ╲
                    ChildMCP                VaultLayer   ← framework-level
             (biosensor tier)          (reorientation tier;  skips gates)
          e.g. RunningChild, CGMChild   Obsidian vault + SQLite index
```

**Two persistence tiers, architecturally distinct:**

| Tier | Purpose | Storage | Lifecycle |
|------|---------|---------|-----------|
| **Biosensor** (ChildMCP) | Ingest, cache, rate-limit raw data | SQLite (`activities.db`) | Ephemeral — rebuildable by re-sync |
| **Reorientation** (VaultLayer) | Cross-session analytical memory | Obsidian vault (markdown + frontmatter) | Durable — canonical record |

Markdown files in the Obsidian vault are the **source of truth** for analytical knowledge; `vault.db` is a query-optimization index. Obsidian is the human-facing view of the same data the LLM accesses via vault tools.

**Key principle**: Behavioral rules (consent gates, cost gates, access tiers) live server-side, not in the LLM. Any LLM client gets identical enforcement. Vault tools skip these gates (metadata, not biometric data) — only param validation and audit apply.

## File Structure

```
src/biosensor_mcp/
  __init__.py              # Package metadata (v4.0.0)
  __main__.py              # CLI: serve | setup | status | demo | uninstall | --help
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
      child.py             # RunningChild(ChildMCP) — 12 tools, 3 tiers
      processing.py        # RunningProcessing — stateless analytics
      strava_api.py        # OAuth + rate-limited Strava API client
  demo/
    __init__.py            # Exports run_demo
    sample_data.py         # Synthetic 60-minute run data (reproducible, stdlib-only)
    runner.py              # Demo runner — execute analytics on synthetic data
  vault/
    __init__.py            # Exports VaultWriter, VaultLayer
    layer.py               # VaultLayer — framework-level reorientation tier, 7 tools
    writer.py              # Post-execute hook; atomic file writes → Obsidian
    renderer.py            # Pure markdown generation (run/trend/compare notes)
    parser.py              # Frontmatter / YAML parsing for vault notes
    rescan.py              # Filesystem → SQLite index revalidation
    storage.py             # VaultStorage — SQLite index of vault notes

tests/
  test_processing.py       # Pure-function analytics tests (no I/O)
  test_middleware.py       # Framework security component tests
  test_router.py           # Router pipeline integration tests (includes VaultLayer)
  test_vault_layer.py      # VaultLayer handler tests
  test_vault_renderer.py   # Markdown renderer tests
  test_vault_writer.py     # VaultWriter atomic write + frontmatter tests
  test_vault_parser.py     # Vault frontmatter parser tests
  test_vault_rescan.py     # Vault index revalidation tests
  security_probe.py        # Standalone security probe (runs in CI, no pytest needed)
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
| 2 — Consent | Downsampled streams at 5–30s for visualisation | 3,000–7,000 | Biometric consent |
| 3 — Cost | Per-second streams with precision reduction | 25,000–60,000 | Consent + cost approval |

~90% of questions are answered at Tier 1 with zero raw biometric data leaving the machine.

## Running Child — 12 Tools

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
| `strava_downsampled_streams` | 2 | HR, pace, GPS at 5–30s intervals |
| `strava_full_streams` | 3 | Per-second data with precision reduction |

## Running and Testing

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run tests
pytest -v

# CLI smoke test
biosensor-mcp --help

# Demo mode (no Strava account needed)
biosensor-mcp demo

# OAuth setup
biosensor-mcp setup

# Start MCP server
biosensor-mcp serve
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
| `BIOSENSOR_CONFIG_DIR` | `~/.biosensor-mcp` | Token, user config, rate limit files |
| `BIOSENSOR_DATA_DIR` | `~/.biosensor-mcp/data` | SQLite databases |
| `STRAVA_STREAM_CACHE_TTL_DAYS` | `7` | Stream cache eviction |

User config at `~/.biosensor-mcp/user_config.json`:
```json
{ "max_hr": 185, "resting_hr": 55, "home_lat": 42.360, "home_lng": -71.058 }
```

## Claude Desktop Integration

```json
{
  "mcpServers": {
    "biosensor-mcp": {
      "command": "~/.biosensor-mcp/venv/bin/python",
      "args": ["-m", "biosensor_mcp", "serve"],
      "env": {
        "BIOSENSOR_CONFIG_DIR": "~/.biosensor-mcp",
        "BIOSENSOR_DATA_DIR": "~/.biosensor-mcp/data"
      }
    }
  }
}
```

## Adding a New Biosensor Child

Implement 4 abstract items and register:

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
        return [ToolDefinition("cgm_daily_report", 1, "Time-in-range, variability", {...})]

    @property
    def param_schemas(self) -> dict: ...

    async def execute(self, tool_name, params) -> dict: ...

    async def estimate_cost(self, tool_name, params) -> CostEstimate: ...

# In __main__.py cmd_serve():
router.register_child(CGMChild(config_dir, data_dir))
# Router auto-generates approve_consent_cgm + revoke_consent_cgm
```

## Framework-Level Infrastructure (Not a ChildMCP)

Components that represent durable cross-session state — not biosensor domains — register directly with the router and bypass the security pipeline (consent/cost gates don't apply to metadata).

`VaultLayer` is the reference implementation of this pattern:

```python
# In __main__.py cmd_serve():
from biosensor_mcp.vault import VaultLayer

router.register_vault_layer(VaultLayer(
    vault_path=vault_path,
    vault_writer=vault_writer,
    backfill_config={                       # decouples from sibling tool names;
        "list_tool": "strava_list_runs",    # cross-child knowledge lives at the
        "report_tool": "strava_run_report", # wiring site, not inside the vault
    },
))
```

Key differences from a ChildMCP:
- No `domain`, `consent_info`, or `estimate_cost()` — these are biosensor-tier concerns
- Dispatch skips circuit breaker, consent gate, cost gate, and post-execute hooks
- Only param validation + audit apply
- Tools must still have unique names (collision with any registered child is rejected)

## CI

`.github/workflows/ci.yml` runs on push/PR to `main` across Ubuntu, Windows, macOS × Python 3.10/3.11/3.12. Steps: install deps → `pytest -v` → `biosensor-mcp --help`.

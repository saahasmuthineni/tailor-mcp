# CLAUDE.md — Biosensor MCP

## What This Project Is

**Local-first infrastructure for LLM-assisted analysis of high-frequency biometric data — built for health research workflows where data governance, audit trails, and reproducibility matter.**

The intended users are health researchers (academic medical centers, mHealth labs, sleep/CGM/cardiology groups) and the research-software engineers who support them. The deliverables are a router that owns cross-cutting concerns, a ChildMCP extension point for new data sources, and a vault layer for durable cross-session analytical memory.

The running child (Strava data) is one **worked example** of the ChildMCP pattern — a complete, copyable template for wrapping a streaming biometric source. It is retained for teaching value; it is not the canonical use case.

## Problems this is built against

1. **Data governance.** Hosted LLMs are the wrong home for participant biometric data. The tier model and local-first processing are the structural response.
2. **Reproducibility.** LLM-assisted analyses in chat windows leave no durable trace. The audit log (every call logged to SQLite, scoped by optional `subject_id`) and `_meta` provenance stamps are the response.
3. **Longitudinal analytical memory.** Observations made in one session disappear when the chat ends. The vault layer (themes, moments, evidence logs, append-only) is the response.

Token efficiency is a useful side effect of computing summaries server-side. It is not the headline.

## Architecture

```
LLM client <--> RouterMCP (validate → circuit break → consent → cost → execute
                           → PHI scrub → audit + provenance stamp)
                   |                 ╲
              ChildMCP                VaultLayer   ← framework-level
     (one per data source)      (reorientation tier;  skips consent/cost gates)
  e.g. RunningChild, CGMChild    Obsidian vault + SQLite index
```

**Two persistence tiers, architecturally distinct:**

| Tier | Purpose | Storage | Lifecycle |
|------|---------|---------|-----------|
| **Biosensor** (ChildMCP) | Ingest, cache, rate-limit raw data | SQLite (`activities.db`) | Ephemeral — rebuildable by re-sync |
| **Reorientation** (VaultLayer) | Cross-session analytical memory | Obsidian vault (markdown + frontmatter) | Durable — canonical record |

Markdown files in the Obsidian vault are the **source of truth** for analytical knowledge; `vault.db` is a query-optimization index. Obsidian is the human-facing view of the same data the LLM accesses via vault tools.

**Key principle**: Behavioral rules (consent gates, cost gates, access tiers, PHI scrubbing) live server-side, not in the LLM. Any LLM client gets identical enforcement. Vault tools skip the biosensor-tier gates (the analyst's notes are not participant biometric data), including the PHI-scrubbing seam — only param validation and audit apply.

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
    router.py              # RouterMCP — security pipeline + dispatch +
                           #   _meta provenance stamps, PHI-scrub seam
    middleware.py          # CircuitBreaker, ConsentGate, CostGate,
                           #   PHIScrubber (no-op default), AuditLog
                           #   (with subject_id), TokenLedger, ParamValidator
    storage.py             # BaseStorage — thread-safe SQLite with WAL
  children/
    __init__.py            # Docstring framing children as the extension
                           #   point for new data sources
    running/               # Worked example — see __init__.py
      __init__.py          # Exports RunningChild; framed as a template
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

## Security Pipeline (Cheapest First)

| Layer | Class | Purpose |
|-------|-------|---------|
| 1 | `ParamValidator` | Type/range/pattern checks — reject before any work |
| 2 | `CircuitBreaker` | Block domain after 3 consecutive failures; auto-reset after 5 min |
| 3 | `ConsentGate` | Per-domain biometric consent, session-scoped, revocable |
| 4 | `CostGate` | Pre-estimate tokens before execution; gate if > 35,000 tokens |
| 5 | `PHIScrubber` | Institutional PHI-stripping seam; no-op default, subclass-per-child when a real policy exists |
| 6 | `AuditLog` + `TokenLedger` | Every call logged to SQLite with optional `subject_id` scoping; cumulative session spend |

Every successful result also carries a `_meta` block stamped with `package_version`, `tool_name`, and a UTC `called_at` timestamp — minimum-viable provenance for results that may end up in a paper.

## Three-Tier Access Model

The tier model is a technical implementation of data minimization — the question "at what resolution does the analyst actually need this?" made executable.

| Tier | What the LLM Sees | Tokens (running example) | Gate |
|------|-----------------|--------|------|
| 1 — Free | Server-computed reports (splits, zones, drift, decoupling, EF, trends) | 200–1,500 | None |
| 2 — Consent | Downsampled streams at 5–30s for visualization | 3,000–7,000 | Biometric consent |
| 3 — Cost | Per-timestamp streams with precision reduction | 25,000–60,000 | Consent + cost approval |

Most analytical questions are answerable at Tier 1 with zero raw biometric data leaving the machine. Token counts are illustrative and come from the running child; other domains will have different baselines.

## Running Child (worked example) — 12 Tools

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

Architectural decisions are captured as numbered ADRs under
[docs/adr/](docs/adr/) — one file per decision, each with its own
context / decision / consequences / alternatives. Summaries below link
to the full record.

- **[ADR 0001 — Audit log is the backbone](docs/adr/0001-audit-log-as-backbone.md).** Every tool call lands in `audit.db`: timestamp, domain, tool, tier, parameters, token estimate, outcome, latency, optional error, optional `subject_id`. Durable evidence of how an analyst accessed participant data — the single most load-bearing feature for research use.
- **[ADR 0002 — `subject_id` scoping](docs/adr/0002-subject-id-scoping.md).** First-class audit column, optional on calls. The router extracts `subject_id` from parameters and threads it to every audit row; children adopt it in `param_schemas` incrementally. Legacy `audit.db` migrates via `ALTER TABLE`.
- **[ADR 0003 — PHI scrubbing is a seam, not a policy](docs/adr/0003-phi-scrubber-seam.md).** `PHIScrubber.scrub()` is a no-op by default; institutions subclass. The default emits a one-time warning on first construction and exposes `scrubber_id` so audit rows distinguish misconfigured deployments from real policies.
- **[ADR 0004 — Structured `LLMInstruction`](docs/adr/0004-structured-llm-instruction.md).** Consent and cost gates return a JSON object with individually checkable `must_do`, `must_not_do`, and `on_ambiguous_reply` fields — not a free-text paragraph. Makes compliance auditable.
- **[ADR 0005 — Pre-estimation, not post-billing](docs/adr/0005-cost-pre-estimation.md).** `CostGate` calls `child.estimate_cost()` before execution using stream metadata (point counts), never the full payload. Estimator failures fail closed.

### Implementation notes

Domain-specific tuning choices that inform behavior but aren't
architectural decisions in the ADR sense:

- **Grade precision at 1 decimal**: GAP calculation uses `cost = 1 + 0.03 * grade%`. Rounding grade to integer introduces ~3% split error. All other numerics are reduced more aggressively.
- **0.5 m/s stop threshold**: 0.3 m/s was too aggressive (flagged slow shuffles at end of hard efforts). 0.5 m/s (~1.8 km/h) is the designed "completely stopped" signal.
- **Spike detection 30-second cooldown**: A single Apple Watch sensor catchup burst can generate dozens of overlapping anomaly entries without the cooldown.
- **orjson with stdlib fallback**: `_dumps`/`_loads` wrappers in `middleware.py` are transparent to all consumers.
- **`router.close()` on Windows**: SQLite WAL connections must be explicitly closed before the process exits on Windows. Call `router.close()` in tests and server shutdown to release file locks.

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

## Adding a New ChildMCP (new data source)

Children are the framework's extension point. Each one wraps one data source (CSV directory, EDF file, FHIR bundle, REDCap export, vendor API) and exposes tiered tools; the router handles everything else uniformly.

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

Components that represent durable cross-session state — not biosensor domains — register directly with the router and bypass the biosensor-tier gates (consent, cost, circuit breaker, PHI scrub). Param validation and audit still apply.

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
- Dispatch skips circuit breaker, consent gate, cost gate, PHI-scrub seam, and post-execute hooks
- Only param validation + audit apply
- Tools must still have unique names (collision with any registered child is rejected)

## Further reading

- [README.md](README.md) — audience-facing overview.
- [docs/design/research-framing.md](docs/design/research-framing.md) — the longer-form document aimed at health-research reviewers and RSEs.
- [docs/adr/](docs/adr/) — Architecture Decision Records for the framework's load-bearing choices.
- [ROADMAP.md](ROADMAP.md) — explicitly deferred work with effort/impact triage (real PHI scrubbing, new children, deterministic replay, full provenance hashing, per-subject tool-parameter scoping, multi-analyst vault attribution, vault freeze, worked-example notebook, evaluation harness).

## CI

`.github/workflows/ci.yml` runs on push/PR to `main` across Ubuntu, Windows, macOS × Python 3.10/3.11/3.12. Steps: install deps → `pytest -v` → `biosensor-mcp --help`.

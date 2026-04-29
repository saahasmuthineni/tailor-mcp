# CLAUDE.md — Biosensor MCP

> **v6.0 (2026-04-23)** — vault-only release. The reorientation tier
> gained seven governance features (snapshot, inbox, health check,
> evidence provenance, theme lifecycle enrichment, corrections,
> session divergence); see
> [ADR 0006](docs/adr/0006-vault-overhaul-v6.md). No router, security,
> child, or CLI changes.

## What This Project Is

**Local-first infrastructure for LLM-assisted analysis of high-frequency biometric data — built for health research workflows where data governance, audit trails, and reproducibility matter.**

The intended users are health researchers (academic medical centers, mHealth labs, sleep/CGM/cardiology groups) and the research-software engineers who support them. The deliverables are a router that owns cross-cutting concerns, a ChildMCP extension point for new data sources, and a vault layer for durable cross-session analytical memory.

The running child (Strava data) is one **worked example** of the ChildMCP pattern — a complete, copyable template for wrapping a streaming biometric source. It is retained for teaching value; it is not the canonical use case.

## Workflow: manager mode

Manager mode is the default working style on this repo. The general conventions — invocation pattern, reporting cadence, when to interrupt vs proceed, the "promote at 3+ uses" bar for new agents — live in `~/.claude/CLAUDE.md` (the global file) so they're consistent across projects. This section names the **specialists this repo provides**.

| Agent | Owns | When to fire |
|---|---|---|
| [`vault-smoke-validator`](.claude/agents/vault-smoke-validator.md) | End-to-end vault behaviour against a temp vault | After any change to `framework/vault/` |
| [`ci-gate-runner`](.claude/agents/ci-gate-runner.md) | pytest + ruff + security probe + CLI smoke, with failure forensics | Before any commit/PR; whenever asking "is the working tree shippable?" |
| [`integration-auditor`](.claude/agents/integration-auditor.md) | Diff-vs-base audit: what's *lost* vs *gained*, classifies losses as Justified / Suspicious / Needs review | Before merging any non-trivial branch — answers "is anything load-bearing being quietly removed?" |
| [`release-shipper`](.claude/agents/release-shipper.md) | Version bump → CLAUDE.md banner → ROADMAP.md → commit → push → PR; **executes `gh pr merge --admin --merge <PR>` once the boss says "ship it"** | When a feature is ready to ship. Boss approves the merge; the agent runs the mechanics. Also accepts merge-only invocations against an existing PR. |
| [`adr-drafter`](.claude/agents/adr-drafter.md) | Drafts a numbered ADR matching the existing voice | When the boss says "ADR this" or a non-obvious decision needs a permanent record |
| [`triage-debugger`](.claude/agents/triage-debugger.md) | Diagnoses a single failure, reports root cause + suggested fix without applying it. Spawnable by *any* agent | When ci-gate-runner, integration-auditor, vault-smoke-validator, or the main session hits a failure they want triaged |

The agents are checked into the repo so the team is reproducible across machines. Per `.gitignore`: `.claude/*` ignores per-machine settings; `!.claude/agents/` re-includes the roster. New specialists land here when the same kind of work has shown up in 3+ sessions on this project.

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
  __init__.py              # Package metadata (v6.0.0)
  __main__.py              # CLI: serve | setup | status | demo | uninstall | --help
  wizard.py                # OAuth setup wizard (localhost callback server)
  config.py                # Centralised env-var + user_config.json reader
  framework/
    __init__.py            # Public API exports
    interfaces.py          # ChildMCP ABC, ToolDefinition, CostEstimate,
                           #   ValidationSchema, ConsentInfo, ConsentScope,
                           #   CostContext, LLMInstruction
    router.py              # RouterMCP — security pipeline + dispatch +
                           #   _meta provenance stamps, PHI-scrub seam
    security.py            # ParamValidator, CircuitBreaker, ConsentGate,
                           #   PHIScrubber (no-op default — see ADR 0003)
    cost.py                # CostGate, TokenLedger, estimate_tokens
    audit.py               # AuditLog (with subject_id) + JSON helpers
                           #   (_dumps, _loads, JSON_BACKEND)
    storage.py             # BaseStorage — thread-safe SQLite with WAL
    vault/                 # Reorientation tier (framework-level
                           #   infrastructure, not a ChildMCP)
      __init__.py          # Exports VaultLayer, VaultWriter
      layer.py             # VaultLayer — 22 tools (v6.0)
      writer.py            # Post-execute hook; atomic file writes → Obsidian
      renderer.py          # Pure markdown (run/trend/compare/theme/moment/snapshot)
      parser.py            # Frontmatter / YAML parsing for vault notes
      rescan.py            # Filesystem → SQLite index revalidation
      storage.py           # VaultStorage — SQLite index of vault notes
  children/
    __init__.py            # Docstring framing children as the extension
                           #   point for new data sources
    running/               # Worked example — see __init__.py
      __init__.py          # Exports RunningChild; framed as a template
      child.py             # RunningChild(ChildMCP) — 12 tools, 3 tiers
      processing.py        # RunningProcessing — stateless analytics
      strava_api.py        # OAuth + rate-limited Strava API client
    csv_dir/               # Generic CSV directory child
      __init__.py          # Exports CSVDirectoryChild, CSVProcessing
      child.py             # CSVDirectoryChild(ChildMCP) — 5 tools, 3 tiers
      processing.py        # CSVProcessing — stateless analytics
    template/              # Runnable starting-point child (copy + rename)
      __init__.py          # Rename checklist for new children
      child.py             # TemplateChild(ChildMCP) — minimal 3-tier skeleton
      processing.py        # TemplateProcessing — stateless analytics stubs
  demo/
    __init__.py            # Exports run_demo
    sample_data.py         # Synthetic 60-minute run data (reproducible, stdlib-only)
    runner.py              # Demo runner — execute analytics on synthetic data

tests/                     # Mirrors src/ layout
  conftest.py              # Shared fixtures (tmp_data_dir, tmp_vault_dirs)
                           #   + probe marker registration
  security_probe.py        # Standalone security probe (runs in CI, no pytest needed)
  test_security_probe_pytest.py   # @pytest.mark.probe wrapper around the standalone probe
  framework/
    test_router.py         # Router pipeline integration tests (includes VaultLayer)
    test_security.py       # ParamValidator / CircuitBreaker / ConsentGate / PHIScrubber
    test_cost.py           # CostGate / TokenLedger / estimate_tokens
    test_audit.py          # AuditLog: subject_id, params truncation, keyword-only error
    vault/
      test_layer.py        # VaultLayer handler tests
      test_renderer.py     # Markdown renderer tests
      test_writer.py       # VaultWriter atomic write + frontmatter tests
      test_parser.py       # Vault frontmatter parser tests
      test_rescan.py       # Vault index revalidation tests
  children/
    running/
      test_child_schema.py # Schema contract tests for RunningChild tools
      test_processing.py   # Pure-function analytics tests (no I/O)
    csv_dir/
      test_csv_shape.py    # Shape contract tests (ported from template)
      test_csv_processing.py  # Pure-function analytics tests
    template/
      test_template_shape.py     # Shape contract tests for the template child
      test_template_processing.py # Pure-function analytics tests
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

## CSV Directory Child — 5 Tools

Opt-in via `csv_dir` key in `user_config.json`. Wraps a local directory of per-subject CSV files — no OAuth, no vendor API. The "ingest a directory" pattern complementing the running child's "wrap an API" pattern.

| Tool | Tier | Description |
|------|------|-------------|
| `csv_list_files` | 1 | List CSV files with size and column names |
| `csv_file_detail` | 1 | Single-file metadata + per-column stats |
| `csv_summary_report` | 1 | Per-column summaries, time range, completeness |
| `csv_downsampled` | 2 | Decimated rows at every Nth interval |
| `csv_raw_stream` | 3 | Full per-row data with precision reduction |

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
- **orjson with stdlib fallback**: `_dumps`/`_loads` wrappers in `framework/audit.py` are transparent to all consumers.
- **`router.close()` on Windows**: SQLite WAL connections must be explicitly closed before the process exits on Windows. Call `router.close()` in tests and server shutdown to release file locks.
- **`subject_id` on `strava_*` tools**: All 12 running tools declare an optional `subject_id` parameter (pattern `^[A-Za-z0-9_\-]{1,64}$`) for audit-log scoping. Does not filter Strava data — one authenticated Strava account may cover multiple study participants, and `subject_id` is the caller's statement of which one this call is about. Vault tools do not yet declare it (ADR 0002, ROADMAP).

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `BIOSENSOR_CONFIG_DIR` | `~/.biosensor-mcp` | Token, user config, rate limit files |
| `BIOSENSOR_DATA_DIR` | `~/.biosensor-mcp/data` | SQLite databases |
| `STRAVA_STREAM_CACHE_TTL_DAYS` | `7` | Stream cache eviction |

User config at `~/.biosensor-mcp/user_config.json`:
```json
{
  "max_hr": 185, "resting_hr": 55,
  "home_lat": 42.360, "home_lng": -71.058,
  "csv_dir": {
    "path": "/path/to/csv/directory",
    "timestamp_column": "timestamp",
    "timestamp_format": "%Y-%m-%dT%H:%M:%S",
    "value_columns": {
      "heart_rate": "Heart rate (bpm)",
      "glucose": "Blood glucose (mg/dL)"
    }
  }
}
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

For a runnable starting point that already passes shape tests, copy
`src/biosensor_mcp/children/template/` and rename. See its
`__init__.py` for the rename checklist.

## Framework-Level Infrastructure (Not a ChildMCP)

Components that represent durable cross-session state — not biosensor domains — register directly with the router and bypass the biosensor-tier gates (consent, cost, circuit breaker, PHI scrub). Param validation and audit still apply.

`VaultLayer` is the reference implementation of this pattern:

```python
# In __main__.py cmd_serve():
from biosensor_mcp.framework.vault import VaultLayer

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

### VaultLayer — 22 Tools (v6.0)

All tools are Tier 1 and skip the biosensor-tier gates.

Orientation & browse:
| Tool | Description |
|------|-------------|
| `vault_get_snapshot` | Read `snapshot.md` — fastest session-start orientation. Falls back to `vault_get_fitness_summary` when no snapshot exists. |
| `vault_generate_snapshot` | (Re)write `snapshot.md` with open themes, recent moments, weekly run aggregates, and vault health. Call at session end. |
| `vault_get_fitness_summary` | Older orientation tool: aggregate weekly fitness + open themes + recent moments by scanning the index. |
| `vault_list_notes` / `vault_read_note` / `vault_search_notes` | Browse, read, full-text search. |
| `vault_list_anomalies` | Runs with `anomaly_count > 0`. |
| `vault_traverse_links` | Wikilink neighbourhood of a note (no bodies). |

Themes & moments:
| Tool | Description |
|------|-------------|
| `vault_list_themes` / `vault_read_theme` | Compact rows or full body of a persistent hypothesis. |
| `vault_upsert_theme` | Create or update. Supports reframe (new hypothesis → `## Prior Framings`), thinking entries, evidence provenance (`evidence_source_*` + `evidence_verification`), and fold-back on resolution. |
| `vault_correct_evidence` | Mark a specific evidence block as superseded by timestamp; preserves the original. |
| `vault_list_moments` / `vault_capture_moment` | Aha-moment notes. |
| `vault_capture_session` | Session-boundary bundle: summary moment + N theme updates + N moments + optional `divergence`. |

Annotation & maintenance:
| Tool | Description |
|------|-------------|
| `vault_annotate_run` | Persist insight notes back to a run note. |
| `vault_backfill` | LLM-driven, server-orchestrated note generation for cached activities. |
| `vault_rescan` | Full filesystem sweep — reconcile SQLite index with user edits. |
| `vault_health_check` | Stale themes, orphaned moments, themes without evidence, inbox depth, counts by status. |

Inbox (low-friction capture):
| Tool | Description |
|------|-------------|
| `vault_inbox_add` | Append a timestamped line to `inbox.md`. |
| `vault_inbox_list` | Parse inbox lines into structured items. |
| `vault_inbox_drain` | Bulk process items: promote to moment / append to theme as evidence / discard. |

## Further reading

- [README.md](README.md) — audience-facing overview.
- [docs/design/research-framing.md](docs/design/research-framing.md) — the longer-form document aimed at health-research reviewers and RSEs.
- [docs/adr/](docs/adr/) — Architecture Decision Records for the framework's load-bearing choices.
- [ROADMAP.md](ROADMAP.md) — explicitly deferred work with effort/impact triage (real PHI scrubbing, new children, deterministic replay, full provenance hashing, per-subject tool-parameter scoping, multi-analyst vault attribution, vault freeze, worked-example notebook, evaluation harness).

## CI

`.github/workflows/ci.yml` runs on push/PR to `main` across Ubuntu, Windows, macOS × Python 3.10/3.11/3.12. Steps: install deps → `pytest -v` → `biosensor-mcp --help`.

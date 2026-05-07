# Biosensor MCP — LLM-Assisted Analysis for Health Research

[![CI](https://github.com/saahasmuthineni/Biosensor-to-LLM-Connector/actions/workflows/ci.yml/badge.svg)](https://github.com/saahasmuthineni/Biosensor-to-LLM-Connector/actions/workflows/ci.yml)
[![Python 3.10 | 3.11 | 3.12](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/downloads/)
[![Platforms](https://img.shields.io/badge/platforms-linux%20%7C%20macos%20%7C%20windows-lightgrey)](.github/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

Local-first infrastructure for LLM-assisted analysis of high-frequency
biometric data — built for health research workflows where data
governance, audit trails, and reproducibility matter.

## 30-second quickstart

For a PI or analyst running a multi-subject CSV pilot:

```bash
uv tool install git+https://github.com/saahasmuthineni/Biosensor-to-LLM-Connector.git
biosensor-mcp pilot          # three prompts, end-to-end smoke check
```

For a developer exploring the framework:

```bash
git clone https://github.com/saahasmuthineni/Biosensor-to-LLM-Connector.git
cd Biosensor-to-LLM-Connector
pip install -e ".[dev]"
biosensor-mcp demo           # researcher first-look: HIP Lab cohort tools on bundled fixtures
biosensor-mcp --help         # see all commands
```

Then open [**docs/guides/worked-example.ipynb**](docs/guides/worked-example.ipynb) for a 10-minute end-to-end walkthrough: the router pipeline, a Tier-1 call, an audit row, the analyst-side consent gate firing, and a vault theme round-tripping to Obsidian-compatible markdown — all on synthetic data, no credentials required.

### Start here

- **PI evaluating for a study** → [Why this exists](#why-this-exists) · [How data minimization works](#how-data-minimization-works) · [10-minute worked example notebook](docs/guides/worked-example.ipynb) · [Status & retention](#status)
- **Analyst / research-software engineer wiring this up** → [Install & run](#install--run) · [Running child tools](#running-child-tools) · [Architecture](#architecture)
- **IRB reviewer evaluating risk** → [How data minimization works](#how-data-minimization-works) · [Status & retention](#status) · [ADR 0001 — audit log](docs/adr/0001-audit-log-as-backbone.md) · [ADR 0003 — PHI scrubber seam](docs/adr/0003-phi-scrubber-seam.md) · [ADR 0009 — `subject_id` integrity](docs/adr/0009-vault-subject-keying.md) · [ADR 0013 — cache purge on consent revocation](docs/adr/0013-cache-only-purge-on-consent-revocation.md)
- **Developer trying the demo** → [Install & run](#install--run)
- **Architect / integrator** → [Architecture](#architecture) · [Adding a new child data source](CLAUDE.md#adding-a-new-childmcp-new-data-source)
- **Curious where this is going** → [What's next](#whats-next) · [full ROADMAP.md](ROADMAP.md)

---

## Who this is for

**For you if** you run health research involving high-frequency biometric
streams, you use an MCP-speaking LLM client (Claude Desktop, Claude API,
VS Code), and you need audit trails and data-minimization controls that
survive beyond a single chat session.

**Not for you if** you want clinical decision support, you're OK pasting
streams into a hosted chat, or you need a finished product rather than
extensible research infrastructure.

---

## What you get

| Capability | What it does |
|---|---|
| **Local-first router** | Runs next to the data. Only what the active tier permits crosses the boundary — Tier 1 ships server-computed summaries; Tiers 2 and 3 release stream data behind the analyst-side consent gate. With the optional [local-LLM guardian](docs/guides/local-llm-guardian.md) opted in (per [ADR 0022](docs/adr/0022-local-llm-guardian.md)), biometric streams stay on the analyst's machine at every tier — including from the hosted LLM. |
| **Tiered access** | Every tool declares an access tier: 1 returns computed summaries, 2 returns downsampled views behind an analyst-side consent gate, 3 returns raw streams behind that gate plus cost approval. Data minimization, implemented. |
| **PHI-scrubber seam** | A documented institutional override point. **Default is a no-op** — institutions subclass to wire their IRB-approved policy. The default surfaces a `scrubber_warning` field in every successful `_meta` block so a misconfigured deployment is visible inside the LLM transcript. See [ADR 0003](docs/adr/0003-phi-scrubber-seam.md). |
| **Durable audit log** | Every call lands in SQLite: timestamp, tool, tier, parameters, outcome, latency, `scrubber_id`, optional `subject_id`. Attachable to a protocol amendment or replication package. |
| **Provenance stamps** | Every result carries a `_meta` block — package version, tool name, UTC timestamp — so any output in a paper is traceable to the code that produced it. |
| **Local-LLM guardian** *(opt-in)* | A framework-tier component that runs an LLM on the analyst's machine to compose structured natural-language responses over deterministic processing output. Cited numerical claims come from `processing.py` and stay deterministic; LLM-generated narrative is explicitly labelled non-citable in `_meta`. Four tiers (Scout/Sentinel/Guardian/Titan) span 4 GB laptops to 32 GB workstations. See [ADR 0022](docs/adr/0022-local-llm-guardian.md) and the [setup guide](docs/guides/local-llm-guardian.md). |
| **Obsidian-backed vault** | Cross-session analytical memory: themes (persistent research questions), moments (observations), evidence logs. Markdown is the source of truth; SQLite makes it queryable. |
| **Extensible child pattern** | Each data source is a ChildMCP. New children inherit the full governance pipeline by implementing a small interface. |

---

## Example interaction

```
User:   summarize my last run
Claude: [calls strava_run_report — Tier 1, no consent required]

Tool:   {"summary": "6.2 mi · 48:12 · avg HR 152",
         "drift_pct": 3.2, "efficiency_factor": 1.71,
         "_meta": {"package_version":   "6.5.0",
                   "tool_name":         "strava_run_report",
                   "called_at":         "2026-04-13T15:42:11Z",
                   "scrubber_id":       "noop",
                   "scrubber_warning":  "PHIScrubber is a no-op default; subclass and wire your institution's policy before processing real PHI"}}

Claude: Your last run was 6.2 miles in 48:12 with 3.2 % HR drift and
        an efficiency factor of 1.71 — aerobic base looks solid.
        The audit log recorded this call; the _meta block stamps
        the code version that produced these numbers.
```

The tier model, audit row, and `_meta` stamp all fired without the
analyst doing anything. That's the point.

---

## Why this exists

Research groups working with high-frequency biometric data (CGM, ECG,
sleep staging, wearable streams) keep hitting the same three problems
when they use LLMs as analytical assistants:

| Problem | Response |
|---|---|
| **Data governance** — hosted LLMs are the wrong home for participant biometric data. Pasting streams into web chats is usually against policy, sometimes against law, and always leaves no defensible trace. | Tier model + local-first processing. Raw data never leaves the machine; only server-computed summaries do. |
| **Reproducibility** — analyses in chat windows don't replay six months later. No log of which tool saw which data, no hook for a replication package. | Audit log (every call in SQLite with optional `subject_id`) + `_meta` provenance stamps on every result. |
| **Longitudinal memory** — observations get dropped at session end. The note an analyst made about a participant in April is exactly what the analyst in September needs. | Vault layer: themes, moments, evidence logs — append-only, Obsidian-backed, queryable across sessions. |

Biosensor MCP is a local MCP server that sits between any MCP-speaking
client and your data sources, owning the cross-cutting concerns — gating,
scrubbing, audit, provenance, durable memory — that each problem needs.

### "Why not just use Claude's memory tool?"

Hosted Memory is a chat-convenience feature: cross-session continuity
inside one vendor's product, opaque to the user, mutable, and
conversation-scoped. Biosensor MCP's vault is governance
infrastructure: append-only markdown that survives the LLM client,
human-readable in Obsidian or any text editor, supersession-tracked
via [`vault_correct_evidence`](CLAUDE.md#vaultlayer--25-tools-v61),
study-scoped via `subject_id`, and inspectable down to the SQLite
index. Same word, different artifact category. For a chat assistant
remembering your name across conversations, Hosted Memory is the right
tool. For an analytical record an IRB or PI can attach to a protocol
amendment six months later, it is not. Biosensor MCP's vault layer
exists for the second case.

For the related question of *"can I use Anthropic Managed Agents on
top of Biosensor MCP?"* — yes, the framework supports a network-MCP
deployment where a hosted agent calls Biosensor MCP as a governed
data boundary. See [docs/design/managed-agents-compat.md](docs/design/managed-agents-compat.md)
for which threat models that path addresses and which it doesn't.

---

## How data minimization works

> The "consent gate" referenced below is a session-scoped switch the
> analyst toggles to unlock higher-tier data views inside one chat —
> distinct from the participant's informed consent under 45 CFR 46,
> which is obtained out-of-band as part of study enrollment.

| Tier | What the LLM sees | Typical tokens | Gate |
|---|---|---|---|
| **1 — Free** | Server-computed reports (splits, zones, drift, decoupling, EF, trends). Where geographic data appears at Tier 1 — e.g. stop-analysis lat/lng — coordinates are coarsened to ~100 m precision (3-decimal) per HIPAA Safe Harbor §164.514(b)(2)(i)(B). | 200 – 1,500 | *None* |
| **2 — Consent** | Downsampled streams at 5 – 30 s for visualization | 3,000 – 7,000 | Biometric consent (analyst-side) |
| **3 — Cost** | Per-timestamp streams with precision reduction | 25,000 – 60,000 | Biometric consent (analyst-side) + cost approval |

Most analytical questions are answerable at Tier 1 — zero raw biometric
data leaving the machine. Token counts are from the running child; other
domains will differ.

Every tool call is persisted to SQLite with enough context to reconstruct
what happened:

```json
{
  "timestamp":      "2026-04-13T15:42:11.203Z",
  "domain":         "running",
  "tool_name":      "strava_run_report",
  "tier":           1,
  "params":         {"activity_id": 14829301},
  "token_estimate": 1180,
  "outcome":        "ok",
  "duration_ms":    142,
  "subject_id":     "P-017",
  "scrubber_id":    "noop"
}
```

Every successful result carries a `_meta` provenance stamp:

```json
{
  "_meta": {
    "package_version":  "6.5.0",
    "tool_name":        "strava_run_report",
    "called_at":        "2026-04-13T15:42:11.345Z",
    "scrubber_id":      "noop",
    "scrubber_warning": "PHIScrubber is a no-op default; subclass and wire your institution's policy before processing real PHI"
  }
}
```

The vault layer adds cross-session analytical memory — **themes**
(persistent research questions with appending evidence logs) and
**moments** (timestamped observations linkable to participants or runs).
See [research-framing.md](docs/design/research-framing.md#the-vault-layer--longitudinal-analytical-memory)
for the full treatment.

<p align="center">
  <img src="docs/assets/vault-insights.svg" alt="Obsidian-backed vault — themes, moments, evidence logs" width="760">
</p>

---

## Status

- One child ships: a Strava running child exercising all three tiers,
  OAuth, cached streams, and the vault writer. Treat it as a template,
  not a dependency.
- A generic CSV-directory child ships alongside the running child (one
  OAuth-free, no-vendor-API path for institutional CSV exports). CGM,
  sleep, ECG, EDF, and FHIR children are roadmap. See [ROADMAP.md](ROADMAP.md).
- PHI scrubbing ships as a documented no-op seam. Institutions subclass
  once their policy is defined. The default scrubber surfaces a warning
  in every successful result's `_meta` block so a no-op deployment
  cannot silently masquerade as a scrubbed one.
- Per-subject **audit-log scoping** is first-class on the biosensor
  tier. `RunningChild` declares `subject_id` on all 12 `strava_*`
  tools; `csv_dir` declares it on all 7 tools. This is caller-asserted
  scoping for the audit log; it does **not** filter source data, since
  one authenticated upstream account may legitimately cover multiple
  study participants.
- Per-subject **vault-tier keying** is first-class
  ([ADR 0009](docs/adr/0009-vault-subject-keying.md)). Themes carry
  an optional, set-once `subject_id` (promotion `None → P004`
  permitted; reassignment `P003 → P007` is a hard error). Evidence
  and moments stamp the writing call's subject. List/search filters
  use the IS-NULL branch so cross-subject themes and pre-keying
  legacy notes stay visible.

### Data retention and withdrawal

Retention is the deployer's responsibility. The audit log, biosensor
cache, and vault are persistent local stores with no automated rotation
— [ADR 0001](docs/adr/0001-audit-log-as-backbone.md) names "long-term
archival is the deployer's responsibility" as a known consequence.

**Consent revocation triggers cache purge** per
[ADR 0013](docs/adr/0013-cache-only-purge-on-consent-revocation.md):
every `revoke_consent_*` call runs a synchronous purge on the affected
child *before* the revocation lands, with the result logged in a paired
`PURGE_CACHE` audit row carrying `rows_purged`, `tables_touched`, and
`preserved`. The vault is durable by design — analyst notes are not
biometric data and are not purged on revocation. ADR 0013 documents
the limits.

**Scope limit:** This is research infrastructure, not a clinical
decision-support system. It has not been validated against any regulatory
framework for patient-facing tools. Analytical output requires human
validation before informing decisions. See
[research-framing.md](docs/design/research-framing.md#scope-limit) for the
full statement.

---

## Install & run

### Prerequisites

- Python 3.10+
- An MCP-speaking LLM client (Claude Desktop is the reference).

### Install

```bash
git clone https://github.com/saahasmuthineni/Biosensor-to-LLM-Connector.git
cd Biosensor-to-LLM-Connector
pip install -e ".[dev]"
```

### Verify

```bash
biosensor-mcp --help
pytest -v
python tests/security_probe.py
```

### Connecting an MCP client

Add to your Claude Desktop config (`claude_desktop_config.json`):

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

Replace `~/.biosensor-mcp/venv/bin/python` with the path to your Python
interpreter.

### Commands

| Command | Description |
|---|---|
| `biosensor-mcp pilot` | Multi-subject CSV pilot wizard (v6.2.1) — three prompts, end-to-end smoke check |
| `biosensor-mcp tour` | Live-audience walkthrough — scaffolds bundled HIP Lab fixtures + registers with Claude Desktop (ADR 0024) |
| `biosensor-mcp serve` | Start the MCP server (invoked by the LLM client) |
| `biosensor-mcp demo` | Researcher first-look — runs cohort tools on bundled HIP Lab fixtures (ADR 0027) |
| `biosensor-mcp setup` | Strava OAuth wizard (for the worked example) |
| `biosensor-mcp status` | Diagnostic check: tokens, DB state, vault config |
| `biosensor-mcp uninstall` | Clean removal |

### Worked example: the running child

The running child wraps Strava as one example of the ChildMCP pattern — see CLAUDE.md for the framing. To exercise it against live data (separate from `demo`, which now showcases the canonical CSV cohort path):

To run against live Strava data:

1. Create a Strava API app at
   [strava.com/settings/api](https://www.strava.com/settings/api)
   (set callback to `localhost`).
2. Run `biosensor-mcp setup` to complete OAuth.
3. Restart your MCP client and query — *"summarize my last run"*,
   *"how has my HR drift changed?"* — to see the full pipeline in action.

### Running child tools

Twelve tools across three tiers:

| Tool | Tier | Description |
|---|---|---|
| `strava_sync` | 1 | Pull recent activities into local cache |
| `strava_list_runs` | 1 | List recent runs with summary stats |
| `strava_activity_detail` | 1 | Single-activity overview |
| `strava_hr_analysis` | 1 | Zone distribution, drift, anomalies |
| `strava_pace_analysis` | 1 | Mile splits, run/walk classification |
| `strava_stop_analysis` | 1 | Pause detection with GPS + saved labels |
| `strava_label_stop` | 1 | Persist stop label to SQLite |
| `strava_run_report` | 1 | Comprehensive: decoupling, EF, drift, phases, GAP |
| `strava_trend_report` | 1 | Rolling weekly volume, avg pace, avg HR |
| `strava_compare_runs` | 1 | Side-by-side comparison of 2–5 runs |
| `strava_downsampled_streams` | 2 | HR, pace, GPS at 5–30 s intervals |
| `strava_full_streams` | 3 | Per-second data with precision reduction |

---

## What's next

The framework is deliberately a worked example plus an extension seam,
not a finished product. The top items on the roadmap — each with a
reason it matters, not just a title:

| Next up | Why it matters |
|---|---|
| [**New ChildMCPs**](ROADMAP.md#new-childmcps-for-research-relevant-data-sources) (CGM, sleep, ECG, EDF, FHIR) | A generic CSV-directory child has shipped; the next domain-specific children unlock broader adoption. The `children/template/` skeleton cuts onboarding to filling a small set of named blanks. |
| [**Real PHI-scrubbing implementations**](ROADMAP.md#real-phi-scrubbing-implementations-behind-the-phiscrubber-slot) | The seam is wired and instrumented; a real policy per child is what any deployment touching actual PHI needs. |
| [**Deterministic mode + provenance hashing**](ROADMAP.md#deterministic-mode-with-seed-control) | Lets a reviewer re-run an analysis and trace every published number to exact code + exact input bytes. |
| [**"Freeze vault" for manuscript submission**](ROADMAP.md#freeze-vault-operation-for-manuscript-submission) | One-command archive of vault + audit + code version for attaching to a submission. |
| [**LLM-client evaluation harness**](ROADMAP.md#evaluation-harness-for-llm-client-behavior) | Makes "client-agnostic governance" a measurable claim rather than a design assertion. |

Full list with effort/impact triage and design notes: [**ROADMAP.md**](ROADMAP.md).

If any of these is the reason you showed up, open a GitHub discussion
or issue before writing code — several have real design questions
(especially `subject_id` → vault keying) worth talking through.

---

## Architecture

<p align="center">
  <img src="docs/assets/footprint.svg" alt="Biosensor MCP system footprint — router, child, vault layer" width="760">
</p>

```mermaid
flowchart LR
    Client([LLM client]) --> Router[RouterMCP<br/>validate · gate · scrub · audit]
    Router --> Children[ChildMCPs<br/>one per data source]
    Router --> Vault[VaultLayer]
    Children -.ephemeral cache.-> SQLite[(SQLite<br/>activities.db)]
    Vault --> Obsidian[(Obsidian vault<br/>markdown + SQLite index)]
```

- The **Router** enforces validation, circuit breaking, the
  analyst-side consent gate, cost, the PHI-scrubber seam (no-op by
  default; see [ADR 0003](docs/adr/0003-phi-scrubber-seam.md)),
  audit, and token accounting — identically for every child.
- A **ChildMCP** owns one data source and exposes tools at declared
  access tiers. The running child is one such implementation.
- The **Vault Layer** handles cross-session analytical memory. Vault
  tools skip consent and cost gates (analyst notes, not biometric data)
  but still run through validation and audit.

Detailed notes in [CLAUDE.md](CLAUDE.md).

---

## Troubleshooting

| Issue | Fix |
|---|---|
| OAuth "address already in use" on port 8189 | Another process is bound to that port. Kill it or wait for it to release. |
| `rate_limit.json` corruption warning | Delete the file — it will be rebuilt on next API call. |
| `subject_id` not appearing in audit rows | Pass `subject_id` as a parameter in the tool call, not as a header. |
| Vault disabled silently | Check `~/.biosensor-mcp/logs/` for a `user_config.json` parse warning. |

---

## Further reading

| Document | Audience |
|---|---|
| [docs/design/research-framing.md](docs/design/research-framing.md) | Health-research reviewers evaluating this for a study |
| [ROADMAP.md](ROADMAP.md) | Anyone — what's deferred and why, with effort/impact triage |
| [CLAUDE.md](CLAUDE.md) | Contributors and operators |
| [docs/adr/](docs/adr/) | Architectural decisions and their rationale |
| [docs/design/design-context.pdf](docs/design/design-context.pdf) | Historical design rationale |

## License

Apache-2.0.

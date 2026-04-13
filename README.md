# Biosensor MCP — LLM-Assisted Analysis for Health Research

[![CI](https://github.com/saahasmuthineni/biosensor-to-llm-middleware/actions/workflows/ci.yml/badge.svg)](https://github.com/saahasmuthineni/biosensor-to-llm-middleware/actions/workflows/ci.yml)
[![Python 3.10 | 3.11 | 3.12](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

Local-first infrastructure for LLM-assisted analysis of high-frequency
biometric data — built for health research workflows where data
governance, audit trails, and reproducibility matter.

> Looking for the running-data worked example?
> Jump to [Worked example: the running child](#worked-example-the-running-child).

---

## Why this exists

Research groups working with high-frequency biometric data (CGM, ECG,
sleep staging, wearable streams, activity traces) keep running into the
same three problems when they try to use LLMs as analytical assistants:

1. **Data governance.** Hosted LLMs are the wrong home for participant
   biometric data. Pasting streams into a web chat is usually against
   institutional policy, sometimes against law, and in all cases leaves
   no defensible trace of what was accessed.

2. **Reproducibility.** An LLM-assisted analysis that lives in a chat
   window is not reproducible six months later — not by the same
   analyst, let alone by a reviewer. There is no log of which tool saw
   which data at which point, no record of the decision about whether
   to load a full stream or a summary, no hook for a replication
   package.

3. **Longitudinal analytical memory.** Research questions evolve across
   months and across team members. The observation an analyst made
   about a participant in April is exactly the context the analyst in
   September needs. Current tooling drops it on the floor at the end of
   each session.

Biosensor MCP is one answer to those three problems: a local MCP
server that sits between any MCP-speaking LLM client (Claude Desktop,
Claude API, VS Code extensions) and the data sources you have on disk,
and owns the cross-cutting concerns — gating, scrubbing, audit,
provenance, durable memory — that each of the three problems needs.

---

## What you get

- **A local-first router** that runs next to the data. Raw streams
  never leave the machine. Only server-computed summaries do, and only
  when a tier and consent gate say they should.
- **Tiered access to sensitive data.** Every tool declares an access
  tier: Tier 1 returns computed summaries, Tier 2 returns downsampled
  views behind a per-domain consent gate, Tier 3 returns raw
  per-timestamp streams behind both consent and a pre-execution cost
  gate. This is data minimization, implemented.
- **A durable audit log** of every tool call: timestamp, tool, tier,
  parameters, outcome, latency, and an optional study `subject_id`.
  Backed by SQLite so you can attach it to an appendix.
- **Provenance stamps on every result** — package version, tool name,
  and a UTC timestamp — so an analyst can trace any output back to the
  code version and moment that produced it.
- **An Obsidian-backed analytical vault** for cross-session memory:
  themes (persistent research questions), moments (observations), and
  evidence logs that accumulate over the life of a study. Markdown
  files are the source of truth; a SQLite index makes them queryable.
- **An extensible child pattern.** Each data source is a ChildMCP. New
  children for CSV directories, EDF files, FHIR bundles, REDCap
  exports, or vendor APIs implement a small interface and inherit the
  full governance pipeline.

---

## How it maps to research workflows

### Data minimization — the tier model

Modern IRB protocols increasingly ask analysts to justify, not just
what data they look at, but at what resolution. The three-tier model
answers that question structurally. Most analytical questions ("is
this participant's HR drift worsening?") are answerable at Tier 1 from
server-side summaries, and Tier 1 never releases raw sensor data.
Tier 2 (downsampled, consent-gated) covers visualization. Tier 3 (raw,
consent + cost gated) covers the rare case that actually needs a
per-timestamp stream. The gate structure is the protocol text made
executable.

### Audit trails — the audit log

Every tool call lands in a SQLite row with enough context to
reconstruct what happened: what tool, who it was scoped to (via
`subject_id`), which parameters, what outcome, how long it took,
whether a gate fired. That row is intended to survive the analysis —
to be attached to protocol amendments, replication packages, or
reproducibility appendices. Nothing in the LLM client can bypass it;
the router writes the row regardless of what the analyst asked for.

### Analytical provenance — the `_meta` block

Every successful tool result carries a `_meta` block with the package
version, the tool name, and a UTC timestamp. If a number ends up in a
paper, the code version that produced it is recoverable from the
metadata that travelled alongside it. Full content-hashed provenance
(raw-data hash → intermediate hash → metric) is the roadmap version
of this; the `_meta` stamp is the minimum version the research shift
ships today.

### Team continuity — themes and moments

The vault layer exposes two objects that exist exactly for research
team continuity:

- **Themes** are persistent research questions or hypotheses — "is
  cooldown HR elevated in participants on medication X?" — with an
  appending evidence log. Evidence blocks are never rewritten.
- **Moments** are observations worth remembering, each timestamped,
  each linkable to specific participants, themes, or runs.

A new analyst joining the project can read the open themes and the
recent moments as their first session step and resume prior reasoning
without having to dig through notebooks.

---

## Status

- One worked-example child ships today: a Strava running child that
  exercises all three access tiers, OAuth, cached streams, and the
  vault writer. Treat it as a template to copy from, not a dependency
  to import.
- CGM, sleep-staging, ECG, EDF-file, CSV-directory, and FHIR-bundle
  children are the next steps. See [docs/roadmap.md](docs/roadmap.md).
- The PHI-scrubbing seam exists as of this release and ships as a
  no-op. Institutions swap in a subclass once their policy is defined;
  nothing in the framework pretends to know what PHI means in a given
  study.
- Per-subject scoping on the audit log is first-class; per-subject
  scoping as an explicit parameter on every child tool is roadmap.
- See [docs/research-framing.md](docs/research-framing.md) for the
  longer document aimed at health-research reviewers.

---

## Install

### Prerequisites

- Python 3.10+
- An MCP-speaking LLM client (Claude Desktop is the reference client
  these docs are written against).

### Install in dev mode

```bash
git clone https://github.com/saahasmuthineni/biosensor-to-llm-middleware.git
cd biosensor-to-llm-middleware
pip install -e ".[dev]"
```

### Verify the install

```bash
biosensor-mcp --help
pytest -v
python tests/security_probe.py
```

The `security_probe.py` script exercises the router pipeline end to
end, including gate enforcement, audit writes, and the
research-framing additions (subject_id scoping, provenance stamps,
PHI-scrubbing seam). It runs without pytest so it can be invoked from
any CI or review harness.

---

## Worked example: the running child

The running child is a concrete implementation of the ChildMCP pattern
against Strava running data. It is retained in this repository as a
teaching artifact: an end-to-end example of how to wrap a streaming
biometric source, declare its access tiers, implement pre-execution
cost estimation, and hand computed reports to the vault layer.

### Try the worked example — no Strava account required

```bash
pip install -e .
biosensor-mcp demo
```

`biosensor-mcp demo` runs the running child's server-side analytics
(splits, zones, drift, efficiency factor, decoupling, anomaly
detection) against synthetic 60-minute run data. No OAuth, no API
keys, no network calls. It exercises the same code path that a real
analyst would hit — just with a reproducible synthetic participant.

### Run it against live Strava data (optional)

If you actually want to drive the running child from your own Strava
account:

1. Create a Strava API application at
   [strava.com/settings/api](https://www.strava.com/settings/api) and
   set the callback domain to `localhost`.
2. Run the OAuth setup wizard:
   ```bash
   biosensor-mcp setup
   ```
3. Register the server with your MCP client (Claude Desktop config):
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
4. Restart the client and query it — "summarize my last run", "how
   has my HR drift changed over the past month" — to watch the tier /
   consent / cost / audit pipeline work.

### What the running child exposes

Twelve tools across three tiers. Tier 1 tools return computed reports
(run reports, trend reports, comparisons); Tier 2 returns downsampled
streams behind biometric consent; Tier 3 returns per-second streams
behind consent + cost approval. See the full table in
[CLAUDE.md § Running Child — 12 Tools](CLAUDE.md#running-child--12-tools).

---

## Commands

```
biosensor-mcp serve       Start the MCP server (invoked by the LLM client)
biosensor-mcp demo        Run analytics on synthetic run data (no network)
biosensor-mcp setup       Run the Strava OAuth wizard (for the worked example)
biosensor-mcp status      Diagnostic check: tokens, DB state, vault config
biosensor-mcp uninstall   Clean removal
```

---

## Architecture, briefly

```
LLM client  ──▶  Router MCP  ──▶  Child MCPs
                     │                 │
                     │           (one per data source)
                     ▼
                 Vault Layer  ──▶  Obsidian vault (markdown + SQLite index)
```

- The **Router** enforces validation, circuit breaking, consent,
  cost, PHI scrubbing, audit, and token accounting — identically for
  every child.
- A **ChildMCP** owns exactly one data source and exposes tools at
  declared access tiers. The running child is one such implementation.
- The **Vault Layer** is framework-level infrastructure for
  cross-session analytical memory: themes, moments, evidence logs.
  Vault tools skip the consent and cost gates (they deal with the
  analyst's notes, not raw biometric data) but still run through param
  validation and audit.

Detailed architectural notes live in [CLAUDE.md](CLAUDE.md).

---

## Further reading

- [docs/research-framing.md](docs/research-framing.md) — the
  longer-form document aimed at health-research reviewers and
  research-software engineers evaluating this for a study.
- [docs/roadmap.md](docs/roadmap.md) — what's explicitly deferred and
  why, including real PHI-scrubbing implementations, new children,
  deterministic replay, full provenance hashing, and multi-analyst
  attribution on vault notes.
- [CLAUDE.md](CLAUDE.md) — operator / contributor reference.
- [docs/design-context.pdf](docs/design-context.pdf) — the original
  design rationale document.

## License

Apache-2.0.

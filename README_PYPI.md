# tailor-mcp

**Local data preprocessing for AI — structured summaries, governed access, auditable answers.**

Pasting raw data into an LLM is expensive, often produces worse answers (the model spends capacity extracting numbers from text instead of reasoning), and at scale is simply impossible. A 16-subject force-plate cohort comparison is **769,311 tokens** of CSV — that **exceeds Claude's 200K context window**. You cannot ask the question at all without chunking, streaming, or some other orchestration workaround.

Tailor computes the answer on your machine and returns **820 tokens**. The result is identical; the question becomes answerable in a single call. Your data never leaves your machine, and every action is recorded in a local SQLite audit log.

Tailor is a local MCP server that sits between an LLM client (Claude Desktop, Cline, Cursor, or a local model via Ollama) and any structured source: directories of per-subject CSVs, MATLAB binary exports, REDCap exports, running data, or anything you register through a small extension point.

## The numbers

Measured, reproducible benchmark — force-plate cohort fixtures, `tiktoken cl100k_base`:

| Scenario | Raw → LLM | Through Tailor | Reduction |
|---|---:|---:|---:|
| Single analytical question, 1 subject | 48,006 tokens | 73 tokens | **657×** |
| 16-subject cohort comparison | 769,311 tokens *(exceeds the 200K window)* | 820 tokens | **938×** |
| Resuming a 5-session analytical thread | 771,743 tokens | 2,427 tokens | **318×** |

Results are identical to processing the raw stream — the computation happens server-side. Over a 5-session analytical thread at Claude Sonnet 4.6 input pricing, that difference is roughly **$11.58 vs $0.04**.

Full methodology, assumptions, and a prompt-caching counter-factual:
<https://github.com/saahasmuthineni/tailor-mcp/blob/main/benchmarks/token_efficiency.md>

## Install

**Prerequisites:**

1. [Claude Desktop](https://claude.ai/download) (Windows: Microsoft Store; macOS: claude.ai/download)
2. [uv](https://docs.astral.sh/uv/getting-started/installation/) — the installer Tailor uses:

   ```
   # Windows (PowerShell)
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

   # macOS / Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

**Install and run:**

```
uv tool install tailor-mcp
tailor pilot
```

`tailor pilot` runs a short setup wizard, registers Tailor with Claude Desktop, and configures your first data source (CSV / MATLAB / REDCap). Fully quit and reopen Claude Desktop (system-tray Exit on Windows; Cmd+Q on macOS), then ask a question about your data — Claude calls a tool, the computation runs locally, and you get back per-group statistics. Nothing leaves your machine.

The bundled demo fixtures (`S001`–`S016`) are synthetic by construction — random-walk traces sized to mimic real cohort shapes, not real participant data.

## How it works

```
LLM client <--> RouterMCP (validate -> circuit break -> consent -> cost
                           -> execute -> scrub -> audit + provenance)
                   |                  \            \
              ChildMCP                 VaultLayer    LocalLLMLayer
   (one per data source:               (cross-session  (optional local-LLM
    CSV dir, MATLAB, REDCap,           analytical       guardian; opt-in)
    running data, your own)            memory)
```

Every tool call passes through a server-side pipeline the LLM cannot bypass: parameter validation, a circuit breaker, a per-domain consent gate, a token cost gate, a PHI/sensitive-data scrubber seam (no-op by default; subclass per child for institutional policy), and an audit log. Every successful result carries a `_meta` provenance stamp — package version, UTC timestamp, domain, tier, scrubber id, token counts — minimum-viable provenance for results that may end up in a report or paper.

## Three-tier access model

Data minimization is enforced server-side, not in the prompt. The LLM cannot escalate to higher-resolution data without explicit user approval.

| Tier | What the LLM sees | Typical tokens | Gate |
|------|-------------------|---------------|------|
| **1 — Free** | Server-computed reports: summaries, stats, trends, anomalies | 200 – 1,500 | None |
| **2 — Consent** | Downsampled streams at 5–30 s resolution | 3,000 – 7,000 | Domain consent |
| **3 — Cost** | Full per-timestamp streams with precision reduction | 25,000 – 60,000 | Consent + cost approval |

Most analytical questions resolve at Tier 1 — zero raw data leaves the machine, and the freed context goes to reasoning rather than data shuffling.

## Data sources shipped today

- **csv_dir** — a local directory of per-subject CSV files; cohort summary + a force-decline fatigue diagnostic
- **matlab_file** — MATLAB `.mat` binary exports (v5/v6/v7.2; requires the `[matlab]` extra)
- **redcap** — REDCap CSV/JSON exports with built-in PHI scrubbing driven by the `project_metadata.csv` data dictionary
- **running** — a Strava API wrapper, shipped as a worked example of the extension pattern, not as the headline use case
- **template** — a runnable starting point: copy, rename, wrap your own source

Adding a source means copying `children/template/` and implementing five things (`domain` / `display_name`, `consent_info`, `tool_definitions` with tiers, `execute()`, `estimate_cost()`); your source inherits the full governance pipeline. `children/csv_dir/` is a complete second worked example.

## Who it's for

**Good fit:** researchers and RSEs building LLM-assisted analysis where data governance, audit trails, or reproducibility matter; teams wiring structured sources into Claude Desktop or any MCP client and wanting server-side computation over raw-data prompts; anyone who needs a local-first setup.

**Not a good fit:** clinical decision-support or regulatory-compliance deployments (this is research infrastructure, not a validated clinical tool); hosted/cloud workflows (the architecture is deliberately local-first); projects requiring an independent security audit (solo-maintainer project, no external review yet).

## Status

Validated on **Windows 11** (Microsoft Store Claude Desktop) and **macOS**. Cross-client round-trip confirmed with Cline; any MCP-compliant client works without bespoke accommodation. CI matrix: Ubuntu · Windows · macOS × Python 3.10–3.12. Community validation is ongoing — issues and reports welcome.

## Project

- **Source code:** <https://github.com/saahasmuthineni/tailor-mcp>
- **Benchmark methodology:** <https://github.com/saahasmuthineni/tailor-mcp/blob/main/benchmarks/token_efficiency.md>
- **Architecture Decision Records:** <https://github.com/saahasmuthineni/tailor-mcp/tree/main/docs/adr>
- **Issues:** <https://github.com/saahasmuthineni/tailor-mcp/issues>

## License

AGPL-3.0-or-later (v9.0.0 onward; releases through v8.0.0 remain Apache-2.0 for prior recipients). For local-first use — the framework's primary deployment shape — the AGPL network-trigger clause rarely fires, so it adds minimal friction for individual researchers and institutional installs. It exists as a structural lever against extractive cloud reuse: a hosted "Tailor as a service" fork must publish its modifications.

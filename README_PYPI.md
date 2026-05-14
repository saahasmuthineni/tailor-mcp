# Tailor — your AI works with your data, on your machine

**Tailor is a personal AI server with research-grade trust.** A local-first framework that lets any MCP-speaking AI (Claude Desktop, Cline, Cursor, or a local model via Ollama) work with your own data — without that data leaving your machine. Every action your AI takes gets recorded in a durable audit log; every result is stamped for reproducibility.

**It also turns a $200/month AI bill into a $2/month one — and makes the AI materially better at your question.** Most analytical questions resolve to a server-computed summary instead of a raw-stream dump (*return the answer, not the data*). Daily workflows that would burn hundreds of dollars a month against a hosted LLM run for single digits through Tailor, because the AI's context window goes to reasoning over your question and your prior work instead of shuffling streams it would have to re-aggregate itself.

**The same architecture works on whatever shape your data is already in.** A directory of per-subject CSVs is the canonical first child today; REDCap exports, EDF sleep recordings, vendor sensor exports, and FHIR bundles fit the same `ChildMCP` extension point — a runnable template child is the starting point, and your data source inherits the full governance pipeline (tier model, audit, scrubber seam, Wardrobe). What works for CSV works for anything you wrap, and the same 10-100× cost-per-question collapse applies regardless of shape.

Today the worked-out recipe is health research — *the first recipe shipped end-to-end, not the platform's identity*. Future recipes (knowledge work, quantified self, household, creative archives) compose on the same engine.

Your **Wardrobe** is what Tailor governs on your behalf: the structured collection of your data and prior analytical work that lives entirely on your machine. *Not clothes — your stuff.* Your Wardrobe accumulates themes (questions you keep returning to), moments (observations worth remembering), evidence (data that grounds your themes), audit history (every action your AI took on your behalf), and the source data itself. Tailor curates your Wardrobe — adds to it, retrieves from it, governs how the AI reaches into it — and never sends any of it to a service you didn't choose.

## Install

```
uv tool install tailor-mcp
```

Bootstrap your first project with `tailor pilot` (multi-subject CSV setup wizard) or `tailor fitting-room` (a guided walkthrough on bundled synthetic fixtures from the HIP Lab realistic demo). No data leaves your machine at any point. The bundled HIP Lab CSV fixtures (`S001`–`S016`) shipped inside the wheel are synthetic by construction — random-walk traces sized to mimic real cohort shapes, not real participant data.

## Architecture

```
LLM client <--> RouterMCP (validate -> circuit break -> consent -> cost
                           -> execute -> PHI scrub -> audit + provenance)
                   |                  \           \
              ChildMCP                  VaultLayer  LocalLLMLayer
   (one per data source                 (reorientation  (local-LLM
    e.g. CSV directory,                  tier;           guardian; opt-in
    Strava API, FHIR bundle)             Obsidian        via user_config)
                                         vault + index)
```

Children ship in the framework today:

- **csv_dir** — wrap a local directory of per-subject CSV files; 7 tools (file detail, summary report, cohort summary, force decline, downsampled stream, raw stream, file list)
- **running** — Strava API wrapper as a worked example; 12 tools across pace, heart rate, GPS, run reports, trend reports
- **template** — runnable starting point for new data sources; copy + rename to wrap your own data

## Three-tier access model

Tailor enforces data minimization server-side, not in the AI's prompt:

| Tier | What the AI sees | Gate |
|---|---|---|
| 1 — Free | Server-computed reports (splits, cohort summaries, decline metrics) | None |
| 2 — Consent | Downsampled streams (5–30s intervals) | Per-domain biometric consent |
| 3 — Cost | Per-timestamp streams | Consent + cost approval |

Most analytical questions resolve at Tier 1 — zero raw biometric data leaves the machine, and the AI's context goes to reasoning rather than to data shuffling.

## Security pipeline

Every tool call passes through six layers, cheapest first:

1. **Parameter validation** — type/range/pattern, reject before any work
2. **Circuit breaker** — block domain after 3 consecutive failures
3. **Consent gate** — per-domain biometric consent, revocable
4. **Cost gate** — pre-estimate tokens before execution
5. **PHI scrubber** — institutional PHI-stripping seam (no-op default; subclass per child)
6. **Audit log + token ledger** — every call logged to SQLite

Every successful result also carries a `_meta` block stamped with package version, tool name, UTC timestamp, domain, tier, scrubber identifier, and token counts — minimum-viable provenance for results that may end up in a paper.

## Problems Tailor is built against

1. **Data governance.** Hosted LLMs are the wrong home for sensitive participant data. The tier model and local-first processing are the structural response.
2. **Reproducibility.** LLM-assisted analyses in chat windows leave no durable trace. The audit log and `_meta` provenance stamps make every result traceable.
3. **Longitudinal analytical memory.** Observations made in one session disappear when the chat ends. The Wardrobe (themes, moments, evidence, append-only) is the response.
4. **AI economics.** Tier-1 server-side computation — *return the answer, not the data* — is simultaneously a cost lever (token-per-question collapses by 1–2 orders of magnitude on most analytical questions) and a cognition lever (freed context goes to reasoning over the analyst's prior work, not to data shuffling). The same architectural choice that satisfies the data-governance problem also makes the AI materially better at the question and reduces cost-per-question by 10–100×.

## Where to read more

The project landing page at <https://saahasmuthineni.github.io/tailor-mcp-landing/> describes the project's stage and audience. The source repository is currently in invited evaluation; full design documentation (35 numbered ADRs, design notes, roadmap) is private until Tailor completes its first beachhead deployment with a research lab.

---

Built by Saahas Muthineni. If you received this URL personally and have questions, reply through whatever channel he sent it through.

# Tailor MCP — Launch Content

*Four pieces for v9.0.0 release. Each platform gets different text. Do not cross-post.*

---

## 1. Show HN Post

**Title:**

> Show HN: Local MCP layer that reduces 769K tokens to 820 — 16-subject cohort exceeds context window without it

---

**Body:**

The problem that motivated this: at 100 Hz, a 16-subject force-plate cohort generates 769,311 tokens of raw CSV data. Claude's context window is 200K tokens. The analytical question — "are men or women losing strength faster?" — cannot be answered in a single call without a different architecture. This isn't a cost problem; it's a structural impossibility.

The architectural decision: run the computation server-side, pass the LLM a structured summary instead of the raw streams. A 16-subject cohort comparison stratified by sex returns a 820-token JSON payload. Same answer. The computation ran deterministically on your machine; nothing left it.

**Benchmark** (reproducible, no credentials, no external download):

```bash
git clone https://github.com/saahasmuthineni/tailor-mcp.git
cd tailor-mcp
pip install tiktoken
python benchmarks/token_efficiency.py
```

| Scenario | Raw to LLM | Through Tailor | Ratio |
|---|---:|---:|---:|
| Single subject, 60s @ 100 Hz | 48,006 tokens | 73 tokens | 657× |
| 16-subject cohort, sex-stratified | 769,311 tokens | 820 tokens | 938× |
| 5-session thread resume | 771,743 tokens | 2,427 tokens | 318× |

Numbers from `tiktoken cl100k_base`. The cross-check with a `chars / 4` heuristic gives 435× and 615× respectively — both above the 100× floor. The script prints a JSON document with every number in the benchmark report; output is bit-identical across machines because the processing functions are pure-static with no PRNG.

**On prompt caching:** the first objection is usually "what about Anthropic's prompt caching?" I worked through this in the benchmark document. Under best-case caching assumptions — same analyst session, calls within the 5-minute TTL, byte-identical payload every time — Tailor is still ~106× cheaper. For multi-day research threads (where the analyst opens Claude Desktop on Tuesday to continue Monday's analysis), the TTL means caching provides nothing; every session is a cold cache write. The benchmark document has the arithmetic.

**What it is:** a local MCP server. `uv tool install tailor-mcp && tailor pilot` runs a three-prompt setup wizard and registers it with Claude Desktop (or any MCP-compliant client — I've confirmed Cline 3.85.0 round-trips correctly with matching audit rows). Point it at a CSV directory, ask a question. Nothing goes to the cloud.

**What it isn't:** not a clinical tool, not cloud-backed, no external security audit, solo maintainer. The README says this directly. The license is AGPL-3.0 (v9.0.0+).

**The extension point:** `ChildMCP` is an abstract base class — implement five methods to register a new data source. Shipped children: generic CSV directories, force-plate CSVs, EMG CSVs, REDCap export directories, MATLAB `.mat` files (v5/v6/v7.2), Strava running data (the copyable template). There's also a `VaultLayer` that writes analytical notes to Obsidian-compatible markdown and retrieves them across sessions — that's the source of the 318× session-persistence number.

The worked example is health-research biomechanics. The framework is data-agnostic; the architecture applies to any structured data that decomposes into per-subject scalars.

https://github.com/saahasmuthineni/tailor-mcp

---

## 2. r/LocalLLaMA Post

**Title:**

> Why I stopped pasting raw data into Claude and built a local preprocessing layer instead (938× token reduction, reproducible benchmark)

---

**Body:**

If you've done any serious local-AI work with structured data, you've probably hit this: the data that actually answers the question is too big to fit in the context window, so you start chunking, summarizing, or just hoping the model doesn't lose the thread halfway through a 50K-token paste.

I hit a concrete version of this. I was working with 100 Hz force-plate data — 16 subjects, 60 seconds each. Pasting the raw CSVs to answer a basic cohort question ("who fatigues faster, men or women?") comes out to **769,311 tokens**. Claude's context window is 200K. The question literally can't be answered without either chunking the data or changing the architecture.

I changed the architecture: run the computation locally, pass the LLM a structured summary. The same cohort question costs **820 tokens**. Same answer.

**938× reduction. And that's not the most interesting number.**

The more interesting number is the session-persistence case. Every time you close Claude Desktop and reopen it, you're starting from zero — the model has no memory of what you found last session. Without persistent structured memory, you're re-pasting the data and reconstructing context every time. Over 5 research sessions on the same cohort, that compounds to ~$11.58 just in input costs. With the local vault layer, it's ~$0.04 — the model retrieves structured notes from the prior sessions and calls Tier-1 tools only for fresh data.

**Benchmark is reproducible:**

```bash
git clone https://github.com/saahasmuthineni/tailor-mcp.git
cd tailor-mcp
pip install tiktoken
python benchmarks/token_efficiency.py
```

No credentials, no external download. The dataset (synthetic, shaped like real 100 Hz force traces) is bundled. Output is bit-identical across machines.

**How it works:**

- Local MCP server (`tailor serve`) runs in the background
- Data sources register as `ChildMCP` children — CSV directories, MATLAB files, REDCap exports, whatever you point it at
- Tools expose three tiers: Tier-1 returns server-side computed summaries (no consent gate, fast), Tier-2 returns downsampled streams (consent-gated), Tier-3 returns full streams (cost-gated)
- Every call logs to a local SQLite audit database with token counts, timing, outcomes, provenance stamps
- VaultLayer writes analytical notes to Obsidian-compatible markdown; they persist across sessions and get retrieved selectively on resume

**On prompt caching:** yes, I know about it, no it doesn't close the gap. The 5-minute TTL kills multi-day research threads. The benchmark document has the arithmetic worked out honestly — even under best-case caching assumptions, Tailor is ~106× cheaper. For the realistic case (research spread across multiple days), the cache never hits.

**Install:**

```bash
uv tool install tailor-mcp
tailor pilot   # three-prompt setup wizard
```

Works with Claude Desktop and any other MCP-compliant client (confirmed Cline 3.85.0). Extension point is a `ChildMCP` ABC — implement five methods to wrap a new data source.

This is AGPL-3.0, solo maintainer, no external security audit. Not for clinical deployments. The README is honest about all of this.

https://github.com/saahasmuthineni/tailor-mcp | benchmark methodology: https://github.com/saahasmuthineni/tailor-mcp/blob/main/benchmarks/token_efficiency.md

---

## 3. r/ClaudeAI Post

**Title:**

> Built a local MCP server that preprocesses structured data before Claude sees it — 938× token reduction, reproducible benchmark, three-prompt setup

---

**Body:**

If you use Claude Desktop with MCP for anything data-intensive, you've probably run into the context-window problem. Paste a CSV, lose a third of your available context. Paste a cohort of CSVs, blow past the limit entirely.

I built a local MCP server called Tailor that sits between Claude Desktop and your data. Instead of passing raw files to Claude, it runs computation server-side and returns structured summaries. The LLM gets the answer, not the data.

**The concrete numbers:** a 16-subject force-plate cohort at 100 Hz generates 769,311 tokens of raw CSV. Claude's context window is 200K. Through Tailor's Tier-1 surface, the same question costs 820 tokens. 938× reduction. And the 16-subject case isn't just "cheaper" — it literally doesn't fit in the context window without a different architecture.

**Setup:**

```bash
# Install uv first (one-liner at astral.sh/uv)
uv tool install tailor-mcp
tailor pilot
```

`tailor pilot` is a three-prompt wizard that configures your data source and registers Tailor with Claude Desktop automatically. Fully quit and reopen Claude Desktop afterward, then ask a question. The tool calls happen in the background; from Claude's perspective it's just getting back a structured JSON result.

**What you get in Claude Desktop:**

- Tier-1 tools for computed reports — cohort summaries, per-subject statistics, trend analysis, fatigue diagnostics. Fast, no approval prompt, no data leaving your machine.
- Tier-2 tools for downsampled streams — gated behind a consent prompt that Claude surfaces to you before proceeding.
- Tier-3 tools for full raw streams — gated behind consent + a cost estimate. You see the token cost before anything runs.
- VaultLayer — analytical notes written to Obsidian-compatible markdown. Cross-session memory. Next time you open Claude Desktop and ask about the same dataset, it retrieves prior session notes instead of starting from scratch.

**The vault number:** resuming a 5-session analytical thread costs 771,743 tokens if you re-paste data and notes every time. Via vault retrieval, it's 2,427 tokens. 318×.

**Reproducible benchmark:**

```bash
git clone https://github.com/saahasmuthineni/tailor-mcp.git
cd tailor-mcp
pip install tiktoken
python benchmarks/token_efficiency.py
```

No credentials, no external data. Output is bit-identical across machines.

**Cross-client:** not Claude-Desktop-only. Confirmed round-trip on Cline 3.85.0 with full `_meta` provenance blocks and matching audit rows.

**Limitations to be clear about:** this is a local-first framework for research and analysis, not a clinical tool. Solo maintainer, no external security audit. AGPL-3.0 license (v9.0.0+). The README is direct about what it's not.

The extension point is a `ChildMCP` abstract base class — implement five methods to point it at any structured data source (CSVs, REDCap exports, MATLAB files, whatever you work with).

https://github.com/saahasmuthineni/tailor-mcp

---

## 4. awesome-mcp-servers Submission

**PR title:**

> Add tailor-mcp: local preprocessing layer for structured data (938× token reduction)

---

**One-liner for the list:**

> Local preprocessing MCP server — runs computation server-side on structured data (CSV, MATLAB, REDCap) and returns summaries instead of raw streams; 938× token reduction on cohort questions; 318× on cross-session retrieval via Obsidian-compatible vault. Includes tiered consent gates, local audit log, and a ChildMCP extension point for new data sources.

---

**Shorter version if one-liners are preferred:**

> Local-first preprocessing layer — 938× token reduction by running computation server-side before the LLM sees raw data. Structured data (CSV, MATLAB, REDCap) + Obsidian-compatible cross-session vault.

---

**Category notes for the PR:**

Tailor fits under a data / analytics / research category if one exists. If the list uses broad categories like "utilities" or "data," use whichever is closest to data analysis / research data.

It does not fit under:
- Cloud connectors or API integrations (deliberately local-first)
- Database MCPs (it's a computation layer over flat files, not a query engine against a database)
- Agent frameworks (it's a server, not a framework for orchestrating agents)

If there is a "local-first" or "privacy" grouping, that is accurate and appropriate.

**Notes for the reviewer:**

- PyPI: `uv tool install tailor-mcp`
- GitHub: https://github.com/saahasmuthineni/tailor-mcp
- License: AGPL-3.0 (v9.0.0+)
- Confirmed cross-client: Claude Desktop (Windows + macOS) and Cline 3.85.0
- The benchmark is in `/benchmarks/token_efficiency.py` — reproducible offline with no credentials

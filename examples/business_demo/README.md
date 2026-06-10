# Business demo — retail operations (non-health worked example)

A worked example on **business data**: twelve retail stores, one CSV
per store, 90 days of daily revenue / transactions / basket size, and
a `metadata.json` sidecar declaring each store's region and format.
The generic `csv_dir` child answers cross-store questions
server-side — **no sales rows ever enter the LLM context**, and every
question Claude asks of the data lands in the local audit log.

This example exists because the framework's other demos are
health-research-shaped. The engine is data-agnostic; this is the
shortest proof. Same child, same router pipeline, same audit log —
different spreadsheet.

---

## TL;DR

```bash
# Fixtures are checked in. To regenerate them deterministically:
python examples/business_demo/generate.py

# Non-interactive end-to-end check (no Claude in the loop) —
# verifies every number quoted below against the real tool output:
python examples/business_demo/rehearse.py
```

Then point Tailor's `csv_dir` child at `examples/business_demo/csv/`
(setup below), restart Claude Desktop, and ask:

> *Which region's stores are doing better, and is anything unusual
> going on at any individual store?*

---

## Setup (2 minutes)

Two paths to the same config:

**Path A — chat (v8.0.0+).** Tell Claude:

> *"I have CSV data at `<absolute path to examples/business_demo/csv>`
> — set Tailor up to use it."*

Claude drives the `tailor_setup_*` MCP tools: detects the schema,
shows you what it found, and writes the source block after you
confirm. The write lands in the audit log as `SETUP_CONFIG_WRITE`.

**Path B — terminal.** Add to `~/.tailor/user_config.json`:

```json
"csv_dir": {
  "path": "/absolute/path/to/examples/business_demo/csv",
  "timestamp_column": "timestamp",
  "timestamp_format": "%Y-%m-%dT%H:%M:%S",
  "value_columns": {
    "daily_revenue": "Daily revenue (USD)",
    "transactions": "Transactions (count)",
    "avg_basket": "Average basket (USD)"
  }
}
```

Either way: fully quit Claude Desktop (system-tray Exit on Windows;
⌘Q on macOS) and reopen.

---

## Walkthrough (5 minutes)

Numbers below are wire-verified by `rehearse.py` — they come from the
actual tool output, not from this document's author. If you
regenerate fixtures after editing `generate.py`, re-run `rehearse.py`
and update the numbers here.

### 1 — The cohort question

> *"Summarize mean daily revenue across all stores, grouped by
> region. Use csv_group_summary."*

Claude calls `csv_group_summary` with `value_column="daily_revenue"`,
`group_by="region"`, `metric="mean"` and reports:

- **north (n=6): mean ≈ $11,700/day**
- **south (n=6): mean ≈ $15,444/day**

**What to notice:** 1,080 daily rows across 12 files were reduced to
two summary rows *server-side*. The raw sales data never entered the
chat. The same call against your real directory works identically.

### 2 — Slice it another way

> *"Now group peak daily revenue by store format."*

`csv_group_summary` with `group_by="format"`, `metric="max"`:

- **mall (n=6): mean of per-store peaks ≈ $25,644**
- **street (n=6): mean of per-store peaks ≈ $13,609**

**What to notice:** grouping identity lives in `metadata.json`
(region, format) — add any field there and it becomes a grouping
dimension with no code change.

### 3 — Find the anomaly

> *"Run csv_summary_report on store_N03.csv. Anything unusual?"*

The report shows **mean ≈ $13,449/day but min ≈ $1,082/day** — a
floor far below anything weekday/weekend seasonality explains
(compare healthy `store_N01.csv`: min $13,373 against mean $16,894).
Claude should flag the two-week revenue collapse mid-quarter — the
fixture encodes a store closure (water-main break, ~8% of revenue
surviving via online fulfilment).

**What to notice:** the LLM found the anomaly from a ~400-token
summary, not from reading 90 rows.

### 4 — The receipt

> *"What calls have you made against my sales data this session?"*

Or inspect directly:

```bash
sqlite3 ~/.tailor/data/audit.db \
  "SELECT tool_name, params, outcome, called_at FROM audit_log ORDER BY id DESC LIMIT 10;"
```

**What to notice:** every question Claude asked of the data is a row —
tool, parameters, outcome, latency, token estimate. This is the same
audit backbone the health-research deployments use for IRB review,
doing the same job here: *you can always reconstruct what the AI did
with your data.*

---

## If Claude drifts

| Symptom | Recovery prompt |
|---|---|
| Answers without calling a tool | *"Call the actual MCP tool — I want the numbers to come from the framework, not your prior knowledge."* |
| Wrong column name | *"Use value_column='daily_revenue' — the literal CSV header."* |
| Paraphrased/wrong number | *"Read the exact number from the tool output — don't paraphrase."* |

---

## What's here

```
examples/business_demo/
  generate.py     Seeded deterministic generator (random.Random(20260610));
                  writes csv/*.csv + csv/metadata.json in place
  rehearse.py     Non-interactive end-to-end check against the real child;
                  prints PASS/FAIL per assertion, exit 0 = demo-ready
  README.md       This file
  CUE_CARD.md     One-page version for live use
  csv/            12 store CSVs (90 daily rows each) + metadata.json sidecar
```

Fixture composition: 6 north / 6 south stores, mall and street formats
in both regions. South region trends up ~+0.35%/day over the quarter,
north drifts down ~-0.20%/day, weekends carry a 1.35× uplift, and
`store_N03` is closed days 41–54 (the anomaly). All synthetic, all
deterministic from the seed.

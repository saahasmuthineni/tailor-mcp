# Business demo — cue card

**One page. Non-health worked example: 12 retail stores, 90 days of
daily sales, generic `csv_dir` child.**

> **Before starting:** fresh Claude Desktop chat, `csv_dir` pointed at
> `examples/business_demo/csv/` (see README § Setup). Run
> `python examples/business_demo/rehearse.py` beforehand — exit 0
> means every number below matches the live tool output.

---

## Headline numbers — wire-verified by rehearse.py

| Quantity | Value |
|---|---|
| Mean daily revenue — north (n=6) | **≈ $11,700** |
| Mean daily revenue — south (n=6) | **≈ $15,444** |
| Mean of per-store peak revenue — mall / street | **≈ $25,644 / ≈ $13,609** |
| store_N03 mean / min daily revenue — *the anomaly* | **≈ $13,449 / ≈ $1,082** |
| Healthy comparator store_N01 mean / min | ≈ $16,894 / ≈ $13,373 |

The anomaly: store_N03's min is ~8% of its mean — a two-week closure
(days 41–54), not weekend seasonality. A healthy store's min stays
above 50% of its mean.

---

## Walkthrough — 4 steps, ~5 minutes

| # | Paste into Claude Desktop | Expected result + what to point out |
|---|---|---|
| **1** | *"Summarize mean daily revenue across all stores, grouped by region. Use csv_group_summary."* | north ≈ $11.7K, south ≈ $15.4K. **"1,080 daily rows reduced to two summary rows server-side. No sales data entered the LLM context."** |
| **2** | *"Now group peak daily revenue by store format."* | mall ≈ $25.6K, street ≈ $13.6K. **"Grouping identity lives in metadata.json — add a field, get a grouping dimension, no code change."** |
| **3** | *"Run csv_summary_report on store_N03.csv. Anything unusual?"* | mean ≈ $13.4K but min ≈ $1.1K. Claude flags the mid-quarter collapse. **"The anomaly was found from a ~400-token summary, not 90 raw rows."** |
| **4** | *"What calls have you made against my sales data this session?"* | Claude recounts the tool calls; every one is also a row in `audit.db`. **"You can always reconstruct what the AI did with your data — tool, params, outcome, timestamp."** |

---

## Tool-call shapes (if Claude needs steering)

- Step 1: `csv_group_summary` — `value_column="daily_revenue"`,
  `group_by="region"`, `metric="mean"`
- Step 2: `csv_group_summary` — `value_column="daily_revenue"`,
  `group_by="format"`, `metric="max"`
- Step 3: `csv_summary_report` — `file_id="store_N03.csv"`

## Recovery prompts

| Symptom | Say |
|---|---|
| Answered without a tool call | *"Call the actual MCP tool — numbers from the framework, not prior knowledge."* |
| Wrong column name | *"value_column is the literal header 'daily_revenue'."* |
| Paraphrased number | *"Read the exact number from the tool output."* |

---

*Numbers last verified against `generate.py` seed 20260610. If the
generator changes, re-run `rehearse.py` and update both this card and
README.md.*

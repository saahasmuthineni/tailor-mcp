# 90-second demo — storyboard

*Launch-week asset plan: one short screen recording (or GIF pair)
showing the loop that makes the project legible in under two minutes:
ask → server computes → answer + receipt. Draft 2026-06-10.*

> **Blocker found while drafting:** the existing
> [`docs/guides/demo.tape`](guides/demo.tape) records
> `tailor walkthrough`, a CLI verb hard-removed in v8.0.0
> (ADR 0040) — running VHS against it today produces a recording of
> an error. The tape (and the README GIF it generates) needs a
> rebuild before launch. This storyboard is the spec for that
> rebuild.

## Why screen recording, not terminal-only

Since v8.0.0 the recipient surface *is* Claude Desktop chat — the
walkthrough and fitting-room are MCP tools, not CLI verbs. A
terminal-only GIF now misrepresents the product. The honest demo is
a chat window doing the work, with one terminal beat at the end for
the audit receipt.

## Shot list (≈90 seconds)

**Beat 1 — the setup, 10 s.** Title card over the Claude Desktop
window: *"12 stores. 90 days of daily sales. The data never leaves
this machine."* (Data: `examples/business_demo/` — business-shaped on
purpose; the viewer should not need a biomechanics degree.)

**Beat 2 — the cohort question, 25 s.** Type:
*"Which region's stores are doing better? Use csv_group_summary."*
Show the tool-call chip expanding; linger two seconds on the result
JSON (north ≈ $11.7K, south ≈ $15.4K, n=6 each) before Claude's
prose. **Caption: "1,080 rows reduced to two summary rows —
server-side. No sales data entered the context window."**

**Beat 3 — the anomaly, 25 s.** Type: *"Anything unusual at any
individual store?"* Claude runs `csv_summary_report` on store_N03,
flags the mid-quarter collapse (min ≈ $1.1K vs mean ≈ $13.4K).
**Caption: "Found from a ~400-token summary, not 8,000 raw rows."**

**Beat 4 — the receipt, 20 s.** Cut to terminal:

```bash
sqlite3 ~/.tailor/data/audit.db \
  "SELECT tool_name, outcome, called_at FROM audit_log ORDER BY id DESC LIMIT 5;"
```

Rows appear. **Caption: "Every call the AI made — tool, params,
outcome — in a local audit log. Not a chat transcript. A receipt."**

**Beat 5 — close, 10 s.** Card:
*"Local-first. Audited. Any MCP client."* →
`uv tool install tailor-mcp` → repo URL.

## Production notes

- Rehearse with `python examples/business_demo/rehearse.py` first
  (exit 0 = the numbers on screen will match this storyboard).
- Record beats 2–3 in one take; Claude's tool choice can drift — the
  recovery prompts in the business demo README fix a bad take.
- Keep the result-JSON linger ≥2 s; it's the only moment that proves
  the numbers come from the tool, not the model.
- Deliverables: one ~90 s MP4 (launch posts) + a cropped ~20 s GIF of
  beat 2 alone (README hero). The VHS tape rebuild covers only the
  terminal beat; the chat beats need a screen recorder.

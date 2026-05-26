---
domain: vault
note_type: snapshot
last_written: "2026-04-20"
written_by: "tailor-fitting-room-seed"
generated_at: "2026-04-20T15:42:00Z"
tags:
  - snapshot
  - hip-lab-demo
---

# Vault Snapshot — HIP Lab Realistic Demo

You're looking at a bundled walkthrough of Tailor scaffolded by
`tailor fitting-room`. Sixteen synthetic subjects (S001 – S016, 8 M
/ 8 F, isometric force-to-failure protocol) live in `force/`, with
matching EMG envelopes in `emg/` and 31P-MRS spectra stubs in `mrs/`.
The data is synthetic by construction — sized to mimic the
sex-difference effect magnitudes from the *J Physiol* 2024 review
literature on human performance, not to defame, identify, or
otherwise stand for any real participant (per ADR 0024).

## Suggested first prompts

These are the questions this walkthrough is designed to answer
cleanly. Try them in order:

- *"Compare male versus female force decline rates in this cohort."*
  Server-side cohort aggregation across all 16 subjects, grouped by
  the `metadata.json` sidecar's `sex` field. No participant-level
  data reaches the AI's context; only the aggregate result envelope
  does.
- *"What about subject four?"* — surfaces the **S004 wow moment**
  documented below; the cross-session analytical memory claim made
  tangible.
- *"Show me subject 4's force trace in detail."* — per-subject
  Tier-1 fatigue diagnostic (peak, decline %, time-to-50%-drop).
- *"Show me the recent moments in the vault."* — surfaces the
  analyst's prior observations via `vault_list_moments`, including
  the S004 moment above. The durable-memory surface the framework
  is built around.
- *"Step me through the tier levels for subject four — what does
  each one cost?"* — Claude walks the three access tiers and
  demonstrates the AI-economics lever. Tier 1 returns a scalar
  answer at ~310 tokens; Tier 2 fires the **consent gate** (a
  structured ADR 0004 `LLMInstruction` envelope that asks the
  operator to approve biometric access before any decimated rows
  cross the wire); Tier 3 fires the **cost gate** at this
  deployment's 15,000-token threshold (Tier 3 raw-window estimate
  for one 60s subject is ~24,000 tokens; actual payload would be
  ~50,000). See the **Token cost shape** section below.

## Recent moments

- 2026-04-20: **S004 (subject four) — atypical EMG/force decoupling
  under fatigue.** S004's peak EMG envelope sits ~240 µV against a
  female-cohort middle band of 150 – 205 µV, with ordinary force
  production and an ordinary fatigue trajectory. The high
  motor-unit recruitment without commensurate force output pattern
  is consistent with the *J Physiol* 2024 sex-differences review
  literature. The moment names possible explanations (recent
  overreaching, upper-extremity issue, unrecovered neural-fatigue
  substrate) and suggests follow-up actions. Ask `vault_read_note`
  with `filename="moments/2026-04-20-s004-emg-force-decoupling-suspected.md"`
  for the full record, or `vault_search_notes` with `query="subject four"`.

## Token cost shape

The same question — *"tell me about subject four"* — costs very
different amounts depending on which tier resolves it. Empirically,
on the bundled HIP Lab fixtures (60s @ 100 Hz per subject, verified
via wire audit during v7.3.4):

| Tier | Tool | Wire tokens (approx) | Gate |
|---|---|---|---|
| 1 | `force_cohort_summary` / `force_summary` (server-computed scalar) | ~310 | None — Tier 1 is free |
| 2 | `force_downsampled` S004 (~600 decimated rows) | ~6,750 | Consent gate (biometric access) |
| 3 | `force_raw_window` S004 (full 60s at 100 Hz) | ~50,000 actual; ~24,000 pre-execution estimate | Cost gate — fires at this deployment's 15,000-token threshold (per `cost_threshold` in `user_config.json`) |

A recipient asking the cohort thesis at Tier 1 spends ~310 tokens
on the AI's context. The same question routed to raw streams at
Tier 3 would spend ~164× more — and on a larger cohort or longer
protocols, the magnitude compounds.

This is the **AI economics** lever (per [ADR 0029](docs/adr/0029-token-reduction-as-analytical-quality.md),
amended 2026-05-12): tier-1 server-side computation isn't just a
cost optimisation, it's a cognition lever — freed context goes to
reasoning over the analyst's prior Wardrobe, the audit log, and the
current question rather than to data shuffling. A $200/month
context budget at the most-expensive AI tier resolves to a $2/month
budget at Tier 1, because most analytical questions are answerable
at Tier 1 without ever sending raw streams.

The two server-side gates (consent at Tier 2; cost at Tier 3) make
the lever auditable. A recipient probing the tiers sees both
structured `LLMInstruction` envelopes (per [ADR 0004](docs/adr/0004-structured-llm-instruction.md))
firing — the consent gate asking for biometric access, the cost
gate asking for cost approval — before any data crosses the wire.

## What this walkthrough demonstrates

- **The cohort thesis (analytical credibility).** Tier-1 server-side
  computation grouped by metadata-sidecar fields. The classic ~30 %
  sex difference in absolute isometric force, reproduced on
  synthetic data sized to match the published literature shape.
- **Durable analytical memory.** The S004 moment above was written
  by an analyst in a prior session and persists across Claude
  restarts. Ask about subject four and the AI surfaces this moment
  unprompted.
- **IRB-grade audit log.** Every call records to `data/audit.db`
  with timestamp, tool name, parameters, outcome, latency, and
  optional `entity_id` (per ADR 0001 + ADR 0002). Open the SQLite
  file from the operator's shell
  (`sqlite3 data/audit.db "SELECT tool_name, outcome, entity_id, called_at FROM audit_log ORDER BY id DESC LIMIT 20;"`)
  to reconstruct a session post-hoc. An MCP-callable audit-query
  tool is queued for v7.4.0 per ADR 0038; in v7.3.4 the audit log
  is inspectable from the shell, not from inside the Claude Desktop
  chat.
- **Deterministic-by-construction processing.** Per ADR 0008,
  every processing function is a `@staticmethod` pure function
  with no PRNG and no clock reads — the same call with the same
  inputs returns the same numbers across machines. The basis for
  the reproducibility claim a manuscript would cite.
- **Local-first.** The data, the vault, the audit log, the
  processing all live on this machine. Hosted LLMs receive only
  server-computed result envelopes, not raw biometric streams.

## Notes on this snapshot

This file is the bundled seed orientation document shipped with the
fitting-room fixtures. It is loaded as a `note_type: snapshot` row
in the vault index per v7.3.4's rescan classifier; `vault_get_snapshot`
returns it verbatim on the first call. Calling `vault_generate_snapshot`
explicitly will regenerate from live vault state and overwrite this
hand-written orientation; for a recipient walkthrough the
operator-tier checkpoint call is not on the path.

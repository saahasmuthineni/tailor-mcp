# Local-LLM Guardian — Setup Guide

**Status:** v0 — opt-in. Defaults to disabled (NullBackend); existing
deployments are behaviourally unchanged until you opt in.

The local-LLM guardian is a framework-tier component that runs an LLM
on the analyst's machine to compose structured natural-language
responses over deterministic processing output. The architectural
commitment is in [ADR 0022 — Local LLM is framework-tier infrastructure](../adr/0022-local-llm-guardian.md).
This guide is the operator-facing setup path.

## What the guardian does, in one sentence

When you ask the hosted LLM (e.g., Claude Desktop) a question about
already-computed cohort or fatigue data, the hosted LLM can call a
new tool — `ask_local_oracle` — that hands the question + your data
to a local model running on your machine. The local model composes a
structured response containing **citable numerical claims** (drawn
verbatim from the deterministic processing output, never invented by
the LLM) and a **non-citable narrative** (LLM-generated prose,
explicitly labelled non-citable in `_meta`).

The architectural rule, in plain English: **numbers come from
`processing.py`; prose comes from the local LLM; the contract enforces
the boundary.**

## Why you might want this

Three benefits, in order of weight:

1. **Stronger privacy posture for IRB-governed deployments.** With the
   guardian opted in, the framework's claim shifts from "no biometric
   streams enter the LLM context at Tier 1" to "no biometric streams
   leave the analyst's machine, ever, at any tier — including to
   hosted LLMs." That sentence unblocks deployments where institutional
   policy forbids any raw biometric data leaving institutional
   infrastructure.

   **Important precision** — the strengthened claim covers **streams**,
   not all identifiers. The `narrative` field of an `OracleResponse`
   is LLM-generated free text and does not pass through the
   [PHI-scrubber seam](../adr/0003-phi-scrubber-seam.md). If a careless
   analyst pastes participant identifiers into a question, or if
   participant CSV files contain unscrubbed identifier columns, a
   misconfigured local model can echo identifiers into the narrative
   that traverses the wire to the hosted LLM. Cited numerical claims
   are unaffected (they come from `processing.py`); the surface
   exposed is *prose-shaped identifiers*, not biometric streams.
   Institutional deployments with strict PHI policies should configure
   a `PHIScrubber` subclass *and* either prompt their local model with
   identifier-refusal instructions or wait for the prompt-injection
   ADR named in [ADR 0022 § "Explicitly out of scope"](../adr/0022-local-llm-guardian.md).

   **Important precision — substrate metadata egress** ([ADR 0023](../adr/0023-local-llm-cooperation-loop.md))
   — every successful `ask_local_oracle` call surfaces vault metadata
   into the hosted-LLM-bound payload via `related_substrate`. The
   fields are deliberately metadata-only: `kind` (`theme` / `moment` /
   `failure_mode`), `slug` (note filename without `.md`), `title`
   (frontmatter title for moments and failure-modes), `subject_id`,
   `status`, and `last_updated`. *No note bodies, no biometric
   streams.* But: **slug and title strings are analyst-authored**.
   If a deployment's analyst names a theme `john-smith-glucose-spike`
   or sets `title: "P004 - Jane Doe MRN 12345"`, that string crosses
   to the hosted LLM verbatim — vault content bypasses the scrubber
   by [ADR 0012](../adr/0012-vault-phi-scrubber-bypass.md). Two
   recommendations: (a) instruct analysts that vault slugs and titles
   should not contain HIPAA Safe Harbor identifiers; (b) for
   institutional deployments where (a) cannot be guaranteed, subclass
   `PHIScrubber` and wire it into the local-LLM dispatch path.

   **Important precision — automatic cross-subject substrate**
   ([ADR 0009](../adr/0009-vault-subject-keying.md) IS-NULL-or-match
   semantics inherited by [ADR 0023](../adr/0023-local-llm-cooperation-loop.md))
   — when an oracle call is scoped to subject P003, the substrate
   scan also surfaces cross-subject themes (`subject_id IS NULL` —
   themes that span the cohort). A theme titled `comparing-p004-and-p007-recovery`
   would surface on a P003-scoped oracle call, with the title string
   crossing to the hosted LLM. ADR 0009 documented this for
   `vault_search_notes` where the analyst chose to query; PR1 makes
   the same surfacing automatic per oracle call. This is structurally
   permitted by ADR 0012 but is a **deployment-shape choice** that
   institutions running this framework against IRB-governed cohorts
   should make explicit:
   - Path A (default — strict-data, opt-in local-LLM): cross-subject
     substrate is permissible because vault content is analyst
     interpretation, not raw participant data.
   - Path B (more conservative): subclass `PHIScrubber` to drop
     `related_substrate` entries whose `subject_id` is NULL.

   **Important precision — gap-reasoning egress**
   ([ADR 0023](../adr/0023-local-llm-cooperation-loop.md) PR2) — PR2
   added two more LLM-generated fields to `OracleResponse` that also
   bypass the PHI-scrubber seam: `next_best_calls` (framework tool
   names the local LLM thinks would raise oracle confidence — bounded
   vocabulary of ~45 framework tool names; low PHI risk in practice
   because the prompt schema is pinned to tool-name shape) and
   `unresolved_intent` (questions the local LLM thinks the analyst
   should answer — **unbounded LLM-generated free text**, structurally
   the same PHI-egress shape as `narrative`). The framing-claim
   covering streams holds; the `unresolved_intent` field can plausibly
   echo subject IDs, dates, or analyst-supplied identifiers as part of
   the question text the local LLM emits (e.g. "did P003's lab visit
   on 2026-04-12 involve insulin?" — a Safe Harbor §164.514(b)(2)
   date-of-service emission the scrubber never sees). Two
   recommendations: (a) treat `unresolved_intent` content as
   institutionally-equivalent to `narrative` for review purposes;
   (b) deployments needing a stricter posture should subclass
   `PHIScrubber` to apply the institution's policy to *both*
   `narrative` and `unresolved_intent` on the local-LLM dispatch path
   (Path B from "automatic cross-subject substrate" above).

   The `oracle_substrate_count`, `oracle_next_best_calls_count`, and
   `oracle_unresolved_intent_count` audit-log columns
   ([ADR 0023](../adr/0023-local-llm-cooperation-loop.md))
   record per oracle call how many vault items were surfaced, how
   many tool suggestions the local LLM emitted, and how many
   analyst-questions it proposed. `_meta.substrate_scan_warning`
   (when present) records swallowed VaultStorage exceptions so a
   reviewer can distinguish "scanned cleanly, found nothing" from
   "scan crashed silently."

2. **Reduced token spend on the hosted LLM.** Routine analytical
   questions get composed locally; only the structured response (with
   already-cited numbers) traverses the wire to the hosted LLM. The
   hosted LLM's job shrinks to "synthesize across multiple oracle
   responses and write the methods paragraph."

3. **Citation-ready manuscript drafting.** Every numerical claim in
   an oracle response carries `processing_call` provenance back to the
   deterministic function that produced it. When the hosted LLM
   composes a methods paragraph from oracle outputs, every cited
   number is auditable to a `processing.py` call.

## Tier table

The four tiers are codenamed Scout / Sentinel / Guardian / Titan. The
**cited numerical claims are identical across all four tiers** (they
come from deterministic processing). What varies is narrative quality,
ambiguity-axis detection, and refusal calibration.

| Tier | Codename | Model | Disk | RAM (loaded) | Hardware floor | Latency (M-series Mac / typical CPU) |
|------|----------|-------|------|--------------|----------------|------|
| Lite | **Scout** | `llama3.2:1b` | ~770 MB | ~1.2 GB | 4 GB laptop | 2–4 s / 4–8 s |
| Conservation | **Sentinel** | `phi3.5:3.8b` | ~2.2 GB | ~3 GB | 8 GB laptop | 2–4 s / 5–8 s |
| Balanced (default) | **Guardian** | `llama3.1:8b` | ~4.7 GB | ~6 GB | 16 GB laptop | 4–7 s / 10–15 s |
| Power | **Titan** | `qwen2.5:14b` | ~9 GB | ~10 GB | 32 GB workstation | 8–12 s / often impractical CPU-only |

If your laptop already runs Slack, Obsidian, and a browser, the
Guardian default (`~6 GB during analysis bursts`) is comfortable on
16 GB and ample on 32 GB. The Scout tier exists for older or
resource-constrained machines — *cited numbers are identical*; the
narrative just gets shorter and ambiguity-axis flagging gets weaker.

## Setup

### 1. Install Ollama

[ollama.com/download](https://ollama.com/download) — official installers
for Windows, macOS, and Linux. After install, the daemon runs in the
background on `localhost:11434`.

Verify:

```bash
ollama --version
```

### 2. Pull a model

Default-tier model (Guardian):

```bash
ollama pull llama3.1:8b
```

Or pick a different tier:

```bash
ollama pull llama3.2:1b      # Scout (4 GB laptop)
ollama pull phi3.5:3.8b      # Sentinel (8 GB laptop)
ollama pull llama3.1:8b      # Guardian (default)
ollama pull qwen2.5:14b      # Titan (32 GB workstation)
```

### 3. Configure `user_config.json`

Add a `local_llm` block to `~/.tailor/user_config.json`:

```json
{
  "local_llm": {
    "backend": "ollama",
    "tier": "guardian",
    "model": "llama3.1:8b",
    "endpoint": "http://localhost:11434",
    "timeout_s": 60
  }
}
```

`backend` is required (`"ollama"` or `"null"`). All other fields are
optional with the defaults shown above.

### 4. Restart the MCP server

```bash
tailor serve
```

Look for this log line:

```
Registered local-LLM layer (backend=ollama, tier=guardian, model=llama3.1:8b)
```

If you see `backend=null`, the config was not picked up — check JSON
syntax with `python -m json.tool < ~/.tailor/user_config.json`.

## How it works in conversation

In Claude Desktop, when you ask a question that involves the cohort
tools (`csv_cohort_summary`, `csv_force_decline`), Claude can call
`ask_local_oracle` after first calling the deterministic tool(s).
The pattern is:

1. **Claude calls** `csv_cohort_summary({"column": "force", "group_by": "sex", "metric": "max"})`.
2. **Claude calls** `ask_local_oracle({"question": "compare male vs female peak force", "resolved_context": {"csv_cohort_summary": <result_from_step_1>}})`.
3. **Local LLM composes** a structured response with cited claims and narrative.
4. **Claude consumes** the response and presents it to you.

You do not need to know any of this is happening; the tool descriptions
guide Claude to use the pattern.

## What's in the response

```json
{
  "numerical_claims": [
    {"metric": "mean", "value": 247.3, "subject_id": "male", "processing_call": "csv_cohort_summary"},
    {"metric": "mean", "value": 189.2, "subject_id": "female", "processing_call": "csv_cohort_summary"}
  ],
  "narrative": "Male cohort's force averaged 247 N (mean); female cohort's averaged 189 N (data from csv_cohort_summary).",
  "ambiguity_axes": [],
  "confidence": 0.7,
  "_meta": {
    "domain": "local_llm",
    "package_version": "7.0.0",
    "tool_name": "ask_local_oracle",
    "called_at": "2026-05-01T12:00:00+00:00",
    "tokens_this_call": 412,
    "session_total_tokens": 412,
    "scrubber_id": "noop-v1",
    "oracle": {
      "model_id": "llama3.1:8b",
      "tier": "guardian",
      "latency_ms": 4523,
      "prompt_hash": "abc123def456",
      "processing_calls": ["csv_cohort_summary"],
      "backend": "ollama",
      "narrative_disclaimer": "narrative is LLM-generated and non-citable; cite from numerical_claims."
    }
  }
}
```

Cite from `numerical_claims` and `processing_call` — those are the
deterministic, reproducible numbers. The `narrative` is for the
analyst's reading comprehension, not for manuscript prose.

## Switching tiers

Edit `tier` and `model` in `user_config.json`:

```json
{
  "local_llm": {
    "backend": "ollama",
    "tier": "scout",
    "model": "llama3.2:1b"
  }
}
```

Restart the server. Pull the new model first if you haven't already
(`ollama pull llama3.2:1b`).

## What gets disabled if Ollama isn't running

The layer falls back gracefully. If Ollama is unreachable, oracle
calls return a structured response with `confidence: 0.0`, narrative
explaining the failure, and the deterministic numerical claims still
flowing through. You will not get manuscript-quality prose, but the
cited numbers remain auditable.

## What's not in v0

v0 ships the seam, the contract, the NullBackend default, the
OllamaBackend, and oracle mediation on the cohort tools. Several
named follow-ups are explicitly out of scope and tracked for future
sessions:

- Verifier behaviour on hosted-LLM responses (catching hosted-LLM
  hallucinations against deterministic ground truth).
- Sanitizer / proxy mode (intercepting tool calls before they reach
  hosted Claude).
- Conductor-mode toggle (`streamlined | balanced | strict`).
- Citation-grounding enforcement on manuscript drafts.
- Migration of the remaining 45 tools to oracle mediation.
- IRB-facing threat-model update for the local-LLM prompt-injection
  attack surface.
- Automatic tier-detection in the pilot wizard based on available RAM.

See ADR 0022 § "Phase 0 v0 scope" and § "Explicitly out of scope" for
the full list.

## Troubleshooting

**`backend=null` in logs even though I set `backend: "ollama"`** —
Check JSON syntax. The most common cause is a trailing comma. Run
`python -m json.tool < ~/.tailor/user_config.json` to validate.

**Oracle call returns `confidence: 0.0` and "unavailable" narrative** —
Ollama daemon is not reachable. Check that Ollama is running
(`ollama list`). Check `endpoint` in config matches the daemon's URL.

**Latency is much higher than the table shows** — First call after
server boot takes ~10 s extra to load the model. Subsequent calls
within 5 minutes are warm. To force a warm-start on serve, call any
oracle request once after `tailor serve` starts.

**RAM pressure on a 16 GB laptop** — Drop to Scout or Sentinel tier.
Cited numerical claims are identical; only narrative quality changes.

## Related ADRs

- [ADR 0022 — Local LLM is framework-tier infrastructure](../adr/0022-local-llm-guardian.md) — the architectural commitment.
- [ADR 0008 — Deterministic-by-construction processing](../adr/0008-deterministic-by-construction-processing.md) — the boundary the local LLM operates against.
- [ADR 0003 — PHI scrubber as seam](../adr/0003-phi-scrubber-seam.md) — the architectural pattern this layer mirrors (no-op default, opt-in via config).
- [ADR 0007 — Rendering-layers policy](../adr/0007-rendering-layers-policy.md) — the dual-output pattern (deterministic source-of-truth + additive overlay).
- [ADR 0015 — Tier-1 cohort surface](../adr/0015-tier-1-cohort-surface-and-metadata-sidecar.md) — the cohort tools v0 mediates.

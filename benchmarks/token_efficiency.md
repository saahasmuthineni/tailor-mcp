# Token-Efficiency Benchmark

Two named measurements back the "AI economics" claim from
[ADR 0029](../docs/adr/0029-token-reduction-as-analytical-quality.md):
**A. Per-query efficiency** (data → answer in one session) and
**B. Session persistence efficiency** (cost of resuming across
sessions). Both run against bundled HIP-Lab realistic fixtures
(synthetic-by-construction per [ADR 0024](../docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md);
data shape mimics 100 Hz isometric force traces from a 16-subject
sex-differences cohort).

| Benchmark | Single-question ratio | Reading |
|---|---:|---|
| A. **Per-query efficiency** (single subject) | **657.6×** | Tier-1 server-side computation vs raw CSV in context |
| A. **Per-query efficiency** (16-subject cohort) | **938.2×** | Same, scaled to a multi-file cohort question |
| B. **Session persistence efficiency** (S004 resume) | **318.0×** | Vault retrieval vs naive re-paste of data + accumulated notes |

The "at least 100× cheaper" claim in ADR 0029 is a *conservative
floor*; on this benchmark the actual ratios are **3.2× to 9.4× the
floor**, depending on scenario. Reproduce from a fresh clone with
`pip install tiktoken` and `python benchmarks/token_efficiency.py`.

---

## Assumptions (everything that could change the numbers)

A skeptical engineer should be able to challenge or replicate this
benchmark by inspecting each row below. Anything not in this table is
either constant across both approaches (e.g. system prompt) or
explicitly excluded under **Limitations** below.

| Dimension | Value | Notes |
|---|---|---|
| **Date of measurement** | 2026-05-26 | Re-run on every release per CI gate (planned) |
| **Package version** | tailor-mcp 8.0.0 (this commit bumps to 9.0.0) | `CSVProcessing` surface stable since v6.5.0 (ADR 0015) |
| **Python** | 3.10+ (any version that runs the test suite) | No version-dependent behavior in the measured code |
| **Primary tokenizer** | `tiktoken==0.13.0`, encoding `cl100k_base` | OpenAI BPE; industry-standard proxy for Claude's tokenizer (see *Why tiktoken not Anthropic's API* below) |
| **Cross-check tokenizer** | `tailor.framework.cost.estimate_tokens` (chars / 4) | Conservative heuristic; per CLAUDE.md v7.3.4 ~2.1× under-counts vs actual wire-measured |
| **Model assumed for $$ math** | Claude Sonnet 4.6 input pricing | $3.00 / million input tokens (Anthropic public list price, late 2025) |
| **Cache pricing assumed** | $0.30 / M cache reads, $3.75 / M cache writes | Anthropic prompt-caching tier — see §"Prompt caching" below |
| **Dataset (Benchmark A)** | 16 force-CSVs, 60s @ 100 Hz, 8M / 8F, in `src/tailor/_fixtures/hip_lab_demo_realistic/force/` | 6,000 samples per file; ~83.5 KB each; synthetic-by-construction per [ADR 0024](../docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md) |
| **Dataset (Benchmark B)** | The same 16 force-CSVs *plus* `src/tailor/_fixtures/hip_lab_demo_realistic/vault/snapshot.md` + the S004 EMG/force-decoupling moment | Bundled vault artifacts represent multi-session accumulated analytical memory |
| **Question (A.1)** | "Summarize subject S004's fatigue trajectory: peak force, decline percentage, time-to-50%-drop, and decline rate over the 60-second isometric trial." | Verbatim |
| **Question (A.2)** | "Compare peak force and time-to-50%-drop between male and female participants across all 16 HIP-Lab subjects; include per-subject decline percentages." | Verbatim |
| **Question (B.1)** | "Resume an analytical thread on the HIP-Lab cohort with particular focus on subject S004's atypical EMG/force decoupling — what's been observed, what should I look at next?" | Verbatim |
| **What is measured** | Data-payload input tokens only | System prompts / question text / output budget excluded (constant across approaches; ratio unchanged) |
| **N sessions for Benchmark B compounding** | 5 | Illustrative typical multi-session research thread; ratio is N-invariant |

### Why tiktoken (cl100k_base) and not the Anthropic count_tokens API

Anthropic does not publish their tokenizer as a standalone library.
Their `messages.count_tokens` endpoint requires network + API key,
which would prevent the benchmark from being reproducible offline
(and from a fresh clone without credentials). `tiktoken cl100k_base`
is OpenAI's BPE encoding; for dense numeric text it tends to count
within ~5–15% of Claude's published per-call token counts on
comparable payloads. The chars-per-4 cross-check is more conservative
still. We report both so a skeptic can pick whichever bound they
prefer; the 100× floor holds under either.

### What this benchmark deliberately does NOT measure

See the **Limitations** section at the bottom — those exclusions are
called out before the numbers so the reader is calibrated correctly.

---

## A. Per-query efficiency

How many tokens does an LLM consume when answering a single
analytical question — if a researcher pastes the raw CSV(s) into the
conversation versus if they call a Tailor Tier-1 tool and paste only
the structured summary?

| Scenario | Baseline (raw CSV → LLM) | Tailor (Tier-1 result → LLM) | Ratio |
|---|---:|---:|---:|
| Single subject S004 — 60s fatigue diagnostic | **48,006 tokens** | **73 tokens** | **657.6×** |
| Cohort — 16 subjects stratified by sex | **769,311 tokens** | **820 tokens** | **938.2×** |

Cross-check with Tailor's conservative `chars / 4` heuristic:
**435.1×** (single subject) and **615.9×** (cohort) — still well over
the 100× floor.

> **Practical implication of the cohort number:** at 769,311 tokens
> the baseline payload **exceeds Claude's 200K context window**. The
> raw-CSV approach isn't just expensive at cohort scale — it's
> structurally impossible without chunking, streaming, or another
> orchestration workaround. Tailor's Tier-1 surface is the difference
> between "the question is answerable in one call" and "the question
> is not answerable at all without a different architecture."

### A.1 — Single-subject fatigue analysis on S004

**Baseline.** `S004_force.csv` pasted into Claude Desktop:
6,000 samples + 1 header = 6,001 lines, 83,539 bytes,
**48,006 tokens** (tiktoken cl100k_base) / 20,884 (chars/4).

**Tailor.** Server-side call to
`CSVProcessing.force_decline_summary(values, timestamps)` returns a
192-byte / **73-token** JSON payload:

```json
{"peak":229.274,"peak_index":1621,"end_value":54.796,"n_samples":6000,
 "decline_pct_total":76.1,"peak_time_s":16.21,"duration_s":59.99,
 "decline_rate_per_min":239.12,"time_to_50pct_drop_s":0.79}
```

**Ratio (tiktoken): 48,006 / 73 = 657.6×.**

The result payload reproduces the v7.3.4 CLAUDE.md banner's
worked-example claim verbatim (peak ≈ 229 N, decline_pct = 76.1%,
time-to-50%-drop = 0.79 s) — the benchmark validates a documented
project claim, not a freshly invented one.

### A.2 — 16-subject cohort comparison stratified by sex

**Baseline.** 16 CSVs (file-name-headered) + `metadata.json` pasted
into Claude Desktop: 1,340,158 bytes, **769,311 tokens** (tiktoken) /
335,039 (chars/4).

**Tailor.** Three pure-function calls server-side (`aggregate_metric`
+ `cohort_stats` + `force_decline_summary`); 2,178-byte / **820-token**
JSON payload stratified by `sex` with per-subject decline appended.

```json
{
  "cohort_summary_by_sex": {
    "F": {
      "max":                { "n": 8, "mean": 200.075, "std": 19.328, "min": 176.371, "max": 229.274 },
      "time_to_50pct_drop_s": { "n": 8, "mean": 0.78,    "std": 0.191,  "min": 0.44,    "max": 0.97 }
    },
    "M": {
      "max":                { "n": 8, "mean": 275.982, "std": 20.181, "min": 249.093, "max": 306.772 },
      "time_to_50pct_drop_s": { "n": 8, "mean": 0.784,  "std": 0.115,  "min": 0.65,    "max": 0.96 }
    }
  },
  "per_subject_decline": { "S001": { "sex": "F", "group": "control", "peak_N": 200.4, ... } }
}
```
(per-subject section truncated for display; full payload is 16 entries)

**Ratio (tiktoken): 769,311 / 820 = 938.2×.**

---

## B. Session persistence efficiency

The first benchmark measures cost *within a single session*. The
second measures cost *across* sessions — what does it take to bring
a fresh LLM session to the same analytical state on a multi-session
thread? Without persistent structured memory, every resume re-pays
the data-paste cost. Tailor's vault is the structural answer:
distilled themes / moments / snapshots live on disk and are
retrieved selectively by the vault layer for the current question.

This benchmark uses **real vault artifacts** — the bundled
`snapshot.md` and the S004 EMG/force-decoupling moment shipped with
the HIP-Lab realistic fixtures. These represent an analyst's
accumulated thinking across a multi-session investigation; they were
written by an analyst in a prior session and persist across Claude
restarts (per the bundled `snapshot.md`'s own claim).

### B.1 — Resuming the S004 cohort thread

**Baseline (stateless reconstruction).** To bring a fresh LLM
session to the same analytical state, the researcher must paste:

1. **The raw cohort data** — so the LLM can verify any claim made
   in pasted-in notes. Without source-of-truth data the LLM is
   operating on the researcher's word, which isn't science.
   16 CSVs + `metadata.json`.
2. **Equivalent accumulated notes** — the irreducible distilled
   knowledge of what's been observed. We use the exact `snapshot.md`
   + S004 moment content as a *charitable proxy* — a real
   researcher's informal notes (Apple Notes, a docx, a lab notebook)
   would likely be longer and less structured.

Combined: 1,349,713 bytes, **771,743 tokens** (tiktoken) / 337,428 (chars/4).

**Tailor (vault retrieval).** When the session starts, the vault
layer auto-surfaces `snapshot.md` via `vault_get_snapshot`. The LLM
searches for "subject four" via `vault_search_notes` and retrieves
the S004 EMG/force-decoupling moment.

What the LLM actually sees on resume:

- `snapshot.md` (6,918 chars): cohort overview, suggested prompts,
  recent moments index, token-cost table, what the walkthrough
  demonstrates
- `moments/2026-04-20-s004-emg-force-decoupling-suspected.md` (2,612
  chars): the S004 wow moment with the EMG envelope observation,
  the hypothesis space, and named follow-up actions

Combined: 9,537 bytes, **2,427 tokens** (tiktoken) / 2,384 (chars/4).

**The data itself stays on disk.** If the LLM needs to verify a
claim against fresh data, it calls `force_cohort_summary` or
`force_decline_summary` and pays the per-query Tier-1 cost (73–820
tokens per Benchmark A) — not the full ~769K raw-data cost.

**Ratio (tiktoken): 771,743 / 2,427 = 318.0×.**

### B.2 — Compounding cost across N sessions

The structural point of Benchmark B is that **baseline cost grows
linearly with session count** (the LLM has no persistent memory; the
researcher must re-paste data and notes every resume), while
**Tailor's per-session cost is asymptotically constant** (the vault
index returns only items relevant to the current question, not the
entire accumulated history).

Illustrative arithmetic over a 5-session multi-session research
thread (a typical scale for a cohort investigation moving from
hypothesis to candidate finding):

| | Baseline | Tailor | Ratio |
|---|---:|---:|---:|
| Tokens per session resume | 771,743 | 2,427 | 318× |
| Tokens × 5 sessions | **3,858,715** | **12,135** | **318×** |

At Claude Sonnet 4.6 input pricing ($3 / million input tokens, no
caching):

- Baseline: ~$11.58 per resume × 5 = **~$57.90** just on the input
  side (output tokens extra)
- Tailor: ~$0.0073 per resume × 5 = **~$0.04** input-side

The cost-per-question lever from ADR 0029 compounds over the
lifetime of an analytical thread.

---

## Prompt caching — quantitative counter-factual

A skeptical reader will ask: *Anthropic supports prompt caching.
Doesn't that erase the gap?* Working through the arithmetic
honestly:

### How prompt caching works

Anthropic's prompt-caching feature (general availability since 2024)
prices repeat prefixes at a steep discount:

- **Cache read** (a hit on a previously-written prefix): 0.1× the
  base input rate (~90% discount).
- **Cache write** (storing a prefix for future reuse): 1.25× the
  base input rate (a one-time premium).
- **Default TTL: 5 minutes** from the last hit. Extended TTL of
  1 hour is available at additional cost.
- The cached content must be **byte-identical** across calls.

### The optimistic case: prompt caching at its best

Assume every baseline call lands within the 5-minute TTL of the
previous one (a single analyst tab open in Claude Desktop, asking
follow-up questions on the same dataset within minutes), and the
researcher pastes exactly the same 769,311-token cohort payload
every time:

- **Cold start (call 1):** 769,311 × $3.75/M = **$2.885**
- **Each subsequent call (within 5 min):** 769,311 × $0.30/M = **$0.231**
- 5 calls: $2.885 + 4 × $0.231 = **$3.81**

Compare to Tailor's session-persistence cost (Benchmark B,
5 sessions): **$0.036**.

Even under the *most favorable* prompt-caching assumption for the
baseline, **Tailor is still ~106× cheaper** (3.81 / 0.036).

### The realistic case: multi-session research

The 5-minute TTL is the killer. Real analytical threads span days
or weeks. A researcher who opens Claude Desktop on Tuesday to
follow up on Monday's analysis pays full cache-write again.
Anthropic's extended 1-hour TTL doesn't change this for multi-day
threads.

For Benchmark B's compounding scenario (5 sessions on 5 different
days):

- Baseline with caching: still 5 × $2.885 = **$14.43** (every
  session is cold; cache write only)
- Baseline without caching: 5 × $2.32 = **$11.58** (caching is
  actually slightly *worse* than no caching when no hits ever land —
  the cache-write premium is dead weight)
- Tailor: **$0.036**

### Why caching doesn't close the gap structurally

1. **Cache content must be byte-identical.** Most analytical threads
   evolve — the analyst adds a new subject, fixes a typo in their
   notes, includes a different question. One byte's difference =
   cache miss.
2. **Cache write costs apply even when the cache is never read
   again.** In a 1-shot session, caching is pure loss.
3. **The vault's lookup pattern is structurally a cache hit, by
   design.** Tailor stores small distilled artifacts that *are*
   what the LLM needs — there is no large payload to cache because
   the structured summary is already small. Caching is what Tailor
   does at the file-system layer, with a TTL of "forever" and a
   write cost of "one Tier-1 call when the analyst first wrote
   their note."
4. **A researcher who hand-engineers a stable cacheable prompt
   wrapper has done most of the engineering Tailor's vault does
   for free.** The cost comparison isn't "Tailor vs Claude
   Desktop"; it's "Tailor vs a hand-engineered caching pipeline
   the researcher must build and maintain."

> **Bottom line on caching:** prompt caching can compress
> within-session repeated-context costs by ~3×, but it does
> nothing for cross-session continuity (the actual workflow shape
> for multi-day analytical work). Tailor's vault is a structurally
> different and complementary technique. They are not in
> competition; a deployment can use both.

---

## Limitations

What this benchmark does NOT capture. A skeptical engineer should
weigh these honestly before generalizing.

### Cases where Tailor's gap is smaller — or where raw data is fine

- **One-shot, one-question analysis on a tiny CSV.** If the data
  fits in a handful of tokens (a 10-row dietary log, a 5-subject
  pilot N), Tailor's overhead (vault initialization, audit log
  schema, scrubber pipeline) is a wash. The 100× claim is about
  data shapes where raw text would be expensive — not about
  arbitrary small data.
- **The LLM legitimately needs to see raw values.** Spotting a
  subtle waveform anomaly the cohort summary aggregated away; doing
  a regex over free-text comments where structure can't be
  pre-extracted. Tier 2 / Tier 3 access exists for these cases;
  Tailor's tier model makes them an explicit (cost-gated) choice
  rather than a default.
- **Datasets that don't decompose into per-subject scalars.**
  Time-series correlations across subjects within a single trial
  (e.g. a leader-follower hand-tracking study) are awkward to
  summarize at Tier 1; the cohort surface assumes per-file
  reduction. Future tools (cross-subject correlation as a Tier-1
  primitive) would close this gap; today, this kind of question
  drops to Tier 2/3 honestly.

### Cost dimensions not captured here

- **Output tokens.** The benchmark measures *input* token cost.
  Output costs are roughly constant across both approaches because
  the *answer* (a few hundred tokens of prose) is the same shape
  regardless of whether the LLM derived it from raw data or a
  structured summary. Including output tokens would inflate both
  columns by the same amount and leave the ratio unchanged.
- **Engineering / setup cost.** Tailor requires a one-time install,
  scaffolding fixtures, and choosing a tier model. A
  back-of-envelope estimate is ~30 minutes for a researcher
  following `tailor pilot` against an existing CSV directory. The
  benchmark assumes this cost is paid; for evaluating it
  separately, see [docs/diagnosis/phase-0-diagnosis-kit.md](../docs/diagnosis/phase-0-diagnosis-kit.md).
- **Latency.** A Tier-1 call is bounded by stdlib CSV parsing
  (~10–50 ms for a 60-second 100 Hz file); a raw-CSV approach has
  no server-side latency but the LLM input-token processing time
  scales with payload size. Latency is not measured here.

### Quality dimensions not captured

- **Answer correctness.** ADR 0029 makes a separate claim — that
  structured input *also* improves analytical quality (the LLM
  reasons over the question instead of doing floating-point
  arithmetic on 6,000 samples by hand). That claim is not measured
  by this benchmark. Anecdotally the structured approach also
  produces more numerically reliable answers, but rigorously
  validating that requires a different methodology (paired
  blind-graded evaluation).
- **Hallucination risk.** A raw-CSV approach forces the LLM to
  extract numerics from text and is empirically more
  hallucination-prone than a structured summary. Not measured here.

### Why the synthetic-but-representative dataset is a fair proxy

The HIP-Lab realistic fixtures are synthetic-by-construction
([ADR 0024](../docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md)
§ "Synthetic-by-construction precondition"). The numerical
behavior of the cohort statistics differs from real data; the
**token shape** (CSV bytes per sample, JSON envelope size, vault
note size) does not. Token counts are determined by data *shape
and density*, not by participant identity. The ratio is expected to
hold on real data of the same shape; if a researcher runs the
benchmark on their own data and gets a substantially different
ratio, that's a finding worth filing.

---

## Reproducing this benchmark

```bash
# From a fresh clone:
git clone https://github.com/saahasmuthineni/tailor-mcp.git
cd tailor-mcp
pip install tiktoken    # one-shot — not in pyproject.toml
python benchmarks/token_efficiency.py
```

The script prints a JSON document with every number used in this
report under two top-level keys (`per_query_efficiency` and
`session_persistence_efficiency`). The dataset (HIP-Lab realistic
fixtures + bundled vault state) is checked into
`src/tailor/_fixtures/`; no external download required.

Output format is JSON so a future CI gate can parse it and fail if
a regression drops the ratio below the ADR 0029 floor on either
benchmark.

**Determinism guarantees:**

- The `CSVProcessing` functions are pure-static per [ADR 0008](../docs/adr/0008-deterministic-by-construction-processing.md):
  no PRNG, no clock reads. Identical inputs always produce
  identical outputs.
- The script imports `CSVProcessing` directly (no MCP server, no
  router, no audit log) — the measurement is purely about data
  shape, not about MCP-pipeline overhead.
- `tiktoken cl100k_base` is deterministic by construction.

The script should produce **bit-identical** output across machines
with the same `tiktoken` version. If it doesn't, file an issue.

## References

- [ADR 0029 — Token reduction as analytical quality](../docs/adr/0029-token-reduction-as-analytical-quality.md)
  — the architectural claim this benchmark validates.
- [ADR 0015 — Tier-1 cohort surface + metadata sidecar](../docs/adr/0015-tier-1-cohort-surface-and-metadata-sidecar.md)
  — the surface Benchmark A exercises.
- [ADR 0006 — Vault overhaul v6](../docs/adr/0006-vault-overhaul-v6.md)
  + the vault-layer table in CLAUDE.md — the surface Benchmark B
  exercises (`vault_get_snapshot`, `vault_search_notes`).
- [ADR 0024 — Wheel-distributed tour + synthetic-by-construction
  precondition](../docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md)
  — the precondition under which these fixtures may exist in the
  repo.
- [ADR 0008 — Analytical processing is deterministic by
  construction](../docs/adr/0008-deterministic-by-construction-processing.md)
  — why these numbers are reproducible across machines.

## Date

Run 2026-05-26 against package version 8.0.0 (this commit bumps to
9.0.0 as part of the public-flip rename sweep — see commit message)
on Python 3.10+ with `tiktoken==0.13.0`. The pure-function
`CSVProcessing` surface has been behaviorally stable since v6.5.0
(ADR 0015); the bundled vault fixture has been stable since v7.3.4
— numbers should reproduce on any version ≥ 7.3.4.

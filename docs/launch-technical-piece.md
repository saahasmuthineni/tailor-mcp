# The context-window economics problem in LLM-assisted analysis

*Draft of the launch-strategy Move 4 piece — the long-shelf-life
technical argument, not a launch post. Target home: GitHub Pages /
linked from the README. ~1,600 words. All figures below are from
[`benchmarks/token_efficiency.md`](../benchmarks/token_efficiency.md),
reproducible offline in three commands.*

---

There's a default architecture for "use an LLM on my data," and
almost everyone starts with it: paste the data into the context
window and ask the question. It works in the demo. It works on the
first real file. And then it stops working — not gradually, not
expensively, but *structurally* — at almost exactly the scale where
the work starts to matter.

This piece makes three arguments. First, that raw-data-into-context
fails as architecture, not as budget — there is a scale, easily
reached, where no amount of money fixes it. Second, that the fix is
an old pattern applied to a new boundary: compute where the data
lives, move only answers. Third, that the same failure has a
less-discussed twin on the time axis — every new session pays a
reconstruction tax — with the same architectural fix. There's a
concrete implementation with a reproducible benchmark at the end,
but the arguments stand without it.

## 1. The impossibility argument

Concrete numbers, from a real workload shape: biomechanics force-plate
data sampled at 100 Hz, 16 subjects, 60 seconds each — a small pilot
study by any research standard. As CSV text, that cohort is
**769,311 tokens** (tiktoken `cl100k_base`).

Claude's context window is 200K tokens.

The natural analytical question — *"are men or women losing strength
faster in this cohort?"* — is a question *about the whole cohort*. In
the paste-the-data architecture, it cannot be asked. Not "costs too
much": **cannot be asked**. The data is 3.8× larger than the largest
container you can put it in. Your options become chunking (ask the
model to hold partial conclusions across 4+ passes over data it never
sees whole — accuracy now depends on the model's bookkeeping),
pre-summarizing by hand (you've just written the server-side
computation, informally and unreproducibly), or downsampling (you're
answering a different question about different data).

The important property of this wall: **it does not soften with model
progress.** Context windows grow; data grows faster — at 1kHz (normal
for EMG) that pilot cohort is ~7.7M tokens; a hundred-subject study
at modest rates is tens of millions. Token prices fall; but below the
wall the relevant cost isn't price, it's possibility. An architecture
that requires the data to fit in the prompt has a ceiling set by
whoever generates the data, and they aren't consulting your model
vendor's roadmap.

And even *below* the wall, where pasting is possible, it's quietly
self-defeating: a 48K-token paste into a 200K window spends a quarter
of the model's working memory on raw rows the model will have to
*statistically eyeball*. LLMs are unreliable calculators —
column-wise means over thousands of pasted rows is exactly the work
they do worst — so the architecture maximizes spend on the step that
minimizes answer quality. Context spent shuttling data is context not
spent reasoning.

## 2. The old pattern, at a new boundary

The fix is not novel, and that's the point. No application fetches a
million rows to render a dashboard number; the database computes the
aggregate and returns it. We've known for fifty years that you move
computation to data, not data to computation. The paste-the-data
architecture violates this so casually because chat made it feel
natural — the prompt is *right there*.

Applied to the LLM boundary, the pattern reads: **return the answer,
not the data.** The same cohort question, served by deterministic
server-side computation (group-by on a per-subject scalar, n / mean /
std / min / max per group), returns **820 tokens** of structured
summary. Same numbers an analyst would compute by hand. The measured
ratios on the benchmark workloads: **657.6×** for a single-subject
diagnostic (48,006 → 73 tokens), **938.2×** for the 16-subject cohort
(769,311 → 820 tokens).

Two properties matter more than the ratios:

- **The summary fits where the data couldn't.** The cohort question
  moves from impossible to costing less than this paragraph.
- **The computation is reproducible and the paste is not.** Server-side
  pure functions — no PRNG, no clock — return identical numbers on
  every machine, every run, and each result can carry a provenance
  stamp (version, tool, parameters, timestamp). The model reading raw
  rows returns its best guess, which differs by sampling temperature.
  For any number that ends up in a paper, a report, or a decision,
  this is the difference between a result and an anecdote.

The standard objection is prompt caching — *"re-pasting is cheap now."*
Worked through honestly (the benchmark doc has the arithmetic), caching
narrows but doesn't close the per-query gap: under best-case
assumptions — same payload, byte-identical, calls inside the 5-minute
TTL — the computed-summary approach is still **~106× cheaper**. And
caching is irrelevant above the wall: you cannot cache a prompt that
doesn't fit. For multi-day work the TTL means every session is a cold
cache anyway — which brings us to the twin problem.

## 3. The reconstruction tax

The context window resets harder than people account for: not per
question but per *session*. Close the chat, and tomorrow's session
knows nothing — not the data, not last week's findings, not the three
hypotheses already ruled out. The default remedies are re-pasting
(pay the full data cost again, every morning) or relying on the chat
log (a transcript, unstructured, client-side, and itself too large to
re-feed).

Measured on the benchmark's five-session analytical thread: resuming
by naive reconstruction costs **771,741 tokens per resume** —
**~3.86M tokens across five sessions, ~$11.58** of input spend at
Sonnet pricing, just to keep re-establishing what was already known.
Resuming from structured, durable notes — themes, observations,
evidence with provenance, written to disk as the work happens and
retrieved selectively — costs **2,425 tokens** (**318×** less,
**~$0.04** across the five sessions).

The deeper claim isn't the dollar figure. It's that *analytical memory
is infrastructure, not conversation*. A finding from Tuesday is a
durable artifact with a subject, a timestamp, and supporting evidence
— it should live in storage built for retrieval, not in a transcript
built for scrolling. Sessions then start from *the accumulated state
of the investigation* at a few thousand tokens, and the freed context
goes to the only thing the LLM uniquely contributes: reasoning over
that state.

## 4. A concrete implementation, and a receipt

These arguments are implemented end-to-end in
[**tailor-mcp**](https://github.com/saahasmuthineni/tailor-mcp), an
open-source (AGPL) local MCP server: deterministic Tier-1 computation
over local structured data (CSV directories, MATLAB files, REDCap
exports, live API children), an Obsidian-compatible vault for the
cross-session memory layer, and — because moving computation
server-side also moves the *trust* question server-side — a governance
pipeline on every call: tiered access, consent and cost gates enforced
in the dispatch path rather than the system prompt, and a local SQLite
audit log recording what the model actually touched. That last part is
its own argument (written up as an [adoptable pattern](design/mcp-governance-pattern.md));
the short version is that once the server computes the answers, the
server is also the right place to enforce the rules and keep the
receipts.

The benchmark is the part you shouldn't take on faith:

```bash
git clone https://github.com/saahasmuthineni/tailor-mcp.git
cd tailor-mcp
pip install tiktoken
python benchmarks/token_efficiency.py
```

No credentials, no downloads; deterministic output;
[methodology, assumptions, and the caching counter-factual](../benchmarks/token_efficiency.md)
documented.

## 5. Where this doesn't apply

Honest boundaries, because an economics argument that hides its
domain is marketing:

- **Tiny data.** A 200-row CSV fits in context with room to spare;
  pasting it is fine and simpler. The architecture earns its keep
  when data outgrows the window or the work outlives the session.
- **Data that doesn't reduce.** The pattern needs questions whose
  answers are computable summaries (statistics, trends, group
  comparisons). Reading a contract's clauses or inspecting a raw
  waveform for artifacts *is* the raw data; no summary substitutes.
- **One-shot work.** The 318× session number is a multi-session
  property. Ask one question once, and the vault layer is overhead.
- **Exploration before formalization.** Server-side tools compute
  what they were built to compute. The "eyeball the raw rows and
  notice something weird" step is real analytical work — the tier
  model's consent-gated raw access exists exactly for it, at which
  point you're back in context-window territory, deliberately and
  with a receipt.

The thesis, compressed: **the context window is the most expensive
real estate in the AI stack, and the default architecture spends it
on freight.** Move the computation to the data, move the memory to
disk, and spend the window on reasoning — which was the only thing
you needed the model for in the first place.

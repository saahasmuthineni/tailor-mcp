# Tailor MCP — Launch Strategy

*Written for v9.0.0 public release. Solo founder, no team, no budget.*

---

## The niche question: resolve it first

**Short answer: Lead with the MCP ecosystem. Anchor with health-research credibility. Don't choose.**

Here's why the bifurcation is a false dilemma:

The MCP ecosystem is where early adopters who will actually install something live — GitHub, Hacker News, r/LocalLLaMA, the MCP Discord. These people move fast, file issues, and amplify. They don't need to be health researchers to understand "938× fewer tokens" or "16-subject cohort exceeds the context window." The worked example being biomechanics makes the numbers *specific and believable* rather than vague and marketing-shaped.

The health-research niche is where *sustained, high-value usage* comes from. But researchers move carefully. They need social proof before adopting a solo-maintainer tool. Win the MCP community first, and the health-research credibility makes adoption there much easier.

Going in the other direction — winning health researchers first, hoping that pulls in MCP developers — doesn't work. Researchers don't amplify to technical communities.

The framing throughout: **"Built for health research, applicable to any structured data."** The specificity of the worked example is a strength, not a narrowing. Don't dilute it into generic positioning.

---

## The load-bearing assets

Before sequencing moves, be clear about what actually makes each move land or flop. These are the assets. Everything else is packaging.

**1. The benchmark is independently reproducible in 3 commands.**

```bash
git clone https://github.com/saahasmuthineni/tailor-mcp.git
cd tailor-mcp
pip install tiktoken && python benchmarks/token_efficiency.py
```

No credentials, no external data download, deterministic output. A skeptical HN reader who runs this and sees 938× is now an advocate. If they can't reproduce it, they're an opponent. The benchmark is the single most valuable asset in the launch.

**2. The impossibility argument, not the cost argument.**

"938× cheaper" is a cost argument. It weakens as models get cheaper and context windows grow.

"16-subject cohort of 100Hz force data = 769,311 tokens, which exceeds Claude's 200K context window" is a *structural* argument. You can't throw money at it. The question isn't answerable at all without Tailor or an equivalent architecture. This argument doesn't soften with time.

Every piece of external communication should lead with the impossibility argument, not the cost argument. The cost numbers are supporting evidence.

**3. The prompt-caching counter-factual is already pre-answered.**

The first objection from any sophisticated reader is "but what about prompt caching?" The benchmark document already addresses this rigorously: even under best-case caching assumptions (same analyst, same dataset, calls within 5 minutes), Tailor is still ~106× cheaper. For multi-session research threads across different days — the actual workflow — caching doesn't help at all because the cache TTL is 5 minutes.

This pre-answer signals intellectual honesty and makes the benchmark substantially harder to dismiss. Link to it whenever the numbers come up.

**4. The install path must actually work.**

`uv tool install tailor-mcp && tailor pilot` followed by a question to Claude. If this breaks on a clean machine, the launch fails regardless of how good the distribution is. This is the pre-launch gate.

---

## Pre-launch gate (days 0–2): Fix friction before distribution

Do this before any public post. A broken first experience is worse than a delayed launch.

**Verify the full install path on at least one machine you don't control**, or simulate it (clean user account, no pre-existing `~/.tailor/`, no pre-existing Claude Desktop config). The path is:

1. Install `uv` (documented in the README)
2. `uv tool install tailor-mcp`
3. `tailor pilot` (3-prompt wizard)
4. Quit Claude Desktop, reopen
5. Ask: *"Are men or women losing strength faster in this cohort?"*
6. Claude calls a tool, returns per-group statistics, nothing left the machine

If any step fails silently or with a confusing error, fix it. The README's Quickstart is already clean; the question is whether the actual install experience matches it on a stranger's machine.

**Also run the benchmark script** on a clean clone and verify the numbers match the documented output. If a version bump during v9 prep changed anything, catch it now.

---

## Move 1 (day 1–3): Hacker News Show HN

This is the highest-leverage single move for initial traction on a technical OSS tool with a strong benchmark claim. The MCP community and the research-software community both read HN. Done right, it generates GitHub stars from people who understand what they're starring — not just passive upvotes.

**The angle is everything.** Wrong angle:

> "Show HN: Tailor — an MCP framework for local-first data governance with audit trails and consent gates"

Right angle:

> "Show HN: Local MCP layer that reduces 769K tokens to 820 — 16-subject cohort exceeds context window without it"

The right angle leads with the structural problem that Tailor solves, not the feature set. The first sentence of the comment body needs to be the impossibility argument, not the product description.

**Comment body structure:**

1. The problem in two sentences: At 100Hz, a 16-subject force-plate cohort generates 769K tokens of raw CSV. That's larger than Claude's context window — the question literally can't be answered without chunking or a different architecture.

2. What Tailor does: runs the computation server-side (pure-function processing, deterministic, auditable), returns a 820-token structured summary instead. Results are identical.

3. Reproducible benchmark: `git clone && pip install tiktoken && python benchmarks/token_efficiency.py`. Bit-identical output across machines.

4. What it isn't: not a clinical tool, not cloud-backed, solo maintainer, no external security audit. Be direct about the limitations before someone asks.

5. Any MCP client: confirmed on Cline 3.85.0 in addition to Claude Desktop.

**Timing:** Tuesday or Wednesday, 9–11am PT. Don't post until the install path is verified clean (pre-launch gate above).

**What success looks like:** Not the upvote count. Look for comments that engage with the benchmark methodology, questions about extending it to new data sources, and people who fork the repo. Those are force factors. A post with 50 upvotes and 20 substantive comments is better than 200 upvotes and silence.

**What can go wrong:** Someone on HN runs the benchmark and gets different numbers, or finds a methodological flaw. The Assumptions and Limitations sections in `benchmarks/token_efficiency.md` are there precisely for this — they demonstrate intellectual honesty and pre-answer most objections. Know the document cold before the post goes up.

---

## Move 2 (day 1–3, concurrent): Subreddit-specific posts — three different angles

Don't cross-post the HN text. Each community has a different entry point.

**r/LocalLLaMA** — token economics angle:

> "Why I stopped pasting raw data into Claude and built a local preprocessing layer instead"

Frame it as a practitioner's solution to a problem they've all hit. Lead with: "100Hz sensor data for 16 subjects = 769K tokens, which doesn't fit in the context window." Show the benchmark script. This subreddit cares deeply about token economics and local-first architectures.

**r/ClaudeAI** — MCP-specific angle:

> "Built a local MCP server that preprocesses structured data before Claude sees it — 938× token reduction with a reproducible benchmark"

This community is Claude Desktop users who are actively exploring MCP. The install path (`uv tool install tailor-mcp`) is directly relevant to their workflow.

**r/ObsidianMD** — vault angle (hold this until week 2, after initial feedback):

> "Tailor writes your LLM analytical notes to Obsidian and retrieves them across sessions — cross-session AI memory for Obsidian users"

The VaultLayer writes standard Obsidian-compatible markdown with frontmatter. This is directly relevant to the Obsidian community's "connected notes" philosophy and their interest in AI tooling that respects their data. This angle is underexplored and the community is large and active. Frame it as: "8 structured notes from prior sessions = ~6,400 tokens to bring Claude up to speed. Re-processing raw data every session = ~544,000 tokens. The vault is the structural answer to why your AI keeps forgetting your work."

---

## Move 3 (week 1): The MCP ecosystem directly

**awesome-mcp-servers** — Submit a PR to the canonical MCP server list. This is table stakes (every MCP server does this), but it matters because it's where developers go to browse. The description in the PR matters: don't write "an MCP framework with governance features." Write: "Local preprocessing layer — 938× token reduction on structured data by running computation server-side before the LLM sees raw streams."

**The MCP community Discord / forums** — If there's an active MCP Discord or forum, post there with the benchmark. The audience is people who are building with MCP, which means they understand the architecture immediately and are the most likely to extend it (add their own ChildMCP).

**GitHub — find the right 10 people.** Search for repos that are:
- MCP servers doing data analysis (they've probably hit the context-window problem)
- REDCap + Python pipelines (exact use case)
- Force-plate or EMG analysis in Python (exact domain)

File an issue or comment on one of their issues where the context-window problem is visible. Don't blast everyone — find 5-10 where the fit is obvious and make it personal.

---

## Move 4 (week 2): One technical piece worth sharing

This is the move that compounds over months, not days. A genuine technical argument that gets bookmarked and cited, not a launch post that dies in 24 hours.

**Proposed title:** "The context-window economics problem in LLM-assisted research: why raw data → LLM is architecturally broken at scale"

**Structure:**
1. The problem statement: at 100Hz, cohort-scale analysis exceeds any current context window. This is not a cost problem; it's a structural impossibility. The architecture of "paste data, get answer" breaks at the scale real research happens at.
2. The pattern: compute server-side, pass structured summaries. This is not new (it's basically what every database does before an application layer touches data). What's new is applying it systematically to the LLM interface layer.
3. The cross-session memory problem: why every session starting from scratch is paying a reconstruction tax. The vault as the structural answer.
4. Tailor as a concrete implementation, with the reproducible benchmark.
5. Honest limitations: where the approach doesn't help (tiny datasets, questions that require raw waveform inspection).

**Where to publish:** GitHub Pages under the repo, linked from the README. Or a Substack post if you want email subscribers. The format matters less than the quality of the argument.

**Who shares it:** Not launch-day followers. People who find the architectural argument interesting — research-software engineers, ML engineers who've built their own data pipelines, academics working on reproducibility in LLM-assisted science. These people have slow but durable reach.

---

## Move 5 (week 2–4): Direct outreach to 5–10 health-research RSEs

Not mass outreach. Targeted, personal, short.

**Who to find:** Research software engineers at academic medical centers and mHealth labs who are visibly working on:
- REDCap data pipelines in Python (GitHub, academic papers, conference talks)
- Force-plate or EMG analysis (same sources)
- "LLM for research" projects

They're findable. GitHub search `redcap python analysis`, filter by recent commits. Academic Twitter/X has a visible RSE community. Lab websites list software contributors.

**The message (short):**

> "I built a local MCP layer that lets Claude analyze REDCap/CSV data without it leaving your machine, with a durable audit trail. The token-efficiency benchmark shows 938× reduction on cohort questions — and a 16-subject cohort literally can't fit in the context window raw, so the structured approach isn't optional at that scale. Would you be willing to try it and tell me if it actually fits your workflow? No obligation — I'm looking for honest feedback, not testimonials."

This is not a pitch. It's a request for feedback. Researchers respond to this because it's honest and asks for something specific. The goal is 1–2 people who become genuine users and tell you what's broken. That feedback is worth more than 500 GitHub stars from people who never ran the code.

---

## Move 6 (ongoing): The Obsidian community as a second distribution channel

The VaultLayer is a sleeper hit in the Obsidian world. The community is:
- Large (~1M users, active forum and subreddit)
- Technically sophisticated and opinionated about local-first tools
- Actively exploring AI integrations that preserve data ownership

The angle: "AI analytical memory that writes to your vault and survives session boundaries." This is distinct from Claude Desktop's default behavior (session-scoped, no persistence). The framing resonates with Obsidian's core value proposition of durable, local knowledge.

Post in the Obsidian forum (forum.obsidian.md) with a focused write-up on the vault integration specifically. The MCP ecosystem and the token economics don't need to be the lead — the lead is "your AI analytical notes in Obsidian, automatically."

This move is lower-priority than the MCP ecosystem moves but has a different audience that doesn't overlap, which matters for reach.

---

## What to measure — real force factors vs. vanity metrics

| Signal | What it means |
|--------|--------------|
| Issues filed (especially bugs) | People installed it and ran it |
| PRs adding a new ChildMCP | Framework adoption — highest signal |
| Stars from accounts with repos in the domain | Real users, not passive amplifiers |
| Benchmark script cited in another project's README | Methodology is trusted |
| Forks with substantive commits | Active use |
| Raw HN upvotes | Largely irrelevant |
| Twitter followers | Irrelevant |
| awesome-mcp-servers listing | Table stakes, not traction |

The real measure of week 1 success: 3–5 people file issues. That means they installed it, ran it, and hit something real. Stars without issues mean people bookmarked it and moved on.

---

## What not to do

**Don't launch on Product Hunt.** Wrong audience. PH skews toward SaaS products with UI. A local-first framework with CLI setup and Python extension points will get lost there.

**Don't target enterprise or institutional sales.** AGPL + solo maintainer + no external security audit = wrong package for institutional procurement. This is not a criticism; it's an accurate description of the current state. The clinical exclusion in the README is correct. Don't soften it in outreach.

**Don't try to be generic.** "Works with any structured data!" weakens the benchmark numbers. The specificity of force-plate data at 100Hz is what makes 938× legible and believable. Generic claims are unverifiable; specific benchmarks are not.

**Don't launch before the install path is clean.** If `tailor pilot` fails silently on a stranger's machine, the launch fails.

**Don't post the same text to every platform.** Each community has a different entry point. The same post everywhere signals low effort and gets treated accordingly.

---

## Sequenced checklist

**Days 0–2 (pre-launch)**
- [ ] Verify clean install path on a machine without existing `~/.tailor/` config
- [ ] Run `python benchmarks/token_efficiency.py` from a clean clone, verify numbers match documented output
- [ ] Read `benchmarks/token_efficiency.md` Assumptions and Limitations sections cold — know the objections before they come

**Day 1–3**
- [ ] Hacker News Show HN — numbers-first, impossibility argument leads, benchmark reproducible link prominent
- [ ] r/LocalLLaMA post — practitioner framing
- [ ] r/ClaudeAI post — MCP-specific framing

**Week 1**
- [ ] Submit PR to awesome-mcp-servers
- [ ] Find 5–10 MCP-ecosystem developers who've visibly hit context-window problems; engage specifically
- [ ] Monitor HN/Reddit responses — answer every substantive question within hours

**Week 2**
- [ ] Publish the technical piece on context-window economics
- [ ] r/ObsidianMD post — vault-specific framing
- [ ] Begin targeted outreach to 5–10 health-research RSEs

**Week 2–4**
- [ ] Direct RSE outreach (5–10 people, personal messages)
- [ ] Obsidian forum post
- [ ] Evaluate what's generating real usage signals (issues, forks) and double down on those channels

---

## The honest calibration

Tailor has real technical substance: a reproducible benchmark, a clean architectural argument, a working install path, and a specific worked example. Those are the ingredients for genuine traction, not just launch-day noise.

The risk isn't that the tool isn't good enough. The risk is distribution friction — a broken install experience, a benchmark that can't be reproduced, or a launch framing that doesn't make the impossibility argument clearly enough to make people actually try it.

Fix the friction first. Then distribute. The distribution channels above are ordered by expected force-factor per effort, not by raw audience size. A technically engaged HN thread with 50 commenters who understand what they're reading is worth more than 10,000 Product Hunt upvotes from people who won't install a CLI tool.

# Biosensor MCP and Anthropic Managed Agents — compatibility positioning

> Audience: research-software engineers and PIs evaluating whether
> Biosensor MCP plays nicely with Anthropic's Managed Agents (or
> any hosted-orchestration layer over MCP). Companion to
> [research-framing.md](research-framing.md), which covers the
> threat models the project addresses.

## TL;DR

- **Biosensor MCP is local-first by design.** The default deployment
  shape is "the server runs next to the data; the LLM client talks
  to it; only server-computed summaries leave the machine." Call
  this **Path A**.
- **The same code also works as a governed boundary called by an
  Anthropic Managed Agent over network MCP.** Call this **Path B**.
  No refactor is required to support it; the router's tier model,
  audit log, and PHI-scrub seam still apply on every call.
- **The two paths address different threat models.** Choose by
  what your study cares about, not by which is "newer."
- **Path A is the recommended default for protocol-bound research.**
  Path B is documented as a deliberate compatibility position for
  studies whose IRBs allow summary-level data to leave the
  analyst's machine.

## Two threat models, two deployment shapes

The project is shaped around two distinct things a research group
might be protecting:

| Threat model | What it cares about | Addressed by |
|---|---|---|
| **Raw-data residency** | Per-timestamp biometric streams must not leave the machine. Pasting a CGM trace into a hosted chat is unacceptable. | Tier model + local-first child execution. Tier-1 returns server-computed summaries; Tier-3 is gated and never the default. |
| **Reasoning auditability** | The full sequence of analytical decisions over the data must be reconstructable. *What was asked, what was returned, what was concluded* — every step must leave a trace. | Audit log + `_meta` provenance stamps + VaultLayer evidence blocks. |

Some studies care about both. Some care primarily about
residency (data is the concern; orchestration is not). Some care
primarily about auditability (the data may already be de-identified
or summary-level, but the analytical chain must be auditable).

The two deployment paths emphasise these threat models differently.

## Path A — local-first orchestration (default)

**What it is.** Biosensor MCP runs on a workstation next to the
data. The analyst opens an MCP-speaking client (Claude Desktop,
Claude Code, or any other MCP client) on the same workstation.
The client calls into Biosensor MCP over local MCP. VaultLayer
holds analytical memory across sessions. No call leaves the
machine except (a) the LLM client's own communication with the
model, and (b) any explicit external API calls a child makes to
its upstream source (e.g. Strava OAuth + activity sync).

**What governance survives.**
- Tier model: yes, fully.
- Audit log: yes — every call lands in `audit.db` locally.
- PHI-scrub seam: yes (no-op default; subclassed per institution).
- Consent gate, cost gate, circuit breaker: yes, all enforced
  server-side.
- VaultLayer: yes — markdown source of truth in the vault, SQLite
  index alongside, all on-disk.

**Threat models addressed.** Both raw-data residency and
reasoning auditability are addressed. This is the configuration
the project's research-framing assumes by default.

**Trade-offs.** Orchestration sits inside the LLM client process,
which means the analyst is driving turn by turn. Async overnight
analysis, scheduled runs, and multi-step exploration that doesn't
need a human in the loop are not naturally part of this path.

## Path B — Managed Agent calls Biosensor MCP over network MCP

**What it is.** Anthropic Managed Agents (or any equivalent hosted
orchestration platform) connects to a Biosensor MCP instance over
network MCP. The agent does the orchestration — looping, multi-
step planning, scheduled execution, hosted memory. Each tool call
the agent makes still goes through the local Biosensor MCP
router, which still validates parameters, gates by tier, gates by
consent, gates by cost, scrubs PHI per the deployed scrubber, and
audits the call locally.

**What governance survives.**
- Tier model: yes. The agent cannot bypass it any more than a
  local LLM client can — tier enforcement is server-side in the
  router.
- Audit log: yes — every call the agent makes lands in the local
  `audit.db`. This audit log gains *additional* value in Path B
  because it is the only local trace of what the hosted agent
  did. A reviewer asking "what did the agent actually access?"
  has one durable answer: the audit log.
- PHI-scrub seam: yes. The scrubber runs in the local router
  before any result is returned to the agent.
- Consent gate, cost gate, circuit breaker: yes, all enforced
  server-side.
- VaultLayer: works, but its narrative role is reduced. If the
  agent uses hosted Memory for cross-session continuity, the
  vault becomes one of two sources rather than the canonical
  one.

**Threat models addressed.** Reasoning auditability is preserved
(local audit log). Raw-data residency is preserved for Tier 1
results because they are summaries computed locally and the same
summaries cross the boundary to the agent — by design, no per-
timestamp data leaves the machine at Tier 1. Tier 2 and Tier 3
calls send downsampled or precision-reduced streams to the agent,
which means they leave the machine on those paths just as they
would in Path A. The difference is *destination*: in Path A the
LLM client process is on the same workstation; in Path B it's
on Anthropic infrastructure.

**Trade-offs.**
- Orchestration moves hosted, which is a meaningfully different
  threat-model decision. A study that explicitly cares about
  *what the hosted system reasoned about over your data* should
  not use this path. A study that cares only about raw-data
  residency may find this path acceptable.
- VaultLayer's role weakens — hosted Memory will likely be the
  agent's primary cross-session store. Vault notes become a
  secondary local mirror unless the deployer explicitly drives
  the agent to write back to the vault on every session.
- Multi-analyst attribution is harder: hosted Memory does not
  expose per-analyst evidence blocks the way VaultLayer does.

## Which path to choose

This is a study-level decision, not a technical one. The
framework supports both; the choice depends on what the IRB
protocol governs and what the analyst's workflow needs.

| If your study… | Path |
|---|---|
| Has strict raw-data residency requirements *and* requires a complete audit of analytical reasoning | A |
| Is an academic medical center engagement where IRB protocol amendments are expected to attach the audit log | A |
| Is an exploratory mHealth project on de-identified summary-level data with no per-timestamp residency requirement | B (acceptable) |
| Needs scheduled / overnight analysis (runs without an analyst at the keyboard) | B (or A with a local agent built on the Claude Agent SDK) |
| Wants longitudinal multi-analyst memory tied to specific evidence and corrections | A (VaultLayer remains canonical) |

If you're not sure, default to A. It is the configuration the
project's design centres around.

## What the framework does not do

The project does not enforce the choice between paths — the
deployer makes that decision when they configure the MCP
endpoint and the LLM client. The framework's job is to make sure
that whichever path is chosen, the same governance pipeline
(validate → gate → scrub → audit → execute → stamp) runs on every
call. Whether the call originates from a local Claude Desktop
process or a hosted Managed Agent makes no difference inside the
router.

The project also does not document how to set up Anthropic
Managed Agents themselves — that's Anthropic's documentation
domain. What this doc commits to is: *if you set them up to call
into a Biosensor MCP instance over network MCP, the governance
properties listed under "What governance survives" above will
hold, and the audit log on the local machine will be the canonical
record of what the agent did.*

## Related governance properties

- The VaultLayer dual-output discipline ([ADR 0007](../adr/0007-rendering-layers-policy.md))
  ensures that vault content remains plain-markdown source-of-truth
  whether the consumer is a local Obsidian-equipped analyst, a
  local LLM client reading via `vault_read_note`, or a Managed
  Agent reading the same content over network MCP. The same vault
  material works for all three.
- The audit log's `subject_id` scoping ([ADR 0002](../adr/0002-subject-id-scoping.md))
  applies identically on both paths. A Managed Agent that
  reaches into multiple subjects' data is just as auditable as a
  local analyst doing the same.
- The PHI scrubber seam ([ADR 0003](../adr/0003-phi-scrubber-seam.md))
  fires in the router, before any result leaves the local
  machine, on both paths. A real institutional scrubber subclass
  protects Path B exactly as it protects Path A.

## Filter for evaluating future hosted features

When Anthropic (or any other vendor) ships a new hosted
orchestration feature, the question to ask is: *does this feature
need raw data, or just summaries?*

- Features that consume tool results and reason over them
  (Managed Agents, Skills, Subagents) are compatible with both
  paths. Tier-1 calls return summaries; the hosted feature
  reasons over summaries; raw data stays local.
- Features that ingest raw data (e.g. a future hosted
  visualisation that wants per-timestamp streams) are
  incompatible with the residency threat model. A study that
  cares about residency must not use them on participant data.

This filter is the same one ADR 0001 applies to the audit log
and ADR 0006 applies to vault content. Hosted features are not
inherently in tension with the project; *hosted features that
consume raw participant data* are.

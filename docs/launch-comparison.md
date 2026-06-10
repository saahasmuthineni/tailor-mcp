# What changes when governance is structural

*An honest comparison: Tailor vs. Khoj, Open WebUI, and AnythingLLM.
Draft for the launch-narrative series (per ROADMAP Phase 3 Direction
B). Facts about the other projects checked against their public docs
2026-06-10; re-verify before publishing — all three ship fast.*

---

Three excellent open-source projects come up whenever someone says
"I want AI over my own data, locally": [Khoj](https://khoj.dev/)
([GitHub](https://github.com/khoj-ai/khoj)), [Open WebUI](https://openwebui.com/)
([GitHub](https://github.com/open-webui/open-webui)), and
[AnythingLLM](https://anythingllm.com/)
([MCP docs](https://docs.anythingllm.com/mcp-compatibility/overview)).
Tailor gets compared to them, and the comparison is mostly a category
error — useful to walk through precisely *because* it's a category
error, since the difference is the point.

## What those three are

All three are **applications**: they own the chat surface, and they
answer questions over your documents by retrieval.

- **Khoj** is an AI second brain — self-hostable (AGPL-3.0), indexes
  your notes and documents (markdown, org-mode, PDF, Word, Notion),
  supports local LLMs, and adds agents, scheduled automations, and
  web search. If you want a personal research assistant over your
  files, it's a strong choice.
- **Open WebUI** is a self-hosted AI interface with a native RAG
  engine, knowledge bases, multi-user role-based access control, and
  a large extension ecosystem. MCP tools connect through its tool
  layer (via the mcpo MCP-to-OpenAPI proxy). If a small team wants a
  shared, governed chat deployment, this is the most mature option.
- **AnythingLLM** is a self-hosted RAG application with workspaces,
  agent capabilities, and MCP tool support (v1.8.0+). If you want
  drag-a-folder-in, chat-with-your-documents, it's probably the
  fastest path.

These are good tools. If your problem is "chat with my documents,"
use one of them — Tailor will not do that job better, and mostly
will not do it at all.

## What Tailor is

Tailor is **middleware, not an application**. It has no chat UI and
never will — it's an MCP server that sits between *any* MCP client
(Claude Desktop, Cline, whatever ships next) and your structured
data, and it differs from the three above on three axes that sound
subtle and are not.

### 1. Computation, not retrieval

RAG retrieves *text chunks* that are semantically similar to your
question and pastes them into context. That's the right architecture
for prose. It is the wrong architecture for structured data: if you
ask a RAG system "which region's stores are declining fastest?" over
twelve CSV files, the honest answers available to it are (a) paste
the rows into context and hope they fit, or (b) retrieve chunks that
*mention* declining revenue. Neither computes anything.

Tailor runs the computation server-side — deterministic pure
functions over the actual data — and returns the answer (a
group-by summary, a trend, a fatigue index) instead of the data.
The result is identical on every run and every machine, carries a
provenance stamp (version, tool, timestamp, tier, token counts),
and is typically two to three orders of magnitude smaller than the
rows it summarizes. For cohort-scale questions the raw data
literally does not fit in any context window; the computed answer
does ([measured benchmark](../benchmarks/token_efficiency.md)).

### 2. Per-call gates, not per-user roles

Open WebUI's RBAC governs *which humans* can use which models and
documents. That's real governance — at the user boundary. Tailor
governs at the **call boundary**: every tool declares an access tier,
and the dispatch pipeline enforces, on every single call, parameter
validation → circuit breaker → consent gate (tier 2+) → cost gate
(tier 3) → scrubbing seam → audit write. The model cannot escalate
from "computed summary" to "raw stream" without a structured refusal
going back, a human approving, and the whole exchange landing in the
log.

The distinction matters the moment the caller is an LLM rather than
a person. A human with read access reads what they need; a model
with read access reads whatever maximizes its next token. "The model
only gets the resolution this question needs, and escalation requires
explicit human approval *enforced server-side*" is a property none
of the application-shaped tools claim — it isn't their problem. It
is Tailor's entire problem.

### 3. An audit log, not a chat history

All three applications retain conversations. A conversation log
tells you what was *said*. Tailor's audit log is a local SQLite
database recording what was *done*: every call — tool, tier,
parameters, outcome, latency, token estimate, and optionally *whose*
data it touched (`entity_id`) — including the refused and failed
calls, which are exactly the rows a reviewer cares about and exactly
the rows a chat transcript doesn't show. "What did the AI access
about participant S004 in March?" is a one-line SQL query, not an
afternoon of scrolling.

## The same fact from both sides

Pick the tool by which sentence describes your problem:

- *"I want to chat with my notes and documents, locally."* → Khoj,
  Open WebUI, or AnythingLLM. Genuinely. Tailor doesn't have a UI,
  doesn't do embeddings, and treats prose as someone else's job.
- *"I need an AI to work with data I'm accountable for — and I need
  to bound what it can touch and prove what it did."* → That's the
  governance-middleware problem. It's what Tailor is, end to end:
  the gates are in the dispatch path, not the system prompt; the
  evidence is in a database, not a transcript.

They also compose rather than compete: an MCP-capable client or
application can sit in front of Tailor, with Tailor providing the
governed access to the structured sources underneath.

## The general claim

The structural-vs-advisory distinction is the load-bearing one, and
it's bigger than any product comparison. A system prompt that says
"ask before reading raw records" is advice to a model. A consent
gate in the server's dispatch path is physics: it behaves identically
for every client, every model generation, every jailbreak. As more
of the world's private data gets MCP endpoints, the question "is your
AI's restraint advisory or structural?" becomes the first question
that matters. Tailor's bet — documented as an adoptable pattern in
[A governance pattern for MCP servers](design/mcp-governance-pattern.md),
whether or not you use Tailor itself — is that the answer has to be
structural, and the place to enforce it is the server.

# ADR 0043: The inspector is an inspector, not an application

- **Status:** Accepted
- **Date:** 2026-06-10
- **Amends (in part):**
  - [ADR 0040 (Bounded setup-time conductor surface)](0040-bounded-setup-time-conductor-surface.md) — the v8.0.0 six-command CLI surface (`serve / pilot / setup / redcap / status / uninstall`) grows to seven with `tailor inspect`. This is a deliberate, documented amendment of that surface contract; the operator-managed-retention clause shape ADR 0040 § Amendment introduced is reused for `--export` output.
- **Related:**
  - [ADR 0001 (Audit log is the backbone)](0001-audit-log-as-backbone.md) — the inspector renders the backbone; it is the visible face of the trust root ADR 0001 codified
  - [ADR 0002 (`entity_id` scoping)](0002-subject-id-scoping.md) — `entity_id` is shown by design; the inspector is the operator/IRB audience the column exists for
  - [ADR 0003 (PHI-scrubber seam)](0003-phi-scrubber-seam.md) — the page renders the no-op-scrubber warning, mirroring `_meta.scrubber_warning`
  - [ADR 0009 (Vault subject-keying)](0009-vault-subject-keying.md) — entity-scoped audit rows are the inspector's filter dimension
  - [ADR 0012 (Framework-tier PHI-scrubber bypass)](0012-vault-phi-scrubber-bypass.md) — the inspector does **not** amend this; it is outside the router pipeline entirely
  - [ADR 0022 (Local-LLM guardian)](0022-local-llm-guardian.md) — the read-only foil to the conductor-mode action surface ADR 0022 deferred
  - [ADR 0033 (Complete the Tailor metaphor — workshop side)](0033-complete-tailor-metaphor-workshop-side.md) — the inspector renders the Ledger as headline and the Wardrobe only as index counts
  - [ADR 0039 (Audit log queryable under a column allowlist)](0039-audit-log-is-llm-queryable-under-column-allowlist.md) — the model-mediated query channel this ADR's channel is deliberately independent of
  - [`docs/design/read-only-inspector-spec.md`](../design/read-only-inspector-spec.md) — the implementation brief this ADR records the decision content of

## Context

ADR 0001 made the audit log the framework's trust root: every tool call
lands in `audit_log` with timestamp, domain, tool, tier, parameters,
token estimate, outcome, latency, optional error, and optional
`entity_id`. ADR 0039 then made that log reachable from inside the
LLM transcript — `audit_query` surfaces structured columns to the
hosted model under a column allowlist, so a researcher can ask "what
just happened?" without dropping to a shell. Both decisions strengthen
the trust story, and both share a structural property: the consent
gates, tier refusals, and cost gates are experienced as *the LLM's
narration of them*. The enforcement is server-side and real, but the
visibility is mediated by the entity whose behaviour the log records.
The watcher is reported on by the watched.

That mediation is acceptable for the day-to-day "what happened?"
question — ADR 0039 is the right shape for an LLM-callable convenience.
It is not acceptable as the *only* channel for the question that
matters to an IRB reviewer or a skeptical operator: "show me what the
framework actually did, through a path the model does not control." A
model can deflect ("no need to check that"), narrate over a refusal it
did not actually hit, or simply not surface the row. The trust claim
ADR 0001 anchors is structurally weaker if the only way to read the
ledger is to ask the thing being audited.

The remaining channels today are shell (`sqlite3 audit.db`) and
`tailor status`. Both are operator surfaces that assume terminal
fluency. There is no rendered, human-legible, model-independent view of
the ledger — nothing an IRB-adjacent reviewer can open and read, no
artifact a launch demo can screenshot. This is ROADMAP Phase 4
Direction F (first bullet), pulled forward as a trust-visibility and
launch asset.

The risk in building any such surface is scope creep. A page that
renders the audit log is one keystroke away from a page that *edits*
consent state, purges caches, or toggles config — and the moment it
grows a control, it becomes a second action surface on the framework's
own state, re-opening exactly the conductor-mode question ADR 0022
deliberately deferred and exposing a new write path the security
pipeline does not mediate. The question this ADR answers: *what is the
hard boundary that keeps an audit-visibility surface from becoming a
second control plane, and how does its invocation channel stay
independent of the model it exists to verify?*

## Decision

Tailor ships **`tailor inspect`** — a read-only, localhost-only,
no-controls, stdlib-only HTML visibility surface over `audit.db` and
the `vault.db` index, running as a standalone process that never
touches the router or the MCP surface. It is an **inspector, not an
application**: it renders what the framework did and offers no way to
change it.

- **It never writes.** SQLite connections are opened read-only via the
  URI form `sqlite3.connect("file:<path>?mode=ro", uri=True)`. There
  are no POST/PUT/DELETE routes; any non-GET method returns 405. A
  test proves a write attempt through the inspector's connection
  raises, and a grep-class test asserts no bare `sqlite3.connect(`
  without `mode=ro` exists in `src/tailor/inspector/`.
- **It never binds beyond localhost.** The listener address is
  hard-coded `127.0.0.1`, asserted in code and in a test. There is no
  flag to widen it. Networked or multi-user inspection is ROADMAP
  Phase 5C, behind a separate ADR.
- **It never grows controls.** No consent toggles, no config editing,
  no purge buttons, no chat. A reviewer who wants to *act* uses the
  existing surfaces (Claude Desktop chat, the `tailor` CLI). The footer
  says so in plain language.
- **It adds no dependencies.** Python stdlib only (`http.server`,
  `sqlite3`, `html`) — inline styles, auto-refresh via
  `<meta http-equiv="refresh">`, no JavaScript, no build step, no CDN.
  The base install stays three deps (`mcp`, `requests`, `orjson`). New
  source lives at `src/tailor/inspector/` (`queries.py` pure, `render.py`
  pure, `server.py` plumbing) under a ~1,000-line ceiling.
- **It is a standalone process, not part of `tailor serve`.** The
  inspector reads on-disk state and serves one HTML page (`/`, plus a
  `/health` probe). It does not embed into or communicate with the
  running MCP server, which speaks JSON-RPC over stdio and must not
  grow an HTTP listener. Connections are short-lived per request; on a
  WAL database held by a running server it reads without taking a lock
  that blocks the writer, honoring the Windows file-lock discipline the
  `router.close()` precedent already documents.

### The invocation ladder — decided once, on paper

Invocation is a three-stage ladder. v1 builds Stage 1 only; Stages 2
and 3 are designed now and recorded here with named build triggers so
they are not re-litigated per release. The sequencing is deliberate
(boss-ratified 2026-06-11): the ambient stages' costs are front-loaded
and land on stranger machines (OS firewall prompts on listener spawn,
dead-bookmark UX when the server is not running, cross-OS shortcut
plumbing — the v6.10.x patch-quartet bug class), while their benefits
accrue only once real recipients exist.

- **Stage 1 — summoned (BUILD THIS, v1).** The CLI verb `tailor inspect`
  serves on `http://127.0.0.1:8765` and opens a browser. Flags:
  `--port`, `--no-browser`, and `--export out.html` (render once to a
  static file and exit — the CI-friendly and screenshot path).
- **Stage 2 — ambient, opt-in (DESIGN ONLY).** `tailor serve` would
  auto-spawn the inspector subprocess when an `"inspector": true` key is
  present in `user_config.json`; `tailor pilot` would gain one yes/no
  prompt and, on yes, write a desktop bookmark ("What is Tailor doing?")
  to a per-install-tokened URL. The recipient reaches the receipt by
  double-click — no terminal, no LLM mediation. **Build trigger:** first
  real recipient install, or first IRB-adjacent reviewer who needs the
  page. The engineering costs to absorb when the trigger fires are
  enumerated in the spec § 2 (firewall prompts at spawn, dead-bookmark
  when Claude Desktop is closed, three OS-specific shortcut formats,
  token-in-URL exposure via browser history, browser-cache retention of
  audit metadata — the last needs an ADR 0040-style operator-managed-
  retention clause). The config key, the pilot prompt, and any shortcut
  writer are **not** built in v1.
- **Stage 3 — ambient, default-on (DEFERRED — identity decision).**
  Every install runs the receipts page. Strongest trust story; changes
  the framework's "no services" footprint posture. **Build trigger:**
  demonstrated Stage-2 usage plus an explicit boss decision; warrants
  its own ADR section when it lands.

### The channel must not be mediated by the model it verifies

The inspector is the *independent verification channel for the model's
behaviour*. Its availability must not be controlled by the entity being
verified. There is therefore **no MCP tool** that opens or spawns the
inspector — no `tailor_open_inspector`, at any stage. A model that
owned the door could deflect, fail to spawn it, or narrate over it.
Claude may freely *mention* the URL as docs-level knowledge; it does
not get a tool that controls the door. This is the deliberate contrast
with ADR 0039: `audit_query` is the model-mediated query path, correct
under a column allowlist for in-transcript convenience; the inspector
is the non-model-mediated independent channel for the same ledger, and
the two are different surfaces with different invariants precisely
because one is reachable by the audited entity and the other is not.

### Raw `params` and `error` render here — a named carve-out from ADR 0039

ADR 0039 restricted the LLM-callable `audit_query` surface to a
structured column allowlist — never raw `params` content, never raw
`error` strings (collapsed to `has_error`) — because that channel
re-egresses ledger rows *into the hosted-LLM transcript*, and the
framework `DataScrubber` default is no-op (ADR 0003), so trusting a
re-scrub at surface time would be wishful thinking. ADR 0039's own
text names the fallback for full content: *"researchers needing full
error content drop to `tailor status` or `sqlite3 audit.db`"* — the
operator-shell path retains full access by design.

The inspector renders `params` and `error` (collapsed behind
`<details>`, home-redacted) **because it is that operator-shell path,
rendered**. Its audience is the operator/IRB reviewer sitting at the
machine that owns the disk — the same person ADR 0039 points at
`sqlite3 audit.db` — reached over localhost only, never a hosted-LLM
transcript, never the network. This is a deliberate, named carve-out
from the allowlist invariant, not a silent widening: the allowlist
governs *model-transcript egress*; the inspector is the
*non-model-mediated operator channel* for the identical rows. What
crosses neither channel is unchanged: Tier-2/3 payloads and vault note
bodies are out of scope here exactly as they are out of scope there.
The residual risk — `params` are LLM-authored text and may carry
subject identifiers a child wrote — is bounded by the same fact that
bounds the `sqlite3` path: the reader already holds the database file.
Home-redaction and HTML-escaping (below) close the path-leak and XSS
vectors the rendering itself introduces. The carve-out therefore
carries a named **deployment assumption: the person opening the page
is the data custodian** (the operator who owns the disk). Home-
redaction collapses only the current operator's `Path.home()`;
foreign-user paths or identifiers a child wrote into `params` render
verbatim, which is acceptable exactly and only under that assumption
— a served localhost page cannot leave the custodian's machine, and
the `--export` artifact that *can* leave it is named as its own
operator-managed retention category (see Consequences and
`docs/design/research-framing.md` § sixth retention category).

### This is outside the pipeline — it does not amend ADR 0012

The inspector is **not** a framework-tier layer. It never registers
with the router, never appears in `tools/list`, and bypasses nothing —
because it is outside the security pipeline entirely. ADR 0012 governs
which *registered framework-tier layers* (`VaultLayer`, `LocalLLMLayer`,
`SetupHelpLayer`, `AuditQueryLayer`, `SetupLayer`) skip the
biosensor-tier gates and under what invariant. The inspector adds no
such layer and therefore does not amend ADR 0012. A reviewer auditing
the framework-tier-bypass roster will not find the inspector there, and
that absence is correct: a separate read-only process reading on-disk
state shares none of the dispatch machinery ADR 0012 reasons about.

### Reversal conditions

The read-only / localhost-only / no-controls boundary holds until one
of two named signals arrives:

1. **First institutional adopter requires authenticated multi-user
   inspection.** A real deployment that needs the inspector reachable
   beyond localhost, with authentication and multiple reviewer
   identities, triggers Phase 5C work under a separate ADR. This is not
   a relaxation of the v1 boundary; it is a different surface with its
   own auth, TLS, and network threat model.
2. **Evidence the read-only constraint blocks a load-bearing IRB
   workflow.** If a real inquiry surfaces a question the read-only,
   derived-from-audit view cannot answer and a reviewer states the gap
   is material, the boundary is revisited under a superseding ADR. The
   bar is a demonstrated load-bearing workflow, not a preference for
   controls.

The rejected MCP-spawner tool carries its own narrower reversal: a real
recipient asks Claude to show the receipt and hits a dead end the
Stage-2 bookmark does not cover. The live-consent-via-IPC option
(rejected below) reverses if an IRB reviewer states the derived
timeline is insufficient in a real inquiry.

## Consequences

### Positive

- The IRB-facing trust claim gains a model-independent channel. ADR
  0001's "every action is recorded" and ADR 0039's "queryable from the
  transcript" are now joined by "renderable through a page the model
  does not control." A reviewer reads the ledger without trusting, or
  even talking to, the entity the ledger audits.
- The headline section renders gate activity — refusal classes
  (`CONSENT_BLOCKED`, `COST_GATE_TRIGGERED`, `CIRCUIT_OPEN`,
  `PARAM_INVALID`) as distinct badges against `SUCCESS` and `ERROR`,
  each with one plain-language sentence on what the gate does. The
  enforcement that was previously visible only as LLM narration becomes
  a legible artifact — the screenshot a launch demo can show.
- The page renders the no-op-scrubber warning. When the default
  `DataScrubber` id (`noop`) appears in the window, a prominent badge
  mirrors the `_meta.scrubber_warning` language from ADR 0003: no
  institutional scrubbing policy is configured. The scrubber posture is
  surfaced where an operator will actually see it, not only in a
  per-call `_meta` block they may never read.
- `entity_id` values are shown deliberately. The inspector is the
  operator/IRB surface, and `entity_id` scoping (ADR 0002 / ADR 0009)
  exists for exactly this audience. Showing the scoping dimension is
  the feature, not a leak.
- The MCP surface is untouched. The inspector adds no tool, no
  framework-tier layer, no router edit. `mcp-protocol-auditor` does not
  trigger on this work — if implementation finds itself editing
  `framework/router.py`, the design has gone wrong.

### Negative

- The CLI surface contract grows from six commands to seven, breaking
  the clean six-verb story ADR 0040 established at v8.0.0. This is a
  deliberate amendment, not drift: the `--help` text, the CLAUDE.md
  "File Structure" and "Running and Testing" sections, and the CLI
  smoke expectations in `ci-gate-runner`'s scope (which asserts
  discoverable commands) all update to seven. The cost is a slightly
  larger operator surface; the benefit is the independent visibility
  channel.
- The consent timeline is **derived from audit events, not live state**.
  Live consent lives in `ConsentGate`'s in-memory dict inside the
  running `tailor serve` process, which a separate process cannot read.
  The inspector renders approve/revoke audit rows, labeled exactly:
  *"derived from audit events — live state lives in the running
  server's session."* It must not be presented as authoritative current
  state. The same caveat applies to token totals, rendered as sums of
  `token_estimate` over the window and labeled as estimates.
- The browser is a new egress surface. Every rendered string that may
  carry a filesystem path passes through a `_redact_home()` equivalent
  (collapsing `Path.home()` to `~`, the HIPAA Safe Harbor rationale of
  the v6.10.2 / v8.0.0 precedents); everything rendered from the DB is
  `html.escape`d (audit `params` are LLM-authored, attacker-influenceable
  text — the inspector must not become an XSS vector); the response
  sets `Content-Security-Policy: default-src 'none'; style-src
  'unsafe-inline'` and `X-Content-Type-Options: nosniff`.
  `phi-irb-risk-reviewer` will correctly examine this surface before
  merge.
- `--export` output lands on disk and is **operator-managed retention**.
  The exported HTML carries audit metadata; it is not purged by any
  consent-revocation path. The export command prints a one-line note to
  that effect, reusing the retention-contract clause shape ADR 0040 §
  Amendment introduced for SetupLayer-written configuration.

### Neutral

- The inspector renders the **Ledger** (audit) as the headline and the
  **Wardrobe** (vault) only as index counts — note counts by type,
  themes by status, most recent `written_at`, titles and slugs only, no
  note bodies in v1. The Ledger/Wardrobe asymmetry is by design per ADR
  0033: the inspector exists to show *that* data moved and under which
  gate, not the analyst's authored content. Rendering vault bodies or
  raw Tier-2/3 payloads is explicitly out of scope.
- Missing databases are a normal state, not an error. With no
  `audit.db` yet, the page renders an honest empty state ("no audit
  database yet — has `tailor serve` run?"). Legacy pre-v9 databases
  still carrying a `subject_id` column (if `AuditLog.__init__`'s rename
  has not run) are detected via `PRAGMA table_info` and aliased rather
  than crashing.
- A `mode=ro` connection cannot replay an un-checkpointed `-wal`
  sidecar, and on Windows a reader can transiently hit
  `database is locked` while the server checkpoints. A silently stale
  or erroring page would undercut the trust claim more than no page
  would — so the inspector detects a non-empty `-wal` sidecar and
  renders a visible caveat ("recent activity may not yet be reflected
  — the server is mid-write or was not cleanly shut down"), and any
  SQLite lock/operational error renders as an honest per-section error
  state rather than a crash. Connections are short-lived per request
  and never held across requests.
- `recipient-install-validator` is file-gated on `__main__.py`, which
  this work touches. The gate is flagged in the PR per the
  gate-composition convention even where the run is skipped under the
  v6.11.x falsification precedent. `cue-card-rehearsal-auditor` does not
  trigger — no `ToolDefinition` changes.

## Alternatives considered

**An MCP spawner tool (`tailor_open_inspector`).** Considered and
rejected for every stage of the ladder. A tool the hosted LLM calls to
open or spawn the inspector would put the independent verification
channel under the control of the entity it verifies — a model can
deflect ("no need to check"), fail to spawn it, or narrate over it. The
whole value of the inspector is that the door does not answer to the
model. Claude may mention the URL as docs-level knowledge; it gets no
tool that controls the door. **Reversal condition:** a real recipient
asks Claude to show the receipt and hits a dead end the Stage-2
bookmark does not cover.

**An HTTP listener embedded in `tailor serve`.** Render the page from
inside the running MCP server, reusing its already-open database
handles and live in-memory consent state. Rejected. The `tailor serve`
process speaks MCP over stdio and must not grow a network listener — a
second protocol surface on the security-critical process, with its own
port-binding, firewall-prompt, and shutdown-ordering failure modes,
bolted onto the one process whose job is to be a clean stdio MCP
server. The standalone-process shape keeps the listener entirely
outside the security pipeline, which is also what lets this ADR avoid
amending ADR 0012 at all. The convenience the embedded shape would buy
(live consent state, shared handles) is not worth coupling the receipt
page to the server's lifecycle and threat model.

**Live consent state via IPC with `tailor serve`.** Have the inspector
talk to the running server over an IPC channel to read `ConsentGate`'s
in-memory dict and present authoritative live state rather than a
derived timeline. Rejected for v1. It couples the inspector to the
server's lifecycle and opens an IPC surface for what is, in practice, a
label upgrade ("live" vs "derived from audit events"). The
derived-from-audit timeline answers the IRB question — *when was
consent granted and revoked, on the record* — and is labeled honestly
about what it is. **Reversal condition:** an IRB reviewer states in a
real inquiry that the derived timeline is insufficient.

**Do nothing — keep the ledger shell-only plus `audit_query`.**
Rejected. The status quo gives the operator `sqlite3 audit.db` and
`tailor status` (terminal-fluent surfaces) and the LLM `audit_query`
(model-mediated, per ADR 0039). Neither is a rendered, model-independent
view a non-terminal IRB-adjacent reviewer can open and read, and
neither is a screenshot a launch demo can show. The gap is exactly the
trust-visibility surface ADR 0001's backbone earns and ADR 0039's
model-mediated channel structurally cannot fill, because the value here
is *independence from the model*, not convenience inside the
transcript.

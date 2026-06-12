# Spec — `tailor inspect`: the read-only inspector

*Implementation brief, written 2026-06-11 to be dropped into a fresh
Claude Code session on this repo. Everything below was verified
against the codebase at v9.0.2 (branch
`claude/fable-repo-monetization-dhngdk`); file:line references are to
that state. Read CLAUDE.md first — all boss-architect protocols and
the specialist-gate culture apply to this work.*

---

## 1. Why this exists (read before coding)

Tailor's load-bearing trust feature — the audit log — is currently
consumed via a `sqlite3` one-liner. The consent gates, tier refusals,
and cost gates are experienced only as *the LLM's narration of them*:
the enforcement is structural, but the visibility is advisory, and
the watcher is reported on by the watched. The inspector closes that
gap: **an independent, read-only, localhost page that renders what
the framework actually did, through a channel the model does not
mediate.**

This is ROADMAP Phase 4 Direction F (first bullet), pulled forward
deliberately as a trust-visibility and launch asset. The
data-quality surface (Direction F second bullet), the vault graph,
and anything interactive are **not** in this scope.

### The hard boundary (non-negotiable)

The inspector is an **inspector, not an application**. It:

- **Never writes.** Not to any database, not to any config, not to
  the vault. SQLite connections are opened read-only (URI
  `file:...?mode=ro`). There are no POST/PUT/DELETE routes; any
  non-GET method returns 405.
- **Never binds beyond localhost.** Hard-coded `127.0.0.1`. No flag
  to widen it. Multi-user/networked deployment is ROADMAP Phase 5C,
  not this.
- **Never grows controls.** No consent toggles, no config editing,
  no purge buttons, no chat. If a reviewer wants to *act*, they use
  the existing surfaces (Claude Desktop chat, CLI).
- **Adds no dependencies.** Python stdlib only (`http.server`,
  `sqlite3`, `html`). No React, no build step, no CDN-loaded JS or
  CSS — inline styles, and auto-refresh via
  `<meta http-equiv="refresh" content="5">` rather than JavaScript.
  The base install stays three deps (`mcp`, `requests`, `orjson`).

If the implementation cannot stay within roughly **~800–1,000 lines
of new source** (excluding tests), the scope has drifted; stop and
re-read this section.

An ADR is part of the deliverable (see § 8): "inspector, not
application," with reversal conditions, drafted via `adr-weigher` →
`adr-drafter` per repo convention.

## 2. Process model and invocation — the ladder

The inspector engine is a standalone process that reads on-disk state
and serves one HTML page. It does not embed into or communicate with
the running `tailor serve` process (which speaks MCP over stdio and
must not grow an HTTP listener).

Invocation is designed as a three-stage **ladder**. v1 builds Stage 1
only; Stages 2–3 are designed now, recorded in the ADR with named
triggers, and NOT built until their triggers fire. This sequencing is
deliberate (boss-ratified 2026-06-11): the ambient stages' costs are
front-loaded and land on stranger machines (OS firewall prompts on
listener spawn, dead-bookmark UX when the server isn't running,
cross-OS desktop-shortcut plumbing — the v6.10.x patch-quartet bug
class), while their benefits only accrue once real recipients exist.

### Stage 1 — summoned (BUILD THIS, v1)

New CLI verb: **`tailor inspect`**.

```
tailor inspect                  # serve on http://127.0.0.1:8765, open browser
tailor inspect --port 9000      # alternate port
tailor inspect --no-browser     # don't auto-open
tailor inspect --export out.html  # render once to a static file, exit
                                  # (CI-friendly; also the screenshot path)
tailor inspect --data-dir DIR   # inspect a non-default data directory
                                # (added v9.2.0; flag > $TAILOR_DATA_DIR)
```

### Stage 2 — ambient, opt-in (DESIGN ONLY — record in ADR, do not build)

`tailor serve` auto-spawns the inspector subprocess when an
`"inspector": true` key is present in `user_config.json`;
`tailor pilot` gains one yes/no prompt offering it and, on yes,
writes a desktop bookmark ("What is Tailor doing?" →
`http://127.0.0.1:8765/?k=<per-install token>`). The model is never
the door — a recipient reaches the receipt by double-click, with no
terminal and no LLM mediation. **Trigger to build:** first real
recipient install, or first IRB-adjacent reviewer who needs the page.
Known costs to engineer around when the trigger fires: OS firewall
prompts at spawn, dead-bookmark when Claude Desktop is closed,
three OS-specific shortcut formats, token-in-URL exposure via
browser history, browser-cache retention of audit metadata
(needs an ADR 0040-style operator-managed-retention clause).

### Stage 3 — ambient, default-on (DEFERRED — identity decision)

Every install runs the receipts page. Strongest trust story; changes
the "no services" footprint posture. **Trigger:** demonstrated Stage-2
usage plus an explicit boss decision; warrants its own ADR section.

### Rejected: an MCP spawner tool (`tailor_open_inspector`)

Considered and rejected for any stage: the inspector is the
*independent verification channel for the model's behavior*, and its
availability should not be mediated by the entity being verified — a
model can deflect ("no need to check"), fail to spawn it, or narrate
over it. Claude may freely *mention* the URL (docs-level knowledge);
it does not get a tool that controls the door. **Reversal
condition:** a real recipient asks Claude to show the receipt and
hits a dead end that the Stage-2 bookmark does not cover.

### Stage-1 mechanics

- Data locations come from the existing config module
  (`src/tailor/config.py` / `TAILOR_CONFIG_DIR`, `TAILOR_DATA_DIR`
  env vars — same resolution `__main__.py` uses; audit DB is
  `DATA_DIR / "audit.db"`, see `__main__.py:552`). Since v9.2.0 the
  `--data-dir DIR` flag overrides that resolution per invocation
  (precedence: flag > `$TAILOR_DATA_DIR` > `~/.tailor/data`); an
  explicitly named directory that does not exist is rejected at the
  CLI boundary (argparse error, exit 2) rather than rendered as the
  honest-empty page — the empty state remains the contract only for
  directories that exist.
- Missing databases are a normal state, not an error: render the
  page with an honest "no audit database yet — has `tailor serve`
  run?" empty state.
- WAL note: `audit.db` uses WAL mode. Read-only URI connections can
  read a WAL database while the server holds it; do NOT take any
  lock that blocks the writer. Use short-lived connections per
  request. On Windows, never hold a connection across requests
  (file-lock discipline per the `router.close()` precedent in
  CLAUDE.md § Implementation notes).
- **CLI surface contract:** this changes the v8.0.0 six-command
  surface (`serve / pilot / setup / redcap / status / uninstall`) to
  seven. That is a deliberate, ADR-documented change. Update:
  CLAUDE.md §"File Structure" + §"Running and Testing", the
  `--help` text, and the CLI smoke expectations in
  `ci-gate-runner`'s scope (it asserts discoverable commands).

## 3. Data sources — ground truth (verified)

The inspector reads **three** on-disk artifacts, all read-only:

### 3a. `audit.db` → table `audit_log` (`framework/audit.py:136-149`)

Columns (post-v9.0.2, after in-place migrations):

```
id, timestamp (TEXT, UTC ISO), domain, tool_name, tier (INTEGER),
params (TEXT, JSON, truncated by the audit layer), token_estimate,
outcome (TEXT), duration_ms, error, entity_id, scrubber_id,
child_scrubber_id, source_metadata_fingerprint,
oracle_model_id, oracle_model_version_hash, oracle_tier,
oracle_confidence, oracle_prompt_hash, oracle_latency_ms,
oracle_substrate_count, oracle_next_best_calls_count,
oracle_unresolved_intent_count
```

Handle legacy DBs gracefully: a pre-v9 file may still carry
`subject_id` if `AuditLog.__init__` (which performs the rename) has
not run since upgrade — the inspector must not crash on it; detect
via `PRAGMA table_info` and alias.

Outcome vocabulary actually emitted by the router (verified by grep;
treat as open-ended, render unknown values as-is): `SUCCESS`,
`ERROR`, `PARAM_INVALID`, `CONSENT_BLOCKED`, `COST_GATE_TRIGGERED`,
`COST_ESTIMATE_ERROR`, `CIRCUIT_OPEN`, `PURGE_CACHE`, `PURGE_FAILED`,
`SETUP_CONFIG_WRITE`, `REATTEST`, `ATTEST_INITIAL`, plus `*_INTERNAL`
variants of the above for `dispatch_internal()` calls.

### 3b. `vault.db` → `VaultStorage` index (`framework/vault/storage.py:36-85`)

Tables: `vault_notes` (filename, domain, note_type, date,
frontmatter_json, written_at, entity_id, …), `vault_themes` (slug,
status, opened, last_updated, …), `vault_links`, `vault_tags`.
Counts and titles only — **no note bodies in v1** (see § 5
Privacy).

### 3c. What is NOT available, and how to be honest about it

- **Live consent state** lives in `ConsentGate`'s in-memory dict
  inside the `tailor serve` process — a separate process cannot read
  it. The inspector instead renders a **consent event timeline**
  derived from `approve_consent_<domain>` / `revoke_consent_<domain>`
  audit rows (the router audits these; see `router.py:587-589,1937`),
  labeled exactly: *"derived from audit events — live state lives in
  the running server's session."* Do not present it as authoritative
  current state.
- **Session token spend** (`TokenLedger`, `framework/cost.py:70`) is
  also in-memory. Render token totals as *sums of `token_estimate`
  over audit rows* for a time window, labeled as estimates.

## 4. The page (single route `/`, plus `/health`)

One server-rendered HTML page, sections top to bottom. Query params:
`?limit=` (default 50, max 500), `?domain=`, `?outcome=`,
`?entity_id=`, `?since=` (ISO date). All filtering in SQL with bound
parameters — never string-interpolate query params into SQL.

1. **Header** — package version (`tailor.__version__`), data dir
   (home-redacted, see § 5), per-DB file size + mtime, row count,
   and a visible **READ-ONLY** badge. Auto-refresh meta tag.
2. **Gate activity summary** (the headline section — this is the
   screenshot) — for the selected window: count of calls by outcome,
   rendered as labeled badges with distinct colors for refusal
   classes (`CONSENT_BLOCKED`, `COST_GATE_TRIGGERED`,
   `CIRCUIT_OPEN`, `PARAM_INVALID`) vs `SUCCESS` vs `ERROR`. One
   sentence of plain language under each refusal class explaining
   what the gate does (reuse phrasing from
   `docs/design/mcp-governance-pattern.md`).
3. **Recent calls table** — id, timestamp, domain, tool, tier,
   outcome badge, duration_ms, token_estimate, entity_id,
   scrubber_id. `params` and `error` collapsed behind
   `<details>` per row, home-redacted on render.
4. **Consent timeline** — approve/revoke events per domain with the
   derived-not-live caveat sentence, newest first.
5. **Scrubber posture** — distinct `scrubber_id` values seen in the
   window. If `"noop"` appears (the default `DataScrubber`'s id,
   `security.py:302-304`), show a prominent warning badge mirroring
   the `_meta.scrubber_warning` language: no institutional scrubbing
   policy is configured. `child_scrubber_id` values listed alongside
   (ADR 0003 two-seam model).
6. **Token estimates** — sum of `token_estimate` by domain for the
   window; labeled "estimates recorded at call time."
7. **Vault index stats** — note counts by `note_type`, themes by
   status, most recent `written_at`. Titles/slugs only.
8. **Footer** — "Inspector is read-only; it opened the databases in
   read-only mode. To act on anything you see, use Claude Desktop
   chat or the `tailor` CLI." Link to the governance-pattern doc.

`/health` returns `200 ok` JSON `{"status": "ok", "read_only": true}`
— for tests and for the demo storyboard.

## 5. Privacy and security requirements

- **Bind 127.0.0.1 only** (assert in code; test it).
- **Read-only SQLite**: open with
  `sqlite3.connect("file:<path>?mode=ro", uri=True)`; add a test
  that proves a write attempt through the inspector's connection
  raises.
- **Home-redaction on render**: every rendered string that may carry
  a filesystem path (data-dir header, `params` JSON, vault
  filenames) passes through a `_redact_home()` equivalent collapsing
  `Path.home()` to `~` — same HIPAA Safe Harbor rationale as the
  v6.10.2 / v8.0.0 precedents (CLAUDE.md v8 banner,
  "`_redact_home()` wire-egress defense"). The browser is a new
  egress surface; `phi-irb-risk-reviewer` will (correctly) examine
  it — run that specialist before merge.
- **HTML-escape everything** rendered from the DB (`html.escape`) —
  audit `params` are attacker-influenceable text (an LLM wrote
  them); the inspector must not be an XSS vector. Set
  `Content-Security-Policy: default-src 'none'; style-src
  'unsafe-inline'` and `X-Content-Type-Options: nosniff`.
- **No caching of secrets**: there are none in scope, but
  `--export` output lands on disk — print a one-line note that the
  export contains audit metadata and is the operator's to manage
  (retention contract shape per ADR 0040 § Amendment).
- **Entity IDs are shown.** That is by design — the inspector is the
  operator/IRB surface and `entity_id` scoping exists for exactly
  this audience (ADR 0002/0009). Note it in the ADR.

## 6. File layout

```
src/tailor/inspector/
  __init__.py        # exports run_inspector(), render_page()
  queries.py         # read-only SQL → plain dicts (pure given a connection)
  render.py          # dicts → HTML string (pure; all escaping + redaction here)
  server.py          # http.server plumbing, arg handling, browser-open
src/tailor/__main__.py   # + cmd_inspect() + argparse wiring (mirror cmd_status's shape)
tests/inspector/
  test_queries.py    # tmp audit.db/vault.db fixtures → expected dicts;
                     # legacy-column (subject_id) tolerance; missing-DB empty states
  test_render.py     # escaping (params containing <script> renders inert),
                     # home-redaction, outcome badges, derived-consent caveat present
  test_server.py     # GET / against a fixture DB → 200 + key sections;
                     # POST → 405; binds 127.0.0.1; /health; read-only write-attempt raises
  test_export.py     # --export writes a self-contained file, process exits 0
```

Keep `queries.py` and `render.py` pure (connection/data in, data/string
out) so most tests need no HTTP server. Reuse `tests/conftest.py`
fixtures where they fit; build tiny audit fixtures by calling the real
`AuditLog.record()` against a tmp path — don't hand-write INSERTs.

## 7. What "done" means (acceptance criteria)

1. `tailor inspect --export /tmp/page.html` against the repo's demo
   data renders all eight sections with honest empty states where
   data is absent.
2. With `tailor serve` running and a few demo calls made from Claude
   Desktop (or the business-demo `rehearse.py` flow), the page shows
   the calls within one refresh interval, including at least one
   refusal row if one occurred.
3. The read-only invariant test passes; no code path in
   `src/tailor/inspector/` opens a DB writable (enforce by grep in a
   test: no bare `sqlite3.connect(` without `mode=ro` in the
   package).
4. Full gates green: `ci-gate-runner` scope (pytest, ruff on
   `src tests`, security probe, CLI smoke — now expecting **seven**
   discoverable commands).
5. New-code line count reported in the PR description against the
   ~1,000-line ceiling.

## 8. Process requirements (this repo's culture — do not skip)

- **ADR first**: run `adr-weigher` on "inspector, not application —
  a read-only localhost visibility surface with a hard no-write,
  no-network, no-controls boundary, and a three-stage invocation
  ladder (summoned → ambient opt-in → ambient default) with named
  build triggers," then `adr-drafter`. The ADR must record the full
  ladder from § 2 — including the rejected MCP-spawner tool and its
  reversal condition — so Stages 2–3 are decided once, on paper,
  not re-litigated per release. Reversal conditions to include:
  (a) first institutional adopter requires authenticated multi-user
  inspection (→ Phase 5C work, separate ADR); (b) evidence the
  read-only constraint is blocking a load-bearing IRB workflow.
- **Pre-implementation audit**: `integration-auditor --proposal-mode`
  on this spec (protocol 2).
- **Specialists that WILL trigger**: `phi-irb-risk-reviewer` (new
  egress surface), `coverage-criticality-mapper` (after CI pass),
  `red-team-reviewer` (on the confident PASS),
  `recipient-install-validator` is **file-gated on `__main__.py`**,
  which this touches — flag it in the PR per the gate-composition
  convention even if the run is skipped per the v6.11.x
  falsification precedent.
- **Specialists that will NOT trigger**: `mcp-protocol-auditor`
  (no router/child/MCP changes — the inspector must not touch
  `framework/router.py` at all; if you find yourself editing it,
  the design has gone wrong), `cue-card-rehearsal-auditor` (no
  ToolDefinition changes).
- **Demo before commit** (protocol 5): the demo is the `--export`
  HTML rendered against the business-demo dataset
  (`examples/business_demo/`) after a `rehearse.py`-style call
  sequence — sent to the boss for confirmation before merge.
- **Docs**: CLAUDE.md CLI sections, README one-line mention under
  "What it is" (visibility surface), ROADMAP Phase 4 Direction F
  first bullet marked partially shipped, version bump + banner via
  `release-shipper` when shipping.

## 9. Explicitly out of scope (so the next session doesn't re-litigate)

- Vault graph visualization, data-quality scoring (rest of
  Direction F) — wait for adoption signal.
- Any write/control affordance — needs a superseding ADR.
- Auth, TLS, non-localhost binding — Phase 5C territory.
- Live consent state via IPC with `tailor serve` — clever, rejected
  for v1: it couples the inspector to the server's lifecycle and
  opens an IPC surface for a label upgrade ("live" vs "derived").
  Reversal condition: an IRB reviewer states the derived timeline is
  insufficient in a real inquiry.
- Stage 2 (ambient opt-in: auto-spawn, pilot prompt, desktop
  bookmark, URL token) and Stage 3 (default-on) — designed in § 2,
  trigger-gated, not part of this implementation. Do not build the
  config key, the pilot prompt, or any shortcut writer in v1.
- An MCP tool that opens or spawns the inspector — rejected with a
  named reversal condition (§ 2). The MCP surface is untouched by
  this work.
- Rendering vault note bodies or raw Tier-2/3 payloads — the
  inspector shows *that* data moved and under which gate, not the
  data itself. This asymmetry is the design.

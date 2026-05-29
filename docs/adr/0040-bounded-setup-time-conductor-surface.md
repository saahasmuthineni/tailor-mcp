# ADR 0040: Bounded setup-time conductor surface

- **Status:** Proposed
- **Date:** 2026-05-19
- **Supersedes (in part):**
  - [ADR 0024 (Wheel-distributed tour and fixture bundling)](0024-wheel-distributed-tour-and-fixture-bundling.md) — the `tailor fitting-room` CLI command is hard-removed in v8.0.0; its scaffolding substance moves to the `FittingRoomLayer` MCP tools.
  - [ADR 0027 (Demo as researcher first-look)](0027-demo-as-researcher-first-look.md) — the `tailor walkthrough` CLI command is hard-removed in v8.0.0; its researcher-first-look substance moves to the `WalkthroughLayer` MCP tools.
  - [ADR 0035 (CLI rename: walkthrough + fitting-room)](0035-cli-rename-walkthrough-and-fitting-room-and-recipient-experience-naming-principle.md) — both renamed CLI verbs are hard-removed in v8.0.0; the naming principle is retained for the MCP tool names.
- **Related:** [ADR 0001](0001-audit-log-as-backbone.md),
  [ADR 0003](0003-phi-scrubber-seam.md),
  [ADR 0011](0011-promotion-policy.md),
  [ADR 0012 § Amendment v7.4.0](0012-vault-phi-scrubber-bypass.md),
  [ADR 0013](0013-cache-only-purge-on-consent-revocation.md) (reversal-shape precedent),
  [ADR 0022 § Explicitly out of scope](0022-local-llm-guardian.md) (the
  conductor-mode-toggle deferral this ADR carves out from),
  [ADR 0026](0026-claude-desktop-config-dual-path.md),
  [ADR 0028](0028-recipient-install-validation-as-release-gate.md),
  [ADR 0038](0038-vault-layer-is-data-source-agnostic.md),
  [ADR 0039](0039-audit-log-is-llm-queryable-under-column-allowlist.md)

## Context

A non-technical recipient (Taylor) installed Tailor v7.5.0 on macOS via
`uv tool install` + `tailor pilot` and hit recipient-experience friction
at the CLI prompt layer — typing `--help` at a path prompt because
terminals were not a familiar interface. Triage surfaced two near-term
bugs (orphan-cleanup clobber between `tailor pilot` and `tailor
fitting-room`, missing `tailor --version`), but the deeper finding is
structural: **the terminal is an operator surface; the recipient-facing
parts of Tailor live there because of historical accident, not because
they belong**. A perfectly-designed CLI prompt still requires the
recipient to find their OS's terminal application, type a command
exactly right, understand that errors might be silent, and know how to
copy output back to Claude if they need help debugging. Chat surfaces
eliminate all four.

[ADR 0022](0022-local-llm-guardian.md) deliberately deferred what it
called "conductor mode" — LLM-driven structural action on the
framework's own state — behind a future superseding ADR. The deferral
is in § "Explicitly out of scope" lines 249-250: *"Conductor-mode toggle
(`streamlined | balanced | strict`) — separate session, requires
UX-surface decisions."* The v7.5.0 banner in `CLAUDE.md` (lines 248-271)
deferred two adjacent surfaces against the same constraint: a
**Wizard-child MCP surface** (fails chicken-and-egg on first install
plus conflicts with the ADR 0022 deferral) and a
**LocalLLMLayer-folded wizard** (extends `OracleResponse` schema to
model file-mutation actions, violating the schema-as-contract invariant
ADR 0022 codifies).

Neither deferral exactly matches Taylor's situation. Taylor hit
*first-install* friction — not mid-conversation-on-running-install (the
Wizard-child reversal condition) and not file-mutation-via-prose (the
LocalLLM-folded wizard's structural conflict). The terminal-aversion
class is real, the reversal conditions on the v7.5.0 paragraph's
deferrals are not strictly triggered, and ADR 0022's load-bearing
schema-as-contract invariant is not threatened — provided the
write-authority granted is **bounded** in a way the deferred surfaces
were not.

The first-install + chicken-and-egg framing also matters structurally:
once `tailor pilot` registers Tailor with Claude Desktop and Claude
Desktop is restarted, a recipient who does not know to invoke
`tailor pilot` again to add a source has no chat-side recourse. The
only chat-side recourse the framework offered as of v7.6.0 was
`SetupHelpLayer`'s diagnostic tool, which surfaces *"run `tailor
fitting-room` in your terminal"* — exactly the surface that just
failed the recipient.

This ADR codifies a bounded carve-out from ADR 0022's conductor-mode
deferral for the *setup-time-only* case: a new framework-tier layer
whose write authority is bounded by a source-key allowlist, routed
through the existing canonical writer seam, and audited as
provenance-recoverable rows.

## Decision

Tailor adds a fifth framework-tier layer, **`SetupLayer`**, parallel to
the four layers already named in [ADR 0012 § Amendment v7.4.0](0012-vault-phi-scrubber-bypass.md)
(`VaultLayer`, `LocalLLMLayer`, `SetupHelpLayer`, `AuditQueryLayer`).
`SetupLayer` exposes four MCP tools:

- **`tailor_setup_status`** — read-only. Returns `{"status":
  "configured" | "awaiting_setup", "configured_sources": [...]}`.
  Always callable.
- **`tailor_setup_detect_schema(source_type: str, path: str)`** —
  read-only schema detection. `source_type` is validated against the
  string allowlist `["csv", "matlab", "redcap"]` via `ParamValidator`
  (the v7.6.0 D1 closure ensures this gate fires on string-type
  schemas). Wraps `pilot._autodetect_csv_schema()` /
  `pilot._scan_mat_files()` / REDCap detection — no parallel
  implementation, no drift.
- **`tailor_setup_confirm_schema(source_type, path, schema)`** — pure
  compute. Returns a canonical structure for Claude to summarize to the
  recipient for confirmation. No file mutation.
- **`tailor_setup_write_source_block(source_type, path,
  validated_schema)`** — the only write tool. Routes through
  `pilot._write_user_config(source_key, source_block)` (the v7.5.0
  canonical multi-source deep-merge writer) and emits a new
  `SETUP_CONFIG_WRITE` audit-log outcome row.

### Bounded-write authority is the load-bearing invariant

`tailor_setup_write_source_block` writes **only** the source-config
keys named in a hard-coded allowlist:

```
SETUP_WRITE_KEY_ALLOWLIST = ("csv_dir", "matlab_file", "redcap_file")
```

The allowlist lives at `src/tailor/framework/setup/sources.py` as a
module-level constant, not derived from configuration. A future
contributor adding a new shipped child (EDF, FHIR, vendor sensor)
must explicitly extend this constant — there is no implicit "if a
ChildMCP declares it, allow it" path. The allowlist is verified by a
load-bearing safety test
(`tests/framework/test_setup_source_allowlist.py`) that exercises:

- Every allowlisted key writes successfully.
- Every non-allowlisted key (`local_llm`, `vault_path`,
  `cost_threshold`, `max_hr`, `home_lat`, `home_lng`,
  `csv_dir.path` post-hoc modification attempts, arbitrary other
  strings, the empty string, `None`) is refused with a
  `PARAM_INVALID` audit row.
- The refusal path returns before the deep-merge writer is even
  consulted (defense-in-depth: a bug in `_write_user_config`'s key
  handling cannot accidentally widen the surface).

This bound is what distinguishes ADR 0040's setup-time-only
carve-out from the deferred surfaces in the v7.5.0 banner.

### Bypass posture

`SetupLayer` bypasses the biosensor-tier gates (consent, cost,
circuit-breaker, PHI scrub) — same posture as `VaultLayer` /
`LocalLLMLayer` / `SetupHelpLayer` / `AuditQueryLayer` per [ADR 0012 §
Amendment v7.4.0](0012-vault-phi-scrubber-bypass.md). Param validation
and audit still apply.

The data being written is configuration — not biometric, not
participant-identifying, not analyst notes. The framework-tier-layer
bypass argument from ADR 0012 holds: this is the analyst's machine
authoring local state, not biosensor data flow.

### Lifecycle: always-registered

`SetupLayer` is registered unconditionally at `cmd_serve()` boot,
mirroring `LocalLLMLayer` and `AuditQueryLayer`. There is no
runtime-unregister convention in the framework as of v7.6.0
(`SetupHelpLayer` is conditionally *registered at boot* via
`_demo_blocks_absent()`; no layer un-registers itself at runtime), and
A' does not introduce one.

The "always-registered" posture means the four setup tools appear in
`tools/list` even on configured deployments. `tailor_setup_status`
returns `{"status": "configured"}` rather than no-op-erroring, so a
recipient asking *"is Tailor set up?"* on a working install gets an
honest answer. The detect/confirm/write tools also remain callable on
configured deployments — Claude orchestrates them when the recipient
asks to *add another source* (e.g., a researcher with a working CSV
deployment who later receives a MATLAB cohort). The v7.5.0 multi-source
coexistence by construction in `_write_user_config` makes this
mid-session add path structurally safe.

This tradeoff was weighed against a `_demo_blocks_absent`-shaped
conditional registration (the SetupHelpLayer pattern). The conditional
shape was rejected because: (1) it would hide the mid-session add-source
path the v7.5.0 deep-merge writer was designed to enable; (2) tool-list
bloat on configured deployments (4 setup tools always visible) is a
small cost; (3) the alternative would require explaining to recipients
that they must restart Claude Desktop to add a second source after the
first one was configured, which contradicts the recipient-experience
goal motivating ADR 0040 in the first place.

### Recipient discovery is pull, not push

A recipient who has installed Tailor and opened Claude Desktop does
**not** receive a pushed welcome message. Instead, `SetupLayer`'s tools
carry descriptions tuned for natural-language inference:
`tailor_setup_detect_schema`'s description reads *"Call when the user
wants to start using Tailor with their own CSV / MATLAB / REDCap data,
or asks how to configure a new data source."* Claude picks the tool by
intent in the same way it already picks `csv_summary_report` over
`csv_force_decline` today. The discovery surface is the tool roster
itself, not a hand-crafted welcome prose.

### New audit outcome: `SETUP_CONFIG_WRITE`

`tailor_setup_write_source_block` emits a row with `outcome =
"SETUP_CONFIG_WRITE"`, populated `subject_id` (NULL for setup writes —
configuration is not subject-scoped per [ADR 0009](0009-vault-subject-keying.md)),
the framework `scrubber_id`, and `params` carrying the
canonical-fingerprint of the source block written (not the path —
path is identified by the source_key and may contain user-identifying
filesystem components per HIPAA Safe Harbor §164.514(b)(2)(i)(B)). An
IRB reviewer querying `audit.db` reconstructs *"when did Claude write
configuration on this machine and what shape was it?"* via:

```sql
SELECT * FROM audit_log
WHERE outcome = 'SETUP_CONFIG_WRITE'
ORDER BY id;
```

The `audit_query` tool's outcome-filter description gains
`SETUP_CONFIG_WRITE` in its common-values list; the schema validation
is unconstrained `type=str` so the new value flows through without an
allowlist amendment (same precedent as `ATTEST_INITIAL` per v7.5.0).

### Reversal condition

This ADR's setup-time-only scope is a **first-instance** carve-out from
ADR 0022's conductor-mode deferral. The reversal condition mirrors
[ADR 0013](0013-cache-only-purge-on-consent-revocation.md)'s
"third-domain-promotes-to-framework-registry" precedent:

> If a second non-tool-call write-authority site is identified in the
> framework — for example, a future `vault_path` mutation surface or
> a `cost_threshold` setup tool — the bounded-write pattern documented
> in this ADR is promoted to a framework primitive
> (`SetupAuthorityRegistry` or similar) and the source-key allowlist
> moves out of `setup/sources.py` into the framework registry. A third
> such site triggers the registry promotion automatically.

Until a second site is identified, the allowlist remains a single
module-level constant — sufficient for the surface area ADR 0040
authorises and small enough that misuse is grep-detectable.

### Out of scope

This ADR explicitly does NOT resolve:

- **Wizard-child MCP surface** (v7.5.0 banner deferral) — A' does
  not introduce a `MCPWizardChild` exposing `wizard_configure_*`
  tools to be called mid-conversation on a running install. The
  reversal condition named in the v7.5.0 paragraph remains accurate
  for that surface: "first institutional ask for 'add a source
  mid-conversation' ergonomics on an already-running install."
- **LocalLLMLayer-folded wizard** (v7.5.0 banner deferral) — A' does
  not extend `OracleResponse` to model file-mutation actions. The
  schema-as-contract invariant from ADR 0022 is preserved. The
  reversal condition for that surface ("`OracleResponse` schema
  extended to model file-mutation actions AND a 7B+ model
  demonstrably outperforms hand-coded heuristics") remains intact.
- **Conductor-mode toggle** (`streamlined | balanced | strict`) per
  ADR 0022 § "Explicitly out of scope" line 249. A' is a bounded
  point-decision on one specific authority surface; the broader
  conductor-mode UX question remains deferred.
- **CLI command preservation for `tailor walkthrough` and
  `tailor fitting-room`.** A' hard-removes both CLI commands (no
  deprecation shim). This is a recipient-facing breaking change and
  drives the SemVer major bump (v8.0.0).

### Criticality classification

Per [ADR 0014](0014-coverage-criticality-invariant.md), this ADR
declares the criticality classification of the new code regions:

- **`framework/setup/layer.py:SetupLayer`** — **CRITICAL**.
  Router-adjacent registration. Newly-uncovered code on this path
  after a diff is `COVERAGE REGRESSION` per ADR 0014.
- **`framework/setup/sources.py:SETUP_WRITE_KEY_ALLOWLIST`** and the
  per-source-block validators — **CRITICAL**. The load-bearing safety
  property of ADR 0040; refusal of non-allowlisted keys is the only
  thing that keeps the bounded-write contract honest.
- **`framework/router.py:register_setup_layer`** and
  **`_dispatch_setup`** — inherit the router's CRITICAL classification.
- **`framework/walkthrough/layer.py:WalkthroughLayer`** — **HIGH**.
  Read-only; no write authority. Pattern parity with
  `LocalLLMLayer` / `AuditQueryLayer` matters for the wire-shape
  contract.
- **`framework/fitting_room/layer.py:FittingRoomLayer`** — **HIGH**.
  Read + scaffold; no Claude Desktop registration authority under A'.

## Consequences

**Positive.**

- A recipient who has installed Tailor and registered it with Claude
  Desktop (via `tailor pilot` for the bootstrap, the only CLI touch
  required) can configure data sources, walk the architectural tour,
  and scaffold the bundled demo entirely through conversational tool
  calls. The terminal returns to being an operator surface.
- The orphan-cleanup defect class (v6.10.3 sibling-cleanup, the v7.5.0
  Taylor failure) self-retires structurally. `tailor fitting-room`
  no longer writes Claude Desktop config because it is no longer a
  CLI command; the bug stops being a bug because the architecture
  changes. No v7.5.1 patch is needed.
- The framework now has a tested precedent for bounded write authority
  granted to the hosted LLM. Future authority extensions
  (configuration-management for `vault_path`, dashboard layouts,
  cost-threshold settings) inherit the seam shape.
- The `_write_user_config` deep-merge writer becomes shared
  infrastructure between operator path (`tailor pilot` CLI) and
  recipient path (`SetupLayer` MCP tools). Single source of truth for
  multi-source coexistence; no drift between the two paths.
- The walkthrough's structural argument (the architectural showcase
  from v6.10.5, ADR 0027) now arrives in a conversational shape that
  matches how recipients consume new tools — paced, interactive, with
  Claude composing follow-up explanation.

**Negative.**

- The hosted LLM now holds a (bounded) write surface on the local
  filesystem. The bound is the structural defense; misconfiguration of
  the allowlist or a regression that widens it is the failure mode.
  The load-bearing safety test in
  `tests/framework/test_setup_source_allowlist.py` is the durable
  guard.
- Tool-list bloat: four setup tools always visible in `tools/list`,
  including on long-configured deployments where they are
  permanently-callable but rarely useful (`tailor_setup_status`
  returns `configured`). The cost is real but small; the alternative
  (conditional registration) was rejected for the reasons named under
  "Lifecycle: always-registered" above.
- The `audit_query` filter `tool LIKE 'tailor_setup_%'` matches both
  `SetupHelpLayer`'s diagnostic tool (`tailor_setup_help`) and
  `SetupLayer`'s four tools. An IRB reviewer or operator querying
  the audit log on setup-related activity will receive both layers'
  rows. This is documented in the v8.0 banner and in
  `audit_query`'s outcome-filter description; it is not a defect.
- The CLI hard-remove of `tailor walkthrough` and
  `tailor fitting-room` breaks any script, doc, or muscle-memory that
  relied on them. This is the SemVer major bump (v8.0.0) and the
  reason A' is not a minor.
- `recipient-install-validator` (ADR 0028) must be amended to
  exercise the conversational setup path (not just `tailor pilot`)
  on the wheel installed on a clean Windows VM. The validator was
  designed for CLI-driven onboarding; A' shifts the boundary.

**Neutral.**

- `SetupHelpLayer` (the v6.10.2 degraded-state diagnostic) is left
  alone. Different purpose: SetupHelpLayer emits a diagnostic ("your
  install is wedged, here is what is wrong"); SetupLayer actively
  configures. They coexist with overlapping conditional surfaces but
  non-overlapping responsibilities. A future ADR might merge them if
  recipient testing surfaces UX confusion between the two; until then
  they are two distinct components with distinct ADR groundings.
- The CLI surface contracts from 8 commands to 6:
  `serve / pilot / setup / redcap / status / uninstall`. The
  contraction is the structural commitment of A'; documented in
  CLAUDE.md and README.
- The walkthrough's `--save-shareable` flag (ADR 0030) becomes a
  parameter on `tailor_walkthrough_section` rather than a CLI flag.
  ADR 0030's zero-outbound-affordances rendering invariant is
  preserved at the tool layer; the URL allowlist enforcement at
  `demo/runner.py:342-375` moves into the WalkthroughLayer dispatch.
- ADR 0026 (dual-path Claude Desktop) is unchanged. `tailor pilot` is
  the sole CLI writer of Claude Desktop config under A'; the dual-path
  logic in `_register_with_claude_desktop` continues to apply.
- ADR 0027's "demo as researcher first-look" framing is honoured —
  the walkthrough tools land in Claude Desktop's first-impression
  surface, which is exactly where ADR 0027 intended the showcase to
  live conceptually.

## Alternatives considered

**(1) Open-ended write authority through `OracleResponse`.** Extend the
`OracleResponse` schema in `framework/local_llm/contract.py` to model
file-mutation actions; let the hosted LLM compose configuration as
prose alongside its analytical claims. Rejected. The v7.5.0 banner's
reversal condition for this surface is explicit: extending
`OracleResponse` to model file-mutation actions violates ADR 0022's
schema-as-contract invariant. Wizard work is configuration authoring,
a third category beyond numerical claims and analytical prose that the
schema is not designed for. Folding it in dilutes the invariant for an
ergonomics gain that bounded-write tools achieve more cleanly.

**(2) Wizard-child MCP surface as a `ChildMCP` subclass.** Introduce a
`MCPWizardChild` exposing `wizard_configure_csv` /
`wizard_configure_matlab` / `wizard_configure_redcap` tools. Rejected.
Fails chicken-and-egg on first install (the MCP child has to be
*configured* before the MCP server registers it, but the child's job
is to *do* the configuring), and conflicts with ADR 0022 § "Out of
scope" conductor-mode-deferred. The v7.5.0 reversal condition for this
surface — "first institutional ask for 'add a source mid-conversation'
ergonomics on an already-running install" — is not what Taylor's
failure surfaces. Taylor's failure is first-install friction; the
Wizard-child reversal condition is mid-session-on-running-install
friction. Different reversal conditions, different surfaces.

**(3) Soften `tailor pilot`'s CLI prompts and ship v7.5.1 instead.**
Address Taylor's specific failure modes — `--help` at path prompts,
weak default cue, orphan-cleanup clobber — with patch-level fixes.
Rejected. Even a perfectly-designed CLI prompt does not solve the
terminal-aversion class. The cost of leaving the architectural mismatch
in place is that every recipient-class user pays the terminal-friction
tax permanently; the cost of A' is one architectural pass and a major
version bump. The triage of Taylor's specific bugs surfaces a deeper
finding worth acting on.

**(4) Selective offload: `walkthrough` and `fitting-room` become MCP
tools, but `pilot` stays CLI without any conversational setup path.**
Considered (option B in the original boss conversation). Captures the
walkthrough/fitting-room win but leaves the
non-terminal-comfortable-recipient unable to configure Tailor without
opening a terminal at least once. Rejected as a partial win:
once we are paying for the architectural cycle, the
right end-state is the setup path also.

**(5) Bootstrap CLI command (`tailor install`) plus full
conversational setup.** Reduce CLI to the minimum: a single bootstrap
command that registers Tailor with Claude Desktop and exits, with all
subsequent setup conducted via SetupLayer tools. Considered (option A
in the original boss conversation). Stronger architectural commitment;
removes one more CLI surface (`tailor pilot`'s prompt flow). Rejected
in favour of A' for two reasons: (a) operators / RSEs setting up
Tailor for a PI prefer the terminal directness `tailor pilot` offers
on a deterministic, finite question (which file?); (b) chicken-and-egg
forces *some* CLI touch on first install regardless, and `tailor
pilot` is the existing surface that does it well. A future ADR may
revisit if recipient testing surfaces the `tailor pilot` step as
unnecessary even for first-install.

## Amendment 2026-05-19 — Retention scope (phi-irb-risk-reviewer Lens 6 closure)

**Context.** The pre-merge phi-irb-risk-reviewer pass on this ADR
returned VIOLATION on Lens 6 (retention). The defect named: a config
block written by `tailor_setup_write_source_block` persists in
`~/.tailor/user_config.json` indefinitely, including after a
participant withdraws consent and the operator runs
`revoke_consent_<domain>`. The ADR 0013 § Decision *"revocation =
no cache"* invariant is biometric-cache-table-only and does not
extend to setup-time configuration writes. The path string written
by SetupLayer — which may itself carry Safe-Harbor identifiers
(usernames in `/Users/jane-smith/cohort-2026-IRB-1234/`, geographic
markers in directory names) — survives consent revocation in:

1. `~/.tailor/user_config.json` on disk (no purge hook).
2. `audit_log.params` for every `SETUP_CONFIG_WRITE` row (50 KB
   bounded; no TTL; no purge hook).
3. `audit_log.params` for every subsequent biosensor-tier call against
   the configured child (the cleaned-params dict echoes the
   path-bearing schema).

The reviewer named two options: (a) add a
`purge_user_config_block(source_key)` companion on the consent-
revocation path; (b) explicitly accept the retention profile in this
ADR + amend `docs/design/research-framing.md`.

**Decision.** This amendment accepts option (b): scope-bound the ADR
0013 *"revocation = no cache"* invariant to biosensor-cache tables
(unchanged from ADR 0013), and explicitly name *"configuration
written by SetupLayer is operator-managed retention"* as the SetupLayer
retention contract. Three structural commitments follow:

1. **Operator-managed configuration retention.** A successful
   `tailor_setup_write_source_block` call writes to
   `~/.tailor/user_config.json` and lands a `SETUP_CONFIG_WRITE`
   audit row. Neither artifact is purged by `revoke_consent_<domain>`.
   The operator removes a written source block by editing
   `user_config.json` directly OR by running
   `tailor pilot --source=<type>` with `force=True` to overwrite. The
   audit log row remains for IRB reconstruction.

2. **Lens-1 path-redaction defense-in-depth.** The wire response from
   SetupLayer tools (`written_path`, `user_config_path`, `path` echo
   on detect/confirm) is redacted through `_redact_home` so
   username-bearing path strings collapse to `~` on the surface the
   hosted LLM (and the Claude Desktop chat transcript) sees. The
   on-disk artifacts (`~/.tailor/user_config.json`, `audit_log.params`)
   carry the un-redacted path — the operator's intent — and the
   operator owns retention there. Closes the WATCH-1 finding in the
   same release.

3. **Plain-language operator surface.** `docs/design/research-framing.md`
   § "Consent withdrawal under this profile" gains a fourth paragraph
   naming SetupLayer-written configuration as an *operator-managed
   retention category alongside the analyst notes (vault) and the
   oracle audit rows*. The biosensor-cache table is the only ADR 0013
   purge-on-revocation site; SetupLayer-written config is an operator
   responsibility on revocation, identified by the
   `SETUP_CONFIG_WRITE` audit-log outcome filter.

**What this does NOT do.** It does NOT add a `purge_user_config_block`
tool to the framework. It does NOT extend ADR 0013's purge contract
to non-cache surfaces. It does NOT touch the existing
`_handle_consent_revocation` path in `framework/router.py`. The
deferral is symmetric to the v6.3.1 / v7.5.0 / ADR 0013 narrow-scope
precedent: a future ADR may codify a setup-config-purge tool if
recipient deployments need it (e.g. a future IRB context where the
configuration itself counts as PHI), but the v8.0 surface explicitly
declines to bundle that.

**Reversal condition.** First real-world deployment that surfaces the
configuration-retention-on-revocation problem during an IRB inquiry,
OR an operator who needs an automated revocation-and-purge ritual to
satisfy an institutional policy. Either triggers a follow-on ADR
extending the ADR 0013 purge surface. Until that signal arrives, the
scope-bound posture matches the framework's overall
local-first / operator-managed retention story.

**Lens-2 (consent re-prompt asymmetry) — deferred.** The reviewer's
WATCH-2 finding (`tailor_setup_write_source_block` with `force=true`
re-points a previously-revoked child without consent re-prompt) is
acknowledged as institutional-clarification territory. The current
behaviour: re-pointing the path silently succeeds at config-write
time, and the NEXT biosensor-tier call against the affected child
will hit the in-memory `ConsentGate` and force consent re-approval.
That gate is the structural defense. Deferred to a future ADR if
recipient deployments surface a need for write-time consent re-prompt
(matching the WATCH-2 reversal condition).

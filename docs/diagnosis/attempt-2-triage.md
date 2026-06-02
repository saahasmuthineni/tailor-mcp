# Phase 0 — attempt 2 triage memo

> Working artifact. Post-run analysis of [friction-log-2026-05-09-attempt-2.md](friction-log-2026-05-09-attempt-2.md) against captured transcripts, screenshots, raw Claude Desktop configs (classic + Store-sandbox), and `~/.tailor/` directory under [captures/2026-05-09-attempt-2/](captures/) (gitignored — local-only). Companion to [attempt-1-triage.md](attempt-1-triage.md).

## Run summary

- **Date:** 2026-05-09, ~04:07 → ~04:28 (≈21 min)
- **Path:** A (README path: `uv tool install` + `tailor tour` + `tailor demo` + Claude Desktop integration check)
- **Tailor version installed:** `tailor-mcp==7.0.0` from git+URL `@82c18e7`
- **Recipient state:** fresh local Windows 11 user `tailor-recipient` (post-reset via `takeown` + `icacls` + `Remove-Item` because the SFAP cache had SYSTEM-only ACLs); **Claude Desktop INSTALLED** via Microsoft Store as `Claude_pzs8sxrjxfjjc` UWP package; user signed into Claude Desktop once before starting the install ritual.
- **Outcome:** **Integration loop closed end-to-end.** All 14 install-ritual steps reached either success or a non-blocking observation. Claude Desktop sees `tailor-tour-cohort`, lists the full tool surface when asked, and offers to run tools. The kit's exit signal is met.

## Headline finding (positive)

**External install of Tailor works end-to-end against a clean Windows recipient account with Claude Desktop installed.** This is the first run in project history where (a) `uv tool install` succeeded on a non-developer profile, (b) `tailor tour` scaffolded fixtures + wrote a Claude Desktop config to a path Claude Desktop actually reads, (c) `tailor demo` ran all five sections cleanly, and (d) Claude Desktop surfaced the full tool surface on request and offered to invoke tools. Falsifies the project-memory "no external install of Tailor has ever worked end-to-end" as scoped to "Tailor itself in recipient hands"; remaining unvalidated surface is "different machines / different recipients" (Phase 0 deliverable 3+).

Evidence:
- [Windows PowerShell Transcript Through A9.txt:79-91](captures/2026-05-09-attempt-2/screenshots/Windows%20PowerShell%20Transcript%20Through%20A9.txt) — tour writes to BOTH classic and Store-sandbox paths; success banner now lists both.
- [claude_desktop_config-store-sandbox-RAW.json](captures/2026-05-09-attempt-2/claude_desktop_config-store-sandbox-RAW.json) — Store-sandbox config has both `mcpServers` (Tailor's entry) and `preferences` (Claude Desktop's own writes), confirming Claude Desktop is reading and writing this file.
- [Claude Side Output.png + Part 2.png](captures/2026-05-09-attempt-2/screenshots/) — Claude Desktop's response to *"list the tools you have available from tailor"* returns the complete tool surface grouped by area (Consent management, Generic CSV, EMG, Force-plate, Strava, Vault, oracle).

## Findings

### F4 — Architectural — sharpened: scope narrowed to "Claude Desktop absent" case

**Was:** "Tour declares registration success when Claude Desktop is not installed."

**Now:** Tour declares correctly when Claude Desktop is installed. Attempt 2's success message lists both written paths (classic + Store-sandbox); Claude Desktop reads from the Store-sandbox path; the chain is honest and functional.

**Remaining gap:** The misleading-success only fires when Claude Desktop is absent (the attempt-1 case). The original architectural fix paths still apply for that edge case:

1. **Detect-and-warn:** tour checks Claude Desktop presence (any UWP `Claude_*` package OR existing classic config dir) and emits a different message when absent.
2. **Hard-fail-with-guidance:** tour exits non-zero when Claude Desktop is absent with "install Claude Desktop first".
3. **Documentation-only:** README states Claude Desktop must be installed first; weak fix.

**Severity revision:** dropped from "P0 across the board" to "P0 for the Claude-Desktop-absent edge case only". For the typical recipient (already a Claude user, installs Tailor as the next step), tour now produces honest output. For the *first-time* Claude user (installs Tailor before Claude Desktop), the misleading-success still fires.

**Bucket:** Architectural OR Documentation, depending on which fix path is chosen. Defers to Phase 0 deliverable 2 patch-vs-restructure decision.

### F5 — Documentation (NEW) — Claude Desktop visually asymmetric: connectors get cards, MCP servers get prose

**What:** When asked *"what MCP servers are connected?"*, Claude Desktop responded:

- **Spotify** — rendered as a structured "Connected" connector card with green status indicator and a "Reconnect" button.
- **`tailor-tour-cohort`** — mentioned only in prose: *"there's also a local 'tailor-tour-cohort' (vault, Strava, EMG/force/CSV tools), but that's a session-scoped server rather than a registered connector."*

**Severity:** P1. Non-technical recipient reads "session-scoped server rather than a registered connector" and may interpret as not-fully-connected. They are wrong — Claude Desktop has the entire tool surface and can invoke tools (confirmed by attempt 2's A12 response listing all tools and offering to run one). But the visual surface treats local MCP servers as second-class to OAuth connectors.

**Where the gap lives:** Upstream Claude Desktop UX. **Not a Tailor bug** — Tailor cannot change Claude Desktop's connector-vs-server distinction. But Tailor's documentation and tour-success message can preempt the recipient's confusion.

**Evidence:** [A11 Partial Success.png](captures/2026-05-09-attempt-2/screenshots/A11%20Partial%20Success.png) — the screenshot the recipient labeled "partial success" because of this asymmetric rendering.

**Mitigation paths:**
1. **Tour success message** could append: *"Tailor will appear as a 'session-scoped server' in Claude Desktop, not as a connector card. That's normal — Claude Desktop reserves connector cards for OAuth-based integrations. Ask Claude 'what tools are available from tailor?' to see the full surface."*
2. **README** could include this expectation in the "what success looks like" section.
3. **`tailor status`** could surface the connector-vs-server framing explicitly when reporting Claude Desktop registration state.

**Bucket:** Documentation. ~10 min to add to tour-success message and README.

### F1 — CONFIRMED FIXED in kit hardening commit `9e223d4`

Attempt 2 used the fixed install-checklist with the install command in a code fence. PowerShell parsed it correctly on first try. Zero `\|` parser failures.

**Status:** closed.

### F2 — CONFIRMED REPRODUCIBLE; recipient applied the workaround successfully

PowerShell 5.1 transcripts again did not capture output of `tailor --help`, `tailor tour`, or `tailor demo`. Recipient used the kit's documented workaround: manually selected terminal contents and saved as [Windows PowerShell Transcript Through A9.txt](captures/2026-05-09-attempt-2/screenshots/Windows%20PowerShell%20Transcript%20Through%20A9.txt). That manual capture is the single most informative artifact of the attempt — without it, the architectural confirmation in F4 (tour writing to both paths) and the structural validation of the demo would not be visible.

**Status:** workaround works; gap remains in PowerShell 5.1 itself. Better long-term fix: per-command `Tee-Object` advice in the kit (already noted in attempt-1-triage F2).

### F3 — CONFIRMED REPRODUCIBLE

`python --version` returned command-not-found on the recipient profile (same as attempt 1). `uv tool install` succeeded with its own provisioned Python. **README likely overstates Python as a prerequisite.**

**Action:** still pending — re-read README's prerequisites section. ~5 min.

## Kit-instrument findings (meta — about the kit itself)

### KF1 — Strict filename conventions don't survive recipient natural-naming

**What:** The artifact-pull script in attempt 2 missed the recipient's screenshots+artifacts folder because the script pattern was `diagnosis-screenshots*` (lowercase, hyphen) and the recipient named the folder "Diagnosis Screenshots Plus Artifacts" (spaces, capitals, descriptive). The folder contained the load-bearing screenshots (A11 Partial Success, Claude Side Output Part 1+2, manual transcript). A second pull script with a different pattern was needed.

**Implication:** Future recovery scripts should either:
- Use content-based detection (any folder under recipient profile containing `*.png` files of significant size + recent timestamp), OR
- Accept a wide range of conventional name variants (`diagnosis*`, `screenshots*`, `artifacts*`, etc., case-insensitive), OR
- Just copy everything under the profile that's not Windows-system files.

**Bucket:** Kit-instrument quick fix. Track separately from F1–F5.

### KF2 — Friction-log fields under-filled even with the new numbered-list format

**What:** Despite the kit hardening converting tables to numbered-list-with-sub-fields, attempt 2's friction log only filled in A1–A6 (mostly with "Success") and left A7–A14 blank. The kit's per-step capture is still too high a discipline burden during a 30+ min ritual where the recipient is also troubleshooting / debugging in parallel.

**Real-world capture pattern observed:** the recipient took screenshots and saved terminal output for the load-bearing moments. The narrative was reconstructed *after* the run from those artifacts. The friction log was supplementary.

**Implication:** The friction-log template should probably be re-shaped around "what to capture as artifact" rather than "what to write in real time". Or accept that the log will be filled retroactively and design for that.

**Bucket:** Kit-design lesson. Doesn't block triage of F1–F5.

## Bucket roll-up vs kit's triage taxonomy

| Bucket | Findings | Implication |
|---|---|---|
| Quick fix | (none active — F1 closed) | — |
| Documentation | F2, F3, F5 | All recipient-visible doc issues; ~30 min total to address |
| Architectural | F4 (Claude-Desktop-absent edge case only) | Defers to Phase 0 deliverable 2 — patch (option 1: detect-and-warn) is cheap; restructure is overkill given evidence |
| Irreducible | (none yet observed — but the F5 underlying issue is upstream Claude Desktop's UX, which Tailor can document around but not fix) | F5's mitigation is documentation; the underlying connector-vs-server framing is structurally upstream |
| Kit-instrument | KF1, KF2 | Track for kit revisions; don't block Phase 0 triage |

**Phase 0 deliverable 2 implication:**
- Two attempts on Path A. Attempt 1 produced 4 findings (F1–F4); attempt 2 confirmed F1 closed, narrowed F4 scope, added F5, and validated the overall integration. **Findings are decisively in the Quick fix + Documentation buckets**, with F4 being the one Architectural item that has a Quick-fix path (detect Claude Desktop presence; emit different success message).
- The existing `uv tool install + tailor tour + Claude Desktop restart` ritual is **not the wrong shape** — it works. It produces a functional integration when followed.
- The friction is in three classes: (a) prerequisite ambiguity (Python on PATH; Claude Desktop pre-installed); (b) misleading success when prerequisites missing (F4); (c) Claude Desktop's own UX rendering of MCP servers (F5).
- All three are addressable via documentation + a small targeted patch on tour. Phase 0 deliverable 2 verdict (preliminary, pending a third attempt or a real outside recipient): **patch, not restructure**.

## Decision

Two attempts is the kit's stated minimum; new-finding rate sharply diminishing (attempt 2 surfaced one new item — F5 — that's documentation-only). A third attempt on this hardware would test reproducibility but is unlikely to surface new architectural findings. The remaining unvalidated surface (different machines, different recipients) is structurally separate from self-driven diagnosis (Phase 0 deliverables 3+).

The natural next step is **Phase 0 deliverable 2 — patch-vs-restructure**, with a clear preliminary answer (patch). The patch scope:
- F4 fix: tour detects Claude Desktop absence and emits an honest message in that case.
- F2 fix: per-command `Tee-Object` advice in kit + capture protocol.
- F3 fix: README prerequisites section trimmed to reflect uv handles Python.
- F5 fix: tour-success-message + README expectation-setting on connector-vs-server framing.

That's a tightly-scoped patch release (call it v7.0.4). Phase 0 deliverable 1 (diagnose what's breaking installs) is effectively answered.

# Phase 0 — attempt 1 triage memo

> Working artifact. Post-run analysis of [friction-log-2026-05-09-attempt-1.md](friction-log-2026-05-09-attempt-1.md) against the captured transcripts, screenshots, raw Claude Desktop config, and `~/.tailor/` directory under [captures/2026-05-09-attempt-1/](captures/) (captures dir gitignored — local-only). Companion to [phase-0-diagnosis-kit.md](phase-0-diagnosis-kit.md).

## Run summary

- **Date:** 2026-05-09, ~02:39 → ~03:16 (≈37 min including ~3 min of A4 troubleshooting)
- **Path:** A (README path: `uv tool install` + `tailor tour` + `tailor demo`)
- **Tailor version installed:** `tailor-mcp==7.0.0` from git+URL `@82c18e7`
- **Recipient state:** fresh local Windows 11 user `tailor-recipient`, never used; **Claude Desktop NOT installed** for this account.
- **Outcome:** Friction log marked A8 as P0 ("claude isnt installed so its stunted from the start"). CLI commands ran without crashing; **tour produced output that promises something the system can't deliver**.

## Headline finding

**Tour declares "registration success" when Claude Desktop is not installed.** The `tailor demo` end-to-end path runs cleanly (cohort stats, router pipeline with audit, three-tier resolution, vault moment, oracle with substrate scan all worked) — but the *next-step instruction* tour prints (`"fully quit Claude Desktop, then re-open it"`) is structurally impossible for a recipient who has no Claude Desktop installed. They cannot tell from the success message that the install is incomplete.

Earlier framing of "Tailor itself worked end-to-end" was wrong. CLI didn't crash, but the recipient-facing message lied. That's the same failure class as the v6.10.x patch quartet under a new shape.

## Findings

### F1 — Quick fix (kit-instrument bug): `\|` in install-checklist breaks PowerShell

**Where:** Step A4 of `C:\Users\Public\tailor-diagnosis\install-checklist.md` (staged this session).

**What:** The install command `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` was placed inline in a markdown table cell. The `\` is a markdown-cell-escape for `|`; rendered markdown strips it, but raw markdown opened in Notepad preserves it as a literal backslash. PowerShell parsed `\` as escape-quote, hit unterminated string, refused to run.

**Evidence:** [diagnosis-transcript-attempt-1.txt:60-69](captures/2026-05-09-attempt-1/diagnosis-transcript-attempt-1.txt) — three failed parses, then recipient improvised by removing the backslash.

**Workaround applied (and not logged in friction log):** recipient removed the `\` to get the command to run. Worth noting for attempt 2's discipline.

**Fix:** Move the install command into a code fence rather than a table cell. A code fence preserves the literal text exactly. ~3 min.

**Bucket:** Quick fix (kit, not Tailor).

### F2 — Documentation (kit gap): PowerShell transcripts don't capture `tailor` command output

**Where:** `Start-Transcript` in step A2 / A5; capture protocol § 1 of phase-0-diagnosis-kit.md.

**What:** Transcript captured `python --version`, `uv tool install`, and the no-Python error. It did NOT capture output from `tailor --help`, `tailor tour`, or `tailor demo` — both transcript files are blank between those prompts.

**Evidence:** [diagnosis-transcript-attempt-1-part2.txt:54,56,58](captures/2026-05-09-attempt-1/diagnosis-transcript-attempt-1-part2.txt) — three commands invoked, zero output captured between them. PowerShell 5.1 transcripts on Windows have known gaps around native exe stdout when the exe writes via Win32 console APIs rather than PowerShell's host (uv-built shim binaries appear to do this).

**Recipient improvisation (load-bearing):** recipient noticed the gap, manually copied terminal contents to [TERMINAL OUTPUT FROM UV INSTALL ONWARD.txt](captures/2026-05-09-attempt-1/screenshots/TERMINAL OUTPUT FROM UV INSTALL ONWARD.txt). That manual capture is the most informative artifact in the whole run — without it, F4 would not have been visible.

**Fix:** Add to capture protocol either (a) `tailor demo 2>&1 | Tee-Object diagnosis-tailor-output.txt` advice per command, or (b) explicit "if transcript is empty after running tailor commands, copy terminal contents to a text file manually". ~10 min.

**Bucket:** Documentation (kit, not Tailor).

### F3 — Documentation (Tailor doc, unverified): does the README overstate Python as a hard prerequisite?

**Where:** Step A3 friction log entry says "Python NO"; A6 (`uv tool install`) succeeded immediately after.

**What:** Recipient hit `python : command not recognized` at A3, but `uv tool install` succeeded — uv provisions a Python interpreter automatically when the target tool's `requires-python` is set. So Python on PATH may not actually be a prerequisite when installing via uv.

**Evidence:** [diagnosis-transcript-attempt-1.txt:20-58](captures/2026-05-09-attempt-1/diagnosis-transcript-attempt-1.txt) (Python failure), then [TERMINAL OUTPUT FROM UV INSTALL ONWARD.txt:8-14](captures/2026-05-09-attempt-1/screenshots/TERMINAL OUTPUT FROM UV INSTALL ONWARD.txt) (uv resolved + installed 36 packages including tailor-mcp 7.0.0 in ~20s).

**Action required:** re-read README's prerequisites section. If it states Python ≥3.10 as a hard prerequisite without naming the uv exception, recipients without Python will stop unnecessarily. ~5 min to verify.

**Bucket:** Documentation (Tailor README, conditional on verification).

### F4 — Architectural (HEADLINE finding): Tour declares success when Claude Desktop is not installed

**Where:** `src/tailor/tour.py:222` calls `_claude_desktop_config_paths()`; `src/tailor/pilot.py:412-462` returns the classic `%APPDATA%\Claude\claude_desktop_config.json` path **unconditionally** when `%APPDATA%` resolves, regardless of whether Claude Desktop is installed.

**The acceptance trail:** [pilot.py:442-444](../../src/tailor/pilot.py#L442-L444) is explicit:

> *"on a Store-only machine that has never run Claude Desktop this is a no-op write that neither variant reads — acceptable per ADR 0026 § 'First-time-install on a Store-only machine'"*

[ADR 0026 § "First-time-install on a Store-only machine"](../adr/0026-dual-path-claude-desktop-config.md) made this trade-off for the *Microsoft-Store-vs-Classic timing* case (user is about to install Claude Desktop, write to both paths so whichever variant they install picks it up). It did **not** consider the *Claude-Desktop-never-installed-at-all* case.

**What recipient sees on attempt 1:**

```
(4/4) register with Claude Desktop
      wrote entry 'tailor-tour-cohort' to C:\Users\tailor-recipient\AppData\Roaming\Claude\claude_desktop_config.json

================================================================
  Tour scaffolded successfully
================================================================
  Claude Desktop: registered as 'tailor-tour-cohort' in
                  C:\Users\tailor-recipient\AppData\Roaming\Claude\claude_desktop_config.json

  Next: fully quit Claude Desktop (system tray Quit on Windows,
        Cmd+Q on macOS), then re-open it. Try this prompt:

    "List the available Tailor tools."
```

A recipient with no Claude Desktop has nothing to "fully quit" or "re-open". The success message is structurally a lie.

**Severity:** P0 for the recipient experience. The recipient cannot tell from this output that the install is incomplete. This is the same failure class as the v6.10.x patch quartet (registered-but-no-tools, config-written-to-wrong-path) under a new shape: *config-written-to-a-path-no-process-will-ever-read-because-no-process-exists*.

**Evidence:** [TERMINAL OUTPUT FROM UV INSTALL ONWARD.txt:79-95](captures/2026-05-09-attempt-1/screenshots/TERMINAL OUTPUT FROM UV INSTALL ONWARD.txt) (the success banner) corroborated by [claude_desktop_config-classic-RAW.json](captures/2026-05-09-attempt-1/claude_desktop_config-classic-RAW.json) (a valid JSON config registered for a process that doesn't exist on this account).

**Possible fix paths (all deferred per kit rule 1 — don't fix during diagnosis):**

1. **Detect-and-warn:** tour checks whether `%APPDATA%\Claude\` parent directory existed before tour wrote to it, AND whether any UWP `Claude_*` package exists. If neither, emit a different success banner: "Claude Desktop not detected. Config staged at <path>; install Claude Desktop and it will pick up tailor automatically. **You cannot use tailor's MCP integration until Claude Desktop is installed.**"
2. **Hard-fail:** tour exits non-zero with "Claude Desktop is required and not installed; install it first" and writes nothing.
3. **Documentation-only:** update README to say "Install Claude Desktop FIRST, then run tour" — weakest fix; relies on recipients reading prerequisites.

Option (1) preserves ADR 0026's "stage for later" benefit while telling the truth about state. Option (2) is more aggressive but matches the kit's "demo working ≠ install successful" exit signal. Option (3) is documentation-only and won't catch the recipient who skips reading.

**Bucket:** Architectural (Tailor framework, requires ADR amendment to ADR 0026).

## What's NOT in any bucket — unknowns at end of attempt 1

- **Whether Tailor + Claude Desktop integration works on a clean account.** Steps A10–A14 didn't run. Resolving requires either (a) installing Claude Desktop for `tailor-recipient` and re-running, or (b) escalating to Path B (fresh VM with Claude Desktop pre-installed).
- **Whether the F4 misleading-success message would actually mislead a real recipient** vs. an experienced operator playing recipient. Self-driven diagnosis can't measure that gap; that's Phase 0 deliverable 3+ (real outside recipient).

## Bucket roll-up vs kit's triage taxonomy

| Bucket | Findings | Implication |
|---|---|---|
| Quick fix | F1 (`\|` escape) | Kit-only; ~3 min fix |
| Documentation | F2 (transcript gap), F3 (Python prereq, conditional) | Kit + README; ~15 min total |
| Architectural | **F4 (tour success when Claude Desktop absent)** | Tailor; needs ADR 0026 amendment + tour code path; not fixed during diagnosis |
| Irreducible | (none yet — too early) | Phase 0 deliverable 3+ |

**Phase 0 deliverable 2 implication so far:** one architectural finding, three documentation/kit findings. Too early to declare patch-vs-restructure — attempt 2 should run with kit bugs fixed and Claude Desktop installed for recipient, to surface findings on the integration path that attempt 1 couldn't reach.

## Decision committed for attempt 2

Commit attempt 1 findings now (this memo + friction log + kit). Then fix kit bugs F1+F2 plus the format change (table → numbered list — boss feedback: "Notepad checklist very ineffective"). Install Claude Desktop on the recipient account. Run attempt 2. **F4 stays open** in the friction log; honors kit rule 1 (don't fix Tailor during diagnosis). If attempt 2 surfaces another architectural finding of similar severity, that's evidence of patch-vs-restructure choice; if it surfaces only documentation/quick-fix items, F4 + a few documentation patches close Phase 0 deliverable 1.

## Discipline notes for attempt 2 (carry forward)

1. **Workarounds section was empty in attempt 1's friction log; should not be empty in attempt 2.** Recipient applied at least one (removed `\` from install command) that wasn't logged. Whether attempt 2 hits zero workarounds is itself a finding.
2. **Friction-class column was sparse in attempt 1.** Either every row gets a class or the kit needs a clearer "fill this in" instruction.
3. **A8's class was "P0 because Claude Desktop isn't installed" — that was the test prerequisite missing, not the tool failing.** Attempt 2 with Claude Desktop installed will distinguish "tool failed" from "test couldn't run" classes more cleanly.

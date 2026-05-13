# Phase 0 — Diagnosis Kit

> Working artifact. Not a release document. Owned by the project author for the duration of [ROADMAP Phase 0](../../ROADMAP.md#phase-0--install-path-validation-active-duration-tbd-by-diagnosis).

## What this kit is for

[ROADMAP Phase 0](../../ROADMAP.md#phase-0--install-path-validation-active-duration-tbd-by-diagnosis) names diagnose-before-fix as the binding discipline. This kit is the operational infrastructure for that discipline — the templates and rituals that turn *"walk through install on a clean machine and log friction"* into a repeatable exercise.

Phase 0 has four deliverables. This kit is for **deliverable 1** (diagnose what's actually breaking installs) and feeds **deliverable 2** (decide patch vs restructure). It does not address deliverables 3 and 4 (prove on first / second outside machine), because those structurally require outside recipients.

The v6.10.x patch quartet is the cautionary tale this kit exists against — four reactive patches (cp1252 → SetupHelpLayer → sibling cleanup → dual-path) that each fixed a visible bug and did not solve the underlying install-end-to-end problem. Diagnose-first changes the question from *"what's the next bug?"* to *"what's the actual binding constraint?"* — which might be architectural, might be documentation, might be a class of bugs the dev environment papers over.

## The constraint we're working under

No outside recipient is available. Diagnosis is self-driven on this machine.

**What self-driven diagnosis substitutes for**: technical install bugs (Path issues, encoding crashes, missing wheels, broken commands, dual-path config writes, Claude Desktop registration paths, file-permission edge cases). These surface as well in a clean-state environment on the project author's hardware as they do on a stranger's machine.

**What it does not substitute for**: recipient-capability friction (a real human who doesn't know how to open PowerShell, doesn't know what a wheel is, doesn't read instructions linearly, hits a confusing error message and stops). That gap is irreducible — Phase 0 *exit* requires real outside recipients on different OSes. Self-driven diagnosis is for the *diagnose* deliverable, not the *prove* deliverables.

The structural backstop for tribal knowledge: the friction log forces workarounds to be written down. **Workarounds you instinctively reach for are the friction a recipient would hit.** That's the load-bearing capture, more so than the bugs that hard-fail.

## Path A — Fresh Windows user account

### Why this path

Cheapest clean-state environment on existing hardware. Surfaces user-profile-scoped bugs (PATH, %APPDATA%, registry HKCU, Claude Desktop per-user config, no `~/.tailor/`). Does not surface machine-level state (Python already installed, system Path entries, Claude Desktop binary already installed). Reset is a 5-minute user-account delete-and-recreate.

When Path A stops surfacing new friction (typically 2-3 attempts in), escalate to **Path B — Fresh Windows VM** (your existing VirtualBox 7.2.8 + Vagrant 2.4.9 infrastructure; manual walkthrough, not the falsified `recipient-install-validator` agent).

### One-time Path A setup

Create the recipient user account (PowerShell as Administrator):

```powershell
$pwd = ConvertTo-SecureString "TempDiagnosisPwd2026!" -AsPlainText -Force
New-LocalUser -Name "tailor-recipient" -Password $pwd -FullName "Tailor Recipient" -Description "Phase 0 diagnosis recipient persona"
Add-LocalGroupMember -Group "Users" -Member "tailor-recipient"
```

Sign out of your daily-driver account. Sign in as `tailor-recipient`. From this point forward, **act as if you are a recipient who has never seen the project**:

- Don't open `c:\Users\saaha\Biosensor-to-LLM-Connector\` in any editor.
- Don't run any command from memory; only run commands that appear in the documented install ritual.
- If a step is ambiguous, **don't infer the right thing** — log the ambiguity and follow the literal text.
- If you reach for a workaround (*"I know I need to also do X"*), stop. Log the workaround. Do not apply it.

### Reset ritual between attempts

Before each new attempt, sign out as `tailor-recipient`, sign back in as your daily-driver account, then:

```powershell
# Remove the recipient profile and recreate
Remove-LocalUser -Name "tailor-recipient"
Remove-Item -Recurse -Force "C:\Users\tailor-recipient" -ErrorAction SilentlyContinue
$pwd = ConvertTo-SecureString "TempDiagnosisPwd2026!" -AsPlainText -Force
New-LocalUser -Name "tailor-recipient" -Password $pwd -FullName "Tailor Recipient" -Description "Phase 0 diagnosis recipient persona"
Add-LocalGroupMember -Group "Users" -Member "tailor-recipient"
```

Confirm the profile directory is fully gone (`C:\Users\tailor-recipient` should not exist) before signing back in. Windows occasionally fails to delete the profile directory on first try if any process is still holding files; retry the `Remove-Item` line if needed.

## Discipline reminders

Pin these to the diagnosis session. They are the rules that distinguish diagnose-first from the v6.10.x reactive shape.

1. **Don't fix anything during diagnosis.** If a fix is obvious, log it as a finding and continue. Fixes during diagnosis create observation bias for the next step.
2. **Log workarounds as friction, not as success.** A workaround you reached for is a step a recipient would not have known to take.
3. **Treat error messages as the user surface.** If you hit an error, copy the exact text. Don't paraphrase. The error message is what the recipient sees.
4. **One attempt = one friction log file.** Don't conflate runs. Comparing two runs against the same template is the value.
5. **Stop at the first hard fail.** Hard-fail = step cannot complete without intervention beyond the documented ritual. Note the friction class as **P0**, capture state, end the run. Do not bash through with workarounds to "see what's beyond."
6. **Demo working ≠ install successful.** The exit signal is `tailor demo` running clean *and* `tailor tour` writing a Claude Desktop config that Claude Desktop actually reads. Both have to work.

## Stranger-eyes install checklist

This is the documented install ritual stripped to literal commands a recipient would execute. The README's recipient install path (`uv tool install git+...` + `tailor tour`) is canonical for v7+. The historical wheel path is preserved at the bottom but is not the priority surface.

For each step, the friction log captures: **expected outcome**, **actual outcome**, **workaround used (if any)**, **friction class**, **screenshot reference**.

### A. README path (canonical for v7+)

> **Format:** numbered linear list, one heading per step, command in a fenced block. Tables-in-Notepad are unreadable for procedural reading and the markdown-cell escape (`\|`) is preserved as a literal backslash, which broke a real PowerShell parse on attempt 1 (see [attempt-1-triage.md § F1](attempt-1-triage.md#f1--quick-fix-kit-instrument-bug-pipe-escape-in-install-checklist-breaks-powershell)).

#### A1 — Open PowerShell

Win + R, type `powershell`, Enter.

**Expected:** New PowerShell window.

#### A2 — Start the transcript

```powershell
Start-Transcript -Path "$env:USERPROFILE\diagnosis-transcript-attempt-1.txt"
```

**Expected:** "Transcript started" message. Will capture commands + most output, but **see capture-protocol § 1 below** — PowerShell 5.1 transcripts have a known gap on uv-shim-built executables; you may need to manually copy terminal contents for `tailor` commands.

#### A3 — Check Python (informational only)

```powershell
python --version
```

**Expected:** Version prints if Python ≥3.10 is on this user's PATH. If not, **log it but continue** — `uv tool install` provisions its own Python, so this is informational, not a hard prerequisite. The friction is whether the README/install docs lead a recipient to believe Python on PATH is required when in fact uv handles it.

#### A4 — Install uv

Per [official docs](https://docs.astral.sh/uv/getting-started/installation/). On Windows, the documented command is exactly:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Expected:** uv binary installed under `$env:USERPROFILE\.local\bin`; PATH updated for new shells.

#### A5 — Open a fresh PowerShell

Close the current PowerShell window so PATH refresh takes effect. Open a new one. Restart the transcript with a different filename:

```powershell
Start-Transcript -Path "$env:USERPROFILE\diagnosis-transcript-attempt-1-part2.txt"
```

**Expected:** Fresh shell, new transcript.

#### A6 — Install tailor via uv

```powershell
uv tool install git+https://github.com/saahasmuthineni/tailor-mcp.git
```

**Expected:** Resolves dependencies, installs `tailor` command into uv's tool space.

#### A7 — Verify tailor command

> **Per-command capture (Phase 0 attempt-1+2 F2 lesson, v7.0.4):** PowerShell 5.1
> `Start-Transcript` does NOT reliably capture stdout from uv-shim-built native
> exes — both attempts of self-diagnosis 2026-05-09 confirmed this. The kit-level
> mitigation is per-command `Tee-Object`. Wrap every `tailor` invocation from A7
> through A13 in a tee redirect so each command's stdout lands in a per-command
> file regardless of transcript behavior. This is a workaround for a PowerShell
> 5.1 limitation, not a Tailor bug.

```powershell
tailor --help 2>&1 | Tee-Object -Append "$env:USERPROFILE\diagnosis-tailor-output-attempt-1.txt"
```

**Expected:** Help text printing subcommands: pilot, tour, serve, demo, setup, status, uninstall. (The `migrate` subcommand was retired in v7.0.9 — see [ADR 0034](../adr/0034-retire-tailor-migrate-subcommand.md).) With the `Tee-Object` wrapper above, the same output also lands in the per-command file even if the transcript file shows blank.

#### A8 — Scaffold the tour

```powershell
tailor tour 2>&1 | Tee-Object -Append "$env:USERPROFILE\diagnosis-tailor-output-attempt-1.txt"
```

**Expected:** Scaffolds bundled HIP Lab fixtures into `~/.tailor/demos/hip-lab/`, writes `user_config.json`, registers with Claude Desktop. Should print success messages and end cleanly. **Watch for:** since v7.0.4, the success banner distinguishes the *Claude-Desktop-installed* case ("registered as 'tailor-tour-hip-lab' in <path>" + "fully quit Claude Desktop, then re-open it") from the *Claude-Desktop-absent* case ("Tour scaffolded; Claude Desktop NOT DETECTED" + "config has been staged for a future install"). Record which message variant the run prints; that is itself the F4-fix's honesty test. (Original finding: [F4 — tour declares success when Claude Desktop is not installed](attempt-1-triage.md#f4--architectural-headline-finding-tour-declares-success-when-claude-desktop-is-not-installed).)

#### A9 — Run the architectural demo

```powershell
tailor demo 2>&1 | Tee-Object -Append "$env:USERPROFILE\diagnosis-tailor-output-attempt-1.txt"
```

**Expected:** Five-section architectural showcase against bundled fixtures. Prints structured output, ends cleanly.

#### A10 — Open Claude Desktop

Claude Desktop must be installed and signed in for this user separately. **Log if it isn't** — A8's "registered" claim is conditional on Claude Desktop existing.

**Expected:** Claude Desktop opens.

#### A11 — Verify MCP server connection

Inside Claude Desktop, either ask *"What MCP servers are connected?"* or check the MCP-server settings UI.

**Expected:** Tailor server is listed and connected (green indicator).

#### A12 — Verify tool surface

Inside Claude Desktop, ask *"List the tools you have available from tailor"*.

**Expected:** Returns the framework tool surface (csv_dir tools, vault tools, oracle tool, setup help if degraded, etc.).

#### A13 — Run tailor status

```powershell
tailor status 2>&1 | Tee-Object -Append "$env:USERPROFILE\diagnosis-tailor-output-attempt-1.txt"
```

**Expected:** Reports diagnostic state: token files, DB state, Wardrobe config.

#### A14 — Stop the transcript

```powershell
Stop-Transcript
```

**Expected:** Transcript saved.

### B. Historical wheel path (lower priority — only if Path A1-A14 surfaces install-ritual problems traceable to git+URL fetching)

This path matches the older `examples/hip_lab_demo/realistic/WINDOWS_QUICKSTART.md` (still references a v6.9.0 wheel name — itself a friction-log-worthy doc-truth observation). Run only if instructed.

#### B1 — Build the wheel

From your daily-driver account:

```powershell
cd c:\Users\saaha\Biosensor-to-LLM-Connector
python -m build
```

**Expected:** Wheel `tailor_mcp-X.Y.Z-py3-none-any.whl` exists in `dist/`.

#### B2 — Copy the wheel to recipient Downloads

As `tailor-recipient`, copy the wheel to `C:\Users\tailor-recipient\Downloads\`.

#### B3 — Install the wheel

```powershell
pip install $env:USERPROFILE\Downloads\tailor_mcp-X.Y.Z-py3-none-any.whl
```

**Expected:** Wheel installs; `tailor` command available.

#### B4–B14

Same as A4–A14 above (skip A6 since the wheel is already installed).

## Friction-log template

Copy this template per attempt. Save as `docs/diagnosis/friction-log-<YYYY-MM-DD>-<attempt-N>.md`. The numbered per-step list + workarounds section + final notes are the load-bearing artifact.

> **Format change from attempt 1:** the step-by-step section is a numbered list with sub-fields per step rather than a markdown table. Per attempt 1 feedback ("Notepad checklist very ineffective — markdown table was unreadable"). Each step gets its own block; cells become labeled lines.

```markdown
# Friction log — Path A attempt N — YYYY-MM-DD

**Environment**: Fresh tailor-recipient user, Win 11 Home 26200, PowerShell 5.1
**Path attempted**: A (README path) | B (wheel path)
**Started**: HH:MM
**Ended**: HH:MM
**Outcome at run-end**: completed cleanly | hard-fail at step Ax | partial success with workarounds (delete the two that don't apply)

## Step-by-step

For each step you ran, fill in all five sub-fields. Use `—` for "not applicable" rather than leaving blank, so you can tell at a glance you considered it.

### A1 — Open PowerShell

- **Expected:** New PowerShell window
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A2 — Start the transcript

- **Expected:** "Transcript started" message
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A3 — Check Python (informational)

- **Expected:** Version prints OR command-not-found (both acceptable; uv handles its own Python)
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A4 — Install uv

- **Expected:** uv binary installed under `~/.local/bin`, PATH updated for new shells
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A5 — Open a fresh PowerShell

- **Expected:** Fresh shell, new transcript
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A6 — uv tool install tailor

- **Expected:** Resolves dependencies, installs `tailor` command
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A7 — tailor --help

- **Expected:** Help text prints subcommand list
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A8 — tailor tour

- **Expected:** Scaffolds + registers, ends cleanly. **Watch:** is the "Claude Desktop registered" message honest given recipient state?
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A9 — tailor demo

- **Expected:** Five-section showcase prints, ends cleanly
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A10 — Open Claude Desktop

- **Expected:** Claude Desktop opens (must be installed for this user)
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A11 — Verify MCP server connection

- **Expected:** Tailor server is listed and connected
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A12 — Verify tool surface

- **Expected:** Returns framework tool surface
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A13 — tailor status

- **Expected:** Reports diagnostic state
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A14 — Stop-Transcript

- **Expected:** Transcript saved
- **Actual:**
- **Workaround used:** —
- **Friction class:**
- **Capture:**

## Friction-class legend

- **P0** — Hard fail. Step cannot complete without intervention beyond documented ritual. **Stop the run here** unless the cause is a missing test prerequisite (e.g. Claude Desktop not installed) — in which case mark it differently and decide whether to continue.
- **P1** — Confusing. Step completes but the recipient would plausibly stop here, or the output is misleading, or the next step is non-obvious.
- **P2** — Cosmetic. Step works but the surface is rough (wording, formatting, slight delay).
- **None** — Step worked exactly as documented.

## Workarounds I reached for and consciously did not apply

> Critical section. The workarounds you wanted to apply but suppressed. **Also include workarounds you applied** (e.g. retrying a command three times until it parsed). The kit's discipline is to log workarounds, not always suppress them.
>
> Format: "At step Ax: <wanted to | applied> <workaround>; <suppressed | applied because the literal command failed>; logged."

-
-
-

## Notes

> Anything that doesn't fit the per-step blocks — surprises, ambiguities, doc-truth gaps observed, second-order observations, kit-instrument feedback.

-
-
-
```

## Capture protocol

Per attempt, capture **all** of:

1. **PowerShell transcript** (with manual-tee fallback). `Start-Transcript -Path "$env:USERPROFILE\diagnosis-transcript-<attempt>.txt"` at session start; `Stop-Transcript` at end. **Known gap (attempt 1):** PowerShell 5.1 transcripts on Windows fail to capture stdout from native exes that write via Win32 console APIs rather than PowerShell's host. uv-shim-built executables (including the `tailor` command after `uv tool install`) appear to do this — `tailor --help`, `tailor tour`, and `tailor demo` produced visible terminal output that the transcript file showed as blank. **Workaround:** if the transcript shows no output between two prompts where you ran a `tailor` command, immediately Select-All in the PowerShell window (right-click title bar → Edit → Select All → Enter to copy), paste into Notepad, and save as `$env:USERPROFILE\diagnosis-terminal-output-<attempt>.txt`. Better fix attempted in attempt 2: each `tailor` invocation can be wrapped as `tailor <subcmd> 2>&1 | Tee-Object -Append "$env:USERPROFILE\diagnosis-tailor-output-<attempt>.txt"` — see [attempt-1-triage.md § F2](attempt-1-triage.md#f2--documentation-kit-gap-powershell-transcripts-dont-capture-tailor-command-output).
2. **Screenshots**. Win + Shift + S, save to `$env:USERPROFILE\diagnosis-screenshots\`. Take one per friction event (any P0, P1, or unexpected output). Reference the filename in the friction-log per-step *Capture* field.
3. **`audit.db` after the demo**. Copy `~/.tailor/data/audit.db` to `$env:USERPROFILE\diagnosis-audit-<attempt>.db`. After signing back in as daily-driver, inspect with `sqlite3` — the audit log is the authoritative record of what the framework actually did, useful for cross-checking observed behaviour against logged behaviour.
4. **Claude Desktop config snapshot**. Both paths if both exist:
    - Classic: `$env:APPDATA\Claude\claude_desktop_config.json`
    - Store-sandboxed: `$env:LOCALAPPDATA\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json`
    Copy both to `$env:USERPROFILE\diagnosis-claude-config-<attempt>\` so the dual-path resolution can be inspected post-hoc.
5. **The user_config.json that `tailor tour` wrote**. `~/.tailor/user_config.json` — copy to `$env:USERPROFILE\diagnosis-user-config-<attempt>.json`.

After each attempt, before resetting the user account, copy the entire `$env:USERPROFILE\diagnosis-*` set to a USB stick or a daily-driver-accessible location. The reset wipes the recipient profile.

> **Note on artifact recovery:** the daily-driver account cannot read another user's home directory by default (Windows protects each user's profile). Recovering the diagnosis artifacts after sign-out requires either an Admin PowerShell session (which bypasses the per-user ACL) or moving the artifacts to `C:\Users\Public\` before signing out. The kit's repo has a recovery script pattern documented in `attempt-1-triage.md` workflow.

## Post-diagnosis triage

After 2-3 Path A attempts (or until Path A stops surfacing new friction), categorize all logged friction into one of four buckets. **Do not fix during diagnosis** — this is the post-diagnosis exercise.

| Bucket | What lands here | Fix path |
|---|---|---|
| **Quick fix** | One-file code change with low blast radius (a missing utf-8-sig, a glyph that crashed cp1252, a broken click on `tailor status`). v6.10.x-shaped. | Patch release after Phase 0 closes. |
| **Documentation** | Step that worked but a recipient would stop at because the wording is wrong, the next step is non-obvious, or a prerequisite isn't named. | Phase 1 README rewrite. |
| **Architectural** | Friction that doesn't fix without restructuring the install path itself (Python prerequisite is a barrier; uv is unfamiliar to non-developers; PATH refresh between shells is invisible). Suggests single-binary executable / Docker / one-shot installer. | Phase 0 deliverable 2 — patch-vs-restructure decision. |
| **Irreducible** | Friction that would only surface for a real recipient (interpretation gaps, cognitive load) and self-driven diagnosis can't pin down. | Phase 0 deliverable 3+ — track for the first real outside recipient run. |

The split across these buckets *is* the answer to Phase 0 deliverable 2. If most friction lands in **Quick fix** + **Documentation**, the existing architecture is patchable and Phase 0 closes via a few targeted fixes + a README rewrite. If most friction lands in **Architectural**, the existing `uv tool install + tailor tour + Claude Desktop restart` ritual is the wrong shape for non-developers and Phase 0 escalates to a structural change (single-binary / Docker / one-shot installer).

## When to escalate from Path A to Path B

Trigger conditions for moving from fresh user account to fresh VM:

- Path A produces a clean run end-to-end with no P0 or P1 friction (test the result on a more hostile environment).
- Path A surfaces friction that's plausibly inherited from machine-level state (Python version installed system-wide, Claude Desktop's machine-installed UWP container, system Path entries containing dev tooling).
- Path A surfaces friction that depends on Claude Desktop *not yet being installed* (Path A inherits the machine-level Claude Desktop binary; Path B starts without it).

When triggered, Path B uses your existing VirtualBox 7.2.8 + Vagrant 2.4.9 infrastructure with a `bento/windows-11` (or equivalent) base box. Manual walkthrough — *not* the falsified `recipient-install-validator` agent. The agent's silent-park failure mode is an automation problem; the underlying VM substrate works.

## What this kit does not include

- Mac and Linux equivalents. Windows is the priority because the v6.10.x bug class lived there. macOS and Linux paths get added when Path A on Windows produces a clean end-to-end run.
- A way to recruit outside recipients. That is the Phase 0 deliverable 3-4 problem and is structurally separate from this kit.
- Automation. Per project memory, the `recipient-install-validator` agent's silent-park failure mode is the cautionary tale against more prose-driven automation here. Manual walkthrough with a written log is the discipline this kit enforces.

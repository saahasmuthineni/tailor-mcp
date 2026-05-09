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

| # | Step | Expected outcome |
|---|---|---|
| A1 | Open PowerShell (Win + R, type `powershell`, Enter) | New PowerShell window |
| A2 | Run `Start-Transcript -Path "$env:USERPROFILE\diagnosis-transcript.txt"` | Transcript started message; will capture every command + output |
| A3 | Run `python --version` | If Python ≥3.10 is on this user's PATH: version prints. If not: command-not-found is itself a friction event — log it and continue per the README's prerequisites section |
| A4 | Install `uv` per [official docs](https://docs.astral.sh/uv/getting-started/installation/) — for Windows, the documented command is `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` | uv binary installed under `$env:USERPROFILE\.local\bin`; PATH updated for new shells |
| A5 | Open a fresh PowerShell so PATH refresh takes effect; rerun `Start-Transcript` with a different filename | Fresh shell |
| A6 | Run `uv tool install git+https://github.com/saahasmuthineni/Biosensor-to-LLM-Connector.git` | Resolves dependencies, installs `tailor` command into uv's tool space |
| A7 | Run `tailor --help` | Help text prints listing subcommands: pilot, tour, serve, demo, setup, status, migrate, uninstall |
| A8 | Run `tailor tour` | Scaffolds bundled HIP Lab fixtures into `~/.tailor/demos/hip-lab/`, writes user_config.json, registers with Claude Desktop. Should print success messages and end cleanly. |
| A9 | Run `tailor demo` | Runs the five-section architectural showcase against bundled fixtures. Prints structured output to terminal, ends cleanly. |
| A10 | Open Claude Desktop (must be installed and signed in for this user separately — log if it isn't) | Claude Desktop opens |
| A11 | Inside Claude Desktop, ask *"What MCP servers are connected?"* or check the MCP-server settings UI | Tailor server is listed and connected (green indicator) |
| A12 | Inside Claude Desktop, ask *"List the tools you have available from tailor"* | Returns the framework tool surface (csv_dir tools, vault tools, oracle tool, setup help if degraded, etc.) |
| A13 | Run `tailor status` in PowerShell | Reports diagnostic state: token files, DB state, Wardrobe config |
| A14 | Run `Stop-Transcript` | Transcript saved |

### B. Historical wheel path (lower priority — only if Path A1-A14 surfaces install-ritual problems traceable to git+URL fetching)

This path matches the older `examples/hip_lab_demo/realistic/WINDOWS_QUICKSTART.md` (still references a v6.9.0 wheel name — itself a friction-log-worthy doc-truth observation). Run only if instructed.

| # | Step | Expected outcome |
|---|---|---|
| B1 | Receive a `tailor_mcp-X.Y.Z-py3-none-any.whl` file (you would build this from your daily-driver account: `cd c:\Users\saaha\Biosensor-to-LLM-Connector; python -m build`) | wheel exists in dist/ on daily-driver account |
| B2 | As `tailor-recipient`, copy the wheel to Downloads | wheel in `C:\Users\tailor-recipient\Downloads\` |
| B3 | Open PowerShell, run `pip install $env:USERPROFILE\Downloads\tailor_mcp-X.Y.Z-py3-none-any.whl` | Wheel installs; `tailor` command available |
| B4-B14 | As A4-A14 above (skip A6 since wheel is already installed) | Same expectations |

## Friction-log template

Copy this template per attempt. Save as `docs/diagnosis/friction-log-<YYYY-MM-DD>-<attempt-N>.md`. The bullet log + table + final notes are the load-bearing artifact.

```markdown
# Friction log — Path A attempt N — YYYY-MM-DD

**Environment**: Fresh tailor-recipient user, Win 11 Home 26200, PowerShell 5.1
**Path attempted**: A (README path) | B (wheel path)
**Started**: HH:MM
**Ended**: HH:MM
**Outcome at run-end**: completed cleanly | hard-fail at step Ax | partial success with workarounds

## Step-by-step

| Step | Expected | Actual | Workaround used | Friction class | Capture |
|---|---|---|---|---|---|
| A1 | New PowerShell | (e.g. exact) | — | None | — |
| A2 | Transcript started | (e.g. exact) | — | None | transcript.txt |
| A3 | Python ≥3.10 prints | command-not-found | — | **P0 hard fail** | screenshot-A3.png |
| ... | | | | | |

## Friction-class legend

- **P0** — Hard fail. Step cannot complete without intervention beyond documented ritual.
- **P1** — Confusing. Step completes but the recipient would plausibly stop here, or the output is misleading, or the next step is non-obvious.
- **P2** — Cosmetic. Step works but the surface is rough (wording, formatting, slight delay).
- **None** — Step worked exactly as documented.

## Workarounds I reached for and consciously did not apply

(Critical section. The workarounds you wanted to apply but suppressed.)

- e.g. "Wanted to run `where python` after A3 to find which Python existed on this account; suppressed; logged the friction instead."
- e.g. "Wanted to manually edit Claude Desktop config when A11 didn't show tailor; suppressed."

## Notes

(Anything that doesn't fit the table — surprises, ambiguities, doc-truth gaps observed, second-order observations.)
```

## Capture protocol

Per attempt, capture **all** of:

1. **PowerShell transcript**. `Start-Transcript -Path "$env:USERPROFILE\diagnosis-transcript-<attempt>.txt"` at session start; `Stop-Transcript` at end. Captures every command + every visible output line.
2. **Screenshots**. Win + Shift + S, save to `$env:USERPROFILE\diagnosis-screenshots\`. Take one per friction event (any P0, P1, or unexpected output). Reference the filename in the friction-log table's *Capture* column.
3. **`audit.db` after the demo**. Copy `~/.tailor/data/audit.db` to `$env:USERPROFILE\diagnosis-audit-<attempt>.db`. After signing back in as daily-driver, inspect with `sqlite3` — the audit log is the authoritative record of what the framework actually did, useful for cross-checking observed behaviour against logged behaviour.
4. **Claude Desktop config snapshot**. Both paths if both exist:
    - Classic: `$env:APPDATA\Claude\claude_desktop_config.json`
    - Store-sandboxed: `$env:LOCALAPPDATA\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json`
    Copy both to `$env:USERPROFILE\diagnosis-claude-config-<attempt>\` so the dual-path resolution can be inspected post-hoc.
5. **The user_config.json that `tailor tour` wrote**. `~/.tailor/user_config.json` — copy to `$env:USERPROFILE\diagnosis-user-config-<attempt>.json`.

After each attempt, before resetting the user account, copy the entire `$env:USERPROFILE\diagnosis-*` set to a USB stick or a daily-driver-accessible location. The reset wipes the recipient profile.

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

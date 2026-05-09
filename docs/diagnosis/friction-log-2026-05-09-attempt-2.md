# Friction log — Path A attempt 2 — 2026-05-09

> **First action: Save As to** `C:\Users\tailor-recipient\Documents\friction-log-2026-05-09-attempt-2.md` so the staging copy stays clean for any attempt 3.

**Environment**: Fresh tailor-recipient user (post-reset), Win 11 Home 26200, PowerShell 5.1, Claude Desktop installed: yes / no (fill in)
**Path attempted**: A (README path)
**Started**: HH:MM
**Ended**: HH:MM
**Outcome at run-end**: completed cleanly | hard-fail at step Ax | partial success with workarounds (delete the two that don't apply)

## Step-by-step

For each step, fill in all five sub-fields. Use `—` for "not applicable" rather than leaving blank, so you can tell at a glance you considered it.

### A1 — Open PowerShell

- **Expected:** New PowerShell window
- **Actual:*Success*
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A2 — Start the transcript

- **Expected:** "Transcript started" message
- **Actual:*Success*
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A3 — Check Python (informational)

- **Expected:** Version prints OR command-not-found (both acceptable; uv handles its own Python)
- **Actual:*Not Found*
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A4 — Install uv

- **Expected:** uv binary installed under `~/.local/bin`, PATH updated for new shells
- **Actual:*Success*
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A5 — Open a fresh PowerShell

- **Expected:** Fresh shell, new transcript
- **Actual:*Success*
- **Workaround used:** —
- **Friction class:**
- **Capture:**

### A6 — uv tool install tailor

- **Expected:** Resolves dependencies, installs `tailor` command
- **Actual:*Success*
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
- **Capture:*Terminal from A5 onward through this step recorded*

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

- **P0** — Hard fail. Step cannot complete without intervention beyond documented ritual.
- **P1** — Confusing. Step completes but the recipient would plausibly stop here.
- **P2** — Cosmetic. Step works but the surface is rough.
- **None** — Step worked exactly as documented.

## Workarounds I reached for

> Critical section. Log workarounds you applied AND ones you suppressed. Both are information.
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

## End-of-run capture checklist

- [ ] Friction log saved to `C:\Users\tailor-recipient\Documents\friction-log-2026-05-09-attempt-2.md`
- [ ] Manual terminal-output capture saved (if PowerShell transcript was empty for tailor commands)
- [ ] PowerShell transcript(s) saved at `$env:USERPROFILE\diagnosis-transcript-*.txt`
- [ ] Screenshots in `$env:USERPROFILE\diagnosis-screenshots\`
- [ ] `audit.db` copied
- [ ] Claude Desktop config(s) copied
- [ ] `user_config.json` copied
- [ ] Signed out

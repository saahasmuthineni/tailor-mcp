# Friction log — Path A attempt 1 — 2026-05-09

> **First action before filling this in: Save As to** `C:\Users\tailor-recipient\Documents\friction-log-2026-05-09-attempt-1.md` so the staging copy stays clean for attempt 2.

**Environment**: Fresh tailor-recipient user, Win 11 Home 26200, PowerShell 5.1
**Path attempted**: A (README path)
**Started**: 02:39 (fill in)
**Ended**: HH:MM (fill in)
**Outcome at run-end**: completed cleanly | hard-fail at step Ax | partial success with workarounds (delete the two that don't apply)

## Step-by-step

| Step | Expected | Actual | Workaround used | Friction class | Capture |
|---|---|---|---|---|---|
| A1 | New PowerShell window |Correct | — | | Y |
| A2 | Transcript started message | Y| — | | transcript file path |
| A3 | Python ≥3.10 prints | NO | — | | Yes|
| A4 | uv installed under ~/.local/bin, PATH updated | | — | | |
| A5 | Fresh shell, new transcript | | — | | |
| A6 | uv tool install resolves and installs tailor |Y| — | |Y|
| A7 | `tailor --help` prints subcommand list |Y| — | | |
| A8 | `tailor tour` scaffolds + registers, ends cleanly |note 1 | — | |P0|
| A9 | `tailor demo` prints five-section showcase, ends cleanly | | — | | |
| A10 | Claude Desktop opens | | — | | |
| A11 | Claude Desktop shows tailor server connected | | — | | |
| A12 | Claude lists tailor tool surface | | — | | |
| A13 | `tailor status` reports diagnostic state | | — | | |
| A14 | Transcript saved | | — | | |

## Workarounds I reached for and consciously did not apply

> Critical section. The workarounds you wanted to apply but suppressed.
> Format: "At step Ax: wanted to <workaround>; suppressed; logged the friction."

-
-
-

## Notes

> Anything that doesn't fit the table — surprises, ambiguities, doc-truth gaps observed, second-order observations.

Note ONE:
A8 theoretically works, but claude isnt installed so its stunted from the start.
-Notepad checklist very innefective
-
-

## End-of-run capture checklist

- [ ] Friction log saved to `C:\Users\tailor-recipient\Documents\friction-log-2026-05-09-attempt-1.md`
- [ ] PowerShell transcript(s) saved at `$env:USERPROFILE\diagnosis-transcript-*.txt`
- [ ] Screenshots in `$env:USERPROFILE\diagnosis-screenshots\`
- [ ] `audit.db` copied (if it existed)
- [ ] Claude Desktop config(s) copied (if they existed)
- [ ] `user_config.json` copied (if it existed)
- [ ] Signed out

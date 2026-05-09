# Windows quickstart — running the demo

Hi! This guide walks you through running a small demo I built. It
analyzes synthetic biometric data inside the **Claude Desktop** app.
You don't need any technical background. Follow the steps in order.

About **10 minutes** to set up; the demo itself takes 5 minutes. If
anything looks different from what's described below, take a
screenshot and send it to me before continuing.

---

## What you'll need

- A Windows 10 or 11 PC
- An internet connection
- A free Anthropic account (sign up at <https://claude.ai> if you
  don't have one)
- **Claude Desktop installed and signed in** — download it from
  <https://claude.ai/download>. Plan ~5 minutes for this *before*
  you start the steps below; it's a separate install from Python.
- The file I sent you ending in `.whl` (probably saved to Downloads)
- About 10 minutes

You will **not** need: GitHub, a programming background, or any
participant data. Everything is synthetic and runs on your laptop.

> **One heads-up on Claude free tier.** The demo runs five prompts
> back-to-back. If you're on the free plan and you've already been
> chatting with Claude today, you may bump into the daily message
> cap mid-demo. Best to do this in a fresh sitting and not burn
> messages on warmup chat first.

---

## Step 1 — Install Python (~5 min)

Python is the programming language this tool is built in. **Skip this
step if you already have Python 3.10 or newer installed** (test by
opening PowerShell and typing `python --version`).

1. Open <https://www.python.org/downloads/> in your browser.
2. Click the big yellow **"Download Python 3.12.x"** button.
3. Open the downloaded file from your Downloads folder
   (`python-3.12.x-amd64.exe`).
4. **IMPORTANT** — on the very first install screen, check the box
   at the bottom that says **"Add python.exe to PATH"**. This is the
   single most common thing to miss; if you skip it, every later
   command in this guide will fail with a confusing error.
5. Click **"Install Now"** and wait for it to finish.
6. Click **"Close"**.

**Check it worked.** Press the Windows key, type `powershell`, hit
Enter. A blue/black terminal window opens. Type:

```
python --version
```

and press Enter. You should see something like `Python 3.12.0`. If
instead you see "command not found" or "not recognized", the PATH
checkbox got missed — re-run the installer and make sure it's
checked this time.

Keep this PowerShell window open for the next step.

---

## Step 2 — Install the demo (~2 min)

In the PowerShell window, type:

```powershell
pip install $env:USERPROFILE\Downloads\tailor_mcp-6.9.0-py3-none-any.whl
```

(If I gave you a slightly different filename or version number,
substitute it. If I sent the file via a different path — say to your
Desktop — replace `Downloads` with `Desktop`.)

You'll see a few "Collecting..." and "Installing..." lines stream
past. When you see your prompt come back (`PS C:\Users\...>`), the
install is done.

**Check it worked.** Type:

```
tailor --help
```

You should see a help screen listing subcommands like `serve`,
`pilot`, `tour`. If you see "not recognized", close PowerShell and
open a fresh one, then try again.

---

## Step 3 — Run the tour scaffolder (~1 min)

Type:

```
tailor tour
```

This one command does everything:

- Copies 16 synthetic-participant data files into a working folder
- Writes a configuration file
- Indexes a small notes database
- **Adds the demo to Claude Desktop's configuration automatically**
  — no JSON editing, no copy-pasting paths

You'll see four progress lines:

```
  (1/4) copy bundled fixtures
        force/=17, emg/=17, mrs/=17, vault/=1
  (2/4) write user_config.json
  (3/4) index vault.db
  (4/4) register with Claude Desktop
        wrote entry 'biosensor-tour-hip-lab' to ...
```

If anything different prints (especially red error text), copy the
output and send it to me before continuing.

---

## Step 4 — Restart Claude Desktop and run the demo

Restart Claude Desktop so it picks up the new tour entry:

1. Find Claude Desktop's icon in the **system tray** (near the clock,
   bottom-right). It may be hidden under the small up-arrow `^` —
   click that to expand the tray if you don't see the icon at first.
2. Right-click the icon → **Quit** — *not* just close the window.
   Closing the window leaves Claude Desktop running in the background,
   so reopening it won't pick up the new tour. The right-click → Quit
   step is the one most likely to trip people up; do this even if it
   feels redundant.
3. Re-open Claude Desktop from the Start menu.

In a fresh chat, send these prompts one at a time, waiting for each
response before sending the next.

### Prompt 1 — confirm tools loaded

> List the available biosensor MCP tools.

Claude should list a long set of tool names — `force_csv_*`,
`emg_csv_*`, `vault_*`, `strava_*`. If it says "I don't have MCP
tools" or similar, see Troubleshooting below.

### Prompt 2 — the cohort summary

> Summarize peak isometric force across the cohort, grouped by sex.
> Use the force_cohort_summary tool with metric=max.

Claude calls a tool and gives you average peak forces for the
female and male groups. **The point:** 96,000 raw samples got
reduced to two summary numbers — none of the raw data left your
computer. That's the core value proposition.

### Prompt 3 — single-subject force

> Run force_summary on S004's trial.

You'll see peak force and an MVC window mean for participant S004.

### Prompt 4 — single-subject EMG

> Now run emg_envelope_summary on S004's EMG trial.

You'll get muscle-activity numbers including a fatigue index.

### Prompt 5 — the cross-session memory moment

> Search the vault for any prior notes about subject S004.

Claude finds a saved note "from two weeks ago" flagging the same
elevated EMG amplitude. **The point:** the framework persists notes
across sessions and re-surfaces them keyed by participant ID. This
is what makes it useful for long-running research projects.

That's the demo.

---

## Troubleshooting

| What you see | What to try |
|---|---|
| `python --version` says "not recognized" | Re-run the Python installer; make sure **"Add python.exe to PATH"** is checked on the first screen. |
| `pip install` fails with a permissions error | Close PowerShell, then re-open it as Administrator (right-click PowerShell in the Start menu → **Run as Administrator**) and try again. |
| `pip install` says "no such file" | Check the path matches where the `.whl` file actually lives. Try `dir $env:USERPROFILE\Downloads\biosensor*` to find it. |
| `tailor --help` is "not recognized" | Open a new PowerShell window so it picks up the new install. If still failing, use `python -m tailor --help`. |
| Claude Desktop doesn't list any biosensor tools | Fully quit Claude Desktop via the system tray (right-click → Quit), then re-open. If still missing, run `tailor tour --force` to re-write the Claude Desktop config and restart again. |
| Claude says "the tool errored" on Prompt 2 | Run `tailor tour --force` to re-scaffold the demo data. |
| Vault search (Prompt 5) returns nothing | Same fix — `tailor tour --force`. |
| Anything else | Take a screenshot of the PowerShell window or Claude chat and send it to me. |

---

## When you're done

Nothing runs in the background after you close Claude Desktop —
there's no service to stop. To remove everything later:

1. Delete the folder at `%USERPROFILE%\.tailor\demos\hip-lab\`
   (paste that path into File Explorer's address bar to find it).
2. Open `%APPDATA%\Claude\claude_desktop_config.json` in Notepad and
   delete the `"biosensor-tour-hip-lab": { ... }` block (and the
   comma before it, if any).
3. Optionally: `pip uninstall tailor` and uninstall Python
   from **Settings → Apps**.

---

*Built by your son. Questions about any step — just text me.*

# HIP Lab demo β — video script

> **Purpose**: 5-minute screen-recorded leave-behind for Dr. Senefeld
> (and one colleague he might forward to). Companion to the live
> walkthrough — the live walkthrough is the primary mode; this is
> the artifact that survives the meeting. Pair with
> `one-pager.md` for written reference.
>
> **Setup before recording**:
> 1. Fresh chat — no prior conversation history with Senefeld /
>    HIP Lab / fatigue topics. The v6.5.0 walkthrough caught the
>    LLM name-dropping "Chunyu's thesis" from prior chat history,
>    not from the framework. Fresh chat is the only fix.
> 2. Activate `TAILOR_CONFIG_DIR=examples/hip_lab_demo/beta`
>    and start `tailor serve`.
> 3. Have a 1080p screen recorder ready. OBS Studio works
>    cross-platform; Windows Game Bar (Win+G) works too.
> 4. Disable notifications.
>
> **Recording target**: 5–6 minutes. If a take runs over 7
> minutes, cut from the audit-log section first (it's the most
> compressible).

---

## [0:00 – 0:30] Open

> *Show: terminal at the demo β directory.*

"Hi — I'm Saahas. This is a 5-minute walkthrough of a tool I've
been building called Biosensor MCP. The pitch is: an LLM-assisted
analysis layer for biometric data where the participant data
never enters the LLM's context window — only server-computed
summaries do. The data and configuration on screen are a
synthetic 16-subject sex-differences-in-fatigue dataset shaped
to your 2024 *J Physiol* review on isometric fatigue. The
analysis runs locally, on this machine. I'll show three things
in five minutes."

---

## [0:30 – 1:30] Wow moment 1 — Tier-1 cohort comparison

> *Show: ask Claude (via Claude Desktop or any MCP client):*
> *"Compare time-to-failure between female and male participants
> in this dataset."*

"What just happened: Claude called a tool called
`csv_cohort_summary`, which read all 16 CSV files locally,
aggregated by the `sex` field in `metadata.json`, and returned
**only the cohort-level statistics** — n, mean, std, min, max
per group. The total tokens flowing back to Claude for this
question are under one thousand. None of the per-second force or
EMG values left this machine. The participants' raw biometric
streams have not entered Claude's context, even encrypted, even
once."

> *Pause to let the answer render.*

"For a fatigue study with 16 subjects this is small enough to
not matter. For a study with 100 subjects at 1 kHz sampling, it's
the difference between 'we can use an LLM to help us' and 'we
can't, because the data won't fit and we wouldn't want it to
anyway.'"

---

## [1:30 – 3:00] Wow moment 2 — vault as cross-session memory

> *Show: ask Claude:*
> *"What do you know about subject S004?"*

"Two weeks ago — this is also synthetic, but the timestamp is
load-bearing — someone running this analysis flagged that S004's
EMG envelope was running ~45% above the female-cohort baseline
even before fatigue should drive central-drive compensation.
That observation was captured as a vault note, here:"

> *Show: open the markdown file at*
> *`vault/moments/2026-04-16-s004-emg-force-decoupling-suspected.md`*
> *in any text editor.*

"This file is the source of truth. It's plain markdown, so the
analyst can read it directly in Obsidian; the LLM reads it via a
vault tool. Notice Claude didn't have to be told this file
existed — the framework's reorientation tier indexed it, the
vault tool surfaced it on the question about S004."

> *Show: ask Claude:*
> *"Re-look at the current S004 force trace and tell me whether
> the EMG decoupling pattern still holds."*

"This is the cross-session memory pattern: an analyst captures a
hypothesis in one session, the next session — possibly weeks
later, possibly a different analyst — picks it up automatically
because the LLM's knowledge of the study lives in version-
controlled markdown, not in chat history."

---

## [3:00 – 4:15] Wow moment 3 — audit log reconstructed from `_meta`

> *Show: in terminal,*
> *`sqlite3 ~/.tailor/data/audit.db ".tables"`*
> *then a select-by-subject_id query.*

"Every tool call from the last few minutes is in this SQLite
file: timestamp, who called, what tool, what tier, what
parameters, what subject ID, token estimate, latency, success or
failure, plus a hash of the parameters for tamper-evidence. If
your IRB coordinator asks 'who accessed S004's data on what
date,' this is the answer — a one-line SQL query, no engineer
needed."

> *Show: query for `subject_id = 'S004'` and walk the result
> aloud.*

"Important: the audit row exists for every call, including
denied calls, including PHI-scrubber-flagged calls. Consent
revocation triggers a paired purge of cached biometric data with
its own audit row; analyst-authored vault notes are preserved as
work product. There's an ADR — Architecture Decision Record —
for that, and four others covering the audit log, subject
keying, the PHI scrubber seam, and the rendering policy that
keeps the markdown source-of-truth readable by both analyst and
LLM."

---

## [4:15 – 5:00] Close — what this demonstrates and how to try it

> *Show: the README's "Honest caveats" section briefly.*

"What this demonstrates for HIP Lab specifically: the framework
is shaped for the kind of cohort fatigue work your group does,
the audit-log story is IRB-grade out of the box, and the
local-first architecture means consent revocation is a real
operation rather than a promise about what hosted services
won't do.

What this demo is not: it is not real data. It is sized to a
pilot study. The data shape is post-rectification 1 Hz envelope,
not raw 1–2 kHz EMG — a real version would ingest from the
upstream sampling stage. The PHI scrubber is the no-op default
in this configuration; an institutional scrubber is the load-
bearing piece that lands when a real protocol is identified.

The README at `examples/hip_lab_demo/beta/README.md` lampshades
five honest caveats up front. The companion one-pager covers the
IRB-coordinator question shape. Happy to walk it live whenever
you have time. Thanks."

> *End recording.*

---

## Post-production checklist

- Trim opening / closing dead air.
- Verify no notifications, no other-window flashes, no email
  preview sidebar visible.
- Re-watch once at 2× to catch dead-air gaps and ums.
- Render at 1080p, target file size under 100 MB so it can attach
  to email if YouTube unlisted is not preferred.
- Filename: `tailor-hip-lab-demo-2026-05-DD.mp4` with
  the actual recording date so version tracking is obvious.

## Hosting

Either:
- **YouTube unlisted** — easy to forward, cite-able URL, can
  re-record without breaking the link if you keep the same video.
- **Direct .mp4 in iCloud / OneDrive shared folder** — no Google
  account required for the recipient, slightly more friction.

Recommend YouTube unlisted unless Senefeld has expressed a
preference for not using Google services. The link survives a
re-record (replace the file, link stays the same), which matters
because the demo will likely get a v2 cut after Senefeld's
first feedback.

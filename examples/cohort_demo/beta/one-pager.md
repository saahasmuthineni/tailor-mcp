# Tailor — one-page reference for the demo cohort

> Companion to the live walkthrough and the 5-minute video.
> Written so an IRB coordinator or a non-engineer PI can read
> it end-to-end in two minutes and answer the
> standard data-governance checklist without asking a
> developer.

## What this is

A local-first analysis layer that lets an LLM help analyze
participant biometric data **without the per-second data ever
entering the LLM's context window**. Built originally around
the kind of cohort fatigue work physiology labs do (calibrated to
Hunter & Senefeld 2024 *J Physiol*); generalizes to any
per-subject CSV / EDF / FHIR data shape.

The demo at `examples/cohort_demo/beta/` is synthetic —
sixteen subjects, deterministic seeded generator, sized to a
pilot. The architecture underneath is real and unchanged from
what would run on real data.

## Where the data goes

```
Participant CSVs   ──►  Local server (this machine)   ──►  Cohort
on disk                 ├─ Reads CSVs locally               summary
                        ├─ Computes per-cohort statistics    statistics
                        ├─ Logs every call to audit.db          │
                        ├─ PHI-scrubs the response              │
                        └─ Stamps result with provenance        ▼
                                                          LLM client
                                                          (Claude
                                                          Desktop, etc)
```

**The per-second force / EMG / HR rows do not leave this
machine.** Only cohort-level statistics (n, mean, std, min,
max per group) flow to the LLM. For the demo's 16-subject
question, the LLM-bound payload is under 1,000 tokens; for a
100-subject 1 kHz study it would be roughly the same size,
because the data shape on the LLM-bound side is summary
statistics, not the underlying samples.

## The three-tier access model

The framework requires the LLM client to escalate access
explicitly, with audit and consent at each step:

| Tier | What the LLM sees | Tokens (this demo) | Gate |
|------|-------------------|---------------------|------|
| 1 — Free | Server-computed cohort + per-file reports | 200–1,500 | none |
| 2 — Consent | Downsampled streams at 5–30s intervals | 3,000–7,000 | per-domain biometric consent, session-scoped |
| 3 — Cost | Per-timestamp rows with precision reduction | 25,000–60,000 | consent + cost approval |

Most analytical questions are answerable at Tier 1. The demo
walkthrough never escalates above Tier 1. Tier 2 and 3 exist
for the cases where you genuinely need the underlying samples.

## What's in the audit log

Every tool call lands in `audit.db` (SQLite, on the analyst's
machine):

- Timestamp (UTC)
- Domain and tool name
- Tier accessed (1, 2, or 3)
- Subject ID (when the call is scoped to a participant)
- Parameters (truncated; tamper-evident hash of full params)
- Token estimate sent to the LLM
- Outcome (success, denied by consent gate, denied by cost
  gate, error)
- Latency
- Scrubber ID (so a misconfigured deployment is provably
  distinguishable from a real institutional scrubber)

When an IRB coordinator asks **"who accessed Participant
P004's data on what date,"** the answer is one SQL query
against this file. No engineer needed for routine reads.

## Consent withdrawal

When a participant withdraws consent (`revoke_consent_*`):

- **Cached biometric data** for that domain is purged
  synchronously before the consent revocation completes.
  Failure to purge aborts the revocation with consent intact
  (the analyst is forced to fix the underlying problem rather
  than silently losing both the data and the audit trail).
- **Analyst-authored vault notes** about the participant
  (themes, moments, evidence) are preserved as work product.
  This is a deliberate distinction: notes contain the
  analyst's interpretation, not the participant's biometric
  stream. ([ADR 0013 — Cache-only purge on consent revocation](../../docs/adr/0013-cache-only-purge-on-consent-revocation.md).)
- **Audit rows for the participant** are preserved. They are
  the IRB-grade evidence that the access happened and that
  the purge happened.

## What the analyst configures before real data lands

Five items, all in `user_config.json`:

1. **PHI scrubber subclass** — the framework ships with a
   no-op default by design (the wrong default scrubber is
   worse than none — institution-specific). The analyst
   installs an institutional scrubber subclass, which writes
   its own `scrubber_id` into every audit row.
2. **Vault path** — must not be on cloud-synced storage
   (OneDrive, iCloud, Dropbox). The framework warns at startup
   if this is misconfigured.
3. **CSV directory path** — local filesystem, same warning if
   on cloud sync.
4. **Subject-ID format** for the study (regex pattern).
5. **Local-LLM tier** (optional) — if Ollama is available on
   the analyst's machine, the framework can route narrative
   composition through a local LLM as well, so even the
   *prose* describing the cohort statistics never reaches a
   hosted LLM. This is the v6.6+ guardian feature; the
   underlying numbers are produced deterministically either
   way.

## What this demo is not

- **Not real data.** Sixteen synthetic subjects.
- **Not pre-rectification.** Real surface EMG samples at
  1–2 kHz raw; this demo uses 1 Hz envelope. A real version
  ingests from the upstream sampling stage.
- **Not a clinical decision support system.** No regulatory
  framework addressed; not a substitute for clinical
  judgment.
- **Not a hosted service.** Local-first by architecture,
  not by accident.

## What a lab would need to try this on real data

Conservative estimate, assuming the lab provides one CSV
export of one prior study:

1. ~2–3 days to map the lab's CSV schema into the
   framework's metadata-sidecar pattern (already done for
   any flat per-subject CSV shape).
2. ~4–7 days to implement an institutional PHI scrubber
   covering HIPAA Safe Harbor identifiers and the lab's
   specific quasi-identifier risks (timestamp coarsening,
   demographic bucketing).
3. ~5–8 days for IRB-template fillable sections plus an
   operational runbook (server crashes, audit log rotation,
   recovery from vault corruption).
4. ~1 day for in-person install on the analyst's machine
   plus a five-day check-in.
5. ~4 weeks of passive observation to determine whether the
   tool is actually useful weekly.

Total: roughly two and a half to three and a half months
calendar time from "yes let's try this" to "the analyst is
using it weekly without prompting."

## Whom to ask what

- **Architecture / data flow / IRB-coordinator-facing
  questions**: Saahas. The repo also has
  `docs/design/research-framing.md` written for this audience.
- **Try the demo yourself**: clone the repo, run
  `TAILOR_CONFIG_DIR=examples/cohort_demo/beta
  tailor serve`, then point any MCP client at it. The
  `README.md` in the demo directory has the five honest
  caveats up front.
- **The five-minute video**: `video-script.md` in this
  directory describes what the live walkthrough covers.

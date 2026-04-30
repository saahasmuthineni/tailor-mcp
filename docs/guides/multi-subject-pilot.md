# Multi-subject pilot quickstart

This guide walks a research lab from a fresh clone of the repo to a
working multi-subject pilot in roughly fifteen minutes. The target
shape is the one v6.2 was built around: one PI, one analyst, 5–20
participants, light IRB review, biometric data arriving as CSV
exports (CGM, sleep tracker, ECG patch — anything tabular). For the
single-vendor-API shape (Strava-style OAuth) see the existing
[worked-example notebook](worked-example.ipynb); the steps here apply
identically once OAuth is configured.

The bundled [`examples/multi_subject_pilot/`](../../examples/multi_subject_pilot)
directory ships with three synthetic participants (P001, P002, P003)
so you can verify the end-to-end flow before pointing the server at
real data. Replace the synthetic CSVs with real per-participant
exports when you're ready.

## What you'll have when you're done

- A local MCP server running against your CSV directory
- A multi-subject vault with per-participant themes, moments, and an
  audit log scoped to each `subject_id`
- One analytical conversation with Claude Desktop demonstrating that
  the same theme accumulates evidence stamped per-participant, and
  `vault_search_notes` filtered by `subject_id` returns only that
  participant's results plus any cohort-level themes (per ADR 0009)
- An audit row per call, attachable to a protocol amendment if your
  IRB asks how the analyst accessed the data

## Step 1 — Clone, install, verify

```bash
git clone https://github.com/saahasmuthineni/Biosensor-to-LLM-Connector.git
cd Biosensor-to-LLM-Connector
python -m venv .venv && source .venv/bin/activate    # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
biosensor-mcp --help     # smoke-test the CLI
```

If you see the CLI usage banner, the framework imports cleanly and
you're ready to configure data.

## Step 2 — Inspect the synthetic participants

```bash
ls examples/multi_subject_pilot/csv/
# P001.csv  P002.csv  P003.csv

head -3 examples/multi_subject_pilot/csv/P001.csv
```

Each file is 72 hourly rows over three days, with a single deliberate
"anomaly" hour the LLM will be able to find — a glucose spike on
P001, a nighttime HR spike on P002, a combined excursion on P003.

To regenerate the data (or adjust the participant baselines):

```bash
python examples/multi_subject_pilot/generate.py
```

The generator is deterministic — same seed, same output. Per ADR
0008, all analytical processing in this project is PRNG-free; the
seeded `random.Random(42)` here lives in `examples/`, not on the
analytical hot path.

## Step 3 — Configure the CSV child

Copy [`examples/multi_subject_pilot/user_config.example.json`](../../examples/multi_subject_pilot/user_config.example.json)
to `~/.biosensor-mcp/user_config.json` and replace `<REPO_ROOT>` with
your actual clone path. The relevant fragment:

```json
{
  "csv_dir": {
    "path": "/absolute/path/to/Biosensor-to-LLM-Connector/examples/multi_subject_pilot/csv",
    "timestamp_column": "timestamp",
    "timestamp_format": "%Y-%m-%dT%H:%M:%S",
    "value_columns": {
      "heart_rate": "Heart rate (bpm)",
      "glucose": "Blood glucose (mg/dL)"
    }
  }
}
```

Real-data tip: for a real pilot, name your CSV files by participant
(`P001.csv`, `P002.csv`, …) so an analyst can pass `file_id="P001.csv"`
and `subject_id="P001"` together. The framework does not auto-link
filenames to `subject_id` in v6.2 — that's a deliberate design
boundary (the analyst is the source of truth for which participant a
call is about).

## Step 4 — Register with Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "biosensor-mcp": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "biosensor_mcp", "serve"]
    }
  }
}
```

Restart Claude Desktop. The available-tools panel should now list the
`csv_*` tools (Tier 1 reports, Tier 2 downsampled streams, Tier 3
raw) plus the 25 `vault_*` tools.

## Step 5 — A first multi-subject conversation

In Claude Desktop, try this exchange:

> *"Run csv_summary_report on P001.csv with subject_id="P001". Then
> capture a moment titled 'P001 baseline established' linked to that
> file, also under subject_id="P001". Then upsert a theme called
> 'glucose-spikes' with hypothesis 'P001 shows post-prandial glucose
> excursions' and the same subject_id."*

After Claude executes those calls, repeat for P002 and P003 with
participant-specific themes. Then ask:

> *"What themes have we opened for subject P001 so far? Use
> vault_list_themes."*

The LLM calls `vault_list_themes(subject_id="P001")` and the response
contains *only* P001's themes plus any cohort-level ones (themes
created without a `subject_id` would surface here too — that's the
ADR 0009 IS NULL branch). Ask the same for P002 and P003 and confirm
each call returns a different scope.

## Step 6 — Inspect the audit trail

```bash
sqlite3 ~/.biosensor-mcp/data/audit.db \
  "SELECT timestamp, tool_name, subject_id, scrubber_id FROM audit_log
   ORDER BY id DESC LIMIT 10;"
```

You should see one row per call, with `subject_id` populated when the
LLM passed it. The `scrubber_id` column will read `noop` until you
configure an institutional PHI scrubber (see [ADR 0003](../adr/0003-phi-scrubber-seam.md));
for a light-IRB pilot on synthetic data the no-op default is fine.

## Step 7 — Inspect the vault on disk

```bash
ls ~/.biosensor-mcp/vault/themes/
# glucose-spikes.md  hr-anomaly-p002.md  ...
head -25 ~/.biosensor-mcp/vault/themes/glucose-spikes.md
```

Each theme note carries a `subject_id` line in its YAML frontmatter
when one was provided. Each evidence block emitted under a subject
carries a `> Subject: P001` blockquote line alongside the existing
`> Source: …` provenance.

The vault directory is human-readable Markdown. If you've configured
Obsidian to point at the same path, the same themes, moments, and
dashboards are browseable in Obsidian's UI without any plugin
dependency (per the [rendering-layers policy, ADR 0007](../adr/0007-rendering-layers-policy.md)).

## What v6.2 makes safe

The week-3 failure mode the integration auditor surfaced for this
deployment shape — themes accumulating cross-subject evidence with no
attribution — is structurally prevented:

- A theme's subject is **set-once**: a call attempting to reassign
  `subject_id="P003"` to `subject_id="P007"` returns an error and
  writes nothing.
- Every evidence block stamped under a subject carries that subject
  in its blockquote metadata. A reader scrolling the theme's evidence
  log months later can see whose observation each block describes.
- `vault_search_notes` and the list tools filter on `subject_id` when
  one is provided. Cross-subject themes (those created without a
  `subject_id` — the cohort-level case) stay visible to all subject-
  filtered queries; legacy notes from a v6.1 vault read as
  "subject unspecified" and remain queryable.

## What's still your responsibility

- **PHI scrubbing.** The default `PHIScrubber` is a documented no-op
  ([ADR 0003](../adr/0003-phi-scrubber-seam.md)). The framework does
  not guess what PHI means in your study. For the synthetic pilot
  here this is fine; for any deployment with real participant data,
  either confirm with your IRB that the no-op is acceptable for your
  data sensitivity *or* subclass `PHIScrubber` with a study-specific
  policy and wire it into the router.
- **Manuscript-time export.** Vault freeze (a tool that bundles
  vault+audit+code-version into a submission archive) is roadmap
  work, not v6.2. For now, snapshot the vault directory and copy
  `audit.db` manually when you submit.
- **Multi-analyst attribution.** v6.2 assumes one analyst at a time
  per workstation. The `written_by` field on `vault_generate_snapshot`
  is the partial answer; full multi-analyst attribution on every
  evidence block is roadmap work.

## Next reading

- [Research framing](../design/research-framing.md) — the longer-form
  document for IRB reviewers and PIs evaluating the framework.
- [ADR 0009 — vault subject-keying](../adr/0009-vault-subject-keying.md)
  — the design memo that motivated v6.2's subject scoping.
- [Worked example notebook](worked-example.ipynb) — the same pipeline
  on a single Strava account, including the consent gate and a
  vault round-trip.
- [ROADMAP.md](../../ROADMAP.md) — explicitly deferred work and where
  v6.3+ is heading.

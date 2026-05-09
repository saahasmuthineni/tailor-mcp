# HIP Lab demo — variant β

> **Crude prototype, real architecture underneath.**
> The UI is bare and the data is synthetic. The audit log, the
> three-tier access model, the local-only execution, the
> cross-session vault memory, and the ADR-codified security pipeline
> are real and unchanged from the framework's normal operating
> shape. Two parts of the demo do not change when this gets fixed up
> for a real study; three parts do.

This walkthrough is shaped like a sex-differences-in-fatigue study
that fits the active intellectual thread of the Hunter & Senefeld
2024 *J Physiol* paper on sex differences in human performance.
The data is synthetic, deterministically generated from a seeded
RNG (`random.Random(20260418)`), and shipped with the framework
so re-running `generate.py` on the same machine produces the
same CSVs every time. See *Reproducibility note* at the bottom
for cross-machine caveats.

**The demo is `examples/`-only beyond the new Tier-1 cohort tools
that landed in v6.5.0.** It does not modify framework code; it
exercises the framework's existing operating shape.

---

## Honest caveats — read first

These are surfaced up front, not buried, because the demo's
credibility depends on being honest about what is and isn't real.

- **The data is synthetic.** Sixteen subjects, deterministic seeded
  generator, calibrated to the published sex-difference effect size
  in submaximal isometric fatigue (female time-to-failure typically
  30–100 % longer than male; female peak force lower; female
  decline rate shallower). Group overlap is intentional. The t-test
  for sex difference at n=8 per arm is positive but not
  overwhelming, which is what real fatigue data of this shape
  produces.
- **The data shape is post-quantification.** Real surface EMG is
  sampled at 1–2 kHz raw; this demo uses a 1 Hz envelope,
  abstracting the rectification + envelope-extraction step. A real
  version would ingest from the rectification stage of the lab's
  pipeline. The demo lives at the analyst-facing tier where 1 Hz
  per-channel is the right grain.
- **The PHI scrubber is the framework's no-op default.** Per ADR
  0003, the framework ships a seam, not a policy: institutional
  subclass required for IRB-cleared deployment against real
  participant data. Every successful response carries a
  `_meta.scrubber_warning` field naming this. For the demo, this is
  by design — we are running synthetic data on a development laptop,
  not real participant data.
- **The hypothetical study is not informed by HIP Lab's actual
  current studies.** The shape was picked because it fits the
  framework cleanly and aligns with the lab's most-cited recent
  publication. A real version would mimic an actual lab study; the
  sex-differences-in-fatigue framing is plausible-shape, not
  insider knowledge.
- **`metadata.json` is out-of-band of the PHI scrubber.** The
  sidecar lives next to the CSVs, not inside any tool result, so
  ADR 0003's `PHIScrubber` seam never sees it. A real-deployment
  sidecar must therefore be IRB-cleared at the source: HIPAA Safe
  Harbor §164.514(b)(2) bans the 18 identifier classes (full DOB
  → use age in years; ZIPs to 3 digits; etc.). The demo's
  `metadata.json` schema (`sex`, `age`, `training_h_per_wk`,
  `max_force_baseline_N`) is illustrative on synthetic data only —
  pairing `age` with sex + small-n cohort and a unique
  baseline-force value can land an institution inside expert-
  determination territory under §164.514(b)(2)(i)(B). Real
  deployments should narrow the schema and bucket the identifiers
  before populating the sidecar.

These four caveats are the "rough prototype" half of the pitch.
The next section is the half that does not change.

## What is real (and stays real when fixed up)

- **Audit log.** Every tool call lands in `audit.db` with timestamp,
  domain, tool, tier, parameter JSON, token estimate, outcome,
  latency, and (when scoped) `subject_id` + `scrubber_id`. ADR 0001.
  Re-runnable; not editable post-hoc; the methods-section sentence
  *"all analyses performed locally; no participant biometric data
  transmitted to hosted LLMs"* is technically true at the moment
  of every call.
- **Three-tier access model.** Tier 1 is server-computed reports
  with no streams entering LLM context. Tier 2 is downsampled
  streams behind a per-domain consent gate. Tier 3 is full streams
  behind cost approval. The new `csv_cohort_summary` tool used in
  Wow Moment 1 is Tier 1 — cohort comparison is computed on the
  laptop and only the result table (n, mean, std per group) reaches
  the LLM. ADR 0015.
- **Vault as cross-session analytical memory.** A subject-keyed
  moment from "two weeks earlier" persists as a markdown file on
  disk (`vault/moments/2026-04-16-s004-emg-force-decoupling-suspected.md`),
  is indexed by SQLite, and surfaces in the new session when the
  LLM searches the vault for `subject_id: S004`. ADR 0009.
- **`_meta` provenance stamps.** Every successful result carries
  `package_version`, `tool_name`, and a UTC `called_at` timestamp.
  The minimum-viable provenance for results that may end up in a
  paper.
- **ADR-codified security pipeline.** Param validation → circuit
  breaker → consent gate → cost gate → PHI-scrub seam → audit log,
  in that order, on every call. ADR 0001 / 0003 / 0005.

---

## Setup (one terminal command)

From the repo root:

```bash
python examples/hip_lab_demo/beta/setup.py
```

This is idempotent. It (1) generates 16 synthetic per-subject CSVs
from a seeded RNG (`generate.py`), (2) writes `metadata.json` next
to them with sex / age / training-volume / baseline MVC per subject,
(3) writes `user_config.json` in this directory pointing at the
absolute paths of `csv/` and `vault/`, and (4) lays down the S004
EMG/force-decoupling seed moment at `vault/moments/2026-04-16-...md`.

To start the server isolated from your normal `~/.tailor/`
config:

```bash
TAILOR_CONFIG_DIR=$(pwd)/examples/hip_lab_demo/beta tailor serve
```

This sets `TAILOR_CONFIG_DIR` to this demo directory, which the
framework reads for `user_config.json`. `TAILOR_DATA_DIR` defaults
to `$TAILOR_CONFIG_DIR/data` — so `audit.db` and `vault.db` are
also isolated to `examples/hip_lab_demo/beta/data/`.

**This avoids the `tailor pilot` wizard path on purpose** —
the wizard writes to `~/.tailor/user_config.json`, which
would clobber your real CSV setup. The env-var-based invocation
keeps everything inside this directory.

### Wiring up Claude Desktop

If running the demo through Claude Desktop, add to
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tailor-hip-demo": {
      "command": "/path/to/your/python",
      "args": ["-m", "tailor", "serve"],
      "env": {
        "TAILOR_CONFIG_DIR": "/path/to/Biosensor-to-LLM-Connector/examples/hip_lab_demo/beta"
      }
    }
  }
}
```

Restart Claude Desktop. The demo registers as `tailor-hip-demo`
so any sibling tailor registration (e.g. your real pilot
setup) keeps working in parallel.

### Walk this in a fresh chat

A subtle hazard worth naming: Claude Desktop's conversation-history
feature lets the LLM reference prior chats. If the demoer has
existing conversation history about this lab, that history bleeds
into what looks like demo output — names of grad students, mention
of specific theses, lab-specific framings — and over-rates the
framework's actual contribution. **Start a new chat** before
walking through the wow moments, and ideally clear conversation
history if the evaluator wants the cleanest possible signal. What
you're evaluating is what the framework + general LLM knowledge
produces given the cohort table; not what your prior chats with
Claude can dredge up.

---

## The three wow moments

Each prompt is exactly what to type into the LLM. Expected outputs
are sketches — the actual numbers come from the seeded generator
and are stable across machines.

### Wow 1 — instant cohort analysis at Tier 1, no streams in LLM context

> **Prompt:** *"Compare time-to-failure between male and female
> subjects. Use whichever Tier-1 tool fits — I want to see this
> without any streams entering your context."*

**What the LLM does:**

1. Calls `csv_list_files` (~200 tokens) — sees 16 subject CSVs.
2. Calls `csv_cohort_summary(column="force_N", group_by="sex",
   metric="duration_s")` (~300 tokens). The tool reads every CSV,
   reduces each to its duration in seconds (time-to-failure under
   this protocol), groups by the `sex` field from `metadata.json`,
   and returns:

   ```
   F: n=8, mean=665.4, std=92.8, min=549.0, max=806.0
   M: n=8, mean=398.4, std=66.2, min=303.0, max=503.0
   subjects-per-group: { F: [S001, S003, S004, S006, ...],
                         M: [S002, S005, S007, ...] }
   ```

3. The LLM presents this as a cohort table and notes the female
   advantage of ~265 s (~4.5 min) — consistent with the published
   sex-differences-in-fatigue literature.

**Why this lands:**

- Total tokens entering the LLM context: ~500. Per-second streams
  for 16 subjects × 660s mean × 5 columns = ~52,800 rows; **none
  of those rows touched the LLM**. The cohort comparison was
  computed on the laptop and the LLM only saw the per-group
  summary.
- The same question can be asked at Tier 2 if the analyst wants
  the trace-level evidence (`csv_downsampled` per subject), but
  the consent gate will fire and the audit log will record every
  Tier-2 call. The architecture makes the choice visible.

**To verify the no-streams claim:**

> *"What's in the audit log for this query?"*

The LLM (or you, opening `data/audit.db`) sees Tier-1 rows only.
No `csv_downsampled` calls, no `csv_raw_stream` calls.

### Wow 2 — the vault surfaces a prior session's moment

> **Prompt:** *"Search the tailor vault for any prior notes
> on subject S004 and tell me how those observations relate to her
> data in this protocol."*

**A note on prompt phrasing.** The earlier draft of this prompt
read *"What do you know about S004 from prior sessions"* — which
real-world LLMs interpret as "search your conversation memory,"
not "search the tailor vault." The vault is a separate
durable store the LLM accesses through tools, so the prompt has
to point at it explicitly. This is the kind of friction a research
team would discover the first time they ran the demo; we surfaced
it on our own walkthrough and tightened the prompt accordingly.
The framework's vault tools work; the discoverability lives in
how the prompt invites their use.

**What the LLM does:**

1. Calls `vault_search_notes(query="S004", subject_id="S004")` —
   surfaces the seed moment at
   `moments/2026-04-16-s004-emg-force-decoupling-suspected.md`.
2. Calls `vault_read_note` to pull the body — sees the prior
   observation: high EMG envelope without commensurate force change,
   suggesting central-drive compensation / overreaching.
3. Calls `csv_force_decline(file_id="S004.csv", column="force_N")`
   for fresh data. Returns peak ~140 N, decline rate ~3 % / min,
   decline-rate-per-minute and time-to-50%-drop fields.
4. Calls `csv_force_decline(file_id="S004.csv",
   column="emg_envelope_uV")` — peak EMG envelope, decline rate.
5. Compares fresh data against the prior moment's claim. Notes
   that S004's EMG-to-force ratio in this session is consistent
   with the prior observation — the pattern persists.

**Why this lands:**

- A prior session's analytical observation, recorded as a markdown
  file, surfaces alongside fresh data **two weeks later** without
  any chat history being preserved. The vault is the cross-session
  analytical memory layer — the thing that's missing when LLM-
  assisted analysis happens in chat windows.
- The subject_id keying means the prior moment surfaces specifically
  for S004, not as a vague "I think someone had unusual data once."
  ADR 0009.
- Re-running the same prompt on a different subject (e.g. S001)
  surfaces nothing — there's no seed moment for S001. The vault is
  honest about what it does and doesn't know.

### Wow 3 — audit log = methods section + IRB continuing-review evidence

> **Prompt:** *"Give me a CSV-formatted dump of every tool call in
> this session: timestamp, tool, tier, subject_id, outcome."*

**What the LLM does:**

1. Reads `data/audit.db` (or asks you to). Per ADR 0001, every call
   is recorded.
2. Returns a tabular dump like:

   ```
   timestamp                  tool                  tier  subject_id  outcome
   2026-04-30T14:02:11.221Z   csv_list_files         1    None        SUCCESS
   2026-04-30T14:02:14.847Z   csv_cohort_summary     1    None        SUCCESS
   2026-04-30T14:02:31.103Z   vault_search_notes     1    S004        SUCCESS
   2026-04-30T14:02:33.418Z   vault_read_note        1    S004        SUCCESS
   2026-04-30T14:02:38.740Z   csv_force_decline      1    S004        SUCCESS
   ...
   ```

3. You point out that this is the methods-section traceability.
   Every call: durable evidence the analyst saw exactly this data,
   in this order, with this tier. The schema columns are
   `timestamp, domain, tool_name, tier, params, token_estimate,
   outcome, duration_ms, error, subject_id, scrubber_id` — see
   `framework/audit.py`. For IRB continuing-review the queryable
   facts are: *"Tier-2 access count by session" — a SQL group-by
   on `tier` and `timestamp`; "consent gate state" — separate
   audit rows on every `approve_consent_*` / `revoke_consent_*`
   dispatch (the gate fires at every Tier-2 / Tier-3 call but
   per-call consent re-affirmation is the gate's behaviour, not a
   per-row column).* That's the precise framing — over-claiming a
   "per-row consent attestation" is the kind of engineer-speak
   that lands wrong on a compliance reader, so we don't.

**Why this lands:**

- Hosted LLM chat windows leave no auditable trace of what the
  analyst actually saw. This does. The audit log is the durable
  evidence of how an analyst accessed participant data — *the
  single most load-bearing feature for research use* (CLAUDE.md
  *§ Problems this is built against*).
- `subject_id` scoping (ADR 0002) means subject-level audit
  filtering is a SQL query: `SELECT * FROM audit WHERE
  subject_id = 'S004' AND tier >= 2 ORDER BY ts;`.
- `scrubber_id` (ADR 0003 / v6.3.1) on every row distinguishes
  default-noop deployments from institutional-subclass deployments.
  At-a-glance: did this analysis run with HIPAA-policy scrubbing
  installed, or not? The audit row knows.

---

## What is rough (and changes when fixed up)

| Rough piece | What changes for a real study |
|---|---|
| Synthetic CSVs from `generate.py` | Real per-subject CSV exports from REDCap / lab acquisition system |
| 1 Hz EMG envelope | Lab-pipeline raw EMG → rectification → envelope, ingested at the envelope tier |
| `metadata.json` written by hand | REDCap export script generates the sidecar |
| No PHI scrubbing policy installed | Institutional subclass of `PHIScrubber` per ADR 0003 |
| One worked-example child (`csv_dir`) | Add an EDF/ECG child for the 9.4 T scanner exports, plus whichever vendor SDKs the lab uses |
| Single-analyst vault | Per-analyst attribution on evidence blocks (ROADMAP.md item — small effort, medium impact) |

The architecture surface is unchanged for any of these — every
fix-up lives behind the same router pipeline, the same audit log,
the same vault.

---

## What an evaluator should look at

Three things, in order:

1. **Open `data/audit.db` after running through the demo.**
   `sqlite3 data/audit.db 'SELECT ts, tool, tier, subject_id,
   outcome FROM audit_log ORDER BY ts;'`. Every call you made,
   recorded with provenance.
2. **Open `vault/moments/2026-04-16-s004-emg-force-decoupling-suspected.md`
   in any text editor** (Obsidian, VS Code, vim, less). The vault
   is plain markdown with YAML frontmatter — durable, AI-readable
   without the framework, and the analyst's editor view is the
   same as the LLM's read view. ADR 0007 rendering-layers policy.
3. **Open `examples/hip_lab_demo/beta/csv/metadata.json`**. The
   sidecar is the cross-file group-identity mechanism (ADR 0015).
   No magic — JSON, schema documented, edit-by-hand. A real study
   replaces this with a generated artifact from the lab's data
   pipeline; the framework's contract is unchanged.

Everything else — the seven CSV-directory tools, the consent
prompts, the vault wikilink graph, the audit-log SQL — is the
framework's normal operating shape. The demo is one config plus
one walkthrough. The bones are not the demo.

---

## Reproducibility note

The synthetic CSVs are produced by a single seeded RNG
(`random.Random(20260418)`). Re-running `generate.py` on the
**same machine** produces byte-identical CSVs every time, which
is what the demo depends on. Cross-machine identical replay is
*not* verified: `random.gauss` calls `math.log` / `math.sqrt`,
which are not IEEE-754-mandated correctly-rounded across libm
implementations on Windows / macOS / Linux. ULP-level divergence
in the underlying transcendentals could occasionally tip a
2-decimal-rounded `force_N` value across a boundary on a
different OS. The cohort-level effect (female TTF longer than
male) is robust to this; per-row byte-identical replay across
machines is not claimed. The audit log timestamps obviously vary
per call — they record the actual moment of each call. ADR 0008.

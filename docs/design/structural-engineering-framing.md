# Tailor for a Structural Engineering Student

*A framing for the undergrad civil engineer heading toward structural — what
this tool is, why it matters for the kind of work you're about to walk into,
and what you could actually do with it as a student.*

This is the longer-form pitch. Readable in about fifteen minutes. If you only
read one section, read **"The world you're walking into"** below and then jump
to **"Things you could actually build"**.

---

## TL;DR

**Tailor is a local-first framework that lets an AI assistant (Claude, etc.)
work with your own data — sensor streams, simulation outputs, inspection
records, analytical notes — without that data ever leaving your laptop, with
every operation recorded in an audit log, and with a memory layer that
survives across chat sessions.**

It was built for biomedical research, with high-frequency biosignals as the
worked example. But the *architecture* — server-side computation over high-rate
streams, tiered access to raw data, durable analytical memory, defensible
audit trails — is exactly the shape a modern structural engineer needs.

You won't find a `bridge_health_monitor` child in the repo today. But the
extension point that would let you write one in a weekend (literally:
`src/tailor/children/template/` is a copy-and-rename starter kit) is the
explicitly-supported way the framework expects new data sources to land.

---

## The world you're walking into

Structural engineering is in the middle of three shifts that haven't fully
landed yet. By the time you're a licensed PE — five to seven years from now —
they will have:

**1. Sensors got cheap.** A MEMS-based three-axis accelerometer costs $5 on a
breakout board. Fiber-optic strain sensing (Brillouin scattering) instruments
every meter along a kilometer of bridge cable. Vibrating-wire piezometers
embedded during foundation pours stream pore-pressure data for the structure's
lifetime. The data is no longer the bottleneck; the bottleneck is doing
something useful with it.

**2. Design is going performance-based.** ASCE 41 retrofit assessments, ASCE 7
risk-targeted maximum-considered earthquake (MCE_R) ground motions, PEER's
performance-based earthquake engineering (PBEE) framework — the question
shifted from "does this satisfy a prescriptive code?" to "what is the demand-
to-capacity ratio under a 2475-year hazard, and what does the failure look
like if we exceed it?" That's a question about *streams of analysis*, not a
single calculation.

**3. AI is going to be in the workflow.** In five to ten years, structural
engineers will have AI assistants. The interesting question isn't *whether*;
it's *what shape*. Two extreme answers:

- **A.** A chatbot you copy-paste into. Lossy, leaky, leaves no audit trail,
  forgets between sessions, can't see your project's history.
- **B.** A system that's been *instrumented* to know what structure you're
  analyzing, what data you've already seen, what hypotheses you've formed,
  what failure modes the team has ruled out, and what answer you actually
  need (a scalar capacity ratio, not a million-sample acceleration trace).

Tailor is a proof-of-concept of answer B, in a different domain (biomedical
research), with the architecture deliberately designed so that "swap the
domain" is a feature, not a rewrite.

`✶ A note on why this isn't just a wrapper around ChatGPT ─────`
Most "AI for engineering" demos today are answer A with extra steps — a
prompt template, a vector store, maybe a code-interpreter handoff. They
fundamentally cannot solve the four problems below because the data and
the audit trail still flow through the hosted service. Tailor's bet is that
the *architecture* matters more than the model: a local server that runs
the analysis, a tier model that returns *the answer* not *the data*, and a
durable record of every operation. The model behind the chat window is
hot-swappable; the substrate is what you build on.
`──────────────────────────────────────────────────────────────`

---

## Why this matters for structural specifically

Structural work has four properties that play unusually well with what
Tailor was designed for. Each one maps onto a problem Tailor explicitly
names as built-against:

### 1. Data governance — your client's data isn't yours to leak

The owner of a building, bridge, or dam typically does not want detailed
information about which structural members are degrading floating out into a
hosted-AI service. There's a confidentiality dimension (the engineering firm's
contractual obligation), a security dimension (knowing which members of a
critical-infrastructure structure are weak is a target-selection signal), and
a litigation dimension (anything sent to a third party can be subpoenaed and
discovered).

Tailor's response is the same as for biomedical: the server runs *next to*
the data, on your workstation. Only computed summaries cross the boundary
between your machine and the AI model. Raw sensor streams never leave.

### 2. Reproducibility — you sign your work, and someone might ask in five years

PE professional liability is a different beast from undergrad coursework. You
will sign and seal calculations. If a structure has a serviceability problem,
a failure, or a litigation event years later, the questions are:

> What data did you look at? What assumptions did you bring in? What numbers
> came out? Show your work.

Tailor's audit log (every tool call recorded in SQLite with timestamp,
parameters, outcome, and optional `subject_id` / `structure_id` scoping) is
the durable-trace problem for the PE world. It was built for IRB review; PE
review wants the same thing under a different name. The `_meta` block stamped
on every result (package version, tool name, UTC call time, tier, scrubber
identity) is the engineering-record equivalent of a calculation header.

### 3. Longitudinal analytical memory — buildings outlive chat sessions

A bridge has a 75-100 year design life. The structural health monitoring
program on it might span 30 years. An observation an engineer made during the
2024 inspection ("Sensor 7 on Pier 3 appears to drift in cold weather; results
from January reads are unreliable") needs to inform the 2039 inspection — by
which time the original engineer has retired.

Tailor's *vault layer* is exactly this. It's a structured collection of:

- **Themes** — persistent hypotheses the team keeps returning to ("modal
  damping ratio on Span 4 has been creeping up since the 2024 retrofit").
- **Moments** — observations worth remembering across sessions ("operator
  noticed unusual signature during the seismic event of 2026-03-12").
- **Evidence** — specific data windows that ground a theme ("FFT of accel
  data 14:23–14:25 on event date shows 2.3 Hz mode signature").
- **Failure modes** — documented dead-ends so the team doesn't suggest them
  again ("Sensor 11 known to be offline post-event; exclude").

All stored as plain markdown files in an Obsidian vault — human-readable,
git-versionable, your team can read them without Tailor present. The AI just
reaches into the same notes a human would write.

### 4. AI economics — high-rate data is exactly the problem the tier model solves

Modern accelerometers sample at 100-2000 Hz. A week of data from a 16-sensor
bridge array at 500 Hz is on the order of *one billion samples*. You will
never load all of that into an AI's context window. You shouldn't *want* to.

Tailor's three-tier access model is the structural answer to the data-volume
question. For a structural example:

| Tier | What the AI sees | Approx. tokens | Gate |
|------|------------------|---------------|------|
| 1 — Free | Server-computed: modal frequencies, peak responses, drift indices, exceedance counts per period | 200–1500 | None |
| 2 — Consent | Downsampled time series (1 Hz or coarser) suitable for visualization | 3000–7000 | Authorization |
| 3 — Cost | Full per-sample data with precision reduction (only when you really need it) | 25000+ | Authorization + cost gate |

"Did peak acceleration during last week's seismic event exceed the design
level?" should never load a million samples into the AI's context. It is a
single Tier 1 computed scalar. The framework makes that the *default*, not an
optimization.

`✶ Insight — this is the cost-quality lever ────────────────────`
The Tier 1 win is simultaneously a cost lever (token-per-question drops by
1-2 orders of magnitude) and a *cognition* lever (the AI's freed context
budget goes to reasoning about your prior analysis, the audit log, and the
question — not to data shuffling). The same architectural choice that
satisfies the governance problem makes the AI materially better at the
question. See ADR 0029 (Amended 2026-05-12) for the longer argument under
the "AI economics" umbrella claim.
`──────────────────────────────────────────────────────────────`

---

## The architecture in five minutes

Here's the picture, with structural-engineering analogues for the abstract
terms:

```
AI client (Claude, etc.)
   ↕  (MCP protocol over stdio — runs locally)
RouterMCP — owns cross-cutting concerns:
   • parameter validation (reject bad inputs fast)
   • circuit breaker (back off if a data source keeps failing)
   • authorization gates (per-domain consent for sensitive data)
   • cost gate (pre-estimate tokens before loading large streams)
   • audit log (every call recorded with optional structure_id scoping)
   ↕
ChildMCP — one per data source. You write a new one for each source:
   • SHMChild         — wraps your bridge sensor exports
   • FEAResultChild   — wraps your SAP2000 / ETABS / OpenSees output
   • InspectionChild  — wraps your inspection database
   • Vault layer      — durable cross-session notes (themes, moments,
                         failure modes, evidence)
```

### The router

Owns everything cross-cutting. You don't reimplement consent or audit per
data source — the router handles it once for every child. As an undergrad
this should feel familiar: it's the *separation of concerns* principle from
your software-design intro course, applied to engineering workflows.

### Children (ChildMCP)

Each child wraps one data source and exposes *tools* the AI can call. The
worked example (`children/running/`) wraps Strava's API for biomedical
runs. The two existing generic children:

- `csv_dir/` — wraps any directory of CSV files. Works today for: anything
  exported from LabVIEW, vendor SHM software that dumps CSV, strain-gauge
  loggers, weather-station data, displacement-transducer recordings.
- `matlab_file/` — wraps `.mat` files (scipy-loaded, v5/v6/v7.2; v7.3 HDF5
  deferred). Useful for: anything coming out of MATLAB-based academic work
  in earthquake engineering or SHM. The PEER tools, a lot of UCB and Caltech
  research code, OpenSees post-processing — all of this dumps `.mat`.

The `children/template/` directory is a runnable starter kit. Copy it,
rename, fill in four methods, and you have a working child.

### The Wardrobe (vault)

Internally we call it the *vault layer* — externally it's the **Wardrobe**:
your AI's structured memory of what it's been told about your structures.
Stored as plain markdown in an Obsidian vault on your disk. The AI reads
from and writes to the same notes a human would maintain.

The split is deliberate: data lives in the children (ephemeral, rebuildable),
analytical memory lives in the Wardrobe (durable, the canonical record). The
audit log is a third store called the **Ledger** — the tailor's own record
of what work was done on your behalf. The Ledger is for compliance and
provenance; the Wardrobe is yours.

### The three tiers

Already covered above. Worth re-stating in structural-engineering terms: the
default mode of asking the AI about your structure is "let the server compute
the answer; return the answer." Raw streams cross the boundary to the AI only
when you've explicitly authorized it for that data source, and they cross
*expensively* (Tier 3) only when you've also approved the cost.

---

## Things you could actually build as a student

This is the section that should give you something to do this weekend, this
summer, or for senior design. The framework's extension model — write one
new `ChildMCP` per data source — is the explicit entry point.

### Project 1 — SHM data explorer (weekend-scale)

The U.S. Geological Survey runs the [Strong Motion Project][usgs-smp]; the
Center for Engineering Strong Motion Data (CESMD) publishes accelerometer
records from earthquake events on instrumented structures. Buildings,
bridges, dams, free-field arrays. Records are available as CSV or COSMOS V2.

[usgs-smp]: https://www.usgs.gov/programs/earthquake-hazards/strong-motion-project

**What you'd do:** Copy `children/template/`, rename to `cesmd_records/`,
parse the CSV format, expose three tools:

1. `cesmd_event_summary` (Tier 1) — peak ground / floor accelerations,
   spectral response at common periods (T=0.3s, 1.0s, 3.0s), Arias
   intensity.
2. `cesmd_downsampled` (Tier 2) — decimated time history for plotting.
3. `cesmd_raw_record` (Tier 3) — full per-sample data.

**What you learn:** ChildMCP extension pattern. Tier model in practice.
Audit log structure. How AI assistants reason over engineering data when
they aren't given the raw stream by default.

### Project 2 — OpenSees post-processor (week-scale)

[OpenSees][opensees] is the Berkeley earthquake-engineering FEA package. Free,
open source, used in a lot of PBEE academic work. It dumps results to CSV or
binary recorder formats.

[opensees]: https://opensees.berkeley.edu/

**What you'd do:** Build an `opensees_results/` child that wraps a model's
output directory. Tools:

1. `opensees_model_summary` (Tier 1) — number of nodes, elements, modal
   periods, applied loads, max displacement / drift / base shear.
2. `opensees_element_response` (Tier 1) — query a specific element's
   demand-to-capacity envelope.
3. `opensees_downsampled_response` (Tier 2) — node displacement time history.
4. `opensees_full_response` (Tier 3) — full nodal results for one node.

**What you learn:** how to expose a non-trivial simulation output to an AI in
a way that makes the AI useful for *review* rather than just data shuffling.
Strong project for a structural-dynamics or earthquake-engineering elective.

### Project 3 — Senior design data backbone (semester-scale)

If your capstone involves any kind of instrumented test (concrete beam
testing, scaled-frame shake-table work, wind-tunnel section model), Tailor
gives you a free data-governance and reproducibility backbone.

**What you'd do:** Configure the existing `csv_dir/` child against your test
data directory. Use the vault layer to record your team's hypotheses, test
plans, and observations. Use the audit log to defend your analytical
decisions in your final report. Optionally: write a small child specific to
your DAQ system's output format.

**What you learn:** What it actually feels like to do engineering with a
defensible audit trail and durable cross-session memory. This is closer to
how mature research labs and consulting firms operate than to undergraduate
lab reports. It's also the closest thing to a "PE workflow simulator" you'll
get before the EIT exam.

### Project 4 — Research-experience pitch (REU / lab-rotation scale)

Most SHM and earthquake-engineering research labs work with high-rate sensor
data and don't have a clean story for how their AI-assisted analysis stays
reproducible. Offering to *build the substrate* — wire their data source into
a Tailor child, set up their vault, configure their audit log — is a much
more interesting pitch to a PI than "I'd like to do undergrad research" with
no specific deliverable.

The realistic shape: 8-10 weeks of work. Output: a deployment-ready
data-governance backbone for the lab plus a write-up of the architectural
decisions. Co-authorship potential on whatever paper uses it next.

---

## What's not there yet (honest)

I want to be upfront about what *doesn't* exist today, because over-promising
is the structural-engineering version of bad faith:

- **No FEA-specific children today.** The OpenSees / SAP2000 / ETABS /
  Abaqus / ANSYS adapters would all need to be written. The template is in
  the repo; the actual writing is on you.
- **No BIM integration.** Revit, Tekla, IFC — none of it. Could be built.
- **No code-checking AI.** The framework gives the AI good *access* to
  your structure data; it does *not* embed ASCE 7 / ACI 318 / AISC 360
  knowledge. That kind of code-reasoning is a different problem (a lot of
  the work happens at the prompt / cue-card layer, not the framework layer).
- **The compliance lens is health-research-shaped.** Tailor's PHI scrubber
  and HIPAA-Safe-Harbor framing don't translate one-to-one to PE liability,
  client confidentiality, and critical-infrastructure-security concerns.
  The *architecture* (a scrubber seam at the framework boundary) is exactly
  right; the *content* of what gets scrubbed would need a new policy.
- **No production deployments in structural work yet.** Tailor's first
  recipient deployments are in the health-research domain. A structural
  deployment would be a forcing function — exactly the kind of thing a
  motivated undergrad could land first.

---

## Where to start if you want to play

Five minutes of setup, then a working install you can actually break:

```bash
# Recipient install (uv is faster and doesn't need a Python env)
uv tool install tailor-mcp

# Sanity-check
tailor --help

# Walk through the bundled demo (synthetic biomedical data — shows you the
# tier model, the vault, the audit log working end-to-end)
tailor walkthrough

# Set up your own data
tailor pilot   # three-prompt wizard for a CSV directory
```

Then read, in this order:

1. [README.md](../../README.md) — the audience-facing overview.
2. [CLAUDE.md](../../CLAUDE.md) §"Architecture" + §"Adding a New ChildMCP" —
   the structural picture.
3. `src/tailor/children/template/` — the starter kit. Look at how short
   `child.py` is. That's the surface area you have to fill in.
4. [docs/adr/](../adr/) — the architecture decision records. ADRs 0001
   (audit log), 0003 (scrubber seam), 0008 (deterministic-by-construction
   processing), 0009 (subject-id scoping), and 0029 (AI economics) are the
   load-bearing ones if you want to understand *why* the framework is shaped
   the way it is.

If you build one of the projects above, the next interesting question is:
"could this be the analytical backbone for the structural engineering
deployment recipe?" Health research is the first recipe Tailor shipped
end-to-end. Structural is — honestly — one of the most natural second
recipes. The four problems map almost perfectly, the data shapes
(high-frequency streams, longitudinal records, audit-trail requirements)
are the same shape, and the field is at exactly the right point in its
AI adoption curve to want this.

---

## Adjacent reading

Because the most useful thing a doc like this can do for a student is point
at the right rabbit holes:

- **Structural health monitoring as a field.** Farrar & Worden, *Structural
  Health Monitoring: A Machine Learning Perspective* (2013). The classic
  textbook; sets up the data-driven framing.
- **Performance-based earthquake engineering.** The PEER Center's
  publications page; specifically the PBEE methodology papers (Cornell &
  Krawinkler, Moehle & Deierlein).
- **MCP, the protocol Tailor speaks.** [modelcontextprotocol.io][mcp]. The
  spec is short and readable.
- **The architecture decision records in this repo.** Linked above. They
  are the closest thing to a structural-engineering-style technical
  specification you'll see in a software project — load-bearing decisions
  recorded with their context, alternatives, and reversal conditions, the
  way an SE report records why a beam size was chosen.

[mcp]: https://modelcontextprotocol.io/

---

The short version of all of this: Tailor is the substrate AI-assisted
structural engineering work *should* run on in five years. The first version
got shipped in a different domain because the first author works in
biomedical research. The architecture was deliberately built to generalize.
The structural-engineering recipe is one motivated undergraduate's senior
project (or REU summer, or first job at the right kind of consulting firm)
away from being real.

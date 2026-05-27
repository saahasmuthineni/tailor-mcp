# Contributing a new ChildMCP

Children are the framework's extension point: one child wraps one data source (a vendor API, a directory of files, a binary export, a clinical-data registry) and exposes tiered tools. The router handles consent, cost, audit, PHI scrubbing, and `_meta` provenance uniformly — your child does not.

This guide walks through writing a new child. For the architectural argument behind the pattern, see [CLAUDE.md § "Adding a New ChildMCP (new data source)"](CLAUDE.md#adding-a-new-childmcp-new-data-source). For general contribution conventions (branching, commit format, lint), see [CONTRIBUTING.md](CONTRIBUTING.md).

## Two onboarding paths

Before writing a new child, check that one of the shipped children (`csv_dir`, `matlab_file`, `redcap`) doesn't already understand the shape of your data. If it does, the [`tailor pilot`](src/tailor/pilot.py) wizard configures it in three prompts — no Python required. This guide is the **L2 path**: a vendor format, an EDF recording, a FHIR bundle, a custom binary, or anything else that doesn't fit a shipped child. Budget ~1–2 days of focused Python work.

## Start from the template

```bash
cp -r src/tailor/children/template src/tailor/children/<yourdomain>
cp -r tests/children/template       tests/children/<yourdomain>
```

Rename the classes:

- `TemplateChild` → `<Yourdomain>Child`
- `TemplateProcessing` → `<Yourdomain>Processing`

The template ships with `# FILL IN:` markers at every spot you need to touch. Work through them in order — the comments name what each blank is for and link to the running-child equivalent.

## Structural reference

When you're unsure how a real child handles a particular structural concern (cohort surfaces, sidecar metadata, child-level PHI scrubbing, lazy optional-dependency imports), read [`src/tailor/children/csv_dir/`](src/tailor/children/csv_dir/). It is the most complete worked example among the shipped children: three-tier surface, optional `metadata.json` sidecar for cohort grouping, no OAuth, no vendor API, no optional extras. For richer cases:

- API + OAuth + rate limiting + caching: [`src/tailor/children/running/`](src/tailor/children/running/)
- Binary format with an optional dependency: [`src/tailor/children/matlab_file/`](src/tailor/children/matlab_file/) (scipy is in the `[matlab]` extra; the child imports it lazily inside handler bodies)
- Domain-specific structured-PHI scrubbing: [`src/tailor/children/redcap/`](src/tailor/children/redcap/) (ships `RedcapPHIScrubber` per [ADR 0003 § Amendment 2026-05-14](docs/adr/0003-phi-scrubber-seam.md))

## The contract

Subclass `tailor.framework.ChildMCP` and implement seven members. The template's `# FILL IN:` markers correspond 1:1 with this list.

| Member | What it is |
|---|---|
| `domain` (property) | Short identifier (`"cgm"`, `"sleep"`, `"redcap"`). Used in audit rows, consent keys, and Claude Desktop's tool listing. Must be unique across registered children. |
| `display_name` (property) | Human-readable name (`"Glucose (Dexcom)"`). Surfaced in consent prompts. |
| `consent_info` (property) | `ConsentInfo(data_types=[...], purpose=...)`. The two strings the analyst sees when granting biometric consent. Be specific — the consent prompt is the IRB-relevant artifact. |
| `tool_definitions` (property) | List of `ToolDefinition(name, tier, description, schema)`. One entry per tool you expose. Tiers are 1 (free), 2 (consent), 3 (cost + consent). |
| `param_schemas` (property) | `dict[str, dict[str, ValidationSchema]]` — per-tool param validation. The router validates against this before your `execute()` runs. Every tool that scopes to a subject must declare `entity_id` here (use `ENTITY_ID_SCHEMA` from `framework.interfaces`). |
| `execute(tool_name, params)` | Async handler. Returns a dict that the router stamps with `_meta` and returns to the LLM. Pure-function processing lives in `<Yourdomain>Processing`; `execute()` does I/O and orchestration. |
| `estimate_cost(tool_name, params)` | Async — returns `CostEstimate(estimated_tokens=..., alternative=...)`. Called by the cost gate **before** `execute()`. Estimate from metadata (row counts, point counts), never the full payload. Estimator failures fail closed. |

The router auto-generates `approve_consent_<domain>` and `revoke_consent_<domain>` from `consent_info` — do not declare them yourself.

## Register the child

Add one line to `src/tailor/__main__.py::cmd_serve()`, alongside the other `router.register_child(...)` calls. The router rejects domain collisions and tool-name collisions at registration time.

## Pure-function processing

Per [ADR 0008](docs/adr/0008-deterministic-by-construction-processing.md), every method on `<Yourdomain>Processing` must be a `@staticmethod` pure function with no PRNG and no clock reads. The same Tier-1 call with the same inputs returns the same numbers across machines. The `reproducibility-provenance-auditor` checks this at PR time.

If your processing genuinely needs the current time (e.g. "trailing 7 days"), pass the timestamp in as a parameter and resolve it in `execute()` — not inside the processing method.

## Subject scoping

Per [ADR 0009](docs/adr/0009-vault-subject-keying.md), every tool that operates on a single subject's data should declare `entity_id` in its `param_schemas`. Import the shared constants from `framework.interfaces`:

```python
from ...framework.interfaces import ENTITY_ID_SCHEMA, ENTITY_ID_PARAM_DOC
```

For biosensor-tier tools, `entity_id` is audit-log scoping only — it does not filter source data. (One authenticated account may cover multiple subjects; `entity_id` is the caller's statement of which subject this call is about.) Make sure your tool description matches that semantics; use `ENTITY_ID_PARAM_DOC` verbatim.

## PHI

The framework-level `DataScrubber` ([ADR 0003](docs/adr/0003-phi-scrubber-seam.md)) runs at the router boundary and is a no-op by default — institutions subclass when they have a deployment-wide policy.

If your data source carries **its own** identifier metadata that the framework cannot see — REDCap's `project_metadata.csv` `identifier=yes/no` flags are the canonical example — implement a child-level scrubber and call it inside `execute()` before returning. See [`src/tailor/children/redcap/scrubber.py`](src/tailor/children/redcap/scrubber.py) for the worked pattern and [ADR 0003 § Amendment 2026-05-14](docs/adr/0003-phi-scrubber-seam.md) for the seam contract.

## Tests

Two test files come with the template. Retarget them at your child — the shape test is the **contract test** for your implementation:

- `tests/children/<yourdomain>/test_<yourdomain>_shape.py` — verifies the `ChildMCP` ABC surface is non-empty and correctly typed, every tool declares `entity_id`, the router accepts `register_child()` without raising, `execute()` returns a dict for every tool, `estimate_cost()` returns a `CostEstimate`. **A new child without passing shape tests is structurally incomplete.**
- `tests/children/<yourdomain>/test_<yourdomain>_processing.py` — pure-function tests for `<Yourdomain>Processing`. No I/O.

Run them while you work:

```bash
pytest tests/children/<yourdomain>/ -v
```

Once the shape tests pass, also run the full suite to make sure no other test broke (e.g. the audit-log schema, a sibling vault test):

```bash
pytest -v
ruff check src tests
```

If your child touches `framework/router.py`, `framework/audit.py`, `framework/security.py`, or any `execute()` path that other code already depends on, the `mcp-protocol-auditor` and `reproducibility-provenance-auditor` agents will fire at PR-review time. Read [CLAUDE.md § "Manager mode"](CLAUDE.md#workflow-manager-mode) for what those gates look at.

## PR checklist

Use the standard PR template. Before opening:

- [ ] `pytest tests/children/<yourdomain>/ -v` passes.
- [ ] `pytest -v` (full suite) passes.
- [ ] `ruff check src tests` passes.
- [ ] Your child is registered in `__main__.py::cmd_serve()`.
- [ ] `tailor --help` still works and your domain appears in `tailor status`.
- [ ] If you added a new optional dependency, it's in `pyproject.toml` as an extra (not in the base install).

## When to write an ADR

If your child introduces a **structural** decision — a new seam, a deferred scope-bound, a new audit-row outcome, a new sidecar schema — that decision deserves an ADR alongside the code. ADR 0036 (MATLAB scope-bound) and ADR 0037 (REDCap export-directory scope + child-level PHI seam) are the recent worked examples. Don't ADR a bug fix or a routine tool addition.

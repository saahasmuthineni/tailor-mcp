# Build your own ChildMCP

*Author a new data source for Tailor against the template child. Intended audience: an RSE or data-engineer who knows Python classes. ~1–2 days of focused work for a typical source axis.*

## Who this guide is for

Tailor onboards new data sources through two distinct product surfaces. Pick the one that matches what you have:

| You have… | Use… | Time |
|---|---|---|
| A directory of files (CSV, `.mat`, REDCap export) whose shape one of Tailor's shipped children already understands | `tailor pilot --source={csv,matlab,redcap}` (the L1 wizard) | ~5 minutes |
| A data source whose shape no shipped child understands — proprietary vendor format, EDF recordings, FHIR bundles, custom binary, a new web API | this guide (the L2 path) | ~1–2 RSE-days |

The L1 wizard is a *researcher-accessible* tool — single command, prompts, smoke check, atomic config write. The L2 path is a *developer-accessible* extension point — copy the template child, rename, implement the abstract base class, register. See [`CLAUDE.md § "Adding a New ChildMCP"`](../../CLAUDE.md) for the structural argument behind the split and the reversal conditions on the deferred alternatives.

If you can use L1, use L1. Only reach for L2 when L1 doesn't cover your source shape.

## Quick start

```bash
# 1. Copy the template child to a new directory
cp -r src/tailor/children/template src/tailor/children/<your_source>

# 2. Rename TemplateChild → YourSourceChild + TemplateProcessing → YourSourceProcessing
#    across child.py, processing.py, __init__.py per the rename checklist
#    in template/__init__.py
```

```python
# 3. In src/tailor/__main__.py:cmd_serve(), add the registration block
#    (mirror the existing matlab_file / redcap_file pattern at ~line 161):

# your_source child (opt-in — requires your_source block in user_config.json)
your_source_child = None
if _ucfg.get("your_source"):
    from tailor.children.your_source import YourSourceChild
    your_source_child = YourSourceChild(config_dir=CONFIG_DIR, data_dir=DATA_DIR)
    router.register_child(your_source_child)
```

```bash
# 4. Run the shape tests against the new child
pytest tests/children/<your_source>/ -v
```

## The four abstract surfaces

Every `ChildMCP` subclass must declare these. The framework owns everything else.

```python
from tailor.framework import (
    ChildMCP, ToolDefinition, CostEstimate, ValidationSchema, ConsentInfo,
)

class YourSourceChild(ChildMCP):

    @property
    def domain(self) -> str:
        """A short slug used in audit rows and consent gates."""
        return "your_source"

    @property
    def display_name(self) -> str:
        """Human-facing name (operator banners, IRB queries)."""
        return "Your Source (description)"

    @property
    def consent_info(self) -> ConsentInfo:
        """What participant data your tools access, for what purpose."""
        return ConsentInfo(
            data_types=["heart-rate streams", "GPS coordinates"],
            purpose="cardiovascular drift analysis",
        )

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        """Three-tier tool surface. Each ToolDefinition declares
        tier (1/2/3), description, and a param-schema dict."""
        return [
            ToolDefinition(
                "your_source_summary",
                tier=1,
                description="...",
                params={...},
            ),
            # ... more tools at tiers 2 and 3 as needed
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        """Validation contracts the framework enforces before execute()
        is called. ParamValidator rejects bad inputs at the cheapest
        layer of the security pipeline."""
        return {"your_source_summary": {"limit": ValidationSchema(...)}}

    async def execute(self, tool_name: str, params: dict) -> dict:
        """Dispatch validated params to the handler that does the work.
        Returns a dict the framework wraps in the _meta provenance envelope."""
        ...

    async def estimate_cost(self, tool_name: str, params: dict) -> CostEstimate:
        """Pre-execution token estimate (Tier 3 only — Tier 1/2 return 0)."""
        ...
```

The template child at [`src/tailor/children/template/`](../../src/tailor/children/template/) is a runnable starting point that already passes shape tests. Read it before reading any of the production children — it's the smallest complete example.

## Optional vault contribution

If your child writes per-activity reports to the Obsidian vault (the running child's pattern — `strava_run_report` writes `note_type: run_report` frontmatter), declare which kinds you contribute via the optional `vault_note_kinds` property added in v7.6.0 per [ADR 0038 § Amendment 2026-05-19](../adr/0038-vault-layer-is-data-source-agnostic.md):

```python
@property
def vault_note_kinds(self) -> tuple[str, ...]:
    """Vault note kinds this child contributes (frontmatter ``note_type`` values)."""
    return ("your_report",)
```

Default is `()` — children that don't author per-activity vault notes (csv_dir, matlab_file, redcap_file, force_csv, emg_csv, template) inherit the empty default and need do nothing. `VaultLayer` reads this property at registration time and unions it with the framework-tier kinds (`theme`, `moment`, `failure_mode`, `dashboard`, `snapshot`) so the `vault_list_notes` / `vault_search_notes` kind filter accepts your contributed kinds without code changes in the vault layer.

## What the framework gives you for free

Every child you author inherits:

- **Audit log row per call** — domain, tool, tier, params, outcome, latency, `entity_id`, `scrubber_id` (ADR 0001 / ADR 0002).
- **Param validation** — `ParamValidator` checks types, ranges, regex patterns from `param_schemas` before `execute()` runs.
- **Circuit breaker** — three consecutive failures on the domain → 5-minute back-off.
- **Consent gate** — Tier 2 tools require operator-granted consent; Tier 3 requires consent + cost approval.
- **Cost gate** — `estimate_cost()` is called pre-execution; calls exceeding `cost_threshold` are blocked with `LLMInstruction` envelopes (ADR 0004 / ADR 0005).
- **PHI-scrubber seam** — framework-level scrub at the router boundary; optional child-level scrubber (the RedcapPHIScrubber pattern; ADR 0003 / ADR 0003 § Amendment 2026-05-14).
- **`_meta` provenance stamp** — every result envelope carries `package_version`, `tool_name`, `called_at`, `domain`, `tier`, `scrubber_id`, token counts.
- **Vault integration** — Tier 1 results can write to the vault layer via the post-execute hook; markdown is the source of truth, SQLite indexes for fast query.
- **MCP wire correctness** — JSON-RPC over stdio, schema serialization, error envelopes; `_dumps`/`_loads` handle datetime/Decimal/Path coercion.

You write the handler. The framework writes the audit row, the consent gate, the cost check, the PHI scrub, and the wire payload.

## Deterministic-by-construction processing

Per [ADR 0008](../adr/0008-deterministic-by-construction-processing.md), every method on `YourSourceProcessing` must be a `@staticmethod` pure function with no PRNG and no clock reads. The same Tier-1 call with the same inputs must return the same numbers across machines.

The template child's `TemplateProcessing` shows the shape: static methods, parameter-only inputs, no side effects, no `random` / `datetime.now()` / file reads inside. The `reproducibility-provenance-auditor` agent enforces this at PR time (see CLAUDE.md § "Researcher-utility and compliance backstops").

## Tests

Copy `tests/children/template/` alongside the template child copy. The shape tests cover:

- `ToolDefinition` schemas validate (`test_*_shape.py`)
- Each tool has a matching `param_schemas` entry
- Pure-function processing returns expected scalars on synthetic inputs (`test_*_processing.py`)

You'll add domain-specific tests on top. The pattern other children follow:

- `csv_dir`, `matlab_file`, `redcap` ship pure-function processing tests that need no external deps
- Shape tests instantiate the child against a tmp directory + synthetic data
- Subprocess wire tests live in `tests/test_serve_*_wire_*.py` for tools that need the full router pipeline

## When NOT to write a new child

If your data is one of these shapes, use a shipped child instead:

- **Time-series CSV** (per-subject files, timestamped rows) → `csv_dir` child via `tailor pilot --source=csv`
- **MATLAB `.mat` v5/v6/v7.2 numeric arrays** → `matlab_file` child via `tailor pilot --source=matlab`
- **REDCap CSV export with `project_metadata.csv` data dictionary** → `redcap_file` child via `tailor pilot --source=redcap`

If your data needs HDF5-based `.mat` v7.3, live REDCap REST API access, or another shape currently in the deferred queue — check the relevant ADR ([ADR 0036](../adr/0036-matlab-child-scope-v72-only-with-deferred-hdf5.md) for HDF5, [ADR 0037](../adr/0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md) for live REDCap) for the named reversal conditions. The right move may be to argue for unblocking the deferred work rather than writing a parallel child.

## Cited decisions

- [ADR 0001](../adr/0001-audit-log-as-backbone.md) — every call writes an audit row; the framework owns this.
- [ADR 0002](../adr/0002-subject-id-scoping.md) + [ADR 0009](../adr/0009-vault-subject-keying.md) — `entity_id` scoping across audit + vault.
- [ADR 0003](../adr/0003-phi-scrubber-seam.md) — framework-level PHI seam (no-op default); ADR 0003 § Amendment 2026-05-14 — child-level scrubber pattern.
- [ADR 0008](../adr/0008-deterministic-by-construction-processing.md) — `@staticmethod` pure-function invariant on processing modules.
- [ADR 0011](../adr/0011-promotion-policy.md) — promotion policy that produced this guide as the answer to the L1/L2 split.

When the third non-shipped child arrives via this path, the wizard's pattern generalizes to a `tailor pilot --source=your_source` extension. Until then, your child lives in `__main__.py:cmd_serve()` as a hand-registered block — the same posture every shipped child started in.

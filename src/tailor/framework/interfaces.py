"""
Biosensor-to-LLM Framework — Interfaces
========================================
Base classes defining the contract between the parent router MCP
and domain-specific child MCPs.

ChildMCP is the extension point for each data source a research
group wants to expose to an LLM analyst: a CSV directory, an EDF
file, a FHIR bundle, a REDCap export, a vendor-specific cloud
API, etc. The running child in this repository is one worked
example of the pattern, not the canonical use case.

Every child declares how sensitive its data is (``consent_info``),
what tools it exposes and at what access tier (``tool_definitions``),
and how to cheaply estimate a per-call token budget
(``estimate_cost``). The router enforces the rest uniformly — so
any LLM client gets identical behavior without domain-specific
prompting.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tailor.framework.router import RouterMCP


@dataclass
class ToolDefinition:
    """Schema for a tool exposed by a child MCP."""
    name: str
    tier: int  # 1=free, 2=consent-gated, 3=cost-gated
    description: str
    params: dict[str, dict]  # param_name -> {type, description, required, ...}


@dataclass
class CostEstimate:
    """
    Pre-execution cost estimate from a child MCP.

    The parent router calls child.estimate_cost() BEFORE execution.
    If tokens exceed the cost gate threshold, the router shows the user
    both options and waits for approval — no wasted computation.
    """
    tokens: int
    has_cheaper_alternative: bool = False
    alternative_tokens: int = 0
    alternative_description: str = ""
    alternative_params: dict = field(default_factory=dict)


@dataclass
class ValidationSchema:
    """Parameter validation rules for a single tool parameter."""
    type: type
    required: bool = False
    default: Any = None
    min: float | None = None
    max: float | None = None
    min_len: int | None = None
    max_len: int | None = None
    pattern: str | None = None
    allowed_values: list | None = None


# ═══════════════════════════════════════════════════════════════
# SHARED PARAMETER SCHEMAS
# ═══════════════════════════════════════════════════════════════

# Optional study-participant identifier declared on every audit-
# scoped tool (biosensor children + vault layer). See ADR 0002 for
# the audit-scoping rationale and ADR 0009 for vault subject-keying.
# The shared definition lives here so children, the vault layer, and
# any future framework-level component agree on the same regex and
# don't drift out of sync if the IRB later specifies a different
# identifier format.
SUBJECT_ID_SCHEMA = ValidationSchema(
    type=str,
    required=False,
    pattern=r"^[A-Za-z0-9_\-]{1,64}$",
)

# MCP-surface description fragment for the same parameter — included
# in every tool's params dict so LLM clients discover it via list_tools.
SUBJECT_ID_PARAM_DOC = {
    "type": "string",
    "description": (
        "Optional study participant identifier for audit-log scoping. "
        "Does not filter data. Pattern: ^[A-Za-z0-9_-]{1,64}$."
    ),
    "required": False,
}


# ═══════════════════════════════════════════════════════════════
# STRUCTURED LLM INSTRUCTION (replaces freeform string)
# ═══════════════════════════════════════════════════════════════

@dataclass
class LLMInstruction:
    """
    Structured behavioral contract for the LLM handling a gate response.

    Each field is individually checkable by any LLM client — makes
    "technically comply while spiritually violating" require deliberate
    effort rather than accidental drift.

    Serializes to a compact JSON object (~150-250 tokens depending on
    gate type). This is a one-time cost per gate event, not per-call.
    """
    must_do: list[str]
    must_not_do: list[str]
    on_ambiguous_reply: str = "Re-ask with a narrower question. Do not proceed."

    def to_dict(self) -> dict:
        return {
            "must_do": self.must_do,
            "must_not_do": self.must_not_do,
            "on_ambiguous_reply": self.on_ambiguous_reply,
        }


@dataclass
class ConsentScope:
    """
    Structured scope metadata for consent decisions.

    Elevates session scope from buried text to a top-level structured
    field that the LLM is required to surface. Includes revocability
    info so the user knows consent isn't a one-way door.
    """
    duration: str = "session"
    duration_human: str = "until this conversation ends"
    covers_future_calls: bool = True
    revocable: bool = True
    revoke_instruction: str = "Say 'revoke consent' at any time."

    def to_dict(self) -> dict:
        return {
            "duration": self.duration,
            "duration_human": self.duration_human,
            "covers_future_calls": self.covers_future_calls,
            "revocable": self.revocable,
            "revoke_instruction": self.revoke_instruction,
        }


@dataclass
class CostContext:
    """
    Human-relatable cost context for token-based cost gates.

    Raw token counts are meaningless to humans. This struct provides
    anchors: relative to a typical call, relative to the cheaper
    alternative, and an optional monetary estimate.

    The server computes these; the LLM is required to present at
    least one alongside the raw number.
    """
    tokens: int
    relative_to_typical: str = ""       # e.g. "~20x a normal chat turn"
    relative_to_cheaper_pct: str = ""   # e.g. "10x more than downsampled"
    estimated_cost_usd: float | None = None  # at current rates, if known

    def to_dict(self) -> dict:
        d: dict = {"tokens": self.tokens, "relative_to_typical": self.relative_to_typical}
        if self.relative_to_cheaper_pct:
            d["relative_to_cheaper_pct"] = self.relative_to_cheaper_pct
        if self.estimated_cost_usd is not None:
            d["estimated_cost_usd"] = self.estimated_cost_usd
        return d


@dataclass
class ConsentInfo:
    """
    Human-readable consent details for a biosensor domain.

    Each child MCP declares this once. The router uses it to generate
    a user_prompt (text to show the user) and structured llm_instruction
    (behavioral contract telling the LLM exactly how to present the ask).

    This keeps consent UX fully server-side — any LLM client gets the
    same experience without custom prompting.
    """
    data_types: list[str]                # e.g. ["heart rate", "GPS location", "pace"]
    purpose: str                         # e.g. "training analysis and visualization"
    scope: ConsentScope = field(default_factory=ConsentScope)


class ChildMCP(ABC):
    """
    Base class for biosensor child MCPs.

    Each child owns one data domain (running, CGM, sleep, etc.)
    and exposes tools through the parent router's security pipeline.

    Children never talk to Claude directly. The parent:
    1. Validates params
    2. Checks circuit breaker (scoped per child domain)
    3. Checks domain-scoped biometric consent
    4. Asks child for cost estimate (before execution)
    5. Fires cost gate if estimate exceeds threshold
    6. Calls child.execute()
    7. Audits everything

    To create a new biosensor child:
    1. Subclass ChildMCP
    2. Define domain, display_name
    3. Define tool_definitions and param_schemas
    4. Implement execute() and estimate_cost()
    5. Register with router.register_child(your_child)
    """

    _router: RouterMCP | None = None  # Set by router during registration

    @property
    @abstractmethod
    def domain(self) -> str:
        """Unique domain identifier (e.g., 'running', 'cgm', 'sleep')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for consent prompts (e.g., 'Running (Strava)')."""
        ...

    @property
    @abstractmethod
    def tool_definitions(self) -> list[ToolDefinition]:
        """All tools this child exposes to the router."""
        ...

    @property
    @abstractmethod
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        """
        Validation schemas: tool_name -> param_name -> ValidationSchema.

        The router validates all params before calling execute().
        """
        ...

    @abstractmethod
    async def execute(self, tool_name: str, params: dict) -> dict:
        """
        Execute a tool. Called only after all security gates pass.

        Params are already validated and cleaned by the router.
        Return a dict — the router serializes it and attaches metadata.
        """
        ...

    @abstractmethod
    async def estimate_cost(self, tool_name: str, params: dict) -> CostEstimate:
        """
        Estimate token cost BEFORE execution.

        The router uses this to decide whether to fire the cost gate.
        Keep this cheap — read metadata/counts, not full data.
        Return CostEstimate(tokens=0) for tools where cost is negligible.
        """
        ...

    @abstractmethod
    def purge_cache(self, *, force: bool = False) -> dict:
        """
        Purge cached participant biometric data for this domain.

        Called synchronously by the router when consent for this
        domain is revoked (per ADR 0013 — Cache-only purge on consent
        revocation). The contract is: every artifact this child has
        cached that derives from raw biometric streams is removed,
        and analyst-authored artifacts (labels, annotations, vault
        notes if any) are preserved.

        Returns a dict with at minimum:
            rows_purged    — int, total rows deleted across tables
            tables_touched — list[str], tables that lost rows
            preserved      — list[str], analyst-authored tables left intact

        Args:
            force: When False (default), I/O or database errors raise
                   so the router's revocation can fail closed —
                   consent stays approved, the participant sees a
                   loud signal that cleanup did not complete. When
                   True, errors are swallowed into the return dict's
                   ``errors`` list and revocation proceeds anyway —
                   used by the ``force_revoke=True`` escape hatch
                   for the "cache file is locked by an external
                   process" edge case.

        Children with no cache (CSV-directory child reading
        institutional CSV files; pure-API children) return
        ``{"rows_purged": 0, "tables_touched": [], "preserved": [],
        "reason": "<why nothing to purge>"}``.
        """
        ...

    @property
    def consent_info(self) -> ConsentInfo:
        """
        Consent metadata for this domain's biometric gate.

        Override in each child to declare exactly what data types are
        accessed and why. Used by the router to build user_prompt and
        structured llm_instruction in the gate response — so any LLM
        client gets a proper consent dialog without custom prompting.
        """
        return ConsentInfo(
            data_types=["biometric data"],
            purpose="health analysis",
        )

    def data_types_for_tool(self, tool_name: str, params: dict) -> list[str]:
        """
        Return the subset of data_types actually needed for this specific call.

        Override in children to provide granular per-call scope.
        Default: returns all data_types (full session scope).
        This enables the consent prompt to distinguish "what this call needs"
        from "what the session will allow," closing the scope-overstating gap.
        """
        return self.consent_info.data_types

    def close(self) -> None:  # noqa: B027 — intentional optional hook, no-op default
        """Release resources (storage connections, file handles).

        Override in children that own a ``BaseStorage`` subclass or
        other closeable resources.  The router calls this on shutdown
        to release SQLite WAL file locks (required on Windows).
        """

    @property
    def child_scrubber_id(self) -> str | None:
        """
        Identity of the child-level PHI scrubber, if any.

        Per ADR 0003 § Amendment 2026-05-14 + ADR 0037: a child that
        ships its own structured-PHI scrubber (one that reads
        domain-specific IRB-approved input like REDCap's
        ``project_metadata.csv`` identifier flags) returns its
        scrubber name here. The router stamps this into the audit
        row's ``child_scrubber_id`` column.

        Default ``None`` means no child-level scrubber runs — the
        framework-level ``PHIScrubber`` seam (ADR 0003) is the only
        scrubber that touches the result. ``None`` for csv_dir,
        matlab_file, running child, template child; e.g.
        ``"redcap_metadata_flags"`` for RedcapFileChild.
        """
        return None

    @property
    def child_source_metadata_fingerprint(self) -> str | None:
        """
        SHA-256 fingerprint of the child-level scrubber's trust-root
        metadata at scrubber construction time, if any.

        Per ADR 0003 § Amendment 2026-05-15: a child whose scrubber
        reads a structured metadata input from disk (REDCap's
        ``project_metadata.csv``; future candidates FHIR profile
        descriptors, EDF channel manifests, vendor calibration
        sidecars) returns its scrubber's ``fingerprint`` property here.
        The router stamps this into the audit row's
        ``source_metadata_fingerprint`` column and surfaces it in
        result ``_meta.source_metadata_fingerprint`` so an IRB reviewer
        can correlate any disclosure with the trust-root state in
        force when the disclosure occurred.

        Default ``None`` means the child does not ship a child-level
        scrubber, or its scrubber does not expose a ``fingerprint``
        property. ``None`` for csv_dir, matlab_file, running child,
        template child; ``RedcapFileChild`` returns its scrubber's
        SHA-256 fingerprint over canonical-form
        ``(field_name, identifier_flag)`` tuples.
        """
        return None

    def get_tier(self, tool_name: str) -> int:
        """Get the access tier for a tool."""
        for tool in self.tool_definitions:
            if tool.name == tool_name:
                return tool.tier
        return 1

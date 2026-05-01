"""
Local LLM Layer — Framework-Level Guardian
==============================================
Framework-level infrastructure that mediates between the hosted
LLM and biometric data using a local LLM running on the analyst's
machine. Registered with the router parallel to ``VaultLayer``;
skips biosensor-tier gates (consent, cost, circuit breaker,
PHI-scrub) — only param validation and audit apply.

See ADR 0022 for the full architectural rationale.

Tools:
    ask_local_oracle    Compose a structured response over
                        deterministic processing output. The
                        local LLM never replaces processing —
                        it only composes responses; numerical
                        claims always come from processing.py.
"""

from __future__ import annotations

import logging

from ..interfaces import (
    SUBJECT_ID_PARAM_DOC,
    SUBJECT_ID_SCHEMA,
    ToolDefinition,
    ValidationSchema,
)
from .backends import LocalLLMBackend
from .backends.null import NullBackend
from .oracle import OracleRequest

log = logging.getLogger("biosensor-mcp.local_llm")


# Tools whose outputs are the canonical inputs to ``ask_local_oracle``
# in Phase 0 (per ADR 0022 § "Phase 0 v0 scope" — the cohort surface
# only). Documented here so docs and tests share the same source of
# truth; not enforced by the dispatch layer (any client-supplied
# resolved_context is accepted).
ORACLE_MEDIATED_TOOLS = frozenset(
    {
        "csv_cohort_summary",
        "csv_force_decline",
    }
)


class LocalLLMLayer:
    """
    Framework-level local-LLM guardian.

    Args:
        backend: A :class:`LocalLLMBackend` implementation. Defaults
                 to :class:`NullBackend` (no-op) when not provided.
                 Operators enable real backends via
                 ``user_config.json``.
    """

    def __init__(self, backend: LocalLLMBackend | None = None):
        self._backend: LocalLLMBackend = backend or NullBackend()
        self._router = None  # Set by RouterMCP.register_local_llm_layer()
        log.info(
            "LocalLLMLayer initialized "
            f"(backend={self._backend.backend_id}, "
            f"tier={self._backend.tier}, "
            f"model={self._backend.model_id})"
        )

    @property
    def backend(self) -> LocalLLMBackend:
        return self._backend

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                "ask_local_oracle",
                1,
                "Ask the local-LLM guardian a natural-language question "
                "about already-computed analytical output. The framework "
                "pre-resolves the deterministic processing call(s) the "
                "question requires; the local LLM only composes a "
                "structured response over the resolved data. Numerical "
                "claims in the response are citable; narrative is "
                "explicitly labeled non-citable in _meta. Best paired "
                "with prior csv_cohort_summary / csv_force_decline calls "
                "— pass their results as resolved_context. ~1500 tokens.",
                {
                    "question": {
                        "type": "string",
                        "description": (
                            "Natural-language question for the local "
                            "oracle (e.g. 'compare fatigue P003 vs P004')."
                        ),
                        "required": True,
                    },
                    "resolved_context": {
                        "type": "object",
                        "description": (
                            "Dict mapping deterministic processing-call "
                            "names to their results. Numerical claims in "
                            "the response are flattened from this — the "
                            "LLM does NOT invent numbers. Hosted Claude "
                            "is expected to populate this by first "
                            "calling the relevant Tier-1 tools "
                            "(typically csv_cohort_summary and/or "
                            "csv_force_decline)."
                        ),
                        "required": True,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        return {
            "ask_local_oracle": {
                "question": ValidationSchema(
                    type=str, required=True, min_len=1, max_len=2000,
                ),
                "resolved_context": ValidationSchema(
                    type=dict, required=True,
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
        }

    async def execute(self, tool_name: str, params: dict) -> dict:
        """Dispatch table for the layer's tools."""
        if tool_name != "ask_local_oracle":
            return {"error": f"Unknown local-LLM tool: {tool_name}"}
        request = OracleRequest(
            question=params["question"],
            resolved_context=params["resolved_context"],
            subject_id=params.get("subject_id"),
        )
        response = await self._backend.compose(request)
        return response.to_dict()

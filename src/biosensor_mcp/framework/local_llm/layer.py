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
        vault_storage: Optional :class:`VaultStorage` reference for
                 the deterministic substrate scan (per ADR 0023).
                 When ``None``, ``_scan_related_substrate`` returns
                 ``[]`` defensively — existing tests and deployments
                 without a vault are unaffected.
    """

    def __init__(
        self,
        backend: LocalLLMBackend | None = None,
        vault_storage=None,
    ):
        self._backend: LocalLLMBackend = backend or NullBackend()
        self._vault_storage = vault_storage
        self._router = None  # Set by RouterMCP.register_local_llm_layer()
        log.info(
            "LocalLLMLayer initialized "
            f"(backend={self._backend.backend_id}, "
            f"tier={self._backend.tier}, "
            f"model={self._backend.model_id}, "
            f"vault_substrate={'on' if self._vault_storage else 'off'})"
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
                "— pass their results as resolved_context. The response "
                "also returns related_substrate: vault notes (themes, "
                "moments, failure-modes) the local layer found relevant "
                "to the subject(s) in scope — incorporate them, or call "
                "vault_read_note for full bodies. ~1500–3000 tokens "
                "depending on substrate count and title length (capped "
                "at 20 entries).",
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
        # ADR 0023 — substrate scan in the layer, not the backend.
        # NullBackend inherits substrate vision for free; the
        # deterministic SQLite query stays out of the LLM-composition
        # boundary so ADR 0008's determinism contract holds.
        response.related_substrate = self._scan_related_substrate(request)
        return response.to_dict()

    # ── Substrate scan (ADR 0023) ──

    # Cap on entries surfaced into the response payload. Token-budget
    # bound — the contract claim in the tool description budgets
    # ~2500 tokens including substrate; growth past 20 entries trips
    # that budget regardless of vault size.
    _SUBSTRATE_CAP = 20

    def _scan_related_substrate(self, request: OracleRequest) -> list[dict]:
        """Deterministic vault scan for substrate referencing the
        subject(s) in scope. Returns up to :data:`_SUBSTRATE_CAP`
        entries, sorted by ``last_updated`` descending.

        Surfaces themes (one query per subject) and notes of kind
        ``moment`` / ``failure_mode`` — the analyst-authored content
        that is most likely to ground the LLM's interpretation.
        Run reports and dashboards are intentionally not surfaced —
        they are derived artifacts, not analyst interpretation.

        Subject collection: explicit ``request.subject_id`` plus any
        per-subject keys in ``resolved_context`` (the
        ``{processing_call: {subject_id: {metric: value}}}`` shape
        ``_flatten_claims`` already detects). When no subjects are
        in scope, the scan returns ``[]`` — the substrate scan is
        purpose-built to find content *about the subject(s) of the
        question*, not arbitrary recent vault content.

        Defensive contract: any exception from VaultStorage is
        swallowed and logged as a warning; the response never breaks
        because of a vault-scan failure. The caller's existing
        narrative + numerical_claims are preserved unchanged.
        """
        if self._vault_storage is None:
            return []
        try:
            subject_ids = self._collect_subjects(request)
            if not subject_ids:
                return []
            entries: list[dict] = []
            seen_slugs: set[str] = set()
            for sid in subject_ids:
                for theme in self._vault_storage.list_themes(
                    subject_id=sid, limit=10,
                ):
                    slug = theme.get("slug")
                    if not slug or slug in seen_slugs:
                        continue
                    seen_slugs.add(slug)
                    entries.append({
                        "kind": "theme",
                        "slug": slug,
                        "title": None,
                        "subject_id": theme.get("subject_id"),
                        "status": theme.get("status"),
                        "last_updated": theme.get("last_updated"),
                    })
                for note_kind in ("moment", "failure_mode"):
                    for note in self._vault_storage.list_notes(
                        note_type=note_kind, subject_id=sid, limit=5,
                    ):
                        filename = note.get("filename") or ""
                        slug = (
                            filename[:-3]
                            if filename.endswith(".md")
                            else filename
                        )
                        if not slug or slug in seen_slugs:
                            continue
                        seen_slugs.add(slug)
                        fm = note.get("frontmatter") or {}
                        title = (
                            fm.get("title") if isinstance(fm, dict) else None
                        )
                        status = (
                            fm.get("status") if isinstance(fm, dict) else None
                        )
                        entries.append({
                            "kind": note_kind,
                            "slug": slug,
                            "title": title,
                            "subject_id": note.get("subject_id"),
                            "status": status,
                            "last_updated": note.get("written_at"),
                        })
            entries.sort(
                key=lambda e: e.get("last_updated") or "",
                reverse=True,
            )
            return entries[: self._SUBSTRATE_CAP]
        except Exception as exc:
            log.warning(f"LocalLLMLayer substrate scan failed: {exc}")
            return []

    @staticmethod
    def _collect_subjects(request: OracleRequest) -> list[str]:
        """Collect subject ids from the request.

        Matches the heuristic ``_flatten_claims`` uses: any inner
        dict in ``resolved_context[processing_call]`` is treated as
        a per-subject grouping where the key is the subject id. The
        explicit ``request.subject_id`` is added first (preserves
        order).
        """
        subjects: list[str] = []
        seen: set[str] = set()
        if request.subject_id is not None:
            subjects.append(request.subject_id)
            seen.add(request.subject_id)
        for result in request.resolved_context.values():
            if not isinstance(result, dict):
                continue
            for key, value in result.items():
                if isinstance(value, dict):
                    key_str = str(key)
                    if key_str not in seen:
                        subjects.append(key_str)
                        seen.add(key_str)
        return subjects

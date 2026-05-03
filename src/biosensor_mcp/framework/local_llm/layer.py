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
                "non-citable (labeled in _meta). Best paired with prior "
                "csv_cohort_summary / csv_force_decline calls — pass "
                "their results as resolved_context. The response is "
                "structured for multi-pass cooperation; three fields "
                "name what to do next: related_substrate (vault notes — "
                "themes, moments, failure-modes — about the subject(s); "
                "read with vault_read_note if relevant), next_best_calls "
                "(framework tool names to fetch missing data; call the "
                "named tool then re-invoke this with the new result "
                "added to resolved_context), and unresolved_intent "
                "(questions to put to the analyst before composing "
                "confidently — surface to the analyst, do not answer "
                "yourself). Empty lists mean no gap of that kind. "
                "Iterate until both reasoning lists are empty or "
                "confidence is sufficient. ~2000–4000 tokens depending "
                "on substrate count (capped at 20) and gap-reasoning "
                "verbosity.",
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
        entries, warning = self._scan_related_substrate(request)
        response.related_substrate = entries
        response.substrate_scan_warning = warning
        return response.to_dict()

    # ── Substrate scan (ADR 0023) ──

    # Cap on entries surfaced into the response payload. Token-budget
    # bound — the contract claim in the tool description budgets
    # ~2500 tokens including substrate; growth past 20 entries trips
    # that budget regardless of vault size.
    _SUBSTRATE_CAP = 20

    def _scan_related_substrate(
        self, request: OracleRequest,
    ) -> tuple[list[dict], str | None]:
        """Deterministic vault scan for substrate referencing the
        subject(s) in scope. Returns ``(entries, warning)`` where
        ``entries`` is up to :data:`_SUBSTRATE_CAP` entries sorted
        by ``last_updated`` descending, and ``warning`` is ``None``
        on the happy path or a short failure-reason string when a
        VaultStorage exception was swallowed (per ADR 0023's WATCH
        finding from `phi-irb-risk-reviewer` — distinguishes
        "scanned cleanly, found nothing" from "scan crashed
        silently"; parallels the ADR 0003 ``scrubber_warning`` seam
        v6.3.1 introduced for the PHI-scrubber default).

        Surfaces themes (one query per subject) and notes of kind
        ``moment`` / ``failure_mode`` — the analyst-authored content
        that is most likely to ground the LLM's interpretation.
        Run reports and dashboards are intentionally not surfaced —
        they are derived artifacts, not analyst interpretation.

        Subject collection: explicit ``request.subject_id`` plus any
        per-subject keys in ``resolved_context`` (the
        ``{processing_call: {subject_id: {metric: value}}}`` shape
        ``_flatten_claims`` already detects). When no subjects are
        in scope, the scan returns ``([], None)`` — the substrate
        scan is purpose-built to find content *about the subject(s)
        of the question*, not arbitrary recent vault content.

        Dedup key is ``(kind, slug)`` so a theme and a moment that
        happen to share a slug both surface — they are distinct
        artifacts living in different vault namespaces.

        Defensive contract: any exception from VaultStorage is
        swallowed; the response never breaks because of a vault-scan
        failure. The caller's existing narrative + numerical_claims
        are preserved unchanged. The reason is surfaced via
        ``warning`` so a reviewer reading the wire payload can see
        that the scan crashed.
        """
        if self._vault_storage is None:
            return [], None
        try:
            subject_ids = self._collect_subjects(request)
            if not subject_ids:
                return [], None
            entries: list[dict] = []
            seen: set[tuple[str, str]] = set()
            for sid in subject_ids:
                for theme in self._vault_storage.list_themes(
                    subject_id=sid, limit=10,
                ):
                    slug = theme.get("slug")
                    if not slug or ("theme", slug) in seen:
                        continue
                    seen.add(("theme", slug))
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
                        if not slug or (note_kind, slug) in seen:
                            continue
                        seen.add((note_kind, slug))
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
            return entries[: self._SUBSTRATE_CAP], None
        except Exception as exc:
            warning = f"substrate scan failed: {exc}"
            log.warning(f"LocalLLMLayer {warning}")
            return [], warning

    @staticmethod
    def _collect_subjects(request: OracleRequest) -> list[str]:
        """Collect subject ids from the request.

        Matches the heuristic ``_flatten_claims`` uses (per
        red-team-reviewer's adversarial pairing on ADR 0023 PR1
        release pass): any inner dict in
        ``resolved_context[processing_call]`` is treated as a
        per-subject grouping where the key is the subject id, BUT
        only if that inner dict has at least one scalar value
        (``int`` or ``float``, excluding ``bool``). This mirrors
        ``_flatten_claims``'s implicit filter at
        ``framework/local_llm/backends/null.py:108-115`` — the
        existing claim-flattener emits no claim for a key whose
        inner values are all non-scalar, so the substrate scan
        likewise should not treat such a key as a subject. Without
        this filter, a tool returning
        ``{call: {"_meta": {...}, "columns": {...}, "P003": {...}}}``
        would surface ``_meta`` and ``columns`` as bogus subjects,
        inflating storage queries and the IS-NULL-or-match cross-
        subject substrate fan-out.

        The explicit ``request.subject_id`` is added first
        (preserves order) and is exempt from the scalar filter —
        it is the caller's explicit declaration of subject scope.
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
                if not isinstance(value, dict):
                    continue
                # Mirror _flatten_claims: only treat as per-subject
                # grouping when the inner dict has at least one
                # numeric scalar (the implicit filter that prevents
                # _meta-shaped sibling keys from being misclassified
                # as subjects).
                has_scalar = any(
                    isinstance(sub_val, (int, float))
                    and not isinstance(sub_val, bool)
                    for sub_val in value.values()
                )
                if not has_scalar:
                    continue
                key_str = str(key)
                if key_str not in seen:
                    subjects.append(key_str)
                    seen.add(key_str)
        return subjects

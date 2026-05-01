"""
NullBackend — no-op default for when local LLM is not configured.

Returns a structured "local LLM not configured" response.
Numerical claims are surfaced from ``resolved_context`` so callers
still get citable numbers; narrative tells the LLM client that
local-LLM mediation is disabled and points to docs/guides/local-llm-guardian.md.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone

from ..oracle import (
    NumericalClaim,
    OracleMeta,
    OracleRequest,
    OracleResponse,
)
from . import LocalLLMBackend


class NullBackend(LocalLLMBackend):
    """No-op backend. Surfaces deterministic claims; no narrative."""

    @property
    def backend_id(self) -> str:
        return "null"

    @property
    def tier(self) -> str:
        return "null"

    @property
    def model_id(self) -> str:
        return "null"

    async def compose(self, request: OracleRequest) -> OracleResponse:
        start = time.time()
        # Surface deterministic numerical claims from resolved_context
        # even though no LLM is running — claims are citable regardless.
        claims = _flatten_claims(request.resolved_context)
        latency_ms = int((time.time() - start) * 1000)
        prompt_hash = hashlib.sha256(
            request.question.encode("utf-8")
        ).hexdigest()[:16]
        return OracleResponse(
            numerical_claims=claims,
            narrative=(
                "Local-LLM guardian is not configured. Numerical claims "
                "above come from deterministic processing and are citable. "
                "To enable narrative composition and ambiguity-axis "
                "detection, configure a backend in user_config.json (see "
                "docs/guides/local-llm-guardian.md)."
            ),
            ambiguity_axes=[],
            confidence=0.0,
            meta=OracleMeta(
                model_id="null",
                model_version_hash="null",
                tier="null",
                latency_ms=latency_ms,
                prompt_hash=prompt_hash,
                called_at=datetime.now(timezone.utc).isoformat(),
                processing_calls=list(request.resolved_context.keys()),
                backend="null",
            ),
        )


def _flatten_claims(resolved_context: dict) -> list[NumericalClaim]:
    """
    Flatten resolved-context dicts into NumericalClaim objects.

    Best-effort: any numeric leaf becomes a claim. Supports two
    common shapes:

    * ``{processing_call: {metric: value}}`` — flat per-call results
      (e.g. ``csv_force_decline`` returns one dict per file).
    * ``{processing_call: {subject_id: {metric: value}}}`` — per-subject
      grouped results (e.g. cohort comparisons).

    Non-numeric values (strings, None, lists, nested dicts beyond two
    levels) are skipped silently — they are not surfaceable as
    citable numerical claims by definition. Booleans are also
    skipped (they are int-subclass in Python but flag-shaped, not
    measurement-shaped). An analyst whose result includes a
    string-typed metric or a load-bearing flag will not see it
    appear in ``numerical_claims`` and should reference the original
    processing-call output directly.

    The function is shared across NullBackend and OllamaBackend so
    the LLM-to-LLM contract's fidelity guarantee (numerical claims
    always come from processing output, never from LLM prose) is
    enforced in one place.
    """
    claims: list[NumericalClaim] = []
    for proc_call, result in resolved_context.items():
        if not isinstance(result, dict):
            continue
        for key, value in result.items():
            if isinstance(value, bool):
                # Booleans are int-subclass in Python; skip to avoid
                # surfacing flag fields as numerical claims.
                continue
            if isinstance(value, (int, float)):
                claims.append(
                    NumericalClaim(
                        metric=key,
                        value=value,
                        processing_call=proc_call,
                    )
                )
            elif isinstance(value, dict):
                # Per-subject shape: {subject_id: {metric: value}}
                for sub_metric, sub_val in value.items():
                    if isinstance(sub_val, bool):
                        continue
                    if isinstance(sub_val, (int, float)):
                        claims.append(
                            NumericalClaim(
                                metric=sub_metric,
                                value=sub_val,
                                subject_id=str(key),
                                processing_call=proc_call,
                            )
                        )
    return claims

"""
OllamaBackend — talks to a local Ollama daemon over HTTP.

Requires Ollama running on ``localhost:11434`` (configurable).
Uses Ollama's JSON-mode (``format: "json"``) to enforce
structurally-valid responses. Schema-validates every response
and retries once on failure with a stricter prompt; if still
invalid, returns a structured fallback response that surfaces
the deterministic claims from ``resolved_context`` without LLM
narrative.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone

import requests

from ..oracle import (
    DEFAULT_TIER,
    LOCAL_LLM_TIERS,
    OracleMeta,
    OracleRequest,
    OracleResponse,
)
from . import LocalLLMBackend
from .null import _flatten_claims

log = logging.getLogger("tailor.local_llm.ollama")

DEFAULT_ENDPOINT = "http://localhost:11434"
DEFAULT_TIMEOUT_S = 60.0


class OllamaBackend(LocalLLMBackend):
    """
    Local-LLM backend backed by an Ollama daemon.

    Args:
        tier:       'scout' | 'sentinel' | 'guardian' | 'titan'
                    (default: ``guardian``).
        model:      Override the tier's default model (e.g. for
                    testing). Default: tier's recommended model.
        endpoint:   Ollama HTTP endpoint. Default ``localhost:11434``.
        timeout_s:  Per-call timeout in seconds. Default ``60``.
    """

    def __init__(
        self,
        tier: str = DEFAULT_TIER,
        model: str | None = None,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ):
        if tier not in LOCAL_LLM_TIERS:
            raise ValueError(
                f"Unknown tier '{tier}'. Allowed: {list(LOCAL_LLM_TIERS)}"
            )
        self._tier = tier
        self._model = model or LOCAL_LLM_TIERS[tier]["model"]
        self._endpoint = endpoint.rstrip("/")
        self._timeout_s = timeout_s

    @property
    def backend_id(self) -> str:
        return "ollama"

    @property
    def tier(self) -> str:
        return self._tier

    @property
    def model_id(self) -> str:
        return self._model

    async def compose(self, request: OracleRequest) -> OracleResponse:
        start = time.time()
        prompt = self._build_prompt(request)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

        try:
            raw = self._call_ollama(prompt)
            parsed = self._parse_or_retry(prompt, raw)
        except Exception as e:
            # Fail open to a fallback response — citable numbers still
            # flow through, narrative is honest about the failure.
            log.warning(
                "OllamaBackend.compose failed: %s; "
                "falling back to deterministic-only response",
                e,
            )
            return self._fallback_response(request, prompt_hash, start, str(e))

        latency_ms = int((time.time() - start) * 1000)
        return self._build_response(request, parsed, prompt_hash, latency_ms)

    # ── prompt construction ──────────────────────────────────────

    def _build_prompt(self, request: OracleRequest) -> str:
        """System + user prompt enforcing structured JSON output."""
        ctx_json = json.dumps(request.resolved_context, default=str, indent=2)
        return (
            "You are a research-data guardian. The framework has already "
            "computed all numerical results from deterministic processing. "
            "Your job is to compose a STRUCTURED JSON response. You MUST "
            "NOT invent numbers — every number you mention must come from "
            "resolved_context. Refuse raw-data display requests by "
            "suggesting a summary alternative.\n\n"
            "If resolved_context is missing data the question requires, "
            "name the gap. The split is load-bearing: name a framework "
            "tool the caller can run to fetch missing data in "
            "next_best_calls; name a question the caller should put to "
            "the analyst in unresolved_intent. Do not duplicate items "
            "across the two lists. Either list may be empty when no "
            "gap exists.\n\n"
            "Respond with ONLY a JSON object matching this schema:\n"
            "{\n"
            '  "narrative": "<one paragraph, plain English, citing only '
            'numbers in resolved_context>",\n'
            '  "ambiguity_axes": ["<research-question disambiguation, or '
            "empty list>\"],\n"
            '  "confidence": <float 0.0-1.0>,\n'
            '  "next_best_calls": ["<framework tool name to fetch '
            'missing data, e.g. csv_force_decline; empty list if no '
            'data gap>"],\n'
            '  "unresolved_intent": ["<question to put to the analyst '
            'before the oracle can compose confidently; empty list if '
            'no analyst-judgment gap>"]\n'
            "}\n\n"
            f"Question: {request.question}\n\n"
            f"resolved_context:\n{ctx_json}\n"
        )

    # ── HTTP call ────────────────────────────────────────────────

    def _call_ollama(self, prompt: str) -> str:
        """POST to Ollama's /api/generate with format=json."""
        url = f"{self._endpoint}/api/generate"
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        resp = requests.post(url, json=payload, timeout=self._timeout_s)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")

    # ── response parsing ─────────────────────────────────────────

    def _parse_or_retry(self, prompt: str, raw: str) -> dict:
        """Parse JSON; retry once with stricter prompt on failure."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            stricter = (
                prompt
                + "\n\nIMPORTANT: respond with ONLY the JSON object, no prose."
            )
            try:
                raw2 = self._call_ollama(stricter)
                return json.loads(raw2)
            except (json.JSONDecodeError, requests.RequestException) as e:
                raise ValueError(f"Ollama returned non-JSON twice: {e}") from e

    # ── response construction ────────────────────────────────────

    def _build_response(
        self,
        request: OracleRequest,
        parsed: dict,
        prompt_hash: str,
        latency_ms: int,
    ) -> OracleResponse:
        # Numerical claims always come from resolved_context, not the
        # LLM. This is the load-bearing fidelity guarantee per ADR 0022.
        claims = _flatten_claims(request.resolved_context)
        narrative = str(parsed.get("narrative", "")).strip() or (
            "Local LLM returned no narrative."
        )
        ambiguity = parsed.get("ambiguity_axes", [])
        if not isinstance(ambiguity, list):
            ambiguity = []
        try:
            confidence = float(parsed.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        # ADR 0023 PR2 — defensive list-coercion mirrors the
        # ambiguity_axes pattern above. A non-list emission from the
        # backend (e.g. the model returns a string by mistake) yields
        # an empty list; non-string entries inside a valid list are
        # coerced via str() so the wire contract holds even when the
        # LLM hallucinates the shape.
        next_calls = parsed.get("next_best_calls", [])
        if not isinstance(next_calls, list):
            next_calls = []
        unresolved = parsed.get("unresolved_intent", [])
        if not isinstance(unresolved, list):
            unresolved = []

        return OracleResponse(
            numerical_claims=claims,
            narrative=narrative,
            ambiguity_axes=[str(x) for x in ambiguity],
            confidence=confidence,
            next_best_calls=[str(x) for x in next_calls],
            unresolved_intent=[str(x) for x in unresolved],
            meta=OracleMeta(
                model_id=self._model,
                # Hash of the model NAME, not weights. Two different
                # Ollama pulls of `llama3.1:8b` (different quantizations,
                # fine-tunes) produce identical hashes. For a true
                # weight-fingerprint we'd need to read the model
                # blob from `~/.ollama/models/` — deferred to a future
                # ADR. The field name is preserved for ADR-0022
                # contract stability; institutions needing weight-
                # provenance should record it out-of-band today.
                model_version_hash=hashlib.sha256(
                    self._model.encode()
                ).hexdigest()[:16],
                tier=self._tier,
                latency_ms=latency_ms,
                prompt_hash=prompt_hash,
                called_at=datetime.now(timezone.utc).isoformat(),
                processing_calls=list(request.resolved_context.keys()),
                backend="ollama",
            ),
        )

    def _fallback_response(
        self,
        request: OracleRequest,
        prompt_hash: str,
        start: float,
        error: str,
    ) -> OracleResponse:
        latency_ms = int((time.time() - start) * 1000)
        claims = _flatten_claims(request.resolved_context)
        # ADR 0023 PR2 — gap-reasoning fields are LLM-generated, so the
        # fallback path emits empty lists. The fallback is the structural
        # signal that no LLM was in the loop; emitting fabricated next-
        # call suggestions here would defeat that signal.
        return OracleResponse(
            numerical_claims=claims,
            narrative=(
                f"Local-LLM guardian unavailable ({error}); deterministic "
                f"numerical claims above are still citable."
            ),
            ambiguity_axes=[],
            confidence=0.0,
            next_best_calls=[],
            unresolved_intent=[],
            meta=OracleMeta(
                model_id=self._model,
                model_version_hash="unavailable",
                tier=self._tier,
                latency_ms=latency_ms,
                prompt_hash=prompt_hash,
                called_at=datetime.now(timezone.utc).isoformat(),
                processing_calls=list(request.resolved_context.keys()),
                backend="ollama-fallback",
            ),
        )

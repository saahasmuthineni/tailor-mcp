"""
Local-LLM backend ABC.

A backend wraps a specific local-inference runtime (Ollama,
llama.cpp, MLX, ...) and exposes a uniform :meth:`compose` method.
The framework calls ``compose()`` with an :class:`OracleRequest` and
expects an :class:`OracleResponse` back, schema-shape-validated.

The default backend is :class:`NullBackend` — registered when the
operator has not opted in. ``NullBackend`` returns a structured
"local LLM not configured" response so callers can branch without
crashing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..oracle import OracleRequest, OracleResponse


class LocalLLMBackend(ABC):
    """Abstract base for local-LLM backends."""

    @property
    @abstractmethod
    def backend_id(self) -> str:
        """Stable identifier for the audit log (e.g., 'null', 'ollama')."""
        ...

    @property
    @abstractmethod
    def tier(self) -> str:
        """Tier codename: 'scout' | 'sentinel' | 'guardian' | 'titan' | 'null'."""
        ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Model identifier used by this backend (e.g., 'llama3.1:8b')."""
        ...

    @abstractmethod
    async def compose(self, request: OracleRequest) -> OracleResponse:
        """
        Compose an OracleResponse over the resolved context.

        Per ADR 0022's resolved-context tool-calling style, the
        framework has already computed all deterministic processing
        calls and supplied results in ``request.resolved_context``.
        The backend's job is to compose a structured OracleResponse
        — it MUST NOT invent numerical claims; ``numerical_claims``
        in the response come from ``resolved_context``, never from
        the LLM's free-text generation.
        """
        ...

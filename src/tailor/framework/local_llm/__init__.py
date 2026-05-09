"""
Local LLM Layer — public API
=============================
Framework-tier infrastructure that mediates between the hosted LLM
and biometric data using a local LLM running on the analyst's
machine. Registered with the router parallel to ``VaultLayer``;
skips biosensor-tier gates (consent, cost, circuit breaker,
PHI-scrub) — only param validation and audit apply.

The architectural commitment is captured in ADR 0022. The
load-bearing object is :class:`OracleResponse`, whose schema
enforces the separation between citable deterministic numerical
claims (from ``processing.py``) and non-citable LLM-generated
narrative.

Tier codenames (per ADR 0022):
    Scout     llama3.2:1b   ~1.2 GB RAM   4 GB laptop floor
    Sentinel  phi3.5:3.8b   ~3 GB RAM     8 GB laptop floor
    Guardian  llama3.1:8b   ~6 GB RAM     16 GB laptop floor (default)
    Titan     qwen2.5:14b   ~10 GB RAM    32 GB workstation floor
"""

from .backends import LocalLLMBackend
from .backends.null import NullBackend
from .backends.ollama import OllamaBackend
from .layer import ORACLE_MEDIATED_TOOLS, LocalLLMLayer
from .oracle import (
    DEFAULT_TIER,
    LOCAL_LLM_TIERS,
    NumericalClaim,
    OracleMeta,
    OracleRequest,
    OracleResponse,
)

__all__ = [
    "DEFAULT_TIER",
    "LOCAL_LLM_TIERS",
    "ORACLE_MEDIATED_TOOLS",
    "LocalLLMBackend",
    "LocalLLMLayer",
    "NullBackend",
    "NumericalClaim",
    "OllamaBackend",
    "OracleMeta",
    "OracleRequest",
    "OracleResponse",
]

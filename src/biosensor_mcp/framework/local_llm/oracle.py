"""
Oracle Contract — Structured LLM-to-LLM Communication
=====================================================
The :class:`OracleResponse` is the load-bearing object the local
LLM returns. It enforces a separation between *cited* output
(deterministic numerical claims grounded in processing.py calls
— citable in a manuscript) and *narrative* output (LLM-generated
prose — explicitly labeled non-citable).

This separation is the architectural property that lets the
local LLM coexist with ADR 0008's deterministic-by-construction
processing invariant. The local LLM never replaces processing;
it composes structured responses over processing's output.

See ADR 0022 for the full architectural rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NumericalClaim:
    """
    A single deterministic numerical claim in an OracleResponse.

    The value comes from a deterministic ``processing.py`` function;
    the local LLM does NOT generate the value, it only composes
    over it. Citable in manuscripts via ``processing_call``.
    """

    metric: str  # e.g. "decline_rate_per_min", "decoupling_pct"
    value: float | int | None  # the actual number (or None if not computable)
    unit: str = ""  # e.g. "bpm", "%", "seconds"
    subject_id: str | None = None  # optional; identifies which subject this claim is about
    processing_call: str = ""  # e.g. "csv_force_decline" — the deterministic source

    def to_dict(self) -> dict:
        d: dict = {"metric": self.metric, "value": self.value}
        if self.unit:
            d["unit"] = self.unit
        if self.subject_id is not None:
            d["subject_id"] = self.subject_id
        if self.processing_call:
            d["processing_call"] = self.processing_call
        return d


@dataclass
class OracleMeta:
    """Provenance for an OracleResponse — written into _meta block."""

    model_id: str
    model_version_hash: str
    tier: str  # "scout" | "sentinel" | "guardian" | "titan" | "null"
    latency_ms: int
    prompt_hash: str
    called_at: str  # ISO 8601 UTC
    processing_calls: list[str] = field(default_factory=list)
    backend: str = ""  # "null" | "ollama" | etc.
    narrative_disclaimer: str = (
        "narrative is LLM-generated and non-citable; "
        "cite from numerical_claims."
    )

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "model_version_hash": self.model_version_hash,
            "tier": self.tier,
            "latency_ms": self.latency_ms,
            "prompt_hash": self.prompt_hash,
            "called_at": self.called_at,
            "processing_calls": self.processing_calls,
            "backend": self.backend,
            "narrative_disclaimer": self.narrative_disclaimer,
        }


@dataclass
class OracleRequest:
    """
    Input to the local LLM.

    The framework pre-resolves the deterministic processing
    call(s) this question requires and passes them as
    ``resolved_context`` — the LLM only composes over already-
    computed data (resolved-context tool-calling, per ADR 0022).
    """

    question: str
    resolved_context: dict  # {processing_call_name: result_dict}
    subject_id: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "question": self.question,
            "resolved_context": self.resolved_context,
        }
        if self.subject_id is not None:
            d["subject_id"] = self.subject_id
        return d


@dataclass
class OracleResponse:
    """
    Structured response from the local LLM.

    Architecture:
        ``numerical_claims`` — deterministic, citable. From processing.py.
        ``narrative``        — LLM-generated, non-citable. Labeled in _meta.
        ``ambiguity_axes``   — research-question disambiguation hints.
        ``confidence``       — 0.0..1.0; below ~0.4 → escalate.
        ``meta``             — provenance.

    See ADR 0022 § "The structured OracleResponse contract".
    """

    numerical_claims: list[NumericalClaim]
    narrative: str
    ambiguity_axes: list[str]
    confidence: float
    meta: OracleMeta
    # ADR 0023 — populated by LocalLLMLayer (not the backend) after
    # backend.compose() returns. Deterministic vault scan; default
    # empty so existing callers and backends are unaffected.
    related_substrate: list[dict] = field(default_factory=list)
    # Surfaces a swallowed VaultStorage exception into the wire payload
    # so an IRB reviewer or analyst can distinguish "scan ran cleanly
    # and found nothing" (count=0, warning=None) from "scan crashed
    # silently" (count=0, warning=<reason>). Parallels the
    # scrubber_warning seam ADR 0003 / v6.3.1 introduced for the
    # PHI-scrubber default. Stays None on the happy path; only set
    # when the substrate scan caught an exception.
    substrate_scan_warning: str | None = None

    def to_dict(self) -> dict:
        d = {
            "numerical_claims": [c.to_dict() for c in self.numerical_claims],
            "narrative": self.narrative,
            "ambiguity_axes": self.ambiguity_axes,
            "confidence": round(self.confidence, 3),
            "related_substrate": self.related_substrate,
            "_meta": self.meta.to_dict(),
        }
        if self.substrate_scan_warning is not None:
            d["substrate_scan_warning"] = self.substrate_scan_warning
        return d


# Tier codenames (per ADR 0022).
# Cited numerical claims are identical across tiers (they come from
# deterministic processing). What varies is narrative quality,
# ambiguity-axis detection, and refusal calibration.
LOCAL_LLM_TIERS: dict[str, dict] = {
    "scout": {"model": "llama3.2:1b", "ram_gb": 1.2, "floor_gb": 4},
    "sentinel": {"model": "phi3.5:3.8b", "ram_gb": 3.0, "floor_gb": 8},
    "guardian": {"model": "llama3.1:8b", "ram_gb": 6.0, "floor_gb": 16},
    "titan": {"model": "qwen2.5:14b", "ram_gb": 10.0, "floor_gb": 32},
}
DEFAULT_TIER = "guardian"

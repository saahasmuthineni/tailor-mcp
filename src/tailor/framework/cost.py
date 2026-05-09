"""
Biosensor-to-LLM Framework — Cost gating and token accounting
==============================================================
The cost gate is a pre-execution check (see ADR 0005). It calls the
child's ``estimate_cost()`` *before* dispatching the tool, using
stream metadata only — never the full payload. If the estimate
exceeds the configured threshold, the router returns a
``COST_APPROVAL_REQUIRED`` ``LLMInstruction`` and never invokes the
tool.

The token ledger is the per-session accumulator that backs the
``status_session()`` view. It's strictly observational and does not
participate in any gating decision.

The ``estimate_tokens`` helper is a rough char-count fallback used
where a child has not declared a more precise estimator.
"""

from datetime import datetime, timezone
from typing import Any

from .audit import _dumps

# ═══════════════════════════════════════════════════════════════
# COST GATE
# ═══════════════════════════════════════════════════════════════

class CostGate:
    """
    Token cost gate. Fires when pre-estimated cost exceeds threshold.

    Uses the child's estimate_cost() — no wasted computation.
    Shows the user full vs. cheaper alternative costs before proceeding.
    Generates human-relatable context so raw token counts aren't presented alone.
    """

    # Baseline for "typical call" comparison (~800 tokens for a run report)
    TYPICAL_CALL_TOKENS = 800

    def __init__(self, threshold: int = 35_000):
        self.threshold = threshold

    def should_gate(self, estimated_tokens: int) -> bool:
        return estimated_tokens >= self.threshold

    def humanize(self, tokens: int, alternative_tokens: int = 0) -> dict:
        """
        Build a CostContext dict with human-relatable anchors.

        Returns a plain dict (not CostContext dataclass) for zero-import
        serialization in the router. Keeps the interface minimal.
        """
        multiple = round(tokens / self.TYPICAL_CALL_TOKENS)
        ctx: dict = {
            "tokens": tokens,
            "relative_to_typical": f"~{multiple}x a typical analysis call",
        }
        if alternative_tokens > 0:
            ratio = round(tokens / max(alternative_tokens, 1))
            ctx["relative_to_cheaper_pct"] = (
                f"~{ratio}x more than the downsampled alternative"
            )
        return ctx


# ═══════════════════════════════════════════════════════════════
# TOKEN LEDGER
# ═══════════════════════════════════════════════════════════════

class TokenLedger:
    """Track cumulative token spend per session, broken down by domain."""

    def __init__(self):
        self._entries: list[dict] = []
        self.session_start = datetime.now(timezone.utc)

    def add(self, domain: str, tool_name: str, tokens: int):
        self._entries.append({
            "domain": domain,
            "tool": tool_name,
            "tokens": tokens,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    @property
    def total(self) -> int:
        return sum(e["tokens"] for e in self._entries)

    def by_domain(self) -> dict[str, int]:
        domains: dict[str, int] = {}
        for e in self._entries:
            domains[e["domain"]] = domains.get(e["domain"], 0) + e["tokens"]
        return domains

    def summary(self) -> dict:
        return {
            "session_total_tokens": self.total,
            "call_count": len(self._entries),
            "by_domain": self.by_domain(),
        }


# ═══════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════

def estimate_tokens(data: Any) -> int:
    """Rough token estimate: ~4 chars per token for JSON payloads."""
    text = _dumps(data) if not isinstance(data, str) else data
    return len(text) // 4

"""
Biosensor-to-LLM Framework
===========================
Local-first router and middleware for LLM-assisted analysis of
high-frequency biometric data in research settings.

The framework is domain-agnostic. It owns the cross-cutting concerns
that research workflows need regardless of data source: parameter
validation, circuit breaking, per-domain consent, cost gating, a
PHI-scrubbing seam, an audit log suitable for reproducibility and
IRB review, and cumulative token accounting. Domain-specific logic
(one data source per child) lives in ChildMCPs that register with
the router.
"""

from .interfaces import (
    ChildMCP,
    ConsentInfo,
    ConsentScope,
    CostContext,
    CostEstimate,
    LLMInstruction,
    ToolDefinition,
    ValidationSchema,
)
from .middleware import (
    AuditLog,
    CircuitBreaker,
    ConsentGate,
    CostGate,
    ParamValidator,
    TokenLedger,
)
from .storage import BaseStorage

# RouterMCP import deferred — requires 'mcp' package at runtime
# Use: from biosensor_mcp.framework.router import RouterMCP

__all__ = [
    "ChildMCP", "ToolDefinition", "CostEstimate", "ValidationSchema",
    "ConsentInfo", "ConsentScope", "CostContext", "LLMInstruction",
    "CircuitBreaker", "ConsentGate", "CostGate",
    "AuditLog", "TokenLedger", "ParamValidator",
    "BaseStorage",
]

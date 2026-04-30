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

Module layout (since v5.0.0):
- ``framework.security``  — ParamValidator, CircuitBreaker,
                            ConsentGate, PHIScrubber
- ``framework.cost``      — CostGate, TokenLedger, estimate_tokens
- ``framework.audit``     — AuditLog (and the JSON helpers used
                            across the framework)
- ``framework.router``    — RouterMCP (deferred import; needs ``mcp``)
- ``framework.storage``   — BaseStorage
- ``framework.interfaces`` — ChildMCP ABC, dataclasses, ConsentScope
- ``framework.vault``     — VaultLayer + VaultWriter (reorientation tier)
"""

from .audit import AuditLog
from .cost import CostGate, TokenLedger, estimate_tokens
from .interfaces import (
    SUBJECT_ID_PARAM_DOC,
    SUBJECT_ID_SCHEMA,
    ChildMCP,
    ConsentInfo,
    ConsentScope,
    CostContext,
    CostEstimate,
    LLMInstruction,
    ToolDefinition,
    ValidationSchema,
)
from .security import (
    CircuitBreaker,
    ConsentGate,
    ParamValidator,
    PHIScrubber,
)
from .storage import BaseStorage

# RouterMCP import deferred — requires 'mcp' package at runtime
# Use: from biosensor_mcp.framework.router import RouterMCP

__all__ = [
    # interfaces
    "ChildMCP", "ToolDefinition", "CostEstimate", "ValidationSchema",
    "ConsentInfo", "ConsentScope", "CostContext", "LLMInstruction",
    "SUBJECT_ID_SCHEMA", "SUBJECT_ID_PARAM_DOC",
    # security
    "CircuitBreaker", "ConsentGate", "ParamValidator", "PHIScrubber",
    # cost
    "CostGate", "TokenLedger", "estimate_tokens",
    # audit
    "AuditLog",
    # storage
    "BaseStorage",
]

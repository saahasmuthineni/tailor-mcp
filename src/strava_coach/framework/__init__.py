"""
Biosensor-to-LLM Framework
===========================
Parent router MCP with security middleware for piping
high-frequency biosensor data into LLM context windows.

Domain-agnostic: the framework handles consent, cost gating,
circuit breaking, audit, and token budgeting. Domain-specific
logic lives in child MCPs that register with the router.
"""

from .interfaces import (
    ChildMCP, ToolDefinition, CostEstimate, ValidationSchema,
    ConsentInfo, ConsentScope, CostContext, LLMInstruction,
)
from .middleware import (
    CircuitBreaker, ConsentGate, CostGate,
    AuditLog, TokenLedger, ParamValidator,
)
from .storage import BaseStorage

# RouterMCP import deferred — requires 'mcp' package at runtime
# Use: from strava_coach.framework.router import RouterMCP

__all__ = [
    "ChildMCP", "ToolDefinition", "CostEstimate", "ValidationSchema",
    "ConsentInfo", "ConsentScope", "CostContext", "LLMInstruction",
    "CircuitBreaker", "ConsentGate", "CostGate",
    "AuditLog", "TokenLedger", "ParamValidator",
    "BaseStorage",
]

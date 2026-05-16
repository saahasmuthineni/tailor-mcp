"""
Framework-level audit-query layer — IRB-grade query surface over audit_log.

See ADR 0012 § Amendment v7.4.0 for the architectural rationale: the
fourth framework-tier layer parallel to VaultLayer / LocalLLMLayer /
SetupHelpLayer. Closes the v7.3.4 audit-log-over-promise gap.

Public surface:
    AuditQueryLayer   The layer class. Construct with an AuditLog
                      reference; register with RouterMCP via
                      ``router.register_audit_query_layer(layer)``.
    parse_since       The since-parameter parser. Exposed for unit
                      testing the parser without going through the
                      layer.
    SinceParseError   Typed parser exception.
    MAX_LOOKBACK_DAYS Hard cap on lookback window (90 days).
"""

from .layer import AuditQueryLayer
from .parser import MAX_LOOKBACK_DAYS, SinceParseError, parse_since

__all__ = [
    "AuditQueryLayer",
    "MAX_LOOKBACK_DAYS",
    "SinceParseError",
    "parse_since",
]

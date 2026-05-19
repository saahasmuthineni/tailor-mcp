"""
Walkthrough Layer — Framework-tier architectural showcase.

Exposes a single MCP tool (``tailor_walkthrough_section``) that
surfaces the v6.12.0 5-section architectural showcase (per ADR 0027 +
ADR 0029) as a conversational tour Claude conducts with the recipient.
Replaces the v6.10.5 / v7.1.0 ``tailor walkthrough`` CLI command per
ADR 0040.

Skips biosensor-tier gates (consent, cost, circuit breaker, framework
PHI scrub) per the framework-tier-layer pattern codified in ADR 0012
§ Amendment v7.4.0 — the walkthrough surfaces architectural narrative
and pre-bundled example outputs, not biosensor data flow.
"""

from __future__ import annotations

from .layer import WalkthroughLayer

__all__ = ["WalkthroughLayer"]

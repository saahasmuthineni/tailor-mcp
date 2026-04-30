"""
Biosensor MCP — Local-First LLM-Assisted Biometric Analysis
============================================================
A local-first MCP server for LLM-assisted analysis of
high-frequency biometric data in health research workflows.

The framework (``biosensor_mcp.framework``) is domain-agnostic:
it owns parameter validation, circuit breaking, per-domain
consent, cost gating, a PHI-scrubbing seam, an audit log suited
to IRB review and reproducibility, and cumulative token
accounting. Each data source is a ChildMCP. The running child
(``biosensor_mcp.children.running``) is one worked example.
"""

__version__ = "6.2.1"

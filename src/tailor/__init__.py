"""
Tailor — Local-First LLM-Assisted Analysis of Your Own Data
============================================================
A local-first MCP server that lets any MCP-speaking AI work
with your own data without that data leaving your machine.

The framework (``tailor.framework``) is data-agnostic: it owns
parameter validation, circuit breaking, per-domain consent,
cost gating, a ``DataScrubber`` seam, an audit log suited to
reproducibility and IRB review, and cumulative token
accounting. Each data source is a ChildMCP. Health research is
the first worked example (``tailor.children.running``), not the
platform's identity.
"""

__version__ = "9.0.2"

"""
Strava Run Coach — Biosensor-to-LLM Reference Implementation
==============================================================
MCP server demonstrating the parent/child pattern for efficiently
piping high-frequency biosensor data into LLM context windows.

The framework (biosensor_mcp.framework) is domain-agnostic.
The running child (biosensor_mcp.children.running) is the first
concrete implementation, using Strava as the data source.
"""

__version__ = "4.0.0"

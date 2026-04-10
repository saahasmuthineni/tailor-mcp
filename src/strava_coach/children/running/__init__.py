"""
Running Child MCP — Strava Integration
========================================
Implements ChildMCP for running data sourced from Strava.

This is one concrete child in the parent/child architecture.
Other biosensor sources (CGM, sleep, ECG) would implement
their own ChildMCP with domain-specific tools and processing.
"""

from .child import RunningChild

__all__ = ["RunningChild"]

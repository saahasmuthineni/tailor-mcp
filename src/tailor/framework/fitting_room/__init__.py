"""
Fitting Room Layer — Framework-tier bundled-demo scaffold surface.

Exposes two MCP tools that recipients invoke through Claude Desktop:
``tailor_fitting_room_scaffold`` (copy bundled fixtures + write demo
user_config + index vault) and ``tailor_fitting_room_status`` (check
whether the demo scaffold exists on the local filesystem).

Replaces the v6.9.0 ``tailor fitting-room`` CLI command per ADR 0040.
Notably, the new MCP path does NOT write Claude Desktop config — that
happens once via ``tailor pilot`` as the operator/RSE bootstrap path.
"""

from __future__ import annotations

from .layer import FittingRoomLayer

__all__ = ["FittingRoomLayer"]

"""
Thin shim — delegates to the ``tailor.fitting_room`` library entry point.

Pre-v6.9.0 this script was the in-repo scaffolder for the demo cohort
realistic demo. v6.9.0 ([ADR 0024](../../../docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md))
moved scaffolding into ``tailor.tour`` so non-technical recipients
could run the demo from a pre-built wheel without GitHub access.
v7.1.0 ([ADR 0035](../../../docs/adr/0035-cli-rename-walkthrough-and-fitting-room-and-recipient-experience-naming-principle.md))
renamed the module to ``tailor.fitting_room``. v8.0.0
([ADR 0040](../../../docs/adr/0040-bounded-setup-time-conductor-surface.md))
hard-removed the ``tailor fitting-room`` CLI command — the recipient
path is now the ``tailor_fitting_room_scaffold`` MCP tool that Claude
calls on request. ``tailor.fitting_room.main()`` is preserved as a
library entry point for developer convenience (this script + rehearsal
scripts), so ``python setup.py`` still works for repo developers.

This file is *not* the canonical end-user path — recipients of the
wheel ask Claude to scaffold the demo through Claude Desktop.
"""

from __future__ import annotations

import sys

if __name__ == "__main__":
    # v8.0.0: imports flipped from ``tailor.tour`` (retired shim) to
    # ``tailor.fitting_room`` (canonical library entry point).
    from tailor.fitting_room import main as fitting_room_main
    sys.exit(fitting_room_main(["--variant=cohort", "--no-claude-desktop"]))

"""
Thin shim — delegates to ``tailor fitting-room``.

Pre-v6.9.0 this script was the in-repo scaffolder for the HIP Lab
realistic demo. v6.9.0 ([ADR 0024](../../../docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md))
moved scaffolding into ``tailor.tour`` so non-technical
recipients can run the demo from a pre-built wheel without GitHub
access. v7.1.0 ([ADR 0035](../../../docs/adr/0035-cli-rename-walkthrough-and-fitting-room-and-recipient-experience-naming-principle.md))
renamed the CLI verb to ``tailor fitting-room`` and the module to
``tailor.fitting_room``; ``tailor.tour`` is retained as a one-cycle
re-export shim so this file's import statement keeps working through
v7.1.x without an update. This file remains as a dev-convenience entry
point so:

- Muscle memory (``python setup.py``) keeps working for repo
  developers.
- Symmetry with ``examples/hip_lab_demo/beta/setup.py`` is
  preserved.
- External references (project memory, prior commit messages,
  CLAUDE.md release banners) stay valid.

It is *not* the canonical end-user path — recipients of the wheel
run ``tailor fitting-room`` directly. If you are reading this in
the source tree, ``python examples/hip_lab_demo/realistic/setup.py``
and ``tailor fitting-room --variant=hip-lab --no-claude-desktop``
are equivalent.
"""

from __future__ import annotations

import sys

if __name__ == "__main__":
    # NOTE: ``tailor.tour`` is the v6.9.0 module path; the v7.1.0
    # rename retained it as a re-export shim so this import keeps
    # working through v7.1.x. The shim retires in v7.2.0 alongside
    # the CLI deprecation alias; this import flips to
    # ``from tailor.fitting_room import main as fitting_room_main``
    # then.
    from tailor.tour import main as tour_main
    sys.exit(tour_main(["--variant=hip-lab", "--no-claude-desktop"]))

"""
Thin shim — delegates to ``tailor tour``.

Pre-v6.9.0 this script was the in-repo scaffolder for the HIP Lab
realistic demo. v6.9.0 ([ADR 0024](../../../docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md))
moved scaffolding into ``tailor.tour`` so non-technical
recipients can run the demo from a pre-built wheel without GitHub
access. This file remains as a dev-convenience entry point so:

- Muscle memory (``python setup.py``) keeps working for repo
  developers.
- Symmetry with ``examples/hip_lab_demo/beta/setup.py`` is
  preserved.
- External references (project memory, prior commit messages,
  CLAUDE.md release banners) stay valid.

It is *not* the canonical end-user path — recipients of the wheel
run ``tailor tour`` directly. If you are reading this in
the source tree, ``python examples/hip_lab_demo/realistic/setup.py``
and ``tailor tour --variant=hip-lab --no-claude-desktop``
are equivalent.
"""

from __future__ import annotations

import sys

if __name__ == "__main__":
    from tailor.tour import main as tour_main
    sys.exit(tour_main(["--variant=hip-lab", "--no-claude-desktop"]))

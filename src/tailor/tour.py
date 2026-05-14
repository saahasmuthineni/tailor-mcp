"""
Deprecated module path — re-export shim for ``tailor.fitting_room``.

``tailor.tour`` was renamed to ``tailor.fitting_room`` in v7.1.0 per
[ADR 0035](../../docs/adr/0035-cli-rename-walkthrough-and-fitting-room-and-recipient-experience-naming-principle.md).
This file is a re-export shim retained for one cycle to preserve

    from tailor.tour import main as tour_main

in ``examples/hip_lab_demo/realistic/setup.py`` and
``examples/hip_lab_demo/realistic/rehearse.py``, which were committed
before the rename. The shim is removed in v7.2.0 alongside the
``tailor tour`` CLI deprecation alias.

New code should import from ``tailor.fitting_room``.
"""

from tailor.fitting_room import main  # noqa: F401

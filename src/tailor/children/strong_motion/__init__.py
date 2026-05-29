"""
Strong-Motion Child MCP — COSMOS V1 Acceleration Records
=========================================================
The launch worked-example child (issue #114). Wraps a local directory
of COSMOS Volume-1 (uncorrected acceleration) strong-motion records and
exposes peak ground acceleration, Arias intensity, significant
duration, and response spectra through the framework's tiered security
pipeline.

Stdlib-only: the COSMOS V1 format is fixed-width text, so no optional
extra is required (contrast ``matlab_file``, which needs scipy).

Opt-in via a ``strong_motion`` block in ``user_config.json``; default
deployments are behaviourally unchanged.
"""

from .child import StrongMotionChild
from .parser import ParseRefusalError, StrongMotionRecord
from .processing import StrongMotionProcessing

__all__ = [
    "StrongMotionChild",
    "StrongMotionProcessing",
    "ParseRefusalError",
    "StrongMotionRecord",
]

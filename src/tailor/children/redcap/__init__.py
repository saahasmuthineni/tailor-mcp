"""
REDCap File Child — Export-Directory Ingestion
================================================
Wraps a local directory of REDCap CSV/JSON exports accompanied by a
REDCap data dictionary (``project_metadata.csv``) and exposes tiered
analytical tools through the framework's security pipeline. No vendor
API tokens, no rate limits — pure file-reading against stdlib ``csv``
and ``json``.

Scope per ADR 0037: this child supports REDCap **export-directory
wrapping only**. The live REDCap REST API is deferred behind a future
superseding ADR (reversal condition: first beachhead lab hits a
use-case that requires API-mediated access against a running REDCap
server).

Built-in PHI scrubbing per ADR 0003 § Amendment 2026-05-14: the child
ships ``RedcapPHIScrubber``, a parallel seam to the framework-level
``PHIScrubber``. The child-level scrubber reads ``project_metadata.csv``
identifier flags set by the IRB at protocol creation and strips
identifier-flagged fields from every Tier-1+ result before return.
Unknown-field default is identifier-positive (fail-closed) so a
mid-study field addition cannot silently leak.

The child is registered by ``__main__.py`` when the ``redcap_file``
key is present in ``user_config.json``. See the module-level docstring
in ``child.py`` for the config shape.

Shape-contract tests at ``tests/children/redcap/test_redcap_shape.py``
mirror the matlab_file shape tests.
"""

from .child import RedcapFileChild
from .processing import RedcapProcessing
from .scrubber import RedcapPHIScrubber

__all__ = ["RedcapFileChild", "RedcapProcessing", "RedcapPHIScrubber"]

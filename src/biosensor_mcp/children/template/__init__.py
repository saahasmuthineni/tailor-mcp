"""
Template Child MCP — Skeleton for New Data Sources
====================================================
A minimal, runnable ChildMCP you can copy when wrapping a new
biometric data source (CGM, sleep, ECG, CSV directory, EDF file,
FHIR bundle, REDCap export, etc.).

This package is **NOT registered** by ``__main__.py`` — it ships
as reference code only. If you import ``TemplateChild`` into a
real deployment without renaming it, the router will register its
tools under the ``example`` domain, which is almost certainly not
what you want.

How to use
----------

1. Copy this directory to a sibling:
   ``src/biosensor_mcp/children/<yourdomain>/``
2. Rename ``TemplateChild`` → ``<Yourdomain>Child`` and
   ``TemplateProcessing`` → ``<Yourdomain>Processing``.
3. Work through the ``# FILL IN:`` comments in ``child.py``.
   There are five substantive "blanks":

     a. ``domain`` and ``display_name`` — the human-facing labels
     b. ``consent_info`` — the data types and purpose string shown
        in the consent prompt
     c. ``__init__`` body — wire your data source (API client,
        ``BaseStorage`` subclass, file reader, etc.)
     d. ``tool_definitions`` / ``param_schemas`` — rename the
        five stub tools to match your domain and adjust schemas
     e. The ``execute()`` handler bodies — replace the echo stubs
        with real logic

4. Add a registration line in ``src/biosensor_mcp/__main__.py``
   alongside ``router.register_child(running)``.

The template ships with shape tests at
``tests/children/template/test_template_shape.py``. They are a
copyable contract-test skeleton you can retarget at your new
child to catch schema drift early.
"""

from .child import TemplateChild
from .processing import TemplateProcessing

__all__ = ["TemplateChild", "TemplateProcessing"]

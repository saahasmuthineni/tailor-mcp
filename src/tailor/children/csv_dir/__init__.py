"""
Generic CSV Directory Child
============================
Wraps a local directory of per-subject CSV files with a declared
timestamp column and value schema.  Exposes five tiered analytical
tools — the lowest-lift path from bespoke per-study scripts to
framework-governed tooling.

Forked from ``src/tailor/children/template/``.

Unlike the template, this child IS registered by ``__main__.py``
when the ``csv_dir`` key is present in ``user_config.json``.  See
the module-level docstring in ``child.py`` for the config shape.

Registration (already wired in ``__main__.py``):

.. code-block:: python

    csv_cfg = user_config.get("csv_dir")
    if csv_cfg:
        from tailor.children.csv_dir import CSVDirectoryChild
        csv_child = CSVDirectoryChild(config_dir=CONFIG_DIR, data_dir=DATA_DIR)
        router.register_child(csv_child)

Shape-contract tests at ``tests/children/csv_dir/test_csv_shape.py``
mirror the template's shape tests.
"""

from .child import CSVDirectoryChild
from .processing import CSVProcessing

__all__ = ["CSVDirectoryChild", "CSVProcessing"]

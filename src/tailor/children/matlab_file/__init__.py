"""
MATLAB File Child — `.mat` Binary Format Ingestion
====================================================
Wraps a local directory of MATLAB binary `.mat` files (version
v5/v6/v7.2) and exposes tiered analytical tools through the
framework's security pipeline. No vendor API, no credentials —
pure file-reading against scipy's MATLAB loader.

Forked from ``src/tailor/children/csv_dir/``.

Unlike csv_dir, the MATLAB child requires an **optional dependency**
(`scipy`). Install with::

    pip install tailor-mcp[matlab]

Scope per ADR 0036: this child supports `.mat` v5/v6/v7.2 only.
MATLAB R2006b+ defaults to v7.3 (HDF5-based) for files >2GB, which
requires `h5py` and a structurally different traversal pattern. v7.3
support is held behind a future superseding ADR.

The child is registered by ``__main__.py`` when the ``matlab_file``
key is present in ``user_config.json``. See the module-level
docstring in ``child.py`` for the config shape.

Shape-contract tests at ``tests/children/matlab_file/test_matlab_shape.py``
mirror the csv_dir shape tests.
"""

from .child import MATLABFileChild
from .processing import MATLABProcessing

__all__ = ["MATLABFileChild", "MATLABProcessing"]

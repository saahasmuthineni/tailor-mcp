"""
Bundled non-code resources shipped inside the wheel.

The ``multi_subject_pilot/csv/`` directory holds the synthetic three-
participant fixtures the ``biosensor-mcp pilot`` wizard offers as the
default CSV directory for "I just want to try it."

Resources are accessed via ``importlib.resources.files`` so they work
identically in source-tree, ``pip install``, ``uv tool install``, and
PyInstaller-bundled distributions. See ``pyproject.toml`` for the
``package-data`` glob that ships these files in the wheel.
"""

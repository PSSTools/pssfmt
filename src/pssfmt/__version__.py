"""Single source of the package version.

Kept in its own module so ``pyproject.toml`` can read it via
``[tool.setuptools.dynamic]`` without importing the package (which would drag
in pssparser at build time).
"""

_pkg_version = "0.2.0"

__version__ = _pkg_version

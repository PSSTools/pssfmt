"""Sphinx configuration.

Follows ``pygments-pss`` rather than ``pssparser``: ``sphinx`` + ``furo``,
because ``pssfmt`` is pure Python, so autodoc needs a plain ``sys.path`` entry
and none of the compiled-extension handling that ``pssparser/docs/conf.py``
documents at length.

**Nothing in ``docs/`` renders the repository's working notes, and that is
deliberate.** This tree used to carry ``docs/design/``, two stubs that
``{include}``-ed the root ``PLAN.md`` and ``formatter.md`` so a living design
document would not need a second copy. The reasoning was sound and the result
was not: those files are drafting documents -- continuously revised, written
to think in rather than to be read -- and publishing them presented working
notes as documentation. They were also untracked, so the tracked stubs
included files that did not exist in a fresh clone, and ``-W`` turned every
resulting warning into a failed build. A docs job that only passes on the
author's machine is worse than no docs job.

Anything from those notes that a reader needs is written into a real page
instead. ``myst_parser`` stays enabled although no Markdown is rendered today;
it costs nothing and the next ``.md`` page should not need a config change.

``sphinx_pss`` gives PSS code blocks real highlighting. It is a dev
dependency, so the build degrades to unhighlighted literal blocks rather than
failing when it is absent -- a docs build that cannot run without the whole
toolchain is a docs build nobody runs.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath("../src"))

project = "pssfmt"
copyright = "2026, Matthew Ballance"
author = "Matthew Ballance"

try:
    from pssfmt.__version__ import _pkg_version as release
except ImportError:  # pragma: no cover -- docs built from a bare checkout
    release = "0.0.0"
version = release

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "myst_parser",
]

try:
    import sphinx_pss  # noqa: F401

    extensions.append("sphinx_pss")
except ImportError:  # pragma: no cover
    pass

myst_enable_extensions = ["colon_fence", "deflist", "fieldlist"]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_static_path = ["_static"]
html_title = f"pssfmt {version}"

autodoc_member_order = "bysource"
autodoc_typehints = "description"

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

# T-10 builds these docs with -W. Anything listed here is a warning we have
# decided to live with, and the list should stay empty.
nitpicky = False
suppress_warnings: list = []

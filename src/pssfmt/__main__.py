"""``python -m pssfmt``.

A second entry point rather than a convenience: the console script only exists
once the package has been installed, and ``python -m`` works from a source
checkout, from a wheel, and inside a virtualenv whose ``bin`` is not on
``PATH``. Editor integrations and CI steps reach for it for exactly that
reason.
"""

from .cli import run

run()

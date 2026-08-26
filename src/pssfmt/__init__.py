"""pssfmt -- a formatter for the Accellera Portable Test and Stimulus Standard.

The public surface is deliberately thin while the pipeline is being built.
Everything under :mod:`pssfmt.layout` is dependency-free by design and is
importable on its own (``formatter.md`` section 10.3, enforced by ``T-9``).
"""

from .__version__ import __version__

__all__ = ["__version__"]

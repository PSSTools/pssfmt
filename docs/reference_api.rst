API reference
=============

Only :mod:`pssfmt.layout` is documented here, because only
:mod:`pssfmt.layout` is public. It is also the extraction candidate: it
depends on nothing, so it could become a standalone package if anything else
ever wants a Wadler pretty-printer.

The rest of ``pssfmt`` is internal until the pipeline exists and its shape has
stopped moving.

Layout IR
---------

.. automodule:: pssfmt.layout.ir
   :members:
   :undoc-members:
   :show-inheritance:

Layout engine
-------------

.. automodule:: pssfmt.layout.engine
   :members: render, propagate_breaks

Column alignment
----------------

.. automodule:: pssfmt.layout.align
   :members: align_text, strip_marks, AlignMode, GroupBoundary, ALIGN_MARK

Width
-----

.. automodule:: pssfmt.layout.width
   :members:

pssfmt
======

A formatter for the Accellera Portable Test and Stimulus Standard.

.. warning::

   **Pre-alpha.** ``pssfmt`` cannot format a file yet: it has no style rules.
   What it *does* have is everything underneath them -- a layout engine, the
   comment-attachment model, and a verifier with a fail-safe -- plus the proof
   that the pipeline never loses a byte. The null formatter reproduces every
   file in the test corpus exactly, which is the point at which style
   decisions become the only thing left and the only thing reversible.

   Follow :doc:`design/plan` for what is done and what is next.

Three audiences, three toctrees, and keeping them apart is deliberate:
conflating the person who runs ``pssfmt`` with the person who writes a rule
for it is the usual way a formatter's documentation becomes useless to both.

.. toctree::
   :maxdepth: 2
   :caption: Using pssfmt

   quickstart

.. toctree::
   :maxdepth: 2
   :caption: Developing pssfmt

   architecture
   layout_ir

.. toctree::
   :maxdepth: 2
   :caption: Reference

   reference_api

.. toctree::
   :maxdepth: 1
   :caption: Design history

   design/formatter
   design/plan

What ``pssfmt`` promises
------------------------

The safety contract is the reason a team is willing to put a formatter in a
pre-commit hook, and most formatters never write it down. Stated early, and
in full, once the verifier lands (``D-8``):

* **It does not change your code.** Output re-lexes to the same token
  sequence as the input -- same types, same text -- and comment text is
  preserved character for character.
* **It converges.** Formatting formatted code is a no-op.
* **It fails safe.** If either property is violated for a file, ``pssfmt``
  emits that file *unchanged* along with a diagnostic. A formatter that is
  occasionally a no-op is survivable; one that occasionally corrupts is not.

Not yet enforced, because the pipeline that would enforce it is not built.
:doc:`design/plan` tracks it as ``P1-3``.

Indices
-------

* :ref:`genindex`
* :ref:`modindex`

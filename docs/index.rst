pssfmt
======

A formatter for the Accellera Portable Test and Stimulus Standard.

.. warning::

   **Pre-alpha, and there is no command-line tool yet.** ``pssfmt`` formats
   declarations, their bodies and their headers, ``extend`` blocks, ``import``
   statements, field declarations, expressions, constraints and activities;
   every other construct is reproduced exactly until its rule is written. That
   is by design rather than by accident: a construct with no rule falls back to
   the formatter that changes nothing, so an incomplete rule set cannot corrupt
   anything, and adding a rule cannot make an unrelated construct worse.

   :doc:`status` says what is built, what is not, and in what order the
   rest lands.

Three audiences, three toctrees, and keeping them apart is deliberate:
conflating the person who runs ``pssfmt`` with the person who writes a rule
for it is the usual way a formatter's documentation becomes useless to both.

.. toctree::
   :maxdepth: 2
   :caption: Using pssfmt

   quickstart
   style
   status

.. toctree::
   :maxdepth: 2
   :caption: Developing pssfmt

   architecture
   layout_ir

.. toctree::
   :maxdepth: 2
   :caption: Reference

   reference_api


What ``pssfmt`` promises
------------------------

The safety contract is the reason a team is willing to put a formatter in a
pre-commit hook, and most formatters never write it down. Stated early, and
in full:

* **It does not change your code.** Output re-lexes to the same token
  sequence as the input -- same types, same text -- and comment text is
  preserved character for character.
* **It converges.** Formatting formatted code is a no-op.
* **It fails safe.** If either property is violated for a file, ``pssfmt``
  emits that file *unchanged* along with a diagnostic. A formatter that is
  occasionally a no-op is survivable; one that occasionally corrupts is not.

The first two are enforced today by the verifier, over the whole test
corpus. The third -- emitting the file unchanged rather than emitting
something wrong -- is what makes the other two safe to rely on. See
:doc:`status`.

Indices
-------

* :ref:`genindex`
* :ref:`modindex`

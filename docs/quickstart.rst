Quickstart
==========

.. warning::

   ``pssfmt`` cannot format PSS yet. This page describes the intended
   interface and the state of each piece, so that what is missing is visible
   rather than inferred from a command that does not work.

Getting the repository
----------------------

``pssfmt`` uses ``ivpm``, like every other ``psstools`` repository. A bare
``ivpm update`` resolves the *development* dependency set, which is what the
test suite and the docs build need:

.. code-block:: console

   $ git clone <pssfmt>
   $ cd pssfmt
   $ ivpm update
   $ ./packages/python/bin/python -m pytest

The test suite passes today. Most of it is the layout engine, which is
dependency-free by design and therefore runnable before the PSS front end
exists at all.

Formatting a file
-----------------

.. code-block:: console

   $ pssfmt -i src/pss/my_component.pss     # rewrite in place
   $ pssfmt --check src/pss/                # exit 1 if anything would change
   $ pssfmt --diff src/pss/my_component.pss # show what would change

**Status: not implemented.** Blocked on the token and CST API in
``pssparser`` (``PLAN.md`` ``U-1``--``U-3``), and then on the null round-trip
formatter that proves the pipeline is lossless (``P1``).

In CI
-----

``--check`` exits non-zero when a file would change, which is the whole of
what a CI gate needs:

.. code-block:: yaml

   - name: Check PSS formatting
     run: pssfmt --check $(git ls-files '*.pss')

For adopting the formatter on an existing codebase without a flag-day
reformat, ``--diff-only`` restricts formatting to lines your change already
touched. Introducing that in v1 rather than v2 is deliberate: a formatter
that can only be adopted by reformatting everything at once frequently is not
adopted at all.

**Status: not implemented** (``P4-1``, ``P4-4``).

Turning it off
--------------

.. code-block:: text

   // pssfmt off
   bit[8]   addr;      // hand-aligned, and staying that way
   bit[32]  data;
   // pssfmt on

   // pssfmt ignore
   constraint c { ... }   // this one construct is left alone

Plus a ``.pssfmtignore`` file, gitignore syntax, for whole paths.

Escape hatches are non-negotiable rather than a concession: a formatter
without an off-switch will not be adopted in a codebase with hand-aligned
register tables, and PSS codebases have those.

**Status: not implemented** (``P3-9``, ``P4-3``).

What is actually built
----------------------

The layout engine: the Layout IR, the line-breaking algorithm, and the column
alignment pass. See :doc:`layout_ir`. It is importable and usable on its own:

.. code-block:: python

   from pssfmt.layout import concat, group, indent, render, text, SOFTLINE

   doc = group(concat(
       text("["),
       indent(concat(SOFTLINE, text("a, b, c")), 4),
       SOFTLINE,
       text("]"),
   ))

   render(doc, print_width=80)   # '[a, b, c]'
   render(doc, print_width=5)    # '[\n    a, b, c\n]'

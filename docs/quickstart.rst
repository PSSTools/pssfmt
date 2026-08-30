Quickstart
==========

Install
-------

.. code-block:: console

   $ pip install pssfmt

That brings in ``pssparser``, which ``pssfmt`` calls on every file it reads.
Python 3.9 or newer.

To build the formatter from a checkout instead -- because you are changing it,
not using it -- see :ref:`from-source` at the end of this page.

Format a file
-------------

With no options, ``pssfmt`` writes the formatted file to stdout and leaves the
original alone. Given this:

.. code-block:: pss

   component uart_c{
     bit[32] base_addr;
     function bit[32] reg_offset(string name){
       match(name){
         ["ctrl"]:return 0x00;
         ["status"]:return 0x04;
         default:return -1;
       }
     }


     action write_a{
       rand bit[8]  data;
       constraint data!=0;
       exec body{comp.base_addr=0x1000;}
     }
   }

``pssfmt uart_c.pss`` produces:

.. code-block:: pss

   component uart_c {
       bit[32] base_addr;
       function bit[32] reg_offset(string name) {
           match (name) {
               ["ctrl"]: return 0x00;
               ["status"]: return 0x04;
               default: return -1;
           }
       }

       action write_a {
           rand bit[8] data;
           constraint data != 0;
           exec body {
               comp.base_addr = 0x1000;
           }
       }
   }

Two things in there are worth pointing at, because they are the ones people
ask about. The run of two blank lines was clamped to one, and the ``exec``
body written on a single line was opened out. A body is a body: ``pssfmt``
does not have a rule that keeps a short one flat, because the corpus it was
measured against does not write them flat.

The three modes that matter:

.. code-block:: console

   $ pssfmt -i src/pss/                 # rewrite in place; directories are searched for *.pss
   $ pssfmt --check src/pss/            # write nothing; exit 1 if anything would change
   $ pssfmt --diff src/pss/uart_c.pss   # show what would change, as a unified diff

``-i`` writes through a temporary file and renames it over the original, so an
interrupted run leaves either the old file or the new one and never a
half-written one. See :doc:`cli` for the full flag list and what each exit code
means.

In CI
-----

``--check`` exits non-zero when a file would change, which is the whole of
what a gate needs:

.. code-block:: yaml

   - name: Check PSS formatting
     run: pssfmt --check $(git ls-files '*.pss')

Distinguish the codes rather than testing for non-zero. ``1`` is "a file would
change" and ``2`` is "``pssfmt`` could not do its job" -- an unreadable file, a
broken ``.pssfmt``, or output the verifier rejected. A gate that treats them
alike will eventually report a style failure for a missing dependency.

Adopting it on an existing codebase
-----------------------------------

``--lines`` restricts formatting to the lines a change already touched, so a
formatter can be adopted without a flag-day reformat of the whole tree:

.. code-block:: console

   $ pssfmt -i --lines 40:58 src/my_pkg.pss

The flag is repeatable, and it is deliberately in v1 rather than v2: a
formatter that can only be adopted by reformatting everything at once is
frequently not adopted at all.

Working the ranges out from a ``git diff`` for you is a separate convenience
that is not built; see :doc:`cli`.

Turning it off
--------------

.. code-block:: pss

   // pssfmt off
   bit[8]   addr;      // hand-aligned, and staying that way
   bit[32]  data;
   // pssfmt on

   // pssfmt ignore
   constraint c { ... }   // the next construct is left alone

Plus a ``.pssfmtignore`` file, gitignore syntax, for whole paths.

Escape hatches are not a concession, they are load-bearing: a formatter
without an off-switch is not adopted in a codebase with hand-aligned register
tables, and PSS codebases have those. Note the spelling -- ``// pssfmt off``,
no colon. A directive ``pssfmt`` does not recognise is an ordinary comment and
says nothing, so a typo turns the hatch off rather than failing loudly.

Most hand-built columns survive without a directive at all. ``pssfmt`` keeps a
column you actually reached and flattens a near-miss, which is measured
behaviour rather than a heuristic -- :doc:`style` says how it decides.

Asking why
----------

``--explain`` describes how the output was produced and writes nothing:

.. code-block:: console

   $ pssfmt --explain regs.pss
   regs.pss: 3 output lines, print_width 80, indent_width 4

   Which rule laid out each line
     1            component_declaration
     2            component_data_declaration
     3            component_declaration

   Every break in this file is unconditional: a rule emitted it.
     The engine measured 0 group(s) and broke none.

That is the first thing to reach for when a line went somewhere surprising: it
names the rule responsible, which is also the answer to "is this construct
formatted at all, or reproduced as I wrote it".

Configuring it
--------------

Optional. With no configuration file every file is formatted with the
canonical style described in :doc:`style`.

A ``.pssfmt`` file -- or a ``[tool.pssfmt]`` table in ``pyproject.toml`` --
holds a small set of options, principally ``print_width``, ``indent_width``,
``line_ending`` and the column-alignment mode:

.. code-block:: toml

   [tool.pssfmt]
   print_width = 100
   indent_width = 4

See :doc:`configuration` for the option list, the discovery rules, and the four
keys that are recognised and deliberately **refused** rather than accepted and
silently ignored.

What is not formatted yet
-------------------------

A construct with no rule is reproduced exactly as you wrote it. That is the
design and not a stage of it: the fallback formatter changes nothing, so an
incomplete rule set cannot corrupt a file, and adding a rule cannot make an
unrelated construct worse.

The constructs left alone today include ``if``/``else``, loops, and any
statement you wrapped across lines yourself. :doc:`status` lists them, and says
why each one is waiting on a decision rather than on code.

Underneath all of it is a contract worth knowing before you put this in a
pre-commit hook: output re-lexes to the same tokens as input, formatting
formatted code is a no-op, and a file that fails either check is emitted
**unchanged** with a diagnostic. See :doc:`index`.

.. _from-source:

Building from source
--------------------

``pssfmt`` uses ``ivpm``, like every other ``psstools`` repository. A bare
``ivpm update`` resolves the *development* dependency set, which is what the
test suite and the docs build need:

.. code-block:: console

   $ git clone <pssfmt>
   $ cd pssfmt
   $ ivpm update
   $ ./packages/python/bin/pip install -e . --no-deps
   $ ./packages/python/bin/python -m pytest

``ivpm`` installs the *dependencies* into ``packages/python``; the
``pip install -e .`` line is what puts ``pssfmt`` itself on the path, so that
the ``pssfmt`` command exists and runs your working copy. ``--no-deps``
because ``ivpm`` has already resolved them, from git rather than from PyPI.

The layout engine is usable on its own, and imports nothing -- not ``pssfmt``,
not ``pssparser``:

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

See :doc:`architecture` for the pipeline and :doc:`layout_ir` for the engine.

The command line
================

.. code-block:: text

   pssfmt [-i | --check | --explain] [--diff] [--lines A:B] [-q] [FILE | DIR ...]

With no ``FILE``, or with ``-``, ``pssfmt`` reads standard input and writes
standard output. A directory argument is searched for ``*.pss``; a *named*
file is formatted whatever it is called, on the grounds that someone who types
a path means that file.

.. code-block:: console

   $ pssfmt src/my_pkg.pss          # formatted text to stdout
   $ pssfmt -i src/                 # rewrite every .pss in the tree
   $ pssfmt --check src/            # write nothing; exit 1 if anything would change
   $ pssfmt --diff src/my_pkg.pss   # show what would change
   $ cat f.pss | pssfmt             # stdin to stdout

Options
-------

``-i``, ``--in-place``
    Rewrite each file. Files that are already formatted are **not** touched,
    so their modification times do not change and nothing downstream rebuilds.

``--check``
    Write nothing anywhere; exit ``1`` if any file would change. This is the
    CI gate. It is silent on success.

``--diff``
    Print a unified diff of what would change, in a form ``patch -p0``
    accepts. On its own it exits ``0`` -- it reports rather than judges.
    Combine it with ``--check`` to do both.

``--lines A:B``
    Format only lines ``A`` through ``B`` of one file. Repeatable. See below.

``--explain``
    Write nothing; describe how the output was produced. See below.

``--explain-tree``
    With ``--explain``, also print the Layout IR.

``-q``, ``--quiet``
    Suppress the per-file notes and the summary. Errors are still reported.

``--version``
    Print the version and exit.

``-i``, ``--check`` and ``--explain`` are mutually exclusive: the first writes
files, the second promises not to, and the third is not a formatting run at
all.

Exit codes
----------

These are the actual interface for anything automated, so they are worth
stating precisely.

.. list-table::
   :header-rows: 1
   :widths: 8 92

   * - Code
     - Meaning
   * - ``0``
     - Every input was already formatted, or was formatted successfully.
   * - ``1``
     - ``--check`` only: at least one file would change.
   * - ``2``
     - Something went wrong -- an unreadable or non-UTF-8 file, invalid
       usage, a malformed ``.pssfmt``, or a file ``pssfmt`` declined to
       format.

``1`` means *"the answer is no"* and ``2`` means *"I could not compute the
answer"*, and they are never merged. In CI those call for opposite responses:
one is a pull request that needs formatting, the other is a broken toolchain.
A gate that treats every non-zero code alike will eventually report a style
failure for a missing dependency.

A declined file is an error
---------------------------

If the verifier rejects the formatted output, ``pssfmt`` leaves the file
alone -- see :doc:`status`. That is the right thing to do with the file, and
it means a declined file looks *exactly* like a clean one from the outside:
under ``--check`` there is no diff, and under ``-i`` nothing was written.

So it is reported explicitly, in every mode, and it exits ``2``. A declined
file means ``pssfmt`` produced output that would have changed your program,
which is a bug in ``pssfmt`` that you should hear about immediately rather
than discover as a file that mysteriously never gets formatted.

In stdout mode the input is still written out. ``pssfmt f.pss > new.pss`` is
a normal way to run a formatter, and by the time anything has gone wrong
``new.pss`` is already an empty file waiting to be filled -- so writing
nothing would not decline to modify it, it would empty it.

Editing in place never loses a file
-----------------------------------

``-i`` writes a temporary file alongside the target and renames it over the
original. A crash, a full disk, or a killed process therefore leaves either
the old file or the new one, and never a half-written one. Opening the target
directly for writing would truncate it first, and the window in which your
source code does not exist would be however long the write takes.

The replacement keeps the original file's permissions.

Line endings and the final newline
----------------------------------

``pssfmt`` reads and writes bytes and does not let the platform translate
newlines in either direction. By default a file keeps the line ending it was
written with (``line_ending: auto``), and a file that mixes them is given the
one it uses most -- a formatted file always has exactly one kind.

Every file ends with a newline, and trailing blank lines and trailing
whitespace are removed. See :doc:`style`.

Which style, and which files
----------------------------

Two questions, two files, both optional. A ``.pssfmt`` (or a
``[tool.pssfmt]`` table in ``pyproject.toml``) says *how* to format, and a
``.pssfmtignore`` says *what* to leave alone. Both are found by looking in the
directory of each file and then upward, stopping at the top of your
repository, and both are resolved per file rather than per run.

With neither, every file is formatted with the canonical style described in
:doc:`style`. See :doc:`configuration` for the option list and the discovery
rules.

Two consequences show up out here rather than in that page. A broken
``.pssfmt`` exits ``2`` and the files it governs are skipped, never formatted
with the defaults instead. And ignore patterns filter a *directory search* and
never a file you name -- ``pssfmt -i gen/thing.pss`` formats it, because you
named it.

Formatting part of a file
-------------------------

``--lines A:B`` formats those lines and leaves the rest of the file
byte-for-byte alone. Line numbers are 1-based and inclusive, and they refer to
the file you passed in. Repeat the flag for several ranges; they union.

.. code-block:: console

   $ pssfmt -i --lines 40:58 src/my_pkg.pss
   $ pssfmt --check --lines 12:18 --lines 90:104 src/my_pkg.pss
   $ pssfmt --lines 3:9 < f.pss            # what an editor does for a selection

This is what makes ``pssfmt`` adoptable on a codebase that has never been
formatted: you reformat what you touched, and the review stays about your
change instead of about the whitespace.

It takes **one** file, or stdin. Line numbers do not mean anything across
several inputs, so more than one path -- or a directory -- is an error rather
than a guess.

Two things about ranges are worth knowing before you rely on them.

**Edits are atomic, so you may get slightly more than you asked for.** If the
formatter moved something across line 20 and the text only lines up again at
line 25, then asking for lines 10--20 applies the change through line 25. Half
of a reflowed expression is not a smaller change than all of it.

**Nothing outside a range is touched, ever.** ``--lines`` never rewrites a
line it was not given, and the result is re-verified as a whole before it is
written -- so a range formats less than the whole file, and never something
other than the file.

That second guarantee has a visible consequence when a range cuts through the
middle of a block, and it is better seen than described. Formatting lines
6--11 of this, with ``indent_width = 2``:

.. code-block:: text

   6          action get_a {
   7              Te          data;
   8          }

leaves the closing brace where it was, because line 8 was not in the range:

.. code-block:: text

   6      action get_a {
   7        Te          data;
   8          }

The brace is not a bug and re-running does not indicate one; it is line 8,
which you did not ask for. Give a range that covers the whole construct and
the question does not arise. Cutting each corpus file at arbitrary
thirds -- about as unkind a choice of boundary as there is -- leaves a
mismatched brace in **50 of 92** files, so it is worth knowing about; ranges
that follow the shape of an edit rather than a fraction of a file hit it much
less often.

For the same reason, **line numbers name the file you passed in**, and running
the same numbers twice is not a no-op: the first run moved the text those
numbers pointed at. There is no fixed point to iterate toward here, and a
range that appears to "not take" the first time has usually just been asked
for again against different lines.

``--check --lines`` is the pre-commit shape: a file that is untidy somewhere
you did not touch is not a failure.

Asking why
----------

``--explain`` formats the file, writes nothing, and reports how the result was
produced. It is the answer to "why is this line laid out like that", which is
otherwise a question you can only answer by reading the rule source.

.. code-block:: console

   $ pssfmt --explain src/my_pkg.pss
   src/my_pkg.pss: 131 output lines, print_width 40, indent_width 4

   Which rule laid out each line
     1-5          compilation_unit
     6            package_declaration
     7-14         import_stmt
     15           const_field_declaration
     ...

   Where the engine chose to break (7 of 7 groups)
     line   rule                           reason
     15     const_field_declaration        needs 44 columns and had 36
     ...

   Lines still over print_width (2)
     line   width  laid out by
     3      80     compilation_unit

Three things are worth knowing about how to read it.

**Most breaks are not decisions.** A rule that puts each member of a
declaration on its own line has already decided; there is nothing for the
layout engine to measure. Across the corpus at the default width the engine
makes exactly **one** fit decision in 92 files. So a report that says *"every
break in this file is unconditional"* is not the tool failing to find
something -- it is the answer, and it means the line you are asking about
comes from a rule rather than from ``print_width``.

**A line attributed to a rule was composed; a line attributed to**
``(verbatim)`` **was copied.** The second is the one to notice: it means the
construct has no rule yet and the formatter reproduced your text exactly. See
:doc:`status`.

**Lines over ``print_width`` are named, not blamed.** A line can exceed the
limit legitimately -- an unbreakable token, a ``exec`` body, a comment the
formatter may not reflow -- so that section says what produced the line and
leaves the judgement to you.

``--explain-tree`` adds the Layout IR itself, one node per line, with each
group marked ``broken`` or ``flat``. That is the deep version, and it is
opt-in because it is one line per node.

``--explain`` writes nothing and formats nothing, so it cannot be combined
with ``-i``, ``--check``, ``--diff`` or ``--lines``; those are refused rather
than given a meaning. It still explains a file that **fails verification**,
and reports the violations at the top -- that is the case it exists for.

What is not here yet
--------------------

``--dump-config`` is not implemented. There is no ``--diff-only`` mode that
reads a ``git diff`` and formats just the changed lines; the machinery for it
is ``--lines`` and what is missing is only the part that turns a diff into
ranges.

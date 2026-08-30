Configuration
=============

``pssfmt`` runs with no configuration at all, and that is the intended way to
use it. Everything on this page exists for projects that have already decided
something and need the formatter to agree, not as a set of knobs to explore.

The option set is deliberately small, and small at the *configuration
surface* rather than at the layer underneath it. The rules ask a resolved
style policy per construct, so exposing a new option later is a schema
addition and not a redesign -- which is why the list below can stay short
without painting anything into a corner.

Where the configuration lives
-----------------------------

Either a ``.pssfmt`` file, or a ``[tool.pssfmt]`` table in ``pyproject.toml``.
Both are TOML.

.. code-block:: toml

   # .pssfmt
   print_width = 80
   indent_width = 4
   alignment = "infer"

.. code-block:: toml

   # pyproject.toml
   [tool.pssfmt]
   print_width = 80

``pssfmt`` looks in the directory holding each file it formats, then in that
directory's parent, and so on. Two rules decide where it stops.

**The first configuration found wins, outright.** The chain is not merged. If
a subdirectory has a ``.pssfmt`` that sets only ``indent_width``, every other
option takes its *default* -- not the value from the ``.pssfmt`` further up.
Merging would make "which file set this value?" a question you cannot answer
by reading, which is the question everybody asks first when a shared
configuration misbehaves.

**The search stops at the top of your repository.** A directory containing
``.git``, ``.hg`` or ``.svn`` is the last one searched. Without that bound the
search runs to the root of the filesystem, and a ``.pssfmt`` in a home
directory would silently restyle every checkout on the machine -- a
configuration nobody can see in the tree and nobody can commit.

Within one directory, ``.pssfmt`` is read before ``pyproject.toml``: a file
named after the tool is a more specific statement than a table inside a file
named after something else. A ``pyproject.toml`` with no ``[tool.pssfmt]``
table is not a configuration for this tool and does not stop the search. An
*empty* ``.pssfmt`` does stop it, which is how you say "use the defaults here"
inside a project that configures something else.

Resolution happens per file, not per run. A repository with two projects in it
has two answers, and picking one for the whole invocation would make the
result depend on which directory you happened to type.

The options
-----------

.. list-table::
   :header-rows: 1
   :widths: 26 14 60

   * - Option
     - Default
     - Meaning
   * - ``version``
     - ``1``
     - The semantics this file was written against. See below.
   * - ``print_width``
     - ``80``
     - The column the layout engine tries to stay inside. Measured from the
       corpus, where 80 behaves like a wall rather than a preference.
   * - ``indent_width``
     - ``4``
     - Columns per level of nesting.
   * - ``continuation_indent``
     - ``4``
     - Columns for a line continued from the one above, as distinct from one
       nested inside it.
   * - ``use_tabs``
     - ``false``
     - Indent with tabs. Column *alignment* is always padded with spaces:
       tabs for indentation are a preference, and tabs for alignment are
       broken for anyone whose tab width differs from yours.
   * - ``brace_style``
     - ``"attach"``
     - Where ``{`` goes. Only ``attach`` is implemented -- see below.
   * - ``max_blank_lines``
     - ``1``
     - Consecutive blank lines kept between members. A blank line is the
       author grouping things; more than one is not more grouping.
   * - ``insert_final_newline``
     - ``true``
     - End the file with a newline. Setting this to ``false`` ensures the file
       does *not* end with one, which is EditorConfig's meaning and is worth
       saying out loud because it is the surprising reading.
   * - ``line_ending``
     - ``"auto"``
     - ``auto``, ``lf`` or ``crlf``. ``auto`` keeps whichever the file
       already uses, and a file that mixes them is given the one it uses
       most. Output always has exactly one kind.
   * - ``alignment``
     - ``"infer"``
     - ``align``, ``flush-left``, ``preserve`` or ``infer``. ``infer``
       preserves a table the author built and does not build one they did
       not, which is the only setting that makes formatting a large existing
       codebase a small diff.
   * - ``alignment_group_boundary``
     - ``"blank-lines"``
     - What ends a run of lines that align together: ``none``,
       ``blank-lines``, ``separator-comments``, or
       ``blank-lines-and-separator-comments``. A change of indentation always
       ends a group regardless.

Any option you do not mention keeps its default. An unknown option is an
error, and a near miss is told what you probably meant:

.. code-block:: console

   $ pssfmt --check src/
   pssfmt: /work/.pssfmt: unknown option `indent_widht`; did you mean `indent_width`?

Recognised, and not implemented
-------------------------------

Four keys are understood and **refused** rather than accepted and ignored:
``style``, ``extends``, ``overrides``, and ``brace_style = "break"``.

That distinction matters more than it looks. A recognised option that silently
does nothing is the worst of the three available behaviours: you have written
down an intention, the tool has accepted it, and the output disagrees with
both -- and nothing anywhere says so. An unknown-key error at least reads as a
typo. Refusing is the only response that cannot quietly produce the wrong
file.

``brace_style`` accepts ``"attach"``, because writing down what already
happens is not an error. ``"break"`` -- Allman braces -- is refused.

Pinning the semantics
---------------------

``version = 1`` states which release's defaults the file was written against.
A ``pssfmt`` that does not understand the version refuses the file rather than
reading it under the older meanings, because a later version may change what
the other keys mean and formatting your code under a guess is exactly what the
pin exists to prevent.

Choosing what not to format
---------------------------

A ``.pssfmtignore`` file lists paths a directory search skips. It is
**gitignore syntax** -- not something close to it, which would be worse than
either a different syntax or the same one:

.. code-block:: text

   # generated register maps; regenerate rather than reformat
   gen/**
   *.generated.pss

   # ...except this one, which is hand-maintained
   !gen/hand_written.pss

The last matching pattern decides, which is what makes ``!`` work. A pattern
with no ``/`` matches at any depth; one with a ``/`` is anchored to the
directory of the file it was written in. A trailing ``/`` matches directories
only. ``*`` and ``?`` do not cross a ``/`` and ``**`` does. An excluded
directory is not descended into, so a pattern cannot re-include a file from
inside one.

Unlike ``.pssfmt``, ignore files **stack**: every one from the top of the
repository down to the directory being searched applies, and a nearer file
overrules a further one. A configuration is a set of values, and merging those
hides where they came from; an ignore file is a set of rules, which compose by
construction -- ``!`` exists precisely so an inner file can overrule an outer
one.

Ignore patterns filter a *directory search* and never a file you name:

.. code-block:: console

   $ pssfmt --check src/          # skips what .pssfmtignore excludes
   $ pssfmt -i gen/thing.pss      # formats it; you named it

This is the same call ``pssfmt`` already makes for the ``.pss`` suffix, and
the same one git makes. Someone who types a path means that file, and a silent
no-op is what gets diagnosed as "the formatter is broken".

Both directions lose something, and the one this loses is worth naming: a
pre-commit hook that passes filenames will format files the project excluded.
An opt-in flag for that belongs with the hook itself and is not built yet.

When the configuration is broken
--------------------------------

A malformed or unreadable ``.pssfmt`` exits ``2``, not ``1``. "I cannot read
the style" is a broken toolchain, not an unformatted pull request; see
:doc:`cli` on why those two codes are never merged. The files it governs are
**skipped** rather than formatted with the defaults, because falling back
would rewrite them to a style you did not ask for and were not told about.

The message is printed once per configuration file rather than once per file
it governs. A broken ``.pssfmt`` above a thousand sources is one problem.

Still to come
-------------

``style`` and ``extends`` (named and inheritable base styles), ``overrides``
(per-path options), ``--dump-config`` for the fully resolved effective style,
and an explicit ``--style=file:`` path. ``.editorconfig`` ingestion, overridden
by ``.pssfmt``, is planned -- most teams already have one.

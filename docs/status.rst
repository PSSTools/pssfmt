Project status
==============

.. warning::

   **Pre-alpha, and there is no command-line tool yet.** ``pssfmt`` formats
   declarations and their bodies; everything else in a file is reproduced
   exactly. This page says what is built, what is not, and in what order the
   rest lands -- so that the gap is visible rather than inferred from a
   command that does not work.

Built and tested
----------------

**The layout engine.** The Layout IR, the Wadler-style line-breaking
algorithm, break propagation, greedy ``Fill``, and the column-alignment pass.
It depends on nothing -- not on ``pssfmt``, not on ``pssparser`` -- so it was
built and tested before the PSS front end existed, and it is usable on its own
today. See :doc:`layout_ir` and :doc:`reference_api`.

**Comment attachment.** The rule that decides which construct a comment
belongs to, and the trivia map that provably accounts for every token in the
stream exactly once. Comments are where formatters lose data, so this is
verified as a *partition* rather than by comparing output text: a duplicated
token and a dropped one cancel out in a text comparison and cannot cancel out
in a partition.

**The null formatter and the verifier.** A formatter with no style rules,
which reassembles the file from the token stream. It reproduces all 92 files
of the shared PSS test corpus **byte for byte**, including deliberately
malformed input, and the verifier accepts every one.

**The canonical style.** Decided, written down, and derived from measurements
over that corpus rather than from preference. See :doc:`style`.

**Declaration layout.** Brace placement, member indentation, and the
blank-line policy between members, for ``package``, ``component``, ``action``
and all five ``struct`` kinds. Comments are the hard part of that and are
where the work went: a comment above a member moves with it, a trailing
comment stays on its line, and a comment alone in an otherwise empty body --
the one no member owns -- survives.

**The style policy.** Those measurements now exist as values a rule can ask
for, per construct, rather than as numbers a rule would otherwise write
inline. That matters less for what ``pssfmt`` does today than for what it can
be asked to do later: whether the rules consult a policy at all is settled by
the first rule and never again, so it was settled before the first rule. A
test checks that each default is still the number the corpus produced, so the
page you are reading and the tool's behaviour cannot drift apart quietly.

Not built yet
-------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Piece
     - What is missing
   * - **Style rules**
     - Most of them. Declarations and their bodies are formatted; statements,
       expressions, constraints, activities and coverage are not, and are
       reproduced exactly until they are.
   * - **Command line**
     - ``pssfmt -i``, ``--check``, ``--diff``, ``--lines``. See
       :doc:`quickstart` for the intended interface.
   * - **Configuration**
     - The ``.pssfmt`` file, named base styles, per-glob overrides.
   * - **Escape hatches**
     - ``// pssfmt off`` / ``on``, ``// pssfmt ignore``, ``.pssfmtignore``.
   * - **Editor integration**
     - Format-on-save and format-selection through the PSS language server.

Why the order is what it is
---------------------------

The proof of safety comes before any style decision, and that ordering is the
main structural commitment of the project.

A formatter is adopted on trust: it is put in a pre-commit hook and then not
watched. So the first thing built was not a rule but the evidence that the
pipeline cannot lose a byte -- the null formatter, which formats nothing and
must therefore reproduce its input exactly. Every style rule added after that
is a change to a pipeline already known to be lossless, and every style
decision is reversible. Had the rules come first, each one would have carried
an unbounded question about whether the pipeline underneath it was sound.

The same reasoning shapes how the rules arrive. PSS has 346 grammar rules,
and a formatter that had to handle all of them before it handled any is one
nobody finishes. So a construct with no rule is not a gap to be worked around
-- it is emitted by the null formatter's own machinery, unchanged. The
consequence is worth stating plainly, because it is unusual: **adding a rule
cannot make an unrelated construct worse**, since nothing was relying on that
rule existing. The worst a missing rule does is leave code looking exactly as
it looks today. That claim is checked against every file in the test corpus,
not asserted.

The same reasoning is why the safety contract on the front page is stated as
three checkable properties rather than as an intention.

Known front-end gaps
--------------------

``pssfmt`` reads PSS through ``pssparser``, and pointing a formatter's test
corpus at that parser found defects no parser suite had -- the corpus was
assembled for a syntax highlighter, so it exercises constructs the parser's
own tests never reached.

**Six corpus files contain valid PSS that the parser rejects.** The grammar is
narrower than the language in five specific places -- among them ``action``
declared inside a ``package``, ``dist`` constraints, and ``cover`` statements
inside an ``activity``. These do not threaten correctness here: the null
formatter round-trips all six anyway, because it works from the token stream.
They do block formatting those constructs, since a rule cannot lay out a node
the tree does not contain.

**Lexical errors do not reach the exit status.** A file containing
untokenizable bytes is reported as clean by the parser's command line: the
lexer writes a diagnostic to standard error and the process still exits zero.
Every other malformed file in the corpus exits non-zero, but only because each
also trips a *parse* error that does count -- so the defect was invisible until
a file arrived with no second error to mask the first. This matters to
``pssfmt`` directly, because ``--check`` in a CI job is exactly a caller that
reads an exit status and not standard error.

Both are tracked upstream and neither blocks the work in progress here.

.. note::

   The detailed roadmap, the open design questions, and the reasoning behind
   decisions that were reversed live in the project's working notes, which are
   not published: they are drafting documents, revised continuously, and
   reading them as documentation would mislead. Anything settled enough to
   depend on is written here instead. If something you need is missing from
   these pages, that is a documentation bug worth reporting.

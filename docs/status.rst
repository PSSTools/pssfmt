Project status
==============

.. warning::

   **Pre-alpha, and there is no command-line tool yet.** ``pssfmt`` formats
   declarations, their bodies and headers, ``extend`` blocks, ``import``
   statements, field declarations, expressions, constraints and activities;
   everything else in a file is reproduced exactly. This page says what is
   built, what is not, and in what order the rest lands -- so that the gap is
   visible rather than inferred from a command that does not work.

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

**Spacing, on the constructs whose shape is settled.** Declaration headers
and ``import`` statements are written out token by token, so ``struct
s:base_s`` becomes ``struct s : base_s`` and the gap comes from the style
rather than from the author. Two things are worth knowing about how that is
bounded.

First, each rule declares the tokens it expects, and **a token it does not
recognise is a refusal, not a guess**. There is no global table mapping a
character to a spacing rule, because the same character is not the same rule
everywhere: ``*`` is multiplication in an expression and a wildcard in
``import pkg::*``, and a table that had to choose would space the wildcard.
The effect is that this machinery cannot mis-format a construct it was not
written for -- it can only decline, which leaves your text as you wrote it.
Headers with a template parameter list are declined today for exactly this
reason.

Second, a style can set any gap to zero, and that must never change what a
file *means*. It cannot: a lexical floor sits under every computed gap.
Escaped identifiers are the case that forces it -- ``\name`` runs to the next
whitespace and swallows whatever follows, so ``\name{`` is a single token,
and a zero gap before ``{`` would turn a declaration into an identifier with
nothing else in the file looking wrong.

**Field declarations.** ``rand bit[64] addr;``, ``mem_c::fill_a f;``,
``static const bit[64] BASE = 0x40;`` -- the most common statement in PSS, and
506 of the members inside the bodies described above.

**Expressions.** ``(a + b) * c``, ``f(handle, -1)``, ``(bit[32])xfer.src`` --
1300 of the corpus's 1383, with the rest declined for reasons given below.
Most of them are inside constraints and activities, which have no rule yet,
so what you see change today is mainly field defaults; the machinery is what
those later rules will use.

Two things about expressions are worth stating because they are the parts
most likely to surprise.

First, **parentheses you wrote are kept and parentheses you did not write are
never added**. ``a + b * c`` stays as it is. A formatter built on an abstract
syntax tree does not have that choice -- the tree records only that the
multiplication is the addition's operand, so the parens have to be
reconstructed from a precedence table, and the output is right only if the
table is. ``pssfmt`` reads a concrete tree in which ``(`` is a token, so
there is no table and nothing to get wrong.

Second, the spacing of an operator comes from the **grammar**, not from the
character. ``-`` is subtraction 49 times in the corpus and negation 103
times; a table keyed on the character has one entry and needs two answers,
and the one it picks is wrong the other way round. So ``a - -1`` gets both
gaps right, from one rule, because ``unary_op`` and ``add_sub_op`` are
different rules in the PSS grammar. The same applies to ``(``, which is a
call, a grouping and a cast in the same expression.

What is declined: ``**`` (65 instances, but all one author's, unanimously
tight, against a general rule that says spaced -- one voice cannot decide
it); ``>>`` (spelled as two ``>`` tokens that must touch inside an operator
that must not, which per-token spacing cannot express); aggregates and
template arguments, which belong to rules not yet written.

**Constraints.** ``constraint len in [1..4096];`` and ``constraint c { … }``
-- both shapes of declaration, and 95 of the corpus's 102 constraint body
items: plain expressions, implications ``a -> b``, ``soft`` and ``default``.

A named constraint block is opened out even when it holds a single item,
because that is what 31 of the 32 in the corpus do, 21 of them with exactly
one item. A formatter that collapsed them would be rewriting a deliberate
convention rather than tidying anything.

The seven items left alone are ``if``/``else``, ``foreach``, ``unique``,
``dist``, an implication whose right-hand side is a braced block, and two
expressions already covered above. Each has **one instance in the corpus or
none**, and each needs a decision the corpus has not made -- where ``else``
goes relative to its brace, what the iterator colon in ``foreach (i : list)``
looks like, whether a ``{a, b}`` list brace follows the rule measured on 725
declaration bodies. One example cannot settle any of those.

**Activities.** ``do mem_copy_a;``, ``parallel { … }``, ``repeat (4) { … }``,
``bind fill_copy.blk copy.src;`` -- the traversals an activity is mostly made
of, and the blocks that frame them.

Worth knowing what the shape of this turned out to be, because it is not what
a reading of the PSS grammar suggests. The control-flow keywords -- ``select``,
``schedule``, ``parallel``, ``repeat``, ``sequence`` -- are 22 instances in the
whole corpus between them. The list of actions being traversed is 83. So an
activity is a list of statements with a keyword around it, and both halves are
shapes ``pssfmt`` already had: a block is a declaration body with a different
word in front of it, and a traversal is a scoped name and a semicolon. Not one
new spacing rule was needed for any of it.

Left alone, each for a reason on the same page as the others: inline
constraints (``do step with { … }``), labels (``a: do step;``), guarded and
weighted ``select`` branches, ``if``/``else``, ``foreach``, ``match``,
``replicate``, and the ``monitor`` operators. Every one is a construct the
corpus contains once, or contains only in a single file -- and a single file
is one author's habit rather than a convention.

**Extensions.** ``extend component spi_c { … }``. A body like any other, and
mentioned separately only because of what it was hiding. 31 of the corpus's 92
files open an ``extend``, and since a rule cannot lay out a node whose parent
has none, *everything* inside those 31 files was being reproduced no matter
how many rules had been written for it. That included alignment tables in
eight files that the field rules were quietly flattening -- a defect that
existed, was reachable by any user who did not use ``extend``, and could not
be seen from the test corpus until ``extend`` itself had a rule. It is fixed:
``input``/``output``/``lock`` fields now keep their columns.

**Column alignment.** ``infer``: a block that was already aligned comes back
exactly as written, and one that was not is set flush left. This is what makes
the field rules safe to turn on -- without it they would flatten every
hand-built table in the test corpus, which is a large, entirely plausible
diff that destroys deliberate work.

Two details are worth stating because they are decisions rather than
accidents. ``infer`` *reproduces* an aligned block rather than re-aligning it
to the tightest consistent column: re-aligning keeps a table a table but
regularises the author's chosen columns away, and for a block of equal-width
cells -- a table of constants -- it is indistinguishable from no alignment at
all. And a lone line is reproduced rather than flattened, because one line is
not a ragged block; it is no evidence, and there is nothing to infer from.

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
     - Most of them. Declarations, their bodies and their headers are
       formatted, as are ``extend`` blocks, ``import`` statements, field
       declarations, expressions, constraints and activities; procedural
       statements, ``exec`` bodies, coverage and template parameter lists are
       not, and are reproduced exactly until they are. Expressions *inside*
       those constructs are reproduced with them: a rule cannot lay out a node
       whose parent has no rule.
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

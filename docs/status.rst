Project status
==============

.. note::

   ``pssfmt`` formats declarations, their bodies and headers, ``extend``
   blocks, ``import`` statements, field declarations, expressions,
   constraints, activities, template arguments, ``enum`` declarations,
   function prototypes and bodies, the statements inside them, and ``exec``
   bodies; everything else in a file is reproduced exactly. This page says what
   is built, what is not, and in what order the rest lands -- so that the gap
   is visible rather than discovered as a construct that mysteriously never
   changes.

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
blank-line policy between members, for ``package``, ``component``, ``action``,
all five ``struct`` kinds, and **function bodies**. Comments are the hard part of that and are
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
A header holding a template *parameter list* -- ``struct s <type T> { … }``,
the declaring side -- was declined for exactly this reason until ``S-7``
named its tokens.

Second, a style can set any gap to zero, and that must never change what a
file *means*. It cannot: a lexical floor sits under every computed gap.
Escaped identifiers are the case that forces it -- ``\name`` runs to the next
whitespace and swallows whatever follows, so ``\name{`` is a single token,
and a zero gap before ``{`` would turn a declaration into an identifier with
nothing else in the file looking wrong.

**Function bodies.** ``function bit[32] f(int ch) { … }`` -- 118 of them
across 46 of the 92 corpus files, and until recently the largest construct the
formatter did not reach at all. That mattered for more than the functions: a
rule can only run on a node whose ancestors all have rules, so *everything*
inside every one of those bodies was reproduced verbatim too.

What a function body gets is the block: the brace pulled onto the header line,
the body indented, blank runs clamped, and comments attached to the statement
they belong to.

One consequence is visible on well-kept code and looks like a regression until
you know the rule: a body written on one line is opened out. 117 of the
corpus's 118 functions are already written open, so the odd one out moves.

**Statements inside a body.** ``return -1;``, ``ctrl.en = 1;``, ``x += 2;``,
``regs.ch[n].write(x);``, ``int nwords = nbytes / 4;`` -- and ``match``, which
is a block rather than a statement and is here for a reason worth knowing::

    match (name) {
        ["ctrl"]:   return SPI_CTRL_OFF;
        ["status"]: return SPI_STATUS_OFF;
        default:    return -1;
    }

**195 of the corpus's 201 ``return`` statements are inside one of those.** A
rule can only run on a node whose ancestors all have rules, so formatting the
statements without formatting ``match`` would have reached 9 returns out of
201 while every test passed. That is why the two landed together.

Two hand-built columns are preserved rather than flattened, because the corpus
builds both in several independent files: the ``=`` of a run of assignments
(22 padded of 93, across 8 files) and the statement column after a match arm's
``:`` (13 of 199, four complete tables). As everywhere else, ``pssfmt`` keeps a
column you actually reached and flattens a near-miss -- see :doc:`style`.

What a statement does not get:

* **A branch that is not braced.** ``if (x) y;`` is legal PSS, and laying it
  out needs a decision :doc:`style` has not made -- while adding the braces
  that would settle it is a change to the token stream, which ``pssfmt`` does
  not make. The whole statement is reproduced. Two in the corpus, and both
  hide a ``break`` or a ``continue`` that stays unformatted with them.
* **``repeat { … } while (e);``** puts its block in the **middle** of the
  statement. The block layout can now express that -- it grew a tail for
  ``else`` -- but the tail would have to be a whole statement rather than a
  keyword and a layout, and the corpus contains none of these.
* **A statement you wrapped that has nowhere to break.** One holding a list
  is joined and re-broken; one holding no list, or two, and whose joined form
  is past the width, keeps the line you gave it.

``if``/``else`` and the loops used to head that list and no longer do.
``} else {`` is decided -- cuddled, argued from four guides rather than
measured, since five corpus instances in three files cannot settle it -- and
``foreach (i : list)``, ``repeat (i : 4)``, ``repeat (4)`` and ``while (x)``
are laid out with it. The same two answers unblocked the same two constructs
in constraints and in activities, which is what makes them language rules
rather than three separate calls.

**``exec`` bodies.** ``exec body { … }``, ``exec init_up { … }`` and the rest
-- 28 in the corpus across 18 files, holding 109 statements that were
reproduced verbatim until the statements themselves had rules. An exec body is
a function body with a different header, so everything above applies inside
one.

PSS spells three different things with the same keyword, and only this one is
touched. ``exec body C = """…"""`` and ``exec file "x" = """…"""`` carry
foreign text, and that text comes out **byte for byte** -- indentation
included, and unchanged even if you change ``indent_width``. Re-anchoring a
generated payload changes what it generates.

**Function headers.** ``function  bit[32]   f( int   ch )`` becomes
``function bit[32] f(int ch)``, in all three places PSS writes a prototype:
a definition, a declaration (``function void f(bit[8] x);``) and an import
(``import target C function void poke(bit[32] addr);``). The gaps come from
the same sites a *call* uses, which is a measurement rather than a shortcut --
the survey counts a name followed by ``(`` without caring which it is looking
at, so there is one number here and not two.

One thing a prototype does not get, and it is a refusal rather than a gap:

* **A prototype you wrapped is joined and re-broken**, which is what changed:
  it used to be reproduced, because joining it was all the formatter could do
  and the ones people wrap join to 90-plus columns. The parameter list has a
  break policy now. Three of the corpus's five are hand-aligned parameter
  tables and lose their columns -- the accepted cost, and ``// pssfmt off``
  is what keeps one.

Varargs used to be the second item in that list and is not. ``function void
f(int... args)`` declined because the corpus contains one instance and one
instance cannot decide a spacing rule -- and that is still true, so the rule
is **argued** rather than measured: tight against the type, one space before
the name, from C's ``printf(const char *fmt, ...)``. The number is the same
one a comma would have given; where it comes from is not.

**Enums.** ``enum op_mode_e { FAST, SLOW }`` and::

    enum dma_addr_mode_e : bit[1] {
        DMA_ADDR_FIXED = 0,
        DMA_ADDR_INCR  = 1
    }

The one body in PSS that is written on a single line more often than not, and
what decides between the two forms is **whether the items carry values** --
not how wide the line would be. The corpus is unanimous on that: all four
enums with values are broken and all nine bare-name ones without an interior
comment are on one line, and two of the broken ones would fit inside 80
columns easily. An enum of bare names is a list; an enum of assignments is a
table.

A value column you built by hand is kept, on the same terms as everywhere
else. A comment inside forces the broken form, because a comment cannot go on
one line with the code after it.

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

What is declined: a **map** literal (``{"a": 1}``) and a **struct** literal
(``{.x = 1}``), each needing a decision the corpus contains no instance of.
Value lists (``{1, 2, 3}``) are formatted -- see the list brace in
:doc:`style`.

``**`` and ``>>`` used to be on that list and are not. ``**`` is the one rule
in the tool that depends on the *shape* of its operands rather than on token
adjacency -- ``x**2`` but ``base ** f(n)``, which is Black's rule and is
argued rather than measured, since all 65 corpus instances are one author's
and all are already tight. ``>>`` is spelled as two ``>``
tokens that must touch inside an operator that must not, which one spacing
rule cannot express -- and two can, one per token. The same reading brought in the
ternary ``p ? 1 : 2``, which the corpus does not contain at all and which is
therefore argued from the general binary-operator rule rather than measured.
:doc:`style` states both.

**Target-template ``exec`` bodies are copied, not formatted.** ``exec body C =
"""…"""`` carries C, or SystemVerilog, or whatever the target consumes. Its
interior comes out byte-for-byte: tabs, trailing whitespace, blank runs and
brace style all survive, because they belong to the target language and in
some of them leading whitespace is semantic.

Two consequences worth knowing before you meet them. The style properties
below -- no trailing whitespace, no tab indentation, no brace alone on a line
-- are claims about the gaps ``pssfmt`` *chose*, and they stop at the edge of
a copied region; enforcing them inside one would mean editing somebody else's
program. And a file holding a target template cannot be fully re-indented:
change ``indent_width`` and the ``exec body C = """`` line moves with its
siblings while the interior and the closing ``"""`` stay in the columns you
wrote them in, because those columns are part of the string's value. The
result looks ragged. The alternative is emitting a different program.

**Tabs.** If you indent with tabs, ``pssfmt`` formats what it has rules for
and leaves the rest where you put it. Until recently it did something much
worse: any tab-indented file containing a construct with no rule aborted the
format outright and came back untouched, because the layout engine refused to
measure a tab. That is fixed, and it is worth naming because no corpus file
could have found it -- 0 of the corpus's 4856 lines contain a tab.

**Template arguments.** ``packed_s<bit, 32>``, ``transparent_addr_space_c<>``
-- 137 argument lists across 34 of the 92 corpus files, and until recently the
single largest thing the formatter would not touch: ``<`` accounted for 131 of
its 155 declined spans.

It is worth saying why one bracket took its own pass. Every other bracket in
PSS is punctuation that is only ever a bracket. ``<`` is also the comparison
operator, and the two constructs have *opposite* measured answers -- ``a < b``
is written spaced 128 times out of 130, and ``packed_s<T, 32>`` is written
tight 137 times out of 137. There is no default that is not wrong about half
the language, so which one a given ``<`` is comes from the parse tree rather
than from the character, and an angle bracket the formatter cannot account for
declines the whole header.

The measurement is why the result is quiet: of the 34 files, 33 come out
byte-identical the first time they are formatted rather than copied.

**Constraints.** ``constraint len in [1..4096];`` and ``constraint c { … }``
-- both shapes of declaration, and 95 of the corpus's 102 constraint body
items: plain expressions, implications ``a -> b``, ``soft`` and ``default``.

A named constraint block is opened out even when it holds a single item,
because that is what 31 of the 32 in the corpus do, 21 of them with exactly
one item. A formatter that collapsed them would be rewriting a deliberate
convention rather than tidying anything.

``if``/``else``, ``foreach`` and ``unique`` were three of the seven items
left alone, and are not any more. Each had one instance in the corpus and each
needed a decision the corpus could not make -- where ``else`` goes relative to
its brace, what the iterator colon in ``foreach (i : list)`` looks like,
whether a ``{a, b}`` list brace follows the rule measured on 725 declaration
bodies. All three are answered in :doc:`style`, by argument and labelled as
such, and the same three answers unblocked the same constructs in procedural
code and in activities.

What is still left alone: ``dist`` (blocked upstream -- it does not parse),
an implication whose right-hand side is a braced block, an ``if`` whose branch
is not braced, and two expressions covered above.

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

Labels are laid out too -- ``a : do step;`` -- and that one is worth naming
separately, because nothing was measured for it. Both human voices in the
corpus space a label colon and the code generator does not, so the rule was
published and then deliberately *not applied* for want of standing to
overrule one voice. It is applied now; see :doc:`style`.

Left alone, each for a reason on the same page as the others: inline
constraints (``do step with { … }``), guarded and weighted ``select``
branches, ``if``/``else``, ``foreach``, ``match``, ``replicate``, and the
``monitor`` operators. Every one is a construct the
corpus contains once, or contains only in a single file -- and a single file
is one author's habit rather than a convention.

**Blank lines at the edges of a block are deferred too**, and this one was
decided, built, measured and then put back. The proposal was to strip a blank
line written immediately after ``{`` or immediately before ``}`` -- which
``gofmt``, ``rustfmt`` and ``black`` all do, and which ``clang-format``'s
``MaxEmptyLinesToKeep`` deliberately does not apply at a block boundary. The
corpus disagrees, and it disagrees in the way this project treats as
strongest: **two independent human voices** write a blank line after an
opening brace -- 37 times in the hand-written voice and 4 in the third-party
standard library, across 41 files -- while the code generator writes none.
The other half is uncontested: 5 blank lines before a closing brace, all in
one voice. Implementing it would have reformatted 33 files against that.
``tools/style_survey.py`` reports both counts, so the deferral rests on a
figure that can be re-checked rather than on one recorded once.
So blank lines are clamped to ``max_blank_lines`` wherever they are, including
against a brace, and the rule waits for a reason better than four style
guides.

**Guarded and weighted ``select`` branches are deferred, not pending.** The
distinction is worth drawing, because the rest of that list is work not yet
started and this one is work deliberately not started::

    select {
        (mode == FAST) [3]: do fast_step;
                       [1]: do slow_step;
    }

That is the corpus's only instance, and it carries *four* undecided
questions at once -- the guard's parens, the weight's bracket, the branch
colon, and the hand-aligned colon column those two branches are written in --
and unlike every other construct
here there is no neighbouring rule to borrow from: a weight bracket is a
construct PSS invented, so the measured bracket rules have nothing to say
about it. It waits on a second independent file, on the same terms as
``pool [4]``.

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

A third detail is a decision *not* to build something. ``infer`` judges a run
of lines as a whole rather than judging each column in it separately, and
judging them separately was measured before being written: it changes not one
of the 92 corpus files. The mixed case it would rescue -- a block whose
comments line up and whose ``=`` does not -- occurs three times in 365 runs,
and in all three the two answers agree. Splitting a group into runs of lines
sharing a first column, which landed earlier, had already covered it.

Two details are worth stating because they are decisions rather than
accidents. ``infer`` *reproduces* an aligned block rather than re-aligning it
to the tightest consistent column: re-aligning keeps a table a table but
regularises the author's chosen columns away, and for a block of equal-width
cells -- a table of constants -- it is indistinguishable from no alignment at
all. And a lone line is reproduced rather than flattened, because one line is
not a ragged block; it is no evidence, and there is nothing to infer from.

**Escape hatches.** ``// pssfmt off`` / ``// pssfmt on`` and
``// pssfmt ignore`` all work, and :doc:`style` documents what they promise.
Two things about them are worth knowing here rather than there.

They cost about forty lines, and the reason is that neither half of the
mechanism was written for them. Every braced body in the language -- a
declaration, a constraint, an activity -- collects its members through one
function, so honouring a hatch at member level is one check rather than one
per rule. Below member level nothing was needed at all: a directive inside a
construct is a comment sitting between two tokens, and the token emitter
already declines any span containing one. The hatch is enforced on both sides
of the member boundary by two mechanisms that each exist for their own
reasons.

The other thing is a gap in the evidence, stated because everything else on
this page rests on measurement. **The corpus contains zero directives**, and
always will until ``pssfmt`` has users, so none of this is exercised by the
92 files the way every other rule is. Its tests are the whole of its
coverage, which is why they are byte comparisons over the malformed cases --
unmatched, nested, misspelled, at end of file -- rather than over the
well-formed one.

**Escaped identifiers.** ``int \busa+index ;`` comes back with its space, and
that space is not a style decision. An escaped identifier runs from the
backslash to the **next whitespace character**, so anything written tight
against one is swallowed by it: ``\esc{`` is a single identifier, not a
declaration, and the file it appears in has quietly lost a block. The
separation is therefore a floor beneath the style rather than a value within
it, and no configuration can lower it to zero.

The rule itself was already in place. What the work on it found was that the
floor was only being applied in one of the three places two tokens end up next
to each other -- the main token emitter had it; a declaration header meeting
its ``{``, and a declaration meeting a stray ``;`` recovered from a syntax
error, did not. Both are fixed. Neither could ever have corrupted a file,
because the verifier catches a merged token and hands back the input
unchanged; the symptom was a correct file silently going unformatted. The
generalisation is the part worth keeping: a floor that only one of three
composition sites consults is not a floor, and the way to find the next such
site is to enumerate the places tokens are composed, not to re-read the rule.

**Whole-file golden tests.** Eight files, one per construct group, each an
untidy input and the output it must produce. They exist because every other
test in the suite asserts about the construct it names, and some defects only
exist *between* constructs. The first one found was real: a ``constraint``
block containing a ``default`` item left its own header unformatted, because
of something four lines below it in the body. Every construct involved had
passing tests.

The expected files are generated by the formatter and then read line by line
before being accepted, which is the only thing separating a golden suite from
a transcript of current behaviour. Two oddities visible in them are documented
rather than fixed: a lone declaration keeps the padding its author gave it
(one line is no evidence of a table), and a constraint block mixing ``soft``
with ``default`` items comes out partly aligned, which is an inconsistency
awaiting evidence rather than a decision.

**The command line.** ``pssfmt``, with ``-i``, ``--check`` and ``--diff``,
directory walking, and stdin/stdout. :doc:`cli` documents it. Two things in it
are worth more attention than the flags: the exit codes separate *"the answer
is no"* from *"I could not compute the answer"*, and ``-i`` writes a sibling
file and renames it over the target, so an interrupted run leaves either the
old file or the new one and never a truncated one. It is the only operation in
the project that destroys information.

**The emit boundary.** The tail of a formatted file -- everything after the
last code token -- is *copied* rather than composed, because no construct owns
it. Until it had a pass of its own, every file-level property held for every
line of the output except the last one: a CRLF file came back with LF
everywhere and CRLF on the final line, trailing whitespace survived on the last
line only, and trailing blank lines outlived a blank-line limit that collapsed
them everywhere else. None of it was visible from the corpus, which contains
no CRLF file, no file ending in whitespace and no file ending in a blank line.
``insert_final_newline`` and ``line_ending`` had been options that nothing
read.

Line endings are now normalised on the way in and applied on the way out, so
no rule and no measurement ever sees a ``\r``. That direction matters: a
multi-line ``/* */`` comment is a *single token* whose text spans lines, so
converting line endings by substituting over finished output rewrites token
text -- which the verifier correctly calls corruption. The verifier grants one
narrow exemption for this, and only this: token text is compared with line
endings normalised. A dropped comment, an altered one, a merged token or a
deleted byte all still fail.

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
   * - **Line breaking**
     - Built. A bracketed list that does not fit breaks -- all or nothing by
       default, greedily with ``pack_arguments = "bin_pack"`` -- and wrapped
       prototypes, statements and template parameter declarations are joined
       and re-broken from their content rather than reproduced. Measured on
       the corpus: **lines over ``print_width`` go from 123 to 51**, and
       almost all of the 51 that remain are hand-built trailing-comment
       tables, which nothing can move off their lines.
   * - **Style rules**
     - Fewer than there were. Declarations, their bodies and their headers
       are formatted, as are ``extend`` blocks, ``import`` statements, field
       declarations, ``enum`` declarations, expressions, constraints,
       activities, template arguments, functions -- body, header, parameter
       list and the statements inside -- and native ``exec`` bodies;
       ``if``/``else`` and the loop statements, coverage, ``compile if``,
       annotations and ``monitor`` blocks are not, and are reproduced exactly
       until they are. Of what remains,
       most is either one construct in one corpus file or a rule deliberately
       waiting on evidence -- ``pool [4]`` is the clearest, where the corpus
       and the measured bracket rule disagree and neither has been overruled,
       and **guarded and weighted ``select`` branches** are the other, deferred
       explicitly rather than merely un-started (see below).
       Expressions *inside* those constructs are reproduced with them: a rule
       cannot lay out a node whose parent has no rule. That was a large caveat
       and is now a small one -- it accounted for 13 of the corpus's 137
       template argument lists, then 10 once parameter lists had a rule, and
       none once ``exec`` bodies did. Each time, writing one rule made lists
       elsewhere reachable with nothing written for them.
   * - **Command line**
     - ``--dump-config``, and a ``--diff-only`` mode that formats just the
       lines a ``git diff`` touched -- which is ``--lines`` plus a diff
       parser. ``--lines`` and ``--explain`` are built. See :doc:`cli`.
   * - **Configuration**
     - Named base styles, ``extends``, and per-glob overrides. The ``.pssfmt``
       file itself is built; see :doc:`configuration`.
   * - **Escape hatches**
     - Nothing. ``.pssfmtignore`` and the three in-file directives are built;
       see above and :doc:`configuration`.
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

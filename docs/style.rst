The canonical style
===================

.. note::

   This is the style ``pssfmt`` produces by default. Every rule below is
   followed by the evidence for it, because a style guide that only states
   conclusions cannot be argued with -- and a formatter's default style will
   be argued with.

Where the rules come from
-------------------------

The intent was to derive the canonical style from the PSS 3.1 LRM examples.
That turned out not to be possible: the test corpus contains no LRM text. What it contains is three **independent voices**, and the rules below
are grouped by how strongly those voices decide each question.

.. list-table::
   :header-rows: 1
   :widths: 20 12 68

   * - Voice
     - Lines
     - What it is
   * - ``hand-written``
     - 3020
     - ``example2/`` and ``language-ref/`` -- one organisation's hand-written
       PSS. The largest body, but a *single* voice.
   * - ``third-party``
     - 247
     - ``stdlib/`` -- the PSS core library, from an unrelated project. Small,
       and the only genuinely independent human.
   * - ``generated``
     - 1589
     - ``peakrdl/`` -- machine-emitted register models. A voice, but a
       program's.

``pss31/`` is excluded from the evidence entirely. It was authored *by this
project, for this corpus*, so deriving a style from it would be circular.

Grouping by voice rather than by file count is the point. Agreement across
independent authors is evidence; agreement within one author's files is one
opinion counted many times.

Reproducing the numbers
-----------------------

Every figure on this page comes from:

.. code-block:: console

   $ python tools/style_survey.py

Run it before arguing with a rule. Two of its design constraints were learned
by getting them wrong:

*It reads tokens, never text.* A ``grep`` for bit-slices over this corpus
reports 111 of them. Ninety-eight are inside trailing comments -- ``peakrdl``
documents field ranges as ``// [31:0] sw=rw`` while the code says
``bit[32] f;``. The true count in code is **2**. A regex cannot tell code from
commentary.

*It disambiguates before it counts.* Three PSS constructs are routinely
miscounted: ``*`` is more often ``import pkg::*`` or the ``bind x *;``
wildcard than multiplication; ``<`` and ``>`` are far more often
type-parameter brackets than comparisons, and cannot be told apart by name
shape because PSS generics are lowercase (``reg_c``, ``packed_s``); and ``:``
serves four unrelated constructs with four different conventions. Each of
these produced a wrong answer before it produced a right one.

Layout
------

.. list-table::
   :header-rows: 1
   :widths: 30 18 52

   * - Rule
     - Evidence
     - Notes
   * - **Indent 4 spaces**
     - 251 / 255 steps
     - Every voice. No other step width appears as a mode.
   * - **Never tabs**
     - 0 / 4856 lines
     - Not one indented line in the corpus uses a tab.
   * - **No trailing whitespace**
     - 0 / 4856 lines
     - Also not one.
   * - **K&R braces**
     - 732 / 733
     - ``{`` on the line that opens the construct. Allman does not occur.
   * - **One space before** ``{``
     - 725 / 732
     - ``component c {``
   * - **One space inside a one-line body**
     - 7 / 10
     - ``enum op_mode_e { FAST, SLOW }``. The only body PSS writes on one
       line, and therefore the only place these two gaps exist at all: every
       other ``{`` in the corpus is followed by a line break. The three that
       disagree are both files of the published 3.1 standard library.
   * - **At most one blank line**
     - 667 runs of 1
     - Two consecutive blank lines occur twice in the whole corpus.
   * - ``//`` **over** ``/* */``
     - 1600 vs 35
     - Block comments are preserved, never generated.

Line width: 80
~~~~~~~~~~~~~~

The corpus does not merely average below 80 -- it stops there. Line lengths
for the two human voices::

    76  #####################################  105
    77  ##################################       98
    78  ###################################     100
    79  ###################################     101
    80  ###########################              78
    81  ######                                   19   <-- cliff
    82  #                                         3
    87  |                                         1
    88+ (nothing)

That is not a distribution, it is a wall: authors are wrapping *to* 80.
``print_width`` defaults to **80**.

The optional semicolon: omitted
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

PSS permits a bare ``;`` as a body item, so ``struct s { … };`` is a
declaration followed by an empty one and the semicolon means nothing. It is a
habit from C++ and SystemVerilog, where it is required.

The corpus writes **27 of them, in 4 of 92 files**, against 701 declarations
that do not. Within those four files the habit is consistent, which is what
makes this a *style* rather than an oversight -- so it is an option
(``optional_semicolon``) rather than a rule, with all three answers available
(``omit``, ``preserve``, ``require``), and the default follows the majority
and drops it.

What is dropped is deliberately narrower than what is optional. A semicolon
goes only where the grammar proves the member before it already ended:
``struct``, ``component``, ``package``, ``enum`` and the rest of the
declarations, all 27 of the corpus's instances. It does *not* go after
``x1 with { … };`` or ``constraint c { … };``, where the derivation reaches a
recursive knot it cannot prove -- and where the corpus writes the semicolon
every time. Caution and evidence agree, which is the only reason a
conservative default is worth having.

``require`` is the same measurement read the other way, for the projects in
the minority: it writes the semicolon after every declaration that closes with
a ``}`` and can legally take one -- 627 of them across this corpus. The two
modes are round-trip inverses on every corpus file, which is the property that
would break first if either had the wrong idea about which semicolons are the
optional ones.

``tools/semicolon_survey.py`` derives both admissible sets from the grammar;
``tests/corpus/test_semicolon_grammar.py`` fails if either drifts.

Spacing
-------

Read the "Evidence" column as *votes in favour / instances measured*.
"Unanimous" means every voice with at least four instances agrees.

Tight -- no space
~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Rule
     - Evidence
     - Example
   * - Inside ``(`` ``)``
     - 765 / 767
     - ``foo(a, b)``
   * - Inside ``[`` ``]``
     - 1002 / 1002
     - ``payload[16]``
   * - Around ``::``
     - 392 / 392
     - ``std_pkg::executor_c``
   * - Around ``.``
     - 531 / 532
     - ``regs.tx.write_val()``
   * - Before ``;``
     - 1242 / 1243
     - ``int x = 1;``
   * - Before ``,``
     - 355 / 362
     - ``f(a, b)``
   * - Callee before ``(``
     - 241 / 244
     - ``write32(...)`` -- note the contrast with control keywords below
   * - Inside type brackets
     - 296 / 299
     - ``reg_c<bit[32], READWRITE, 32>``
   * - Unary ``+`` ``-``
     - 92 / 92
     - ``-1``
   * - Range ``..``
     - 18 / 18
     - ``[0..7, 16, 32..63]``

Spaced -- exactly one space
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Rule
     - Evidence
     - Example
   * - Around ``=``
     - 271 / 319
     - ``int x = 1;``
   * - After ``,``
     - 312 / 318
     - ``f(a, b)``
   * - Around ``+`` ``-`` (binary)
     - 94 / 94
     - ``base + offset``
   * - Control keyword before ``(``
     - 118 / 118
     - ``if (x)``, ``foreach (i : list)``
   * - Around comparisons
     - 128 / 130
     - ``a < b``, ``x == y`` -- see below
   * - Around ``&&`` ``||``
     - 14 / 14
     - Thin, but uncontradicted.

.. note::

   ``=`` looks weakest in that table at 271 / 319, and it is not. Its 48
   exceptions are almost entirely *wider* gaps -- 43 sites at widths 2 through
   8 -- which is column alignment, not disagreement about the rule. One space
   is the base rule; ``infer`` alignment is what pads it. The same is true of
   the ten case-item exceptions below. Nothing in the corpus omits the space.

Parens: three constructs, three rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``(`` rule is worth stating explicitly because it is three rules that
look like one. The corpus's 65 expression parens split cleanly between them
-- 40, 12 and 13 -- so this is a partition rather than a corner case.

.. list-table::
   :header-rows: 1
   :widths: 26 24 20 30

   * - Construct
     - Rule
     - Evidence
     - Example
   * - Call
     - tight against the callee, tight inside
     - 241 / 244, 765 / 767
     - ``write32(handle, value)``
   * - Control keyword
     - one space after the keyword
     - 118 / 118, and 3 / 3
     - ``if (x)``, ``repeat (4)``
   * - Grouping and cast
     - tight inside
     - 12 / 12, 13 / 13
     - ``(a + b) * c``, ``(bit[32])addr``

.. code-block:: pss

   if (idx < limit) {
       write32(handle, value);
   }

Grouping and casting share one rule because the corpus gives them one answer,
across 14 files between them and with nothing writing either any other way.
They are still a *separate* rule from the call, and the reason is worth being
plain about: the numbers agreeing today does not make the decisions the same
one. A house style that spaces a call's arguments has said nothing about
whether ``(a + b)`` should become ``( a + b )``, and one setting answering
both questions would be a coincidence hardened into an interface.

**Colons: a fifth construct.** ``docs/style.rst`` names four readings of
``:`` and an ``enum``'s base type is a fifth -- ``enum spi_mode_e : bit[2]``.
It takes the inheritance rule, spaced, because that is what it is: the type
the enum is based on. 4 of 4 in the corpus agree, against a rule measured at
355 of 358.

A **function's parameter list** goes the other way, and for the reason that
argument gives rather than against it: ``function void poke(bit[32] addr)``
takes the call's rule, because the survey cannot tell the two apart. It
counts a name followed by ``(``, and its 241 / 244 already includes all 150
prototypes in the corpus -- three of the four dissenters are prototypes. So
there is one measurement here, and splitting it into two rules would mean
inventing a second default out of the first one's evidence. Other formatters
do separate them (``clang-format`` has a setting for the declaring side
alone); the day this corpus can say something about that split is the day to
add the rule, and it is a change to the survey first.

A note on what is *not* decided here: **parentheses you wrote are kept, and
parentheses you did not write are never added.** ``a + b * c`` does not
become ``a + (b * c)``, however much clearer that might be, and ``(a) + b``
keeps its redundant pair. Both would require ``pssfmt`` to reason about
operator precedence, and a formatter that reasons about precedence is one
that can be wrong about it.

Brackets: four constructs, two rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``[`` looks like the least controversial character in PSS, and three of its
four uses are: they are tight, unanimously, across hundreds of instances. The
fourth is not, and the split is worth knowing about because a declaration can
contain both.

.. list-table::
   :header-rows: 1
   :widths: 28 20 22 30

   * - Construct
     - Rule
     - Evidence
     - Example
   * - Index
     - tight
     - 1002 / 1002
     - ``chans[i]``
   * - Declarator dimension
     - tight
     - 34 / 34
     - ``bit chan[4];``
   * - Type width
     - tight
     - 333 / 333
     - ``bit[64] addr;``
   * - Set / domain
     - one space before
     - 14 / 16
     - ``len in [1..4096]``

.. code-block:: pss

   rand bit[3] in [2..4] mode;

Both brackets on that line come from the *same* grammar production, three
characters apart. Nothing about the token or the node distinguishes them --
only their position relative to ``in`` -- which is why ``pssfmt`` decides it
from the parse tree rather than from the character.

The set bracket is the weakest rule on this page at 14 / 16, and the two
dissenters are worth naming rather than rounding away: they are two files
writing ``in[1..4]`` against eleven writing ``in [1..4]``. Range operators
inside the brackets are tight either way -- ``1..4096``, 18 / 18.

Angle brackets: one character, two opposite rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``<`` is the sharpest case on this page, because its two readings do not
merely differ -- they disagree.

.. list-table::
   :header-rows: 1
   :widths: 28 20 22 30

   * - Construct
     - Rule
     - Evidence
     - Example
   * - Template arguments
     - tight inside
     - 137 / 137
     - ``packed_s<bit, 32>``
   * - Comparison
     - one space each side
     - 128 / 130
     - ``a < b``

Same character, same token type, and no single answer that is not wrong about
half the language. So the rule is decided from the parse tree, exactly as the
``[`` case above is, and a style can move one without moving the other.

The template rule is the most unanimous measurement on this page: every one of
the 137 argument lists in the corpus, across 34 files, writes both ends tight.
The type meets its own argument list tightly too, 135 / 137 -- two instances
in one file write ``foo <T>``. Arguments are separated the way arguments are
separated everywhere, one space after the comma, 122 / 127.

**Template parameter *declarations* are a different construct**, and this page
does not decide them. ``struct base_s <struct TRAIT : addr_trait_s =
empty_addr_trait_s>`` is 16 instances in 5 files, and they do not agree: 7 of
16 are tight after the ``<``, because 5 of the rest put the parameter on a
line of its own. A parameter also carries a ``:`` that is a *bound* rather
than inheritance, which the next section would have to grow a fifth rule for.
``pssfmt`` leaves them exactly as written.

Colons: four constructs, four rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Reported as a single figure, ``:`` looks like a 60/40 disagreement. Separated
by construct, each is internally consistent -- and the split matches the
distinctions the `lowRISC Verilog style guide
<https://github.com/lowRISC/style-guides/blob/master/VerilogCodingStyle.md>`_
draws independently.

.. list-table::
   :header-rows: 1
   :widths: 26 20 22 32

   * - Construct
     - Rule
     - Evidence
     - Example
   * - Bit-slice
     - tight both sides
     - 2 / 2 *(see note)*
     - ``bit[31:0]``
   * - Case / select item
     - none before, one after
     - 214 / 224
     - ``[DMA_MEM_TO_MEM]: {``
   * - Inheritance
     - one space both sides
     - 355 / 358
     - ``struct dma_csr_s : packed_s<> {``
   * - Label, ``foreach``
     - one space both sides
     - 36 human / 84 generated
     - ``begin : foo``, ``repeat (i : n)``

.. note::

   **Two of these are decided by guide rather than by corpus, and it matters
   which.**

   *Bit-slice* has two instances in code across the entire corpus, both in
   files this project authored. That is not evidence. The rule is taken from
   lowRISC, which permits compact notation in bit-vector declarations, and
   from Verible, whose ``--compact_indexing_and_selections`` defaults to true.

   *Label* is the one rule on this page chosen by preference. Both human
   voices space it (36 instances); the code generator does not (84). The
   decision was made in favour of the humans, and lowRISC agrees: *"When
   labeling code blocks, add one space before and after the colon."*

   Because it is a preference rather than a measurement, **it is not
   applied**: an activity label (``a: do step;``) and a ``repeat (i : 4)``
   iterator are reproduced as written. All eight activity labels in the corpus
   are in a single file, and there is exactly one iterator colon -- one voice
   and one instance respectively, which is how much evidence would be needed
   to promote a preference into a rule the formatter acts on. The row stays on
   this page because the *default* is decided; what is missing is the standing
   to use it.

Two questions the corpus argued about
-------------------------------------

Exactly two spacing rules came back split, and both split the same way:
**every human voice on one side, the code generator on the other.**

``*`` ``/`` ``%`` -- spaced, like every other binary operator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: pss

   return DMA_CH_BASE + index * DMA_CH_STRIDE + 0x04;   // chosen
   return DMA_CH_BASE + index*DMA_CH_STRIDE + 0x04;     // rejected

The rejected form is *precedence tightening*: bind higher-precedence
operators more tightly to show grouping. The corpus rejects it and so does
every comparable tool.

**The corpus.** The hand-written voice spaces multiplication 24 times out of
24 -- including all 9 occurrences inside mixed ``+``/``*`` expressions, which
is the exact case precedence tightening exists for. The only voice that
tightens is the generator, 28 out of 28.

**The guides.**

* `lowRISC / Verible
  <https://github.com/lowRISC/style-guides/blob/master/VerilogCodingStyle.md>`_,
  the closest domain peer: *"Include whitespace on both sides of all binary
  operators."* No precedence exception. Its only exception is contextual --
  compact notation inside bit-vector declarations.
* `Black <https://black.readthedocs.io/en/stable/the_black_code_style/current_style.html>`_,
  the closest philosophical peer, since ``pssfmt`` also aims to ship few
  options: spaces all binary operators. `PEP 8 offers precedence tightening
  <https://discuss.python.org/t/pep-8-spaces-around-operators/14860>`_ as
  optional guidance and Black **declined it**, hugging only ``**``, and only
  when both operands are "simple".
* `gofmt <https://github.com/golang/go/issues/3693>`_ is the one mainstream
  implementation -- and an unhappy one. The Go team describes making it look
  good in general as non-trivial and a work in progress, with `open
  inconsistency bugs <https://github.com/golang/go/issues/1206>`_ about the
  same expression formatting differently inside a call than inside a struct
  literal.

**The mechanical argument, which is decisive.** Precedence tightening
requires reasoning about expression-tree shape and nesting depth, so an
identical subexpression formats differently depending on where it sits.
Uniform spacing is a rule about adjacent tokens. For a formatter whose first
promise is that it does not change your code, the simpler invariant wins.

*Accepted consequence:* ``pssfmt`` reformats those 28 generated sites.
Bounded, and it is the generator that is the outlier.

Comparisons -- spaced, and it carries information
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

64 instances in the hand-written voice, all spaced; lowRISC's "all binary
operators" rule covers them; ``==`` and ``!=`` are already spaced 48 out of
48. But the argument specific to PSS is the strong one.

PSS overloads ``<`` and ``>`` for comparison *and* for type parameters. Since
type brackets are tight (296 of 299), spacing comparisons makes the two
visually distinct:

.. code-block:: pss

   if (idx < limit) { ... }                // comparison -- spaced
   reg_c<bit[32], READWRITE, 32>           // type parameters -- tight

Most languages get this separation from their grammar. PSS does not, so here
the spacing rule carries disambiguating information rather than merely taste.

Alignment: ``infer``
--------------------

The default is ``infer`` -- align a block only if its author already aligned
it -- and this is the rule the corpus decides most sharply.

.. list-table::
   :header-rows: 1
   :widths: 34 33 33

   * - Voice
     - Trailing-comment runs
     - ``=`` runs
   * - hand-written
     - **7 aligned, 0 ragged**
     - **14 aligned, 4 ragged**
   * - generated
     - **0 aligned, 15 ragged**
     - 0 aligned, 3 ragged

A run is three or more consecutive lines sharing the construct. The
hand-written ``=`` gaps carry a visible padding tail -- widths of 2 through 8
across 43 sites -- which is deliberate column work, not noise.

So a global ``align`` would column-ise 18 generated blocks nobody asked to be
aligned, and a global ``flush-left`` would destroy 21 hand-built tables.
``infer`` reproduces both exactly. Verible's precedent is what first
suggested this default; the measurements are why it is kept.

**Reproduces, not re-aligns**, and the distinction turned out to be the whole
value of the mode. An obvious reading of "align a block the author aligned"
is to recompute its columns to the tightest consistent position. That keeps a
table a table, but it regularises away the columns the author chose -- and
for a block whose cells are all the same width, which is what a table of
constants usually is, the result is character-for-character what ``flush-left``
would have produced. Measured over the corpus, that reading left 71 of 92
files untouched against ``flush-left``'s 70. Reproducing the block instead
leaves 78. A mode worth one file is not a mode.

A block of **one** marked line is likewise reproduced. ``infer`` infers from a
run; with a single line there is no run and therefore no conclusion, so
collapsing its spacing would be a guess presented as a decision. One line is
not a ragged block -- it is no evidence.

**Where the columns are.** ``infer`` can only keep a column somewhere a rule
said one may exist, so the list is worth stating: a trailing comment, the
declarator and the ``=`` of a declaration, the seams of a flow or resource
reference, the ``=`` of a run of assignments (22 padded of 93, across 8
files), and the statement after a ``match`` arm's ``:`` (13 of 199, four
complete tables). A ``function`` prototype's name column is deliberately
**not** on that list: the corpus pads it once, in one file, against 149 that
do not, and one voice does not make a column.

One consequence is worth knowing before you meet it. ``infer`` asks whether
*every* marked column in a block lines up, so a line that carries a stop it
cannot satisfy loses the columns it could -- two assignments that align their
trailing comments but not their ``=`` come out flush. Judging each column
independently is a change to this mode rather than to a rule, and it has not
been made.

Alignment runs *after* line breaking and can never affect a fit decision, and
it is abandoned for a block that would push past ``print_width``.

Switching it off
----------------

Every rule on this page can be overruled, by you, in the file. Three
directives do it:

.. code-block:: pss

   // pssfmt off
   struct hand_aligned_regs {
       bit[8]  cmd;    bit[16] addr;
       bit[8]  status; bit[16] mask;
   }
   // pssfmt on

   // pssfmt ignore
   struct just_this_one { bit[8]  a;   bit[8]  b; }

Everything between ``off`` and ``on`` comes back **byte for byte** --
including the blank lines inside it, which are otherwise clamped, and
including trailing whitespace and tabs, which are otherwise removed.
``ignore`` does the same for the single construct that follows it, whatever
size that construct is.

This is deliberately not a lint suppression. There is no rule name to
name and no diagnostic to silence: the region is copied, not exempted, so
the tool has no opinion about it at all.

Both comment syntaxes work, since ``/* pssfmt off */`` is the only spelling
available mid-line. A directive takes effect **where it is written**: an
own-line comment applies from the construct below it, and a comment at the
end of a line applies from the next one, so ``} // pssfmt off`` still
formats the thing it is written on.

The match is exact
~~~~~~~~~~~~~~~~~~

``pssfmt off`` is a directive only when it is the *whole* comment.
``// we should turn pssfmt off for this table`` is prose about the tool, and
reading it as an instruction would silently stop formatting the rest of the
file. Prose mentioning a formatter is much more common than directives are,
so the loose match is the one that is wrong on the common case.

The cost is that a near miss -- ``// pssfmt: off``, ``// pssfmt off!`` --
is an ordinary comment, silently. That is the safer side to be wrong on, but
it is still a wrong side, and reporting unrecognised ``pssfmt`` comments is
on the list for when there is a diagnostics channel to report them on.

When the directives do not pair up
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Directives are written by hand, usually in a hurry, so the malformed cases
are the normal cases and each has a decided answer:

``off`` with no ``on``
    Protects to the end of the file. Treating it as unmatched would reformat
    precisely the region someone was trying to protect.
``on`` with no ``off``
    Does nothing. There is nothing to close.
``off`` inside an ``off``
    They do not nest; the first ``on`` closes the region. Counting depth
    would turn one forgotten ``on`` into a file that is silently never
    formatted again -- the same failure as the unmatched case, but invisible
    instead of visible.

One thing is not byte-exact, and it is the region's **first line**. The
enclosing block writes an indent before every member and a copied region
cannot refuse it, so under a changed ``indent_width`` the first line moves
and the rest keep the columns you gave them. That is what keeps the table a
table; the raggedness at the top edge is the price.

Escaped identifiers
-------------------

``\busa+index``, ``\{a,b}``, ``\***error-condition***``: a backslash followed
by everything up to the **next whitespace character**. That last part is the
whole of the rule, and it is unlike anything else in the language, because it
makes a space part of the token rather than part of the gap between tokens.

So ``pssfmt`` always leaves at least one whitespace character on each side of
one, and no setting can reduce it to zero::

    int \busa+index ;          // the space before the ``;`` is not optional
    component \top-level_c {   // nor the one before the ``{``

Written tight, ``\busa+index;`` is a *single identifier* whose name ends in a
semicolon, and ``\top-level_c{`` is a single identifier that has eaten the
brace opening the component body. Both still parse, which is what makes this
worth a section: nothing about the result looks wrong.

Two consequences follow, and the second one usually surprises people:

* **More than one space is fine.** The identifier ends at the *first*
  whitespace character, so column alignment may pad past a single space
  without changing the name.
* **A line break is fine.** A newline is whitespace like any other, so
  ``pssfmt`` may break a long expression next to an escaped identifier just as
  it would anywhere else. There is no rule keeping breaks away from them.

The end of the file
-------------------

Three things about the last line, grouped because they are one decision: the
tail of a file is the part no construct owns, so it is the part where a
formatter is most likely to have no opinion at all.

* **Every file ends with exactly one newline.** A file with none gains one;
  a file with several loses the extras.
* **Trailing whitespace is removed from every line, including the last.**
  Which sounds like it goes without saying, and did not: the last line was the
  one line of the file that no rule rendered.
* **A file keeps the line ending it was written with.** ``\r\n`` if that is
  what it uses, ``\n`` otherwise. A file that mixes them is given whichever it
  uses more, so a formatted file always has exactly one kind.

The first two apply inside a ``pssfmt off`` region as well, and that is the
one place these rules reach past an escape hatch. A hatch suspends decisions
about *your code*; where the file ends is not one of them, and a hatch that
could leave a file without a final newline would make ``--check`` unstable for
everyone downstream.

What ``pssfmt`` will never do
-----------------------------

A style guide that only says what a tool *does* leaves its reader guessing at
the boundary. These are commitments, not defaults, and no option turns them
on.

**It will not reorder anything.** Not imports, not members, not
``constraint`` blocks, not ``enum`` items. Order in PSS can carry meaning --
declaration order interacts with inheritance and with ``extend`` -- and a
formatter that sorts is a formatter that changes behaviour. It is also the
single most common reason a team disables a formatter after adopting it.

**It will not reflow comment text.** Comments are moved as blocks and
re-indented, but their interiors are preserved character for character. A
comment can contain a table, an ASCII diagram, a licence header, or a URL
that must not be broken. ``pssfmt`` cannot tell those from prose, so it does
not try.

**It will not touch ``exec`` target-template interiors.** The body of a target
template is foreign text -- C, SystemVerilog, whatever the target consumes --
and PSS is merely carrying it. It is emitted byte for byte, exempt from width
accounting, and it forces its enclosing group to break.

That commitment outranks every rule on this page, and it is worth being
explicit about what that costs, because the two collide in practice.

*The unanimous properties stop at the edge of a copied region.* No trailing
whitespace, no tab indentation, no brace alone on a line: each was measured
over PSS that people wrote and each is a claim about a gap ``pssfmt`` chose.
A target template's interior has no such gaps -- every character came out of
one token -- so a tab or a trailing space inside one is not a violation, and
removing it would be editing a program in another language. The same holds
inside a ``pssfmt off`` region, for the same reason arrived at from the other
direction: there the gaps are ones ``pssfmt`` was told not to choose.

*A file holding a target template cannot be fully re-indented.* Change
``indent_width`` and the ``exec body C = """`` line moves with its siblings
while the interior and the closing ``"""`` do not, because those columns are
inside the string and are part of its value. The output is ragged and stable.
Making it tidy would mean changing what the tool generates.

**It will not change the tokens.** Output re-lexes to the same token
sequence as the input: same types, same text. If it would not, ``pssfmt``
emits the file unchanged with a diagnostic instead. That is the fail-safe,
and it is why the three commitments above are checkable rather than merely
promised.

What this page does not decide
------------------------------

Stated so that silence is not mistaken for consensus. The corpus has too few
instances to decide these, and they are settled by the general rules above
rather than by evidence:

* Bitwise ``&`` ``|`` ``^`` and shifts ``<<`` ``>>`` -- 14 instances total.
  Treated as binary operators, hence spaced.

  Implication ``->`` used to be in this bullet and has been measured out of
  it: on its own it is **6 / 6 spaced across 5 independent files**, which
  agrees with the general rule it was being defaulted to. Stated separately
  because "we defaulted it" and "we measured it" are different claims.

  ``>>`` is a special case, and not for a reason about style: PSS has no
  ``>>`` token, and the shift operator is two ``>`` that must be written
  touching while the operator as a whole is spaced. That is not something a
  per-token rule can express, so ``pssfmt`` leaves a right shift exactly as
  you wrote it. One instance in the corpus.
* Exponentiation ``**`` -- 65 instances, but all from a **single author**,
  who writes ``a**2`` without spaces. Agreement within one voice is one
  opinion counted 65 times, so it decides nothing; and the binary-operator
  rule above would overrule the only evidence there is. ``pssfmt`` therefore
  formats neither way and leaves ``**`` expressions alone.
* The ternary ``? :`` -- not present.
* Line-breaking policy for long constraint and activity bodies. That is
  the style-rule layer's work, and the layout engine derives it from
  ``print_width`` rather than from a style constant.

.. seealso::

   :doc:`status` -- what is built, and what still stands between this page
   and a formatter that applies it.

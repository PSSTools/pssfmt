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

Alignment runs *after* line breaking and can never affect a fit decision, and
it is abandoned for a block that would push past ``print_width``.

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

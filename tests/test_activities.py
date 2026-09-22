"""``T-25`` -- activities and ``extend`` (``P3-6``).

``PLAN.md`` calls activities "the visual centerpiece of a PSS file" and budgets
the largest rule module in the project for them. The corpus says the
centerpiece is the list of actions an activity traverses -- 83 instances, none
written across more than one line -- and that the control-flow keywords the
plan named are the rarest things in the file, 22 instances between all five.
So what is tested here is two shapes: a one-line statement and a block.

The other half of this file is ``extend``, which is not in ``PLAN.md`` at all
and turned out to gate most of ``P3-6``. 31 of the corpus's 92 files open one,
and a rule cannot lay out a node whose parent has none -- so before it was
registered, *zero* of the corpus's ten activity binds were reachable and eight
files' worth of hand-built alignment tables were being flattened where nobody
could see it. The tests that pin that are at the bottom.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.rules import format_source  # noqa: E402
from pssfmt.style import Site, Spacing, Style  # noqa: E402
from pssfmt.verify import verify  # noqa: E402

pytestmark = pytest.mark.unit


def fmt(src: str, style: Style = None) -> str:
    return format_source(src, style=style) if style else format_source(src)


def in_activity(*body: str) -> str:
    """*body* inside ``component c { action a { activity { … } } }``."""
    return ("component c {\n    action a {\n        activity {\n"
            + "".join("            %s\n" % b for b in body)
            + "        }\n    }\n}\n")


# ---------------------------------------------------------------------------
# The shape the corpus actually has
# ---------------------------------------------------------------------------


class TestTraversalsAreTheCommonCase:
    """83 of the corpus's ~120 activity nodes, in 13 files, none multi-line."""

    def test_a_bare_traversal(self):
        assert fmt(in_activity("fill ;")) == in_activity("fill;")

    def test_a_do_traversal(self):
        """``do`` is word-class: 34 of 34 corpus instances write one space."""
        assert fmt(in_activity("do   mem_copy_a ;")) == \
            in_activity("do mem_copy_a;")

    def test_a_scoped_type_is_tight(self):
        """``::`` is ``Site.SCOPE_RESOLUTION``, 6 of 6 tight in three files."""
        assert fmt(in_activity("do mem_c :: fill_a ;")) == \
            in_activity("do mem_c::fill_a;")

    def test_an_indexed_traversal_uses_the_index_bracket(self):
        assert fmt(in_activity("s_arr [ 2 ] ;")) == in_activity("s_arr[2];")

    def test_an_index_expression_gets_its_sites_from_the_tree(self):
        """The one place a traversal's spacing is not decided by its tokens.

        Everything else in a traversal -- names, ``::``, ``.``, ``;`` -- means
        one thing wherever it appears, so the vocabulary alone would do. An
        index holds an *expression*, and there ``+`` is additive or unary and
        only the tree knows which. Without the tree sites this comes back
        ``s_arr[i+1]``, which is the placeholder spacing an ambiguous token
        carries in the vocabulary rather than a measurement.
        """
        assert fmt(in_activity("s_arr[ i+1 ];")) == in_activity("s_arr[i + 1];")


class TestABlockIsADeclarationBodyWithADifferentKeyword:
    """29 of 29 activity blocks write exactly one space before ``{``.

    That is ``Site.BRACE_OPEN``, measured on 725 *declaration* bodies -- so
    these blocks needed no new spacing decision, only a vocabulary that admits
    their keyword.
    """

    @pytest.mark.parametrize("keyword", ["parallel", "schedule", "select"])
    def test_the_keyword_blocks(self, keyword):
        src = in_activity("%s{ a ; b ; }" % keyword)
        assert fmt(src) == in_activity(
            "%s {" % keyword, "    a;", "    b;", "}")

    def test_a_named_sequence_block(self):
        src = in_activity("sequence   { s1 ; s2 ; }")
        assert fmt(src) == in_activity("sequence {", "    s1;", "    s2;", "}")

    def test_repeat_takes_a_control_paren(self):
        """``Site.CONTROL_PAREN_*``, carried since ``P3-2`` with no user.

        Measured at 118/118 on other constructs; the three corpus ``repeat``
        headers agree with it, which is the point of having measured it before
        the first caller arrived rather than when one did.
        """
        src = in_activity("repeat( 4 ){ do step ; }")
        assert fmt(src) == in_activity("repeat (4) {", "    do step;", "}")

    def test_a_block_nests(self):
        src = in_activity("parallel { schedule { a ; b ; } c ; }")
        assert fmt(src) == in_activity(
            "parallel {", "    schedule {", "        a;", "        b;",
            "    }", "    c;", "}")


class TestBindsKeepTheirColumn:
    """Six of the corpus's ten binds are padded to a column, in two files.

    The seam is the start of ``activity_bind_item_or_list`` -- a node
    boundary, so it is taken from the tree rather than inferred from tokens,
    for the same reason ``stmts._column_stops`` takes the type/declarator seam
    from the tree.
    """

    def test_an_aligned_bind_block_survives(self):
        src = in_activity(
            "bind fill_copy.blk  copy.src;",
            "bind copy.dst       chk.blk;")
        assert fmt(src) == src

    def test_a_ragged_bind_block_is_flushed(self):
        """``infer``: the block was not a table, so it is not made into one."""
        src = in_activity(
            "bind fill_copy.blk   copy.src;",
            "bind copy.dst  chk.blk;")
        assert fmt(src) == in_activity(
            "bind fill_copy.blk copy.src;", "bind copy.dst chk.blk;")

    def test_a_bind_normalises_its_punctuation(self):
        assert fmt(in_activity("bind  x . b y . c ;")) == \
            in_activity("bind x.b y.c;")

    def test_a_lone_padded_bind_keeps_its_padding(self):
        """One line is no evidence, so there is nothing to infer from.

        ``infer`` reproduces a single marked line rather than flattening it,
        which is the documented behaviour and reads as a surprise every time:
        the padding here is *not* normalised, because one line is not a
        ragged block and the formatter has no basis for calling it one.
        """
        src = in_activity("bind x.b   y.c;")
        assert fmt(src) == src


# ---------------------------------------------------------------------------
# What declines, and that it declines through the vocabulary
# ---------------------------------------------------------------------------


class TestItDeclinesRatherThanGuesses:
    """Each of these is reproduced exactly, and each for a stated reason.

    The property under test is not "the output is pretty" but that the input
    comes back **byte for byte**: a construct this module has no measurement
    for is left alone rather than formatted by whichever rule was nearest.
    """

    def test_an_inline_constraint_declines(self):
        """``TOK_WITH``/``TOK_LCBRACE`` are absent from the vocabulary.

        Four corpus instances in two files, all on one line -- but the only
        comparable measured construct is the named constraint block, which 31
        of 32 corpus instances open out. Formatting these means contradicting
        that or inventing an exception, on four instances.
        """
        src = in_activity("do step with { id == ri; };")
        assert fmt(src) == src

    def test_an_anonymous_block_is_laid_out(self):
        """``T-46`` -- ``S-3``. The one documented exception to attached braces.

        This construct used to decline, and the reasoning was sound as far as
        it went: ``docs/style.rst`` measures braces as *attached*, no corpus
        file puts one alone, and a headerless block emits a line containing
        only ``{``.

        What ``S-3`` decided is that the brace rule is about a brace and *its
        header*. An anonymous sequence block has none, so there is nothing for
        its brace to have moved off -- it is not an Allman brace, it is a
        construct the rule does not describe. Declining it also cost the
        traversals inside, which is the half that made it worth deciding.
        """
        out = fmt(in_activity("parallel {", "    { copy; chk; }",
                              "    other;", "}"))
        assert out == in_activity(
            "parallel {",
            "    {",
            "        copy;",
            "        chk;",
            "    }",
            "    other;",
            "}")

    def test_the_keyword_spelling_is_unaffected(self):
        """``sequence { … }`` was always laid out and still is."""
        out = fmt(in_activity("sequence { copy; chk; }"))
        assert out == in_activity("sequence {", "    copy;", "    chk;", "}")

    def test_an_anonymous_block_nests(self):
        out = fmt(in_activity("parallel {", "    { { copy; } }", "}"))
        assert "                    {\n" in out

    def test_an_anonymous_block_is_idempotent(self):
        once = fmt(in_activity("parallel {", "    { copy; chk; }", "}"))
        assert fmt(once) == once

    def test_the_declining_construct_does_not_take_its_neighbours_with_it(self):
        """A decline is node-scoped: the statements around it still format."""
        src = in_activity("do step with { id == ri; };", "do   other ;")
        assert fmt(src) == in_activity("do step with { id == ri; };",
                                       "do other;")


class TestTheIteratorColon:
    """``T-48`` -- ``S-5``. ``repeat (i : 4)``, spaced.

    Nothing here is measured. The corpus's one ``foreach`` is the *colon-less*
    ``foreach (chans[i])`` spelling, so the number of iterator colons it
    contains is **zero** and this is argued outright: C++'s range-``for``
    writes ``for (auto x : xs)``, the inheritance colon beside it is 355/358
    spaced, and lowRISC asks for a space either side of a colon that labels
    rather than delimits.

    What the item bought is the header. ``TOK_COLON`` was absent from the
    block header vocabulary, so a ``repeat`` with an iterator had its header
    reproduced while its body still opened out.
    """

    @pytest.mark.parametrize("header", [
        "repeat (ri : 4) {", "repeat (ri:4) {", "repeat ( ri  :  4 ) {",
    ], ids=["canonical", "tight", "wide"])
    def test_every_spelling_lands_on_the_canonical_one(self, header: str):
        out = fmt(in_activity(header, "    do step;", "}"))
        assert "repeat (ri : 4) {" in out

    def test_the_body_is_laid_out_too(self):
        """The half that was already working, pinned so it stays working."""
        out = fmt(in_activity("repeat (ri : 4) { do   step ; }"))
        assert "                do step;" in out

    def test_a_repeat_without_an_iterator_still_works(self):
        """``repeat (4)`` -- three corpus instances, and the colon is
        optional in all three grammar spellings that carry one."""
        out = fmt(in_activity("repeat (4) { do step; }"))
        assert "repeat (4) {" in out

    def test_the_gap_comes_from_the_style(self):
        out = fmt(in_activity("repeat (ri : 4) { do step; }"),
                  Style(spacing_overrides={Site.COLON_ITERATOR: Spacing(0, 0)}))
        assert "repeat (ri:4) {" in out

    def test_it_is_idempotent(self):
        once = fmt(in_activity("repeat (ri:4) { do step; }"))
        assert fmt(once) == once


class TestTheLabelColon:
    """``T-49`` -- ``S-6``. ``a : do step;``.

    **This decided nothing; it granted standing.** ``Site.COLON_LABEL`` has
    been spaced since ``P3-0`` and ``docs/style.rst`` published it, credited
    lowRISC, and then explained that the formatter had no standing to apply
    it: both human voices space it in 36 instances and the code generator
    does not in 84, which is a preference rather than a measurement. All
    eight activity labels in the corpus are in one file.

    So the whole visible effect of this item is that one voice being
    overruled, and the tests are crafted rather than corpus-driven.
    """

    @pytest.mark.parametrize("src", ["a: do step;", "a : do step;",
                                     "a:do step;", "a  :  do step;"],
                             ids=["c-style", "canonical", "tight", "wide"])
    def test_every_spelling_lands_on_the_canonical_one(self, src: str):
        assert fmt(in_activity(src)) == in_activity("a : do step;")

    def test_a_label_on_a_block_keeps_the_block(self):
        out = fmt(in_activity("b:parallel { do x; }"))
        assert "            b : parallel {\n" in out
        assert "                do x;\n" in out

    def test_an_unlabelled_statement_is_untouched(self):
        assert fmt(in_activity("do  step ;")) == in_activity("do step;")

    def test_the_gap_comes_from_the_style(self):
        assert fmt(in_activity("a : do step;"),
                   Style(spacing_overrides={Site.COLON_LABEL: Spacing(0, 0)})) \
            == in_activity("a:do step;")

    def test_the_match_arm_colon_is_a_different_site(self):
        """The split is real and this is the test that proves it.

        ``Site.COLON_CASE_ITEM`` is measured at 214/224 -- none before, one
        after -- and moving the *label* colon must not move it. Two colons,
        two sites, and the values differ, so a single shared site would show
        up here as either arm losing its rule.
        """
        style = Style(spacing_overrides={Site.COLON_LABEL: Spacing(3, 3)})
        src = ("component c {\n"
               "    function int f(string n) {\n"
               "        match (n) {\n"
               '            ["a"]: return 1;\n'
               "            default: return 0;\n"
               "        }\n"
               "    }\n"
               "}\n")
        assert '["a"]: return 1;' in fmt(src, style)

    def test_it_is_idempotent(self):
        once = fmt(in_activity("a:do step;"))
        assert fmt(once) == once

    def test_no_token_is_lost(self):
        src = in_activity("a:do step;")
        assert list(verify(src, fmt(src))) == []


class TestNoTokenIsEverLost:
    """The safety contract, on this module's constructs.

    Checked as re-lexing to the same token sequence rather than by comparing
    text, because that is the property ``pssfmt`` promises and the only one a
    reader can rely on.
    """

    @pytest.mark.parametrize("body", [
        "fill;",
        "do mem_c::fill_a;",
        "bind a.b  c.d;",
        "parallel { x; y; }",
        "repeat (4) { do step; }",
        "select { do a; do b; }",
        "schedule { a; b; }",
        "sequence { a; b; }",
        "do step with { id == ri; };",
        "a: do step;",
        "{ copy; chk; }",
    ])
    def test_it_round_trips(self, body):
        src = in_activity(body)
        violations = list(verify(src, fmt(src)))
        assert not violations, violations


class TestTheGapsComeFromTheStyle:
    """Not from the author, and not from a number written inside a rule.

    Setting a site to a different width must move the output, which is what
    says the rule consulted the policy rather than hard-coding what the policy
    happens to say.
    """

    def test_the_brace_gap_is_the_styles(self):
        style = Style(spacing_overrides={Site.BRACE_OPEN: Spacing(3, 0)})
        assert "parallel   {" in fmt(in_activity("parallel { a; }"), style)

    def test_the_control_paren_gap_is_the_styles(self):
        style = Style(spacing_overrides={
            Site.CONTROL_PAREN_OPEN: Spacing(0, 1)})
        assert "repeat( 4) {" in fmt(in_activity("repeat (4) { a; }"), style)

    def test_the_semicolon_gap_is_the_styles(self):
        style = Style(spacing_overrides={Site.SEMICOLON: Spacing(2, 0)})
        assert "do step  ;" in fmt(in_activity("do step;"), style)


# ---------------------------------------------------------------------------
# extend -- the rule that was missing, and what it was hiding
# ---------------------------------------------------------------------------


class TestExtendIsABodyLikeAnyOther:
    """32 instances across 31 files, in five shapes, all the same one."""

    def test_a_component_extension(self):
        src = "extend  component   pss_top{\n int x ;\n}\n"
        assert fmt(src) == "extend component pss_top {\n    int x;\n}\n"

    def test_a_scoped_action_extension(self):
        """``::`` in a declaration header, which ``P3-2b``'s set lacked."""
        src = "extend action dma_c :: xfer {\n int y ;\n}\n"
        assert fmt(src) == "extend action dma_c::xfer {\n    int y;\n}\n"

    def test_the_scope_operator_is_not_split(self):
        """``a : :b`` would re-lex differently -- ``P3-4``'s munch check.

        Worth a test rather than an argument: ``TOK_COLON`` and
        ``TOK_DOUBLE_COLON`` now live in one vocabulary, and a style that set
        both gaps to zero is the case where a lexical floor is all that stands
        between ``dma_c::xfer`` and a different program.
        """
        style = Style(spacing_overrides={
            Site.SCOPE_RESOLUTION: Spacing(0, 0),
            Site.COLON_INHERITANCE: Spacing(0, 0)})
        src = "extend action dma_c::xfer {\n int y ;\n}\n"
        violations = list(verify(src, fmt(src, style)))
        assert not violations, violations


class TestExtendMadeTheAlignmentGapVisible:
    """``input``/``output``/``lock`` fields had no column stops at all.

    They use ``flow_object_type``/``resource_object_type``/``object_ref_field``
    rather than the ``data_instantiation`` ``_column_stops`` looked for, so
    through ``P3-5`` any column an author built in one was collapsed. It went
    unnoticed because the files that do it put their actions inside an
    ``extend``, which had no rule -- the damage existed and was unreachable.

    Two tests, and both are needed: the first fails if the seams are dropped,
    the second fails if only some of them are, which is the state that
    actually shipped.
    """

    def test_an_aligned_flow_field_block_survives(self):
        src = ("extend component c {\n"
               "    action a {\n"
               "        input  mem_blk_s   src;\n"
               "        output spi_data_s  data;\n"
               "    }\n}\n")
        assert fmt(src) == src

    def test_a_lock_field_does_not_collapse_its_neighbours(self):
        """``lock`` is a third production, and omitting it broke the block.

        A ``lock`` line contributes one stop where its ``input`` neighbours
        contribute two, so the group's shared column count drops to one and
        every line is then measured on a cell that has already been collapsed.
        The failure is not confined to the ``lock`` line, which is why it is
        pinned separately.
        """
        src = ("extend component c {\n"
               "    action a {\n"
               "        input  mem_blk_s     src;\n"
               "        output mem_blk_s     dst;\n"
               "        lock   dma_chan_s    ch;\n"
               "    }\n}\n")
        assert fmt(src) == src

    def test_a_flow_field_with_no_assignment_is_not_offered_a_break(self):
        """``_break_after_assign`` used to mean "the second column stop".

        That held only while every statement with two stops had an ``=`` as
        the second one. A flow reference has two stops and no ``=``, so the
        old form would have offered a break after its declarator.
        """
        src = ("extend component c {\n    action a {\n"
               "        output spi_data_s data;\n    }\n}\n")
        assert fmt(src) == src


class TestConstraintColumnsSurviveToo:
    """The other table ``extend`` had been hiding.

    Thin evidence, and recorded as such: two padded instances in one file
    against 72 written tight in 17. What makes marking the column safe rather
    than a new rule is that a stop is not a decision to pad -- ``infer`` reads
    each block's own spacing, so the 72 tight items flush left and land back
    on the single space they already had.
    """

    def test_an_aligned_constraint_block_survives(self):
        src = ("component c {\n    action a {\n        constraint copy_c {\n"
               "            dst.mem.size == src.mem.size;\n"
               "            dst.pattern  == src.pattern;\n"
               "            dst.seed     == src.seed;\n"
               "        }\n    }\n}\n")
        assert fmt(src) == src

    def test_a_tight_constraint_block_is_unchanged(self):
        src = ("component c {\n    action a {\n        constraint copy_c {\n"
               "            a == b;\n            c == d;\n"
               "        }\n    }\n}\n")
        assert fmt(src) == src

    def test_a_nested_expression_offers_no_column(self):
        """Two operators, so "before the operator" would be a choice.

        The stop is offered only for a single binary operation. This block is
        padded to a column before its ``&&`` and is deliberately **not**
        preserved: with two operators there is no way to say which one the
        column belongs to without deciding it, and the corpus has not. So the
        padding is collapsed rather than guessed at.

        Written so that guessing would be visible -- aligning on the *first*
        operator reproduces this block exactly, which is what makes the
        restriction testable rather than merely stated.
        """
        src = ("component c {\n    action a {\n        constraint k {\n"
               "            aa && b == c;\n            b  && c == d;\n"
               "        }\n    }\n}\n")
        assert fmt(src) == (
            "component c {\n    action a {\n        constraint k {\n"
            "            aa && b == c;\n            b && c == d;\n"
            "        }\n    }\n}\n")

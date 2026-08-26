"""``T-2`` -- the layout engine, tested against hand-built IR only.

No PSS and no pssparser appear anywhere in this file, by design. This suite is
what lets Phase 2 be built and trusted while the upstream token API is still
unwritten (``PLAN.md`` section 3, ``formatter.md`` section 10.3).
"""

from __future__ import annotations

import pytest

from pssfmt.layout import (
    BREAK_PARENT,
    EMPTY,
    HARDLINE,
    LINE,
    SOFTLINE,
    Fill,
    Group,
    HardLine,
    IfBreak,
    Indent,
    Text,
    Verbatim,
    align_to,
    concat,
    fill_with,
    group,
    indent,
    join,
    propagate_breaks,
    render,
    text,
)

pytestmark = [pytest.mark.layout, pytest.mark.unit]


def brackets(inner, sep=SOFTLINE, open_="[", close="]", width=4):
    """``[ inner ]`` -- the canonical break-together shape."""
    return group(
        concat(
            text(open_),
            indent(concat(sep, inner), width),
            sep,
            text(close),
        )
    )


# --------------------------------------------------------------------------
# fits boundaries
# --------------------------------------------------------------------------


class TestFitsBoundary:
    """``print_width`` is inclusive: a line of exactly N columns fits in N."""

    def make(self):
        # Flat form is "[xxxxxxxx]" -- exactly 10 columns.
        return brackets(text("x" * 8))

    def test_exactly_at_width_stays_flat(self):
        assert render(self.make(), print_width=10) == "[xxxxxxxx]"

    def test_one_under_width_stays_flat(self):
        assert render(self.make(), print_width=11) == "[xxxxxxxx]"

    def test_one_over_width_breaks(self):
        assert render(self.make(), print_width=9) == "[\n    xxxxxxxx\n]"

    def test_zero_width_still_terminates(self):
        # A degenerate width must not loop or raise; it just breaks everything.
        assert render(self.make(), print_width=0) == "[\n    xxxxxxxx\n]"


def test_fits_accounts_for_what_follows_on_the_same_line():
    """The trailing ``;`` is part of this line and must be measured with it.

    A group measured in isolation is the classic overflow bug: the group fits
    in the remaining columns, the text that must follow it does not, and the
    line ends up over the limit by exactly that text's width.
    """
    doc = concat(brackets(text("x" * 8)), text(";;;"))
    # Flat is "[xxxxxxxx];;;" = 13 columns.
    assert render(doc, print_width=13) == "[xxxxxxxx];;;"
    assert render(doc, print_width=12) == "[\n    xxxxxxxx\n];;;"


# --------------------------------------------------------------------------
# Nesting
# --------------------------------------------------------------------------


def test_outer_group_breaks_before_inner():
    """Outer breaks first; the inner group is then re-measured and stays flat.

    This is the property that makes nested calls readable, and it is not coded
    anywhere -- it falls out of measuring each group independently against the
    width remaining at the point it starts.
    """
    inner = brackets(text("abc"))  # flat: "[abc]" (5)
    outer = group(
        concat(
            text("("),
            indent(concat(SOFTLINE, text("a" * 10), text(","), LINE, inner), 4),
            SOFTLINE,
            text(")"),
        )
    )  # flat: "(aaaaaaaaaa, [abc])" (19)

    assert render(outer, print_width=19) == "(aaaaaaaaaa, [abc])"

    got = render(outer, print_width=16)
    assert got == "(\n    aaaaaaaaaa,\n    [abc]\n)"
    assert "[abc]" in got, "inner group should still fit flat once outer broke"


def test_hardline_propagates_through_three_levels():
    deep = group(concat(text("c"), HARDLINE, text("d")))
    mid = group(concat(text("b"), LINE, deep))
    top = group(concat(text("a"), LINE, mid))

    broken = propagate_breaks(top)
    assert broken[id(deep)] is True
    assert broken[id(mid)] is True
    assert broken[id(top)] is True

    # Every enclosing Line becomes a newline even though the text is tiny.
    assert render(top, print_width=200) == "a\nb\nc\nd"


def test_break_parent_forces_without_emitting():
    g = group(concat(text("a"), LINE, text("b"), BREAK_PARENT))
    assert propagate_breaks(g)[id(g)] is True
    assert render(g, print_width=200) == "a\nb"


def test_sibling_group_unaffected_by_a_forced_break():
    forced = group(concat(text("x"), HARDLINE, text("y")))
    quiet = group(concat(text("p"), LINE, text("q")))
    doc = concat(forced, text(" "), quiet)
    broken = propagate_breaks(doc)
    assert broken[id(forced)] is True
    assert broken[id(quiet)] is False


def test_should_break_forces_without_a_hardline():
    g = Group(concat(text("a"), LINE, text("b")), should_break=True)
    assert render(g, print_width=200) == "a\nb"


# --------------------------------------------------------------------------
# Indent and Align
# --------------------------------------------------------------------------


def test_indent_is_a_column_count_not_a_level():
    doc = group(concat(text("{"), indent(concat(HARDLINE, text("body")), 2), HARDLINE, text("}")))
    assert render(doc) == "{\n  body\n}"


def test_nested_indent_accumulates():
    doc = concat(
        text("a"),
        indent(concat(HARDLINE, text("b"), indent(concat(HARDLINE, text("c")), 4)), 4),
    )
    assert render(doc) == "a\n    b\n        c"


def test_align_targets_the_current_column():
    """``Align`` hangs under wherever the line has got to, unlike ``Indent``."""
    doc = concat(text("call("), align_to(concat(text("a"), HARDLINE, text("b"))), text(")"))
    assert render(doc) == "call(a\n     b)"


def test_align_offset_is_relative_to_the_current_column():
    doc = concat(text("ab"), align_to(concat(text("x"), HARDLINE, text("y")), 2))
    assert render(doc) == "abx\n    y"


def test_align_inside_indent_wins_for_its_subtree():
    doc = indent(concat(HARDLINE, text("f("), align_to(concat(text("1"), HARDLINE, text("2")))), 4)
    assert render(doc) == "\n    f(1\n      2"


def test_indent_inside_align_adds_to_it():
    doc = concat(
        text("f("),
        align_to(concat(text("1"), indent(concat(HARDLINE, text("2")), 4))),
        text(")"),
    )
    assert render(doc) == "f(1\n      2)"


def test_use_tabs_indents_with_tabs_but_aligns_with_spaces():
    doc = concat(
        text("a"),
        indent(concat(HARDLINE, text("f("), align_to(concat(text("1"), HARDLINE, text("2")))), 4),
    )
    got = render(doc, use_tabs=True, tab_width=4)
    lines = got.split("\n")
    assert lines[1].startswith("\t"), "indentation should use a tab"
    # The alignment column (6) is past the tab's 4, so the remainder is spaces.
    assert lines[2] == "\t  2", repr(lines[2])


# --------------------------------------------------------------------------
# IfBreak
# --------------------------------------------------------------------------


class TestIfBreak:
    def make(self):
        # A trailing comma that exists only in the exploded form.
        items = join(concat(text(","), LINE), [text("aa"), text("bb")])
        return group(
            concat(
                text("("),
                indent(concat(SOFTLINE, items, IfBreak(text(","))), 4),
                SOFTLINE,
                text(")"),
            )
        )

    def test_flat_state_omits_the_trailing_comma(self):
        assert render(self.make(), print_width=40) == "(aa, bb)"

    def test_broken_state_emits_it(self):
        assert render(self.make(), print_width=6) == "(\n    aa,\n    bb,\n)"

    def test_group_id_consults_a_named_group_not_the_enclosing_one(self):
        named = Group(concat(text("x"), LINE, text("y")), should_break=True, id="outer")
        doc = concat(named, text("|"), IfBreak(text("B"), text("F"), group_id="outer"))
        assert render(doc, print_width=200) == "x\ny|B"

    def test_unknown_group_id_reads_as_flat(self):
        doc = IfBreak(text("B"), text("F"), group_id="never-defined")
        assert render(doc) == "F"

    def test_a_hardline_in_break_contents_does_not_make_its_own_condition_true(self):
        """Otherwise ``IfBreak`` would be self-fulfilling and therefore useless."""
        g = group(concat(text("a"), LINE, IfBreak(HARDLINE, text("!"))))
        assert propagate_breaks(g)[id(g)] is False
        assert render(g, print_width=200) == "a !"


# --------------------------------------------------------------------------
# Fill
# --------------------------------------------------------------------------


class TestFill:
    def items(self, *names):
        return fill_with(concat(text(","), LINE), [text(n) for n in names])

    def test_packs_greedily_rather_than_one_per_line(self):
        doc = self.items("aa", "bb", "cc", "dd", "ee")
        # Flat is "aa, bb, cc, dd, ee" (18). At 10 columns it should pack.
        got = render(doc, print_width=10)
        assert got == "aa, bb,\ncc, dd, ee", repr(got)

    def test_everything_on_one_line_when_it_fits(self):
        assert render(self.items("aa", "bb", "cc"), print_width=40) == "aa, bb, cc"

    def test_separator_width_is_charged_to_the_line_it_ends(self):
        """The off-by-one greedy fill always gets wrong.

        Measuring an item alone packs it, then discovers the separator that
        must follow does not fit, and overflows by exactly the separator width.
        Here ``aaa`` plus ``,`` is exactly 4, so at width 4 it may be packed;
        at width 3 it may not.
        """
        doc = self.items("aaa", "bbb")
        assert max(len(l) for l in render(doc, print_width=4).split("\n")) <= 4

    def test_single_item_fill(self):
        assert render(fill_with(concat(text(","), LINE), [text("only")])) == "only"

    def test_empty_fill(self):
        assert render(Fill(())) == ""

    def test_fill_never_exceeds_the_width_it_was_given(self):
        doc = self.items(*[f"item{i}" for i in range(20)])
        for width in (8, 12, 20, 33, 60):
            longest = max(len(l) for l in render(doc, print_width=width).split("\n"))
            assert longest <= width, f"width={width} produced a {longest}-column line"


# --------------------------------------------------------------------------
# Verbatim
# --------------------------------------------------------------------------


class TestVerbatim:
    def test_bytes_are_preserved_including_interior_indentation(self):
        payload = "  line one\n      line two\n"
        assert payload in render(Verbatim(payload))

    def test_forces_enclosing_groups_broken(self):
        g = group(concat(text("a"), LINE, Verbatim("x")))
        assert propagate_breaks(g)[id(g)] is True

    def test_is_exempt_from_width_accounting_while_being_measured(self):
        """A payload's bulk must not decide a break for the code around it.

        A Verbatim always forces its enclosing groups broken, so the only way
        its width can reach a fit decision is through a ``must_be_flat``
        measurement -- a Fill item, in practice. It contributes nothing there.
        """
        long_payload = "z" * 500
        doc = fill_with(
            concat(text(","), LINE),
            [Verbatim(long_payload), text("aa"), text("bb")],
        )
        got = render(doc, print_width=20)
        assert got.startswith(long_payload + ", aa"), repr(got[-40:])

    def test_a_payload_does_not_leak_into_the_next_line(self):
        long_payload = "z" * 500
        doc = concat(Verbatim(long_payload), HARDLINE, group(concat(text("a"), LINE, text("b"))))
        assert render(doc, print_width=20).endswith("\na b")

    def test_column_tracking_resumes_after_a_multiline_payload(self):
        doc = concat(Verbatim("aa\nbbbb"), align_to(concat(text("!"), HARDLINE, text("?"))))
        # Align targets the column where it is *entered* -- 4, after "bbbb" --
        # not where the text inside it happens to start.
        assert render(doc) == "aa\nbbbb!\n    ?"


# --------------------------------------------------------------------------
# Whitespace hygiene
# --------------------------------------------------------------------------


def test_no_trailing_whitespace_on_a_line_that_ends_up_empty():
    doc = indent(concat(HARDLINE, HARDLINE, text("x")), 4)
    got = render(doc)
    assert got == "\n\n    x"
    assert not any(l != l.rstrip() for l in got.split("\n"))


def test_blank_lines_before_a_hard_break():
    doc = concat(text("a"), HardLine(blank_before=2), text("b"))
    assert render(doc) == "a\n\n\nb"


def test_output_never_ends_in_trailing_whitespace():
    doc = concat(text("a"), indent(HARDLINE, 8))
    assert render(doc) == "a\n"


def test_rendering_is_pure():
    """Rendering twice gives the same answer -- no state leaks between calls."""
    doc = brackets(fill_with(concat(text(","), LINE), [text(f"n{i}") for i in range(12)]))
    assert render(doc, print_width=21) == render(doc, print_width=21)


def test_shared_subtree_is_laid_out_consistently():
    shared = group(concat(text("["), SOFTLINE, text("shared"), SOFTLINE, text("]")))
    doc = concat(shared, text(" "), shared)
    assert render(doc, print_width=200) == "[shared] [shared]"


# --------------------------------------------------------------------------
# Node hygiene
# --------------------------------------------------------------------------


def test_text_rejects_newlines():
    with pytest.raises(ValueError, match="must not contain a newline"):
        Text("a\nb")


def test_concat_flattens_and_drops_empties():
    doc = concat(text("a"), concat(EMPTY, text("b")), EMPTY, [text("c")])
    assert render(doc) == "abc"
    assert not isinstance(doc.parts[0], type(EMPTY)) or doc.parts[0].value == "a"


def test_concat_of_nothing_is_empty():
    assert render(concat()) == ""


def test_unknown_node_is_rejected_rather_than_ignored():
    class Bogus:
        pass

    with pytest.raises(TypeError, match="unknown Layout node"):
        render(Bogus())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="not a Layout node"):
        concat(text("a"), Bogus())  # type: ignore[arg-type]


def test_deep_nesting_does_not_recurse():
    """A formatter that raises RecursionError on a big file is not usable."""
    doc = text("leaf")
    for _ in range(5000):
        doc = group(indent(concat(SOFTLINE, doc), 0))
    assert render(doc, print_width=100) == "leaf"

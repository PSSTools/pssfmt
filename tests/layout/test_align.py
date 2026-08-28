"""``T-2`` / ``P2-4`` / ``P2-6`` -- the four alignment modes.

``infer`` carries the most weight here: it is the resolution to ``Q-5``, and
the reason the alignment-versus-diff-size argument in ``formatter.md``
section 7.6 is a false binary (``PLAN.md`` section 6.4). If ``infer`` is
wrong, hand-aligned register tables get destroyed or ordinary code gets huge
diffs, and either one loses the tool its users.
"""

from __future__ import annotations

import pytest

from pssfmt.layout import ALIGN_MARK as M
from pssfmt.layout import AlignMode, GroupBoundary, align_text, strip_marks

pytestmark = [pytest.mark.layout, pytest.mark.unit]


def lines(*ls):
    return "\n".join(ls)


# A block the author hand-aligned: every comment starts at the same column.
ALIGNED = lines(
    f"bit[8]  addr;{M}     // offset",
    f"bit[32] data;{M}     // payload",
    f"bit     valid;{M}    // strobe",
)

# The same declarations with nobody having aligned anything.
UNALIGNED = lines(
    f"bit[8]  addr;{M} // offset",
    f"bit[32] data;{M} // payload",
    f"bit     valid;{M} // strobe",
)


class TestPreserve:
    def test_leaves_the_authors_spacing_exactly_alone(self):
        assert align_text(ALIGNED, mode=AlignMode.PRESERVE) == strip_marks(ALIGNED)
        assert align_text(UNALIGNED, mode=AlignMode.PRESERVE) == strip_marks(UNALIGNED)

    def test_is_a_true_no_op_apart_from_removing_the_marks(self):
        messy = f"a;{M}        // x\nbbbbbb;{M} // y"
        assert align_text(messy, mode=AlignMode.PRESERVE) == messy.replace(M, "")


class TestFlushLeft:
    def test_collapses_every_stop_to_one_space(self):
        got = align_text(ALIGNED, mode=AlignMode.FLUSH_LEFT)
        assert got == lines(
            "bit[8]  addr; // offset",
            "bit[32] data; // payload",
            "bit     valid; // strobe",
        )


class TestAlign:
    def test_pads_every_stop_to_the_widest_cell(self):
        got = align_text(UNALIGNED, mode=AlignMode.ALIGN)
        assert got == lines(
            "bit[8]  addr;  // offset",
            "bit[32] data;  // payload",
            "bit     valid; // strobe",
        )
        cols = {l.index("//") for l in got.split("\n")}
        assert len(cols) == 1

    def test_multiple_column_stops_align_independently(self):
        src = lines(
            f"bit{M} a{M} = 1;",
            f"bit[32]{M} bbbb{M} = 2;",
        )
        got = align_text(src, mode=AlignMode.ALIGN)
        assert got == lines(
            "bit     a    = 1;",
            "bit[32] bbbb = 2;",
        )

    def test_a_wide_early_cell_pushes_every_later_column(self):
        src = lines(f"a{M} x{M} 1;", f"aaaaaaaa{M} y{M} 2;")
        got = align_text(src, mode=AlignMode.ALIGN).split("\n")
        assert got[0].index("1;") == got[1].index("2;")

    def test_lines_with_fewer_stops_drop_out_of_later_columns(self):
        src = lines(f"aa{M} b{M} c", f"a{M} bb")
        got = align_text(src, mode=AlignMode.ALIGN)
        assert got == lines("aa b c", "a  bb")

    def test_east_asian_width_is_respected(self):
        """Aligning on ``len()`` puts CJK comments a column out; this catches it."""
        src = lines(f"你好;{M} // a", f"ab;{M} // b")
        got = align_text(src, mode=AlignMode.ALIGN).split("\n")
        from pssfmt.layout import width_of

        assert width_of(got[0].split("//")[0]) == width_of(got[1].split("//")[0])


class TestInfer:
    def test_keeps_an_already_aligned_block_aligned(self):
        got = align_text(ALIGNED, mode=AlignMode.INFER)
        cols = {l.index("//") for l in got.split("\n")}
        assert len(cols) == 1, got

    def test_an_aligned_block_comes_back_byte_for_byte(self):
        """``infer`` reproduces a table; it does not re-align one.

        The test above passes under either behaviour, because re-aligning to
        the tightest consistent column also leaves the ``//`` in one column.
        The difference is whether the author's *chosen* column survives, and
        it is the whole value of the mode: re-aligning collapses a block of
        equal-width cells to exactly what flush-left would produce, which over
        the PSS corpus made ``infer`` worth one file more than flush-left.
        """
        assert align_text(ALIGNED, mode=AlignMode.INFER) == strip_marks(ALIGNED)

    def test_leaves_an_unaligned_block_flush_left(self):
        got = align_text(UNALIGNED, mode=AlignMode.INFER)
        assert got == align_text(UNALIGNED, mode=AlignMode.FLUSH_LEFT)

    def test_a_single_marked_line_is_left_exactly_as_written(self):
        """One line is not a ragged block -- it is no evidence at all.

        ``infer`` concludes from a *run*. With nothing to compare against
        there is no conclusion to draw, so collapsing the author's padding
        would be a guess wearing a decision's clothes. Reproduced instead.
        """
        src = f"bit a;{M}      // lonely"
        assert align_text(src, mode=AlignMode.INFER) == "bit a;      // lonely"

    def test_equal_length_declarations_are_not_read_as_a_table(self):
        """Identical widths align by coincidence; that is not authorial intent.

        Without this test, a run of same-length declarations reads as
        deliberately aligned, ``infer`` turns alignment on for the block, and
        the next line anybody adds reflows all of them -- exactly the large
        diff section 7.6 warns about.
        """
        src = lines(f"aa;{M} // x", f"bb;{M} // y")
        assert align_text(src, mode=AlignMode.INFER) == lines("aa; // x", "bb; // y")

    def test_decides_per_group_not_per_file(self):
        src = ALIGNED + "\n\n" + UNALIGNED
        got = align_text(src, mode=AlignMode.INFER).split("\n")
        assert len({l.index("//") for l in got[:3]}) == 1
        assert len({l.index("//") for l in got[4:]}) > 1


class TestGroupBoundaries:
    def test_blank_lines_separate_tables_by_default(self):
        src = lines(f"a;{M} // x", f"bbbbbb;{M} // y", "", f"c;{M} // z")
        got = align_text(src, mode=AlignMode.ALIGN).split("\n")
        assert got[0].index("//") == got[1].index("//")
        assert got[3] == "c; // z", "the third line is its own group"

    def test_boundary_none_aligns_across_a_blank_line(self):
        src = lines(f"a;{M} // x", "", f"bbbbbb;{M} // y")
        got = align_text(src, mode=AlignMode.ALIGN, boundary=GroupBoundary.NONE).split("\n")
        assert got[0].index("//") == got[2].index("//")

    @pytest.mark.parametrize("sep", ["//------", "// ======", "/* ***** */"])
    def test_separator_comments_split_a_table_when_configured(self, sep):
        src = lines(f"a;{M} // x", sep, f"bbbbbb;{M} // y")
        got = align_text(
            src, mode=AlignMode.ALIGN, boundary=GroupBoundary.SEPARATOR_COMMENTS
        ).split("\n")
        assert got[2] == "bbbbbb; // y"

    def test_an_ordinary_comment_is_not_a_separator(self):
        src = lines(f"a;{M} // x", "// a real remark", f"bbbbbb;{M} // y")
        got = align_text(
            src, mode=AlignMode.ALIGN, boundary=GroupBoundary.SEPARATOR_COMMENTS
        ).split("\n")
        assert got[0].index("//") == got[2].index("//")

    def test_an_indentation_change_always_splits(self):
        """Members at different nesting depths are not one table.

        Aligning across depths is what produces the drifting-column effect
        that makes people turn alignment off entirely, so this holds under
        every boundary setting.
        """
        src = lines(f"a;{M} // x", f"    bbbbbb;{M} // y")
        for boundary in GroupBoundary:
            got = align_text(src, mode=AlignMode.ALIGN, boundary=boundary).split("\n")
            assert got[0] == "a; // x", boundary
            assert got[1] == "    bbbbbb; // y", boundary


class TestAbandonOverLimit:
    def test_alignment_never_causes_an_overflow(self):
        """Verible's rule, and the reason alignment can be on by default.

        Padding the *short* line out to the long line's column is what
        overflows; the long line itself was always fine.
        """
        src = lines(
            f"a;{M} // {'y' * 60}",
            f"{'x' * 60};{M} // ok",
        )
        got = align_text(src, mode=AlignMode.ALIGN, print_width=80)
        assert all(len(l) <= 80 for l in got.split("\n")), got
        assert got.split("\n")[0].startswith("a; //"), "group fell back to flush-left"

    def test_an_inherently_long_line_does_not_cost_the_block_its_alignment(self):
        """Abandoning here would lose the alignment without fixing the overflow.

        Verible's rule is that alignment must not *cause* an overflow. A line
        that is over the limit flush-left is over the limit either way, and
        flattening the whole table for it is a strictly worse outcome.
        """
        src = lines(
            f"short;{M} // ok",
            f"{'x' * 60};{M} // this one is very long indeed",
        )
        got = align_text(src, mode=AlignMode.ALIGN, print_width=80).split("\n")
        assert got[0].index("//") == got[1].index("//")

    def test_a_group_that_fits_is_still_aligned(self):
        got = align_text(UNALIGNED, mode=AlignMode.ALIGN, print_width=80)
        assert len({l.index("//") for l in got.split("\n")}) == 1

    def test_infer_also_abandons_rather_than_overflowing(self):
        src = lines(
            f"a;{M}                          // {'y' * 40}",
            f"{'x' * 40};{M}  // ok",
        )
        got = align_text(src, mode=AlignMode.INFER, print_width=70)
        assert all(len(l) <= 70 for l in got.split("\n")), got


class TestHygiene:
    def test_text_without_marks_is_returned_untouched(self):
        src = "component c {\n    action a {}\n}"
        for mode in AlignMode:
            assert align_text(src, mode=mode) == src

    def test_no_mark_survives_any_mode(self):
        for mode in AlignMode:
            for boundary in GroupBoundary:
                out = align_text(ALIGNED, mode=mode, boundary=boundary)
                assert M not in out, (mode, boundary)

    def test_line_count_is_preserved(self):
        for mode in AlignMode:
            src = ALIGNED + "\n\n" + UNALIGNED
            assert align_text(src, mode=mode).count("\n") == src.count("\n")

    def test_alignment_is_idempotent(self):
        """Alignment output has no marks, so a second pass must be a no-op."""
        for mode in AlignMode:
            once = align_text(ALIGNED, mode=mode)
            assert align_text(once, mode=mode) == once

    def test_unmarked_lines_pass_through_a_group_unchanged(self):
        src = lines(f"a;{M} // x", "    continued", f"bbbbbb;{M} // y")
        got = align_text(src, mode=AlignMode.ALIGN, boundary=GroupBoundary.NONE).split("\n")
        assert got[1] == "    continued"

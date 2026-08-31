"""``T-34`` -- ``pssfmt.ranges``, the ``--lines`` machinery (``P4-4``).

Most of this file is one idea used four ways: a range formatter cannot be
checked against hand-written expected output, because the thing that makes it
correct is a *relationship* to the whole-file formatter, not a shape somebody
can eyeball. So the oracles are relationships:

* ``restrict`` with the whole file selected **is** the full format. This makes
  ``--lines 1:N`` and a plain format the same operation, which turns every
  corpus file into a test of the range machinery for free.
* ``restrict`` with nothing selected **is** the input, byte for byte.
* Every edit is whitespace-only. This is the assertion ``P4-4`` asked for.
  It is a test here rather than an ``assert`` in the module because the
  module makes it true by construction -- so the thing worth checking is the
  construction, over real input, and not one run of it.
* Any selection at all preserves the non-whitespace text. That is the
  property a user cares about: whatever ``--lines`` did, it did not move any
  of your program.

Together those pin the behaviour without a single expected-output file, which
is section 7.1's argument again -- the same one that produced the round-trip
and idempotence oracles, and the ``git check-ignore`` differential in
``T-33``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ``pssfmt.rules`` reaches ``pssfmt.trivia``, which imports ``pssparser.tokens``
# at module scope, so this file cannot even be *collected* without the parser.
# Every other suite that crosses that line skips; this one was the exception,
# which turned a pssparser-free run into a collection error rather than a skip
# (T-2 requires the layout suites to pass with pssparser absent, and a
# collection error in a sibling file stops the whole run).
pytest.importorskip("pssparser")

from support import corpus_files  # noqa: E402

from pssfmt.ranges import (Edit, LineRange, RangeError, edits,  # noqa: E402
                           parse_range, parse_ranges, restrict)
from pssfmt.rules import format_source  # noqa: E402
from pssfmt.style import Style  # noqa: E402
from pssfmt.verify import verify  # noqa: E402


def nonws(text: str) -> str:
    return "".join(text.split())


#: Styles chosen to move a lot of text around, because the interesting inputs
#: to this module are files the formatter changes *heavily*. At the default
#: style most of the corpus is already formatted and produces no edits at all
#: -- 42 hunks across 92 files -- which would make a green suite here mean
#: almost nothing.
STYLES = (
    Style(),
    Style(print_width=40, indent_width=2),
    Style(print_width=120, indent_width=8, max_blank_lines=0),
)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

class TestParsing:

    def test_a_range(self):
        assert parse_range("12:34") == LineRange(12, 34)

    def test_whitespace_is_allowed_around_the_numbers(self):
        assert parse_range(" 1 : 2 ") == LineRange(1, 2)

    def test_a_single_line(self):
        assert parse_range("7:7") == LineRange(7, 7)

    @pytest.mark.parametrize("spec", ["12", "", ":", "12:", ":34", "a:b",
                                      "1:2:3", "1.5:2", "1,2", "2:1"])
    def test_anything_else_is_refused(self, spec):
        """Strict, because the failure mode of a lenient parser here is a
        silently different range -- and a wrong range is invisible in the
        output, which is the whole reason ``P4-1`` refused this flag rather
        than ignoring it."""
        with pytest.raises(RangeError):
            parse_range(spec)

    def test_line_numbers_start_at_one(self):
        with pytest.raises(RangeError, match="start at 1"):
            parse_range("0:3")

    def test_a_backwards_range_is_refused(self):
        with pytest.raises(RangeError, match="ends before it starts"):
            parse_range("9:2")

    def test_several_ranges_union(self):
        assert parse_ranges(["1:2", "9:9"]) == (LineRange(1, 2),
                                                LineRange(9, 9))

    def test_ranges_need_not_be_sorted_or_disjoint(self):
        """A caller assembling ranges from a diff has no reason to tidy them,
        and making it do so would be a second thing to get wrong."""
        assert len(parse_ranges(["9:20", "1:12"])) == 2


# ---------------------------------------------------------------------------
# The edit computation itself
# ---------------------------------------------------------------------------

class TestEdits:

    def test_identical_texts_have_no_edits(self):
        lines = ["a;\n", "b;\n"]
        assert edits(lines, lines) == ()

    def test_a_changed_line(self):
        assert edits(["a ;\n"], ["a;\n"]) == (Edit(0, 1, 0, 1),)

    def test_a_deleted_blank_line(self):
        assert edits(["a;\n", "\n", "b;\n"], ["a;\n", "b;\n"]) == (
            Edit(1, 2, 1, 1),)

    def test_an_inserted_blank_line(self):
        assert edits(["a;\n", "b;\n"], ["a;\n", "\n", "b;\n"]) == (
            Edit(1, 1, 1, 2),)

    def test_lines_joined_into_one(self):
        assert edits(["f(\n", "  a);\n"], ["f(a);\n"]) == (Edit(0, 2, 0, 1),)

    def test_a_repeated_line_does_not_create_a_false_cut(self):
        """The failure mode that makes ``difflib`` unusable here.

        Two closing braces are the same line, so a line matcher will happily
        pair the second with the first and produce a hunk that straddles real
        code. Cut points are computed from how much non-whitespace text has
        been emitted, so an identical line at the *wrong* offset is not a cut
        point at all.
        """
        before = ["if (a) {\n", "x;\n", "}\n", "if (b) {\n", "y;\n", "}\n"]
        after = ["if (a) { x;\n", "}\n", "if (b) {\n", "y; }\n"]
        for edit in edits(before, after):
            assert nonws("".join(before[edit.start:edit.stop])) == \
                nonws("".join(after[edit.new_start:edit.new_stop]))

    def test_texts_that_are_not_whitespace_variants_are_refused(self):
        """The precondition, stated out loud. Every caller has run the
        verifier first, so this cannot fire in practice -- which is exactly
        why it is worth having a test that says what would happen if it did,
        rather than a comment claiming it cannot."""
        with pytest.raises(RangeError, match="same non-whitespace"):
            edits(["a;\n"], ["b;\n"])

    def test_edits_are_disjoint_and_ordered(self):
        before = ["a ;\n", "b;\n", "\n", "\n", "c ;\n"]
        after = ["a;\n", "b;\n", "\n", "c;\n"]
        found = edits(before, after)
        assert found
        assert all(x.stop <= y.start for x, y in zip(found, found[1:]))
        assert all(x.new_stop <= y.new_start for x, y in zip(found, found[1:]))


# ---------------------------------------------------------------------------
# restrict, against synthetic input
# ---------------------------------------------------------------------------

SOURCE = """\
component  a   {
    int    x   ;
}
component  b   {
    int    y   ;
}
"""


def formatted(text: str, style: Style = Style()) -> str:
    return format_source(text, style=style)


class TestRestrict:

    def test_no_ranges_is_the_input(self):
        assert restrict(SOURCE, formatted(SOURCE), []) == SOURCE

    def test_the_whole_file_is_the_full_format(self):
        out = formatted(SOURCE)
        n = len(SOURCE.splitlines())
        assert restrict(SOURCE, out, [LineRange(1, n)]) == out

    def test_a_range_leaves_the_rest_byte_for_byte(self):
        out = restrict(SOURCE, formatted(SOURCE), [LineRange(4, 6)])
        assert out.splitlines()[:3] == SOURCE.splitlines()[:3]
        assert out.splitlines()[3:] == formatted(SOURCE).splitlines()[3:]

    def test_a_range_formats_what_it_names(self):
        out = restrict(SOURCE, formatted(SOURCE), [LineRange(1, 3)])
        assert "component a {" in out
        assert "component  b   {" in out

    def test_two_ranges_union(self):
        both = restrict(SOURCE, formatted(SOURCE),
                        [LineRange(1, 1), LineRange(4, 4)])
        assert "component a {" in both
        assert "component b {" in both
        # ...and the member lines, named by neither range, are untouched.
        assert "    int    x   ;" in both

    def test_a_wider_range_never_undoes_a_narrower_one(self):
        """Monotonicity. It is what makes ``--lines`` composable: a caller
        widening the range because the user selected more text must not find
        that something it had already formatted came back."""
        narrow = restrict(SOURCE, formatted(SOURCE), [LineRange(4, 6)])
        wide = restrict(SOURCE, formatted(SOURCE), [LineRange(1, 6)])
        assert nonws(narrow) == nonws(wide) == nonws(SOURCE)
        assert narrow.splitlines()[3:] == wide.splitlines()[3:]

    def test_a_range_past_the_end_of_the_file_is_harmless(self):
        out = formatted(SOURCE)
        assert restrict(SOURCE, out, [LineRange(1, 9999)]) == out

    def test_a_range_below_every_edit_changes_nothing(self):
        already = formatted(SOURCE)
        assert restrict(already, formatted(already), [LineRange(1, 3)]) == \
            already

    def test_an_empty_file(self):
        assert restrict("", "", [LineRange(1, 1)]) == ""

    def test_trailing_blank_lines_are_one_edit_each(self):
        """The end of the file is where the two sides stop lining up: three
        trailing blank lines become none, so one side runs out while the other
        still has lines. They come out as three edits rather than one, and
        that granularity is the point -- ``--lines 3:3`` over this file should
        remove the blank line on line 3 and not the two around it.

        An earlier version coalesced them into a single ``Edit(1, 4, 1, 1)``
        by requiring both sides to run out together. It was sound, it was
        untested, and it was worse: naming one line deleted three.
        """
        assert edits(["a;\n", "\n", "\n", "\n"], ["a;\n"]) == (
            Edit(1, 2, 1, 1), Edit(2, 3, 1, 1), Edit(3, 4, 1, 1))

    def test_a_range_takes_only_the_blank_line_it_names(self):
        src, out = "a;\n\n\n\n", "a;\n"
        assert restrict(src, out, [LineRange(3, 3)]) == "a;\n\n\n"

    def test_an_insertion_at_the_edge_of_a_range_is_taken(self):
        """A pure insertion occupies no input lines, so it cannot *overlap* a
        range -- it can only sit against one. A blank line the formatter wants
        before a member you asked to format is part of formatting it, so an
        edit touching either end of the range counts.

        Passed literal texts rather than formatter output: what matters is the
        boundary arithmetic, and depending on the rule set to produce an
        insertion at a chosen line would make this test fragile for no gain.
        """
        src, out = "a;\nb;\n", "a;\n\nb;\n"
        assert restrict(src, out, [LineRange(1, 1)]) == out
        assert restrict(src, out, [LineRange(2, 2)]) == out

    def test_an_insertion_away_from_a_range_is_not_taken(self):
        """The other half of the rule above, which a boundary condition
        loosened far enough would satisfy vacuously."""
        src = "a;\nb;\nc;\nd;\n"
        out = "a;\nb;\n\nc;\nd;\n"
        assert restrict(src, out, [LineRange(4, 4)]) == src


# ---------------------------------------------------------------------------
# The corpus, as an oracle
# ---------------------------------------------------------------------------

FILES = corpus_files()

CASES = [(path, style) for path in FILES for style in STYLES]


def _ids(cases):
    return ["%s-w%d-i%d" % (p.name, s.print_width, s.indent_width)
            for p, s in cases]


@pytest.mark.corpus
@pytest.mark.integration
class TestTheCorpus:
    """The relationships, over every corpus file at three widths.

    No expected output anywhere in here, and that is the point: these hold for
    any input the formatter accepts, so the suite grows with the corpus rather
    than with somebody's patience for writing ``.expected`` files.
    """

    @pytest.mark.parametrize("path,style", CASES, ids=_ids(CASES))
    def test_every_edit_is_whitespace_only(self, path, style):
        source = path.read_text(encoding="utf-8")
        out = format_source(source, style=style)
        before = source.splitlines(keepends=True)
        after = out.splitlines(keepends=True)
        for edit in edits(before, after):
            assert nonws("".join(before[edit.start:edit.stop])) == \
                nonws("".join(after[edit.new_start:edit.new_stop])), (
                    "edit %r in %s is not whitespace-only" % (edit, path.name))

    @pytest.mark.parametrize("path,style", CASES, ids=_ids(CASES))
    def test_selecting_everything_is_the_full_format(self, path, style):
        source = path.read_text(encoding="utf-8")
        out = format_source(source, style=style)
        n = len(source.splitlines()) or 1
        assert restrict(source, out, [LineRange(1, n)]) == out

    @pytest.mark.parametrize("path,style", CASES, ids=_ids(CASES))
    def test_selecting_nothing_is_the_input(self, path, style):
        source = path.read_text(encoding="utf-8")
        out = format_source(source, style=style)
        assert restrict(source, out, []) == source

    @pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
    def test_any_partial_selection_preserves_the_program_text(self, path):
        """Four ranges per file, chosen to land on quarter boundaries so they
        cut wherever the file happens to have something interesting."""
        source = path.read_text(encoding="utf-8")
        out = format_source(source, style=STYLES[1])
        n = max(len(source.splitlines()), 1)
        q = max(n // 4, 1)
        for lo, hi in ((1, q), (q, 2 * q), (2 * q, 3 * q), (3 * q, n)):
            spliced = restrict(source, out, [LineRange(lo, hi)])
            assert nonws(spliced) == nonws(source), \
                "lines %d:%d of %s lost or gained text" % (lo, hi, path.name)

    @pytest.mark.parametrize("path", FILES[::12], ids=lambda p: p.name)
    def test_a_partial_selection_passes_the_verifier(self, path):
        """The expensive version of the test above, on a sample.

        The cheap one compares text; this one re-lexes and re-parses, which is
        the check that matters because whitespace is not always insignificant
        -- ``//`` runs to the end of a line. A sample rather than the whole
        corpus because it costs four parses per file, and the property it
        checks does not vary much by file.
        """
        source = path.read_text(encoding="utf-8")
        out = format_source(source, style=STYLES[1])
        n = max(len(source.splitlines()), 1)
        for lo, hi in ((1, n // 2 or 1), (n // 2 or 1, n)):
            spliced = restrict(source, out, [LineRange(lo, hi)])
            assert verify(source, spliced) == (), \
                "lines %d:%d of %s did not verify" % (lo, hi, path.name)

    def test_the_corpus_actually_exercises_this(self):
        """Non-vacuity. Every test above passes trivially on a file the
        formatter does not change, and at the default style most of the
        corpus is such a file -- which is why ``STYLES`` is not just the
        default one, and why this counts."""
        total = 0
        for path in FILES:
            source = path.read_text(encoding="utf-8")
            out = format_source(source, style=STYLES[1])
            total += len(edits(source.splitlines(keepends=True),
                               out.splitlines(keepends=True)))
        assert total > 500, "only %d edits across the corpus" % total

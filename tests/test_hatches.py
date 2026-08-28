"""``T-28`` -- the escape hatches (``P3-9``, § 5.3).

Section 5.3 is the one part of the design marked *non-negotiable*, and the
reason is in section 1: users need escape hatches more than they need options.
A formatter that cannot be switched off over the one table somebody spent an
afternoon aligning is a formatter that gets switched off over the repository.

Three directives::

    // pssfmt off      … everything from here    ─┐  reproduced
    // pssfmt on       … until here               ─┘  byte for byte
    // pssfmt ignore   … the next construct only

What is actually being tested
-----------------------------
The promise is **bytes**, so nearly every assertion here is a byte comparison
against a region of the input rather than a check that the output "looks
right". A hatch that merely produced *tidier* output than formatting would
have is a hatch that failed.

The corpus contributes nothing to this file, and cannot: it holds **zero**
directives across 92 files, for the good reason that ``pssfmt`` has never
shipped. So every input here is hand-written, and the malformed ones matter
more than the well-formed ones -- a directive is written by hand, under
deadline, by someone who is already annoyed, and it will be misspelled,
unmatched, and nested.

Where the mechanism lives
-------------------------
Two places, and neither was written for this:

* :func:`pssfmt.rules.decls._collect` is the only place any body's members are
  gathered -- declarations, constraints and activities all reach it -- so
  member-level protection is one check rather than one per rule;
* :func:`pssfmt.rules.tokens.emit_span` already declines any span containing a
  comment between two tokens, which is what a directive *inside* a construct
  is. Below member level the hatch is honoured for free.

That is why section 5.3 could promise "a few lines rather than a subsystem"
and be right.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from dataclasses import replace  # noqa: E402

from pssparser import cst as _cst  # noqa: E402

from pssfmt.rules import format_source  # noqa: E402
from pssfmt.style import DEFAULT_STYLE  # noqa: E402
from pssfmt.trivia import TriviaMap  # noqa: E402
from pssfmt.verbatim import (Hatches, NO_HATCHES, directive_of,  # noqa: E402
                             scan_hatches, verbatim_lines)
from pssfmt.verify import verify  # noqa: E402

#: A member the formatter would certainly rewrite if it were allowed to: two
#: fields on one line, with hand-inserted padding between them. Every "is it
#: frozen?" test below leans on the fact that formatting this is *visible*.
TABLE = "struct a { bit[8]  x;   bit[8]  y; }"


def hatches_for(src: str) -> Hatches:
    """The directives in *src*, resolved to code positions."""
    return scan_hatches(TriviaMap(_cst.parse(src).tokens))


def assert_safe(src: str) -> str:
    """Formats *src*, and checks the output still says what the input said."""
    out = format_source(src)
    violations = verify(src, out)
    assert not violations, "verifier rejected the output: %s" % (violations,)
    assert format_source(out) == out, "not idempotent"
    return out


# ---------------------------------------------------------------------------
# Recognising a directive
# ---------------------------------------------------------------------------


class TestWhatCountsAsADirective:
    """The match is exact, and the hazard is on the permissive side.

    ``// we should turn pssfmt off for this table`` is prose *about* the
    formatter, and a substring match would read it as an instruction and
    silently stop formatting the rest of the file. Prose mentioning the tool
    is far more common than directives are, so a loose match is wrong on the
    common case rather than on the rare one.
    """

    @pytest.mark.parametrize("comment,verb", [
        ("// pssfmt off", "off"),
        ("// pssfmt on", "on"),
        ("// pssfmt ignore", "ignore"),
        ("//pssfmt off", "off"),
        ("//   pssfmt   off   ", "off"),
        ("// pssfmt off\n", "off"),
        ("/* pssfmt off */", "off"),
        ("/*pssfmt off*/", "off"),
    ])
    def test_the_spellings_that_are_directives(self, comment, verb):
        assert directive_of(comment) == verb

    @pytest.mark.parametrize("comment", [
        "// we should turn pssfmt off for this table",
        "// pssfmt off for now",
        "// TODO: pssfmt off",
        "// pssfmt: off",
        "// pssfmt off!",
        "// pssfmt",
        "// pssfmt disable",
        "// pssfmt OFF",
        "// PSSFMT off",
        "// off",
        "// pssfmt off on",
        "not a comment at all",
        "",
    ])
    def test_the_spellings_that_are_not(self, comment):
        assert directive_of(comment) is None

    def test_prose_about_the_formatter_does_not_disable_the_formatter(self):
        """The whole reason the match is exact, end to end."""
        src = ("component c {\n"
               "    // we should turn pssfmt off for this table\n"
               "    %s\n"
               "}\n" % TABLE)
        assert TABLE not in assert_safe(src)


# ---------------------------------------------------------------------------
# off / on
# ---------------------------------------------------------------------------


class TestOffAndOn:

    def test_the_region_is_reproduced_byte_for_byte(self):
        src = ("component c {\n"
               "    // pssfmt off\n"
               "    %s\n"
               "    // pssfmt on\n"
               "    %s\n"
               "}\n" % (TABLE, TABLE))
        out = assert_safe(src)
        assert "    %s\n" % TABLE in out, "the hatched member was reformatted"
        assert out.count(TABLE) == 1, "the member after ``on`` was not formatted"

    def test_a_directive_applies_from_the_token_it_leads(self):
        """``off`` protects what follows it, not what precedes it.

        Attachment does the work: section 3.1 makes an own-line comment the
        *leading* trivia of the next code token, so "where the directive takes
        effect" is a question the trivia map has already answered and this
        does not re-answer.
        """
        src = ("component c {\n"
               "    %s\n"
               "    // pssfmt off\n"
               "    %s\n"
               "}\n" % (TABLE, TABLE))
        out = assert_safe(src)
        assert out.count(TABLE) == 1, "the member before ``off`` was frozen too"

    def test_a_trailing_directive_applies_from_the_next_token(self):
        """``} // pssfmt off`` -- same rule, arrived at from the other side.

        A trailing comment belongs to the token *before* it, so the directive
        takes effect at the token after that one. The member it is written on
        is therefore still formatted, which is the answer someone writing it
        at the end of a line intends.
        """
        src = ("component c {\n"
               "    struct a { bit[8]  x; } // pssfmt off\n"
               "    %s\n"
               "}\n" % TABLE)
        out = assert_safe(src)
        assert "    } // pssfmt off\n" in out, "the member it sits on was frozen"
        assert TABLE in out, "the member after it was not frozen"

    def test_the_enclosing_construct_is_still_formatted(self):
        """The case that makes the whole design work.

        A ``component`` whose body holds a hatch *overlaps* that hatch. An
        implementation that froze on overlap alone would freeze the component,
        and then -- one level up -- the file. Containment has to be
        distinguished from straddling, and this is the test that says so.
        """
        src = ("component  c  {\n"
               "    // pssfmt off\n"
               "    %s\n"
               "    // pssfmt on\n"
               "}\n" % TABLE)
        out = assert_safe(src)
        assert out.startswith("component c {"), "the enclosing header was frozen"
        assert TABLE in out, "the hatched member was reformatted"

    def test_a_hatch_works_at_the_top_level_too(self):
        """The compilation unit collects members through the same function."""
        src = ("// pssfmt off\n"
               "component  c  { }\n"
               "// pssfmt on\n"
               "component  d  { }\n")
        out = assert_safe(src)
        assert "component  c  { }\n" in out
        assert "component d {}\n" in out

    def test_a_hatch_works_inside_a_constraint(self):
        """Constraints reach ``_collect`` through ``_block`` like everything else."""
        src = ("component c {\n"
               "    action a {\n"
               "        constraint  q  {\n"
               "            // pssfmt off\n"
               "            x   ==   1;\n"
               "            y   ==   2;\n"
               "            // pssfmt on\n"
               "        }\n"
               "    }\n"
               "}\n")
        out = assert_safe(src)
        assert "            x   ==   1;\n            y   ==   2;\n" in out
        assert "constraint q {" in out, "the constraint header was frozen"

    def test_both_comment_syntaxes_work(self):
        """``/* */`` matters because it is the only mid-line spelling."""
        src = ("component c {\n"
               "    /* pssfmt off */\n"
               "    %s\n"
               "    /* pssfmt on */\n"
               "    %s\n"
               "}\n" % (TABLE, TABLE))
        assert assert_safe(src).count(TABLE) == 1


class TestBlankLinesInsideARegion:
    """The reason consecutive hatched members are copied as one block.

    Blank lines *between* members are decided by ``_stack`` and clamped to
    ``max_blank_lines``. Members frozen one at a time would each be byte-exact
    and the spacing between them would still be rewritten -- a hatch that
    reformats the file slightly is exactly the failure it exists to prevent.
    """

    def test_a_blank_run_inside_the_region_survives_the_clamp(self):
        region = ("    struct a { bit[8]  x; }\n"
                  "\n"
                  "\n"
                  "\n"
                  "    struct b { bit[8]  y; }\n")
        src = ("component c {\n"
               "    // pssfmt off\n"
               "%s"
               "    // pssfmt on\n"
               "}\n" % region)
        assert region in assert_safe(src)

    def test_a_blank_run_outside_it_is_still_clamped(self):
        """A hatch freezes what it encloses, not its surroundings."""
        src = ("component c {\n"
               "    struct a { bit[8]  x; }\n"
               "\n"
               "\n"
               "\n"
               "    // pssfmt off\n"
               "    %s\n"
               "    // pssfmt on\n"
               "}\n" % TABLE)
        out = assert_safe(src)
        assert "\n\n\n" not in out, "blank lines before the region were not clamped"
        assert TABLE in out


class TestTheOneThingThatIsNotByteExact:
    """The region's first line is re-indented, and every other line is not.

    The enclosing block writes an indent before every member and a ``Verbatim``
    cannot refuse it -- there is no layout node for "start at an absolute
    column". Stated as a test rather than as a docs sentence so that the day
    somebody adds that node, this fails and the docs get corrected with it.
    """

    def test_the_interior_keeps_its_columns_under_a_different_indent_width(self):
        src = ("component c {\n"
               "    // pssfmt off\n"
               "    struct a {\n"
               "        bit[8]  x;   bit[8]  y;\n"
               "    }\n"
               "    // pssfmt on\n"
               "}\n")
        out = format_source(src, style=replace(DEFAULT_STYLE, indent_width=8))
        assert "        bit[8]  x;   bit[8]  y;\n    }\n" in out, (
            "the region's interior moved with the indent width")
        assert "        struct a {" in out, (
            "the region's first line was not re-anchored -- if a layout node "
            "for absolute columns now exists, this test and docs/style.rst "
            "both want updating")

    def test_tabs_and_trailing_whitespace_inside_a_region_survive(self):
        """Both are things the formatter removes everywhere else.

        Also a regression guard for ``P3-8``: a tab reaching the width
        measurement used to abort the render of the whole file.
        """
        region = ("    struct a { bit[8]  x; }   \n"
                  "\tstruct b { bit[8]  y; }\n")
        src = ("component c {\n"
               "    // pssfmt off\n"
               "%s"
               "    // pssfmt on\n"
               "}\n" % region)
        assert region in assert_safe(src)


# ---------------------------------------------------------------------------
# ignore
# ---------------------------------------------------------------------------


class TestIgnore:

    def test_it_skips_exactly_one_construct(self):
        src = ("component c {\n"
               "    // pssfmt ignore\n"
               "    %s\n"
               "    %s\n"
               "}\n" % (TABLE, TABLE))
        out = assert_safe(src)
        assert out.count(TABLE) == 1, "``ignore`` covered more than one construct"

    def test_it_skips_the_construct_rather_than_the_line(self):
        """A construct is a tree fact, so a multi-line one is covered whole."""
        region = ("    struct a {\n"
                  "        bit[8]  x;   bit[8]  y;\n"
                  "    }\n")
        src = ("component c {\n"
               "    // pssfmt ignore\n"
               "%s"
               "}\n" % region)
        assert region in assert_safe(src)

    def test_it_covers_the_outermost_construct_starting_there(self):
        """Many nested nodes begin at one token; the member is the one meant."""
        src = ("// pssfmt ignore\n"
               "component  c  { struct a { bit[8]  x; } }\n")
        out = assert_safe(src)
        assert "component  c  { struct a { bit[8]  x; } }\n" in out

    def test_an_ignore_with_nothing_after_it_protects_nothing(self):
        src = ("component c {\n"
               "    %s\n"
               "}\n"
               "// pssfmt ignore\n" % TABLE)
        out = assert_safe(src)
        assert TABLE not in out
        assert "// pssfmt ignore\n" in out, "the directive comment was dropped"


# ---------------------------------------------------------------------------
# The malformed cases -- section 5.3's real user
# ---------------------------------------------------------------------------


class TestTheUglyCases:
    """Every one of these resolves to more or less protection, never a crash.

    A directive is hand-written by someone who is already annoyed. The
    question for each shape is not "is it well formed" but "which way should
    it be wrong", and the answers differ.
    """

    def test_off_with_no_on_protects_to_the_end_of_the_file(self):
        """The alternative reformats precisely what someone was protecting."""
        src = ("component c {\n"
               "    // pssfmt off\n"
               "    %s\n"
               "    %s\n"
               "}\n" % (TABLE, TABLE))
        assert assert_safe(src).count(TABLE) == 2

    def test_on_with_no_off_is_a_no_op(self):
        src = ("component c {\n"
               "    // pssfmt on\n"
               "    %s\n"
               "}\n" % TABLE)
        assert TABLE not in assert_safe(src)

    def test_off_inside_off_does_not_nest(self):
        """The first ``on`` closes the region, whatever the depth looks like.

        Counting depth would turn one forgotten ``on`` into a file that is
        silently never formatted again -- the same failure as the unmatched
        case, but arrived at invisibly instead of visibly.
        """
        src = ("component c {\n"
               "    // pssfmt off\n"
               "    %s\n"
               "    // pssfmt off\n"
               "    %s\n"
               "    // pssfmt on\n"
               "    %s\n"
               "}\n" % (TABLE, TABLE, TABLE))
        assert assert_safe(src).count(TABLE) == 2

    def test_off_immediately_followed_by_on_protects_nothing(self):
        src = ("component c {\n"
               "    // pssfmt off\n"
               "    // pssfmt on\n"
               "    %s\n"
               "}\n" % TABLE)
        out = assert_safe(src)
        assert TABLE not in out
        assert "// pssfmt off\n" in out and "// pssfmt on\n" in out

    def test_a_directive_after_the_last_code_token_protects_nothing(self):
        """It has nothing to apply to, which is correct rather than a limit."""
        src = ("component c {\n"
               "    %s\n"
               "}\n"
               "// pssfmt off\n" % TABLE)
        out = assert_safe(src)
        assert TABLE not in out
        assert out.endswith("// pssfmt off\n"), "the directive comment was dropped"

    def test_off_inside_an_ignored_construct_keeps_going_past_it(self):
        """The plan's nastiest named case, and the answer is: both apply.

        ``ignore`` covers the construct; the ``off`` inside it is unmatched and
        so runs to the end of the file. They are a union, not a contest, and
        the member after the ignored one is frozen by the ``off`` rather than
        by the ``ignore``.
        """
        src = ("component c {\n"
               "    // pssfmt ignore\n"
               "    struct a {\n"
               "        // pssfmt off\n"
               "        bit[8]  x;\n"
               "    }\n"
               "    %s\n"
               "}\n" % TABLE)
        assert TABLE in assert_safe(src)

    def test_a_directive_inside_an_expression_freezes_its_member(self):
        """Below member level nothing had to be written.

        ``emit_span`` already declines any span holding a comment between two
        tokens, so a directive there stops the construct being composed
        without the hatch machinery being consulted at all.
        """
        src = ("component c {\n"
               "    struct a {\n"
               "        bit[8]  x = 1  +  /* pssfmt off */  2  /* pssfmt on */  + 3;\n"
               "        bit[8]  y = 4  +  5;\n"
               "    }\n"
               "}\n")
        out = assert_safe(src)
        assert "1  +  /* pssfmt off */  2  /* pssfmt on */  + 3;" in out
        assert "bit[8]  y = 4 + 5;" in out, "the neighbouring member was frozen too"


# ---------------------------------------------------------------------------
# The scan, on its own
# ---------------------------------------------------------------------------


class TestTheScanResolvesPositions:
    """Unit-level, because the position arithmetic is off-by-one country.

    The end-to-end tests above would survive a range that is one token too
    wide in either direction -- a member boundary usually absorbs it. These
    would not.
    """

    def test_a_file_with_no_directives_has_no_hatches(self):
        assert hatches_for("component c { struct a { bit[8] x; } }\n") \
            is NO_HATCHES

    def test_no_hatches_is_falsey_and_protects_nothing(self):
        assert not NO_HATCHES
        assert NO_HATCHES.region_of(0, 99) is None

    def test_the_range_starts_at_the_token_the_off_leads(self):
        src = "component c { }\n// pssfmt off\ncomponent d { }\n"
        hatches = hatches_for(src)
        # Code tokens: component c { }  component d { }  -> positions 0..7.
        assert hatches.ranges == ((4, 7),)

    def test_the_range_ends_at_the_token_before_the_one_on_leads(self):
        src = ("component c { }\n"
               "// pssfmt off\n"
               "component d { }\n"
               "// pssfmt on\n"
               "component e { }\n")
        assert hatches_for(src).ranges == ((4, 7),)

    def test_an_empty_region_is_not_recorded(self):
        src = "// pssfmt off\n// pssfmt on\ncomponent c { }\n"
        assert hatches_for(src) is NO_HATCHES

    def test_an_ignore_is_an_anchor_rather_than_a_range(self):
        src = "component c { }\n// pssfmt ignore\ncomponent d { }\n"
        hatches = hatches_for(src)
        assert hatches.ranges == ()
        assert hatches.ignores == frozenset({4})

    @pytest.mark.parametrize("first,last,expected", [
        (4, 7, 0),      # exactly the range
        (5, 6, 0),      # inside it
        (3, 5, 0),      # straddling the start
        (6, 9, 0),      # straddling the end
        (0, 3, None),   # entirely before it
        (8, 9, None),   # entirely after it
        (0, 9, None),   # containing it -- recurse, do not freeze
    ])
    def test_how_a_span_meets_a_range(self, first, last, expected):
        hatches = Hatches(ranges=((4, 7),))
        assert hatches.region_of(first, last) == expected

    def test_two_spans_in_one_range_share_an_identity(self):
        """What lets consecutive hatched members be copied as a single block."""
        hatches = Hatches(ranges=((4, 7), (12, 15)))
        assert hatches.region_of(4, 5) == hatches.region_of(6, 7)
        assert hatches.region_of(6, 7) != hatches.region_of(12, 13)

    def test_an_ignore_beats_a_range_it_sits_inside(self):
        """Only in identity, not in outcome: both freeze, and both must."""
        hatches = Hatches(ranges=((0, 9),), ignores=frozenset({4}))
        assert hatches.region_of(4, 5) == ("ignore", 4)
        assert hatches.region_of(5, 6) == 0


# ---------------------------------------------------------------------------
# What the rest of the tool has to know about a hatch
# ---------------------------------------------------------------------------


class TestTheStylePropertiesDoNotApplyToAHatch:
    """``verbatim_lines`` has to grow a second source, or the gates go wrong.

    Every claim ``pssfmt`` makes about its own output -- no trailing
    whitespace, no tab indentation, and later ``--check`` and ``--diff`` -- is
    a claim about gaps it chose. Inside a hatch it chose none. The corpus
    cannot catch this the moment a user writes their first directive, because
    the corpus has none, which is the same shape of blind spot that let three
    gates make PSS claims about copied C until ``P3-8``.
    """

    def test_the_lines_of_a_region_are_reported_as_copied(self):
        out = ("component c {\n"          # 1
               "    // pssfmt off\n"      # 2
               "    struct a { }   \n"    # 3  trailing whitespace
               "\tstruct b { }\n"         # 4  tab indentation
               "    // pssfmt on\n"       # 5
               "    struct d { }\n"       # 6
               "}\n")                     # 7
        assert verbatim_lines(out) == {2, 3, 4, 5}

    def test_an_unmatched_region_runs_to_the_last_line(self):
        out = ("component c {\n"
               "    // pssfmt off\n"
               "    struct a { }   \n"
               "}\n")
        assert verbatim_lines(out) == {2, 3, 4}

    def test_a_file_with_no_directives_is_unaffected(self):
        out = "component c {\n    struct a { }\n}\n"
        assert verbatim_lines(out) == set()

    def test_a_hatch_and_a_target_template_are_both_reported(self):
        """The two sources are independent and must not shadow each other."""
        out = ('component c {\n'            # 1
               '    action a {\n'           # 2
               '        exec body C = """\n'  # 3
               '            foo();\n'       # 4
               '        """;\n'             # 5
               '    }\n'                    # 6
               '    // pssfmt off\n'        # 7
               '    struct s { }\n'         # 8
               '    // pssfmt on\n'         # 9
               '}\n')                       # 10
        assert verbatim_lines(out) == {4, 5, 7, 8, 9}

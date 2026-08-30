"""``T-40`` -- enum declarations (``P3-12``).

The last construct in the corpus with broad presence and no rule: **15 across
10 files**, and the first body in the rule set that is a **list**.

Two things make it unlike every body before it
-----------------------------------------------
**Its members are separated rather than terminated.** A ``,`` between two
``enum_item`` nodes is a direct terminal of the *parent*, and ``decls._collect``
had refused any terminal at member level since ``P3-2`` -- correctly, since a
token nobody claims is a token about to go missing. So an enum declined for
ten items and never for a reason anybody chose. ``_collect`` now takes a
*separator* the caller names, and the merge is the one
``_is_trailing_semicolon`` was already doing for ``enum e {A, B};`` -- two
constructs, different grammar reasons, one piece of code.

**It is written on one line more often than not**, which is the opposite of
every other body. 10 of the 15 are ``enum op_mode_e { FAST, SLOW }``.

The rule is not a fit decision, and that is the finding
-------------------------------------------------------
======================================= ===== ==============
shape                                   count written
======================================= ===== ==============
items have ``= value``                    4/4 one per line
bare names, no interior comment           9/9 one line
bare names + interior comment             1/1 one per line
======================================= ===== ==============

The ten inline enums end at columns 33 to 60; the five broken ones join to 69,
75, 92, 95 and 237. **A ``Group`` at ``print_width`` gets 13 of 15 right** --
it would collapse the two shortest broken ones, both of which are hand-built
``=`` tables. "Does an item have a value" gets 15 of 15. An enum of bare names
is a list and an enum of assignments is a table, and that is why authors write
them differently -- not where column 80 falls.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest.importorskip("pssparser")

from pssfmt.rules import REGISTRY, format_source  # noqa: E402
from pssfmt.style import Site, Spacing, Style  # noqa: E402
from pssfmt.verify import format_safely  # noqa: E402


def fmt(src: str, style: Style = Style()) -> str:
    return format_source(src, style=style)


def one(decl: str, style: Style = Style()) -> list:
    """*decl* inside a package, formatted, as the lines between the braces."""
    out = fmt("package p {\n%s\n}\n" % decl, style)
    lines = out.splitlines()
    assert lines[0] == "package p {" and lines[-1] == "}", out
    return lines[1:-1]


class TestItIsReachedAtAll:

    @pytest.mark.parametrize("rule", ["enum_declaration", "enum_item"])
    def test_the_rule_is_registered(self, rule):
        assert rule in REGISTRY

    def test_an_enum_is_no_longer_reproduced_verbatim(self):
        assert one("    enum e {A,B}") == ["    enum e { A, B }"]


class TestTheSeparator:
    """``_collect`` grew a *separator*, and these are the tests that say what
    it must not do: lose the comma, move it, or stop owning the trivia after
    it."""

    def test_the_comma_stays_with_the_item_before_it(self):
        assert one("    enum e : bit[2] {A = 0,B = 1}") == [
            "    enum e : bit[2] {",
            "        A = 0,",
            "        B = 1",
            "    }",
        ]

    def test_no_line_is_a_lone_comma(self):
        out = one("    enum e : bit[8] {A = 0, B = 1, C = 2}")
        assert not any(line.strip() == "," for line in out)

    def test_a_comment_after_a_comma_belongs_to_that_item(self):
        """The comma's *trailing* trivia, which is the item's comment -- the
        item's own trailing run is empty, because the comma sits between."""
        assert one("    enum e {\nA, // first\nB\n}") == [
            "    enum e {",
            "        A, // first",
            "        B",
            "    }",
        ]

    def test_a_comment_above_an_item_moves_with_it(self):
        out = one("    enum e {\n// why\nA,\nB\n}")
        assert out[1:3] == ["        // why", "        A,"]

    def test_the_comma_is_written_against_the_item_s_last_token(self):
        """Which token the separator is composed against, and the only input
        that can tell: an escaped identifier is delimited by whitespace, so
        the lexical floor fires on it and on nothing else here.

        ``\\esc = 1`` starts with an escaped name and ends with a literal.
        Compose the ``,`` against the item's *first* token and the floor sees
        ``\\esc`` and inserts a space; against its *last*, it sees ``1`` and
        does not. Every other item in PSS gives the same answer either way,
        which is why the old hand-written version of this merge carried a
        paragraph explaining that the mutant was unkillable -- it was, for a
        ``;`` after a declaration. It is not, for a ``,`` after an enum item.
        """
        assert one("    enum e : bit[2] { \\esc = 1, B = 2 }") == [
            "    enum e : bit[2] {",
            "        \\esc = 1,",
            "        B = 2",
            "    }",
        ]

    def test_a_trailing_semicolon_still_merges(self):
        """``enum e {A, B};`` -- the ``;`` is a *sibling* of the enum, and it
        is the construct the shared merge was written for in ``P3-2``."""
        assert one("    enum e {A,B} ;") == ["    enum e { A, B };"]


class TestOneLineOrOnePerLine:

    def test_bare_names_stay_on_one_line(self):
        """9 of 9 with no interior comment, and it is the *reason* that
        matters: every other body in this formatter breaks."""
        assert one("    enum op_mode_e {\nFAST,\nSLOW\n}") == [
            "    enum op_mode_e { FAST, SLOW }"]

    def test_values_break_it(self):
        """4 of 4. Not because of width -- see the next test."""
        assert one("    enum e { A = 0, B = 1 }") == [
            "    enum e {", "        A = 0,", "        B = 1", "    }"]

    def test_a_short_valued_enum_still_breaks(self):
        """The case that rules out width. ``enum spi_dir_e : bit[1] { … }``
        joins to column 69 -- inside ``print_width`` -- and the corpus breaks
        it anyway, because it is a table."""
        out = one("    enum spi_dir_e : bit[1] { SPI_XFER_WRITE = 0, "
                  "SPI_XFER_READ = 1 }")
        assert len(out) == 4
        assert all(len(line) < 80 for line in out)

    def test_a_long_bare_enum_still_stays_on_one_line(self):
        """The other side of the same rule, stated so that nobody 'fixes' it
        into a fit decision later. This is the honest cost of choosing values
        over width: a bare-name enum wide enough to pass ``print_width``
        stays on one line, and the corpus contains none to say otherwise."""
        out = one("    enum e {%s}" % ", ".join("NAME_%02d" % i for i in range(12)))
        assert len(out) == 1
        assert len(out[0]) > 80

    def test_an_interior_comment_breaks_it(self):
        """Needs no rule of its own: the inline form is one ``emit_span``
        call, and that has refused a span holding a comment since
        ``P3-2b``."""
        assert one("    enum e { A, /* why */ B }") == [
            "    enum e {", "        A, /* why */", "        B", "    }"]

    def test_an_empty_enum_is_tight(self):
        """``enum e {}``, like every other empty body. The corpus has none, so
        this is the house answer rather than a measured one -- and it is the
        house answer already written down for ``buffer b {}``."""
        assert one("    enum e {   }") == ["    enum e {}"]


class TestTheMeasuredGaps:

    def test_the_braces_are_spaced_inside(self):
        """7 of 10, across 5 files, against 3 in 2 files that are both the
        published 3.1 standard library. ``Site.BRACE_OPEN.after`` and
        ``Site.BRACE_CLOSE.before`` were **placeholders** until this item: all
        733 corpus braces open a body that breaks, so nothing had ever
        followed a ``{`` on the same line."""
        assert one("    enum e {A, B}") == ["    enum e { A, B }"]

    def test_a_comma_is_followed_by_one_space(self):
        assert one("    enum e {A,B}") == ["    enum e { A, B }"]
        assert one("    enum e {A ,  B}") == ["    enum e { A, B }"]

    def test_the_base_type_colon_is_spaced(self):
        """A *fifth* reading of a character ``docs/style.rst`` splits four
        ways, and it takes ``Site.COLON_INHERITANCE`` because that is what it
        is -- the type the enum is based on. 4 of 4 spaced both sides."""
        assert one("    enum e:bit[2] {A = 0}")[0] == "    enum e : bit[2] {"

    def test_the_width_bracket_stays_tight(self):
        """``bit[2]``, and the reason this vocabulary cannot be the shared
        declaration one: that set's colon closure is 'no span of these tokens
        contains a ``[``'."""
        assert one("    enum e : bit [ 2 ] {A = 0}")[0] == \
            "    enum e : bit[2] {"

    def test_a_value_is_spaced_around_its_equals(self):
        assert one("    enum e {A=0}")[1] == "        A = 0,"[:-1]


class TestTheColumnStop:
    """3 of the corpus's 11 valued items are padded, and they are two complete
    tables in two files -- thinner than the assignments' 22 of 93 and the same
    shape, so the same answer: mark the seam, let ``infer`` decide."""

    def test_a_hand_built_value_table_survives(self):
        assert one("    enum e : bit[2] {\n"
                   "        DMA_ADDR_FIXED = 0,\n"
                   "        DMA_ADDR_INCR  = 1\n"
                   "    }") == [
            "    enum e : bit[2] {",
            "        DMA_ADDR_FIXED = 0,",
            "        DMA_ADDR_INCR  = 1",
            "    }",
        ]

    def test_a_ragged_run_is_flushed(self):
        assert one("    enum e : bit[2] {\n"
                   "        A    = 0,\n"
                   "        BBBB   = 1\n"
                   "    }") == [
            "    enum e : bit[2] {", "        A = 0,", "        BBBB = 1",
            "    }",
        ]


class TestTheStyleIsConsulted:

    def test_the_brace_sites_reach_an_inline_enum(self):
        assert one("    enum e {A, B}", Style(spacing_overrides={
            Site.BRACE_OPEN: Spacing(1, 0),
            Site.BRACE_CLOSE: Spacing(0, 0)})) == ["    enum e {A, B}"]

    def test_the_comma_site_reaches_an_enum(self):
        assert one("    enum e {A, B}", Style(spacing_overrides={
            Site.COMMA: Spacing(0, 0)})) == ["    enum e { A,B }"]

    def test_the_type_bracket_site_reaches_the_header(self):
        """That the broken form's header takes its bracket sites **from the
        tree** rather than from the vocabulary.

        Invisible at the default style, because ``TYPE_BRACKET_OPEN`` is tight
        and so is the vocabulary's fallback -- so "asked the tree" and "did
        not ask" produce the same header, which is exactly the silent-wrong-
        answer shape ``pssfmt.rules.exprs`` exists to prevent. Set the site to
        something the fallback cannot produce and the two separate."""
        assert one("    enum e : bit[2] {A = 0}",
                   Style(spacing_overrides={
                       Site.TYPE_BRACKET_OPEN: Spacing(1, 0)}))[0] == \
            "    enum e : bit [2] {"

    def test_indent_width_reaches_a_broken_enum(self):
        assert one("    enum e {A = 0}", Style(indent_width=2)) == [
            "  enum e {", "    A = 0", "  }"]


class TestSafety:

    SOURCES = [
        "package p {\n    enum e {A,B}\n}\n",
        "package p {\n    enum e {}\n}\n",
        "package p {\n    enum e : bit[2] {A = 0, B = 1}\n}\n",
        "package p {\n    enum e {A, /* why */ B}\n}\n",
        "package p {\n    enum e {\nA, // first\nB\n}\n}\n",
        "package p {\n    enum e {A,B} ;\n}\n",
        "package p {\n    enum \\esc {\\a, \\b}\n}\n",
        "package p {\n    // pssfmt off\n    enum e {A,   B}\n"
        "    // pssfmt on\n}\n",
        "package p {\n    enum e : bit[2] {\n        A = 0,\n"
        "        BB  = 1\n    }\n}\n",
    ]

    @pytest.mark.parametrize("src", SOURCES)
    def test_the_verifier_accepts_it(self, src):
        result = format_safely(src, formatter=format_source)
        assert result.ok, result.diagnostic()

    @pytest.mark.parametrize("src", SOURCES)
    def test_it_is_idempotent(self, src):
        once = fmt(src)
        assert fmt(once) == once

    def test_a_hatched_enum_is_frozen(self):
        out = one("    // pssfmt off\n    enum e {A,   B}\n    // pssfmt on")
        assert "    enum e {A,   B}" in out

    def test_an_escaped_identifier_keeps_its_space(self):
        """``P3-10``'s floor, and the enum vocabulary is a new place two
        tokens are written against each other: ``\\esc`` runs to the next
        whitespace, so a tight brace would swallow the first item into the
        type name."""
        out = one("    enum \\esc { \\a , \\b }",
                  Style(spacing_overrides={
                      Site.BRACE_OPEN: Spacing(1, 0),
                      Site.BRACE_CLOSE: Spacing(0, 0),
                      Site.COMMA: Spacing(0, 0)}))
        assert out == ["    enum \\esc { \\a , \\b }"]

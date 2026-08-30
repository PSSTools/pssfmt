"""``T-29`` -- escaped identifiers (``P3-10``, § 4.4).

An escaped identifier is ``'\\' [!-~]+ [^ \\r\\t\\n]*`` in ``PSSLexer.g4``: a
backslash, then **everything up to the next whitespace character**. That one
rule is the whole of this file's difficulty, because it inverts the usual
relationship between spacing and meaning. Everywhere else in PSS, whitespace
is the thing a formatter is free to change; here it is the token's terminator,
and deleting it does not produce ugly PSS, it produces a *different program*
that still parses.

Two facts, both checked below against the real lexer rather than read off the
grammar, because the grammar file is not what runs:

* **Every** non-whitespace character merges. Not a hazard list -- ``\\esc{``,
  ``\\esc;``, ``\\esc)`` and ``\\esc,`` are each one token. This is why
  :func:`~pssfmt.rules.tokens.must_separate` gives ``ESCAPED_ID`` an
  unconditional branch instead of leaving it to the maximal-munch test that
  handles every other pair.
* **Every** whitespace character terminates, newline included. Section 4.4
  cautions against "a newline immediately adjacent without care", and the
  lexer says a newline is exactly as safe as a space. That is worth pinning
  down rather than leaving as folklore: it is what lets the layout engine put
  a ``LINE`` next to an escaped identifier and break it like any other, with
  no rule of its own.

What ``P3-10`` actually found
-----------------------------
Not the rule -- ``P3-2b`` had already made the floor unconditional here, and
the field declarations in ``escaped_identifiers.pss`` have been coming out as
``int \\busa+index ;`` ever since. What it found was that
:func:`~pssfmt.rules.tokens.emit_span` is not the only place two tokens are
written next to each other. Two sites in ``decls.py`` compose a token as
*layout* -- a header meeting its ``{``, and a declaration meeting a stray
``;`` -- and neither consulted the floor:

* ``component /* c */ \\esc {`` under a style with no gap before ``{`` became
  ``\\esc{``, and the file lost its block structure;
* ``\\x ;`` recovered from a syntax error became ``\\x;`` at the **default**
  style.

The ``P1-3`` fail-safe caught both, so neither could have corrupted a file --
the whole file would silently have gone unformatted instead. That is the right
severity to keep in mind while reading these tests: they are about a formatter
that declines correct work, not about one that destroys it.

The generalisation, which is the part worth carrying forward: a floor that
only one of three composition sites consults is not a floor. The way to find
the next one is to enumerate the sites, not to re-read the rule -- so
:class:`TestEveryCompositionSite` does exactly that.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssparser import cst as _cst  # noqa: E402

from pssfmt.rules import format_source  # noqa: E402
from pssfmt.rules.tokens import floor_gap, must_separate  # noqa: E402
from pssfmt.style import DEFAULT_STYLE, Site, Spacing  # noqa: E402
from pssfmt.verify import verify  # noqa: E402

#: A style with every gap the rules can reach configured to zero. Nothing
#: ships this, and that is the point: a lexical floor whose only evidence is
#: that the default spacing happens to be positive is not being tested at all.
TIGHT = DEFAULT_STYLE.evolve(spacing_overrides={
    site: Spacing(0, 0) for site in Site
})


def lex(src: str):
    """The code tokens of *src* as ``(type, text)`` pairs."""
    return [(t.type_name, t.text) for t in _cst.parse(src).tokens
            if t.type_name != "EOF"]


def escaped_ids(src: str):
    """Every escaped identifier in *src*, in order."""
    return [t.text for t in _cst.parse(src).tokens
            if t.type_name == "ESCAPED_ID"]


def assert_safe(src: str, style=DEFAULT_STYLE) -> str:
    """Formats *src* and checks the output still says what the input said.

    The token-equivalence check is the one that matters here. A merged escaped
    identifier is invisible to a check on the *text* -- the bytes are all still
    present, in order -- and shows up only as a token count that dropped.
    """
    out = format_source(src, style=style)
    violations = verify(src, out)
    assert not violations, "verifier rejected the output: %s" % (violations,)
    assert format_source(out, style=style) == out, "not idempotent"
    assert escaped_ids(out) == escaped_ids(src), "an escaped identifier changed"
    return out


# ---------------------------------------------------------------------------
# What the lexer actually does
# ---------------------------------------------------------------------------

class TestTheLexicalFacts:
    """The two facts every rule below rests on, taken from the lexer itself.

    Written as a sweep rather than as examples on purpose. The failure mode
    these guard against is somebody adding a character to a hazard list and
    believing the list is now complete, and a list is exactly what the answer
    is not: it is *all* of one class and *none* of the other.
    """

    @pytest.mark.parametrize("follower", [
        "{", "}", "(", ")", "[", "]", ";", ",", ".", ":", "=", "+", "-", "*",
        "/", "<", ">", "&", "|", "!", "?", "@", "#", "%", "^", "~", "$",
        "x", "0", "_", "\\y", "\"s\"",
    ])
    def test_no_gap_swallows_whatever_follows(self, follower):
        """Written tight, the identifier eats it -- whatever it is.

        And eats it *whole*: the run does not stop at the end of the token
        that was meant to follow, it stops at whitespace. So a merge does not
        cost one token, it costs every token up to the next space.
        """
        assert lex("\\esc" + follower) == [("ESCAPED_ID", "\\esc" + follower)]

    @pytest.mark.parametrize("gap", [
        " ", "  ", "\t", "\n", "\r\n", "\n    ", " \t ", "\n\n",
    ])
    @pytest.mark.parametrize("follower", ["{", ";", "x", ")", "\\y"])
    def test_any_whitespace_terminates(self, gap, follower):
        """Including a newline. Section 4.4's caution is stricter than the
        lexer, so the engine needs no special break rule."""
        assert lex("\\esc" + gap + follower)[0] == ("ESCAPED_ID", "\\esc")

    def test_the_backslash_is_required(self):
        """Sanity: these tests would pass vacuously if ``\\esc`` were an
        ordinary identifier and the merges were ordinary word merges."""
        assert lex("esc")[0][0] == "ID"


# ---------------------------------------------------------------------------
# The floor
# ---------------------------------------------------------------------------

class TestTheFloor:
    """:func:`must_separate` and :func:`floor_gap` over escaped identifiers."""

    class _Tok:
        def __init__(self, text, type_name):
            self.text, self.type_name = text, type_name

    def tok(self, text, type_name="ESCAPED_ID"):
        return self._Tok(text, type_name)

    def test_separated_on_the_right(self):
        """The lexically necessary side: ``\\esc{`` is one token."""
        assert must_separate(self.tok("\\esc"), self.tok("{", "TOK_LCBRACE"))

    def test_separated_on_the_left(self):
        """Not lexically necessary -- ``component\\esc`` does lex as two --
        and a floor anyway. See ``tokens.py``: this is the side that survived
        a token-equivalence check and had to be found by reading output."""
        assert must_separate(self.tok("component", "TOK_COMPONENT"),
                             self.tok("\\esc"))

    def test_two_escaped_identifiers(self):
        """Where the left side *is* lexically necessary."""
        assert must_separate(self.tok("\\a"), self.tok("\\b"))

    def test_floor_raises_zero_to_one(self):
        assert floor_gap(0, self.tok("\\esc"),
                         self.tok("{", "TOK_LCBRACE")) == 1

    def test_floor_never_lowers(self):
        """A style asking for three columns keeps them: this is a floor, not
        a normaliser. Section 4.4 says "exactly one space" and means "at
        least one" -- the identifier ends at the first whitespace character,
        so the alignment pass may pad past one without changing the token."""
        assert floor_gap(3, self.tok("\\esc"),
                         self.tok("{", "TOK_LCBRACE")) == 3

    def test_floor_leaves_a_harmless_pair_alone(self):
        assert floor_gap(0, self.tok("a", "ID"),
                         self.tok(";", "TOK_SEMI")) == 0


# ---------------------------------------------------------------------------
# Every place two tokens are written next to each other
# ---------------------------------------------------------------------------

class TestEveryCompositionSite:
    """One test per site that writes a token against another token's text.

    This class is the finding, not the regressions below it. ``emit_span`` had
    the floor from ``P3-2b`` and the other two sites did not, and no amount of
    re-reading section 4.4 would have said so -- only enumerating the places a
    token gets composed. If a fourth site appears, it belongs here on the day
    it is written, whether or not anybody has an escaped-identifier bug.

    A fourth appeared, in ``P3-11b``, and it did arrive with its test -- so
    the instruction above has now been followed once rather than merely
    written down. ``P3-10a`` still stands: this is a hand-written list of
    four, which is the shape that goes stale the *next* time.
    """

    def test_emit_span(self):
        """The main path: a span of code tokens with computed gaps."""
        out = assert_safe("package p {\n    struct s {\n"
                          "        int \\x ;\n    }\n}\n", style=TIGHT)
        assert "\\x ;" in out, out

    def test_header_meets_its_brace(self):
        """``decls._header``'s fallback, reached when ``emit_span`` declines.

        The comment is what makes it decline -- a span holding an interior
        comment has been ``emit_span``'s business to refuse since ``P3-2b``,
        which is exactly why the floor inside ``emit_span`` never ran here.
        """
        out = assert_safe("package p {\n    component /* c */ \\esc {\n"
                          "        int x;\n    }\n}\n", style=TIGHT)
        assert "\\esc {" in out, out

    def test_a_match_arm_meets_its_statement(self):
        """The fourth site, added by ``P3-11b`` on the day it was written.

        A match arm's ``:`` is followed by a statement built by *its own
        rule*, so the two are composed as layouts rather than emitted as one
        span -- which puts this outside ``emit_span`` and therefore outside
        its floor. Deliberately outside: building the statement separately is
        what keeps ``procedural_return_stmt``'s builder reached for the 195
        corpus returns that live in an arm.

        Invisible at the default style, because ``Site.COLON_CASE_ITEM``
        already spaces it. Under ``TIGHT`` the computed gap is zero and only
        the floor stands between ``\\esc`` and the token in front of it.
        """
        out = assert_safe("component c {\n    function void f() {\n"
                          "        match (n) {\n"
                          "            [0]: \\esc = 1;\n"
                          "        }\n    }\n}\n", style=TIGHT)
        assert ": \\esc" in out, out

    def test_declaration_meets_a_stray_semicolon(self):
        """``decls._collect``'s trailing-``;`` merge, at the *default* style.

        Unlike the other two this needs no unusual configuration, because the
        merge writes the ``;`` tight by intent and never consults the style at
        all. It needs a syntax error instead -- which the merge's own
        docstring names as one of the two things it exists for.
        """
        out = assert_safe("package p {\n    struct s {\n"
                          "        \\x ;\n    }\n}\n")
        assert "\\x ;" in out, out


# ---------------------------------------------------------------------------
# The identifier in each position the rules can put it
# ---------------------------------------------------------------------------

class TestInEveryPosition:
    """A sweep, under ``TIGHT``, so a gap that only the default style provides
    cannot pass for a floor."""

    @pytest.mark.parametrize("src", [
        "package \\p {\n    struct s {\n        int x;\n    }\n}\n",
        "package p {\n    component \\c {\n        int x;\n    }\n}\n",
        "package p {\n    struct \\s {\n        int x;\n    }\n}\n",
        "package p {\n    struct s {\n        int \\x;\n    }\n}\n",
        "package p {\n    struct s {\n        \\t x;\n    }\n}\n",
        "package p {\n    struct s {\n        int x = \\y;\n    }\n}\n",
        "package p {\n    struct s {\n        int x = \\a + \\b;\n    }\n}\n",
        "package p {\n    struct s {\n        constraint \\c {\n"
        "            \\x > 0;\n        }\n    }\n}\n",
        "package p {\n    component c {\n        action \\a {\n"
        "            activity {\n                \\s1;\n"
        "            }\n        }\n    }\n}\n",
        "package p {\n    import \\pkg::*;\n}\n",
        "package p {\n    typedef int \\t;\n}\n",
        "package p {\n    struct s {\n        \\a \\b;\n    }\n}\n",
    ], ids=lambda s: s.split("\n")[1].strip()[:38])
    def test_position(self, src):
        assert_safe(src, style=TIGHT)


class TestTheOnesThatLookLikeOtherSyntax:
    """An escaped identifier may *contain* the characters of other tokens.

    This is the case that makes the construct worth its own test file rather
    than a line in ``test_tokens.py``. ``\\{a,b}`` holds a brace and two
    commas; ``\\a*(b+c)`` holds an operator and a paren pair. Nothing may
    treat those as syntax, and nothing may treat the identifier as a place a
    line could break.
    """

    @pytest.mark.parametrize("name", [
        "\\busa+index", "\\-clock", "\\***error-condition***", "\\net1/\\net2",
        "\\{a,b}", "\\a*(b+c)", "\\cpu3", "\\a;b", "\\//not-a-comment",
        "\\/*not-a-comment*/", "\\\"not-a-string\"",
    ])
    def test_survives_as_one_token(self, name):
        src = "package p {\n    struct s {\n        int %s ;\n    }\n}\n" % name
        assert escaped_ids(src) == [name], "the sample is not what it looks like"
        assert_safe(src, style=TIGHT)


# ---------------------------------------------------------------------------
# Line breaking
# ---------------------------------------------------------------------------

class TestBreaking:
    """A break next to an escaped identifier is safe, and must stay possible.

    Both halves matter. Safe, because a newline terminates the identifier just
    as a space does -- so no rule has to keep breaks away. Possible, because
    the cheap way to be safe would have been to forbid them, and that would
    make a long initializer containing an escaped identifier unbreakable and
    silently over-width.
    """

    def test_a_long_initializer_still_breaks(self):
        name = "\\a-very-long-escaped-identifier-name"
        src = ("package p {\n    struct s {\n        int x = %s + %s + %s;\n"
               "    }\n}\n" % (name, name, name))
        out = assert_safe(src)
        assert "\n" in out.split("int x =")[1].split(";")[0], (
            "expected the initializer to break:\n" + out)

    def test_a_broken_line_never_splits_an_identifier(self):
        """Every line of output either contains a whole escaped identifier or
        none of it. Checked by re-lexing rather than by looking for
        backslashes, because a backslash appears inside the name too."""
        name = "\\a-very-long-escaped-identifier-name"
        src = ("package p {\n    struct s {\n        int x = %s + %s + %s;\n"
               "    }\n}\n" % (name, name, name))
        out = format_source(src)
        assert escaped_ids(out) == escaped_ids(src)
        for line in out.splitlines():
            assert name.rstrip("e") not in line or name in line, line


# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------

class TestTheCorpusSample:
    """``escaped_identifiers.pss`` holds 11 of the corpus's 12 instances.

    ``test_tier1_corpus.py`` already checks the multiset survives formatting.
    What is checked here is the thing that check cannot see: that the space
    before each ``;`` is the *floor* doing its job and not the author's own
    text being reproduced because a rule declined the member.
    """

    def test_the_fields_are_formatted_and_still_spaced(self):
        src = ("package p {\n    struct s {\n"
               "        int \\busa+index    ;\n"
               "        int \\-clock ;\n"
               "    }\n}\n")
        out = assert_safe(src)
        # The author's four columns were rewritten, so the member was
        # formatted rather than copied -- and the survivor is one space.
        assert "int \\busa+index ;" in out, out
        assert "int \\-clock ;" in out, out

"""``T-19`` -- Tier 1 declarations and their bodies (``P3-2``).

The first rules that actually reformat, so the first tests with a hand-written
expected output. ``PLAN.md`` section 7.1 puts golden tests last and calls them
expensive for good reason, so these stay small and each one pins a decision
rather than a rendering: brace placement, where members go, what happens to
blank lines, and -- taking most of the room -- what happens to comments.

Comments get the space because they are where formatters lose data, and
because every bug found while writing this module was a comment or a blank
line rather than a brace.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.rules import decls, format_source  # noqa: E402
from pssfmt.verify import verify  # noqa: E402
from pssfmt.style import Construct, SemicolonMode, Style  # noqa: E402

pytestmark = pytest.mark.unit


def fmt(src: str, style: Style = None) -> str:
    return format_source(src, style=style) if style else format_source(src)


def roundtrips(src: str, style: Style = None) -> None:
    """Formatting is stable and reproduces *src* exactly."""
    once = fmt(src, style)
    assert once == src
    assert fmt(once, style) == once


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


class TestBraces:
    def test_a_body_breaks_and_members_are_indented(self):
        assert fmt("package p { struct s {} }\n") == (
            "package p {\n"
            "    struct s {}\n"
            "}\n"
        )

    def test_an_empty_body_stays_flat(self):
        """``{ }`` and ``{\\n}`` both become ``{}``.

        Two lines to say a construct is empty reads worse than none, and the
        corpus contains both spellings, so leaving them alone would mean the
        formatter had no opinion where it clearly should.
        """
        for spelling in ("component c { }\n", "component c {\n}\n", "component c {}\n"):
            assert fmt(spelling) == "component c {}\n"

    def test_one_space_before_the_brace(self):
        """``Site.BRACE_OPEN``.

        The double space after ``component`` goes too, which it did not
        before ``P3-2b``: the header is now written out token by token rather
        than reproduced. See ``T-21`` for that half.
        """
        assert fmt("component  c{}\n") == "component c {}\n"

    def test_the_closing_brace_returns_to_the_construct_column(self):
        assert fmt("package p {\n    component c {\n        action a {}\n}\n}\n") == (
            "package p {\n"
            "    component c {\n"
            "        action a {}\n"
            "    }\n"
            "}\n"
        )

    @pytest.mark.parametrize(
        "kind", ["struct", "buffer", "stream", "state", "resource"])
    def test_all_five_struct_kinds(self, kind: str):
        assert fmt("package p { %s s { } }\n" % kind) == (
            "package p {\n"
            "    %s s {}\n"
            "}\n" % kind
        )

    def test_a_declaration_drops_its_optional_semicolon(self):
        """``struct s {};`` -- the ``;`` is an empty ``package_body_item``.

        PSS does not require it and the default style does not write it. See
        ``tests/test_semicolons.py`` for the rest of this rule, including the
        semicolons that are *not* optional and stay.
        """
        assert fmt("package p {\n    struct s {};\n}\n") == (
            "package p {\n"
            "    struct s {}\n"
            "}\n"
        )

    def test_preserve_keeps_it_on_the_line_it_terminates(self):
        """Treated as a member of its own it would land on its own line."""
        roundtrips("package p {\n    struct s {};\n}\n",
                   Style(optional_semicolon=SemicolonMode.PRESERVE))


class TestIndentationComesFromTheStyle:
    def test_indent_width_is_honoured(self):
        out = fmt("package p { struct s { int x; } }\n", Style(indent_width=2))
        assert out == (
            "package p {\n"
            "  struct s {\n"
            "    int x;\n"
            "  }\n"
            "}\n"
        )

    def test_a_per_construct_override_reaches_the_rule(self):
        """The seam, end to end -- not just that ``Style`` stores the value.

        This is the assertion ``P3-0`` exists for: a construct's indentation
        can be changed without touching a rule module.
        """
        style = Style(indent_overrides={Construct.STRUCT_BODY: 8})
        out = fmt("package p { struct s { int x; } }\n", style)
        assert "\n            int x;\n" in out, out
        assert "\n    struct s {\n" in out, out

    def test_members_under_indented_by_the_author_are_re_anchored(self):
        """A member at column 0 inside a body moves to the body's indent.

        This is the re-anchoring path: the member has no rule of its own, so
        it is reproduced -- but reproduced *relative* to where the layout puts
        it, not where the author left it.
        """
        assert fmt("component c {\nint x;\n}\n") == "component c {\n    int x;\n}\n"

    def test_relative_indentation_inside_a_moved_member_survives(self):
        """Only the anchor moves; the shape inside the block does not."""
        src = "struct s {\nconstraint c {\n    x < 1;\n}\n}\n"
        assert fmt(src) == (
            "struct s {\n"
            "    constraint c {\n"
            "        x < 1;\n"
            "    }\n"
            "}\n"
        )


class TestBlankLines:
    def test_a_blank_line_between_members_is_kept(self):
        roundtrips("package p {\n    struct a {}\n\n    struct b {}\n}\n")

    def test_two_blank_lines_are_clamped_to_one(self):
        assert fmt("package p {\n    struct a {}\n\n\n\n    struct b {}\n}\n") == (
            "package p {\n    struct a {}\n\n    struct b {}\n}\n")

    def test_the_clamp_is_the_style_value(self):
        assert fmt("package p {\n    struct a {}\n\n    struct b {}\n}\n",
                   Style(max_blank_lines=0)) == (
            "package p {\n    struct a {}\n    struct b {}\n}\n")

    def test_a_blank_line_before_the_closing_brace_is_kept(self):
        roundtrips("package p {\n    struct a {}\n\n}\n")

    def test_no_blank_line_is_invented_after_the_opening_brace(self):
        roundtrips("package p {\n    struct a {}\n}\n")


class TestNothingIsReordered:
    def test_members_keep_their_order(self):
        """A commitment, not a preference -- ``docs/style.rst``.

        Order in PSS can carry meaning, and a formatter that sorts is a
        formatter that changes behaviour.
        """
        src = "package p {\n    struct z {}\n    struct a {}\n    struct m {}\n}\n"
        assert [line.strip() for line in fmt(src).splitlines()[1:-1]] == [
            "struct z {}", "struct a {}", "struct m {}"]


# ---------------------------------------------------------------------------
# Comments -- where the data loss lives
# ---------------------------------------------------------------------------


class TestComments:
    def test_a_comment_above_a_member_stays_above_it(self):
        roundtrips("package p {\n    // why\n    struct s {}\n}\n")

    def test_a_blank_line_between_comment_and_member_survives(self):
        """The one a naive implementation eats.

        A ``//`` comment token carries its own trailing newline, so counting
        newlines in the whitespace that follows cannot tell "comment, then
        code" from "comment, blank line, then code".
        """
        roundtrips("package p {\n    // why\n\n    struct s {}\n}\n")

    def test_a_comment_above_a_member_moves_with_it(self):
        assert fmt("package p {\n// why\nstruct s {}\n}\n") == (
            "package p {\n    // why\n    struct s {}\n}\n")

    def test_a_trailing_comment_stays_on_its_line(self):
        roundtrips("package p {\n    struct s {}  // why\n}\n")

    def test_a_trailing_comment_after_a_nested_declaration_survives(self):
        """The one nothing else would catch.

        A rule builder emits its construct and stops. Nothing inside
        ``struct_declaration`` knows about the comment hanging off its closing
        brace, so if the enclosing body did not pick it up it would simply be
        gone -- and the output would still be valid PSS.
        """
        roundtrips("package p {\n    struct s {\n        int x;\n    }  // end s\n}\n")

    def test_a_comment_alone_before_the_closing_brace_survives(self):
        """Section 3.1 rule 4: dangling, owned by nobody, easy to drop."""
        roundtrips("package p {\n    struct s {}\n\n    // TODO more\n}\n")

    def test_a_comment_in_an_otherwise_empty_body(self):
        roundtrips("package p {\n    // nothing here yet\n}\n")

    def test_a_block_comment_interior_is_never_re_anchored(self):
        """``docs/style.rst``: comment interiors are preserved exactly.

        A block comment can hold a diagram or a table, and shifting its
        continuation lines breaks it as thoroughly as rewrapping would. So the
        block is emitted where the author had it rather than moved.
        """
        src = ("package p {\n"
               "    /* +----+\n"
               "       | ab |\n"
               "       +----+ */\n"
               "    struct s {}\n"
               "}\n")
        assert "       | ab |\n" in fmt(src)

    def test_a_file_header_comment_stays_at_the_top(self):
        roundtrips("// SPDX-License-Identifier: Apache-2.0\n\npackage p {\n}\n"
                   .replace("package p {\n}\n", "package p {}\n"))


class TestPayloadsAreNeverMoved:
    def test_a_target_template_body_is_untouched(self):
        """Re-indenting an ``exec`` template edits the generated string.

        Section 4.7.1.2 -- a semantic change, not a cosmetic one. The member
        has no rule, so it would otherwise go down the re-anchoring path.
        """
        src = ('component c {\n'
               '    exec body C = """\n'
               'do_it();\n'
               '""";\n'
               '}\n')
        assert '\ndo_it();\n' in fmt(src)


# ---------------------------------------------------------------------------
# Bailing out
# ---------------------------------------------------------------------------


class TestItDeclinesRatherThanGuesses:
    @pytest.mark.parametrize("src", [
        "component c {\n    int x = 1;\n    \\\n}\n",
        "package p {\n    string s = \"never closed;\n    int x = 1;\n}\n",
    ], ids=["lone backslash", "unclosed string"])
    def test_a_lexical_error_in_a_body_is_reproduced_not_deleted(self, src: str):
        """A token no grammar rule claims lands in the trivia a body discards.

        Replacing that run with a computed indent deletes a byte of the user's
        file. The ``P1-3`` fail-safe would catch it -- and hand back the whole
        file unformatted, where declining here costs one construct.
        """
        out = fmt(src)
        for fragment in ("\\", '"never closed'):
            if fragment in src:
                assert fragment in out, out

    def test_output_is_stable(self):
        """Idempotence on the awkward cases, which is where it breaks."""
        for src in ("component c {\n    int x = 1;\n    \\\n}\n",
                    "package p {\n    struct s {};\n}\n",
                    "package p {\n\n\n    struct s {}\n\n\n}\n"):
            once = fmt(src)
            assert fmt(once) == once, once


# ---------------------------------------------------------------------------
# The tiling invariant
# ---------------------------------------------------------------------------


class TestMembersMustTileTheBody:
    """``_tiles`` -- the guard against a token falling between two members.

    Tested as a function. It fires on real input but no input found so far
    makes it change the *output*, because a stray terminal between the braces
    is refused earlier; see its docstring. Testing it through behaviour would
    therefore be testing nothing, and would look like testing something.
    """

    @pytest.mark.parametrize("spans,first,last,expected", [
        ([(0, 2), (3, 5)], 0, 5, True),
        ([(0, 5)], 0, 5, True),
        ([], 3, 2, True),                 # an empty body covers an empty range
        ([], 0, 5, False),                # ... but not a non-empty one
        ([(0, 2), (4, 5)], 0, 5, False),  # a gap between members
        ([(1, 5)], 0, 5, False),          # a token before the first member
        ([(0, 4)], 0, 5, False),          # a token after the last
        ([(0, 3), (2, 5)], 0, 5, False),  # overlapping members
    ], ids=["contiguous", "single", "empty-range", "empty-but-tokens",
            "gap", "short-at-start", "short-at-end", "overlap"])
    def test_tiles(self, spans, first, last, expected):
        assert decls._tiles(spans, first, last) is expected


class TestNoTokenIsEverLost:
    """Token equivalence on the shapes that send the parser into recovery.

    These are the inputs that reach the bail-outs. Asserting token equivalence
    rather than an expected rendering keeps the test meaningful whichever path
    the rule takes -- the point is that nothing disappears, not which branch
    declined to format it.
    """

    @pytest.mark.parametrize("src", [
        "package p {\n    struct s {}\n    ;\n}\n",
        "package p {\n    @foo struct s {}\n}\n",
        "component c {\n    int x = ;\n}\n",
        "package p {\n    struct }\n}\n",
        "package p {\n    struct s { int } }\n}\n",
        "component c {\n    action a {} action b {}\n}\n",
    ], ids=["stray semicolon", "annotation", "incomplete member",
            "keyword with no name", "unbalanced inner", "two on one line"])
    def test_the_tokens_survive(self, src: str):
        violations = list(verify(src, fmt(src)))
        assert not violations, violations

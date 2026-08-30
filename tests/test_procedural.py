"""``T-36`` -- function bodies (``P3-11``).

Every test here works from **deliberately mis-indented input**, and that is a
statement about the corpus rather than a stylistic choice. Registering this
rule changes 1 of the 92 corpus files, because the corpus is hand-written in
the house style and its function bodies already look like what the rule
produces. So the corpus cannot show that the rule does anything -- it can only
show that the rule does no *harm*, which ``tests/corpus/`` already covers.

What is left to test is the part the corpus is silent on: that a function
nobody has formatted comes out formatted. Hence inputs whose braces, indents
and blank runs are all wrong, and assertions on the whole output rather than
on a substring -- a substring check passes on a file that is right in one
place and wrong everywhere else.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest.importorskip("pssparser")

from pssfmt.rules import REGISTRY, format_source  # noqa: E402
from pssfmt.style import Style  # noqa: E402
from pssfmt.verify import format_safely  # noqa: E402


def fmt(src: str, style: Style = Style()) -> str:
    return format_source(src, style=style)


class TestItIsReachedAtAll:

    def test_the_rule_is_registered(self):
        """`P3-6`'s lesson, asserted rather than assumed: a rule that is not
        registered formats nothing and fails no test."""
        assert "procedural_function" in REGISTRY

    def test_a_function_body_is_no_longer_reproduced_verbatim(self):
        out = fmt("component c {\nfunction void f() {\nint x;\n}\n}\n")
        assert out == ("component c {\n"
                       "    function void f() {\n"
                       "        int x;\n"
                       "    }\n"
                       "}\n")


class TestTheBlock:
    """Brace placement, indentation and the blank-line policy -- the three
    things a block owns, checked one at a time so a failure names one."""

    def test_the_brace_moves_onto_the_header_line(self):
        out = fmt("component c {\n    function void f()\n    {\n"
                  "        int x;\n    }\n}\n")
        assert "function void f() {" in out
        assert "\n    {\n" not in out

    def test_the_body_is_indented_one_level(self):
        out = fmt("component c {\nfunction void f() {\nint x;\nint y;\n}\n}\n")
        assert out.splitlines()[2:4] == ["        int x;", "        int y;"]

    def test_indent_width_reaches_it(self):
        out = fmt("component c {\nfunction void f() {\nint x;\n}\n}\n",
                  Style(indent_width=2))
        assert out.splitlines()[2] == "    int x;"

    def test_a_blank_run_is_collapsed_to_the_limit(self):
        out = fmt("component c {\n    function void f() {\n        int x;\n"
                  "\n\n\n\n        int y;\n    }\n}\n")
        assert "\n\n\n" not in out
        assert "        int x;\n\n        int y;" in out

    def test_blank_lines_between_statements_survive(self):
        """The other direction. A blank line is the author grouping things,
        and a formatter that removes them all is one people stop running."""
        out = fmt("component c {\n    function void f() {\n        int x;\n"
                  "\n        int y;\n    }\n}\n")
        assert "        int x;\n\n        int y;" in out

    def test_an_empty_body_closes_immediately(self):
        """``{}``, not ``{\\n}``. The same answer every declaration body
        gives -- there is no member to put on a line."""
        out = fmt("component c {\n    function void f() {   }\n}\n")
        assert out == "component c {\n    function void f() {}\n}\n"


class TestOneLineBodies:

    def test_a_one_line_body_is_opened(self):
        """117 of the corpus's 118 functions are written open, so the rule
        opens the 118th rather than collapsing the 117. Identical decision to
        ``P3-5``'s for constraint blocks, on identical evidence -- and the one
        corpus file `P3-11` moves is exactly this."""
        out = fmt("component c {\n"
                  "    function bit[32] g(int ch) { return ch * 4; }\n}\n")
        assert out == ("component c {\n"
                       "    function bit[32] g(int ch) {\n"
                       "        return ch * 4;\n"
                       "    }\n"
                       "}\n")


class TestComments:
    """Comments are where formatters lose data, so a new body layout has to
    be asked about them explicitly rather than assumed to inherit them."""

    def test_a_comment_above_a_statement_moves_with_it(self):
        out = fmt("component c {\nfunction void f() {\n"
                  "// why\nint x;\n}\n}\n")
        assert "        // why\n        int x;" in out

    def test_a_trailing_comment_stays_on_its_line(self):
        out = fmt("component c {\nfunction void f() {\n"
                  "int x; // why\n}\n}\n")
        assert "        int x; // why" in out

    def test_a_comment_alone_in_a_body_survives(self):
        """The one no member owns."""
        out = fmt("component c {\nfunction void f() {\n// nothing yet\n}\n}\n")
        assert "// nothing yet" in out


class TestWhatIsLeftAlone:
    """What survives of the boundary this class was written to pin.

    Both of ``P3-11``'s deferrals have since landed and both tests here
    failed, which is what they were for. The header moved to
    ``tests/test_prototypes.py`` (``T-37``) and statement spacing to
    ``tests/test_statements.py`` (``T-38``), each turned round: what was
    pinned as reproduced is now pinned as normalised.

    What is left is the one thing ``P3-11`` claimed that is still true and
    still worth a test -- that laying out a body does not flatten a table
    inside it.
    """

    def test_a_hand_built_table_inside_a_body_survives(self):
        """`infer` reaches into a function body now that the body is a block.
        A table the author built is preserved; that is the setting's whole
        purpose and it would be easy to lose here without noticing."""
        out = fmt("component c {\n    function void f() {\n"
                  "        bit[32]  expected;\n"
                  "        bit[32]  actual;\n    }\n}\n")
        assert "        bit[32]  expected;\n        bit[32]  actual;" in out


class TestTheTrailingSemicolonMerge:
    """Existing machinery at a new call site, which is the thing this
    repository has twice found missing from exactly one place.

    ``procedural_data_declaration`` does not own its terminator: the grammar
    makes the ``;`` a *sibling* ``procedural_stmt``, so a body of three
    declarations is six members, three of which are a bare semicolon. Laid out
    as members in their own right they land on their own lines -- which is how
    ``std_pkg.pss`` once came back with four bare semicolons in it.

    ``decls._is_trailing_semicolon`` already merges them; it was written for
    ``enum e {A, B};`` in ``P3-2`` and this is a second construct with the same
    shape, reached for the first time here. 37 of the corpus's 300
    ``procedural_stmt`` nodes across 17 files are one of these, so a
    regression would be loud -- but only in files nobody was formatting until
    now, which is why it is pinned rather than left to the corpus.
    """

    def test_a_declaration_keeps_its_semicolon_on_its_line(self):
        out = fmt("component c {\n    function void f() {\n"
                  "        int x;\n        int y;\n    }\n}\n")
        assert out.splitlines()[2:4] == ["        int x;", "        int y;"]

    def test_no_line_is_a_lone_semicolon(self):
        out = fmt("component c {\n    function void f() {\n"
                  "        int a;\n        int b;\n        int c;\n"
                  "    }\n}\n")
        assert not any(line.strip() == ";" for line in out.splitlines())


class TestSafety:

    SOURCES = [
        "component c {\nfunction void f() {\nint x;\n}\n}\n",
        "component c {\n    function bit[32] g(int ch) { return ch * 4; }\n}\n",
        "component c {\n    function void f() {   }\n}\n",
        "component c {\n    function void f() {\n        // only a comment\n"
        "    }\n}\n",
        "package p {\n    pure component c {}\n}\n",
    ]

    @pytest.mark.parametrize("src", SOURCES)
    def test_the_verifier_accepts_it(self, src):
        result = format_safely(src, formatter=format_source)
        assert result.ok, result.diagnostic()

    @pytest.mark.parametrize("src", SOURCES)
    def test_it_is_idempotent(self, src):
        once = fmt(src)
        assert fmt(once) == once

    def test_a_function_with_no_braces_is_reproduced(self):
        """A prototype-only declaration reaches no block. ``_block`` falls
        back to reproducing the whole node when it finds no braces, so this is
        safe by construction rather than by a check here -- which is worth a
        test precisely because nothing in this module does it."""
        src = "component c {\n    function void f();\n}\n"
        result = format_safely(src, formatter=format_source)
        assert result.ok
        assert "function void f();" in result.text

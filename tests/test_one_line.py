"""A branch the author wrote on one line stays on one line.

``docs/style.rst``, "A branch written on one line": ``if (x) { y = 0; }``
-- header, ``{``, one statement and ``}`` on a single source line -- is kept,
in procedural code, activities and constraints, and so are ``foreach``/``repeat``/``while``. The
other direction is unchanged: a body the author broke is never joined. An
``if``/``else`` chain is kept whole or opened whole, and opens out when any
line of it would pass ``print_width``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.rules import format_source  # noqa: E402
from pssfmt.style import Style  # noqa: E402
from pssfmt.verify import format_safely  # noqa: E402


def fmt(src: str, style: Style = Style()) -> str:
    return format_source(src, style=style)


def in_function(*lines: str) -> str:
    return ("component c {\n    function void f(int n) {\n"
            + "".join("        %s\n" % line for line in lines)
            + "    }\n}\n")


def in_activity(*lines: str) -> str:
    return ("component c {\n    action a {\n        rand int x;\n"
            "        activity {\n"
            + "".join("            %s\n" % line for line in lines)
            + "        }\n    }\n}\n")


def in_constraint(*lines: str) -> str:
    return ("component c {\n    action a {\n        rand int x;\n"
            "        constraint c1 {\n"
            + "".join("            %s\n" % line for line in lines)
            + "        }\n    }\n}\n")


class TestProcedural:

    @pytest.mark.parametrize("src,expected", [
        ("if(n>0){n=0;}", "if (n > 0) { n = 0; }"),
        ("if (n > 0) { n = 0; } else { n = 1; }",
         "if (n > 0) { n = 0; } else { n = 1; }"),
        ("foreach(i:arr){n+=i;}", "foreach (i : arr) { n += i; }"),
        ("repeat (4) { n = n + 1; }", "repeat (4) { n = n + 1; }"),
        ("while(n<4){n+=1;}", "while (n < 4) { n += 1; }"),
    ], ids=["if", "if-else", "foreach", "repeat", "while"])
    def test_kept_and_normalised(self, src, expected):
        assert fmt(in_function(src)) == in_function(expected)

    def test_else_stays_on_its_own_line(self):
        src = in_function("if (n == 1) { n = 0; }",
                          "else if (n == 2) { n = 3; }",
                          "else { n = 9; }")
        assert fmt(src) == src

    def test_an_aligned_brace_column_is_kept(self):
        src = in_function("if(n==1)          {n = 0;}",
                          "else if (n == 22) { n = 3; }",
                          "else              { n = 9; }")
        assert fmt(src) == in_function("if (n == 1)       { n = 0; }",
                                       "else if (n == 22) { n = 3; }",
                                       "else              { n = 9; }")

    def test_an_unaligned_brace_column_is_not_invented(self):
        src = in_function("if (n == 1)  { n = 0; }",
                          "else if (n == 22) { n = 3; }")
        assert fmt(src) == in_function("if (n == 1) { n = 0; }",
                                       "else if (n == 22) { n = 3; }")

    def test_an_assignment_column_is_not_carried_inline(self):
        assert fmt(in_function("if (n > 0) { n  -=  1; }")) == \
            in_function("if (n > 0) { n -= 1; }")

    @pytest.mark.parametrize("src", [
        "if (n > 0) {\n            n = 0; }",
        "if (n > 0)\n        { n = 0; }",
    ], ids=["broken-body", "broken-header"])
    def test_a_broken_branch_opens_out(self, src):
        assert fmt(in_function(src)) == in_function("if (n > 0) {",
                                                    "    n = 0;", "}")

    def test_two_statements_open_out(self):
        assert fmt(in_function("if (n > 0) { n = 0; n = 1; }")) == \
            in_function("if (n > 0) {", "    n = 0;", "    n = 1;", "}")

    def test_a_comment_inside_opens_out(self):
        out = fmt(in_function("if (n > 0) { /* why */ n = 0; }"))
        assert "if (n > 0) { /* why */ n = 0; }" not in out
        assert "/* why */" in out

    def test_a_comment_before_else_is_kept(self):
        src = in_function("if (n > 0) { n = 0; } /* why */ else { n = 1; }")
        result = format_safely(src, formatter=format_source)
        assert result.ok, result.diagnostic()
        assert "/* why */" in result.text

    def test_a_mixed_chain_opens_whole(self):
        src = in_function("if (n == 1) { n = 0; }",
                          "else {",
                          "    n = 9;",
                          "}")
        assert fmt(src) == in_function("if (n == 1) {", "    n = 0;",
                                       "} else {", "    n = 9;", "}")

    def test_too_wide_opens_the_whole_chain(self):
        """The *second* line is the wide one, so this fails if only the line
        the group starts on is measured."""
        src = in_function("if (n == 1) { n = 0; }",
                          "else { n = 1234567890 + 1234567890; }")
        narrow = Style(print_width=40)
        assert fmt(src, narrow) == in_function(
            "if (n == 1) {", "    n = 0;", "} else {",
            "    n = 1234567890 + 1234567890;", "}")
        assert fmt(src) == src

    def test_width_never_joins(self):
        src = in_function("if (n > 0) {", "    n = 0;", "}")
        assert fmt(src, Style(print_width=400)) == src

    @pytest.mark.parametrize("src", [
        in_function("if (n == 1)      { n = 0; }",
                    "else if (n == 2) { n = 3; }"),
        in_function("if(n>0){n=0;}else{n=1;}", "foreach(i:arr){n+=i;}"),
        in_function("if (n > 0) { n  =  0; }", "m   = 1;"),
    ], ids=["aligned-chain", "one-line", "assignment-run"])
    def test_idempotent_and_verified(self, src):
        result = format_safely(src, formatter=format_source)
        assert result.ok, result.diagnostic()
        assert fmt(result.text) == result.text


class TestActivity:

    def test_kept(self):
        src = in_activity("if (x == 1)      { do a; }",
                          "else if (x == 2) { do a; }",
                          "else             { do a; }",
                          "repeat (4) { do a; }")
        assert fmt(src) == src

    def test_two_traversals_open_out(self):
        assert fmt(in_activity("repeat (4) { do a; do a; }")) == \
            in_activity("repeat (4) {", "    do a;", "    do a;", "}")


class TestConstraint:

    def test_kept(self):
        src = in_constraint("if (x == 1) { x < 2; } else { x > 3; }",
                            "foreach (arr[i]) { arr[i] < 5; }")
        assert fmt(src) == src

    def test_a_broken_branch_opens_the_chain(self):
        src = in_constraint("if (x == 1) { x < 2; }", "else {", "    x > 3;",
                            "}")
        assert fmt(src) == in_constraint("if (x == 1) {", "    x < 2;",
                                         "} else {", "    x > 3;", "}")


class TestTrailingComments:
    """A comment after a branch's ``}`` is that row's trailing comment, and
    the comment column is inferred like any other."""

    def test_an_aligned_comment_column_is_kept(self):
        src = in_function("if (n == 1) { n = 0; }      // case 1",
                          "else if (n == 2) { n = 3; } // case 2",
                          "else { ; }                  // case 3")
        assert fmt(src) == src

    def test_a_ragged_comment_column_is_flushed(self):
        src = in_function("if (n == 1) { n = 0; } // case 1",
                          "else if (n == 2) { n = 3; }   // case 2",
                          "else { ; }    // case 3")
        assert fmt(src) == in_function("if (n == 1) { n = 0; } // case 1",
                                       "else if (n == 2) { n = 3; } // case 2",
                                       "else { ; } // case 3")

    def test_a_comment_before_else_on_its_own_line_opens_nothing(self):
        src = in_function("if (n == 1) { n = 0; }", "// why",
                          "else { n = 3; }")
        result = format_safely(src, formatter=format_source)
        assert result.ok, result.diagnostic()
        assert "// why" in result.text

    def test_idempotent_and_verified(self):
        src = in_function("int r = 0;",
                          "if (n == 1) { r = 0; }      // case 1",
                          "else if (n == 2) { r = 3; } // case 2",
                          "else if (n == 3) { ; }        // case 3",
                          "// ...")
        result = format_safely(src, formatter=format_source)
        assert result.ok, result.diagnostic()
        assert fmt(result.text) == result.text


class TestCommentColumnAcrossConstructs:
    """Comments on the ``{`` of each branch of an opened chain, separated
    by the bodies between them. End to end, because the alignment pass only
    sees this shape once the rules have marked every one of those comments."""

    CHAIN = ("if (n == 1) {        // case 1",
             "    n = 0;",
             "} else if (n == 2) { // case 2",
             "    n = 3;",
             "} else if (n == 3) { // case 3",
             "    ;",
             "}")

    def test_an_aligned_column_is_kept(self):
        src = in_function(*self.CHAIN)
        assert fmt(src) == src

    def test_kept_with_a_marked_line_directly_above(self):
        """The case that broke: ``int r = 0;`` joins the first ``{`` line's
        alignment group, which made that line a run of one and flushed it,
        while ``case 2`` and ``case 3`` kept their padding."""
        src = in_function("int r = 0;", *self.CHAIN)
        assert fmt(src) == src

    def test_a_ragged_column_is_flushed(self):
        src = in_function("if (n == 1) {      // case 1",
                          "    n = 0;",
                          "} else if (n == 2) { // case 2",
                          "    n = 3;",
                          "} else if (n == 3) {   // case 3",
                          "    ;",
                          "}")
        assert fmt(src) == in_function("if (n == 1) { // case 1",
                                       "    n = 0;",
                                       "} else if (n == 2) { // case 2",
                                       "    n = 3;",
                                       "} else if (n == 3) { // case 3",
                                       "    ;",
                                       "}")

    def test_idempotent_and_verified(self):
        src = in_function("int r = 0;", *self.CHAIN, "// ...")
        result = format_safely(src, formatter=format_source)
        assert result.ok, result.diagnostic()
        assert fmt(result.text) == result.text


class TestCommentColumnOverDifferingCode:
    """Comments the author lined up stay lined up when the code in front of
    them is not itself a table."""

    def test_fields(self):
        src = ("component c {\n"
               "    int a;          // first\n"
               "    bit[8] bb;      // second\n"
               "}\n")
        assert fmt(src) == src

    def test_a_declaration_and_assignments(self):
        src = in_function("int x = 1;      // one",
                          "x = 22;         // two",
                          "x = 333;        // three")
        assert fmt(src) == src

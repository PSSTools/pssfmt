"""``T-45`` -- the commitments, pinned as behaviour rather than as prose.

``docs/style.rst`` has a section called "What ``pssfmt`` will never do", and
until this file existed every promise in it was kept by *absence*: no rule
reordered anything, no rule reflowed a comment, no rule collapsed a body,
because no rule had been written that did. An absence is not a commitment. It
is a thing that holds until somebody adds the feature and calls it a tidy-up,
and the review that would have caught it is the one that reads the diff rather
than the page.

So this suite tests the negative space. Each test names a construct that could
plausibly *acquire* the behaviour being ruled out, and fails if it does.

``S-2`` is the item that started it, and the collapse commitment is the one
worth explaining. PSS bodies are written open: 31 of the corpus's 32 named
constraint blocks are broken, 21 of them holding exactly one item, and 117 of
its 118 function bodies likewise. A formatter that collapsed a short body onto
one line would be rewriting a deliberate convention rather than tidying
anything -- and it would do so on the smallest, most numerous constructs,
which is where a large diff comes from.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.rules import format_source  # noqa: E402

pytestmark = pytest.mark.unit


def fmt(src: str) -> str:
    return format_source(src)


# ---------------------------------------------------------------------------
# S-2 -- a body is never collapsed onto one line
# ---------------------------------------------------------------------------


class TestABodyIsNeverCollapsed:
    """Written as *inline input opens out*, which is the stronger claim.

    Asserting only that a broken body stays broken would pass for a formatter
    that had no opinion at all. These inputs are written on one line and must
    come back open, so the rule is doing work in every one of them.
    """

    def test_a_one_item_constraint_block_opens_out(self):
        assert fmt(
            "component c {\n"
            "    action a {\n"
            "        constraint x { a == b; }\n"
            "    }\n"
            "}\n"
        ) == (
            "component c {\n"
            "    action a {\n"
            "        constraint x {\n"
            "            a == b;\n"
            "        }\n"
            "    }\n"
            "}\n"
        )

    def test_a_one_line_function_body_opens_out(self):
        assert fmt(
            "component c {\n"
            "    function void f() { g(); }\n"
            "}\n"
        ) == (
            "component c {\n"
            "    function void f() {\n"
            "        g();\n"
            "    }\n"
            "}\n"
        )

    def test_an_activity_block_opens_out(self):
        assert fmt(
            "component c {\n"
            "    action a {\n"
            "        activity { do b; }\n"
            "    }\n"
            "}\n"
        ) == (
            "component c {\n"
            "    action a {\n"
            "        activity {\n"
            "            do b;\n"
            "        }\n"
            "    }\n"
            "}\n"
        )

    def test_width_does_not_enter_into_it(self):
        """The rule is about the construct, not about whether it would fit.

        A collapse rule keyed on ``print_width`` is the tempting version --
        "join it if it fits" -- and it is the one that makes output depend on
        a setting rather than on the code. A very wide ``print_width`` must
        change nothing here.
        """
        from pssfmt.style import DEFAULT_STYLE

        src = (
            "component c {\n"
            "    function void f() { g(); }\n"
            "}\n"
        )
        wide = format_source(src, style=DEFAULT_STYLE.evolve(print_width=400))
        assert wide == fmt(src)


class TestTheEnumExceptionIsNotAContradiction:
    """``enum`` *is* written on one line, and it is not a collapse rule.

    Stated here beside the commitment because the two read as contradictory
    otherwise. What decides an enum's shape is **whether its items carry
    values** -- a list on one line, a table broken -- which is measured
    (4 of 4 valued enums broken, 9 of 9 bare-name ones flat) and is not a
    question about width or about how short the body happens to be.
    """

    def test_a_bare_name_enum_stays_on_one_line(self):
        assert fmt("package p {\n    enum e { A, B }\n}\n") == (
            "package p {\n"
            "    enum e { A, B }\n"
            "}\n"
        )

    def test_an_enum_with_values_is_broken_even_though_it_would_fit(self):
        assert fmt("package p {\n    enum e { A = 0, B = 1 }\n}\n") == (
            "package p {\n"
            "    enum e {\n"
            "        A = 0,\n"
            "        B = 1\n"
            "    }\n"
            "}\n"
        )

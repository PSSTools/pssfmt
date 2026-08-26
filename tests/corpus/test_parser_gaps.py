"""``U-8`` -- minimal reproducers for the ``pssparser`` gaps the corpus found.

Found by pointing ``P1``'s round-trip gate at the ``pygments-pss`` corpus,
which no ``pssparser`` suite had run against: that corpus was built for a
*lexer*, so it contains constructs the AST tests never exercise.

Every case here is valid PSS that ``pssparser`` rejects. They are marked
``xfail(strict=True)``, so this file is an executable specification -- fixing a
gap turns its case green, which fails the strict mark and forces both this
entry and the matching ``KNOWN_UNPARSEABLE`` entry to be deleted together.

None of these block ``P1``. The null formatter round-trips every one of them
byte for byte, which is what the fail-safe is for. They block ``P3``: a rule
cannot lay out a construct the tree does not contain.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssparser import cst, tokens  # noqa: E402

from pssfmt.null import format_null  # noqa: E402

pytestmark = [pytest.mark.corpus, pytest.mark.integration]


GAPS = {
    "U-8a: action in a package":
        "package p { action a { } }",
    "U-8b: dist constraint":
        "component c { action a { rand int x; "
        "constraint { dist x := 1; } } }",
    "U-8c: cover statement in an activity":
        "component c { action a { activity { cover { } } } }",
    "U-8d: underscore inside a based number":
        "component c { bit[31:0] e = 16'h_FF; }",
    "U-8e: octal escape in a string literal":
        'component c { string s = "a: \\101"; }',
}


@pytest.mark.parametrize("src", GAPS.values(), ids=list(GAPS))
@pytest.mark.xfail(strict=True, reason="U-8: pssparser grammar/lexer gap")
def test_valid_pss_parses(src):
    assert cst.parse(src).num_syntax_errors == 0


@pytest.mark.parametrize("src", GAPS.values(), ids=list(GAPS))
def test_the_formatter_survives_every_gap(src):
    # The point of the fail-safe, demonstrated on the real thing rather than on
    # a mock: pssparser cannot parse these, and pssfmt still does not lose a
    # byte of them.
    assert format_null(src).text == src


def test_the_two_lexer_gaps_are_lexer_gaps_not_parser_gaps():
    # Worth distinguishing. A parser gap leaves well-formed tokens the grammar
    # cannot assemble; a lexer gap leaves synthetic error tokens standing for
    # text no rule matched. The second kind is invisible to anything working
    # above the token stream, so it needs recording where it can be seen.
    assert tokens.tokenize("component c { bit[31:0] e = 16'h_FF; }") \
        .num_errors > 0
    assert tokens.tokenize('component c { string s = "a: \\101"; }') \
        .num_errors > 0
    assert tokens.tokenize("package p { action a { } }").num_errors == 0


def test_the_nearest_accepted_spellings_still_work():
    # Pins where each boundary actually is, so a fix can be checked against
    # something narrower than "the file parses now".
    assert cst.parse("package p { abstract action a { } }") \
        .num_syntax_errors == 0
    assert cst.parse("component c { action a { } }").num_syntax_errors == 0
    assert cst.parse("component c { bit[31:0] e = 16'hFF; }") \
        .num_syntax_errors == 0
    assert cst.parse('component c { string s = "a: \\n"; }') \
        .num_syntax_errors == 0

"""``T-3`` -- the section 3.1 attachment rule.

The rule has two clauses and everything downstream inherits whichever one it
gets wrong, so each clause is tested on its own before anything combines them.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssparser import tokens  # noqa: E402

from pssfmt.trivia import TriviaMap  # noqa: E402

pytestmark = pytest.mark.trivia


def tmap(src, **kw):
    return TriviaMap(tokens.tokenize(src), **kw)


def by_text(tm, text, nth=0):
    """The trivia of the *nth* code token whose text is *text*."""
    seen = 0
    for trivia in tm:
        if trivia.token is not None and trivia.token.text == text:
            if seen == nth:
                return trivia
            seen += 1
    raise AssertionError(
        "no code token %r (occurrence %d) in the stream" % (text, nth))


def texts(comments):
    return [c.text for c in comments]


# ---------------------------------------------------------------------------
# Clause 1 -- same line, after a token => trailing
# ---------------------------------------------------------------------------

def test_same_line_comment_trails_the_preceding_token():
    tm = tmap("int x; // why\nint y;\n")
    assert texts(by_text(tm, ";").trailing) == ["// why\n"]
    assert by_text(tm, "int", 1).leading == ()


def test_a_comment_on_its_own_line_leads_the_next_token():
    tm = tmap("// why\nint x;\n")
    assert texts(by_text(tm, "int").leading) == ["// why\n"]
    assert texts(by_text(tm, "int").trailing) == []


def test_block_comment_between_tokens_on_one_line_trails_backwards():
    # Rule 1 is applied literally: every same-line comment attaches to what
    # precedes it. In `f(/* name */ x)` that is `(`, not `x`. This is the case
    # a rule builder is most likely to guess wrong about, so it is pinned.
    tm = tmap("f(/* name */ x);")
    assert texts(by_text(tm, "(").trailing) == ["/* name */"]
    assert by_text(tm, "x").leading == ()


def test_comment_before_finds_it_on_either_side():
    # ...and this is the accessor that spares them from knowing.
    tm = tmap("f(/* name */ x);")
    x = [t for t in tm.stream if t.text == "x"][0]
    assert texts(tm.comment_before(x)) == ["/* name */"]


def test_comment_before_prefers_the_tokens_own_leading_block():
    tm = tmap("int x; // trailing\n// leading\nint y;\n")
    y = [t for t in tm.stream if t.text == "int"][1]
    assert texts(tm.comment_before(y)) == ["// leading\n"]


def test_the_first_comment_in_a_file_leads_even_with_no_newline_before_it():
    tm = tmap("/* head */ component c { }")
    assert texts(by_text(tm, "component").leading) == ["/* head */"]


def test_a_trailing_block_ends_at_the_first_own_line_comment():
    # `// a` trails `;`. `/* b */` starts a line, so it and everything after it
    # lead `int` -- including `/* c */`, which shares a line with `/* b */` and
    # would be mistaken for trailing by a rule that asked "same line?" of each
    # comment independently rather than stopping at the first own-line one.
    tm = tmap("int x; // a\n/* b */ /* c */ int y;\n")
    assert texts(by_text(tm, ";").trailing) == ["// a\n"]
    assert texts(by_text(tm, "int", 1).leading) == ["/* b */", "/* c */"]


def test_several_comments_on_one_line_all_trail():
    tm = tmap("int x; /* a */ /* b */\nint y;\n")
    assert texts(by_text(tm, ";").trailing) == ["/* a */", "/* b */"]


def test_multiline_block_comment_ends_the_line_it_ends_on():
    # A token after a multi-line comment is on the comment's *last* line, so
    # the comment before it trails the token before the comment.
    tm = tmap("int x; /* a\nb */ int y;\n")
    assert texts(by_text(tm, ";").trailing) == ["/* a\nb */"]
    assert by_text(tm, "int", 1).leading == ()


def test_a_comment_after_a_line_comment_never_trails_it():
    # `//` owns its newline, so anything after it is on a new line even though
    # no whitespace token separates them.
    tm = tmap("int x; // a\n/* b */ int y;\n")
    assert texts(by_text(tm, ";").trailing) == ["// a\n"]
    assert texts(by_text(tm, "int", 1).leading) == ["/* b */"]


# ---------------------------------------------------------------------------
# own_line and is_block
# ---------------------------------------------------------------------------

def test_own_line_distinguishes_placement():
    tm = tmap("int x; // trailing\n// own line\nint y;\n")
    assert by_text(tm, ";").trailing[0].own_line is False
    assert by_text(tm, "int", 1).leading[0].own_line is True


@pytest.mark.parametrize("src,expected", [
    ("// a\nint x;", False),
    ("/* a */\nint x;", True),
])
def test_is_block_distinguishes_the_two_comment_forms(src, expected):
    # It matters because only one of them contains its own newline; a rule that
    # emits comment text and then a line break doubles it for `//`.
    tm = tmap(src)
    assert by_text(tm, "int").leading[0].is_block is expected


# ---------------------------------------------------------------------------
# Lookup surface
# ---------------------------------------------------------------------------

def test_lookup_by_token_and_by_index_agree():
    tm = tmap("int x;\n")
    tok = [t for t in tm.stream if t.text == "x"][0]
    assert tm.of(tok) is tm.of(tok.index)


def test_lookup_of_a_trivia_token_is_an_error_not_an_empty_answer():
    # Silently answering "no trivia" for a whitespace token would let a caller
    # walk the wrong sequence and never notice.
    tm = tmap("int x;\n")
    ws = [t for t in tm.stream if t.is_trivia][0]
    assert ws not in tm
    with pytest.raises(KeyError):
        tm.of(ws)


def test_iteration_is_source_order_and_ends_with_the_eof_entry():
    tm = tmap("int x;\n")
    seen = list(tm)
    assert [t.token.text for t in seen[:-1]] == ["int", "x", ";"]
    assert seen[-1] is tm.eof
    assert seen[-1].is_dangling


def test_max_blank_lines_must_be_non_negative():
    with pytest.raises(ValueError):
        tmap("int x;", max_blank_lines=-1)

"""``T-3`` -- dangling comments, section 3.1 clause 4.

Its own module because ``PLAN.md`` ``P1-1`` says so, and ``PLAN.md`` section
1.2 lesson 5 says why: dangling is the case every formatter gets wrong. There
are two of them and they are unrelated to each other.

**At end of file.** No following code token exists, so no token can own the
comment. It lives on :attr:`TriviaMap.eof`. A formatter that walks code tokens
and never asks for it truncates the file.

**In an empty block.** ``{ /* nothing else */ }`` has a following token -- the
closing brace -- so the attachment rule answers happily and answers unhelpfully:
the comment is *about* the block, and indenting it against ``}`` puts it in the
wrong column. Distinguishing this case needs the tree, so it is a query rather
than a field.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssparser import tokens  # noqa: E402

from pssfmt.trivia import TriviaMap  # noqa: E402

pytestmark = pytest.mark.trivia


def tmap(src):
    return TriviaMap(tokens.tokenize(src))


def texts(comments):
    return [c.text for c in comments]


def index_of(tm, text, nth=0):
    seen = 0
    for tok in tm.stream:
        if tok.text == text and not tok.is_trivia:
            if seen == nth:
                return tok.index
            seen += 1
    raise AssertionError("no %r (occurrence %d)" % (text, nth))


# ---------------------------------------------------------------------------
# At end of file
# ---------------------------------------------------------------------------

def test_a_trailing_comment_at_end_of_file_dangles():
    tm = tmap("component c { }\n// afterthought\n")
    assert texts(tm.eof.leading) == ["// afterthought\n"]
    assert tm.eof.is_dangling
    assert tm.eof.token is None


def test_a_comment_on_the_last_code_tokens_line_still_trails_it():
    # Clause 1 wins: this one has an anchor, so it is not dangling.
    tm = tmap("component c { } // done\n")
    assert tm.eof.leading == ()
    close = tm.of(index_of(tm, "}"))
    assert texts(close.trailing) == ["// done\n"]


def test_a_file_of_nothing_but_comments_dangles_entirely():
    tm = tmap("// a\n// b\n")
    assert texts(tm.eof.leading) == ["// a\n", "// b\n"]
    assert tm.code_indices == ()


def test_an_empty_file_has_an_empty_eof_entry():
    tm = tmap("")
    assert tm.eof.leading == ()
    assert tm.eof.is_dangling
    assert not tm.eof.has_comments


def test_trailing_whitespace_after_the_last_token_is_kept_raw():
    # Not a comment, so nothing semantic attaches to it -- but the null
    # formatter has to emit it or the file loses its final newline.
    tm = tmap("component c { }\n\n")
    assert "".join(t.text for t in tm.eof.raw_leading) == "\n\n"


# ---------------------------------------------------------------------------
# In an empty block
# ---------------------------------------------------------------------------

def test_a_comment_alone_in_a_block_is_reported_as_dangling():
    tm = tmap("component c { /* nothing else */ }")
    got = tm.dangling_between(index_of(tm, "{"), index_of(tm, "}"))
    assert texts(got) == ["/* nothing else */"]


def test_an_own_line_comment_alone_in_a_block_dangles_too():
    # This one attaches as *leading* on `}` rather than trailing on `{`, so a
    # query that looked at only one side would miss it.
    tm = tmap("component c {\n    // nothing else\n}\n")
    got = tm.dangling_between(index_of(tm, "{"), index_of(tm, "}"))
    assert texts(got) == ["// nothing else\n"]


def test_a_block_with_code_in_it_has_nothing_dangling():
    tm = tmap("component c { /* a */ int x; }")
    assert tm.dangling_between(index_of(tm, "{"), index_of(tm, "}")) is None


def test_none_and_empty_are_different_answers():
    # "Not the empty-body case" and "the empty-body case with no comments" are
    # different facts. A caller that conflates them indents against the wrong
    # node, so the distinction is in the return type rather than in a docstring.
    tm = tmap("component c { }")
    assert tm.dangling_between(index_of(tm, "{"), index_of(tm, "}")) == ()

    tm = tmap("component c { int x; }")
    assert tm.dangling_between(index_of(tm, "{"), index_of(tm, "}")) is None


def test_an_inverted_or_degenerate_range_is_not_the_empty_body_case():
    tm = tmap("component c { }")
    assert tm.dangling_between(index_of(tm, "}"), index_of(tm, "{")) is None
    assert tm.dangling_between(index_of(tm, "{"), index_of(tm, "{")) is None


def test_the_query_works_from_a_cst_nodes_span():
    # The intended caller is a rule builder holding a node, not a test holding
    # token indices. `start_token`/`stop_token` are what it has.
    cst = pytest.importorskip("pssparser.cst")
    tree = cst.parse("component c {\n    // nothing else\n}\n")
    node = [n for n in tree.root.walk()
            if n.rule_name == "component_declaration"][0]
    tm = TriviaMap(tree.tokens)
    inner = tm.dangling_between(
        index_of(tm, "{"), index_of(tm, "}"))
    assert node.start_token <= index_of(tm, "{") <= node.stop_token
    assert texts(inner) == ["// nothing else\n"]

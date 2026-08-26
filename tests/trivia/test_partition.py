"""``T-3`` -- the trivia map accounts for every byte.

The attachment rule decides *which* token owns a comment. This module checks
the weaker but more important property underneath it: that every token is owned
by exactly one thing, in order, with nothing duplicated and nothing dropped.
``P1-2`` reproduces a file by walking this structure, so if the partition
leaks, the null formatter loses text -- and it loses it quietly.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssparser import tokens  # noqa: E402

from pssfmt.trivia import TriviaMap  # noqa: E402
from support import assert_partitions_the_stream  # noqa: E402

pytestmark = pytest.mark.trivia


SOURCES = {
    "empty": "",
    "whitespace only": "\n\n   \n",
    "no trailing newline": "component c { }",
    "crlf": "component c {\r\n    int x;\r\n}\r\n",
    "lone cr": "component c {\r    int x;\r}\r",
    "tabs": "component c {\n\tint x;\n}\n",
    "comments only": "// a\n/* b */\n",
    "leading and trailing comments":
        "// head\ncomponent c { } // tail\n// foot\n",
    "byte order mark": "﻿component c { }\n",
    "unlexable character": "component c { } $ component d { }\n",
    "unterminated block comment": "/* a\ncomponent c { }\n",
    "unterminated string": 'component c { string s = "oops;\n}\n',
    "nested-looking block comment": "/* a /* b */ c */\ncomponent c { }\n",
    "triple quoted": ('component c { exec body C = """\n'
                      '  not // pss at all /*\n"""; }\n'),
    "escaped identifier": "component \\c-d { }\n",
    "unicode": "// café — 日本語\ncomponent c { }\n",
    "syntax error": "component c { this is not pss }",
}


@pytest.mark.parametrize("src", SOURCES.values(), ids=list(SOURCES))
def test_the_map_partitions_the_stream(src):
    assert_partitions_the_stream(TriviaMap(tokens.tokenize(src)))


@pytest.mark.parametrize("src", SOURCES.values(), ids=list(SOURCES))
def test_the_map_reproduces_the_source(src):
    # The partition assertion implies this, but stated separately because it is
    # the property a reader of this file actually cares about.
    tm = TriviaMap(tokens.tokenize(src))
    out = []
    for trivia in tm:
        out.extend(t.text for t in trivia.raw_leading)
        if trivia.token is not None:
            out.append(trivia.token.text)
        out.extend(t.text for t in trivia.raw_trailing)
    assert "".join(out) == src


@pytest.mark.parametrize("src", SOURCES.values(), ids=list(SOURCES))
def test_the_clamp_never_affects_the_partition(src):
    # Blank-line policy is a style decision; losslessness is not. No setting of
    # max_blank_lines may change what the raw runs contain.
    a = TriviaMap(tokens.tokenize(src), max_blank_lines=0)
    b = TriviaMap(tokens.tokenize(src), max_blank_lines=99)
    for x, y in zip(a, b):
        assert [t.index for t in x.raw_leading] == \
            [t.index for t in y.raw_leading]
        assert [t.index for t in x.raw_trailing] == \
            [t.index for t in y.raw_trailing]


def test_every_comment_in_the_stream_is_attached_exactly_once():
    src = "// a\nint x; // b\n/* c */ int y; /* d */\n// e\n"
    tm = TriviaMap(tokens.tokenize(src))
    attached = []
    for trivia in tm:
        attached.extend(c.token.index for c in trivia.leading)
        attached.extend(c.token.index for c in trivia.trailing)
    in_stream = [t.index for t in tm.stream if t.is_comment]
    assert sorted(attached) == in_stream
    assert len(set(attached)) == len(attached)


def test_an_error_token_is_carried_in_the_raw_runs():
    # Error tokens are not trivia and not comments, so nothing semantic claims
    # them. They still have to come out, and this is where they live.
    tm = TriviaMap(tokens.tokenize("component c { } $ int x;\n"))
    raw = [t for trivia in tm
           for t in trivia.raw_leading + trivia.raw_trailing]
    assert [t.text for t in raw if t.is_error] == ["$"]

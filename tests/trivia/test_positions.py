"""``TriviaMap.code_indices``: built once, and looked up by bisection.

Rule builders call ``code_indices.index(token_index)`` per token. The
property used to copy the list into a fresh tuple on every access, and
``tuple.index`` scans; together they made formatting quadratic in the file.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssparser import tokens  # noqa: E402

from pssfmt.trivia import TriviaMap  # noqa: E402

pytestmark = pytest.mark.trivia

SRC = "component c { // note\n    int a; /* x */ int b;\n}\n"


def test_it_is_built_once():
    tm = TriviaMap(tokens.tokenize(SRC))
    assert tm.code_indices is tm.code_indices


def test_index_agrees_with_a_scan():
    tm = TriviaMap(tokens.tokenize(SRC))
    code = tm.code_indices
    assert list(code) == sorted(code)
    for pos, idx in enumerate(code):
        assert code.index(idx) == pos == tuple(code).index(idx)


def test_a_trivia_token_is_not_found():
    tm = TriviaMap(tokens.tokenize(SRC))
    trivia = [t.index for t in tm.stream if t.is_trivia]
    assert trivia
    for idx in trivia:
        with pytest.raises(ValueError):
            tm.code_indices.index(idx)

"""``P1-2`` -- the null formatter reproduces its input.

One assertion, made many ways: ``format_null(src).text == src``. The corpus
sweep lives in ``tests/corpus``; this module covers the shapes a corpus of real
PSS does not contain, which is most of the ways a round trip actually breaks.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssparser import cst  # noqa: E402

from pssfmt.null import format_null  # noqa: E402
from support import assert_partitions_the_stream  # noqa: E402

pytestmark = pytest.mark.unit


SOURCES = {
    "empty": "",
    "whitespace only": "\n\n   \n",
    "no trailing newline": "component c { }",
    "crlf": "component c {\r\n    int x;\r\n}\r\n",
    "lone cr": "component c {\r    int x;\r}\r",
    "tabs and spaces": "component c {\n\t int x;  \n}\n",
    "trailing whitespace": "component c { }   \n   \n",
    "comments only": "// a\n/* b */\n",
    "comment at end of file, no newline": "component c { } // tail",
    "byte order mark": "﻿component c { }\n",
    "many blank lines": "component c { }\n\n\n\n\n\ncomponent d { }\n",
    "unlexable character": "component c { } $ component d { }\n",
    "unterminated block comment": "/* a\ncomponent c { }\n",
    "unterminated string": 'component c { string s = "oops;\n}\n',
    "triple quoted": ('package p { component c { exec body C = """\n'
                      '   verbatim // not pss  /*\n"""; } }\n'),
    "escaped identifier": "component \\c-d { }\n",
    "unicode": "// café — 日本語\ncomponent c { }\n",
    "compile if": ("package p {\n  compile if (X) {\n"
                   "    component taken { }\n  } else {\n"
                   "    component not_taken { }\n  }\n}\n"),
    "redundant parens": "component c { int x; constraint { ((x)) > 0; } }\n",
    "syntax error": "component c { this is not pss }\n",
    "only a brace": "}\n",
}


@pytest.mark.parametrize("src", SOURCES.values(), ids=list(SOURCES))
def test_the_output_is_the_input(src):
    assert format_null(src).text == src


@pytest.mark.parametrize("src", SOURCES.values(), ids=list(SOURCES))
def test_the_tree_reaches_every_code_token(src):
    # `skipped` is the emitter's safety net: text the tree walk stepped past
    # and the cursor had to flush. It being empty is the interesting claim --
    # it means the CST really does cover the file, including the files that do
    # not parse.
    assert format_null(src).skipped == ()


@pytest.mark.parametrize("src", SOURCES.values(), ids=list(SOURCES))
def test_the_trivia_map_it_built_is_a_partition(src):
    assert_partitions_the_stream(format_null(src).trivia)


def test_bytes_are_accepted_and_decoded():
    assert format_null(b"component c { }\n").text == "component c { }\n"


def test_invalid_utf8_propagates_rather_than_guessing():
    # There is no text to hand back, so there is nothing safe to return.
    with pytest.raises(UnicodeDecodeError):
        format_null(b"// caf\xe9\ncomponent c { }\n")


def test_a_file_that_does_not_parse_still_round_trips():
    src = "component c { this is not pss }\n"
    result = format_null(src)
    assert result.num_syntax_errors > 0
    assert result.text == src


def test_an_already_parsed_tree_can_be_reused():
    # Parsing is the expensive half. `format_safely` and the verifier both
    # want the tree, and paying for it twice is the kind of thing that only
    # shows up as "the formatter is slow on big files".
    src = "component c { int x; }\n"
    tree = cst.parse(src)
    from pssfmt.null import emit_null
    assert emit_null(tree).text == src


def test_max_blank_lines_does_not_change_the_output():
    # It is a style knob, and the null formatter has no style. If this ever
    # fails, something in the emit path is reading a policy field it should
    # not be able to see.
    src = "component c { }\n\n\n\n\ncomponent d { }\n"
    assert format_null(src, max_blank_lines=0).text == src
    assert format_null(src, max_blank_lines=9).text == src

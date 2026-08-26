"""``T-3`` -- ``blank_lines_before``, section 3.1 clause 3.

Preserving *whether* the author left a blank line but not how many is the gofmt
behaviour. Two things make the count easy to get wrong and both are pinned
here: a ``//`` comment carries its own newline, and the count belongs in front
of the *leading-comment block*, not in front of the token.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssparser import tokens  # noqa: E402

from pssfmt.trivia import DEFAULT_MAX_BLANK_LINES, TriviaMap  # noqa: E402

pytestmark = pytest.mark.trivia


def tmap(src, **kw):
    return TriviaMap(tokens.tokenize(src), **kw)


def second(tm, text):
    seen = 0
    for trivia in tm:
        if trivia.token is not None and trivia.token.text == text:
            if seen:
                return trivia
            seen += 1
    raise AssertionError("no second %r" % text)


@pytest.mark.parametrize("gap,expected", [
    (" ", 0),
    ("\n", 0),
    ("\n\n", 1),
    ("\n\n\n", 1),
    ("\n\n\n\n\n", 1),
])
def test_blank_lines_are_counted_then_clamped(gap, expected):
    tm = tmap("int x;%sint y;\n" % gap)
    assert second(tm, "int").blank_lines_before == expected


@pytest.mark.parametrize("gap,expected", [("\n", 0), ("\n\n", 1),
                                          ("\n\n\n\n", 3)])
def test_the_unclamped_count_is_kept_too(gap, expected):
    # `--explain` (P4-5) reports what the clamp threw away; a report that can
    # only say "1" cannot tell a user why their four blank lines became one.
    tm = tmap("int x;%sint y;\n" % gap)
    assert second(tm, "int").raw_blank_lines_before == expected


def test_the_clamp_is_configurable():
    src = "int x;\n\n\n\n\nint y;\n"
    assert second(tmap(src, max_blank_lines=2), "int").blank_lines_before == 2
    assert second(tmap(src, max_blank_lines=0), "int").blank_lines_before == 0


def test_the_default_clamp_is_one():
    assert DEFAULT_MAX_BLANK_LINES == 1


def test_the_count_sits_in_front_of_the_leading_block_not_the_token():
    # Two blank lines before the comment, none between it and `int`. Section
    # 3.1 asks for the space the author left before the *block*, because that
    # is the space a formatter has to decide whether to reproduce.
    tm = tmap("int x;\n\n\n// note\nint y;\n")
    trivia = second(tm, "int")
    assert trivia.blank_lines_before == 1
    assert trivia.leading[0].blank_lines_before == 1


def test_a_line_comment_supplies_its_own_newline():
    # `// a\n` ends the line itself, so the single `\n` after it makes exactly
    # one blank line. Counting only the whitespace token would say zero.
    tm = tmap("int x; // a\n\nint y;\n")
    assert second(tm, "int").blank_lines_before == 1


def test_a_line_comment_directly_followed_by_code_leaves_no_blank_line():
    tm = tmap("int x; // a\nint y;\n")
    assert second(tm, "int").blank_lines_before == 0


def test_blank_lines_between_two_leading_comments():
    tm = tmap("int x;\n// a\n\n// b\nint y;\n")
    lead = second(tm, "int").leading
    assert [c.blank_lines_before for c in lead] == [0, 1]


def test_a_multiline_block_comment_does_not_count_its_own_newlines():
    # The newlines are inside the token. They are the comment's shape, not
    # vertical space the author put between two things.
    tm = tmap("int x;\n/* a\n\n\nb */\nint y;\n")
    trivia = second(tm, "int")
    assert trivia.blank_lines_before == 0
    assert trivia.leading[0].blank_lines_before == 0


def test_blank_lines_at_the_start_of_a_file_are_all_blank():
    # Off by one everywhere else: normally the first newline in a gap only
    # terminates the line above it. At the top of a file there is no line
    # above, so all three newlines here make blank lines.
    tm = tmap("\n\n\ncomponent c { }\n")
    first = next(iter(tm))
    assert first.token.text == "component"
    assert first.raw_blank_lines_before == 3
    assert first.blank_lines_before == 1


def test_a_leading_comment_at_the_top_of_a_file_counts_the_same_way():
    tm = tmap("\n\n// note\ncomponent c { }\n")
    first = next(iter(tm))
    assert first.raw_blank_lines_before == 2
    assert first.leading[0].blank_lines_before == 1


def test_a_file_that_starts_with_code_has_no_blank_lines_before_it():
    tm = tmap("component c { }\n")
    assert next(iter(tm)).raw_blank_lines_before == 0

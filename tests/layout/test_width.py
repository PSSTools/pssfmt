"""``T-2`` / ``Q-6`` -- display width is one function, and this pins it.

``formatter.md`` section 7.7 leaves the counting unit open. The decision
recorded in ``PLAN.md`` ``Q-6`` is display columns, and the reason it is
survivable to decide it early is that it lives at exactly one call site. These
tests exist so that changing the decision has to change them too -- an
accidental drift back to ``len()`` is caught rather than shipped.
"""

from __future__ import annotations

import pytest

from pssfmt.layout import render, text, width_of
from pssfmt.layout.ir import concat, group, indent
from pssfmt.layout.width import char_width

pytestmark = [pytest.mark.layout, pytest.mark.unit]


def test_ascii_is_one_column_per_character():
    assert width_of("component pss_top") == 17


def test_empty_string():
    assert width_of("") == 0


@pytest.mark.parametrize(
    "s,expected",
    [
        ("你好", 4),          # CJK: two Wide characters
        ("ＡＢ", 4),          # Fullwidth Latin
        ("a你b", 4),              # mixed
        ("안녕", 4),          # Hangul syllables are Wide
    ],
)
def test_east_asian_wide_counts_as_two(s, expected):
    assert width_of(s) == expected


@pytest.mark.parametrize(
    "s,expected",
    [
        ("é", 1),               # e + combining acute
        ("à́̂", 1),   # one base, three marks
        ("​", 0),                # zero-width space (Cf)
    ],
)
def test_combining_marks_are_zero_width(s, expected):
    assert width_of(s) == expected


def test_precomposed_and_decomposed_forms_measure_the_same():
    """Otherwise the same-looking identifier breaks differently by encoding."""
    assert width_of("café") == width_of("café")


def test_len_and_width_disagree_which_is_the_whole_point():
    s = "你好"
    assert len(s) == 2
    assert width_of(s) == 4


def test_a_tab_in_measured_text_is_an_error_not_a_guess():
    """Indentation is the engine's to emit; a tab in a Text node is a rule bug."""
    with pytest.raises(ValueError, match="tab in measured text"):
        width_of("a\tb")
    with pytest.raises(ValueError, match="tab in measured text"):
        char_width("\t")


def test_the_engine_breaks_on_columns_not_characters():
    """The end-to-end consequence: a CJK comment breaks earlier than its len()."""
    wide = "你" * 6  # 6 characters, 12 columns
    doc = group(concat(text("["), indent(concat(text(wide),), 4), text("]")))
    assert width_of(render(doc, print_width=100)) == 14

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
from pssfmt.layout.width import char_width, expand_tabs

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


# ---------------------------------------------------------------------------
# Tabs the formatter did not write (``P3-8``)
# ---------------------------------------------------------------------------
#
# The refusal above is right for composed text and wrong for copied text, and
# the two needed separating. A ``Verbatim`` node holds the author's bytes --
# a declined construct, or the interior of a target-template ``exec`` body --
# and those may contain a tab. Raising there does not prevent anything; it
# aborts the render, and the fail-safe hands back the whole file unformatted.


@pytest.mark.parametrize("text_in, start, expected", [
    ("\ta", 0, "    a"),
    ("\ta", 3, " a"),          # already at column 3; the stop is at 4
    ("\ta", 4, "    a"),       # exactly on a stop; a full tab follows
    ("a\tb", 0, "a   b"),
    ("\t\ta", 0, "        a"),
    ("ab", 0, "ab"),           # untouched, and returned as-is
    ("", 0, ""),
])
def test_expand_tabs_advances_to_the_next_stop(text_in, start, expected):
    assert expand_tabs(text_in, start, 4) == expected


def test_expand_tabs_is_measurable_where_width_of_alone_is_not():
    """The composition that is the whole point of the function."""
    with pytest.raises(ValueError):
        width_of("\tf();")
    assert width_of(expand_tabs("\tf();", 0, 4)) == 8


@pytest.mark.parametrize("src, why", [
    ("package p {\n\tcovergroup cg {\n\t\tc : coverpoint x;\n\t}\n}\n",
     "a tab-indented multi-line declined construct"),
    ("package p {\n    covergroup cg {\n        c : coverpoint\tx;\n    }\n}\n",
     "a tab in the middle of a one-line declined construct"),
    ("component c {\n    compile if\t(P) { int x; }\n}\n",
     "a tab inside `compile if`"),
    ("package p {\n    @desc_c {.text\t= \"x\"}\n    struct s { int x; }\n}\n",
     "a tab inside an annotation"),
    ('component c {\n    action a {\n        exec body C = """\n'
     '\tf();\n        """;\n    }\n}\n',
     "a tab inside a target template"),
])
def test_a_tab_the_author_wrote_does_not_abort_the_render(src, why):
    """The end-to-end defect, from outside, in every shape that reaches it.

    A declined construct is emitted as the author's bytes. Put a tab in one
    and those bytes reach the engine -- as ``Text`` if the body was judged
    re-anchorable, as ``Verbatim`` if not -- and before ``P3-8`` both paths
    called ``width_of`` on it and raised. The fail-safe caught the exception
    and handed the file back with no rule having run, so the formatter did
    nothing at all to any tab-indented file holding a declined construct.

    Both paths are here on purpose: fixing only the ``Verbatim`` one left the
    ``Text`` one raising, and a mutation run is what said so.

    The corpus cannot catch any of this. 0 of its 4856 lines contain a tab.
    """
    pytest.importorskip("pssparser")
    from pssfmt.rules import format_source
    from pssfmt.verify import format_safely
    assert format_safely(src, formatter=format_source).ok, why
    once = format_source(src)
    assert format_source(once) == once, why

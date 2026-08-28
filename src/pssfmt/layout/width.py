"""Display width of a string -- the one place width is defined.

Whether ``print_width`` counts characters or display columns is a real
choice, and the two disagree wherever a PSS file contains a wide character --
in a comment or a string literal, most often. This package counts **display
columns**, with East-Asian Wide and Fullwidth forms counted as two, so that a
line that looks like it fits does fit.

The decision lives behind one function rather than in every caller, so that
changing it is one edit rather than an audit.

This module is that call site. Nothing else in the engine may use ``len()`` on
text that will be rendered.

Grapheme clustering
-------------------
A full grapheme-cluster segmenter (UAX #29) needs either a dependency or a
large table, and ``layout/`` takes no dependencies. The approximation here is
the conventional ``wcwidth`` one: characters in the combining categories
(``Mn`` non-spacing mark, ``Me`` enclosing mark, ``Cf`` format) contribute zero
width, so a base character plus its combining marks measures as one column.

That is exact for the composing sequences that occur in identifiers and
comments and wrong only for emoji ZWJ sequences and regional-indicator pairs,
which measure wide here but render as a single cluster in most terminals. If a
PSS file ever puts a flag emoji in a trailing comment the line may be measured
two columns wide instead of one; that is the whole of the known error, and it
can only cause an *earlier* break, never an overflow.
"""

from __future__ import annotations

import unicodedata

__all__ = ["width_of", "char_width", "expand_tabs"]

# Categories that occupy no column of their own.
_ZERO_WIDTH_CATEGORIES = frozenset(("Mn", "Me", "Cf"))

# East Asian Width classes that occupy two columns.
_WIDE_EAW = frozenset(("W", "F"))


def char_width(ch: str) -> int:
    """Display width of a single character, in columns.

    Returns 0 for combining marks and format characters, 2 for East-Asian Wide
    and Fullwidth forms, and 1 otherwise.
    """
    if ch == "\t":
        # A tab in rendered text has no context-free width. The engine emits
        # tabs only as indentation, where its width is known from tab_width,
        # so a tab reaching here means a Text node carried one -- a bug in a
        # rule, not something to guess about.
        raise ValueError(
            "tab in measured text: indentation is the engine's to emit, "
            "and a Text node must not contain one"
        )
    if ch == "\x00":
        return 0
    o = ord(ch)
    if o < 0x20 or o == 0x7F:
        # Other C0 controls. Treat as zero rather than raising: they can appear
        # inside Verbatim payloads, which are exempt from width anyway.
        return 0
    if o < 0x7F:
        # Fast path: printable ASCII is always one column.
        return 1
    if unicodedata.category(ch) in _ZERO_WIDTH_CATEGORIES:
        return 0
    if unicodedata.east_asian_width(ch) in _WIDE_EAW:
        return 2
    return 1


def width_of(text: str) -> int:
    """Display width of ``text`` in columns.

    ``text`` must not contain a newline -- a measured string is by definition
    one that fits on a line.
    """
    if not text:
        return 0
    if text.isascii():
        # Overwhelmingly the common case in PSS source. Avoid the per-character
        # unicodedata lookups entirely.
        if "\t" in text:
            raise ValueError(
                "tab in measured text: indentation is the engine's to emit, "
                "and a Text node must not contain one"
            )
        return sum(1 for ch in text if ch >= " " and ch != "\x7f")
    return sum(char_width(ch) for ch in text)


def expand_tabs(text: str, start_col: int = 0, tab_width: int = 4) -> str:
    """*text* with each tab advanced to the next tab stop from *start_col*.

    For measuring text the formatter did **not** compose. :func:`width_of`
    refuses a tab outright, and that refusal is worth keeping: a ``Text`` node
    is something a rule built, indentation is the engine's to emit, and a tab
    arriving in composed text means a rule wrote one. There is no width that
    answer should have.

    A ``Verbatim`` node is the opposite case. It is the author's bytes, copied
    because the formatter decided it was not entitled to move them -- a
    declined construct, or the interior of a target-template ``exec`` body --
    and those bytes may contain a tab for reasons that are none of the
    engine's business. Refusing to measure one does not protect anything; it
    just raises, and the fail-safe then returns the whole file unformatted.

    Which is not hypothetical: before ``P3-8`` any tab-indented file holding a
    multi-line declined construct did exactly that. The corpus could not show
    it, because 0 of its 4856 lines begin with a tab.

    *start_col* matters because a tab stop is absolute. ``"\\ta"`` measures 4
    columns at the start of a line and 1 more column at column 3, and the
    single-line ``Verbatim`` case starts wherever the line had got to.
    """
    if "\t" not in text:
        return text
    # Tab stops count from the start of the line, so shift the text to its
    # real column, expand, and shift back. Spaces expand to themselves, which
    # is what makes the round trip exact rather than approximate.
    return (" " * start_col + text).expandtabs(tab_width)[start_col:]

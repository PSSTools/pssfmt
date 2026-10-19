"""Line breaking does not count the padding the alignment pass may remove.

A hand-aligned block whose padding pushes one line past ``print_width`` used
to be declined as non-idempotent. The engine measured the padding and broke
that line. The break left the block ragged, so ``infer`` flushed the padding
away, and formatting the output again found the line fitting and joined it
back up::

    idempotence (output line 4): formatting the output again changed it ...

It took two lines (one line is no evidence, so ``infer`` reproduces it
padding and all) and enough indentation to tip the second one over the
width. See :func:`pssfmt.layout.align.column_stop` for the fix.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.layout import AlignMode  # noqa: E402
from pssfmt.rules import format_source  # noqa: E402
from pssfmt.style import Style  # noqa: E402
from pssfmt.verify import format_safely  # noqa: E402

pytestmark = pytest.mark.unit


# The reported shape. The second line is 83 columns with its padding and 66
# flush-left; the first fits either way.
TABLE = """\
package p {
    component fab_c {
        array<bit[1], NUM_PORTS>     port_is_client;          // CLIENT_PORT?
        array<bit[1], NUM_PORTS>     port_check_on_reset;     // trust-level check
    }
}
"""

# The same table without its padding.
FLUSH = """\
package p {
    component fab_c {
        array<bit[1], NUM_PORTS> port_is_client; // CLIENT_PORT?
        array<bit[1], NUM_PORTS> port_check_on_reset; // trust-level check
    }
}
"""

# Aligned assignments, where the column stop is a token seam rather than a
# trailing comment. The second line is 82 columns padded and 80 flush-left.
ASSIGNMENTS = """\
component c {
    function void g() {
        xfer.src                       = make_handle(src.mem_region, 4, 8);
        xfer.destination_address_reg   = make_handle(dst.region, 4, 8, 16, 32, 1);
    }
}
"""

MODES = list(AlignMode)


def style(mode: AlignMode, **kw) -> Style:
    return Style(alignment=mode, **kw)


def safe(src: str, st: Style):
    return format_safely(src, formatter=lambda s: format_source(s, style=st))


@pytest.mark.parametrize("mode", MODES, ids=lambda m: m.value)
@pytest.mark.parametrize("src", [TABLE, FLUSH, ASSIGNMENTS],
                         ids=["table", "flush", "assignments"])
def test_the_output_is_accepted(src, mode):
    result = safe(src, style(mode))
    assert result.ok, result.diagnostic()


@pytest.mark.parametrize("mode", MODES, ids=lambda m: m.value)
@pytest.mark.parametrize("src", [TABLE, FLUSH, ASSIGNMENTS],
                         ids=["table", "flush", "assignments"])
@pytest.mark.parametrize("width", range(40, 101, 3))
def test_it_is_idempotent_at_every_width(src, mode, width):
    st = style(mode, print_width=width)
    once = format_source(src, style=st)
    assert format_source(once, style=st) == once


@pytest.mark.parametrize("spacing", [1, 2, 3])
def test_it_is_idempotent_with_a_wider_comment_gap(spacing):
    st = Style(spaces_before_trailing_comment=spacing)
    once = format_source(TABLE, style=st)
    assert format_source(once, style=st) == once


@pytest.mark.parametrize("src", [TABLE, ASSIGNMENTS],
                         ids=["table", "assignments"])
def test_infer_keeps_the_authors_table(src):
    """The padding is the author's, and only padding overflowed. Nothing is
    broken to make room for it, and the table survives as written -- as an
    unbreakable over-long table always has."""
    assert format_source(src, style=style(AlignMode.INFER)) == src


def test_flush_left_breaks_nothing_once_the_padding_is_gone():
    assert format_source(TABLE, style=style(AlignMode.FLUSH_LEFT)) == FLUSH


def test_flush_left_joins_the_assignment_at_exactly_the_width():
    got = format_source(ASSIGNMENTS, style=style(AlignMode.FLUSH_LEFT))
    assert max(len(l) for l in got.splitlines()) == 80, got


def test_the_unpadded_table_is_already_formatted():
    assert format_source(FLUSH, style=style(AlignMode.INFER)) == FLUSH


def test_preserve_still_measures_the_padding():
    """``preserve`` keeps the author's spacing whatever the width, so line
    breaking has to see it -- that mode must break where it overflows."""
    once = format_source(TABLE, style=style(AlignMode.PRESERVE))
    assert all(len(l) <= 80 for l in once.splitlines()), once

"""Post-layout column alignment, and the four alignment modes.

This pass runs **after** line breaking, never before, so alignment can never
influence a fit decision. Line breaking decides
where lines end; this decides how the columns inside a run of finished lines
line up. Doing it in the other order makes the two mutually recursive.

The marker protocol
-------------------
A rule marks a column stop by emitting :data:`ALIGN_MARK` immediately before
the whitespace it wants controlled, and leaves the author's original spacing
after it:

    Text("bit[8] addr;") + ALIGN_MARK + Text("   // the register offset")

The mark measures zero columns (see :func:`~pssfmt.layout.width.char_width`),
so it is invisible to the engine. Carrying the original spacing *after* the
mark is what makes ``preserve`` and ``infer`` implementable at all: by the time
this pass runs, the source is gone, and the only record of what the author did
is what the rule brought along.

The four modes
--------------
Taken from verible, the closest peer formatter, which also defaults to
``infer``. That default is not just precedent: measured over the PSS test
corpus, hand-written code aligns its trailing comments in every run of three
or more lines, and machine-generated code aligns none of them. A global
``align`` would column-ise generated output nobody asked to be aligned; a
global ``flush-left`` would destroy hand-built register tables. ``infer``
reproduces both. See the style guide for the measurements.

``align``
    Pad each column to the widest cell in its group.
``flush-left``
    One space at each column stop. No padding.
``preserve``
    Leave the author's spacing exactly as it was.
``infer``
    Per group: if the author already had this block aligned, align it;
    otherwise flush it left.

``infer`` is why the alignment-versus-diff-size argument (section 7.6) is a
false binary. Hand-aligned register tables keep their alignment, ordinary code
gets small diffs, and neither needs a config setting.

Abandon-if-over-limit
---------------------
Copied verbatim from verible, and worth copying: if aligning a group would
push any of its lines past ``print_width``, the whole group falls back to
flush-left. Alignment never causes an overflow -- which is what lets it stay
on by default.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from .width import width_of

__all__ = [
    "ALIGN_MARK",
    "AlignMode",
    "GroupBoundary",
    "align_text",
    "strip_marks",
]

#: Zero-width sentinel marking a column stop. NUL is used because it cannot
#: occur in PSS source (the lexer would have rejected the file long before
#: here), so a mark can never collide with content.
ALIGN_MARK = "\x00"

_DEFAULT_MIN_SPACING = 1


class AlignMode(str, Enum):
    """How a group of column stops is resolved."""

    ALIGN = "align"
    FLUSH_LEFT = "flush-left"
    PRESERVE = "preserve"
    INFER = "infer"


class GroupBoundary(str, Enum):
    """What terminates a run of lines that align together.

    Mirrors verible's ``--alignment_group_boundary``. Indentation changes
    always terminate a group regardless of this setting: a member at one
    nesting depth and a member at another are not a table, and aligning across
    the two produces the drifting-column effect that makes people turn
    alignment off.
    """

    NONE = "none"
    BLANK_LINES = "blank-lines"
    SEPARATOR_COMMENTS = "separator-comments"
    BLANK_LINES_AND_SEPARATOR_COMMENTS = "blank-lines-and-separator-comments"


# `//====`, `//-----`, `/* ***** */` and friends: a comment whose body is one
# punctuation character repeated. Authors use these as section rules, and a
# section rule is exactly where one table ends and the next begins.
_SEPARATOR_COMMENT = re.compile(r"^\s*(//+|/\*)\s*(?P<body>([^\w\s])\3{2,})\s*(\*/)?\s*$")


def strip_marks(text: str) -> str:
    """Remove every column stop, leaving the spacing that follows it.

    This is the ``preserve`` implementation, and also what a caller uses when
    it wants no alignment pass at all.
    """
    return text.replace(ALIGN_MARK, "")


def align_text(
    text: str,
    *,
    mode: AlignMode = AlignMode.INFER,
    boundary: GroupBoundary = GroupBoundary.BLANK_LINES,
    print_width: int = 100,
    min_spacing: int = _DEFAULT_MIN_SPACING,
) -> str:
    """Resolve every column stop in ``text``.

    ``text`` is the engine's output, complete with :data:`ALIGN_MARK`
    sentinels. The result contains none.
    """
    if ALIGN_MARK not in text:
        return text
    if mode is AlignMode.PRESERVE:
        return strip_marks(text)

    lines = text.split("\n")
    parsed = [_parse_line(line) for line in lines]

    out: List[str] = [None] * len(lines)  # type: ignore[list-item]
    for start, stop in _groups(lines, parsed, boundary):
        _resolve_group(lines, parsed, start, stop, mode, print_width, min_spacing, out)

    for i, line in enumerate(lines):
        if out[i] is None:
            out[i] = line.replace(ALIGN_MARK, "")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Line parsing
# --------------------------------------------------------------------------


class _Line:
    """A line split at its column stops.

    ``cells`` are the contents between stops, with the author's padding
    removed; ``pads`` are those removed widths, one per stop, kept so
    ``infer`` can ask what the author actually did.
    """

    __slots__ = ("cells", "pads", "indent", "blank")

    def __init__(self, cells: List[str], pads: List[int], indent: int, blank: bool) -> None:
        self.cells = cells
        self.pads = pads
        self.indent = indent
        self.blank = blank

    @property
    def marked(self) -> bool:
        return len(self.cells) > 1


def _parse_line(line: str) -> _Line:
    raw = line.replace(ALIGN_MARK, "")
    blank = not raw.strip()
    indent = len(raw) - len(raw.lstrip(" \t"))

    parts = line.split(ALIGN_MARK)
    cells = [parts[0]]
    pads: List[int] = []
    for part in parts[1:]:
        stripped = part.lstrip(" ")
        pads.append(len(part) - len(stripped))
        cells.append(stripped)
    return _Line(cells, pads, indent, blank)


# --------------------------------------------------------------------------
# Grouping
# --------------------------------------------------------------------------


def _is_boundary(line: str, parsed: _Line, boundary: GroupBoundary) -> bool:
    if boundary is GroupBoundary.NONE:
        return False
    if parsed.blank and boundary in (
        GroupBoundary.BLANK_LINES,
        GroupBoundary.BLANK_LINES_AND_SEPARATOR_COMMENTS,
    ):
        return True
    if boundary in (
        GroupBoundary.SEPARATOR_COMMENTS,
        GroupBoundary.BLANK_LINES_AND_SEPARATOR_COMMENTS,
    ) and _SEPARATOR_COMMENT.match(line.replace(ALIGN_MARK, "")):
        return True
    return False


def _groups(
    lines: Sequence[str], parsed: Sequence[_Line], boundary: GroupBoundary
) -> List[Tuple[int, int]]:
    """Half-open ``[start, stop)`` ranges of lines that align together.

    A group runs until a configured boundary line, an indentation change, or
    the end of the text. Unmarked lines inside a group are carried along but
    contribute no cells -- so a single unmarked continuation line in the middle
    of a declaration block does not split the table in two.
    """
    result: List[Tuple[int, int]] = []
    start: Optional[int] = None
    group_indent: Optional[int] = None

    for i, line in enumerate(lines):
        p = parsed[i]
        terminates = _is_boundary(line, p, boundary)
        if not terminates and p.marked and group_indent is not None and p.indent != group_indent:
            terminates = True

        if terminates:
            if start is not None:
                result.append((start, i))
            start = None
            group_indent = None
            continue

        if p.marked:
            if start is None:
                start = i
                group_indent = p.indent
        elif start is None:
            # Unmarked line outside any group: nothing to join.
            continue

    if start is not None:
        result.append((start, len(lines)))

    # Trim trailing unmarked lines off each group; they were only ever
    # passengers and including them makes the ranges harder to reason about.
    trimmed: List[Tuple[int, int]] = []
    for start, stop in result:
        while stop > start and not parsed[stop - 1].marked:
            stop -= 1
        if stop > start:
            trimmed.append((start, stop))
    return trimmed


# --------------------------------------------------------------------------
# Column resolution
# --------------------------------------------------------------------------


def _resolve_group(
    lines: Sequence[str],
    parsed: Sequence[_Line],
    start: int,
    stop: int,
    mode: AlignMode,
    print_width: int,
    min_spacing: int,
    out: List[str],
) -> None:
    members = [i for i in range(start, stop) if parsed[i].marked]

    effective = mode
    if mode is AlignMode.INFER:
        effective = AlignMode.ALIGN if _was_aligned(parsed, members) else AlignMode.FLUSH_LEFT

    if effective is AlignMode.FLUSH_LEFT:
        _emit_flush_left(parsed, members, min_spacing, out)
        return

    targets = _column_targets(parsed, members, min_spacing)
    rendered = {i: _emit_with_targets(parsed[i], targets, min_spacing) for i in members}

    # Abandon alignment rather than overflow (verible's rule) -- but only when
    # alignment is what causes the overflow. A block containing one inherently
    # over-long line would otherwise lose its alignment for a reason alignment
    # cannot fix, which is a strictly worse result for the same overflow.
    if any(width_of(t) > print_width for t in rendered.values()):
        flush: List[str] = list(out)
        _emit_flush_left(parsed, members, min_spacing, flush)
        if all(width_of(flush[i]) <= print_width for i in members):
            for i in members:
                out[i] = flush[i]
            return

    for i, textline in rendered.items():
        out[i] = textline


def _was_aligned(parsed: Sequence[_Line], members: Sequence[int]) -> bool:
    """Did the author already have this block aligned?

    The signal is the author's own padding: a block is taken to be aligned
    when every member reaches each column stop at the same column, and at
    least one member needed more than the minimum spacing to get there. The
    second half of that test is what stops a run of same-length declarations
    from being read as a deliberate table.

    A single marked line is never a table.

    .. note::

       This reads the columns as they stand *after* line breaking, which is an
       approximation of the columns the author wrote. It is exact whenever the
       cells before the stop were not themselves re-laid-out, which is the
       common case for trailing comments and declaration bodies. The trivia
       map records true original columns, and this function should take those
       instead once the pipeline threads them through.
    """
    if len(members) < 2:
        return False

    ncols = min(len(parsed[i].cells) for i in members)
    if ncols < 2:
        return False

    any_padding = False
    for col in range(1, ncols):
        columns = set()
        for i in members:
            p = parsed[i]
            reached = sum(width_of(c) for c in p.cells[:col]) + sum(p.pads[: col - 1])
            columns.add(reached + p.pads[col - 1])
            if p.pads[col - 1] > _DEFAULT_MIN_SPACING:
                any_padding = True
        if len(columns) != 1:
            return False
    return any_padding


def _column_targets(
    parsed: Sequence[_Line], members: Sequence[int], min_spacing: int
) -> List[int]:
    """Left-to-right column positions for each stop in the group.

    Computed cumulatively: column *n*'s target depends on where column *n-1*
    put every member, so a wide cell early in the group pushes every later
    column right for all of its members. Lines with fewer stops than the group
    simply drop out of the later columns.
    """
    ncols = max(len(parsed[i].cells) for i in members)
    targets = [0] * ncols
    running = {i: width_of(parsed[i].cells[0]) for i in members}

    for col in range(1, ncols):
        participants = [i for i in members if col < len(parsed[i].cells)]
        if not participants:
            continue
        target = max(running[i] + min_spacing for i in participants)
        targets[col] = target
        for i in participants:
            running[i] = target + width_of(parsed[i].cells[col])
    return targets


def _emit_with_targets(p: _Line, targets: Sequence[int], min_spacing: int) -> str:
    parts = [p.cells[0]]
    col = width_of(p.cells[0])
    for idx in range(1, len(p.cells)):
        pad = max(targets[idx] - col, min_spacing)
        parts.append(" " * pad)
        parts.append(p.cells[idx])
        col = (col + pad) + width_of(p.cells[idx])
    return "".join(parts)


def _emit_flush_left(
    parsed: Sequence[_Line], members: Sequence[int], min_spacing: int, out: List[str]
) -> None:
    pad = " " * min_spacing
    for i in members:
        p = parsed[i]
        parts = [p.cells[0]]
        for cell in p.cells[1:]:
            parts.append(pad)
            parts.append(cell)
        out[i] = "".join(parts)

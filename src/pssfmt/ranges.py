"""``P4-4`` -- formatting part of a file, and the edits that describes.

``--lines A:B`` formats the named lines and leaves the rest of the file
byte-for-byte alone. ``formatter.md`` section 8.4 asks for this first and then
derives the rest from it, because LSP ``rangeFormatting``, a
``clang-format-diff``-style "only what I changed" mode and minimal
``TextEdit[]`` output are the same machinery wearing three interfaces.

The whole file is formatted regardless
--------------------------------------
Formatting a *range* by parsing only that range is a different and much worse
program: a line range is not a syntactic unit, so it has no tree, and the
indentation it should get is a fact about ancestors that lie outside it. So
the file is formatted whole, and this module decides how much of the result to
keep. The cost is that a huge file is formatted to change three lines of it;
section 6 measures layout in microseconds and that trade is not close.

What an edit is, and why it is not a diff hunk
----------------------------------------------
Keeping "the part of the output that covers lines A to B" only means anything
if the output can be *cut* at a line boundary without cutting through a token.
The obvious implementation asks :mod:`difflib` for hunks and keeps the ones
that overlap the range. That is wrong, and not marginally:

    92 corpus files x 24 styles produce 11400 ``difflib`` hunks, and **5768 of
    them are not whitespace-only** -- their original lines and their
    replacement lines do not contain the same non-whitespace characters.

``difflib`` matches *lines*, and a closing ``}`` on its own line is identical
to every other closing ``}`` on its own line. When the line count shifts, it
happily pairs one with another, and the hunk on either side of that pairing
then straddles real code. Splicing such a hunk in on its own moves tokens
into or out of the file. ``P4-4`` asked for an assertion that this never
happens on the grounds that the token-preserving architecture guarantees it;
the guarantee is real but it is **whole-file**, and it does not survive being
cut into hunks by something that does not know what a token is.

So the cut points are computed rather than assumed. Because the formatter
preserves tokens, the file with every whitespace character removed is
*invariant*: ``nows(input) == nows(output)``. Number the line boundaries of
each side by how many non-whitespace characters precede them, and a boundary
pair ``(i, j)`` with the same count is a point where both sides have emitted
exactly the same text so far -- equal-length prefixes of one string are the
same prefix. Cutting there is safe, and cutting anywhere else is not.

The edits between consecutive cut points are therefore **whitespace-only by
construction**: same non-whitespace characters in, same ones out. That is the
property ``P4-4`` wanted asserted, obtained by making it true instead of by
hoping and crashing. :func:`edits` is O(lines) and uses no heuristics.

Where a range cannot be honoured exactly
----------------------------------------
An edit is atomic. If lines 10-20 are asked for and one edit spans 8-25 --
because the formatter moved something across the boundary and the two sides
only re-synchronise at line 25 -- the whole edit is applied. That is the safe
direction and it is also the only sensible one: half a reflowed expression is
not a smaller change than all of it, it is a broken file.

What is deliberately not here
-----------------------------
There is no ``TextEdit`` type and no offset-based edit list, though this is
where they will go. Nothing consumes them yet: ``--lines`` needs whole text,
and the LSP server that needs ``TextEdit[]`` is ``P4-6``. An exported type
with no caller is an untested promise, which is the thing ``P4-2`` spent an
afternoon learning not to make. :func:`edits` already returns the line spans
they will be built from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

__all__ = ["RangeError", "LineRange", "Edit", "parse_range", "parse_ranges",
           "edits", "restrict"]


class RangeError(ValueError):
    """A ``--lines`` argument that is not a usable range."""


@dataclass(frozen=True)
class LineRange:
    """An inclusive, 1-based line range, in the coordinates of the **input**.

    1-based and inclusive because that is what every editor, every compiler
    diagnostic and ``clang-format --lines`` mean by a line number, and a
    formatter that quietly used a different convention would be off by one in
    a way whose symptom is "it formatted the wrong function".
    """

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 1:
            raise RangeError("line numbers start at 1, got %d" % self.start)
        if self.end < self.start:
            raise RangeError("range %d:%d ends before it starts"
                             % (self.start, self.end))


def parse_range(spec: str) -> LineRange:
    """Parse one ``A:B``.

    Strict on purpose. A lenient parser here turns a typo into a silently
    different range, and the whole reason ``--lines`` was refused rather than
    ignored in ``P4-1`` is that a wrong range is invisible in the output.
    """
    # No separate "there is no colon" branch: `"12".partition(":")` leaves an
    # empty tail, and `int("")` raises, so the check below already covers it
    # with the same message. The explicit branch was written first and the
    # mutation run found it unreachable -- two ways to reach one diagnostic is
    # one way too many.
    head, _, tail = spec.strip().partition(":")
    try:
        start, end = int(head.strip()), int(tail.strip())
    except ValueError:
        raise RangeError("expecting a range like 12:34, got %r" % spec) from None
    return LineRange(start, end)


def parse_ranges(specs: Iterable[str]) -> Tuple[LineRange, ...]:
    """Parse every ``--lines`` argument. They union; they need not be sorted
    and they may overlap, because a caller assembling them from a diff has no
    reason to tidy them first."""
    return tuple(parse_range(s) for s in specs)


@dataclass(frozen=True)
class Edit:
    """One atomic change: replace input lines ``[start:stop)`` with output
    lines ``[new_start:new_stop)``. Half-open and 0-based -- these are list
    indices, not line numbers, and mixing the two conventions in one module is
    how off-by-ones get written."""

    start: int
    stop: int
    new_start: int
    new_stop: int


def _squeezed(lines: Sequence[str]) -> Tuple[str, List[int]]:
    """The text with all whitespace removed, and where each line boundary
    falls in it. The count list is ``len(lines) + 1`` long.

    ``str.split`` is the whitespace definition rather than a hand-written set,
    so it covers ``\\r`` -- which matters, since ``line_ending`` conversion is
    a legitimate output difference and rewrites bytes inside multi-line
    comment and template tokens.
    """
    parts: List[str] = []
    counts = [0]
    total = 0
    for line in lines:
        for piece in line.split():
            parts.append(piece)
            total += len(piece)
        counts.append(total)
    return "".join(parts), counts


def edits(before: Sequence[str], after: Sequence[str]) -> Tuple[Edit, ...]:
    """The atomic differences between two line lists.

    :raises RangeError: if the two sides do not contain the same
        non-whitespace characters. Every caller here has already run the
        verifier, so this cannot fire on a verified format -- it is the
        precondition stated out loud rather than assumed, because everything
        below it is only sound while it holds.
    """
    # The *characters* are compared and not just how many there are. Equal
    # counts on two different strings would make every cut point a lie, and
    # the whole construction rests on "equal-length prefixes of one string are
    # the same prefix" -- which needs there to be one string.
    sa, ca = _squeezed(before)
    sb, cb = _squeezed(after)
    if sa != sb:
        raise RangeError("the two texts do not contain the same "
                         "non-whitespace characters; a range cannot be "
                         "applied to them")

    found: List[Edit] = []
    i = j = 0
    # `ca[i] == cb[j]` at the top of every iteration: it holds at the start,
    # the fast path advances both sides by one identical line, and the inner
    # loop below exits on exactly that condition. Everything here is sound
    # only while it does, which is why it is written down.
    while i < len(before) or j < len(after):
        if i < len(before) and j < len(after) and before[i] == after[j]:
            # An identical line at a synchronised boundary is not an edit.
            i, j = i + 1, j + 1
            continue
        start, new_start = i, j
        # Consume at least one line, then advance the side that is behind
        # until the boundaries agree again. One index moves per iteration, so
        # this terminates; and it always can, because the totals are equal.
        #
        # Which side takes that first step decides how *narrow* the edit
        # comes out. A line carrying no code -- a blank one being inserted or
        # removed -- resynchronises immediately, so stepping it alone gives a
        # one-line edit; stepping the other side first drags the following
        # line of real code into the edit for no reason, and a range naming
        # only that line would then reformat its neighbour too.
        blank_before = i < len(before) and ca[i + 1] == ca[i]
        blank_after = j < len(after) and cb[j + 1] == cb[j]
        if blank_after and not blank_before:
            j += 1
        elif i < len(before):
            i += 1
        else:
            j += 1
        while ca[i] != cb[j]:
            if i == len(before):
                j += 1
            elif j == len(after):
                i += 1
            elif ca[i] < cb[j]:
                i += 1
            else:
                j += 1
        found.append(Edit(start, i, new_start, j))
    return tuple(found)


def _selected(edit: Edit, ranges: Sequence[LineRange]) -> bool:
    """Does *edit* fall inside any requested range?

    An edit that deletes nothing -- pure insertion -- has no lines of its own
    to intersect, so it is taken when it sits *against* a requested line. A
    blank line the formatter wants to insert before a member you asked to
    format is part of formatting that member.
    """
    for r in ranges:
        lo, hi = r.start - 1, r.end          # 0-based, half-open
        if edit.start == edit.stop:
            if lo <= edit.start <= hi:
                return True
        elif edit.start < hi and edit.stop > lo:
            return True
    return False


def restrict(source: str, formatted: str,
             ranges: Sequence[LineRange]) -> str:
    """*formatted* where *ranges* say so, *source* everywhere else.

    With ranges covering the whole file this returns *formatted* exactly, and
    with no ranges it returns *source* exactly. Both are tested, and the first
    is the useful one: it makes ``--lines 1:N`` and a plain format the same
    operation, so the range machinery is checked against the formatter itself
    on every file rather than against hand-written expectations.
    """
    before = source.splitlines(keepends=True)
    after = formatted.splitlines(keepends=True)

    out: List[str] = []
    cursor = 0
    for edit in edits(before, after):
        # The run between two edits is byte-identical on both sides -- that is
        # what made it not an edit -- so which side it is copied from cannot
        # matter. Taking it from `before` says the right thing about intent:
        # unselected text is the user's, untouched.
        out.extend(before[cursor:edit.start])
        if _selected(edit, ranges):
            out.extend(after[edit.new_start:edit.new_stop])
        else:
            out.extend(before[edit.start:edit.stop])
        cursor = edit.stop
    out.extend(before[cursor:])
    return "".join(out)

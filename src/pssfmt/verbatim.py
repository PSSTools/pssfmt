"""Regions the formatter copies rather than composes -- ``P3-8``, § 4.3.

A target-template ``exec`` body is not PSS. It is C, or SystemVerilog, or
whatever the target consumes, carried inside a PSS file as a string::

    exec body C = \"\"\"
        func_{{func_id}}({{arg}});
    \"\"\";

``formatter.md`` section 4.3 calls these *sacred*: emit them byte-for-byte,
and **do not touch the interior at all in v1**. Leading whitespace is
semantic in some target languages, trailing whitespace is part of the string,
and the mustache elements carry offsets into the raw text that only stay
valid if the raw text does not move.

Why there is no rule registered for them
----------------------------------------
Because there does not need to be, and adding one would be worse than not.

``pssfmt``'s unhandled path is not a stub: a node with no builder is emitted
as the author wrote it, byte for byte (see :mod:`pssfmt.rules`). A target
template therefore already gets exactly the treatment section 4.3 asks for,
and a builder returning ``ctx.verbatim(node)`` would be a second way of
saying the same thing -- one that no test could distinguish from the first,
because both produce identical bytes. ``P3-7`` deleted a guard of exactly that
shape after mutation testing showed it and the check it duplicated each kept
the other alive. The lesson generalises: a safeguard that cannot fail on its
own is not a safeguard, it is a comment that costs a rebuild.

What the interior *is* protected by is narrower and testable:
:func:`pssfmt.rules.emit.is_reindentable` refuses to re-anchor any span
holding a token whose own content spans lines, so the one transformation that
could reach inside a multi-line string is declined at the point it would
happen. ``T-27`` pins that from the outside, in bytes.

The visible cost, and why it is the right one
----------------------------------------------
A file containing a target template cannot be fully re-indented. Change
``indent_width`` and the ``exec body C = \"\"\"`` line moves with its siblings
while the interior and the closing ``\"\"\"`` stay in the columns the author
wrote, because those columns are inside the token and are part of the string's
value. The output looks ragged; the alternative is emitting a different
program. Section 4.3 already chose, and this module records that the raggedness
is the choice rather than an oversight.

What this module is for
-----------------------
One question, asked by anything that wants to make a claim about the
formatter's output: **which lines did the formatter not choose?** The style
properties in ``docs/style.rst`` -- no trailing whitespace, no tab
indentation, no brace alone on a line -- are claims about gaps ``pssfmt``
decided. Applied to a copied region they are claims about somebody else's C,
and enforcing them there would require the corruption section 4.3 forbids.

``P3-9`` needs the same notion for ``// pssfmt off``, which marks a token
range verbatim for a different reason and with identical consequences.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import (Any, FrozenSet, List, Optional, Sequence, Set, Tuple,
                    Union)

__all__ = [
    "verbatim_lines",
    "DIRECTIVES",
    "directive_of",
    "Hatches",
    "NO_HATCHES",
    "scan_hatches",
]

#: The three directives, exactly as section 5.3 spells them. Nothing else is
#: one: see :func:`directive_of` on why the match is this strict.
DIRECTIVES = ("off", "on", "ignore")


def directive_of(comment: str) -> Optional[str]:
    """The directive *comment* is, or ``None`` if it is an ordinary comment.

    Both comment syntaxes carry a directive -- ``// pssfmt off`` and
    ``/* pssfmt off */`` -- because a user who wants one mid-line has only the
    second, and a hatch that exists in one syntax is a hatch people file bugs
    about.

    The match is **exact**: the comment's entire body, markers and surrounding
    whitespace removed, must be ``pssfmt`` followed by one of
    :data:`DIRECTIVES`. Nothing else counts, and the reason is a hazard rather
    than fastidiousness. ``// we should turn pssfmt off for this table`` is
    prose about the formatter, written by someone describing a problem, and a
    substring match would answer it by silently disabling the formatter over
    the rest of the file. Prose mentioning the tool is far more common than
    directives, so the permissive reading is wrong on the common case.

    The cost is that ``// pssfmt: off`` and ``// pssfmt off!`` are plain
    comments, silently. That is the wrong side to be wrong on, but it *is* a
    wrong side, and ``P3-9b`` is the note to report unrecognised ``pssfmt``
    comments once there is a diagnostics channel to report them on.
    """
    body = comment.strip()
    if body.startswith("//"):
        body = body[2:]
    elif body.startswith("/*") and body.endswith("*/"):
        body = body[2:-2]
    else:
        return None
    parts = body.split()
    if len(parts) != 2 or parts[0] != "pssfmt" or parts[1] not in DIRECTIVES:
        return None
    return parts[1]


@dataclass(frozen=True)
class Hatches:
    """Which code positions the author has told the formatter to leave alone.

    Positions are indices into ``TriviaMap.code_indices`` -- the same currency
    every rule already works in -- rather than token indices or character
    offsets, so a caller holding a member's span can ask directly.

    Two kinds, kept apart because they are resolved at different times.
    :attr:`ranges` are settled by the scan: ``off`` and ``on`` are token
    positions and need no tree. :attr:`ignores` are *anchors* only -- "the
    construct starting here" is a question about the tree, and the scan has
    none, so the anchor is recorded and the answer is left to whoever is
    holding the construct.
    """

    #: Inclusive ``(first, last)`` code-position ranges under ``off``.
    ranges: Tuple[Tuple[int, int], ...] = ()
    #: Code positions at which ``ignore`` was seen.
    ignores: FrozenSet[int] = frozenset()

    def __bool__(self) -> bool:
        return bool(self.ranges or self.ignores)

    def region_of(self, first: int, last: int) \
            -> Optional[Union[int, Tuple[str, int]]]:
        """An identity for the hatch covering ``first..last``, or ``None``.

        Two spans with the same non-``None`` identity are inside one hatch and
        may be reproduced as a single block; two with different identities are
        separate hatches even if adjacent. Callers use it for both questions,
        which is why it returns a key rather than a boolean.

        Three ways a span can meet a range, and only one of them is not a
        hatch:

        **Inside it** -- the ordinary case, and the answer is the range.

        **Straddling one of its ends** -- also the range. A construct half
        inside a hatch cannot be half formatted, and over-freezing is the
        direction that cannot corrupt anything.

        **Containing it** -- ``None``, and this is the case that makes the
        rest work. A ``component`` whose body holds a hatch *overlaps* that
        hatch, and freezing on overlap alone freezes the component, then the
        file. The enclosing construct is not what the author switched off; it
        is what the author expects to be formatted *around* the part they
        did. So a span strictly containing a range is recursed into, and the
        hatch is found again at the level it was actually written at.
        """
        if first in self.ignores:
            return ("ignore", first)
        for i, (lo, hi) in enumerate(self.ranges):
            if lo <= first and last <= hi:
                return i
            if first <= lo and hi <= last:
                continue
            if first <= hi and last >= lo:
                return i
        return None


#: The answer for a file with no directives in it, shared so the common path
#: allocates nothing.
NO_HATCHES = Hatches()


def scan_hatches(trivia: Any) -> Hatches:
    """Resolves the directives in *trivia* to protected code positions.

    A directive takes effect **where it is written**, which the trivia map has
    already worked out: a leading comment of the token at *p* applies from
    *p*, and a trailing comment of *p* applies from *p+1*. That is the whole
    of the placement logic, and it falls out of section 3.1's attachment rule
    rather than being a second rule invented here.

    The malformed cases all resolve to *less* protection than the author asked
    for or *more*, never to a crash, and each is a deliberate choice:

    ``off`` with no ``on``
        Protects to the end of the file. The alternative -- treating it as
        unmatched and formatting everything -- reformats precisely the region
        someone was trying to protect, which is the worst available answer.
    ``on`` with no ``off``
        Ignored. There is nothing to close.
    ``off`` inside an ``off``
        Ignored; the first ``on`` closes the region. Nesting would mean
        counting depth, and a depth counter turns one forgotten ``on`` into a
        file that is silently never formatted again -- the same failure as the
        unmatched case, but arrived at invisibly.
    ``off`` immediately followed by ``on``
        No range. An empty region protects nothing, and recording it would put
        a zero-width entry in front of every later overlap test.
    ``ignore`` inside an ``off`` region
        Recorded anyway, even though the range already covers it. Protection
        is a union, so the anchor is redundant rather than wrong -- and
        suppressing it would be a branch whose only effect is to make the
        result depend on directive order.

    Directives after the last code token are not seen at all, which is correct
    rather than a limitation: they have nothing to apply to. The exception is
    a trailing directive on the *last* code token, which resolves to an anchor
    one past the end -- harmless, because no span starts there, and left
    unguarded on purpose. A guard that cannot fire is one nothing can test,
    and an untestable guard is how a real one gets deleted later without
    anything failing.
    """
    code = trivia.code_indices
    n = len(code)
    ranges: List[Tuple[int, int]] = []
    ignores: Set[int] = set()
    open_at: Optional[int] = None

    def apply(verb: str, at: int) -> None:
        nonlocal open_at
        if verb == "off":
            if open_at is None:
                open_at = at
        elif verb == "on":
            if open_at is not None:
                if at - 1 >= open_at:
                    ranges.append((open_at, at - 1))
                open_at = None
        else:
            ignores.add(at)

    def scan(comments: Sequence[Any], at: int) -> None:
        for comment in comments:
            verb = directive_of(comment.text)
            if verb is not None:
                apply(verb, at)

    for pos in range(n):
        entry = trivia.of(code[pos])
        # Leading first, then trailing: that is stream order, and stream order
        # is what makes ``off`` on one line and ``on`` on the next pair up.
        scan(entry.leading, pos)
        scan(entry.trailing, pos + 1)

    if open_at is not None and open_at < n:
        ranges.append((open_at, n - 1))

    if not ranges and not ignores:
        return NO_HATCHES
    return Hatches(ranges=tuple(ranges), ignores=frozenset(ignores))


def verbatim_lines(text: str, tree: Optional[Any] = None) -> Set[int]:
    """1-based line numbers in *text* the formatter copied rather than composed.

    Two sources, and they are separate facts about the same output.

    A line **inside a single token** is one the formatter cannot have
    composed: every character on it came out of one token's text, so there is
    no gap on it that any style decided. Multi-line string literals are the
    case that matters -- target templates above all -- and multi-line block
    comments fall out of the same rule for the same reason.

    A line **inside a ``pssfmt off`` region** is one the formatter was told
    not to compose. The bytes there are the author's, and every claim the tool
    makes about its own output is a claim about gaps it chose -- so a style
    property asserted over a hatch would be asserting that the author's hand
    alignment obeys the formatter's rules, which is the one thing a hatch
    exists to permit. The two directive lines themselves are included, since
    the region's first line is re-anchored by the enclosing block and so is
    not wholly the formatter's either (see ``docs/style.rst``).

    ``pssfmt ignore`` is **not** exempted here, and the reason is that its
    extent is a fact about the tree while this function has only lines. One
    ignored construct's worth of hand alignment can therefore still trip a
    style gate. Recorded rather than papered over: ``P3-9c``.

    The line the token *starts* on is excluded, and deliberately. That line
    holds whatever preceded the token (``exec body C = ``) and its indentation
    is the layout engine's, so the style does apply to it. Only the lines the
    token continues onto are foreign.

    A token's own trailing newlines do not count as spanning lines: a ``//``
    comment carries its line terminator, and that is a terminator rather than
    content on the line below. This is the same exclusion, for the same
    reason, that :func:`pssfmt.rules.emit._has_multiline_payload` makes -- and
    the two are separate because they answer different questions about the
    same fact, one before formatting and one after.

    *tree* is an already-parsed :class:`Cst` for *text*, for callers that have
    one. Parsing is the only way to ask this question honestly: scanning for
    ``\"\"\"`` would be a second, worse lexer, and it would be wrong about a
    ``\"\"\"`` inside a comment.
    """
    if tree is None:
        from pssparser import cst as _cst
        tree = _cst.parse(text)
    last_line = len(text.splitlines())
    lines: Set[int] = set()
    hatch_from: Optional[int] = None
    for token in tree.tokens:
        if not token.text.strip():
            continue
        spanned = token.text.rstrip("\n").count("\n")
        if spanned:
            lines.update(range(token.line + 1, token.line + spanned + 1))
        # No ``is_comment`` test: ``directive_of`` already requires a comment
        # opener, and only a comment token's text can start with one -- a
        # string literal's text begins at its quote. The check that reads as
        # defence in depth is a second copy of the same question.
        verb = directive_of(token.text)
        if verb == "off":
            if hatch_from is None:
                hatch_from = token.line
        elif verb == "on" and hatch_from is not None:
            lines.update(range(hatch_from, token.line + 1))
            hatch_from = None
    if hatch_from is not None:
        lines.update(range(hatch_from, last_line + 1))
    return lines

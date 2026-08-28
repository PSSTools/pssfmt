"""Turning a stretch of original source into a Layout a rule can place.

``P3-1`` deliberately shipped without this. Its fallback emitted a node as
:class:`~pssfmt.layout.ir.Verbatim` -- byte-exact, and *fixed*: Verbatim keeps
its own newlines and its own indentation, because the node behind it exists
for ``exec`` target templates whose interior must not move. That is correct
for a formatter that changes nothing, and useless the moment a rule wants to
put a member at a different indentation than the author did.

So there are two ways to reproduce text you have no rule for, and the
difference is whether you are moving it:

:func:`verbatim_layout`
    unchanged, including its indentation. For text that must not move.
:func:`reindented_layout`
    unchanged *relative to itself*, re-anchored to whatever column the
    enclosing :class:`~pssfmt.layout.ir.Indent` puts it at. Every line after
    the first keeps its offset from the block's original start column.

What is never re-indented
-------------------------
A span containing a token whose own text spans lines is emitted verbatim
instead, because moving it would edit a payload rather than a layout:

* a **triple-quoted string** -- an ``exec`` target template body. Its content
  is C or SystemVerilog that PSS is merely carrying, and re-indenting it
  changes the generated string. That is a semantic change (section 4.7.1.2),
  not a cosmetic one, and it is the reason this check exists at all.
* a **block comment** -- which may hold an ASCII diagram, a table, or a
  licence header. ``docs/style.rst`` commits to never reflowing comment
  interiors, and shifting the continuation lines of a box-drawn comment
  breaks it just as thoroughly as rewrapping it would.

Note that a ``//`` comment token carries its own trailing newline, so the
test is for a newline with text after it, not for any newline at all. Getting
that wrong bails out of re-indentation for every line comment in the corpus,
silently, and the output still looks right.

Tabs are also a bail-out. Re-anchoring means counting columns, a tab's width
is a display setting rather than a fact about the file, and the corpus
contains no indented tab at all -- so the case is unreachable in practice and
guessing at it would be worse than declining.
"""

from __future__ import annotations

import bisect
from typing import Any, List, Optional, Sequence, Tuple

from ..layout import HARDLINE, Layout, Verbatim, join, text
from ..layout.ir import HardLine
from ..trivia import TriviaMap

__all__ = [
    "code_span",
    "span_tokens",
    "span_text",
    "block_of",
    "verbatim_layout",
    "reindented_layout",
    "is_reindentable",
    "reindent",
    "hardline",
]


def code_span(trivia: TriviaMap, node: Any) -> Optional[Tuple[int, int]]:
    """Positions in ``trivia.code_indices`` covered by *node*, inclusive.

    ``start_token`` and ``stop_token`` are stream indices, and a stream index
    need not be a code token. Widening *inwards* -- first code token at or
    after the start, last at or before the stop -- keeps the span within the
    node even when the parser's bounds land on trivia. A span that leaked
    outwards would emit a neighbouring construct's tokens a second time, and
    no corpus file would notice, because no node the parser produces has
    bounds on trivia.
    """
    start = getattr(node, "start_token", None)
    stop = getattr(node, "stop_token", None)
    if start is None or stop is None or start < 0 or stop < start:
        return None
    code = trivia.code_indices
    first = bisect.bisect_left(code, start)
    last = bisect.bisect_right(code, stop) - 1
    if first > last or first >= len(code) or last < 0:
        return None
    return first, last


def span_tokens(trivia: TriviaMap,
                first: int,
                last: int,
                *,
                leading: bool = True,
                trailing: bool = True) -> Tuple[Any, ...]:
    """Every token in the span, trivia included, in stream order.

    Reconstructed from the trivia map rather than sliced out of the stream by
    index, because the map is a proven partition (``P1-1``) and this is the
    same walk the null formatter makes -- so the two cannot drift.

    *leading* excludes the first code token's leading run, which is where a
    member's original indentation lives: a caller that is about to re-anchor
    the block does not want the old anchor coming along with it.
    """
    out: List[Any] = []
    for pos in range(first, last + 1):
        entry = trivia.of(trivia.code_indices[pos])
        if leading or pos != first:
            out.extend(entry.raw_leading)
        out.append(entry.token)
        if trailing or pos != last:
            out.extend(entry.raw_trailing)
    return tuple(out)


def span_text(trivia: TriviaMap,
              first: int,
              last: int,
              *,
              leading: bool = True,
              trailing: bool = True) -> str:
    """:func:`span_tokens`, concatenated."""
    return "".join(
        tok.text
        for tok in span_tokens(trivia, first, last, leading=leading,
                               trailing=trailing))


def block_of(trivia: TriviaMap, first: int, last: int) -> Tuple[Tuple[Any, ...], int]:
    """A member's own tokens, and the blank lines separating it from the last.

    A member owns its **own-line leading comments**: they were written above
    it, they describe it, and a rule that emitted them separately would have
    to decide where the blank line between comment and code went. Keeping the
    block together answers that by not asking -- everything from the first
    leading comment onwards is reproduced exactly, and only the whitespace
    *before* the block is a layout decision.

    Returns the block's tokens and the number of blank lines preceding it,
    unclamped. Clamping is the caller's, because ``max_blank_lines`` is a
    style question and this module does not read style.
    """
    entry = trivia.of(trivia.code_indices[first])
    lead = entry.raw_leading

    start = len(lead)
    for i, tok in enumerate(lead):
        if tok.is_comment:
            start = i
            break

    separator = "".join(tok.text for tok in lead[:start])
    blanks = max(0, separator.count("\n") - 1)

    body = list(lead[start:])
    body.extend(span_tokens(trivia, first, last, leading=False))
    return tuple(body), blanks


def _has_multiline_payload(tokens: Sequence[Any]) -> bool:
    """True if any token's own *content* spans lines.

    Two exclusions, and both were bugs before they were exclusions -- each
    silently disabling re-anchoring, which leaves the output correct-looking
    and merely never re-indented:

    * **Whitespace is skipped.** The newlines between a member's lines live in
      whitespace tokens, and they are precisely what re-anchoring rewrites.
      Counting them marks every multi-line member immovable, which is to say
      almost every member there is.
    * **A trailing newline does not count.** A ``//`` comment token carries
      its own line terminator; that is a terminator, not content on the line
      below.
    """
    for tok in tokens:
        if not tok.text.strip():
            continue
        if "\n" in tok.text.rstrip("\n"):
            return True
    return False


def is_reindentable(tokens: Sequence[Any], body: str) -> bool:
    """Whether *body* may be re-anchored to a different column.

    Two refusals, and the second is broader than it first needs to be.

    A **multi-line payload** cannot move because the newlines inside a token
    are the token's, not the layout's -- see :func:`_has_multiline_payload`.

    A **tab anywhere** cannot move for two reasons that happen to coincide.
    :func:`reindent` strips leading *spaces* and would silently leave a
    tab-indented line where it was while its siblings moved; and the lines
    this function green-lights become :class:`~pssfmt.layout.ir.Text` nodes,
    which the engine measures with :func:`~pssfmt.layout.width.width_of`, and
    which refuses a tab outright. That refusal is correct -- a tab in composed
    text means a rule wrote one -- but these lines are *not* composed, they
    are the author's bytes being carried, so the answer is to stop calling
    them composed rather than to weaken the check.

    ``P3-8`` widened this from "a tab in the indentation of a continuation
    line" to "a tab at all", because the narrow version let a one-line
    declined construct holding a tab through -- ``c : coverpoint\\tx;`` --
    and it reached ``width_of`` as ``Text`` and aborted the render. The
    corpus has 0 tabs in 4856 lines and could not have shown it. The cost of
    the wider rule is that such a body keeps the column the author gave it,
    which is what declining has always meant here.
    """
    return not _has_multiline_payload(tokens) and "\t" not in body


def reindent(body: str, origin: int) -> List[str]:
    """Lines of *body*, with each line after the first dedented by *origin*.

    *origin* is the column the block started at in the original file. Removing
    exactly that much leading space -- never more -- turns absolute columns
    into offsets from the block, which the enclosing ``Indent`` then re-anchors
    wherever the layout puts it. Relative structure inside the block is
    untouched, which is the whole contract.
    """
    lines = body.split("\n")
    out = [lines[0]]
    for line in lines[1:]:
        indent_len = len(line) - len(line.lstrip(" "))
        out.append(line[min(indent_len, origin):])
    return out


def verbatim_layout(body: str) -> Layout:
    """*body* exactly, including its own indentation. Never re-anchored."""
    return Verbatim(body)


def reindented_layout(tokens: Sequence[Any], body: str, origin: int) -> Layout:
    """*body* as lines the engine will indent, or verbatim if it must not move.

    The verbatim fall-through is not a failure: it is a span the formatter has
    decided it is not entitled to move, and emitting it where the author put it
    is the only answer that cannot corrupt anything.
    """
    if not is_reindentable(tokens, body):
        return verbatim_layout(body)
    lines = reindent(body, origin)
    if len(lines) == 1:
        return text(lines[0])
    return join(HARDLINE, [text(line) for line in lines])


def hardline(blank_before: int = 0) -> Layout:
    """A break, optionally preceded by blank lines."""
    return HARDLINE if blank_before == 0 else HardLine(blank_before=blank_before)

"""Comment attachment -- ``P1-1``, implementing ``formatter.md`` section 3.1.

This is the module ``formatter.md`` calls out as *"the part that must be nailed
down first, because everything downstream inherits its bugs"*. It answers one
question: given a lossless token stream, which code token does each comment
belong to, and how much vertical space did the author leave around it?

The rule
--------
Verbatim from section 3.1, in the order it is applied:

1. A comment on the **same line as, and after,** a preceding token is a
   **trailing** comment of that token.
2. Otherwise it is a **leading** comment of the next default-channel token.
3. ``blank_lines_before`` is the number of blank lines immediately preceding
   the token's leading-comment block, clamped to ``max_blank_lines`` (default
   1). Preserving *whether* the author left a blank line but not how many is
   the gofmt behaviour, and it is correct.
4. A comment with no following default-channel token, or with no meaningful
   anchor (``{ /* nothing else */ }``), is **dangling** and owned by the
   enclosing CST node.

Rule 1 is applied literally, which has one consequence worth stating out loud:
in ``f(/* name */ x)`` the comment is *trailing* on ``(``, not leading on
``x``, because it is on the same line as a preceding token. Every same-line
comment attaches backwards. That is what section 3.1 specifies and what
clang-format does; a rule builder that wants "the comment just before ``x``"
must look at the trailing block of the token before it, and
:meth:`TriviaMap.comment_before` exists so it does not have to know that.

Losslessness
------------
The map is an **exhaustive partition** of the token stream. Every token is in
exactly one of: a token's raw trailing run, a token's raw leading run, the
default-channel tokens themselves, or the end-of-file dangling run -- and the
partition is in stream order. That is what lets ``P1-2`` reproduce a file byte
for byte by walking this structure rather than by concatenating the stream, and
it is checked as an invariant rather than assumed.

The ``raw_*`` runs carry whitespace, error and byte-order-mark tokens as well
as comments. :attr:`Trivia.leading` and :attr:`Trivia.trailing` are the
*semantic* view -- comments only, with their vertical spacing already computed.
A style rule wants the semantic view; the null formatter wants the raw one.

Newlines are LF
---------------
Blank-line counts come from counting ``\\n`` in source text, matching how the
lexer assigns line numbers. Under lone-CR line endings the whole file is one
line to both, so nothing here disagrees with a token's ``line`` attribute; it
is uniformly blind in the same way. See ``PLAN.md`` R10's neighbours in the
"Known lexer behavior" section of the pssparser docs.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from pssparser.tokens import CHANNEL_DEFAULT

__all__ = [
    "DEFAULT_MAX_BLANK_LINES",
    "Comment",
    "Trivia",
    "TriviaMap",
]

#: Section 3.1's default clamp: keep at most one blank line.
DEFAULT_MAX_BLANK_LINES = 1


@dataclass(frozen=True)
class Comment:
    """A comment token together with how the author placed it.

    The placement fields are what a style rule needs and what a raw token
    cannot answer on its own, because both depend on the text *between*
    tokens.
    """

    #: The ``SL_COMMENT`` or ``ML_COMMENT`` token, text exactly as written.
    token: Any

    #: Blank lines between this comment and whatever precedes it, clamped.
    blank_lines_before: int

    #: True when nothing but whitespace precedes this comment on its line.
    #: An own-line comment is indented with the code that follows it; a
    #: same-line one keeps its position relative to the code before it.
    own_line: bool

    @property
    def text(self) -> str:
        return self.token.text

    @property
    def is_block(self) -> bool:
        """True for ``/* ... */``, false for ``//``.

        Worth distinguishing because a ``//`` comment **contains its own
        trailing newline** while a block comment does not. A rule that emits
        comment text and then adds a line break doubles it for the first kind.
        """
        return not self.token.text.startswith("//")


@dataclass(frozen=True)
class Trivia:
    """Everything attached to one default-channel token."""

    #: The code token this trivia belongs to. ``None`` for the end-of-file
    #: entry, which has no anchor -- that is what makes it dangling.
    token: Optional[Any]

    #: Comments before the token that are not trailing anything else.
    leading: Tuple[Comment, ...] = ()

    #: Comments on the same line as, and after, the token.
    trailing: Tuple[Comment, ...] = ()

    #: Blank lines before the leading block, or before the token when the
    #: leading block is empty. Clamped to ``max_blank_lines``.
    blank_lines_before: int = 0

    #: The unclamped count, for a caller that wants to know what was thrown
    #: away -- ``--explain`` (``P4-5``) reports it.
    raw_blank_lines_before: int = 0

    #: Every token preceding this one that no earlier token claimed, in
    #: stream order, whitespace included. The null formatter's input.
    raw_leading: Tuple[Any, ...] = ()

    #: Every token following this one up to and including its last same-line
    #: comment, in stream order.
    raw_trailing: Tuple[Any, ...] = ()

    @property
    def is_dangling(self) -> bool:
        """True for the end-of-file entry: comments with nothing to attach to.

        The *other* dangling case from section 3.1 -- a comment alone in an
        empty block -- is not visible from the token stream, because ``}`` is
        a perfectly good following token. Resolving it needs the tree; see
        :meth:`TriviaMap.dangling_between`.
        """
        return self.token is None

    @property
    def has_comments(self) -> bool:
        return bool(self.leading or self.trailing)


class TriviaMap:
    """The section 3.1 attachment, computed once for a token stream.

    Construct it from a :class:`pssparser.tokens.TokenStream`::

        ts = tokens.tokenize(src)
        tm = TriviaMap(ts)
        tm.of(some_code_token).leading

    Lookups are by stream index, which is what a CST terminal carries, so a
    tree walk needs no side table.
    """

    def __init__(self, stream: Any,
                 max_blank_lines: int = DEFAULT_MAX_BLANK_LINES) -> None:
        if max_blank_lines < 0:
            raise ValueError("max_blank_lines must be >= 0")

        self._stream = stream
        self._max_blank_lines = max_blank_lines
        self._by_index: Dict[int, Trivia] = {}
        self._code_indices: List[int] = []
        self._eof = Trivia(token=None)
        self._build()

    # -- construction -----------------------------------------------------

    def _clamp(self, raw: int) -> int:
        return min(raw, self._max_blank_lines)

    def _build(self) -> None:
        toks = list(self._stream)
        code_positions = [i for i, t in enumerate(toks)
                          if t.channel == CHANNEL_DEFAULT]
        self._code_indices = [toks[i].index for i in code_positions]

        # Each run is the stretch of non-code tokens between two code tokens,
        # with `None` standing in for "start of file" and "end of file". A run
        # is split between the token before it and the token after it, so
        # walking runs in order visits every token exactly once.
        bounds = [-1] + code_positions + [len(toks)]

        for n in range(len(bounds) - 1):
            lo, hi = bounds[n], bounds[n + 1]
            prev_code = toks[lo] if lo >= 0 else None
            next_code = toks[hi] if hi < len(toks) else None
            run = toks[lo + 1:hi]

            raw_trailing, trailing, raw_leading, leading, blanks, raw_blanks = \
                self._split_run(run, prev_code, next_code)

            if prev_code is not None:
                # The trailing half belongs to the token that opened this run,
                # which was built with an empty trailing block on the previous
                # iteration; fill it in now that the run has been seen.
                assert prev_code.index in self._by_index
                self._by_index[prev_code.index] = _with_trailing(
                    self._by_index[prev_code.index], raw_trailing, trailing)

            entry = Trivia(
                token=next_code,
                leading=leading,
                trailing=(),
                blank_lines_before=blanks,
                raw_blank_lines_before=raw_blanks,
                raw_leading=raw_leading,
                raw_trailing=(),
            )
            if next_code is None:
                self._eof = entry
            else:
                self._by_index[next_code.index] = entry

    def _split_run(self, run: Sequence[Any], prev_code: Optional[Any],
                   next_code: Optional[Any]):
        """Splits one inter-token run into a trailing half and a leading half.

        Returns ``(raw_trailing, trailing, raw_leading, leading, blanks,
        raw_blanks)``. The two raw halves concatenate back to *run*, in order,
        which is the invariant the whole module rests on.
        """
        # Walk the run once, recording each comment with the number of
        # newlines separating it from the previous piece of content. A `//`
        # comment ends its own line, so it contributes a newline that is not
        # in any whitespace token -- forgetting this is the classic off-by-one
        # in blank-line counting.
        #
        # `prev_content` is None only at the very start of the file, where the
        # arithmetic differs: normally the first newline merely terminates the
        # preceding line and does not make a blank one, but with nothing above,
        # every newline is a blank line.
        newlines = 0
        prev_content = prev_code
        carried_newline = _ends_line(prev_code)
        found: List[Tuple[int, Comment, int]] = []

        for pos, tok in enumerate(run):
            if tok.is_comment:
                nl = newlines + (1 if carried_newline else 0)
                raw = nl if prev_content is None else max(0, nl - 1)
                found.append((pos, Comment(
                    token=tok,
                    blank_lines_before=self._clamp(raw),
                    own_line=nl > 0 or prev_content is None,
                ), raw))
                newlines = 0
                prev_content = tok
                carried_newline = _ends_line(tok)
            else:
                newlines += tok.text.count("\n")

        # Rule 1: comments are trailing while each one sits on the same line
        # as what precedes it. The first comment that starts a new line ends
        # the trailing block, and everything from there on is leading -- even a
        # later comment that shares *its* line.
        n_trailing = 0
        if prev_code is not None:
            for _, comment, _raw in found:
                if comment.own_line:
                    break
                n_trailing += 1

        split = found[n_trailing - 1][0] + 1 if n_trailing else 0
        raw_trailing = tuple(run[:split])
        raw_leading = tuple(run[split:])
        trailing = tuple(c for _, c, _raw in found[:n_trailing])
        leading = tuple(c for _, c, _raw in found[n_trailing:])

        # Rule 3: the blank count is the one in front of the leading block --
        # or in front of the token itself when there is no leading block, in
        # which case the loop above already left the tail count in `newlines`.
        if leading:
            raw_blanks = found[n_trailing][2]
        else:
            nl = newlines + (1 if carried_newline else 0)
            raw_blanks = nl if prev_content is None else max(0, nl - 1)

        return (raw_trailing, trailing, raw_leading, leading,
                self._clamp(raw_blanks), raw_blanks)

    # -- lookup -----------------------------------------------------------

    @property
    def stream(self) -> Any:
        return self._stream

    @property
    def max_blank_lines(self) -> int:
        return self._max_blank_lines

    @property
    def eof(self) -> Trivia:
        """Trivia after the last code token: dangling by rule 4.

        Always present, possibly empty. A file whose last line is a comment
        puts it here, and a null formatter that forgets to emit it loses the
        end of the file -- which is exactly why it is a named attribute rather
        than something a caller has to remember to ask for.
        """
        return self._eof

    def of(self, token_or_index: Any) -> Trivia:
        """Trivia for a default-channel token, by token or by stream index."""
        idx = token_or_index if isinstance(token_or_index, int) \
            else token_or_index.index
        try:
            return self._by_index[idx]
        except KeyError:
            raise KeyError(
                "no trivia for stream index %r: it is not a default-channel "
                "token" % (idx,)) from None

    def __contains__(self, token_or_index: Any) -> bool:
        idx = token_or_index if isinstance(token_or_index, int) \
            else token_or_index.index
        return idx in self._by_index

    def __iter__(self) -> Iterator[Trivia]:
        """Every code token's trivia in source order, then the EOF entry."""
        for idx in self._code_indices:
            yield self._by_index[idx]
        yield self._eof

    @property
    def code_indices(self) -> Tuple[int, ...]:
        return tuple(self._code_indices)

    def comment_before(self, token_or_index: Any) -> Tuple[Comment, ...]:
        """Comments immediately before a token, whichever token owns them.

        Rule 1 attaches every same-line comment backwards, so the comment in
        ``f(/* name */ x)`` is trailing on ``(``. A rule builder asking "what
        did the author write just before ``x``" wants both halves, and this is
        the one place that knows to look in two.
        """
        idx = token_or_index if isinstance(token_or_index, int) \
            else token_or_index.index
        trivia = self.of(idx)
        pos = bisect.bisect_left(self._code_indices, idx)
        before: Tuple[Comment, ...] = ()
        if pos > 0 and not trivia.leading:
            before = self._by_index[self._code_indices[pos - 1]].trailing
        return before + trivia.leading

    def dangling_between(self, open_index: int,
                         close_index: int) -> Optional[Tuple[Comment, ...]]:
        """Rule 4's second case: comments alone between two code tokens.

        Given the indices of a node's opening and closing tokens, returns the
        comments between them if the node has **no code of its own** -- an
        empty ``{ /* nothing else */ }`` body -- and ``None`` otherwise.

        Returning ``None`` rather than an empty tuple is deliberate: "this node
        has no dangling comments" and "this node is not the empty-body case at
        all" are different answers, and a caller that conflates them indents
        the comment against the wrong node.
        """
        if close_index <= open_index:
            return None
        lo = bisect.bisect_right(self._code_indices, open_index)
        hi = bisect.bisect_left(self._code_indices, close_index)
        if lo != hi:
            return None  # there is real code inside; nothing dangles
        trailing = self.of(open_index).trailing if open_index in self else ()
        leading = self.of(close_index).leading if close_index in self else ()
        return trailing + leading


def _with_trailing(trivia: Trivia, raw_trailing: Tuple[Any, ...],
                   trailing: Tuple[Comment, ...]) -> Trivia:
    return Trivia(
        token=trivia.token,
        leading=trivia.leading,
        trailing=trailing,
        blank_lines_before=trivia.blank_lines_before,
        raw_blank_lines_before=trivia.raw_blank_lines_before,
        raw_leading=trivia.raw_leading,
        raw_trailing=raw_trailing,
    )


def _ends_line(tok: Optional[Any]) -> bool:
    """True when *tok* carries the newline that terminates its own line.

    Only ``//`` comments do. It matters because that newline is inside the
    token rather than in the whitespace run after it, so counting newlines
    between tokens misses it.
    """
    return tok is not None and tok.text.endswith("\n")

"""The null formatter -- ``P1-2``, and the proof of safety.

``formatter.md`` section 9 item 2: *"Build the null round-trip formatter first.
It is the proof of safety."* This module is that formatter. It walks the
concrete syntax tree, emits every token it finds with the author's original
spacing, and makes no style decision whatsoever. Its output must equal its
input, byte for byte, for every file in the corpus.

Why bother with something that does nothing?
--------------------------------------------
Because "does nothing" is the hard part. A real formatter is this walk with the
spacing decisions replaced; if the walk itself cannot reach every byte of a
file, no amount of correct style rules will save the output. Running it over
the corpus answers three questions that are otherwise answered by guesswork:

* Does the tree reach every code token? (:attr:`Result.skipped` says when not.)
* Does the trivia map account for every comment and every space?
* Is there any construct where the token stream and the tree disagree?

Tokens the tree does not reach
------------------------------
ANTLR's error recovery can drop a token instead of putting it in an error node,
and a file with an unlexable character has tokens that were never in the
grammar to begin with. Rather than trusting the walk, the emitter keeps a
cursor over the token stream and flushes anything the walk stepped past. The
output is therefore byte-exact *by construction* rather than by assumption --
and the tokens that needed flushing are reported in :attr:`Result.skipped`,
because a corpus file that needs them is a finding, not a detail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from pssparser import cst as _cst

from .trivia import DEFAULT_MAX_BLANK_LINES, TriviaMap

__all__ = ["Result", "format_null", "emit_null"]


@dataclass
class Result:
    """The formatted text plus what the walk learned on the way."""

    #: The output. For the null formatter this equals the input.
    text: str

    #: The parsed tree, kept so a caller does not have to parse twice.
    tree: Any

    #: The trivia map built from ``tree.tokens``.
    trivia: TriviaMap

    #: Stream indices of code tokens the tree walk never visited, in order.
    #: Empty for every file the parser accepts; non-empty is a finding.
    skipped: Tuple[int, ...] = ()

    @property
    def num_syntax_errors(self) -> int:
        return self.tree.num_syntax_errors


def format_null(src: Any,
                max_blank_lines: int = DEFAULT_MAX_BLANK_LINES) -> Result:
    """Parses *src* and re-emits it unchanged.

    :param src: PSS source as :class:`str` or UTF-8 :class:`bytes`, or any
        object with a ``read`` method.
    :raises UnicodeDecodeError: if the input is not valid UTF-8 -- propagated
        from the tokenizer, and the right signal to leave the file alone.
    """
    tree = _cst.parse(src)
    return emit_null(tree, max_blank_lines=max_blank_lines)


def emit_null(tree: Any,
              max_blank_lines: int = DEFAULT_MAX_BLANK_LINES) -> Result:
    """The walk itself, over an already-parsed tree."""
    trivia = TriviaMap(tree.tokens, max_blank_lines=max_blank_lines)
    out: List[str] = []
    skipped: List[int] = []

    # The cursor is a position in `code_indices`, not a token index, so
    # "everything up to here" is a slice rather than a search.
    code = trivia.code_indices
    cursor = 0

    def emit(pos: int) -> None:
        entry = trivia.of(code[pos])
        for tok in entry.raw_leading:
            out.append(tok.text)
        out.append(entry.token.text)
        for tok in entry.raw_trailing:
            out.append(tok.text)

    order = {idx: pos for pos, idx in enumerate(code)}

    for node in _terminals(tree.root):
        pos = order.get(node.token_index)
        if pos is None:
            # A terminal with no token: ANTLR's error recovery inserts these
            # for a token it expected and did not find. It stands for text
            # that is not in the file, so there is nothing to emit.
            continue
        if pos < cursor:
            # Would move backwards. The tree is supposed to be in source
            # order; if it ever is not, silently reordering the user's file is
            # the worst possible response.
            raise RuntimeError(
                "CST terminals are out of source order at token index %d"
                % node.token_index)
        while cursor < pos:
            skipped.append(code[cursor])
            emit(cursor)
            cursor += 1
        emit(cursor)
        cursor += 1

    while cursor < len(code):
        skipped.append(code[cursor])
        emit(cursor)
        cursor += 1

    # Rule 4's first case: comments and whitespace after the last code token
    # belong to nobody. Forgetting them truncates the file.
    for tok in trivia.eof.raw_leading:
        out.append(tok.text)

    return Result(text="".join(out), tree=tree, trivia=trivia,
                  skipped=tuple(skipped))


def _terminals(node: Optional[Any]):
    """Yields the terminal nodes of *node* in source order."""
    if node is None:
        return
    stack = [node]
    while stack:
        cur = stack.pop()
        if not cur.is_rule:
            yield cur
        else:
            stack.extend(reversed(cur.children))

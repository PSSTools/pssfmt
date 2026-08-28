"""Emitting individual tokens with spacing computed from the style (``P3-2b``).

Up to here a rule either placed a whole span of the author's text or refused
to touch it. Both are safe and neither can normalise ``import  a :: b ;`` --
for that a rule has to write the tokens out itself and decide each gap, which
is what :func:`emit_span` does.

Why the vocabulary is a parameter
---------------------------------
There is no global token-type-to-:class:`~pssfmt.style.Site` table here, and
that is deliberate. The same character is different sites in different
places: ``docs/style.rst`` already splits ``:`` four ways, and ``*`` is
multiplication in an expression and a wildcard in ``import pkg::*``. A global
table would have to guess from context, and guessing wrong emits
``import pkg:: * ;``.

So the caller passes the vocabulary it expects, and **a token type not in it
is a bail-out, not a default**. A rule that knows it is looking at an import
pattern can say so; the emitter never has to infer it. This is the same
principle ``style.py`` states for gap composition -- a decision that needs to
see two tokens belongs in the module that knows both -- applied one level
down.

The consequence is that this module cannot silently mis-format a construct it
was not written for. It can only decline to format it, and declining leaves
the author's text exactly as it was.

Separation is a lexical fact, not a style choice
------------------------------------------------
``Style`` can legitimately be configured down to a zero gap almost anywhere.
It must never be able to configure two tokens into one, because that does not
produce ugly PSS, it produces *different* PSS. :func:`must_separate` is the
floor under every computed gap, and it answers a question about the lexer
rather than about taste:

* **Two word-like tokens** -- ``package p``, not ``packagep``.
* **Either side of an escaped identifier.** ``ESCAPED_ID`` is
  ``'\\' [!-~]+ [^ \\r\\t\\n]*`` in ``PSSLexer.g4``: it runs to the next
  whitespace and swallows anything printable on the way.

  The two sides are floors for different reasons, and it is worth being
  precise about which is which. *After* is lexical necessity: ``\\esc{`` is a
  single token, so a style with a zero gap before ``{`` would turn a component
  declaration into an identifier, and nothing else in the file would look
  wrong. *Before* is not -- ``component\\esc`` does lex as two tokens, which
  is exactly why it survived a token-equivalence check and had to be found by
  reading the output. It is a floor anyway, because an escaped identifier is
  delimited by whitespace on both sides everywhere it appears, and because a
  left neighbour that is itself escaped **would** merge.

* **Two punctuation tokens the lexer would munch together.** ``&`` then
  ``&`` is ``&&``; ``<`` then ``<`` is ``<<``; ``.`` then ``..`` is ``...``.
  This is maximal munch stated directly: separate *left* and *right* when
  writing them adjacent would let the lexer take a first token longer than
  *left*.

  Through ``P3-3`` this case did not arise, because no vocabulary contained
  an operator, and the module said so. ``P3-4`` is the vocabulary that does,
  so the rule is now lexical rather than absent -- and ``T-23`` checks it the
  only way worth checking it, by running every ordered pair of vocabulary
  lexemes through the real lexer and requiring the answers to agree.

A token type not in a vocabulary is still the primary defence, and the check
that all of this holds is token equivalence in ``pssfmt.verify``, which
re-lexes the output -- a merge there is a violation, not a diff.

Some sites are facts about the tree, not about the token
--------------------------------------------------------
A vocabulary is a map from token *type*, which makes it context-free, which
is what makes it auditable. Some tokens have no context-free answer at all:
``-`` is unary 103 times and additive 49 times in the corpus, and ``(`` is a
call, a grouping or a cast in the same expression. The grammar already names
all three -- ``unary_op`` and ``add_sub_op`` are different rules -- so the
answer is in the tree, and *sites_at* is how a caller that has walked the
tree passes it down. The emitter still never infers anything.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Callable, List, Mapping, Optional, Sequence, Union

from ..layout import (ALIGN_MARK, LINE, SOFTLINE, Layout, concat, group,
                      indent, text)
from ..style import Site

__all__ = ["WORD", "Vocabulary", "must_separate", "floor_gap", "emit_span"]


class _Word:
    """A token that is not a style site: an identifier, a keyword, a literal.

    Distinct from ``None``, which :meth:`~pssfmt.style.Style.gap` already uses
    for "contributes no spacing", and distinct from absence, which means the
    caller did not expect this token and the emitter must decline. Three
    states, three values -- collapsing any two of them turns a bail-out into a
    guess.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "WORD"


#: The vocabulary entry for a token with no spacing opinion of its own.
WORD = _Word()

#: What a caller declares it expects to see: token type name -> site or WORD.
Vocabulary = Mapping[str, Union[Site, _Word]]

_MISSING = object()

#: Shared empty override map, so the common call allocates nothing.
_NO_SITES: Mapping[int, Site] = MappingProxyType({})

#: Characters that continue an identifier or a number. Two tokens whose
#: touching ends are both in this class would lex as one.
_WORD_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")

#: Every punctuation lexeme in ``PSSLexer.g4``, plus the two comment openers.
#:
#: Used for one thing: deciding whether a longer token starts where *left*
#: ends. ``>>`` is deliberately absent because the lexer has no such token --
#: PSS spells the shift operator as two ``TOK_GT`` -- while ``>>=`` is present
#: because it does. The comment openers are here because ``/`` then ``*``
#: would open a block comment and swallow the rest of the file; no PSS
#: expression can actually place them adjacent, and ``T-23`` reports that as
#: an unreachable entry rather than leaving it unstated.
_LEXEMES = frozenset("""
    ! != # % & && &= ( ) * ** + += , - -= -> . .. ... / : :/ :: := ; < << <<=
    <= = == > >= >>= ? @ [ ] ^ { | |= || } ~ // /*
""".split())

#: The longest lexeme, so the munch test has a bound.
_LONGEST = max(len(lexeme) for lexeme in _LEXEMES)


def must_separate(left: Any, right: Any) -> bool:
    """Whether *left* and *right* would lex differently if written together.

    A floor under the computed gap, never a replacement for it: this says
    "not zero", and the style still says how much more.
    """
    if "ESCAPED_ID" in (left.type_name, right.type_name):
        return True
    lt, rt = left.text, right.text
    if not lt or not rt:
        return False
    if lt[-1] in _WORD_CHARS and rt[0] in _WORD_CHARS:
        return True
    return _munches(lt, rt)


def floor_gap(width: int, left: Any, right: Any) -> int:
    """*width*, raised to 1 where writing the two tokens together would relex.

    :func:`must_separate` answers the question; this applies the answer, and
    it exists because *applying* it is where the floor was being lost.
    :func:`emit_span` is not the only place two tokens end up adjacent -- a
    header meets its ``{`` and a declaration meets a stray ``;`` in
    ``decls.py``, composed as layout rather than emitted from a span -- and a
    floor that only one of the three consults is not a floor. ``P3-10`` found
    both of the others by looking for the composition sites rather than by
    reading the rule, which is the way to look for the next one.

    Note this raises a gap and never lowers one: a style that asks for three
    columns keeps them. More than one space after an escaped identifier is
    harmless, because the identifier ends at the *first* whitespace character
    and what follows it is not part of the token -- so the alignment pass may
    pad past one and ``formatter.md`` section 4.4's "exactly one space" is
    satisfied by any positive number.

    *left* and *right* are in **source order**, and :func:`must_separate` is
    genuinely asymmetric -- ``/`` then ``*`` opens a comment while ``*`` then
    ``/`` does not. Passing them the other way round is nevertheless a mutant
    no test kills, and the reason is worth recording rather than testing
    around: for all twelve asymmetric pairs the direction that answers *true*
    is a compound operator -- ``->``, ``-=``, ``+=``, ``>=``, ``<=``, ``/*``
    -- and the grammar cannot put its two halves adjacent as separate tokens.
    So a reversed call can only add a space that was not needed; it can never
    drop one that was. Killing it would mean asserting exact column counts
    under a style nothing ships and ``docs/style.rst`` does not promise.
    """
    return 1 if width == 0 and must_separate(left, right) else width


def _munches(lt: str, rt: str) -> bool:
    """Whether the lexer would take more than *lt* from ``lt + rt``.

    Maximal munch, applied at the seam. Only a prefix *longer* than *lt*
    matters: a shorter one means the lexer stops early, which it cannot do
    when *lt* is itself a token.
    """
    joined = lt + rt
    for end in range(len(lt) + 1, min(len(joined), _LONGEST) + 1):
        if joined[:end] in _LEXEMES:
            return True
    return False


def _site(entry: Union[Site, _Word]) -> Optional[Site]:
    return None if entry is WORD else entry


def emit_span(ctx: Any,
              first: int,
              last: int,
              vocabulary: Vocabulary,
              separate: Optional[Callable[..., bool]] = None,
              mark_at: Sequence[int] = (),
              sites_at: Mapping[int, Site] = _NO_SITES,
              break_at: Optional[int] = None) -> Optional[Layout]:
    """Code tokens ``first..last`` written out with computed gaps.

    *separate* is an extra floor the caller owns, on top of
    :func:`must_separate`. ``style.py`` says a decision that needs to see two
    tokens belongs in the module that knows both, and this is where such a
    decision gets in. The case that forces it: ``bit[64] x`` needs a space
    that ``max(left.after, right.before)`` cannot produce, because ``]`` has
    no ``after`` worth setting -- give it one and ``a[i];`` becomes ``a[i] ;``
    -- and an identifier has no ``before`` at all. The space is not between a
    bracket and a name, it is between a *type* and a *declarator*, and only
    the rule knows that.

    It is called as ``separate(left, right, left_site, right_site)``. The
    sites are there because ``P3-7`` produced a seam the *tokens* cannot
    settle: ``packed_s<T, 32> hdr`` needs the same floor as ``bit[64] x``, but
    ``>`` is ``TOK_GT``, which is also a comparison -- so a callback keyed on
    the character alone would fire between ``a > b`` too and claim a type
    boundary that is not there. Under today's spacing that is invisible,
    because comparisons are spaced anyway; it would surface the day someone
    configured them tight, which is precisely the kind of latent wrong answer
    a floor should not contain. The emitter has already resolved both sites,
    so it passes them rather than making the caller re-derive them.

    Note this is a floor and not an override: it can turn a zero gap into
    one space, never a space into nothing.

    *mark_at* lists code positions to place a **column stop** before. The
    alignment pass (:mod:`pssfmt.layout.align`) needs two things there, and
    the second is easy to forget: the mark itself, and *the author's own
    spacing after it*. By the time that pass runs the source is gone, so the
    original gap is the only evidence of whether this block was a deliberate
    table -- emitting the computed gap instead would make ``infer`` unable to
    infer anything, and every hand-built table would collapse while looking
    like it had been considered. A stop is skipped where the original gap
    spans lines, since a column stop across a line break means nothing.

    *sites_at* maps a code position to the :class:`~pssfmt.style.Site` that
    position really is, overriding whatever the vocabulary says for its token
    type. It exists because a vocabulary is keyed by type and some tokens have
    no answer at that granularity -- ``-`` is unary or additive, ``(`` is a
    call, a grouping or a cast -- while the *grammar* names each of them with
    a different rule. A caller that has walked the tree knows; the emitter
    still does not guess. Note that a caller doing this owes itself a
    completeness check, since a position it forgot silently falls back to the
    type's answer, and for an ambiguous type that answer is wrong rather than
    absent.

    ``None`` means *this span is not mine* and the caller should reproduce it
    instead. There are three reasons, and all three are cases where emitting
    something would mean inventing a decision:

    * a token type the *vocabulary* does not name -- see the module docstring;
    * a **comment** between two tokens. ``component c /* why */ {`` has a real
      answer, but it is a question about where comments go rather than about
      spacing, and this module has no opinion worth acting on;
    * any other non-whitespace trivia, which in practice is a lexical error
      token. Replacing it with a computed gap deletes a byte of the file.

    Whitespace *is* discarded, newlines included: a header the author wrapped
    is joined back onto one line. That is the point of the function, and
    through ``P3-3`` it was also the whole story, because every span a caller
    passed was short by construction.

    ``P3-4`` ended that: an initializer is an expression and an expression is
    any length, so joining can now push a line past ``print_width`` -- which
    the corpus shows authors treat as a wall, not a preference. *break_at* is
    the answer, and it is deliberately the smallest one: **a single** position
    that may become a line break, with everything after it indented one level.
    In flat mode it renders as the computed gap, so a span that fits is
    byte-identical to one emitted without it; the engine breaks it only when
    it must.

    One break and not a list of them, because "which of several places to
    break, and in what order" is a policy question ``docs/style.rst``
    explicitly leaves open, and a ``Fill`` would be answering it by accident.
    """
    trivia = ctx.trivia
    code = trivia.code_indices
    if first > last:
        return None

    parts: List[Layout] = []
    prev_token = None
    prev_site: Optional[Site] = None
    broke_at: Optional[int] = None

    for pos in range(first, last + 1):
        entry = trivia.of(code[pos])
        token = entry.token
        found = vocabulary.get(token.type_name, _MISSING)
        if found is _MISSING:
            return None
        # The tree wins where the caller has consulted it: see the module
        # docstring on sites that are not a property of the token type.
        site = sites_at.get(pos) if pos in sites_at else _site(found)

        if pos != first:
            if not _discardable(entry.raw_leading):
                return None
            gap = floor_gap(ctx.style.gap(prev_site, site), prev_token, token)
            if gap == 0 and separate is not None and separate(
                    prev_token, token, prev_site, site):
                gap = 1
            original = _original_gap(trivia, code, pos)
            if pos == break_at:
                broke_at = len(parts)
                parts.append(LINE if gap else SOFTLINE)
            elif pos in mark_at and gap and original is not None:
                parts.append(text(ALIGN_MARK + " " * max(gap, original)))
            elif gap:
                parts.append(text(" " * gap))
        if pos != last and not _discardable(entry.raw_trailing):
            return None

        parts.append(text(token.text))
        prev_token, prev_site = token, site

    if broke_at is None:
        return concat(parts)
    return group(concat(
        parts[:broke_at]
        + [indent(concat(parts[broke_at:]), ctx.style.indent_width)]))


def _discardable(run: Any) -> bool:
    """Whether a trivia run holds nothing but whitespace."""
    return all(not tok.text.strip() for tok in run)


def _original_gap(trivia: Any, code: Any, pos: int) -> Optional[int]:
    """Columns the author left before the token at *pos*, or ``None``.

    ``None`` where the two tokens are on different lines, which is not a gap
    on any one line and so cannot be a column stop.
    """
    before = trivia.of(code[pos - 1]).raw_trailing
    after = trivia.of(code[pos]).raw_leading
    run = "".join(tok.text for tok in before) + "".join(tok.text for tok in after)
    if "\n" in run:
        return None
    return len(run)

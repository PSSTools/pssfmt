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
from typing import (Any, Callable, Dict, List, Mapping, Optional, Sequence,
                    Tuple, Union)

from dataclasses import dataclass

from ..layout import (ALIGN_MARK, LINE, SOFTLINE, Layout, align_to, concat,
                      fill_with, group, indent, text)
from ..style import BreakMode, Construct, Site

__all__ = ["WORD", "Vocabulary", "Wrap", "must_separate", "floor_gap",
           "emit_span", "original_gap", "flat_width"]


@dataclass(frozen=True)
class Wrap:
    """A bracketed list inside a span that may break across lines (``S-16``).

    Everything here is a **code position**, and every one of them comes from
    the caller's walk of the tree rather than from anything this module
    infers. That is the same discipline ``sites_at`` follows and for the same
    reason: a ``,`` is a list separator in an argument list and part of a
    declarator elsewhere, and a module that guessed from the character would
    be wrong exactly where it mattered.

    One wrap per span, deliberately. A span holding two lists --
    ``f(a, b) + g(c, d)`` -- declines to wrap and is emitted flat, which is
    what it did before this item. Choosing *which* of two lists to break, and
    in what order, is a policy question with no evidence behind it, and a
    formatter that answered it by taking the first one would be answering it
    by accident.
    """

    #: Whose break policy and continuation indent apply.
    construct: Construct
    #: The opening bracket.
    open_at: int
    #: The closing bracket.
    close_at: int
    #: Each separator inside it -- the ``,`` positions, in order.
    separators: Tuple[int, ...] = ()


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
              break_at: Optional[int] = None,
              wrap: Optional[Wrap] = None) -> Optional[Layout]:
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

    *break_at* is one break and not a list of them. That used to be the whole
    of the line-breaking story here, on the grounds that "which of several
    places to break, and in what order" was a policy question
    ``docs/style.rst`` left open -- and ``S-16`` is the item that answered it,
    so this docstring would otherwise be arguing against the parameter below.

    *wrap* is a **bracketed list** that may break as a unit: an argument list,
    a parameter list, a template parameter list, a range list. It is a
    different shape from *break_at* rather than a generalisation of it --
    that one continues a line, this one distributes a list -- and the two
    compose, since a span can hold both.

    What it emits is the shape prettier established and every formatter with
    a Wadler engine has since::

        group( "(" + indent(softline + items joined by ("," + line))
                   + softline + ")" )

    All-or-nothing falls out of ``Group`` for free: flat if the whole list
    fits, otherwise **every** ``Line`` inside breaks. ``pack_arguments =
    "bin_pack"`` swaps the ``join`` for a ``Fill`` and
    ``align_after_open_bracket = true`` swaps the ``indent`` for an ``Align``;
    both were already in the IR, unused, which is why choosing all-or-nothing
    as the default cost nothing to build and choosing the other would have
    cost a second engine.

    **The flat rendering is byte-identical to what this function emitted
    before the wrap existed**, and that is asserted rather than hoped: a
    ``Line`` renders as one space flat and a ``SoftLine`` as nothing, so the
    wrap is only taken where the computed gaps are exactly 1 and 0. Under any
    other style -- a configured space inside call parens, say -- the wrap is
    declined and the span is emitted as before. A list that fits must not move
    because a policy for lists that do not fit was added.
    """
    trivia = ctx.trivia
    code = trivia.code_indices
    if first > last:
        return None

    parts: List[Layout] = []
    prev_token = None
    prev_pos = first - 1
    prev_site: Optional[Site] = None
    broke_at: Optional[int] = None
    #: parts index of the SoftLine after the wrap's `(`, and of the one
    #: before its `)`. Recorded during the loop because reassembly needs to
    #: slice at exactly those two points and nothing else knows where they are.
    wrap_open: Optional[int] = None
    wrap_close: Optional[int] = None
    wrap_seps: List[int] = []
    wrap_marks: List[Tuple[int, int]] = []
    if wrap is not None and not (first <= wrap.open_at < wrap.close_at <= last):
        # A wrap the caller computed for a different span. Refusing beats
        # slicing at an index that means nothing here.
        wrap = None

    for pos in range(first, last + 1):
        entry = trivia.of(code[pos])
        token = entry.token
        found = vocabulary.get(token.type_name, _MISSING)
        if found is _MISSING:
            return None
        # The tree wins where the caller has consulted it: see the module
        # docstring on sites that are not a property of the token type.
        #
        # It does *not* win over absence, and `S-10` tried making it do so.
        # The argument was that `sites_at` is a claim about one position made
        # by walking the rule that owns it, which is stronger evidence than a
        # claim about a token type. True, and still the wrong change: the
        # walk in `pssfmt.rules.exprs` assigns brackets generously, so
        # trusting it over absence silently un-declined `packed_s<bit[8], 4>`
        # -- a header `P3-7a` refuses precisely because admitting `[` there
        # makes `s<A[3:0]>` spellable and its bit-slice colon reachable in a
        # vocabulary whose `:` means inheritance. The decline was load-bearing
        # and nothing about the ternary needed it lifted.
        site = sites_at.get(pos) if pos in sites_at else _site(found)

        if pos != first:
            if not _discardable(entry.raw_leading):
                return None
            gap = floor_gap(ctx.style.gap(prev_site, site), prev_token, token)
            if gap == 0 and separate is not None and separate(
                    prev_token, token, prev_site, site):
                gap = 1
            original = original_gap(trivia, code, pos)
            wrapped = _wrap_break(wrap, pos, prev_pos, gap)
            if wrapped is not None:
                if prev_pos == wrap.open_at:
                    wrap_open = len(parts)
                elif pos == wrap.close_at:
                    wrap_close = len(parts)
                else:
                    wrap_seps.append(len(parts))
                wrap_marks.append((len(parts), gap))
                parts.append(wrapped)
            elif wrap is not None and _wrap_seam(wrap, pos, prev_pos):
                # A seam of the wrap whose computed gap is not what its break
                # renders flat -- 0 for a SoftLine, 1 for a Line. Declining
                # the whole wrap rather than this seam: a list that breaks at
                # three of its four commas is worse than one that does not
                # break at all.
                #
                # **And the seams already emitted have to be put back**, which
                # is the half that was missed first time. A SoftLine left
                # behind outside any group renders as a break, because the
                # root is broken -- so declining mid-span produced a list that
                # broke after its opening bracket and nowhere else. Caught by
                # a comma-tight style, which is the only configuration that
                # reaches this branch at all.
                for idx, width in wrap_marks:
                    parts[idx] = text(" " * width)
                wrap = None
                wrap_open = wrap_close = None
                wrap_seps = []
                wrap_marks = []
                if gap:
                    parts.append(text(" " * gap))
            elif pos == break_at:
                broke_at = len(parts)
                parts.append(LINE if gap else SOFTLINE)
            elif pos in mark_at and gap and original is not None:
                parts.append(text(ALIGN_MARK + " " * max(gap, original)))
            elif gap:
                parts.append(text(" " * gap))
        if pos != last and not _discardable(entry.raw_trailing):
            return None

        parts.append(text(token.text))
        prev_token, prev_site, prev_pos = token, site, pos

    if wrap is not None and wrap_open is not None and wrap_close is not None:
        return _assemble_wrap(ctx, parts, wrap, wrap_open, wrap_close,
                              wrap_seps)
    if broke_at is None:
        return concat(parts)
    # `continuation_indent`, not `indent_width`: this is the one place in the
    # rules where a line is continued rather than nested, and the two are
    # separate options in the config for exactly that reason. They are both 4
    # by default, so the distinction is invisible until somebody sets one --
    # which is what `P4-2` made possible, and how this was found. Until then
    # `continuation_indent` was a declared option that nothing read.
    return group(concat(
        parts[:broke_at]
        + [indent(concat(parts[broke_at:]), ctx.style.continuation_indent)]))


def _wrap_seam(wrap: Wrap, pos: int, prev_pos: int) -> bool:
    """Whether the gap before *pos* is one the wrap owns."""
    return (prev_pos == wrap.open_at
            or pos == wrap.close_at
            or prev_pos in wrap.separators)


def _wrap_break(wrap: Optional[Wrap], pos: int, prev_pos: int,
                gap: int) -> Optional[Layout]:
    """The break layout for a wrap seam, or ``None`` if this is not one.

    ``None`` is also the answer when the computed gap is not what the break
    renders flat -- 0 for a ``SoftLine``, 1 for a ``Line``. That guard is what
    keeps a list that fits byte-identical to what it was before wrapping
    existed, under **any** style rather than only the shipped one.
    """
    if wrap is None or not _wrap_seam(wrap, pos, prev_pos):
        return None
    if prev_pos == wrap.open_at or pos == wrap.close_at:
        return SOFTLINE if gap == 0 else None
    return LINE if gap == 1 else None


def _assemble_wrap(ctx: Any, parts: List[Layout], wrap: Wrap,
                   open_idx: int, close_idx: int,
                   sep_idx: Sequence[int]) -> Layout:
    """The three-piece shape: head, indented body, closing break and tail.

    The leading ``SoftLine`` goes **inside** the indent and the trailing one
    outside, which is what puts the closing bracket back at the opening
    line's column rather than at the items'. Getting that the other way round
    is the classic version of this bug and it is invisible until a list
    actually breaks.
    """
    style = ctx.style
    body_parts = parts[open_idx:close_idx]
    if style.break_policy_for(wrap.construct) is BreakMode.FILL and sep_idx:
        # `bin_pack`. The separators are already `Line` nodes in `parts`; a
        # `Fill` wants the items and the separators handed over separately, so
        # the body is re-sliced at exactly those indices. The comma itself
        # stays with the item before it -- a `Fill` measures each separator
        # against the *next* item, and a leading comma would measure the wrong
        # pair.
        chunks: List[Layout] = []
        prev = open_idx + 1
        for idx in sep_idx:
            chunks.append(concat(parts[prev:idx]))
            prev = idx + 1
        chunks.append(concat(parts[prev:close_idx]))
        body = concat([parts[open_idx], fill_with(LINE, chunks)])
    else:
        body = concat(body_parts)

    if style.align_after_open_bracket:
        inner = align_to(body)
    else:
        inner = indent(body, style.continuation_for(wrap.construct))
    return group(concat(
        parts[:open_idx] + [inner] + parts[close_idx:]))


def flat_width(layout: Layout) -> int:
    """Columns *layout* occupies rendered flat, counting no line breaks.

    What ``S-17``'s guard needs and the only thing it needs: **would joining
    this construct produce a line the tool then cannot break?** A `Line`
    renders as one space flat and a `SoftLine` as nothing, which is what the
    two additions below say.

    Measured on the built layout rather than estimated from the tokens,
    because the gaps are the style's and re-deriving them here would be a
    second implementation of the thing being measured. Cheap: the layouts
    this is asked about are one construct's worth of text.
    """
    from ..layout.ir import Concat, Fill, Group, Indent, Line, Text, Verbatim
    from ..layout.width import width_of

    total = 0
    stack = [layout]
    while stack:
        node = stack.pop()
        if isinstance(node, Text):
            total += width_of(node.value)
        elif isinstance(node, Line):
            total += 1
        elif isinstance(node, Verbatim):
            total += width_of(node.value.split("\n")[0])
        elif isinstance(node, (Concat, Fill)):
            stack.extend(node.parts)
        elif isinstance(node, (Group, Indent)):
            stack.append(node.contents)
    return total


def _discardable(run: Any) -> bool:
    """Whether a trivia run holds nothing but whitespace."""
    return all(not tok.text.strip() for tok in run)


def original_gap(trivia: Any, code: Any, pos: int) -> Optional[int]:
    """Columns the author left before the token at *pos*, or ``None``.

    ``None`` where the two tokens are on different lines, which is not a gap
    on any one line and so cannot be a column stop.

    Public since ``P3-11b``, which places a column stop by composing layouts
    rather than through :func:`emit_span`'s *mark_at*: a match choice's
    statement is built by its own rule, so the mark has to be written between
    two layouts instead of between two tokens. What a stop needs there is
    identical -- the mark, and *the author's own spacing after it* -- so the
    measurement is shared rather than restated. See *mark_at* on why the
    original gap and not the computed one.
    """
    before = trivia.of(code[pos - 1]).raw_trailing
    after = trivia.of(code[pos]).raw_leading
    run = "".join(tok.text for tok in before) + "".join(tok.text for tok in after)
    if "\n" in run:
        return None
    return len(run)

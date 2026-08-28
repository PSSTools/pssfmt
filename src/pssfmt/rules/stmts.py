"""Tier 1 -- field declarations (``P3-3``).

The most common statement in PSS by a wide margin. Of the members inside the
bodies ``P3-2`` already lays out, these six rules account for **526** of them
-- more than everything else put together -- and 521 fit on one line::

    rand bit en;
    bit[64] spi_tx_addr;
    mem_c::fill_a fill_copy;
    input mem_blk_s blk;
    static const bit[64] DMA_CH_BASE = 0x40;
    pool[4] dma_chan_s chan_p;
    bind chan_p *;

Written out token by token through :func:`~pssfmt.rules.tokens.emit_span`, so
the gaps come from the style rather than from the author.

Where the boundary is, and why
------------------------------
Through ``P3-3`` the vocabulary stopped at the ``=``: a default that was a
single literal or name was inside it, and an expression was not. ``P3-4``
supplies the rest, so ``= DMA_CH_BASE + DMA_NUM_CH * DMA_CH_STRIDE`` is now
written out too -- by merging :data:`~pssfmt.rules.exprs.EXPRESSION_VOCABULARY`
in and taking the ambiguous tokens' sites from the tree. What
:mod:`pssfmt.rules.exprs` declines, a field holding it declines with it, and
those reasons are argued there rather than repeated here.

``P3-5`` then supplied the domain form, so ``rand int in [1..4] n;`` is
written out as well -- and ``bit[3] in [2..4]`` gets a tight width bracket and
a spaced set bracket out of the same grammar node.

The cut this module still makes for itself, each for a stated reason:

``<T, N>``
    A template argument list -- a list that may need to *break*, not a run of
    tokens that fits. ``P3-7``, same as the templated headers ``P3-2b`` left
    alone.
``bit[31:0]``
    A bit-slice colon. Excluded not because it is hard but because
    ``Site.COLON_BIT_SLICE`` is tight while ``Site.COLON_INHERITANCE`` is
    spaced, and telling them apart needs bracket depth -- the first piece of
    *context* the token emitter would have to carry. It occurs 13 times in
    the corpus, all in one lexical torture file, against 248 plain ``[N]``
    widths. Not worth making the emitter context-sensitive for; revisit if
    real code disagrees.
``\"\"\"...\"\"\"``
    A target-template payload, which must never be re-anchored (§4.7.1.2).

Two-token facts the style cannot express
----------------------------------------
``max(left.after, right.before)`` is order-independent, which is what makes
it composable, and the price is that it cannot say "a space here but not
there" for the same token. Two gaps in this module need exactly that, and
both are *grammatical* rather than aesthetic -- they mark the seam between
two parts of a declaration, which is why they live here and not in the style:

* ``]`` before a name -- ``bit[64] x``, ``pool[4] t p``. Giving ``]`` an
  ``after`` of one would put a space in ``a[i];`` too.
* a name before ``*`` -- ``bind chan_p *``. The wildcard has no site, for the
  same reason it has none in an import.

Both are sound only because the vocabularies are closed: ``]`` followed by a
word cannot be anything but a part boundary when no operator can appear
between them.
"""

from __future__ import annotations

from typing import Any

from ..layout import Layout
from ..style import Site
from .emit import code_span
from .exprs import ATOMS as _ATOMS
from .exprs import EXPRESSION_VOCABULARY, WORD_LIKE, sites_for
from .tokens import WORD, emit_span

#: Field modifiers and the built-in scalar types. All word-class: they need
#: separating from their neighbours and have no other spacing opinion.
_MODIFIERS_AND_TYPES = (
    "TOK_RAND", "TOK_STATIC", "TOK_CONST", "TOK_INPUT", "TOK_OUTPUT",
    "TOK_LOCK", "TOK_SHARE", "TOK_POOL", "TOK_ACTION",
    "TOK_BIT", "TOK_INT", "TOK_BOOL", "TOK_STRING", "TOK_FLOAT32",
    "TOK_FLOAT64", "TOK_CHANDLE", "TOK_VOID",
)

#: The punctuation a declaration owns, as opposed to what its initializer does.
_DECLARATION_PUNCTUATION = {
    "TOK_DOUBLE_COLON": Site.SCOPE_RESOLUTION,
    "TOK_LSBRACE": Site.INDEX_BRACKET_OPEN,
    "TOK_RSBRACE": Site.INDEX_BRACKET_CLOSE,
    "TOK_COMMA": Site.COMMA,
    "TOK_SINGLE_EQ": Site.ASSIGN,
    "TOK_SEMICOLON": Site.SEMICOLON,
}

#: ``rand bit[64] x = DMA_BASE + n * STRIDE;`` -- the declaration's own tokens
#: and everything an expression may contain (``P3-4``).
#:
#: The merge is safe in the direction that matters. An expression token can now
#: appear anywhere in the statement, but every ambiguous one is in
#: :data:`~pssfmt.rules.exprs.TREE_DECIDED`, and :func:`_tree_sites` refuses a
#: statement holding one the tree did not classify. So a ``-`` outside an
#: expression -- wherever that would come from -- declines instead of picking
#: up whichever meaning happened to be listed.
_FIELD_VOCABULARY = dict(EXPRESSION_VOCABULARY)
_FIELD_VOCABULARY.update((name, WORD) for name in _MODIFIERS_AND_TYPES)
_FIELD_VOCABULARY.update(_DECLARATION_PUNCTUATION)

#: ``bind chan_p *;``. ``*`` is a wildcard here and multiplication in an
#: expression, so it is word-class in this vocabulary -- the same split
#: ``P3-2b`` made for ``import pkg::*``. Sound because no operator can appear
#: in a bind statement to be confused with it, which is also why this
#: vocabulary is built from the atoms rather than from the field one: pulling
#: in the expression tokens would put ``*`` in two roles at once.
_BIND_VOCABULARY = dict(
    [(name, WORD) for name in _ATOMS + _MODIFIERS_AND_TYPES]
    + list(_DECLARATION_PUNCTUATION.items())
)
_BIND_VOCABULARY.update({
    "TOK_BIND": WORD,
    "TOK_ASTERISK": WORD,
    "TOK_DOT": Site.MEMBER_ACCESS,
})

_WORD_LIKE = WORD_LIKE | frozenset(_MODIFIERS_AND_TYPES)


def _after_a_width_bracket(left: Any, right: Any) -> bool:
    """``bit[64] x`` -- the seam between a type and the name it declares."""
    return left.type_name == "TOK_RSBRACE" and right.type_name in _WORD_LIKE


def _around_a_bind_wildcard(left: Any, right: Any) -> bool:
    """``bind chan_p *`` -- the seam between the path and the bind item."""
    return right.type_name == "TOK_ASTERISK" and left.type_name in _WORD_LIKE


#: The node boundaries a hand-aligned field declaration lines up on.
#:
#: Every one is a *rule* boundary rather than a token adjacency, which is what
#: makes taking them from the tree exact: inferring the end of a type from
#: tokens would mean re-deciding where a type ends, and the grammar has
#: already decided.
#:
#: ``flow_object_type`` and ``object_ref_field`` were added in ``P3-6``, and
#: the reason they were missing is worth recording. They belong to
#: ``input``/``output``/``lock``/``share`` fields, which have no
#: ``data_instantiation`` at all -- a different production with the same
#: shape -- so through ``P3-5`` those fields got *no* stops and any column an
#: author had built in one was collapsed. That went unnoticed because 31 of
#: the 92 corpus files put their actions inside an ``extend``, which had no
#: rule, so the damage was unreachable. Registering ``extend_stmt`` made it
#: reachable, and the corpus reported it as eight files of flattened tables.
#:
#: The evidence for the two seams, over the corpus::
#:
#:     before object_ref_field   24 padded (17 files)   10 tight (2 files)
#:     before flow_object_type   10 padded ( 8 files)   13 tight (9 files)
#:
#: The second is genuinely mixed, and is marked anyway, because a stop is not
#: a decision to pad: :func:`~pssfmt.layout.align._was_aligned` reads each
#: block's own columns and reproduces or flushes accordingly. Marking a seam
#: says a column may exist there, and declining to mark one is what makes it
#: impossible for the author's to survive.
#:
#: The gap before ``rand``/``static const`` and the type is deliberately *not*
#: here: the corpus pads it zero times.
#: ``resource_object_type`` is ``lock``/``share`` what ``flow_object_type`` is
#: to ``input``/``output``: the same column in a third production. Omitting it
#: does not merely lose that field's own column, it destroys the whole
#: block's -- a ``lock`` line among ``input`` lines contributes one stop where
#: its neighbours contribute two, so the group's shared column count drops to
#: one and every line is measured on a cell that has already been collapsed.
_SEAM_RULES = ("data_instantiation", "flow_object_type", "resource_object_type",
               "object_ref_field")


def _column_stops(ctx: Any, node: Any) -> tuple:
    """Where a hand-aligned field declaration puts its columns.

    For an attribute, two of them, and both are needed together::

        static const bit[64]  SPI_CTRL_OFF   = 0x00;
        static const bit[64]  SPI_STATUS_OFF = 0x08;
                            ^^             ^^

    The first is the seam between the type and the declarator. The second is
    the gap before ``=``. Marking only the first looks like it works and is
    not: where every type is the same width -- which is the usual case in a
    table of constants -- the first column is already consistent at one space,
    so the block is reproduced with its ``=`` column collapsed and nothing
    reports a problem.

    A flow or resource reference has the same two-column shape written with
    different productions, and no ``=`` to make a third::

        input  mem_blk_s   src;
        output spi_data_s  data;
        lock   dma_chan_s  ch;
              ^           ^

    Empty for ``pool`` and ``bind``, which have no seam rule below them.
    """
    code = ctx.trivia.code_indices
    stops: list = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if not cur.is_rule:
            continue
        if cur.rule_name in _SEAM_RULES:
            span = code_span(ctx.trivia, cur)
            if span is None:
                return ()
            stops.append(span[0])
            for pos in range(span[0] + 1, span[1] + 1):
                if ctx.trivia.of(code[pos]).token.type_name == "TOK_SINGLE_EQ":
                    stops.append(pos)
                    break
            # A seam's own subtree holds no further seam, and descending into
            # it would let a nested declaration contribute a column to the
            # statement containing it.
            continue
        stack.extend(reversed(cur.children))
    return tuple(stops)


def _tree_sites(ctx: Any, node: Any) -> Any:
    """Sites for the whole statement, or ``None`` if any token is unclassified.

    The check runs over the *statement*, not over its initializer, because the
    declaration has tree-decided tokens of its own: ``bit[64]``'s brackets
    belong to ``integer_type``, which the grammar distinguishes from an index
    -- so they are ``TYPE_BRACKET`` here rather than the ``INDEX_BRACKET`` a
    token-type vocabulary had to call them through ``P3-3``. Same number
    either way; the tree simply knows which construct it is.
    """
    return sites_for(ctx, node)


def _statement(ctx: Any, node: Any, vocabulary: Any, separate: Any,
               tree_sites: bool = True) -> Layout:
    """*node* written out, or reproduced unchanged if it is not ours."""
    span = code_span(ctx.trivia, node)
    if span is None:
        return _reproduce(ctx, node)
    sites: Any = {}
    if tree_sites:
        sites = _tree_sites(ctx, node)
        if sites is None:
            return _reproduce(ctx, node)
    stops = _column_stops(ctx, node)
    emitted = emit_span(ctx, span[0], span[1], vocabulary,
                        separate=separate,
                        mark_at=stops,
                        sites_at=sites,
                        break_at=_break_after_assign(ctx, span))
    return emitted if emitted is not None else _reproduce(ctx, node)


def _break_after_assign(ctx: Any, span: tuple) -> Any:
    """The one place a field declaration may be split: just after its ``=``.

    ``P3-3`` could join any wrapped declaration back onto one line because a
    declaration without an expression is short. With ``P3-4`` it need not be,
    and the corpus contains a field the author wrapped precisely because the
    joined form is 84 columns -- so joining it is not a neutral diff, it is
    output that breaks the one measurement ``docs/style.rst`` calls a wall.

    Break *after* the ``=`` and indent one level, which is the single instance
    the corpus has and therefore the weakest claim available: it reproduces
    what the author did rather than deciding anything they did not. Where a
    field has no ``=`` there is nothing to say and no break is offered.

    The ``=`` is located by token type rather than by index into the column
    stops, which is what it was through ``P3-5``. That worked only while every
    statement with two stops had an ``=`` as the second one, and ``P3-6``'s
    flow-reference seams broke the coincidence: ``output spi_data_s data;``
    has two stops and no ``=``, and the old form would have offered a break
    after its declarator.
    """
    code = ctx.trivia.code_indices
    for pos in range(span[0], span[1] + 1):
        if ctx.trivia.of(code[pos]).token.type_name == "TOK_SINGLE_EQ":
            return pos + 1
    return None


def _reproduce(ctx: Any, node: Any) -> Layout:
    # Imported lazily to keep the module pair acyclic: ``decls`` owns the
    # body layout that calls into here, and reproduction is its notion.
    from .decls import _reproduce as reproduce

    return reproduce(ctx, node)


#: The four rules that share the field vocabulary, and the one that does not.
#:
#: ``component_pool_declaration`` is deliberately absent, and it is worth
#: saying why rather than leaving it to look like an oversight. All ten in the
#: corpus are written ``pool [4] t p;`` -- with a space before the bracket --
#: and ``Site.INDEX_BRACKET_OPEN`` says tight, because it was measured on
#: 1002 *index* expressions (``a[i]``) and not on ten pool sizes. Emitting
#: ``pool[4]`` would be applying a number to a construct it was never measured
#: over, against unanimous evidence from the construct itself. Whether a pool
#: size is an index bracket or something else is a question for the survey, not
#: for this module to settle by default.
_FIELD_RULES = (
    "attr_field",
    "component_data_declaration",
    "action_field_declaration",
    "const_field_declaration",
)


def register(registry) -> None:
    """Binds this module's builders. See ``decls.register`` on why a function."""

    def _make(vocabulary, separate, tree_sites=True):
        def builder(ctx, node):
            return _statement(ctx, node, vocabulary, separate, tree_sites)
        return builder

    for rule_name in _FIELD_RULES:
        registry.register(
            rule_name, _make(_FIELD_VOCABULARY, _after_a_width_bracket))

    # ``bind`` opts out of the tree sites for the same reason it has its own
    # vocabulary: its ``*`` is a wildcard, and a walk that classified operators
    # would have to have an opinion about it.
    registry.register(
        "object_bind_stmt",
        _make(_BIND_VOCABULARY,
              lambda left, right: (_after_a_width_bracket(left, right)
                                   or _around_a_bind_wildcard(left, right)),
              tree_sites=False))

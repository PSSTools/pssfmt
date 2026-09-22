"""Tier 2 -- constraints (``P3-5``).

The corpus has 52 constraint declarations and 102 body items, and the shape of
this module is decided almost entirely by how lopsided that distribution is::

    expression_constraint_item      90   (23 files)
    implication_constraint_item      6   ( 5 files)
    default_constraint               2   ( 2 files)
    if_constraint_item               1
    foreach_constraint_item          1
    unique_constraint_item           1
    dist_directive                   1
    forall_constraint_item           0

**Every one of the 102 is written on a single line.** So a constraint body
item is a run of tokens ending in ``;``, which is a thing this codebase
already knows how to emit, and there is no ``Fill``, no range-list breaking
and no fit decision anywhere in here. ``PLAN.md`` budgeted for those; the
measurement says the corpus does not ask for them, and building a
line-breaking policy against zero instances would be inventing one.

The two shapes of a declaration
-------------------------------
The grammar has ``constraint <set>`` and ``[dynamic] constraint <name>
<block>``, and the corpus writes them differently enough that they are two
rules rather than one::

    constraint len in [1..4096];          20 / 20 on one line,  7 files
    constraint checkable_c {              31 / 32 broken,      14 files
        blk.pattern != MEM_PATTERN_UNKNOWN;
    }

A named constraint is therefore laid out as a *block* -- the same
:func:`~pssfmt.rules.decls._block` every declaration body uses, which is why
that function grew a *body* parameter rather than this module growing a copy
of it. The 31-against-1 split also means a one-item body is **not** collapsed
onto one line: 21 of the 31 have exactly one item and are still written open.

An anonymous constraint is a statement: keyword, expression, semicolon.

Nested braces decline, and that is the vocabulary doing it
----------------------------------------------------------
``TOK_LCBRACE`` is absent from :data:`_ITEM_VOCABULARY`, so an item whose body
is a block -- ``(a > 0) -> { b > 0; c > 0; }``, ``if (x) { … } else { … }`` --
declines without this module testing for it. That is worth stating because it
is the difference between a boundary and a special case: nothing here knows
what an ``if`` constraint is, and nothing had to.

What is declined, and why each
------------------------------
Every entry below is a construct with **one instance or none** in the corpus.
The test applied to each is not "is it hard" but *does formatting it require
a decision the corpus has not made* -- and where the answer is yes, one
instance cannot make it.

``if`` / ``else``
    One instance. Needs a brace-placement rule for ``else`` (``} else {`` or
    ``}\\nelse {``), which ``docs/style.rst`` does not decide and one example
    cannot. The condition's parens are already measured (118/118); the
    ``else`` is the open question.
``foreach``
    One instance, and it is the ``foreach (chans[i])`` spelling -- so the
    corpus contains **zero** measurements of the iterator colon in
    ``foreach (i : list)``. That would be a fifth colon construct, and
    ``docs/style.rst`` names four because four is what was measured.
``forall``
    Zero instances.
``unique``
    One instance. Its ``{a, b}`` is a *list* brace, and ``Site.BRACE_OPEN``
    was measured on 725 declaration bodies -- a different construct that
    happens to share the character. The same argument ``P3-3`` used to drop
    ``pool[4]``.
``dist``
    Blocked upstream: ``dist`` constraints do not parse (``U-8b``), so the
    one corpus instance is inside a file the parser rejects and there is no
    tree to lay out.
``generic_constraint_*``
    Zero instances.

Soft and default constraints are *in* despite being thin (0 and 2 instances)
because they need no decision at all: ``soft`` and ``default`` are word-class
keywords and every other gap in them comes from a site already measured for
something else. Thin evidence is a reason to be careful about inventing a
rule, not a reason to decline one that follows entirely from rules already
made.
"""

from __future__ import annotations

from typing import Any, Tuple

from ..layout import Layout, Verbatim, concat, text
from ..style import Construct, Site
from .emit import code_span
from .exprs import EXPRESSION_COLON, EXPRESSION_VOCABULARY, sites_for
from .tokens import WORD, emit_span

#: Keywords that introduce a constraint or one of its items. All word-class:
#: they need separating from a neighbour and have no other spacing opinion.
#:
#: ``->`` is the exception, and the only genuinely new operator here:
#: ``Site.IMPLICATION``, spaced 6 times out of 6 across 5 independent files.
#: ``docs/style.rst`` lists it under what the page does not decide, on 14
#: instances of bitwise-and-shift lumped together; measured on its own it
#: agrees with the general binary-operator rule it was being defaulted to.
_ITEM_KEYWORDS = ("TOK_CONSTRAINT", "TOK_SOFT", "TOK_DEFAULT", "TOK_DISABLE")

#: A constraint body item: an expression, plus the few keywords that can
#: introduce one, plus the terminator.
#:
#: Built from the expression vocabulary because that is what a constraint
#: *is* -- 90 of the 102 items in the corpus are an expression and a
#: semicolon. Note ``TOK_LCBRACE`` is not here: see the module docstring on
#: why nested blocks decline without being mentioned.
_ITEM_VOCABULARY = dict(EXPRESSION_VOCABULARY)
_ITEM_VOCABULARY.update((name, WORD) for name in _ITEM_KEYWORDS)
_ITEM_VOCABULARY.update({
    "TOK_SEMICOLON": Site.SEMICOLON,
    "TOK_IMPLIES": Site.IMPLICATION,
})
# `S-10`: a `:` in a constraint item is a bit slice or a ternary. See
# `exprs.EXPRESSION_COLON` for the closure argument and what it costs.
_ITEM_VOCABULARY.update(EXPRESSION_COLON)

#: The rules this module emits as a one-line statement. All of them are
#: ``<tokens> ;`` and all of them are one line in every corpus instance.
_ITEM_RULES = (
    "expression_constraint_item",
    "implication_constraint_item",
    "soft_constraint_item",
    "default_constraint",
    "default_disable_constraint",
)


#: What :mod:`pssfmt.rules.exprs` cannot be expected to know.
#:
#: ``default len == 64;`` puts its ``==`` directly on ``default_constraint``
#: rather than inside an ``eq_neq_op``, so the completeness check refuses it --
#: correctly, because nothing in the expression module knows what that token
#: is doing there. It is an equality by spelling and by spacing (both corpus
#: instances write it spaced, and ``Site.EQUALITY`` is 48/48 spaced), so
#: naming it costs no new decision. This module knows; it says so.
_EXTRA_SITES = {
    "default_constraint": {"TOK_DOUBLE_EQ": Site.EQUALITY},
}


#: The grammar's binary-operator rules, as :mod:`pssfmt.rules.exprs` names
#: them. Used only to count: see :func:`_operator_stop`.
_BINARY_OPS = frozenset({
    "add_sub_op", "mul_div_mod_op", "logical_inequality_op", "eq_neq_op",
    "logical_and_op", "logical_or_op", "binary_and_op", "binary_or_op",
    "binary_xor_op", "shift_op",
})


def _operator_stop(ctx: Any, node: Any) -> Tuple[int, ...]:
    """The column a hand-aligned constraint block lines up its operator on::

        dst.mem.size == src.mem.size;
        dst.pattern  == src.pattern;
        dst.seed     == src.seed;
                    ^^

    Returned **only** when the item contains exactly one binary operator, and
    that restriction is the whole design. "The column is before the operator"
    is unambiguous for ``a == b`` and a choice for ``a && b == c`` -- and
    which operator a nested expression would align on is a decision the
    corpus has not made. One operator, one candidate, nothing to decide.

    The evidence for the *padding* is thin and stated as such: two instances,
    in one file, against 72 written tight across 17. On its own that is one
    voice, and ``P3-4`` declined ``**`` on exactly that basis.

    What makes this different is that a stop is not a decision to pad. It says
    a column may exist here; :func:`~pssfmt.layout.align._was_aligned` then
    reads each block's own spacing and reproduces or flushes accordingly. All
    72 tight instances are unaffected either way -- with no padding to find,
    the block flushes left and lands back on the single space it already had.
    So the choice here is not "align constraints or not"; it is whether an
    author's existing table survives contact with the formatter, and the
    project's contract already answers that.
    """
    ops = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if not cur.is_rule:
            continue
        if cur.rule_name in _BINARY_OPS:
            ops.append(cur)
            continue
        stack.extend(reversed(cur.children))
    # One guard, not two. An early ``return`` on the second operator would be
    # a free optimisation and would also make this check unremovable without
    # a test noticing -- the redundancy ``P3-4`` found in its ``>>`` guard and
    # fixed the same way.
    if len(ops) != 1:
        return ()
    span = code_span(ctx.trivia, ops[0])
    return () if span is None else (span[0],)


def _statement(ctx: Any, node: Any, vocabulary: Any = None) -> Layout:
    """*node* written out on one line, or reproduced if it is not ours.

    *vocabulary* defaults to :data:`_ITEM_VOCABULARY`. ``S-12``'s ``unique``
    passes its own, so that the brace it needs stays out of the set whose
    omission of that brace is still declining braced implications.
    """
    span = code_span(ctx.trivia, node)
    if span is None:
        return _reproduce(ctx, node)
    sites = sites_for(ctx, node, extra_rules=_EXTRA_SITES)
    if sites is None:
        return _reproduce(ctx, node)
    # No ``separate`` callback, deliberately. :mod:`pssfmt.rules.stmts` needs
    # one because ``bit[64] x`` puts a ``]`` next to a declarator; a constraint
    # item has no declarator, so after a ``]`` the grammar allows only an
    # operator, a comma, a closing bracket or the semicolon -- never a word.
    # A callback here was written, ran 155 times over the corpus, and returned
    # true zero times; dead code that adds a space reads as a decision somebody
    # made, and this one nobody had to.
    emitted = emit_span(ctx, span[0], span[1],
                        vocabulary or _ITEM_VOCABULARY,
                        sites_at=sites, mark_at=_operator_stop(ctx, node))
    return emitted if emitted is not None else _reproduce(ctx, node)


def _unique(ctx: Any, node: Any) -> Layout:
    """``unique {a, b};`` -- a one-line statement with a list brace (``S-12``).

    ``unique_constraint_argument`` is
    ``'{' hierarchical_id_list '}' | hierarchical_id``, so both spellings are
    a run of tokens ending in ``;`` and this is :func:`_statement` with one
    more vocabulary entry. The decision is which site that entry names, and
    it is argued in :data:`_UNIQUE_VOCABULARY`.
    """
    return _statement(ctx, node, vocabulary=_UNIQUE_VOCABULARY)


def _reproduce(ctx: Any, node: Any) -> Layout:
    # Lazy, for the same reason ``stmts`` does it: ``decls`` owns the body
    # layout that calls into here, and reproduction is its notion.
    from .decls import _reproduce as reproduce

    return reproduce(ctx, node)


#: ``if (a > 0) {`` and ``foreach (i : list) {`` inside a constraint block.
#:
#: A separate vocabulary from :data:`_ITEM_VOCABULARY`, and the separation is
#: the point rather than a convenience: ``TOK_LCBRACE`` is admissible *here*
#: and stays out of the item vocabulary, where its absence is still what
#: declines a braced implication (``(a > 0) -> { b > 0; c > 0; }``). Scoping
#: the brace per rule rather than per module is what let ``S-1`` and ``S-12``
#: land without one silently un-declining the other's construct.
#: ``unique {chans, addrs};`` (``S-12``).
#:
#: Its own vocabulary for the same reason the control one has its own: the
#: brace is admissible *here* and nowhere else in this module, so admitting
#: it cannot un-decline the braced implication that
#: :data:`_ITEM_VOCABULARY`'s omission is still refusing.
#:
#: ``Site.LIST_BRACE_*`` rather than ``BRACE_*``, and that is the whole
#: decision: 725 declaration bodies measured one answer for a brace that
#: opens a *body*, and this one delimits a list. Every list-like construct
#: the corpus does measure is tight inside.
_UNIQUE_VOCABULARY = dict(_ITEM_VOCABULARY)
_UNIQUE_VOCABULARY["TOK_UNIQUE"] = WORD
_UNIQUE_VOCABULARY["TOK_LCBRACE"] = Site.LIST_BRACE_OPEN
_UNIQUE_VOCABULARY["TOK_RCBRACE"] = Site.LIST_BRACE_CLOSE

_CONTROL_VOCABULARY = dict(_ITEM_VOCABULARY)
_CONTROL_VOCABULARY.update((name, WORD) for name in ("TOK_IF", "TOK_FOREACH"))
_CONTROL_VOCABULARY["TOK_LCBRACE"] = Site.BRACE_OPEN

#: Each control item's own parens -- and ``foreach``'s own colon, which is its
#: **direct** terminal, so a colon deeper in the expression keeps the item
#: vocabulary's bit-slice answer. Same mechanism as ``default y == 2;``.
_CONTROL_SITES = {
    "if_constraint_item": {
        "TOK_LPAREN": Site.CONTROL_PAREN_OPEN,
        "TOK_RPAREN": Site.CONTROL_PAREN_CLOSE,
    },
    "foreach_constraint_item": {
        "TOK_LPAREN": Site.CONTROL_PAREN_OPEN,
        "TOK_RPAREN": Site.CONTROL_PAREN_CLOSE,
        "TOK_COLON": Site.COLON_ITERATOR,
    },
}


def _constraint_block_of(node: Any) -> Any:
    """The braced ``constraint_set`` before any ``else``, or ``None``.

    ``constraint_set`` is ``constraint_body_item | constraint_block``, and
    only the second is braced -- ``if (a) b < c;`` is legal and is the
    unbraced branch this module declines for the same reason
    ``pssfmt.rules.procedural`` does: laying it out needs a second decision
    and inserting braces would change the token stream.
    """
    from .decls import _effective

    for child in node.children:
        if not child.is_rule:
            if getattr(child.token, "type_name", None) == "TOK_ELSE":
                return None
            continue
        if child.rule_name != "constraint_set":
            continue
        inner = _effective(child)
        return inner if getattr(inner, "rule_name", None) == "constraint_block" \
            else None
    return None


def _else_set(node: Any) -> Any:
    """Whatever follows ``else``, braced or not, or ``None`` if there is none."""
    from .decls import _effective

    seen_else = False
    for child in node.children:
        if not child.is_rule:
            if getattr(child.token, "type_name", None) == "TOK_ELSE":
                seen_else = True
            continue
        if child.rule_name == "constraint_set" and seen_else:
            return _effective(child)
    return None


def _clean_before(ctx: Any, pos: int) -> bool:
    """Whitespace only before code position *pos*. See
    ``procedural._nothing_but_whitespace_before`` for what this prevents."""
    code = ctx.trivia.code_indices
    if pos <= 0 or pos >= len(code):
        return False
    run = list(ctx.trivia.of(code[pos - 1]).raw_trailing) \
        + list(ctx.trivia.of(code[pos]).raw_leading)
    return all(not tok.text.strip() for tok in run)


def _control(ctx: Any, node: Any) -> Layout:
    """``if (…) { … } else { … }`` and ``foreach (…) { … }`` (``S-1``, ``S-5``).

    One instance each in the corpus, and both were declined for a decision
    rather than for difficulty: where ``} else {`` goes, and what the iterator
    colon looks like. Both are decided now, and neither is decided *here* --
    they are language-wide answers in ``docs/style.rst``, which is why the
    same two questions unblocked the same two constructs in three modules.
    """
    from .decls import _block

    body = _constraint_block_of(node)
    if body is None:
        return _reproduce(ctx, node)
    sites = sites_for(ctx, node, extra_rules=_CONTROL_SITES)
    if sites is None:
        return _reproduce(ctx, node)

    tail = None
    otherwise_set = _else_set(node)
    if otherwise_set is not None:
        name = getattr(otherwise_set, "rule_name", None)
        if name == "if_constraint_item":
            otherwise = _control(ctx, otherwise_set)
        elif name == "constraint_block":
            otherwise = _block(ctx, otherwise_set, Construct.CONSTRAINT_IF_BODY)
        else:
            return _reproduce(ctx, node)
        span = code_span(ctx.trivia, body)
        if span is None or not _clean_before(ctx, span[1] + 1) \
                or not _clean_before(ctx, span[1] + 2) \
                or isinstance(otherwise, Verbatim):
            return _reproduce(ctx, node)
        tail = concat([
            text(" " * ctx.style.gap(Site.BLOCK_TAIL, None) + "else"
                 + " " * ctx.style.gap(None, Site.BLOCK_TAIL)),
            otherwise,
        ])
    return _block(ctx, node, Construct.CONSTRAINT_IF_BODY, body=body,
                  vocabulary=_CONTROL_VOCABULARY, sites=sites, tail=tail)


def _block_of(node: Any) -> Any:
    """The ``constraint_block`` child, if this is the named form."""
    for child in node.children:
        if child.is_rule and child.rule_name == "constraint_block":
            return child
    return None


def _declaration(ctx: Any, node: Any) -> Layout:
    """``constraint c { … }`` as a block, ``constraint e;`` as a statement."""
    from .decls import _block

    block = _block_of(node)
    if block is not None:
        return _block(ctx, node, Construct.CONSTRAINT_BODY, body=block)
    return _statement(ctx, node)


def register(registry) -> None:
    """Binds this module's builders. See ``decls.register`` on why a function."""
    registry.register("constraint_declaration", _declaration)
    registry.register("unique_constraint_item", _unique)
    registry.register("if_constraint_item", _control)
    registry.register("foreach_constraint_item", _control)
    for rule_name in _ITEM_RULES:
        registry.register(rule_name, _statement)

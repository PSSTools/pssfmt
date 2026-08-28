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

from typing import Any

from ..layout import Layout
from ..style import Construct, Site
from .emit import code_span
from .exprs import EXPRESSION_VOCABULARY, sites_for
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


def _statement(ctx: Any, node: Any) -> Layout:
    """*node* written out on one line, or reproduced if it is not ours."""
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
    emitted = emit_span(ctx, span[0], span[1], _ITEM_VOCABULARY,
                        sites_at=sites)
    return emitted if emitted is not None else _reproduce(ctx, node)


def _reproduce(ctx: Any, node: Any) -> Layout:
    # Lazy, for the same reason ``stmts`` does it: ``decls`` owns the body
    # layout that calls into here, and reproduction is its notion.
    from .decls import _reproduce as reproduce

    return reproduce(ctx, node)


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
    for rule_name in _ITEM_RULES:
        registry.register(rule_name, _statement)

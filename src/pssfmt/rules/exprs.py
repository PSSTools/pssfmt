"""Tier 1 -- expressions (``P3-4``).

1383 of them in the corpus, and **not one spans a line**. That measurement
decides the shape of this module before anything else does: an expression is
a run of tokens with computed gaps, not a structure that has to break, so
there is no ``Group``, no ``Fill`` and no fit decision here. Line breaking
inside an expression is a real question for wide constraint and activity
expressions later; it is not a question this corpus asks.

Why a vocabulary is not enough
------------------------------
Every rule module so far could name its tokens and stop, because a token type
answered the spacing question by itself. Expressions are where that stops
being true, and it stops being true twice:

``-`` and friends
    ``-`` is unary 103 times and additive 49 times. ``+``, ``&``, ``|`` and
    ``^`` are all in both ``unary_op`` and a binary operator rule too. A
    vocabulary keyed by token type has one slot and there are two answers.
``(``
    Three constructs, and the corpus contains all three in the same
    expressions: a call ``f(a, b)``, a grouping ``(a + b)``, and a cast
    ``(bit[32])x``. They partition the corpus's 65 expression parens exactly
    -- 40, 12, 13 -- so this is not a corner case.
``[``
    Four: an index ``a[i]``, a declarator dimension ``chan[4]``, a type width
    ``bit[64]`` and a set ``in [1..4096]``. The first three are tight and the
    fourth is spaced, and ``bit[3] in [2..4]`` writes two of them three
    characters apart -- inside a *single* grammar node, which is why
    :func:`_assign_domain_brackets` exists (``P3-5``).

The grammar already distinguishes all of them: ``unary_op`` and ``add_sub_op``
are different rules, and so are ``paren_expr``, ``cast_expression`` and
``function_parameter_list``. So the site comes from the **tree**, through
``emit_span``'s ``sites_at``, and the vocabulary is reduced to its other job
-- saying which tokens are recognised at all.

That inverts the usual reading of :mod:`pssfmt.rules.tokens`: here the
vocabulary is the gate and the tree is the decision. It is also why
:func:`sites_for` checks its own completeness. A position it forgot does not
raise; it quietly falls back to the token type's answer, and for an ambiguous
type that answer is *wrong* rather than missing. Everything ambiguous is
therefore listed in :data:`_TREE_DECIDED`, and an unassigned one is a refusal.

What this module declines, and why each
---------------------------------------
``**`` (``exp_op``)
    65 instances, **one voice**. That voice writes ``a**2``, unanimously; the
    general binary-operator rule in ``docs/style.rst`` says spaced. One file
    cannot decide a site -- ``tools/style_survey.py`` says so in its own
    docstring -- and inventing ``Site.EXPONENT`` from it would be the mistake
    ``P3-3`` refused to make with ``pool[4]``, while spacing it would
    overrule the only evidence there is with a number never measured on it.
    So: no site, no formatting, and the author's text stands. Revisit when a
    second voice appears.
``>>``
    PSS has no ``>>`` token: ``shift_op`` is ``TOK_GT TOK_GT``, two tokens
    that must be written with *nothing* between them while the operator as a
    whole is spaced. ``max(left.after, right.before)`` cannot say "zero here,
    one outside" for one token type, and ``separate`` is a floor -- it can
    raise a gap, never lower one. Emitting it would produce ``a > > b``:
    valid, token-equivalent, and not what anyone wrote. One instance in the
    corpus, so the cost of declining is one expression. ``<<`` is a single
    token and is formatted normally.
``{1, 2, 3}``
    An aggregate literal: 2 instances, 2 files, nothing decidable. Its brace
    would have to borrow ``Site.BRACE_OPEN``, which was measured on 725
    *declaration* braces.
``<T, N>``
    A template argument list, reached through a cast's type. ``P3-7``, the
    same place ``P3-2b`` and ``P3-3`` sent it.
``? :``
    Zero instances in the corpus, and the ``:`` would be a fifth colon
    construct with no measured rule. ``docs/style.rst`` names four.

Authored parens are never re-derived
------------------------------------
``formatter.md`` section 2.2 lists "re-insert semantically required parens
from precedence" as a hazard of an AST-based formatter, which loses ``(a + b)``
and has to reconstruct it from operator precedence -- a computation that is
correct only if the precedence table is. This formatter reads a **CST**, where
``paren_expr`` is a node holding two real tokens, so the parens are copied
rather than inferred and there is no precedence table to be wrong. The
property is asserted directly in ``T-23`` rather than left implied.
"""

from __future__ import annotations

import bisect
from typing import Any, Dict, Mapping, Optional

from ..style import Site
from .emit import code_span
from .tokens import WORD

__all__ = ["ATOMS", "WORD_LIKE", "EXPRESSION_VOCABULARY", "TREE_DECIDED",
           "sites_for"]

#: Literals and names -- the leaves of an expression, with no spacing opinion.
#: Shared with :mod:`pssfmt.rules.stmts`, which adds the field modifiers.
ATOMS = (
    "ID", "ESCAPED_ID",
    "DEC_LITERAL", "HEX_LITERAL", "OCT_LITERAL", "BIN_LITERAL",
    "BASED_DEC_LITERAL", "BASED_HEX_LITERAL", "BASED_OCT_LITERAL",
    "BASED_BIN_LITERAL",
    "FLOAT_DEC_LITERAL", "FLOAT_SCI_LITERAL",
    "DOUBLE_QUOTED_STRING",
    "TOK_TRUE", "TOK_FALSE", "TOK_NULL",
)

#: The scalar type keywords, which reach an expression through a cast.
_CAST_TYPES = (
    "TOK_BIT", "TOK_INT", "TOK_BOOL", "TOK_STRING",
    "TOK_FLOAT32", "TOK_FLOAT64", "TOK_CHANDLE",
)

#: Punctuation whose site *is* a property of the token type. Three of them:
#: everything else in an expression is ambiguous or is a bracket.
_PUNCTUATION = {
    "TOK_DOUBLE_COLON": Site.SCOPE_RESOLUTION,
    "TOK_DOT": Site.MEMBER_ACCESS,
    "TOK_COMMA": Site.COMMA,
    "TOK_ELIPSIS": Site.RANGE,
}

#: ``in``, the set-membership keyword. Word-class, like any other keyword;
#: the bracket that follows it is where the decision lives.
_KEYWORDS = ("TOK_IN",)

#: Token types whose site must come from the tree. Two families:
#:
#: * genuinely ambiguous -- ``+``, ``-``, ``&``, ``|``, ``^`` are each both a
#:   unary and a binary operator, and every bracket is two or three constructs;
#: * unambiguous today but named by the grammar anyway -- ``*``, ``%``, ``==``.
#:   These are here so the rule is *one* rule rather than a rule and a list of
#:   exceptions, and so that a grammar change cannot silently reclassify one.
TREE_DECIDED = frozenset({
    "TOK_LPAREN", "TOK_RPAREN", "TOK_LSBRACE", "TOK_RSBRACE",
    "TOK_PLUS", "TOK_MINUS", "TOK_ASTERISK", "TOK_DIV", "TOK_MOD",
    "TOK_LT", "TOK_LTE", "TOK_GT", "TOK_GTE",
    "TOK_DOUBLE_EQ", "TOK_NE",
    "TOK_DOUBLE_AND", "TOK_DOUBLE_OR",
    "TOK_SINGLE_AND", "TOK_SINGLE_OR", "TOK_CARET",
    "TOK_NOT", "TOK_NEG",
    "TOK_DOUBLE_LT",
})

#: Everything an expression may contain. Tree-decided types map to ``WORD``
#: because their real site arrives through ``sites_at``; the vocabulary's job
#: for them is only to say "recognised".
EXPRESSION_VOCABULARY = dict(
    [(name, WORD) for name in ATOMS + _CAST_TYPES + _KEYWORDS]
    + [(name, WORD) for name in TREE_DECIDED]
    + list(_PUNCTUATION.items())
)

#: Everything in this module that is a word rather than punctuation.
#:
#: Its use is the ``]``-meets-a-name seam: ``bit[64] x`` and ``bit[3] in
#: [2..4]`` both need a space that ``max(left.after, right.before)`` cannot
#: produce, and the rule supplying it has to know what counts as a name. It
#: is derived rather than written out so that adding a keyword to the
#: vocabulary cannot silently leave it out -- which is exactly how
#: ``bit[3]in [2..4]`` got emitted once.
WORD_LIKE = frozenset(ATOMS + _CAST_TYPES + _KEYWORDS)

#: Grammar rule -> the site every terminal it owns gets. The precedence
#: classes ``docs/style.rst`` names, spelled the way the grammar spells them.
_OPERATOR_SITES = {
    "unary_op": Site.UNARY,
    "add_sub_op": Site.ADDITIVE,
    "mul_div_mod_op": Site.MULTIPLICATIVE,
    "logical_inequality_op": Site.COMPARISON,
    "eq_neq_op": Site.EQUALITY,
    "logical_and_op": Site.LOGICAL,
    "logical_or_op": Site.LOGICAL,
    "binary_and_op": Site.BITWISE,
    "binary_or_op": Site.BITWISE,
    "binary_xor_op": Site.BITWISE,
    # Only ever reached for `<<`: see the precondition in :func:`_walk`.
    "shift_op": Site.SHIFT,
}


def _terminal_count(node: Any) -> int:
    return sum(1 for child in node.children if not child.is_rule)


def _assign_domain_brackets(ctx: Any, node: Any, sites: Dict[int, Site]) -> None:
    """``bit[3] in [2..4]`` -- a width bracket and a domain bracket, one node.

    ``integer_type`` is ``integer_atom_type ('[' width ']')? ('in' '[' … ']')?``
    and ``string_type`` has the same domain tail, so a single node can carry
    both brackets: one tight 333 times out of 333, the other spaced 14 out of
    16. Which is which is *positional* -- everything after the ``in`` keyword
    is the domain -- so this cannot be a per-node answer the way every other
    bracket in :data:`_BRACKET_SITES` is. Getting that wrong emits
    ``int in[1..4]``, which no file in the corpus writes and which reads as a
    subscript.
    """
    seen_in = False
    for child in node.children:
        if child.is_rule:
            continue
        type_name = child.token.type_name
        if type_name == "TOK_IN":
            seen_in = True
            continue
        if type_name not in _OPENERS and type_name not in _CLOSERS:
            continue
        if seen_in:
            site = (Site.SET_BRACKET_OPEN if type_name in _OPENERS
                    else Site.SET_BRACKET_CLOSE)
        else:
            site = (Site.TYPE_BRACKET_OPEN if type_name in _OPENERS
                    else Site.TYPE_BRACKET_CLOSE)
        _assign(ctx, child, site, sites)

#: Grammar rule -> the (open, close) sites for the bracket pair it owns.
#: Note ``paren_expr`` and ``cast_expression`` share one pair: see
#: ``DEFAULT_SPACING`` on why the corpus gives those two constructs one answer.
_BRACKET_SITES = {
    "paren_expr": (Site.GROUP_PAREN_OPEN, Site.GROUP_PAREN_CLOSE),
    "cast_expression": (Site.GROUP_PAREN_OPEN, Site.GROUP_PAREN_CLOSE),
    "function_parameter_list": (Site.CALL_PAREN_OPEN, Site.CALL_PAREN_CLOSE),
    # `x in [1..4096]` (``P3-5``). The one bracket in PSS written with a space
    # before it, which is why it is not the index bracket it looks like.
    "in_expression": (Site.SET_BRACKET_OPEN, Site.SET_BRACKET_CLOSE),
    "member_path_elem_index": (Site.INDEX_BRACKET_OPEN,
                               Site.INDEX_BRACKET_CLOSE),
    # `bit chan[4];` -- a declarator dimension rather than a subscript, but
    # the same bracket by shape and by evidence: 34/34 tight across 17 files,
    # against ``INDEX_BRACKET_OPEN``'s 1002/1002. Present because the
    # completeness check found it: through ``P3-3`` these 34 declarations got
    # the site from their token type and nobody had to name the construct.
    "array_dim": (Site.INDEX_BRACKET_OPEN, Site.INDEX_BRACKET_CLOSE),
}

#: Openers, so a pair is matched by shape rather than by counting children.
_OPENERS = {"TOK_LPAREN", "TOK_LSBRACE"}
_CLOSERS = {"TOK_RPAREN", "TOK_RSBRACE"}

#: Rules whose brackets need :func:`_assign_domain_brackets` because one node
#: can hold two kinds. See there.
_DOMAIN_BEARING = frozenset({"integer_type", "string_type"})

#: Constructs this module refuses outright. Each is argued in the module
#: docstring; none of them is "not implemented yet" in the sense of being an
#: oversight, and three of them belong to a later item by name.
_DECLINED = frozenset({
    "exp_op",
    "aggregate_literal",
    "value_list_literal",
    "template_param_value_list",
    "conditional_expr",
})


def sites_for(ctx: Any, node: Any,
              extra_rules: Optional[Mapping[str, Mapping[str, Site]]] = None
              ) -> Optional[Dict[int, Site]]:
    """Sites for every tree-decided token under *node*, or ``None`` to decline.

    ``None`` is returned for a declined construct (see the module docstring)
    and -- crucially -- for any token in :data:`TREE_DECIDED` this walk did not
    reach. That second case is the completeness check, and it is what makes
    the strictness here safe to rely on: a construct nobody thought about
    declines rather than picking up whatever its token type happens to mean
    somewhere else.

    *extra_rules* maps a grammar rule name to ``{token type: site}`` for its
    **direct** terminals, and exists so a caller can teach this walk about a
    construct outside expressions without that construct's tokens having to be
    guessed at here. ``P3-5``'s case is ``default len == 64;``: the ``==``
    belongs to ``default_constraint`` itself rather than to an ``eq_neq_op``,
    so the completeness check refuses it -- correctly, since nothing in this
    module knows what it is. The constraint module does, and says so.
    """
    span = code_span(ctx.trivia, node)
    if span is None:
        return None
    sites: Dict[int, Site] = {}
    if not _walk(ctx, node, sites, extra_rules or {}):
        return None
    code = ctx.trivia.code_indices
    for pos in range(span[0], span[1] + 1):
        if pos in sites:
            continue
        if ctx.trivia.of(code[pos]).token.type_name in TREE_DECIDED:
            return None
    return sites


def _walk(ctx: Any, node: Any, sites: Dict[int, Site],
          extra_rules: Mapping[str, Mapping[str, Site]]) -> bool:
    """Depth-first assignment. ``False`` means a declined construct was met."""
    if not node.is_rule:
        return True
    name = node.rule_name
    if name in _DECLINED:
        return False
    if name == "shift_op" and _terminal_count(node) != 1:
        # `<<` is one token and formats; `>>` is two, and the branch below
        # would happily give a site to each -- producing `a > > b`, which the
        # completeness check cannot object to because nothing is missing. So
        # the precondition is here, before any site is assigned, and counting
        # is the whole of it: the number of tokens *is* the difference.
        return False
    if name in _OPERATOR_SITES:
        site = _OPERATOR_SITES[name]
        for child in node.children:
            if not child.is_rule:
                _assign(ctx, child, site, sites)
    if name in _DOMAIN_BEARING:
        _assign_domain_brackets(ctx, node, sites)
    elif name in _BRACKET_SITES:
        open_site, close_site = _BRACKET_SITES[name]
        for child in node.children:
            if child.is_rule:
                continue
            type_name = child.token.type_name
            if type_name in _OPENERS:
                _assign(ctx, child, open_site, sites)
            elif type_name in _CLOSERS:
                _assign(ctx, child, close_site, sites)
    for token_type, site in extra_rules.get(name, {}).items():
        for child in node.children:
            if not child.is_rule and child.token.type_name == token_type:
                _assign(ctx, child, site, sites)
    return all(_walk(ctx, child, sites, extra_rules)
               for child in node.children)


def _assign(ctx: Any, terminal: Any, site: Site, sites: Dict[int, Site]) -> None:
    """Records *site* at the code position of *terminal*.

    A terminal carries a *stream* index, and every position in this module is
    a position in ``code_indices``. The two differ by however much trivia is
    in between, so the translation is a search rather than an offset.

    The guard is unreachable by construction -- a terminal in the tree is
    always a code token, and it fired zero times in 440 assignments over the
    corpus. It stays because *not* recording a site is the safe answer if the
    invariant is ever wrong: the completeness check in :func:`sites_for` then
    declines the span, where writing to a mismatched position would instead
    move some unrelated token's spacing and say nothing.
    """
    code = ctx.trivia.code_indices
    pos = bisect.bisect_left(code, terminal.token_index)
    if pos < len(code) and code[pos] == terminal.token_index:
        sites[pos] = site

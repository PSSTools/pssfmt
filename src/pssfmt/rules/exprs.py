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
``<``
    Two, and they are the sharpest pair in the language because their
    measured answers are *opposite*. ``a < b`` is ``Site.COMPARISON``, spaced
    128 times out of 130; ``packed_s<T, 32>`` is
    ``Site.TEMPLATE_ANGLE_OPEN``, tight 137 times out of 137 (``P3-7``). One
    character, one token type, and no possible default that is not wrong half
    the time -- so this is the case that would have to be answered from the
    tree even if none of the others were.

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
``{1, 2, 3}``
    An aggregate literal: 2 instances, 2 files, nothing decidable. Its brace
    would have to borrow ``Site.BRACE_OPEN``, which was measured on 725
    *declaration* braces.

Two constructs used to be on that list and are not, and both came off for the
same reason -- the obstacle was a reading of the model rather than the model:

``>>`` (``S-9``)
    PSS has no ``>>`` token: ``shift_op`` is ``TOK_GT TOK_GT``, two tokens
    that must be written with *nothing* between them while the operator as a
    whole is spaced. That was declined as inexpressible, and it is -- for
    *one* site. Two sites express it exactly, because the gap between them is
    ``max(SHIFT_RIGHT_OPEN.after, SHIFT_RIGHT_CLOSE.before) = 0`` while both
    outer gaps are 1. See :func:`_assign_right_shift`, which also carries the
    hazard: two touching ``>`` are also a nested template close.
``? :`` (``S-10``)
    Zero instances in the corpus -- so nothing here is measured, and the two
    sites say so. The ``:`` is not the fifth *colon construct* it looked like:
    it is half of a ternary operator, spaced from the general binary-operator
    rule, which is why it is ``Site.COLON_TERNARY`` and not a fifth row in the
    colon table.

    Where a ternary *breaks* when it does not fit is a separate question and
    is not answered here.

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
from typing import Any, Dict, List, Mapping, Optional

from ..style import Construct, Site
from .emit import code_span
from .tokens import WORD, Wrap

__all__ = ["ATOMS", "WORD_LIKE", "EXPRESSION_VOCABULARY", "EXPRESSION_COLON",
           "EXPRESSION_LIST_BRACE", "TREE_DECIDED", "sites_for",
           "wrap_for"]

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

#: Punctuation whose site *is* a property of the token type. Four of them:
#: everything else in an expression is ambiguous or is a bracket.
#:
#: ``TOK_COLON`` is deliberately absent, and ``S-10`` put it here briefly and
#: took it out again, which is worth recording because the reasoning looked
#: sound. The set of colons reachable *inside an expression* is genuinely
#: closed -- the ternary, two bit-slice spellings, and a map literal that
#: ``aggregate_literal`` already declines -- so a bit-slice fallback here
#: seemed safe. It is not, because this vocabulary is not only used for
#: expressions: ``activities._BLOCK_HEADER_VOCABULARY`` is built from it and
#: covers ``repeat (ri : 4) {``, whose colon is an iterator and is not in an
#: expression at all. The entry emitted ``repeat (ri:4)``.
#:
#: :data:`EXPRESSION_COLON` is the opt-in version, merged by the three
#: callers that can make the closure argument for their own spans.
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
    "TOK_DOUBLE_LT", "TOK_EXP",
    # `?` is unambiguous by type -- `conditional_expr` is the only rule in the
    # grammar that spells one -- and is here for the second reason above: a
    # `?` this walk did not reach is a construct nobody has thought about, and
    # should decline rather than pick up the ternary's answer.
    #
    # `:` is deliberately *not* here, and the reason is the whole of `S-10`'s
    # care. Putting it here makes a claim about the token type everywhere,
    # and four vocabularies outside this module already own a colon by
    # closure -- inheritance in `decls`, the case item in `procedural`. The
    # completeness check is over the caller's whole span, so the claim would
    # refuse every declaration header in the corpus. It is not needed: a
    # ternary's colon is assigned by the walk below, every time, so `sites_at`
    # covers it and the vocabulary's answer is never the one that reaches it.
    "TOK_COND",
})

#: Everything an expression may contain. Tree-decided types map to ``WORD``
#: because their real site arrives through ``sites_at``; the vocabulary's job
#: for them is only to say "recognised".
EXPRESSION_VOCABULARY = dict(
    [(name, WORD) for name in ATOMS + _CAST_TYPES + _KEYWORDS]
    + [(name, WORD) for name in TREE_DECIDED]
    + list(_PUNCTUATION.items())
)

#: The ``:`` entry a caller adds when it wants ternaries (``S-10``).
#:
#: Opt-in rather than part of :data:`EXPRESSION_VOCABULARY`, because that one
#: is shared with spans that are not expressions -- see :data:`_PUNCTUATION`
#: on the ``repeat (ri : 4)`` header it broke. A caller merges this only if it
#: can make the closure argument for its *own* span, and the argument is
#: always the same one: within a field declaration, a procedural statement or
#: a constraint item, a ``:`` is either a bit slice or a ternary. The ternary
#: takes ``Site.COLON_TERNARY`` from the tree and overrides this; the slice is
#: what the entry is for, at ``docs/style.rst``'s tight rule.
#:
#: Two consequences worth stating, since neither is what the item was for. Bit
#: slices become *formatted* in those spans rather than declined, which
#: applies a rule the page already publishes and the corpus already writes
#: tight. And a construct that puts a fifth reading of ``:`` into one of those
#: spans would be emitted with the slice's spacing rather than declined -- so
#: the closure claim is the load-bearing part, exactly as it is for
#: ``decls._HEADER_VOCABULARY``.
EXPRESSION_COLON = {"TOK_COLON": Site.COLON_BIT_SLICE}

#: The list-brace entries a caller adds when it wants aggregate literals
#: (``S-12``).
#:
#: Opt-in for exactly the reason :data:`EXPRESSION_COLON` is: ``{`` is the
#: most overloaded character in PSS -- it opens a declaration body, a
#: constraint block, an activity block, an inline ``with`` constraint and a
#: list -- and every one of those is a *different* site. Putting it in the
#: shared vocabulary would hand a body brace the list's spacing in every
#: header built from that vocabulary.
#:
#: A caller merges this only where a ``{`` in its span can only be a list. The
#: braces are also assigned **from the tree** in :func:`_walk`, so these
#: entries are the gate and the tree is the decision; a brace the walk did not
#: reach is not a list literal and declines.
EXPRESSION_LIST_BRACE = {
    "TOK_LCBRACE": Site.LIST_BRACE_OPEN,
    "TOK_RCBRACE": Site.LIST_BRACE_CLOSE,
}

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
    # Only ever reached for `<<`, which is one token. `>>` is two, and is
    # assigned as a pair -- see :func:`_assign_right_shift`.
    "shift_op": Site.SHIFT,
}


def _assign_right_shift(ctx: Any, node: Any, sites: Dict[int, Site]) -> None:
    """``a >> b`` -- one operator, two tokens, two sites.

    ``shift_op`` is ``TOK_DOUBLE_LT | TOK_GT TOK_GT``, so the right shift is
    the only operator in PSS whose spelling is two tokens. It was declined
    through ``P3-4`` on the grounds that per-token spacing cannot say "tight
    here, spaced outside" -- true of one site, and false of two:
    ``SHIFT_RIGHT_OPEN`` is ``(1, 0)`` and ``SHIFT_RIGHT_CLOSE`` is ``(0, 1)``,
    which compose to 1, 0, 1 across the three seams.

    Nothing in here looks at *adjacency*, and that is the whole of the care
    this function needs. Two touching ``TOK_GT`` are also how a nested
    template argument list closes -- ``packed_s<foo_s<T>>`` -- and those get
    ``TEMPLATE_ANGLE_CLOSE`` from :data:`_ANGLE_SITES`, which reaches them
    through ``template_param_value_list``. Both readings come from the tree,
    never from the characters. Under the shipped defaults the two readings
    happen to render identically, so a mistake here would be invisible until
    somebody configured template angles or comparisons differently.
    """
    seen = 0
    for child in node.children:
        if child.is_rule:
            continue
        site = Site.SHIFT_RIGHT_OPEN if seen == 0 else Site.SHIFT_RIGHT_CLOSE
        _assign(ctx, child, site, sites)
        seen += 1


#: ``p ? a : b`` -- the ternary's two tokens (``S-10``).
#:
#: A rule of its own rather than an entry in :data:`_OPERATOR_SITES` because
#: its two terminals take *different* sites, which that table cannot express:
#: it maps a rule to one site and gives it to every terminal the rule owns.
_CONDITIONAL_SITES = {
    "TOK_COND": Site.TERNARY_COND,
    "TOK_COLON": Site.COLON_TERNARY,
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
    # `function void f(bit[32] addr, int n)` -- the *declaration* of what the
    # line above calls (``P3-11a``). The same site pair, and that is a
    # measurement rather than a convenience: ``tools/style_survey.py`` counts
    # ``callee -> '('`` lexically, as any name followed by ``(`` that is not a
    # control keyword, so its 241/244 already *includes* all 150 corpus
    # prototypes -- 147 of which are tight, which is where three of the four
    # dissenters come from. There is one measurement here, not two.
    #
    # Worth stating because the opposite call was made for ``GROUP_PAREN``:
    # there the corpus measures a grouping paren separately from a call, and
    # the numbers agreeing did not make the decisions one. Here the survey
    # cannot tell them apart, so splitting the site would mean inventing a
    # second default from the first one's evidence. clang-format does split
    # them (``SpaceBeforeParensOptions.AfterFunctionDeclarationName``); the day
    # this corpus can say something about that split is the day to add the
    # site, and it is a survey change first.
    "function_parameter_list_prototype": (Site.CALL_PAREN_OPEN,
                                          Site.CALL_PAREN_CLOSE),
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

#: ``packed_s<T, 32>`` -- the angle pair, kept out of :data:`_BRACKET_SITES`
#: (``P3-7``).
#:
#: Not because it behaves differently -- the assignment below is the same one
#: -- but because *matching by shape* is what the other pairs do, and ``<``
#: cannot be matched that way. ``(`` and ``[`` are punctuation whose only
#: readings are brackets, so a rule owning one owns a pair. ``<`` is
#: ``TOK_LT``, which is a **comparison operator** everywhere else in this
#: module and is spaced there; widening :data:`_OPENERS` to include it would
#: mean every rule in :data:`_BRACKET_SITES` and every
#: :data:`_DOMAIN_BEARING` node silently started claiming any ``<`` beneath
#: it. None of them can contain one today, which is exactly the kind of
#: "safe for now" this module refuses to build on.
#:
#: So the angle pair is matched by *token type* against one named rule, and
#: the ``<`` in ``a < b`` is reached only through ``logical_inequality_op``.
_ANGLE_SITES = {
    "template_param_value_list": (Site.TEMPLATE_ANGLE_OPEN,
                                  Site.TEMPLATE_ANGLE_CLOSE),
    # The *declaring* side (``S-7``): ``struct base_s <struct TRAIT : t = e>``.
    # The same pair, and that is the decision rather than a convenience --
    # ``docs/style.rst`` measured 137/137 tight on argument lists and said
    # explicitly that parameter *declarations* are a different construct it
    # did not decide. What decides them is that the corpus does not disagree
    # about the angles themselves: 7 of its 16 are tight after the ``<`` and
    # the other 9 are not written on one line at all, so the only instances
    # that can hold an opinion hold this one.
    "template_param_decl_list": (Site.TEMPLATE_ANGLE_OPEN,
                                 Site.TEMPLATE_ANGLE_CLOSE),
}

#: ``struct TRAIT : addr_trait_s`` -- a parameter's **bound** (``S-7``).
#:
#: ``Site.COLON_INHERITANCE`` and not a sixth colon site, because it is not a
#: sixth colon *construct*: the thing after it is the type the parameter is
#: bounded by, which is what an inheritance colon separates too. 355/358
#: spaced, and the corpus's template parameter bounds agree.
_BOUND_SITES = {
    "type_restriction": {"TOK_COLON": Site.COLON_INHERITANCE},
}

#: Rules whose brackets need :func:`_assign_domain_brackets` because one node
#: can hold two kinds. See there.
_DOMAIN_BEARING = frozenset({"integer_type", "string_type"})

#: Constructs this module refuses outright. Each is argued in the module
#: docstring; none of them is "not implemented yet" in the sense of being an
#: oversight, and three of them belong to a later item by name.
_DECLINED = frozenset({
    # `{ "a": 1 }` and `{ .x = 1 }`. Both would need a decision this page has
    # not made -- a *sixth* reading of `:` for the map, and a `.name =` seam
    # for the struct -- and the corpus contains neither. `S-12` decided the
    # list brace and stopped there, which is why these are named individually
    # rather than the whole `aggregate_literal` being declined: two of its
    # four alternatives are settled and two are not.
    "map_literal",
    "struct_literal",
})

#: Grammar rules a **simple** operand may be made of, and nothing else
#: (``S-8``).
#:
#: An allowlist rather than a list of disqualifiers, because the two fail in
#: opposite directions and only one of them is safe. A grammar rule this set
#: has never heard of makes the operand *not* simple, so ``**`` comes out
#: spaced -- the conventional answer, and a visible one. Under a blocklist the
#: same unknown rule would make it simple, and ``f(n)**2`` would be emitted
#: tight, which is wrong and looks deliberate.
#:
#: Read positively: a name, a dotted or scoped path, and a number literal of
#: any base. Read by what is *absent*: ``function_parameter_list`` (a call),
#: ``member_path_elem_index`` (a subscript), ``paren_expr``, ``unary_op``, and
#: every operator rule -- so ``f(n)``, ``a[i]``, ``(b + 1)``, ``-a`` and
#: ``a + b`` are all complex.
_SIMPLE_OPERAND_RULES = frozenset({
    "expression", "primary",
    # A name, however qualified: `a`, `p.q.r`, `pkg::C`, `\esc`.
    "ref_path", "hierarchical_id", "member_path_elem", "identifier",
    "static_ref_path", "static_ref_path_prefix", "type_identifier_elem",
    # A literal, in every base the grammar spells.
    "number", "integer_number",
    "dec_number", "hex_number", "oct_number", "bin_number",
    "based_dec_number", "based_hex_number", "based_oct_number",
    "based_bin_number",
    "floating_point_number", "floating_point_dec_number",
    "floating_point_sci_number",
})


def _is_simple(node: Any) -> bool:
    """Whether *node* is an operand ``**`` may be written tight against.

    **The one predicate in this codebase that asks about operand shape.**
    Every other spacing decision here is a function of token adjacency, and
    ``docs/style.rst`` is explicit that the simpler invariant is what makes a
    formatter trustworthy. The concession is made once, for one operator, on
    Black's precedent -- it declined PEP 8's general precedence tightening and
    hugged ``**`` alone, and only when both operands are "simple".

    Kept to one function on purpose. Nothing else in the rule layer gains an
    operand-shape question, and the two sites it chooses between are ordinary
    sites from there on.
    """
    stack = [node]
    while stack:
        cur = stack.pop()
        if not cur.is_rule:
            continue
        if cur.rule_name not in _SIMPLE_OPERAND_RULES:
            return False
        stack.extend(cur.children)
    return True


def _exponent_sites(ctx: Any, node: Any, sites: Dict[int, Site]) -> None:
    """``x**2`` or ``base ** f(n)``, decided by the operands (``S-8``).

    *node* is the ``expression`` that owns the ``exp_op``, so its two
    ``expression`` children are the operands. Both must be simple; one call
    on either side is enough to space the operator.

    A chain needs no special handling and comes out asymmetric, which is
    worth stating because it looks like a bug::

        a**b ** c

    ``exp_op`` is left-recursive in the grammar, so ``a**b**c`` is
    ``(a**b) ** c``. The inner operands are both simple and the inner
    operator is tight; the *outer* left operand contains an ``exp_op``, so it
    is not simple and the outer operator is spaced. Black produces the mirror
    image of this in Python, where ``**`` is right-associative -- so the
    behaviour is the rule applied consistently rather than an oversight, and
    the asymmetry is the reader's cue to the grouping.

    A unary operand is **not** simple: ``-a ** 2``, because ``-a`` is
    ``(-a)`` and ``unary_op`` is not in the allowlist. Narrower than Black,
    which folds a unary into a simple operand, and narrower is the side to
    err on: the corpus contains no such expression and spacing is the
    reversible answer.
    """
    operands = [c for c in node.children
                if c.is_rule and c.rule_name == "expression"]
    simple = len(operands) == 2 and all(_is_simple(o) for o in operands)
    site = Site.EXPONENT if simple else Site.EXPONENT_WIDE
    for child in node.children:
        if child.is_rule and child.rule_name == "exp_op":
            for token in child.children:
                if not token.is_rule:
                    _assign(ctx, token, site, sites)


#: The two aggregate literals ``S-12`` decided, and the brace pair each owns.
_LIST_BRACE_SITES = {
    "value_list_literal": (Site.LIST_BRACE_OPEN, Site.LIST_BRACE_CLOSE),
    "empty_aggregate_literal": (Site.LIST_BRACE_OPEN, Site.LIST_BRACE_CLOSE),
}


#: Grammar rule -> the ``Construct`` whose break policy governs its list
#: (``S-16``).
#:
#: Four entries, and each is a construct ``Construct`` has carried a member
#: for since ``P3-0`` with nothing ever setting it. Naming them here is what
#: makes ``break_policy_for`` reachable at all.
#:
#: ``function_parameter_list`` is a *call*'s arguments and
#: ``function_parameter_list_prototype`` is a declaration's parameters -- the
#: same site pair for spacing, because the survey cannot tell them apart, and
#: deliberately **different** constructs for breaking, because a break policy
#: is a question about a list's shape rather than about a gap and the two
#: lists have visibly different shapes: arguments are short and numerous,
#: parameters are typed and few.
#: ``(construct, open type, close type, separator-bearing child)``.
#:
#: The fourth field is the one that had to exist. For a call the brackets and
#: the commas belong to the same node; for a **range list** they do not --
#: ``in_expression`` is ``'in' '[' open_range_list ']'``, so the brackets are
#: the outer node's and the commas are its child's. Keyed on the bracket
#: owner, because that is the node whose span the wrap has to cover.
_WRAPPED_LISTS = {
    "function_parameter_list":
        (Construct.ARGUMENT_LIST, "TOK_LPAREN", "TOK_RPAREN", None),
    "function_parameter_list_prototype":
        (Construct.PARAMETER_LIST, "TOK_LPAREN", "TOK_RPAREN", None),
    "template_param_value_list":
        (Construct.TEMPLATE_PARAMETER_LIST, "TOK_LT", "TOK_GT", None),
    "template_param_decl_list":
        (Construct.TEMPLATE_PARAMETER_LIST, "TOK_LT", "TOK_GT", None),
    "in_expression":
        (Construct.RANGE_LIST, "TOK_LSBRACE", "TOK_RSBRACE",
         "open_range_list"),
    # `rand bit[8] in [1, 2, 3] v;` -- the *type's* domain, which is a second
    # spelling of the same construct and needs the same positional care
    # `_assign_domain_brackets` needs: `integer_type` holds the width bracket
    # and the domain bracket, and only the second is a list. Everything after
    # the `in` keyword is the domain.
    "integer_type":
        (Construct.RANGE_LIST, "TOK_LSBRACE", "TOK_RSBRACE",
         "domain_open_range_list"),
    "string_type":
        (Construct.RANGE_LIST, "TOK_LSBRACE", "TOK_RSBRACE",
         "domain_open_range_list"),
}


def wrap_for(ctx: Any, node: Any,
             limit: Optional[int] = None) -> Optional[Wrap]:
    """The one bracketed list in *node* that may break, or ``None``.

    ``None`` when there is no list, and when there is more than one at the
    **outermost** level. That second case is the interesting one:
    ``emit_span`` takes a single wrap, so a span holding ``f(a, b) + g(c, d)``
    would have to choose, and choosing by position would be answering an
    undecided policy question by accident. Both are emitted flat, exactly as
    they were before ``S-16``.

    A **nested** list is not a refusal, and getting that wrong made the corpus
    worse before it made it better. ``write32(make_handle(base, i * 4),
    pattern_word(p, s, i))`` is one outer list holding two inner ones, and it
    is the ordinary shape of real code rather than a corner case. The inner
    lists simply do not break: only this list's own direct terminals become
    ``Line`` nodes, so the inner commas render as the plain gaps they always
    were. Refusing them left that call joined onto a 96-column line, which is
    the failure ``S-17`` exists to avoid.

    So the walk stops descending at the first list it finds, and "more than
    one" means two lists neither of which contains the other.
    """
    code = ctx.trivia.code_indices
    found: List[Any] = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if not cur.is_rule:
            continue
        if _is_a_list(cur):
            if limit is not None and not _starts_before(ctx, cur, limit):
                # A list in the *body* of the construct whose header is being
                # emitted. Skipping it rather than counting it is the whole of
                # what `limit` is for: a declaration whose body holds a call
                # would otherwise read as "two lists" and refuse to wrap the
                # header it does have.
                continue
            found.append(cur)
            continue                    # outermost only: do not descend
        stack.extend(cur.children)
    # One guard, not two. An early `return None` on the second list would be
    # a free optimisation and would also make this check unremovable without
    # a test noticing -- it survived a mutation run for exactly that reason,
    # and `constraints._operator_stop` records the same finding one item
    # earlier. `!= 1` covers both refusals: no list, and more than one.
    if len(found) != 1:
        return None

    listed = found[0]
    construct, open_type, close_type, sep_rule = _WRAPPED_LISTS[listed.rule_name]
    open_at = close_at = None
    # `integer_type` carries two bracket pairs and only the one after `in` is
    # a list. For every other rule here there is no `in`, so the flag never
    # turns on and the first pair is taken -- one branch, both shapes.
    in_domain = listed.rule_name not in _DOMAIN_BEARING
    for child in listed.children:
        if child.is_rule or child.token is None:
            continue
        name = child.token.type_name
        if name == "TOK_IN":
            in_domain = True
            continue
        if not in_domain:
            continue
        pos = _position(code, child)
        if pos is None:
            return None
        if name == open_type and open_at is None:
            open_at = pos
        elif name == close_type:
            close_at = pos
    if open_at is None or close_at is None or close_at <= open_at:
        return None

    bearer = listed
    if sep_rule is not None:
        bearer = next((c for c in listed.children
                       if c.is_rule and c.rule_name == sep_rule), None)
        if bearer is None:
            return None
    separators: List[int] = []
    for child in bearer.children:
        if child.is_rule or child.token is None:
            continue
        if child.token.type_name != "TOK_COMMA":
            continue
        pos = _position(code, child)
        if pos is None:
            return None
        separators.append(pos)
    if not separators:
        # A one-item list has nothing to distribute. Breaking it would put a
        # single argument on a line of its own, which is longer than the line
        # it was trying to shorten.
        return None
    return Wrap(construct, open_at, close_at, tuple(separators))


def _is_a_list(node: Any) -> bool:
    """Whether *node* is one of the bracketed lists a wrap can break.

    Not simply membership in :data:`_WRAPPED_LISTS`, because two of its keys
    are types rather than lists: ``integer_type`` is ``bit[32]`` far more
    often than it is ``bit[8] in [1, 2, 3]``, and it is the *domain* that
    makes it a list. Without this the walk found a second "list" in every
    parameter list holding a ``bit[32]``, read that as two lists, and refused
    to wrap -- which is how a 86-column prototype came out unbroken with the
    whole mechanism apparently working.
    """
    if not node.is_rule or node.rule_name not in _WRAPPED_LISTS:
        return False
    if node.rule_name not in _DOMAIN_BEARING:
        return True
    return any(not c.is_rule and c.token is not None
               and c.token.type_name == "TOK_IN" for c in node.children)


def _starts_before(ctx: Any, node: Any, limit: int) -> bool:
    span = code_span(ctx.trivia, node)
    return span is not None and span[0] < limit


def _position(code: Any, terminal: Any) -> Optional[int]:
    """*terminal*'s index in ``code_indices``, or ``None`` if it is not code."""
    pos = bisect.bisect_left(code, terminal.token_index)
    return pos if pos < len(code) and code[pos] == terminal.token_index else None


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
        # `<<` is one token and takes `Site.SHIFT` from the table below. `>>`
        # is two, and giving each the same site would emit `a > > b` -- valid,
        # token-equivalent, and not what anyone wrote. Counting is the whole
        # of the test: the number of tokens *is* the difference between the
        # two operators this rule spells.
        _assign_right_shift(ctx, node, sites)
    elif name in _OPERATOR_SITES:
        site = _OPERATOR_SITES[name]
        for child in node.children:
            if not child.is_rule:
                _assign(ctx, child, site, sites)
    if any(c.is_rule and c.rule_name == "exp_op" for c in node.children):
        _exponent_sites(ctx, node, sites)
    if name in _LIST_BRACE_SITES:
        open_site, close_site = _LIST_BRACE_SITES[name]
        for child in node.children:
            if child.is_rule:
                continue
            if child.token.type_name == "TOK_LCBRACE":
                _assign(ctx, child, open_site, sites)
            elif child.token.type_name == "TOK_RCBRACE":
                _assign(ctx, child, close_site, sites)
    if name == "conditional_expr":
        for child in node.children:
            if child.is_rule:
                continue
            site = _CONDITIONAL_SITES.get(child.token.type_name)
            if site is not None:
                _assign(ctx, child, site, sites)
    if name in _BOUND_SITES:
        for token_type, site in _BOUND_SITES[name].items():
            for child in node.children:
                if not child.is_rule and child.token.type_name == token_type:
                    _assign(ctx, child, site, sites)
    if name in _ANGLE_SITES:
        open_site, close_site = _ANGLE_SITES[name]
        for child in node.children:
            if child.is_rule:
                continue
            if child.token.type_name == "TOK_LT":
                _assign(ctx, child, open_site, sites)
            elif child.token.type_name == "TOK_GT":
                _assign(ctx, child, close_site, sites)
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

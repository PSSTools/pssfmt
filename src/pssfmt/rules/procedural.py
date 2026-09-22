"""Tier 2 -- procedural code: functions, their statements, and ``exec`` bodies.

``P3-11`` (the function body), ``P3-11a`` (its header), ``P3-11b`` (the
statements inside) and ``P3-8a`` (``exec`` bodies), in that order and each one
once the item before it made the next reachable. The last is the clearest
case: ``exec_stmt`` is ``procedural_stmt``, so an ``exec`` body is a function
body with a different header, and the largest construct left on the frontier
turned into a ``_block`` call the moment the statements had rules.

``procedural_function`` is the largest single construct the formatter did not
reach: **118 instances across 46 of the 92 corpus files**, half the corpus.
Everything inside one was reproduced verbatim, and -- this is the part that
matters -- so was everything the rule set would otherwise have formatted
inside it. An unwritten rule high in the tree hides every rule below it, which
is the lesson ``P3-6``'s ``extend`` taught at a cost of two releases.

Measuring the frontier before choosing
--------------------------------------
The constructs the formatter reaches and declines, counted through the real
dispatch rather than a walk of my own -- ``_member_body`` asks the registry
and reproduces on a miss, so a registry that records what it was asked
reports exactly the frontier and nothing behind it::

    procedural_function           118   (46 files)   <- this module
    function_decl                  29   ( 3 files)
    exec_block_stmt                24   (15 files)
    enum_declaration               15   (10 files)
    constraint_body_item           15   ( 1 file)
    component_pool_declaration     10   ( 5 files)
    ... 26 more, 271 declines total

What this module does, and what it leaves alone
-----------------------------------------------
A function is a **block**: a header, indented members, a closing brace. That
is :func:`~pssfmt.rules.decls._block`, unchanged, with the
``Construct.FUNCTION_BODY`` member ``P3-0`` provisioned for it -- so the whole
of this module's layout is one call, and its value is almost entirely in
deciding that a function *is* one of those.

The members are ``procedural_stmt`` nodes, and none of them has a rule yet, so
each is reproduced verbatim inside a correctly indented body. That split is
the point of the increment: brace placement, indentation, the blank-line
policy and comment attachment all come from the block, and statement *spacing*
is a separate vocabulary that is worth its own item.

The corpus barely notices, and that is expected
------------------------------------------------
Registering this changes **1 of 92 files** and declines none. The corpus is
hand-written in the house style, so its function bodies are already indented
the way this produces them -- which makes the corpus nearly useless as
evidence that the rule *does* anything, and is why the tests here work from
deliberately mis-indented input. On a file nobody has formatted:

.. code-block:: text

    component c {                    component c {
      function bit[32] f(int ch)         function bit[32] f(int ch) {
    {                                        int x = ch * 4;
       int x = ch * 4;         ->
                                             return x;
                                         }
           return x;                   }
      }
    }

The one corpus file that moves is a one-line body
--------------------------------------------------
``function bit[32] ch_addr(int ch) { return base_addr + ch * 0x20; }`` becomes
three lines. Written as a decision rather than fallen into: 117 of the 118
corpus functions are already written open, and ``P3-5`` made the identical
call for constraint blocks on the identical evidence -- 21 of 31 named
constraints have exactly one item and are still written open. A collapse rule
would be inventing a policy that one instance cannot support.

The header, one item later (``P3-11a``)
---------------------------------------
``function  bit[32]   f( int   ch )`` kept its gaps through ``P3-11``, because
:func:`~pssfmt.rules.decls._block` reproduces a header it has no vocabulary
for. It has one now, and the same vocabulary covers all three productions that
carry a prototype -- so this module registers three rules rather than one:

======================== ===== ===== ==========================================
rule                     count files shape
======================== ===== ===== ==========================================
``procedural_function``    118    46  a header and a body
``function_decl``           29     3  ``function void f(bit[8] x);``
``import_function``          7     3  ``import target C function void poke();``
======================== ===== ===== ==========================================

The last two are **header-only**, so they were unreachable through ``P3-11``
and needed their own registration: a function with no body is not a block, and
:func:`~pssfmt.rules.decls._block` would have reproduced it whole.

What the corpus says about a prototype
--------------------------------------
150 of them across 49 files, and they agree with the sites already measured
for a *call*, which is the finding that decided the shape of this:

* ``f(`` tight -- **147/150**. The three that are not are one file.
* ``(`` to the first parameter tight -- **137/137** on one line.
* the last parameter to ``)`` tight -- **138/138**.
* ``,`` then a parameter spaced -- **69/70** on one line.
* the return type to the name, one space -- **149/150**.

That last one is why this emits **no column stop**. The single padded instance
is one file, and one voice does not decide a site here any more than it did
for ``**`` in ``P3-4`` or a ``default`` constraint in ``P3-5``. A stop would
be cheap and would let ``infer`` keep::

    import target C function void poke(bit[32] addr, bit[32] data);
    import target C function int  sample_dut();

...which is the corpus's only padded name column. It collapses to one space,
which is what the other 149 write.

What is deliberately not here
-----------------------------
**A prototype the author wrapped.** :func:`~pssfmt.rules.tokens.emit_span`
discards newlines, so formatting one would join it onto a single line -- and
the corpus's five wrapped prototypes are wrapped *because* the joined form is
90 to 100 columns, past the width ``docs/style.rst`` calls a wall. Three of
the five are hand-aligned parameter tables besides::

    target function void check(
        addr_handle_t  base,
        bit[32]        nbytes,
        mem_pattern_e  pattern,
        bit[32]        seed) {

Laying that out properly means a break policy for a parameter list --
``Construct.PARAMETER_LIST`` exists and nothing sets it -- and a policy is not
something five instances can decide. So a wrapped prototype declines and is
reproduced, exactly as it was before this item, while its *body* is still laid
out. That split is what a header decline had to be worth: see
:func:`~pssfmt.rules.decls._header` on why ``sites=None`` stopped meaning the
same thing as ``sites={}``.

**Varargs** landed with ``S-14``, and the shape of the argument is the part
worth keeping. ``function void varargs(int... args)`` is one instance in one
file, and this module used to decline it on exactly that basis -- noting that
the spacing was expressible as ``Spacing(0, 1)``, *the comma's shape*, and
that borrowing a number from an unrelated site is how a site invented from a
single instance comes to look measured.

The decline was right and the reasoning about the number still is.
``Site.VARARGS`` is that value, and it is argued from **C's**
``printf(const char *fmt, ...)`` rather than from the comma: tight against
what precedes it, one space before the name. Same number, different claim,
and the comment in ``style.py`` says which.

**A one-line body.** Not collapsed; see above.

The statements, one item later (``P3-11b``)
--------------------------------------------
``PLAN.md`` called this "a vocabulary rather than a layout" and named four
alternatives as 85% of all procedural statements, ``procedural_return_stmt``
first at 201 instances. Building exactly that reaches **158 of 388 statements
and 9 of the 201 returns**, because **195 of them are inside a
``procedural_match_choice``** -- and ``match`` is a block::

    match (name) {
        ["ctrl"]:   return SPI_CTRL_OFF;
        ["status"]: return SPI_STATUS_OFF;
        default:    return -1;
    }

So ``match`` is here, in an item about spacing, and that is not scope creep:
six builders bound and almost never dispatched is ``P3-6``'s ``extend`` at a
third scale, and every test would have passed. What each construct unblocks:

===================================== ==========
blocked by                            statements
===================================== ==========
``procedural_match_choice``                  195
``+ procedural_sequence_block_stmt``          12
``procedural_repeat_stmt`` / ``foreach``      16
``procedural_if_else_stmt``                    7
===================================== ==========

With ``match``, its choices and the braced-arm block: **365 of 388**.

Two column stops, and one refusal one item ago
-----------------------------------------------
The only style decisions in the statement work are where a column may exist:
the ``=`` of a run of assignments (**22 padded of 93, across 8 files**) and
the statement column after an arm's ``:`` (**13 of 199, four complete tables
in four files**). Both marked, and ``infer`` decides what becomes of them.

Worth reading against ``P3-11a`` immediately above, which *declined* to mark a
prototype's name column -- one padded instance in one file. Same mechanism,
opposite evidence, opposite call. Either one alone reads as a preference; the
pair is the rule.

What the statements leave alone
--------------------------------
**``if``/``else``.** 5 instances in 3 files, and it needs the ``} else {``
decision ``docs/style.rst`` does not make -- the same reason ``P3-5`` declined
``if`` constraints on one instance. It hides 7 statements and the corpus's
only ``break`` and ``continue``, which is why those two are in ``T-30``'s
corpus-unreached set.

**Loops.** Two reasons, and only the first is stylistic. ``repeat (i : n)``
carries a colon that is a fifth reading of a character ``docs/style.rst``
already splits four ways -- ``activities.py`` declined the identical construct
for the identical reason. And ``repeat { … } while (e);`` puts its block in
the **middle** of the statement: :func:`~pssfmt.rules.decls._block` emits a
header, a body and a ``}``, so everything after the closing brace would be
dropped. That one is a shape the block layout cannot express at all, rather
than a decision nobody has made.

**A statement the author wrapped**, on ``P3-11a``'s rule and its evidence: six
of the corpus's seven wrapped calls join to between 86 and 108 columns.
"""

from __future__ import annotations

from typing import Any, Optional

from ..layout import ALIGN_MARK, concat, text
from ..layout.ir import Layout, Verbatim
from ..style import Construct, Site
from .decls import _block, _braces, _reproduce, sites_before
from .emit import code_span
from .exprs import (EXPRESSION_COLON, EXPRESSION_VOCABULARY, TREE_DECIDED,
                    sites_for, wrap_for)
from .stmts import after_a_width_bracket
from .tokens import WORD, emit_span, flat_width, floor_gap, original_gap

__all__ = ["register"]

#: What a prototype and its qualifiers may contain.
#:
#: Built from :data:`~pssfmt.rules.exprs.EXPRESSION_VOCABULARY` for the reason
#: :mod:`pssfmt.rules.stmts` gives: a parameter is a declaration, its type is a
#: ``data_type`` and its default is a ``constant_expression``, so everything an
#: expression may hold can appear here and every ambiguous one of those is in
#: :data:`~pssfmt.rules.exprs.TREE_DECIDED` and gets its site from the tree.
#: The corpus's whole prototype inventory is 18 token types and this covers all
#: but one of them.
#:
#: The keywords below are word-class: each needs separating from its
#: neighbours, which the lexical floor already does, and none has a second
#: reading in a span made of these. ``TOK_INPUT`` and ``TOK_OUTPUT`` are a
#: parameter *direction* here and a flow-object modifier in a field
#: declaration; that they are word-class in both is a coincidence of this
#: language rather than a shared decision, which is why the two vocabularies
#: are separate objects and not one shared set.
#:
#: ``TOK_TRIPLE_ELIPSIS`` is ``Site.VARARGS`` (``S-14``); it was deliberately
#: absent until then, and the module docstring records why.
_PROTOTYPE_VOCABULARY = dict(EXPRESSION_VOCABULARY)
_PROTOTYPE_VOCABULARY.update((name, WORD) for name in (
    "TOK_FUNCTION", "TOK_PURE", "TOK_STATIC", "TOK_IMPORT",
    # `target function`, `solve function`, `target solve function`.
    "TOK_TARGET", "TOK_SOLVE",
    "TOK_VOID",
    # A parameter's category and direction: `const`, `ref`, `type`,
    # `input`/`output`/`inout`.
    "TOK_CONST", "TOK_REF", "TOK_TYPE",
    "TOK_INPUT", "TOK_OUTPUT", "TOK_INOUT",
))
#: ``bit[64] offset = 0`` -- a parameter's default value.
_PROTOTYPE_VOCABULARY["TOK_SINGLE_EQ"] = Site.ASSIGN
#: ``int... args`` -- the varargs parameter (``S-14``).
_PROTOTYPE_VOCABULARY["TOK_TRIPLE_ELIPSIS"] = Site.VARARGS

#: ``function void f(...) {`` -- the header of a definition.
_FUNCTION_HEADER_VOCABULARY = dict(_PROTOTYPE_VOCABULARY)
_FUNCTION_HEADER_VOCABULARY["TOK_LCBRACE"] = Site.BRACE_OPEN

#: ``function void f(...);`` -- a declaration, which is the whole statement.
#:
#: Two vocabularies rather than one holding both terminators, because the sets
#: are what carry the argument that a token has one reading: a definition's
#: header cannot contain a ``;`` and a declaration cannot contain a ``{``, and
#: a set that admits a token no span can hold is a set nobody can check.
_FUNCTION_DECL_VOCABULARY = dict(_PROTOTYPE_VOCABULARY)
_FUNCTION_DECL_VOCABULARY["TOK_SEMICOLON"] = Site.SEMICOLON


def _prototype(node: Any) -> Optional[Any]:
    """The ``function_prototype`` child, where there is one.

    ``import_function`` has an alternative without one --
    ``import target function read;``, four instances in the corpus -- which is
    why this can answer ``None`` rather than being an accessor.
    """
    for child in node.children:
        if child.is_rule and child.rule_name == "function_prototype":
            return child
    return None


def _joins_usefully(ctx: Any, node: Any, span: Any, emitted: Any,
                    wrap: Any) -> bool:
    """Whether joining *node* produces something the engine can lay out.

    ``S-17``'s guard, and it is about **width** rather than about whether the
    author wrapped anything. Joining a wrapped construct is what
    :func:`~pssfmt.rules.tokens.emit_span` is for; what it could not do before
    ``S-16`` is break the result, so six of the corpus's seven wrapped calls
    joined to between 86 and 108 columns and the construct was reproduced.

    With a break policy the question narrows to exactly one case: a construct
    the author wrapped, that holds **no** list this can break, and whose
    joined form is past the width. There the author's line stands -- worse
    than a rule, and better than a line the tool has decided it cannot break
    and emitted anyway.

    Anything that fits is joined, wrapped or not, which is what ``S-16d``
    decided: width decides, not the author's wrap.
    """
    if wrap is not None or not _wrapped(ctx, node):
        return True
    origin = ctx.trivia.of(ctx.trivia.code_indices[span[0]]).token.col
    return origin + flat_width(emitted) <= ctx.style.print_width


def _wrapped(ctx: Any, node: Any) -> bool:
    """Whether the author broke *node* across lines.

    Asked of the **prototype** rather than of the header, so that the brace on
    its own line -- which ``P3-11`` exists to pull up -- is not read as a
    wrapped prototype. The two are the same character count apart and opposite
    decisions: a header the author split before ``{`` is a header this module
    joins, and a parameter list they split is one it must not touch.
    """
    span = code_span(ctx.trivia, node)
    if span is None:
        return False
    code = ctx.trivia.code_indices
    return (ctx.trivia.of(code[span[0]]).token.line
            != ctx.trivia.of(code[span[1]]).token.line)


def _header_sites(ctx: Any, node: Any, limit: int) -> Any:
    """Sites for the header's tree-decided tokens, or ``None`` to decline.

    One trigger now, and it used to be two. A construct
    :mod:`pssfmt.rules.exprs` declines -- a map literal in a default value --
    is a site nobody has measured, and that one remains.

    A **wrapped prototype** was the other, and it was a *policy* gap rather
    than a vocabulary one: every token was classifiable and joining them was
    the only thing this could do, which for the corpus's five instances means
    90 to 100 columns. ``S-16`` gave the parameter list a break policy and
    ``S-17`` removed the refusal, so a wrapped prototype is now joined and
    re-broken from its content.
    """
    return sites_before(ctx, node, limit)


def procedural_function(ctx: Any, node: Any) -> Layout:
    """``function <prototype> { <statements> }``.

    The header declining is not the construct declining: ``_block`` is called
    either way, so a prototype this module must not touch still gets its body
    laid out. That is what ``P3-11`` already did for *every* function, and
    keeping it true for the hard ones is the reason ``sites=None`` had to
    become distinguishable from ``sites={}``.

    :func:`~pssfmt.rules.decls._block` already falls back to reproducing the
    whole node when it finds no braces, which is what makes a prototype-only
    declaration reaching this by some future grammar change safe rather than
    wrong -- and is why the brace lookup below can hand back the same call.
    """
    braces = _braces(node)
    if braces is None:
        return _block(ctx, node, Construct.FUNCTION_BODY)
    # The brace's own position, which is exactly the bound ``_header`` passes
    # ``sites_before`` on its default path -- the sites must cover the span
    # ``_header`` is about to emit, ``first..brace_pos`` inclusive, and no
    # more. Adding one to it is a mutant nothing kills, and the reason is
    # narrower than it looks: ``sites_before`` skips a *rule child* starting
    # at or after the bound, and a ``procedural_function``'s ``{`` is its own
    # terminal, so no child begins there. The bound is ``>=`` rather than
    # ``>`` for constructs where that is false -- a ``constraint``, a
    # ``repeat`` -- and that is argued at ``sites_before`` itself.
    limit = ctx.trivia.code_indices.index(node.children[braces[0]].token_index)
    sites = _header_sites(ctx, node, limit)
    if sites is None:
        return _block(ctx, node, Construct.FUNCTION_BODY)
    # `S-16`/`S-17`: the parameter list may break. Asked of the *prototype*
    # rather than of the whole node, so a list inside the body -- a call in
    # the first statement -- is not offered as this header's wrap.
    prototype = _prototype(node)
    scope = prototype if prototype is not None else node
    wrap = wrap_for(ctx, scope)
    return _block(ctx, node, Construct.FUNCTION_BODY,
                  vocabulary=_FUNCTION_HEADER_VOCABULARY, sites=sites,
                  separate=after_a_width_bracket, wrap=wrap)


def _declaration(ctx: Any, node: Any) -> Layout:
    """``function void f(bit[8] x);`` and ``import target C function ...;``.

    A statement rather than a block, so it is emitted the way
    :mod:`pssfmt.rules.stmts` emits a field: the whole span, one vocabulary,
    sites from the tree over the whole node -- which is safe here and is not
    safe for a definition, because there is no body below to be refused by.
    """
    span = code_span(ctx.trivia, node)
    if span is None:
        return _reproduce(ctx, node)
    # No body, so the header is the whole node and the bound is one past its
    # last token. ``span[1]`` renders identically and is a mutant no test
    # kills: the last token of both these productions is the terminal ``;``,
    # and ``sites_before`` bounds *rule children*, none of which can begin
    # there. Written as the intent rather than as the coincidence.
    sites = _header_sites(ctx, node, span[1] + 1)
    if sites is None:
        return _reproduce(ctx, node)
    wrap = wrap_for(ctx, node)
    emitted = emit_span(ctx, span[0], span[1], _FUNCTION_DECL_VOCABULARY,
                        separate=after_a_width_bracket, sites_at=sites,
                        wrap=wrap)
    if emitted is None or not _joins_usefully(ctx, node, span, emitted, wrap):
        return _reproduce(ctx, node)
    return emitted


# ---------------------------------------------------------------------------
# Statements (``P3-11b``)
# ---------------------------------------------------------------------------

#: What a procedural statement may contain.
#:
#: Built from the expression vocabulary, like every statement vocabulary in
#: this rule set: a ``return``, an assignment and a void call are a keyword or
#: a path in front of an expression, and there is nothing else in them.
#:
#: The seven assignment operators share one site, and that is the *grammar's*
#: grouping rather than one invented here -- ``assign_op`` is a single
#: production with seven alternatives. It matters, because six of the seven
#: are a single instance in the corpus (``=`` 87, ``+=`` 7, ``-=`` 2, and one
#: each of ``<<=``, ``>>=``, ``|=``, ``&=``) and giving each its own site
#: would be seven defaults measured on one voice apiece. ``Site.ASSIGN`` is
#: measured at 271/319 over the construct they all belong to.
_STATEMENT_VOCABULARY = dict(EXPRESSION_VOCABULARY)
_STATEMENT_VOCABULARY.update((name, WORD) for name in (
    "TOK_RETURN", "TOK_BREAK", "TOK_CONTINUE", "TOK_YIELD",
))
#: ``assign_op``'s seven alternatives. Written once and used twice -- as the
#: vocabulary entries below and as the column stop's target -- because two
#: lists of the same seven token types is one list that eventually gains an
#: eighth and one that does not.
_ASSIGN_OPS = frozenset((
    "TOK_SINGLE_EQ", "TOK_PLUS_EQ", "TOK_MINUS_EQ",
    "TOK_SHL_EQ", "TOK_SHR_EQ", "TOK_OR_EQ", "TOK_AND_EQ",
))
_STATEMENT_VOCABULARY.update((name, Site.ASSIGN) for name in _ASSIGN_OPS)
_STATEMENT_VOCABULARY["TOK_SEMICOLON"] = Site.SEMICOLON
# `S-10`: a `:` in a procedural statement is a bit slice or a ternary. The
# match arm's colon is a different span with a different vocabulary --
# `_CHOICE_VOCABULARY` below, which sets its own and must keep doing so.
_STATEMENT_VOCABULARY.update(EXPRESSION_COLON)

#: ``match (name) {`` -- a keyword, a control paren and a brace.
_MATCH_HEADER_VOCABULARY = dict(EXPRESSION_VOCABULARY)
_MATCH_HEADER_VOCABULARY["TOK_MATCH"] = WORD
_MATCH_HEADER_VOCABULARY["TOK_LCBRACE"] = Site.BRACE_OPEN

#: ``["ctrl"]:`` and ``default:`` -- a choice's label, plus the ``{`` of the
#: four choices whose statement is a block.
_CHOICE_VOCABULARY = dict(EXPRESSION_VOCABULARY)
_CHOICE_VOCABULARY["TOK_DEFAULT"] = WORD
_CHOICE_VOCABULARY["TOK_COLON"] = Site.COLON_CASE_ITEM
_CHOICE_VOCABULARY["TOK_LCBRACE"] = Site.BRACE_OPEN

#: ``match``'s parens hang off ``procedural_match_stmt`` itself, so no rule in
#: :mod:`pssfmt.rules.exprs` claims them. Naming them costs no new decision:
#: ``Site.CONTROL_PAREN_*`` is 118/118 over ``if``/``repeat``/``foreach``, and
#: the corpus's 92 ``match`` headers all agree with it. Same mechanism, and
#: the same argument, as ``activities._REPEAT_SITES``.
_MATCH_SITES = {
    "TOK_LPAREN": Site.CONTROL_PAREN_OPEN,
    "TOK_RPAREN": Site.CONTROL_PAREN_CLOSE,
}

#: A choice's own punctuation, likewise unclaimed by any expression rule.
#:
#: The brackets are ``Site.SET_BRACKET_*`` rather than the index bracket they
#: look like, and the grammar is what settles it rather than a resemblance:
#: ``procedural_match_choice`` is ``'[' open_range_list ']' ':' stmt`` and
#: ``in_expression`` is ``'in' '[' open_range_list ']'``. Literally the same
#: production inside the brackets, so this is the site already measured for
#: it, not a new reading of ``[``. Tight inside, 107/107 here.
#:
#: Its ``before`` of 1 -- the thing that makes a set bracket a set bracket --
#: is never consulted, because a choice starts a line and nothing is composed
#: against its ``[``. So the *observable* answer would be the same under
#: ``INDEX_BRACKET`` too. Recorded because that makes the choice
#: unfalsifiable by test, which is exactly when the argument has to be
#: written down instead.
_CHOICE_SITES = {
    "TOK_LSBRACE": Site.SET_BRACKET_OPEN,
    "TOK_RSBRACE": Site.SET_BRACKET_CLOSE,
    "TOK_COLON": Site.COLON_CASE_ITEM,
}


def _sites_through(ctx: Any, node: Any, limit: int, own: Any) -> Any:
    """Sites for *node*'s first token through *limit*, or ``None`` to decline.

    Two sources, because a header holds two kinds of token and only one of
    them has an owner. The **child subtrees** are asked through
    :func:`~pssfmt.rules.decls.sites_before`, which is where every ambiguous
    expression token gets its answer. **A node's own terminals** -- ``match``'s
    parens, a choice's brackets and colon -- belong to no child rule at all,
    so ``sites_for`` never sees them; they are classified here by type, from a
    table the caller supplies, which is the ``P3-5`` *extra_rules* mechanism
    at the one place ``extra_rules`` cannot reach.

    ``setdefault`` and not assignment: a child's classification wins. An
    ``a[i]`` inside a range list has already been told it is an index bracket,
    and the table would otherwise overwrite it with the set bracket that
    belongs to the *choice's* brackets rather than to that one.

    The loop at the end is the completeness check, and it is the reason this
    is a function rather than two lines at each call site. ``sites_for`` makes
    the same check over a subtree; nothing was making it over the tokens
    *between* subtrees, so a tree-decided token the table forgot would have
    silently taken its vocabulary answer -- which for an ambiguous type is
    wrong rather than missing.
    """
    sites = sites_before(ctx, node, limit)
    if sites is None:
        return None
    span = code_span(ctx.trivia, node)
    if span is None:
        return None
    code = ctx.trivia.code_indices
    for pos in range(span[0], limit + 1):
        type_name = ctx.trivia.of(code[pos]).token.type_name
        if type_name in own:
            sites.setdefault(pos, own[type_name])
        elif pos not in sites and type_name in TREE_DECIDED:
            return None
    return sites


def _after_return(left: Any, right: Any,
                  left_site: Any = None, right_site: Any = None) -> bool:
    """``return -1`` -- a keyword meeting the expression it returns.

    The third of the two-token facts ``max(left.after, right.before)`` cannot
    express, after :mod:`pssfmt.rules.stmts`'s two, and the one this item
    would have shipped without. ``return`` is word-class and contributes no
    gap; ``-`` is ``Site.UNARY``, measured tight on both sides at 92/92. So
    the computed gap is **zero** and the output is ``return-1;``.

    Which still lexes as three tokens. Token equivalence passes, the verifier
    is silent, and every test written against ``return x;`` passes too --
    because there both sides are word characters and the lexical floor fires.
    Exactly the shape that shipped ``bit[3]in [2..4]`` once, and 90 of the
    corpus's 201 returns are ``return -1;``.

    The ``;`` is excluded, and that exclusion is the whole reason this is a
    two-sided test rather than "is the left token ``return``". ``return;`` is
    a return with **no** expression -- 201 of 201 corpus returns write it
    tight, ``Site.SEMICOLON`` says tight, and a one-sided floor emits
    ``return ;``. The floor is about an operand, so it has to ask whether
    there is one.

    Asked by token type, which is sound for the reason the other two are: the
    vocabularies are closed, and no span of these tokens can put ``return``
    anywhere but in front of its operand or its terminator.
    """
    return (left.type_name == "TOK_RETURN"
            and right.type_name != "TOK_SEMICOLON")


def _statement(ctx: Any, node: Any) -> Layout:
    """``return x;``, ``a.b = c;``, ``f(x);``, ``break;``.

    The four alternatives the plan measured at 85% of all procedural
    statements, plus the three one-word ones that come free with them. A
    vocabulary and a floor: none of these breaks, none has a body, and every
    gap in them is a site already measured somewhere else.

    Not :func:`~pssfmt.rules.stmts.after_a_width_bracket`, and it is worth
    saying which floor is *not* here: a statement has no declarator, so the
    type-meets-name seam cannot arise -- ``bit[32]`` reaches a statement only
    through a cast, where the ``]`` is followed by ``)``.
    """
    span = code_span(ctx.trivia, node)
    if span is None:
        return _reproduce(ctx, node)
    # `S-17`. A statement the author wrapped used to be reproduced, and the
    # reason was never that joining it was wrong -- it was that `emit_span`
    # discards newlines, so joining was all this could do, and six of the
    # corpus's seven wrapped calls join to between 86 and 108 columns.
    #
    # `S-16` supplied the missing half, and the guard below is where the two
    # meet: **join only where there is somewhere to break.** A statement the
    # author wrapped that holds a list is joined and re-broken from its
    # *content*, which is the property that makes this correct rather than
    # merely possible -- the same call written on one line and across four
    # now produce the same output. One that holds no list, or two of them,
    # has nowhere to break, and joining it would produce exactly the 86-to-108
    # column line the old decline existed to avoid. So the author's wrap
    # stands there, as it always did.
    #
    # Worth being plain that this is narrower than `S-16d`, which says width
    # decides rather than the author's wrap. It does -- wherever the tool can
    # decide. Where it cannot break the line at all, "width decides" would
    # mean emitting a line that violates the width, which decides nothing.
    wrap = wrap_for(ctx, node)
    sites = sites_for(ctx, node)
    if sites is None:
        return _reproduce(ctx, node)
    emitted = emit_span(ctx, span[0], span[1], _STATEMENT_VOCABULARY,
                        separate=_after_return, sites_at=sites,
                        mark_at=_assign_stop(ctx, span),
                        wrap=wrap)
    if emitted is None or not _joins_usefully(ctx, node, span, emitted, wrap):
        return _reproduce(ctx, node)
    return emitted


def _assign_stop(ctx: Any, span: tuple) -> tuple:
    """Where a hand-aligned run of assignments puts its column::

        ctrl.en        = 1;
        ctrl.start     = 0;
        ctrl.lsb_first = cfg.lsb_first;

    The same seam ``stmts._column_stops`` marks for a field with an
    initialiser, in the construct that is a field's initialiser without the
    field. The evidence is stronger here than there: **22 of the corpus's 93
    assignments are padded, across 8 files**, and they are not scattered --
    they are five complete tables.

    One stop and not two, because an assignment has no declarator to be the
    other one. That is also why this is a small function rather than a call
    into ``_column_stops``: that one works from ``_SEAM_RULES``, which are
    *declaration* productions, and an assignment contains none of them.

    Located by token type, like ``stmts._break_after_assign`` and for the
    same reason: an assignment operator cannot occur anywhere else in a span
    of :data:`_STATEMENT_VOCABULARY`, because no expression contains one.
    """
    code = ctx.trivia.code_indices
    for pos in range(span[0], span[1] + 1):
        if ctx.trivia.of(code[pos]).token.type_name in _ASSIGN_OPS:
            return (pos,)
    return ()


def _match(ctx: Any, node: Any) -> Layout:
    """``match (name) { ["a"]: …; default: …; }``.

    A block, and the item's real work: 92 of them across 30 files, and by
    ``P3-6``'s rule they were hiding **195 of the corpus's 201 return
    statements**. Registering the leaf statements without this one would have
    left the largest alternative 96% inert while every test passed.
    """
    braces = _braces(node)
    if braces is None:
        return _reproduce(ctx, node)
    limit = ctx.trivia.code_indices.index(node.children[braces[0]].token_index)
    sites = _sites_through(ctx, node, limit, _MATCH_SITES)
    if sites is None:
        return _block(ctx, node, Construct.MATCH_BODY)
    return _block(ctx, node, Construct.MATCH_BODY,
                  vocabulary=_MATCH_HEADER_VOCABULARY, sites=sites)


def _colon(node: Any) -> Optional[Any]:
    """A choice's own ``:``, found among the direct terminals.

    By child rather than by scanning the span, because a colon deeper in is a
    different construct entirely -- ``a[3:0]`` is a bit slice -- and a
    position scan would classify the first one it met.
    """
    for child in node.children:
        if not child.is_rule and child.token is not None \
                and child.token.type_name == "TOK_COLON":
            return child
    return None


def _labelled(ctx: Any, node: Any) -> Optional[Any]:
    """The statement a choice labels, looked through its wrapper.

    ``ctx.build`` dispatches on the node it is handed, and ``procedural_stmt``
    is in ``decls._PASSTHROUGH`` rather than in the registry -- so handing it
    the wrapper would reproduce the statement together with the leading trivia
    this rule has already emitted as a gap.
    """
    from .decls import _effective

    for child in node.children:
        if child.is_rule and child.rule_name == "procedural_stmt":
            return _effective(child)
    return None


def _match_choice(ctx: Any, node: Any) -> Layout:
    """``["ctrl"]: return SPI_CTRL_OFF;`` and ``[A]: { … }``.

    Two shapes and two mechanisms. The braced one is a block whose braces
    belong to a child, which is exactly what ``_block``'s *body* parameter is
    for -- the same shape as a ``constraint`` and an activity ``repeat``.

    The inline one is the interesting half, because the statement after the
    colon is built by **its own rule** rather than emitted as part of this
    span. That is deliberate: emitting the whole choice as one run of tokens
    would work, and would mean ``procedural_return_stmt``'s builder never ran
    for 195 of its 201 instances, so ``T-30`` would report a rule nothing
    reaches while the output looked right.

    Composing two layouts instead means this is a **token composition site**,
    with everything ``P3-10`` says that entails: the gap between the ``:``
    and the statement is computed from the style, floored by the lexer, and
    carries a column stop.
    """
    colon = _colon(node)
    statement = _labelled(ctx, node)
    if colon is None or statement is None:
        return _reproduce(ctx, node)
    trivia = ctx.trivia
    code = trivia.code_indices
    colon_pos = code.index(colon.token_index)

    if getattr(statement, "rule_name", None) == "procedural_sequence_block_stmt":
        braces = _braces(statement)
        if braces is None:
            return _reproduce(ctx, node)
        limit = code.index(statement.children[braces[0]].token_index)
        sites = _sites_through(ctx, node, limit, _CHOICE_SITES)
        if sites is None:
            return _reproduce(ctx, node)
        return _block(ctx, node, Construct.COMPOUND_STATEMENT, body=statement,
                      vocabulary=_CHOICE_VOCABULARY, sites=sites)

    span = code_span(trivia, node)
    if span is None or colon_pos >= span[1] or _wrapped(ctx, node):
        # A choice the author spread over lines is not this shape, and the
        # check is load-bearing rather than tidy: the inline form writes a
        # **column stop** before the statement, and a column is a fact about
        # one line. Put a stop in front of a layout that turns out to be three
        # lines and :mod:`pssfmt.layout.align` measures a cell containing a
        # newline -- which is not merely wrong, it is *not idempotent*, and
        # the gap grows by two columns on every pass. Found exactly that way,
        # by the corpus fail-safe, on a file with four braced choices.
        return _reproduce(ctx, node)
    sites = _sites_through(ctx, node, colon_pos, _CHOICE_SITES)
    if sites is None:
        return _reproduce(ctx, node)
    label = emit_span(ctx, span[0], colon_pos, _CHOICE_VOCABULARY,
                      sites_at=sites)
    if label is None:
        return _reproduce(ctx, node)
    return concat([label, _after_the_colon(ctx, colon_pos),
                   ctx.build(statement)])


def _after_the_colon(ctx: Any, colon_pos: int) -> Layout:
    """The gap between a choice's ``:`` and its statement, with a column stop.

    Three things, and the third is why this is not ``text(" ")``:

    * the **computed** gap -- ``Site.COLON_CASE_ITEM``, measured at 214/224
      spaced in ``docs/style.rst`` and 186/199 here;
    * the **lexical floor**, because this is a place two tokens are written
      against each other outside :func:`~pssfmt.rules.tokens.emit_span`, and
      ``P3-10`` found two of the three such places had forgotten it;
    * a **column stop**, carrying the author's own spacing rather than the
      computed one, because 13 of the corpus's 199 choices are padded and
      they are not scattered -- they are four complete hand-built tables in
      four files::

          ["ctrl"]:   return SPI_CTRL_OFF;
          ["div"]:    return SPI_DIV_OFF;
          ["status"]: return SPI_STATUS_OFF;

      Stronger evidence than ``P3-11a`` declined a stop on, and the
      difference is the whole reason that one was declined and this one is
      not: there, one padded gap in one file; here, four independent voices
      each building the same column. Marking a seam is not a decision to pad
      -- :mod:`pssfmt.layout.align` reads each block's own columns and
      reproduces or flushes accordingly -- but declining to mark one makes
      the author's table impossible to keep.
    """
    trivia = ctx.trivia
    code = trivia.code_indices
    left = trivia.of(code[colon_pos]).token
    right = trivia.of(code[colon_pos + 1]).token
    gap = floor_gap(ctx.style.gap(Site.COLON_CASE_ITEM, None), left, right)
    original = original_gap(trivia, code, colon_pos + 1)
    if gap and original is not None:
        return text(ALIGN_MARK + " " * max(gap, original))
    return text(" " * gap)


#: The leaf statements, all of them one vocabulary and no layout.
#:
#: ``procedural_data_declaration`` is deliberately absent: it is registered in
#: :mod:`pssfmt.rules.stmts` instead, because it *is* a field declaration in
#: everything but name. See ``_FIELD_RULES`` there.
#: ``exec body {`` -- a keyword, a kind and a brace (``P3-8a``).
#:
#: ``exec_kind`` is an ``identifier`` rather than a keyword: the grammar has a
#: commented-out list of ``pre_solve``/``body``/``init_up`` and so on, and the
#: note above it says the kinds were made local instead of global keywords. So
#: the whole vocabulary is three entries, and the corpus is unanimous on both
#: gaps -- 28/28 one space after ``exec``, 28/28 one space before ``{``.
#:
#: ``TOK_FILE`` is deliberately absent. It is not a native exec kind:
#: ``exec file "out/x.txt" = """…"""`` is a ``target_file_exec_block``, which
#: this rule never sees, and the only reason a ``file`` kind reaches here at
#: all is that the corpus's one instance sits in a file with a syntax error,
#: where recovery matched it as an ``exec_block``.
#:
#: Adding it back is a mutant no test kills, and the proof is worth writing
#: down rather than testing around. That recovered node's children are
#: ``exec``, ``exec_kind``, *a brace token with no text*, ``exec_stmt``,
#: ``}`` -- so ``_braces`` finds no pair and :func:`~pssfmt.rules.decls._block`
#: reproduces the whole node before a vocabulary is consulted at all. On any
#: input that *parses*, the construct is a different grammar rule. So the
#: entry is unreachable in both directions, and it stays out because the set
#: is the argument for what a native exec kind is.
_EXEC_HEADER_VOCABULARY = {
    "TOK_EXEC": WORD,
    "ID": WORD,
    "ESCAPED_ID": WORD,
    "TOK_LCBRACE": Site.BRACE_OPEN,
}


def _exec_block(ctx: Any, node: Any) -> Layout:
    """``exec body { … }`` -- **28 of them across 18 files** (``P3-8a``).

    One ``_block`` call, and the item is one line of layout because
    ``P3-11b`` landed first. ``exec_stmt`` is ``procedural_stmt`` (109 of them
    in these bodies) plus ``exec_super_stmt``, which the corpus does not
    contain -- so an exec body is a function body with a different header, and
    every rule written for the inside of one already applies.

    ``PLAN.md`` scoped this as the largest remaining item and said it "needs
    ``procedural_stmt`` first, which is bigger than ``P3-7`` and ``P3-8``
    together". That was true when it was written. What it makes clear in
    hindsight is that the cost of an item is a fact about the *frontier at the
    time*, not about the construct -- this one went from the biggest thing
    left to a twenty-line change without anybody touching ``exec``.

    Not to be confused with ``P3-8``'s ``target_code_exec_block``, which is
    the same keyword in front of a foreign-language payload and must never be
    re-anchored. That one has no builder, on purpose, and reaching this
    wrapper does not change it.
    """
    return _block(ctx, node, Construct.EXEC_BODY,
                  vocabulary=_EXEC_HEADER_VOCABULARY, sites={})


#: ``if (x) {``, ``foreach (i : list) {``, ``repeat (i : 4) {``,
#: ``while (x) {`` -- and ``repeat {``, which is a keyword and a brace.
#:
#: The ``:`` here is :data:`~pssfmt.rules.exprs.EXPRESSION_COLON`'s bit-slice
#: fallback, **not** the iterator (``S-5``). An iterator colon is a *direct*
#: terminal of the loop rule and is assigned from the tree in
#: :func:`_control_block`; a colon anywhere else in a control header is inside
#: the condition, where it is a bit slice -- ``if (a[3:0] == 0) {``.
#:
#: Which is a distinction the vocabulary cannot draw, and getting it the other
#: way round is invisible until somebody writes such a condition. The case
#: that reaches this code is a cast -- ``if ((bit[3:0])x == 0) {`` -- because
#: an expression's own ``bit_slice`` (``a[3:0]``) declines a step earlier on
#: its unclassified brackets, while ``integer_type``'s width slice does not.
#: Naming ``TOK_COLON`` as the iterator here emits ``(bit[3 : 0])x``.
_CONTROL_HEADER_VOCABULARY = dict(EXPRESSION_VOCABULARY)
_CONTROL_HEADER_VOCABULARY.update((name, WORD) for name in (
    "TOK_IF", "TOK_FOREACH", "TOK_REPEAT", "TOK_WHILE",
))
_CONTROL_HEADER_VOCABULARY.update(EXPRESSION_COLON)
_CONTROL_HEADER_VOCABULARY["TOK_LCBRACE"] = Site.BRACE_OPEN

#: A control statement's own parens, unclaimed by any expression rule --
#: the same mechanism and the same argument as :data:`_MATCH_SITES`, and the
#: constructs ``Site.CONTROL_PAREN_*``'s 118/118 was actually measured on.
_CONTROL_SITES = {
    "TOK_LPAREN": Site.CONTROL_PAREN_OPEN,
    "TOK_RPAREN": Site.CONTROL_PAREN_CLOSE,
}


def _direct_terminal(node: Any, type_name: str) -> Optional[Any]:
    """*node*'s own terminal of *type_name*, or ``None``.

    Direct children only, which is the whole of the iterator colon's
    classification: ``foreach (i : a[3:0])`` holds two colons and exactly one
    of them is this node's.
    """
    for child in node.children:
        if not child.is_rule and child.token is not None \
                and child.token.type_name == type_name:
            return child
    return None

#: Loop rules, and the body construct each is laid out under.
_LOOP_RULES = {
    "procedural_foreach_stmt": Construct.LOOP_BODY,
    "procedural_repeat_stmt": Construct.LOOP_BODY,
}


def _braced_body(node: Any) -> Optional[Any]:
    """The ``{ … }`` a control statement wraps, or ``None``.

    ``procedural_stmt`` is a passthrough wrapper, so the block is one level
    down; :func:`~pssfmt.rules.decls._effective` is what looks through it.

    ``None`` means the branch is a bare statement -- ``if (x) y;`` is legal
    PSS -- and every caller here treats that as a decline. **Inserting braces
    is not an option**: it changes the token stream, which is the one thing
    this formatter does not do, and laying the statement out without them
    needs a second decision (on the same line, or broken and indented?) that
    ``docs/style.rst`` has not made and five instances cannot.
    """
    from .decls import _effective

    for child in node.children:
        if child.is_rule and child.rule_name == "procedural_stmt":
            inner = _effective(child)
            if getattr(inner, "rule_name", None) \
                    == "procedural_sequence_block_stmt":
                return inner
            return None
    return None


def _branches(node: Any):
    """``(then_block, else_stmt)`` for an ``if``, or ``(None, None)``.

    Both halves come from the *direct* children, and the ``else`` half is
    found by position relative to ``TOK_ELSE`` rather than by taking the
    second ``procedural_stmt``. Same answer today; the positional version
    stops being right the moment the grammar grows an alternative, and it
    reads as though it were checking something it is not.
    """
    from .decls import _effective

    seen_else = False
    then_block = else_stmt = None
    for child in node.children:
        if not child.is_rule:
            if getattr(child.token, "type_name", None) == "TOK_ELSE":
                seen_else = True
            continue
        if child.rule_name != "procedural_stmt":
            continue
        if seen_else:
            else_stmt = _effective(child)
        else:
            inner = _effective(child)
            if getattr(inner, "rule_name", None) \
                    == "procedural_sequence_block_stmt":
                then_block = inner
    return then_block, else_stmt


def _control_block(ctx: Any, node: Any, body: Any, construct: Construct,
                   tail: Optional[Layout] = None) -> Optional[Layout]:
    """``<header> { … }`` with *tail* after the brace, or ``None`` to decline.

    The header runs from *node*'s first token to *body*'s ``{``, across two
    nodes, which is what ``_block``'s *body* parameter is for.
    """
    braces = _braces(body)
    if braces is None:
        return None
    limit = ctx.trivia.code_indices.index(
        body.children[braces[0]].token_index)
    sites = _sites_through(ctx, node, limit, _CONTROL_SITES)
    if sites is None:
        return None
    iterator = _direct_terminal(node, "TOK_COLON")
    if iterator is not None:
        code = ctx.trivia.code_indices
        sites[code.index(iterator.token_index)] = Site.COLON_ITERATOR
    return _block(ctx, node, construct, body=body,
                  vocabulary=_CONTROL_HEADER_VOCABULARY, sites=sites,
                  tail=tail)


def _nothing_but_whitespace_before(ctx: Any, pos: int) -> bool:
    """Whether the gap before code position *pos* holds only whitespace.

    The check :func:`~pssfmt.rules.tokens.emit_span` makes for every seam
    inside a span, applied at the two seams a *tail* creates -- which are
    outside every span, because the whole point of a tail is that it joins
    two layouts across the ``}`` between them.

    ``} /* why */ else {`` is the case, and it was a real defect rather than
    a hypothetical: the comment sits in trivia that neither the block's last
    token nor the tail's first one owns, so it was **dropped**. The verifier
    caught it -- a lost comment is a token-equivalence failure and the file
    came back unchanged with a diagnostic -- which is the fail-safe working
    and is not the same as the rule being right. Where a comment goes
    relative to an ``else`` is a question about comments, and this module has
    no opinion worth acting on; it declines.
    """
    code = ctx.trivia.code_indices
    if pos <= 0 or pos >= len(code):
        return False
    run = list(ctx.trivia.of(code[pos - 1]).raw_trailing) \
        + list(ctx.trivia.of(code[pos]).raw_leading)
    return all(not tok.text.strip() for tok in run)


def _after_the_brace(ctx: Any, keyword: str) -> Layout:
    """The gap between a ``}`` and the keyword cuddled against it.

    ``Site.BLOCK_TAIL``, and a literal would be a ``T-13`` failure. There is
    no lexical floor to apply: ``}`` is neither a word character nor half of
    a longer lexeme, so nothing here can merge however the site is configured.
    """
    return text(" " * ctx.style.gap(Site.BLOCK_TAIL, None)
                + keyword
                + " " * ctx.style.gap(None, Site.BLOCK_TAIL))


def _if_else(ctx: Any, node: Any) -> Layout:
    """``if (x) { … }``, ``} else { … }``, ``} else if (y) { … }`` (``S-1``).

    Cuddled, and that is argued rather than measured: 5 instances in 3 files
    is not a measurement and they do not agree. Every comparable guide does --
    K&R, the Linux kernel, Google C++, lowRISC -- and Allman appears nowhere
    in this corpus, so the alternative is a shape no voice here is asking for.

    **The chain is the part that is wrong by default.** ``else if`` is not a
    construct in PSS: it is an ``else`` whose statement is another
    ``procedural_if_else_stmt``, so the obvious recursion -- build the else
    branch and indent it like a body -- produces a staircase::

        } else {
            if (b) {

    The nested ``if`` is therefore composed *flat*, with no indent and no
    line break, which is the whole of what makes ``} else if (b) {`` come out
    on one line. Pinned by a three-branch chain in ``T-44``, because a green
    suite will not otherwise notice.

    A branch that is not braced declines the whole statement. See
    :func:`_braced_body`.
    """
    then_block, else_stmt = _branches(node)
    if then_block is None:
        return _reproduce(ctx, node)
    if else_stmt is None:
        laid = _control_block(ctx, node, then_block, Construct.IF_BODY)
        return laid if laid is not None else _reproduce(ctx, node)

    name = getattr(else_stmt, "rule_name", None)
    if name == "procedural_if_else_stmt":
        # The chain. Flat, deliberately: see the docstring.
        otherwise = _if_else(ctx, else_stmt)
    elif name == "procedural_sequence_block_stmt":
        otherwise = _block(ctx, else_stmt, Construct.ELSE_BODY)
    else:
        return _reproduce(ctx, node)
    # The two seams a tail creates: `}` to `else`, and `else` to whatever
    # follows it. Both are outside any span, so nothing else checks them.
    then_span = code_span(ctx.trivia, then_block)
    if then_span is None \
            or not _nothing_but_whitespace_before(ctx, then_span[1] + 1) \
            or not _nothing_but_whitespace_before(ctx, then_span[1] + 2):
        return _reproduce(ctx, node)
    if isinstance(otherwise, Verbatim):
        # The else half declined. Reproducing *it* inside a formatted `if`
        # would put reproduced text after a composed gap, which is the one
        # thing `_reproduce` exists to keep from happening mid-construct.
        return _reproduce(ctx, node)
    laid = _control_block(ctx, node, then_block, Construct.IF_BODY,
                          tail=concat([_after_the_brace(ctx, "else"),
                                       otherwise]))
    return laid if laid is not None else _reproduce(ctx, node)


def _loop(ctx: Any, node: Any) -> Layout:
    """``foreach (i : list) { … }``, ``repeat (i : 4) { … }``, ``while (x) {``.

    One builder for three keywords, because the grammar gives all three the
    same shape: header tokens, then a ``procedural_stmt`` wrapping the block.

    ``repeat { … } while (e);`` is the fourth alternative of
    ``procedural_repeat_stmt`` and is **not** handled here. It puts its block
    in the middle of the statement, which ``_block``'s *tail* can now express
    -- but the tail would be a whole statement rather than a keyword and a
    layout, and the corpus contains none of them. Declined, and named so that
    it reads as a decision rather than an omission.
    """
    body = _braced_body(node)
    if body is None or _has_a_tail(ctx, node, body):
        return _reproduce(ctx, node)
    laid = _control_block(ctx, node, body, _LOOP_RULES[node.rule_name])
    return laid if laid is not None else _reproduce(ctx, node)


def _has_a_tail(ctx: Any, node: Any, body: Any) -> bool:
    """Whether anything of *node*'s follows *body*'s closing brace.

    Which is the repeat-while form and nothing else. Asked as a question
    about **shape** rather than by looking for ``TOK_WHILE``, and the first
    version did look for the token: it also fired on ``while (x) { … }``,
    whose ``while`` is its *first* token, and declined a loop that has no
    tail at all. The two spellings share a keyword and differ in where the
    block sits, so where the block sits is what to ask about.
    """
    span = code_span(ctx.trivia, node)
    body_span = code_span(ctx.trivia, body)
    return span is None or body_span is None or body_span[1] < span[1]


_STATEMENT_RULES = (
    "procedural_return_stmt",
    "procedural_assignment_stmt",
    "procedural_void_function_call_stmt",
    "procedural_break_stmt",
    "procedural_continue_stmt",
    "procedural_yield_stmt",
)


def _function_decl(ctx: Any, node: Any) -> Layout:
    """``function_decl`` -- a prototype-only declaration *or* a definition.

    The grammar used to offer these as two productions, ``function_decl`` for
    ``... ;`` and ``procedural_function`` for ``... { ... }``, and this module
    bound a builder to each. pssparser factored them into one rule with a
    trailing ``(';' | '{' procedural_stmt* '}')`` choice, because as separate
    alternatives the parser had to predict past the whole signature -- up to
    36 tokens -- before it could tell them apart.

    So the choice the parser no longer makes is made here instead, on the one
    token it turns on: a body means the block builder, no body means the
    statement builder. :func:`procedural_function` is no longer *registered* --
    there is no such rule left to dispatch on, and a builder bound to a name
    the grammar cannot produce is a builder no test can reach -- but it is
    still the block half of this construct and is called from here.
    """
    return (procedural_function(ctx, node) if _braces(node) is not None
            else _declaration(ctx, node))


def register(registry: Any) -> None:
    registry.register("function_decl", _function_decl)
    registry.register("import_function", _declaration)
    for rule_name in _STATEMENT_RULES:
        registry.register(rule_name, _statement)
    registry.register("procedural_match_stmt", _match)
    registry.register("procedural_match_choice", _match_choice)
    registry.register("exec_block", _exec_block)
    registry.register("procedural_if_else_stmt", _if_else)
    for rule_name in _LOOP_RULES:
        registry.register(rule_name, _loop)

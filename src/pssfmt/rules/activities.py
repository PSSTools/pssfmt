"""Tier 2 -- activities (``P3-6``).

``PLAN.md`` §4.1 calls activities "the visual centerpiece of a PSS file" and
budgets this as the single largest rule module. The survey disagrees with the
budget, and in a specific way worth recording, because it is the second time
in two items that a plan written from the *grammar* has mispredicted the
corpus.

What the corpus actually contains, over 92 files::

    activity_action_traversal_stmt   83   (13 files)   0 multi-line
    activity_bind_stmt               10   ( 5 files)   0 multi-line
    activity_declaration             15   (12 files)  15 multi-line
    activity_sequence_block_stmt      9   ( 3 files)   8 multi-line
    activity_parallel_stmt            5   ( 5 files)   5 multi-line
    activity_schedule_stmt            3   ( 3 files)   3 multi-line
    activity_repeat_stmt              3   ( 2 files)   3 multi-line
    activity_select_stmt              2   ( 2 files)   2 multi-line
    activity_if_else_stmt             1
    activity_foreach_stmt             1
    activity_match_stmt               1
    activity_replicate_stmt           1
    activity_atomic_block_stmt        1
    activity_scheduling_constraint    1
    monitor_activity_*               34   ( 1 file )

The plan's shopping list was "``sequence``, ``parallel``, ``schedule``,
``select``, ``repeat``, ``do``". Five of those six are the *rarest* things
here, 22 instances between them; the sixth, mentioned last, is 83 instances
and more than half of everything in the table. The centerpiece of an activity
is the list of actions it traverses, and the control-flow keywords are the
frame around it.

So this module is two shapes and nothing else
---------------------------------------------
**A statement**, written on one line: a traversal (``fill;``, ``do
mem_copy_a;``) or a bind. 93 of the corpus's instances, none of them written
across more than one line, so there is nothing here to break and no fit
decision to make.

**A block**: a header, members one per line, a closing brace. That is
:func:`~pssfmt.rules.decls._block`, unchanged -- 29 of 29 activity blocks in
the corpus write exactly one space before the ``{``, which is
``Site.BRACE_OPEN`` measured on 725 declaration bodies. An activity block is
a declaration body with a different keyword in front of it.

Not one new spacing site
------------------------
Every gap this module emits was measured on some *other* construct, and the
survey re-confirms three of them independently:

============================  =======================  ==================
Gap                           Site                     This corpus says
============================  =======================  ==================
``parallel␣{``                ``BRACE_OPEN``           29 / 29, 6 rules
``repeat␣(4)``                ``CONTROL_PAREN_OPEN``   3 / 3  (was 118/118)
``fill;``                     ``SEMICOLON``            82 / 82, 13 files
``do␣step``                   word-class               34 / 34,  6 files
``pkg::a``                    ``SCOPE_RESOLUTION``     6 / 6,   3 files
``x.b``                       ``MEMBER_ACCESS``        2 / 2
============================  =======================  ==================

``Site.CONTROL_PAREN_OPEN`` had been carried since ``P3-2`` with a measured
default and no user. ``repeat (4)`` is its first, and agrees with the number
already there -- which is the outcome that makes a measured default worth
having, as opposed to one invented when the first caller arrived.

Binds are a table, so the column survives
-----------------------------------------
Six of the ten binds are padded to a column::

    bind fill_copy.blk  copy.src;
    bind copy.dst       chk.blk;
    bind fill_spi.blk   dma_half.src;

Two files do this and three do not, and a rule that collapsed the gap to one
space would flatten a hand-built table -- the exact failure ``P3-3`` built the
alignment pass to prevent. The seam is the start of
``activity_bind_item_or_list``, which is a *node* boundary, so it is taken
from the tree for the same reason ``_column_stops`` takes the type/declarator
seam from the tree rather than guessing it from tokens.

What declines, and how
----------------------
Almost all of it declines through a token the vocabulary does not contain,
rather than through code that knows what the construct is. This is the same
property ``P3-5`` got from omitting ``TOK_LCBRACE``, and it is why the module
is short:

``do step with { id == ri; }``
    ``TOK_WITH`` and ``TOK_LCBRACE`` are absent from
    :data:`_TRAVERSAL_VOCABULARY`, so an inline constraint declines. Four
    instances in two files, all written on one line -- but the only comparable
    measured construct is the named constraint block, which 31 of 32 corpus
    instances write *opened out*. Formatting these would mean either
    contradicting that measurement or inventing an exception for inline
    constraints on four instances. Neither is a decision four instances can
    make.
``a: do step;``
    Labels. Eight instances, all in **one** file -- one voice, the same
    argument that declined ``**`` in ``P3-4``. Handled entirely by
    ``decls._effective``: see the ``P3-6`` note in ``_PASSTHROUGH``.
``repeat (ri : 4)``
    A fifth colon construct, one instance. ``docs/style.rst`` names four
    because four is what was measured. ``TOK_COLON`` is absent from
    :data:`_BLOCK_HEADER_VOCABULARY`, so the *header* is reproduced as
    written while the body still opens out -- the fallback ``_header`` has
    had since ``P3-2b`` for templated headers, doing useful work here.
``select { (mode == FAST) [3]: do fast_step; }``
    Guarded and weighted branches: a label colon, a weight bracket that is
    not any of the four measured brackets, and hand-aligned colons. One
    instance. The ``select`` *block* still opens out; its branches decline
    individually and are reproduced.
``if``/``else``, ``foreach``, ``match``, ``replicate``, ``atomic``,
``activity_scheduling_constraint``
    One instance each. Not registered, so reproduced whole.
``monitor_activity_*``
    34 instances and a genuinely rich set of operators -- ``concat``,
    ``eventually``, ``overlap`` -- but **all 34 are in one file**. Volume is
    not independence; this is one author's dialect until a second file
    agrees.

The cost of a decline is stated exactly in ``docs/status.rst``: a rule cannot
lay out a node whose parent has none, so a declined ``repeat`` would take its
body's traversals with it. That is why ``repeat`` is registered on three
instances -- not because three is good evidence for a ``repeat``, but because
the block shape needs no new decision and declining it would silently cost
six ``do`` statements inside it.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from ..layout import Layout
from ..style import Construct, Site
from .decls import _block, _reproduce
from .emit import code_span
from .exprs import EXPRESSION_VOCABULARY, sites_for
from .tokens import WORD, emit_span

#: ``activity {``, ``parallel {``, ``schedule {``, ``select {``,
#: ``sequence {``, ``repeat (4) {`` -- and the bare ``{`` of an anonymous
#: sequence block, which is a header of exactly one token.
#:
#: Closed, and the closure does the same work here that it does in
#: ``decls._HEADER_VOCABULARY``: ``TOK_COLON`` is absent, so ``repeat (ri :
#: 4)`` cannot be given the inheritance colon's spacing by accident. It
#: declines instead, and the header is reproduced.
#:
#: The expression tokens are here for ``repeat``'s count. They bring the same
#: ambiguity they bring everywhere -- ``-`` is unary or additive, ``(`` is a
#: call or a grouping -- and the same answer: :func:`_repeat_sites` takes
#: those from the tree, and refuses the header if the tree did not classify
#: one.
_BLOCK_HEADER_VOCABULARY = dict(EXPRESSION_VOCABULARY)
_BLOCK_HEADER_VOCABULARY.update((name, WORD) for name in (
    "TOK_ACTIVITY",
    "TOK_PARALLEL",
    "TOK_SCHEDULE",
    "TOK_SELECT",
    "TOK_SEQUENCE",
    "TOK_REPEAT",
))
_BLOCK_HEADER_VOCABULARY["TOK_LCBRACE"] = Site.BRACE_OPEN

#: ``repeat``'s parens are the statement's own, not an expression's, so no
#: rule inside :mod:`~pssfmt.rules.exprs` claims them -- and the completeness
#: check would therefore refuse the header. Naming them costs no new decision:
#: ``Site.CONTROL_PAREN_*`` was measured at 118/118, and the three ``repeat``
#: headers in the corpus agree with it.
#:
#: The same mechanism ``P3-5`` added for ``default y == 2;``.
_REPEAT_SITES = {
    "activity_repeat_stmt": {
        "TOK_LPAREN": Site.CONTROL_PAREN_OPEN,
        "TOK_RPAREN": Site.CONTROL_PAREN_CLOSE,
    },
}

#: ``s_arr[2];`` -- traversing one element of an action-handle array.
#:
#: The brackets hang directly off ``action_handle_traversal_stmt`` rather than
#: off the ``member_path_elem_index`` an expression would use, so no rule in
#: :mod:`~pssfmt.rules.exprs` claims them and the completeness check refuses
#: the statement. Naming them here is the same move ``P3-5`` made for
#: ``default y == 2;``: the module that knows what the token is doing says so.
#:
#: No new decision. It is an index of an array, and ``Site.INDEX_BRACKET_*``
#: is 1002 of 1002 tight. The corpus has no indexed traversal to measure --
#: its one array traversal is the whole-array ``s_arr;`` -- but this is the
#: same construct at a different tree position rather than a new one, which
#: is the distinction that separates a gap from an unmade decision.
_TRAVERSAL_EXTRA_SITES = {
    "action_handle_traversal_stmt": {
        "TOK_LSBRACE": Site.INDEX_BRACKET_OPEN,
        "TOK_RSBRACE": Site.INDEX_BRACKET_CLOSE,
    },
}

#: ``fill;``, ``do mem_copy_a;``, ``do pkg::step;``, ``s_arr[2];``.
#:
#: Built from the expression vocabulary because a traversal *is* a scoped
#: name, optionally with an index -- there is nothing in it the expression
#: rules do not already classify. ``TOK_DO`` is word-class: it needs
#: separating from the type name after it (34/34 write one space) and has no
#: other opinion.
#:
#: ``TOK_WITH`` and ``TOK_LCBRACE`` are deliberately absent. See the module
#: docstring on inline constraints.
#:
#: A note on ``TOK_DO``, because mutation testing found it: what this entry
#: does is *admit* the token, and its value is inert. ``WORD`` contributes no
#: gap, and the space in ``do step`` comes from the lexical floor -- two
#: word-character tokens must be separated or they lex as one identifier. Any
#: zero-width site here would render identically, so the only mutation that
#: shows up is deleting the entry, which makes the statement decline. The same
#: is true of every keyword mapped to ``WORD`` in this codebase; it is stated
#: once, here, rather than left to look like an untested decision.
_TRAVERSAL_VOCABULARY = dict(EXPRESSION_VOCABULARY)
_TRAVERSAL_VOCABULARY["TOK_DO"] = WORD
_TRAVERSAL_VOCABULARY["TOK_SEMICOLON"] = Site.SEMICOLON

#: ``bind fill_copy.blk copy.src;``.
#:
#: Built from the atoms rather than from the expression vocabulary, for the
#: reason ``stmts._BIND_VOCABULARY`` gives: a bind statement holds names, not
#: arithmetic, and pulling in the operators would put tokens in two roles at
#: once for no gain. ``TOK_LCBRACE`` is absent, so ``bind a {b, c};`` declines.
_BIND_VOCABULARY = {
    "TOK_BIND": WORD,
    "ID": WORD,
    "ESCAPED_ID": WORD,
    "TOK_DOT": Site.MEMBER_ACCESS,
    "TOK_DOUBLE_COLON": Site.SCOPE_RESOLUTION,
    "TOK_COMMA": Site.COMMA,
    "TOK_LSBRACE": Site.INDEX_BRACKET_OPEN,
    "TOK_RSBRACE": Site.INDEX_BRACKET_CLOSE,
    "TOK_SEMICOLON": Site.SEMICOLON,
}

#: Rule name -> the body construct its indentation is asked for under.
#:
#: Six members for what v1 renders identically, following the precedent
#: ``Construct`` set for the seven declaration bodies: a member exists where a
#: plausible house style could want a different answer. Wanting ``parallel``
#: indented differently from ``schedule`` is odd; wanting it *possible* costs
#: an enum member, and merging them later is a rules edit either way.
_BLOCK_RULES = {
    "activity_declaration": Construct.ACTIVITY_BODY,
    "activity_sequence_block_stmt": Construct.ACTIVITY_SEQUENCE,
    "activity_parallel_stmt": Construct.ACTIVITY_PARALLEL,
    "activity_schedule_stmt": Construct.ACTIVITY_SCHEDULE,
    "activity_select_stmt": Construct.ACTIVITY_SELECT,
}

#: A block whose header is nothing but its own ``{``.
#:
#: ``activity_sequence_block_stmt`` has two spellings, ``sequence { … }`` and
#: a bare ``{ … }``, and only the first is laid out here. The bare one is
#: declined, and the corpus is what says so -- by failing a *style* test
#: rather than a rule test.
#:
#: ``docs/style.rst`` measures brace placement as attached: a ``{`` sits at
#: the end of the line its header is on, and no corpus file puts one alone.
#: An anonymous block has no header, so there is nothing for its brace to
#: attach to, and laying it out emits a line containing only ``{``. That is
#: not a rule that needs a special case; it is a construct that does not fit
#: the shape, and the honest response is to leave it as written.
#:
#: Declining also leaves the one inline instance -- ``{ copy; chk; }``, a
#: two-action sequence written compactly inside a ``parallel`` -- exactly as
#: its author wrote it. Whether such a block collapses is undecided anyway:
#: the corpus opens seven out and writes one inline, and a 7-to-1 split in
#: two files is not enough to rewrite the eighth.
_ANONYMOUS_BLOCK = "activity_sequence_block_stmt"

#: The two spellings of a traversal: ``fill;`` and ``do mem_copy_a;``.
_TRAVERSAL_RULES = (
    "action_handle_traversal_stmt",
    "action_type_traversal_stmt",
)


def _statement(ctx: Any, node: Any, vocabulary: Any,
               stops: Tuple[int, ...] = (), extra: Any = None) -> Layout:
    """*node* on one line, or reproduced unchanged if it is not ours."""
    span = code_span(ctx.trivia, node)
    if span is None:
        return _reproduce(ctx, node)
    sites = sites_for(ctx, node, extra_rules=extra)
    if sites is None:
        return _reproduce(ctx, node)
    emitted = emit_span(ctx, span[0], span[1], vocabulary,
                        sites_at=sites, mark_at=stops)
    return emitted if emitted is not None else _reproduce(ctx, node)


def _traversal(ctx: Any, node: Any) -> Layout:
    return _statement(ctx, node, _TRAVERSAL_VOCABULARY,
                      extra=_TRAVERSAL_EXTRA_SITES)


def _bind_stops(ctx: Any, node: Any) -> Tuple[int, ...]:
    """The one column a hand-aligned bind block lines up on.

    The seam between the source path and the target, which the grammar makes a
    node boundary -- ``activity_bind_stmt`` is ``'bind' hierarchical_id
    activity_bind_item_or_list ';'``. Taking it from the tree is exact;
    inferring it from tokens would mean re-deciding where a path ends.

    One stop rather than the two ``stmts._column_stops`` returns, because a
    bind has no ``=``: there is no second column, so there is no second column
    to lose.
    """
    for child in node.children:
        if child.is_rule and child.rule_name == "activity_bind_item_or_list":
            span = code_span(ctx.trivia, child)
            return () if span is None else (span[0],)
    return ()


def _bind(ctx: Any, node: Any) -> Layout:
    return _statement(ctx, node, _BIND_VOCABULARY, _bind_stops(ctx, node))


def _has_keyword(node: Any) -> bool:
    """Does this sequence block open with ``sequence`` rather than with ``{``?

    See :data:`_ANONYMOUS_BLOCK`. Asked of the first terminal rather than by
    searching for the keyword, because a nested block further in would
    otherwise answer for its parent.
    """
    for child in node.children:
        if child.is_rule or child.token is None:
            continue
        return child.token.type_name == "TOK_SEQUENCE"
    return False


def _repeat_body(node: Any) -> Optional[Any]:
    """The ``{ … }`` a ``repeat`` wraps.

    ``repeat (4) { … }`` parses as ``'repeat' '(' expression ')'
    activity_stmt``, and the braces belong to the sequence block inside that
    statement -- so the header spans two nodes and the body is a third, which
    is what ``_block``'s *body* parameter is for.

    ``repeat (4) do step;`` -- a repeat whose body is a single statement with
    no braces -- returns ``None`` and is reproduced. The corpus has none, and
    a block layout is the wrong shape for it anyway.
    """
    stack = list(node.children)
    while stack:
        cur = stack.pop(0)
        if not cur.is_rule:
            continue
        if cur.rule_name == "activity_sequence_block_stmt":
            return cur
        if cur.rule_name in ("activity_stmt_ann", "activity_stmt",
                             "activity_labeled_stmt", "labeled_activity_stmt"):
            stack.extend(cur.children)
    return None


def _repeat(ctx: Any, node: Any) -> Layout:
    body = _repeat_body(node)
    if body is None:
        return _reproduce(ctx, node)
    sites = sites_for(ctx, node, extra_rules=_REPEAT_SITES)
    if sites is None:
        return _reproduce(ctx, node)
    return _block(ctx, node, Construct.ACTIVITY_REPEAT, body=body,
                  vocabulary=_BLOCK_HEADER_VOCABULARY, sites=sites)


def register(registry) -> None:
    """Binds this module's builders. See ``decls.register`` on why a function."""

    def _make_block(construct):
        def builder(ctx, node):
            if node.rule_name == _ANONYMOUS_BLOCK and not _has_keyword(node):
                return _reproduce(ctx, node)
            return _block(ctx, node, construct,
                          vocabulary=_BLOCK_HEADER_VOCABULARY)
        return builder

    for rule_name, construct in _BLOCK_RULES.items():
        registry.register(rule_name, _make_block(construct))

    registry.register("activity_repeat_stmt", _repeat)
    registry.register("activity_bind_stmt", _bind)
    for rule_name in _TRAVERSAL_RULES:
        registry.register(rule_name, _traversal)

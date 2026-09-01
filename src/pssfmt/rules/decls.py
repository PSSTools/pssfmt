"""Tier 1 -- declarations and their bodies (``P3-2``).

The seven declaration forms PSS spells differently and lays out identically:
``package``, ``component``, ``action``, and ``struct`` in each of its five
kinds (``struct``, ``buffer``, ``stream``, ``state``, ``resource``). Plus the
compilation unit, which is a body with no braces around it.

What this module decides
------------------------
Structure, and only structure:

* ``{`` attaches to the line that opens the construct, one space before it
  (``docs/style.rst``: 732 of 733 attach, 725 of 732 with one space).
* A non-empty body breaks. Each member starts on its own line, indented by
  ``style.indent_for()`` -- never by a number written here (``T-13``).
* ``}`` returns to the construct's own column, on its own line.
* An empty body stays flat: ``buffer b {}``. There is nothing to put on a
  line, and a construct that spent two lines saying so reads worse.
* Blank lines between members are preserved and clamped to
  ``max_blank_lines``. Preserved, because a blank line is the author saying
  these members are a group; clamped, because how *many* they left is not.
* **Nothing is reordered.** Members are emitted in the order encountered
  (``docs/style.rst``: a commitment, not a default).

What it leaves alone
--------------------
The members themselves. A member with a rule is built by that rule; a member
without one is reproduced exactly, re-anchored to its new column and
otherwise untouched. That is what makes the tier adoptable one construct at a
time, and it means this module changes nothing inside a construct it does not
name.

The header is likewise reproduced rather than rebuilt: ``struct s : base_s``
keeps the author's spacing. Normalising it means emitting individual tokens,
and emitting a token means owning the comments attached to it. That is the
next step, not this one.

Where the comments go
---------------------
Two rules, and between them they cover every comment a body can hold:

* An **own-line comment above a member** is emitted with that member, as a
  block, including any blank line between comment and code. Treating a
  comment as a member in its own right would make the formatter re-decide
  something the author already decided.
* A **trailing comment** is appended by this module rather than by whatever
  built the member, so that a nested declaration's ``} // end of c`` survives.
  A rule builder emits its construct and stops; nothing in it knows about the
  comment hanging off its last token, and if the parent did not pick that up
  it would simply be gone.
"""

from __future__ import annotations

from typing import Any, List, NamedTuple, Optional, Tuple

from ..layout import ALIGN_MARK, Layout, concat, indent, text
from ..style import Construct, SemicolonMode, Site
from .emit import (
    code_span,
    hardline,
    reindented_layout,
    span_text,
    span_tokens,
    verbatim_layout,
)
from .exprs import sites_for
from .tokens import WORD, emit_span, floor_gap

#: ``struct_kind`` covers five spellings that lay out the same way but are
#: separate members of :class:`~pssfmt.style.Construct`, so a house style can
#: eventually treat a ``buffer`` differently from a ``struct`` without any of
#: this changing.
_OBJECT_KINDS = {
    "TOK_STRUCT": Construct.STRUCT_BODY,
    "TOK_BUFFER": Construct.BUFFER_BODY,
    "TOK_STREAM": Construct.STREAM_BODY,
    "TOK_STATE": Construct.STATE_BODY,
    "TOK_RESOURCE": Construct.RESOURCE_BODY,
}

#: Wrapper rules the grammar puts between a body and its items. They carry no
#: text of their own and cover exactly the same tokens as the thing inside
#: them, so a member is looked *through* them rather than at them.
#:
#: They are not registered as builders. A passthrough builder would have to
#: delegate to ``ctx.build``, whose fallback reproduces a node together with
#: its leading and trailing trivia -- correct for ``P3-1``, and wrong here,
#: because the enclosing body has already emitted that trivia itself. The
#: result is a comment and an indent emitted twice. Resolving the chain
#: before deciding anything keeps one owner for each byte.
_PASSTHROUGH = (
    "portable_stimulus_description",
    "package_body_item_ann",
    "package_body_item",
    "component_body_item_ann",
    "component_body_item",
    "action_body_item_ann",
    "action_body_item",
    "struct_body_item",
    # ``P3-5``. ``constraint_body_item`` wraps every item in a constraint
    # block, and ``constraint_set`` wraps the single item of an anonymous
    # ``constraint e;`` -- both are one-child rules with nothing of their own
    # to say, exactly like the body-item wrappers above.
    "constraint_body_item",
    "constraint_set",
    "default_constraint_item",
    # ``P3-6``. Four wrappers cover one activity statement:
    # ``activity_stmt_ann`` -> ``activity_stmt`` -> ``activity_labeled_stmt``
    # -> ``labeled_activity_stmt`` -> the statement itself.
    #
    # A *labelled* statement stops the walk here rather than needing a rule to
    # decline it, and that is worth saying because it is the whole treatment
    # of labels in ``P3-6``: ``a: do step;`` makes ``activity_labeled_stmt``
    # two rules plus a bearing ``:``, which the guard below already refuses to
    # look through. All eight labels in the corpus are in one file, so one
    # voice, so undecided -- and the label colon's default in ``style.py`` is
    # marked "by preference" for exactly that reason. It stays unused.
    "activity_stmt_ann",
    "activity_stmt",
    "activity_labeled_stmt",
    "labeled_activity_stmt",
    # A ``select`` branch. Plain branches are a wrapper like the others; a
    # *guarded* or *weighted* one -- ``(mode == FAST) [3]: do fast_step;`` --
    # carries its guard and weight as bearing tokens, so the guard above stops
    # the walk and the branch is reproduced. One corpus instance, and it needs
    # a label colon and a weight bracket that is none of the four measured.
    "select_branch",
    # ``activity_action_traversal_stmt`` wraps the handle and type spellings
    # of the same statement; both are laid out by one builder, registered on
    # the two inner rules rather than on this wrapper.
    "activity_action_traversal_stmt",
    # ``P3-11b``. Every member of a function body is one of these, wrapping
    # one of thirteen alternatives -- so until it was here, registering
    # ``procedural_return_stmt`` bound a builder that dispatch could never
    # reach. ``T-30`` said so on the first run, which is the third time that
    # test has been the thing that noticed.
    #
    # A lone ``;`` is also a ``procedural_stmt`` and must *not* be looked
    # through: it has no rule child at all, so the guard below stops on it,
    # and ``_is_trailing_semicolon`` has already merged it by then anyway.
    "procedural_stmt",
    # ``P3-8a``. One wrapper over PSS's three ``exec`` forms, and it was the
    # reason the frontier census reported ``exec_block_stmt`` as the largest
    # declined construct: 24 of them, and *none* of them was an exec block --
    # they were this wrapper, which nothing looked through, so the thing
    # inside was never asked about.
    #
    # The three shapes it resolves to are all handled correctly and only one
    # of them by a rule: 22 wrap a native ``exec_block``, 2 wrap a
    # ``target_code_exec_block`` (``P3-8``'s verbatim kind, still reproduced,
    # deliberately), and 2 are a bare ``;`` with no rule child at all, which
    # the guard below stops on.
    "exec_block_stmt",
    # ...and the wrapper *inside* it, which is a separate omission and was
    # caught separately. Registering ``exec_block`` reached 28 exec blocks and
    # unblocked **nothing inside them**: the members of an exec body are
    # ``exec_stmt``, not ``procedural_stmt``, so every one of the 109
    # statements in them was still being reproduced while the header and the
    # indentation moved. A reach census run *with and without* the new rule is
    # what showed a delta of exactly zero -- the same measurement that found
    # this wrapper's twin one item earlier.
    #
    # ``exec_stmt`` is ``procedural_stmt | exec_super_stmt``. The second is a
    # bare ``super;`` with a rule of its own and none in the registry, so it
    # resolves and then reproduces, which is what it did before.
    "exec_stmt",
)


#: What a declaration header may contain for this module to write it out
#: token by token (``P3-2b``). A closed set, and closed at the point the
#: evidence stops being uniform: 225 of the corpus's 356 headers use exactly
#: this vocabulary, in 16 shapes, none of them wrapped across lines and none
#: containing a comment.
#:
#: The other 131 have a **template parameter list** -- ``component c<struct
#: TRAIT : addr_trait_s = empty_addr_trait_s>`` -- which brings ``<``, ``>``,
#: ``,``, ``=`` and a nested default-value expression, is where all nine
#: multi-line headers and the one interior comment live, and is a list that
#: may need to break rather than a run of tokens that fits. That is a rule
#: about parameter lists, and it is ``P3-7``'s (§7.1 tier 3). Until then a
#: templated header is reproduced as the author wrote it, which is what
#: happened before this vocabulary existed.
#:
#: ``TOK_COLON`` maps to inheritance unconditionally, which is safe only
#: *because* the set is closed: a bit-slice colon needs ``[``, and a case-item
#: colon needs a case, and neither can occur in a span made of these tokens.
_HEADER_VOCABULARY = {
    "TOK_PACKAGE": WORD,
    "TOK_COMPONENT": WORD,
    "TOK_ACTION": WORD,
    "TOK_STRUCT": WORD,
    "TOK_BUFFER": WORD,
    "TOK_STREAM": WORD,
    "TOK_STATE": WORD,
    "TOK_RESOURCE": WORD,
    "TOK_PURE": WORD,
    # ``constraint c {`` and ``dynamic constraint c {`` (``P3-5``). Word-class
    # keywords with no second reading, and they cannot make the colon
    # ambiguous either: a constraint header has no inheritance clause, so the
    # only ``:`` reachable in a span of these tokens is still that one.
    "TOK_CONSTRAINT": WORD,
    "TOK_DYNAMIC": WORD,
    # ``extend component spi_c {``, ``extend action dma_c::xfer {`` -- 32
    # instances across 31 files, in five shapes, all of them this one
    # (``P3-6``). ``extend`` reuses the object-kind keywords already here, so
    # the only genuinely new token is ``::``.
    #
    # Neither addition weakens the closure argument the colon rests on: no
    # span of these tokens can contain a ``[`` or a case, so ``:`` is still
    # unambiguously inheritance. ``:`` next to ``:`` is a *lexical* question
    # rather than a spacing one, and ``must_separate`` already answers it --
    # emitting ``a : :b`` for ``a::b`` would be a different program, which is
    # the merge ``P3-4`` made the emitter check for.
    "TOK_EXTEND": WORD,
    "TOK_DOUBLE_COLON": Site.SCOPE_RESOLUTION,
    "ID": WORD,
    "ESCAPED_ID": WORD,
    "TOK_COLON": Site.COLON_INHERITANCE,
    "TOK_LCBRACE": Site.BRACE_OPEN,
    # ``struct dma_csr_s : packed_s<bit, 32> {`` -- template arguments
    # (``P3-7``). The single largest cause of declined headers before this
    # item: 116 of the corpus's 131, across 32 files.
    #
    # ``<`` and ``>`` are ``WORD`` here in the sense :mod:`pssfmt.rules.exprs`
    # established -- recognised, but with no answer of their own. Their site
    # arrives through ``sites_at`` from :func:`sites_before`, because
    # ``TOK_LT`` is *also* the comparison operator and the two have opposite
    # measured answers. The completeness check there is what makes admitting
    # them safe: an angle bracket this module cannot account for declines the
    # header rather than picking up whichever reading came first.
    "TOK_LT": WORD,
    "TOK_GT": WORD,
    "TOK_COMMA": Site.COMMA,
    # What a template argument can be, besides a name: a literal or a scalar
    # type. Both word-class, neither with a second reading. Measured inside
    # the corpus's 137 argument lists, the whole inventory is ID (172), ``,``
    # (120), DEC_LITERAL (67), ``bit`` (6), ``[`` / ``]`` (6) and ``int`` (1).
    "DEC_LITERAL": WORD,
    "HEX_LITERAL": WORD,
    "OCT_LITERAL": WORD,
    "BIN_LITERAL": WORD,
    "TOK_TRUE": WORD,
    "TOK_FALSE": WORD,
    "TOK_BIT": WORD,
    "TOK_INT": WORD,
    "TOK_BOOL": WORD,
    "TOK_STRING": WORD,
    "TOK_FLOAT32": WORD,
    "TOK_FLOAT64": WORD,
    "TOK_CHANDLE": WORD,
    # Note what is deliberately *not* here: ``[`` and ``]``. So
    # ``packed_s<bit[8], 4>`` still declines -- 6 instances across 4 files.
    #
    # That boundary is drawn by the colon argument above and not by effort.
    # The closure making ``:`` unambiguously inheritance is "no span of these
    # tokens can contain a ``[``", and a template argument is a constant
    # *expression*, so admitting the bracket makes ``s<A[3:0]>`` spellable and
    # ``Site.COLON_BIT_SLICE`` reachable here in principle. Six instances is
    # not worth trading a proof for a coincidence. Nothing else added for
    # ``P3-7`` touches that closure: a header cannot contain a case item, so
    # ``,`` cannot be one, and none of the rest is punctuation at all.
    #
    # Admitting the bracket is a real item rather than a refusal -- it wants
    # the colon closure turned from this comment into a completeness check
    # over ``:`` first, the way ``<`` is checked below. See ``P3-7a``.
}

#: ``import pkg::*;`` -- all 147 imports in the corpus, and the same shape
#: every time.
#:
#: ``*`` is deliberately **not** a site. In an expression it is
#: ``Site.MULTIPLICATIVE`` and spaced; here it is a wildcard, and the gaps on
#: both sides of it are already decided by its neighbours --
#: ``Site.SCOPE_RESOLUTION`` is tight and ``Site.SEMICOLON`` is tight. Giving
#: it a site of its own would mean inventing a default no measurement
#: supports; giving it the expression site would emit ``import pkg:: * ;``.
#: Contributing nothing is both correct and the only option backed by
#: evidence.
#:
#: ``import target function read;`` is a different grammar rule
#: (``import_function``) and is not handled here.
_IMPORT_VOCABULARY = {
    "TOK_IMPORT": WORD,
    "ID": WORD,
    "ESCAPED_ID": WORD,
    "TOK_DOUBLE_COLON": Site.SCOPE_RESOLUTION,
    "TOK_ASTERISK": WORD,
    "TOK_SEMICOLON": Site.SEMICOLON,
}


#: Returned where ``None`` already means "there is none": tells the caller to
#: reproduce the construct rather than lay it out. A distinct object because
#: "nothing here" and "do not touch this" are opposite instructions and
#: collapsing them into one falsy value is how the second becomes the first.
_BAIL = object()


class _Member(NamedTuple):
    """A member of a body, with the vertical space the author left above it."""

    blanks_before: int
    layout: Layout


class _Leading(NamedTuple):
    """What sits between the previous member and this one's first code token."""

    #: Blank lines before the whole block, comments included.
    blanks_before: int
    #: The comment run, re-anchorable, or ``None`` when there is none.
    comments: Optional[Layout]
    #: Blank lines between the last comment and the code it introduces.
    blanks_after: int


def _only_whitespace(tokens: Any) -> bool:
    """Whether *tokens* can be thrown away and replaced by a layout decision.

    Every run this module discards -- the indentation before a member, the gap
    before ``{`` -- is *supposed* to be pure whitespace, and usually is. But a
    lexical error puts a token in the stream that no grammar rule claims and
    no CST node covers, and it lands in exactly these runs. Replacing that with
    a computed indent deletes a byte of the user's file.

    The ``P1-3`` fail-safe does catch it, which is how it was found. Catching
    it here is better: the fail-safe hands back the whole file unformatted,
    where this reproduces one construct and formats the rest.
    """
    return all(not tok.text.strip() for tok in tokens)


def _terminal_type(node: Any) -> Optional[str]:
    if node is None or node.is_rule or node.token is None:
        return None
    return node.token.type_name


def _braces(node: Any) -> Optional[Tuple[int, int]]:
    """Child positions of the body's ``{`` and ``}``.

    The *first* ``{`` and the *last* ``}`` among this node's direct children.
    Deeper braces belong to a nested construct and are that construct's
    problem; taking the outermost pair is what makes this work without knowing
    which declaration it is looking at.
    """
    open_at = close_at = None
    for i, child in enumerate(node.children):
        kind = _terminal_type(child)
        if kind == "TOK_LCBRACE" and open_at is None:
            open_at = i
        elif kind == "TOK_RCBRACE":
            close_at = i
    if open_at is None or close_at is None or close_at < open_at:
        return None
    return open_at, close_at


def _blank_lines_before(ctx: Any, tok: Any) -> int:
    """Empty lines between *tok* and the last content above it.

    Computed from line numbers rather than by counting newlines in the
    whitespace between, because a ``//`` comment token **carries its own
    trailing newline**. Counting characters, that newline is indistinguishable
    from a blank line, so ``// x`` followed by a genuinely blank line reports
    the same number as ``// x`` followed by nothing -- and the blank line the
    author left disappears.

    ``rstrip`` on the previous token for the same reason: the newline
    terminating a line comment is not content on the following line.
    """
    stream = ctx.trivia.stream
    i = tok.index - 1
    while i >= 0 and stream[i].is_trivia and not stream[i].is_comment:
        i -= 1
    if i < 0:
        return 0
    prev = stream[i]
    return max(0, tok.line - (prev.line + prev.text.rstrip("\n").count("\n")) - 1)


def _comment_run(lead: Tuple[Any, ...], start: int) -> Layout:
    """The comments in *lead* from *start* on, as a re-anchorable block."""
    body = "".join(tok.text for tok in lead[start:]).rstrip()
    return reindented_layout(tuple(lead[start:]), body, lead[start].col)


def _leading(ctx: Any, token_index: int) -> Optional[_Leading]:
    """``None`` when the run holds something this module must not discard."""
    entry = ctx.trivia.of(token_index)
    lead = entry.raw_leading
    start = next((i for i, tok in enumerate(lead) if tok.is_comment), None)
    if start is None:
        if not _only_whitespace(lead):
            return None
        return _Leading(_blank_lines_before(ctx, entry.token), None, 0)
    if not _only_whitespace(lead[:start]):
        return None
    return _Leading(
        _blank_lines_before(ctx, lead[start]),
        _comment_run(lead, start),
        _blank_lines_before(ctx, entry.token),
    )


def _trailing(ctx: Any, token_index: int) -> Optional[Layout]:
    """A same-line comment hanging off *token_index*, if there is one.

    Emitted behind a **column stop**, with the author's own gap after it. This
    is the run ``docs/style.rst`` measured most sharply: hand-written code
    aligns its trailing comments in every run of three or more, and generated
    code never does. ``infer`` tells them apart, but only if the original
    spacing reaches it -- so the gap carried here is the author's, not a
    computed one, and :mod:`pssfmt.layout.align` decides what becomes of it.
    """
    run = ctx.trivia.of(token_index).raw_trailing
    if not any(tok.is_comment for tok in run):
        return None if _only_whitespace(run) else _BAIL
    body = "".join(tok.text for tok in run).rstrip()
    if "\n" in body:
        return _BAIL
    stripped = body.lstrip(" \t")
    gap = len(body) - len(stripped)
    if "\t" in body[:gap]:
        # Re-anchoring a tab means guessing a tab width, which is a display
        # setting rather than a fact about the file. Reproduced as written.
        return text(body)
    return text(ALIGN_MARK + " " * max(gap, 1) + stripped)


def _effective(node: Any) -> Any:
    """Looks through the grammar's wrapper rules to the declaration inside.

    ``package_body_item_ann`` -> ``package_body_item`` -> ``struct_declaration``
    are three nodes covering one span. Only the last has anything to say about
    layout; the first two exist to hang annotations on, and stopping at one of
    them means the declaration inside never reaches its rule.
    """
    while node.is_rule and node.rule_name in _PASSTHROUGH:
        rules = [c for c in node.children if c.is_rule]
        bearing = [c for c in node.children
                   if not c.is_rule and c.token is not None]
        if len(rules) != 1 or bearing:
            # An annotation, or something else carrying text of its own.
            # Looking through it would drop that text.
            return node
        node = rules[0]
    return node


def _reproduce(ctx: Any, node: Any) -> Layout:
    """*node* as written, **without** the trivia its parent already emitted.

    Not :meth:`BuildContext.verbatim`, and the difference is the whole reason
    this function exists. ``ctx.verbatim`` reproduces a node together with its
    leading and trailing trivia, which is right for ``P3-1``'s fallback --
    there, nobody else is going to emit it. Inside a body, the enclosing rule
    has *already* emitted that trivia as an indent and a blank-line count, so
    reproducing it again writes the member's original indentation a second
    time. The symptom is a stray blank line, and it only appears where a rule
    bails out mid-construct, which is exactly where nobody is looking.
    """
    span = code_span(ctx.trivia, node)
    if span is None:
        return text("")
    first, last = span
    body = span_text(ctx.trivia, first, last, leading=False, trailing=False)
    tokens = span_tokens(ctx.trivia, first, last, leading=False, trailing=False)
    origin = ctx.trivia.of(ctx.trivia.code_indices[first]).token.col
    return reindented_layout(tokens, body, origin)


def _member_body(ctx: Any, node: Any, first: int, last: int) -> Layout:
    """The member itself: its own rule if it has one, reproduced if not.

    Excludes both the leading and the trailing trivia runs, which
    :func:`_member` owns -- see the module docstring on why the parent picks
    up the trailing comment rather than the builder.
    """
    inner = _effective(node)
    if not getattr(inner, "is_error", False) and inner.is_rule \
            and ctx.registry.get(inner.rule_name) is not None:
        return ctx.build(inner)
    return _reproduce(ctx, node)


def _member(ctx: Any, node: Any, terminator: bool = False) -> Optional[_Member]:
    """One member of a body, with its comments.

    *terminator* writes a ``;`` after it -- ``SemicolonMode.REQUIRE``. It is a
    flag here rather than something the caller concatenates on afterwards
    because of *where* the token goes: between the member and its trailing
    comment. ``struct s {} // note`` composed the other way round becomes
    ``struct s {} // note;``, which is a semicolon inside a comment.
    """
    span = code_span(ctx.trivia, node)
    if span is None:
        return None
    first, last = span

    lead = _leading(ctx, ctx.trivia.code_indices[first])
    if lead is None:
        return None
    parts: List[Layout] = []
    if lead.comments is not None:
        parts.append(lead.comments)
        parts.append(hardline(lead.blanks_after))
    parts.append(_member_body(ctx, node, first, last))
    if terminator:
        # No lexical floor: the caller only asks for this after a ``}``, which
        # cannot be an escaped identifier and so cannot swallow what follows
        # it. See ``_wants_a_terminator``.
        parts.append(text(";"))

    trailing = _trailing(ctx, ctx.trivia.code_indices[last])
    if trailing is _BAIL:
        return None
    if trailing is not None:
        parts.append(trailing)

    return _Member(lead.blanks_before, concat(parts))


def _dangling(ctx: Any, close_index: int) -> Optional[_Member]:
    """Comments with nothing after them but the closing brace.

    ``formatter.md`` section 3.1 rule 4. They are the one kind of comment no
    member owns, and dropping them is the classic way a formatter loses the
    ``// TODO`` that was the only thing in an empty block.
    """
    lead = ctx.trivia.of(close_index).raw_leading
    start = next((i for i, tok in enumerate(lead) if tok.is_comment), None)
    if start is None:
        return None if _only_whitespace(lead) else _BAIL
    if not _only_whitespace(lead[:start]):
        return _BAIL
    return _Member(_blank_lines_before(ctx, lead[start]),
                   _comment_run(lead, start))


def _stack(ctx: Any, members: List[_Member], *, lead_break: bool) -> Layout:
    """Members one per line, with the author's blank lines clamped.

    *lead_break* asks for a break before the first member too. A braced body
    needs one -- the member follows ``{`` on the opening line otherwise -- and
    the compilation unit must not have one, because there is nothing above the
    first declaration in a file to break away from.
    """
    limit = ctx.style.max_blank_lines
    parts: List[Layout] = []
    for i, member in enumerate(members):
        if i or lead_break:
            parts.append(hardline(min(member.blanks_before, limit)))
        parts.append(member.layout)
    return concat(parts)


def _tiles(spans: List[Tuple[int, int]], first: int, last: int) -> bool:
    """Whether *spans* cover ``first..last`` exactly, in order, with no gap.

    The invariant that makes this module safe to point at anything. A rule
    emits its members and nothing else, so a code token that falls between two
    members -- or before the first, or after the last -- is simply not written
    out. Nothing else notices: the output is shorter and still looks like PSS.

    Specifically, it backs the one place :func:`_collect` skips a child: a
    rule node whose ``code_span`` is ``None`` contributes no members, which is
    harmless when it really has no tokens and silent data loss when recovery
    has left it with reversed bounds. Skipping is right; noticing the hole it
    leaves is this function's job.

    **No input found so far reaches the bail-out with an observable effect.**
    It fires five times over the corpus and on several crafted malformed
    inputs, and in every one the path without it produces identical output --
    because a stray *terminal* between the braces is already refused by
    :func:`_collect`. Said plainly rather than left implied: this is a guard
    against a case that has not been demonstrated, kept because its failure
    mode is a token disappearing from the user's file, and tested as a
    function (``T-19``) rather than through behaviour that does not vary.
    """
    if not spans:
        return first > last
    if spans[0][0] != first or spans[-1][1] != last:
        return False
    return all(b[0] == a[1] + 1 for a, b in zip(spans, spans[1:]))


#: Rules after which a sibling ``;`` is **decoration** rather than a
#: terminator -- every alternative of the rule ends in a ``;`` or a ``}`` of
#: its own, so a further one can only be the enclosing body's empty-item
#: alternative.
#:
#: Derived, not curated: ``tools/semicolon_survey.py`` computes it as a least
#: fixed point over ``PSSParser.g4`` and prints exactly this list.
#: ``tests/corpus/test_semicolon_grammar.py`` re-runs the derivation whenever
#: the grammar is on disk and fails if the two have drifted.
#:
#: The exclusions are the point. ``procedural_data_declaration`` is absent
#: because it ends in an *expression* -- the grammar makes its terminator a
#: sibling ``procedural_stmt``, so ``int a[4] = {1, 2};`` is a lone ``;``
#: after a ``}`` that must never be dropped, and it is indistinguishable from
#: ``enum e {A, B};`` by position alone. ``constraint_declaration`` and the
#: traversal statements are absent for a softer reason -- they reach a
#: recursive knot the fixed point cannot prove -- and the corpus agrees with
#: the caution: all four of its ``x with { … };`` and ``constraint c { … };``
#: sites write the semicolon.
_SELF_TERMINATING = frozenset((
    "abstract_action_declaration",
    "abstract_monitor_declaration",
    "action_declaration",
    "action_field_declaration",
    "action_handle_declaration",
    "action_initializer_list",
    "activity_atomic_block_stmt",
    "activity_bind_stmt",
    "activity_data_field",
    "activity_declaration",
    "activity_match_stmt",
    "activity_parallel_stmt",
    "activity_schedule_stmt",
    "activity_scheduling_constraint",
    "activity_select_stmt",
    "activity_sequence_block_stmt",
    "activity_super_stmt",
    "aggregate_literal",
    "annotation_attr_field",
    "annotation_declaration",
    "annotation_params_list",
    "attr_field",
    "bins_or_empty",
    "compile_assert_stmt",
    "component_data_declaration",
    "component_declaration",
    "component_pool_declaration",
    "const_field_declaration",
    "constraint_block",
    "cover_stmt",
    "covergroup_coverpoint",
    "covergroup_coverpoint_binspec",
    "covergroup_coverpoint_body_item",
    "covergroup_cross",
    "covergroup_cross_binspec",
    "covergroup_cross_body_item",
    "covergroup_declaration",
    "covergroup_instantiation",
    "covergroup_option",
    "covergroup_options_or_empty",
    "covergroup_type_instantiation",
    "coverpoint_bins",
    "cross_item_or_null",
    "data_declaration",
    "default_constraint",
    "default_constraint_item",
    "default_disable_constraint",
    "dist_directive",
    "empty_aggregate_literal",
    "enum_declaration",
    "exec_block",
    "exec_block_stmt",
    "exec_super_stmt",
    "export_action",
    "export_function",
    "expression_constraint_item",
    "extend_stmt",
    "flow_ref_field_declaration",
    "function_decl",
    "generic_constraint_value",
    "import_class_decl",
    "import_class_function_decl",
    "import_function",
    "import_stmt",
    "inline_covergroup",
    "instance_override",
    "map_literal",
    "monitor_activity_concat_stmt",
    "monitor_activity_declaration",
    "monitor_activity_overlap_stmt",
    "monitor_activity_schedule_stmt",
    "monitor_activity_select_stmt",
    "monitor_activity_sequence_block_stmt",
    "monitor_constraint_block",
    "monitor_declaration",
    "monitor_field_declaration",
    "monitor_handle_declaration",
    "object_bind_stmt",
    "object_ref_field_declaration",
    "override_action_declaration",
    "override_declaration",
    "package_declaration",
    "procedural_assignment_stmt",
    "procedural_break_stmt",
    "procedural_continue_stmt",
    "procedural_function",
    "procedural_match_stmt",
    "procedural_return_stmt",
    "procedural_sequence_block_stmt",
    "procedural_void_function_call_stmt",
    "procedural_yield_stmt",
    "pyimport_from_module",
    "pyimport_single_module",
    "pyimport_stmt",
    "resource_ref_field_declaration",
    "soft_constraint_item",
    "struct_declaration",
    "struct_literal",
    "symbol_call",
    "symbol_declaration",
    "target_code_exec_block",
    "target_file_exec_block",
    "target_template_function",
    "type_override",
    "typedef_declaration",
    "unique_constraint_item",
    "value_list_literal",
))


#: Rules that admit a bare ``;`` as an alternative -- the body kinds where an
#: empty item is grammatical, and therefore the only ones
#: ``SemicolonMode.REQUIRE`` may write one into.
#:
#: Derived by ``tools/semicolon_survey.py --empty-items`` and checked by
#: ``tests/corpus/test_semicolon_grammar.py``, like :data:`_SELF_TERMINATING`.
#: It is a *separate* question from that one and neither implies the other:
#: deleting is justified by the member (what came before already ended, so the
#: ``;`` says nothing), inserting is justified by the body (a rule with no
#: empty-item alternative would be handed a syntax error). An ``enum``
#: separates them cleanly -- ``enum e {A, B}`` is self-terminating so a ``;``
#: after it goes, and ``enum_item`` is not here so no ``;`` is ever written
#: between two enum items.
#:
#: Asked of the *tree* rather than of a ``Construct``: :func:`_permits_a_null_item`
#: walks the wrapper chain the grammar actually built above a member, so a
#: body kind nobody has mapped to a ``Construct`` yet cannot be answered wrongly
#: by omission. Six of these -- the ``…_or_empty`` shapes and
#: ``procedural_randomization_term`` -- are "X or ``;``" rules rather than item
#: lists and can never appear in that chain, because none of them is in
#: :data:`_PASSTHROUGH`.
_PERMITS_EMPTY_ITEM = frozenset((
    "action_body_item",
    "activity_stmt",
    "annotation_body_item",
    "bins_or_empty",
    "component_body_item",
    "constraint_body_item",
    "covergroup_body_item",
    "covergroup_options_or_empty",
    "cross_item_or_null",
    "exec_block_stmt",
    "inline_constraints_or_empty",
    "monitor_activity_stmt",
    "monitor_body_item",
    "monitor_constraint_body_item",
    "monitor_inline_constraints_or_empty",
    "override_stmt",
    "package_body_item",
    "procedural_randomization_term",
    "procedural_stmt",
    "struct_body_item",
))


def _is_trailing_semicolon(ctx: Any,
                           span: Tuple[int, int],
                           prev: Optional[Tuple[int, int]]) -> bool:
    """Whether *span* is a lone ``;`` closing the member before it.

    PSS permits a semicolon after a declaration -- ``enum e {A, B};`` -- and
    the grammar makes it a sibling of the enum rather than part of it. Treated
    as a member in its own right it lands on its own line, which is how
    ``std_pkg.pss`` came back with four bare semicolons in it. It belongs to
    the declaration it follows, and :func:`_semicolon_member` decides what
    becomes of it there -- merged onto that line, or dropped.

    Note what this function does *not* decide. It answers "does this ``;``
    belong to the member before it", which is a question about position; the
    separate question of whether the grammar *required* it is answered from
    the member's rule, one call further on. Half of the semicolons reaching
    here are required terminators the grammar models as siblings.

    The same-line test is what keeps this from swallowing a semicolon that the
    author genuinely put somewhere else, and it is also what makes it fire on
    error recovery, where a stray ``;`` ends up a sibling for a different
    reason and wants exactly the same treatment.
    """
    if prev is None or span[0] != span[1]:
        return False
    code = ctx.trivia.code_indices
    tok = ctx.trivia.of(code[span[0]]).token
    if tok.text != ";":
        return False
    prev_entry = ctx.trivia.of(code[prev[1]])
    if any(t.is_comment for t in prev_entry.raw_trailing):
        return False
    return tok.line == prev_entry.token.line


def _hatched(ctx: Any, first: int, last: int) -> Optional[_Member]:
    """Code positions ``first..last`` as one block, byte for byte (``P3-9``).

    The body of a member the author has switched the formatter off over. It is
    :func:`~pssfmt.rules.emit.verbatim_layout` rather than
    :func:`~pssfmt.rules.emit.reindented_layout` because re-anchoring is the
    one transformation a hatch is most often written to prevent: a hand-built
    alignment table means nothing once its columns move.

    Everything else about a member still applies. The leading comment run --
    which is where the ``// pssfmt off`` itself lives -- and the trailing
    comment are emitted by the same code as for any other member, so a hatch
    does not need its own answer to where comments go.

    One thing here is not byte-exact and it is worth being exact about which:
    the **first line's indentation**. The enclosing block writes an indent
    before every member, and a :class:`~pssfmt.layout.ir.Verbatim` cannot
    refuse it -- there is no layout node for "start at an absolute column".
    Every line after the first keeps the column the author gave it, which is
    what makes the table survive. ``P3-9a`` is the note for the layout node
    that would close the gap.
    """
    trivia = ctx.trivia
    lead = _leading(ctx, trivia.code_indices[first])
    if lead is None:
        return None
    parts: List[Layout] = []
    if lead.comments is not None:
        parts.append(lead.comments)
        parts.append(hardline(lead.blanks_after))
    parts.append(verbatim_layout(
        span_text(trivia, first, last, leading=False, trailing=False)))
    trailing = _trailing(ctx, trivia.code_indices[last])
    if trailing is _BAIL:
        return None
    if trailing is not None:
        parts.append(trailing)
    return _Member(lead.blanks_before, concat(parts))


def _merge_terminal(ctx: Any, members: List[_Member],
                    spans: List[Tuple[int, int]], at: int) -> bool:
    """Writes the code token at *at* onto the end of the previous member.

    The shape two constructs share: a terminal that belongs to the member
    before it rather than being one. ``enum e {A, B};``'s ``;`` is a *sibling*
    of the enum (``P3-2``), and an ``enum``'s own ``,`` is a separator its
    parent owns (``P3-12``) -- different grammar reasons, identical treatment.

    ``False`` means the trailing trivia held something this cannot discard,
    and the caller must decline.

    Written tight, by intent, and the style is not consulted: a terminator is
    part of what it terminates. Both measurements agree anyway -- ``;`` before
    a declaration is 1242/1243 tight and an enum's ``,`` is 25/25. The
    **lexical floor** still applies and is not theoretical here: a recovered
    fragment can end in an escaped identifier, which swallows a ``;`` written
    against it (``P3-10``).
    """
    code = ctx.trivia.code_indices
    tail = _trailing(ctx, code[at])
    if tail is _BAIL:
        return False
    token = ctx.trivia.of(code[at]).token
    prev_last = ctx.trivia.of(code[spans[-1][1]]).token
    parts = [members[-1].layout,
             text(" " * floor_gap(0, prev_last, token) + token.text)]
    if tail is not None:
        parts.append(tail)
    members[-1] = _Member(members[-1].blanks_before, concat(parts))
    spans[-1] = (spans[-1][0], at)
    return True


def _drop_terminal(ctx: Any, members: List[_Member],
                   spans: List[Tuple[int, int]], at: int) -> bool:
    """Deletes the code token at *at*, keeping everything attached to it.

    :func:`_merge_terminal` without the token: the optional ``;`` of
    ``SemicolonMode.OMIT``. The span still has to be claimed -- ``_tiles``
    checks that the members between two braces account for every code
    position, and a hole in that cover is how a body silently loses a member
    -- so this is a deletion in the *output*, not in the bookkeeping.

    The comment a ``;`` owns survives it. ``struct s {};  // done`` loses the
    semicolon and keeps the note, re-attached to the ``}`` that is now the
    last token on the line -- the same layout :func:`_trailing` would have
    produced for it there. Dropping a token is allowed to cost that token and
    nothing else.

    ``False`` means :func:`_trailing` refused the run, and the caller keeps
    the semicolon.

    Nothing here looks at the ``;``'s *leading* trivia, and that is the same
    silence as :func:`_merge_terminal`'s rather than an oversight: a comment
    between the two tokens is on the previous token's line, so the trivia map
    files it as that token's trailing run -- where
    :func:`_is_trailing_semicolon` has already seen it and declined, long
    before either function is called. ``} /* why */ ;`` reaches neither.
    """
    tail = _trailing(ctx, ctx.trivia.code_indices[at])
    if tail is _BAIL:
        return False
    if tail is not None:
        members[-1] = _Member(members[-1].blanks_before,
                              concat([members[-1].layout, tail]))
    spans[-1] = (spans[-1][0], at)
    return True


def _semicolon_member(ctx: Any, members: List[_Member],
                      spans: List[Tuple[int, int]], at: int,
                      construct: Optional[Construct],
                      prev_rule: Optional[str]) -> bool:
    """Disposes of the optional ``;`` at code position *at*.

    The one place the style is consulted about a *token* rather than about the
    space around one, and the only place ``pssfmt`` removes something the
    author wrote. Three conditions gate it, and all three must hold:

    * :meth:`~pssfmt.style.Style.optional_semicolon_for` says ``omit``;
    * *prev_rule*, the rule of the member this ``;`` follows, is in
      :data:`_SELF_TERMINATING` -- so the grammar already ended that member
      and this ``;`` is the body's empty-item alternative;
    * that member really did end where its rule says it ends -- see below;
    * :func:`_drop_terminal` finds nothing attached to the token.

    Anything else -- an unrecognised rule, a member built by error recovery,
    a construct with no style answer -- merges it onto the line above, which
    is what every ``pssfmt`` before this option did.

    Why the rule name is not enough
    -------------------------------
    A rule name describes the grammar; error recovery produces nodes that do
    not honour it. ``pathological/unclosed_string.pss`` is the corpus's proof:

        component c {
            string s = "this string is never closed;
            int x = 1;
        }

    The unterminated literal runs to the end of its line, so the parser builds
    a ``component_data_declaration`` that stops at the string -- with **no**
    terminator -- and the next line's ``;`` becomes its sibling. That name is
    in :data:`_SELF_TERMINATING`, correctly, because every alternative of the
    real rule ends in ``;``. This one did not. Dropping that semicolon deletes
    a token from a file whose author is mid-edit, which is the single thing
    the tier is most careful never to do.

    So the member is asked what its last token actually *was*. A rule that
    self-terminates ends in ``;`` or ``}``; a truncated one does not, and the
    two conditions together admit only members where the grammar and the text
    agree.
    """
    if (construct is not None
            and prev_rule in _SELF_TERMINATING
            and _ends_with_a_terminator(ctx, spans[-1])
            and ctx.style.optional_semicolon_for(construct)
            is SemicolonMode.OMIT
            and _drop_terminal(ctx, members, spans, at)):
        return True
    return _merge_terminal(ctx, members, spans, at)


def _ends_with_a_terminator(ctx: Any, span: Tuple[int, int]) -> bool:
    """Whether the member at *span* ends in a ``;`` or a ``}`` of its own."""
    last = ctx.trivia.of(ctx.trivia.code_indices[span[1]]).token
    return last.text in (";", "}")


def _permits_a_null_item(node: Any, inner: Any) -> bool:
    """Whether the grammar allows a bare ``;`` beside this member.

    Asked of the wrapper chain the parser actually built -- *node* is the body
    item as it came out of the tree, *inner* is :func:`_effective`'s answer,
    and the rules between them are the ones that decide what a sibling of this
    member may be. A ``struct`` in a package arrives as
    ``package_body_item_ann`` -> ``package_body_item`` -> ``struct_declaration``
    and ``package_body_item`` is the one carrying the empty-item alternative;
    an ``enum``'s items arrive as bare ``enum_item`` nodes and none of them
    carries it, which is why ``require`` never writes ``{A;, B}``.

    Reading the tree rather than mapping :class:`~pssfmt.style.Construct` to a
    grammar rule by hand is the safer direction of a question whose wrong
    answer is a syntax error: a body kind nobody has written down yet is
    absent from the set and gets no semicolon, where a hand-written map would
    have to be *remembered* for each one.
    """
    while True:
        if node.is_rule and node.rule_name in _PERMITS_EMPTY_ITEM:
            return True
        if node is inner or not node.is_rule \
                or node.rule_name not in _PASSTHROUGH:
            return False
        rules = [c for c in node.children if c.is_rule]
        if len(rules) != 1:
            return False
        node = rules[0]


def _wants_a_terminator(ctx: Any, node: Any, inner: Any,
                        span: Tuple[int, int],
                        construct: Optional[Construct]) -> bool:
    """Whether ``require`` should write a ``;`` after this member.

    The mirror of :func:`_semicolon_member`, and deliberately *not* its exact
    inverse. Five conditions:

    * the parser understood the whole file -- see below;
    * the style says ``require`` for this construct;
    * the member's rule is in :data:`_SELF_TERMINATING`, so a ``;`` after it
      would be decoration rather than a second terminator;
    * the member ends in a ``}`` -- **not** merely in a terminator. This is
      where the asymmetry with ``omit`` lives, and it is the whole difference
      between a house style and a mess: ``omit`` turns ``int x;;`` into
      ``int x;``, but ``require`` must not turn ``int x;`` into ``int x;;``.
      What the option is *for* is the brace, ``struct s { … };``, so the brace
      is what it asks for;
    * the grammar admits an empty item beside this member --
      :func:`_permits_a_null_item`.

    The ``}`` test carries a local error-recovery guard too, for the same
    reason it does on the deletion side: a member the parser cut short does
    not end in the brace its rule promised, and a truncated fragment is the
    last thing to append a token to.

    Why a clean parse is required and deletion needs no such thing
    -------------------------------------------------------------
    Deleting is local -- the token goes, and every other token is read exactly
    as before. Inserting is not: a new token changes how the text after it is
    lexed and parsed, and in a file the parser did not understand there is
    nothing here that knows what that text *is*.

    ``pathological/lone_quote.pss`` is the corpus's proof, and it is not a
    case anyone would have guessed:

        component c {
            int x = 'ff;
            int y = 4';
            int z = ';
        }

    Three unbalanced quotes, two syntax errors, and a ``component_declaration``
    that nonetheless ends in an honest ``}``. Every local test above passes.
    Writing ``};`` at the end of that file makes it parse *worse* -- three
    errors, not two -- because the trailing garbage lexes differently with one
    more character after it. No per-member condition can see that; the file
    can. So the whole file is the unit for insertion, and only for insertion.
    """
    return (ctx.parsed_cleanly
            and construct is not None
            and ctx.style.optional_semicolon_for(construct)
            is SemicolonMode.REQUIRE
            and inner.is_rule
            and not getattr(inner, "is_error", False)
            and inner.rule_name in _SELF_TERMINATING
            and ctx.trivia.of(ctx.trivia.code_indices[span[1]]).token.text == "}"
            and _permits_a_null_item(node, inner))


def _already_terminated(ctx: Any, children: Any, index: int,
                        span: Tuple[int, int]) -> bool:
    """Whether the member at *index* is already followed by its optional ``;``.

    One member of lookahead, and it is what makes ``require`` idempotent:
    without it the second pass would add a semicolon to a member that gained
    one on the first and produce ``};;``. The same question
    :func:`_is_trailing_semicolon` answers, asked one child early.
    """
    for later in children[index + 1:]:
        if not later.is_rule:
            return False
        nxt = code_span(ctx.trivia, later)
        if nxt is None:
            continue
        return _is_trailing_semicolon(ctx, nxt, span)
    return False


def _collect(ctx: Any, children: Any, separator: Optional[str] = None,
             construct: Optional[Construct] = None) \
        -> Optional[Tuple[List[_Member], List[Tuple[int, int]]]]:
    """Members and their spans, or ``None`` if this body should not be touched.

    This is the one place a body's members are gathered -- declarations,
    constraints and activities all reach it through :func:`_block` -- which is
    what lets ``P3-9``'s escape hatches be a check here rather than a check in
    every rule. Below member level nothing is needed either: a directive
    inside a construct is a comment between two tokens, and
    :func:`~pssfmt.rules.tokens.emit_span` already declines any span holding
    one. So the hatch is honoured on both sides of the member boundary, by two
    mechanisms that were each written for their own reasons.

    Consecutive members inside **one** hatch are reproduced as a single block.
    That is not an optimisation: the blank lines *between* two members are
    decided by :func:`_stack` and clamped to ``max_blank_lines``, so members
    frozen one at a time would still have the spacing between them rewritten.
    Coalescing puts those gaps inside the copied span, where nothing composes
    them. The gaps at the region's outer edges are still the formatter's, and
    correctly so -- a hatch freezes what it encloses, not its surroundings.
    """
    members: List[_Member] = []
    spans: List[Tuple[int, int]] = []
    #: Identity of the hatch the previous member belonged to, if any.
    hatch: Any = None
    #: Rule name of the member a trailing ``;`` would attach to, or ``None``
    #: when there is nothing to ask -- no member yet, a member the formatter
    #: was switched off over, or one error recovery assembled. All three mean
    #: "keep the semicolon", which is the answer that changes nothing.
    prev_rule: Optional[str] = None
    # Materialised because ``require`` needs one child of lookahead -- see
    # ``_already_terminated`` -- and *children* arrives as a slice of the
    # tree in one caller and a comprehension in the other.
    children = list(children)
    for index, child in enumerate(children):
        if not child.is_rule:
            # A terminal at member level. *separator* names the one the
            # grammar puts between members of this body and the caller
            # therefore expects -- an ``enum``'s ``,`` (``P3-12``) -- and it
            # joins the member before it. Anything else is a separator nobody
            # declared or error recovery; either way it is not a member, and
            # guessing at its placement is how a token goes missing.
            if (separator is not None and child.token is not None
                    and child.token.type_name == separator and spans):
                at = ctx.trivia.code_indices.index(child.token_index)
                if not _merge_terminal(ctx, members, spans, at):
                    return None
                continue
            return None
        span = code_span(ctx.trivia, child)
        if span is None:
            continue
        # Asked before the semicolon merge below, so that a ``;`` inside a
        # hatch is copied along with what it terminates rather than being
        # re-composed as ``text(";")`` against the preceding block.
        covering = ctx.hatches.region_of(*span)
        if covering is not None:
            start = span[0]
            if covering == hatch:
                start = spans.pop()[0]
                members.pop()
            built = _hatched(ctx, start, span[1])
            if built is None:
                return None
            members.append(built)
            spans.append((start, span[1]))
            hatch = covering
            prev_rule = None
            continue
        # ``hatch`` is deliberately not cleared here. A range is a contiguous
        # run of code positions, so an unhatched member can never sit between
        # two members of the *same* range -- there is nothing for a stale
        # identity to match against. Clearing it would be a guard no test
        # could distinguish from its absence.
        if _is_trailing_semicolon(ctx, span, spans[-1] if spans else None):
            if not _semicolon_member(ctx, members, spans, span[0],
                                     construct, prev_rule):
                return None
            continue
        # The *grammar* shape of the member, not whether a rule laid it out:
        # a member this tier reproduces verbatim still ends where the grammar
        # says it ends. An error node is the exception -- its name describes
        # what the parser was attempting, not what it consumed.
        inner = _effective(child)
        built = _member(ctx, child,
                        _wants_a_terminator(ctx, child, inner, span, construct)
                        and not _already_terminated(ctx, children, index, span))
        if built is None:
            return None
        members.append(built)
        spans.append(span)
        prev_rule = (inner.rule_name if inner.is_rule
                     and not getattr(inner, "is_error", False) else None)
    return members, spans


def _members_of(ctx: Any, node: Any, open_at: int, close_at: int,
                separator: Optional[str] = None,
                construct: Optional[Construct] = None) \
        -> Optional[List[_Member]]:
    """The body's members, or ``None`` if this body should not be touched."""
    code = ctx.trivia.code_indices
    open_pos = code.index(node.children[open_at].token_index)
    close_pos = code.index(node.children[close_at].token_index)

    collected = _collect(ctx, node.children[open_at + 1:close_at], separator,
                         construct)
    if collected is None:
        return None
    members, spans = collected

    if not _tiles(spans, open_pos + 1, close_pos - 1):
        return None

    dangling = _dangling(ctx, node.children[close_at].token_index)
    if dangling is _BAIL:
        return None
    if dangling is not None:
        members.append(dangling)
    return members


def sites_before(ctx: Any, node: Any, last: int) -> Any:
    """Tree-decided sites for every rule child of *node* that starts before
    *last*, or ``None`` to decline the header.

    The general contract first, since ``P3-11a`` gave this a second caller:
    a header is the run of tokens from a construct's first to the token before
    its body, it can hold anything the grammar puts there, and the ambiguous
    ones among those have no answer at the token-type granularity a vocabulary
    works in. So each child is asked, one at a time, and a child that declines
    declines the header.

    The rest of this docstring is the *declaration* header, which is where the
    strictness came from and is still the sharpest case of why it is needed.

    Every ``<`` in a declaration header belongs to one of two constructs, and
    they are *not* the same construct written twice:

    ``packed_s<bit, 32>``
        A ``template_param_value_list`` -- a use. 137 in the corpus across 34
        files, and the most unanimous thing measured so far: tight inside at
        137/137 on both ends. :mod:`pssfmt.rules.exprs` knows this one.

    ``struct base_s <struct TRAIT : addr_trait_s = empty_addr_trait_s>``
        A ``template_param_decl_list`` -- a declaration. 16 instances in 5
        files, and the corpus does **not** agree about them: 7/16 tight after
        the ``<``, because 5 of the other 9 put the parameter on its own line.
        A parameter also carries a ``:`` that is a *bound* rather than
        inheritance, and a ``=`` that is a default, so it is a fifth colon
        reading in the one vocabulary whose colon closure is load-bearing.

    So this returns sites only for the first, and the second declines --
    without anything here saying so. ``sites_for`` assigns nothing to a decl
    list's angles; ``TOK_LT`` and ``TOK_GT`` are in
    :data:`~pssfmt.rules.exprs.TREE_DECIDED`, so *its own* completeness check
    refuses the subtree; and refusing one child refuses the header. An absent
    answer is the decline, which is one fewer thing that can rot.

    That is also why there is no second completeness check over the header
    span here. There was one, and mutation testing showed it and the refusal
    below each kept the other alive: every angle bracket in a declaration
    header belongs to some child rule, so ``sites_for`` has already asked the
    question and this would only be asking it again one layer up. Two guards
    where the tests can only see one is how a real guard gets deleted later
    without anything failing (``P3-4``'s ``>>`` check, ``P3-6``'s ``_effective``
    return, and now this).

    The children are asked one at a time rather than asking *node*, because
    *node* is the whole declaration: its span runs to the closing brace, so
    asking it would let a single declined construct anywhere in the body --
    ``a**2`` is one, and the corpus has it in two files -- refuse the header
    of the thing containing it. It would be quadratic as well. That is also
    what ``P3-11a`` needs and could not have got from a whole-node walk: a
    function body is 300 statements the rule set has no vocabulary for, and
    every one of them would have refused the prototype above it.

    *last* is the ``{`` position, and the bound below is ``>=`` rather than
    ``>`` for a reason worth stating, because ``>`` is what was written first
    and it defeated the paragraph above. Where the braces belong to a *child*
    node rather than to *node* itself -- a ``constraint``, whose block is its
    own rule, and ``repeat (4) { … }`` for the same reason -- that child's
    span begins exactly *at* the brace. So ``>`` let it through, ``sites_for``
    was handed the entire body, and one unclassifiable item anywhere inside
    refused the header: ``constraint   defaults_c {`` kept the author's
    spacing because a ``default`` item four lines below could not be
    classified. Found by ``T-6``, which is the first test to look at a whole
    formatted file rather than at the construct it was checking.
    """
    trivia = ctx.trivia
    sites: dict = {}
    for child in node.children:
        if not child.is_rule:
            continue
        span = code_span(trivia, child)
        if span is None or span[0] >= last:
            continue
        found = sites_for(ctx, child)
        if found is None:
            return None
        sites.update(found)
    return sites


def _header(ctx: Any, node: Any, open_child: Any,
            vocabulary: Any = None, sites: Any = None,
            separate: Any = None) -> Layout:
    """Everything up to and including ``{``.

    Written out token by token when the header uses *vocabulary*, so that
    ``struct  s:base_s`` normalises to ``struct s : base_s``. Anything outside
    that vocabulary -- a template *parameter* list, or a comment sitting
    mid-header -- is reproduced as the author wrote it, with only the gap
    before ``{`` normalised (``Site.BRACE_OPEN``). That was the whole of this
    function before ``P3-2b`` and it remains the fallback, so a header the
    emitter declines is no worse off than it was.

    A template *argument* list is no longer in that set: ``P3-7`` writes
    ``packed_s<bit, 32>`` out, with the angle sites coming from the tree via
    :func:`sites_before`. Declining now has a third trigger alongside the
    two above -- an angle bracket that walk could not account for.

    *vocabulary* and *sites* exist for ``P3-6``. An activity block's header is
    a keyword and a brace -- ``parallel {`` -- and a ``repeat (4) {`` header
    additionally holds an expression, whose ``(`` is a *control* paren rather
    than the call or grouping paren an expression's own parens would be. Both
    are decided the way every header is decided here; they simply cannot be
    decided by the *declaration* vocabulary, which is closed and whose
    closure is load-bearing (see :data:`_HEADER_VOCABULARY` on ``TOK_COLON``).
    Passing the vocabulary in keeps that closure per-caller instead of
    widening one shared set until nothing in it is unambiguous any more.

    A caller that passes a *vocabulary* passes *sites* too, and passing
    ``None`` there is a **decline** rather than "there are none" -- ``{}`` is
    how a caller says a header holds nothing the tree has to classify. The
    two were one value until ``P3-11a`` needed to tell them apart, which is
    the distinction :data:`_BAIL` exists for one level up: a function whose
    prototype this module must not touch still has a body it should lay out,
    so declining the header cannot mean declining the construct.

    *separate* is the caller's extra floor, passed straight to
    :func:`~pssfmt.rules.tokens.emit_span`. No declaration header needs one --
    a header ends at ``{``, whose ``before`` is 1 -- and a *prototype* header
    needs one on almost every line it has: ``bit[32] nbytes`` is a type
    meeting its declarator, which is the seam
    :func:`~pssfmt.rules.stmts.after_a_width_bracket` was written for in a
    field declaration.
    """
    trivia = ctx.trivia
    span = code_span(trivia, node)
    brace_pos = trivia.code_indices.index(open_child.token_index)
    if span is None or brace_pos <= span[0]:
        return text("{")
    first = span[0]

    if vocabulary is None:
        vocabulary = _HEADER_VOCABULARY
        sites = sites_before(ctx, node, brace_pos)

    emitted = None if sites is None else emit_span(
        ctx, first, brace_pos, vocabulary, separate=separate, sites_at=sites)
    if emitted is not None:
        return emitted

    origin = trivia.of(trivia.code_indices[first]).token.col

    brace_lead = trivia.of(open_child.token_index).raw_leading
    if not _only_whitespace(brace_lead):
        return reindented_layout(
            span_tokens(trivia, first, brace_pos, leading=False),
            span_text(trivia, first, brace_pos, leading=False),
            origin)

    head = span_text(trivia, first, brace_pos - 1, leading=False)
    tokens = span_tokens(trivia, first, brace_pos - 1, leading=False)
    # ``emit_span`` declined this header, so its floor did not run -- but the
    # brace is still being written against the header's last token. Today's
    # ``BRACE_OPEN.before`` is 1, which hides this; configure it to 0 and
    # ``component /* c */ \esc {`` becomes ``\esc{``, one identifier, and the
    # block structure of the file is gone (``P3-10``).
    # Argument order is unobservable at *this* site specifically: no token
    # that can end a header is asymmetric against ``{`` under
    # ``must_separate``, since ``{`` is neither a word character nor half of
    # any longer lexeme. Only the escaped-identifier branch can fire here, and
    # that one is symmetric. Source order anyway -- see ``floor_gap``.
    last = trivia.of(trivia.code_indices[brace_pos - 1]).token
    brace = trivia.of(open_child.token_index).token
    gap = " " * floor_gap(ctx.style.gap(None, Site.BRACE_OPEN), last, brace)
    return concat([reindented_layout(tokens, head, origin), text(gap + "{")])


def _block(ctx: Any, node: Any, construct: Construct,
           body: Any = None, vocabulary: Any = None, sites: Any = None,
           separate: Any = None, separator: Optional[str] = None) -> Layout:
    """A braced declaration: header, indented members, closing brace.

    *body* is the node holding the braces, where that is not *node* itself.
    A constraint is the case that needs it: ``constraint_declaration`` is
    ``'constraint' identifier constraint_block``, so the name is one node's
    and the braces are its child's, while the header still runs from the
    keyword to the ``{`` across both. ``P3-6``'s ``repeat (4) { … }`` is the
    same shape for the same reason -- the braces belong to the sequence block
    the ``repeat`` wraps. Everything else here works in *code positions*
    already, so this is the only seam that had to open.

    *vocabulary*, *sites* and *separate* are passed through to
    :func:`_header`, and only the header uses them: a body is members, and a
    member is built by its own rule or reproduced.
    """
    body = node if body is None else body
    braces = _braces(body)
    if braces is None:
        return _reproduce(ctx, node)
    open_at, close_at = braces

    members = _members_of(ctx, body, open_at, close_at, separator,
                          construct)
    if members is None:
        return _reproduce(ctx, node)

    header = _header(ctx, node, body.children[open_at], vocabulary, sites,
                     separate)
    if not members:
        return concat([header, text("}")])

    close_token = ctx.trivia.of(body.children[close_at].token_index).token
    blanks = _blank_lines_before(ctx, close_token)

    return concat([
        header,
        indent(_stack(ctx, members, lead_break=True),
               ctx.style.indent_for(construct)),
        hardline(min(blanks, ctx.style.max_blank_lines)),
        text("}"),
    ])


#: ``enum spi_mode_e : bit[2] { SPI_MODE_0 = 0, … }`` (``P3-12``).
#:
#: A separate vocabulary from :data:`_HEADER_VOCABULARY` and not an addition
#: to it, because the closure that makes that one's ``TOK_COLON`` unambiguous
#: is "no span of these tokens can contain a ``[``" -- and an enum's base type
#: is ``bit[2]``. The colon here is a *fifth* reading of the character
#: ``docs/style.rst`` splits four ways, and it takes
#: ``Site.COLON_INHERITANCE`` because that is what it is: the type the enum is
#: based on, spaced on both sides in all 4 corpus instances, against a rule
#: measured at 355/358.
#:
#: The bracket is safe for the same reason it is safe in a prototype: it
#: belongs to an ``integer_type``, so its site comes from the tree and no
#: bit-slice colon can reach here -- ``integer_type``'s width is a
#: ``constant_expression``, and no expression contains a ``:``.
_ENUM_VOCABULARY = {
    "TOK_ENUM": WORD,
    "ID": WORD,
    "ESCAPED_ID": WORD,
    "TOK_COLON": Site.COLON_INHERITANCE,
    "TOK_LCBRACE": Site.BRACE_OPEN,
    "TOK_RCBRACE": Site.BRACE_CLOSE,
    "TOK_COMMA": Site.COMMA,
    "TOK_SINGLE_EQ": Site.ASSIGN,
    # The scalar types an enum may be based on, and the literals an item may
    # be given. The whole corpus inventory, and nothing beyond it.
    "TOK_BIT": WORD,
    "TOK_INT": WORD,
    "DEC_LITERAL": WORD,
    "HEX_LITERAL": WORD,
    "OCT_LITERAL": WORD,
    "BIN_LITERAL": WORD,
    "TOK_LSBRACE": WORD,
    "TOK_RSBRACE": WORD,
}


def _enum_items(node: Any) -> List[Any]:
    return [c for c in node.children
            if c.is_rule and c.rule_name == "enum_item"]


def _has_values(node: Any) -> bool:
    """Whether any item is written ``NAME = value``."""
    return any(any(not k.is_rule and k.token is not None
                   and k.token.type_name == "TOK_SINGLE_EQ"
                   for k in item.children)
               for item in _enum_items(node))


def _holds_a_comment(ctx: Any, first: int, last: int) -> bool:
    code = ctx.trivia.code_indices
    for pos in range(first, last + 1):
        entry = ctx.trivia.of(code[pos])
        if any(t.is_comment for t in entry.raw_leading) or \
                any(t.is_comment for t in entry.raw_trailing):
            return True
    return False


def _enum_column_stop(ctx: Any, node: Any) -> tuple:
    """Where a hand-aligned enum puts its column::

        DMA_MEM_TO_MEM  = 0,
        DMA_MEM_TO_PERI = 1,
        DMA_PERI_TO_MEM = 2

    The gap before ``=``, which is the same seam ``stmts._column_stops`` marks
    for a field with an initialiser and ``procedural._assign_stop`` marks for a
    run of assignments. **3 of the corpus's 11 valued items are padded, and
    they are two complete tables in two files** -- thinner evidence than the
    assignments' 22 of 93, and the same shape, so it gets the same answer:
    mark the seam and let ``infer`` decide. A block whose names happen to be
    equal width shows no padding, is not read as a table, and comes out at one
    space either way.
    """
    code = ctx.trivia.code_indices
    span = code_span(ctx.trivia, node)
    if span is None:
        return ()
    for pos in range(span[0], span[1] + 1):
        if ctx.trivia.of(code[pos]).token.type_name == "TOK_SINGLE_EQ":
            return (pos,)
    return ()


def _enum_item(ctx: Any, node: Any) -> Layout:
    """``SPI_MODE_0 = 0`` -- a name, optionally with a value."""
    span = code_span(ctx.trivia, node)
    if span is None:
        return _reproduce(ctx, node)
    emitted = emit_span(ctx, span[0], span[1], _ENUM_VOCABULARY,
                        mark_at=_enum_column_stop(ctx, node))
    return emitted if emitted is not None else _reproduce(ctx, node)


def _enum(ctx: Any, node: Any) -> Layout:
    """``enum e { A, B }`` and ``enum e : bit[2] { A = 0, B = 1 }``.

    The first body in this module that is a **list**: its members are
    separated by a ``,`` the *parent* owns, where every other body's members
    terminate themselves. That is why :func:`_collect` grew a *separator* --
    a terminal at member level was previously always a refusal, which is why
    an enum declined for ten items and never for a reason anybody chose.

    One line or one item per line, and the corpus decides it unanimously
    without reference to width:

    ==================================== ===== ==============
    shape                                count written
    ==================================== ===== ==============
    items have ``= value``                 4/4 one per line
    bare names, no interior comment        9/9 one line
    bare names + interior comment          1/1 one per line
    ==================================== ===== ==============

    **Not a fit decision**, and that is the finding. The ten inline enums end
    at columns 33 to 60, and the five broken ones join to 69, 75, 92, 95 and
    237 -- so a ``Group`` at ``print_width`` would collapse two of them,
    including this table::

        enum dma_addr_mode_e : bit[1] {
            DMA_ADDR_FIXED = 0,
            DMA_ADDR_INCR  = 1
        }

    Width gets 13 of 15 right; "does an item have a value" gets 15 of 15. An
    enum of bare names is a *list* and an enum of assignments is a *table*,
    and authors write them differently for that reason rather than because of
    where column 80 falls.

    A comment forces the broken form too, and needs no rule of its own: the
    inline form is one :func:`~pssfmt.rules.tokens.emit_span` call, and that
    function has refused a span holding a comment since ``P3-2b``. The one
    corpus enum in this position is the one the table above counts.
    """
    braces = _braces(node)
    if braces is None:
        return _reproduce(ctx, node)
    open_at, close_at = braces
    span = code_span(ctx.trivia, node)
    if span is None:
        return _reproduce(ctx, node)

    if not _enum_items(node):
        # ``enum e {}``, not ``enum e { }``. The corpus has none, so this is
        # the house answer rather than a measured one -- and the house answer
        # is already written down: every empty body in this module stays flat
        # and tight, because there is nothing to put a space around. Reached
        # through ``_block``, which says so in one place for all of them.
        return _block(ctx, node, Construct.ENUM_BODY,
                      vocabulary=_ENUM_VOCABULARY,
                      sites=sites_before(ctx, node,
                                         _brace_pos(ctx, node, open_at)))
    if not _has_values(node):
        emitted = emit_span(ctx, span[0], span[1], _ENUM_VOCABULARY)
        if emitted is not None:
            return emitted
    return _block(ctx, node, Construct.ENUM_BODY,
                  vocabulary=_ENUM_VOCABULARY,
                  sites=sites_before(ctx, node, _brace_pos(ctx, node, open_at)),
                  separator="TOK_COMMA")


def _brace_pos(ctx: Any, node: Any, open_at: int) -> int:
    return ctx.trivia.code_indices.index(node.children[open_at].token_index)


def _struct_construct(node: Any) -> Construct:
    """Which of the five ``struct_kind`` spellings this declaration uses."""
    for child in node.children:
        if child.is_rule and child.rule_name == "struct_kind":
            for term in _terminals(child):
                mapped = _OBJECT_KINDS.get(term.token.type_name)
                if mapped is not None:
                    return mapped
    return Construct.STRUCT_BODY


def _terminals(node: Any):
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur.is_rule:
            stack.extend(reversed(cur.children))
        elif cur.token is not None:
            yield cur


def register(registry) -> None:
    """Binds this module's builders.

    A function rather than decorators evaluated at import time, so a test can
    register the tier into an isolated registry without the shipped one being
    involved -- and so importing this module has no global effect.
    """

    @registry.rule("compilation_unit")
    def _compilation_unit(ctx, node):
        """The file itself: a body with no braces and no indentation."""
        collected = _collect(ctx, [c for c in node.children if c.is_rule],
                             construct=Construct.PACKAGE_BODY)
        if collected is None:
            return ctx.verbatim(node)
        members, spans = collected
        if not members or not _tiles(spans, 0, len(ctx.trivia.code_indices) - 1):
            # Top level, so `ctx.verbatim` is right here: nothing above this
            # node emitted the file's leading trivia, and nothing else will.
            return ctx.verbatim(node)
        return _stack(ctx, members, lead_break=False)

    @registry.rule("import_stmt")
    def _import(ctx, node):
        """``import pkg::*;`` -- the first statement written out as tokens.

        Small enough to be uncontroversial and uniform enough to be safe: one
        shape, 147 times, no comments and no line breaks anywhere in the
        corpus. It is here to make the token path carry a real construct
        before ``P3-3`` points it at statements that vary.
        """
        span = code_span(ctx.trivia, node)
        if span is None:
            return _reproduce(ctx, node)
        emitted = emit_span(ctx, span[0], span[1], _IMPORT_VOCABULARY)
        return emitted if emitted is not None else _reproduce(ctx, node)

    @registry.rule("package_declaration")
    def _package(ctx, node):
        return _block(ctx, node, Construct.PACKAGE_BODY)

    @registry.rule("component_declaration")
    def _component(ctx, node):
        return _block(ctx, node, Construct.COMPONENT_BODY)

    @registry.rule("action_declaration")
    def _action(ctx, node):
        return _block(ctx, node, Construct.ACTION_BODY)

    @registry.rule("struct_declaration")
    def _struct(ctx, node):
        return _block(ctx, node, _struct_construct(node))

    @registry.rule("extend_stmt")
    def _extend(ctx, node):
        """``extend component spi_c { … }`` -- a body like any other.

        Added in ``P3-6`` rather than in ``P3-2`` with the other declaration
        bodies, where it belonged: it was simply missed, and ``PLAN.md`` has
        no item for it. What made the omission visible is that ``extend``
        gates far more than itself. 31 of the corpus's 92 files open one, and
        a rule cannot lay out a node whose parent has none -- so every action,
        field, constraint and activity inside those 31 files was being
        reproduced no matter how many rules had been written for it. Before
        this, *zero* of the corpus's ten activity binds were reachable.

        One ``Construct`` for all five spellings, unlike ``struct``: the kind
        keyword names the type being extended rather than a different kind of
        body, and all 32 corpus instances indent identically.
        """
        return _block(ctx, node, Construct.EXTEND_BODY)

    registry.register("enum_declaration", _enum)
    registry.register("enum_item", _enum_item)


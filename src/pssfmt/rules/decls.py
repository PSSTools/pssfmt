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

from ..layout import Layout, concat, indent, text
from ..style import Construct, Site
from .emit import (
    code_span,
    hardline,
    reindented_layout,
    span_text,
    span_tokens,
)

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
)


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

    Emitted with the original gap before it. That gap is what ``infer``
    alignment would preserve for a hand-aligned block and what it would leave
    alone for a ragged one, so reproducing it is the right answer under both
    -- until the alignment pass runs here, which is ``P2-8``'s work.
    """
    run = ctx.trivia.of(token_index).raw_trailing
    if not any(tok.is_comment for tok in run):
        return None if _only_whitespace(run) else _BAIL
    body = "".join(tok.text for tok in run).rstrip()
    return text(body) if "\n" not in body else _BAIL


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


def _member(ctx: Any, node: Any) -> Optional[_Member]:
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


def _is_trailing_semicolon(ctx: Any,
                           span: Tuple[int, int],
                           prev: Optional[Tuple[int, int]]) -> bool:
    """Whether *span* is a lone ``;`` closing the member before it.

    PSS permits a semicolon after a declaration -- ``enum e {A, B};`` -- and
    the grammar makes it a sibling of the enum rather than part of it. Treated
    as a member in its own right it lands on its own line, which is how
    ``std_pkg.pss`` came back with four bare semicolons in it. It belongs to
    the declaration it terminates, so it is merged into it.

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


def _collect(ctx: Any, children: Any) -> Optional[Tuple[List[_Member],
                                                        List[Tuple[int, int]]]]:
    """Members and their spans, or ``None`` if this body should not be touched."""
    members: List[_Member] = []
    spans: List[Tuple[int, int]] = []
    for child in children:
        if not child.is_rule:
            # A stray terminal at member level: a separator the grammar puts
            # here, or error recovery. Either way it is not a member, and
            # guessing at its placement is how a token goes missing.
            return None
        span = code_span(ctx.trivia, child)
        if span is None:
            continue
        if _is_trailing_semicolon(ctx, span, spans[-1] if spans else None):
            tail = _trailing(ctx, ctx.trivia.code_indices[span[1]])
            if tail is _BAIL:
                return None
            parts = [members[-1].layout, text(";")]
            if tail is not None:
                parts.append(tail)
            members[-1] = _Member(members[-1].blanks_before, concat(parts))
            spans[-1] = (spans[-1][0], span[1])
            continue
        built = _member(ctx, child)
        if built is None:
            return None
        members.append(built)
        spans.append(span)
    return members, spans


def _members_of(ctx: Any, node: Any, open_at: int, close_at: int) \
        -> Optional[List[_Member]]:
    """The body's members, or ``None`` if this body should not be touched."""
    code = ctx.trivia.code_indices
    open_pos = code.index(node.children[open_at].token_index)
    close_pos = code.index(node.children[close_at].token_index)

    collected = _collect(ctx, node.children[open_at + 1:close_at])
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


def _header(ctx: Any, node: Any, open_child: Any) -> Layout:
    """Everything up to and including ``{``.

    Reproduced as written, except the whitespace immediately before the brace,
    which is a style decision (``Site.BRACE_OPEN``). If a comment sits in that
    gap -- ``component c /* why */ {`` -- the whole run is reproduced instead:
    normalising around a comment means deciding where the comment goes, and
    this module has no opinion there worth acting on.
    """
    trivia = ctx.trivia
    span = code_span(trivia, node)
    brace_pos = trivia.code_indices.index(open_child.token_index)
    if span is None or brace_pos <= span[0]:
        return text("{")
    first = span[0]
    origin = trivia.of(trivia.code_indices[first]).token.col

    brace_lead = trivia.of(open_child.token_index).raw_leading
    if not _only_whitespace(brace_lead):
        return reindented_layout(
            span_tokens(trivia, first, brace_pos, leading=False),
            span_text(trivia, first, brace_pos, leading=False),
            origin)

    head = span_text(trivia, first, brace_pos - 1, leading=False)
    tokens = span_tokens(trivia, first, brace_pos - 1, leading=False)
    gap = " " * ctx.style.gap(None, Site.BRACE_OPEN)
    return concat([reindented_layout(tokens, head, origin), text(gap + "{")])


def _block(ctx: Any, node: Any, construct: Construct) -> Layout:
    """A braced declaration: header, indented members, closing brace."""
    braces = _braces(node)
    if braces is None:
        return _reproduce(ctx, node)
    open_at, close_at = braces

    members = _members_of(ctx, node, open_at, close_at)
    if members is None:
        return _reproduce(ctx, node)

    header = _header(ctx, node, node.children[open_at])
    if not members:
        return concat([header, text("}")])

    close_token = ctx.trivia.of(node.children[close_at].token_index).token
    blanks = _blank_lines_before(ctx, close_token)

    return concat([
        header,
        indent(_stack(ctx, members, lead_break=True),
               ctx.style.indent_for(construct)),
        hardline(min(blanks, ctx.style.max_blank_lines)),
        text("}"),
    ])


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
        collected = _collect(ctx, [c for c in node.children if c.is_rule])
        if collected is None:
            return ctx.verbatim(node)
        members, spans = collected
        if not members or not _tiles(spans, 0, len(ctx.trivia.code_indices) - 1):
            # Top level, so `ctx.verbatim` is right here: nothing above this
            # node emitted the file's leading trivia, and nothing else will.
            return ctx.verbatim(node)
        return _stack(ctx, members, lead_break=False)

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


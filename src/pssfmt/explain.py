"""``P4-5`` -- ``--explain``: why the output looks like that.

``formatter.md`` section 8.6 gives the reason for building this early, and it
is not a feature argument: clang-format's *lack* of it is the number one
debugging complaint, verible ships ``--show_token_partition_tree``, and the
information involved is free at the moment a decision is made and
unrecoverable a microsecond later. By the time there is output text, why a
line ended where it did has been thrown away.

What the question turned out to be
----------------------------------
Section 8.6 phrases it as *"which rule caused this break?"*, and the obvious
reading is a fit decision: some group did not fit, so the engine broke it.
Measured before writing the report, across the corpus:

===========  =====================================  ==============
print_width  files with any group decision (of 92)   groups broken
===========  =====================================  ==============
40           11                                      24
60           11                                       5
80           11                                       1
120          11                                       0
===========  =====================================  ==============

**One broken group in 92 files at the default width.** Not a defect -- it is
what this formatter is. Breaks here are overwhelmingly *unconditional*: a rule
emits a :class:`~pssfmt.layout.ir.HardLine` between two members because
members go on separate lines, and there is nothing for the engine to measure.
Fit decisions arise only inside expressions, constraints and activities, which
is the 11 files.

So a report built only on fit decisions would be empty for 81 of 92 files.
The question a user actually arrives with -- *"which rule produced this
line?"* -- is answerable for all 92, and it is the same question with the
architecture's own answer substituted: usually the rule did, directly. Both
are reported, and the emptiness of the second section is itself informative.

How the three answers are obtained
----------------------------------
1. **Which rule laid this out?** :class:`Recorder` is a
   :class:`~pssfmt.rules.RuleRegistry` that writes down what it hands out, so
   the layout a builder returns is tagged with the builder's name. Nothing in
   :mod:`pssfmt.rules` changes, nothing in the layout package learns what a
   rule is, and ``build_tree`` already takes a registry -- the instrumented
   run goes down the same code path as a real one, because an explanation
   produced by a parallel implementation would explain that implementation.
2. **Where did each tagged node produce output?** The engine appends a
   :class:`~pssfmt.layout.engine.Visit` for every watched node, which this
   module turns into line spans.
3. **What is the document?** The Layout IR, printed as a tree. ``Built.doc``
   has been kept for exactly this since ``P3-1``.

Attribution is by nearest tagged ancestor
-----------------------------------------
A builder is tagged on the node it *returns*, so groups it creates inside
helper functions attribute to the enclosing tagged node. That is the right
answer -- ``expression`` is more useful than the name of a private helper --
and two consequences are worth stating rather than discovering:

* A shared subtree has more than one parent and this keeps whichever was
  walked last. Rules build fresh nodes, so it does not arise today; if it ever
  does, the symptom is a plausible *wrong* rule name in a report, which is the
  kind of thing that gets believed.
* A construct with no builder is laid out verbatim and has no rule to name.
  It is reported as ``(verbatim)`` rather than attributed upward, because
  "this was copied" is the answer to the question and not a gap in it -- and
  for a formatter that is incomplete on purpose it is the single most useful
  thing the report says. That required naming ``Verbatim`` nodes explicitly:
  the upward walk always finds *some* tag, so until it did, the corpus's 40
  copied regions were all reported as having been laid out by whichever rule
  happened to enclose them, and ``(verbatim)`` appeared zero times while the
  documentation called it the signal to look for.

What this deliberately does not do
----------------------------------
It does not run the fail-safe and it writes nothing. ``--explain`` is for the
case where the output is *wrong*, which is precisely when the verifier may be
about to reject it, so refusing to explain a file the verifier dislikes would
remove the tool from the situation it exists for. The violations are reported
alongside instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .layout.align import ALIGN_MARK
from .layout.engine import Decision, Visit, flat_width
from .layout.ir import (Align, Concat, Fill, Group, IfBreak, Indent, Layout,
                        Text, Verbatim, children_of)
from .rules import REGISTRY, Builder, RuleRegistry, build_tree
from .style import DEFAULT_STYLE, Style
from .verify import verify

#: What a line laid out by no rule is called. Text the formatter *copied*
#: rather than composed, which is an answer to "which rule laid this out"
#: rather than a gap in it -- and the one a reader of a deliberately
#: incomplete formatter most needs to see.
VERBATIM = "(verbatim)"

__all__ = ["Recorder", "Explanation", "Break", "Span", "VERBATIM", "explain",
           "report"]


class Recorder(RuleRegistry):
    """A registry that remembers which builder produced which layout."""

    def __init__(self, base: RuleRegistry = REGISTRY) -> None:
        super().__init__(base)
        #: ``id(layout)`` -> the rule name whose builder returned it. Handed to
        #: the engine as a live ``keys()`` view: the nodes do not exist until
        #: the tree is built, and the tree is built inside the same call that
        #: renders it.
        self.origins: Dict[int, str] = {}
        #: Keeps those layouts alive. The ``id()`` of a collected object can be
        #: reissued, and a reissued key is a *wrong* answer rather than a
        #: missing one. Most of these are also reachable from the finished
        #: tree; the ones that are not are the ``Concat`` nodes flattening
        #: spliced out, and those are exactly the ids that could be reissued.
        #: No test can force that collision, so this is a guard held in place
        #: by argument rather than by the suite -- said out loud because an
        #: unkillable mutant with no note reads as dead code.
        self._kept: List[Layout] = []

    def get(self, rule_name: str) -> Optional[Builder]:
        inner = super().get(rule_name)
        if inner is None:
            return None

        def recording(ctx: Any, node: Any) -> Layout:
            built = inner(ctx, node)
            self._tag(built, rule_name)
            return built

        return recording

    def _tag(self, node: Layout, rule_name: str) -> None:
        """Tag *node*, and a ``Concat``'s parts as well as the ``Concat``.

        The parts are not belt-and-braces, they are the whole thing.
        :func:`~pssfmt.layout.ir.concat` **flattens nested concatenations**, so
        when a parent builder concatenates this builder's result the ``Concat``
        object returned here is spliced out of existence and its children are
        re-parented into the parent's. Tagging only the returned node left 1 of
        6 tags reachable in the finished tree for a small file -- and the one
        that survived was the root, so the report cheerfully attributed the
        entire file to ``compilation_unit``.

        Worth noting how that failed, because it is the shape to watch for: a
        builder returning a ``Group`` or an ``Indent`` *does* survive
        flattening, so attribution quality varied by the accident of which node
        type a rule happened to return, and it varied **silently**.

        ``setdefault`` because builders run innermost-first, so the first tag
        on a node is the most specific one; a parent must not overwrite its
        child's answer with its own.
        """
        self._mark_copies(node)
        self._claim(node, rule_name)
        if isinstance(node, Concat):
            for part in node.parts:
                self._claim(part, rule_name)

    def _claim(self, node: Layout, rule_name: str) -> None:
        if isinstance(node, Verbatim):
            self.origins[id(node)] = VERBATIM
        else:
            self.origins.setdefault(id(node), rule_name)
        self._kept.append(node)

    def _mark_copies(self, root: Layout) -> None:
        """Name every ``Verbatim`` in this builder's subtree as copied.

        Without this the answer exists and is never reachable: ``rule_for``
        walks up until it finds a tag, and there is always one -- at worst the
        root rule -- so a copied region was reported as having been laid out
        by whichever rule happened to enclose it. The corpus holds 40
        ``Verbatim`` nodes and ``(verbatim)`` appeared **zero** times, while
        the documentation described it as the signal to look for. A promise a
        report can never keep is worse than a report without it.

        Pruned at any node an inner builder already claimed, since that
        builder ran this same walk over its own subtree. That is what keeps
        the total linear in the tree rather than quadratic in its depth --
        and the prune is *only* a cost saving: removing it finds exactly the
        same nodes, more slowly, which a mutation run confirmed rather than
        assumed.
        """
        stack: List[Layout] = list(children_of(root))
        while stack:
            node = stack.pop()
            if isinstance(node, Verbatim):
                self.origins[id(node)] = VERBATIM
                self._kept.append(node)
                continue
            if id(node) in self.origins:
                continue
            stack.extend(children_of(node))


def _parents(doc: Layout) -> Dict[int, Layout]:
    parents: Dict[int, Layout] = {}
    stack: List[Layout] = [doc]
    seen = {id(doc)}
    while stack:
        node = stack.pop()
        for child in children_of(node):
            parents[id(child)] = node
            if id(child) not in seen:
                seen.add(id(child))
                stack.append(child)
    return parents


@dataclass(frozen=True)
class Span:
    """Output lines produced by one rule, inclusive."""

    first: int
    last: int
    rule: str


@dataclass(frozen=True)
class Break:
    """One group the engine broke, and why."""

    line: int
    rule: str
    reason: str
    column: int
    available: int
    needed: int

    def describe(self) -> str:
        if self.reason == "forced":
            return "contains a hard break, so it was never one line"
        return "needs %d columns and had %d" % (self.needed, self.available)


@dataclass
class Explanation:
    """Everything ``--explain`` knows about one file."""

    name: str
    style: Style
    text: str
    doc: Layout
    decisions: Tuple[Decision, ...]
    visits: Tuple[Visit, ...]
    origins: Dict[int, str]
    violations: Tuple[Any, ...] = ()
    _parents: Dict[int, Layout] = field(default_factory=dict, repr=False)

    @property
    def lines(self) -> int:
        if not self.text:
            return 0
        return self.text.count("\n") + (0 if self.text.endswith("\n") else 1)

    def rule_for(self, node: Layout) -> str:
        """The rule that built *node*, or its nearest tagged ancestor's."""
        current: Optional[Layout] = node
        while current is not None:
            name = self.origins.get(id(current))
            if name is not None:
                return name
            current = self._parents.get(id(current))
        return VERBATIM

    def _is_ancestor(self, maybe: Layout, node: Layout) -> bool:
        current = self._parents.get(id(node))
        while current is not None:
            if current is maybe:
                return True
            current = self._parents.get(id(current))
        return False

    def spans(self) -> Tuple[Span, ...]:
        """Which rule produced each run of output lines.

        Visits arrive in document order, so an open node stays open until a
        visit appears that is not one of its descendants. Where several
        spans cover a line the innermost wins -- deepest, then latest -- which
        is the specific answer rather than "the file", and being told the whole
        file was laid out by ``compilation_unit`` is being told nothing.
        """
        end = max(self.lines, 1)
        raw: List[Tuple[int, int, int, str]] = []   # start, stop, depth, rule
        stack: List[Visit] = []
        for v in self.visits:
            while stack and not self._is_ancestor(stack[-1].node, v.node):
                top = stack.pop()
                raw.append((top.line, max(v.line - 1, top.line), len(stack),
                            self.rule_for(top.node)))
            stack.append(v)
        while stack:
            top = stack.pop()
            raw.append((top.line, end, len(stack), self.rule_for(top.node)))

        best: Dict[int, Tuple[int, int, str]] = {}
        for start, stop, depth, rule in raw:
            for line in range(start, min(stop, end) + 1):
                key = (depth, start)
                if line not in best or key > best[line][:2]:
                    best[line] = (depth, start, rule)

        out: List[Span] = []
        for line in range(1, end + 1):
            rule = best[line][2] if line in best else VERBATIM
            if out and out[-1].rule == rule and out[-1].last == line - 1:
                out[-1] = Span(out[-1].first, line, rule)
            else:
                out.append(Span(line, line, rule))
        return tuple(out)

    def breaks(self) -> Tuple[Break, ...]:
        """Every group the engine *chose* to break, in output order.

        Groups that fit are left out; they are the overwhelming majority and
        are never why a file looks wrong.
        """
        out = [
            Break(line=d.line, rule=self.rule_for(d.group), reason=d.reason,
                  column=d.column, available=d.available,
                  needed=flat_width(d.group, self.style.indent_width))
            for d in self.decisions if d.broke
        ]
        out.sort(key=lambda b: (b.line, b.column))
        return tuple(out)

    def overlong(self) -> Tuple[Tuple[int, int, str], ...]:
        """``(line, width, rule)`` for output lines wider than ``print_width``.

        A line can exceed the limit legitimately -- an unbreakable token, a
        ``Verbatim`` region, a comment the formatter may not reflow -- so this
        names what produced it rather than reporting a fault.
        """
        spans = self.spans()
        out = []
        for i, line in enumerate(self.text.splitlines(), start=1):
            if len(line) > self.style.print_width:
                rule = next((s.rule for s in spans if s.first <= i <= s.last),
                            VERBATIM)
                out.append((i, len(line), rule))
        return tuple(out)

    def tree(self) -> str:
        """The Layout IR, one node per line."""
        broke = {id(d.group): d.broke for d in self.decisions}
        lines: List[str] = []
        stack: List[Tuple[Layout, int]] = [(self.doc, 0)]
        while stack:
            node, depth = stack.pop()
            lines.append("%s%s" % ("  " * depth, self._label(node, broke)))
            for child in reversed(children_of(node)):
                stack.append((child, depth + 1))
        return "\n".join(lines)

    def _label(self, node: Layout, broke: Dict[int, bool]) -> str:
        kind = type(node).__name__
        tag = self.origins.get(id(node))
        suffix = "  [%s]" % tag if tag else ""
        if isinstance(node, Text):
            # The alignment mark is a NUL, which prints as `\x00` and reads as
            # corruption. It is neither: it is a column stop the alignment
            # pass consumes after line breaking, and a debug tree that makes
            # its own machinery look like a bug is worse than no debug tree.
            if ALIGN_MARK in node.value:
                return "Text <column stop> + %r%s" % (
                    node.value.replace(ALIGN_MARK, ""), suffix)
            return "Text %r%s" % (node.value, suffix)
        if isinstance(node, Verbatim):
            return "Verbatim %d chars, %d lines%s" % (
                len(node.value), node.value.count("\n") + 1, suffix)
        if isinstance(node, Group):
            state = broke.get(id(node))
            mark = "unreached" if state is None else (
                "broken" if state else "flat")
            return "Group %s%s" % (mark, suffix)
        if isinstance(node, Indent):
            return "Indent +%d%s" % (node.width, suffix)
        if isinstance(node, Align):
            return "Align +%d%s" % (node.offset, suffix)
        if isinstance(node, (Concat, Fill)):
            return "%s (%d)%s" % (kind, len(node.parts), suffix)
        if isinstance(node, IfBreak):
            return "IfBreak%s%s" % (
                " of %s" % node.group_id if node.group_id else "", suffix)
        return "%s%s" % (kind, suffix)


def explain(source: str, style: Style = DEFAULT_STYLE,
            name: str = "<input>") -> Explanation:
    """Format *source*, keeping the reasons."""
    from pssparser import cst as _cst

    recorder = Recorder()
    trace: List[Any] = []
    built = build_tree(_cst.parse(source), style=style, registry=recorder,
                       trace=trace, watch=recorder.origins.keys())
    return Explanation(
        name=name, style=style, text=built.text, doc=built.doc,
        decisions=tuple(d for d in trace if isinstance(d, Decision)),
        visits=tuple(v for v in trace if isinstance(v, Visit)),
        origins=recorder.origins,
        violations=verify(source, built.text),
        _parents=_parents(built.doc))


def report(exp: Explanation, tree: bool = False) -> str:
    """The human-readable form. Returns text; printing is the caller's job."""
    out: List[str] = [
        "%s: %d output lines, print_width %d, indent_width %d"
        % (exp.name, exp.lines, exp.style.print_width, exp.style.indent_width)
    ]

    if exp.violations:
        out += ["", "This output FAILS verification and would not be written:"]
        out += ["  %s" % v for v in exp.violations]

    out += ["", "Which rule laid out each line"]
    for span in exp.spans():
        where = ("%d" % span.first if span.first == span.last
                 else "%d-%d" % (span.first, span.last))
        out.append("  %-12s %s" % (where, span.rule))

    broken = exp.breaks()
    out.append("")
    if broken:
        out.append("Where the engine chose to break (%d of %d groups)"
                   % (len(broken), len(exp.decisions)))
        out.append("  %-6s %-30s %s" % ("line", "rule", "reason"))
        for b in broken:
            out.append("  %-6d %-30s %s" % (b.line, b.rule, b.describe()))
    else:
        # Worth saying rather than omitting: an empty section here reads as
        # "the tool found nothing", and the truth is that there was nothing to
        # find. Every break in this file was a rule's decision, not a
        # measurement -- which is the answer to "why did it break there".
        out.append("Every break in this file is unconditional: a rule emitted "
                   "it.")
        out.append("  The engine measured %d group(s) and broke none."
                   % len(exp.decisions))

    over = exp.overlong()
    if over:
        out += ["", "Lines still over print_width (%d)" % len(over),
                "  %-6s %-6s %s" % ("line", "width", "laid out by")]
        out += ["  %-6d %-6d %s" % row for row in over]

    if tree:
        out += ["", "Layout IR", exp.tree()]

    return "\n".join(out) + "\n"

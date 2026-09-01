"""The rule layer -- ``P3-1``, dispatch and the fallback that makes it safe.

PSS has 346 grammar rules. A formatter that must handle all of them before it
handles any is one nobody ever finishes, so this layer is built to be
*incomplete on purpose*: a node with a registered builder is formatted, and a
node without one is emitted exactly as the author wrote it.

Why the fallback is not a compromise
------------------------------------
The unhandled path is not a stub, a guess, or a best effort. It is the
``P1-2`` null formatter's emission, node-scoped: the original tokens with the
original whitespace and the original comments, byte for byte. So the rule set
is incrementally adoptable *and* the empty rule set is already correct --
which is the property this module is tested for. With nothing registered,
:func:`format_source` reproduces the entire corpus unchanged, because it
degenerates to the formatter that already did.

That inverts the usual risk. Adding a rule cannot make an unrelated construct
worse, because nothing else was relying on that rule existing; the worst a
missing rule does is leave a construct looking exactly as it does today.

Error nodes are never formatted
-------------------------------
A subtree ANTLR marked as an error is emitted verbatim regardless of what is
registered. The tree there is a recovery artifact rather than a parse, and a
rule handed one would be laying out a structure the author did not write.
This is checked before the registry is consulted, so it cannot be overridden
by registering a builder.

What is deliberately absent
---------------------------
There is no ``ctx.token()`` helper. Emitting a *token* rather than a span
means taking responsibility for the comments attached to it, and the trivia
placement rules that go with that belong to the first real rule module
(``P3-2``) rather than to a skeleton that would have to guess at them. Until
then :meth:`BuildContext.build` has exactly one emission path, which is why
the round-trip claim above is checkable rather than aspirational.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

from ..finish import finish, normalize, resolve_line_ending
from ..layout import Layout, Verbatim, align_text, render
from ..style import DEFAULT_STYLE, LineEnding, Style
from ..trivia import TriviaMap
from ..verbatim import NO_HATCHES, Hatches, scan_hatches
from .emit import code_span, span_text

__all__ = [
    "Builder",
    "RuleRegistry",
    "REGISTRY",
    "rule",
    "BuildContext",
    "Built",
    "build_tree",
    "format_tree",
    "format_source",
]

#: A rule builder: given the build context and a CST node, return a Layout.
#: Builders recurse through ``ctx.build(child)`` rather than calling each
#: other, so a child with no builder still falls back correctly.
Builder = Callable[["BuildContext", Any], Layout]


class RuleRegistry:
    """A mapping from CST rule name to the builder that lays it out.

    A class rather than a module-level dict because tests need to register a
    builder without leaking it into every subsequent test. A single global
    registry makes rule tests order-dependent, and an order-dependent test
    suite is one that eventually gets its failures explained away.
    """

    def __init__(self, base: Optional["RuleRegistry"] = None) -> None:
        self._builders: Dict[str, Builder] = dict(base._builders) if base else {}

    def register(self, rule_name: str, builder: Builder) -> None:
        """Binds *rule_name* to *builder*.

        Rebinding a name is an error. Two modules quietly claiming the same
        construct is a real possibility once the rule set spans eight files,
        and the symptom -- one of them silently never running -- is close to
        undiagnosable.
        """
        if rule_name in self._builders:
            raise ValueError(
                f"{rule_name!r} already has a builder "
                f"({self._builders[rule_name].__qualname__}); "
                "two rules cannot claim one construct"
            )
        self._builders[rule_name] = builder

    def rule(self, *rule_names: str) -> Callable[[Builder], Builder]:
        """Decorator form. Returns the builder unchanged, so it stays testable."""
        if not rule_names:
            raise ValueError("@rule() needs at least one CST rule name")

        def decorate(builder: Builder) -> Builder:
            for name in rule_names:
                self.register(name, builder)
            return builder

        return decorate

    def get(self, rule_name: str) -> Optional[Builder]:
        return self._builders.get(rule_name)

    def names(self) -> Tuple[str, ...]:
        return tuple(sorted(self._builders))

    def __contains__(self, rule_name: object) -> bool:
        return rule_name in self._builders

    def __len__(self) -> int:
        return len(self._builders)

    def __iter__(self) -> Iterator[str]:
        return iter(self.names())


#: The registry the rule modules populate at import time.
REGISTRY = RuleRegistry()

#: Convenience alias so a rule module writes ``@rule("component_declaration")``.
rule = REGISTRY.rule


@dataclass(frozen=True)
class BuildContext:
    """Everything a builder is allowed to consult.

    The invariant is what *kind* of thing is here, not how many: the resolved
    policy, what the author wrote, and which rules are in play. A builder that
    reaches for anything else is either doing the layout engine's job or
    reading configuration, and both are the failures this layer exists to
    prevent -- see ``T-13``.

    ``P3-9`` added the fourth field and it is the third kind, not a new one:
    ``// pssfmt off`` is something the author wrote, in a comment, saying
    which of these rules may run where.

    ``P4-13`` added the fifth, which *is* a new kind, and it is here because
    exactly one rule needs it. ``optional_semicolon = "require"`` writes a
    token into the file, and inserting a token changes how everything after it
    is read -- in a file the parser did not understand, "what comes after"
    is not a thing anything here knows. So insertion asks first. Deletion does
    not need to: it is guarded per member by what that member's last token
    actually was, which is a local question with a local answer.
    """

    #: The resolved policy. Never configuration: see :mod:`pssfmt.style`.
    style: Style
    #: Comment attachment and the original whitespace (``P1-1``).
    trivia: TriviaMap
    #: Which builders are in play.
    registry: RuleRegistry = field(default=REGISTRY)
    #: Where the author has switched the formatter off (``P3-9``, § 5.3).
    hatches: Hatches = field(default=NO_HATCHES)
    #: Whether the parser reported no syntax errors for this tree (``P4-13``).
    #: Only a rule that *adds* tokens may consult it; see the class docstring.
    parsed_cleanly: bool = True

    def build(self, node: Any) -> Layout:
        """Lays out *node*: its builder if it has one, verbatim if it does not."""
        if node is None:
            return Verbatim("")
        if getattr(node, "is_error", False) or not node.is_rule:
            return self.verbatim(node)
        builder = self.registry.get(node.rule_name)
        if builder is None:
            return self.verbatim(node)
        return builder(self, node)

    def verbatim(self, node: Any) -> Layout:
        """*node* exactly as the author wrote it, comments and spacing intact."""
        return Verbatim(self.source_of(node))

    def source_of(self, node: Any) -> str:
        """The original text spanned by *node*.

        Reconstructed from the trivia map rather than sliced out of the input,
        because the map is a proven partition of the token stream (``P1-1``)
        and a character offset is not: the two disagree exactly where a
        formatter is most likely to be wrong.
        """
        span = code_span(self.trivia, node)
        if span is None:
            return ""
        return span_text(self.trivia, *span)


@dataclass(frozen=True)
class Built:
    """A formatted tree: the text, and the Layout it came from."""

    #: The output.
    text: str
    #: The Layout IR that produced it. Kept for ``P4-5``'s ``--explain``,
    #: which is cheap now and expensive to retrofit.
    doc: Layout
    #: The trivia map built for this tree.
    trivia: TriviaMap


def build_tree(tree: Any,
               style: Style = DEFAULT_STYLE,
               registry: RuleRegistry = REGISTRY,
               trace: Optional[list] = None,
               watch: Optional[Any] = None) -> Built:
    """Formats an already-parsed tree.

    :param trace: passed straight to :func:`~pssfmt.layout.engine.render`,
        which appends one decision per group and one visit per watched node.
    :param watch: also passed straight through. For ``P4-5``; ``None`` for
        both means the engine does not know it is being watched, which is the
        only way an explanation can be trusted to describe the real run.
    """
    trivia = TriviaMap(tree.tokens, max_blank_lines=style.max_blank_lines)
    ctx = BuildContext(style=style, trivia=trivia, registry=registry,
                       hatches=scan_hatches(trivia),
                       parsed_cleanly=getattr(
                           tree, "num_syntax_errors", 0) == 0)
    doc = ctx.build(tree.root)
    text = render(
        doc,
        print_width=style.print_width,
        use_tabs=style.use_tabs,
        tab_width=style.indent_width,
        trace=trace,
        watch=watch,
    )
    # Column alignment runs on finished lines, after line breaking, so it can
    # never influence a fit decision -- see ``pssfmt.layout.align``. It is a
    # no-op on text containing no column stop, which is every construct whose
    # rule does not ask for one.
    text = align_text(
        text,
        mode=style.alignment,
        boundary=style.alignment_group_boundary,
        print_width=style.print_width,
    )
    # Trivia after the last code token belongs to no node, so no builder can
    # emit it. Dropping it truncates the file -- usually by exactly the final
    # newline, which is the kind of diff that gets committed without comment.
    text += "".join(tok.text for tok in trivia.eof.raw_leading)
    # ...and because it is *copied* rather than composed, every file-level
    # property held for every line but the last one until this call existed.
    # See `pssfmt.finish`.
    return Built(text=finish(text, style, trivia.stream), doc=doc,
                 trivia=trivia)


def format_tree(tree: Any,
                style: Style = DEFAULT_STYLE,
                registry: RuleRegistry = REGISTRY) -> str:
    """:func:`build_tree`, keeping only the text."""
    return build_tree(tree, style=style, registry=registry).text


def format_source(src: Any,
                  style: Style = DEFAULT_STYLE,
                  registry: RuleRegistry = REGISTRY) -> str:
    """Parses *src* and formats it.

    Signature-compatible with the ``formatter`` argument of
    :func:`pssfmt.verify.format_safely`, via a one-argument closure. Nothing
    here verifies anything: the fail-safe is a separate layer on purpose, so
    that no rule can be written in a way that quietly bypasses it.

    Line endings are handled entirely at the two ends of this function and
    nowhere in between -- normalised before the parser sees the text, applied
    again by the emit boundary. The rule layer has no CRLF handling and needs
    none as a result; ``pssfmt.finish.normalize`` records what happens without
    this, which is a raise rather than bad output.

    ``auto`` is resolved here too, for the same reason in reverse. It is a
    question about the input, and by the time there is a tree the input has
    been normalised and every file in the world reports LF.
    """
    from pssparser import cst as _cst

    text = src.decode("utf-8") if isinstance(src, (bytes, bytearray)) else src
    resolved = style.evolve(
        line_ending=LineEnding.CRLF
        if resolve_line_ending(style, text) == "\r\n" else LineEnding.LF)
    return format_tree(_cst.parse(normalize(text)), style=resolved,
                       registry=registry)


# Registered last, and by an explicit call rather than by import side effect:
# a module that binds builders merely by being imported makes the shipped
# formatter's contents depend on import order, which is the sort of thing that
# is fine until the day it is not.
from . import activities  # noqa: E402
from . import constraints  # noqa: E402
from . import decls  # noqa: E402
from . import procedural  # noqa: E402
from . import stmts  # noqa: E402

decls.register(REGISTRY)
procedural.register(REGISTRY)
stmts.register(REGISTRY)
constraints.register(REGISTRY)
activities.register(REGISTRY)

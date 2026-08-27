"""Layout IR -- the algebraic document a rule builds.

Terminology
-----------
This is called the **Layout IR**, not "Doc". Prettier's literature -- and
most writing about Wadler-style pretty printing -- calls the equivalent
structure a "Doc", but this project has ``sphinx-pss`` and a ``docs/`` tree,
so "Doc" is actively misleading here. When reading that literature, read
"Doc" for "Layout".

The node set
------------
Wadler-style pretty printing, with the practical extensions every real
formatter ends up needing:

:class:`Text`
    literal characters; never contains a newline
:class:`Concat`
    sequence
:class:`Group`
    a break-together unit: flat if it fits, otherwise broken
:class:`Indent`
    increase indentation by a column count
:class:`Align`
    indent to the *current column* plus an offset
:class:`Line`
    a space when flat, a newline when broken
:class:`SoftLine`
    nothing when flat, a newline when broken
:class:`HardLine`
    always a newline; forces every enclosing group to break
:class:`Fill`
    greedy packing: break only where the next item does not fit
:class:`IfBreak`
    choose content based on the enclosing group's mode
:class:`Verbatim`
    byte-preserved text, exempt from width, forces breaks
:class:`BreakParent`
    a marker forcing enclosing groups to break

Nodes are frozen and hashable by identity, so a subtree may be shared freely
between parents. The engine memoises break propagation on ``id()``, which
makes sharing cheap rather than merely legal.

Invariant
---------
Nothing in this package imports ``pssfmt.*`` or ``pssparser.*``. The layout
engine is a general-purpose pretty printer that happens to live here; keeping
it free of PSS lets it be tested against hand-written trees alone, and lets it
be extracted if anything else ever wants it. A test enforces this
mechanically, because a convention that is only written down is not enough.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple, Union

__all__ = [
    "Layout",
    "Text",
    "Concat",
    "Group",
    "Indent",
    "Align",
    "Line",
    "SoftLine",
    "HardLine",
    "Fill",
    "IfBreak",
    "Verbatim",
    "BreakParent",
    "LINE",
    "SOFTLINE",
    "HARDLINE",
    "BREAK_PARENT",
    "EMPTY",
    "SPACE",
    "text",
    "concat",
    "group",
    "indent",
    "align_to",
    "join",
    "fill_with",
    "children_of",
]


class _Node:
    """Base for every Layout node. Not public; use :data:`Layout`."""

    __slots__ = ()


@dataclass(frozen=True)
class Text(_Node):
    """Literal characters.

    Must not contain a newline: a newline in the output is always a layout
    decision, never a payload. Use :class:`HardLine` for an unconditional
    break and :class:`Verbatim` for text whose newlines are the author's.
    """

    value: str

    def __post_init__(self) -> None:
        if "\n" in self.value or "\r" in self.value:
            raise ValueError(
                "Text must not contain a newline; use HardLine or Verbatim "
                f"(got {self.value!r})"
            )


@dataclass(frozen=True)
class Concat(_Node):
    """An ordered sequence of nodes."""

    parts: Tuple["Layout", ...]


@dataclass(frozen=True)
class Group(_Node):
    """A break-together unit.

    Rendered flat if its entire contents fit in the remaining width; otherwise
    every :class:`Line`/:class:`SoftLine` *directly* inside it becomes a
    newline. Nested groups are re-measured independently, which is what makes
    the outer-breaks-first behaviour fall out rather than being coded.

    ``should_break`` forces the broken mode without measuring. ``id`` names the
    group so an :class:`IfBreak` elsewhere can ask about *this* group's mode
    rather than its own enclosing one.
    """

    contents: "Layout"
    should_break: bool = False
    id: Optional[str] = None


@dataclass(frozen=True)
class Indent(_Node):
    """Increase indentation by ``width`` columns for ``contents``.

    ``width`` is a column count supplied by the caller -- in practice by the
    resolved style policy, per construct. A rule module passing an integer
    literal here is a bug, and a test fails on it: indentation width is
    configurable, so a rule that hardcodes it silently ignores the user.
    """

    contents: "Layout"
    width: int


@dataclass(frozen=True)
class Align(_Node):
    """Indent ``contents`` to the current output column, plus ``offset``.

    Distinct from :class:`Indent`, which adds a *logical level*. Align is for
    hanging alignment -- continuation lines that line up under an open paren or
    after a keyword -- where the target depends on where the line happens to
    have got to.

    Alignment is emitted with spaces even when ``use_tabs`` is set: tabs for
    indentation, spaces for alignment is the only rule under which a file
    renders the same at every tab stop.
    """

    contents: "Layout"
    offset: int = 0


@dataclass(frozen=True)
class Line(_Node):
    """A space when flat, a newline when broken."""


@dataclass(frozen=True)
class SoftLine(_Node):
    """Nothing when flat, a newline when broken."""


@dataclass(frozen=True)
class HardLine(_Node):
    """Always a newline. Forces every enclosing group broken.

    ``blank_before`` emits that many blank lines ahead of the break; the
    trivia layer clamps it to ``max_blank_lines`` before it gets here
    (``P1-1``), so the engine does no policy of its own.
    """

    blank_before: int = 0


@dataclass(frozen=True)
class Fill(_Node):
    """Greedy packing: fit as many items per line as possible.

    ``parts`` alternates content and separator, starting and ending with
    content: ``[c0, sep0, c1, sep1, c2]``. Each separator is measured against
    the *next* content and broken only if that pair does not fit -- so a long
    list wraps rather than exploding one item per line.

    This matters more in PSS than in most languages: constraint range lists
    (``x in [0..7, 16, 32..63]``) and enum bodies are exactly this shape.
    """

    parts: Tuple["Layout", ...]


@dataclass(frozen=True)
class IfBreak(_Node):
    """Content chosen by mode: ``break_contents`` when broken, else ``flat_contents``.

    The canonical use is a trailing comma that should exist only in the
    exploded form. With ``group_id`` set, the mode consulted is that of the
    named group rather than the enclosing one.

    A forced break *inside* ``break_contents`` does not propagate outward. If
    it did, the mere presence of a conditional hard break would make the
    condition true, and the node would be useless.
    """

    break_contents: "Layout"
    flat_contents: "Layout" = field(default_factory=lambda: EMPTY)
    group_id: Optional[str] = None


@dataclass(frozen=True)
class Verbatim(_Node):
    """Text reproduced byte for byte, exempt from width accounting.

    Its enclosing groups are forced broken -- a payload with its own newlines
    cannot participate in a flat layout. This is the node behind ``exec``
    target-template bodies (section 4.3), template strings (section 4.3.1) and
    ``// pssfmt off`` regions (section 5.3).

    The ``value`` is emitted exactly as given, including its newlines and
    including its original indentation. The engine does not re-indent it: any
    re-indentation would change the generated string, which for a target
    template is a semantic change, not a cosmetic one.
    """

    value: str


@dataclass(frozen=True)
class BreakParent(_Node):
    """A marker with no output that forces enclosing groups broken."""


# Singletons for the nullary nodes. Frozen dataclasses with no fields compare
# equal, but sharing one instance keeps the propagation memo small.
LINE = Line()
SOFTLINE = SoftLine()
HARDLINE = HardLine()
BREAK_PARENT = BreakParent()
EMPTY = Text("")
SPACE = Text(" ")

Layout = Union[
    Text,
    Concat,
    Group,
    Indent,
    Align,
    Line,
    SoftLine,
    HardLine,
    Fill,
    IfBreak,
    Verbatim,
    BreakParent,
]


# --------------------------------------------------------------------------
# Constructors. Rules read better built from these than from the classes, and
# they do the small normalisations (flattening, empty elision) that keep the
# tree the engine walks smaller than the tree a rule describes.
# --------------------------------------------------------------------------


def text(value: str) -> Text:
    """``Text``, with the empty string folded to the shared :data:`EMPTY`."""
    return EMPTY if value == "" else Text(value)


def concat(*parts: Union["Layout", Sequence["Layout"]]) -> "Layout":
    """Concatenate, accepting either varargs or a single sequence.

    Flattens nested ``Concat`` and drops empty text, so the engine never walks
    structure that cannot produce output.
    """
    flat: list = []
    _flatten(parts, flat)
    if not flat:
        return EMPTY
    if len(flat) == 1:
        return flat[0]
    return Concat(tuple(flat))


def _flatten(items, out: list) -> None:
    for item in items:
        if isinstance(item, _Node):
            if isinstance(item, Concat):
                _flatten(item.parts, out)
            elif item is EMPTY or (isinstance(item, Text) and item.value == ""):
                continue
            else:
                out.append(item)
        elif item is None:
            continue
        else:
            try:
                iter(item)
            except TypeError:
                raise TypeError(
                    f"not a Layout node and not a sequence of them: {item!r}"
                ) from None
            _flatten(item, out)


def group(contents: "Layout", *, should_break: bool = False, id: Optional[str] = None) -> Group:
    return Group(contents, should_break=should_break, id=id)


def indent(contents: "Layout", width: int) -> Indent:
    return Indent(contents, width)


def align_to(contents: "Layout", offset: int = 0) -> Align:
    return Align(contents, offset)


def join(separator: "Layout", parts: Sequence["Layout"]) -> "Layout":
    """``parts`` interleaved with ``separator``."""
    out: list = []
    for i, part in enumerate(parts):
        if i:
            out.append(separator)
        out.append(part)
    return concat(out)


def fill_with(separator: "Layout", items: Sequence["Layout"]) -> "Layout":
    """A :class:`Fill` over ``items``, interleaving ``separator``.

    Builds the alternating content/separator shape :class:`Fill` requires, so
    callers do not have to remember it.
    """
    items = list(items)
    if not items:
        return EMPTY
    if len(items) == 1:
        return items[0]
    parts: list = [items[0]]
    for item in items[1:]:
        parts.append(separator)
        parts.append(item)
    return Fill(tuple(parts))


def children_of(node: "Layout") -> Tuple["Layout", ...]:
    """Direct children, for generic traversal.

    Note that :class:`IfBreak` reports **no** children. Its branches are
    reachable only through the mode that selects them, and traversals that
    treat them as unconditional children -- break propagation above all -- get
    the wrong answer.
    """
    if isinstance(node, Concat):
        return node.parts
    if isinstance(node, Fill):
        return node.parts
    if isinstance(node, (Group, Indent, Align)):
        return (node.contents,)
    return ()

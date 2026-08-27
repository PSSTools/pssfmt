"""The layout engine: break propagation, ``fits``, and ``best`` (``P2-2``).

Two passes, in this order, and the order is the point:

1. :func:`propagate_breaks` walks the tree bottom-up and marks every group that
   *contains* a forced break as broken. Without it, an inner ``HardLine`` would
   be measured as though it were zero width, an outer group would be judged to
   fit, and the output would be flat-with-a-newline-in-it.

2. :func:`render` walks top-down with an explicit command stack, choosing flat
   or broken per group by asking :func:`fits` whether the group's contents --
   *plus whatever must follow on the same line* -- stay inside ``print_width``.

The "plus whatever must follow" is the part naive implementations drop. A
group that fits in isolation but is followed by ``);`` on the same line does
not fit; :func:`fits` therefore continues into the enclosing command stack
after exhausting the group.

Column alignment is deliberately **not** here. It runs after line breaking,
in :mod:`pssfmt.layout.align`, so it can never influence a fit decision --
alignment depends on where lines end, and line breaking depends on how wide
lines are, so running them in the other order makes them mutually recursive
with no fixpoint guarantee.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .ir import (
    Align,
    BreakParent,
    Concat,
    Fill,
    Group,
    HardLine,
    IfBreak,
    Indent,
    Layout,
    Line,
    SoftLine,
    Text,
    Verbatim,
)
from .width import width_of

__all__ = ["render", "propagate_breaks", "MODE_BREAK", "MODE_FLAT"]

MODE_BREAK = 1
MODE_FLAT = 2


# --------------------------------------------------------------------------
# Pass 1 -- break propagation
# --------------------------------------------------------------------------


def propagate_breaks(doc: Layout) -> Dict[int, bool]:
    """Map ``id(group)`` to whether that group must render broken.

    A group breaks if it contains a :class:`HardLine`, a :class:`BreakParent`,
    a :class:`Verbatim`, or an already-broken group -- or if it was built with
    ``should_break=True``.

    :class:`IfBreak` branches are **not** traversed. A forced break inside
    ``break_contents`` must not make its own condition true; see
    :class:`~pssfmt.layout.ir.IfBreak`.

    The walk is iterative. Expression chains and deeply nested activities can
    both produce trees deeper than is comfortable for recursion, and a
    formatter that raises ``RecursionError`` on a large file is a formatter
    nobody runs in a pre-commit hook.

    The returned dict is keyed on ``id()``, which is only meaningful while the
    tree is alive. :func:`render` holds the tree for the duration, and the
    memo dies with the call.
    """
    broken: Dict[int, bool] = {}
    # id(node) -> does this subtree contain a forced break
    forces: Dict[int, bool] = {}

    stack: List[Tuple[Layout, bool]] = [(doc, False)]
    while stack:
        node, visited = stack.pop()
        key = id(node)
        if not visited:
            if key in forces:
                continue
            stack.append((node, True))
            if isinstance(node, (Concat, Fill)):
                for child in node.parts:
                    stack.append((child, False))
            elif isinstance(node, (Group, Indent, Align)):
                stack.append((node.contents, False))
            # IfBreak: no children, on purpose. Text/lines/Verbatim: leaves.
            continue

        if isinstance(node, (HardLine, BreakParent, Verbatim)):
            forces[key] = True
        elif isinstance(node, (Concat, Fill)):
            forces[key] = any(forces.get(id(c), False) for c in node.parts)
        elif isinstance(node, (Indent, Align)):
            forces[key] = forces.get(id(node.contents), False)
        elif isinstance(node, Group):
            is_broken = node.should_break or forces.get(id(node.contents), False)
            broken[key] = is_broken
            # A broken group propagates outward: its newlines are real.
            forces[key] = is_broken
        else:
            forces[key] = False

    return broken


# --------------------------------------------------------------------------
# Indentation state
# --------------------------------------------------------------------------


class _Ind:
    """An indentation prefix and its display width.

    Both are carried because they diverge under ``use_tabs``: the prefix is
    what gets written, the length is what ``fits`` measures against.
    """

    __slots__ = ("value", "length")

    def __init__(self, value: str, length: int) -> None:
        self.value = value
        self.length = length


_ROOT_IND = _Ind("", 0)


def _make_indent(ind: _Ind, width: int, use_tabs: bool, tab_width: int) -> _Ind:
    if width <= 0:
        return ind
    if use_tabs and tab_width > 0:
        added = "\t" * (width // tab_width) + " " * (width % tab_width)
    else:
        added = " " * width
    return _Ind(ind.value + added, ind.length + width)


def _make_align(ind: _Ind, target: int) -> _Ind:
    """Indent to column ``target``.

    Alignment is padded with spaces even under ``use_tabs`` -- tabs for
    indentation, spaces for alignment is the only rule under which the file
    renders identically at every tab stop. The existing prefix is kept when it
    already reaches the target, so tab-indented code stays tab-indented.
    """
    if target < 0:
        target = 0
    if target >= ind.length:
        return _Ind(ind.value + " " * (target - ind.length), target)
    return _Ind(" " * target, target)


# --------------------------------------------------------------------------
# Pass 2 -- fits
# --------------------------------------------------------------------------


def _fits(
    next_cmd: Tuple[_Ind, int, Layout],
    rest_cmds: List[Tuple[_Ind, int, Layout]],
    width: int,
    broken: Dict[int, bool],
    group_modes: Dict[str, int],
    must_be_flat: bool = False,
) -> bool:
    """Does ``next_cmd`` -- and everything that must follow it on this line --
    fit in ``width`` remaining columns?

    Returns as soon as a newline is reached in break mode: everything past the
    newline is somebody else's line and cannot affect this one. ``rest_cmds``
    is consumed from its end, i.e. in the order :func:`render` would have
    processed it.
    """
    if width < 0:
        return False

    rest_idx = len(rest_cmds)
    cmds: List[Tuple[_Ind, int, Layout]] = [next_cmd]

    while width >= 0:
        if not cmds:
            if rest_idx == 0:
                return True
            rest_idx -= 1
            cmds.append(rest_cmds[rest_idx])
            continue

        ind, mode, doc = cmds.pop()

        if isinstance(doc, Text):
            width -= width_of(doc.value)
        elif isinstance(doc, (Concat, Fill)):
            for child in reversed(doc.parts):
                cmds.append((ind, mode, child))
        elif isinstance(doc, Indent):
            cmds.append((ind, mode, doc.contents))
        elif isinstance(doc, Align):
            cmds.append((ind, mode, doc.contents))
        elif isinstance(doc, Group):
            if must_be_flat and broken.get(id(doc), False):
                return False
            group_mode = MODE_BREAK if broken.get(id(doc), False) else mode
            cmds.append((ind, group_mode, doc.contents))
        elif isinstance(doc, IfBreak):
            if doc.group_id is not None:
                group_mode = group_modes.get(doc.group_id, MODE_FLAT)
            else:
                group_mode = mode
            chosen = doc.break_contents if group_mode == MODE_BREAK else doc.flat_contents
            cmds.append((ind, mode, chosen))
        elif isinstance(doc, HardLine):
            return True
        elif isinstance(doc, (Line, SoftLine)):
            if mode == MODE_BREAK:
                return True
            if isinstance(doc, Line):
                width -= 1
        elif isinstance(doc, Verbatim):
            # Exempt from width accounting (P2-5). A multi-line payload ends
            # the line, so nothing after it competes for this line's width;
            # a single-line one contributes nothing and cannot force a break.
            if "\n" in doc.value:
                return True
        elif isinstance(doc, BreakParent):
            pass
        else:  # pragma: no cover -- exhaustive over the node set
            raise TypeError(f"unknown Layout node in fits: {doc!r}")

    return False


# --------------------------------------------------------------------------
# Pass 2 -- render
# --------------------------------------------------------------------------


def _trim_trailing_space(out: List[str]) -> None:
    """Drop trailing spaces and tabs from the emitted output.

    Called before every newline. Indentation is emitted eagerly when a line
    starts, so a line that turns out to hold nothing would otherwise leave the
    indentation behind as trailing whitespace -- the single most common
    diff-noise complaint about hand-rolled formatters.
    """
    while out:
        stripped = out[-1].rstrip(" \t")
        if stripped:
            out[-1] = stripped
            return
        out.pop()


def render(
    doc: Layout,
    *,
    print_width: int = 100,
    use_tabs: bool = False,
    tab_width: int = 4,
) -> str:
    """Lay ``doc`` out into text.

    The result uses ``\\n`` throughout. Translating to CRLF is a single
    substitution at the emit boundary and belongs to the ``line_ending``
    option, not to the engine -- keeping it out of here means ``fits`` never
    has to reason about a two-character newline.
    """
    broken = propagate_breaks(doc)
    group_modes: Dict[str, int] = {}

    out: List[str] = []
    pos = 0
    should_remeasure = False

    cmds: List[Tuple[_Ind, int, Layout]] = [(_ROOT_IND, MODE_BREAK, doc)]

    while cmds:
        ind, mode, node = cmds.pop()

        if isinstance(node, Text):
            out.append(node.value)
            pos += width_of(node.value)

        elif isinstance(node, Concat):
            for child in reversed(node.parts):
                cmds.append((ind, mode, child))

        elif isinstance(node, Indent):
            cmds.append((_make_indent(ind, node.width, use_tabs, tab_width), mode, node.contents))

        elif isinstance(node, Align):
            cmds.append((_make_align(ind, pos + node.offset), mode, node.contents))

        elif isinstance(node, BreakParent):
            pass

        elif isinstance(node, Verbatim):
            out.append(node.value)
            if "\n" in node.value:
                pos = width_of(node.value.rsplit("\n", 1)[1])
            else:
                pos += width_of(node.value)

        elif isinstance(node, Group):
            is_broken = broken.get(id(node), False)
            if mode == MODE_FLAT and not should_remeasure:
                cmds.append((ind, MODE_BREAK if is_broken else MODE_FLAT, node.contents))
                if node.id is not None:
                    group_modes[node.id] = MODE_BREAK if is_broken else MODE_FLAT
                continue
            should_remeasure = False
            if is_broken:
                chosen = MODE_BREAK
            else:
                flat_cmd = (ind, MODE_FLAT, node.contents)
                chosen = (
                    MODE_FLAT
                    if _fits(flat_cmd, cmds, print_width - pos, broken, group_modes)
                    else MODE_BREAK
                )
            if node.id is not None:
                group_modes[node.id] = chosen
            cmds.append((ind, chosen, node.contents))

        elif isinstance(node, IfBreak):
            if node.group_id is not None:
                group_mode = group_modes.get(node.group_id, MODE_FLAT)
            else:
                group_mode = mode
            chosen = node.break_contents if group_mode == MODE_BREAK else node.flat_contents
            cmds.append((ind, mode, chosen))

        elif isinstance(node, Fill):
            _push_fill(node, ind, mode, cmds, broken, group_modes, print_width - pos)

        elif isinstance(node, (Line, SoftLine, HardLine)):
            hard = isinstance(node, HardLine)
            if mode == MODE_FLAT and not hard:
                if isinstance(node, Line):
                    out.append(" ")
                    pos += 1
                continue
            if hard:
                # A hard break inside an otherwise-flat region means every
                # later group on this stack was measured against a line that
                # no longer exists. Re-measure the next one.
                should_remeasure = True
            _trim_trailing_space(out)
            blanks = node.blank_before if hard else 0
            out.append("\n" * (1 + blanks))
            out.append(ind.value)
            pos = ind.length

        else:  # pragma: no cover -- exhaustive over the node set
            raise TypeError(f"unknown Layout node in render: {node!r}")

    _trim_trailing_space(out)
    return "".join(out)


def _push_fill(
    node: Fill,
    ind: _Ind,
    mode: int,
    cmds: List[Tuple[_Ind, int, Layout]],
    broken: Dict[int, bool],
    group_modes: Dict[str, int],
    rem: int,
) -> None:
    """One step of greedy fill.

    Measures the *pair* (this item, separator, next item) rather than the item
    alone. Measuring the item alone is the classic off-by-one: it packs an item
    onto a line, then discovers the separator that must follow it does not fit,
    and the line overflows by exactly the separator's width.

    Only two items are decided per step; the rest is pushed back as a smaller
    :class:`Fill` and re-measured against the width remaining *then*, which is
    what makes the packing greedy rather than precomputed.
    """
    parts = node.parts
    if not parts:
        return

    content = parts[0]
    content_flat = (ind, MODE_FLAT, content)
    content_break = (ind, MODE_BREAK, content)

    if len(parts) == 1:
        content_fits = _fits(content_flat, [], rem, broken, group_modes, must_be_flat=True)
        cmds.append(content_flat if content_fits else content_break)
        return

    separator = parts[1]
    sep_flat = (ind, MODE_FLAT, separator)
    sep_break = (ind, MODE_BREAK, separator)

    # A separator is not necessarily pure whitespace: the common list shape is
    # `Text(",") + Line`, and that comma lands on the line the item ends even
    # when the Line breaks. Measuring the item alone therefore overflows by
    # exactly the separator's non-breaking width. Passing the separator as a
    # *rest* command in break mode charges it and then stops at its newline,
    # which is precisely the accounting we want.
    tail_break = [(ind, MODE_BREAK, separator)]
    content_fits = _fits(content_flat, tail_break, rem, broken, group_modes, must_be_flat=True)

    if len(parts) == 2:
        if content_fits:
            cmds.append(sep_flat)
            cmds.append(content_flat)
        else:
            cmds.append(sep_break)
            cmds.append(content_break)
        return

    remaining = (ind, mode, Fill(parts[2:]))
    pair = Concat((content, separator, parts[2]))
    # Same accounting one item further along: if a separator follows the pair,
    # its non-breaking part is charged to this line too.
    pair_tail = [(ind, MODE_BREAK, parts[3])] if len(parts) > 3 else []
    pair_fits = _fits(
        (ind, MODE_FLAT, pair), pair_tail, rem, broken, group_modes, must_be_flat=True
    )

    # Pushed in reverse: content is processed first.
    cmds.append(remaining)
    if pair_fits:
        cmds.append(sep_flat)
        cmds.append(content_flat)
    elif content_fits:
        cmds.append(sep_break)
        cmds.append(content_flat)
    else:
        cmds.append(sep_break)
        cmds.append(content_break)

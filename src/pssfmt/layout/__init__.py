"""The layout engine -- Layout IR, line breaking, and column alignment.

This subpackage is **dependency-free by construction**: nothing under it
imports ``pssfmt.*`` or ``pssparser.*`` (``formatter.md`` section 10.3). Two
things follow from that, and both are the reason for the rule:

* it can be built and tested while the upstream token/CST API is still in
  flight (``PLAN.md`` Phase U), which is what keeps ``P2`` off the critical
  path; and
* it is extractable as a standalone package if anything else ever wants a
  Wadler pretty-printer.

``T-9`` enforces the boundary as a test rather than a convention, because
section 10.3 is explicit that a convention is not sufficient here.
"""

from .align import ALIGN_MARK, AlignMode, GroupBoundary, align_text, strip_marks
from .engine import MODE_BREAK, MODE_FLAT, propagate_breaks, render
from .ir import (
    BREAK_PARENT,
    EMPTY,
    HARDLINE,
    LINE,
    SOFTLINE,
    SPACE,
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
    align_to,
    children_of,
    concat,
    fill_with,
    group,
    indent,
    join,
    text,
)
from .width import width_of

__all__ = [
    # IR
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
    # Engine
    "render",
    "propagate_breaks",
    "MODE_BREAK",
    "MODE_FLAT",
    # Alignment
    "ALIGN_MARK",
    "AlignMode",
    "GroupBoundary",
    "align_text",
    "strip_marks",
    # Width
    "width_of",
]

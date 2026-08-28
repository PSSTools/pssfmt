"""The resolved style policy -- the seam every rule consults.

A rule module never reads configuration and never writes a whitespace
constant. It asks this object, and it asks **per construct**, even though v1
answers most questions with one global value. That asymmetry is the whole
point: how many options are *exposed* is reversible at any time, but whether
rules are written against a policy at all is decided by the first rule and
never again. A rule set that emits ``Indent(body, 4)`` makes every future
option a cross-cutting edit across every rule module, each with its own bug
tail. ``T-13`` in ``tests/test_boundaries.py`` fails the build on such a
literal, so the seam is enforced mechanically rather than by review.

Two kinds of question, two keys
-------------------------------
Style questions in a formatter come in two shapes, and conflating them is how
half of an API ends up meaningless for half of its arguments:

:class:`Construct`
    a **node kind** -- a component body, an argument list, an activity. It
    answers indentation, brace placement, alignment, and break policy.
:class:`Site`
    a **token adjacency** -- the gap before or after ``::``, ``,``, ``=``.
    It answers spacing, and nothing else.

``PLAN.md`` section 6.6 sketched a single ``Construct`` enum with a
``spacing_for(Construct)`` accessor alongside ``indent_for``. Splitting it
preserves the seam property that item cares about while keeping every
accessor total over its own key type: there is no ``indent_for(COMMA)`` to
answer wrongly, and no spacing site without a measured default. Both enums
are checked for exhaustiveness against their tables by ``T-16``.

How gaps compose
----------------
The whitespace between two adjacent tokens is ``max(left.after,
right.before)`` -- not the sum. Sites are written independently of what
happens to sit next to them, so ``x = -1`` resolves the gap after ``=`` as
``max(ASSIGN.after=1, UNARY.before=0)``, and ``f(a);`` resolves the gap
before ``;`` as ``max(CALL_PAREN_CLOSE.after=0, SEMICOLON.before=0)``. Taking
the maximum makes the composition order-independent, which summing is not.

The consequence, stated because it is a real limit: a site cannot *force*
tightness against a spaced neighbour. No rule measured over the corpus needs
to, and a site that did would be describing a two-token pattern rather than a
token, which belongs in the rule module that knows both.

Where the defaults come from
----------------------------
Every default in this module is a measured value, not a preference. The
evidence, the counts, and the two rules decided by argument rather than by
consensus are in ``docs/style.rst``; ``tools/style_survey.py`` reproduces the
numbers, and ``tests/corpus/test_style_survey.py`` fails if the corpus stops
supporting them. Do not change a default here without changing that page --
``T-16`` checks the two agree.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from .layout.align import AlignMode, GroupBoundary

__all__ = [
    "Construct",
    "Site",
    "Spacing",
    "BraceMode",
    "BreakMode",
    "LineEnding",
    "AlignMode",
    "GroupBoundary",
    "Style",
    "DEFAULT_SPACING",
    "TIGHT",
    "SPACED",
    "DEFAULT_STYLE",
]


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------


class Construct(str, Enum):
    """A node kind a rule lays out.

    Granularity follows the rule tiers in ``PLAN.md`` section 5: a member
    exists where a plausible house style could want a different answer, which
    is why the seven declaration bodies are separate members even though v1
    gives all seven the same indentation. Splitting them later would be a
    rules edit; splitting them now costs an enum member.

    Inheriting from ``str`` makes members usable directly as configuration
    keys and readable in a failure message, which matters more here than
    nominal typing: a ``KeyError`` naming ``'component_body'`` is diagnosable
    and one naming ``<Construct.COMPONENT_BODY: 4>`` is not.
    """

    # -- Tier 1: declarations (P3-2)
    PACKAGE_BODY = "package_body"
    COMPONENT_BODY = "component_body"
    ACTION_BODY = "action_body"
    STRUCT_BODY = "struct_body"
    BUFFER_BODY = "buffer_body"
    STREAM_BODY = "stream_body"
    STATE_BODY = "state_body"
    RESOURCE_BODY = "resource_body"
    ENUM_BODY = "enum_body"
    EXTEND_BODY = "extend_body"
    FUNCTION_BODY = "function_body"

    # -- Tier 1: statements (P3-3)
    COMPOUND_STATEMENT = "compound_statement"

    # -- Tier 1: expressions (P3-4)
    BINARY_EXPRESSION = "binary_expression"
    PAREN_EXPRESSION = "paren_expression"
    ARGUMENT_LIST = "argument_list"
    PARAMETER_LIST = "parameter_list"

    # -- Tier 2: constraints (P3-5)
    CONSTRAINT_BODY = "constraint_body"
    CONSTRAINT_IF_BODY = "constraint_if_body"
    RANGE_LIST = "range_list"

    # -- Tier 2: activity (P3-6)
    ACTIVITY_BODY = "activity_body"
    ACTIVITY_SEQUENCE = "activity_sequence"
    ACTIVITY_PARALLEL = "activity_parallel"
    ACTIVITY_SCHEDULE = "activity_schedule"
    ACTIVITY_SELECT = "activity_select"
    ACTIVITY_REPEAT = "activity_repeat"

    # -- Tier 3: coverage and templates (P3-7)
    COVERGROUP_BODY = "covergroup_body"
    COVERPOINT_BODY = "coverpoint_body"
    CROSS_BODY = "cross_body"
    BINS_BODY = "bins_body"
    TEMPLATE_PARAMETER_LIST = "template_parameter_list"

    # -- Tier 3: verbatim (P3-8)
    EXEC_BODY = "exec_body"

    # -- Trivia
    TRAILING_COMMENT = "trailing_comment"


class Site(str, Enum):
    """A token adjacency whose surrounding whitespace is a style decision.

    Named after the rules in ``tools/style_survey.py`` so a default here can
    be traced to the measurement that produced it. Bracket pairs are two
    members rather than one with an ``inside`` field: the survey measures
    ``"'(' -> inside"`` and ``"inside -> ')'"`` separately, and a close
    bracket's ``after`` is not a style question at all -- whatever follows
    owns its own ``before``.
    """

    # -- Punctuation
    SEMICOLON = "semicolon"
    COMMA = "comma"
    SCOPE_RESOLUTION = "scope_resolution"      # ::
    MEMBER_ACCESS = "member_access"            # .
    RANGE = "range"                            # ..

    # -- Operators
    ASSIGN = "assign"
    ADDITIVE = "additive"                      # + -
    MULTIPLICATIVE = "multiplicative"          # * / %
    COMPARISON = "comparison"                  # < <= > >=
    EQUALITY = "equality"                      # == !=
    LOGICAL = "logical"                        # && ||
    BITWISE = "bitwise"                        # & | ^
    SHIFT = "shift"                            # << >>
    IMPLICATION = "implication"                # ->
    UNARY = "unary"                            # + - ! ~

    # -- Brackets
    CALL_PAREN_OPEN = "call_paren_open"
    CALL_PAREN_CLOSE = "call_paren_close"
    CONTROL_PAREN_OPEN = "control_paren_open"
    CONTROL_PAREN_CLOSE = "control_paren_close"
    GROUP_PAREN_OPEN = "group_paren_open"      # (a + b), (bit[32])x
    GROUP_PAREN_CLOSE = "group_paren_close"
    INDEX_BRACKET_OPEN = "index_bracket_open"
    INDEX_BRACKET_CLOSE = "index_bracket_close"
    TYPE_BRACKET_OPEN = "type_bracket_open"
    TYPE_BRACKET_CLOSE = "type_bracket_close"
    SET_BRACKET_OPEN = "set_bracket_open"      # in [1..4096]
    SET_BRACKET_CLOSE = "set_bracket_close"
    TEMPLATE_ANGLE_OPEN = "template_angle_open"    # packed_s<T, N>
    TEMPLATE_ANGLE_CLOSE = "template_angle_close"
    BRACE_OPEN = "brace_open"
    BRACE_CLOSE = "brace_close"

    # -- The four colons (docs/style.rst, "Colons: four constructs, four rules")
    COLON_BIT_SLICE = "colon_bit_slice"
    COLON_CASE_ITEM = "colon_case_item"
    COLON_INHERITANCE = "colon_inheritance"
    COLON_LABEL = "colon_label"


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Spacing:
    """Columns of whitespace immediately before and after a :class:`Site`.

    ``before`` and ``after`` are independent, and a gap between two tokens is
    the maximum of the left token's ``after`` and the right token's
    ``before``. See the module docstring.
    """

    before: int = 0
    after: int = 0

    def __post_init__(self) -> None:
        if self.before < 0 or self.after < 0:
            raise ValueError(f"spacing cannot be negative: {self!r}")


#: No space on either side.
TIGHT = Spacing(0, 0)

#: Exactly one space on either side.
SPACED = Spacing(1, 1)


class BraceMode(str, Enum):
    """Where ``{`` goes relative to the line that opens the construct."""

    #: ``component c {`` -- K&R. 732 of 733 in the corpus; Allman does not occur.
    ATTACH = "attach"
    #: ``{`` on its own line.
    BREAK = "break"


class BreakMode(str, Enum):
    """How a construct's contents relate to line breaking.

    v1 answers ``FIT`` for every construct. The other members exist because
    the rule tiers already know they will need them -- ``RANGE_LIST`` wants
    ``FILL`` (``P3-5``) and ``EXEC_BODY`` is forced broken by its verbatim
    interior (``P3-8``) -- and encoding those answers before the rule that
    needs them would be guessing at a decision the rule module owns.
    """

    #: Flat if the whole construct fits, otherwise broken. A ``Group``.
    FIT = "fit"
    #: Always broken, regardless of width.
    ALWAYS = "always"
    #: Greedy packing: break only where the next item does not fit. A ``Fill``.
    FILL = "fill"
    #: Never broken by this rule; width is somebody else's problem.
    NEVER = "never"


class LineEnding(str, Enum):
    """Line terminator for emitted files."""

    #: Match the dominant ending of the input file.
    AUTO = "auto"
    LF = "lf"
    CRLF = "crlf"


# ---------------------------------------------------------------------------
# The measured defaults
# ---------------------------------------------------------------------------

#: Spacing for every :class:`Site`, from ``docs/style.rst``.
#:
#: The counts in the comments are votes-in-favour / instances-measured across
#: the corpus's independent voices. Sites with no count were not decided by
#: the corpus -- too few instances -- and follow the general binary-operator
#: rule instead; ``docs/style.rst`` lists them under "What this page does not
#: decide" so that silence is not mistaken for consensus.
DEFAULT_SPACING: Mapping[Site, Spacing] = MappingProxyType({
    Site.SEMICOLON: Spacing(0, 0),               # before: 1242/1243
    Site.COMMA: Spacing(0, 1),                   # 355/362, 312/318
    Site.SCOPE_RESOLUTION: TIGHT,                # 392/392
    Site.MEMBER_ACCESS: TIGHT,                   # 531/532
    Site.RANGE: TIGHT,                           # 18/18

    Site.ASSIGN: SPACED,                         # 271/319; the rest is alignment
    Site.ADDITIVE: SPACED,                       # 94/94
    Site.MULTIPLICATIVE: SPACED,                 # split; decided for the humans
    Site.COMPARISON: SPACED,                     # 128/130
    Site.EQUALITY: SPACED,                       # 48/48
    Site.LOGICAL: SPACED,                        # 14/14
    Site.BITWISE: SPACED,                        # undecided; binary-operator rule
    Site.SHIFT: SPACED,                          # undecided; binary-operator rule
    Site.IMPLICATION: SPACED,                    # undecided; binary-operator rule
    Site.UNARY: Spacing(0, 0),                   # after: 92/92

    # `foo(a, b)` -- tight against the callee, tight inside.
    Site.CALL_PAREN_OPEN: Spacing(0, 0),         # 241/244, 765/767
    Site.CALL_PAREN_CLOSE: Spacing(0, 0),        # 765/767
    # `if (x)` -- one space after the keyword. Same bracket, different rule,
    # which is why these are separate sites rather than one.
    Site.CONTROL_PAREN_OPEN: Spacing(1, 0),      # 118/118
    Site.CONTROL_PAREN_CLOSE: Spacing(0, 0),
    # `(a + b)` and `(bit[32])x` -- a third paren, and a third rule. The two
    # constructs are one site because the corpus gives them one answer: tight
    # inside, 12/12 grouping across 6 files and 13/13 cast across 10, with no
    # file writing either any other way. Distinct from CALL_PAREN because the
    # numbers agreeing today does not make the *decisions* the same one: a
    # style that spaces a call's arguments has said nothing about whether
    # `(a + b)` should become `( a + b )`.
    Site.GROUP_PAREN_OPEN: Spacing(0, 0),        # 12/12 + 13/13
    Site.GROUP_PAREN_CLOSE: Spacing(0, 0),       # 12/12 + 13/13
    Site.INDEX_BRACKET_OPEN: Spacing(0, 0),      # 1002/1002
    Site.INDEX_BRACKET_CLOSE: Spacing(0, 0),
    Site.TYPE_BRACKET_OPEN: Spacing(0, 0),       # 296/299
    Site.TYPE_BRACKET_CLOSE: Spacing(0, 0),
    # `len in [1..4096]` -- the only bracket in PSS with a space before it,
    # and the reason it is a separate site from the index and the width. Those
    # two are 1002/1002 and 333/333 tight; this one is 14/16 spaced, and the
    # same `[` character carries both rules within one declaration:
    # `bit[3] in [2..4]`.
    Site.SET_BRACKET_OPEN: Spacing(1, 0),        # 14/16, 11 files against 2
    Site.SET_BRACKET_CLOSE: Spacing(0, 0),
    # `packed_s<T, 32>` -- a bracket that is not a bracket character, and the
    # most unanimous site measured so far: tight inside on both ends in every
    # one of the 137 argument lists the corpus writes, across 34 files.
    #
    # Its `before` is a *type* meeting its own argument list rather than one
    # token meeting another, which is why 135/137 is quoted for it and not
    # 137/137: two instances write `foo <T>`, in one file.
    #
    # Deliberately not shared with any other site. `<` is TOK_LT, which is
    # also Site.COMPARISON at 128/130 *spaced* -- the same token type with the
    # opposite answer -- so this is the clearest case in the style of why a
    # site is a construct rather than a character. Which one a given `<` is
    # comes from the tree; see `pssfmt.rules.exprs`.
    Site.TEMPLATE_ANGLE_OPEN: Spacing(0, 0),     # before: 135/137; after: 137/137
    Site.TEMPLATE_ANGLE_CLOSE: Spacing(0, 0),    # before: 137/137
    Site.BRACE_OPEN: Spacing(1, 0),              # before: 725/732
    Site.BRACE_CLOSE: Spacing(0, 0),

    Site.COLON_BIT_SLICE: TIGHT,                 # by guide: lowRISC, Verible
    Site.COLON_CASE_ITEM: Spacing(0, 1),         # 214/224
    Site.COLON_INHERITANCE: SPACED,              # 355/358
    Site.COLON_LABEL: SPACED,                    # by preference; humans over generator
})


def _frozen(m: Mapping) -> Mapping:
    """A defensive copy that cannot be mutated through the returned view."""
    return MappingProxyType(dict(m))


@dataclass(frozen=True)
class Style:
    """A fully resolved style policy.

    Immutable, and constructed once per run: by the time a rule sees this,
    every configuration file has been read, every override applied, and every
    question has an answer. Rules therefore never handle a missing value, and
    there is exactly one place -- here -- that knows a default.

    The global fields mirror the v1 configuration keys in ``PLAN.md`` section
    6.7, so ``P4-2`` maps a ``.pssfmt`` file onto this object field by field
    rather than translating. The ``*_overrides`` maps are the per-construct
    machinery those keys sit in front of: empty in v1, populated the day an
    org asks for ``constraint_alignment`` specifically, with no rule changed.
    """

    # -- Global options (PLAN.md section 6.7)
    print_width: int = 80
    indent_width: int = 4
    continuation_indent: int = 4
    use_tabs: bool = False
    brace_style: BraceMode = BraceMode.ATTACH
    max_blank_lines: int = 1
    insert_final_newline: bool = True
    line_ending: LineEnding = LineEnding.AUTO
    alignment: AlignMode = AlignMode.INFER
    alignment_group_boundary: GroupBoundary = GroupBoundary.BLANK_LINES

    # -- Per-construct overrides. Empty in v1; the seam is the accessor, not
    #    the table, so a rule written today needs no change when one fills up.
    indent_overrides: Mapping[Construct, int] = field(default_factory=dict)
    continuation_overrides: Mapping[Construct, int] = field(default_factory=dict)
    brace_overrides: Mapping[Construct, BraceMode] = field(default_factory=dict)
    alignment_overrides: Mapping[Construct, AlignMode] = field(default_factory=dict)
    boundary_overrides: Mapping[Construct, GroupBoundary] = field(default_factory=dict)
    break_overrides: Mapping[Construct, BreakMode] = field(default_factory=dict)
    spacing_overrides: Mapping[Site, Spacing] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.print_width < 1:
            raise ValueError(f"print_width must be positive, got {self.print_width}")
        if self.indent_width < 0:
            raise ValueError(f"indent_width cannot be negative, got {self.indent_width}")
        if self.continuation_indent < 0:
            raise ValueError(
                f"continuation_indent cannot be negative, got {self.continuation_indent}"
            )
        if self.max_blank_lines < 0:
            raise ValueError(
                f"max_blank_lines cannot be negative, got {self.max_blank_lines}"
            )
        for name in (
            "indent_overrides", "continuation_overrides", "brace_overrides",
            "alignment_overrides", "boundary_overrides", "break_overrides",
            "spacing_overrides",
        ):
            object.__setattr__(self, name, _frozen(getattr(self, name)))

    # -- Accessors. Total over their key type: every Construct answers every
    #    construct question, every Site answers spacing. A rule never branches
    #    on whether the policy happens to know.

    def indent_for(self, construct: Construct) -> int:
        """Columns to indent the body of ``construct``."""
        return self.indent_overrides.get(construct, self.indent_width)

    def continuation_for(self, construct: Construct) -> int:
        """Columns to indent a continuation line within ``construct``."""
        return self.continuation_overrides.get(construct, self.continuation_indent)

    def brace_for(self, construct: Construct) -> BraceMode:
        """Where ``{`` goes for ``construct``."""
        return self.brace_overrides.get(construct, self.brace_style)

    def alignment_for(self, construct: Construct) -> AlignMode:
        """How columns within ``construct`` are aligned."""
        return self.alignment_overrides.get(construct, self.alignment)

    def group_boundary_for(self, construct: Construct) -> GroupBoundary:
        """What ends an alignment group within ``construct``."""
        return self.boundary_overrides.get(construct, self.alignment_group_boundary)

    def break_policy_for(self, construct: Construct) -> BreakMode:
        """How ``construct`` relates to line breaking."""
        return self.break_overrides.get(construct, BreakMode.FIT)

    def spacing_for(self, site: Site) -> Spacing:
        """Whitespace immediately around ``site``.

        Raises ``KeyError`` for a site with no default, which can only happen
        if a member was added to :class:`Site` without adding the measured
        value it was added for. ``T-16`` catches that before it reaches here.
        """
        override = self.spacing_overrides.get(site)
        if override is not None:
            return override
        return DEFAULT_SPACING[site]

    def gap(self, left: Site | None, right: Site | None) -> int:
        """Columns of whitespace between two adjacent tokens.

        ``max(left.after, right.before)``, with ``None`` standing for a token
        that is not a style site -- an identifier or a literal -- and
        contributes nothing. See the module docstring for why this is a
        maximum and not a sum.
        """
        after = self.spacing_for(left).after if left is not None else 0
        before = self.spacing_for(right).before if right is not None else 0
        return max(after, before)

    def evolve(self, **changes) -> "Style":
        """A copy with ``changes`` applied. The only way to vary a Style."""
        return replace(self, **changes)


#: The canonical style: what ``pssfmt`` produces with no configuration.
DEFAULT_STYLE = Style()

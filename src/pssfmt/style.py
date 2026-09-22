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

That limit is about *a* site, and the distinction turned out to matter. A
two-token operator gets **two** sites, and the pair says between them what
neither can say alone -- ``Site.SHIFT_RIGHT_OPEN`` and ``SHIFT_RIGHT_CLOSE``
render ``a >> b`` spaced outside and tight between, under exactly the
composition rule above. So the limit is on how much one member can express,
not on which rules are expressible. ``>>`` was declined on the stronger
reading of it, by this docstring and by ``docs/style.rst`` both.

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
    "PackMode",
    "LineEnding",
    "SemicolonMode",
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

    # -- Tier 2: procedural statements (P3-11b)
    MATCH_BODY = "match_body"

    # -- Tier 2: procedural control flow (S-1, S-5)
    IF_BODY = "if_body"
    ELSE_BODY = "else_body"
    LOOP_BODY = "loop_body"

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
    SHIFT = "shift"                            # <<
    IMPLICATION = "implication"                # ->
    UNARY = "unary"                            # + - ! ~
    # `a >> b`. Two members for *one* operator, because PSS has no `>>` token:
    # `shift_op` is `TOK_GT TOK_GT`, two tokens that must be written touching
    # inside an operator that is spaced. See DEFAULT_SPACING.
    SHIFT_RIGHT_OPEN = "shift_right_open"      # the first `>`
    SHIFT_RIGHT_CLOSE = "shift_right_close"    # the second
    # `p ? a : b`. The colon is its own site rather than a fifth reading of
    # COLON_*, because it is not a colon *construct* -- it is the second half
    # of a ternary operator that happens to be spelled with one.
    TERNARY_COND = "ternary_cond"              # ?
    COLON_TERNARY = "colon_ternary"            # :
    VARARGS = "varargs"                        # int... args
    # `**`. Two members for one operator, and the *only* pair in this enum
    # chosen by the shape of what surrounds it rather than by the tokens
    # themselves. See DEFAULT_SPACING.
    EXPONENT = "exponent"                      # x**2
    EXPONENT_WIDE = "exponent_wide"            # base ** f(n)

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
    # `unique {a, b}`, `{1, 2, 3}` -- a brace delimiting a *list*, which is a
    # different construct from a declaration body that happens to share the
    # character. Kept separate for the reason SET_BRACKET is kept separate
    # from INDEX_BRACKET.
    LIST_BRACE_OPEN = "list_brace_open"
    LIST_BRACE_CLOSE = "list_brace_close"
    # `} else {`, `} while (e);` -- a keyword written after a closing brace on
    # the same line. One site because it is one style question asked twice.
    BLOCK_TAIL = "block_tail"

    # -- The colons (docs/style.rst, "Colons: five constructs, five rules")
    COLON_BIT_SLICE = "colon_bit_slice"
    COLON_CASE_ITEM = "colon_case_item"
    COLON_INHERITANCE = "colon_inheritance"
    COLON_LABEL = "colon_label"
    COLON_ITERATOR = "colon_iterator"          # foreach (i : list)


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


class SemicolonMode(str, Enum):
    """What happens to a ``;`` the grammar does not require.

    PSS lets a body item be nothing but a ``;`` -- ``package_body_item``,
    ``struct_body_item``, ``procedural_stmt`` and seven more each carry a bare
    ``TOK_SEMICOLON`` alternative -- so ``struct s { … };`` is a struct
    followed by an empty item, and the ``;`` says nothing. It is a habit
    carried over from C++ and SystemVerilog, where it *is* required.

    This is the only style option that changes the token stream rather than
    the whitespace between tokens, which is why the verifier has to be told
    about it (:func:`pssfmt.verify.verify`).

    :attr:`OMIT` and :attr:`REQUIRE` are near-inverses rather than exact ones,
    and the asymmetry is the difference between a house style and a mess.
    ``omit`` removes any decorative ``;``, including the second one in
    ``int x;;``. ``require`` writes one only after a ``}``, because that is
    what the option is *for* -- ``struct s { … };`` -- and a mode that
    terminated every terminated thing would produce ``int x;;``.
    """

    #: Drop it. The default: 27 of the corpus's 728 declarations are written
    #: with one, in 4 of 92 files, so the majority is not close.
    OMIT = "omit"
    #: Leave the author's semicolons exactly where they are. What ``pssfmt``
    #: did before this option existed.
    PRESERVE = "preserve"
    #: Write one after every declaration that closes with a ``}`` and can
    #: legally take one -- the C++ and SystemVerilog habit, made consistent.
    REQUIRE = "require"


class PackMode(str, Enum):
    """How a list that does not fit distributes its items (``S-16a``).

    Two answers, and they are not variations of one rule -- they are the two
    line-breaking philosophies, and choosing between them is the largest
    single style decision after the width itself::

        never                       bin_pack
        -----                       --------
        f(                          f(alpha, beta,
            alpha,                    gamma);
            beta,
            gamma
        );

    ``NEVER`` is what a :class:`~pssfmt.layout.ir.Group` already means: flat
    if the whole list fits, otherwise **every** separator breaks. ``BIN_PACK``
    is a :class:`~pssfmt.layout.ir.Fill`: break only where the next item does
    not fit.
    """

    #: All or nothing. One item per line when it breaks at all, so a diff
    #: touching one argument touches one line.
    NEVER = "never"
    #: Greedy packing -- LLVM's shape, and clang-format's ``BinPackArguments``
    #: default. Fewer lines; a diff touching one argument can reflow the rest.
    BIN_PACK = "bin_pack"


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
    # Ratified by `S-11`, and the label matters: these are **argued**, from
    # lowRISC's "whitespace on both sides of all binary operators", not
    # measured. 14 instances between them is not a measurement, and a value
    # nobody chose should not go on looking like one somebody counted.
    Site.BITWISE: SPACED,                        # argued: binary-operator rule
    Site.SHIFT: SPACED,                          # argued: binary-operator rule
    # ...except this one, which was defaulted and then measured, and the
    # difference is the whole reason the two labels are kept apart.
    Site.IMPLICATION: SPACED,                    # 6/6, across 5 files
    Site.UNARY: Spacing(0, 0),                   # after: 92/92

    # `a >> b`, spaced outside and tight between -- from *two* sites, because
    # one cannot say it. The module docstring above notes that a site cannot
    # force tightness against a spaced neighbour, and that is true of a site;
    # it is not true of a pair. Composed by `max(left.after, right.before)`:
    #
    #     a  >>  b        gap(None, OPEN)  = max(0, 1) = 1
    #      ^^  ^^         gap(OPEN, CLOSE) = max(0, 0) = 0
    #                     gap(CLOSE, None) = max(1, 0) = 1
    #
    # Same shape as TEMPLATE_ANGLE_OPEN/CLOSE, and argued rather than
    # measured: one instance in the corpus, and the value is `SHIFT`'s read
    # across the pair.
    Site.SHIFT_RIGHT_OPEN: Spacing(1, 0),        # argued; see Site.SHIFT
    Site.SHIFT_RIGHT_CLOSE: Spacing(0, 1),       # argued; see Site.SHIFT

    # `p ? a : b` -- argued from the general binary-operator rule, with the
    # Linux kernel's "binary *and ternary* operators" as the named peer. The
    # corpus contains no ternary at all, so there is nothing here to measure
    # and this says so rather than quoting a count from a neighbour.
    Site.TERNARY_COND: SPACED,                   # argued; no corpus instances
    Site.COLON_TERNARY: SPACED,                  # argued; no corpus instances

    # `function void f(int... args)`. Argued from C's
    # `printf(const char *fmt, ...)` -- tight against the type, one space
    # before the name -- and **not** from the comma's shape, though the value
    # is the same. `pssfmt.rules.procedural` names borrowing the comma's
    # number as the trap this site had to avoid: a site invented from a single
    # instance looks measured, and the corpus has exactly one varargs
    # parameter. The number is not the claim; where it came from is.
    Site.VARARGS: Spacing(0, 1),                 # argued; 1 corpus instance

    # `x**2` tight, `base ** f(n)` spaced -- Black's rule, and the one place
    # in this tool where a gap depends on the *shape* of the operands rather
    # than on token adjacency. Argued: 65 corpus instances, all one author's,
    # all tight with simple operands, so the corpus cannot distinguish this
    # rule from "always tight" and the spaced branch has no evidence at all.
    #
    # Two sites rather than one operand-aware site, so the concession is
    # contained: which of them applies comes from the tree via `sites_at`,
    # exactly as it does for TEMPLATE_ANGLE_* against COMPARISON. Everything
    # downstream of `pssfmt.rules.exprs._exponent_sites` is ordinary.
    Site.EXPONENT: TIGHT,                        # argued; 65/65 with simple operands
    Site.EXPONENT_WIDE: SPACED,                  # argued; 0 corpus instances

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
    # `component c {` and `enum e { A, B }`. The `before` is the one every
    # declaration exercises. The other two sides were **placeholders until
    # `P3-12`** and are worth flagging as such: all 733 corpus braces open a
    # body that breaks, so nothing followed a `{` on the same line and nothing
    # preceded a `}` -- `BRACE_CLOSE` was referenced by no rule at all. An
    # inline `enum` is the first construct where either is observable, and it
    # says spaced: 7 of 10 across 5 files, against 3 in 2 files that are both
    # the published 3.1 standard library. Five voices to one, which is the
    # same shape as `MULTIPLICATIVE`'s split and decided the same way.
    Site.BRACE_OPEN: Spacing(1, 1),              # before: 725/732; after: 7/10
    Site.BRACE_CLOSE: Spacing(1, 0),             # before: 7/10
    # `unique {a, b};` and `{1, 2, 3}` -- tight inside. Argued (`S-12`): one
    # `unique` and two aggregate literals, in three files, which is not a
    # measurement. The reason it is not simply BRACE_OPEN's 7/10 is that that
    # number was measured on **declaration bodies**, and a list is not one:
    # every list-like construct already measured in PSS is tight inside --
    # `f(a, b)` 765/767, `packed_s<T, 32>` 137/137, `[1..4096]` 18/18 -- so
    # borrowing the body's answer here would make a list the one exception.
    Site.LIST_BRACE_OPEN: Spacing(1, 0),         # argued; 3 corpus instances
    Site.LIST_BRACE_CLOSE: Spacing(0, 0),        # argued; 3 corpus instances
    # `} else {` -- cuddled. Argued (`S-1`): 5 if/else in 3 files is not a
    # measurement, and the corpus is not unanimous. Every comparable guide
    # is: K&R, the Linux kernel ("put the closing brace last, followed by
    # `else`"), Google C++, and lowRISC all write `} else {`. Allman does not
    # occur anywhere in this corpus, so the shape it would need is not one
    # any voice here is asking for.
    Site.BLOCK_TAIL: SPACED,                     # argued; 5 corpus instances

    Site.COLON_BIT_SLICE: TIGHT,                 # by guide: lowRISC, Verible
    Site.COLON_CASE_ITEM: Spacing(0, 1),         # 214/224
    Site.COLON_INHERITANCE: SPACED,              # 355/358
    Site.COLON_LABEL: SPACED,                    # by preference; humans over generator
    # `foreach (i : list)`, `repeat (i : 4)`. Argued (`S-5`): one instance in
    # the corpus, and it is the *colon-less* `foreach (chans[i])` spelling, so
    # there is nothing here to measure at all. Spaced because that is what the
    # construct is -- C++'s range-`for` writes `for (auto x : xs)`, the
    # inheritance colon beside it is 355/358 spaced, and lowRISC asks for a
    # space either side of a colon that labels rather than delimits.
    Site.COLON_ITERATOR: SPACED,                 # argued; 0 corpus instances
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
    optional_semicolon: SemicolonMode = SemicolonMode.OMIT
    alignment: AlignMode = AlignMode.INFER
    alignment_group_boundary: GroupBoundary = GroupBoundary.BLANK_LINES
    #: How a list that does not fit distributes its items (``S-16a``).
    #:
    #: ``never`` -- all or nothing. The corpus cannot decide this: it contains
    #: no wrapped argument list that a rule reaches, because every construct
    #: holding one was declined until this item. So it is argued, and the
    #: argument is about diffs rather than about density -- an all-or-nothing
    #: list changes one line when one argument changes, and a packed list can
    #: reflow every line after it. `prettier`, `rustfmt` and `black` all
    #: chose this way; `clang-format`'s LLVM style did not, which is why the
    #: other answer is an option and not an opinion.
    pack_arguments: PackMode = PackMode.NEVER
    #: Where a broken list's items line up (``S-16b``).
    #:
    #: ``False`` indents them by ``continuation_indent`` from the line that
    #: opened the list. ``True`` aligns them under the character after the
    #: open bracket, which is clang-format's ``AlignAfterOpenBracket: Align``.
    #:
    #: Argued the same way and for the same reason: continuation indent
    #: survives a rename of the callee, and open-paren alignment re-indents
    #: every continuation line when the name before the bracket changes width.
    align_after_open_bracket: bool = False
    #: Columns before a trailing ``// comment`` (``S-18``).
    #:
    #: A **floor**, not a replacement, and the distinction is the whole of the
    #: option's design. ``decls._trailing`` carries the *author's* gap through
    #: to the alignment pass, because by then the source is gone and that gap
    #: is the only evidence a block was a deliberate table. This raises the
    #: floor under it; it never overwrites a wider one. Overwriting would make
    #: ``infer`` unable to infer, and every hand-built comment column would
    #: collapse while looking considered.
    #:
    #: Default 1, which is the status quo and what the corpus writes for a
    #: comment that is not part of a column. Exposed because two spaces is a
    #: house style with real backing -- Google's C++ guide asks for it -- and
    #: nothing about it is derivable from PSS.
    spaces_before_trailing_comment: int = 1

    # -- Per-construct overrides. Empty in v1; the seam is the accessor, not
    #    the table, so a rule written today needs no change when one fills up.
    indent_overrides: Mapping[Construct, int] = field(default_factory=dict)
    continuation_overrides: Mapping[Construct, int] = field(default_factory=dict)
    brace_overrides: Mapping[Construct, BraceMode] = field(default_factory=dict)
    alignment_overrides: Mapping[Construct, AlignMode] = field(default_factory=dict)
    boundary_overrides: Mapping[Construct, GroupBoundary] = field(default_factory=dict)
    break_overrides: Mapping[Construct, BreakMode] = field(default_factory=dict)
    semicolon_overrides: Mapping[Construct, SemicolonMode] = field(default_factory=dict)
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
        if self.spaces_before_trailing_comment < 1:
            # One, not zero: `int x;// why` is legal and unreadable, and a
            # floor of zero would make the option able to produce it.
            raise ValueError(
                "spaces_before_trailing_comment must be at least 1, got "
                f"{self.spaces_before_trailing_comment}"
            )
        for name in (
            "indent_overrides", "continuation_overrides", "brace_overrides",
            "alignment_overrides", "boundary_overrides", "break_overrides",
            "semicolon_overrides", "spacing_overrides",
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
        """How ``construct`` relates to line breaking.

        The global default follows ``pack_arguments``: ``never`` is a
        ``Group`` (``FIT``) and ``bin_pack`` is a ``Fill``. Per-construct
        overrides still win.

        :data:`_FILLED` is the one construct that does not follow it, and it
        is not an exception invented here -- :class:`BreakMode` has said
        ``RANGE_LIST`` wants ``FILL`` since ``P3-5``, and ``formatter.md``
        section 3.2 argued for it before that. ``S-16a`` decided how an
        *argument* list distributes, which is a question about a list of
        expressions; a range list is a list of numbers, and one number per
        line turns ``in [0..7, 16, 32..63]`` written across 64 constants into
        64 lines.
        """
        if construct in _FILLED:
            default = BreakMode.FILL
        else:
            default = (BreakMode.FILL
                       if self.pack_arguments is PackMode.BIN_PACK
                       else BreakMode.FIT)
        return self.break_overrides.get(construct, default)

    def optional_semicolon_for(self, construct: Construct) -> SemicolonMode:
        """What to do with a ``;`` this body does not require."""
        return self.semicolon_overrides.get(construct, self.optional_semicolon)

    def _any_semicolon_mode(self, mode: SemicolonMode) -> bool:
        return (self.optional_semicolon is mode
                or any(m is mode for m in self.semicolon_overrides.values()))

    def drops_optional_semicolons(self) -> bool:
        """Whether *any* body may lose a ``;``.

        The verifier's question, and the reason it is asked of the whole style
        rather than of a construct: token equivalence is checked over the
        file, so the exemption has to be decided before anything knows which
        construct a given token sat in. ``True`` here does not mean a
        semicolon *will* go, only that one is allowed to.
        """
        return self._any_semicolon_mode(SemicolonMode.OMIT)

    def adds_optional_semicolons(self) -> bool:
        """Whether *any* body may gain a ``;``. The other half of the above."""
        return self._any_semicolon_mode(SemicolonMode.REQUIRE)

    def rewrites_optional_semicolons(self) -> bool:
        """Whether the two texts may differ in ``;`` at all, either way.

        What :mod:`pssfmt.ranges` needs: its cut points are computed over an
        alphabet, and the alphabet is the same whichever direction the option
        moves the semicolons in.
        """
        return self.drops_optional_semicolons() \
            or self.adds_optional_semicolons()

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


#: Constructs whose break policy is ``FILL`` regardless of ``pack_arguments``.
#: See :meth:`Style.break_policy_for`.
_FILLED = frozenset({Construct.RANGE_LIST})

#: The canonical style: what ``pssfmt`` produces with no configuration.
DEFAULT_STYLE = Style()

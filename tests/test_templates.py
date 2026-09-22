"""``T-26`` -- template argument lists (``P3-7``).

``PLAN.md`` lists five things under ``P3-7``. Measured against the corpus,
four of them are a rounding error and the fifth is the single largest thing
the formatter was declining to do:

=========================== ========== =======
construct                    instances   files
=========================== ========== =======
template arguments ``<T,N>``       137      34
``covergroup`` bodies                9       2
``bins`` specifications              7       1
``compile if``                       1       1
``@`` annotations                    5       1
``pyimport``                         0       0
=========================== ========== =======

So this file tests template arguments, and the decline tests at the bottom
are the record of the rest. Before this item, ``<`` caused **131 of the
formatter's 155 declined spans**, across 32 of the 92 files; after it, 5.

Why the angle bracket is the interesting one
--------------------------------------------
Every other bracket in PSS is punctuation that is only ever a bracket. ``<``
is ``TOK_LT``, which is also the comparison operator, and the two have
*opposite* measured answers -- ``a < b`` is spaced 128/130, ``packed_s<T, 32>``
is tight 137/137. There is no default that is not wrong half the time, so the
answer comes from the tree, and a ``<`` the walk cannot account for declines
the whole span rather than guessing. Both halves of that are tested here.

The other half of the item is a decline that had to be *positive*: template
parameter **declarations** share the bracket and are a different construct
with different evidence (7/16 tight, because 5 of the 16 put the parameter on
its own line). They must keep declining even though their tokens are now in
the vocabulary, and they do -- by having no site, not by a check.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.rules import format_source  # noqa: E402
from pssfmt.style import Site, Spacing, Style  # noqa: E402
from pssfmt.verify import verify  # noqa: E402

pytestmark = pytest.mark.unit


def fmt(src: str, style: Style = None) -> str:
    return format_source(src, style=style) if style else format_source(src)


# ---------------------------------------------------------------------------
# The shape the corpus has
# ---------------------------------------------------------------------------


class TestArgumentsAreTight:
    """137/137 on both ends, across 34 files. Nothing in the corpus disagrees."""

    def test_a_single_argument(self):
        assert fmt("package p {\n    struct s : base_s < T > {\n"
                   "        int x;\n    }\n}\n") == (
               "package p {\n    struct s : base_s<T> {\n"
               "        int x;\n    }\n}\n")

    def test_several_arguments_take_the_comma_site(self):
        """``,`` is ``Site.COMMA`` -- measured elsewhere, and it agrees here.

        122 of the corpus's 127 inter-argument gaps are one space, which is
        what ``Site.COMMA`` already said at 355/362. A construct that agrees
        with a site measured somewhere else is the cheapest kind of evidence
        there is, and worth keeping a test on precisely because nothing had
        to be invented for it.
        """
        assert fmt("package p {\n    struct s : base_s<a ,b,  c> {\n"
                   "        int x;\n    }\n}\n") == (
               "package p {\n    struct s : base_s<a, b, c> {\n"
               "        int x;\n    }\n}\n")

    def test_an_empty_list(self):
        """``packed_s<>`` -- 17 instances in 7 files, and it is real PSS."""
        assert fmt("package p {\n    struct s : packed_s < > {\n"
                   "        int x;\n    }\n}\n") == (
               "package p {\n    struct s : packed_s<> {\n"
               "        int x;\n    }\n}\n")

    def test_the_type_meets_its_argument_list_tightly(self):
        """135/137 write ``foo<T>``; two files write ``foo <T>``."""
        assert fmt("package p {\n    struct s : base_s <T> {\n"
                   "        int x;\n    }\n}\n") == (
               "package p {\n    struct s : base_s<T> {\n"
               "        int x;\n    }\n}\n")

    def test_a_literal_argument(self):
        """67 of the corpus's arguments are integers rather than names."""
        assert fmt("package p {\n    struct s : packed_s<bit, 32> {\n"
                   "        int x;\n    }\n}\n") == (
               "package p {\n    struct s : packed_s<bit, 32> {\n"
               "        int x;\n    }\n}\n")

    def test_a_field_declaration_gets_the_same_answer(self):
        """A template type is a type wherever it appears.

        The header and the field go through different rule modules with
        different vocabularies, and they reach the same site through the same
        tree walk. If they ever disagree, this is the test that says so.
        """
        assert fmt("component c {\n    wrapper_s < T , 8 > w;\n}\n") == (
               "component c {\n    wrapper_s<T, 8> w;\n}\n")


class TestTheAngleBracketIsNotTheComparison:
    """One token type, two constructs, opposite answers. The point of ``P3-7``."""

    def test_a_comparison_stays_spaced(self):
        assert fmt("component c {\n    bit x = a<b;\n}\n") == (
               "component c {\n    bit x = a < b;\n}\n")

    def test_both_in_one_file(self):
        """Neither reading leaks into the other."""
        src = ("component c {\n"
               "    wrapper_s<T, 8> w;\n"
               "    bit ok = a < b;\n"
               "}\n")
        assert fmt(src) == src

    def test_the_style_can_move_them_independently(self):
        """A style that spaces template arguments does not touch comparisons.

        This is the test that would fail if the two constructs had been given
        one site because their characters match. It asserts the *separation*,
        not the numbers: what matters is that moving one leaves the other
        where it was.
        """
        style = Style(spacing_overrides={
            Site.TEMPLATE_ANGLE_OPEN: Spacing(0, 1),
            Site.TEMPLATE_ANGLE_CLOSE: Spacing(1, 0)})
        out = fmt("component c {\n    wrapper_s<T, 8> w;\n"
                  "    bit ok = a < b;\n}\n", style)
        assert "wrapper_s< T, 8 > w;" in out
        assert "a < b;" in out


class TestTheSeamAfterTheClosingAngle:
    """``packed_s<T, 32> hdr`` -- a type meeting the name it declares."""

    def test_a_declarator_keeps_its_space(self):
        """Without the floor this is ``wrapper_s<T, 8>w``.

        Which still lexes as two tokens, so token equivalence passes and
        nothing in the verifier complains -- the same way ``bit[3]in [2..4]``
        once shipped. The floor is the only thing standing here.

        The input is written *without* the space rather than with too many,
        so that what is being tested is the floor and not the alignment pass:
        a lone padded line is reproduced by ``infer`` whatever the floor says.
        """
        assert fmt("component c {\n    wrapper_s<T, 8>w;\n}\n") == (
               "component c {\n    wrapper_s<T, 8> w;\n}\n")

    def test_the_floor_does_not_fire_on_a_comparison(self):
        """The reason the seam asks for the *site* rather than the character.

        ``>`` is ``TOK_GT`` in ``a > b`` too. A floor keyed on the token type
        would claim a type boundary there and force a space -- invisible
        today, because comparisons are spaced anyway, and wrong the moment a
        style says otherwise. So the style says otherwise here.
        """
        style = Style(spacing_overrides={Site.COMPARISON: Spacing(0, 0)})
        assert "ok = a>b;" in fmt("component c {\n    bit ok = a > b;\n}\n", style)

    def test_a_scope_resolution_stays_tight(self):
        """``foo<T>::bar`` -- the seam must not fire before ``::`` either."""
        src = "component c {\n    wrapper_s<T>::inner_s w;\n}\n"
        assert fmt(src) == src


class TestNestingLexesBack:
    """``a<b<c>>`` is safe, and it is worth knowing *why* rather than assuming.

    PSS has no ``>>`` token: ``shift_op`` is two ``TOK_GT``. So writing the
    two closers adjacent cannot merge, and ``must_separate`` says so from the
    real lexeme table rather than from a hand-written list. The corpus has no
    nested template at all, so this is the case with no measurement behind it
    -- which is exactly why it gets a token-equivalence check and not just an
    expectation.
    """

    def test_the_closers_may_touch(self):
        assert fmt("package p {\n    struct s : a< b< c > > {\n"
                   "        int x;\n    }\n}\n") == (
               "package p {\n    struct s : a<b<c>> {\n"
               "        int x;\n    }\n}\n")

    def test_and_the_output_still_lexes_the_same(self):
        src = ("package p {\n    struct s : a< b< c > > {\n"
               "        int x;\n    }\n}\n")
        violations = list(verify(src, fmt(src)))
        assert not violations, violations


# ---------------------------------------------------------------------------
# What it declines, and why each
# ---------------------------------------------------------------------------


class TestItDeclinesRatherThanGuesses:

    def test_a_bracket_inside_the_arguments_declines_the_header(self):
        """``packed_s<bit[8], 4>`` -- 6 instances in 4 files, and left alone.

        Not an oversight and not laziness: the header vocabulary's ``:`` is
        ``Site.COLON_INHERITANCE`` because *no span of those tokens can
        contain a ``[```. A template argument is a constant expression, so
        admitting the bracket makes ``s<A[3:0]>`` spellable and a bit-slice
        colon reachable in a vocabulary that has no site for one. Six
        instances do not buy that. See ``P3-7a``.
        """
        src = ("package p {\n    struct s : packed_s<bit[8],  4> {\n"
               "        int x;\n    }\n}\n")
        assert fmt(src) == src

    def test_declining_the_header_leaves_the_body_alone_too(self):
        """A declined header is not a declined declaration.

        Worth pinning because the two are separate returns in ``_header`` and
        it would be easy to make the outer one bail as well -- which would
        silently un-format every member of six files.

        The member's gap is one the alignment pass has no say in -- a space
        before ``;`` is never a column -- so this asks about the rule and not
        about ``infer``. Two members padded to the same width *would* be a
        column, and would pass while the body went unformatted.
        """
        out = fmt("package p {\n    struct s : packed_s<bit[8], 4> {\n"
                  "        int x ;\n    }\n}\n")
        assert "int x;" in out
        assert "packed_s<bit[8], 4>" in out

    def test_the_body_cannot_veto_the_header(self):
        """A header asks its *own* children about sites, not the whole tree.

        ``sites_for`` refuses a subtree containing a construct it declines --
        ``a**2`` is one -- and a declaration node's children include every
        member of its body. Asking the declaration would therefore let one
        ``**`` anywhere inside a package silently un-format the header of the
        thing containing it, and the corpus has ``**`` in two files.

        It would also be quadratic, which is the lesser of the two problems
        and the easier one to notice.
        """
        assert fmt("package p {\n    struct s : base_s < T > {\n"
                   "        int x = a**2;\n    }\n}\n") == (
               "package p {\n    struct s : base_s<T> {\n"
               "        int x = a**2;\n    }\n}\n")

    def test_an_annotation_is_left_alone(self):
        """``@`` -- one voice, and the second file holding one is the
        deliberately-invalid ``pathological/invalid_tokens.pss``. ``P3-7``
        measured five real instances in a single file; ``docs/style.rst``
        already refuses to decide a site on one voice."""
        src = ("package p {\n    @desc_c {.text = \"x\"}\n"
               "    struct s {\n        int x;\n    }\n}\n")
        assert fmt(src) == src

    def test_a_compile_if_is_left_alone(self):
        """One instance in the corpus -- and the *correctness* requirement
        ``PLAN.md`` states for it is already met.

        The plan asks that both branches be formatted and the condition never
        evaluated. The unregistered fallback does both, trivially and by
        construction: it copies the tokens. A rule is what would put that
        property at risk, so a rule is what needs evidence to justify, and one
        instance is not it.
        """
        src = ("component c {\n    compile if (config_pkg::FAST) {\n"
               "        int  x;\n    }\n}\n")
        assert fmt(src) == src


class TestNoTokenIsEverLost:
    """Token equivalence over every shape above, including the declined ones."""

    @pytest.mark.parametrize("src", [
        "package p {\n    struct s : base_s < T > {\n        int x;\n    }\n}\n",
        "package p {\n    struct s : packed_s<> {\n        int x;\n    }\n}\n",
        "package p {\n    struct s : packed_s<bit[8], 4> {\n"
        "        int x;\n    }\n}\n",
        "package p {\n    struct base_s <struct TRAIT : t_s = e_s> {\n"
        "        int x;\n    }\n}\n",
        "component c {\n    wrapper_s<T, 8>  w;\n    bit ok = a < b;\n}\n",
        "component c {\n    wrapper_s<T>::inner_s w;\n}\n",
    ])
    def test_the_tokens_survive(self, src):
        violations = list(verify(src, fmt(src)))
        assert not violations, violations


# ---------------------------------------------------------------------------
# What formatting them for the first time made visible
# ---------------------------------------------------------------------------


class TestAlignmentAcrossANewlyFormattedLine:
    """The corpus's two diffs, both of them the alignment pass, both correct.

    Formatting a construct for the first time gives its line a *neighbour* it
    did not have: a declined line keeps the author's spacing verbatim, so a
    stray gap on it survives regardless of what the lines around it do. Once
    the line is emitted, ``infer`` gets to ask whether the gap is a column,
    and answers with the evidence rather than the intent.

    Both directions are pinned. Without the first test the alignment pass
    could be deleted and the corpus would look better, not worse.
    """

    def test_a_real_column_survives(self):
        src = ("component c {\n"
               "    wrapper_s<>                  w_default;\n"
               "    wrapper_s<base_payload_s, 8> w_eight;\n"
               "}\n")
        assert fmt(src) == src

    def test_a_near_miss_is_not_a_column(self):
        """One column short of lining up, which is the case ``infer`` exists
        to catch. Both corpus diffs ``P3-7`` produced are this."""
        assert fmt("component c {\n"
                   "    wrapper_s<>                 w_default;\n"
                   "    wrapper_s<base_payload_s, 8> w_eight;\n"
                   "}\n") == (
               "component c {\n"
               "    wrapper_s<> w_default;\n"
               "    wrapper_s<base_payload_s, 8> w_eight;\n"
               "}\n")

    def test_a_templated_type_can_carry_the_column(self):
        """The seam stop has to land at the declarator, not at the ``<``.

        ``_column_stops`` takes its seams from rule boundaries, and a
        templated type ends at a ``>`` rather than at an identifier. If the
        stop were derived from tokens instead, this table would break at the
        first template.
        """
        src = ("component c {\n"
               "    packed_s<bit, 8>   a;\n"
               "    transparent_c<>    b;\n"
               "    int                d;\n"
               "}\n")
        assert fmt(src) == src


class TestTheGapsComeFromTheStyle:
    """No spacing constant is written in the rule module. ``T-13``'s property,
    applied to the two sites this item added."""

    def test_spacing_the_brackets_moves_the_output(self):
        style = Style(spacing_overrides={
            Site.TEMPLATE_ANGLE_OPEN: Spacing(1, 1),
            Site.TEMPLATE_ANGLE_CLOSE: Spacing(1, 1)})
        assert "base_s < T > " in fmt(
            "package p {\n    struct s : base_s<T> {\n        int x;\n    }\n}\n",
            style)

    def test_the_comma_site_reaches_the_arguments(self):
        style = Style(spacing_overrides={Site.COMMA: Spacing(1, 1)})
        assert "base_s<a , b>" in fmt(
            "package p {\n    struct s : base_s<a, b> {\n"
            "        int x;\n    }\n}\n",
            style)


class TestTheDeclaringSide:
    """``T-50`` -- ``S-7``. Template parameter *declarations*.

    ``docs/style.rst`` left these alone in as many words: 16 instances in 5
    files, and *they do not agree* -- 7 of 16 are tight after the ``<``
    because 5 of the rest put the parameter on a line of its own. That is not
    a split about the angle brackets; it is a split about **line breaking**,
    and the two halves were separated by giving the list a break policy
    (``S-16``) and then deciding the spacing here.

    Every gap this construct needs was already measured on something else:
    the angles from the argument list (137/137 tight), the bound colon from
    inheritance (355/358 spaced), the default ``=`` from ``Site.ASSIGN``
    (271/319). Not one new site.
    """

    @pytest.mark.parametrize("src,expected", [
        ("struct s <type T> {", "struct s<type T> {"),
        ("struct s < type T , int N > {", "struct s<type T, int N> {"),
        ("struct s<int W=8> {", "struct s<int W = 8> {"),
    ], ids=["spaced-angle", "wide", "default"])
    def test_the_angles_take_the_argument_list_s_rule(self, src, expected):
        out = fmt("package p {\n    %s\n        int x;\n    }\n}\n" % src)
        assert "    " + expected in out

    def test_the_bound_colon_takes_the_inheritance_rule(self):
        """``struct TRAIT : addr_trait_s`` -- and it is not a sixth reading
        of ``:``. What follows a bound colon is the type the parameter is
        bounded by, which is what an inheritance colon separates too."""
        out = fmt("package p {\n"
                  "    struct base_s <struct TRAIT:addr_trait_s = e_s> {\n"
                  "        int x;\n    }\n}\n")
        assert "    struct base_s<struct TRAIT : addr_trait_s = e_s> {" in out

    def test_a_declaration_and_a_use_agree(self):
        """The point of sharing the site rather than inventing one: the two
        sides of the same template come out the same shape."""
        out = fmt("package p {\n"
                  "    struct base_s <type T> {\n        int x;\n    }\n"
                  "    struct d_s : base_s <int> {\n        int y;\n    }\n}\n")
        assert "struct base_s<type T> {" in out
        assert "struct d_s : base_s<int> {" in out

    def test_a_comparison_elsewhere_stays_spaced(self):
        """``<`` is ``TOK_LT`` and so is a comparison. Same token type,
        opposite measured answers, and the tree is what tells them apart."""
        out = fmt("package p {\n    struct s <int W> {\n"
                  "        bool b = a < W;\n    }\n}\n")
        assert "struct s<int W> {" in out
        assert "bool b = a < W;" in out

    def test_a_long_parameter_list_breaks(self):
        """``S-16``'s half of the item, and the reason ``S-7`` had to wait
        for it: 5 of the corpus's 16 put each parameter on its own line, and
        joining those without a break policy is what ``P3-11a`` refused to
        do to a wrapped prototype."""
        out = fmt("package p {\n"
                  "    struct addr_claim_s <struct TRAIT : addr_trait_s = "
                  "empty_addr_trait_s, type U = int> {\n"
                  "        int x;\n    }\n}\n")
        assert "    struct addr_claim_s<\n" in out
        assert "        struct TRAIT : addr_trait_s = empty_addr_trait_s,\n" in out
        assert "\n    > {\n" in out

    def test_a_header_with_two_lists_keeps_the_author_s_wrap(self):
        """``emit_span`` takes one wrap, and this header has two -- the
        parameter list and the base type's argument list. Joining it would
        make a 108-column line with nowhere to break, so the author's line
        stands. Worse than a rule, better than a violated width."""
        src = ("package p {\n"
               "    struct transparent_addr_claim_s<\n"
               "            struct TRAIT : addr_trait_s = empty_addr_trait_s>"
               " : addr_claim_s<TRAIT> {\n"
               "        rand bit[64] addr;\n"
               "    }\n}\n")
        assert "    struct transparent_addr_claim_s<\n" in fmt(src)

    def test_a_short_header_the_author_wrapped_is_still_joined(self):
        """The guard is about width, not about wrapping. Joining a wrapped
        header is what ``P3-2b`` built this path for."""
        out = fmt("package p {\n    struct s\n    <type T>\n    {\n"
                  "        int x;\n    }\n}\n")
        assert "    struct s<type T> {" in out

    def test_it_is_idempotent(self):
        src = ("package p {\n    struct base_s <struct TRAIT : t_s = e_s> {\n"
               "        int x;\n    }\n}\n")
        once = fmt(src)
        assert fmt(once) == once

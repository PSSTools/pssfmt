"""``T-22`` -- field declarations and column alignment (``P3-3``, ``P2-8``).

Two things landed together because one could not ship without the other. The
field rules reformat 506 of the corpus's body members; without an alignment
pass they would also flatten every hand-built table in it, which
``docs/style.rst`` commits to preserving. So the tests come in two halves:
what a field declaration looks like, and what happens to a block of them.

The alignment half is the more interesting one, because its failure mode is
not a crash or a lost token. It is a large, plausible-looking diff that
destroys deliberate work, and nothing about the output says anything went
wrong.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.rules import format_source  # noqa: E402
from pssfmt.rules import stmts  # noqa: E402
from pssfmt.style import AlignMode, Site, Spacing, Style  # noqa: E402
from pssfmt.verify import verify  # noqa: E402

pytestmark = pytest.mark.unit


def fmt(src: str, style: Style = None) -> str:
    return format_source(src, style=style) if style else format_source(src)


def in_struct(*body: str) -> str:
    return "struct s {\n" + "".join("    %s\n" % b for b in body) + "}\n"


# ---------------------------------------------------------------------------
# The declaration itself
# ---------------------------------------------------------------------------


class TestNormalisation:
    @pytest.mark.parametrize("src,expected", [
        ("rand  bit en ;", "rand bit en;"),
        ("bit [ 64 ] addr ;", "bit[64] addr;"),
        ("mem_c :: fill_a f ;", "mem_c::fill_a f;"),
        ("static  const  int N=8 ;", "static const int N = 8;"),
        ("int a , b ;", "int a, b;"),
        ("bit chan [ 4 ] ;", "bit chan[4];"),
    ], ids=["modifiers", "width", "scoped-type", "const", "two-declarators",
            "array-dim"])
    def test_a_field_is_written_out(self, src: str, expected: str):
        assert fmt(in_struct(src)) == in_struct(expected)

    def test_a_lone_line_keeps_the_padding_at_its_column_stops(self):
        """A consequence of ``infer``, stated rather than discovered later.

        The gap before the declarator is a column stop, and ``infer`` does not
        touch a stop it has no run to judge -- one line is not a ragged block,
        it is no evidence. So ``int  x;`` keeps its second space while every
        *other* gap on the line is normalised.

        This is the same rule that leaves a lone trailing comment alone, and
        it is applied to both rather than being special-cased to the one where
        padding is obviously deliberate. It costs nothing measurable: the
        corpus contains no such line.
        """
        assert fmt(in_struct("rand  bit  en ;")) == in_struct("rand bit  en;")

    def test_a_width_bracket_is_tight_but_the_name_is_not(self):
        """``bit[64] x`` -- the gap the style cannot express on its own.

        ``max(left.after, right.before)`` gives zero here: ``]`` has no
        ``after`` worth setting (it would put a space in ``a[i];``) and an
        identifier has no ``before`` at all. The space marks a *type* meeting
        a *declarator*, which only the rule knows, so the rule supplies it.
        """
        out = fmt(in_struct("bit[64] addr;"))
        assert "bit[64] addr;" in out
        assert "bit[64]addr" not in out

    def test_a_bind_wildcard_keeps_its_space(self):
        """``bind chan_p *`` -- the other gap with no site behind it."""
        src = "component c {\n    bind chan_p *;\n}\n"
        assert fmt(src) == src


class TestTheGapsComeFromTheStyle:
    def test_the_assignment_gap_follows_its_site(self):
        style = Style(spacing_overrides={Site.ASSIGN: Spacing(0, 0)})
        assert fmt(in_struct("int n = 8;"), style) == in_struct("int n=8;")

    def test_the_comma_gap_follows_its_site(self):
        style = Style(spacing_overrides={Site.COMMA: Spacing(0, 0)})
        assert fmt(in_struct("int a, b;"), style) == in_struct("int a,b;")

    def test_a_zero_everywhere_style_still_emits_valid_tokens(self):
        style = Style(spacing_overrides={site: Spacing(0, 0) for site in Site})
        src = in_struct("rand bit[64] addr;", "static const int N = 8;")
        violations = list(verify(src, fmt(src, style)))
        assert not violations, violations


class TestItDeclinesRatherThanGuesses:
    """Everything past the ``=`` that is not a single value belongs elsewhere.

    Each of these asserts the author's text comes back unchanged, which is the
    point: the boundary costs nothing that was not already the case.
    """

    @pytest.mark.parametrize("src", [
        "rand int in [1..4] n;",
        "array<bit[8], 3> sizes = {1, 2, 3};",
        "bit[31:0] e;",
        "rand transparent_addr_claim_s<> mem;",
    ], ids=["inline-constraint", "aggregate", "bit-slice", "template-args"])
    def test_it_is_reproduced(self, src: str):
        assert fmt(in_struct(src)) == in_struct(src)

    def test_an_expression_default_is_no_longer_one_of_these(self):
        """``P3-4`` moved this case across the boundary, and the assertion
        moved with it rather than being deleted.

        A default that was an expression used to be reproduced because ``+``
        was not in the vocabulary. It is now written out, which means the
        case that used to prove the *boundary* now proves the opposite -- and
        an unchanged ``==`` assertion would keep passing either way, because
        canonical input formats to itself. ``T-23`` owns expressions; this
        checks only that they reach the field rules at all.
        """
        assert fmt(in_struct("static const int N = A+B*C;")) == in_struct(
            "static const int N = A + B * C;")

    def test_a_target_template_default_is_never_touched(self):
        """A triple-quoted payload must not be re-anchored (§4.7.1.2)."""
        src = 'struct s {\n    string t = """\nliteral\n""";\n}\n'
        assert "\nliteral\n" in fmt(src)

    def test_a_pool_declaration_is_not_ours(self):
        """``pool [4]`` is unanimous in the corpus; ``INDEX_BRACKET_OPEN``
        was measured on 1002 index expressions and says tight. Applying it
        here would overrule the construct's own evidence."""
        src = "component c {\n    pool [4] dma_chan_s chan_p;\n}\n"
        assert fmt(src) == src

    def test_an_interior_comment_is_left_alone(self):
        src = in_struct("static const int nbits = /* why */ 1;")
        assert fmt(src) == src


# ---------------------------------------------------------------------------
# Alignment -- the half that cannot be skipped
# ---------------------------------------------------------------------------


ALIGNED = in_struct(
    "bit[8]  addr;",
    "bit[32] data;",
    "bit     valid;",
)

RAGGED = in_struct(
    "bit[8] addr;",
    "bit[32]   data;",
    "bit valid;",
)


class TestHandBuiltTablesSurvive:
    def test_an_aligned_block_is_reproduced_byte_for_byte(self):
        """The regression the field rules would otherwise have shipped.

        Without a column stop these three lines collapse to one space each.
        Nothing is lost, nothing fails to parse, and a reviewer sees a large
        diff that looks considered.
        """
        assert fmt(ALIGNED) == ALIGNED

    def test_an_aligned_constant_table_keeps_its_equals_column(self):
        """Two stops are needed, and marking only the first hides that.

        Where every type has the same width the first column is already
        consistent at one space, so a single stop reproduces the block with
        its ``=`` column quietly flattened.
        """
        src = in_struct(
            "static const bit[64] A_LONG_NAME = 0x00;",
            "static const bit[64] B           = 0x08;",
        )
        assert fmt(src) == src

    def test_an_aligned_trailing_comment_run_survives(self):
        src = in_struct(
            "bit[8]  addr;    // where",
            "bit[32] data;    // what",
            "bit     valid;   // when",
        )
        assert fmt(src) == src

    @pytest.mark.parametrize("src,expected", [
        ("struct s {\n    bit[64]\n        addr;\n}\n",
         "struct s {\n    bit[64] addr;\n}\n"),
        ("struct s {\n    static const int N\n        = 8;\n}\n",
         "struct s {\n    static const int N = 8;\n}\n"),
        ("struct s {\n    int\n      n\n      = 8;\n}\n",
         "struct s {\n    int n = 8;\n}\n"),
    ], ids=["before-name", "before-equals", "both"])
    def test_a_wrapped_declaration_does_not_become_a_column(self, src, expected):
        """A gap that spans lines is not a gap on any line.

        The declaration is joined back onto one line, so the whitespace at a
        column stop is a newline plus the next line's indent. Measured as a
        width it is large and meaningless: without the guard this emits
        ``bit[64]         addr;``. Output that is obviously wrong, from a code
        path no aligned or ragged block reaches -- found by mutation testing,
        not by reading.
        """
        assert fmt(src) == expected

    def test_a_ragged_block_is_flattened(self):
        """``infer`` cuts both ways, or it is just ``preserve``."""
        assert fmt(RAGGED) == in_struct(
            "bit[8] addr;", "bit[32] data;", "bit valid;")

    def test_a_lone_trailing_comment_is_left_as_written(self):
        """One line is no evidence, so there is nothing to infer from."""
        src = in_struct("bit[8] addr;    // where")
        assert fmt(src) == src

    def test_a_blank_line_separates_two_tables(self):
        """``GroupBoundary.BLANK_LINES`` -- two blocks, two column decisions."""
        src = ("struct s {\n"
               "    bit[8]  addr;\n"
               "    bit[32] data;\n"
               "\n"
               "    bit a;\n"
               "    bit b;\n"
               "}\n")
        assert fmt(src) == src

    def test_the_mode_is_a_style_value(self):
        style = Style(alignment=AlignMode.FLUSH_LEFT)
        assert fmt(ALIGNED, style) == in_struct(
            "bit[8] addr;", "bit[32] data;", "bit valid;")

    def test_preserve_leaves_even_a_ragged_block_alone(self):
        assert fmt(RAGGED, Style(alignment=AlignMode.PRESERVE)) == RAGGED


class TestColumnStops:
    """``_column_stops`` as a function: which positions get a mark."""

    def test_a_field_with_a_default_has_two(self):
        assert len(self._stops("struct s {\n    int n = 8;\n}\n")) == 2

    def test_a_field_without_one_has_one(self):
        assert len(self._stops("struct s {\n    int n;\n}\n")) == 1

    def test_a_rule_with_no_declarator_has_none(self):
        assert self._stops("component c {\n    bind chan_p *;\n}\n") == ()

    @staticmethod
    def _stops(src: str):
        from pssparser import cst as _cst

        from pssfmt.rules import BuildContext
        from pssfmt.style import DEFAULT_STYLE
        from pssfmt.trivia import TriviaMap

        tree = _cst.parse(src)
        ctx = BuildContext(style=DEFAULT_STYLE, trivia=TriviaMap(tree.tokens))
        found = []

        def walk(node):
            if not node.is_rule:
                return
            if node.rule_name in stmts._FIELD_RULES + ("object_bind_stmt",):
                found.append(stmts._column_stops(ctx, node))
            for child in node.children:
                walk(child)

        walk(tree.root)
        assert found, "no field declaration in the sample"
        return found[0]


class TestNoTokenIsEverLost:
    @pytest.mark.parametrize("src", [
        in_struct("rand bit[64] addr;"),
        in_struct("static const int N = 8;"),
        ALIGNED,
        RAGGED,
        in_struct("int a, b;", "int c;"),
        "component c {\n    bind chan_p *;\n}\n",
        in_struct("static const int N = A + B;"),
        in_struct("bit chan[4];"),
    ])
    def test_the_tokens_survive(self, src: str):
        violations = list(verify(src, fmt(src)))
        assert not violations, violations

    @pytest.mark.parametrize("src", [ALIGNED, RAGGED,
                                     in_struct("bit[8] a;    // c")])
    def test_output_is_stable(self, src: str):
        once = fmt(src)
        assert fmt(once) == once, once

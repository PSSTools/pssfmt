"""``T-24`` -- constraints (``P3-5``).

The interesting thing about this item is how much of it is *not* here.
``PLAN.md`` budgeted for implication, ``if``/``else``, ``forall``, ``unique``,
nested braces and range lists broken with ``Fill``. The corpus has one
``if``, one ``foreach``, one ``unique``, zero ``forall``, and **not a single
constraint body item written across more than one line** -- so most of that
list is a construct with one instance or none, and a line-breaking policy
would have been built against nothing.

What is tested here is therefore what the corpus actually contains: two shapes
of declaration, four kinds of one-line item, and a bracket that turns out to
be the only one in PSS with a space in front of it.
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


def in_action(*body: str) -> str:
    return ("component c {\n    action a {\n"
            + "".join("        %s\n" % b for b in body)
            + "    }\n}\n")


def in_constraint(*body: str) -> str:
    return ("component c {\n    action a {\n        constraint c1 {\n"
            + "".join("            %s\n" % b for b in body)
            + "        }\n    }\n}\n")


# ---------------------------------------------------------------------------
# The two shapes of a declaration
# ---------------------------------------------------------------------------


class TestTheTwoShapesOfADeclaration:
    """``constraint <set>`` and ``[dynamic] constraint <name> <block>``.

    The corpus writes them differently enough to make them two rules: 20 of 20
    anonymous constraints are on one line, and 31 of 32 named ones are opened
    out.
    """

    def test_an_anonymous_constraint_is_a_statement(self):
        assert fmt(in_action("constraint  len > 0 && len <= MAX ;")) == \
            in_action("constraint len > 0 && len <= MAX;")

    def test_a_named_constraint_is_a_block(self):
        src = in_action("constraint  c1 { blk . pattern != X ; }")
        assert fmt(src) == in_constraint("blk.pattern != X;")

    def test_a_one_item_body_is_still_opened_out(self):
        """21 of the 31 opened-out bodies hold exactly one item.

        So "collapse a single-item block onto one line" is not a rule the
        corpus supports -- it is the thing the corpus consistently declines to
        do, and a formatter that did it would rewrite 21 constraints nobody
        asked it to touch.
        """
        assert fmt(in_action("constraint c1 { a > 0; }")) == in_constraint("a > 0;")

    def test_dynamic_is_part_of_the_header(self):
        src = in_action("dynamic  constraint  d1 { z > 0; }")
        assert fmt(src) == (
            "component c {\n    action a {\n        dynamic constraint d1 {\n"
            "            z > 0;\n        }\n    }\n}\n")

    def test_an_empty_body_is_not_opened(self):
        assert fmt(in_action("constraint c1 {}")) == in_action("constraint c1 {}")


class TestNormalisation:
    @pytest.mark.parametrize("src,expected", [
        ("blk . pattern != X ;", "blk.pattern != X;"),
        ("a>0 -> b>0 ;", "a > 0 -> b > 0;"),
        ("a > 0->b > 0;", "a > 0 -> b > 0;"),
        ("soft  x==1 ;", "soft x == 1;"),
        ("default  y==2 ;", "default y == 2;"),
        ("default  disable  z ;", "default disable z;"),
        ("len in [ 1 .. 4096 ] ;", "len in [1..4096];"),
        ("len in[1,2,4];", "len in [1, 2, 4];"),
    ], ids=["path", "implication", "tight-implication", "soft", "default",
            "default-disable", "in-range", "in-list"])
    def test_an_item_is_written_out(self, src: str, expected: str):
        assert fmt(in_constraint(src)) == in_constraint(expected)


class TestTheGapsComeFromTheStyle:
    def test_the_implication_gap_follows_its_site(self):
        """6 out of 6 across 5 files -- measured, where ``docs/style.rst``
        had been defaulting it to the general binary-operator rule."""
        style = Style(spacing_overrides={Site.IMPLICATION: Spacing(0, 0)})
        assert fmt(in_constraint("a > 0 -> b > 0;"), style) == \
            in_constraint("a > 0->b > 0;")

    def test_the_set_bracket_gap_follows_its_site(self):
        style = Style(spacing_overrides={Site.SET_BRACKET_OPEN: Spacing(0, 0)})
        assert fmt(in_constraint("len in [1..4096];"), style) == \
            in_constraint("len in[1..4096];")

    def test_a_zero_everywhere_style_still_emits_valid_tokens(self):
        style = Style(spacing_overrides={site: Spacing(0, 0) for site in Site})
        src = in_constraint("a > 0 -> b > 0;", "soft x == 1;",
                            "len in [1..4096];")
        violations = list(verify(src, fmt(src, style)))
        assert not violations, violations


# ---------------------------------------------------------------------------
# The bracket that is not the bracket it looks like
# ---------------------------------------------------------------------------


class TestTheSetBracketIsNotTheIndexBracket:
    """``[`` is four constructs in PSS, and this is the fourth.

    An index ``a[i]`` is 1002/1002 tight, a declarator dimension ``chan[4]``
    is 34/34 tight, a type width ``bit[64]`` is 333/333 tight -- and a set
    ``in [1..4096]`` is 14/16 spaced. One character, two answers.
    """

    def test_a_width_and_a_domain_in_one_declaration(self):
        """``bit[3] in [2..4]`` -- both brackets, three characters apart, and
        both inside a *single* ``integer_type`` node. Nothing about the token,
        the node, or its parent tells them apart; only their position relative
        to ``in`` does.

        Note the single space before ``n``: the gap there is a *column stop*,
        and ``infer`` reproduces the author's width on a line it has no run to
        compare against. Writing two spaces in the input would test that rule
        instead of this one.
        """
        assert fmt(in_action("rand  bit[3]  in [ 2 .. 4 ] n ;")) == \
            in_action("rand bit[3] in [2..4] n;")

    def test_a_field_domain_is_spaced(self):
        assert fmt(in_action("rand int in[1..4] n;")) == \
            in_action("rand int in [1..4] n;")

    def test_an_index_is_still_tight(self):
        assert fmt(in_constraint("chans[i] < 8;")) == in_constraint("chans[i] < 8;")

    def test_a_string_domain_is_spaced_too(self):
        assert fmt(in_action('rand string in["a","b"] t;')) == \
            in_action('rand string in ["a", "b"] t;')

    def test_the_closing_bracket_still_separates_from_a_name(self):
        """``in [1..4] n`` -- ``]`` then a declarator.

        A field declaration, so this is :mod:`pssfmt.rules.stmts` supplying
        the seam, not the constraint rules. Worth stating: a constraint item
        has no declarator, so the same callback written there ran 155 times
        over the corpus without once returning true, and was removed.
        """
        out = fmt(in_action("rand int in [1..4] n;"))
        assert "[1..4] n;" in out
        assert "]n" not in out


# ---------------------------------------------------------------------------
# The boundary
# ---------------------------------------------------------------------------


class TestItDeclinesRatherThanGuesses:
    """Each of these has one corpus instance or none.

    The test applied is not "is it hard" but *does formatting it need a
    decision the corpus has not made*. Where the answer is yes, one instance
    cannot make it -- so the author's text comes back untouched.
    """

    def test_an_if_constraint_is_left_alone(self):
        """One instance. ``} else {`` versus ``}\\nelse {`` is a brace rule
        ``docs/style.rst`` does not state, and one example cannot decide."""
        src = in_constraint("if (len > 1024) { addr % 64 == 0; } else { x; }")
        assert fmt(src) == src

    def test_a_foreach_constraint_is_left_alone(self):
        """One instance, and it is the ``foreach (a[i])`` spelling -- so the
        corpus holds *zero* measurements of the ``foreach (i : list)`` colon,
        which would be a fifth colon construct."""
        src = in_constraint("foreach (chans[i]) { chans[i] < 8; }")
        assert fmt(src) == src

    def test_a_unique_constraint_is_left_alone(self):
        """Its ``{a, b}`` is a list brace; ``Site.BRACE_OPEN`` was measured on
        725 declaration bodies. Same argument that dropped ``pool[4]``."""
        src = in_constraint("unique {chans};")
        assert fmt(src) == src

    def test_a_braced_implication_is_left_alone(self):
        """And nothing in the module says so.

        ``TOK_LCBRACE`` is simply absent from the item vocabulary, so an item
        whose right-hand side is a block declines the way any unrecognised
        token declines. That is the difference between a boundary and a
        special case.
        """
        src = in_constraint("(a > 0) -> { b > 0; c > 0; }")
        assert fmt(src) == src

    def test_an_exponent_still_declines_inside_a_constraint(self):
        """``P3-4``'s boundary is inherited rather than re-litigated."""
        src = in_constraint("a == b**2;")
        assert fmt(src) == src

    def test_a_comment_inside_an_item_is_left_alone(self):
        src = in_constraint("a > /* why */ 0;")
        assert fmt(src) == src


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


class TestNoTokenIsEverLost:
    @pytest.mark.parametrize("src", [
        in_action("constraint len in [1..4096];"),
        in_action("constraint c1 { a > 0; }"),
        in_action("dynamic constraint d1 { z > 0; }"),
        in_constraint("a > 0 -> b > 0;", "soft x == 1;", "default y == 2;"),
        in_constraint("if (a) { b; } else { c; }"),
        in_constraint("unique {chans};"),
        in_action("rand bit[3] in [2..4] n;"),
    ])
    def test_the_tokens_survive(self, src: str):
        violations = list(verify(src, fmt(src)))
        assert not violations, violations

    @pytest.mark.parametrize("src", [
        in_action("constraint c1 { a > 0; }"),
        in_constraint("len in [1..4096];"),
        in_constraint("if (a) { b; } else { c; }"),
    ])
    def test_output_is_stable(self, src: str):
        once = fmt(src)
        assert fmt(once) == once, once

    def test_a_trailing_comment_stays_on_its_item(self):
        src = in_constraint("st.cfg.dma_en;    // must be raising DMA")
        assert fmt(src) == src


def test_the_corpus_constraints_format(request):
    """The coverage number, computed rather than quoted.

    95 of the corpus's 102 constraint body items. The seven that decline are
    each named in ``pssfmt.rules.constraints`` -- one ``if``, one ``foreach``,
    one ``unique``, one ``dist``, one braced implication, and the two
    expressions ``P3-4`` already declined (``**`` and ``>>``). The assertion
    is on the count so that a *new* kind of decline shows up as a failure
    rather than as a number nobody re-reads.
    """
    corpus = request.config.rootpath / "packages" / "pss-corpus"
    if not corpus.is_dir():
        pytest.skip("corpus not present")
    from pssparser import cst as _cst

    from pssfmt.rules import BuildContext
    from pssfmt.rules import constraints as c
    from pssfmt.rules.emit import code_span
    from pssfmt.rules.exprs import sites_for
    from pssfmt.rules.tokens import emit_span
    from pssfmt.style import DEFAULT_STYLE
    from pssfmt.trivia import TriviaMap

    items = ("expression_constraint_item", "foreach_constraint_item",
             "forall_constraint_item", "if_constraint_item",
             "implication_constraint_item", "unique_constraint_item",
             "soft_constraint_item", "default_constraint",
             "default_disable_constraint", "dist_directive")
    formatted = declined = 0
    for path in sorted(corpus.rglob("*.pss")):
        try:
            tree = _cst.parse(path.read_text(errors="replace"))
        except Exception:
            continue
        ctx = BuildContext(style=DEFAULT_STYLE, trivia=TriviaMap(tree.tokens))
        stack = [tree.root]
        while stack:
            node = stack.pop()
            if not node.is_rule:
                continue
            if node.rule_name in items:
                span = code_span(ctx.trivia, node)
                sites = (sites_for(ctx, node, extra_rules=c._EXTRA_SITES)
                         if span is not None else None)
                built = None
                # `is not None`, not truthiness: an item with no tree-decided
                # token gets an empty map, which is a complete answer and not
                # a refusal. Testing `if sites` reports seven false declines.
                if sites is not None and span is not None:
                    built = emit_span(ctx, span[0], span[1],
                                      c._ITEM_VOCABULARY, sites_at=sites)
                if built is None:
                    declined += 1
                else:
                    formatted += 1
            stack.extend(reversed(node.children))

    assert formatted + declined == 102, (formatted, declined)
    assert declined == 7, declined

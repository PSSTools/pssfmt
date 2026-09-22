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

    def test_an_unbraced_if_constraint_is_left_alone(self):
        """``if (a) b < c;`` is legal, and ``S-1`` did not decide it.

        Braces cannot be inserted -- that changes the token stream -- and
        laying the bare item out needs a second decision nobody has made.
        """
        src = in_constraint("if (len > 1024)  addr % 64 == 0;")
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

    98 of the corpus's 103 constraint body items, measured on the *one-line
    statement* path -- this test calls ``emit_span`` directly against
    ``_ITEM_VOCABULARY`` rather than going through dispatch. The five it
    counts as declining are, exactly:

    * the ``if`` and the ``foreach`` in ``language-ref/constraints.pss``, and
      the ``unique`` beside them;
    * the braced implication and the ``dist`` in ``lexical/operators.pss``.

    **Three of those five are formatted by the tool.** ``S-1`` lays the
    ``if`` out as a block, ``S-5`` the ``foreach``, and ``S-12`` the
    ``unique`` through a vocabulary of its own -- and this count sees none of
    that, because none of it goes through the item path. That is the point of
    measuring one path rather than the outcome: a decline *here* is a
    statement about `_ITEM_VOCABULARY`, and the two constructs still declined
    outright are the braced implication and ``dist``.

    The count has moved twice in this phase, both times for real. ``S-9``
    took it 7 -> 6 by formatting the corpus's only ``>>``; ``S-8`` took it
    6 -> 5 by formatting its ``**``.

    Worth stating, because a count that does not move through a landing item
    reads as a test that is not watching, and here it is the opposite: the
    count is watching one specific path and saying so.

    The assertion is on the count so that a *new* kind of decline shows up as
    a failure rather than as a number nobody re-reads.

    The total was 102 until pss-corpus completed the three ``pss31/`` files:
    ``templates_and_activity.pss`` now parses and contributes the one item it
    always contained; that moved the total and not the declines.

    The declines went 7 -> 6 with ``S-9``, and that one *is* the item: the
    corpus's only ``>>`` is in a constraint, so this count is where the right
    shift landing is visible over real code rather than over crafted input.
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

    assert formatted + declined == 103, (formatted, declined)
    assert declined == 5, declined


class TestControlItems:
    """``T-44`` and ``T-48`` in a constraint -- ``S-1`` and ``S-5``.

    One corpus instance each, and both were declined for a *decision* rather
    than for difficulty: where ``} else {`` goes, and what the iterator colon
    looks like. Neither is decided here. They are language-wide answers in
    ``docs/style.rst``, which is why the same two questions unblocked the same
    two constructs in three separate rule modules.
    """

    def test_an_if_constraint_cuddles_its_else(self):
        assert fmt(in_constraint("if(len>1024){addr%64==0;}else{x<2;}")) == \
            in_constraint(
                "if (len > 1024) {",
                "    addr % 64 == 0;",
                "} else {",
                "    x < 2;",
                "}")

    def test_a_chain_does_not_staircase(self):
        out = fmt(in_constraint("if(a){x<1;}else if(b){x<2;}else{x<3;}"))
        assert "            } else if (b) {" in out
        assert "                } else if (b) {" not in out

    def test_a_foreach_constraint_spaces_its_iterator(self):
        assert fmt(in_constraint("foreach(i:chans){chans[i]<8;}")) == \
            in_constraint(
                "foreach (i : chans) {",
                "    chans[i] < 8;",
                "}")

    def test_the_colon_less_foreach_still_works(self):
        """The corpus's only ``foreach`` is this spelling, and the colon is
        optional in the grammar."""
        assert fmt(in_constraint("foreach(chans[i]){chans[i]<8;}")) == \
            in_constraint(
                "foreach (chans[i]) {",
                "    chans[i] < 8;",
                "}")

    def test_a_braced_implication_still_declines(self):
        """The hazard ``S-12`` was sequenced around, pinned.

        ``TOK_LCBRACE``'s absence from ``_ITEM_VOCABULARY`` was doing two
        jobs: declining a list brace *and* declining a braced implication.
        Admitting the brace for ``if`` had to not admit it for these, which
        is why the brace is scoped to a control vocabulary rather than added
        to the item one.
        """
        src = in_constraint("(x > 0) -> { y > 0; }")
        assert fmt(src) == src

    def test_it_is_idempotent(self):
        once = fmt(in_constraint("if(a){x<1;}else{foreach(i:c){c[i]<2;}}"))
        assert fmt(once) == once


class TestTheListBrace:
    """``T-55`` -- ``S-12``. ``unique {a, b};``.

    Three instances across the corpus -- one ``unique`` and two aggregate
    literals, in three files -- so the value is argued rather than measured.
    What it is argued *from* is the point: not ``Site.BRACE_OPEN``'s 7/10,
    which was measured on declaration bodies, but from every list-like
    construct PSS does measure. ``f(a, b)`` is 765/767 tight inside,
    ``packed_s<T, 32>`` is 137/137, ``[1..4096]`` is 18/18. A list brace
    spaced inside would be the sole exception.
    """

    @pytest.mark.parametrize("src", [
        "unique {chans, addrs};", "unique { chans, addrs };",
        "unique{chans,addrs};",
    ], ids=["canonical", "spaced", "tight"])
    def test_every_spelling_lands_on_the_canonical_one(self, src: str):
        assert fmt(in_constraint(src)) == in_constraint("unique {chans, addrs};")

    def test_the_unbraced_spelling_still_works(self):
        """``unique_constraint_argument`` is ``'{' list '}' | hierarchical_id``
        and the corpus's one instance is the braced form."""
        assert fmt(in_constraint("unique  chans ;")) == \
            in_constraint("unique chans;")

    def test_a_body_brace_in_the_same_file_keeps_the_body_rule(self):
        """The test that proves the two sites are genuinely separate.

        ``Site.BRACE_OPEN``'s *after* is 1 -- ``enum e { A, B }`` -- and the
        list brace's is 0. One file, both braces, and they must disagree.
        """
        src = ("package p {\n"
               "    enum e { A, B }\n"
               "    struct s {\n"
               "        constraint k {\n"
               "            unique {x, y};\n"
               "        }\n"
               "    }\n"
               "}\n")
        out = fmt(src)
        assert "enum e { A, B }" in out
        assert "unique {x, y};" in out

    def test_the_gaps_come_from_the_style(self):
        out = fmt(in_constraint("unique {chans};"),
                  Style(spacing_overrides={
                      Site.LIST_BRACE_OPEN: Spacing(1, 1),
                      Site.LIST_BRACE_CLOSE: Spacing(1, 0)}))
        assert "unique { chans };" in out

    def test_it_is_idempotent(self):
        once = fmt(in_constraint("unique{a,b};"))
        assert fmt(once) == once

"""``T-38`` -- procedural statements (``P3-11b``).

The last thing between a mis-formatted function and a formatted one, and the
item whose scope was decided by a measurement rather than by the plan.

Why ``match`` is in a file about statement spacing
--------------------------------------------------
``PLAN.md`` describes this item as "a vocabulary rather than a layout", names
four alternatives as 85% of all procedural statements, and lists
``procedural_return_stmt`` first at 201 instances. Registering those four
reaches **158 of 388** statements, and **9 of the 201 returns** -- because 195
of them sit inside a ``procedural_match_choice``, and ``match`` is a block.

So the vocabulary alone would have bound six builders that dispatch almost
never reached, with every test in this file passing. That is ``P3-6``'s
``extend`` at a third scale, and the only reason it was caught before shipping
is that ``T-30`` asks about dispatch rather than about text.

What the tests are shaped around
--------------------------------
Three kinds, because there are three ways this item can be wrong:

* **the measured gaps**, one test each, from input that disagrees with them;
* **the two column stops**, which are the item's only real style decisions and
  are the ones a corpus of well-kept code will not notice going missing;
* **the refusals**, from deliberately mis-spaced input, since a decline and a
  rule that ran and agreed produce the same file otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest.importorskip("pssparser")

from pssfmt.rules import REGISTRY, format_source  # noqa: E402
from pssfmt.style import Site, Spacing, Style  # noqa: E402
from pssfmt.verify import format_safely  # noqa: E402


def fmt(src: str, style: Style = Style()) -> str:
    return format_source(src, style=style)


def body(statements: str, style: Style = Style()) -> list:
    """*statements* inside a function, formatted, as the body's lines.

    Returned as a list so a test asserts about *every* line it produced
    rather than about a substring of one -- ``T-36``'s rule, and it matters
    more here than there because a statement rule that drops a token leaves
    output that still reads like PSS.
    """
    out = fmt("component c {\n    function void f() {\n%s\n    }\n}\n"
              % statements, style)
    lines = out.splitlines()
    assert lines[0] == "component c {" and lines[-1] == "}", out
    return lines[2:-2]


class TestItIsReachedAtAll:
    """The measurement that set this item's scope, as an assertion.

    ``match`` is registered here rather than left to a later item because 195
    of the corpus's 201 ``return`` statements are behind one. ``T-30`` proves
    the dispatch; this proves the *registration*, which is the thing a later
    edit can quietly undo.
    """

    @pytest.mark.parametrize("rule", [
        "procedural_return_stmt", "procedural_assignment_stmt",
        "procedural_void_function_call_stmt", "procedural_break_stmt",
        "procedural_continue_stmt", "procedural_yield_stmt",
        "procedural_match_stmt", "procedural_match_choice",
        # Registered in ``rules/stmts.py``: it is a field declaration in
        # everything but name, and a second copy of that vocabulary is how the
        # two would come to disagree.
        "procedural_data_declaration",
    ])
    def test_the_rule_is_registered(self, rule):
        assert rule in REGISTRY

    def test_a_statement_is_no_longer_reproduced_verbatim(self):
        assert body("        x = 1 ;") == ["        x = 1;"]

    def test_a_statement_inside_a_match_arm_is_reached(self):
        """The whole argument for this item's scope, in one assertion: the
        statement is formatted, and nothing but ``match`` having a rule makes
        that possible."""
        assert body("        match (n) {\n[0]: return  - 1 ;\n}") == [
            "        match (n) {",
            "            [0]: return -1;",
            "        }",
        ]


class TestTheMeasuredGaps:

    def test_an_assignment_is_spaced(self):
        """``Site.ASSIGN``, 271/319."""
        assert body("        a.b=c;") == ["        a.b = c;"]

    def test_every_assignment_operator_takes_the_same_site(self):
        """``assign_op`` is one production with seven alternatives, and six of
        them are a single corpus instance apiece. One site because the
        *grammar* groups them, not because the counts were pooled."""
        assert body("        x+=1;\n        x-=1;\n        x<<=1;\n"
                    "        x>>=1;\n        x|=1;\n        x&=1;") == [
            "        x += 1;", "        x -= 1;", "        x <<= 1;",
            "        x >>= 1;", "        x |= 1;", "        x &= 1;"]

    def test_a_call_is_tight(self):
        assert body("        regs . ch [ n ] . write ( x , 3 ) ;") == [
            "        regs.ch[n].write(x, 3);"]

    def test_the_gap_before_a_semicolon_goes(self):
        assert body("        return x ;") == ["        return x;"]

    def test_a_bare_return_keeps_none(self):
        """``return;`` -- 201 of 201 tight, and the case the ``return`` floor
        below has to *not* fire on. A one-sided floor emits ``return ;``."""
        assert body("        return ;") == ["        return;"]

    def test_a_match_header_takes_the_control_paren(self):
        """``Site.CONTROL_PAREN_OPEN``, 118/118 over ``if``/``repeat``, and
        the corpus's 92 ``match`` headers agree with it."""
        assert body("        match( n ){\n[0]: return 0;\n}")[0] == \
            "        match (n) {"

    def test_a_choice_label_is_tight_and_its_colon_is_not(self):
        """107/107 tight inside the brackets and before the colon, 92/92 tight
        after ``default``, 186/199 one space after the colon."""
        assert body("        match (n) {\n[ 0 ] :return 1;\ndefault :return 2;\n}") == [
            "        match (n) {",
            "            [0]: return 1;",
            "            default: return 2;",
            "        }",
        ]


class TestTheReturnFloor:
    """``return -1`` -- 90 of the corpus's 201 returns.

    ``return`` is word-class and contributes no gap; ``-`` is ``Site.UNARY``,
    measured tight at 92/92. So the computed gap is zero and the output is
    ``return-1;`` -- which still lexes as three tokens, so token equivalence
    passes, the verifier is silent, and a test written against ``return x;``
    passes too, because *there* both sides are word characters and the lexical
    floor fires.

    That is the shape that shipped ``bit[3]in [2..4]`` once, and it is why
    these two tests exist as a pair: the one that would have caught it is the
    one whose operand does not start with a letter.
    """

    def test_return_of_a_negative_literal_keeps_its_space(self):
        assert body("        return -1;") == ["        return -1;"]

    def test_return_of_a_name_keeps_its_space(self):
        assert body("        return x;") == ["        return x;"]

    def test_return_of_a_parenthesised_expression_keeps_its_space(self):
        assert body("        return (a + b);") == ["        return (a + b);"]


class TestTheColumnStops:
    """The item's two style decisions, and the two things a corpus of
    well-kept code cannot tell you are missing: it looks identical whether a
    stop is emitted and reproduced, or never emitted at all. Both are tested
    the only way that distinguishes them -- against input whose table is
    *already* built, where losing the stop flattens it."""

    def test_an_assignment_table_survives(self):
        """22 of the corpus's 93 assignments are padded, across 8 files, and
        they are five complete tables. Marking the seam is what makes keeping
        them possible; ``infer`` decides whether they are kept."""
        assert body("        ctrl.en        = 1;\n"
                    "        ctrl.start     = 0;\n"
                    "        ctrl.lsb_first = 1;") == [
            "        ctrl.en        = 1;",
            "        ctrl.start     = 0;",
            "        ctrl.lsb_first = 1;",
        ]

    def test_a_match_arm_table_survives(self):
        """13 of the corpus's 199 choices are padded, and they are four
        complete tables in four files -- much stronger evidence than
        ``P3-11a`` declined a name-column stop on, which is why that one was
        declined and this one is not."""
        assert body('        match (name) {\n'
                    '            ["ctrl"]:   return 0;\n'
                    '            ["status"]: return 8;\n'
                    '            default:    return -1;\n'
                    '        }') == [
            "        match (name) {",
            '            ["ctrl"]:   return 0;',
            '            ["status"]: return 8;',
            "            default:    return -1;",
            "        }",
        ]

    def test_a_lone_marked_line_keeps_its_padding(self):
        """Both stops inherit ``infer``'s rule that one line is no evidence of
        a table, and both are worth pinning because a reader meeting it for
        the first time in a *statement* will read it as a rule that failed to
        run. It is the same answer ``docs/style.rst`` gives for a lone field
        declaration, and it is why the two tests above have three lines each
        rather than one."""
        assert body("        x   =   1;") == ["        x   = 1;"]
        assert body("        match (n) {\n[0]:   return 1;\n}")[1] == \
            "            [0]:   return 1;"

    def test_a_ragged_run_is_flushed(self):
        """The other half of what a stop means. ``infer`` reproduces a table
        and flattens a near-miss, and marking a seam is not a decision to
        pad -- so a run that reaches no common column comes out at one
        space."""
        assert body("        a = 1;\n"
                    "        bbbbbb   = 2;") == [
            "        a = 1;",
            "        bbbbbb = 2;",
        ]

    def test_a_local_declaration_table_survives(self):
        """``procedural_data_instantiation`` had to be added to
        ``stmts._SEAM_RULES`` for this: a local variable is a declaration
        written with a different production from a field, so it got *no*
        stops and any column in one would have been collapsed the moment the
        statement started being written out. Exactly the ``flow_object_type``
        omission ``P3-6`` found."""
        assert body("        int      nwords = 4;\n"
                    "        bit[32]  expected;\n"
                    "        bit[32]  actual;") == [
            "        int      nwords = 4;",
            "        bit[32]  expected;",
            "        bit[32]  actual;",
        ]


class TestTheMatchBlock:

    def test_the_brace_moves_onto_the_header_line(self):
        out = body("        match (n)\n{\n[0]: return 0;\n}")
        assert out[0] == "        match (n) {"

    def test_arms_are_indented_one_level(self):
        assert body("        match (n) {\n[0]: return 0;\n[1]: return 1;\n}")[1:3] == [
            "            [0]: return 0;", "            [1]: return 1;"]

    def test_indent_width_reaches_it(self):
        out = fmt("component c {\nfunction void f() {\nmatch (n) {\n"
                  "[0]: return 0;\n}\n}\n}\n", Style(indent_width=2))
        assert "    match (n) {\n      [0]: return 0;\n    }" in out

    def test_an_arm_whose_statement_is_a_block(self):
        """Four of the corpus's 199 choices, holding 12 statements that
        nothing could reach before this item. The braces belong to a *child*
        of the choice, which is what ``_block``'s ``body`` parameter is for --
        the same shape as a ``constraint`` and an activity ``repeat``."""
        assert body("        match (n) {\n[0]: {\nx=1;\ny=2;\n}\n}") == [
            "        match (n) {",
            "            [0]: {",
            "                x = 1;",
            "                y = 2;",
            "            }",
            "        }",
        ]

    def test_a_comment_above_an_arm_moves_with_it(self):
        out = body("        match (n) {\n// why\n[0]: return 0;\n}")
        assert out[1:3] == ["            // why", "            [0]: return 0;"]

    def test_a_trailing_comment_on_an_arm_survives(self):
        out = body("        match (n) {\n[0]: return 0; // why\n}")
        assert out[1] == "            [0]: return 0; // why"


class TestWhatDeclines:
    """Every refusal from mis-spaced input, so that "declined" and "agreed"
    are different files."""

    def test_if_else_is_reproduced(self):
        """5 instances in 3 files, and it needs the ``} else {`` rule
        ``docs/style.rst`` does not state -- the same reason ``P3-5`` declined
        ``if`` constraints on one instance. It hides 7 statements, which is
        the price and is recorded rather than paid quietly."""
        assert body("        if (n > 0)  { n  -=  1; } else { n  +=  1; }") == [
            "        if (n > 0)  { n  -=  1; } else { n  +=  1; }"]

    def test_repeat_while_is_reproduced(self):
        """Two reasons, and the second is structural rather than stylistic:
        ``repeat { … } while (e);`` puts its block in the *middle* of the
        statement, and a block layout emits a header, a body and a ``}`` --
        everything after the closing brace would be dropped."""
        assert body("        repeat { n += 1; } while (n < 4);") == [
            "        repeat { n += 1; } while (n < 4);"]

    def test_a_labelled_repeat_is_reproduced(self):
        """``repeat (i : n)`` -- 6 of the corpus's 11. The colon is a fifth
        reading of a character ``docs/style.rst`` already splits four ways,
        and ``activities.py`` declined the identical construct for the
        identical reason."""
        assert body("        repeat (i : 4) { n  +=  1; }") == [
            "        repeat (i : 4) { n  +=  1; }"]

    def test_a_wrapped_arm_is_reproduced(self):
        """The same rule one level in, and it is load-bearing for the same
        reason the braced-arm path is: the inline path writes a **column
        stop**, a column is a fact about one line, and a stop in front of a
        two-line layout makes ``align`` measure a cell containing a newline.
        A wrapped statement declines and is reproduced *as two lines*, so
        without this check the arm above it would be the braced-arm bug
        again."""
        out = body("        match (n) {\n"
                   "            [0]: msg(a,\n"
                   "                     b);\n"
                   "            [1]: return 1;\n"
                   "        }")
        assert out == [
            "        match (n) {",
            "            [0]: msg(a,",
            "                     b);",
            "            [1]: return 1;",
            "        }",
        ]

    def test_a_wrapped_statement_is_reproduced(self):
        """``P3-11a``'s rule at a second construct, on the same evidence:
        ``emit_span`` discards newlines, so formatting a wrapped statement is
        joining it, and six of the corpus's seven wrapped calls join to
        between 86 and 108 columns."""
        assert body("        message(NONE, \"a very long message indeed\",\n"
                    "                a, b, c);") == [
            "        message(NONE, \"a very long message indeed\",",
            "                a, b, c);"]

    def test_a_bit_slice_declines(self):
        """``a[3:0] = x;``. ``Site.COLON_BIT_SLICE`` is tight and
        ``Site.COLON_INHERITANCE`` is spaced, and telling them apart needs
        bracket depth -- so ``TOK_COLON`` is not in the statement vocabulary
        and the statement declines. Inherited from ``stmts``' documented cut
        rather than decided again here."""
        assert body("        a[3:0]  =  x;") == ["        a[3:0]  =  x;"]

    def test_a_void_cast_call_declines(self):
        """``(void)f();`` -- one corpus instance. Its parens hang off the
        statement rather than off any expression rule, so nothing classifies
        them and the completeness check in ``sites_for`` refuses the
        statement. A decline nobody had to write."""
        assert body("        (void)f( 1 ) ;") == ["        (void)f( 1 ) ;"]


class TestASiteFromTheTreeBeatsOneFromTheTable:
    """A match header and an arm label carry punctuation no expression rule
    owns -- ``match``'s parens, an arm's brackets and colon -- so they are
    classified by *token type* from a table. That table must not reach the
    same character inside a child subtree, where the tree has already given a
    better answer.

    Both of these are one character in two roles on one line, which is the
    situation :mod:`pssfmt.rules.exprs` exists for; the tests are here because
    the table is what could override it.
    """

    def test_an_index_inside_an_arm_label_stays_an_index(self):
        """``[arr[0]]:`` -- the outer bracket is a *set* bracket, spaced
        before; the inner is an index, tight. Take the table's answer for both
        and the output is ``[arr [0]]:``."""
        assert body("        match (n) {\n[arr[0]]: return 1;\n}")[1] == \
            "            [arr[0]]: return 1;"

    def test_a_grouping_paren_in_a_match_header_stays_a_grouping(self):
        """``match ((a + b))`` -- the outer paren is a control paren, one
        space after the keyword; the inner is a grouping, tight. Take the
        table's answer for both and the output is ``match ( (a + b))``."""
        assert body("        match ((a + b)) {\n[0]: return 1;\n}")[0] == \
            "        match ((a + b)) {"


class TestTheCompletenessCheck:
    """``_sites_through`` refuses a span holding a tree-decided token its
    table did not name.

    Tested as a *function*, because neither of the two tables that exist has
    a gap -- so no input reaches this, and behaviour that does not vary cannot
    be asserted through behaviour. That is ``decls._tiles``'s situation and it
    gets ``_tiles``'s treatment: the guard stays, because its failure mode is
    a token silently taking the wrong site, and the test calls it directly.

    What it is guarding is specific and easy to reintroduce. ``sites_for``
    checks its own completeness over each *subtree*; nothing was checking the
    tokens **between** subtrees, which is exactly where a node's own
    punctuation lives, and an unclassified ambiguous token there does not
    raise -- it quietly takes the vocabulary's answer.
    """

    def context(self, src: str):
        from pssparser import cst as _cst

        from pssfmt.rules import BuildContext
        from pssfmt.style import DEFAULT_STYLE
        from pssfmt.trivia import TriviaMap

        tree = _cst.parse(src)
        return BuildContext(style=DEFAULT_STYLE,
                            trivia=TriviaMap(tree.tokens)), tree

    def choice(self, tree):
        stack = [tree.root]
        while stack:
            node = stack.pop()
            if not node.is_rule:
                continue
            if node.rule_name == "procedural_match_choice":
                return node
            stack.extend(reversed(node.children))
        raise AssertionError("no match choice in the tree")

    SRC = ("component c {\n    function void f() {\n        match (n) {\n"
           "            [0]: return 1;\n        }\n    }\n}\n")

    def test_the_real_table_classifies_everything(self):
        from pssfmt.rules.procedural import _CHOICE_SITES, _sites_through

        ctx, tree = self.context(self.SRC)
        node = self.choice(tree)
        colon = next(c for c in node.children
                     if not c.is_rule and c.token.type_name == "TOK_COLON")
        limit = ctx.trivia.code_indices.index(colon.token_index)
        assert _sites_through(ctx, node, limit, _CHOICE_SITES) is not None

    def test_a_table_with_a_hole_declines(self):
        """The mutant this exists for: drop the check and this table -- which
        says nothing about ``[`` -- silently gets ``Site.INDEX_BRACKET_OPEN``
        from the vocabulary instead of declining."""
        from pssfmt.rules.procedural import _sites_through
        from pssfmt.style import Site

        ctx, tree = self.context(self.SRC)
        node = self.choice(tree)
        colon = next(c for c in node.children
                     if not c.is_rule and c.token.type_name == "TOK_COLON")
        limit = ctx.trivia.code_indices.index(colon.token_index)
        incomplete = {"TOK_COLON": Site.COLON_CASE_ITEM}
        assert _sites_through(ctx, node, limit, incomplete) is None


class TestTheStyleIsConsulted:
    """``T-32``'s lesson pointed at a rule: the way this fails is by copying
    text that looks like what a site would have produced."""

    def test_the_assign_site_reaches_a_statement(self):
        assert body("        x = 1;",
                    Style(spacing_overrides={Site.ASSIGN: Spacing(0, 0)})) == [
            "        x=1;"]

    def test_the_case_item_colon_reaches_a_match_arm(self):
        assert body("        match (n) {\n[0]: return 0;\n}",
                    Style(spacing_overrides={
                        Site.COLON_CASE_ITEM: Spacing(1, 1)}))[1] == \
            "            [0] : return 0;"

    def test_the_control_paren_reaches_a_match_header(self):
        assert body("        match (n) {\n[0]: return 0;\n}",
                    Style(spacing_overrides={
                        Site.CONTROL_PAREN_OPEN: Spacing(0, 1),
                        Site.CONTROL_PAREN_CLOSE: Spacing(1, 0)}))[0] == \
            "        match( n ) {"

    def test_max_blank_lines_reaches_a_match_body(self):
        out = body("        match (n) {\n[0]: return 0;\n\n\n\n[1]: return 1;\n}")
        assert out[2] == ""
        assert out[3] == "            [1]: return 1;"


class TestSafety:

    SOURCES = [
        "component c {\n    function void f() {\n        x   =   1 ;\n    }\n}\n",
        "component c {\n    function bit[64] f(string n) {\n"
        "        match ( n ) {\n[\"a\"]: return 0x0;\ndefault: return -1;\n}\n"
        "    }\n}\n",
        "component c {\n    function void f() {\n        match (n) {\n"
        "[0]: {\nx=1;\n}\n}\n    }\n}\n",
        "component c {\n    function void f() {\n        return ;\n    }\n}\n",
        "component c {\n    function void f() {\n        return  - 1 ;\n    }\n}\n",
        "component c {\n    function void f() {\n"
        "        if (n > 0) { n -= 1; } else { n += 1; }\n    }\n}\n",
        "component c {\n    function void f() {\n"
        "        repeat { n += 1; } while (n < 4);\n    }\n}\n",
        "component c {\n    function void f() {\n        int   x  =  1 ;\n"
        "        a[3:0] = x;\n        (void)g();\n    }\n}\n",
        "component c {\n    function void f() {\n        \\esc = 1;\n"
        "        return \\esc ;\n    }\n}\n",
    ]

    @pytest.mark.parametrize("src", SOURCES)
    def test_the_verifier_accepts_it(self, src):
        result = format_safely(src, formatter=format_source)
        assert result.ok, result.diagnostic()

    @pytest.mark.parametrize("src", SOURCES)
    def test_it_is_idempotent(self, src):
        once = fmt(src)
        assert fmt(once) == once

    def test_a_braced_arm_is_idempotent(self):
        """Pinned on its own because it was a live bug, and one the ordinary
        idempotence check above is what caught: a braced arm fell into the
        *inline* path, which writes a column stop, and a column stop in front
        of a three-line layout makes ``align`` measure a cell containing a
        newline. The gap grew by two columns on every pass. Four such arms in
        one corpus file, and the corpus fail-safe is what reported it."""
        src = ("component c {\n    function void f() {\n        match (n) {\n"
               "            [0]: {\n                x = 1;\n            }\n"
               "            default: {\n                x = 2;\n            }\n"
               "        }\n    }\n}\n")
        once = fmt(src)
        assert fmt(once) == once
        assert "            default: {" in once

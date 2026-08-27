"""``T-17`` -- rule dispatch and its fallback (``P3-1``).

The registry and the context are small enough to read; what needs testing is
the claim they rest on. Three things, in ascending order of what they buy:

1. Dispatch does what it says -- registered builder wins, unregistered node
   falls back, error node falls back *regardless* of what is registered.
2. The fallback is byte-exact for the node it covers.
3. **An empty rule set formats nothing and therefore breaks nothing.** The
   corpus version of that claim is in ``tests/corpus/test_rule_fallback.py``,
   where it is worth something; here it is checked on hand-written sources so
   a failure names a construct rather than a file.

The parser is required, so this module skips without it, matching the rest of
the non-layout suites (``T-2``).
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssparser import cst  # noqa: E402

from pssfmt.layout import Verbatim, render, text  # noqa: E402
from pssfmt.rules import (  # noqa: E402
    REGISTRY,
    BuildContext,
    RuleRegistry,
    build_tree,
    format_source,
)
from pssfmt.style import DEFAULT_STYLE, Style  # noqa: E402
from pssfmt.trivia import TriviaMap  # noqa: E402

pytestmark = pytest.mark.unit

#: Every construct the shipped rule set claims today (``P3-2``, Tier 1).
#: The wrapper rules the grammar puts between a body and its items are
#: deliberately absent -- ``decls`` looks *through* them rather than
#: registering them, so that one node owns each byte of trivia.
SHIPPED = {
    "compilation_unit",
    "package_declaration",
    "component_declaration",
    "action_declaration",
    "struct_declaration",
}


SAMPLES = {
    "package": "package p {\n}\n",
    "component with a member": (
        "package p {\n"
        "    component c {\n"
        "        int x = 1;\n"
        "    }\n"
        "}\n"
    ),
    "line comment": "package p {\n    // a note\n    int x;\n}\n",
    "block comment": "package p {\n    /* a\n       note */\n    int x;\n}\n",
    "trailing comment": "package p {\n    int x;  // why\n}\n",
    "hand-aligned block": (
        "package p {\n"
        "    int   a = 1;    // first\n"
        "    bit   b = 2;    // second\n"
        "    int   c = 30;   // third\n"
        "}\n"
    ),
    "no final newline": "package p {\n}",
    "blank lines kept": "package p {\n\n    int x;\n\n}\n",
    "crlf": "package p {\r\n    int x;\r\n}\r\n",
    "leading blank lines": "\n\npackage p {\n}\n",
    "only a comment": "// nothing else at all\n",
    "empty file": "",
    "unicode identifier text": "package p {\n    // ééé 中文\n    int x;\n}\n",
    "tabs the author chose": "package p {\n\tint x;\n}\n",
    "trailing whitespace the author left": "package p {\n    int x;   \n}\n",
}


# ---------------------------------------------------------------------------
# The claim: an empty rule set is already correct
# ---------------------------------------------------------------------------


class TestTheEmptyRuleSetChangesNothing:
    """``P3-1``'s safety argument, made checkable.

    If this ever fails, the fallback is not the null formatter's emission and
    the incremental-adoption argument collapses -- because every construct
    without a rule is riding on it.
    """

    @pytest.mark.parametrize("src", SAMPLES.values(), ids=list(SAMPLES))
    def test_output_is_the_input(self, src: str):
        assert format_source(src, registry=RuleRegistry()) == src

    @pytest.mark.parametrize("src", SAMPLES.values(), ids=list(SAMPLES))
    def test_it_agrees_with_the_null_formatter(self, src: str):
        """Not implied by the above: both could be wrong in the same way.

        It is still worth pinning, because the two reach the bytes by
        different routes -- the null formatter walks terminals and flushes
        what the walk stepped past, the fallback takes a token span -- and the
        constructs where those disagree are exactly the interesting ones.
        """
        from pssfmt.null import format_null

        assert format_source(src, registry=RuleRegistry()) == format_null(src).text

    def test_a_style_change_cannot_move_a_byte_while_no_rule_exists(self):
        """No rule means nothing consults the policy, so nothing may react to it.

        A narrow ``print_width`` that reflowed something here would mean some
        path is laying out rather than reproducing.
        """
        src = SAMPLES["hand-aligned block"]
        cramped = Style(print_width=20, indent_width=8, use_tabs=True)
        assert format_source(src, style=cramped, registry=RuleRegistry()) == src


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _context(src: str, registry: RuleRegistry) -> tuple:
    tree = cst.parse(src)
    trivia = TriviaMap(tree.tokens, max_blank_lines=DEFAULT_STYLE.max_blank_lines)
    return tree, BuildContext(style=DEFAULT_STYLE, trivia=trivia, registry=registry)


class TestDispatch:
    def test_a_registered_builder_is_used(self):
        reg = RuleRegistry()
        root_rule = cst.parse(SAMPLES["package"]).root.rule_name

        @reg.rule(root_rule)
        def _build(ctx, node):
            return text("REPLACED")

        assert format_source(SAMPLES["package"], registry=reg) == "REPLACED\n"

    def test_an_unregistered_rule_falls_back(self):
        reg = RuleRegistry()

        @reg.rule("a_rule_name_that_does_not_exist")
        def _build(ctx, node):  # pragma: no cover -- must never run
            raise AssertionError("dispatched to the wrong builder")

        assert format_source(SAMPLES["package"], registry=reg) == SAMPLES["package"]

    def test_a_builder_that_recurses_over_children_is_a_no_op(self):
        """The degenerate structural rule, and a useful property to have.

        A rule that only recurses reproduces its input, so a rule module can
        be written outside-in: claim the construct first, then replace the
        pieces one at a time, with the file never broken in between.
        """
        from pssfmt.layout import concat

        reg = RuleRegistry()
        src = SAMPLES["component with a member"]
        root_rule = cst.parse(src).root.rule_name

        @reg.rule(root_rule)
        def _build(ctx, node):
            return concat([ctx.build(c) for c in node.children])

        assert format_source(src, registry=reg) == src

    def test_rebinding_a_rule_name_is_an_error(self):
        """Two modules claiming one construct, where one silently never runs."""
        reg = RuleRegistry()

        @reg.rule("some_rule")
        def _first(ctx, node):  # pragma: no cover
            return text("")

        with pytest.raises(ValueError, match="already has a builder"):

            @reg.rule("some_rule")
            def _second(ctx, node):  # pragma: no cover
                return text("")

    def test_the_decorator_returns_the_function(self):
        """So a builder stays directly callable in a test."""
        reg = RuleRegistry()

        @reg.rule("some_rule")
        def _build(ctx, node):  # pragma: no cover
            return text("")

        assert callable(_build)

    def test_one_builder_may_claim_several_rules(self):
        reg = RuleRegistry()

        @reg.rule("rule_a", "rule_b")
        def _build(ctx, node):  # pragma: no cover
            return text("")

        assert reg.names() == ("rule_a", "rule_b")
        assert len(reg) == 2

    def test_registering_nothing_is_an_error(self):
        with pytest.raises(ValueError, match="at least one"):
            RuleRegistry().rule()

    def test_a_registry_copies_its_base_rather_than_sharing_it(self):
        base = RuleRegistry()
        base.register("rule_a", lambda ctx, node: text(""))
        derived = RuleRegistry(base)
        derived.register("rule_b", lambda ctx, node: text(""))
        assert "rule_b" not in base
        assert "rule_a" in derived

    def test_the_shipped_registry_is_untouched_by_these_tests(self):
        """Isolation, asserted rather than assumed.

        The reason ``RuleRegistry`` is a class at all. If this fails, some
        test above registered into the global and every later test is running
        against a registry that depends on collection order.

        Pinned by name rather than by count, so that a rule module which
        registered a construct it did not mean to claim shows up as the wrong
        *name* instead of the right total.
        """
        assert set(REGISTRY.names()) == SHIPPED


class TestErrorNodesAreNeverFormatted:
    """A recovery artifact is not a parse, and must not be laid out.

    Checked *before* the registry, so it cannot be defeated by registering a
    builder for the rule the error node happens to be labelled with.
    """

    def test_a_builder_is_not_called_for_an_error_node(self):
        reg = RuleRegistry()
        calls = []

        class _FakeError:
            is_rule = True
            is_error = True
            rule_name = "some_rule"
            start_token = 0
            stop_token = 0

        @reg.rule("some_rule")
        def _build(ctx, node):  # pragma: no cover -- must never run
            calls.append(node)
            return text("REPLACED")

        _tree, ctx = _context(SAMPLES["package"], reg)
        out = render(ctx.build(_FakeError()))
        assert calls == []
        assert out == "package"

    def test_broken_source_still_comes_back_unchanged(self):
        """The case that matters: a file the user is halfway through editing."""
        for src in ("package p { int x = ; }\n",
                    "component {{{ \n",
                    "package p {\n    int x = 1\n}\n"):
            assert format_source(src, registry=RuleRegistry()) == src


# ---------------------------------------------------------------------------
# The fallback itself
# ---------------------------------------------------------------------------


class TestVerbatimSpans:
    def test_a_node_reproduces_its_own_source_exactly(self):
        src = SAMPLES["component with a member"]
        tree, ctx = _context(src, RuleRegistry())

        seen = []

        def walk(node):
            if node.is_rule:
                seen.append(ctx.source_of(node))
                for child in node.children:
                    walk(child)

        walk(tree.root)
        assert seen, "no rule nodes to check"
        for span in seen:
            assert span in src, f"reconstructed text not present in the input: {span!r}"

    def test_a_node_spanning_no_code_tokens_is_empty(self):
        """An empty rule node -- the parser produces them, and a span for one
        that leaked outwards would emit a neighbour's tokens twice."""
        _tree, ctx = _context(SAMPLES["package"], RuleRegistry())

        class _Empty:
            is_rule = True
            is_error = False
            rule_name = "empty"
            start_token = -1
            stop_token = -1

        assert ctx.source_of(_Empty()) == ""
        assert ctx.build(_Empty()) == Verbatim("")

    def test_a_span_whose_bounds_land_on_trivia_stays_inside(self):
        """The bounds are stream indices, and a stream index need not be code.

        Every node the parser produces happens to start and stop on a code
        token, so this branch is never reached by the corpus -- which is
        exactly why it is worth a direct test. A span that widened *outwards*
        would emit the neighbouring construct a second time, and the corpus
        would not notice.

        ``package p {`` / ``int x;`` / ``}`` lexes so that index 5 is the
        whitespace before ``int`` and index 10 is the newline after ``;``.
        A node bounded by those two must cover ``int x ;`` and neither brace.
        """
        src = "package p {\n    int x;\n}\n"
        _tree, ctx = _context(src, RuleRegistry())

        class _OnTrivia:
            is_rule = True
            is_error = False
            rule_name = "spans_trivia"
            start_token = 5   # the WS before `int`
            stop_token = 10   # the WS after `;`

        span = ctx.source_of(_OnTrivia())
        assert "int" in span and "x" in span and ";" in span
        assert "{" not in span, f"span leaked backwards past the brace: {span!r}"
        assert "}" not in span, f"span leaked forwards past the brace: {span!r}"

    def test_none_builds_to_nothing(self):
        _tree, ctx = _context(SAMPLES["package"], RuleRegistry())
        assert ctx.build(None) == Verbatim("")

    def test_the_doc_is_kept_for_explain(self):
        """``P4-5`` wants the Layout that produced the text, not just the text."""
        built = build_tree(cst.parse(SAMPLES["package"]), registry=RuleRegistry())
        assert built.doc is not None
        assert built.trivia is not None


class TestTheFailSafeStillWraps:
    """``P1-3`` sits above this layer, not inside it.

    Worth pinning now: the moment a rule is wrong, this is the thing that
    stops it reaching the user's file, and it must not have been bypassed by
    the new entry point.
    """

    def test_format_safely_accepts_the_rule_formatter(self):
        from pssfmt.verify import format_safely

        src = SAMPLES["component with a member"]
        result = format_safely(src, formatter=lambda s: format_source(
            s, registry=RuleRegistry()))
        assert result.ok
        assert result.text == src

    def test_a_corrupting_rule_is_caught_and_the_file_survives(self):
        """The whole point, demonstrated with a rule that deletes code."""
        from pssfmt.verify import format_safely

        reg = RuleRegistry()
        src = SAMPLES["component with a member"]

        @reg.rule(cst.parse(src).root.rule_name)
        def _build(ctx, node):
            return text("package p { }")

        result = format_safely(src, formatter=lambda s: format_source(s, registry=reg))
        assert not result.ok
        assert result.text == src, "the fail-safe must hand back the original"

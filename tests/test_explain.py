"""``T-35`` -- ``pssfmt.explain`` and ``--explain`` (``P4-5``).

Two of these tests carry almost all the weight, and they are the two a
debugging tool is uniquely able to get wrong.

**The explanation must not change what it explains.** An instrumented run
swaps the registry and hands the engine a trace list; if either perturbed the
output, every report would describe a file the user never gets. Checked over
the corpus at three widths by the strongest available oracle -- the
uninstrumented formatter.

**The explanation must not be vacuously right.** Attributing every line to
``compilation_unit`` is a perfectly consistent, entirely useless answer, and
it is what the first implementation actually produced: builders return
``Concat`` nodes, ``concat()`` flattens nested concatenations, and the tagged
objects were spliced out of the tree before anything could see them. Nothing
crashed and no test failed. So the numbers are pinned.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest.importorskip("pssparser")

from support import corpus_files  # noqa: E402

from pssfmt.explain import (VERBATIM, Recorder, explain,  # noqa: E402
                            report)
from pssfmt.layout.engine import flat_width  # noqa: E402
from pssfmt.layout.ir import (EMPTY, Group, HardLine, Line, SoftLine,  # noqa: E402
                              concat, group, indent, text)
from pssfmt.rules import format_source  # noqa: E402
from pssfmt.style import Style  # noqa: E402

STYLES = (Style(), Style(print_width=40, indent_width=2),
          Style(print_width=120, indent_width=8))

SOURCE = """\
component a {
    int x;
    int y;
}
"""

FILES = corpus_files()
CASES = [(p, s) for p in FILES for s in STYLES]
IDS = ["%s-w%d" % (p.name, s.print_width) for p, s in CASES]


# ---------------------------------------------------------------------------
# The explanation must not change the thing it explains
# ---------------------------------------------------------------------------

@pytest.mark.corpus
@pytest.mark.integration
@pytest.mark.parametrize("path,style", CASES, ids=IDS)
def test_instrumenting_does_not_change_the_output(path, style):
    """The load-bearing invariant, against the uninstrumented formatter.

    ``--explain`` replaces the registry with a recording one and passes the
    engine a trace list and a watch set. Any of those leaking into a layout
    decision would make every report describe a file that is never written --
    and it would look completely plausible while doing it.
    """
    source = path.read_text(encoding="utf-8")
    assert explain(source, style=style).text == format_source(source,
                                                              style=style)


# ---------------------------------------------------------------------------
# ...and must not be vacuously right
# ---------------------------------------------------------------------------

@pytest.mark.corpus
@pytest.mark.integration
class TestAttributionIsRealAcrossTheCorpus:
    """Pinned as numbers because the failure mode is a consistent wrong answer.

    The bug these exist for did not raise, did not change any output, and
    produced a report in exactly the right shape -- every line of every file
    attributed to ``compilation_unit``. The only thing that distinguishes that
    from a working implementation is how *specific* the answers are.
    """

    def measure(self):
        total = root = 0
        rules = set()
        for path in FILES:
            spans = explain(path.read_text(encoding="utf-8")).spans()
            for span in spans:
                n = span.last - span.first + 1
                total += n
                root += n if span.rule == "compilation_unit" else 0
                rules.add(span.rule)
        return total, root, rules

    def test_most_lines_are_attributed_to_a_specific_rule(self):
        total, root, _ = self.measure()
        assert total > 4000, "corpus got smaller; retune these bounds"
        # Measured at 20.5%: file-level comments and constructs with no rule
        # legitimately land on the root. The broken version scored 100%.
        assert root / total < 0.35, (
            "%.1f%% of lines attributed to the root rule -- attribution has "
            "collapsed upward" % (100 * root / total))

    def test_many_distinct_rules_are_named(self):
        _, _, rules = self.measure()
        # Measured at 25.
        assert len(rules) >= 20, sorted(rules)


# ---------------------------------------------------------------------------
# Spans
# ---------------------------------------------------------------------------

class TestSpans:

    def test_every_line_is_attributed_exactly_once(self):
        exp = explain(SOURCE)
        spans = exp.spans()
        covered = [n for s in spans for n in range(s.first, s.last + 1)]
        assert covered == list(range(1, exp.lines + 1))

    def test_adjacent_lines_with_one_rule_are_one_span(self):
        spans = explain(SOURCE).spans()
        assert all(a.rule != b.rule for a, b in zip(spans, spans[1:]))

    def test_the_inner_rule_wins(self):
        """Being told the whole file was laid out by ``compilation_unit`` is
        being told nothing, so the innermost covering rule is the answer."""
        by_line = {n: s.rule for s in explain(SOURCE).spans()
                   for n in range(s.first, s.last + 1)}
        assert by_line[1] == "component_declaration"
        assert by_line[2] == "component_data_declaration"
        assert by_line[3] == "component_data_declaration"
        assert by_line[4] == "component_declaration"

    @pytest.mark.corpus
    @pytest.mark.integration
    @pytest.mark.parametrize("name,line,rule", [
        # The deepest-then-latest tiebreak. Without it the constraint's line
        # is credited to the action containing it -- true, and one level too
        # coarse to be the answer to "which rule laid this out".
        ("check_a.pss", 13, "constraint_declaration"),
        # The span end-clamp. Without it a rule's span collapses to its first
        # line and everything after falls through to whatever encloses it,
        # here all the way to the root.
        ("check.pss", 22, "extend_stmt"),
    ])
    def test_a_line_that_distinguishes_a_boundary_case(self, name, line, rule):
        """Two lines from the corpus, each chosen because a plausible
        simplification of :meth:`spans` gets exactly that line wrong.

        Both simplifications looked like dead code and were nearly deleted on
        that reasoning; measuring said they move 60 and 649 lines of corpus
        attribution respectively. An argument that a guard is redundant is not
        evidence that it is.
        """
        path = next(p for p in FILES if p.name == name)
        by_line = {n: s.rule
                   for s in explain(path.read_text(encoding="utf-8")).spans()
                   for n in range(s.first, s.last + 1)}
        assert by_line[line] == rule

    @pytest.mark.corpus
    @pytest.mark.integration
    def test_copied_text_is_reported_as_copied(self):
        """The signal a reader of a *deliberately incomplete* formatter most
        needs, and the one that silently did not exist.

        ``rule_for`` walks up until it finds a tag and there is always one --
        at worst the root rule -- so a copied region was attributed to
        whichever rule enclosed it. The corpus holds 40 ``Verbatim`` nodes and
        ``(verbatim)`` appeared zero times, while the documentation described
        it as the thing to look for. Pinned as a count so it cannot quietly go
        back to zero.
        """
        total = files = 0
        for path in FILES:
            n = sum(s.last - s.first + 1
                    for s in explain(path.read_text(encoding="utf-8")).spans()
                    if s.rule == VERBATIM)
            total += n
            files += n > 0
        # Pinned exactly, for the reason `T-30` pins builder reach as an
        # equality: a *fall* means attribution has regressed, and a *rise*
        # means a construct stopped being copied, at which point some comment
        # somewhere claiming it is unformatted has become false. Either way
        # the right response is to look, not to widen the bound.
        #
        # 41 of these lines and 3 of these files come from `_mark_copies`
        # alone -- `Verbatim` nodes sitting below the top level of a builder's
        # result. A looser bound passes without it.
        # 451 -> 449 with `P3-12`: two lines stopped being copied because
        # `enum` got a rule. That is the *rise* direction this comment
        # anticipates, and the response was the one it asks for -- look at
        # which lines, confirm they are enums, then move the number.
        assert (total, files) == (449, 36), (
            "%d lines across %d files report copied text, expected 451/36"
            % (total, files))

    def test_a_rule_is_named_for_every_line_or_verbatim_is(self):
        """There is no third answer. A line was laid out by a builder or it
        was copied, and a report that left a line unaccounted for would be
        hiding the interesting case."""
        exp = explain("component c {\n    exec init_down {\n"
                      "        x = 1;\n    }\n}\n")
        assert all(s.rule for s in exp.spans())
        assert sum(s.last - s.first + 1 for s in exp.spans()) == exp.lines


# ---------------------------------------------------------------------------
# Break decisions
# ---------------------------------------------------------------------------

class TestBreaks:

    def test_a_file_with_no_fit_decision_says_so(self):
        """And says it in words rather than by printing an empty table. An
        empty section reads as "the tool found nothing"; the truth is that
        there was nothing to find, which is itself the answer."""
        out = report(explain(SOURCE))
        assert "Every break in this file is unconditional" in out

    def test_a_group_that_does_not_fit_is_reported_with_both_widths(self):
        # A `static const` field, which is the construct whose builder makes a
        # group: taken from the corpus rather than invented, because the first
        # three sources tried here produced no group at all and passed the
        # test vacuously in the other direction.
        source = ("package p {\n"
                  "    static const bit[64]  SPI_CTRL_OFFSET_LONG = 0x00;\n"
                  "}\n")
        exp = explain(source, style=Style(print_width=40))
        broken = [b for b in exp.breaks() if b.reason == "too-wide"]
        assert broken, exp.breaks()
        b = broken[0]
        assert b.needed > b.available
        assert "needs %d columns and had %d" % (b.needed, b.available) == \
            b.describe()

    def test_a_group_that_fits_is_not_listed_as_a_break(self):
        """``breaks()`` is the *interesting* subset. Listing every group the
        engine resolved would bury the one that explains the problem under
        the hundreds that do not."""
        source = ("package p {\n"
                  "    static const bit[64]  A = 0x00;\n"
                  "}\n")
        exp = explain(source, style=Style(print_width=100))
        assert exp.decisions, "no group here at all; the test proves nothing"
        assert exp.breaks() == ()

    def test_line_numbers_count_blank_lines(self):
        """The engine tracks the output line for the trace itself, so a blank
        line that a ``HardLine`` carries has to be counted. Getting this wrong
        shifts every reported line number after the first blank line -- and a
        report that is confidently off by two is worse than no report."""
        source = ("package p {\n"
                  "    static const bit[64]  A = 0x00;\n"
                  "\n"
                  "\n"
                  "    static const bit[64]  SPI_CTRL_OFFSET_IS_LONG = 0x04;\n"
                  "}\n")
        exp = explain(source, style=Style(print_width=40))
        broken = exp.breaks()
        assert broken, "expected the second field to break"
        # The long field is on output line 4: the blank run collapses to one.
        assert broken[-1].line == 4, [b.line for b in broken]

    def test_a_forced_break_is_distinguished_from_a_measured_one(self):
        """They have opposite fixes: one is the rule's decision and no width
        will change it, the other is a width you can raise."""
        exp = explain(SOURCE)
        assert all(d.reason in ("forced", "fits", "too-wide", "inherited")
                   for d in exp.decisions)


class TestFlatWidth:
    """The "by how much" the engine's ``_fits`` deliberately never computes."""

    def test_text(self):
        assert flat_width(text("hello")) == 5

    def test_a_line_is_a_space_when_flat(self):
        assert flat_width(concat(text("a"), Line(), text("b"))) == 3

    def test_a_soft_line_is_nothing_when_flat(self):
        assert flat_width(concat(text("a"), SoftLine(), text("b"))) == 2

    def test_indent_does_not_add_width_when_flat(self):
        assert flat_width(indent(text("abc"), 4)) == 3

    def test_a_hard_break_ends_the_measurement(self):
        assert flat_width(concat(text("ab"), HardLine(), text("cdef"))) == 2

    def test_empty(self):
        assert flat_width(EMPTY) == 0

    def test_a_group_measures_its_contents(self):
        assert flat_width(group(concat(text("ab"), text("cd")))) == 4


# ---------------------------------------------------------------------------
# The tree
# ---------------------------------------------------------------------------

class TestTree:

    def test_every_node_gets_a_line(self):
        from pssfmt.layout.ir import children_of
        exp = explain(SOURCE)
        count = 0
        stack = [exp.doc]
        while stack:
            node = stack.pop()
            count += 1
            stack.extend(children_of(node))
        assert len(exp.tree().splitlines()) == count

    def test_groups_are_labelled_with_their_outcome(self):
        exp = explain("package p {\n"
                      "    static const bit[64]  SPI_CTRL_OFFSET_LONG = 0x00;\n"
                      "}\n", style=Style(print_width=40))
        assert "Group broken" in exp.tree()

    def test_the_alignment_mark_is_not_shown_as_a_control_character(self):
        """It is a column stop the alignment pass consumes, not corruption,
        and a debug tree that makes its own machinery look like a bug is worse
        than no debug tree."""
        tree = explain(SOURCE).tree()
        assert "\\x00" not in tree
        assert "\x00" not in tree
        assert "<column stop>" in tree


# ---------------------------------------------------------------------------
# The recorder
# ---------------------------------------------------------------------------

class TestRecorder:

    def test_it_tags_the_parts_of_a_concat_and_not_only_the_concat(self):
        """The regression test for the flattening bug, at the unit level.

        ``concat()`` splices a nested ``Concat`` out of existence, so a builder
        returning one loses the node that carried its tag. Tagging the parts is
        what makes attribution survive.
        """
        rec = Recorder()
        parts = (text("a"), text("b"))
        rec._tag(concat(*parts), "some_rule")
        assert all(id(p) in rec.origins for p in parts)

    def test_the_innermost_rule_wins(self):
        rec = Recorder()
        inner = text("x")
        rec._tag(inner, "inner_rule")
        rec._tag(concat(inner, text("y")), "outer_rule")
        assert rec.origins[id(inner)] == "inner_rule"

    def test_an_unregistered_name_stays_unregistered(self):
        assert Recorder().get("no_such_rule_exists") is None

    def test_tagged_nodes_are_kept_alive(self):
        """``id()`` of a collected object can be reissued, and a reissued key
        is a *wrong* answer rather than a missing one."""
        rec = Recorder()
        rec._tag(text("a"), "r")
        assert rec._kept


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

class TestReport:

    def test_the_header_names_the_file_and_the_style(self):
        out = report(explain(SOURCE, style=Style(print_width=60), name="f.pss"))
        assert out.startswith("f.pss: 4 output lines, print_width 60")

    def test_the_tree_is_opt_in(self):
        exp = explain(SOURCE)
        assert "Layout IR" not in report(exp)
        assert "Layout IR" in report(exp, tree=True)

    def test_overlong_lines_are_listed_with_what_produced_them(self):
        exp = explain(SOURCE, style=Style(print_width=5))
        out = report(exp)
        assert "Lines still over print_width" in out
        assert exp.overlong()

    def test_a_line_exactly_at_the_width_is_not_over_it(self):
        """``print_width`` is the column the output may reach, not the first
        one it may not."""
        source = "component aaaa {\n    int xxxxxxxxxx;\n}\n"
        width = max(len(line) for line in source.splitlines())
        exp = explain(source, style=Style(print_width=width))
        assert exp.overlong() == ()
        assert explain(source, style=Style(print_width=width - 1)).overlong()

    def test_a_file_with_nothing_over_the_width_omits_that_section(self):
        assert "over print_width" not in report(explain(SOURCE))

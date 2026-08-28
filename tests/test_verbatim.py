"""``T-27`` -- target-template ``exec`` bodies are sacred (``P3-8``, § 4.3).

``exec body C = \"\"\" … \"\"\"`` carries foreign text -- C, SystemVerilog,
whatever the target consumes -- through a PSS file. ``formatter.md`` section
4.3 is unusually blunt about it: emit it byte-for-byte, and **do not touch the
interior at all in v1**. Leading whitespace is semantic in some target
languages, trailing whitespace is part of the string's value, and the mustache
elements carry offsets into the raw text that are only valid while the raw
text has not moved.

What this file tests, and what it deliberately does not
--------------------------------------------------------
It tests the *guarantee*, in bytes, from outside. It does not test a rule,
because there is not one and should not be: an unhandled node is already
emitted exactly as written, so a builder returning verbatim would be a second
spelling of the fallback that no test could tell apart from the first. See
:mod:`pssfmt.verbatim` for the full argument, and ``P3-7``'s progress-log
entry for what happens when two guards each keep the other alive.

That makes these tests the whole of the safeguard rather than a supplement to
it, which is why they are byte comparisons on hostile inputs and not spot
checks.

The corpus cannot do this job
------------------------------
The 92 files hold **two** target templates, in one file, and both are tidy:
no tabs, no trailing whitespace, no blank runs, no brace alone on a line.
Every hazard below is therefore hand-written. That is also how the three
corpus style gates came to be wrong -- they scanned every output line
including foreign ones, and passed only because no corpus input reached the
case (``P3-6``'s ``extend``, again).
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.rules import format_source  # noqa: E402
from pssfmt.style import Style  # noqa: E402
from pssfmt.verbatim import verbatim_lines  # noqa: E402
from pssfmt.verify import format_safely, verify  # noqa: E402
from support import (lone_brace_offenders, tab_indent_offenders,  # noqa: E402
                     trailing_whitespace_offenders)

pytestmark = pytest.mark.unit

#: Enough surrounding PSS that the template is a *member* of a body the
#: formatter does lay out -- which is the only interesting position for it.
TEMPLATE = ('component c {\n'
            '    action a {\n'
            '        exec body C = """\n'
            '%s'
            '        """;\n'
            '    }\n'
            '}\n')


def wrap(interior: str) -> str:
    return TEMPLATE % interior


def fmt(src: str, style: Style = None) -> str:
    return format_source(src, style=style) if style else format_source(src)


class TestTheInteriorIsNeverTouched:
    """Byte identity, one hazard at a time, so a failure names the hazard."""

    @pytest.mark.parametrize("interior, hazard", [
        ("            int x = 1;   \n", "trailing whitespace"),
        ("\tint x = 1;\n", "a tab indent"),
        ("            if (y)\n            {\n            }\n", "an Allman brace"),
        ("            a();\n\n\n\n            b();\n", "a run of blank lines"),
        ("            " + "x" * 200 + ";\n", "a line past print_width"),
        ("  a();\n        b();\n   c();\n", "ragged indentation"),
        ("\n", "nothing but a newline"),
        ("", "an empty interior"),
        ("            func_{{func_id}}({{arg}});   {#} a mustache\n", "mustaches"),
        ("            {# a template comment #}\n", "a template comment"),
        ("            char *s = \"a string inside the string\";\n", "nested quotes"),
    ])
    def test_the_file_comes_back_byte_for_byte(self, interior, hazard):
        src = wrap(interior)
        assert fmt(src) == src, hazard

    @pytest.mark.parametrize("interior", [
        "            int x = 1;   \n", "\tint x = 1;\n",
        "            if (y)\n            {\n            }\n",
        "            a();\n\n\n\n            b();\n", "\n", "",
        "            func_{{func_id}}({{arg}});   {#} a mustache\n",
        "            {# a template comment #}\n",
        "            char *s = \"a string inside the string\";\n",
    ])
    def test_every_sample_actually_parses(self, interior):
        """Guards every byte-identity test above.

        A sample with a syntax error is reproduced verbatim by the error path
        regardless of what any rule does, so it would assert byte identity
        against a formatter that had been deleted. The hazards here are
        deliberately odd -- braces and mustaches inside a string -- which is
        exactly the kind of sample that stops parsing without anyone noticing.
        """
        from pssparser import cst
        assert cst.parse(wrap(interior)).num_syntax_errors == 0

    def test_and_the_verifier_agrees(self):
        """Byte identity is the strong claim; this is the independent one.

        ``verify`` re-lexes rather than comparing text, so it would catch a
        change that happened to be invisible to the comparison above -- and it
        is what runs in production, where the comparison does not.
        """
        src = wrap("            int x = 1;   \n\tint y;\n")
        violations = list(verify(src, fmt(src)))
        assert not violations, violations

    def test_the_fail_safe_is_not_what_is_doing_the_work(self):
        """A tripped fail-safe also returns the input unchanged.

        So every byte-identity test above would pass just as well on a
        formatter that corrupted the template and then caught itself. This is
        the test that says the output is untouched because nothing touched it.
        """
        result = format_safely(wrap("\tint x = 1;   \n"),
                               formatter=format_source)
        assert result.ok


class TestBothSpellingsOfATargetTemplate:
    """The grammar allows more shapes than the corpus writes."""

    def test_a_single_quoted_target_template(self):
        """``string_literal`` is not only the triple-quoted form.

        One line, so nothing about it spans lines, so the multi-line guard
        that protects the usual case does not apply. It survives for the
        plainer reason that no vocabulary contains a string token -- worth a
        test precisely because it is a *different* reason.
        """
        src = 'component c {\n    action a {\n        exec body C = "f( );";\n    }\n}\n'
        assert fmt(src) == src

    def test_an_exec_file_block(self):
        """``exec file "out.txt" = \"\"\" … \"\"\";`` -- zero corpus instances,
        and the same treatment, because the treatment is not construct-aware."""
        src = ('component c {\n    action a {\n'
               '        exec file "gen.c" = """\n'
               '\tint  x;\n'
               '        """;\n'
               '    }\n}\n')
        assert fmt(src) == src


class TestIsOwnLineIsSemantic:
    """§ 4.7.1.2: a directive alone on a line has its whitespace and newline
    excluded from the expansion, so moving one on or off its own line changes
    the string the tool generates.

    ``pssfmt`` cannot get this wrong, and the reason is worth stating rather
    than assuming: the CST does not decompose a template string at all. The
    whole thing, mustaches included, is one ``TRIPLE_DOUBLE_QUOTED_STRING``
    token, so "emit ``raw``" and "emit the token" are the same instruction and
    there is no element the formatter could relocate.

    These tests pin the observable consequence, since a future item that
    *does* decompose the string (§ 4.3.1's offsets exist for that) would break
    them rather than discovering this the hard way.
    """

    def test_a_directive_alone_on_its_line_stays_alone(self):
        src = wrap("            {{a}}\n            f();\n")
        assert fmt(src) == src

    def test_the_same_directive_inline_stays_inline(self):
        src = wrap("            f({{a}});\n")
        assert fmt(src) == src

    def test_the_two_are_not_normalised_towards_each_other(self):
        """The failure this guards against is subtle: both files above are
        individually stable, and a formatter that moved every directive onto
        its own line would still be idempotent. What it would not be is
        equal to the input."""
        alone = wrap("            {{a}}\n")
        inline = wrap("            f({{a}});\n")
        assert fmt(alone) != fmt(inline)
        assert fmt(alone) == alone and fmt(inline) == inline


class TestTheStylePropertiesDoNotApplyToForeignText:
    """The three corpus gates, run on the input the corpus does not contain.

    Without the exemption each of these fails, and the only way to make it
    pass would be to rewrite somebody else's C. This is the test that makes
    the exemption in ``T-20`` mean something -- no corpus file exercises it.
    """

    HOSTILE = wrap("\tint x = 1;   \n            if (y)\n            {\n            }\n")

    def test_the_hazards_really_are_in_the_output(self):
        """Guards the guard: if the sample stopped containing them, the three
        tests below would pass by testing nothing."""
        out = fmt(self.HOSTILE)
        lines = out.splitlines()
        assert any(ln != ln.rstrip() for ln in lines)
        assert any("\t" in ln[:len(ln) - len(ln.lstrip())] for ln in lines)
        assert any(ln.strip() == "{" for ln in lines)

    @pytest.mark.parametrize("offenders", [
        trailing_whitespace_offenders, tab_indent_offenders,
        lone_brace_offenders])
    def test_each_corpus_gate_passes_on_it(self, offenders):
        """The *same* functions ``T-20`` runs, on input the corpus lacks.

        Shared rather than re-implemented on purpose: a gate that took its
        exemption back would otherwise still pass here against a stale copy,
        which is the failure this test exists to prevent.
        """
        out = fmt(self.HOSTILE)
        assert not offenders(out, verbatim_lines(out))

    @pytest.mark.parametrize("offenders", [
        trailing_whitespace_offenders, tab_indent_offenders,
        lone_brace_offenders])
    def test_and_would_fail_without_the_exemption(self, offenders):
        """Guards the test above, which would pass on a sample that had
        stopped containing the hazard."""
        out = fmt(self.HOSTILE)
        assert offenders(out, set())

    def test_a_tab_indented_closing_delimiter_is_exempt_too(self):
        """The line the closing ``\"\"\"`` sits on is inside the token.

        Its leading whitespace is part of the string's value, so the tab gate
        must not reach it either -- and the exemption has to run one line
        further than the last line of *interior* text to cover it.

        Note where the line ends: the ``;`` and anything after it are outside
        the token, so a space there is ordinary trailing whitespace and *is*
        removed. The exemption covers the string, not the line.
        """
        src = ('component c {\n    action a {\n        exec body C = """\n'
               '            f();\n\t""";\n    }\n}\n')
        assert fmt(src) == src
        out = fmt(src)
        exempt = verbatim_lines(out)
        assert not tab_indent_offenders(out, exempt)
        assert tab_indent_offenders(out, set())

    def test_the_line_the_template_opens_on_is_not_exempt(self):
        """``exec body C = \"\"\"`` is composed by the formatter -- its
        indentation is the engine's -- so the style does apply to it. An
        exemption that swallowed it would quietly stop checking a real line."""
        out = fmt(self.HOSTILE)
        opener = next(i for i, ln in enumerate(out.splitlines(), 1)
                      if 'exec body' in ln)
        assert opener not in verbatim_lines(out)

    def test_a_file_with_no_foreign_text_exempts_nothing(self):
        assert verbatim_lines(fmt("component c {\n    int x;\n}\n")) == set()

    def test_a_comment_is_not_made_exempt_by_its_own_newline(self):
        """A ``//`` comment token carries its line terminator. Counting that
        as spanning a line would exempt the line *below* every comment in the
        file, which is most of the file."""
        out = fmt("component c {\n    // note\n    int x;\n}\n")
        assert verbatim_lines(out) == set()


class TestWhatThisCosts:
    """The limitation, asserted rather than described.

    A file holding a target template cannot be fully re-indented: the opening
    line moves with its siblings and the interior does not, because those
    columns are inside the token and are part of the string's value. The
    result is ragged, and it is the only answer that does not emit a different
    program.
    """

    def test_the_interior_does_not_follow_a_changed_indent_width(self):
        src = ('component c {\n    action a {\n        exec body C = """\n'
               '            f();\n        """;\n    }\n}\n')
        out = fmt(src, Style(indent_width=8))
        assert "                exec body C" in out      # opener moved
        assert "\n            f();\n" in out             # interior did not
        assert '\n        """;' in out                   # nor did the closer

    def test_which_is_still_idempotent(self):
        """Ragged is fine; unstable is not. Formatting the ragged output again
        must not chase the interior."""
        src = ('component c {\n    action a {\n        exec body C = """\n'
               '            f();\n        """;\n    }\n}\n')
        once = fmt(src, Style(indent_width=8))
        assert fmt(once, Style(indent_width=8)) == once

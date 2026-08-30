"""``T-39`` -- native ``exec`` bodies (``P3-8a``).

PSS spells three different things with one keyword and only one of them is
code this formatter may touch:

``exec body { … }``
    Ordinary PSS. **28 in the corpus across 18 files**, holding 109
    statements. This item's subject.
``exec body C = \"\"\"…\"\"\"``
    A foreign-language payload. ``P3-8``'s, deliberately without a builder,
    and it must come out byte for byte -- re-anchoring it changes what a
    generator emits.
``exec file "x" = \"\"\"…\"\"\"``
    The target-*file* form, same treatment.

The item was one line of layout, and that is the finding
--------------------------------------------------------
``PLAN.md`` scoped this as the largest thing left and said it "needs
``procedural_stmt`` (545 instances, 55 files) first, which is bigger than
``P3-7`` and ``P3-8`` together". True when written. ``P3-11b`` supplied that
prerequisite, and what was left was a ``_block`` call and a three-entry
vocabulary -- **the cost of an item is a fact about the frontier at the time,
not about the construct**.

Two wrappers, and only the first was obvious
---------------------------------------------
``exec_block_stmt`` wraps the three forms above and nothing looked through it,
which is why the frontier census reported *it* as the largest declined
construct rather than any exec block. Adding it to the passthrough set made
``exec_block`` reachable -- and unblocked **nothing inside it**, because an
exec body's members are ``exec_stmt``, not ``procedural_stmt``. A reach census
run with and without the new rule is what showed a delta of exactly zero.
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


def body(statements: str, kind: str = "body", style: Style = Style()) -> list:
    """*statements* inside an ``exec``, formatted, as the block's lines."""
    out = fmt("component c {\n    exec %s {\n%s\n    }\n}\n"
              % (kind, statements), style)
    lines = out.splitlines()
    assert lines[0] == "component c {" and lines[-1] == "}", out
    return lines[1:-1]


class TestItIsReachedAtAll:

    def test_the_rule_is_registered(self):
        assert "exec_block" in REGISTRY

    def test_the_target_code_kind_has_no_builder(self):
        """Absent on purpose, and asserted rather than assumed: registering
        one would be the fastest way to re-anchor a payload that must not
        move."""
        assert "target_code_exec_block" not in REGISTRY
        assert "target_file_exec_block" not in REGISTRY

    def test_an_exec_body_is_no_longer_reproduced_verbatim(self):
        assert body("x =   1 ;") == ["    exec body {", "        x = 1;",
                                     "    }"]

    def test_the_statements_inside_are_reached(self):
        """The half the first attempt missed. Registering ``exec_block``
        formatted 28 headers and left all 109 statements inside them
        reproduced, because ``exec_stmt`` is a second wrapper -- so this
        asserts about the *contents*, not the block."""
        assert body("regs . ctrl . write ( h ) ;\n        return ;") == [
            "    exec body {",
            "        regs.ctrl.write(h);",
            "        return;",
            "    }",
        ]


class TestTheBlock:

    def test_the_header_is_normalised(self):
        """28/28 one space after ``exec``, 28/28 one space before ``{``."""
        assert body("x = 1;")[0] == "    exec body {"
        assert fmt("component c {\n    exec  init_up   {\n"
                   "        x = 1;\n    }\n}\n").splitlines()[1] == \
            "    exec init_up {"

    @pytest.mark.parametrize("kind", ["body", "init_up", "init_down",
                                      "pre_solve", "post_solve", "run_start"])
    def test_every_kind_is_the_same_rule(self, kind):
        """``exec_kind`` is an ``identifier``, not a keyword -- the grammar
        has the keyword list commented out with a note that the kinds were
        made local. So the vocabulary is three entries and covers all of
        them."""
        assert body("x   =   1;", kind=kind)[0] == "    exec %s {" % kind

    def test_the_brace_moves_onto_the_header_line(self):
        out = fmt("component c {\n    exec body\n    {\n        x = 1;\n"
                  "    }\n}\n")
        assert "exec body {" in out
        assert "\n    {\n" not in out

    def test_the_body_is_indented_one_level(self):
        assert body("x = 1;\ny = 2;")[1:3] == ["        x = 1;",
                                               "        y = 2;"]

    def test_indent_width_reaches_it(self):
        out = fmt("component c {\nexec body {\nx = 1;\n}\n}\n",
                  Style(indent_width=2))
        assert out == ("component c {\n  exec body {\n    x = 1;\n  }\n}\n")

    def test_an_empty_body_closes_immediately(self):
        assert fmt("component c {\n    exec body {   }\n}\n") == \
            "component c {\n    exec body {}\n}\n"

    def test_a_blank_run_is_collapsed(self):
        out = body("x = 1;\n\n\n\n\ny = 2;")
        assert out == ["    exec body {", "        x = 1;", "",
                       "        y = 2;", "    }"]

    def test_a_comment_alone_in_a_body_survives(self):
        assert "// nothing yet" in "\n".join(body("// nothing yet"))


class TestTheTargetCodeKindIsUntouched:
    """The risk the item carries, and the only one: the wrapper over the three
    ``exec`` forms is now looked through, so a target-code block is *reached*
    where before it was not even asked about. It has no builder, so it is
    reproduced -- and these tests are the difference between believing that
    and knowing it."""

    SRC = ('component c {\n'
           '    action a {\n'
           '        exec body C = """\n'
           '              for (int i = 0; i < 4; i++) {\n'
           '                    poke(i);\n'
           '              }\n'
           '        """;\n'
           '    }\n}\n')

    def test_the_payload_is_byte_identical(self):
        out = fmt(self.SRC)
        assert '              for (int i = 0; i < 4; i++) {\n' in out
        assert '                    poke(i);\n' in out

    def test_it_is_unchanged_even_under_a_different_indent(self):
        """The sharpest version: re-anchoring is exactly what an indent change
        would do to it, and the payload must not move."""
        assert '                    poke(i);\n' in fmt(self.SRC,
                                                       Style(indent_width=8))

    def test_a_native_block_beside_it_is_still_formatted(self):
        """Both kinds in one body. The native one formats, the foreign one
        does not, and the wrapper cannot tell them apart -- the *registry*
        does."""
        out = fmt('component c {\n    action a {\n'
                  '        exec body {\n            x =   1;\n        }\n'
                  '        exec body C = """\n          poke(1);\n        """;\n'
                  '    }\n}\n')
        assert "            x = 1;" in out
        assert "          poke(1);\n" in out


class TestTheHatchReachesInside:
    """``P3-9``'s escape hatch is a check in ``decls._collect``, which is the
    one place a body's members are gathered -- so it covers an exec body's
    statements without a line written for them. Worth asserting now that there
    is something inside an exec worth switching off."""

    def test_a_hatched_region_is_frozen(self):
        out = body("// pssfmt off\n        a   =   1;\n"
                   "        bb  =   2;\n        // pssfmt on\n"
                   "        c   =   3;")
        assert "        a   =   1;" in out
        assert "        bb  =   2;" in out
        assert "        c   = 3;" in out

    def test_a_misspelt_directive_is_an_ordinary_comment(self):
        """The match is exact on purpose: prose about the formatter must never
        switch it off. ``P3-9b`` is the note for reporting these."""
        out = body("// pssfmt: off\n        d   =   4;")
        assert "        d   = 4;" in out


class TestWhatIsLeftAlone:

    def test_exec_super_is_reproduced(self):
        """``exec_stmt`` is ``procedural_stmt | exec_super_stmt``, and only
        the first has rules. Zero corpus instances, so this is the whole
        coverage -- and it is a decline, so it needs none."""
        assert "super ;" in "\n".join(body("super ;"))


class TestSafety:

    SOURCES = [
        "component c {\n    exec body {\n        x   =   1 ;\n    }\n}\n",
        "component c {\n    exec  init_up   {\n   h  =  f( d ) ;\n}\n}\n",
        "component c {\n    exec body {   }\n}\n",
        "component c {\n    exec body {\n        // only a comment\n    }\n}\n",
        TestTheTargetCodeKindIsUntouched.SRC,
        "component c {\n    exec body {\n        // pssfmt off\n"
        "        a   =   1;\n        // pssfmt on\n    }\n}\n",
        "component c {\n    action a {\n        exec body {\n"
        "            match ( m ) {\n                [0]: return;\n"
        "            }\n        }\n    }\n}\n",
        "component c {\n    exec body {\n        super ;\n    }\n}\n",
    ]

    @pytest.mark.parametrize("src", SOURCES)
    def test_the_verifier_accepts_it(self, src):
        result = format_safely(src, formatter=format_source)
        assert result.ok, result.diagnostic()

    @pytest.mark.parametrize("src", SOURCES)
    def test_it_is_idempotent(self, src):
        once = fmt(src)
        assert fmt(once) == once


class TestTheStyleIsConsulted:

    def test_the_brace_site_reaches_an_exec_header(self):
        out = fmt("component c {\n    exec body {\n        x = 1;\n    }\n}\n",
                  Style(spacing_overrides={Site.BRACE_OPEN: Spacing(3, 0)}))
        assert "    exec body   {" in out

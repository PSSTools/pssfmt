"""``T-37`` -- function headers (``P3-11a``).

``P3-11`` laid out a function *body* and left its header exactly as written,
pinning that in ``T-36``'s ``TestWhatIsLeftAlone`` so the boundary of the
increment could not be read as a bug. This file is that pin turned round.

Three productions carry a ``function_prototype`` and one vocabulary covers
all three, so the shapes below are the three registrations rather than one
rule tested three ways::

    function void f(bit[32] addr) { … }     procedural_function   118 / 46 files
    function void f(bit[32] addr);          function_decl          29 /  3 files
    import target C function void f();      import_function         7 /  3 files

What the corpus can and cannot say here
---------------------------------------
More than it could for ``P3-11``, and still not enough on its own. The 150
corpus prototypes are hand-written in the house style, so **six lines across
two files** move -- which is a good result for a formatter and a poor one for
a test suite, because five of those six are one gap each in one file. So the
tests that matter are the ones the corpus is silent on: a header nobody has
formatted, and the four constructs the vocabulary refuses.

The refusals get the most space, deliberately. Every one of them leaves the
author's text alone, which is indistinguishable from a rule that ran and
agreed -- so each is tested from *deliberately mis-spaced* input, where a
decline and a normalisation produce visibly different files.
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


def one(body: str, style: Style = Style()) -> str:
    """*body* inside a package, formatted, returned as its one middle line.

    Whole-line rather than substring, for ``T-36``'s reason: a substring
    assertion passes on output that is right where it looks and wrong
    everywhere else.
    """
    out = fmt("package p {\n%s\n}\n" % body, style)
    lines = out.splitlines()
    assert len(lines) == 3, out
    return lines[1]


class TestItIsReachedAtAll:
    """``P3-6``'s lesson, and the reason ``function_decl`` was 29 instances
    across 3 files of declined construct until now: a function with no body is
    not a block, so ``P3-11``'s registration could never have reached it."""

    @pytest.mark.parametrize("rule", ["function_decl", "import_function"])
    def test_the_rule_is_registered(self, rule):
        assert rule in REGISTRY


class TestTheMeasuredGaps:
    """One test per measurement in ``docs/style.rst``, from input that
    disagrees with it -- so each names the site it is about when it fails."""

    def test_the_name_is_tight_against_the_paren(self):
        """147 of 150, and the same ``Site.CALL_PAREN_OPEN`` a call uses:
        the survey counts ``callee -> '('`` lexically, so its 241/244 already
        includes every one of these."""
        assert one("    function void f ();") == "    function void f();"

    def test_the_parameters_are_tight_inside_the_parens(self):
        """137/137 after ``(`` and 138/138 before ``)``, on one line."""
        assert one("    function void f( int a );") == \
            "    function void f(int a);"

    def test_a_comma_is_followed_by_one_space(self):
        assert one("    function void f(int a,int b);") == \
            "    function void f(int a, int b);"

    def test_the_return_type_and_the_name_get_one_space(self):
        """149/150. The one that does not is the corpus's only padded name
        column, and :class:`TestNoColumnStop` is why it loses."""
        assert one("    function  void   f();") == "    function void f();"

    def test_the_qualifiers_are_part_of_the_header(self):
        """``target``/``solve``/``pure``/``static`` sit outside the prototype
        in the grammar and inside the header here, which is the span
        ``emit_span`` is handed."""
        assert one("    pure  static   function bit[8] g( );") == \
            "    pure static function bit[8] g();"

    def test_an_import_is_normalised_too(self):
        assert one("    import  target  C  function  void  poke ( bit[32] a ) ;") \
            == "    import target C function void poke(bit[32] a);"

    def test_the_no_prototype_import_form_survives(self):
        """``import target function read;`` -- the alternative of
        ``import_function`` with no prototype at all. Four in the corpus."""
        assert one("    import  target  function  read ;") == \
            "    import target function read;"

    def test_a_parameter_default_is_spaced(self):
        assert one("    function void f(bit[64] off=0777);") == \
            "    function void f(bit[64] off = 0777);"

    def test_a_direction_and_a_category_are_word_class(self):
        """``input``/``output``/``inout``, ``const``, ``ref``, ``type``. None
        has a second reading in a span of prototype tokens; all they need is
        the lexical floor, which is what ``WORD`` means."""
        assert one("    function void f(input int a, ref foo_s r, const int k);") \
            == "    function void f(input int a, ref foo_s r, const int k);"


class TestTheTypeDeclaratorFloor:
    """``bit[32] addr`` is a *type* meeting a *declarator*, and
    ``max(left.after, right.before)`` cannot say so: ``]`` has no ``after``
    worth setting -- give it one and ``a[i];`` becomes ``a[i] ;``.

    Shared with :mod:`pssfmt.rules.stmts` rather than restated here, which is
    the point of these two tests: the same predicate now has two callers, and
    a floor each module keeps its own copy of is a floor one of them loses.
    Without it the output is ``bit[32]addr`` -- still two tokens, so token
    equivalence passes and nothing else complains.
    """

    def test_a_width_bracket_is_separated_from_the_name(self):
        assert one("    function void f(bit[32]   addr);") == \
            "    function void f(bit[32] addr);"

    def test_a_template_close_is_separated_from_the_name(self):
        """The second shape, asked by *site* rather than by character: ``>``
        is ``TOK_GT``, which is also a comparison, so a check on the token
        would claim a type boundary in ``a > b`` too."""
        assert one("    function int demo(array<int,8>   a);") == \
            "    function int demo(array<int, 8> a);"

    def test_an_escaped_identifier_keeps_its_space_before_the_paren(self):
        """``P3-10``'s floor at a composition site that did not exist when it
        was written. ``Site.CALL_PAREN_OPEN`` is tight and ``ESCAPED_ID`` runs
        to the next whitespace, so emitting the measured gap would make
        ``\\esc(int`` a single identifier and the parameter list would vanish
        into the name."""
        assert one("    function void \\esc ( int x );") == \
            "    function void \\esc (int x);"


class TestNoColumnStop:
    """The corpus pads a prototype's name column exactly once, in one file::

        import target C function void poke(bit[32] addr, bit[32] data);
        import target C function int  sample_dut();

    A column stop there would let ``infer`` keep it, and it would cost
    nothing to emit. It is not emitted because 149 of the 150 write one
    space, and one voice does not decide a site -- the same call ``P3-4``
    made for ``**`` and ``P3-5`` made for a ``default`` constraint item.
    Pinned so that adding a stop later is a deliberate act with evidence
    behind it rather than a quiet improvement.
    """

    def test_a_padded_name_column_collapses(self):
        out = fmt("package p {\n"
                  "    function void poke(bit[32] a);\n"
                  "    function int  sample();\n"
                  "}\n")
        assert out == ("package p {\n"
                       "    function void poke(bit[32] a);\n"
                       "    function int sample();\n"
                       "}\n")


class TestWhatDeclines:
    """Four refusals, each from mis-spaced input so that "declined" and
    "agreed" are different files.

    A decline here is header-only. That is what ``P3-11a`` had to buy with a
    change to ``decls._header`` -- ``sites=None`` and ``sites={}`` were one
    value, and a function whose prototype must not be touched still has a
    body that should be laid out.
    """

    def test_a_wrapped_prototype_is_reproduced(self):
        """Three of the corpus's five are hand-aligned parameter tables and
        all five join to 90-plus columns. ``emit_span`` discards newlines, so
        formatting one is joining one, and there is no parameter-list break
        policy to do better -- ``Construct.PARAMETER_LIST`` exists and nothing
        sets it."""
        out = fmt("component c {\n"
                  "    target function void check(\n"
                  "        addr_handle_t  base,\n"
                  "        bit[32]        nbytes) {\n"
                  " int x;\n"
                  "}\n"
                  "}\n")
        assert ("    target function void check(\n"
                "        addr_handle_t  base,\n"
                "        bit[32]        nbytes) {\n") in out

    def test_a_wrapped_prototype_still_gets_its_body_formatted(self):
        """The half of the decline that is not free. Reproducing the header
        by reproducing the whole construct would have undone ``P3-11`` for
        every function whose parameters are a table."""
        out = fmt("component c {\n"
                  "    target function void check(\n"
                  "        bit[32]        nbytes) {\n"
                  " int x;\n"
                  "}\n"
                  "}\n")
        assert "\n        int x;\n    }\n" in out

    def test_varargs_declines(self):
        """One instance, one file. ``Spacing(0, 1)`` -- the comma's shape --
        would reproduce it exactly, and that is the trap rather than the
        answer: a site invented from a single instance reads as measured."""
        assert "function void  varargs( int...  args ) {" in fmt(
            "component c {\n"
            "    function void  varargs( int...  args ) { }\n}\n")

    def test_a_comment_inside_a_prototype_declines(self):
        """``function void print(string fmt/*, type ... args*/);`` -- two in
        the corpus, both in ``std_pkg.pss``. ``emit_span`` refuses any span
        holding a comment, so this needs nothing here; it is tested because
        the *reason* it holds is one function away from this vocabulary."""
        assert one("    function void  f( string   fmt /* why */ );") == \
            "    function void  f( string   fmt /* why */ );"

    def test_a_declined_header_is_byte_identical(self):
        """Stated as bytes rather than as a substring, because "declined"
        means the author's text and nothing near it."""
        src = ("package p {\n"
               "    function void  f( string   fmt /* why */ );\n"
               "}\n")
        assert fmt(src) == src


class TestTheStyleIsConsulted:
    """``T-32``'s lesson pointed at a rule instead of a config key: the way
    this fails is silently, by copying text that looks like what a site would
    have produced. Each of these sets a non-default value and requires the
    output to move, which no reproduce-the-header path can do.
    """

    def test_the_comma_site_reaches_a_parameter_list(self):
        assert one("    function void f(int a, int b);",
                   Style(spacing_overrides={Site.COMMA: Spacing(0, 0)})) == \
            "    function void f(int a,int b);"

    def test_the_call_paren_site_reaches_a_prototype(self):
        assert one("    function void f(int a);",
                   Style(spacing_overrides={
                       Site.CALL_PAREN_OPEN: Spacing(1, 1),
                       Site.CALL_PAREN_CLOSE: Spacing(1, 0)})) == \
            "    function void f ( int a );"

    def test_the_semicolon_site_reaches_a_declaration(self):
        """The one of these written *because* of a surviving mutant.
        ``Site.SEMICOLON`` is ``Spacing(0, 0)`` and so is ``WORD``, so mapping
        the token to either renders identically under every shipped style --
        the entry looks decided and is inert, which is the shape
        ``activities.py`` documents for ``TOK_DO``. Here it is cheaper to make
        the difference observable than to write the proof that it is not."""
        assert one("    function void f();",
                   Style(spacing_overrides={Site.SEMICOLON: Spacing(1, 0)})) \
            == "    function void f() ;"

    def test_the_assign_site_reaches_a_parameter_default(self):
        assert one("    function void f(int a = 1);",
                   Style(spacing_overrides={Site.ASSIGN: Spacing(0, 0)})) == \
            "    function void f(int a=1);"


class TestSafety:

    SOURCES = [
        "package p {\n    function void  f ( bit[32]  a , int b ) ;\n}\n",
        "package p {\n    import  target  C  function int  s ( ) ;\n}\n",
        "package p {\n    import target function read;\n}\n",
        "package p {\n    function void f(string fmt /* why */);\n}\n",
        "component c {\n    function void  varargs( int... args ) { }\n}\n",
        "component c {\n    function  bit[32]  f( int  ch )\n"
        "{\n   return ch * 4;\n  }\n}\n",
        "component c {\n    target function void check(\n"
        "        addr_handle_t  base,\n        bit[32]        n) {\n"
        " int x;\n}\n}\n",
        "package p {\n    function void \\esc (int x);\n}\n",
        "package p {\n    function int demo(array<int,8> a, int n);\n}\n",
    ]

    @pytest.mark.parametrize("src", SOURCES)
    def test_the_verifier_accepts_it(self, src):
        result = format_safely(src, formatter=format_source)
        assert result.ok, result.diagnostic()

    @pytest.mark.parametrize("src", SOURCES)
    def test_it_is_idempotent(self, src):
        once = fmt(src)
        assert fmt(once) == once

    @pytest.mark.parametrize("src", SOURCES)
    def test_no_line_exceeds_the_width(self, src):
        """A header is joined onto one line, which is the one way this item
        can make a file worse. It is why a wrapped prototype declines; these
        inputs are the short ones, and this asserts the joining did not
        overshoot on them either."""
        assert all(len(line) <= 80 for line in fmt(src).splitlines())

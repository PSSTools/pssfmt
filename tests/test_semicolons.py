"""``T-41`` -- the optional semicolon (``optional_semicolon``).

PSS lets a body item be nothing but a ``;``. Ten body rules carry a bare
``TOK_SEMICOLON`` alternative, so ``struct s { … };`` is a struct followed by
an empty item and the ``;`` says nothing at all. ``omit`` deletes it; that is
the default, and it is the **only** thing in this formatter that removes a
token the author wrote.

Which is why this file is longer than the option is big. Three questions, and
the second is the one with teeth:

1. Does the option do what it says, both ways?
2. Does it leave alone every ``;`` that is *not* optional? The grammar makes
   some required terminators siblings of the thing they terminate, so a
   required ``;`` and a decorative one occupy the same position and look
   identical. ``int a[4] = {1, 2};`` and ``enum e {A, B};`` are the pair that
   matters -- both a lone ``;`` on the same line, both after a ``}``.
3. Does the safety net still hold? Deleting a token breaks the verifier's
   token-equivalence check by construction, so that check has an exemption
   now, and an exemption is only as good as what it refuses.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.config import ConfigError, style_from_table  # noqa: E402
from pssfmt.rules import format_source  # noqa: E402
from pssfmt.rules.decls import _SELF_TERMINATING  # noqa: E402
from pssfmt.style import (  # noqa: E402
    Construct,
    DEFAULT_STYLE,
    SemicolonMode,
    Style,
)
from pssfmt.verify import (  # noqa: E402
    check_token_equivalence,
    format_safely,
    verify,
)

pytestmark = pytest.mark.unit

PRESERVE = Style(optional_semicolon=SemicolonMode.PRESERVE)
REQUIRE = Style(optional_semicolon=SemicolonMode.REQUIRE)


def fmt(src: str, style: Style = DEFAULT_STYLE) -> str:
    return format_source(src, style=style)


def body(src: str, style: Style = DEFAULT_STYLE):
    """The lines inside the outermost ``package p { … }``."""
    return fmt("package p {\n%s\n}\n" % src, style).splitlines()[1:-1]


# ---------------------------------------------------------------------------
# The option
# ---------------------------------------------------------------------------

class TestTheDefaultOmits:

    @pytest.mark.parametrize("decl", [
        "struct s {}",
        "buffer b {}",
        "component c {}",
        "enum e { A, B }",
        "struct s : base_s {}",
    ])
    def test_a_declaration_loses_it(self, decl):
        assert body("    %s;" % decl) == ["    %s" % decl]

    def test_a_declaration_inside_a_component_loses_it_too(self):
        """``action`` is not a package body item, so it needs its own case."""
        assert fmt("component c {\n    action a {};\n}\n") == (
            "component c {\n    action a {}\n}\n")

    def test_at_the_top_level_of_a_file_too(self):
        """The file itself is a body: the grammar's top level *is*
        ``package_body_item``, empty-item alternative included."""
        assert fmt("component c {};\n") == "component c {}\n"

    def test_a_nested_body_too(self):
        assert fmt("package p {\n    component c {\n"
                   "        action a {};\n    }\n}\n") == (
            "package p {\n"
            "    component c {\n"
            "        action a {}\n"
            "    }\n"
            "}\n")

    def test_the_result_is_stable(self):
        once = fmt("package p {\n    struct s {};\n}\n")
        assert fmt(once) == once


class TestPreserveKeepsIt:

    def test_the_semicolon_survives(self):
        assert body("    struct s {};", PRESERVE) == ["    struct s {};"]

    def test_it_is_the_previous_behaviour(self):
        """Merged onto the line it terminates rather than left as a member of
        its own -- what ``P3-2`` built the shared merge for."""
        assert body("    struct s {}   ;", PRESERVE) == ["    struct s {};"]

    def test_a_semicolon_on_its_own_line_is_left_where_it_is(self):
        """Neither mode touches it, in either direction. The merge and the
        deletion are both same-line rules, because a ``;`` the author put on
        a line of its own is not the one this option is about."""
        for style in (DEFAULT_STYLE, PRESERVE):
            assert body("    struct s {}\n    ;", style) == [
                "    struct s {}", "    ;"]

    def test_a_file_with_none_is_unaffected_either_way(self):
        src = "package p {\n    struct s {}\n}\n"
        assert fmt(src) == fmt(src, PRESERVE) == src


class TestRequireWritesIt:

    @pytest.mark.parametrize("decl", [
        "struct s {}",
        "buffer b {}",
        "component c {}",
        "enum e { A, B }",
    ])
    def test_a_declaration_gains_one(self, decl):
        assert body("    %s" % decl, REQUIRE) == ["    %s;" % decl]

    def test_the_file_s_own_declarations_too(self):
        assert fmt("component c {}\n", REQUIRE) == "component c {};\n"

    def test_one_that_already_has_it_does_not_gain_a_second(self):
        """The lookahead. Without it the second pass would write ``};;``."""
        assert body("    struct s {};", REQUIRE) == ["    struct s {};"]

    def test_it_is_idempotent(self):
        once = fmt("package p {\n    struct s {}\n    enum e { A }\n}\n",
                   REQUIRE)
        assert fmt(once, REQUIRE) == once

    def test_it_goes_before_the_trailing_comment(self):
        """Composed onto the member rather than concatenated after it. The
        other order puts the semicolon inside the comment."""
        assert body("    struct s {}  // note", REQUIRE) == [
            "    struct s {};  // note"]

    def test_a_terminated_statement_does_not_gain_one(self):
        """The asymmetry with ``omit``, and the whole difference between a
        house style and a mess: ``int x;`` must not become ``int x;;``."""
        assert body("    int x;", REQUIRE) == ["    int x;"]

    def test_an_enum_item_does_not_gain_one(self):
        """``enum_item`` has no empty-item alternative, so a ``;`` between two
        of them is a syntax error rather than a style."""
        assert body("    enum e { A, B }", REQUIRE) == ["    enum e { A, B };"]

    def test_a_hatched_member_does_not_gain_one(self):
        src = ("package p {\n    // pssfmt off\n    struct s {A}\n"
               "    // pssfmt on\n}\n")
        assert fmt(src, REQUIRE) == src

    def test_a_file_the_parser_did_not_understand_gains_nothing(self):
        """``pathological/lone_quote.pss``. Every *local* test passes on its
        ``component`` -- it ends in an honest ``}`` -- and writing ``};`` at
        the end of it makes the file parse worse, because the trailing garbage
        lexes differently with one more character after it. Insertion asks
        about the whole file; deletion does not have to."""
        src = ("component c {\n    int x = 'ff;\n    int y = 4';\n"
               "    int z = ';\n}\n")
        assert fmt(src, REQUIRE) == src

    def test_the_two_modes_are_round_trip_inverses(self):
        src = ("package p {\n    struct s {}\n    enum e { A };\n"
               "    component c {};\n}\n")
        assert fmt(fmt(src, REQUIRE)) == fmt(src)
        assert fmt(fmt(src), REQUIRE) == fmt(src, REQUIRE)


class TestItIsAStyleQuestion:
    """Asked through the style seam, so a house style can answer it."""

    def test_a_per_construct_override_reaches_the_rule(self):
        style = Style(optional_semicolon=SemicolonMode.OMIT,
                      semicolon_overrides={
                          Construct.COMPONENT_BODY: SemicolonMode.PRESERVE})
        out = fmt("package p {\n    component c {\n        action a {};\n"
                  "    }\n\n    struct s {};\n}\n")
        assert "action a {}\n" in out and "struct s {}\n" in out

        out = fmt("package p {\n    component c {\n        action a {};\n"
                  "    }\n\n    struct s {};\n}\n", style)
        assert "action a {};\n" in out, out
        assert "struct s {}\n" in out, out

    @pytest.mark.parametrize("value, mode", [
        ("omit", SemicolonMode.OMIT),
        ("preserve", SemicolonMode.PRESERVE),
        ("require", SemicolonMode.REQUIRE),
    ])
    def test_the_config_key_sets_it(self, tmp_path, value, mode):
        style = style_from_table({"optional_semicolon": value},
                                 tmp_path / ".pssfmt")
        assert style.optional_semicolon is mode

    def test_a_misspelling_is_refused_with_a_suggestion(self, tmp_path):
        with pytest.raises(ConfigError) as raised:
            style_from_table({"optional_semicolon": "presrve"},
                             tmp_path / ".pssfmt")
        assert "did you mean `preserve`?" in str(raised.value)


# ---------------------------------------------------------------------------
# The semicolons that are not optional
# ---------------------------------------------------------------------------

class TestRequiredSemicolonsStay:
    """The whole risk of this option, in one class.

    Each of these is a lone ``;`` sitting as the next sibling of the member
    before it, on the same line -- indistinguishable by *position* from the
    decoration cases above. Only the grammar of the member separates them.
    """

    def test_a_local_declaration_keeps_its_terminator(self):
        """``procedural_data_declaration`` ends in an expression; the ``;``
        is a sibling ``procedural_stmt`` and is not optional."""
        assert "int x = 1;" in fmt(
            "package p {\n    function void f() {\n        int x = 1;\n"
            "    }\n}\n")

    def test_an_aggregate_initialiser_keeps_its_terminator(self):
        """The case that rules out "it follows a ``}``, so it is decoration".

        ``int a[4] = {1, 2};`` is a lone ``;`` after a ``}`` on the same line,
        exactly like ``enum e {A, B};`` -- and dropping it is a syntax error.
        """
        out = fmt("package p {\n    function void f() {\n"
                  "        int a[4] = {1, 2};\n    }\n}\n")
        assert "= {1, 2};" in out, out

    def test_a_field_declaration_keeps_its_terminator(self):
        assert body("    int x;") == ["    int x;"]

    def test_an_inline_constraint_traversal_keeps_its_semicolon(self):
        """Not required by the grammar, and kept anyway.

        ``x1 with { … };`` reaches the recursive knot in ``constraint_set``
        that the derivation in ``tools/semicolon_survey.py`` cannot prove, so
        the rule is not in :data:`_SELF_TERMINATING` and the semicolon stays.
        Unproven fails closed -- and the corpus writes all four of these with
        the semicolon, so caution and evidence agree here.
        """
        src = ("package p {\n    action a {\n        b x1;\n"
               "        activity {\n            x1 with { x == 1; };\n"
               "        }\n    }\n}\n")
        assert "x1 with { x == 1; };" in fmt(src), fmt(src)

    def test_error_recovery_never_loses_one(self):
        """``pathological/unclosed_string.pss``, reduced.

        The unterminated literal runs to the end of its line, so the parser
        builds a ``component_data_declaration`` -- a rule that *does*
        self-terminate -- which stopped before any terminator, and the next
        line's ``;`` became its sibling. The rule name says the ``;`` is
        decoration; the tokens say the member never ended. The tokens win.
        """
        src = 'component c {\n    string s = "never closed;\n    int x = 1;\n}\n'
        assert fmt(src).count(";") == src.count(";")

    def test_a_hatched_member_is_not_followed_into(self):
        """``// pssfmt off`` means hands off, including the ``;`` after it."""
        src = ("package p {\n    // pssfmt off\n    struct s {A};\n"
               "    // pssfmt on\n}\n")
        assert "struct s {A};" in fmt(src), fmt(src)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

class TestCommentsSurviveTheDeletion:

    def test_a_trailing_comment_moves_to_the_brace(self):
        assert body("    struct s {};  // done") == [
            "    struct s {}  // done"]

    def test_a_comment_between_the_brace_and_the_semicolon_stops_it(self):
        """Nothing for the comment to hang off if the ``;`` goes, so it
        stays. Declining is the same answer ``_is_trailing_semicolon`` already
        gave this shape before the option existed."""
        out = fmt("package p {\n    struct s {} /* why */ ;\n}\n")
        assert "/* why */" in out
        assert ";" in out

    def test_the_comment_above_the_member_is_untouched(self):
        assert body("    // why\n    struct s {};") == [
            "    // why", "    struct s {}"]


# ---------------------------------------------------------------------------
# The safety net
# ---------------------------------------------------------------------------

class TestTheVerifier:

    SOURCES = [
        "package p {\n    struct s {};\n}\n",
        "package p {\n    enum e {A, B};\n}\n",
        "package p {\n    struct s {};  // done\n}\n",
        "component c {};\n",
        "package p {\n    function void f() {\n        int a[4] = {1, 2};\n"
        "    }\n}\n",
        'component c {\n    string s = "never closed;\n    int x = 1;\n}\n',
    ]

    @pytest.mark.parametrize("src", SOURCES)
    def test_the_fail_safe_accepts_the_default_style(self, src):
        result = format_safely(src, formatter=format_source,
                               allow_dropped_semicolons=True)
        assert result.ok, result.diagnostic()

    @pytest.mark.parametrize("src", SOURCES)
    def test_preserve_needs_no_exemption(self, src):
        """The strict check still passes when nothing is dropped, which is
        what makes the exemption an opt-in rather than a hole."""
        result = format_safely(
            src, formatter=lambda s: format_source(s, style=PRESERVE))
        assert result.ok, result.diagnostic()

    def test_forgetting_the_exemption_rejects_the_format(self):
        """The default is strict, so a caller that drops semicolons and does
        not say so gets a declined file rather than an unchecked one."""
        result = format_safely("package p {\n    struct s {};\n}\n",
                               formatter=format_source)
        assert not result.ok
        assert result.text == "package p {\n    struct s {};\n}\n"

    @pytest.mark.parametrize("src", SOURCES)
    def test_the_fail_safe_accepts_require(self, src):
        result = format_safely(
            src, formatter=lambda s: format_source(s, style=REQUIRE),
            allow_added_semicolons=True)
        assert result.ok, result.diagnostic()

    def test_the_exemption_refuses_an_inserted_semicolon(self):
        """Each direction is opted into separately: a formatter set to
        ``omit`` that inserted one is a bug, and this is where it surfaces."""
        assert check_token_equivalence("int x\n", "int x;\n", True)

    def test_the_other_exemption_refuses_a_dropped_one(self):
        assert check_token_equivalence("int x;\n", "int x\n",
                                       False, True)

    def test_the_other_exemption_allows_an_inserted_one(self):
        assert check_token_equivalence("int x\n", "int x;\n",
                                       False, True) == ()

    def test_both_directions_together_forgive_a_moved_semicolon(self):
        """Recorded rather than hidden. Only ``semicolon_overrides`` can turn
        both on at once -- a single global mode is one or the other -- and
        check 3 still has to pass, but within check 1 this is the cost."""
        assert check_token_equivalence("a; b\n", "a b;\n", True, True) == ()
        assert check_token_equivalence("a; b\n", "a b;\n", True, False)

    def test_the_exemption_refuses_any_other_deletion(self):
        assert check_token_equivalence("int x;\n", "x;\n", True)

    def test_the_exemption_refuses_a_moved_semicolon(self):
        """A general diff would forgive this as a deletion plus an insertion.
        The forward walk only ever skips on the input side, so it does not."""
        assert check_token_equivalence("a; b\n", "a b;\n", True)

    def test_the_exemption_allows_only_semicolons(self):
        assert check_token_equivalence("a; b;\n", "a b;\n", True) == ()

    def test_a_dropped_comment_still_fails(self):
        violations = check_token_equivalence(
            "struct s {}; // why\n", "struct s {}\n", True)
        assert any(v.kind == "comments" for v in violations)

    def test_verify_defaults_to_strict(self):
        assert verify("package p {\n    struct s {};\n}\n",
                      "package p {\n    struct s {}\n}\n")
        assert verify("package p {\n    struct s {};\n}\n",
                      "package p {\n    struct s {}\n}\n",
                      allow_dropped_semicolons=True) == ()


# ---------------------------------------------------------------------------
# The derived set
# ---------------------------------------------------------------------------

class TestTheSelfTerminatingSet:
    """It is data, and data pasted from a generator goes stale silently.

    ``tests/corpus/test_semicolon_grammar.py`` re-derives it from
    ``PSSParser.g4`` when the grammar is on disk. These are the properties
    that hold with or without it.
    """

    def test_the_rules_this_option_was_written_for_are_in_it(self):
        for name in ("struct_declaration", "component_declaration",
                     "action_declaration", "package_declaration",
                     "enum_declaration", "extend_stmt", "data_declaration"):
            assert name in _SELF_TERMINATING, name

    def test_the_rule_that_would_break_a_file_is_not(self):
        assert "procedural_data_declaration" not in _SELF_TERMINATING

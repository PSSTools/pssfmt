"""``T-21`` -- emitting tokens with computed spacing (``P3-2b``).

The first rules that write PSS out rather than move the author's text around,
so the first place a style value can produce something that is not merely
ugly but *wrong*. These tests are split accordingly:

* what the style decides -- gaps, and that changing the policy changes them;
* what the style must never be allowed to decide -- whether two tokens stay
  two tokens;
* what the emitter declines, which is everything it was not told to expect.

The third group is the one that keeps the other two honest. An emitter that
guessed at an unfamiliar token would make this module's blast radius the
whole language instead of two closed vocabularies.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.rules import format_source  # noqa: E402
from pssfmt.rules.tokens import WORD, must_separate  # noqa: E402
from pssfmt.style import Site, Spacing, Style  # noqa: E402
from pssfmt.verify import verify  # noqa: E402

pytestmark = pytest.mark.unit


def fmt(src: str, style: Style = None) -> str:
    return format_source(src, style=style) if style else format_source(src)


class _Tok:
    """The two attributes :func:`must_separate` reads."""

    def __init__(self, text: str, type_name: str = "ID"):
        self.text = text
        self.type_name = type_name


# ---------------------------------------------------------------------------
# What the style decides
# ---------------------------------------------------------------------------


class TestNormalisation:
    @pytest.mark.parametrize("src,expected", [
        ("import a::b;\n", "import a::b;\n"),
        ("import  a :: b ;\n", "import a::b;\n"),
        ("import a::*  ;\n", "import a::*;\n"),
        ("import\na::b;\n", "import a::b;\n"),
    ], ids=["already-canonical", "spaced-out", "wildcard", "wrapped"])
    def test_an_import_is_written_out(self, src: str, expected: str):
        assert fmt(src) == expected

    def test_the_wildcard_is_not_multiplication(self):
        """``*`` is spaced as an operator and tight as an import wildcard.

        The same character, two sites, and the reason the vocabulary a caller
        passes is a parameter rather than a global table. A single mapping
        would have to pick one, and picking ``Site.MULTIPLICATIVE`` emits
        ``import pkg:: * ;``.
        """
        assert fmt("import pkg::*;\n") == "import pkg::*;\n"

    @pytest.mark.parametrize("src,expected", [
        ("struct  s {}\n", "struct s {}\n"),
        ("struct s:base_s {}\n", "struct s : base_s {}\n"),
        ("component  c  :  b  {}\n", "component c : b {}\n"),
        ("pure  component c {}\n", "pure component c {}\n"),
        ("component\nc\n:\nb {}\n", "component c : b {}\n"),
        ("component c {\n    action  a:b {}\n}\n",
         "component c {\n    action a : b {}\n}\n"),
    ], ids=["extra-space", "tight-colon", "spaced-out", "pure", "wrapped",
            "action"])
    def test_a_header_is_written_out(self, src: str, expected: str):
        assert fmt(src) == expected


class TestTheGapsComeFromTheStyle:
    def test_the_inheritance_colon_follows_its_site(self):
        style = Style(spacing_overrides={Site.COLON_INHERITANCE: Spacing(0, 0)})
        assert fmt("struct s : base_s {}\n", style) == "struct s:base_s {}\n"

    def test_the_scope_resolution_gap_follows_its_site(self):
        style = Style(spacing_overrides={Site.SCOPE_RESOLUTION: Spacing(1, 1)})
        assert fmt("import a::b;\n", style) == "import a :: b;\n"

    def test_the_semicolon_gap_follows_its_site(self):
        style = Style(spacing_overrides={Site.SEMICOLON: Spacing(1, 0)})
        assert fmt("import a::b;\n", style) == "import a::b ;\n"

    def test_a_gap_is_the_maximum_not_the_sum(self):
        """``docs/style.rst``: composition has to be order-independent.

        With ``::`` spaced on both sides and ``;`` spaced before, the gap
        between ``b`` and ``;`` is one space rather than two.
        """
        style = Style(spacing_overrides={
            Site.SCOPE_RESOLUTION: Spacing(1, 1),
            Site.SEMICOLON: Spacing(1, 1),
        })
        assert fmt("import a::b;\n", style) == "import a :: b ;\n"


# ---------------------------------------------------------------------------
# What the style must not be allowed to decide
# ---------------------------------------------------------------------------


class TestTokensNeverMerge:
    """The floor under every computed gap.

    A style may set any site to zero -- that is a legitimate house style. It
    may never thereby change what the file *means*, and the distance between
    those two is one space.
    """

    @pytest.mark.parametrize("left,right,expected", [
        (_Tok("package", "TOK_PACKAGE"), _Tok("p"), True),
        (_Tok("a"), _Tok("1", "DEC_LITERAL"), True),
        (_Tok("a"), _Tok("::", "TOK_DOUBLE_COLON"), False),
        (_Tok("::", "TOK_DOUBLE_COLON"), _Tok("*", "TOK_ASTERISK"), False),
        (_Tok("*", "TOK_ASTERISK"), _Tok(";", "TOK_SEMICOLON"), False),
        (_Tok("c"), _Tok("{", "TOK_LCBRACE"), False),
        (_Tok("\\esc", "ESCAPED_ID"), _Tok("{", "TOK_LCBRACE"), True),
        (_Tok("component", "TOK_COMPONENT"), _Tok("\\esc", "ESCAPED_ID"), True),
        (_Tok("\\a", "ESCAPED_ID"), _Tok("\\b", "ESCAPED_ID"), True),
    ], ids=["keyword-ident", "ident-digit", "ident-scope", "scope-star",
            "star-semi", "ident-brace", "escaped-brace", "keyword-escaped",
            "escaped-escaped"])
    def test_must_separate(self, left, right, expected):
        assert must_separate(left, right) is expected

    @pytest.mark.parametrize("left,right,expected", [
        (_Tok("&", "TOK_SINGLE_AND"), _Tok("&", "TOK_SINGLE_AND"), True),
        (_Tok("<", "TOK_LT"), _Tok("<", "TOK_LT"), True),
        (_Tok(">", "TOK_GT"), _Tok(">", "TOK_GT"), False),
        (_Tok("-", "TOK_MINUS"), _Tok("-", "TOK_MINUS"), False),
    ], ids=["and-and", "lt-lt", "gt-gt", "minus-minus"])
    def test_operator_pairs_are_a_lexical_question_now(self, left, right,
                                                       expected):
        """``P3-4`` retired this module's claim that they could not arise.

        Through ``P3-3`` no vocabulary held an operator, and the docstring
        said the closed vocabulary was the reason rather than an oversight.
        Expressions are the vocabulary that does, so maximal munch is checked
        here directly -- ``&&`` and ``<<`` are tokens, ``>>`` and ``--`` are
        not, and the rule has to know the difference rather than assume it.

        ``T-23`` proves the rule against the lexer over every ordered pair;
        these four are here so the intent is readable at the definition.
        """
        assert must_separate(left, right) is expected

    def test_an_escaped_identifier_survives_a_zero_gap_style(self):
        """The case a token-equivalence check cannot catch on its own.

        ``ESCAPED_ID`` runs to the next whitespace, so ``\\esc{`` is one
        token: with a zero gap before ``{`` and no floor, this declaration
        becomes an identifier and the closing brace has nothing to match.
        """
        style = Style(spacing_overrides={Site.BRACE_OPEN: Spacing(0, 0)})
        out = fmt("component \\top-level_c {}\n", style)
        assert out == "component \\top-level_c {}\n", out
        assert not list(verify("component \\top-level_c {}\n", out))

    def test_an_escaped_identifier_is_delimited_on_the_left_too(self):
        """The half that is *not* lexical, and so is not caught by ``verify``.

        ``component\\esc`` does lex as two tokens. It was emitted for real,
        passed token equivalence, and was found by reading the corpus diff --
        which is the argument for a floor rather than for trusting the check.
        """
        assert fmt("component \\esc {}\n") == "component \\esc {}\n"

    @pytest.mark.parametrize("src", [
        "import a::b;\n",
        "struct s : base_s {}\n",
        "component \\esc {}\n",
        "pure component c : b {}\n",
    ])
    def test_a_zero_everywhere_style_still_emits_valid_tokens(self, src: str):
        """Every site tightened at once -- the worst a style can do."""
        style = Style(spacing_overrides={site: Spacing(0, 0) for site in Site})
        violations = list(verify(src, fmt(src, style)))
        assert not violations, violations


# ---------------------------------------------------------------------------
# What it declines
# ---------------------------------------------------------------------------


class TestItDeclinesRatherThanGuesses:
    """A token outside the vocabulary is reproduced, never guessed at.

    Each of these asserts the *author's* text comes back, which is the whole
    claim: declining costs nothing that was not already the case.
    """

    def test_a_template_parameter_list_is_left_alone(self):
        """``P3-7``'s work, and the reason the vocabulary stops where it does.

        131 of the corpus's 356 headers are this shape. They bring ``<``,
        ``>``, ``,``, ``=`` and a default-value expression, they are where
        every multi-line header lives, and they are a list that may need to
        break rather than a run of tokens that fits.
        """
        src = "struct s<int W=8> : base_s {}\n"
        assert fmt(src) == src

    @pytest.mark.parametrize("src", [
        "component c /* why */ {}\n",
        "package p {\n    import a /* x */ ::b;\n}\n",
    ], ids=["header", "import"])
    def test_a_same_line_comment_is_left_alone(self, src: str):
        """A real answer exists; it is a question about comments, not gaps."""
        assert fmt(src) == src

    @pytest.mark.parametrize("src", [
        "component c\n    // why\n{}\n",
        "component\n// why\nc {}\n",
        "component c\n/* why */\n{}\n",
        "package p {\n    import a\n    // why\n    ::b;\n}\n",
        "package p {\n    import\n    // why\n    a::b;\n}\n",
    ], ids=["before-brace", "mid-header", "block-before-brace",
            "import-before-scope", "import-after-keyword"])
    def test_an_own_line_comment_is_left_alone(self, src: str):
        """The half a same-line comment does not reach, and it deletes data.

        A comment on the same line as the token before it is that token's
        *trailing* trivia; one on its own line is the next token's *leading*
        trivia. Only the first was tested at first, so the leading check could
        be removed with every test still passing -- and removing it does not
        merely misplace the comment, it drops it, because whitespace between
        two emitted tokens is replaced by a computed gap.

        This is the sixth time on this project that a check went unexercised
        because no test supplied its subject. Mutation testing is what found
        it, which is the argument for continuing to run it.
        """
        assert fmt(src) == src

    def test_an_import_function_is_not_an_import_statement(self):
        """``import target function read;`` is a different grammar rule."""
        src = "component c {\n    import target function read;\n}\n"
        assert fmt(src) == src

    def test_the_gap_before_the_brace_is_still_normalised_when_it_declines(self):
        """Declining the token path does not undo what ``P3-2`` already did."""
        assert fmt("struct s<int W=8>{}\n") == "struct s<int W=8> {}\n"


class TestNoTokenIsEverLost:
    @pytest.mark.parametrize("src", [
        "import a::b;\n",
        "import  a :: * ;\n",
        "struct s:base_s {}\n",
        "component \\top-level_c {}\n",
        "package p {\n    import a::*;\n    struct s : b {}\n}\n",
        "struct s<int W=8> : base_s {}\n",
        "component c /* why */ {}\n",
    ])
    def test_the_tokens_survive(self, src: str):
        violations = list(verify(src, fmt(src)))
        assert not violations, violations

    @pytest.mark.parametrize("src", [
        "import  a :: b ;\n",
        "component\nc\n:\nb {}\n",
        "component \\esc {}\n",
    ])
    def test_output_is_stable(self, src: str):
        once = fmt(src)
        assert fmt(once) == once, once


class TestTheCallerCanOverrideASite:
    """``sites_at`` -- the escape hatch for a token whose type has no answer.

    Tested through ``P3-4``'s consumer rather than by hand, because the
    interesting property is that *the same token type* comes out two ways in
    one span. A synthetic call with a fabricated map would demonstrate the
    plumbing and not the point.
    """

    def test_one_token_type_two_gaps(self):
        src = "struct s {\n    int n = a--1;\n}\n"
        assert fmt(src) == "struct s {\n    int n = a - -1;\n}\n"

    def test_an_override_beats_the_vocabulary_entry(self):
        """``(`` is ``WORD`` in the expression vocabulary and is still spaced
        correctly, which can only come from the override."""
        src = "struct s {\n    int n = f( a );\n}\n"
        assert fmt(src) == "struct s {\n    int n = f(a);\n}\n"


def test_the_word_sentinel_is_not_a_site():
    """Three states -- a site, no site, not expected -- kept distinct.

    ``WORD`` and ``None`` would be interchangeable in
    :meth:`~pssfmt.style.Style.gap`, but not in the vocabulary lookup, where
    ``None`` is a plausible mapping and absence means decline.
    """
    assert WORD is not None
    assert WORD not in list(Site)

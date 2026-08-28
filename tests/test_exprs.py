"""``T-23`` -- expressions (``P3-4``).

Three things are being checked here and they are not equally interesting.

The spacing tests are ordinary. The two that matter are:

**Nothing merges.** The expression vocabulary is the first one containing
operators, which retires the argument ``pssfmt.rules.tokens`` made through
``P3-3`` -- that no vocabulary could hold two tokens the lexer would munch
together. ``a & &b`` written tight is ``a && b``, a different program that
parses. So :func:`~pssfmt.rules.tokens.must_separate` grew a real rule, and a
hand-written list of pairs would only ever be as good as the person who wrote
it. It is checked instead by running **every ordered pair** of vocabulary
lexemes through the real lexer and requiring the function to agree.

**Nothing is invented.** A formatter that works from an AST has to re-derive
``(a + b)`` from operator precedence, and is wrong exactly when its precedence
table is (``formatter.md`` section 2.2). This one reads a CST where the parens
are tokens, so the property to assert is not "the parens are correct" but "no
paren was ever computed".
"""

from __future__ import annotations

import itertools

import pytest

pytest.importorskip("pssparser")

from pssfmt.rules import BuildContext, format_source  # noqa: E402
from pssfmt.rules import exprs  # noqa: E402
from pssfmt.rules.emit import code_span  # noqa: E402
from pssfmt.rules.tokens import emit_span, must_separate  # noqa: E402
from pssfmt.style import DEFAULT_STYLE, Site, Spacing, Style  # noqa: E402
from pssfmt.trivia import TriviaMap  # noqa: E402
from pssfmt.verify import verify  # noqa: E402

pytestmark = pytest.mark.unit


def fmt(src: str, style: Style = None) -> str:
    return format_source(src, style=style) if style else format_source(src)


def field(default: str) -> str:
    """A field declaration carrying *default*, which is where a Tier 1
    expression is reachable today: constraints and activities have no rule
    yet, so their expressions are still reproduced by their enclosing block."""
    return "struct s {\n    int n = %s;\n}\n" % default


# ---------------------------------------------------------------------------
# Spacing
# ---------------------------------------------------------------------------


class TestNormalisation:
    @pytest.mark.parametrize("src,expected", [
        ("a+b", "a + b"),
        ("a  *  b", "a * b"),
        ("a<b", "a < b"),
        ("a!=b", "a != b"),
        ("a&&b", "a && b"),
        ("a|b", "a | b"),
        ("a<<2", "a << 2"),
        ("a::b.c", "a::b.c"),
        ("f( a ,b )", "f(a, b)"),
        ("arr[ i ]", "arr[i]"),
    ], ids=["additive", "multiplicative", "comparison", "equality", "logical",
            "bitwise", "shift", "path", "call", "index"])
    def test_an_expression_is_written_out(self, src: str, expected: str):
        assert fmt(field(src)) == field(expected)

    @pytest.mark.parametrize("src,expected", [
        ("-1", "-1"),
        ("- 1", "-1"),
        ("!flag", "!flag"),
        ("~mask", "~mask"),
        ("a - -1", "a - -1"),
        ("a--1", "a - -1"),
    ], ids=["negative", "loose-negative", "not", "invert", "binary-then-unary",
            "tight-binary-then-unary"])
    def test_a_unary_operator_is_not_its_binary_twin(self, src, expected):
        """``-`` is unary 103 times in the corpus and additive 49 times.

        A vocabulary keyed by token type has one slot for it, which is why
        this module's sites come from the tree. ``a--1`` is the case that
        shows both readings in one line: the first ``-`` is additive and
        spaced, the second is unary and tight, and they are the same token
        type three characters apart.
        """
        assert fmt(field(src)) == field(expected)

    @pytest.mark.parametrize("src,expected", [
        ("(a+b)*2", "(a + b) * 2"),
        ("( a + b )", "(a + b)"),
        ("(bit[32])x", "(bit[32])x"),
        ("(bit)cfg.en", "(bit)cfg.en"),
        ("f(a)+g(b)", "f(a) + g(b)"),
    ], ids=["group", "loose-group", "cast", "cast-plain", "calls"])
    def test_the_three_parens_are_three_constructs(self, src, expected):
        """``(`` is a call 40 times, a grouping 12 and a cast 13 -- a
        partition of every paren in the corpus, not a corner case."""
        assert fmt(field(src)) == field(expected)


class TestAuthoredParensSurvive:
    """``formatter.md`` section 2.2, item 6, asserted rather than assumed.

    An AST-based formatter loses ``(a + b)`` -- the tree records only that
    the addition is the multiplication's left operand -- and has to put the
    parens back by consulting a precedence table. That is a computation, and
    a computation can be wrong. A CST has ``paren_expr``, so there is no
    table here and nothing to get wrong.
    """

    @pytest.mark.parametrize("src", [
        "(a + b) * c",
        "a * (b + c)",
        "((a))",
        "(a) + (b)",
        "(a + b) * (c + d)",
    ])
    def test_a_written_paren_is_copied(self, src: str):
        assert fmt(field(src)) == field(src)

    @pytest.mark.parametrize("src", [
        "a + b * c",
        "a * b + c",
        "a && b || c",
        "a + b + c",
    ])
    def test_a_paren_that_was_not_written_is_never_added(self, src: str):
        """The failure this guards against is *helpfulness*: emitting
        ``a + (b * c)`` because it is clearer. It is also a different file
        from the one the author committed, for no reason they asked for."""
        assert fmt(field(src)) == field(src)
        assert fmt(field(src)).count("(") == 0

    def test_removing_a_redundant_paren_is_not_this_formatter_s_job(self):
        """``(a) + b`` is redundant and stays. Deciding it is redundant needs
        the same precedence table, used in the other direction."""
        assert fmt(field("(a) + b")) == field("(a) + b")


class TestTheGapsComeFromTheStyle:
    def test_the_additive_gap_follows_its_site(self):
        style = Style(spacing_overrides={Site.ADDITIVE: Spacing(0, 0)})
        assert fmt(field("a + b"), style) == field("a+b")

    def test_the_grouping_paren_is_not_the_call_paren(self):
        """The two sites carry the same number today and are still two sites.

        A style that spaces a call's arguments has said nothing about whether
        ``(a + b)`` should become ``( a + b )``, and one site would answer
        both questions with one setting.
        """
        style = Style(spacing_overrides={
            Site.GROUP_PAREN_OPEN: Spacing(0, 1),
            Site.GROUP_PAREN_CLOSE: Spacing(1, 0),
        })
        assert fmt(field("(a + b) * f(c)"), style) == field("( a + b ) * f(c)")

    def test_the_unary_gap_follows_its_site(self):
        style = Style(spacing_overrides={Site.UNARY: Spacing(0, 1)})
        assert fmt(field("-a + b"), style) == field("- a + b")


# ---------------------------------------------------------------------------
# The property the operators put at risk
# ---------------------------------------------------------------------------


#: One text per vocabulary token type, each of which must lex as exactly that
#: one token -- checked below, so a wrong sample cannot quietly weaken the
#: sweep by testing a two-token string instead.
LEXEMES = {
    "ID": "a", "ESCAPED_ID": "\\x",
    "DEC_LITERAL": "1", "HEX_LITERAL": "0x1", "OCT_LITERAL": "07",
    "BIN_LITERAL": "0b1",
    "BASED_DEC_LITERAL": "'d1", "BASED_HEX_LITERAL": "'hF",
    "BASED_OCT_LITERAL": "'o7", "BASED_BIN_LITERAL": "'b1",
    "FLOAT_DEC_LITERAL": "1.5", "FLOAT_SCI_LITERAL": "1e5",
    "DOUBLE_QUOTED_STRING": '"s"',
    "TOK_TRUE": "true", "TOK_FALSE": "false", "TOK_NULL": "null",
    "TOK_BIT": "bit", "TOK_INT": "int", "TOK_BOOL": "bool",
    "TOK_STRING": "string", "TOK_FLOAT32": "float32",
    "TOK_FLOAT64": "float64", "TOK_CHANDLE": "chandle",
    "TOK_LPAREN": "(", "TOK_RPAREN": ")",
    "TOK_LSBRACE": "[", "TOK_RSBRACE": "]",
    "TOK_PLUS": "+", "TOK_MINUS": "-", "TOK_ASTERISK": "*",
    "TOK_DIV": "/", "TOK_MOD": "%",
    "TOK_LT": "<", "TOK_LTE": "<=", "TOK_GT": ">", "TOK_GTE": ">=",
    "TOK_DOUBLE_EQ": "==", "TOK_NE": "!=",
    "TOK_DOUBLE_AND": "&&", "TOK_DOUBLE_OR": "||",
    "TOK_SINGLE_AND": "&", "TOK_SINGLE_OR": "|", "TOK_CARET": "^",
    "TOK_NOT": "!", "TOK_NEG": "~", "TOK_DOUBLE_LT": "<<",
    "TOK_DOUBLE_COLON": "::", "TOK_DOT": ".", "TOK_COMMA": ",",
    "TOK_IN": "in", "TOK_ELIPSIS": "..",
}


class _Tok:
    """The two attributes ``must_separate`` reads."""

    def __init__(self, type_name: str, text: str) -> None:
        self.type_name, self.text = type_name, text


def lex(src: str):
    from pssparser import cst as _cst

    return [(t.type_name, t.text) for t in _cst.parse(src).tokens
            if not t.is_trivia]


class TestTokensNeverMerge:
    """The safety property, checked against the lexer rather than a list.

    ``docs/status.rst`` states it as: a style may set any gap to zero, and
    that must never change what a file *means*. Every other test in this
    suite would pass with the check removed, because the default style spaces
    these operators anyway -- so the sweep runs at zero.
    """

    def test_every_vocabulary_entry_has_a_single_token_sample(self):
        """Otherwise an unsampled type is silently outside the sweep."""
        assert set(exprs.EXPRESSION_VOCABULARY) == set(LEXEMES)
        wrong = {name: text for name, text in LEXEMES.items()
                 if lex(text) != [(name, text)]}
        assert not wrong, wrong

    def test_no_pair_the_lexer_would_join_is_left_unseparated(self):
        """Every ordered pair, against the real lexer. 2304 of them.

        ``must_separate`` is allowed to be *conservative* -- saying "separate"
        where the lexer would have coped -- because a floor that is too high
        emits a space nobody needed. It is never allowed to be permissive:
        that is a silently different program.
        """
        missed = []
        for left, right in itertools.product(sorted(LEXEMES), repeat=2):
            lt, rt = LEXEMES[left], LEXEMES[right]
            joins = lex(lt + rt) != [(left, lt), (right, rt)]
            if joins and not must_separate(_Tok(left, lt), _Tok(right, rt)):
                missed.append((lt, rt, lex(lt + rt)))
        assert not missed, missed

    @pytest.mark.parametrize("left,right,joined", [
        ("&", "&", "&&"),
        ("|", "|", "||"),
        ("<", "<", "<<"),
        ("<", "<=", "<<="),
        (">", ">=", ">>="),
        ("-", ">", "->"),
        ("!", "=", "!="),
    ], ids=["and", "or", "shift", "shift-assign", "rshift-assign",
            "implies", "not-equal"])
    def test_the_pairs_that_forced_the_rule(self, left, right, joined):
        """Named so the regression is legible without reading the sweep.

        Most are a *unary operator following a binary one* -- ``a & &b`` --
        which is the only way PSS puts two of these characters next to each
        other, and each becomes a different, valid operator when joined.
        """
        assert must_separate(_Tok("", left), _Tok("", right))
        assert lex(joined)[0][1] == joined

    @pytest.mark.parametrize("left,right", [
        (">", ">"),
        ("-", "-"),
        ("+", "+"),
    ], ids=["gt-gt", "minus-minus", "plus-plus"])
    def test_the_pairs_that_look_like_they_would_and_do_not(self, left, right):
        """PSS has no ``>>``, ``--`` or ``++`` token.

        ``>>`` is the interesting one: the *shift operator* is spelled as two
        ``TOK_GT``, so writing them together is how you get a shift rather
        than how you lose one. Separating here would be harmless but wrong
        about the language, and the sweep would not catch it -- being
        conservative is always allowed.
        """
        assert not must_separate(_Tok("", left), _Tok("", right))

    def test_a_zero_everywhere_style_cannot_change_the_program(self):
        style = Style(spacing_overrides={site: Spacing(0, 0) for site in Site})
        for src in ["a & &b", "a | |b", "a - -1", "a < <b", "(a + b) * -c",
                    "f(a, -b) + arr[i]"]:
            source = field(src)
            violations = list(verify(source, fmt(source, style)))
            assert not violations, (src, violations)


# ---------------------------------------------------------------------------
# The boundary
# ---------------------------------------------------------------------------


class TestItDeclinesRatherThanGuesses:
    @pytest.mark.parametrize("src", [
        "a**2",
        "a ** 2",
    ], ids=["tight", "spaced"])
    def test_exponent_is_left_exactly_as_written(self, src: str):
        """65 instances, one voice, unanimously tight -- against a general
        binary-operator rule that says spaced. One file cannot decide a site,
        and formatting it either way overrules somebody with nothing."""
        assert fmt(field(src)) == field(src)

    def test_a_right_shift_is_left_alone(self):
        """``>>`` is ``TOK_GT TOK_GT``: two tokens that must touch, inside an
        operator that must not. ``max(left.after, right.before)`` cannot say
        that, so emitting it would produce ``a > > b`` -- valid, token
        equivalent, and not what anyone wrote."""
        assert fmt(field("a >> b")) == field("a >> b")
        assert "> >" not in fmt(field("a >> b"))

    def test_a_left_shift_is_not_affected_by_that(self):
        """``<<`` is one token, so the reason does not apply to it."""
        assert fmt(field("a<<b")) == field("a << b")

    @pytest.mark.parametrize("src", [
        "a in [1..4]",
        "{1, 2, 3}",
        "a ? b : c",
    ], ids=["in-set", "aggregate", "ternary"])
    def test_the_constructs_owned_by_a_later_item(self, src: str):
        assert fmt(field(src)) == field(src)

    def test_an_unclassified_operator_declines_rather_than_defaulting(self):
        """The completeness check, exercised directly.

        A token in ``TREE_DECIDED`` that the walk did not reach must make the
        whole span decline. If it merely fell back to the vocabulary the
        result would be *wrong* rather than absent, because the vocabulary
        entry for an ambiguous token is a placeholder -- and nothing about
        the output would say so.
        """
        src = "struct s {\n    int n = a + b;\n}\n"
        ctx, node = _expression_of(src)
        assert exprs.sites_for(ctx, node) is not None

        try:
            exprs._OPERATOR_SITES.pop("add_sub_op")
            assert exprs.sites_for(ctx, node) is None
        finally:
            exprs._OPERATOR_SITES["add_sub_op"] = Site.ADDITIVE


def _expression_of(src: str):
    from pssparser import cst as _cst

    tree = _cst.parse(src)
    ctx = BuildContext(style=DEFAULT_STYLE, trivia=TriviaMap(tree.tokens))
    stack = [tree.root]
    while stack:
        node = stack.pop()
        if not node.is_rule:
            continue
        if node.rule_name == "constant_expression":
            return ctx, node
        stack.extend(reversed(node.children))
    raise AssertionError("no expression in %r" % src)


class TestSitesComeFromTheTree:
    def test_the_same_token_gets_two_sites_in_one_expression(self):
        """``a - -1``: two ``TOK_MINUS``, two answers, from one walk."""
        ctx, node = _expression_of("struct s {\n    int n = a - -1;\n}\n")
        sites = exprs.sites_for(ctx, node)
        assert sorted(sites.values(), key=str) == sorted(
            [Site.ADDITIVE, Site.UNARY], key=str)

    def test_every_paren_is_classified(self):
        ctx, node = _expression_of(
            "struct s {\n    int n = f((bit[8])(a + b));\n}\n")
        sites = exprs.sites_for(ctx, node)
        assert sites is not None
        found = {site for site in sites.values()}
        assert Site.CALL_PAREN_OPEN in found
        assert Site.GROUP_PAREN_OPEN in found

    def test_a_declined_construct_returns_none(self):
        ctx, node = _expression_of("struct s {\n    int n = a**2;\n}\n")
        assert exprs.sites_for(ctx, node) is None


# ---------------------------------------------------------------------------
# The corpus, and the whole point of the module
# ---------------------------------------------------------------------------


class TestNoTokenIsEverLost:
    @pytest.mark.parametrize("src", [
        "a + b * c",
        "(a + b) * c",
        "(bit[32])x.y",
        "f(a, b) + arr[i]",
        "-1",
        "a != b && c < d",
        "a**2",
        "a >> b",
    ])
    def test_the_tokens_survive(self, src: str):
        source = field(src)
        violations = list(verify(source, fmt(source)))
        assert not violations, violations

    @pytest.mark.parametrize("src", ["a + b * c", "(a + b) * c", "a**2"])
    def test_output_is_stable(self, src: str):
        once = fmt(field(src))
        assert fmt(once) == once, once


class TestWrappingIsNotUndone:
    def test_a_declaration_that_no_longer_fits_keeps_its_break(self):
        """The regression ``P3-4`` introduced and had to answer.

        ``P3-3`` could join any wrapped field back onto one line, because a
        declaration with no expression in it is short. An initializer is an
        expression and an expression is any length, so joining started
        producing lines past ``print_width`` -- which ``docs/style.rst``
        measured as a wall authors wrap *to*, not a preference. One corpus
        file said so, by being the only one that changed.
        """
        src = ("package p {\n"
               "    static const bit[64] DMA_REG_SPAN =\n"
               "        DMA_CH_BASE + DMA_NUM_CH * DMA_CH_STRIDE;\n"
               "}\n")
        assert fmt(src) == src

    def test_a_declaration_that_does_fit_is_still_joined(self):
        """The break is offered, not taken: ``P3-3``'s behaviour is intact
        for everything that was never too long."""
        src = "struct s {\n    static const int N\n        = 8;\n}\n"
        assert fmt(src) == "struct s {\n    static const int N = 8;\n}\n"

    def test_the_break_respects_a_zero_assignment_gap(self):
        """Flat mode renders the break as the *computed* gap, so a style that
        made ``=`` tight does not get a space back through the layout."""
        style = Style(spacing_overrides={Site.ASSIGN: Spacing(0, 0)})
        assert fmt(field("8"), style) == "struct s {\n    int n=8;\n}\n"


def test_the_corpus_expressions_format(request):
    """The coverage number, kept honest by being computed rather than quoted.

    Most corpus expressions live in constraints and activities, which have no
    rule yet -- so this exercises the module directly rather than through
    ``format_source``, which would only reach the handful in field defaults.
    """
    corpus = request.config.rootpath / "packages" / "pss-corpus"
    if not corpus.is_dir():
        pytest.skip("corpus not present")
    from pssparser import cst as _cst

    formatted = declined = 0
    for path in sorted(corpus.rglob("*.pss")):
        try:
            tree = _cst.parse(path.read_text(errors="replace"))
        except Exception:
            continue
        ctx = BuildContext(style=DEFAULT_STYLE, trivia=TriviaMap(tree.tokens))
        stack = [(tree.root, False)]
        while stack:
            node, inside = stack.pop()
            if not node.is_rule:
                continue
            is_expr = node.rule_name in ("expression", "constant_expression")
            if is_expr and not inside:
                sites = exprs.sites_for(ctx, node)
                span = code_span(ctx.trivia, node)
                built = None
                if sites is not None and span is not None:
                    built = emit_span(ctx, span[0], span[1],
                                      exprs.EXPRESSION_VOCABULARY,
                                      sites_at=sites)
                if built is None:
                    declined += 1
                else:
                    formatted += 1
            stack.extend((c, inside or is_expr)
                         for c in reversed(node.children))

    total = formatted + declined
    assert total > 1000, total
    assert formatted / total > 0.9, (formatted, declined)

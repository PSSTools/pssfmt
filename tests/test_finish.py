"""``T-31`` -- the emit boundary, and the three things it was not doing.

``pssfmt.finish`` exists because the tail of a formatted file is *copied*
rather than composed: trivia after the last code token belongs to no CST node,
so no builder emits it and ``build_tree`` appends it verbatim. Every
file-level property the formatter claimed was therefore true of every line
except the last one.

The three defects are the first three tests below, one apiece, because they
failed for three unrelated reasons and a single "the tail is right now" test
would go green if two of them came back. Each is written as the observable
symptom rather than as a call to ``finish``, so it still fails if the fix
moves somewhere else.

Why the corpus is silent here
-----------------------------
Of 92 corpus files: zero use CRLF, zero end in trailing whitespace, zero end
in a blank line, and the single file without a final newline is a deliberately
truncated pathological case. So this is the shape ``P3-4`` and ``P3-5a`` are
also in -- a question the corpus cannot vote on -- with one difference that
made it actionable rather than deferrable: **it needs no vote.** A file with
two different line terminators in it is wrong under every style, so unlike
``**`` spacing there was nothing here to wait for evidence about.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.finish import detect_line_ending, finish  # noqa: E402
from pssfmt.rules import format_source  # noqa: E402
from pssfmt.style import DEFAULT_STYLE, LineEnding, Style  # noqa: E402
from pssfmt.verify import format_safely, verify  # noqa: E402

CRLF = "\r\n"
LF = "\n"


def lines_end_consistently(text):
    """True when every terminator in *text* is the same one."""
    crlf = text.count(CRLF)
    return crlf == 0 or crlf == text.count(LF)


# ---------------------------------------------------------------------------
# The three defects, as symptoms
# ---------------------------------------------------------------------------


class TestWhatTheTailWasDoing:

    def test_a_crlf_file_does_not_come_back_with_two_kinds_of_line_ending(self):
        """The one that could reach a user's file today.

        The engine emits ``\\n`` for every line it composes and the copied tail
        kept its ``\\r\\n``, so a CRLF file came out mixed -- LF everywhere and
        CRLF on the last line. The verifier cannot see it, because line
        endings are trivia and token equivalence holds perfectly.
        """
        out = format_source("component a {" + CRLF + "    int x;" + CRLF
                            + "}" + CRLF)
        assert lines_end_consistently(out), repr(out)
        assert out.endswith(CRLF)

    def test_the_last_line_has_no_trailing_whitespace_either(self):
        """The layout engine strips it from every line it renders, and the
        tail was not rendered. ``T-8`` asserts no-trailing-whitespace as a
        property of the engine over generated IR, and that assertion was true
        of the engine and false of the output.
        """
        assert format_source("component a {\n}   \n") == "component a {}\n"

    def test_trailing_blank_lines_do_not_survive(self):
        """Blank-line clamping happens in the trivia map, which the tail
        bypasses -- so six blank lines at EOF outlived a ``max_blank_lines``
        of 1 while three in the middle of the file collapsed to one.
        """
        assert format_source("component a {\n}\n\n\n\n\n\n") == "component a {}\n"


# ---------------------------------------------------------------------------
# Line endings
# ---------------------------------------------------------------------------


class TestLineEndings:

    @pytest.mark.parametrize("src,expected", [
        ("a\r\nb\r\n", CRLF),
        ("a\nb\n", LF),
        ("", LF),
        ("no terminator at all", LF),
        # Ties go to LF, and a tie is reachable: one line converted by an
        # editor is enough.
        ("a\r\nb\n", LF),
        ("a\r\nb\r\nc\n", CRLF),
    ])
    def test_detection_is_by_majority(self, src, expected):
        assert detect_line_ending(src) == expected

    def test_detection_agrees_whether_given_text_or_tokens(self):
        """Both spellings are accepted because different callers hold
        different things, and they had better be one measurement."""
        from pssparser import tokens as _tokens

        for src in ("component a {\r\n}\r\n", "component a {\n}\n",
                    "component a {}"):
            assert detect_line_ending(src) == \
                detect_line_ending(_tokens.tokenize(src))

    @pytest.mark.parametrize("ending", [LineEnding.LF, LineEnding.CRLF])
    @pytest.mark.parametrize("src", ["component a {\n}\n",
                                     "component a {\r\n}\r\n"])
    def test_an_explicit_setting_overrides_what_the_file_had(self, ending, src):
        want = CRLF if ending is LineEnding.CRLF else LF
        out = format_source(src, style=DEFAULT_STYLE.evolve(line_ending=ending))
        assert out.endswith(want)
        assert lines_end_consistently(out)
        if want == LF:
            assert CRLF not in out

    @pytest.mark.parametrize("ending", [LF, CRLF])
    def test_applying_an_ending_normalises_first_whatever_it_is_given(self, ending):
        """:func:`~pssfmt.finish.apply_line_ending` documents that its input
        must already be LF, and normalises anyway. Tested at the unit level
        because the pipeline upholds that precondition, so nothing reaches it
        the other way -- and a defensive guard whose only justification is a
        docstring is one somebody deletes as dead code.
        """
        from pssfmt.finish import apply_line_ending

        for given in ("a\r\nb\r\n", "a\nb\n", "a\r\nb\n"):
            out = apply_line_ending(given, ending)
            assert "\r\r" not in out
            assert out == "a%sb%s" % (ending, ending)

    def test_converting_to_crlf_never_produces_a_lone_cr_pair(self):
        """``\\n`` -> ``\\r\\n`` on text that is already CRLF gives ``\\r\\r\\n``
        unless it is normalised first. The tail arrives already CRLF whenever
        the input was, so this is the ordinary case rather than a corner."""
        out = finish("a\r\nb\n", DEFAULT_STYLE.evolve(line_ending=LineEnding.CRLF))
        assert "\r\r" not in out
        assert out == "a\r\nb\r\n"

    #: Constructs whose *token text* spans lines. These are why the formatter
    #: normalises its input rather than substituting over its output: a naive
    #: substitution rewrites the text of one of these tokens, and the verifier
    #: -- correctly, on the evidence available to it -- calls that corruption.
    SPANS_LINES = {
        "block comment": "component a {%(n)s/* one%(n)s   two */%(n)s"
                         "    int x;%(n)s}%(n)s",
        "exec template": 'component a {%(n)s    exec body C = """%(n)s'
                         '  raw%(n)s""";%(n)s}%(n)s',
    }

    @pytest.mark.parametrize("ending", [LineEnding.LF, LineEnding.CRLF])
    @pytest.mark.parametrize("was", [LF, CRLF], ids=["from lf", "from crlf"])
    @pytest.mark.parametrize("src", SPANS_LINES.values(), ids=list(SPANS_LINES))
    def test_a_token_that_spans_lines_converts_without_tripping_the_fail_safe(
            self, src, was, ending):
        """The bug this module's design is shaped around.

        A multi-line ``/* */`` comment is **one token**, and so is a
        triple-quoted ``exec`` template. Converting a file's line endings by
        substituting over the finished text therefore edits token text, and
        ``line_ending: lf`` used to fail on any CRLF file containing a block
        comment -- output rejected, file left alone, diagnostic blaming
        ``pssfmt``. Normalising the *input* instead makes it impossible: every
        token the parser sees is already LF.

        Run through :func:`~pssfmt.verify.format_safely` and not
        :func:`~pssfmt.rules.format_source`, because the symptom was never
        wrong output. It was the fail-safe declining correct output.
        """
        want = CRLF if ending is LineEnding.CRLF else LF
        style = DEFAULT_STYLE.evolve(line_ending=ending)
        result = format_safely(src % {"n": was},
                               formatter=lambda s: format_source(s, style=style))
        assert result.ok, result.diagnostic()
        assert lines_end_consistently(result.text)
        assert result.text.endswith(want)

    @pytest.mark.parametrize("ending", [LineEnding.AUTO, LineEnding.LF,
                                        LineEnding.CRLF])
    def test_a_crlf_comment_run_does_not_crash_the_rule_layer(self, ending):
        """Why the *input* is normalised, which is not what I first wrote down.

        The obvious story -- "normalising the input is what stops the
        line-ending conversion from rewriting token text" -- is false, and a
        mutation run said so: removing the input normalisation changed no
        result, because :func:`~pssfmt.finish.apply_line_ending` normalises the
        finished text anyway. What actually made forced conversion work is the
        narrow exemption in the verifier, tested directly below.

        The real reason is this test. A run of ``//`` comments before a member
        is re-indented by splitting the run on ``\\n``, which on CRLF input
        leaves a ``\\r`` on the end of every line -- and ``Text`` rejects it,
        so the rule layer *raises*. The fail-safe catches it, so the symptom
        is a declined file rather than a damaged one, but every CRLF file with
        two adjacent comments in it was reaching that path.

        Recorded at this length because the first rationale was wrong in the
        direction that is hardest to catch: it was plausible, it sat above
        code that worked, and only a mutant disagreed with it.
        """
        src = ("component a {%(n)s    // one%(n)s    // two%(n)s"
               "    int x;%(n)s}%(n)s") % {"n": CRLF}
        style = DEFAULT_STYLE.evolve(line_ending=ending)
        result = format_safely(src,
                               formatter=lambda s: format_source(s, style=style))
        assert result.ok, result.diagnostic()
        assert result.error is None
        assert lines_end_consistently(result.text)

    def test_the_exemption_the_verifier_grants_is_only_line_endings(self):
        """The other half of that trade, stated as a test.

        Comparing token text with line endings normalised is a real weakening
        of the strongest safety property in the project, so the bound on it is
        worth pinning rather than asserting in a docstring: a comment whose
        content changed still fails, and so does one that disappeared.
        """
        assert not verify("/* a\r\nb */\n", "/* a\nb */\n")
        assert verify("/* a\nb */\n", "/* a\nc */\n")
        assert verify("/* a */\n", "\n")

    def test_a_lone_cr_is_not_treated_as_a_line_ending(self):
        """A bare ``\\r`` inside a file is far more likely to be a stray byte
        in a literal than a Mac OS 9 terminator, and rewriting it would change
        a *token* rather than whitespace -- which the verifier would then
        reject, turning a cosmetic guess into a declined file."""
        assert detect_line_ending("a\rb\rc") == LF


# ---------------------------------------------------------------------------
# The final newline
# ---------------------------------------------------------------------------


class TestTheFinalNewline:

    def test_it_is_added_when_missing(self):
        assert format_source("component a {\n}") == "component a {}\n"

    def test_an_empty_file_stays_empty(self):
        """The promise is that a file *ends* with a newline, and a file with
        no content does not begin. Writing one here would be the formatter
        inventing a byte, which is a different thing from formatting one."""
        assert finish("", DEFAULT_STYLE) == ""
        assert format_source("") == ""

    def test_a_whitespace_only_file_becomes_empty(self):
        assert format_source("\n\n\n") == ""
        assert finish("   \n  \t\n", DEFAULT_STYLE) == ""

    def test_false_removes_it_rather_than_preserving_it(self):
        """EditorConfig's semantics for the key this option is named after,
        and the surprising half of them: ``false`` means "ensure it does not
        end with a newline", not "leave whatever was there alone". Preserving
        the author's choice is a third state and a bool cannot hold three.

        Pinned as a test rather than left to the docstring because it is the
        one behaviour here that a reader would guess wrong.
        """
        style = DEFAULT_STYLE.evolve(insert_final_newline=False)
        assert format_source("component a {\n}\n", style=style) == "component a {}"
        assert format_source("component a {\n}", style=style) == "component a {}"


# ---------------------------------------------------------------------------
# The properties that make it safe to run on every file
# ---------------------------------------------------------------------------


STYLES = [
    ("default", DEFAULT_STYLE),
    ("crlf", DEFAULT_STYLE.evolve(line_ending=LineEnding.CRLF)),
    ("lf", DEFAULT_STYLE.evolve(line_ending=LineEnding.LF)),
    ("no final newline", DEFAULT_STYLE.evolve(insert_final_newline=False)),
    ("crlf, no final newline",
     DEFAULT_STYLE.evolve(line_ending=LineEnding.CRLF,
                          insert_final_newline=False)),
]

SOURCES = {
    "lf": "component a {\n    int x;\n}\n",
    "crlf": "component a {\r\n    int x;\r\n}\r\n",
    "mixed": "component a {\r\n    int x;\n}\r\n",
    "no final newline": "component a {\n    int x;\n}",
    "trailing blanks": "component a {\n}\n\n\n\n",
    "trailing whitespace": "component a {\n}  \t \n",
    "comment at eof": "component a {\n}\n// tail\n",
    "empty": "",
    "whitespace only": "\n  \n",
    "broken": "component {{{ \n",
}


@pytest.mark.parametrize("style", [s for _, s in STYLES],
                         ids=[n for n, _ in STYLES])
@pytest.mark.parametrize("src", SOURCES.values(), ids=list(SOURCES))
def test_it_is_idempotent(src, style):
    """Not optional, and not merely tidy: the fail-safe formats twice and
    compares, so a non-idempotent step here would *reject every file it
    touched* rather than corrupt one. Both transformations are projections,
    which is the argument -- re-normalising a canonical form is a no-op."""
    once = format_source(src, style=style)
    assert format_source(once, style=style) == once


@pytest.mark.parametrize("style", [s for _, s in STYLES],
                         ids=[n for n, _ in STYLES])
@pytest.mark.parametrize("src", SOURCES.values(), ids=list(SOURCES))
def test_it_only_ever_moves_whitespace(src, style):
    """The verifier's own oracle, pointed at the one pass that runs after it
    would normally have looked. ``finish`` rewrites ``\\r\\n`` sequences, and
    a ``\\r\\n`` inside a string literal is part of a *token*; this is what
    says the rewrite never reaches one."""
    assert not verify(src, format_source(src, style=style))


@pytest.mark.parametrize("style", [s for _, s in STYLES],
                         ids=[n for n, _ in STYLES])
@pytest.mark.parametrize("src", SOURCES.values(), ids=list(SOURCES))
def test_the_result_has_one_kind_of_line_ending(src, style):
    assert lines_end_consistently(format_source(src, style=style))


def test_finish_runs_even_with_no_rule_registered():
    """The emit boundary is not behind the rule registry, and that is a
    decision rather than an accident: the null-rule-set case is the one the
    whole architecture rests on, and a file that no builder touched still
    needs one consistent line terminator."""
    from pssfmt.rules import RuleRegistry

    out = format_source("component a {\r\n}\r\n", registry=RuleRegistry())
    assert lines_end_consistently(out) and out.endswith(CRLF)


def test_a_cramped_style_still_cannot_reach_past_the_boundary():
    """Guards the containment claim from the other side. ``finish`` reads
    exactly two options; if it ever grew a third by accident, a style varying
    only the *other* eight would start moving bytes here."""
    a = finish("component a {}\n", Style(print_width=20, indent_width=8,
                                         use_tabs=True, max_blank_lines=0))
    b = finish("component a {}\n", DEFAULT_STYLE)
    assert a == b

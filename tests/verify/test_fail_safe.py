"""``P1-3`` -- the verifier and the fail-safe.

Every test here formats with a *deliberately broken* formatter and asserts that
the user's file survives. Section 3.4: *"a formatter that is occasionally a
no-op is survivable; a formatter that occasionally corrupts is not."* These are
the corruptions, one per plausible bug.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.verify import (  # noqa: E402
    check_parse_errors,
    check_token_equivalence,
    format_safely,
    verify,
)

pytestmark = pytest.mark.unit


SRC = "component c {\n    int x; // note\n    /* block */\n}\n"


def kinds(result):
    return sorted({v.kind for v in result.violations})


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------

def test_the_null_formatter_passes_every_check():
    result = format_safely(SRC)
    assert result.ok
    assert result.violations == ()
    assert result.text == SRC
    assert not result.changed


def test_a_whitespace_only_change_is_allowed():
    # This is the whole point: reformatting is legal, changing content is not.
    result = format_safely(SRC, lambda s: s.replace("    ", "  "))
    assert result.ok, result.diagnostic()
    assert result.changed
    assert result.text == SRC.replace("    ", "  ")


def test_stripping_trailing_whitespace_inside_a_comment_is_allowed():
    src = "int x; // note   \n"
    result = format_safely(src, lambda s: s.replace("note   ", "note"))
    assert result.ok, result.diagnostic()


def test_bytes_input_is_decoded():
    assert format_safely(SRC.encode("utf-8")).text == SRC


# ---------------------------------------------------------------------------
# Check 1 -- token equivalence
# ---------------------------------------------------------------------------

def test_a_dropped_code_token_is_caught():
    result = format_safely(SRC, lambda s: s.replace("int x; ", ""))
    assert not result.ok
    assert "tokens" in kinds(result)
    assert result.text == SRC


def test_an_invented_code_token_is_caught():
    result = format_safely(SRC, lambda s: s.replace("int x;", "int x, y;"))
    assert not result.ok
    assert "tokens" in kinds(result)


def test_renaming_an_identifier_is_caught():
    result = format_safely(SRC, lambda s: s.replace("int x", "int y"))
    assert not result.ok
    assert "tokens" in kinds(result)


def test_a_dropped_comment_is_caught():
    result = format_safely(SRC, lambda s: s.replace("/* block */", ""))
    assert not result.ok
    assert "comments" in kinds(result)
    assert result.text == SRC


def test_rewriting_comment_content_is_caught():
    result = format_safely(SRC, lambda s: s.replace("// note", "// NOTE"))
    assert not result.ok
    assert "comments" in kinds(result)


def test_a_dropped_error_token_is_caught():
    # Section 3.5 asks only for the default channel. Error tokens stand for
    # bytes of the user's file that no lexer rule matched, and silently
    # deleting them is exactly the failure mode this whole layer exists to
    # prevent, so they are compared too.
    src = "component c { } $ component d { }\n"
    result = format_safely(src, lambda s: s.replace(" $", ""))
    assert not result.ok
    assert "tokens" in kinds(result)


def test_the_diagnostic_names_the_first_divergence():
    result = format_safely(SRC, lambda s: s.replace("int x", "int y"))
    text = result.diagnostic("c.pss")
    assert "c.pss" in text
    assert "'x'" in text and "'y'" in text
    assert "has not been modified" in text


# ---------------------------------------------------------------------------
# Check 2 -- idempotence
# ---------------------------------------------------------------------------

def test_a_formatter_that_never_settles_is_caught():
    result = format_safely(SRC, lambda s: s + "\n")
    assert not result.ok
    assert kinds(result) == ["idempotence"]
    assert result.text == SRC


def test_idempotence_can_be_switched_off():
    # Wanted by the corpus sweep, which formats thousands of files and pays
    # for a second pass on every one of them.
    result = format_safely(SRC, lambda s: s + "\n", check_idempotence=False)
    assert result.ok


def test_the_rejected_output_is_kept_for_debugging():
    result = format_safely(SRC, lambda s: s + "\n")
    assert result.rejected == SRC + "\n"


# ---------------------------------------------------------------------------
# Check 3 -- parse errors, and R10
# ---------------------------------------------------------------------------

def test_uncommenting_a_block_by_splitting_its_opener_is_caught():
    # PLAN.md R10, the hazard the lexer cannot see. `/*` becoming `/ *` turns a
    # comment into code. The lexer reports zero errors either way, which is why
    # check 3 counts the *parser's* syntax errors.
    src = "component c { /* int x; */ }\n"
    result = format_safely(src, lambda s: s.replace("/*", "/ *"))
    assert not result.ok
    assert "parse-errors" in kinds(result)
    assert result.text == src


def test_the_lexer_reports_that_hazard_as_clean():
    # The sentinel for R10 itself: if this ever starts failing, the grammar
    # changed and check 3 could in principle be relaxed. Until then it may not.
    from pssparser import tokens
    assert tokens.tokenize("/* a").num_errors == 0


def test_a_file_that_already_does_not_parse_may_still_be_formatted():
    # "At least as well as the input", not "cleanly". Refusing to touch broken
    # files is a separate policy decision and not this layer's to make.
    src = "component c { this is not pss }\n"
    result = format_safely(src, lambda s: s.replace("  ", " "))
    assert result.ok, result.diagnostic()


def test_making_a_parsing_file_stop_parsing_is_caught():
    result = format_safely(SRC, lambda s: s.replace("{", "{{"))
    assert not result.ok
    assert "parse-errors" in kinds(result)


# ---------------------------------------------------------------------------
# The formatter itself failing
# ---------------------------------------------------------------------------

def test_a_crash_still_returns_the_input():
    def boom(_src):
        raise RuntimeError("rule for `activity` is not written yet")

    result = format_safely(SRC, boom)
    assert not result.ok
    assert result.text == SRC
    assert isinstance(result.error, RuntimeError)
    assert "not written yet" in result.diagnostic()


def test_a_crash_on_the_second_pass_still_returns_the_input():
    calls = []

    def once(src):
        calls.append(src)
        if len(calls) > 1:
            raise RuntimeError("second pass")
        return src

    result = format_safely(SRC, once)
    assert not result.ok
    assert result.text == SRC


def test_a_formatter_that_returns_the_wrong_type_is_caught():
    result = format_safely(SRC, lambda s: s.encode("utf-8"))
    assert not result.ok
    assert result.text == SRC


def test_invalid_utf8_is_the_one_thing_that_propagates():
    # There is no text to hand back. Guessing an encoding and writing the guess
    # would be the corruption the fail-safe exists to prevent.
    with pytest.raises(UnicodeDecodeError):
        format_safely(b"// caf\xe9\n")


def test_a_non_source_argument_is_a_type_error():
    with pytest.raises(TypeError):
        format_safely(42)


# ---------------------------------------------------------------------------
# The checks on their own
# ---------------------------------------------------------------------------

def test_check_functions_are_usable_directly():
    assert check_token_equivalence(SRC, SRC) == ()
    assert check_parse_errors(SRC, SRC) == ()
    assert verify(SRC, SRC) == ()


def test_check_parse_errors_accepts_a_precomputed_count():
    # The caller usually parsed the input already; re-parsing it to count is
    # pure waste on a corpus sweep.
    src = "component c { this is not pss }\n"
    assert check_parse_errors(src, src, original_errors=99) == ()

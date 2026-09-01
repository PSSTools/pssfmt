"""``T-43`` -- ``optional_semicolon`` over the whole corpus.

``tests/test_semicolons.py`` pins the decisions on hand-written input. This
file asks the questions that only real files can answer, and it needs no
expected output for any of them:

* the fail-safe never fires, in any of the three modes;
* the two rewriting modes are **round-trip inverses** -- ``omit`` after
  ``require`` lands exactly where ``omit`` alone does, and the other way
  round. That is the property that would break first if either mode moved a
  semicolon it should not have, and it is checkable on every file;
* the sweep is not vacuous.

**Fails when the corpus is missing; does not skip** (``C-8``).
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.rules import format_source  # noqa: E402
from pssfmt.style import SemicolonMode, Style  # noqa: E402
from pssfmt.verify import format_safely  # noqa: E402
from support import corpus_files  # noqa: E402

pytestmark = [pytest.mark.corpus, pytest.mark.integration]

FILES = corpus_files()

OMIT = Style()
PRESERVE = Style(optional_semicolon=SemicolonMode.PRESERVE)
REQUIRE = Style(optional_semicolon=SemicolonMode.REQUIRE)

MODES = [("omit", OMIT), ("preserve", PRESERVE), ("require", REQUIRE)]


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def fmt(source: str, style: Style) -> str:
    return format_source(source, style=style)


@pytest.mark.parametrize("name,style", MODES, ids=[m[0] for m in MODES])
@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_file_trips_the_fail_safe(path, name, style):
    result = format_safely(
        read(path), formatter=lambda s: fmt(s, style),
        allow_dropped_semicolons=style.drops_optional_semicolons(),
        allow_added_semicolons=style.adds_optional_semicolons())
    assert result.ok, "%s under %s: %s" % (
        path.name, name, result.error or list(result.violations))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_the_modes_are_round_trip_inverses(path):
    """``omit`` undoes ``require`` and ``require`` redoes it, exactly.

    Stronger than idempotence, which each mode has on its own: this says the
    two agree about *which* semicolons are the optional ones. A mode that
    deleted one the other would not write back -- or wrote one the other would
    not delete -- fails here on the first file that contains it.
    """
    source = read(path)
    assert fmt(fmt(source, REQUIRE), OMIT) == fmt(source, OMIT)
    assert fmt(fmt(source, OMIT), REQUIRE) == fmt(source, REQUIRE)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_preserve_never_moves_a_semicolon(path):
    """The mode that opts out. Its output must be token-identical to the
    input under the *strict* check, with no exemption at all -- which is what
    makes the exemption elsewhere an opt-in rather than a hole."""
    result = format_safely(read(path), formatter=lambda s: fmt(s, PRESERVE))
    assert result.ok, result.diagnostic(path.name)


def test_the_corpus_actually_exercises_both_directions():
    """Non-vacuity, counted in tokens rather than files.

    Every test above passes trivially on a file with no optional semicolon in
    it and no declaration to give one to, and most of the corpus is the first
    kind. The figures are the ones ``docs/style.rst`` quotes.
    """
    dropped = added = 0
    for path in FILES:
        source = read(path)
        base = fmt(source, PRESERVE).count(";")
        dropped += base - fmt(source, OMIT).count(";")
        added += fmt(source, REQUIRE).count(";") - base
    assert dropped == 27, "the corpus drops %d semicolons, not 27" % dropped
    assert added > 500, "only %d semicolons added across the corpus" % added

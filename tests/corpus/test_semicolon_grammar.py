"""``T-42`` -- the derived sets still match the grammar they came from.

``optional_semicolon`` rests on two facts about ``PSSParser.g4``, one per
direction:

:data:`pssfmt.rules.decls._SELF_TERMINATING`
    which semicolons ``omit`` may delete;
:data:`pssfmt.rules.decls._PERMITS_EMPTY_ITEM`
    which bodies ``require`` may write one into.

Both are *pasted derivations*: ``tools/semicolon_survey.py`` computes them and
the output is committed into the rule module, because the grammar is not a
runtime dependency of this package.

Pasted data goes stale silently, and these go stale in the directions that
delete tokens from users' files and add tokens to them. So the derivations are
re-run here whenever the grammar is on disk and each is compared as an
equality.

**Skips when the grammar is absent**, unlike the corpus gate, and the
difference is deliberate. ``C-8`` makes a missing *corpus* a failure because
the corpus is vendored by ``ivpm`` and its absence means the environment is
wrong. ``PSSParser.g4`` is a source file inside the parser checkout rather
than a published artefact, so an installed-from-PyPI ``pssparser`` is a normal
setup with no grammar in it, and failing there would be reporting a fault in
the wrong repository.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("pssparser")

from pssfmt.rules.decls import (  # noqa: E402
    _PERMITS_EMPTY_ITEM,
    _SELF_TERMINATING,
)

pytestmark = [pytest.mark.corpus, pytest.mark.integration]

_ROOT = Path(__file__).resolve().parents[2]
_TOOL = _ROOT / "tools" / "semicolon_survey.py"


def _load():
    spec = importlib.util.spec_from_file_location("semicolon_survey", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def survey():
    assert _TOOL.is_file(), "tools/semicolon_survey.py is missing"
    return _load()


@pytest.fixture(scope="module")
def grammar(survey):
    found = survey.find_grammar([])
    if found is None or not found.is_file():
        pytest.skip("PSSParser.g4 not on disk; see the module docstring")
    return found


def test_the_self_terminating_set_still_matches(survey, grammar):
    derived = survey.self_terminating(survey.parse_rules(grammar.read_text()))
    assert derived == set(_SELF_TERMINATING), (
        "the grammar and _SELF_TERMINATING have drifted.\n"
        "  only in the grammar: %s\n"
        "  only in decls.py:    %s\n"
        "Re-run `python tools/semicolon_survey.py --python` and paste the "
        "result, having read what moved -- a rule entering this set is a rule "
        "whose trailing `;` pssfmt will start deleting."
        % (sorted(derived - set(_SELF_TERMINATING)),
           sorted(set(_SELF_TERMINATING) - derived)))


def test_the_empty_item_set_still_matches(survey, grammar):
    derived = survey.permits_empty_item(survey.parse_rules(grammar.read_text()))
    assert derived == set(_PERMITS_EMPTY_ITEM), (
        "the grammar and _PERMITS_EMPTY_ITEM have drifted.\n"
        "  only in the grammar: %s\n"
        "  only in decls.py:    %s\n"
        "Re-run `python tools/semicolon_survey.py --empty-items --python` and "
        "paste the result, having read what moved -- a rule entering this set "
        "is a body pssfmt will start writing semicolons into."
        % (sorted(derived - set(_PERMITS_EMPTY_ITEM)),
           sorted(set(_PERMITS_EMPTY_ITEM) - derived)))


def test_the_two_sets_are_different_questions(survey, grammar):
    """Neither implies the other, and a derivation that conflated them would
    still pass both tests above if it were wrong in the same way twice.

    ``enum_declaration`` self-terminates but ``enum_item`` admits no empty
    item; ``procedural_stmt`` admits one but does not self-terminate.
    """
    assert "enum_declaration" in _SELF_TERMINATING
    assert "enum_item" not in _PERMITS_EMPTY_ITEM
    assert "procedural_stmt" in _PERMITS_EMPTY_ITEM
    assert "procedural_stmt" not in _SELF_TERMINATING


def test_the_derivation_is_not_vacuous(survey, grammar):
    """A parser bug that matched nothing would make the test above pass by
    agreeing that everything is empty."""
    rules = survey.parse_rules(grammar.read_text())
    assert len(rules) > 200, "only %d parser rules found" % len(rules)
    assert "procedural_data_declaration" in rules

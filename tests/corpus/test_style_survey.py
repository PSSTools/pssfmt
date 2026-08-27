"""``D-6`` -- the style survey stays runnable and keeps saying what the docs say.

``docs/style.rst`` is unusual for a style guide: nearly every rule in it cites
a measurement, and the measurement comes from ``tools/style_survey.py``. That
only stays honest while the tool runs and reports the same thing, so this file
pins the handful of figures the document leans on hardest.

It deliberately does *not* pin every number. A test that asserts all 30-odd
histograms would fail whenever the corpus is re-vendored, which is a normal
event, and the fix would be to paste new numbers in -- a test nobody reads the
output of. What is pinned here is the set of claims that would make
``docs/style.rst`` wrong rather than merely stale: the rules stated as
unanimous must still be unanimous, and the two documented splits must still be
split.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("pssparser")

from tests.support import CORPUS_ROOT  # noqa: E402

pytestmark = [pytest.mark.corpus, pytest.mark.integration]

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "style_survey.py"


def _load():
    spec = importlib.util.spec_from_file_location("style_survey", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def surveys():
    if CORPUS_ROOT is None:
        pytest.fail(
            "the style survey needs the corpus; absent means fail, not skip "
            "(pss-corpus PLAN.md C-8)")
    mod = _load()
    import collections

    out = collections.defaultdict(mod.Survey)
    for bucket, voice in mod.VOICE_OF.items():
        for path in sorted((Path(CORPUS_ROOT) / bucket).rglob("*.pss")):
            mod.analyse(out[voice], path)
    return mod, out


def _consensus(mod, surveys, rule):
    """(set of modal gaps, total n) across the evidence voices."""
    gaps, total = set(), 0
    for voice in mod.EVIDENCE_VOICES:
        gap, _share, n = mod.verdict(surveys[voice].gap[rule])
        if n >= 4:
            gaps.add(gap)
            total += n
    return gaps, total


#: Rules ``docs/style.rst`` states as decided, and the gap it states.
#: A change here is a change to the documented style, never a test fix.
UNANIMOUS = {
    "lhs -> ';'": 0,
    "lhs -> ','": 0,
    "',' -> rhs": 1,
    "around '::'": 0,
    "around '.'": 0,
    "'(' -> inside": 0,
    "inside -> ')'": 0,
    "'[' -> inside": 0,
    "inside -> ']'": 0,
    "callee -> '('": 0,
    "control keyword -> '('": 1,
    "'=' -> rhs": 1,
    "lhs -> '='": 1,
    "additive + - -> rhs": 1,
    "lhs -> additive + -": 1,
    "unary + - -> operand": 0,
    "lhs -> '{'": 1,
    "':' inheritance -> rhs": 1,
    "lhs -> ':' inheritance": 1,
    "':' case/select item -> rhs": 1,
    "lhs -> ':' case/select item": 0,
    "type bracket '<' -> inside": 0,
    "inside -> type bracket '>'": 0,
}

#: The two rules the corpus argues about, both humans-vs-generator. Documented
#: as split and decided by argument, so if either stops being split the
#: document's reasoning needs rereading, not its numbers.
SPLIT = ("multiplicative -> rhs", "lhs -> multiplicative", "lhs -> ':' label")


@pytest.mark.parametrize("rule,expected", sorted(UNANIMOUS.items()))
def test_the_documented_rule_is_still_unanimous(surveys, rule, expected):
    mod, sv = surveys
    gaps, n = _consensus(mod, sv, rule)
    assert n >= 4, f"{rule}: too few instances to decide ({n})"
    assert gaps == {expected}, (
        f"{rule}: docs/style.rst says {expected}, corpus now says "
        f"{sorted(gaps)} over {n} instances")


@pytest.mark.parametrize("rule", SPLIT)
def test_the_documented_splits_are_still_split(surveys, rule):
    mod, sv = surveys
    gaps, n = _consensus(mod, sv, rule)
    assert len(gaps) > 1, (
        f"{rule}: docs/style.rst documents this as a split the humans win, "
        f"but the corpus now agrees on {sorted(gaps)} over {n} instances. "
        "Reread that section rather than editing this test.")


def test_indent_is_four_spaces_and_never_a_tab(surveys):
    mod, sv = surveys
    for voice in mod.EVIDENCE_VOICES:
        steps = sv[voice].indent_steps
        assert steps.most_common(1)[0][0] == 4, f"{voice}: {dict(steps)}"
        assert sv[voice].tab_indent == 0


def test_braces_are_k_and_r(surveys):
    mod, sv = surveys
    same = sum(sv[v].brace["same-line"] for v in mod.EVIDENCE_VOICES)
    own = sum(sv[v].brace["own-line"] for v in mod.EVIDENCE_VOICES)
    assert same > own * 100, f"same-line {same}, own-line {own}"


def test_alignment_splits_hand_written_from_generated(surveys):
    """The ``Q-5`` ``infer`` evidence -- the sharpest result in the survey.

    Hand-written code aligns its trailing comments; generated code does not.
    If this ever stops being true, ``infer`` stops being justified.
    """
    _mod, sv = surveys
    hand = sv["hand-written"].align
    gen = sv["generated"].align
    assert hand["trailing comment runs: aligned"] > 0
    assert hand["trailing comment runs: ragged"] == 0
    assert gen["trailing comment runs: ragged"] > 0
    assert gen["trailing comment runs: aligned"] == 0


def test_the_survey_reads_code_not_comments(surveys):
    """The trap that produced a wrong number in ``docs/style.rst``'s draft.

    ``peakrdl`` documents field ranges in trailing comments -- ``// [31:0]``
    -- while its code says ``bit[32] f;``. A text search finds 98 bit-slices
    there; the token stream finds none. Pinned because the failure is silent:
    a survey that quietly counts commentary still prints plausible numbers.
    """
    _mod, sv = surveys
    slices = sv["generated"].gap["':' bit-slice [a:b] -> rhs"]
    assert sum(slices.values()) == 0, (
        "the survey is counting bit-slices in generated code, which has none "
        "-- it is reading comments as code")

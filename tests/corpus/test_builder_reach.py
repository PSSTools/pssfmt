"""``T-30`` -- which registered builders the corpus actually runs.

The measurement this file automates has been made by hand three times, and
each time it found something a fully green suite was silent about:

* ``P3-6`` -- 31 of the 92 corpus files put their declarations inside an
  ``extend``, and until ``extend`` had a rule *every rule that would have
  applied within those files was inert*. Field rules had been flattening
  hand-built tables in eight of them for two releases.
* ``P3-7`` -- 13 of 137 template argument lists are never reached, because
  they sit inside ``exec`` bodies and function parameter lists, neither of
  which has a rule.
* ``P3-8`` -- three corpus style gates passed only because no input reached
  the case they were written for.

The general form is worth stating, because it is not obvious and it cost two
releases to learn: **coverage of the corpus text and coverage of the rules
that ran are different measurements.** A rule can only run on a node whose
ancestors all have rules, so an unwritten -- or unreached -- rule high in the
tree hides every defect below it. Counting files, lines, or constructs will
not show this. Counting *builder invocations* will.

Two different questions
-----------------------
This file asks both, because conflating them is how the pinned list below
would rot into a rubber stamp:

``test_every_builder_is_reached_by_something``
    Is this builder exercised **at all**, by any test in the suite? A "no"
    means an untested rule, which is a defect regardless of the corpus.

``test_the_corpus_reaches_every_builder_but_these``
    Is it exercised by **real PSS that somebody wrote**? A "no" is not a
    defect -- some constructs are genuinely rare -- but it is a fact that
    must be *stated* rather than discovered later, because it downgrades
    every claim this project makes from "measured over 92 files" to "checked
    against an example I wrote myself".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("pssparser")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from support import corpus_files  # noqa: E402

import pssfmt.rules as rules  # noqa: E402

#: Builders no corpus file reaches, each with where it *is* covered.
#:
#: A literal rather than a computed set, so that a construct falling out of
#: corpus reach is a failure rather than a silently larger number. Adding a
#: name here is a deliberate act that says "no real PSS I have exercises
#: this"; removing one is free.
NOT_IN_THE_CORPUS = {
    # `soft x == 1;` -- covered by T-21 (tests/test_constraints.py) and by
    # the tier2_constraints golden. The corpus has zero soft constraints,
    # which is surprising for a randomisation language and probably says
    # more about what people publish than about what they write.
    "soft_constraint_item",
    # `default disable x;` -- same two places. `default_constraint` (the
    # value form) is reached exactly once, in one file, so this pair is thin
    # in the corpus rather than absent from it.
    "default_disable_constraint",
    # `break;` and `continue;` -- covered by T-38 (tests/test_statements.py)
    # and by the tier2_functions golden. The corpus has exactly one of each,
    # and both are inside the same `if (el == 0) break;`, so they are hidden
    # by `procedural_if_else_stmt` rather than absent: `P3-11b` declines that
    # construct until `docs/style.rst` decides where `} else {` goes.
    #
    # Worth stating plainly because the two facts are different: these rules
    # are exercised by real corpus *text*, and by no corpus *dispatch*. That
    # distinction is the whole reason this file asks two questions.
    "procedural_break_stmt",
    "procedural_continue_stmt",
}


def reach_over(sources):
    """Builder name -> (calls, files) over *sources*, by instrumenting the
    registry.

    Instrumentation rather than coverage tooling: what is being counted is
    *dispatch*, not line execution, and a builder that runs and then bails
    out on its first line is reached for this purpose. Line coverage would
    call that covered too, but for the opposite reason, and the distinction
    is the entire point of the measurement.
    """
    names = sorted(rules.REGISTRY._builders)
    calls = {n: 0 for n in names}
    files = {n: set() for n in names}
    current = [None]

    def wrap(name, fn):
        def wrapped(ctx, node, *a, **k):
            calls[name] += 1
            files[name].add(current[0])
            return fn(ctx, node, *a, **k)
        return wrapped

    original = dict(rules.REGISTRY._builders)
    try:
        for name in names:
            rules.REGISTRY._builders[name] = wrap(name, original[name])
        for label, text in sources:
            current[0] = label
            rules.format_source(text)
    finally:
        rules.REGISTRY._builders.update(original)
    return {n: (calls[n], len(files[n])) for n in names}


@pytest.fixture(scope="module")
def corpus_reach():
    return reach_over([(p.name, p.read_text()) for p in corpus_files()])


@pytest.fixture(scope="module")
def golden_reach():
    root = Path(__file__).resolve().parent.parent / "golden"
    return reach_over([(d.name, (d / "input.pss").read_text())
                       for d in sorted(root.iterdir()) if d.is_dir()])


def test_the_corpus_reaches_every_builder_but_these(corpus_reach):
    """Pins the corpus-unreached set exactly, in both directions.

    Equality and not a subset check. A builder that *gains* corpus reach is
    good news, and it still fails here -- because the entry above claims
    something about the corpus that has stopped being true, and a stale claim
    in a file whose whole job is honest accounting is worse than no file.
    """
    unreached = {n for n, (c, _) in corpus_reach.items() if c == 0}
    assert unreached == NOT_IN_THE_CORPUS, (
        "corpus builder reach changed.\n"
        "  no longer reached: %s\n"
        "  newly reached: %s\n"
        "Update NOT_IN_THE_CORPUS, and say in the comment where each is "
        "covered instead." % (sorted(unreached - NOT_IN_THE_CORPUS),
                              sorted(NOT_IN_THE_CORPUS - unreached)))


def test_every_builder_is_reached_by_something(corpus_reach, golden_reach):
    """No registered builder is entirely unexercised.

    The corpus and the goldens together, because that is the union this
    project actually stands behind: real PSS where it exists, and a
    hand-written file that a human read where it does not.
    """
    dead = {n for n in corpus_reach
            if corpus_reach[n][0] == 0 and golden_reach.get(n, (0, 0))[0] == 0}
    assert not dead, (
        "registered but never dispatched by the corpus or any golden: %s. "
        "A rule nobody runs is a rule nobody tests." % sorted(dead))


def test_the_goldens_cover_what_the_corpus_cannot(golden_reach):
    """The goldens are why ``NOT_IN_THE_CORPUS`` is admissible.

    Without this, that set could quietly become a list of constructs with no
    coverage anywhere, and the file above it would read as though the gap had
    been considered.
    """
    missed = {n for n in NOT_IN_THE_CORPUS
              if golden_reach.get(n, (0, 0))[0] == 0}
    assert not missed, (
        "declared absent from the corpus and also absent from the goldens: "
        "%s" % sorted(missed))


def test_reach_is_measured_over_a_real_corpus(corpus_reach):
    """Guards the measurement itself.

    Every assertion above is vacuous if the corpus failed to load -- an empty
    source list makes *everything* unreached, which the equality check would
    report as a long confusing diff rather than as "there is no corpus".
    """
    assert sum(c for c, _ in corpus_reach.values()) > 500

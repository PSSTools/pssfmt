"""``T-6`` -- golden files, one directory per construct group.

``PLAN.md`` section 7.1 puts golden tests last and calls them expensive, and
that ordering was right: written first they pin renderings nobody has decided
yet, and every subsequent rule change becomes a diff review. Written last, on
top of a suite that already pins the *decisions* construct by construct, they
answer the one question those tests structurally cannot.

What a golden adds that a snippet test does not
-----------------------------------------------
A snippet test asserts about the construct it names. A golden asserts about a
**whole file**, which is where constructs interact: blank lines between
members, a comment attached to the thing below it, an alignment group ending
where a rule that does not align begins, and -- the one that mattered -- a
header refusing to format because of something in a body four lines away.

That last was a live bug, found by reading the first generated output rather
than by any assertion here: a ``constraint`` block containing a ``default``
item kept the author's spacing in its *header*, because the sites walk was
bounded with ``>`` where it needed ``>=`` and so was handed the entire body.
Every construct involved had passing tests. Nothing smaller than a whole file
puts a header and a distant body item in the same field of view.

Why the expected files are generated and then *read*
----------------------------------------------------
Hand-writing them would test my typing. Generating them without reading them
would pin whatever the formatter does, including its bugs, which is the
standard way a golden suite becomes a liability. So the workflow is: generate,
read every line, and treat anything surprising as a bug report against the
formatter until it is explained. Three things in the current outputs were
surprising; one was the bug above, and the other two are documented behaviour
worth knowing about before you conclude a golden is wrong:

* **A lone declaration keeps the author's padding.** ``bit[4]   priority;``
  alone in a body stays as written. ``infer`` treats one line as no evidence
  of a table, so it reproduces rather than flattens. Two lines padded to the
  same column are read as a deliberate table and also kept.
* **Constraint items do not all align alike.** ``soft`` and plain expression
  items emit a column stop; ``default`` items do not. A block mixing them
  comes out partly aligned. That is an inconsistency rather than a decision
  (``P3-5a``), and it is *pinned here on purpose* so that fixing it shows up
  as a golden diff rather than as silence.

Regenerating
------------
``pytest tests/test_golden.py --update-golden`` rewrites every
``expected.pss`` and then **fails**, so a regeneration can never be mistaken
for a passing run. Read the diff before committing it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pssparser")

from pssparser import cst as _cst  # noqa: E402

from pssfmt.rules import format_source  # noqa: E402
from pssfmt.verify import verify  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"

#: One directory per construct group, mirroring the ``P3-*`` tiers.
CASES = sorted(d.name for d in GOLDEN.iterdir()
               if d.is_dir() and (d / "input.pss").exists())


def read(case: str, which: str) -> str:
    return (GOLDEN / case / which).read_text()


def test_there_are_cases():
    """A golden suite that silently collects nothing passes forever.

    The directory listing is the test's input, so an empty or mistyped
    ``GOLDEN`` would turn every test below into zero tests and report
    success. Cheap to assert, and the alternative is a suite that goes quiet
    without failing.
    """
    assert len(CASES) >= 8, CASES


@pytest.mark.parametrize("case", CASES)
def test_input_parses_cleanly(case):
    """No golden input may rely on error recovery.

    A file with a syntax error exercises the fallback -- which reproduces the
    author's bytes -- and a golden built on that pins *copying* while looking
    like it pins formatting. Two of these inputs did parse with errors when
    first written (a field named ``pool``, which is a keyword, and a bare
    ``const`` where PSS wants ``static const``); both looked completely
    ordinary in the expected output.
    """
    assert _cst.parse(read(case, "input.pss")).num_syntax_errors == 0


@pytest.mark.parametrize("case", CASES)
def test_matches_expected(case, request):
    """The golden assertion, and the ``--update-golden`` path."""
    src = read(case, "input.pss")
    out = format_source(src)
    path = GOLDEN / case / "expected.pss"

    if request.config.getoption("--update-golden"):
        path.write_text(out)
        pytest.fail("--update-golden rewrote %s; review the diff" % path.name)

    assert path.exists(), (
        "%s has no expected.pss -- run with --update-golden" % case)
    assert out == path.read_text()


@pytest.mark.parametrize("case", CASES)
def test_expected_is_idempotent(case):
    """Formatting the expected output again changes nothing.

    ``PLAN.md`` ``T-6`` calls this mandatory "or they will rot", and the rot
    it prevents is specific: an expected file regenerated from a formatter
    with an unstable rule records the *first* of two outputs, and the suite
    then passes while the tool oscillates on real input.
    """
    expected = read(case, "expected.pss")
    assert format_source(expected) == expected


@pytest.mark.parametrize("case", CASES)
def test_expected_says_what_the_input_said(case):
    """Token equivalence, checked here and not only inside the formatter.

    ``format_source`` deliberately does not verify -- the fail-safe is a
    separate layer so that no rule can bypass it -- which means these files
    are generated by the *unverified* path. Checking them here is what makes
    a golden a check on the rules rather than a transcript of them.
    """
    violations = verify(read(case, "input.pss"), read(case, "expected.pss"))
    assert not violations, violations

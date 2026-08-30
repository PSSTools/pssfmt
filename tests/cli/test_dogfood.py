"""``P4``'s exit criterion: ``pssfmt --check`` runs clean on this repo's own
tracked ``.pss`` files.

Restated, because taken literally it cannot be satisfied and should not be.
The only tracked ``.pss`` files here are the golden pairs, and half of them
are ``input.pss`` -- **deliberately untidy**, since a golden whose input is
already formatted tests nothing. A criterion of "every tracked file is clean"
would be met by deleting the inputs.

So the two halves are asserted separately, and together they say something the
original wording did not:

* every ``expected.pss`` is clean, which is the actual dogfooding claim;
* every ``input.pss`` that the golden suite records as changing is reported by
  ``--check`` as changing.

The second is the one worth having. It is an **end-to-end cross-check between
the CLI and the golden suite**, reached by completely different routes: the
goldens compare in memory through ``format_source``, and this runs the
argument parser, the directory walk, the file reader and the exit-code logic
over the same files on disk. A CLI that formatted correctly and reported
wrongly passes every other test in this directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pssparser")

from pssfmt import cli  # noqa: E402

GOLDEN = Path(__file__).resolve().parent.parent / "golden"


def cases():
    return sorted(d for d in GOLDEN.iterdir() if d.is_dir())


def check(*paths):
    import io

    out, err = io.StringIO(), io.StringIO()
    code = cli.main(["--check"] + [str(p) for p in paths],
                    stdin=io.StringIO(), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_there_are_golden_directories():
    """Guards the two tests below against passing over an empty list, which is
    how a dogfooding test quietly stops dogfooding."""
    assert len(cases()) >= 5


@pytest.mark.parametrize("case", cases(), ids=lambda d: d.name)
def test_check_is_clean_on_every_expected_file(case):
    """The criterion itself.

    Failing here means the CLI disagrees with the formatter that produced the
    file, which can only be the parts the golden tests do not touch: how the
    bytes are read, how they are decoded, and what counts as a change.
    """
    code, out, err = check(case / "expected.pss")
    assert code == cli.OK, err
    assert (out, err) == ("", "")


@pytest.mark.parametrize("case", cases(), ids=lambda d: d.name)
def test_check_reports_exactly_what_the_goldens_say_will_change(case):
    """Both directions, so neither a false clean nor a false diff passes."""
    src = (case / "input.pss").read_text()
    expected = (case / "expected.pss").read_text()
    code, _, _ = check(case / "input.pss")
    if src == expected:
        assert code == cli.OK
    else:
        assert code == cli.WOULD_CHANGE


def test_a_walk_over_the_golden_tree_finds_every_file():
    """The walk, on a real directory tree rather than a synthetic one.

    ``walk`` is the only part of the CLI whose bugs are silent: a skipped
    directory makes ``--check`` greener, not redder, so it is the one function
    here that must be checked against a known answer rather than against
    itself.
    """
    found = {p.relative_to(GOLDEN).as_posix() for p in cli.walk(GOLDEN)}
    assert found == {"%s/%s" % (d.name, n)
                     for d in cases() for n in ("expected.pss", "input.pss")}

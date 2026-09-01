"""``U-8`` -- minimal reproducers for the ``pssparser`` gaps the corpus found.

Found by pointing ``P1``'s round-trip gate at the ``pygments-pss`` corpus,
which no ``pssparser`` suite had run against: that corpus was built for a
*lexer*, so it contains constructs the AST tests never exercise.

Every case in :data:`GAPS` is valid PSS that ``pssparser`` rejects. They are marked
``xfail(strict=True)``, so this file is an executable specification -- fixing a
gap turns its case green, which fails the strict mark and forces both this
entry and the matching ``KNOWN_UNPARSEABLE`` entry to be deleted together.

None of these block ``P1``. The null formatter round-trips every one of them
byte for byte, which is what the fail-safe is for. They block ``P3``: a rule
cannot lay out a construct the tree does not contain.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("pssparser")

from pssparser import cst, tokens  # noqa: E402

from pssfmt.null import format_null  # noqa: E402

pytestmark = [pytest.mark.corpus, pytest.mark.integration]


GAPS = {
    "U-8b: dist constraint":
        "component c { action a { rand int x; "
        "constraint { dist x := 1; } } }",
    "U-8d: underscore inside a based number":
        "component c { bit[31:0] e = 16'h_FF; }",
    "U-8e: octal escape in a string literal":
        'component c { string s = "a: \\101"; }',
}


#: ``U-8a`` and ``U-8c``, withdrawn. Not fixed -- *never defects*. Both were
#: read out of the three ``pss31/`` corpus files, which had been transcribed
#: from the LRM's examples, and the LRM's examples are fragments rather than
#: compilable PSS:
#:
#: * ``U-8a`` -- ``package_body_item`` (Annex B.1) admits only
#:   ``abstract_action_declaration``. A bare ``action`` at package scope is a
#:   syntax error by the standard.
#: * ``U-8c`` -- ``activity_stmt`` (B.11) does not list ``cover_stmt``, which
#:   B.7 admits only as a ``component_body_item``.
#:
#: Kept as live assertions rather than deleted. Both entries spent their whole
#: life marked ``xfail(strict=True)`` here and in pssparser, which reads as
#: *known and scheduled*; that is exactly why the misdiagnosis survived. Turning
#: them around means the next person to "close U-8a" by widening the grammar
#: gets a failing test naming the clause instead of a green suite.
WITHDRAWN = {
    "U-8a: action at package scope is a syntax error (B.1)":
        "package p { action a { } }",
    "U-8c: cover in an activity is a syntax error (B.11)":
        "component c { action a { activity { cover { } } } }",
}


@pytest.mark.parametrize("src", GAPS.values(), ids=list(GAPS))
@pytest.mark.xfail(strict=True, reason="U-8: pssparser grammar/lexer gap")
def test_valid_pss_parses(src):
    assert cst.parse(src).num_syntax_errors == 0


@pytest.mark.parametrize("src", WITHDRAWN.values(), ids=list(WITHDRAWN))
def test_withdrawn_gaps_are_still_correctly_rejected(src):
    assert cst.parse(src).num_syntax_errors > 0, (
        "pssparser now accepts source Annex B does not derive. This was once "
        "recorded as a U-8 gap; it is not one. Widening the grammar to admit "
        "it makes the front end unsound -- see the note above WITHDRAWN.")


@pytest.mark.parametrize("src", WITHDRAWN.values(), ids=list(WITHDRAWN))
def test_the_formatter_survives_every_withdrawn_gap(src):
    # Same fail-safe promise as for the open gaps: unparseable input, whatever
    # the reason, still round-trips byte for byte.
    assert format_null(src).text == src


@pytest.mark.parametrize("src", GAPS.values(), ids=list(GAPS))
def test_the_formatter_survives_every_gap(src):
    # The point of the fail-safe, demonstrated on the real thing rather than on
    # a mock: pssparser cannot parse these, and pssfmt still does not lose a
    # byte of them.
    assert format_null(src).text == src


def test_the_two_lexer_gaps_are_lexer_gaps_not_parser_gaps():
    # Worth distinguishing. A parser gap leaves well-formed tokens the grammar
    # cannot assemble; a lexer gap leaves synthetic error tokens standing for
    # text no rule matched. The second kind is invisible to anything working
    # above the token stream, so it needs recording where it can be seen.
    assert tokens.tokenize("component c { bit[31:0] e = 16'h_FF; }") \
        .num_errors > 0
    assert tokens.tokenize('component c { string s = "a: \\101"; }') \
        .num_errors > 0
    assert tokens.tokenize("package p { action a { } }").num_errors == 0


def test_the_nearest_accepted_spellings_still_work():
    # Pins where each boundary actually is, so a fix can be checked against
    # something narrower than "the file parses now".
    assert cst.parse("package p { abstract action a { } }") \
        .num_syntax_errors == 0
    assert cst.parse("component c { action a { } }").num_syntax_errors == 0
    assert cst.parse("component c { bit[31:0] e = 16'hFF; }") \
        .num_syntax_errors == 0
    assert cst.parse('component c { string s = "a: \\n"; }') \
        .num_syntax_errors == 0


# ---------------------------------------------------------------------------
# C-20 -- the same names on both sides of the boundary
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: pssparser's corpus sweep (pss-corpus PLAN.md C-18), which records the same
#: defects from the other side: it sweeps whole corpus *files*, this module
#: reproduces each cause in one line of PSS.
_SWEEP = (_REPO_ROOT / "packages" / "pssparser" / "tests" / "python"
          / "corpus" / "test_pss_corpus.py")


def _literals(path, *names):
    """Read module-level literal assignments without importing the module.

    Read rather than imported on purpose. Importing would run pssparser's
    corpus discovery, insert on ``sys.path`` and bind that module's idea of
    where the corpus lives into this process -- for what is a comparison of two
    tables of strings. Parsing sidesteps all of it, and works whether or not
    the file's own dependencies are satisfied here.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                out[target.id] = ast.literal_eval(node.value)
    missing = set(names) - set(out)
    assert not missing, "%s no longer defines %s" % (path.name, sorted(missing))
    return out


def _sweep_tables():
    if not _SWEEP.is_file():
        # Legitimately absent: pssfmt can be developed against an installed
        # pssparser wheel, which carries no tests. The check this skips is a
        # duplicate -- pssparser's own suite pins its tables internally
        # (test_the_recorded_defects_use_the_declared_identifiers). What is
        # lost here is only the cross-repo half.
        pytest.skip("pssparser's corpus sweep is not in this checkout: %s"
                    % _SWEEP)
    return _literals(_SWEEP, "RECORDED_DEFECTS", "KNOWN_UNPARSEABLE")


def _ids(reasons):
    return {r.split(":", 1)[0].strip() for r in reasons}


def test_every_gap_reproduced_here_is_one_pssparser_records():
    # The direction that catches a stale reproducer: a gap fixed upstream and
    # struck from pssparser's table, while this file still carries a case for
    # it under a name that no longer means anything.
    tables = _sweep_tables()
    ours = _ids(GAPS)
    theirs = set(tables["RECORDED_DEFECTS"])
    assert ours <= theirs, (
        "this file reproduces gaps pssparser does not record: %s. Either the "
        "identifier is stale here, or pssparser's RECORDED_DEFECTS lost an "
        "entry it still needs." % sorted(ours - theirs))


def test_every_u8_pssparser_records_is_reproduced_here():
    # The other direction, and the one with teeth. A gap only pssparser knows
    # about has no minimal case anywhere, so whoever fixes it has nothing to
    # work against but a 200-line corpus file.
    #
    # Restricted to U-8: those are valid PSS the grammar rejects, which is what
    # this module is for. U-9 is the inverse -- input the front end wrongly
    # *accepts* -- and a reproducer for it belongs with the CLI's exit-status
    # behaviour, not here among constructs pssfmt must round-trip.
    tables = _sweep_tables()
    theirs = {d for d in tables["RECORDED_DEFECTS"] if d.startswith("U-8")}
    ours = _ids(GAPS)
    assert theirs <= ours, (
        "pssparser records U-8 gaps with no minimal reproducer here: %s"
        % sorted(theirs - ours))


def test_the_two_repos_agree_on_which_corpus_files_fail():
    # The strongest of the three: not just the vocabulary but the findings.
    # Both repos sweep the same 92 files with the same parser, so their
    # file-to-cause tables must be equal -- if they diverge, one of them is
    # describing a parser that is not the one being run.
    tables = _sweep_tables()
    # Read from source, like the other side, rather than imported: importing
    # test_round_trip depends on pytest having put this directory on sys.path,
    # which is a property of how the suite was invoked and not of the tables.
    ours = _literals(
        Path(__file__).with_name("test_round_trip.py"),
        "KNOWN_UNPARSEABLE")["KNOWN_UNPARSEABLE"]

    theirs = tables["KNOWN_UNPARSEABLE"]
    assert set(ours) == set(theirs), (
        "the repos disagree on which corpus files fail to parse.\n"
        "  only pssfmt:    %s\n  only pssparser: %s"
        % (sorted(set(ours) - set(theirs)), sorted(set(theirs) - set(ours))))
    differing = sorted(k for k in ours if ours[k] != theirs[k])
    assert not differing, (
        "same files, different recorded causes: %s. The cause strings are "
        "shared verbatim so that one fix flips both repos' markers together."
        % differing)

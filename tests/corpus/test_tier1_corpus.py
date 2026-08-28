"""``T-20`` -- the shipped rule set over the corpus (``P3-2``).

The gate changes shape here, and that is the point of the file.

Until ``P3-2`` the formatter reproduced its input, so the corpus test could
assert **byte identity** -- the strongest possible oracle, and free. Tier 1
reformats, so byte identity is no longer the right question and asserting it
would only invite weakening the rules to keep the test green.

What replaces it is ``PLAN.md`` section 7.1's tiers 2 through 4, which need no
hand-authored expected output either:

* **token equivalence** -- the output re-lexes to the same tokens;
* **idempotence** -- formatting the output again changes nothing;
* **no new parse errors**;
* and, above all, **the fail-safe never fires**, which is a different claim
  from "the output was fine": a tripped fail-safe returns the input, so a test
  comparing output to input would pass on the one file where the formatter
  had gone wrong.

Plus the style properties ``docs/style.rst`` measured as unanimous, which the
output must now satisfy rather than merely preserve.

Byte identity has not disappeared -- it moved to the *empty* rule set, in
``test_rule_fallback.py``, where it is still exactly right. The hand-written
counterpart to this file, where a failure names a construct rather than a
corpus file, is ``tests/test_tier1.py``.

**Fails when the corpus is missing; does not skip** (``C-8``).
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.rules import REGISTRY, format_source  # noqa: E402
from pssfmt.verify import format_safely  # noqa: E402
from support import CORPUS_ROOT, CORPUS_SOURCE, corpus_files  # noqa: E402

pytestmark = [pytest.mark.corpus, pytest.mark.integration]

FILES = corpus_files()

#: The corpus files Tier 1 changes, and why. Pinned as a set so that the
#: *blast radius* of a rule change is visible in a diff rather than buried in
#: a count -- a rule that suddenly reformats twenty more files is a finding
#: whether or not each change is individually defensible.
#:
#: Every entry is one of three things: an empty body written ``{ }``, a body
#: written on one line, or a member the author indented to a column that is
#: not the body's. All three are decided by ``docs/style.rst``.
REFORMATTED = {
    "example2/dma_types_pkg.pss",
    "example2/mem_c.pss",
    "example2/spi_types_pkg.pss",
    "language-ref/activity_shapes.pss",
    "language-ref/behavioral_coverage.pss",
    "language-ref/coverage.pss",
    # The fourth kind, added by ``P3-5``, and the only entry here that is a
    # second-order effect rather than a direct one::
    #
    #     rand T   payload;
    #     rand int in [1..N] count;
    #
    # The author padded ``T`` to the width of ``int``. Until ``P3-5`` the
    # second line declined -- ``in`` was not in any vocabulary -- so the first
    # was a *lone* marked line, which ``infer`` reproduces because one line is
    # no evidence. Formatting the second line gives the group a second member,
    # and by the column ``infer`` actually measures (the declarator: ``payload``
    # at 9, ``count`` at 24) the two do not line up. So the block is ragged and
    # is set flush left, which is what ``docs/style.rst`` says ``infer`` does.
    #
    # Recorded rather than worked around: what the author aligned is the *type*
    # column, and inferring that from two lines of different shape is not
    # something one instance can justify teaching the alignment pass.
    "language-ref/extension_variants.pss",
    "language-ref/flow_basic.pss",
    # ``P3-5``, and the only file constraints move at all -- the other 51
    # constraint declarations in the corpus were already written the way the
    # measurement says. See :data:`HOSTILE_BUT_VALID` below for why this one
    # is formatted rather than declined.
    "lexical/escaped_identifiers.pss",
    "stdlib/addr_reg_pkg.pss",
    "stdlib/executor_pkg.pss",
    "stdlib/std_pkg.pss",
}


def ident(path):
    return str(path.relative_to(CORPUS_ROOT)) if CORPUS_ROOT else str(path)


def read(path):
    # Binary, then decode explicitly: text mode translates newlines, and a
    # CRLF file would then pass for the wrong reason.
    return path.read_bytes().decode("utf-8")


def test_the_corpus_is_present():
    """The one test here that cannot vanish along with its input."""
    assert CORPUS_SOURCE != "none", (
        "no PSS corpus found. It is a declared ivpm dependency and should be "
        "at packages/pss-corpus -- run `ivpm update`, or set PSS_CORPUS.")
    assert len(FILES) >= 50, (
        "%d files from %s -- too few to be the curated corpus"
        % (len(FILES), CORPUS_SOURCE))


def test_there_are_rules_to_test():
    """Guards the guard. Every test below would pass on an empty registry.

    They would pass by testing the ``P3-1`` fallback all over again, having
    checked nothing about Tier 1 -- the same shape of failure as a suite whose
    corpus is missing, and just as quiet.
    """
    assert len(REGISTRY) > 0


# ---------------------------------------------------------------------------
# The oracles that need no expected output
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_no_file_trips_the_fail_safe(path):
    """Token equivalence, idempotence and parse errors, in one assertion.

    The second assertion is the one that matters. A tripped fail-safe returns
    the *input*, so a test that only compared output to input would pass on
    precisely the file where something went wrong.
    """
    src = read(path)
    result = format_safely(src, formatter=format_source)
    assert result.ok, (
        "%s tripped the fail-safe: %s"
        % (ident(path), result.error or list(result.violations)))


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_formatting_is_idempotent(path):
    """Asserted separately from the fail-safe, and deliberately so.

    ``format_safely`` checks idempotence and then hides the answer behind a
    fallback. Running it directly means a failure here reports *what* moved on
    the second pass, which is the only thing that makes an oscillating rule
    findable.
    """
    once = format_source(read(path))
    assert format_source(once) == once


#: The one file under ``lexical/`` or ``pathological/`` that is not malformed.
#:
#: It is *hostile* -- ``\\top-level_c``, ``\\busa+index``, escaped identifiers
#: that swallow whatever follows them -- and it is also the only file in either
#: directory the parser accepts with **zero** error nodes. So it is valid PSS,
#: and from ``P3-5`` it contains a construct the formatter accounts for
#: completely: ``constraint \\c1 { \\busa+index > 0; }``, which is opened out
#: like the other 31 named constraint blocks in the corpus.
#:
#: Excluded here rather than the rule being narrowed, because the property this
#: test defends is "decline what you cannot account for", not "never touch a
#: file with a difficult name in it". What must still hold for it is checked
#: below and is the part that matters: every token survives, and every escaped
#: identifier survives character for character.
HOSTILE_BUT_VALID = "lexical/escaped_identifiers.pss"


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_broken_input_is_still_not_mangled(path):
    """Malformed input matters more here, not less.

    A file the user is halfway through editing is what a formatter must not
    damage, and it is where the tree least resembles the source. Tier 1
    declines to lay out a construct it cannot account for, so these come back
    intact rather than reformatted.
    """
    src = read(path)
    result = format_safely(src, formatter=format_source)
    assert result.ok
    if ident(path) == HOSTILE_BUT_VALID:
        return
    if "pathological" in ident(path) or "lexical" in ident(path):
        assert result.text == src, (
            "%s was reformatted despite being deliberately malformed; Tier 1 "
            "is supposed to decline rather than guess" % ident(path))


def test_the_hostile_file_keeps_every_escaped_identifier():
    """What :data:`HOSTILE_BUT_VALID` gives up byte-identity for.

    An escaped identifier runs to the next whitespace and swallows anything
    printable on the way, so it is the construct a formatter is most likely to
    damage while producing output that looks entirely reasonable. Checked as a
    multiset so that a *moved* identifier still passes and a mangled, merged or
    dropped one cannot.
    """
    from pssparser import cst as _cst

    matching = [p for p in FILES if ident(p) == HOSTILE_BUT_VALID]
    if not matching:
        pytest.skip("%s not in this corpus" % HOSTILE_BUT_VALID)
    src = read(matching[0])

    def escaped(text):
        return sorted(t.text for t in _cst.parse(text).tokens
                      if t.type_name == "ESCAPED_ID")

    before = escaped(src)
    assert before, "the sample is supposed to be full of these"
    assert escaped(format_source(src)) == before


# ---------------------------------------------------------------------------
# The style the output must now have, not merely preserve
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_the_output_has_no_trailing_whitespace(path):
    """``docs/style.rst``: 0 of 4856 lines. Unanimous across every voice."""
    offenders = [i for i, line in enumerate(format_source(read(path)).splitlines(), 1)
                 if line != line.rstrip()]
    assert not offenders, "%s: trailing whitespace on lines %s" % (
        ident(path), offenders[:10])


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_the_output_never_indents_with_a_tab(path):
    """Also 0 of 4856, and ``use_tabs`` defaults to false."""
    out = format_source(read(path))
    offenders = [i for i, line in enumerate(out.splitlines(), 1)
                 if "\t" in line[:len(line) - len(line.lstrip())]]
    assert not offenders, "%s: tab indentation on lines %s" % (
        ident(path), offenders[:10])


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_the_output_never_puts_a_brace_on_its_own_line(path):
    """K&R, 732 of 733. Allman does not occur in the corpus and must not be
    introduced by the formatter."""
    offenders = [i for i, line in enumerate(format_source(read(path)).splitlines(), 1)
                 if line.strip() == "{"]
    assert not offenders, "%s: lone opening brace on lines %s" % (
        ident(path), offenders[:10])


# ---------------------------------------------------------------------------
# Blast radius
# ---------------------------------------------------------------------------


def test_the_set_of_files_tier_1_changes_is_the_expected_one():
    """Which files move, not how many.

    A rule that starts reformatting files it did not touch before is worth
    looking at even when every individual change is defensible, and a count
    would not say which ones. Update ``REFORMATTED`` deliberately, having read
    the diffs -- that edit is the record that somebody did.
    """
    changed = {ident(p) for p in FILES if format_source(read(p)) != read(p)}
    assert changed == REFORMATTED, (
        "newly reformatted: %s\nno longer reformatted: %s"
        % (sorted(changed - REFORMATTED), sorted(REFORMATTED - changed)))

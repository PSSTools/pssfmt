"""``P1-4`` / ``T-4`` / ``T-5`` -- the corpus gate, and ``P1``'s exit criterion.

*"``P1-2`` reproduces every corpus file byte-for-byte, including
``pathological/`` and ``lexical/``, in CI."*

Buckets carry policy, exactly as ``T-4`` specifies:

* **every** file must round-trip through the null formatter byte for byte, and
  must survive the ``P1-3`` fail-safe. Deliberately broken input is *more*
  important here, not less: mangling a file the user was in the middle of
  editing is the failure this layer exists to prevent.
* only files outside ``pathological/`` must parse cleanly. A file in that
  bucket is expected not to.

One test per file, so a regression names its file rather than reporting that
"the corpus" broke.

Where the corpus comes from
---------------------------
``Q-3`` is closed: the corpus is ``pss-corpus``, an ivpm dependency landing at
``packages/pss-corpus``, resolved by :func:`support._find_corpus` (that plan's
section 5.1).

**A missing corpus fails this suite; it does not skip it** (``C-8``). A gate
that skips when its input is absent is not a gate -- it reports success in
exactly the circumstance it was built to catch, which is how ``P1``'s exit
criterion sat at "met, but not in CI" for as long as it did.

*Missing corpus* and *missing parser* are different conditions and must not
collapse into one. ``pssparser`` absent still skips, via the ``importorskip``
below, because ``T-2`` requires the layout suite to collect without it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.null import format_null  # noqa: E402
from pssfmt.verify import format_safely  # noqa: E402
from support import (  # noqa: E402
    CORPUS_ROOT,
    CORPUS_SOURCE,
    FALLBACK_BROKEN_BUCKETS,
    assert_partitions_the_stream,
    broken_buckets,
    corpus_files,
)

pytestmark = [pytest.mark.corpus, pytest.mark.integration]

FILES = corpus_files()

#: Files here are expected not to parse. ``T-4``: excluded from the must-parse
#: rule, never from the must-not-corrupt rule.
#:
#: ``C-9``: read from the corpus's own ``manifest.toml``, so a new bucket
#: arrives carrying its policy rather than needing a matching commit in each of
#: three consumers.
BROKEN_BUCKETS = broken_buckets()

#: Corpus files that are valid PSS and that ``pssparser`` cannot parse today.
#:
#: ``P1``'s exit criterion is explicit that a file which fails is *"either a
#: ``U-*`` bug or an explicitly-recorded known-bad entry with an issue number --
#: never a silent skip"*. These are the former, recorded here until ``U-8``
#: closes them. Each entry is the **first** cause found in that file; a file may
#: have more behind it.
#:
#: The marks are strict, so fixing a gap turns the corresponding entry into a
#: failure and forces it to be deleted. A list like this rots the moment it is
#: allowed to pass silently.
#:
#: The three ``pss31/`` entries were removed when ``U-8a`` and ``U-8c`` were
#: **withdrawn** -- neither was ever a pssparser defect. Those files were
#: transcribed from the LRM's examples, which are fragments: a bare ``action``
#: at package scope and a ``cover`` inside an activity are syntax errors *by the
#: standard*, so accepting them would have been the unsound direction. The
#: corpus files were completed instead (pssparser P7-C1); see "Completing LRM
#: examples" in the corpus's ``PROVENANCE.md``.
#: ``lexical/numbers.pss`` left when ``U-8d`` was **fixed**: pssparser widened
#: the digit portion of every ``BASED_*_LITERAL`` to any alphanumeric/underscore
#: run, so ``16'sH_FF`` lexes. Struck here and in pssparser's table together, as
#: the strict xfail exists to force.
KNOWN_UNPARSEABLE = {
    "lexical/comments_and_strings.pss":
        "U-8e: octal escape in a string literal (\"\\101\")",
    "lexical/operators.pss":
        "U-8b: `dist` constraints. This file also contains deliberately "
        "ungrammatical operator torture (`a = -b` in a constraint), so it may "
        "not reach zero even once U-8b lands -- reclassify then, do not "
        "assume",
}


def ident(path):
    return str(path.relative_to(CORPUS_ROOT)) if CORPUS_ROOT else str(path)


def is_expected_broken(path):
    parts = path.relative_to(CORPUS_ROOT).parts if CORPUS_ROOT else ()
    return any(p in BROKEN_BUCKETS for p in parts)


def read(path):
    # Binary, always. Text mode translates newlines, which would make every
    # assertion in this file pass for the wrong reason.
    return path.read_bytes()


@pytest.fixture(scope="module")
def _report_source():
    return CORPUS_SOURCE


def test_the_corpus_is_present(_report_source):
    # C-8, and the load-bearing test in this file. Every other test here is
    # parametrized over FILES, so an empty corpus makes them all collect zero
    # cases and the suite goes green having checked nothing. This is the one
    # test that cannot vanish with its input.
    assert _report_source != "none", (
        "no PSS corpus found. It is a declared ivpm dependency and should be "
        "at packages/pss-corpus -- run `ivpm update`, or set PSS_CORPUS. This "
        "is a failure and not a skip on purpose: a gate that skips when its "
        "input is missing reports success in exactly the case it exists to "
        "catch.")
    assert len(FILES) >= 50, (
        "%d files from %s -- too few to be the curated corpus"
        % (len(FILES), _report_source))


def test_the_manifest_agrees_with_the_fallback():
    # C-9 leaves two sources of bucket policy: the corpus manifest, and the
    # hardcoded tuple used when there is no manifest to read. Pin them
    # together, or the fallback rots silently and only bites the one
    # configuration nobody runs.
    assert set(BROKEN_BUCKETS) == set(FALLBACK_BROKEN_BUCKETS), (
        "manifest.toml says %s do not parse, the fallback says %s. If a "
        "bucket was genuinely added or reclassified, update "
        "support.FALLBACK_BROKEN_BUCKETS to match."
        % (sorted(BROKEN_BUCKETS), sorted(FALLBACK_BROKEN_BUCKETS)))


def test_the_broken_bucket_actually_exists():
    # A bucket policy that names nothing on disk excludes nothing, and reads
    # as if it excludes something.
    assert CORPUS_ROOT is not None, "no corpus; see test_the_corpus_is_present"
    for bucket in BROKEN_BUCKETS:
        assert (CORPUS_ROOT / bucket).is_dir(), (
            "%r is declared unparseable but is not a directory in the corpus"
            % bucket)


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_round_trips_byte_for_byte(path):
    data = read(path)
    src = data.decode("utf-8")
    result = format_null(src)
    assert result.text == src
    assert result.text.encode("utf-8") == data


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_the_tree_reaches_every_code_token(path):
    # Non-empty means the CST walk stepped past text and the emitter's cursor
    # had to rescue it. Byte-exact either way, but it is a finding about the
    # grammar and it should not pass unremarked.
    assert format_null(read(path).decode("utf-8")).skipped == ()


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_the_trivia_map_partitions_the_stream(path):
    trivia = format_null(read(path).decode("utf-8")).trivia
    assert_partitions_the_stream(trivia, ident(path))


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_the_verifier_accepts_the_null_format(path):
    # The fail-safe must not fire on a formatter that changes nothing. If it
    # does, the verifier is wrong, and a verifier that cries wolf on the null
    # formatter would veto every real format too.
    result = format_safely(read(path).decode("utf-8"))
    assert result.ok, result.diagnostic(ident(path))
    assert not result.changed


def _must_parse():
    """The must-parse files, with the recorded gaps marked xfail-strict."""
    out = []
    for path in FILES:
        if is_expected_broken(path):
            continue
        reason = KNOWN_UNPARSEABLE.get(ident(path).replace("\\", "/"))
        marks = [pytest.mark.xfail(strict=True, reason=reason)] if reason \
            else []
        out.append(pytest.param(path, marks=marks))
    return out


@pytest.mark.parametrize("path", _must_parse(), ids=lambda p: ident(p))
def test_parses_cleanly(path):
    result = format_null(read(path).decode("utf-8"))
    assert result.num_syntax_errors == 0


def test_every_recorded_gap_names_a_file_that_exists():
    # A stale entry is worse than no entry: it silently stops covering a file
    # that was renamed, and reads as if it still does.
    present = {ident(p).replace("\\", "/") for p in FILES}
    assert set(KNOWN_UNPARSEABLE) <= present, (
        "KNOWN_UNPARSEABLE names files that are not in the corpus: %s"
        % sorted(set(KNOWN_UNPARSEABLE) - present))


@pytest.mark.parametrize(
    "path", [p for p in FILES if is_expected_broken(p)], ids=ident)
def test_broken_input_is_still_never_corrupted(path):
    # The bucket that matters most. These files are not required to parse and
    # are required to survive.
    src = read(path).decode("utf-8")
    result = format_safely(src)
    assert result.text == src

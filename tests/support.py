"""Shared assertions, kept out of any one suite because several need them.

Nothing here imports ``pssparser`` or ``pssfmt``: every function takes an
already-built object. That keeps this module importable from ``conftest`` and
from the layout suite, which must collect with pssparser absent (``T-2``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional

__all__ = [
    "walk_partition",
    "assert_partitions_the_stream",
    "corpus_files",
    "broken_buckets",
    "CORPUS_ROOT",
    "CORPUS_REPO",
    "CORPUS_SOURCE",
    "trailing_whitespace_offenders",
    "tab_indent_offenders",
    "lone_brace_offenders",
]


def walk_partition(trivia_map: Any) -> List[Any]:
    """Every token the trivia map accounts for, in the order it accounts."""
    out: List[Any] = []
    for trivia in trivia_map:
        out.extend(trivia.raw_leading)
        if trivia.token is not None:
            out.append(trivia.token)
        out.extend(trivia.raw_trailing)
    return out


def assert_partitions_the_stream(trivia_map: Any, label: str = "") -> None:
    """The invariant ``P1-2`` rests on.

    Every token of the stream appears exactly once in the map, in stream order.
    Stated as a partition rather than as "the text comes out the same", because
    a duplicated token and a dropped one can cancel out in a text comparison
    and cannot cancel out here.
    """
    where = (" in %s" % label) if label else ""
    seen = walk_partition(trivia_map)
    stream = list(trivia_map.stream)

    assert [t.index for t in seen] == list(range(len(stream))), (
        "trivia map is not a partition of the token stream%s: %d tokens "
        "accounted for, %d in the stream" % (where, len(seen), len(stream)))
    assert "".join(t.text for t in seen) == trivia_map.stream.text, (
        "trivia map does not reproduce the source%s" % where)


# ---------------------------------------------------------------------------
# Corpus location -- pss-corpus PLAN.md section 5.1, items C-7 and C-9
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent

#: Where the corpus was found, for diagnostics and for the record.
CORPUS_SOURCE = "none"

#: The corpus *repository* root -- where ``manifest.toml`` lives. Distinct from
#: :data:`CORPUS_ROOT`, which is the subtree being swept. ``None`` when the
#: corpus is a bare directory of ``.pss`` files with no repository around it.
CORPUS_REPO: Optional[Path] = None


def _sweep_root(path: Path) -> Path:
    """The subtree to sweep, given a corpus location.

    ``pss-corpus`` splits ``curated/`` from ``breadth/`` because they carry
    different promises: curated files have recorded provenance and a bucket
    policy, breadth files are bulk input of unknown validity. The contract is
    that a consumer selects between them *with a path* rather than with a
    filter it maintains itself -- so this gate sweeps ``curated/`` and breadth
    material cannot leak into it by arriving.

    Falling back to ``path`` itself is what keeps a bare directory usable:
    ``$PSS_CORPUS`` pointed at a scratch directory of ``.pss`` files, with no
    ``curated/`` and no manifest.
    """
    curated = path / "curated"
    return curated if curated.is_dir() else path


def _find_corpus() -> Optional[Path]:
    """Locates a PSS corpus, in decreasing order of how settled it is.

    The order is the shared contract (``pss-corpus`` ``PLAN.md`` section 5.1),
    duplicated in each consumer rather than shared through a package: it is
    twenty lines, and a package to hold it would add a build, a release cadence
    and a version-skew failure mode to a repository whose whole value is having
    none of those.

    The sibling fallback is the last of the three, and now points at a sibling
    ``pss-corpus`` checkout: ``C-15`` deleted ``pygments-pss/tests/corpus/``, so
    the old target no longer exists in any current checkout. Kept, retargeted,
    because what it buys is unchanged -- a bare working tree stays usable
    without an ``ivpm update``.
    """
    global CORPUS_SOURCE, CORPUS_REPO

    # A rename with a trap in it: silently ignoring an environment variable
    # someone deliberately set is how a sweep ends up running against the wrong
    # files while reporting success. Say so instead. Short-lived -- delete once
    # no working copy still exports the old name.
    if os.environ.get("PSSFMT_CORPUS") and not os.environ.get("PSS_CORPUS"):
        raise RuntimeError(
            "PSSFMT_CORPUS is set but is no longer read: the variable names "
            "the corpus, not the consumer, and three tools each honouring a "
            "differently-spelled variable is the divergence pss-corpus exists "
            "to stop. Export PSS_CORPUS instead.")

    override = os.environ.get("PSS_CORPUS")
    candidates = []
    if override:
        candidates.append(("PSS_CORPUS", Path(override)))
    candidates += [
        ("ivpm", _REPO_ROOT / "packages" / "pss-corpus"),
        ("sibling", _REPO_ROOT.parent / "pss-corpus"),
    ]
    for name, path in candidates:
        if not path.is_dir():
            continue
        root = _sweep_root(path)
        if any(root.rglob("*.pss")):
            CORPUS_SOURCE = "%s (%s)" % (name, root)
            CORPUS_REPO = path if (path / "manifest.toml").is_file() else None
            return root
    return None


CORPUS_ROOT = _find_corpus()


def corpus_files() -> List[Path]:
    """Every ``.pss`` file in the corpus, sorted. Empty when there is none."""
    if CORPUS_ROOT is None:
        return []
    return sorted(CORPUS_ROOT.rglob("*.pss"))


#: Used when the corpus has no ``manifest.toml`` -- a bare ``$PSS_CORPUS``
#: directory of ``.pss`` files, pointed at a scratch tree.
FALLBACK_BROKEN_BUCKETS = ("pathological",)


def broken_buckets() -> tuple:
    """Bucket names whose files are *not* expected to parse.

    Read from the corpus's own ``manifest.toml`` where there is one, so a new
    bucket arrives with its policy attached instead of needing a matching
    commit here. ``test_the_manifest_agrees_with_the_fallback`` pins the two
    together, so the fallback cannot quietly go stale.
    """
    if CORPUS_REPO is None:
        return FALLBACK_BROKEN_BUCKETS
    # `tomllib` is stdlib only from 3.11, and this project supports 3.9. The
    # gap was invisible until the corpus started being fetched in CI (C-9a):
    # with no corpus, CORPUS_REPO is None and this line is never reached, so
    # the 3.9 and 3.10 legs passed by not getting here. That is the same shape
    # as the skip C-8 removed -- a check that holds only while its input is
    # missing -- one level down.
    try:
        import tomllib
    except ModuleNotFoundError:  # Python < 3.11
        import tomli as tomllib
    data = tomllib.loads(
        (CORPUS_REPO / "manifest.toml").read_text(encoding="utf-8"))
    return tuple(sorted(
        name for name, spec in data.get("bucket", {}).items()
        if not spec.get("parses", True)))


# ---------------------------------------------------------------------------
# The style properties, as functions (``P3-8``)
# ---------------------------------------------------------------------------
#
# Shared because they have two callers that need to stay in step, and the
# second one is why they moved here. ``T-20`` runs them over the corpus, where
# no file reaches the interesting case; ``T-27`` runs them over hand-written
# foreign text, which is the only place the *exemption* they take can be
# checked at all. Kept in one place so a change to a gate cannot pass because
# the hostile test still holds the old copy.
#
# Each takes the set of lines ``pssfmt.verbatim.verbatim_lines`` exempted:
# these are claims about gaps the formatter chose, and a line copied out of a
# target-template body has none.


def trailing_whitespace_offenders(out: str, exempt) -> List[int]:
    """``docs/style.rst``: 0 of 4856 corpus lines."""
    return [i for i, line in enumerate(out.splitlines(), 1)
            if line != line.rstrip() and i not in exempt]


def tab_indent_offenders(out: str, exempt) -> List[int]:
    """Also 0 of 4856, and ``use_tabs`` defaults to false."""
    return [i for i, line in enumerate(out.splitlines(), 1)
            if "\t" in line[:len(line) - len(line.lstrip())] and i not in exempt]


def lone_brace_offenders(out: str, exempt) -> List[int]:
    """K&R, 732 of 733. Allman does not occur in the corpus."""
    return [i for i, line in enumerate(out.splitlines(), 1)
            if line.strip() == "{" and i not in exempt]

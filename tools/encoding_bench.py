#!/usr/bin/env python3
"""Measure what encoding detection costs, so the answer is a number.

    python tools/encoding_bench.py [--corpus DIR] [--format]

:mod:`pssfmt.encoding` sits in front of every byte the formatter reads -- source
files, ``.pssfmt``, ``.pssfmtignore`` -- and it does strictly more work than the
``data.decode("utf-8")`` it replaced.  That is a thing worth knowing the size
of before anyone is tempted to optimise it, and worth re-running if the
detection ever grows a third case.

What is actually being compared
-------------------------------
The headline ratio is :func:`pssfmt.encoding.decode` against a bare UTF-8
decode of the same bytes, on the path that is almost every path: UTF-8, no
mark.  That ratio is unflattering and misleading in the same breath, because
the baseline is a SIMD memcpy and *anything* looks slow beside it.  So the
run also decomposes the fast path into its three steps, and -- with
``--format`` -- puts the whole thing next to the cost of actually formatting
the file, which is the only comparison that decides anything.

The decomposition is the useful output.  It separates the two halves of the
work, which have very different costs and very different justifications:

``_by_bom``
    The mark test.  Free, and expected to stay free: :data:`_BOM_FIRST` turns
    five ``startswith`` calls into one membership test for every file that
    begins with a letter.
``"\\x00" not in text``
    A full scan of the decoded string, and in practice the entire overhead.
    It is not incidental -- it is what makes the BOM-less UTF-16 guess
    reachable at all, since ASCII in UTF-16 LE is valid UTF-8 that decodes to
    a string full of NULs.  Removing it would not be an optimisation, it would
    be deleting the feature.

The non-UTF-8 encodings are timed too, mostly to confirm they are unremarkable.
The BOM-less UTF-16 sniff is bounded by :data:`pssfmt.encoding._SNIFF_BYTES`,
so it should not grow with the file; if it ever does, that bound stopped
working.

Reading the output
------------------
Sizes are reached by repeating the corpus, which is kinder to cache than a
genuinely large source file would be.  That flatters the large-input rows, and
it does not matter: the margin the ``--format`` comparison reports is four
orders of magnitude, and no cache effect closes that.
"""

from __future__ import annotations

import sys
import timeit
from pathlib import Path
from typing import Callable, List, Tuple

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from pssfmt import encoding as E  # noqa: E402

#: Repetitions of the corpus, and the labels for them.  The 1x row exists to
#: show the ratio shrinking: at small sizes the fixed cost of a Python call
#: dominates, which is why the overhead looks worst on the smallest input.
_MULTIPLIERS: Tuple[int, ...] = (1, 10, 100)

#: Best-of-N.  The minimum rather than the mean, because a timing is a floor
#: plus noise and the noise is never negative.
_REPEAT = 7


def _best(fn: Callable[[], object], number: int) -> float:
    """Microseconds per call, best of :data:`_REPEAT` runs."""
    return min(timeit.repeat(fn, number=number, repeat=_REPEAT)) / number * 1e6


def _corpus(root: Path) -> str:
    """Every ``.pss`` file under *root*, concatenated."""
    files = sorted(root.rglob("*.pss"))
    if not files:
        raise SystemExit("no .pss files under %s" % root)
    text = "".join(f.read_text(encoding="utf-8") for f in files)
    print("corpus: %d chars from %d files\n" % (len(text), len(files)))
    return text


def _scaling(src: str) -> None:
    """``encoding.decode`` against a bare UTF-8 decode, at three sizes."""
    print("UTF-8, no mark -- the common path")
    print("%-16s %15s %17s %10s"
          % ("size", "baseline", "encoding.decode", "ratio"))
    print("-" * 62)
    for mult in _MULTIPLIERS:
        data = (src * mult).encode("utf-8")
        number = max(1, 2000 // mult)
        base = _best(lambda: data.decode("utf-8"), number)
        ours = _best(lambda: E.decode(data), number)
        print("%-16s %13.1fus %15.1fus %9.2fx"
              % ("%dx (~%dKB)" % (mult, len(data) // 1024), base, ours,
                 ours / base))


def _decompose(src: str) -> None:
    """Where the overhead actually is.  Spoiler: all of it is the NUL scan."""
    text = src * 10
    data = text.encode("utf-8")
    print("\nDecomposing that path (~%dKB):" % (len(data) // 1024))
    for label, fn in (
        ("data.decode('utf-8')", lambda: data.decode("utf-8")),
        ("_by_bom(data)", lambda: E._by_bom(data)),
        ("'\\x00' not in text", lambda: "\x00" not in text),
        ("full encoding.decode", lambda: E.decode(data)),
    ):
        print("  %-24s %9.1fus" % (label, _best(fn, 200)))


def _encodings(src: str) -> None:
    """The paths that are not UTF-8, which should all be unremarkable."""
    text = src * 10
    print("\nOther encodings (same %d chars):" % len(text))
    for label, enc in (
        ("UTF-8 BOM", E.UTF_8_SIG),
        ("UTF-16 LE BOM", E.UTF_16_LE),
        ("UTF-16 BE BOM", E.UTF_16_BE),
        ("UTF-32 LE BOM", E.UTF_32_LE),
        ("UTF-32 BE BOM", E.UTF_32_BE),
    ):
        data = enc.encode(text)
        print("  %-18s %9.1fus  (%d bytes)"
              % (label, _best(lambda: E.decode(data), 200), len(data)))

    # The sniff path.  Timed separately because it is the only one that reads
    # the bytes twice, and the only one whose cost is capped rather than
    # proportional -- _SNIFF_BYTES is what caps it.
    data = text.encode("utf-16-le")
    detected = E.decode(data)[1]
    print("  %-18s %9.1fus  (detected: %s)"
          % ("UTF-16 LE no BOM", _best(lambda: E.decode(data), 200),
             detected.label))


def _against_format(src: str) -> None:
    """Detection next to formatting -- the comparison that settles it.

    Kept behind a flag because it imports the world and takes a second, while
    everything above is self-contained and instant.
    """
    import contextlib
    import io
    import tempfile

    from pssfmt.cli import main

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bench.pss"
        path.write_text(src, encoding="utf-8")

        def run() -> None:
            with contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                try:
                    main([str(path)])
                except SystemExit:
                    pass

        run()  # Warm the import and any per-run memoisation.
        fmt = min(timeit.repeat(run, number=1, repeat=5)) * 1e6

    data = src.encode("utf-8")
    dec = _best(lambda: E.decode(data), 200)
    print("\nAgainst the work it precedes (%d chars):" % len(src))
    print("  %-24s %9.1fms" % ("full CLI format", fmt / 1000))
    print("  %-24s %9.1fus   (%.4f%% of format time)"
          % ("encoding.decode", dec, dec / fmt * 100))


def main(argv: List[str]) -> int:
    root = _ROOT / "tests"
    if "--corpus" in argv:
        root = Path(argv[argv.index("--corpus") + 1])

    src = _corpus(root)
    _scaling(src)
    _decompose(src)
    _encodings(src)
    if "--format" in argv:
        _against_format(src)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

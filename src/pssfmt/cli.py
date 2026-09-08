"""``P4-1`` -- the command line.

::

    pssfmt [-i] [--check] [--diff] [--lines A:B] [--explain] [FILE|DIR ...]

With no ``-i`` and no ``--check``, formatted output goes to stdout, which is
what makes the tool composable and what an editor integration shells out to.
``-i`` rewrites files in place; ``--check`` writes nothing and reports.

Exit codes, which are the actual interface for anything automated:

==== =========================================================================
0    every input was already formatted, or was formatted successfully
1    ``--check`` only: at least one file would change
2    something went wrong -- unreadable file, bad usage, a broken ``.pssfmt``,
     or a file the fail-safe declined
==== =========================================================================

``1`` is reserved for *"the answer is no"* and never used for *"I could not
compute the answer"*, because the two call for opposite responses in CI: one
is a pull request that needs formatting, the other is a broken toolchain.
Conflating them is how a CI job starts reporting style failures for a
missing-dependency error. A malformed configuration file is squarely the
second kind, however tempting it is to treat "cannot read the style" as
"nothing to say about the style".

What gets formatted, and how
----------------------------
Two questions, two files, and they are answered in different modules for
reasons each explains at length: :mod:`pssfmt.config` resolves *how* (a
``.pssfmt`` or a ``[tool.pssfmt]`` table, the first one found on the way up),
and :mod:`pssfmt.ignore` resolves *what* (``.pssfmtignore``, gitignore
syntax, every file on the way up stacking). ``--lines`` answers *what* a
third time and at a finer grain, in :mod:`pssfmt.ranges`.

Both are resolved **per input file** rather than once per run. A monorepo with
two projects in it has two answers, and choosing one for the whole invocation
would make the result depend on which directory the user happened to type.

The fail-safe is an error, not a diff
-------------------------------------
When :func:`pssfmt.verify.format_safely` rejects an output the file is left
alone -- so under ``--check`` it looks exactly like a clean file, and under
``-i`` it looks exactly like a formatted one. Neither is what happened. A
declined file means the formatter produced output that would have changed the
program, which is a ``pssfmt`` bug the user should hear about immediately and
loudly, so it exits ``2`` and prints the verifier's diagnostic in every mode.

What is deliberately absent
---------------------------
There is no ``pssparser format`` subcommand and there will not be one. It
would make the parser depend on the formatter, inverting the direction the
whole repository layout rests on: the formatter is a consumer of the parser's
CST, and a parser that ships a formatter cannot be released without one.
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, TextIO, Tuple

from .__version__ import __version__
from .config import ConfigError, Resolver
from .encoding import UTF_8, Encoding
from .encoding import decode as decode_bytes
from .explain import explain, report
from .ignore import IgnoreSet, load_ignores
from .ranges import LineRange, RangeError, parse_ranges, restrict
from .rules import format_source
from .style import DEFAULT_STYLE, Style
from .verify import SafeResult, Violation, format_safely, verify

__all__ = ["main"]

#: The extension a directory walk collects. A single suffix rather than a
#: configurable list: ``.pss`` is what the standard names, and a formatter
#: that has to be told which files are its own is one that will eventually be
#: pointed at somebody's Verilog.
SUFFIX = ".pss"

#: What to say when the bytes are not text in any encoding we recognise.
#: It names the encodings that *were* tried, because "not valid UTF-8" sends
#: a user with a perfectly good UTF-16 file looking for a corruption that is
#: not there -- and since :mod:`pssfmt.encoding` now reads those files, a
#: message that still only mentions UTF-8 would be describing an older tool.
UNDECODABLE = "cannot decode: not UTF-8, UTF-16, or UTF-32"

#: Directories a walk never descends into.
#:
#: Deliberately short, and deliberately not a place to put anything
#: project-specific. It held ``packages`` for an afternoon -- where *this*
#: repository's dependency checkout lives -- which would have silently skipped
#: a directory of real PSS in anybody else's tree. A walk that quietly omits
#: files is the worst kind of wrong for a ``--check`` gate, because the
#: symptom is a green run.
#:
#: Everything beyond machine-generated and version-control directories belongs
#: in ``.pssfmtignore`` (``P4-3``, :mod:`pssfmt.ignore`), where the user can
#: see it and change it. That file now exists, and this set has still not
#: grown -- which is the test of whether the rule was real.
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", ".tox", ".venv",
             "node_modules"}

OK, WOULD_CHANGE, ERROR = 0, 1, 2

STDIN = "-"


# ---------------------------------------------------------------------------
# Discovering what to format
# ---------------------------------------------------------------------------

def collect(paths: Sequence[str]) -> Tuple[List[Path], List[str]]:
    """Expand *paths* into files to format, plus a list of complaints.

    A named file is formatted whatever it is called; only a *walk* filters by
    suffix. Someone who types the path of a file means that file, and
    silently skipping it because it is called ``foo.pss.in`` is the kind of
    no-op that gets diagnosed as "the formatter is broken".

    ``.pssfmtignore`` follows that same rule, and it is worth being explicit
    because git makes the same call: **ignore patterns filter a walk and never
    a named file.** Both directions lose something. Honouring ignores for
    named files makes ``pssfmt -i generated/thing.pss`` a silent no-op, which
    is the diagnosis above verbatim; not honouring them means a hook invoked
    as ``pssfmt $(git ls-files)`` reformats files the project excluded. Git
    resolves the second with ``--force-exclude``-style opt-in, and so should
    ``P4-7`` when the hook lands; until then the rule matches the one already
    written down for suffixes, which is worth more than either behaviour on
    its own.
    """
    files: List[Path] = []
    errors: List[str] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(walk(path))
        elif path.exists():
            files.append(path)
        else:
            errors.append("%s: no such file or directory" % raw)
    return files, errors


def walk(root: Path) -> List[Path]:
    """Every ``*.pss`` under *root*, sorted, minus what is ignored.

    Sorted so that output order is a property of the tree rather than of the
    filesystem, which is what makes ``--diff`` reviewable and ``--check``
    reproducible across machines.

    Ignored *directories* are pruned rather than filtered file by file. That
    is git's semantics rather than an optimisation: pruning is what makes a
    ``!`` pattern unable to re-include a file out of an excluded directory,
    so this walk and ``git check-ignore`` agree instead of nearly agreeing.
    """
    root = Path(root)
    found: List[Path] = []
    # Every ignore file from the version-control root down to `root` is in
    # force before the walk starts; the ones *inside* the tree are picked up
    # as it descends, each applying to its own subtree.
    # Keyed with `os.path.join` and never with `str(Path(...) / name)`: the
    # two disagree for a relative root, since `os.walk(".")` yields
    # `./sub` where `Path(".") / "sub"` stringifies as `sub`. A miss here is
    # silent -- the subtree just proceeds with no ignore rules at all -- and
    # `.` is the commonest way anyone runs this, so the bug was invisible to
    # every test using an absolute `tmp_path`.
    active: Dict[str, IgnoreSet] = {os.fspath(root): load_ignores(root)}
    for dirpath, dirnames, filenames in os.walk(root):
        here = active.pop(dirpath, IgnoreSet())
        kept = []
        for name in sorted(dirnames):
            if name in SKIP_DIRS or name.startswith("."):
                continue
            child = os.path.join(dirpath, name)
            if here.decide(Path(child), True):
                continue
            kept.append(name)
            active[child] = here.extend(Path(child))
        dirnames[:] = kept
        for name in sorted(filenames):
            if not name.endswith(SUFFIX):
                continue
            path = Path(os.path.join(dirpath, name))
            if not here.decide(path, False):
                found.append(path)
    return found


# ---------------------------------------------------------------------------
# Formatting one thing
# ---------------------------------------------------------------------------

def run_format(source: str, style: Style) -> SafeResult:
    """The single call every mode goes through.

    Every path in this module formats via :func:`~pssfmt.verify.format_safely`
    and none reaches :func:`~pssfmt.rules.format_source` directly. That is not
    style: the fail-safe is the only thing standing between a rule bug and a
    damaged file, and a mode that skipped it -- ``--diff``, say, on the
    argument that it writes nothing -- would print a diff of output too broken
    to write, which is worse than not printing one.
    """
    return format_safely(
        source, formatter=lambda s: format_source(s, style=style),
        allow_dropped_semicolons=style.drops_optional_semicolons(),
        allow_added_semicolons=style.adds_optional_semicolons())


def apply_ranges(source: str, result: SafeResult,
                 ranges: Sequence[LineRange],
                 style: Style = DEFAULT_STYLE) -> SafeResult:
    """Keep the parts of a successful format that *ranges* asked for.

    Verified again, and not because :func:`pssfmt.ranges.restrict` is
    suspected: it is sound by construction and there is a test to that effect.
    Splicing is simply a *new place output is produced*, and this repository's
    one recurring bug -- the token-spacing floor, the file's copied tail --
    has been an invariant enforced at every production site but one. Nothing
    about a whitespace-only edit makes a file still parse, either: ``//`` runs
    to the end of a line, so "only whitespace changed" and "the program is
    unchanged" are different claims and only the second one matters.
    """
    try:
        text = restrict(source, result.text, ranges,
                        style.rewrites_optional_semicolons())
    except RangeError as exc:
        violations: Tuple[Violation, ...] = (Violation("range", str(exc)),)
        text = result.text
    else:
        violations = verify(
            source, text,
            allow_dropped_semicolons=style.drops_optional_semicolons(),
            allow_added_semicolons=style.adds_optional_semicolons())
        if not violations:
            return SafeResult(text=text, ok=True, _original=source)
    return SafeResult(text=source, ok=False, violations=violations,
                      rejected=text, _original=source)


def unified(before: str, after: str, path: str) -> str:
    """A ``patch -p0``-applicable diff, or ``""`` when there is no change."""
    diff = difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=path, tofile=path,
        fromfiledate="original", tofiledate="formatted", n=3)
    return "".join(diff)


def write_atomically(path: Path, text: str,
                     encoding: Encoding = UTF_8) -> None:
    """Replace *path*'s contents, never leaving a partial file behind.

    Write a sibling temporary and rename over the target: a crash, a full
    disk, or a ``SIGKILL`` mid-write then leaves either the old file or the
    new one, and never a truncated one. ``open(path, "w")`` truncates first,
    so the window where the user's source code does not exist is however long
    the write takes -- small, and the file is unrecoverable if it is unlucky.

    The temporary is a *sibling* rather than in the system temp directory
    because :func:`os.replace` is only atomic within a filesystem, and
    ``/tmp`` routinely is not the same one.

    *encoding* is the one the file was **read** in, not a preference: see
    :mod:`pssfmt.encoding`. A UTF-16 file stays UTF-16, mark and byte order
    intact, because re-encoding a file the user did not ask to have re-encoded
    is a change that does not show up in the diff they read.
    """
    directory = path.parent if str(path.parent) else Path(".")
    fd, tmp = tempfile.mkstemp(dir=str(directory), prefix=".pssfmt-",
                               suffix=SUFFIX)
    try:
        # Binary, and the encoding applied by hand. Text mode would do the
        # encoding but would also translate newlines, and `newline=""` turns
        # that off only for the codecs where a `\n` is one byte. On POSIX the
        # translation is a no-op -- text mode substitutes `os.linesep`, which
        # is already `\n` -- so no test on this platform could distinguish it,
        # and the mutation run says so honestly rather than being worked
        # around. On Windows it is the difference between `line_ending: lf`
        # working and every emitted `\n` silently becoming `\r\n` on the way
        # to the disk, which would make the whole of `pssfmt.finish`
        # unobservable there.
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoding.encode(text))
        # Carry the original's permissions over; mkstemp creates 0600, so
        # without this an in-place format quietly makes a file private.
        try:
            os.chmod(tmp, os.stat(str(path)).st_mode & 0o7777)
        except OSError:
            pass
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_text(path: Path) -> Tuple[str, Encoding]:
    """The file's text, and the encoding to write it back in.

    Read as *bytes* and decoded here rather than opened in text mode, for two
    reasons that pull the same way. Text mode turns ``\\r\\n`` into ``\\n`` on
    read, which would make every CRLF file look like an LF file and hand
    ``line_ending: auto`` the wrong answer for the one setting it exists to
    serve. And it would have to be told an encoding up front, when the whole
    point is that the bytes say which one it is (:mod:`pssfmt.encoding`).
    """
    return decode_bytes(path.read_bytes())


def write_stream(stream: TextIO, text: str, encoding: Encoding) -> None:
    """Write formatted source to *stream* in the encoding it came in.

    For the ordinary UTF-8 input this is a plain ``stream.write`` and nothing
    is different. For a UTF-16 input it goes to the stream's underlying binary
    buffer instead, so that ``pssfmt file.pss > out.pss`` and an editor
    driving ``pssfmt -`` both get back a file in the encoding they supplied,
    rather than one transcoded to whatever the process's stdout happens to be.
    That is the same promise ``-i`` makes, kept in the mode where the caller
    -- not ``pssfmt`` -- owns the destination.

    A stream with no ``buffer`` (a ``StringIO``, which is what the tests pass,
    and a captured stdout under some runners) takes the text as text. There is
    no byte layer to write to, so preserving bytes is not on the table.
    """
    buffer = getattr(stream, "buffer", None) if not encoding.is_utf8 else None
    if buffer is None:
        stream.write(text)
        return
    # Anything already buffered on the text layer must land first, or the
    # bytes written below overtake it.
    stream.flush()
    buffer.write(encoding.encode(text))
    buffer.flush()


def read_stdin(stdin: TextIO) -> Tuple[str, Encoding]:
    """Standard input, decoded the same way a named file is.

    Read through ``stdin.buffer`` when there is one, because ``sys.stdin``
    would otherwise decode with the *locale* encoding -- on Windows a legacy
    code page, which turns piped UTF-16 into mojibake without ever raising.
    Silent corruption is worse than the error it replaces.
    """
    buffer = getattr(stdin, "buffer", None)
    if buffer is None:
        return stdin.read(), UTF_8
    return decode_bytes(buffer.read())


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

class Reporter:
    """Where messages go, and the tally at the end.

    stdout carries *output* -- formatted text, diffs -- and stderr carries
    everything about the run. Mixing them means ``pssfmt file.pss > out.pss``
    writes a warning into the user's source file.
    """

    def __init__(self, out: TextIO, err: TextIO, quiet: bool = False) -> None:
        self.out = out
        self.err = err
        self.quiet = quiet
        self.changed: List[str] = []
        self.unchanged: List[str] = []
        self.failed: List[str] = []

    def note(self, message: str) -> None:
        if not self.quiet:
            print(message, file=self.err)

    def error(self, message: str) -> None:
        print("pssfmt: %s" % message, file=self.err)

    def summary(self, wrote_files: bool) -> None:
        """The tally, on stderr.

        Silent when nothing changed and nothing failed, so a clean ``--check``
        in CI produces no output at all. The verb turns on whether files were
        actually written and not on which flag was passed: ``--diff`` and the
        default stdout mode both leave every file on disk exactly as it was,
        and reporting "1 file reformatted" for either is a false statement
        about the user's working tree.
        """
        if self.quiet or not (self.changed or self.failed):
            return
        verb = "reformatted" if wrote_files else "would be reformatted"
        parts = []
        if self.changed:
            parts.append("%s %s" % (_count(len(self.changed), "file"), verb))
        if self.unchanged:
            parts.append("%s left unchanged" % _count(len(self.unchanged), "file"))
        if self.failed:
            parts.append("%s declined" % _count(len(self.failed), "file"))
        print(", ".join(parts), file=self.err)


def _count(n: int, noun: str) -> str:
    return "%d %s%s" % (n, noun, "" if n == 1 else "s")


def explain_one(source: str, name: str, style: Style,
                reporter: Reporter, tree: bool) -> int:
    """``--explain`` for one input.

    Does not go through :func:`run_format`, and that is the point rather than
    an oversight: ``--explain`` exists for the case where the output is wrong,
    which is exactly when the fail-safe may be about to reject it. A mode that
    refused to explain a file the verifier dislikes would be missing from the
    one situation it was built for. The violations are reported inside the
    explanation instead.
    """
    try:
        exp = explain(source, style=style, name=name)
    except BaseException as exc:  # noqa: BLE001 -- a debugging aid may not
        # become the thing that needs debugging. Anything the formatter can
        # raise, it can raise here too, and the useful response is to say so.
        reporter.error("%s: could not explain: %s: %s"
                       % (name, type(exc).__name__, exc))
        return ERROR
    reporter.out.write(report(exp, tree=tree))
    return OK


def process(source: str, name: str, args, style: Style,
            reporter: Reporter,
            ranges: Sequence[LineRange] = (),
            encoding: Encoding = UTF_8) -> int:
    """Format one input and act on the result. Returns an exit code.

    *encoding* is what the input was decoded from, and every path that emits
    the *source* -- stdout, ``-i`` -- puts it back in that encoding. The diff
    and the messages are not source: they are this run talking to the user,
    and they go out as text on the ordinary streams.
    """
    if args.explain or args.explain_tree:
        return explain_one(source, name, style, reporter, args.explain_tree)

    result = run_format(source, style)
    if result.ok and ranges:
        result = apply_ranges(source, result, ranges, style)

    if not result.ok:
        # Printed in every mode, including --check, because a declined file
        # is indistinguishable from a clean one by its output alone.
        print(result.diagnostic(name), file=reporter.err)
        reporter.failed.append(name)
        # ...and in stdout mode the input is still written out, which is the
        # single most important line in this file. `pssfmt f.pss > new.pss`
        # is a normal way to run a formatter, and stdout is *already* the
        # truncated destination by the time this code runs. Emitting nothing
        # here does not decline to modify the file -- it empties it. The
        # fail-safe's whole promise is that a rejected format hands back the
        # input, and `result.text` is that input.
        if not (args.check or args.in_place or args.diff):
            write_stream(reporter.out, result.text, encoding)
        return ERROR

    if result.text == source:
        reporter.unchanged.append(name)
        if args.diff:
            return OK
        if not (args.check or args.in_place):
            write_stream(reporter.out, result.text, encoding)
        return OK

    reporter.changed.append(name)

    if args.diff:
        reporter.out.write(unified(source, result.text, name))
    if args.check:
        return WOULD_CHANGE
    if args.in_place:
        write_atomically(Path(name), result.text, encoding)
        reporter.note("reformatted %s" % name)
    elif not args.diff:
        write_stream(reporter.out, result.text, encoding)
    return OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pssfmt",
        description="Format Accellera PSS source.",
        epilog="With no FILE, or with -, reads stdin and writes stdout.")
    parser.add_argument("files", nargs="*", metavar="FILE",
                        help="files or directories; directories are searched "
                             "for *%s" % SUFFIX)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("-i", "--in-place", action="store_true",
                      help="rewrite files in place")
    mode.add_argument("--check", action="store_true",
                      help="write nothing; exit 1 if any file would change")
    mode.add_argument("--explain", action="store_true",
                      help="describe how the output was produced; write "
                           "nothing")
    parser.add_argument("--explain-tree", action="store_true",
                        help="with --explain, also print the Layout IR")
    parser.add_argument("--diff", action="store_true",
                        help="print a unified diff of the changes")
    parser.add_argument("--lines", metavar="A:B", action="append",
                        help="format only lines A through B of one file "
                             "(1-based, inclusive; repeatable)")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="suppress the per-file and summary notes")
    parser.add_argument("--version", action="version",
                        version="pssfmt %s" % __version__)
    return parser


def main(argv: Optional[Sequence[str]] = None,
         stdin: Optional[TextIO] = None,
         stdout: Optional[TextIO] = None,
         stderr: Optional[TextIO] = None) -> int:
    """Entry point. Returns an exit code rather than calling :func:`sys.exit`.

    The three streams are parameters so that the tests drive the real entry
    point instead of a testable copy of it. A CLI whose tests exercise a
    parallel implementation checks the part nobody runs.
    """
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr

    args = build_parser().parse_args(argv)
    reporter = Reporter(stdout, stderr, quiet=args.quiet)

    if args.explain or args.explain_tree:
        # A report, not a formatting run. Refused rather than given a meaning
        # for each combination: "explain what --lines would have done" and
        # "explain and also write the file" are both defensible readings, and
        # picking one silently is how a flag acquires a behaviour nobody
        # chose. `-i` and `--check` are already refused by the mode group.
        clashing = [flag for flag, on in (("-i", args.in_place),
                                          ("--check", args.check),
                                          ("--diff", args.diff),
                                          ("--lines", bool(args.lines)))
                    if on]
        if clashing:
            reporter.error("--explain writes nothing and formats nothing; it "
                           "cannot be combined with %s" % ", ".join(clashing))
            return ERROR

    ranges: Tuple[LineRange, ...] = ()
    if args.lines:
        try:
            ranges = parse_ranges(args.lines)
        except RangeError as exc:
            reporter.error("--lines: %s" % exc)
            return ERROR
        # Line numbers are meaningless across several inputs, and guessing
        # which one they meant is worse than asking. Refused on the
        # *arguments* rather than on what they expand to, so that a directory
        # that happens to hold one file gives the same answer as one that
        # holds two.
        if len(args.files) > 1 or any(Path(f).is_dir() for f in args.files):
            reporter.error("--lines takes one file, or stdin; line numbers "
                           "do not mean anything across several files")
            return ERROR

    # Resolution is per *file*, not per run: a monorepo with two projects in
    # it has two answers, and picking one of them for the whole invocation
    # would make the result depend on which directory the user typed.
    resolver = Resolver()

    use_stdin = not args.files or args.files == [STDIN]
    if use_stdin:
        if args.in_place:
            reporter.error("-i needs a file to rewrite; stdin has no name")
            return ERROR
        # Standard input has no path, so discovery starts from the working
        # directory. That is the only available answer and it is a defensible
        # one -- an editor shelling out to `pssfmt -` runs it in the project.
        try:
            style = resolver.for_directory(Path(".")).style
        except ConfigError as exc:
            reporter.error(str(exc))
            return ERROR
        try:
            text, encoding = read_stdin(stdin)
        except UnicodeDecodeError:
            reporter.error("<stdin>: %s" % UNDECODABLE)
            return ERROR
        return process(text, "<stdin>", args, style, reporter, ranges,
                       encoding)

    if STDIN in args.files:
        reporter.error("cannot mix - with named files")
        return ERROR

    files, errors = collect(args.files)
    for message in errors:
        reporter.error(message)
    status = ERROR if errors else OK

    if not files and not errors:
        reporter.note("no %s files found" % SUFFIX)

    complained: Set[Path] = set()
    for path in files:
        name = str(path)
        try:
            style = resolver.for_path(path).style
        except ConfigError as exc:
            # Reported once per configuration file rather than once per file
            # it governs: a broken `.pssfmt` above a thousand `.pss` files is
            # one problem, and printing it a thousand times buries every other
            # message in the run.
            if exc.path not in complained:
                complained.add(exc.path)
                reporter.error(str(exc))
            # The file is *skipped*, not formatted with the defaults. Falling
            # back would format it to a style the user did not ask for and did
            # not get told about, which is the failure this whole module is
            # organised against.
            status = ERROR
            continue

        try:
            source, encoding = read_text(path)
        except OSError as exc:
            reporter.error("%s: %s" % (name, exc.strerror or exc))
            status = ERROR
            continue
        except UnicodeDecodeError:
            reporter.error("%s: %s" % (name, UNDECODABLE))
            status = ERROR
            continue

        code = process(source, name, args, style, reporter, ranges, encoding)
        # ERROR outranks WOULD_CHANGE: a run that both found a diff and hit a
        # broken file must not report the milder of the two.
        if code == ERROR or status == ERROR:
            status = ERROR
        elif code == WOULD_CHANGE:
            status = WOULD_CHANGE

    reporter.summary(args.in_place)
    return status


def run() -> None:
    """``console_scripts`` entry point."""
    sys.exit(main())


if __name__ == "__main__":
    run()

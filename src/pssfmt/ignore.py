"""``P4-3`` -- ``.pssfmtignore``, and every "should the walk skip this?"
question.

``P4-1`` left :data:`pssfmt.cli.SKIP_DIRS` as a four-entry list of
version-control and machine-generated directories, and deliberately refused to
grow it. It briefly held ``packages``, this repository's dependency checkout,
which would have silently skipped a directory of real PSS in anybody else's
tree. That is the worst failure mode a ``--check`` gate has, because the
symptom is a *green* run: a walk that quietly omits files makes the gate
greener rather than redder, and nothing in the output says a file was never
looked at.

So the answer to "skip this?" lives in a file the user writes, can read back,
and can commit -- which is what makes the omission visible and reviewable.

Gitignore syntax, and why not a simpler one
-------------------------------------------
Anyone who would write this file has written a ``.gitignore``, and a syntax
that is *almost* gitignore is worse than either a different one or the same
one: the failure mode is a pattern that means something subtly different from
what its author has been reading for a decade. So the semantics here are
git's, including the parts that are easy to get wrong and tempting to drop:

* the last matching pattern decides, which is what makes ``!`` re-inclusion
  work at all;
* a pattern with no ``/`` in it matches at **any depth**; one with a ``/``
  is anchored to the directory of the file it was written in;
* a trailing ``/`` matches directories only;
* ``*`` and ``?`` do not cross ``/``; ``**`` does;
* nested ``.pssfmtignore`` files apply to their own subtree, and the deeper
  file wins.

One git rule is kept that looks like an optimisation and is not: **an excluded
directory is not descended into, so a pattern cannot re-include a file inside
one.** Implementing it as pruning rather than as a per-file test is what makes
this module agree with ``git check-ignore`` instead of *nearly* agreeing.

Ignore files stack; configuration does not
-------------------------------------------
:mod:`pssfmt.config` stops at the first ``.pssfmt`` it finds. Every
``.pssfmtignore`` from the walk root up to the version-control root applies,
and so does every one inside the tree. The asymmetry is deliberate.

A configuration is a set of *values*, and merging them makes "which file set
this?" a question the user cannot answer by reading. An ignore file is a set
of *rules*, which compose by construction -- ``!`` exists precisely so an
inner file can overrule an outer one -- and refusing to stack them would mean
a ``.pssfmtignore`` in a subdirectory silently disabled the repository's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import List, Optional, Tuple

from .encoding import decode as decode_bytes

__all__ = ["IGNORE_NAME", "Rule", "Patterns", "IgnoreSet", "compile_pattern",
           "read_ignore_file", "load_ignores"]

IGNORE_NAME = ".pssfmtignore"

#: Directories whose presence ends the upward search for ignore files. Same
#: boundary as :mod:`pssfmt.config`, and for the same reason: a rule outside
#: the repository is one nobody can see in the tree.
VCS_MARKERS = (".git", ".hg", ".svn")


@dataclass(frozen=True)
class Rule:
    """One pattern line, compiled.

    *source* and *line* are carried so a future ``--explain`` (``P4-5``) can
    answer "why was this file skipped?" with the pattern that skipped it,
    which is the only question anybody asks about an ignore file.
    """

    pattern: str
    regex: "re.Pattern[str]"
    negated: bool
    dir_only: bool
    source: Optional[Path] = None
    line: int = 0

    def matches(self, relative: str, is_dir: bool) -> bool:
        if self.dir_only and not is_dir:
            return False
        return self.regex.fullmatch(relative) is not None


def compile_pattern(pattern: str, source: Optional[Path] = None,
                    line: int = 0) -> Optional[Rule]:
    """Compile one line of a ``.pssfmtignore``, or ``None`` if it is not one.

    ``None`` means a blank line or a comment. Everything else compiles,
    including a pattern that can never match anything -- refusing to parse a
    valid-looking line would be a worse failure than a rule that is simply
    never used.
    """
    text = _strip_trailing_space(pattern)
    if not text or text.startswith("#"):
        return None

    negated = text.startswith("!")
    if negated:
        text = text[1:]
    elif text.startswith("\\#") or text.startswith("\\!"):
        # `\#` and `\!` are literal. Only meaningful in the first position,
        # which is why this is here and not in the segment translator.
        text = text[1:]

    dir_only = text.endswith("/") and not text.endswith("\\/")
    if dir_only:
        text = text[:-1]
    if not text:
        return None

    anchored = "/" in text
    if text.startswith("/"):
        text = text[1:]

    body = _translate(text)
    prefix = "" if anchored else r"(?:.*/)?"
    return Rule(pattern=pattern, regex=re.compile(prefix + body),
                negated=negated, dir_only=dir_only, source=source, line=line)


def _strip_trailing_space(text: str) -> str:
    """Drop trailing spaces, unless the last one is backslash-escaped.

    Git's rule, and it exists because trailing whitespace in a config file is
    almost always accidental -- but ``foo\\ `` is how somebody writes a name
    that really does end in a space, and silently mangling it would make that
    file unignorable.
    """
    end = len(text)
    while end > 0 and text[end - 1] in " \t":
        backslashes = 0
        index = end - 2
        while index >= 0 and text[index] == "\\":
            backslashes += 1
            index -= 1
        if backslashes % 2:
            break
        end -= 1
    return text[:end]


def _translate(pattern: str) -> str:
    """A gitignore pattern as a regex over a ``/``-separated relative path."""
    parts = pattern.split("/")
    out: List[str] = []
    last = len(parts) - 1
    index = 0
    while index <= last:
        segment = parts[index]
        if segment == "**":
            if index == last:
                # `a/**` -- everything inside `a`, at any depth.
                out.append(".*")
            else:
                # `**/b` and `a/**/b` -- zero or more intervening segments, so
                # `a/**/b` matches `a/b` as well as `a/x/y/b`. Appending the
                # separator here is why the loop continues rather than falling
                # through to the shared one below.
                out.append(r"(?:[^/]+/)*")
                index += 1
                continue
        else:
            out.append(_segment(segment))
        if index != last:
            out.append("/")
        index += 1
    return "".join(out)


def _segment(segment: str) -> str:
    """One path segment as a regex. ``*`` and ``?`` never cross a ``/``."""
    out: List[str] = []
    index = 0
    length = len(segment)
    while index < length:
        char = segment[index]
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "\\" and index + 1 < length:
            out.append(re.escape(segment[index + 1]))
            index += 2
            continue
        elif char == "[":
            closing = _class_end(segment, index)
            if closing is None:
                out.append(re.escape(char))
            else:
                out.append(_char_class(segment[index + 1:closing]))
                index = closing + 1
                continue
        else:
            out.append(re.escape(char))
        index += 1
    return "".join(out)


def _class_end(segment: str, start: int) -> Optional[int]:
    """Index of the ``]`` closing the class opened at *start*, or ``None``.

    A ``]`` immediately after the opening bracket (or after its negation) is
    a literal member rather than the terminator -- ``[]]`` is the class
    containing ``]``.
    """
    index = start + 1
    if index < len(segment) and segment[index] in "!^":
        index += 1
    if index < len(segment) and segment[index] == "]":
        index += 1
    while index < len(segment):
        if segment[index] == "]":
            return index
        index += 1
    return None


def _char_class(body: str) -> str:
    if body.startswith("!"):
        body = "^" + body[1:]
    # The body is passed through untouched apart from the negation spelling.
    # Rewriting backslashes inside it would break `[a\-z]`, and the class
    # cannot introduce a regex construct: `[` ... `]` is inert.
    #
    # The lookahead is not cosmetic. A negated class matches anything it does
    # not list, `/` included, so `[!x]*` in an unanchored pattern would reach
    # across a directory boundary -- the one thing every wildcard here is
    # supposed not to do.
    return "(?![/])[%s]" % body


@dataclass(frozen=True)
class Patterns:
    """The rules from one ``.pssfmtignore``, and the directory they apply to."""

    base: Path
    rules: Tuple[Rule, ...]

    def decide(self, path: Path, is_dir: bool) -> Optional[bool]:
        """``True`` ignored, ``False`` re-included, ``None`` no opinion.

        The last matching rule decides, which is the whole reason ``!`` works.
        """
        relative = _relative(path, self.base)
        if relative is None:
            return None
        verdict: Optional[bool] = None
        for rule in self.rules:
            if rule.matches(relative, is_dir):
                verdict = not rule.negated
        return verdict


def _relative(path: Path, base: Path) -> Optional[str]:
    """*path* relative to *base* in POSIX form, or ``None`` if it is outside."""
    try:
        relative = Path(path).resolve().relative_to(Path(base).resolve())
    except ValueError:
        return None
    text = PurePosixPath(*relative.parts).as_posix()
    return None if text == "." else text


@dataclass(frozen=True)
class IgnoreSet:
    """Every ``.pssfmtignore`` in effect, outermost first.

    Ordering is the whole content of the type: a deeper file's verdict wins
    over a shallower one's, so ``sources`` is kept in the order they were
    discovered and consulted in that order.
    """

    sources: Tuple[Patterns, ...] = ()

    def decide(self, path: Path, is_dir: bool) -> Optional[bool]:
        verdict: Optional[bool] = None
        for patterns in self.sources:
            answer = patterns.decide(path, is_dir)
            if answer is not None:
                verdict = answer
        return verdict

    def ignores(self, path: Path, is_dir: bool = False) -> bool:
        """Whether *path* is ignored, counting its ancestors.

        The ancestor walk is what implements git's rule that an excluded
        directory cannot have a file re-included from inside it. The directory
        walk gets the same answer by pruning -- cheaper, and the reason this
        method exists anyway is that a caller holding a single path (a name on
        the command line, an editor's open buffer) has no walk to prune.
        """
        if self.decide(path, is_dir):
            return True
        if not self.sources:
            return False
        # Stop once the ancestors climb above the outermost ignore file: no
        # rule can have anything to say about a directory none of them covers.
        outermost = min((len(Path(p.base).resolve().parts)
                         for p in self.sources))
        for parent in Path(path).resolve().parents:
            if len(parent.parts) < outermost:
                break
            if self.decide(parent, True):
                return True
        return False

    def extend(self, directory: Path) -> "IgnoreSet":
        """This set plus *directory*'s own ignore file, if it has one."""
        found = read_ignore_file(Path(directory) / IGNORE_NAME)
        return self if found is None else IgnoreSet(self.sources + (found,))


def read_ignore_file(path: Path) -> Optional[Patterns]:
    """Compile *path*, or ``None`` if it does not exist.

    An unreadable file is treated as absent rather than raising, and that is
    a deliberate asymmetry with :mod:`pssfmt.config`: a broken *config*
    changes how files are formatted, so it must stop the run, while a missing
    ignore file can only cause more files to be looked at. Erring toward
    formatting more is the safe direction -- the fail-safe still stands behind
    every one of them.
    """
    try:
        # Bytes and an explicit decode, matching source files and `.pssfmt`:
        # a `.pssfmtignore` saved as UTF-16 by a Windows editor would
        # otherwise be treated as unreadable, which here means "ignores
        # nothing" -- a silent failure that formats files the user excluded.
        text = decode_bytes(Path(path).read_bytes())[0]
    except (OSError, UnicodeDecodeError):
        return None
    rules = []
    for number, line in enumerate(text.splitlines(), start=1):
        rule = compile_pattern(line, source=Path(path), line=number)
        if rule is not None:
            rules.append(rule)
    return Patterns(base=Path(path).parent, rules=tuple(rules))


def load_ignores(start: Path) -> IgnoreSet:
    """Every ignore file from the version-control root down to *start*.

    Outermost first, so a nearer file overrules a further one. Unlike
    :func:`pssfmt.config.find_config` this does not stop at the first hit --
    see the module docstring on why rules stack and values do not.
    """
    directory = Path(start).resolve()
    chain: List[Path] = [directory]
    for parent in directory.parents:
        if _has_vcs(chain[-1]):
            break
        chain.append(parent)
    found: List[Patterns] = []
    for candidate in reversed(chain):
        patterns = read_ignore_file(candidate / IGNORE_NAME)
        if patterns is not None:
            found.append(patterns)
    return IgnoreSet(tuple(found))


def _has_vcs(directory: Path) -> bool:
    return any((directory / marker).exists() for marker in VCS_MARKERS)

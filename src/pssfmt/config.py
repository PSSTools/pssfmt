"""``P4-2`` -- where a :class:`~pssfmt.style.Style` comes from.

A ``.pssfmt`` file, or a ``[tool.pssfmt]`` table in ``pyproject.toml``,
discovered by walking up from each input file. Thirteen keys -- the twelve of
``PLAN.md`` section 6.7 plus ``optional_semicolon``, added when the trailing
``;`` after a declaration became a style rather than a fixed behaviour --
every one of them optional, and anything not mentioned keeps the measured
default.

TOML, not YAML
--------------
Section 6.7 sketches the option set as YAML. It is read as TOML here, and the
deviation is deliberate rather than an oversight.

The ``pyproject.toml`` half of this item is not optional -- it is where a
Python-adjacent project expects tool configuration to live -- so a TOML reader
has to exist either way. Supporting YAML *as well* would mean two parsers, two
type systems and two sets of error messages for one option set, and the two
type systems genuinely differ: YAML reads ``no`` as a boolean and ``~`` as
null, so ``line_ending: no`` is a boolean in one file and the string ``"no"``
in the other. It would also make ``PyYAML`` a hard runtime dependency of a
package whose dependency list is deliberately empty and whose layout engine
carries a *tested* zero-dependency promise (``T-9``).

What is exposed is not what is implemented
------------------------------------------
Every key in section 6.7 is recognised here, and that is not the same as every
key working. Three of them describe behaviour this version does not have, and
one describes it only at its default value:

``style``, ``extends``, ``overrides``
    ``P4-9`` and ``P4-11``. Recognised and **refused**.
``brace_style``
    ``attach`` is what the formatter does -- 732 of 733 corpus declarations,
    with Allman appearing nowhere. ``break`` is not implemented; no rule reads
    :meth:`~pssfmt.style.Style.brace_for` yet. Writing ``attach`` is accepted
    because writing down what already happens is not an error; writing
    ``break`` is refused.

Refusing rather than accepting-and-ignoring is the same call ``P4-1`` made for
``--lines``, and for the same reason. A recognised option that silently does
nothing is the worst of the three available behaviours: the user has written
down an intention, the tool has accepted it, and the output disagrees with
both. An unknown-key error reads as a typo; a refusal says what the key means
and that this version cannot honour it.

That rule cuts the other way too. ``continuation_indent`` was in the same
state when this module was written -- a section 6.7 key that
:meth:`~pssfmt.style.Style.continuation_for` answered and *nothing asked*,
with the one continuation site in the rules reaching for ``indent_width``
instead. It cost one line to make real, so it was made real rather than
refused. The check is worth stating as a habit: **exposing an option is a
promise, so the last step before exposing one is finding the code that keeps
it.**

Discovery
---------
From the directory holding each input file, upward. The search stops at the
first directory that *provides* a configuration, or at a version-control root,
whichever comes first -- and the VCS boundary is checked inclusively, so a
``.pssfmt`` beside ``.git`` is found.

Stopping at the VCS root matters more than it looks. Without it the search
runs to ``/``, and a ``.pssfmt`` in a home directory silently restyles every
repository the user owns -- a configuration nobody can see in the tree and
nobody can commit. Stopping there costs the ability to set a machine-wide
default, which is not a thing a formatter should offer anyway.

Only the *first* configuration found applies; the chain is not merged. Merging
would make "which file set this value?" a question the user cannot answer by
reading, and ``P4-9``'s ``extends`` is the deliberate way to compose two files
-- deliberate being the point, since it is written down in one of them.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple

from .layout.align import AlignMode, GroupBoundary
from .style import (
    DEFAULT_STYLE,
    BraceMode,
    LineEnding,
    SemicolonMode,
    Style,
)

__all__ = [
    "ConfigError",
    "Resolved",
    "Resolver",
    "CONFIG_NAME",
    "OPTIONS",
    "find_config",
    "load_table",
    "style_from_table",
]

#: The dedicated configuration file. Read before ``pyproject.toml`` in the
#: same directory: a file named after the tool is a more specific statement
#: than a table inside a file named after something else.
CONFIG_NAME = ".pssfmt"

PYPROJECT = "pyproject.toml"

#: Directories whose presence ends the upward search. See the module
#: docstring; the check is inclusive of the directory itself.
VCS_MARKERS = (".git", ".hg", ".svn")

#: The TOML version pin (``P4-12``). A file written for a later ``pssfmt``
#: may rely on defaults this one does not have, and formatting it under the
#: old ones is exactly what the pin exists to prevent.
SUPPORTED_VERSION = 1


class ConfigError(Exception):
    """A configuration file that cannot be used.

    Carries the path so the message can name it. Every caller turns this into
    exit code ``2`` -- *"I could not compute the answer"* -- and never ``1``,
    which means *"the answer is no"*. A broken ``.pssfmt`` under ``--check``
    is a broken toolchain, not an unformatted pull request.
    """

    def __init__(self, path: Path, message: str) -> None:
        super().__init__(message)
        self.path = path
        self.message = message

    def __str__(self) -> str:
        return "%s: %s" % (self.path, self.message)


# ---------------------------------------------------------------------------
# Reading a table
# ---------------------------------------------------------------------------

def _toml_loads(data: bytes, path: Path) -> Mapping[str, Any]:
    """Parse TOML, or explain precisely what is missing.

    ``tomllib`` is stdlib from 3.11 and ``tomli`` is the backport this package
    declares for 3.9 and 3.10. If neither is importable the configuration file
    is *not* skipped: a file the user wrote and the tool cannot read must stop
    the run, because carrying on means formatting to a style nobody asked for
    while reporting success.
    """
    try:
        import tomllib as toml  # type: ignore[import-not-found]
    except ModuleNotFoundError:  # pragma: no cover - 3.9/3.10 only
        try:
            import tomli as toml  # type: ignore[no-redef]
        except ModuleNotFoundError:
            raise ConfigError(
                path,
                "cannot read TOML on this interpreter; install `tomli` "
                "(`pip install tomli`) or use Python 3.11 or newer") from None
    try:
        return toml.loads(data.decode("utf-8"))
    except UnicodeDecodeError:
        raise ConfigError(path, "not valid UTF-8") from None
    except Exception as exc:  # tomllib.TOMLDecodeError, and tomli's
        raise ConfigError(path, "not valid TOML: %s" % exc) from None


def load_table(path: Path) -> Optional[Mapping[str, Any]]:
    """The option table in *path*, or ``None`` if it holds none.

    ``None`` is returned only for a ``pyproject.toml`` with no
    ``[tool.pssfmt]`` -- the file exists, but it is not a configuration for
    this tool, and the search should carry on past it. A ``.pssfmt`` always
    counts, including an empty one, which is a legitimate way to say
    *"stop here, use the defaults"*.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ConfigError(path, exc.strerror or str(exc)) from None

    table = _toml_loads(data, path)
    if path.name != PYPROJECT:
        return table

    tool = table.get("tool")
    if not isinstance(tool, dict) or "pssfmt" not in tool:
        return None
    section = tool["pssfmt"]
    if not isinstance(section, dict):
        raise ConfigError(path, "[tool.pssfmt] must be a table")
    return section


# ---------------------------------------------------------------------------
# The schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Option:
    """One recognised configuration key.

    *field* is the :class:`~pssfmt.style.Style` attribute it sets, or ``None``
    for a key that is recognised and refused. Keeping refused keys in the same
    table as working ones is what makes a typo of ``extends`` suggest
    ``extends`` rather than the nearest *implemented* key, which would be a
    confusing thing to be told.
    """

    name: str
    field: Optional[str]
    parse: Callable[[Any, Path], Any]
    summary: str


def _reject(path: Path, key: str, message: str) -> "ConfigError":
    return ConfigError(path, "%s: %s" % (key, message))


def _integer(key: str, minimum: int) -> Callable[[Any, Path], int]:
    def parse(value: Any, path: Path) -> int:
        # `bool` is a subclass of `int`, and TOML has real booleans, so
        # `print_width = true` would otherwise resolve to a print width of 1.
        if isinstance(value, bool) or not isinstance(value, int):
            raise _reject(path, key,
                          "expected an integer, got %s" % _describe(value))
        if value < minimum:
            raise _reject(path, key,
                          "must be %d or greater, got %d" % (minimum, value))
        return value
    return parse


def _boolean(key: str) -> Callable[[Any, Path], bool]:
    def parse(value: Any, path: Path) -> bool:
        if not isinstance(value, bool):
            raise _reject(path, key,
                          "expected true or false, got %s" % _describe(value))
        return value
    return parse


def _choice(key: str, enum: Any,
            unimplemented: Mapping[str, str] = {}) -> Callable[[Any, Path], Any]:
    """A value from *enum*, with the nearest one suggested on a miss.

    *unimplemented* names members that are spelled correctly and do not work,
    mapping each to what to say about it. They are separated from the misspelt
    ones on purpose: "did you mean `attach`?" is a wrong and confusing answer
    to somebody who typed `break` and meant it.
    """
    allowed = [member.value for member in enum]

    def parse(value: Any, path: Path) -> Any:
        if not isinstance(value, str):
            raise _reject(path, key,
                          "expected one of %s, got %s"
                          % (_alternatives(allowed), _describe(value)))
        if value in unimplemented:
            raise _reject(path, key, unimplemented[value])
        try:
            return enum(value)
        except ValueError:
            raise _reject(path, key, "%r is not one of %s%s"
                          % (value, _alternatives(allowed),
                             _suggestion(value, allowed))) from None
    return parse


def _version(value: Any, path: Path) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _reject(path, "version",
                      "expected an integer, got %s" % _describe(value))
    if value != SUPPORTED_VERSION:
        raise _reject(path, "version",
                      "this pssfmt understands version %d, not %d. A later "
                      "version may change what the other keys mean, so the "
                      "file is refused rather than read under the old "
                      "meanings" % (SUPPORTED_VERSION, value))
    return None


def _named_style(value: Any, path: Path) -> None:
    if value != "pss":
        raise _reject(path, "style",
                      "the only base style in this version is `pss`; named "
                      "and installable base styles are not implemented yet")
    return None


def _unimplemented(key: str, what: str) -> Callable[[Any, Path], None]:
    def parse(value: Any, path: Path) -> None:
        raise _reject(path, key, "%s is not implemented in this version" % what)
    return parse


def _describe(value: Any) -> str:
    """A value in a message, named by kind rather than dumped."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "a table"
    return repr(value)


def _alternatives(allowed: Iterable[str]) -> str:
    return ", ".join("`%s`" % v for v in allowed)


def _suggestion(value: str, allowed: Iterable[str]) -> str:
    near = difflib.get_close_matches(value, list(allowed), n=1, cutoff=0.6)
    return "; did you mean `%s`?" % near[0] if near else ""


#: Every key section 6.7 names, in the order that section lists them.
#:
#: ``T-16``-style exhaustiveness is checked from the other end too: a
#: ``Style`` field named in section 6.7 with no entry here is an option the
#: documentation promises and the config cannot set.
OPTIONS: Tuple[Option, ...] = (
    Option("version", None, _version,
           "the default-semantics pin"),
    Option("style", None, _named_style,
           "the named base style to build on"),
    Option("extends", None,
           _unimplemented("extends", "inheriting from another config file"),
           "a config file or package to inherit from"),

    Option("print_width", "print_width", _integer("print_width", 1),
           "the column the layout engine tries to stay inside"),
    Option("indent_width", "indent_width", _integer("indent_width", 0),
           "columns per level of nesting"),
    Option("continuation_indent", "continuation_indent",
           _integer("continuation_indent", 0),
           "columns for a line continued from the one above"),
    Option("use_tabs", "use_tabs", _boolean("use_tabs"),
           "indent with tabs instead of spaces"),
    Option("brace_style", "brace_style",
           _choice("brace_style", BraceMode, {
               "break": "`break` (Allman) is not implemented in this version; "
                        "declarations are always written with the brace on "
                        "the header line"}),
           "where `{` goes"),
    Option("max_blank_lines", "max_blank_lines", _integer("max_blank_lines", 0),
           "consecutive blank lines kept between members"),
    Option("insert_final_newline", "insert_final_newline",
           _boolean("insert_final_newline"),
           "end the file with a newline"),
    Option("line_ending", "line_ending", _choice("line_ending", LineEnding),
           "the line terminator to emit"),
    Option("optional_semicolon", "optional_semicolon",
           _choice("optional_semicolon", SemicolonMode),
           "what to do with a `;` PSS does not require"),

    Option("alignment", "alignment", _choice("alignment", AlignMode),
           "how columns within a group of lines are aligned"),
    Option("alignment_group_boundary", "alignment_group_boundary",
           _choice("alignment_group_boundary", GroupBoundary),
           "what ends a run of lines that align together"),

    Option("overrides", None,
           _unimplemented("overrides", "per-path option overrides"),
           "per-path option overrides"),
)

_BY_NAME: Mapping[str, Option] = {option.name: option for option in OPTIONS}


def style_from_table(table: Mapping[str, Any], path: Path,
                     base: Style = DEFAULT_STYLE) -> Style:
    """Apply *table* to *base*, or raise :class:`ConfigError`.

    Keys are applied in the schema's order rather than the file's, so two
    files with the same keys in a different order cannot resolve differently
    and an error message does not depend on typing order either.
    """
    unknown = [key for key in table if key not in _BY_NAME]
    if unknown:
        key = sorted(unknown)[0]
        raise ConfigError(path, "unknown option `%s`%s"
                          % (key, _suggestion(key, _BY_NAME)))

    changes: Dict[str, Any] = {}
    for option in OPTIONS:
        if option.name not in table:
            continue
        value = option.parse(table[option.name], path)
        if option.field is not None:
            changes[option.field] = value

    try:
        return base.evolve(**changes)
    except ValueError as exc:
        # Style validates too, and its message is the better one -- it knows
        # the invariant. Reaching here means the schema's bound and Style's
        # disagree, which is worth surfacing rather than hiding behind a
        # duplicate check.
        raise ConfigError(path, str(exc)) from None


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _candidates(directory: Path) -> Iterable[Path]:
    yield directory / CONFIG_NAME
    yield directory / PYPROJECT


def find_config(start: Path) -> Optional[Tuple[Path, Mapping[str, Any]]]:
    """The configuration governing *start*, or ``None`` for the defaults.

    *start* is a directory. Returns the file it was found in along with the
    raw table, so a caller can report the origin -- the first question anyone
    asks when a shared configuration misbehaves.
    """
    for directory in _upward(start):
        for candidate in _candidates(directory):
            if not candidate.is_file():
                continue
            table = load_table(candidate)
            if table is not None:
                return candidate, table
        if _is_vcs_root(directory):
            break
    return None


def _upward(start: Path) -> Iterable[Path]:
    """*start* and each of its parents, ending at the filesystem root."""
    directory = start.resolve()
    yield directory
    for parent in directory.parents:
        yield parent


def _is_vcs_root(directory: Path) -> bool:
    return any((directory / marker).exists() for marker in VCS_MARKERS)


@dataclass(frozen=True)
class Resolved:
    """A style and where it came from. ``origin`` is ``None`` for defaults."""

    style: Style
    origin: Optional[Path] = None


class Resolver:
    """Per-directory configuration lookup, memoised.

    One object per run. The cache is what keeps a thousand-file walk from
    stat-ing its way to the filesystem root a thousand times, and it is keyed
    on the *directory* because that is what discovery actually depends on --
    two files in one directory cannot resolve differently.
    """

    def __init__(self, base: Style = DEFAULT_STYLE) -> None:
        self._base = base
        self._cache: Dict[Path, Resolved] = {}

    def for_path(self, path: Path) -> Resolved:
        """The style governing *path*, a file. May raise :class:`ConfigError`."""
        return self.for_directory(path.parent if path.parent != Path("")
                                  else Path("."))

    def for_directory(self, directory: Path) -> Resolved:
        key = directory.resolve()
        found = self._cache.get(key)
        if found is None:
            found = self._resolve(key)
            self._cache[key] = found
        return found

    def _resolve(self, directory: Path) -> Resolved:
        discovered = find_config(directory)
        if discovered is None:
            return Resolved(self._base)
        path, table = discovered
        return Resolved(style_from_table(table, path, self._base), path)

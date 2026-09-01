"""``T-32`` -- ``P4-2``, configuration discovery and the option schema.

Four things are worth testing about a config layer, and only the last one is
about parsing.

**Discovery**, because the whole feature is "the right file wins" and the ways
to get that wrong are all silent: the wrong file, a merged chain, or a file
outside the repository that the user cannot see.

**Refusal**, because ``P4-1`` established that a recognised option which does
nothing is the worst of the three available behaviours, and three of the
twelve keys are in exactly that position.

**That every exposed option is real**, which is
:class:`TestEveryOptionDoesSomething` below and is the test this module exists
for. ``P4-1a`` found two section 6.7 options that nothing read, and writing a
config layer converts an unread field into a *promise*. The check is
mechanical rather than a habit for the same reason ``T-30`` is: the failure
mode is a green suite.

**Parsing**, last and briefly, because a wrong type or a typo is a message
quality problem rather than a correctness one -- with one exception worth
singling out, which is that ``bool`` is a subclass of ``int`` in Python and
TOML has real booleans, so ``print_width = true`` reads as a print width of
one unless somebody stops it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pssparser")

from pssfmt.config import (  # noqa: E402
    CONFIG_NAME, OPTIONS, ConfigError, Resolver, find_config, style_from_table,
)
from pssfmt.layout.align import AlignMode, GroupBoundary  # noqa: E402
from pssfmt.rules import format_source  # noqa: E402
from pssfmt.style import (DEFAULT_STYLE, BraceMode, LineEnding,  # noqa: E402
                          SemicolonMode, Style)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def resolve(directory: Path):
    return Resolver().for_directory(directory)


def parse(text: str, path: Path = Path("<test>")) -> Style:
    """A ``.pssfmt`` body straight to a Style, bypassing discovery."""
    # `tomllib` is stdlib only from 3.11, and this project supports 3.9 and
    # 3.10, where `tomli` is the declared backport. `pssfmt.config._parse_toml`
    # has carried this fallback since it was written; this helper did not, and
    # nothing said so until the matrix ran for the first time -- the 3.9 and
    # 3.10 legs had never reached a test, because every job failed at `pip
    # install` while pssparser was unresolvable. Same shape as `C-9b`, and the
    # same fallback `tests/support.py` already uses.
    try:
        import tomllib
    except ModuleNotFoundError:  # Python < 3.11
        import tomli as tomllib
    return style_from_table(tomllib.loads(text), path)


# ---------------------------------------------------------------------------


class TestDiscovery:
    """Which file wins, and where the search stops."""

    def test_no_config_anywhere_is_the_measured_default(self, tmp_path):
        (tmp_path / ".git").mkdir()
        found = resolve(tmp_path)
        assert found.style == DEFAULT_STYLE
        assert found.origin is None

    def test_found_by_walking_up(self, tmp_path):
        (tmp_path / ".git").mkdir()
        write(tmp_path / CONFIG_NAME, "indent_width = 2\n")
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        assert resolve(deep).style.indent_width == 2

    def test_the_nearest_file_wins_outright(self, tmp_path):
        """Not merged. The near file's silence is the *default*, not the far
        file's value -- which is the whole difference between "first wins" and
        "merge", and the reason `extends` exists as a separate feature."""
        (tmp_path / ".git").mkdir()
        write(tmp_path / CONFIG_NAME, "indent_width = 2\nprint_width = 60\n")
        near = tmp_path / "sub"
        write(near / CONFIG_NAME, "indent_width = 8\n")
        style = resolve(near).style
        assert style.indent_width == 8
        assert style.print_width == DEFAULT_STYLE.print_width

    def test_pssfmt_beats_pyproject_in_the_same_directory(self, tmp_path):
        (tmp_path / ".git").mkdir()
        write(tmp_path / CONFIG_NAME, "indent_width = 2\n")
        write(tmp_path / "pyproject.toml", "[tool.pssfmt]\nindent_width = 8\n")
        found = resolve(tmp_path)
        assert found.style.indent_width == 2
        assert found.origin.name == CONFIG_NAME

    def test_pyproject_is_read_when_there_is_no_pssfmt(self, tmp_path):
        (tmp_path / ".git").mkdir()
        write(tmp_path / "pyproject.toml",
              '[project]\nname = "x"\n\n[tool.pssfmt]\nindent_width = 3\n')
        found = resolve(tmp_path)
        assert found.style.indent_width == 3
        assert found.origin.name == "pyproject.toml"

    def test_a_pyproject_without_our_table_does_not_stop_the_search(self, tmp_path):
        """It is not a configuration *for this tool*, so it says nothing --
        including nothing about whether to keep looking."""
        (tmp_path / ".git").mkdir()
        write(tmp_path / CONFIG_NAME, "indent_width = 2\n")
        sub = tmp_path / "sub"
        write(sub / "pyproject.toml", '[project]\nname = "y"\n')
        assert resolve(sub).style.indent_width == 2

    def test_an_empty_pssfmt_stops_the_search(self, tmp_path):
        """"Use the defaults here" is a thing somebody may need to say, and an
        empty file is how they say it. Treating it as absent would silently
        hand the directory the outer project's style."""
        (tmp_path / ".git").mkdir()
        write(tmp_path / CONFIG_NAME, "indent_width = 2\n")
        sub = tmp_path / "sub"
        write(sub / CONFIG_NAME, "")
        found = resolve(sub)
        assert found.style == DEFAULT_STYLE
        assert found.origin is not None

    def test_the_search_stops_at_a_vcs_root(self, tmp_path):
        """A `.pssfmt` above the repository is one nobody can see in the tree
        and nobody can commit. Without this bound the search runs to `/` and a
        file in a home directory restyles every checkout on the machine."""
        write(tmp_path / CONFIG_NAME, "indent_width = 2\n")
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        assert resolve(repo).style == DEFAULT_STYLE

    def test_the_vcs_boundary_is_inclusive(self, tmp_path):
        """The repository root is where the config actually lives, so the
        directory holding `.git` is searched before the search stops."""
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        write(repo / CONFIG_NAME, "indent_width = 2\n")
        deep = repo / "src" / "pss"
        deep.mkdir(parents=True)
        assert resolve(deep).style.indent_width == 2

    def test_origin_names_the_file_it_came_from(self, tmp_path):
        (tmp_path / ".git").mkdir()
        path = write(tmp_path / CONFIG_NAME, "indent_width = 2\n")
        assert resolve(tmp_path).origin.samefile(path)

    def test_two_directories_can_resolve_differently_in_one_run(self, tmp_path):
        """A monorepo has more than one answer, which is why resolution is per
        file rather than once per invocation."""
        (tmp_path / ".git").mkdir()
        write(tmp_path / "one" / CONFIG_NAME, "indent_width = 2\n")
        write(tmp_path / "two" / CONFIG_NAME, "indent_width = 8\n")
        resolver = Resolver()
        assert resolver.for_directory(tmp_path / "one").style.indent_width == 2
        assert resolver.for_directory(tmp_path / "two").style.indent_width == 8

    def test_the_cache_is_keyed_on_the_directory_not_the_file(self, tmp_path):
        (tmp_path / ".git").mkdir()
        write(tmp_path / CONFIG_NAME, "indent_width = 2\n")
        resolver = Resolver()
        first = resolver.for_path(tmp_path / "a.pss")
        second = resolver.for_path(tmp_path / "b.pss")
        assert first is second

    def test_find_config_returns_the_raw_table(self, tmp_path):
        (tmp_path / ".git").mkdir()
        write(tmp_path / CONFIG_NAME, "indent_width = 2\n")
        path, table = find_config(tmp_path)
        assert path.name == CONFIG_NAME
        assert table == {"indent_width": 2}


class TestEveryOptionDoesSomething:
    """The promise test, and the reason this module exists.

    ``P4-1a`` found ``insert_final_newline`` and ``line_ending`` declared in
    ``Style`` and read by nothing. A config file turns that from a dormant
    field into a documented promise, so every key the schema accepts is
    checked here against real formatter output: set it, format, and require
    the result to differ from the same input under the default.

    Two things this deliberately does *not* assert. It does not pin the
    output, because that would make it a golden test in disguise and it would
    fail for reasons that have nothing to do with the option. And it does not
    say the change is *correct* -- only that the option is wired to something.
    Correctness is the golden suite's job; being connected at all is this
    one's, and being connected at all is what was missing twice.
    """

    LONG = "component a {\n    int x = aaaaaaaa + bbbbbbbb + cccccccc + dddddddd;\n}\n"
    BLANKS = "component a {\n    int x;\n\n\n\n    int y;\n}\n"
    SEMICOLON = "package p {\n    struct s {};\n}\n"
    TABLE = ("component a {\n"
             "    int    x;\n"
             "    bit[8] yy;\n"
             "\n"
             "    bit[128] zzz;\n"
             "    int      w;\n"
             "}\n")

    #: ``alignment_group_boundary`` needs its own source, and the reason is a
    #: finding rather than a detail. It used to share :data:`TABLE`, where
    #: merging two groups made ``infer`` see one ragged block and flush
    #: everything. ``P3-11c`` made ``infer`` judge each *run* of lines sharing
    #: a column instead of the whole block, so on that source the two settings
    #: now produce the same output -- the two tables survive either way, which
    #: is the improvement.
    #:
    #: The option still does something, and this is what it does: with the
    #: blank line as a boundary, ``int   x;`` is the only marked line in its
    #: group, so it is reproduced -- one line is no evidence. Remove the
    #: boundary and it joins a group whose other members reach a different
    #: column, which *is* evidence, and it is flushed.
    BOUNDARY = ("component a {\n"
                "    int   x;\n"
                "\n"
                "    bit[8]  yy;\n"
                "    int     zz;\n"
                "}\n")

    #: ``(key, TOML text, source, extra options both sides share)``.
    #:
    #: The shared options exist for ``continuation_indent``, which cannot be
    #: observed at all until something has been continued -- so both sides of
    #: that comparison need the narrow ``print_width`` that forces a break,
    #: and the option under test has to be the *only* difference.
    PROBES = (
        ("print_width", "print_width = 24", LONG, ""),
        ("indent_width", "indent_width = 2", LONG, ""),
        ("continuation_indent", "continuation_indent = 9", LONG,
         "print_width = 24"),
        ("use_tabs", "use_tabs = true", LONG, ""),
        ("max_blank_lines", "max_blank_lines = 0", BLANKS, ""),
        ("insert_final_newline", "insert_final_newline = false", LONG, ""),
        ("line_ending", 'line_ending = "crlf"', LONG, ""),
        ("optional_semicolon", 'optional_semicolon = "preserve"', SEMICOLON, ""),
        ("alignment", 'alignment = "flush-left"', TABLE, ""),
        ("alignment_group_boundary", 'alignment_group_boundary = "none"',
         BOUNDARY, ""),
    )

    @pytest.mark.parametrize("key, toml, source, shared",
                             PROBES, ids=[p[0] for p in PROBES])
    def test_setting_it_changes_the_output(self, key, toml, source, shared):
        base = format_source(source, style=parse(shared))
        changed = format_source(source, style=parse(shared + "\n" + toml))
        assert changed != base, (
            "`%s` is accepted by the config schema and changes nothing about "
            "the output -- an exposed option that does not exist" % key)

    def test_every_settable_option_is_probed(self):
        """The list above is a hand-written one, which is the shape that goes
        stale: option thirteen gets added and nobody adds the probe. Pinning
        it against the schema is what keeps the previous test honest."""
        settable = {option.name for option in OPTIONS if option.field}
        probed = {probe[0] for probe in self.PROBES}
        assert settable - probed == {"brace_style"}, (
            "an option gained a Style field with no probe; either wire it to "
            "the formatter or refuse it, per the module docstring")

    def test_brace_style_is_the_documented_exception(self):
        """It is settable-but-only-to-its-default, which is why it is the one
        member of the gap above. `attach` is what the formatter does; `break`
        is refused rather than accepted-and-ignored."""
        assert parse('brace_style = "attach"').brace_style is BraceMode.ATTACH
        with pytest.raises(ConfigError) as raised:
            parse('brace_style = "break"')
        assert "not implemented" in str(raised.value)
        assert "did you mean" not in str(raised.value)


class TestRefusal:
    """Recognised, and refused. See the module docstring on why not ignored."""

    @pytest.mark.parametrize("toml, expected", [
        ('extends = "../base.pssfmt"', "extends"),
        ("[overrides]\n", "overrides"),
        ('style = "google"', "style"),
        ("version = 2", "version"),
    ])
    def test_recognised_but_unavailable(self, toml, expected):
        with pytest.raises(ConfigError) as raised:
            parse(toml)
        message = str(raised.value)
        assert expected in message
        assert "unknown option" not in message, (
            "a key section 6.7 names must never be reported as a typo")

    def test_the_supported_version_is_accepted(self):
        assert parse("version = 1\nindent_width = 2").indent_width == 2

    def test_a_later_version_says_why_rather_than_just_refusing(self):
        """The pin exists because a later file may rely on defaults this
        version does not have, so the message has to name that and not read as
        a validation nit."""
        with pytest.raises(ConfigError) as raised:
            parse("version = 9")
        assert "what the other keys mean" in str(raised.value)


class TestBadInput:
    """Message quality, plus the one trap that is a correctness bug."""

    def test_bool_is_not_an_integer(self):
        """`isinstance(True, int)` is True and TOML has real booleans, so
        without an explicit check `print_width = true` resolves to a print
        width of 1 and every line in the file wraps."""
        with pytest.raises(ConfigError) as raised:
            parse("print_width = true")
        assert "expected an integer" in str(raised.value)

    def test_a_string_is_not_an_integer(self):
        with pytest.raises(ConfigError) as raised:
            parse('print_width = "80"')
        assert "expected an integer" in str(raised.value)

    def test_an_integer_is_not_a_boolean(self):
        with pytest.raises(ConfigError) as raised:
            parse("use_tabs = 1")
        assert "expected true or false" in str(raised.value)

    def test_bounds_are_enforced(self):
        with pytest.raises(ConfigError) as raised:
            parse("print_width = 0")
        assert "1 or greater" in str(raised.value)

    def test_negative_indent_is_refused(self):
        with pytest.raises(ConfigError):
            parse("indent_width = -1")

    def test_unknown_key_suggests_the_nearest_one(self):
        with pytest.raises(ConfigError) as raised:
            parse("indent_widht = 2")
        assert "unknown option `indent_widht`" in str(raised.value)
        assert "did you mean `indent_width`?" in str(raised.value)

    def test_an_unrecognisable_key_gets_no_guess(self):
        """A wrong suggestion is worse than none: it sends the reader off to
        check a key they never wrote."""
        with pytest.raises(ConfigError) as raised:
            parse("banana = 2")
        assert "did you mean" not in str(raised.value)

    def test_a_bad_enum_value_suggests_the_nearest_value(self):
        with pytest.raises(ConfigError) as raised:
            parse('line_ending = "clrf"')
        assert "did you mean `crlf`?" in str(raised.value)

    def test_a_bad_enum_value_lists_the_alternatives(self):
        with pytest.raises(ConfigError) as raised:
            parse('alignment = "sideways"')
        for value in AlignMode:
            assert value.value in str(raised.value)

    def test_malformed_toml_names_the_file(self, tmp_path):
        (tmp_path / ".git").mkdir()
        write(tmp_path / CONFIG_NAME, "indent_width = = 2\n")
        with pytest.raises(ConfigError) as raised:
            resolve(tmp_path)
        assert str(tmp_path / CONFIG_NAME) in str(raised.value)
        assert "not valid TOML" in str(raised.value)

    def test_a_pyproject_table_that_is_not_a_table(self, tmp_path):
        (tmp_path / ".git").mkdir()
        write(tmp_path / "pyproject.toml", 'tool = {pssfmt = 3}\n')
        with pytest.raises(ConfigError) as raised:
            resolve(tmp_path)
        assert "must be a table" in str(raised.value)

    def test_the_error_names_the_key(self):
        with pytest.raises(ConfigError) as raised:
            parse('max_blank_lines = "lots"')
        assert "max_blank_lines" in str(raised.value)


class TestTheSchemaMatchesStyle:
    """Both directions, because either gap is invisible from the other side."""

    def test_every_settable_option_names_a_real_style_field(self):
        for option in OPTIONS:
            if option.field is not None:
                assert hasattr(DEFAULT_STYLE, option.field), option.name

    def test_every_option_has_a_summary(self):
        """Not decoration: `docs/configuration.rst` and the error messages
        both read from here, so an entry without one is an option that shows
        up in the documentation as a bare name."""
        for option in OPTIONS:
            assert option.summary.strip(), option.name

    def test_the_schema_covers_the_section_6_7_key_set(self):
        """Pinned as an equality. A key added to section 6.7 and not here is
        an option the documentation promises and the config cannot set; one
        added here and not there is an undocumented option, which is how a
        small config surface stops being small."""
        assert {option.name for option in OPTIONS} == {
            "version", "style", "extends",
            "print_width", "indent_width", "continuation_indent", "use_tabs",
            "brace_style", "max_blank_lines", "insert_final_newline",
            "line_ending", "optional_semicolon",
            "alignment", "alignment_group_boundary",
            "overrides",
        }

    def test_values_round_trip_through_their_enums(self):
        assert parse('line_ending = "crlf"').line_ending is LineEnding.CRLF
        assert parse('alignment = "preserve"').alignment is AlignMode.PRESERVE
        assert (parse('alignment_group_boundary = "none"')
                .alignment_group_boundary is GroupBoundary.NONE)
        assert (parse('optional_semicolon = "require"')
                .optional_semicolon is SemicolonMode.REQUIRE)

    def test_an_empty_table_is_the_default_style(self):
        assert parse("") == DEFAULT_STYLE

    def test_key_order_in_the_file_does_not_matter(self):
        first = parse("indent_width = 2\nprint_width = 60")
        second = parse("print_width = 60\nindent_width = 2")
        assert first == second

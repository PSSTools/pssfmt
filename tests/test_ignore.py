"""``T-33`` -- ``P4-3``, ``.pssfmtignore``.

The claim this module has to support is "gitignore syntax", and that is a
claim about somebody else's implementation, not about a specification anybody
reads. So the load-bearing test here is a **differential** one:
:class:`TestAgainstGit` writes the same patterns into a ``.gitignore`` and a
``.pssfmtignore``, asks ``git check-ignore`` and this module about the same
paths, and requires them to agree.

That is worth more than any number of hand-written expectations, and it costs
nothing to author -- the same argument ``PLAN.md`` section 7.1 makes for the
round-trip and idempotence oracles. A hand-written test asserts what its author
believed gitignore does; this one asserts what gitignore does.

It agreed on the first run, and that is worth saying plainly rather than
dressing up: this oracle has not yet caught a bug. Its value is in the future
tense. What it does establish today is that the twenty-four verdicts were
checked against something other than the same belief that produced the code,
which is exactly what the hand-written version could not have established
however green it was.

The hand-written tests below it are still worth having, for the cases git
cannot be asked about: nested files stacking, the walk's pruning, and the
decision that ignore patterns filter a walk and never a named file.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from pssfmt.ignore import (
    IGNORE_NAME, IgnoreSet, compile_pattern, load_ignores, read_ignore_file,
)

HAS_GIT = shutil.which("git") is not None


def write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The oracle
# ---------------------------------------------------------------------------

#: Patterns and paths exercised against real git. Every entry is here because
#: it is a place the two implementations could plausibly disagree, not because
#: it is a feature worth demonstrating.
PATTERNS = """\
# a comment, and a blank line follow

build/
*.tmp
/anchored.pss
gen/*.pss
deep/**/*.pss
logs/**
notadir/
**/vendor
keep/*
!keep/wanted.pss
question?.pss
[abc]class.pss
[!x]other.pss
trailing.pss\x20
"""

PATHS = (
    "build/x.pss", "sub/build/x.pss", "build",
    "a.tmp", "sub/a.tmp",
    "anchored.pss", "sub/anchored.pss",
    "gen/x.pss", "gen/deeper/x.pss",
    "deep/x.pss", "deep/a/b/x.pss",
    "logs/x.pss", "logs/a/b/x.pss",
    "notadir",
    "vendor/x.pss", "a/vendor/x.pss",
    "keep/other.pss", "keep/wanted.pss",
    "question1.pss", "questionAB.pss",
    "aclass.pss", "zclass.pss",
    "yother.pss", "xother.pss",
    "trailing.pss",
    "plain.pss", "a/b/plain.pss",
)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(("git",) + args, cwd=str(repo), capture_output=True,
                          text=True)


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    """One git repository, with identical `.gitignore` and `.pssfmtignore`."""
    root = tmp_path_factory.mktemp("ignore-oracle")
    git(root, "init", "-q")
    write(root / ".gitignore", PATTERNS)
    write(root / IGNORE_NAME, PATTERNS)
    for relative in PATHS:
        target = root / relative
        # `build` is in PATHS as a *directory* to check, and `build/x.pss`
        # already created it. Asking about a directory is the point of the
        # entry, not an oversight.
        if not target.is_dir():
            write(target, "component a {}\n")
    return root


@pytest.fixture(scope="module")
def ignores(repo):
    return load_ignores(repo)


@pytest.mark.skipif(not HAS_GIT, reason="git is not installed")
class TestAgainstGit:
    """``git check-ignore`` is the specification. Agree with it."""

    @pytest.mark.parametrize("relative", PATHS)
    def test_agrees_with_git(self, repo, ignores, relative):
        path = repo / relative
        is_dir = path.is_dir()
        # `--no-index` so the answer does not depend on what happens to be
        # staged, which is a fact about the repository rather than about the
        # patterns.
        result = git(repo, "check-ignore", "--no-index", "-q", relative)
        assert result.returncode in (0, 1), result.stderr
        expected = result.returncode == 0
        assert ignores.ignores(path, is_dir) is expected, (
            "git says %s and pssfmt says %s for %r"
            % (expected, not expected, relative))

    def test_the_oracle_is_not_vacuous(self, repo, ignores):
        """A differential test that agrees because both sides always say
        "no" proves nothing. Both verdicts have to occur."""
        verdicts = {ignores.ignores(repo / r, (repo / r).is_dir())
                    for r in PATHS}
        assert verdicts == {True, False}


# ---------------------------------------------------------------------------
# What git cannot be asked
# ---------------------------------------------------------------------------

class TestStacking:
    """Ignore files compose; configuration files do not. See the module."""

    def test_a_nested_file_applies_to_its_own_subtree(self, tmp_path):
        (tmp_path / ".git").mkdir()
        write(tmp_path / "sub" / IGNORE_NAME, "*.pss\n")
        write(tmp_path / "sub" / "x.pss")
        write(tmp_path / "x.pss")
        outer = load_ignores(tmp_path)
        inner = outer.extend(tmp_path / "sub")
        assert not outer.ignores(tmp_path / "x.pss")
        assert inner.ignores(tmp_path / "sub" / "x.pss")

    def test_a_nested_file_can_re_include(self, tmp_path):
        """The reason stacking has to be ordered rather than a union: an inner
        `!` is meaningless unless the outer rules are evaluated first."""
        (tmp_path / ".git").mkdir()
        write(tmp_path / IGNORE_NAME, "*.pss\n")
        write(tmp_path / "sub" / IGNORE_NAME, "!wanted.pss\n")
        outer = load_ignores(tmp_path)
        inner = outer.extend(tmp_path / "sub")
        assert outer.ignores(tmp_path / "sub" / "wanted.pss")
        assert not inner.ignores(tmp_path / "sub" / "wanted.pss")

    def test_every_file_up_to_the_vcs_root_applies(self, tmp_path):
        """Unlike config discovery, which stops at the first hit."""
        (tmp_path / ".git").mkdir()
        write(tmp_path / IGNORE_NAME, "*.tmp\n")
        write(tmp_path / "sub" / IGNORE_NAME, "*.bak\n")
        found = load_ignores(tmp_path / "sub")
        assert len(found.sources) == 2

    def test_the_search_stops_at_the_vcs_root(self, tmp_path):
        write(tmp_path / IGNORE_NAME, "*.pss\n")
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        assert load_ignores(repo).sources == ()

    def test_a_missing_file_is_not_an_error(self, tmp_path):
        assert read_ignore_file(tmp_path / IGNORE_NAME) is None
        assert load_ignores(tmp_path).sources == ()

    def test_an_empty_set_ignores_nothing(self, tmp_path):
        assert not IgnoreSet().ignores(tmp_path / "x.pss")


class TestParsing:
    """The lines that are not patterns."""

    @pytest.mark.parametrize("line", ["", "   ", "# comment", "#", "\t"])
    def test_not_a_pattern(self, line):
        assert compile_pattern(line) is None

    def test_a_literal_hash(self):
        rule = compile_pattern(r"\#notacomment.pss")
        assert rule is not None
        assert rule.matches("#notacomment.pss", False)

    def test_a_literal_bang(self):
        rule = compile_pattern(r"\!important.pss")
        assert rule is not None
        assert not rule.negated
        assert rule.matches("!important.pss", False)

    def test_trailing_space_is_dropped(self):
        assert compile_pattern("x.pss   ").matches("x.pss", False)

    def test_an_escaped_trailing_space_is_kept(self):
        """`foo\\ ` is how somebody names a file that really ends in a space.
        Stripping it would make that file unignorable."""
        rule = compile_pattern("odd\\ ")
        assert rule.matches("odd ", False)
        assert not rule.matches("odd", False)

    def test_a_slash_only_pattern_is_not_a_pattern(self):
        assert compile_pattern("/") is None

    def test_the_source_and_line_are_carried(self, tmp_path):
        """For `P4-5`. "Why was this file skipped?" has exactly one useful
        answer and it is the pattern that skipped it."""
        path = write(tmp_path / IGNORE_NAME, "# lead\n\n*.tmp\n")
        found = read_ignore_file(path)
        assert len(found.rules) == 1
        assert found.rules[0].line == 3
        assert found.rules[0].source == path

    def test_an_unterminated_class_is_a_literal_bracket(self):
        """Refusing to parse a valid-looking line would be a worse failure
        than a rule that simply never matches."""
        rule = compile_pattern("[unclosed.pss")
        assert rule is not None
        assert rule.matches("[unclosed.pss", False)

    def test_a_trailing_double_star_matches_at_any_depth(self):
        """``logs/**`` is everything inside ``logs``, however deep, and not
        just its immediate children.

        Asserted here at the *rule* level and not through
        :meth:`IgnoreSet.ignores`, because end to end the two are
        indistinguishable: a rule that only reached one level down would still
        ignore ``logs/a/b/x.pss`` via its ancestor ``logs/a``, and the walk
        would still prune the same directories. Narrowing this to ``[^/]*``
        passes every other test in this file, the git oracle included. The
        difference is real and it is only observable from here.
        """
        rule = compile_pattern("logs/**")
        assert rule.matches("logs/x.pss", False)
        assert rule.matches("logs/a/b/x.pss", False)
        assert not rule.matches("logs", True)

    def test_a_class_cannot_cross_a_directory_boundary(self):
        """A negated class matches everything it does not list, `/` included,
        which is the one way a wildcard here could reach into a subdirectory."""
        rule = compile_pattern("a[!x]b.pss")
        assert not rule.matches("a/b.pss", False)

    def test_last_match_wins_within_one_file(self, tmp_path):
        path = write(tmp_path / IGNORE_NAME, "*.pss\n!keep.pss\nkeep.pss\n")
        found = read_ignore_file(path)
        assert found.decide(tmp_path / "keep.pss", False) is True

    def test_a_path_outside_the_base_has_no_opinion(self, tmp_path):
        path = write(tmp_path / "in" / IGNORE_NAME, "*.pss\n")
        found = read_ignore_file(path)
        assert found.decide(tmp_path / "out" / "x.pss", False) is None


class TestTheWalk:
    """``cli.walk``: where the ignore set actually gets used."""

    @pytest.fixture(autouse=True)
    def _needs_the_parser(self):
        """``pssfmt.cli`` imports the formatter, so it reaches ``pssparser``.

        Every other suite that crosses that line skips when the parser is
        absent; this class imported ``cli`` inside each test instead, which
        turned a pssparser-free run into eight errors rather than eight skips.
        The walk itself needs no parser -- only the module that hosts it does.
        """
        pytest.importorskip("pssparser")

    def test_an_ignored_file_is_not_walked(self, tmp_path):
        from pssfmt import cli
        (tmp_path / ".git").mkdir()
        write(tmp_path / IGNORE_NAME, "generated.pss\n")
        write(tmp_path / "generated.pss")
        write(tmp_path / "hand.pss")
        assert [p.name for p in cli.walk(tmp_path)] == ["hand.pss"]

    def test_an_ignored_directory_is_pruned(self, tmp_path):
        from pssfmt import cli
        (tmp_path / ".git").mkdir()
        write(tmp_path / IGNORE_NAME, "gen/\n")
        write(tmp_path / "gen" / "a.pss")
        write(tmp_path / "src" / "b.pss")
        assert [p.name for p in cli.walk(tmp_path)] == ["b.pss"]

    def test_pruning_beats_re_inclusion(self, tmp_path):
        """Git's rule, and the reason directories are pruned rather than
        filtered file by file: once a directory is excluded, a `!` inside it
        cannot bring a file back. Filtering per file would quietly disagree."""
        from pssfmt import cli
        (tmp_path / ".git").mkdir()
        write(tmp_path / IGNORE_NAME, "gen/\n!gen/wanted.pss\n")
        write(tmp_path / "gen" / "wanted.pss")
        write(tmp_path / "keep.pss")
        assert [p.name for p in cli.walk(tmp_path)] == ["keep.pss"]

    def test_a_nested_ignore_file_is_picked_up_during_the_walk(self, tmp_path):
        from pssfmt import cli
        (tmp_path / ".git").mkdir()
        write(tmp_path / "sub" / IGNORE_NAME, "*.pss\n")
        write(tmp_path / "sub" / "x.pss")
        write(tmp_path / "top.pss")
        assert [p.name for p in cli.walk(tmp_path)] == ["top.pss"]

    @pytest.mark.parametrize("root", [".", "./"], ids=["dot", "dot-slash"])
    def test_a_relative_root_keeps_its_rules_in_subdirectories(
            self, tmp_path, monkeypatch, root):
        """``pssfmt .`` is how this is actually run, and it is the one case
        where the walk's bookkeeping can lose the ignore set.

        ``os.walk(".")`` yields ``./sub`` while ``Path(".") / "sub"``
        stringifies as ``sub``; keying the per-directory map with the second
        and looking it up with the first misses, and a miss is *silent* --
        the subtree simply proceeds with no rules. Every test above uses an
        absolute ``tmp_path``, where the two spellings agree, so none of them
        can see it. This was a real bug, found by running the tool on a corpus
        copy rather than by any test in this file.
        """
        from pssfmt import cli
        (tmp_path / ".git").mkdir()
        write(tmp_path / IGNORE_NAME, "gen/\n")
        write(tmp_path / "sub" / "gen" / "skip.pss")
        write(tmp_path / "sub" / "keep.pss")
        monkeypatch.chdir(tmp_path)
        assert [p.name for p in cli.walk(Path(root))] == ["keep.pss"]

    def test_a_relative_root_still_finds_nested_ignore_files(
            self, tmp_path, monkeypatch):
        from pssfmt import cli
        (tmp_path / ".git").mkdir()
        write(tmp_path / "sub" / IGNORE_NAME, "*.pss\n")
        write(tmp_path / "sub" / "x.pss")
        write(tmp_path / "top.pss")
        monkeypatch.chdir(tmp_path)
        assert [p.name for p in cli.walk(Path("."))] == ["top.pss"]

    def test_the_walk_is_unaffected_with_no_ignore_file(self, tmp_path):
        from pssfmt import cli
        (tmp_path / ".git").mkdir()
        write(tmp_path / "a.pss")
        write(tmp_path / "b" / "c.pss")
        assert [p.name for p in cli.walk(tmp_path)] == ["a.pss", "c.pss"]

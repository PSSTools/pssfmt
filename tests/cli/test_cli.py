"""``T-7`` -- the command line.

Every test here calls :func:`pssfmt.cli.main` with real streams and real files
in a ``tmp_path``. That is the point of ``main`` taking its three streams as
parameters and returning an exit code instead of calling :func:`sys.exit`: a
CLI test suite that exercises a parallel, more-testable implementation is
checking the part nobody runs.

What is worth testing about a formatter's CLI is not the formatting -- 2800
tests already do that -- but the four things that only exist out here:

**Exit codes**, because they are the entire interface for CI. ``1`` means "the
answer is no" and ``2`` means "I could not compute the answer", and a suite
that only checks *non-zero* would not notice them swapping.

**Atomicity**, because the failure mode is losing somebody's source file
rather than misformatting it. ``-i`` is the only operation in this project
that destroys information.

**Which stream**, because ``pssfmt f.pss > out.pss`` must not write a progress
note into the output.

**What happens when the fail-safe fires**, because a declined file is
byte-identical to a clean one and every mode has to say so out loud rather
than infer "no change" from "no diff".
"""

from __future__ import annotations

import io
import os
import stat
import sys
from pathlib import Path

import pytest

pytest.importorskip("pssparser")

from pssfmt import cli  # noqa: E402
from pssfmt.verify import SafeResult, Violation  # noqa: E402

UNTIDY = "component a {\n    int x   ;\n}\n"
TIDY = "component a {\n    int x;\n}\n"
ALREADY = "component b {}\n"


def run(*argv, stdin=""):
    """Call the real entry point. Returns ``(code, stdout, stderr)``."""
    out, err = io.StringIO(), io.StringIO()
    code = cli.main([str(a) for a in argv], stdin=io.StringIO(stdin),
                    stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def tree(tmp_path):
    """A small directory: one file that changes, one that does not."""
    (tmp_path / "untidy.pss").write_text(UNTIDY)
    (tmp_path / "tidy.pss").write_text(ALREADY)
    return tmp_path


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


class TestExitCodes:

    def test_clean_is_zero(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(ALREADY)
        assert run("--check", f)[0] == cli.OK

    def test_would_change_is_one(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        assert run("--check", f)[0] == cli.WOULD_CHANGE

    def test_a_missing_file_is_two_and_not_one(self, tmp_path):
        """The distinction the whole scheme exists for.

        A pull request that needs formatting and a CI job with a broken
        checkout call for opposite responses, and a suite that asserted only
        "non-zero" would let them swap.
        """
        code, _, err = run("--check", tmp_path / "nope.pss")
        assert code == cli.ERROR
        assert "no such file" in err

    def test_a_file_that_is_not_utf8_is_two(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_bytes(b"component a {\n    int \xff x;\n}\n")
        code, _, err = run("--check", f)
        assert code == cli.ERROR
        assert "UTF-8" in err

    def test_bad_usage_is_two(self, tmp_path):
        """argparse's own exit code, asserted rather than assumed: it is 2 by
        convention and this scheme depends on that convention holding."""
        with pytest.raises(SystemExit) as exc:
            run("--nonesuch")
        assert exc.value.code == cli.ERROR

    def test_an_error_outranks_a_diff(self, tmp_path):
        """A run that both found a diff and hit a broken file reports the
        error. Reporting ``1`` would tell CI "please run the formatter" when
        the truth is "the formatter could not read your tree"."""
        (tmp_path / "a.pss").write_text(UNTIDY)
        code, _, _ = run("--check", tmp_path / "a.pss", tmp_path / "gone.pss")
        assert code == cli.ERROR

    def test_diff_alone_does_not_fail(self, tmp_path):
        """``--diff`` reports; ``--check`` judges. Black's split, and the one
        users already have in their fingers."""
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        assert run("--diff", f)[0] == cli.OK
        assert run("--check", "--diff", f)[0] == cli.WOULD_CHANGE


# ---------------------------------------------------------------------------
# -i, and not losing the file
# ---------------------------------------------------------------------------


class TestInPlace:

    def test_it_rewrites_the_file(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        assert run("-i", f)[0] == cli.OK
        assert f.read_text() == TIDY

    def test_it_writes_nothing_to_stdout(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        assert run("-i", f)[1] == ""

    def test_an_unchanged_file_is_not_rewritten(self, tmp_path):
        """Not an optimisation. Touching the mtime of a file that did not
        change re-triggers every build system and file watcher pointed at the
        tree, which is how a formatter gets removed from a save hook."""
        f = tmp_path / "f.pss"
        f.write_text(ALREADY)
        before = f.stat().st_mtime_ns
        assert run("-i", f)[0] == cli.OK
        assert f.stat().st_mtime_ns == before

    def test_it_never_leaves_a_truncated_file(self, tmp_path, monkeypatch):
        """The failure this project can least afford, forced rather than
        hoped for.

        ``open(path, "w")`` truncates before writing, so a crash mid-write
        leaves the user with a partial file and no copy of the original.
        Writing a sibling and renaming means an interrupted run leaves either
        the old file or the new one. Simulated by making the *write* raise,
        which is the window that matters.
        """
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)

        real = os.fdopen

        def exploding(fd, *a, **k):
            handle = real(fd, *a, **k)
            handle.write = lambda *_: (_ for _ in ()).throw(OSError("disk full"))
            return handle

        monkeypatch.setattr(os, "fdopen", exploding)
        with pytest.raises(OSError):
            run("-i", f)
        assert f.read_text() == UNTIDY

    def test_it_leaves_no_temporary_behind(self, tmp_path, monkeypatch):
        """The other half of atomicity, and the half that is easy to forget:
        a failed write that leaks ``.pssfmt-abc123.pss`` into the source tree
        turns one bad run into a directory somebody has to clean by hand --
        and those files are valid ``*.pss``, so the next ``--check`` walk
        picks them up.
        """
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)

        real = os.fdopen

        def exploding(fd, *a, **k):
            handle = real(fd, *a, **k)
            handle.write = lambda *_: (_ for _ in ()).throw(OSError("disk full"))
            return handle

        monkeypatch.setattr(os, "fdopen", exploding)
        with pytest.raises(OSError):
            run("-i", f)
        assert sorted(p.name for p in tmp_path.iterdir()) == ["f.pss"]

    def test_the_target_is_replaced_and_never_opened_for_writing(
            self, tmp_path, monkeypatch):
        """Kills the mutant the test above cannot.

        Failing the *temp* write proves the original survives, but so does a
        version that writes the target directly -- it fails at the same point,
        before touching anything. The two are only distinguishable by failing
        at the moment the temp is complete and the rename has not happened,
        which is the window a truncating write does not have at all.
        """
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)

        def refuse(*a, **k):
            raise OSError("rename failed")

        monkeypatch.setattr(os, "replace", refuse)
        with pytest.raises(OSError):
            run("-i", f)
        assert f.read_text() == UNTIDY
        assert sorted(p.name for p in tmp_path.iterdir()) == ["f.pss"]

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
    def test_it_keeps_the_original_permissions(self, tmp_path):
        """``mkstemp`` creates 0600. Renaming that over a group-readable file
        silently makes somebody's checked-in source private, and the symptom
        turns up later and somewhere else."""
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        f.chmod(0o644)
        assert run("-i", f)[0] == cli.OK
        assert stat.S_IMODE(f.stat().st_mode) == 0o644

    def test_it_refuses_stdin(self):
        code, _, err = run("-i", stdin=UNTIDY)
        assert code == cli.ERROR
        assert "stdin" in err

    def test_it_cannot_be_combined_with_check(self, tmp_path):
        """Contradictory rather than redundant: one writes, the other promises
        not to. argparse refuses it before anything is opened."""
        with pytest.raises(SystemExit) as exc:
            run("-i", "--check", tmp_path / "f.pss")
        assert exc.value.code == cli.ERROR


# ---------------------------------------------------------------------------
# Which stream
# ---------------------------------------------------------------------------


class TestStreams:

    def test_formatted_output_goes_to_stdout(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        code, out, _ = run(f)
        assert code == cli.OK
        assert out == TIDY

    def test_stdin_to_stdout(self):
        code, out, _ = run(stdin=UNTIDY)
        assert (code, out) == (cli.OK, TIDY)

    def test_a_dash_means_stdin(self):
        assert run("-", stdin=UNTIDY)[1] == TIDY

    def test_notes_never_reach_stdout(self, tree):
        """``pssfmt f.pss > out.pss`` must not write a progress note into the
        user's source file. Checked over every mode, since each has its own
        reporting path."""
        for argv in ([tree], ["--check", tree], ["--diff", tree], ["-i", tree]):
            _, out, _ = run(*argv)
            assert "reformatted" not in out
            assert "left unchanged" not in out

    def test_check_says_nothing_at_all_when_clean(self, tmp_path):
        """A green CI step should be silent. Anything else trains people to
        stop reading the log."""
        f = tmp_path / "f.pss"
        f.write_text(ALREADY)
        assert run("--check", f)[1:] == ("", "")

    def test_the_summary_does_not_claim_files_were_written(self, tmp_path):
        """It says "would be reformatted" unless ``-i`` actually wrote. The
        first version said "reformatted" for the stdout and ``--diff`` modes,
        which is a false statement about the user's working tree."""
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        assert "would be reformatted" in run("--diff", f)[2]
        assert "would be reformatted" in run(f)[2]
        f.write_text(UNTIDY)
        assert "would be reformatted" not in run("-i", f)[2]

    def test_quiet_suppresses_notes_but_not_errors(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        assert run("-q", "-i", f)[2] == ""
        code, _, err = run("-q", "--check", tmp_path / "gone.pss")
        assert code == cli.ERROR and err != ""


# ---------------------------------------------------------------------------
# --diff
# ---------------------------------------------------------------------------


class TestDiff:

    def test_it_is_a_unified_diff_naming_the_file(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        out = run("--diff", f)[1]
        assert out.startswith("--- %s" % f)
        assert "+++ %s" % f in out
        assert "@@" in out
        assert "-    int x   ;" in out
        assert "+    int x;" in out

    def test_it_writes_nothing_for_a_clean_file(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(ALREADY)
        assert run("--diff", f)[1] == ""

    def test_it_does_not_touch_the_file(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        run("--diff", f)
        assert f.read_text() == UNTIDY

    def test_it_can_be_applied(self, tmp_path):
        """The shape claim, made checkable instead of asserted. A diff nobody
        can apply is a report; the header format is the difference."""
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        patch = run("--diff", f)[1]

        applied = list(UNTIDY.splitlines(keepends=True))
        hunks = [line for line in patch.splitlines(keepends=True)
                 if line[:1] in ("-", "+") and not line.startswith(("---", "+++"))]
        for line in hunks:
            if line.startswith("-"):
                applied.remove(line[1:])
            else:
                applied.append(line[1:])
        assert "".join(sorted(applied)) == "".join(sorted(TIDY.splitlines(
            keepends=True)))


# ---------------------------------------------------------------------------
# Walking a directory
# ---------------------------------------------------------------------------


class TestDiscovery:

    def test_a_directory_is_searched_for_pss_files(self, tree):
        code, _, err = run("--check", tree)
        assert code == cli.WOULD_CHANGE
        assert "1 file would be reformatted" in err
        assert "1 file left unchanged" in err

    def test_other_extensions_are_left_alone(self, tmp_path):
        (tmp_path / "notes.txt").write_text(UNTIDY)
        (tmp_path / "x.pss").write_text(ALREADY)
        assert run("--check", tmp_path)[0] == cli.OK

    def test_a_named_file_is_formatted_whatever_it_is_called(self, tmp_path):
        """Only a *walk* filters by suffix. Someone who types a path means
        that file, and skipping it because it is called ``f.pss.in`` is the
        kind of silent no-op that gets reported as "the formatter is broken".
        """
        f = tmp_path / "f.pss.in"
        f.write_text(UNTIDY)
        assert run("--check", f)[0] == cli.WOULD_CHANGE

    def test_dot_directories_and_vcs_metadata_are_skipped(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "hook.pss").write_text(UNTIDY)
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "stale.pss").write_text(UNTIDY)
        (tmp_path / "keep.pss").write_text(ALREADY)
        assert run("--check", tmp_path)[0] == cli.OK

    def test_the_walk_is_sorted(self, tmp_path):
        """So that ``--diff`` output and ``--check`` reports are a property of
        the tree rather than of the filesystem's readdir order."""
        for name in ("c.pss", "a.pss", "b.pss"):
            (tmp_path / name).write_text(UNTIDY)
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "d.pss").write_text(UNTIDY)
        found = [p.name for p in cli.walk(tmp_path)]
        assert found == sorted(found[:3]) + ["d.pss"]

    def test_an_empty_directory_is_not_an_error(self, tmp_path):
        code, _, err = run("--check", tmp_path)
        assert code == cli.OK
        assert ".pss" in err

    def test_mixing_stdin_with_files_is_refused(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        code, _, err = run("-", f)
        assert code == cli.ERROR
        assert "cannot mix" in err


# ---------------------------------------------------------------------------
# --lines
# ---------------------------------------------------------------------------


class TestLines:
    """``P4-4``. ``--lines`` was declared and refused from ``P4-1`` onward
    rather than left undeclared or accepted-and-ignored -- accepting it would
    have reformatted whole files while the user believed a range was
    protected. It now does the thing instead.

    Almost nothing here checks *formatting*: :mod:`tests.test_ranges` does
    that against the whole corpus. What only exists out here is which
    invocations are refused, and what the exit codes are.
    """

    MULTI = ("component a {\n"      # 1
             "    int x   ;\n"      # 2
             "}\n"                  # 3
             "component b {\n"      # 4
             "    int y   ;\n"      # 5
             "}\n")                 # 6

    def test_a_range_formats_only_that_range(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(self.MULTI)
        code, out, err = run("--lines", "4:6", f)
        assert code == cli.OK
        assert out.splitlines()[:3] == self.MULTI.splitlines()[:3]
        assert "int y;" in out

    def test_the_whole_file_range_is_a_plain_format(self, tmp_path):
        """The oracle that makes every other ``--lines`` invocation
        trustworthy: with the whole file named, this is not a special mode at
        all."""
        f = tmp_path / "f.pss"
        f.write_text(self.MULTI)
        whole = run(f)[1]
        assert run("--lines", "1:6", f)[1] == whole

    def test_in_place_writes_only_the_range(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(self.MULTI)
        code, out, err = run("-i", "--lines", "1:3", f)
        assert code == cli.OK
        text = f.read_text()
        assert "int x;" in text
        assert "    int y   ;" in text

    def test_check_reports_only_on_the_range(self, tmp_path):
        """The point of ``--check --lines`` in a hook: a file that is untidy
        somewhere you did not touch is not a failure."""
        f = tmp_path / "f.pss"
        f.write_text(self.MULTI)
        assert run("--check", "--lines", "4:6", f)[0] == cli.WOULD_CHANGE
        f.write_text("component a {\n    int x;\n}\ncomponent b {\n"
                     "    int y   ;\n}\n")
        assert run("--check", "--lines", "1:3", f)[0] == cli.OK

    def test_a_range_that_changes_nothing_exits_zero(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(self.MULTI)
        code, out, err = run("--check", "--lines", "3:3", f)
        assert code == cli.OK
        assert err == ""

    def test_diff_covers_only_the_range(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(self.MULTI)
        out = run("--diff", "--lines", "1:3", f)[1]
        # The *changed* lines, not the context ones: unified diff carries
        # three lines of context either side, so `int y` appearing at all
        # would have passed a naive substring check whatever `--lines` did.
        changed = [ln for ln in out.splitlines()
                   if ln[:1] in "+-" and not ln.startswith(("---", "+++"))]
        assert any("int x" in ln for ln in changed)
        assert not any("int y" in ln for ln in changed)

    def test_stdin_takes_a_range(self, tmp_path, monkeypatch):
        """The reason this feature exists. An editor shelling out for
        ``rangeFormatting`` has no file to name."""
        monkeypatch.chdir(tmp_path)
        code, out, err = run("--lines", "4:6", stdin=self.MULTI)
        assert code == cli.OK
        assert out.splitlines()[1] == "    int x   ;"
        assert "int y;" in out

    def test_several_ranges_union(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(self.MULTI)
        out = run("--lines", "1:3", "--lines", "4:6", f)[1]
        assert out == run(f)[1]

    @pytest.mark.parametrize("spec", ["1", "0:3", "9:2", "a:b", ""])
    def test_a_malformed_range_is_a_usage_error(self, tmp_path, spec):
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        code, out, err = run("--lines", spec, f)
        assert code == cli.ERROR
        assert "--lines" in err
        assert out == ""
        assert f.read_text() == UNTIDY

    def test_two_files_are_refused(self, tmp_path):
        """Line numbers do not mean anything across several inputs, and
        guessing which file they meant is worse than asking."""
        a, b = tmp_path / "a.pss", tmp_path / "b.pss"
        a.write_text(UNTIDY)
        b.write_text(UNTIDY)
        code, out, err = run("--lines", "1:2", a, b)
        assert code == cli.ERROR
        assert "one file" in err
        assert a.read_text() == UNTIDY and b.read_text() == UNTIDY

    def test_a_directory_is_refused(self, tree):
        """Refused on the argument rather than on what it expands to, so a
        directory holding one file answers the same way as one holding two."""
        code, out, err = run("--lines", "1:2", tree)
        assert code == cli.ERROR
        assert "one file" in err

    def test_a_range_past_the_end_of_the_file_is_harmless(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(self.MULTI)
        assert run("--lines", "1:9999", f)[1] == run(f)[1]

    def test_a_range_cutting_through_a_block_leaves_the_brace_alone(
            self, tmp_path):
        """Pinned because it looks like a bug and is not.

        Re-indenting a block's header and body without its closing brace
        leaves the brace at the old indentation -- it is a line the range did
        not name, and the alternative is a formatter that edits lines you told
        it not to. Measured over the corpus at arbitrary thirds, 50 of 92
        files end up like this, so it will be reported; this test is where the
        answer lives.
        """
        (tmp_path / ".pssfmt").write_text("indent_width = 2\n")
        f = tmp_path / "f.pss"
        f.write_text("component c {\n"          # 1
                     "    action a {\n"         # 2
                     "        int x;\n"         # 3
                     "    }\n"                  # 4
                     "}\n")                     # 5
        run("-i", "--lines", "2:3", f)
        assert f.read_text().splitlines() == [
            "component c {",     # not named, untouched
            "  action a {",      # re-indented
            "    int x;",        # re-indented
            "    }",             # not named, so still at four
            "}",
        ]

    def test_running_the_same_range_twice_is_not_a_no_op(self, tmp_path):
        """And must not be mistaken for instability. Line numbers name the
        file that was passed in; the first run moved the text they pointed
        at, so the second run is a different request."""
        (tmp_path / ".pssfmt").write_text("indent_width = 2\n")
        f = tmp_path / "f.pss"
        f.write_text("component c {\n    action a {\n        int x;\n"
                     "    }\n}\n")
        run("-i", "--lines", "2:3", f)
        first = f.read_text()
        run("-i", "--lines", "2:4", f)
        assert f.read_text() != first
        assert f.read_text().splitlines()[3] == "  }"

    def test_the_spliced_result_is_verified_too(self, tmp_path, monkeypatch):
        """Splicing is a *new place output is produced*, so it goes through
        the verifier like every other one.

        Reached by breaking ``restrict`` on purpose, because it cannot be
        reached any other way: the splice is sound by construction and
        ``tests/test_ranges.py`` proves that over the corpus. A safety net
        with no test is a safety net nobody knows the state of, and this
        repository has twice found an invariant missing from exactly one of
        its call sites.
        """
        monkeypatch.setattr(cli, "restrict",
                            lambda source, formatted, ranges: "int stolen;\n")
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        code, out, err = run("-i", "--lines", "1:2", f)
        assert code == cli.ERROR
        assert "left unchanged" in err
        assert f.read_text() == UNTIDY

    def test_a_declined_file_is_still_declined(self, tmp_path, monkeypatch):
        """``--lines`` must not become a way around the fail-safe: the whole
        file is formatted first, and a format that failed verification has no
        range to take."""
        monkeypatch.setattr(
            cli, "run_format",
            lambda src, style: SafeResult(
                text=src, ok=False, _original=src,
                violations=(Violation("tokens", "invented"),)))
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        code, out, err = run("-i", "--lines", "1:2", f)
        assert code == cli.ERROR
        assert f.read_text() == UNTIDY


# ---------------------------------------------------------------------------
# --explain
# ---------------------------------------------------------------------------


class TestExplain:
    """``P4-5``. The report's *content* is tested in ``tests/test_explain.py``;
    what only exists out here is that it goes to stdout, formats nothing, and
    refuses the combinations that have no meaning."""

    def test_it_writes_a_report_and_changes_nothing(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        code, out, err = run("--explain", f)
        assert code == cli.OK
        assert "Which rule laid out each line" in out
        assert f.read_text() == UNTIDY

    def test_the_report_goes_to_stdout(self, tmp_path):
        """stdout carries output and stderr carries the run. A report is
        output -- it is the thing the user asked for."""
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        code, out, err = run("--explain", f)
        assert out and not err

    def test_it_does_not_print_the_formatted_file(self, tmp_path):
        """The default mode writes formatted text to stdout; ``--explain``
        replaces that rather than adding to it, or the report would arrive
        spliced into somebody's source file."""
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        assert TIDY not in run("--explain", f)[1]

    def test_the_tree_is_opt_in(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        assert "Layout IR" not in run("--explain", f)[1]
        assert "Layout IR" in run("--explain", "--explain-tree", f)[1]

    def test_explain_tree_alone_implies_explain(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        code, out, err = run("--explain-tree", f)
        assert code == cli.OK
        assert "Layout IR" in out

    def test_stdin(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        code, out, err = run("--explain", stdin=UNTIDY)
        assert code == cli.OK
        assert out.startswith("<stdin>:")

    @pytest.mark.parametrize("flag", ["--diff", "--lines"])
    def test_flags_that_have_no_meaning_together_are_refused(
            self, tmp_path, flag):
        """Refused rather than given a meaning. "Explain what ``--lines``
        would have done" and "explain and also write the file" are both
        defensible readings, and picking one silently is how a flag acquires a
        behaviour nobody chose."""
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        argv = ["--explain", flag] + (["1:2"] if flag == "--lines" else []) + [f]
        code, out, err = run(*argv)
        assert code == cli.ERROR
        assert flag in err
        assert out == ""

    def test_in_place_is_refused(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        code, out, err = run("--explain-tree", "-i", f)
        assert code == cli.ERROR
        assert f.read_text() == UNTIDY

    def test_a_file_that_fails_verification_is_still_explained(
            self, tmp_path, monkeypatch):
        """The situation ``--explain`` exists for. Refusing to explain a file
        the verifier dislikes would remove the tool from the one case that
        needs it, so the violations are reported inside the explanation
        instead of replacing it."""
        import pssfmt.explain as explain_mod
        monkeypatch.setattr(explain_mod, "verify",
                            lambda a, b: (Violation("tokens", "invented"),))
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        code, out, err = run("--explain", f)
        assert code == cli.OK
        assert "FAILS verification" in out
        assert "Which rule laid out each line" in out

    def test_a_crash_while_explaining_is_reported_not_raised(
            self, tmp_path, monkeypatch):
        """A debugging aid may not become the thing that needs debugging."""
        monkeypatch.setattr(cli, "explain",
                            lambda *a, **k: (_ for _ in ()).throw(
                                RuntimeError("boom")))
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        code, out, err = run("--explain", f)
        assert code == cli.ERROR
        assert "could not explain" in err and "boom" in err

    def test_several_files(self, tmp_path):
        """Unlike ``--lines``, a report per file is perfectly meaningful."""
        for name in ("a.pss", "b.pss"):
            (tmp_path / name).write_text(UNTIDY)
        code, out, err = run("--explain", tmp_path)
        assert code == cli.OK
        assert out.count("Which rule laid out each line") == 2


# ---------------------------------------------------------------------------
# The fail-safe
# ---------------------------------------------------------------------------


class TestWhenTheFailSafeFires:
    """A declined file is byte-identical to a clean one, so every mode has to
    say so out loud rather than let the user infer "no change" from "no diff".

    Forced by substituting a formatter that corrupts, because the real one
    does not -- and a test that waited for a genuine rule bug to appear would
    be testing nothing until the day it mattered.
    """

    @pytest.fixture
    def declining(self, monkeypatch):
        def bad(source, style):
            return SafeResult(
                text=source, ok=False, _original=source,
                rejected="component q {}\n",
                violations=(Violation("tokens", "token 2 changed: a -> q"),))
        monkeypatch.setattr(cli, "run_format", bad)

    def test_check_reports_it_as_an_error_not_as_clean(self, tmp_path, declining):
        f = tmp_path / "f.pss"
        f.write_text(ALREADY)
        code, _, err = run("--check", f)
        assert code == cli.ERROR
        assert "left unchanged" in err
        assert "pssfmt bug" in err

    def test_in_place_does_not_write_and_does_not_claim_success(
            self, tmp_path, declining):
        f = tmp_path / "f.pss"
        f.write_text(ALREADY)
        code, _, err = run("-i", f)
        assert code == cli.ERROR
        assert f.read_text() == ALREADY
        assert "1 file declined" in err

    def test_stdout_mode_emits_the_input_unchanged(self, tmp_path, declining):
        """The fail-safe's whole promise, at the one place a caller can break
        it -- and the bug this test was written with, backwards, before its
        own docstring was read back.

        ``pssfmt f.pss > new.pss`` is a normal way to run a formatter, and by
        the time this code runs stdout is *already* the truncated destination.
        Writing nothing does not decline to modify the file; it empties it. A
        rejected format has to hand the input back through whichever channel
        the output was going to.
        """
        f = tmp_path / "f.pss"
        f.write_text(ALREADY)
        code, out, err = run(f)
        assert code == cli.ERROR
        assert out == ALREADY
        assert "pssfmt bug" in err

    def test_diff_mode_prints_no_diff_of_output_it_would_not_write(
            self, tmp_path, declining):
        f = tmp_path / "f.pss"
        f.write_text(ALREADY)
        code, out, _ = run("--diff", f)
        assert code == cli.ERROR
        assert out == ""


# ---------------------------------------------------------------------------
# Line endings, out here where the bytes are real
# ---------------------------------------------------------------------------


class TestLineEndingsSurviveTheRoundTrip:
    """``pssfmt.finish`` decides these; this checks the file layer does not
    quietly undo it. Python's text mode translates newlines on both read and
    write, so a CLI that used it would turn every CRLF file into an LF file
    while the formatter believed it was preserving them.
    """

    def test_a_crlf_file_stays_crlf_on_disk(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_bytes(b"component a {\r\n    int x   ;\r\n}\r\n")
        assert run("-i", f)[0] == cli.OK
        assert f.read_bytes() == b"component a {\r\n    int x;\r\n}\r\n"

    def test_an_lf_file_does_not_grow_carriage_returns(self, tmp_path):
        f = tmp_path / "f.pss"
        f.write_bytes(UNTIDY.encode())
        assert run("-i", f)[0] == cli.OK
        assert b"\r" not in f.read_bytes()

    def test_check_agrees_with_what_in_place_would_write(self, tmp_path):
        """The two must never disagree, and line endings are exactly where
        they would: ``--check`` compares in memory and ``-i`` writes to disk.
        A translating write would make ``--check`` pass forever on a CRLF file
        that ``-i`` rewrites every single run."""
        for data in (b"component a {\r\n}\r\n", b"component a {\n}\n"):
            f = tmp_path / "f.pss"
            f.write_bytes(data)
            first = run("--check", f)[0]
            run("-i", f)
            assert run("--check", f)[0] == cli.OK
            assert first == cli.OK or f.read_bytes() != data


# ---------------------------------------------------------------------------
# Configuration and ignore files, at the layer where they meet the exit code
# ---------------------------------------------------------------------------


class TestConfigurationReachesTheFormatting:
    """``P4-2``. ``tests/test_config.py`` covers discovery and the schema;
    what is only testable out here is that the resolved style reaches the
    formatter and that a *broken* one reaches the exit code.
    """

    def test_a_config_changes_what_check_says(self, tmp_path):
        """The end-to-end statement, and the one that fails if the seam in
        ``main`` is left holding ``DEFAULT_STYLE``: a file that is clean under
        the default style is not clean under a config that disagrees."""
        (tmp_path / ".git").mkdir()
        f = tmp_path / "f.pss"
        f.write_text(TIDY)
        assert run("--check", f)[0] == cli.OK
        (tmp_path / ".pssfmt").write_text("indent_width = 2\n")
        assert run("--check", f)[0] == cli.WOULD_CHANGE

    def test_a_config_changes_what_in_place_writes(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".pssfmt").write_text("indent_width = 2\n")
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        assert run("-i", f)[0] == cli.OK
        assert f.read_text() == "component a {\n  int x;\n}\n"

    def test_two_directories_in_one_run_get_their_own_answers(self, tmp_path):
        """Resolution is per file. A run that picked one style for the whole
        invocation would give a different result depending on whether the user
        typed the two directories or their parent."""
        (tmp_path / ".git").mkdir()
        for name, width in (("two", 2), ("eight", 8)):
            directory = tmp_path / name
            directory.mkdir()
            (directory / ".pssfmt").write_text("indent_width = %d\n" % width)
            (directory / "f.pss").write_text(UNTIDY)
        assert run("-i", tmp_path)[0] == cli.OK
        # Whole lines, not substrings: `"  int"` occurs inside an eight-space
        # indent too, so a substring check here would pass whichever style
        # both files got.
        for name, width in (("two", 2), ("eight", 8)):
            written = (tmp_path / name / "f.pss").read_text().splitlines()
            assert written[1] == " " * width + "int x;"

    def test_a_broken_config_is_an_error_and_not_a_diff(self, tmp_path):
        """Exit ``2``. "I cannot read the style" is a broken toolchain, not an
        unformatted pull request, and ``--check`` reporting ``1`` for it would
        send somebody to reformat a file that is already fine."""
        (tmp_path / ".git").mkdir()
        (tmp_path / ".pssfmt").write_text("indent_width = = 2\n")
        f = tmp_path / "f.pss"
        f.write_text(TIDY)
        code, _, err = run("--check", f)
        assert code == cli.ERROR
        assert ".pssfmt" in err

    def test_a_broken_config_does_not_fall_back_to_the_defaults(self, tmp_path):
        """The file is skipped, not formatted some other way. Falling back
        would rewrite it to a style the user did not ask for and was not told
        about, which is worse than doing nothing."""
        (tmp_path / ".git").mkdir()
        (tmp_path / ".pssfmt").write_text("indent_width = = 2\n")
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        assert run("-i", f)[0] == cli.ERROR
        assert f.read_text() == UNTIDY

    def test_a_broken_config_is_reported_once_not_once_per_file(self, tmp_path):
        """One problem, one message. A `.pssfmt` above a thousand `.pss` files
        printing a thousand times buries every other message in the run."""
        (tmp_path / ".git").mkdir()
        (tmp_path / ".pssfmt").write_text("banana = 2\n")
        for name in ("a.pss", "b.pss", "c.pss"):
            (tmp_path / name).write_text(UNTIDY)
        code, _, err = run("--check", tmp_path)
        assert code == cli.ERROR
        assert err.count("banana") == 1

    def test_a_refused_option_names_itself(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".pssfmt").write_text('brace_style = "break"\n')
        (tmp_path / "f.pss").write_text(TIDY)
        code, _, err = run("--check", tmp_path / "f.pss")
        assert code == cli.ERROR
        assert "brace_style" in err and "not implemented" in err

    def test_stdin_resolves_from_the_working_directory(self, tmp_path, monkeypatch):
        """Standard input has no path, so there is exactly one place to look
        and it should be looked in rather than skipped."""
        (tmp_path / ".git").mkdir()
        (tmp_path / ".pssfmt").write_text("indent_width = 2\n")
        monkeypatch.chdir(tmp_path)
        code, out, _ = run(stdin=UNTIDY)
        assert code == cli.OK
        assert out == "component a {\n  int x;\n}\n"


class TestIgnoreFilesReachTheWalk:
    """``P4-3``. ``tests/test_ignore.py`` covers the patterns; this is the
    behaviour a user sees.
    """

    def test_an_ignored_file_is_not_reported_by_check(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".pssfmtignore").write_text("generated.pss\n")
        (tmp_path / "generated.pss").write_text(UNTIDY)
        (tmp_path / "hand.pss").write_text(TIDY)
        assert run("--check", tmp_path)[0] == cli.OK

    def test_without_the_ignore_file_the_same_tree_is_not_clean(self, tmp_path):
        """The control for the test above. A walk that found nothing at all
        would pass it just as well, and a `--check` gate made green by *not
        looking* is the failure this whole feature is organised against."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "generated.pss").write_text(UNTIDY)
        (tmp_path / "hand.pss").write_text(TIDY)
        assert run("--check", tmp_path)[0] == cli.WOULD_CHANGE

    def test_an_ignored_file_is_not_rewritten(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".pssfmtignore").write_text("gen/\n")
        (tmp_path / "gen").mkdir()
        (tmp_path / "gen" / "f.pss").write_text(UNTIDY)
        assert run("-i", tmp_path)[0] == cli.OK
        assert (tmp_path / "gen" / "f.pss").read_text() == UNTIDY

    def test_a_named_file_is_formatted_even_when_ignored(self, tmp_path):
        """Ignore patterns filter a walk and never a name -- the same call
        ``collect`` already makes for the ``.pss`` suffix, and the same one git
        makes. Somebody who types the path means that file, and a silent no-op
        is what gets diagnosed as "the formatter is broken"."""
        (tmp_path / ".git").mkdir()
        (tmp_path / ".pssfmtignore").write_text("f.pss\n")
        f = tmp_path / "f.pss"
        f.write_text(UNTIDY)
        assert run("-i", f)[0] == cli.OK
        assert f.read_text() == TIDY

    def test_an_ignore_file_does_not_have_to_exist(self, tmp_path, tree):
        assert run("--check", tmp_path)[0] == cli.WOULD_CHANGE

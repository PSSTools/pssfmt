"""``T-10`` -- the documentation build is a test, not a courtesy.

``pygments-pss`` treats its docs build as a real regression signal and the same
reasoning applies here: ``docs/reference_api.rst`` runs autodoc over the layout
engine, so a malformed docstring, a broken cross-reference, or a renamed public
symbol fails this test rather than quietly producing a worse page.

Warnings are errors. A warning nobody fails on is a warning nobody fixes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"

pytestmark = [pytest.mark.slow, pytest.mark.integration]


@pytest.mark.skipif(
    not (DOCS / "conf.py").exists(), reason="docs/ not scaffolded"
)
def test_docs_build_clean_with_warnings_as_errors(tmp_path):
    sphinx = pytest.importorskip("sphinx", reason="sphinx is a dev dependency (ivpm default-dev)")
    del sphinx

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sphinx",
            "-b",
            "html",
            str(DOCS),
            str(tmp_path / "html"),
            "-W",
            "--keep-going",
            # Isolate from any incremental state in docs/_build.
            "-d",
            str(tmp_path / "doctrees"),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        "docs build failed:\n" + result.stdout[-4000:] + "\n" + result.stderr[-4000:]
    )


def _tracked(paths):
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", *paths],
        capture_output=True, cwd=REPO_ROOT,
    )
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.decode().split("\0") if p]


@pytest.mark.skipif(
    not (DOCS / "conf.py").exists(), reason="docs/ not scaffolded"
)
def test_docs_build_from_tracked_files_only(tmp_path):
    """The build must work in a fresh clone, not merely in this working copy.

    The test above builds ``docs/`` in place, so it sees every untracked file
    on this disk. That is how a real breakage stayed invisible: two tracked
    stubs under ``docs/design/`` used MyST ``{include}`` to pull in the root
    ``PLAN.md`` and ``formatter.md``, which are working notes and deliberately
    untracked. Locally the include resolved and the build was green; in CI the
    files did not exist, every page emitted warnings, and ``-W`` failed the
    job. The docs test could not report it, because the thing it was missing
    was present in the only place it looked.

    So this one copies **only what git tracks** and builds that. It is the
    same shape as the corpus rule elsewhere in this suite: a check that passes
    because its input happens to be lying around is not a check.
    """
    pytest.importorskip("sphinx", reason="sphinx is a dev dependency")
    # ``src`` as well as ``docs``: conf.py puts ``../src`` on sys.path so
    # autodoc can import the layout package, and an unimportable module is a
    # warning, which -W makes a failure.
    files = _tracked(["docs", "src"])
    if files is None:
        pytest.skip("not a git checkout")
    assert files, "no tracked files under docs/ -- git ls-files found nothing"

    root = tmp_path / "tracked"
    copied = 0
    for rel in files:
        src = REPO_ROOT / rel
        # Tracked but gone from the working tree = a deletion not yet
        # committed. A fresh clone made after that commit will not have it,
        # so model the intent rather than the stale index entry.
        if not src.is_file():
            continue
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        copied += 1
    assert copied, "no tracked docs files survive on disk"

    result = subprocess.run(
        [sys.executable, "-m", "sphinx", "-b", "html",
         str(root / "docs"), str(tmp_path / "html"), "-W", "--keep-going",
         "-d", str(tmp_path / "doctrees")],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        "docs build fails from tracked files alone -- it would fail in a "
        "fresh clone and in CI, however green it looks here:\n"
        + result.stdout[-4000:] + "\n" + result.stderr[-4000:]
    )


#: Working notes: drafting documents, revised continuously, written to think
#: in rather than to be read. Published pages must not render them or send a
#: reader to them.
WORKING_NOTES = ("PLAN.md", "formatter.md")


def test_no_published_page_references_the_working_notes():
    """Published documentation stands on its own.

    Not a style preference: these files are untracked, so any published
    reference to them is a link a reader cannot follow and an include that
    breaks the build. Anything from them that a reader needs belongs on a real
    page instead.
    """
    offenders = []
    for path in sorted(DOCS.rglob("*")):
        if path.is_dir() or path.suffix not in (".rst", ".md"):
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(note in line for note in WORKING_NOTES):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "published pages reference the repository's working notes:\n  "
        + "\n  ".join(offenders)
    )

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

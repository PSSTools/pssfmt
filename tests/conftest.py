"""Shared test fixtures.

Deliberately thin. The layout suite must be runnable with pssparser absent
(``PLAN.md`` ``T-2``) -- that is what lets Phase 2 proceed while Phase U is in
flight -- so nothing here may import pssparser at collection time.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"

# Support running the suite from a plain checkout, before `pip install -e .`.
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# ``tests/`` is not a package, so pytest puts each test file's own directory on
# the path and not this one. Shared test helpers live in ``tests/support.py``
# and several suites need them, so put it within reach.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

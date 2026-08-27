"""``T-9`` and ``T-13`` -- the two architectural boundaries, enforced mechanically.

``formatter.md`` section 10.3 is explicit that the layout-engine boundary must
be *"an import-linter test, not a convention"*, and ``PLAN.md`` section 6.3
makes the same argument for the style seam: a rule that hardcodes a spacing
constant is not caught by review reliably enough to matter, and by the time it
is noticed there are eight modules of them.

Both tests are pure source inspection. Neither imports pssparser, so both run
before Phase U lands.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, List, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LAYOUT_DIR = REPO_ROOT / "src" / "pssfmt" / "layout"
RULES_DIR = REPO_ROOT / "src" / "pssfmt" / "rules"

pytestmark = pytest.mark.unit


def python_files(directory: Path) -> List[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts)


def imported_modules(tree: ast.AST) -> Iterator[Tuple[str, int]]:
    """Every module name this file imports, with its line number.

    Relative imports are reported with leading dots intact (``.ir``), so a
    within-package import is distinguishable from ``pssfmt.layout.ir`` -- the
    former is fine and the latter is not, even though they name the same file.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            yield "." * node.level + (node.module or ""), node.lineno


# --------------------------------------------------------------------------
# T-9 -- the layout engine takes no dependencies
# --------------------------------------------------------------------------


class TestLayoutIsSelfContained:
    """Nothing under ``src/pssfmt/layout/`` may import ``pssfmt.*`` or ``pssparser.*``.

    Two things depend on this and both are load-bearing (``PLAN.md`` section 3):
    the engine can be built and tested while the upstream token API is still
    unwritten, which keeps ``P2`` off the critical path; and it stays
    extractable as a standalone pretty-printer.
    """

    def test_the_directory_is_actually_there(self):
        """A guard that silently guards nothing is worse than no guard."""
        assert python_files(LAYOUT_DIR), f"no modules found under {LAYOUT_DIR}"

    @pytest.mark.parametrize("path", python_files(LAYOUT_DIR), ids=lambda p: p.name)
    def test_no_forbidden_import(self, path: Path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders = []
        for module, lineno in imported_modules(tree):
            if module.startswith("."):
                continue  # within-package, which is the point of a package
            root = module.split(".")[0]
            if root in ("pssfmt", "pssparser"):
                offenders.append(f"{path.name}:{lineno} imports {module}")
        assert not offenders, (
            "layout/ must not depend on the rest of pssfmt or on pssparser "
            "(formatter.md section 10.3):\n  " + "\n  ".join(offenders)
        )

    def test_layout_imports_with_pssparser_unavailable(self, monkeypatch):
        """The end-to-end version of the same claim.

        Static import checking misses a deferred import inside a function.
        Blocking the module outright and re-importing catches both.
        """
        import builtins
        import importlib
        import sys

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name.split(".")[0] == "pssparser":
                raise ImportError("pssparser is deliberately unavailable in this test")
            return real_import(name, *args, **kwargs)

        for name in [m for m in sys.modules if m.startswith("pssfmt")]:
            monkeypatch.delitem(sys.modules, name, raising=False)
        monkeypatch.setattr(builtins, "__import__", blocked)

        layout = importlib.import_module("pssfmt.layout")
        assert layout.render(layout.text("ok")) == "ok"


# --------------------------------------------------------------------------
# T-13 -- rules consult the Style policy, never a literal
# --------------------------------------------------------------------------

#: Constructors whose numeric argument is a column count -- a style decision
#: the resolved ``Style`` owns. ``Align``'s offset is exempt at zero, because
#: "align to the current column" is a structural statement rather than a
#: measurement.
_COLUMN_ARGS = {"Indent": 1, "indent": 1, "Align": 1, "align_to": 1}

#: Constructors that take literal output text. A rule emitting ``text(" ")``
#: has decided a spacing question that :class:`pssfmt.style.Site` owns, and it
#: is a likelier slip than a hardcoded indent because it looks so harmless.
_TEXT_CTORS = {"Text", "text"}


def _called_name(node: ast.Call) -> str:
    """``Indent(...)`` and ``ir.Indent(...)`` both report ``Indent``."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _style_literals(tree: ast.AST):
    """Yields ``(lineno, description)`` for every hardcoded style constant."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _called_name(node)

        pos = _COLUMN_ARGS.get(name)
        if pos is not None:
            args = list(node.args)
            for kw in node.keywords:
                if kw.arg in ("width", "offset"):
                    args.append(kw.value)
                    pos = len(args) - 1
            if pos < len(args):
                arg = args[pos]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, int) \
                        and not isinstance(arg.value, bool):
                    if not (name in ("Align", "align_to") and arg.value == 0):
                        yield node.lineno, f"{name}(..., {arg.value})"

        if name in _TEXT_CTORS:
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                        and arg.value and not arg.value.strip():
                    yield node.lineno, f"{name}({arg.value!r})"


class TestRulesUseTheStyleSeam:
    """``P3-0``: no rule module reads config or hardcodes a spacing constant.

    Written and committed before the first rule so it could never be
    retrofitted onto a module set that had already grown literals
    (``PLAN.md`` section 6.3: the exposed option count is reversible, this
    seam is not). It skipped until ``P3-1`` created ``rules/``.

    **It was also wrong for that whole time.** The first version matched
    ``Indent`` with a regex whose argument class excluded parentheses, so
    ``Indent(ctx.build(node), 4)`` -- the shape every real rule takes, because
    the first argument is always a built subtree -- sailed past it. The guard
    passed because its pattern could not match real code, which is the same
    failure as a guard whose input is missing, wearing different clothes.
    Matching the syntax tree instead is both simpler and immune to how the
    call happens to be written across lines.

    ``# T-13-allow`` suppresses a hit. It goes on the line the *call starts*
    on, which for a call split across lines is the line with the opening
    parenthesis rather than the line with the number.
    """

    def test_the_directory_is_actually_there(self):
        """A guard that silently guards nothing is worse than no guard.

        This file's other half (``T-9``) has carried this test from the
        start. ``T-13`` went without it while ``rules/`` did not exist, and
        should not go without it now that it does.
        """
        assert python_files(RULES_DIR), f"no modules found under {RULES_DIR}"

    @pytest.mark.parametrize("path", python_files(RULES_DIR), ids=lambda p: p.name)
    def test_no_hardcoded_spacing_literal(self, path: Path):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source, filename=str(path))
        hits = [
            f"{path.name}:{lineno}: {what}"
            for lineno, what in _style_literals(tree)
            if "T-13-allow" not in lines[lineno - 1]
        ]
        assert not hits, (
            "rules must ask the resolved Style per construct -- e.g. "
            "style.indent_for(Construct.COMPONENT_BODY) or "
            "style.gap(left, right) -- rather than writing the number "
            "(PLAN.md section 6.3):\n  " + "\n  ".join(hits)
        )

    @pytest.mark.parametrize("path", python_files(RULES_DIR), ids=lambda p: p.name)
    def test_no_rule_reads_config_directly(self, path: Path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders = [
            f"{path.name}:{lineno} imports {module}"
            for module, lineno in imported_modules(tree)
            if module.rstrip(".").endswith("config")
        ]
        assert not offenders, (
            "rules see a resolved Style, never the config that produced it:\n  "
            + "\n  ".join(offenders)
        )

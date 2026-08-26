"""``T-8`` (layout slice) -- property oracles over randomly generated IR.

``formatter.md`` section 1.2 lesson 1: the property oracles catch more bugs
than any hand-written case, and they cost nothing to author per feature. The
corpus-level oracles need the upstream token API (Phase U); these three do
not, so the engine gets its property coverage now rather than after ``P1``:

* **content preservation** -- every ``Text`` reaches the output, in order,
  and layout only ever changes the whitespace between them. This is the
  layout-layer analogue of token equivalence, and it is the property that
  makes the engine safe to trust before the verifier exists.
* **width respect** -- given a tree that *can* be broken, no line exceeds
  ``print_width``.
* **determinism** -- same tree, same width, same answer. Guards against state
  leaking between renders through the propagation memo.

Seeded, so a failure is reproducible from the printed seed rather than being
a story about a build that once went red.
"""

from __future__ import annotations

import random
import string

import pytest

from pssfmt.layout import (
    LINE,
    SOFTLINE,
    concat,
    fill_with,
    group,
    indent,
    render,
    text,
    width_of,
)

pytestmark = [pytest.mark.property, pytest.mark.layout]

SEEDS = list(range(40))
MAX_ATOM = 6
INDENT = 2
MAX_DEPTH = 4


def atom(rng: random.Random):
    n = rng.randint(1, MAX_ATOM)
    return text("".join(rng.choice(string.ascii_letters) for _ in range(n)))


def breakable_tree(rng: random.Random, depth: int = 0):
    """A tree that always *can* be laid out inside a reasonable width.

    Every sequence is joined by a ``Line`` or ``SoftLine`` and every nesting
    level is a group, so there is a legal breaking of it at any width wider
    than the deepest indent plus the widest atom. Without that guarantee the
    width property would be testing the generator, not the engine.
    """
    if depth >= MAX_DEPTH or rng.random() < 0.35:
        return atom(rng)

    n = rng.randint(2, 4)
    kids = [breakable_tree(rng, depth + 1) for _ in range(n)]
    kind = rng.random()

    if kind < 0.25:
        return group(fill_with(LINE, kids))

    sep = LINE if rng.random() < 0.5 else SOFTLINE
    body = []
    for i, kid in enumerate(kids):
        if i:
            body.append(sep)
        body.append(kid)
    inner = concat(body)
    if rng.random() < 0.6:
        inner = indent(concat(sep, inner), INDENT)
    return group(inner)


def texts_of(doc, out=None):
    """Every ``Text`` value in the tree, in emission order."""
    from pssfmt.layout.ir import Concat, Fill, Group, Indent, Text

    if out is None:
        out = []
    if isinstance(doc, Text):
        out.append(doc.value)
    elif isinstance(doc, (Concat, Fill)):
        for part in doc.parts:
            texts_of(part, out)
    elif isinstance(doc, (Group, Indent)):
        texts_of(doc.contents, out)
    return out


WIDTHS = [8, 13, 20, 40, 100, 1000]


@pytest.mark.parametrize("seed", SEEDS)
def test_layout_only_changes_whitespace(seed):
    """The layout-layer analogue of token equivalence.

    If this fails the engine is dropping or duplicating content, which is the
    one class of formatter bug that is never survivable (section 3.4).
    """
    rng = random.Random(seed)
    doc = breakable_tree(rng)
    expected = "".join(texts_of(doc))
    for width in WIDTHS:
        got = render(doc, print_width=width)
        stripped = "".join(got.split())
        assert stripped == expected, f"seed={seed} width={width}"


@pytest.mark.parametrize("seed", SEEDS)
def test_no_line_exceeds_print_width(seed):
    rng = random.Random(seed)
    doc = breakable_tree(rng)
    # The floor below which even a fully-broken tree cannot fit: deepest
    # indent plus the widest atom.
    floor = MAX_DEPTH * INDENT + MAX_ATOM
    for width in WIDTHS:
        if width < floor:
            continue
        for line in render(doc, print_width=width).split("\n"):
            assert width_of(line) <= width, f"seed={seed} width={width}: {line!r}"


@pytest.mark.parametrize("seed", SEEDS)
def test_render_is_deterministic(seed):
    rng = random.Random(seed)
    doc = breakable_tree(rng)
    for width in WIDTHS:
        assert render(doc, print_width=width) == render(doc, print_width=width)


@pytest.mark.parametrize("seed", SEEDS)
def test_no_trailing_whitespace_anywhere(seed):
    rng = random.Random(seed)
    doc = breakable_tree(rng)
    for width in WIDTHS:
        got = render(doc, print_width=width)
        offenders = [l for l in got.split("\n") if l != l.rstrip()]
        assert not offenders, f"seed={seed} width={width}: {offenders!r}"


@pytest.mark.parametrize("seed", SEEDS)
def test_a_wider_page_never_produces_more_lines(seed):
    """Monotonicity: more room must not mean more breaks.

    A violation means some fit decision is reading a width it should not --
    the symptom users report as "it reformatted differently for no reason".
    """
    rng = random.Random(seed)
    doc = breakable_tree(rng)
    counts = [render(doc, print_width=w).count("\n") for w in WIDTHS]
    assert counts == sorted(counts, reverse=True), f"seed={seed}: {list(zip(WIDTHS, counts))}"

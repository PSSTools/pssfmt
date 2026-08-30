"""``T-18`` -- the empty rule set is already correct, over the whole corpus.

``P3-1``'s safety argument is that a construct with no rule is emitted by the
``P1-2`` null formatter's own machinery, so an incomplete rule set cannot
corrupt anything. ``tests/test_rules.py`` checks that on hand-written sources,
where a failure names a construct. This file checks it on 92 real files,
where a failure names something nobody thought to write down.

It is the same gate ``T-4`` applies to the null formatter, pointed at the new
entry point. That duplication is deliberate: the two reach the bytes by
different routes -- the null formatter walks terminals and flushes what the
walk stepped past, the rule layer takes a token span per node -- and a test
that only ran one of them would be checking the route rather than the file.

**This suite fails when the corpus is missing; it does not skip** (``C-8``).
A missing parser still skips, via ``importorskip``, because ``T-2`` requires
the layout suite to collect without it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.finish import finish  # noqa: E402
from pssfmt.rules import REGISTRY, RuleRegistry, format_source  # noqa: E402
from pssfmt.style import DEFAULT_STYLE, Style  # noqa: E402
from pssfmt.verify import format_safely  # noqa: E402
from support import CORPUS_ROOT, CORPUS_SOURCE, corpus_files  # noqa: E402

pytestmark = [pytest.mark.corpus, pytest.mark.integration]

FILES = corpus_files()

#: Deliberately empty, and constructed fresh rather than reusing ``REGISTRY``:
#: the claim under test is about the *empty* rule set, and it has to keep
#: meaning that after ``P3-2`` starts populating the shipped one.
EMPTY = RuleRegistry()


def ident(path):
    return str(path.relative_to(CORPUS_ROOT)) if CORPUS_ROOT else str(path)


def read(path):
    # Binary, then decode explicitly. Text mode translates newlines, which
    # would make a CRLF file pass this suite for the wrong reason.
    return path.read_bytes().decode("utf-8")


def test_the_corpus_is_present():
    """The one test here that cannot vanish along with its input.

    Everything else is parametrized over ``FILES``, so an empty corpus makes
    them collect zero cases and the file goes green having read nothing.
    """
    assert CORPUS_SOURCE != "none", (
        "no PSS corpus found. It is a declared ivpm dependency and should be "
        "at packages/pss-corpus -- run `ivpm update`, or set PSS_CORPUS.")
    assert len(FILES) >= 50, (
        "%d files from %s -- too few to be the curated corpus"
        % (len(FILES), CORPUS_SOURCE))


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_the_empty_rule_set_reproduces_the_file(path):
    """Byte for byte, including the buckets that do not parse.

    Deliberately broken input matters *more* here, not less: a file the user
    was in the middle of editing is exactly what a formatter must not mangle,
    and it is where the tree is least like the source.

    "Byte for byte" is measured against the input **through the emit
    boundary**, not against the input, and the distinction is the whole
    content of ``pssfmt.finish``. ``insert_final_newline`` and ``line_ending``
    are file-level style options that were always meant to change files; they
    just did not, so this assertion read as byte identity for two phases. It
    is exactly as strong either way -- ``finish`` is a projection, so
    comparing against it still catches any byte the rule layer moves -- and
    only one of the two spellings is true.
    """
    src = read(path)
    assert format_source(src, registry=EMPTY) == finish(src, DEFAULT_STYLE)


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_it_agrees_with_the_null_formatter(path):
    """Both could be wrong; they are unlikely to be wrong identically.

    The null formatter reports the tokens its walk stepped past
    (``Result.skipped``) and the rule layer cannot, because a token span
    covers them without noticing. So where the two agree, the span route
    covered the gap; where they disagree, this names the file.
    """
    from pssfmt.null import format_null

    src = read(path)
    assert (format_source(src, registry=EMPTY)
            == finish(format_null(src).text, DEFAULT_STYLE))


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_no_file_trips_the_fail_safe(path):
    """``P1-3`` over the new entry point.

    A pass here means the verifier found no token change and no instability,
    rather than that the fail-safe quietly handed the input back -- which is
    the same output and a completely different fact, so it is asserted
    separately.
    """
    src = read(path)
    result = format_safely(src, formatter=lambda s: format_source(s, registry=EMPTY))
    assert result.ok, (
        "%s tripped the fail-safe: %s"
        % (ident(path), result.error or list(result.violations)))
    assert result.text == finish(src, DEFAULT_STYLE)


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_the_only_thing_the_style_can_move_is_the_emit_boundary(path):
    """A containment claim, and the second thing ``P4-1`` needed pinned.

    A cramped width and tab indentation would visibly reflow anything being
    laid out rather than reproduced, so with nothing registered the output
    must be independent of all of it. That was once spelled "the style cannot
    move a byte", with a note that it should be *deleted* rather than weakened
    once ``P3-2`` landed. It is neither: the emit boundary is a place the
    style legitimately reaches with no rule involved, so the claim is restated
    to say which place, which is a stronger thing to assert than nothing.

    ``line_ending`` and ``insert_final_newline`` are held at their defaults
    here on purpose -- varying them would only re-test ``finish`` -- while
    every option a *rule* consults is pushed to an extreme.
    """
    src = read(path)
    cramped = Style(print_width=20, indent_width=8, use_tabs=True, max_blank_lines=0)
    assert (format_source(src, style=cramped, registry=EMPTY)
            == finish(src, cramped))


def test_the_shipped_registry_is_not_the_one_under_test():
    """The premise of every assertion above, made explicit.

    These tests are about the **empty** rule set, and they stay meaningful
    only while ``EMPTY`` and the shipped registry are different things. Once
    ``P3-2`` landed, the shipped registry reformats; if this file were ever
    pointed at it by accident it would compare the real formatter's output
    against its input and call the difference a failure -- or, worse, pass
    because nothing was registered after all.

    The shipped rule set has its own corpus gate in ``test_tier1_corpus.py``, which
    asserts the properties that survive reformatting rather than byte
    identity.
    """
    assert len(REGISTRY) > 0, (
        "the shipped registry is empty, so this file and test_tier1_corpus.py "
        "are testing the same thing and one of them is not doing its job")
    assert len(EMPTY) == 0

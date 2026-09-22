"""``T-20`` -- the shipped rule set over the corpus (``P3-2``).

The gate changes shape here, and that is the point of the file.

Until ``P3-2`` the formatter reproduced its input, so the corpus test could
assert **byte identity** -- the strongest possible oracle, and free. Tier 1
reformats, so byte identity is no longer the right question and asserting it
would only invite weakening the rules to keep the test green.

What replaces it is ``PLAN.md`` section 7.1's tiers 2 through 4, which need no
hand-authored expected output either:

* **token equivalence** -- the output re-lexes to the same tokens;
* **idempotence** -- formatting the output again changes nothing;
* **no new parse errors**;
* and, above all, **the fail-safe never fires**, which is a different claim
  from "the output was fine": a tripped fail-safe returns the input, so a test
  comparing output to input would pass on the one file where the formatter
  had gone wrong.

Plus the style properties ``docs/style.rst`` measured as unanimous, which the
output must now satisfy rather than merely preserve.

Byte identity has not disappeared -- it moved to the *empty* rule set, in
``test_rule_fallback.py``, where it is still exactly right. The hand-written
counterpart to this file, where a failure names a construct rather than a
corpus file, is ``tests/test_tier1.py``.

**Fails when the corpus is missing; does not skip** (``C-8``).
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.finish import finish  # noqa: E402
from pssfmt.rules import REGISTRY, format_source  # noqa: E402
from pssfmt.style import DEFAULT_STYLE  # noqa: E402
from pssfmt.verbatim import verbatim_lines  # noqa: E402
from pssfmt.verify import format_safely  # noqa: E402
from support import (CORPUS_ROOT, CORPUS_SOURCE, corpus_files,  # noqa: E402
                     lone_brace_offenders, tab_indent_offenders,
                     trailing_whitespace_offenders)

pytestmark = [pytest.mark.corpus, pytest.mark.integration]

FILES = corpus_files()

#: The corpus files Tier 1 changes, and why. Pinned as a set so that the
#: *blast radius* of a rule change is visible in a diff rather than buried in
#: a count -- a rule that suddenly reformats twenty more files is a finding
#: whether or not each change is individually defensible.
#:
#: Every entry is one of three things: an empty body written ``{ }``, a body
#: written on one line, or a member the author indented to a column that is
#: not the body's. All three are decided by ``docs/style.rst``.
REFORMATTED = {
    # ``S-3``. The corpus's one *inline* anonymous activity sequence block --
    # `{ copy; chk; }` inside a `parallel` -- opens out; the other seven are
    # already open. It used to decline, on the grounds that a headerless block
    # emits a line containing only `{` and `docs/style.rst` measures braces as
    # attached. `S-3` decided that the brace rule is about a brace and *its
    # header*, and that this construct has none -- so it is the one documented
    # exception rather than a violation, and `lone_brace_offenders` now knows
    # the difference.
    #
    # The visible diff is three lines. What it actually buys is the two
    # traversals inside, which were unreachable behind the decline.
    "example2/concurrent_dma_a.pss",
    "example2/dma_types_pkg.pss",
    "example2/mem_c.pss",
    "example2/spi_types_pkg.pss",
    "language-ref/activity_shapes.pss",
    "language-ref/behavioral_coverage.pss",
    # ``S-12``, and the whole of what the list brace moves in this corpus is
    # one line::
    #
    #     unique { chans };   ->   unique {chans};
    #
    # A `{` that delimits a **list** rather than opening a body, so it is
    # `Site.LIST_BRACE_*` and not the `Site.BRACE_*` measured on 725
    # declaration bodies. Three instances across the corpus is not a
    # measurement either, so the value is argued: every list-like construct
    # PSS *has* measured is tight inside -- `f(a, b)` 765/767,
    # `packed_s<T, 32>` 137/137, `[1..4096]` 18/18 -- and borrowing the body's
    # answer would make a list the sole exception.
    #
    # This file also holds the corpus's only `if` and `foreach` constraints,
    # and `S-1` and `S-5` format both. Neither moves a byte: the author had
    # already written them the way the rules produce. Worth recording, because
    # "this file is in the list" now has two causes and only one of them is
    # visible in the diff.
    "language-ref/constraints.pss",
    "language-ref/coverage.pss",
    # The fourth kind, added by ``P3-5``, and the only entry here that is a
    # second-order effect rather than a direct one::
    #
    #     rand T   payload;
    #     rand int in [1..N] count;
    #
    # The author padded ``T`` to the width of ``int``. Until ``P3-5`` the
    # second line declined -- ``in`` was not in any vocabulary -- so the first
    # was a *lone* marked line, which ``infer`` reproduces because one line is
    # no evidence. Formatting the second line gives the group a second member,
    # and by the column ``infer`` actually measures (the declarator: ``payload``
    # at 9, ``count`` at 24) the two do not line up. So the block is ragged and
    # is set flush left, which is what ``docs/style.rst`` says ``infer`` does.
    #
    # Recorded rather than worked around: what the author aligned is the *type*
    # column, and inferring that from two lines of different shape is not
    # something one instance can justify teaching the alignment pass.
    #
    # ``P3-7`` added a *second* instance of exactly that shape to this file,
    # for exactly the same reason one item later::
    #
    #     wrapper_s<>               w_default;   // <> required
    #     wrapper_s<base_payload_s, 8> w_eight;
    #
    # Until templates were formatted the first line declined and kept its
    # padding. Both are formatted now, and the declarators sit at columns 30
    # and 33 -- the author padded towards a column without reaching one, which
    # is the case ``infer`` is specifically built not to honour. A genuine
    # table survives; ``T-26`` pins both directions so this stays a
    # measurement rather than an anecdote.
    "language-ref/extension_variants.pss",
    "language-ref/flow_basic.pss",
    # ``P3-11a``, and the whole of what function headers move in this corpus
    # is six lines across two files. Two of them are here, and each is a
    # measured majority applied to a construct that was simply not being
    # written out before::
    #
    #     import target C function int  sample_dut();   ->  int sample_dut()
    #     function int demo(array<int,8> a, int n)      ->  array<int, 8>
    #
    # The first is the corpus's *only* padded name column in 150 prototypes
    # (149 write one space), and it is the reason this item emits no column
    # stop there: a stop would let ``infer`` keep it, and one voice does not
    # decide a site. The second is ``Site.COMMA`` at 355/362, reaching a
    # template argument list inside a parameter list for the first time.
    #
    # ``P3-11b`` adds four more lines to this file, and three of them are one
    # finding rather than three changes: **a column stop that does not line up
    # costs a column that did.** ``infer`` requires every marked column in a
    # block to agree, so a line that gains a stop it cannot satisfy flushes
    # the whole line -- including a column the author really had::
    #
    #     p.x = a;      // visible to the caller: p is a handle
    #     a = 0;        // NOT visible to the caller: a is a copy
    #
    # Those two align their *comments*; the ``=`` stop this item adds does not
    # line up (``p.x `` is 4 columns, ``a `` is 2), so both columns go. Kept
    # rather than worked around, because the alternative is not adding the
    # stop -- and that stop is what saves five larger tables in four other
    # files. ``P3-11c`` is the note for per-column alignment, which is what
    # would let both survive.
    #
    # The fourth is a table this item breaks *by improving a line inside it*:
    # ``[8,16,32]:`` becomes ``[8, 16, 32]:`` and is now a column wider than
    # the arm above it, so the match block no longer lines up and is flushed.
    "language-ref/procedural_realization.pss",
    # The fifth kind, added by ``P3-11``: a function body written on one line.
    #
    #     function bit[32] ch_addr(int ch) { return base_addr + ch * 0x20; }
    #
    # The only one of the corpus's 118 functions written that way, and the
    # only file `P3-11` moves at all -- the other 117 are already open, which
    # is why the rule opens it rather than collapsing the rest. Identical
    # decision to ``P3-5``'s for constraint blocks, on identical evidence.
    "language-ref/resource_arbitration.pss",
    # ``P3-5``, and the only file constraints move at all -- the other 51
    # constraint declarations in the corpus were already written the way the
    # measurement says. See :data:`HOSTILE_BUT_VALID` below for why this one
    # is formatted rather than declined.
    "lexical/escaped_identifiers.pss",
    # ``P3-11b``, and the eleven files here are one change repeated: these are
    # generated PeakRDL output, and every one of them writes ``index*0x4``
    # inside a ``match`` arm. ``Site.MULTIPLICATIVE`` is spaced, and it is one
    # of the two defaults ``docs/style.rst`` decided by *argument* rather than
    # by measurement -- the corpus splits, and the split is a code generator
    # against the humans. So this is that argument's first bill, 27 lines of
    # it, and the files paying it are the generator's.
    #
    # They are here at all because ``match`` got a rule: these arms sat behind
    # 92 unformatted ``match`` statements, so nothing in them was reachable.
    "peakrdl/arrays_1d.pss",
    "peakrdl/arrays_nd.pss",
    "peakrdl/arrays_nd__index_helpers.pss",
    "peakrdl/basic.pss",
    "peakrdl/basic__hier.pss",
    "peakrdl/basic__no_pure.pss",
    "peakrdl/deep.pss",
    "peakrdl/params.pss",
    "peakrdl/reset.pss",
    "peakrdl/reset__reset_consts.pss",
    "peakrdl/wide.pss",
    # ``P3-8a``, and the only file native ``exec`` bodies move at all -- 28 of
    # them across 18 files were reproduced verbatim until this item, and 27 of
    # those files were already written the way the rules produce. What moves
    # here is one gap, and it is not an ``exec`` decision at all::
    #
    #     write32(h,  0xdead_beef);   ->   write32(h, 0xdead_beef);
    #
    # ``Site.COMMA`` at 355/362. The author aligned the two arguments of two
    # adjacent calls, and an argument list carries no column stop -- marking
    # one would mean deciding that a call's arguments are a table, which two
    # lines in one file cannot support.
    "language-ref/regs_and_mem.pss",
    # ``P3-7``, and the only file templates move at all: the other 33 of the
    # 34 files holding a template argument list are byte-identical after being
    # formatted for the first time. That is the real result of the item -- 137
    # argument lists newly written out by the formatter rather than copied,
    # and 33 files' worth of agreement that ``<`` and ``>`` are tight.
    #
    # What moves here is one gap, and it is the same near-miss as
    # ``extension_variants.pss`` above::
    #
    #     scalar_regs_c regs;
    #     transparent_addr_space_c<>  sys_mem;
    #
    # Two spaces where the neighbouring field has one, and the two declarators
    # are 13 columns apart, so there is no column to keep.
    "peakrdl/scalar_regs__base_address_top.pss",
    # ``P4-1``, and the only entry that is not a layout decision at all: this
    # file ends mid-token with no final newline, and the emit boundary now
    # adds one (``insert_final_newline``, previously a declared option that
    # nothing read). Every other byte is unchanged, and the file is still
    # *declined* by every rule -- see ``test_broken_input_is_still_not_mangled``,
    # which asserts exactly that by comparing against ``finish`` rather than
    # against the input.
    "pathological/truncated_mid_token.pss",
    # Already here before ``P3-11a``; the other four of that item's six lines
    # are in this file. ``addr_region_s <TRAIT>`` loses its space (the angle
    # site, 135/137) and ``write8 (`` loses its (147/150 tight) -- the latter
    # padded to line up with the ``write16(`` below it, which is a column
    # three-quarters of its own block does not keep.
    #
    # What it does *not* move is the point: the two wrapped prototypes at
    # lines 83 and 85 are declined and reproduced, because joining them is
    # 92 columns and there is no parameter-list break policy to do better.
    "stdlib/addr_reg_pkg.pss",
    "stdlib/executor_pkg.pss",
    "stdlib/std_pkg.pss",
    # The three ``pss31/`` files, and they are here for a reason none of the
    # entries above share: nothing about pssfmt changed. These files did not
    # *parse* until pss-corpus completed them (``U-8a``/``U-8c`` were withdrawn
    # as not-defects and the files were rewritten to declare their actions
    # inside a component), so every rule declined them and the fail-safe
    # reproduced them byte for byte. Now that they parse, Tier 1 sees them for
    # the first time.
    #
    # What moves is the first kind this set already records -- an empty body
    # written ``{ }``, and a body written on one line::
    #
    #     action write_a { }                ->  action write_a {}
    #     action write_a { rand int size; } ->  action write_a {
    #                                               rand int size;
    #                                           }
    # ``S-4`` **is not here, and that is the item's outcome.** It proposed
    # stripping a blank line immediately after `{` and immediately before `}`.
    # It was implemented, measured, and reverted::
    #
    #     blank line after `{`   41 -- 37 hand-written, 4 third-party, 0 generated
    #     blank line before `}`    5 -- all third-party
    #
    # Across 41 of the 92 files, and reproducible: `tools/style_survey.py`
    # reports both counts per voice. The first draft of this comment said
    # 47/43, which counted `pss31/` -- the files this project authored, and
    # the one voice `docs/style.rst` excludes from evidence as circular.
    #
    # The plan predicted a small radius on the grounds that the corpus could
    # not decide this. It can: *two independent human voices* write a blank
    # line after an opening brace, in 41 of the 92 files, and the code
    # generator writes none. Agreement across independent authors is what this
    # project counts as evidence -- it is the first claim `docs/style.rst`
    # makes about its own method -- so implementing the rule would have been
    # 33 files of diff taken against the strongest kind of evidence the corpus
    # produces.
    #
    # Deferred rather than un-started; `docs/status.rst` records it beside
    # `pool [4]` and the `select` weights. The argument for stripping them is
    # good (`gofmt`, `rustfmt` and `black` all do, and `clang-format`'s
    # `MaxEmptyLinesToKeep` does not apply at a block boundary) and will be
    # made again -- which is why the numbers are here rather than only in a
    # commit message.
    # ``S-16`` and its two consumers, ``S-7`` and ``S-17``: 23 files, and the
    # only entry in this set whose justification is a **number about the
    # output** rather than a rule applied to an input.
    #
    #     lines over ``print_width``   input 123   ->   output 51
    #
    # Every other item in phase S is a spacing decision whose radius is
    # whatever the corpus happens to contain. This one has a job, and that is
    # the measure of whether it did it. It more than halves the corpus's
    # over-width lines, and the 51 that remain are almost entirely hand-built
    # trailing-comment tables -- a comment cannot be moved off its line, so
    # nothing here can reach them.
    #
    # What moves, in three shapes:
    #
    # * **wrapped prototypes and calls join and re-break** (``S-17``). The
    #   nine ``example2`` files are this. Three carried hand-aligned parameter
    #   tables and lose them, which is ``S-16d``'s stated cost -- the release
    #   note points at ``// pssfmt off``.
    # * **generated lines past 80 are now broken** (``S-16``). The thirteen
    #   ``peakrdl`` files are one line each, at 82 columns, that nothing could
    #   break before.
    # * **a template parameter declaration is formatted** (``S-7``).
    #   ``sync_pkg.pss`` is ``int DEPTH=1`` gaining its spaces.
    "example2/check.pss",
    "example2/check_a.pss",
    "example2/dma_c.pss",
    "example2/fill.pss",
    "example2/fill_a.pss",
    "example2/pattern_word.pss",
    "example2/prog_read_a.pss",
    "example2/prog_write_a.pss",
    "example2/pss_top.pss",
    "peakrdl/access_matrix.pss",
    "peakrdl/alias.pss",
    "peakrdl/encode.pss",
    "peakrdl/encode__enums_off.pss",
    "peakrdl/endian.pss",
    "peakrdl/gaps.pss",
    "peakrdl/gaps__pad_tail.pss",
    "peakrdl/gaps__rsvd_prefix.pss",
    "peakrdl/keywords.pss",
    "peakrdl/msb0.pss",
    "peakrdl/scalar_regs.pss",
    "peakrdl/scalar_regs__base_address.pss",
    "peakrdl/widths.pss",
    "stdlib/sync_pkg.pss",
    "pss31/annotations.pss",
    "pss31/behavioral_coverage.pss",
    "pss31/templates_and_activity.pss",
}


def ident(path):
    return str(path.relative_to(CORPUS_ROOT)) if CORPUS_ROOT else str(path)


def read(path):
    # Binary, then decode explicitly: text mode translates newlines, and a
    # CRLF file would then pass for the wrong reason.
    return path.read_bytes().decode("utf-8")


def test_the_corpus_is_present():
    """The one test here that cannot vanish along with its input."""
    assert CORPUS_SOURCE != "none", (
        "no PSS corpus found. It is a declared ivpm dependency and should be "
        "at packages/pss-corpus -- run `ivpm update`, or set PSS_CORPUS.")
    assert len(FILES) >= 50, (
        "%d files from %s -- too few to be the curated corpus"
        % (len(FILES), CORPUS_SOURCE))


def test_there_are_rules_to_test():
    """Guards the guard. Every test below would pass on an empty registry.

    They would pass by testing the ``P3-1`` fallback all over again, having
    checked nothing about Tier 1 -- the same shape of failure as a suite whose
    corpus is missing, and just as quiet.
    """
    assert len(REGISTRY) > 0


# ---------------------------------------------------------------------------
# The oracles that need no expected output
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_no_file_trips_the_fail_safe(path):
    """Token equivalence, idempotence and parse errors, in one assertion.

    The second assertion is the one that matters. A tripped fail-safe returns
    the *input*, so a test that only compared output to input would pass on
    precisely the file where something went wrong.
    """
    src = read(path)
    result = format_safely(src, formatter=format_source,
                           allow_dropped_semicolons=True)
    assert result.ok, (
        "%s tripped the fail-safe: %s"
        % (ident(path), result.error or list(result.violations)))


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_formatting_is_idempotent(path):
    """Asserted separately from the fail-safe, and deliberately so.

    ``format_safely`` checks idempotence and then hides the answer behind a
    fallback. Running it directly means a failure here reports *what* moved on
    the second pass, which is the only thing that makes an oscillating rule
    findable.
    """
    once = format_source(read(path))
    assert format_source(once) == once


#: The one file under ``lexical/`` or ``pathological/`` that is not malformed.
#:
#: It is *hostile* -- ``\\top-level_c``, ``\\busa+index``, escaped identifiers
#: that swallow whatever follows them -- and it is also the only file in either
#: directory the parser accepts with **zero** error nodes. So it is valid PSS,
#: and from ``P3-5`` it contains a construct the formatter accounts for
#: completely: ``constraint \\c1 { \\busa+index > 0; }``, which is opened out
#: like the other 31 named constraint blocks in the corpus.
#:
#: Excluded here rather than the rule being narrowed, because the property this
#: test defends is "decline what you cannot account for", not "never touch a
#: file with a difficult name in it". What must still hold for it is checked
#: below and is the part that matters: every token survives, and every escaped
#: identifier survives character for character.
HOSTILE_BUT_VALID = "lexical/escaped_identifiers.pss"


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_broken_input_is_still_not_mangled(path):
    """Malformed input matters more here, not less.

    A file the user is halfway through editing is what a formatter must not
    damage, and it is where the tree least resembles the source. Tier 1
    declines to lay out a construct it cannot account for, so these come back
    intact rather than reformatted.

    "Intact" is measured through the emit boundary, which is the difference
    between *no rule touched this* and *no byte changed*. One pathological
    file ends with no final newline and gains one; that is a file-level style
    option doing its job, not a rule guessing at a broken tree, and comparing
    against :func:`~pssfmt.finish.finish` says so while still failing on any
    byte a rule moves.
    """
    src = read(path)
    result = format_safely(src, formatter=format_source,
                           allow_dropped_semicolons=True)
    assert result.ok
    if ident(path) == HOSTILE_BUT_VALID:
        return
    if "pathological" in ident(path) or "lexical" in ident(path):
        assert result.text == finish(src, DEFAULT_STYLE), (
            "%s was reformatted despite being deliberately malformed; Tier 1 "
            "is supposed to decline rather than guess" % ident(path))


def test_the_hostile_file_keeps_every_escaped_identifier():
    """What :data:`HOSTILE_BUT_VALID` gives up byte-identity for.

    An escaped identifier runs to the next whitespace and swallows anything
    printable on the way, so it is the construct a formatter is most likely to
    damage while producing output that looks entirely reasonable. Checked as a
    multiset so that a *moved* identifier still passes and a mangled, merged or
    dropped one cannot.
    """
    from pssparser import cst as _cst

    matching = [p for p in FILES if ident(p) == HOSTILE_BUT_VALID]
    if not matching:
        pytest.skip("%s not in this corpus" % HOSTILE_BUT_VALID)
    src = read(matching[0])

    def escaped(text):
        return sorted(t.text for t in _cst.parse(text).tokens
                      if t.type_name == "ESCAPED_ID")

    before = escaped(src)
    assert before, "the sample is supposed to be full of these"
    assert escaped(format_source(src)) == before


# ---------------------------------------------------------------------------
# The style the output must now have, not merely preserve
# ---------------------------------------------------------------------------
#
# All three ask about lines the formatter *composed*, and skip the ones it
# copied. A target-template ``exec`` body is C or SystemVerilog carried inside
# a string, emitted byte-for-byte by ``formatter.md`` section 4.3; a claim
# about PSS style applied there is a claim about somebody else's language, and
# the only way to satisfy it would be the corruption 4.3 forbids.
#
# No corpus file reaches that case today -- the one target template in the 92
# is tidy -- which is exactly why the exemption is exercised by hand in
# ``T-27`` instead. A gate that is green because its input never reaches the
# case is the shape ``P3-6``'s ``extend`` came in.


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_the_output_has_no_trailing_whitespace(path):
    """``docs/style.rst``: 0 of 4856 lines. Unanimous across every voice."""
    out = format_source(read(path))
    offenders = trailing_whitespace_offenders(out, verbatim_lines(out))
    assert not offenders, "%s: trailing whitespace on lines %s" % (
        ident(path), offenders[:10])


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_the_output_never_indents_with_a_tab(path):
    """Also 0 of 4856, and ``use_tabs`` defaults to false."""
    out = format_source(read(path))
    offenders = tab_indent_offenders(out, verbatim_lines(out))
    assert not offenders, "%s: tab indentation on lines %s" % (
        ident(path), offenders[:10])


#: Lines past ``print_width`` in the corpus, before and after formatting.
#:
#: The number ``S-16`` is judged by, and the only figure in this suite that is
#: a property of the **output** rather than of an input. Every other rule in
#: the style has a radius -- whatever the corpus happens to contain. Line
#: breaking has a *job*, so the measure of whether it did it is whether the
#: over-width lines went down.
#:
#: Pinned as an inequality with a floor rather than as an exact number,
#: because the exact number moves whenever any rule changes a line's width and
#: that is not a regression. What *is* a regression is the ratio getting
#: worse, and the floor is what catches a change that quietly stops breaking.
OVER_WIDTH_IN_THE_INPUT = 123
OVER_WIDTH_CEILING = 55


def test_line_breaking_reduces_the_over_width_lines():
    """``S-16``'s reason for existing, measured over 92 real files.

    The 51 or so that remain are almost entirely hand-built trailing-comment
    tables. Nothing here can reach those: a comment cannot be moved off the
    line it annotates, so the only way to bring one inside the width would be
    to reflow the comment -- which ``docs/style.rst`` commits to never doing.

    If this fails *low*, the ceiling wants lowering and the item got better.
    If it fails high, something stopped breaking.
    """
    before = sum(len(line) > DEFAULT_STYLE.print_width
                 for path in FILES for line in read(path).splitlines())
    after = sum(len(line) > DEFAULT_STYLE.print_width
                for path in FILES
                for line in format_source(read(path)).splitlines())

    assert before == OVER_WIDTH_IN_THE_INPUT, (
        "the corpus changed; re-measure the baseline before reading the "
        "assertion below as a regression (%d, was %d)"
        % (before, OVER_WIDTH_IN_THE_INPUT))
    assert after <= OVER_WIDTH_CEILING, (
        "%d lines are past print_width after formatting, against a ceiling "
        "of %d. Line breaking has stopped reaching something it used to."
        % (after, OVER_WIDTH_CEILING))
    assert after < before // 2, (
        "formatting no longer halves the corpus's over-width lines "
        "(%d -> %d)" % (before, after))


@pytest.mark.parametrize("path", FILES, ids=ident)
def test_the_output_never_puts_a_brace_on_its_own_line(path):
    """K&R, 732 of 733. Allman does not occur in the corpus and must not be
    introduced by the formatter."""
    out = format_source(read(path))
    offenders = lone_brace_offenders(out, verbatim_lines(out))
    assert not offenders, "%s: lone opening brace on lines %s" % (
        ident(path), offenders[:10])


# ---------------------------------------------------------------------------
# Blast radius
# ---------------------------------------------------------------------------


def test_the_set_of_files_tier_1_changes_is_the_expected_one():
    """Which files move, not how many.

    A rule that starts reformatting files it did not touch before is worth
    looking at even when every individual change is defensible, and a count
    would not say which ones. Update ``REFORMATTED`` deliberately, having read
    the diffs -- that edit is the record that somebody did.
    """
    changed = {ident(p) for p in FILES if format_source(read(p)) != read(p)}
    assert changed == REFORMATTED, (
        "newly reformatted: %s\nno longer reformatted: %s"
        % (sorted(changed - REFORMATTED), sorted(REFORMATTED - changed)))

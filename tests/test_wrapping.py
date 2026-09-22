"""``T-57``–``T-60`` -- list line breaking (``S-16``) and its consumers (``S-17``).

The last subsystem in the style, and the only item in phase S that built one
rather than applying a decision through a seam that already existed. Every
other rule here is a ``Site`` and a measured default; this one is a policy
over *where* a construct may break, which nothing in the rule layer had.

What the corpus can say about it is almost nothing, and that shapes the file.
There is no wrapped argument list in the corpus that a rule reached, because
every construct holding one was declined until now -- so the defaults are
argued, not measured, and the tests below are crafted. What the corpus *does*
provide is the property that matters most and is checked at the bottom: the
number of lines over ``print_width`` must go **down**.

The three tests worth reading first
------------------------------------
* **a list that fits is byte-identical to what it was before wrapping
  existed.** A policy for lists that do not fit must not move one that does.
* **the same call written on one line and across four produce the same
  output.** That is what makes the result a function of content rather than of
  the author's whitespace, and it is the whole of why ``S-17`` is correct
  rather than merely possible.
* **each option changes real output.** Two new configuration keys, and
  ``P4-2``'s lesson was that two of the original twelve were read by nothing.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pssparser")

from pssfmt.rules import format_source  # noqa: E402
from pssfmt.style import (DEFAULT_STYLE, BreakMode, Construct,  # noqa: E402
                          PackMode, Site, Spacing, Style)
from pssfmt.verify import format_safely, verify  # noqa: E402

pytestmark = pytest.mark.unit


def fmt(src: str, style: Style = None) -> str:
    return format_source(src, style=style) if style else format_source(src)


def in_function(*body: str) -> str:
    return ("component c {\n    function void g() {\n"
            + "".join("        %s\n" % b for b in body)
            + "    }\n}\n")


LONG = ('message(NONE, "a call the author wrapped, which joins past the '
        'width", n, n, n);')


# ---------------------------------------------------------------------------
# T-57 -- the engine
# ---------------------------------------------------------------------------


class TestAListThatFitsDoesNotMove:
    """The property everything else rests on.

    ``S-16`` adds ``Line`` and ``SoftLine`` nodes where plain gap text used to
    be, and a ``Line`` renders as one space flat while a ``SoftLine`` renders
    as nothing -- which is exactly what the computed gaps were. So a list that
    fits comes out unchanged, and the wrap is *declined* wherever a style
    makes those gaps anything else.
    """

    @pytest.mark.parametrize("src", [
        "f(a, b);", "f(a, b, c);", "f();", "f(a);",
    ], ids=["two", "three", "empty", "one"])
    def test_it_is_byte_identical(self, src: str):
        assert fmt(in_function(src)) == in_function(src)

    def test_a_comma_tight_style_declines_the_wrap_entirely(self):
        """A gap of 0 after a separator is not what a ``Line`` renders flat,
        so the wrap is refused and the span is emitted as it always was.

        Pinned because the first version refused the wrap *mid-span* and left
        the ``SoftLine`` it had already emitted behind -- which, outside any
        group, renders as a break. The list broke after its opening bracket
        and nowhere else.
        """
        style = Style(spacing_overrides={Site.COMMA: Spacing(0, 0)})
        assert fmt(in_function("f(a, b);"), style) == in_function("f(a,b);")

    def test_a_style_that_spaces_inside_call_parens_declines_too(self):
        style = Style(spacing_overrides={
            Site.CALL_PAREN_OPEN: Spacing(0, 1),
            Site.CALL_PAREN_CLOSE: Spacing(1, 0)})
        out = fmt(in_function("f(a, b);"), style)
        assert "        f( a, b );\n" in out


class TestAListThatDoesNotFit:
    def test_every_element_breaks(self):
        """16a, option A: all or nothing. A ``Group`` already means this --
        flat if the whole list fits, else *every* ``Line`` inside breaks --
        which is why choosing it cost nothing to build."""
        assert fmt(in_function(LONG)) == in_function(
            "message(",
            '    NONE,',
            '    "a call the author wrapped, which joins past the width",',
            "    n,",
            "    n,",
            "    n",
            ");")

    def test_the_closing_bracket_returns_to_the_opening_line_s_column(self):
        """The leading break goes inside the indent and the trailing one
        outside. Reversed, the ``)`` lands under the items -- the classic
        version of this bug, invisible until a list actually breaks."""
        out = fmt(in_function(LONG))
        assert "\n        );\n" in out

    def test_the_continuation_indent_is_consulted(self):
        style = Style(continuation_indent=2)
        out = fmt(in_function(LONG), style)
        assert "\n          NONE,\n" in out

    def test_a_one_item_list_is_never_broken(self):
        """Breaking it puts a single argument on a line of its own, which is
        longer than the line it was trying to shorten."""
        long_call = 'f("%s");' % ("x" * 80)
        assert fmt(in_function(long_call)) == in_function(long_call)

    def test_a_nested_list_stays_flat(self):
        """One outer list, two inner ones, and only the outer breaks.

        This is the ordinary shape of real code rather than a corner case,
        and refusing it -- which the first version did -- left the call
        joined onto a 96-column line.
        """
        out = fmt(in_function(
            "write32(make_handle_from_handle(base, i * 4), "
            "pattern_word(pattern, seed, i));"))
        assert "            make_handle_from_handle(base, i * 4),\n" in out
        assert "            pattern_word(pattern, seed, i)\n" in out

    def test_two_sibling_lists_decline(self):
        """``emit_span`` takes one wrap, so a span with two lists would have
        to choose -- and choosing by position answers an undecided policy
        question by accident. Both are emitted flat, as before ``S-16``."""
        src = ("x = averylongfunctionname(alpha, beta) + "
               "anotherlongfunction(gamma, delta);")
        assert fmt(in_function(src)) == in_function(src)

    @pytest.mark.parametrize("width", [40, 60, 80, 100, 200])
    def test_it_is_idempotent_at_several_widths(self, width: int):
        style = Style(print_width=width)
        once = fmt(in_function(LONG), style)
        assert fmt(once, style) == once

    def test_no_trailing_comma_is_added(self):
        """16c. Adding one changes the token stream, which is the thing this
        formatter does not do -- and ``optional_semicolon`` needed the
        verifier taught about it. This item does not acquire a second
        exception."""
        assert ",\n        );" not in fmt(in_function(LONG))

    def test_no_token_is_lost(self):
        src = in_function(LONG)
        assert list(verify(src, fmt(src))) == []


# ---------------------------------------------------------------------------
# T-59 -- the two options
# ---------------------------------------------------------------------------


class TestTheOptions:
    """``P4-2``'s obligation: a key the configuration accepts is a promise.

    Both of these were already in the layout IR and read by nothing --
    ``Fill`` and ``Align`` have existed since ``P2``. That is what made
    all-or-nothing cheap to *ship* and the alternative cheap to *offer*.
    """

    def test_bin_pack_packs(self):
        style = Style(pack_arguments=PackMode.BIN_PACK)
        out = fmt(in_function(LONG), style)
        assert out != fmt(in_function(LONG))
        # Greedy: more than one argument survives on a line.
        assert any(line.count(",") > 1 for line in out.splitlines())

    def test_align_after_open_bracket_aligns(self):
        style = Style(align_after_open_bracket=True)
        out = fmt(in_function(LONG), style)
        assert out != fmt(in_function(LONG))

    def test_the_two_options_are_independent(self):
        both = fmt(in_function(LONG),
                   Style(pack_arguments=PackMode.BIN_PACK,
                         align_after_open_bracket=True))
        one = fmt(in_function(LONG), Style(pack_arguments=PackMode.BIN_PACK))
        assert both != one

    def test_the_break_policy_follows_pack_arguments(self):
        assert DEFAULT_STYLE.break_policy_for(Construct.ARGUMENT_LIST) \
            is BreakMode.FIT
        packed = Style(pack_arguments=PackMode.BIN_PACK)
        assert packed.break_policy_for(Construct.ARGUMENT_LIST) \
            is BreakMode.FILL

    def test_a_per_construct_override_still_wins(self):
        """The shape ``formatter.md`` section 3.2 argued for and no rule
        could ask for: pack range lists, explode argument lists."""
        style = Style(break_overrides={Construct.RANGE_LIST: BreakMode.FILL})
        assert style.break_policy_for(Construct.RANGE_LIST) is BreakMode.FILL
        assert style.break_policy_for(Construct.ARGUMENT_LIST) is BreakMode.FIT

    @pytest.mark.parametrize("style", [
        Style(pack_arguments=PackMode.BIN_PACK),
        Style(align_after_open_bracket=True),
        Style(pack_arguments=PackMode.BIN_PACK, align_after_open_bracket=True),
    ], ids=["bin-pack", "align", "both"])
    def test_every_option_is_idempotent(self, style):
        once = fmt(in_function(LONG), style)
        assert fmt(once, style) == once


# ---------------------------------------------------------------------------
# T-60 -- S-17, the consumers
# ---------------------------------------------------------------------------


class TestWhatTheAuthorWroteDoesNotDecideTheOutput:
    """``S-17``'s defining property, and the reason it had to wait.

    Joining a wrapped statement was always possible -- ``emit_span`` discards
    newlines. What was missing was somewhere for the joined line to break, so
    joining produced 86 to 108 columns and the construct was reproduced
    instead. With a break policy the join is safe, and the output stops being
    a function of the author's whitespace.
    """

    def test_one_line_and_four_produce_the_same_output(self):
        one = in_function(LONG)
        many = in_function(
            'message(NONE,',
            '        "a call the author wrapped, which joins past the width",',
            "    n, n,",
            "            n);")
        assert fmt(one) == fmt(many)

    def test_a_wrapped_prototype_joins_and_re_breaks(self):
        wrapped = ("component c {\n"
                   "    target function void check(\n"
                   "        addr_handle_t  base,\n"
                   "        bit[32]        nbytes,\n"
                   "        mem_pattern_e  pattern,\n"
                   "        bit[32]        seed) {\n"
                   "        int x;\n"
                   "    }\n"
                   "}\n")
        flat = ("component c {\n"
                "    target function void check(addr_handle_t base, "
                "bit[32] nbytes, mem_pattern_e pattern, bit[32] seed) {\n"
                "        int x;\n"
                "    }\n"
                "}\n")
        assert fmt(wrapped) == fmt(flat)
        assert "        addr_handle_t base,\n" in fmt(wrapped)

    def test_a_hand_aligned_parameter_table_is_lost_and_that_is_16d(self):
        """The accepted cost, stated as a test so it is a decision rather
        than a surprise. Three such tables are in the corpus; the release
        note points at ``// pssfmt off``, which is what keeps one."""
        out = fmt("component c {\n"
                  "    target function void check(\n"
                  "        addr_handle_t  base,\n"
                  "        bit[32]        nbytes) {\n"
                  "        int x;\n"
                  "    }\n"
                  "}\n")
        assert "addr_handle_t  base" not in out

    def test_a_hatch_keeps_the_table(self):
        out = fmt("component c {\n"
                  "    // pssfmt off\n"
                  "    target function void check(\n"
                  "        addr_handle_t  base,\n"
                  "        bit[32]        nbytes) { }\n"
                  "    // pssfmt on\n"
                  "}\n")
        assert "addr_handle_t  base," in out

    def test_a_wrapped_statement_with_no_list_joins_if_it_fits(self):
        """The guard is about **width**, not about whether the author
        wrapped. Joining is what ``emit_span`` is for; what it could not do
        before ``S-16`` is break the result."""
        assert fmt(in_function("x = alpha +", "    beta;")) == \
            in_function("x = alpha + beta;")

    def test_a_wrapped_statement_with_no_list_and_no_room_keeps_its_line(self):
        """The one case the author's wrap survives: nothing to break, and
        the joined form past the width. Emitting it anyway would be deciding
        by width and then violating it, which decides nothing."""
        long_name = "a_very_long_identifier_indeed_%s" % ("x" * 20)
        src = in_function("q = %s +" % long_name, "    %s;" % long_name)
        assert fmt(src) == src

    @pytest.mark.parametrize("src", [
        in_function(LONG),
        ("component c {\n    target function void check(\n"
         "        addr_handle_t  base,\n        bit[32] n) {\n"
         "        int x;\n    }\n}\n"),
    ], ids=["statement", "prototype"])
    def test_the_verifier_accepts_it(self, src: str):
        result = format_safely(src, formatter=format_source)
        assert result.ok, result.diagnostic()

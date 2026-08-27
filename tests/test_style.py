"""``T-16`` -- the resolved style policy, and its link back to the evidence.

``T-13`` (``tests/test_boundaries.py``) enforces that rules *consult* the
policy. These tests enforce that the policy is worth consulting: that every
key answers, that no site was added without the measured value it exists to
carry, and that the defaults still say what ``docs/style.rst`` says they say.

That last one is the point of the file. A style default is a number with a
provenance, and the provenance lives in three places -- the corpus, the
survey that measures it, and the page that publishes it. Nothing stops those
three from drifting apart except a test that reads all of them.

No corpus and no ``pssparser``: these are unit tests over constants.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from pssfmt.layout.align import AlignMode, GroupBoundary
from pssfmt.style import (
    DEFAULT_SPACING,
    DEFAULT_STYLE,
    BraceMode,
    BreakMode,
    Construct,
    LineEnding,
    Site,
    Spacing,
    Style,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent
STYLE_DOC = REPO_ROOT / "docs" / "style.rst"


# ---------------------------------------------------------------------------
# Totality -- every key answers
# ---------------------------------------------------------------------------


class TestEveryKeyAnswers:
    """A policy with a hole in it is a policy a rule has to branch around.

    The accessors are total over their key type by construction, so these
    tests exist for the case that construction changes: an accessor rewritten
    to consult a per-construct table without a fallback would still pass
    every rule test written so far, because v1 rules only touch a handful of
    constructs.
    """

    @pytest.mark.parametrize("construct", list(Construct), ids=lambda c: c.value)
    def test_construct_questions_are_total(self, construct: Construct):
        s = DEFAULT_STYLE
        assert isinstance(s.indent_for(construct), int)
        assert isinstance(s.continuation_for(construct), int)
        assert isinstance(s.brace_for(construct), BraceMode)
        assert isinstance(s.alignment_for(construct), AlignMode)
        assert isinstance(s.group_boundary_for(construct), GroupBoundary)
        assert isinstance(s.break_policy_for(construct), BreakMode)

    @pytest.mark.parametrize("site", list(Site), ids=lambda s: s.value)
    def test_every_site_has_a_measured_default(self, site: Site):
        """The failure this catches is adding a ``Site`` and no value for it.

        Which is easy to do -- the enum member is what a rule needs to
        compile, and the number is what it needs to be *right*.
        """
        assert site in DEFAULT_SPACING, (
            f"{site.value} has no entry in DEFAULT_SPACING. Add the measured "
            "value from docs/style.rst, or the rule using this site will "
            "raise KeyError at format time."
        )
        assert isinstance(DEFAULT_STYLE.spacing_for(site), Spacing)

    def test_no_default_without_a_site(self):
        """The other direction: a stale entry for a site that no longer exists."""
        assert set(DEFAULT_SPACING) == set(Site)

    def test_enum_values_are_unique(self):
        """``str``-valued enums silently alias on a duplicate value.

        Two members with the same string become the same member, and the
        second name becomes an alias for the first -- so a copy-paste slip in
        the table above would make one construct answer for another with no
        error anywhere.
        """
        for enum in (Construct, Site):
            names = [m.name for m in enum]
            values = [m.value for m in enum]
            assert len(set(values)) == len(names), f"{enum.__name__} has aliases"


# ---------------------------------------------------------------------------
# The defaults are the measured values
# ---------------------------------------------------------------------------

#: Maps each rule the survey reports to the policy value that carries it.
#: ``(Site, sides)`` -- the survey usually measures one side of a token, and
#: :class:`Spacing` stores each side independently. The two ``around '...'``
#: rules measure both sides at once, so both are checked; naming only one
#: would leave the other side unpinned and free to drift.
#:
#: Keys are exactly the ``UNANIMOUS`` dict in
#: ``tests/corpus/test_style_survey.py``, which is checked against the corpus
#: itself. This table is the last link in the chain: corpus -> survey ->
#: published page -> the number a rule actually emits.
SURVEY_RULE_TO_POLICY = {
    "lhs -> ';'": (Site.SEMICOLON, ("before",)),
    "lhs -> ','": (Site.COMMA, ("before",)),
    "',' -> rhs": (Site.COMMA, ("after",)),
    "around '::'": (Site.SCOPE_RESOLUTION, ("before", "after")),
    "around '.'": (Site.MEMBER_ACCESS, ("before", "after")),
    "'(' -> inside": (Site.CALL_PAREN_OPEN, ("after",)),
    "inside -> ')'": (Site.CALL_PAREN_CLOSE, ("before",)),
    "'[' -> inside": (Site.INDEX_BRACKET_OPEN, ("after",)),
    "inside -> ']'": (Site.INDEX_BRACKET_CLOSE, ("before",)),
    "callee -> '('": (Site.CALL_PAREN_OPEN, ("before",)),
    "control keyword -> '('": (Site.CONTROL_PAREN_OPEN, ("before",)),
    "'=' -> rhs": (Site.ASSIGN, ("after",)),
    "lhs -> '='": (Site.ASSIGN, ("before",)),
    "additive + - -> rhs": (Site.ADDITIVE, ("after",)),
    "lhs -> additive + -": (Site.ADDITIVE, ("before",)),
    "unary + - -> operand": (Site.UNARY, ("after",)),
    "lhs -> '{'": (Site.BRACE_OPEN, ("before",)),
    "':' inheritance -> rhs": (Site.COLON_INHERITANCE, ("after",)),
    "lhs -> ':' inheritance": (Site.COLON_INHERITANCE, ("before",)),
    "':' case/select item -> rhs": (Site.COLON_CASE_ITEM, ("after",)),
    "lhs -> ':' case/select item": (Site.COLON_CASE_ITEM, ("before",)),
    "type bracket '<' -> inside": (Site.TYPE_BRACKET_OPEN, ("after",)),
    "inside -> type bracket '>'": (Site.TYPE_BRACKET_CLOSE, ("before",)),
}


def _unanimous():
    """The corpus-checked rule table, imported without needing the corpus.

    ``tests/corpus/test_style_survey.py`` fails loudly when the corpus is
    absent, but its ``UNANIMOUS`` constant is a plain dict and reading it
    costs nothing. Importing it rather than restating it is the whole point:
    a restated table drifts silently.
    """
    import importlib.util

    path = REPO_ROOT / "tests" / "corpus" / "test_style_survey.py"
    spec = importlib.util.spec_from_file_location("_style_survey_consts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.UNANIMOUS


class TestDefaultsMatchTheEvidence:
    def test_every_unanimous_rule_is_mapped(self):
        """A survey rule with no policy value is a measurement going unused."""
        unmapped = set(_unanimous()) - set(SURVEY_RULE_TO_POLICY)
        assert not unmapped, (
            "docs/style.rst documents these as unanimous but no Site carries "
            f"them: {sorted(unmapped)}"
        )

    @pytest.mark.parametrize(
        "rule,expected", sorted(_unanimous().items()), ids=lambda x: str(x)
    )
    def test_the_default_is_the_measured_value(self, rule, expected):
        site, sides = SURVEY_RULE_TO_POLICY[rule]
        for side in sides:
            actual = getattr(DEFAULT_STYLE.spacing_for(site), side)
            assert actual == expected, (
                f"{rule}: the corpus says {expected}, {site.value}.{side} says "
                f"{actual}. Change docs/style.rst and the survey first; this "
                "table follows the evidence, not the other way round."
            )

    def test_the_two_argued_rules_went_to_the_humans(self):
        """The rules the corpus split on, decided against the code generator.

        Pinned separately because no measurement backs them -- if either
        default flips, it is because somebody changed their mind, and that
        should be a deliberate edit here and in ``docs/style.rst``.
        """
        assert DEFAULT_STYLE.spacing_for(Site.MULTIPLICATIVE) == Spacing(1, 1)
        assert DEFAULT_STYLE.spacing_for(Site.COLON_LABEL) == Spacing(1, 1)

    def test_print_width_matches_the_published_page(self):
        doc = STYLE_DOC.read_text(encoding="utf-8")
        match = re.search(r"``print_width`` defaults to \*\*(\d+)\*\*", doc)
        assert match, "docs/style.rst no longer states a print_width default"
        assert DEFAULT_STYLE.print_width == int(match.group(1))

    def test_layout_defaults_match_the_published_page(self):
        """Indent, tabs, braces and blank lines, as the Layout table states them."""
        assert DEFAULT_STYLE.indent_width == 4
        assert DEFAULT_STYLE.use_tabs is False
        assert DEFAULT_STYLE.brace_style is BraceMode.ATTACH
        assert DEFAULT_STYLE.max_blank_lines == 1
        assert DEFAULT_STYLE.alignment is AlignMode.INFER


# ---------------------------------------------------------------------------
# Gap composition
# ---------------------------------------------------------------------------


class TestGapComposition:
    """``max``, not sum -- so the result does not depend on evaluation order."""

    def test_a_non_site_token_contributes_nothing(self):
        assert DEFAULT_STYLE.gap(None, None) == 0
        assert DEFAULT_STYLE.gap(None, Site.ASSIGN) == 1
        assert DEFAULT_STYLE.gap(Site.ASSIGN, None) == 1

    def test_spaced_beside_tight_stays_spaced(self):
        """``x = -1``: the unary minus must not eat the space after ``=``."""
        assert DEFAULT_STYLE.gap(Site.ASSIGN, Site.UNARY) == 1

    def test_tight_beside_tight_is_tight(self):
        """``f(a);``"""
        assert DEFAULT_STYLE.gap(Site.CALL_PAREN_CLOSE, Site.SEMICOLON) == 0

    def test_the_two_paren_rules_differ(self):
        """The one place a bracket's spacing depends on what precedes it.

        ``if (x)`` against ``write32(x)`` -- two rules that look like one, and
        the reason ``Site`` distinguishes call parens from control parens.
        """
        assert DEFAULT_STYLE.gap(None, Site.CONTROL_PAREN_OPEN) == 1
        assert DEFAULT_STYLE.gap(None, Site.CALL_PAREN_OPEN) == 0

    def test_gap_is_symmetric_under_swapping_equal_sites(self):
        for site in Site:
            assert DEFAULT_STYLE.gap(site, site) == max(
                DEFAULT_STYLE.spacing_for(site).after,
                DEFAULT_STYLE.spacing_for(site).before,
            )


# ---------------------------------------------------------------------------
# The object itself
# ---------------------------------------------------------------------------


class TestStyleIsResolvedAndImmutable:
    def test_fields_cannot_be_assigned(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            DEFAULT_STYLE.print_width = 100  # type: ignore[misc]

    def test_overrides_cannot_be_mutated_through_the_caller_s_dict(self):
        """A Style built from a live dict must not change when that dict does.

        The failure mode is a config loader that reuses one dict across
        several resolved styles: without the defensive copy, editing it for
        the second file retroactively changes the first.
        """
        mutable = {Construct.COMPONENT_BODY: 2}
        style = Style(indent_overrides=mutable)
        mutable[Construct.ACTION_BODY] = 8
        assert style.indent_for(Construct.COMPONENT_BODY) == 2
        assert style.indent_for(Construct.ACTION_BODY) == 4

    def test_overrides_cannot_be_mutated_through_the_style(self):
        with pytest.raises(TypeError):
            DEFAULT_STYLE.indent_overrides[Construct.ACTION_BODY] = 8  # type: ignore[index]

    def test_an_override_wins_over_the_global(self):
        style = DEFAULT_STYLE.evolve(
            brace_overrides={Construct.CONSTRAINT_BODY: BraceMode.BREAK}
        )
        assert style.brace_for(Construct.CONSTRAINT_BODY) is BraceMode.BREAK
        assert style.brace_for(Construct.COMPONENT_BODY) is BraceMode.ATTACH

    def test_evolve_leaves_the_original_alone(self):
        narrow = DEFAULT_STYLE.evolve(print_width=60)
        assert narrow.print_width == 60
        assert DEFAULT_STYLE.print_width == 80

    def test_spacing_override_wins(self):
        style = DEFAULT_STYLE.evolve(
            spacing_overrides={Site.MULTIPLICATIVE: Spacing(0, 0)}
        )
        assert style.spacing_for(Site.MULTIPLICATIVE) == Spacing(0, 0)
        assert style.spacing_for(Site.ADDITIVE) == Spacing(1, 1)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"print_width": 0},
            {"print_width": -1},
            {"indent_width": -1},
            {"continuation_indent": -1},
            {"max_blank_lines": -1},
        ],
        ids=lambda k: str(k),
    )
    def test_a_nonsensical_value_is_rejected_at_construction(self, kwargs):
        """Loudly, and once -- not as a mystery in the layout engine later."""
        with pytest.raises(ValueError):
            Style(**kwargs)

    def test_negative_spacing_is_rejected(self):
        with pytest.raises(ValueError):
            Spacing(-1, 0)

    def test_enums_are_string_valued_for_config_and_diagnostics(self):
        """``P4-2`` maps ``.pssfmt`` keys onto these directly, and a failure
        message naming ``'attach'`` beats one naming an integer."""
        assert BraceMode.ATTACH == "attach"
        assert LineEnding.AUTO == "auto"
        assert Construct.COMPONENT_BODY == "component_body"
        assert Site.COLON_LABEL == "colon_label"


class TestTheStyleDoesNotImportTheWorld:
    def test_style_imports_without_pssparser(self, monkeypatch):
        """``P3-0`` lands before the rule layer and must not drag the parser in.

        Not a boundary anyone declared -- but the layout engine's independence
        (``T-9``) is worth nothing if the policy object beside it imports the
        parser, since every rule imports both.
        """
        import builtins
        import importlib
        import sys

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name.split(".")[0] == "pssparser":
                raise ImportError("pssparser is deliberately unavailable")
            return real_import(name, *args, **kwargs)

        for name in [m for m in sys.modules if m.startswith("pssfmt")]:
            monkeypatch.delitem(sys.modules, name, raising=False)
        monkeypatch.setattr(builtins, "__import__", blocked)

        style = importlib.import_module("pssfmt.style")
        assert style.DEFAULT_STYLE.indent_width == 4

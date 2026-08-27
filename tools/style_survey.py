#!/usr/bin/env python3
"""Measure the de-facto style of a PSS corpus, so ``Q-4`` is settled by
rerunning a command rather than by argument.

    python tools/style_survey.py [CORPUS_ROOT] [--json]

``CORPUS_ROOT`` defaults to the same discovery order the test suite uses:
``$PSS_CORPUS``, then ``packages/pss-corpus``, then a sibling checkout.

Why this exists
---------------
``docs/style.rst`` states a canonical style, and almost every rule in it is a
measurement rather than a preference.  A measurement that cannot be
reproduced is an assertion, so this is the program that produced the numbers
in that document, kept runnable.

Two rules it follows, both learned by getting them wrong first:

**Tokens, never regexes.**  A ``grep`` for ``\\[[0-9]+:[0-9]+\\]`` over this
corpus reports 111 bit-slices.  Ninety-eight of them are inside trailing
comments -- ``peakrdl`` documents field ranges as ``// [31:0] sw=rw`` while
the code says ``bit[32] f;``.  The real count in code is 2.  A regex cannot
tell code from commentary; the token stream cannot confuse them.

**Group by voice, not by file.**  Agreement across independent authors is
evidence.  Agreement within one author's files is one opinion counted many
times, and the largest bucket here is a single author's.

Ambiguities that must be resolved before a figure means anything -- each of
these produced a wrong answer on the first attempt:

``*``
    Mostly not multiplication.  ``import pkg::*`` and the ``bind x *;``
    wildcard together outnumber real multiplication 4:1.
``<`` ``>``
    Mostly not comparison.  PSS generic types are lowercase (``packed_s``,
    ``reg_c``), so a name-shape heuristic misclassifies type-parameter
    brackets as comparisons.  They are matched as bracket pairs here.
``:``
    Four unrelated constructs -- bit-slice, case item, inheritance, label --
    with four different conventions.  Lumped together they look like a
    disagreement; separated, each is internally consistent.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

try:
    from pssparser import tokens as T
except ImportError:  # pragma: no cover
    sys.exit("style_survey needs pssparser: pip install -e packages/pssparser")

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Bucket -> voice.  ``lexical`` and ``pathological`` are deliberately absent:
#: they are torture input, so their layout carries no style signal.
VOICE_OF = {
    "example2": "hand-written",
    "language-ref": "hand-written",
    "stdlib": "third-party",
    "peakrdl": "generated",
    "pss31": "ours",
}

#: ``ours`` is authored by this project *for* this corpus, so it is reported
#: separately and never counted as evidence -- deriving a style from files we
#: wrote to demonstrate the style is circular.
EVIDENCE_VOICES = ("hand-written", "third-party", "generated")

CONTROL_KEYWORDS = {"if", "while", "foreach", "for", "switch", "repeat",
                    "match", "select"}
DECL_KEYWORDS = {"component", "struct", "action", "buffer", "stream", "state",
                 "resource", "pool", "enum", "extend", "package"}
ADDITIVE = {"+", "-"}
MULTIPLICATIVE = {"*", "/", "%"}
COMPARISON = {"<", ">", "<=", ">=", "==", "!="}
LOGICAL = {"&&", "||", "&", "|", "^", "<<", ">>"}

#: A ``+``/``-`` directly after one of these is unary, not binary.
PREFIX_CONTEXT = {"(", ",", "=", "[", "{", ";", "return", "&&", "||", "+",
                  "-", "*", "/", "==", "!=", "<", ">", "<=", ">=", "in", ":",
                  "..", "?", "->"}


def find_corpus(explicit=None):
    """Same discovery order as ``tests/support.py``."""
    if explicit:
        return Path(explicit)
    env = os.environ.get("PSS_CORPUS")
    for cand in ([Path(env)] if env else []) + [
        REPO_ROOT / "packages" / "pss-corpus",
        REPO_ROOT.parent / "pss-corpus",
    ]:
        if cand.is_dir():
            curated = cand / "curated"
            return curated if curated.is_dir() else cand
    sys.exit("no corpus found; set $PSS_CORPUS")


class Survey:
    def __init__(self):
        self.files = 0
        self.lines = 0
        self.line_len = []
        self.tab_indent = 0
        self.trailing_ws = 0
        self.blank_runs = collections.Counter()
        self.indent_steps = collections.Counter()
        self.brace = collections.Counter()      # 'same-line' / 'own-line'
        self.comment = collections.Counter()    # '//' / '/* */'
        self.align = collections.Counter()      # aligned / ragged runs
        #: rule name -> Counter of observed whitespace gaps
        self.gap = collections.defaultdict(collections.Counter)

    # -- helpers ---------------------------------------------------------
    def note(self, rule, gap):
        self.gap[rule][gap] += 1


def type_bracket_indices(toks):
    """Indices of ``<`` and its matching ``>`` when they delimit type
    parameters, found by matching the pair rather than by guessing from the
    preceding name -- PSS generic types are lowercase, so name shape does not
    distinguish ``reg_c<...>`` from ``a < b``."""
    found = set()
    for i, t in enumerate(toks):
        if t.text != "<" or i == 0:
            continue
        if toks[i - 1].type_name not in ("ID", "ESCAPED_ID"):
            continue
        depth = 0
        for j in range(i, min(len(toks), i + 48)):
            x = toks[j].text
            if x == "<":
                depth += 1
            elif x == ">":
                depth -= 1
                if depth == 0:
                    nxt = toks[j + 1] if j + 1 < len(toks) else None
                    # ':' belongs here: a parameterized type declaration is
                    # routinely followed by its base --
                    # `struct addr_region_s<struct TRAIT : ...> : base_s`.
                    # Omitting it misfiled every generic in the stdlib as a
                    # comparison, which is the whole third-party voice.
                    if nxt is not None and (
                        nxt.text in ("{", ",", ")", ";", ">", ":", "::")
                        or nxt.type_name in ("ID", "ESCAPED_ID")
                    ):
                        found |= {i, j}
                    break
            elif x in (";", "{", "}"):
                break
    return found


def colon_kind(toks, i, bracket_depth):
    """Which of the four unrelated ``:`` constructs this is."""
    if bracket_depth > 0:
        return "':' bit-slice [a:b]"
    if toks[i - 1].text == "]":
        return "':' case/select item"
    if toks[max(0, i - 2)].text in DECL_KEYWORDS:
        return "':' inheritance"
    return "':' label"


def star_kind(toks, i):
    """``*`` is usually not multiplication in PSS."""
    if i and toks[i - 1].text == "::":
        return None                      # import pkg::*
    if toks[i + 1].text == ";":
        return None                      # bind foo *;
    prev = toks[i - 1] if i else None
    if prev is None:
        return None
    if prev.type_name in ("ID", "ESCAPED_ID") or prev.text in (")", "]") \
            or (prev.text and prev.text[0].isdigit()):
        return "multiplicative * / %"
    return None


def analyse(sv: Survey, path: Path):
    ts = T.tokenize(path.read_bytes())
    text = ts.text
    toks = [t for t in ts.tokens if not t.is_trivia]
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    sv.files += 1
    sv.lines += len(lines)

    blank = 0
    for raw in lines:
        body = raw.rstrip("\r")
        if not body.strip():
            blank += 1
            continue
        if blank:
            sv.blank_runs[blank] += 1
            blank = 0
        sv.line_len.append(len(body))
        indent = body[: len(body) - len(body.lstrip())]
        if "\t" in indent:
            sv.tab_indent += 1
        if body != body.rstrip():
            sv.trailing_ws += 1

    for t in ts.tokens:
        if t.channel == T.CHANNEL_SL_COMMENT:
            sv.comment["//"] += 1
        elif t.channel == T.CHANNEL_ML_COMMENT:
            sv.comment["/* */"] += 1

    by_line = collections.defaultdict(list)
    for t in toks:
        by_line[t.line].append(t)

    # indent step per nesting level
    depth_indent = collections.defaultdict(collections.Counter)
    depth = 0
    for lineno in sorted(by_line):
        row = by_line[lineno]
        d = depth - 1 if row[0].text == "}" else depth
        raw = lines[lineno - 1] if lineno - 1 < len(lines) else ""
        if d >= 0:
            depth_indent[d][len(raw) - len(raw.lstrip())] += 1
        for t in row:
            depth += t.text == "{"
            depth -= t.text == "}"
    for d in sorted(depth_indent):
        if d + 1 in depth_indent:
            a = depth_indent[d].most_common(1)[0][0]
            b = depth_indent[d + 1].most_common(1)[0][0]
            if b > a:
                sv.indent_steps[b - a] += 1

    for t in toks:
        if t.text == "{":
            leading = [x for x in by_line[t.line] if x.index < t.index]
            sv.brace["same-line" if leading else "own-line"] += 1

    brackets = type_bracket_indices(toks)
    bracket_depth = 0
    for i, t in enumerate(toks[:-1]):
        if t.text == "[":
            bracket_depth += 1
        elif t.text == "]":
            bracket_depth -= 1
        nxt = toks[i + 1]
        if nxt.line != t.line:
            continue
        gap = nxt.start - t.stop - 1
        prev = toks[i - 1].text if i else ""

        def both(rule):
            """Gap on this side of a two-sided operator."""
            sv.note(rule, gap)

        if t.text == "=":
            both("'=' -> rhs")
        if nxt.text == "=":
            both("lhs -> '='")
        if t.text in ADDITIVE and prev not in PREFIX_CONTEXT:
            both("additive + - -> rhs")
        if nxt.text in ADDITIVE and t.text not in PREFIX_CONTEXT:
            both("lhs -> additive + -")
        if t.text in ADDITIVE and prev in PREFIX_CONTEXT:
            both("unary + - -> operand")
        if t.text in MULTIPLICATIVE and star_kind(toks, i):
            both("multiplicative -> rhs")
        if nxt.text in MULTIPLICATIVE and star_kind(toks, i + 1):
            both("lhs -> multiplicative")
        for op_set, label in ((COMPARISON, "comparison"), (LOGICAL, "logical")):
            if t.text in op_set and i not in brackets:
                both(f"{label} -> rhs")
            if nxt.text in op_set and (i + 1) not in brackets:
                both(f"lhs -> {label}")
        if i in brackets:
            both(f"type bracket '{t.text}' -> inside")
        if (i + 1) in brackets:
            both(f"inside -> type bracket '{nxt.text}'")
        if t.text == ":":
            both(colon_kind(toks, i, bracket_depth) + " -> rhs")
        if nxt.text == ":":
            d = bracket_depth + (1 if nxt.text == "[" else 0)
            both("lhs -> " + colon_kind(toks, i + 1, d))
        if nxt.text == ",":
            both("lhs -> ','")
        if t.text == ",":
            both("',' -> rhs")
        if nxt.text == ";":
            both("lhs -> ';'")
        if t.text == "(":
            both("'(' -> inside")
        if nxt.text == ")":
            both("inside -> ')'")
        if t.text == "[":
            both("'[' -> inside")
        if nxt.text == "]":
            both("inside -> ']'")
        if t.text == "::" or nxt.text == "::":
            both("around '::'")
        if t.text == "." or nxt.text == ".":
            both("around '.'")
        if t.text == "..":
            both("'..' range -> rhs")
        if nxt.text == "{":
            both("lhs -> '{'")
        if t.type_name in ("ID", "ESCAPED_ID") and nxt.text == "(":
            both("callee -> '('" if t.text not in CONTROL_KEYWORDS
                 else "control keyword -> '('")
        if t.text in CONTROL_KEYWORDS and nxt.text == "(":
            both("control keyword -> '('")

    _alignment(sv, toks, by_line, ts)


def _alignment(sv, toks, by_line, ts):
    """Runs of >=3 consecutive lines sharing a construct: aligned or ragged.

    This is the ``Q-5`` evidence.  A global ``align`` would column-ise blocks
    whose author left them ragged; a global ``flush-left`` would destroy
    hand-built tables.  Which of those is the mistake depends entirely on
    these counts.
    """
    trailing = {}
    for t in ts.tokens:
        if t.channel == T.CHANNEL_SL_COMMENT and by_line.get(t.line):
            if any(x.index < t.index for x in by_line[t.line]):
                trailing[t.line] = t.col
    eq = {}
    for lineno, row in by_line.items():
        signs = [x for x in row if x.text == "="]
        if len(signs) == 1:
            eq[lineno] = signs[0].col

    for label, colmap in (("trailing comment", trailing), ("'='", eq)):
        run = []
        for ln in sorted(colmap) + [None]:
            if run and ln is not None and ln == run[-1] + 1:
                run.append(ln)
                continue
            if len(run) >= 3:
                cols = {colmap[x] for x in run}
                key = f"{label} runs: " + ("aligned" if len(cols) == 1
                                           else "ragged")
                sv.align[key] += 1
            run = [ln] if ln is not None else []


def verdict(counter):
    """(modal gap, share, n) -- the rule the corpus votes for."""
    n = sum(counter.values())
    if not n:
        return None, 0.0, 0
    gap, hits = counter.most_common(1)[0]
    return gap, hits / n, n


def report(surveys, out=sys.stdout):
    def w(s=""):
        print(s, file=out)

    for voice in EVIDENCE_VOICES + ("ours",):
        sv = surveys[voice]
        if not sv.files:
            continue
        tag = "  [excluded from evidence: authored here]" if voice == "ours" else ""
        w("=" * 76)
        w(f"VOICE: {voice}   ({sv.files} files, {sv.lines} lines){tag}")
        w("=" * 76)
        L = sorted(sv.line_len)
        q = lambda p: L[min(len(L) - 1, int(len(L) * p))]
        over = sum(1 for x in L if x > 80)
        w(f"  line length  p50={q(.5)}  p90={q(.9)}  p95={q(.95)}  "
          f"p99={q(.99)}  max={L[-1]}   >80: {over} "
          f"({100 * over // max(1, len(L))}%)")
        w(f"  tabs in indent {sv.tab_indent}    trailing whitespace "
          f"{sv.trailing_ws}")
        w(f"  indent step  {dict(sv.indent_steps)}")
        w(f"  braces       {dict(sv.brace)}")
        w(f"  comments     {dict(sv.comment)}")
        w(f"  blank runs   {dict(sorted(sv.blank_runs.items()))}")
        w(f"  alignment    {dict(sv.align)}")
        w("  spacing (n >= 4):")
        for rule in sorted(sv.gap):
            gap, share, n = verdict(sv.gap[rule])
            if n < 4:
                continue
            w(f"    {rule:<32} n={n:<4} -> {gap} ({share:.0%})   "
              f"{dict(sorted(sv.gap[rule].items()))}")
        w()

    w("=" * 76)
    w("CONSENSUS across independent voices")
    w("=" * 76)
    rules = set()
    for v in EVIDENCE_VOICES:
        rules |= set(surveys[v].gap)
    for rule in sorted(rules):
        votes = {}
        for v in EVIDENCE_VOICES:
            gap, share, n = verdict(surveys[v].gap[rule])
            if n >= 4:
                votes[v] = (gap, share, n)
        if not votes:
            continue
        gaps = {g for g, _, _ in votes.values()}
        total = sum(n for _, _, n in votes.values())
        if len(gaps) == 1:
            mark = "UNANIMOUS" if len(votes) > 1 else "one voice "
        else:
            mark = "SPLIT    "
        detail = "  ".join(f"{v.split('-')[0]}={g}({n})"
                           for v, (g, _, n) in votes.items())
        w(f"  {mark} {rule:<32} n={total:<4} {detail}")
    w()
    w("  UNANIMOUS = every voice with n>=4 agrees on the modal gap.")
    w("  one voice = only one voice has enough instances; not consensus.")
    w("  SPLIT     = the corpus does not decide this; see docs/style.rst.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("corpus", nargs="?", help="corpus root (default: auto)")
    ap.add_argument("--json", action="store_true", help="machine-readable")
    args = ap.parse_args(argv)

    root = find_corpus(args.corpus)
    surveys = collections.defaultdict(Survey)
    for bucket, voice in VOICE_OF.items():
        for path in sorted((root / bucket).rglob("*.pss")):
            analyse(surveys[voice], path)
    if not any(s.files for s in surveys.values()):
        sys.exit(f"no .pss files under {root}")

    if args.json:
        blob = {
            v: {
                "files": s.files, "lines": s.lines,
                "indent_steps": dict(s.indent_steps),
                "braces": dict(s.brace),
                "alignment": dict(s.align),
                "gaps": {k: dict(c) for k, c in s.gap.items()},
            }
            for v, s in surveys.items() if s.files
        }
        json.dump(blob, sys.stdout, indent=2, sort_keys=True)
        print()
    else:
        report(surveys)
    return 0


if __name__ == "__main__":
    sys.exit(main())

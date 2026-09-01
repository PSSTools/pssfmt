#!/usr/bin/env python3
"""Derive the two grammar facts ``optional_semicolon`` rests on.

    python tools/semicolon_survey.py [PSSParser.g4] [--python] [--empty-items]

Two sets, one per direction of the option:

``--self-terminating`` (the default)
    Rules after which a sibling ``;`` is decoration.  ``omit`` may delete one
    of these; :data:`pssfmt.rules.decls._SELF_TERMINATING`.
``--empty-items``
    Rules that admit a bare ``;`` as an alternative -- the body kinds where an
    empty item is *grammatical*.  ``require`` may insert one only inside these;
    :data:`pssfmt.rules.decls._PERMITS_EMPTY_ITEM`.

The two are not the same question and neither implies the other.  Deleting is
justified by the *member*: what came before the semicolon already ended, so
the semicolon says nothing.  Inserting is justified by the *body*: a rule that
has no empty-item alternative would be handed a syntax error.  An enum is the
case that separates them cleanly -- ``enum e {A, B}`` is self-terminating, so
a ``;`` after it goes; ``enum_item`` has no bare ``;``, so no ``;`` is ever
put *between* two enum items.

Why this exists
---------------
``optional_semicolon = "omit"`` deletes a token from the user's file and
``"require"`` adds one, which are things a formatter gets exactly one chance
to be wrong about.  The question deletion has to answer is whether a given
``;`` is decoration or a terminator, and the two are indistinguishable at the
position they occupy:

    struct s { int a; } ;        // decoration -- an empty struct_body_item
    int a[4] = {1, 2}   ;        // the terminator of a data declaration

Both are a lone ``;`` sitting as the next sibling of the member before it, on
the same line, after a ``}``.  What separates them is the *grammar of the
member*, and nothing else:

    self-terminating
        every alternative of the rule ends in ``;`` or ``}`` of its own.  A
        ``;`` after one of these can only be the body's empty-item
        alternative, so it carries no meaning and may go.
    not self-terminating
        some alternative can end in an expression -- and
        ``procedural_data_declaration`` is exactly that, which is why
        ``int a[4] = {1, 2};`` is a sibling ``;`` that must stay.

This program computes the first set as a least fixed point over the ANTLR
grammar and prints it.  ``pssfmt.rules.decls._SELF_TERMINATING`` is its output,
pasted in: the grammar is not a runtime dependency of this package, and a set
that is *derived* rather than curated is one nobody has to argue about.  The
empty-item set is a one-pass scan of the same parse and needs no fixed point --
a bare ``TOK_SEMICOLON`` alternative is either written down or it is not.

Least fixed point, deliberately
-------------------------------
Mutually recursive rules -- ``constraint_set`` reaches ``constraint_body_item``
reaches ``if_constraint_item`` reaches ``constraint_set`` -- never enter the
set, because the iteration starts empty and a rule joins only once every
alternative is already proven.  The greatest fixed point would admit them.
Two reasons this one is right:

* Being out of the set means "preserve", which is the behaviour of every
  earlier ``pssfmt``.  Unproven has to fail closed when the consequence is a
  deleted token.
* It also matches the corpus.  Every one of the corpus's ``x1 with { … };``
  traversals and ``constraint c { … };`` blocks writes the semicolon, and
  each of those reaches the set through the recursive knot.  The rules the
  fixed point *does* admit -- ``struct_declaration``, ``enum_declaration``,
  ``component_declaration``, ``package_declaration`` -- are the ones the
  corpus writes both ways, 32 times with and 701 without.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

#: Terminators a rule may end with and still be self-terminating.
CLOSERS = ("TOK_SEMICOLON", "TOK_RCBRACE")

_ATOM = re.compile(r"[A-Za-z_]\w*\s*=|[A-Za-z_]\w*|'[^']*'|[()\[\]|?*+~.]")
_LABEL = re.compile(r"^\w+\s*=$")


def strip_comments(text: str) -> str:
    text = re.sub(r"//[^\n]*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def parse_rules(text: str) -> Dict[str, List[str]]:
    """``{rule name: token list}``, one entry per parser rule."""
    out: Dict[str, List[str]] = {}
    # Non-greedy to the first bare `;` at end of line: ANTLR ends a rule with
    # one and the grammar spells the *token* `TOK_SEMICOLON`, so there is no
    # other bare `;` to stop on. The `\s*$` rather than `^\s*;` matters --
    # `floating_point_dec_number: FLOAT_DEC_LITERAL;` is written on one line,
    # and an anchor that insisted on its own line swallowed nine rules after it.
    for name, body in re.findall(r"(?ms)^(\w+)\s*:(.*?);[ \t]*$",
                                 strip_comments(text)):
        if name[:1].isupper():
            continue                      # a lexer rule; not our business
        out[name] = _ATOM.findall(body)
    return out


def alternatives(tokens: Sequence[str]) -> List[List[str]]:
    """Split on ``|`` at bracket depth zero."""
    out: List[List[str]] = [[]]
    depth = 0
    for tok in tokens:
        if tok in "([":
            depth += 1
        elif tok in ")]":
            depth -= 1
        if tok == "|" and depth == 0:
            out.append([])
        else:
            out[-1].append(tok)
    return [alt for alt in out if alt]


def final_atoms(alt: Sequence[str]) -> Optional[Set[str]]:
    """Every atom this alternative can end with, or ``None`` if it can be empty.

    Walks backwards through trailing ``?``/``*`` elements, because an optional
    tail means the element before it can also be last -- ``TOK_RETURN
    expression? TOK_SEMICOLON`` ends in ``;`` but ``a b?`` can end in ``a``.
    A ``(x | y)`` group contributes the endings of both branches.
    """
    found: Set[str] = set()
    i = len(alt) - 1
    while i >= 0:
        optional = False
        if alt[i] in "?*":
            optional = True
            i -= 1
            if i < 0:
                return None
        atom = alt[i]
        if _LABEL.match(atom):            # `is_do=TOK_DO`; skip the label
            i -= 1
            continue
        if atom in ")]":
            depth = 0
            j = i
            while j >= 0:
                if alt[j] in ")]":
                    depth += 1
                elif alt[j] in "([":
                    depth -= 1
                    if depth == 0:
                        break
                j -= 1
            if j < 0:
                return None               # unbalanced; treat as unknown
            if alt[j] == "[":
                optional = True
            for branch in alternatives(alt[j + 1:i]):
                inner = final_atoms(branch)
                if inner is None:
                    optional = True
                else:
                    found |= inner
            i = j - 1
        else:
            found.add(atom)
            i -= 1
        if not optional:
            return found
    return None                           # the whole alternative can be empty


def self_terminating(rules: Dict[str, List[str]]) -> Set[str]:
    """Least fixed point: rules whose every alternative ends in ``;`` or ``}``."""
    proven: Set[str] = set()
    growing = True
    while growing:
        growing = False
        for name, tokens in rules.items():
            if name in proven:
                continue
            alts = alternatives(tokens)
            if not alts:
                continue
            if all(_closes(final_atoms(alt), proven) for alt in alts):
                proven.add(name)
                growing = True
    return proven


def permits_empty_item(rules: Dict[str, List[str]]) -> Set[str]:
    """Rules with a bare ``TOK_SEMICOLON`` alternative.

    "Bare" means the alternative is that token and nothing else -- an empty
    item, the thing ``require`` writes. A rule whose semicolon merely *appears*
    somewhere is not one of these; ``import_stmt`` ends in a ``;`` and admits
    no empty alternative at all.
    """
    return {name for name, tokens in rules.items()
            if any(alt == ["TOK_SEMICOLON"] for alt in alternatives(tokens))}


def _closes(endings: Optional[Set[str]], proven: Set[str]) -> bool:
    if not endings:
        return False
    return all(e in CLOSERS or e in proven for e in endings)


def find_grammar(argv: Sequence[str]) -> Optional[Path]:
    for arg in argv:
        if not arg.startswith("-"):
            return Path(arg)
    root = Path(__file__).resolve().parent.parent
    for candidate in (root / "packages" / "pssparser" / "src" / "PSSParser.g4",
                      root.parent / "pssparser" / "src" / "PSSParser.g4"):
        if candidate.is_file():
            return candidate
    return None


def main(argv: Sequence[str]) -> int:
    grammar = find_grammar(argv)
    if grammar is None or not grammar.is_file():
        print("no PSSParser.g4 found; pass one as an argument",
              file=sys.stderr)
        return 2
    rules = parse_rules(grammar.read_text())
    names = sorted(permits_empty_item(rules) if "--empty-items" in argv
                   else self_terminating(rules))
    if "--python" in argv:
        for name in names:
            print('    "%s",' % name)
    else:
        print("\n".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

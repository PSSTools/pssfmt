"""The verifier and the fail-safe -- ``P1-3``, ``formatter.md`` section 3.5.

Three checks run on every format, and failing any of them aborts the format and
returns the **input unchanged** with a diagnostic:

1. **Token equivalence.** Re-lex the output; the sequence of non-trivia tokens
   must be identical in type and text. Comment text must be identical modulo
   trailing whitespace.
2. **Idempotence.** ``fmt(fmt(x)) == fmt(x)``.
3. **No new parse errors.** The output must parse with no more syntax errors
   than the input had.

Section 3.5 states the reason in one line, and it is the reason this module
exists at all rather than being a ``--check`` flag someone can forget to pass:

    *A formatter that is occasionally a no-op is survivable; a formatter that
    occasionally corrupts is not.*

So the fail-safe is the default path, not an option. :func:`format_safely` is
the entry point every caller should use; a caller that wants the unchecked
output has to reach past it deliberately.

Counting parse errors
---------------------
Check 3 counts :attr:`Cst.num_syntax_errors`, from the parser, and **never**
``TokenStream.num_errors``, from the lexer. ``PLAN.md`` R10: an unterminated
``/*`` lexes as ``TOK_DIV``, ``TOK_ASTERISK``, ``ID`` with the lexer reporting
zero errors, so a spacing rule that turned ``/*`` into ``/ *`` would comment
out the rest of the file and pass a lexer-based check cleanly. The parser sees
it; the lexer does not.

Slightly stricter than section 3.5
----------------------------------
Section 3.5 says the *default-channel* token sequence must match. This module
compares every **non-trivia** token, which additionally covers the synthetic
error tokens standing for text no lexer rule matched. Dropping a stray ``$``
silently deletes a byte of the user's file, and a default-channel-only
comparison would not notice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Sequence, Tuple

from pssparser import cst as _cst
from pssparser import tokens as _tokens

from . import null as _null
from .finish import normalize as _normalize

__all__ = [
    "Violation",
    "SafeResult",
    "verify",
    "format_safely",
    "check_token_equivalence",
    "check_parse_errors",
]


@dataclass(frozen=True)
class Violation:
    """One failed check."""

    #: ``"tokens"``, ``"comments"``, ``"idempotence"`` or ``"parse-errors"``.
    kind: str

    #: One line, suitable for a diagnostic. Says what changed, not what to do.
    message: str

    #: Line in the *output* the problem was noticed at, when known.
    line: Optional[int] = None

    def __str__(self) -> str:
        where = "" if self.line is None else " (output line %d)" % self.line
        return "%s%s: %s" % (self.kind, where, self.message)


@dataclass
class SafeResult:
    """What :func:`format_safely` returns. Read :attr:`text` and nothing else
    if you just want the answer -- it is always safe to write to the file."""

    #: The text to write. The formatted output when :attr:`ok`, otherwise the
    #: **unmodified input**.
    text: str

    #: True when every check passed.
    ok: bool

    #: Empty when :attr:`ok`. Never partially applied -- a format either passes
    #: entirely or is discarded entirely.
    violations: Tuple[Violation, ...] = ()

    #: The output that was rejected, kept for debugging and for ``--explain``.
    #: ``None`` when the format succeeded (:attr:`text` is it) or when the
    #: formatter itself raised.
    rejected: Optional[str] = None

    #: Set when the formatter raised rather than produced bad output. That is
    #: also a fail-safe path: a crash must not lose the file either.
    error: Optional[BaseException] = None

    @property
    def changed(self) -> bool:
        return self.ok and self.text != self._original

    _original: str = field(default="", repr=False)

    def diagnostic(self, path: str = "<input>") -> str:
        """A multi-line message explaining why the file was left alone."""
        if self.ok:
            return ""
        if self.error is not None:
            return ("%s: left unchanged -- the formatter raised %s: %s"
                    % (path, type(self.error).__name__, self.error))
        lines = ["%s: left unchanged -- the formatted output failed "
                 "verification:" % path]
        lines.extend("  %s" % v for v in self.violations)
        lines.append("  This is a pssfmt bug. The file has not been modified.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# The individual checks
# ---------------------------------------------------------------------------

def _significant(stream: Any) -> List[Any]:
    return [t for t in stream if not t.is_trivia]


def _comments(stream: Any) -> List[Any]:
    return [t for t in stream if t.is_comment]


def check_token_equivalence(original: str,
                            formatted: str) -> Tuple[Violation, ...]:
    """Check 1: the output says the same thing the input said.

    Two comparisons, reported separately because they fail for different
    reasons: a code-token difference is a rule emitting or eating text, while a
    comment difference is nearly always the trivia map attaching a comment to
    the wrong side of something.

    Both sides are compared with line endings normalised, and that exemption
    is narrow enough to state exactly: it permits ``\\r\\n`` <-> ``\\n`` and
    nothing else, anywhere. It is needed because a line ending can live
    *inside* a token -- a multi-line ``/* */`` comment and a triple-quoted
    ``exec`` template are each one token whose text spans lines -- so
    converting a file's line endings, which ``line_ending: lf`` exists to do,
    necessarily rewrites token text. Without this, that option declined every
    file containing a block comment and blamed the formatter for it.

    What is given up is small and what is kept is not: a dropped comment, an
    altered one, a merged token or a deleted byte all still fail. The
    conversion this permits is byte-level, total, and its own inverse -- it is
    checkable without a parser, which is why it is allowed to happen outside
    the part a parser checks.
    """
    out: List[Violation] = []

    a = _significant(_tokens.tokenize(_normalize(original)))
    b = _significant(_tokens.tokenize(_normalize(formatted)))
    diff = _first_difference([(t.type, t.text) for t in a],
                            [(t.type, t.text) for t in b])
    if diff is not None:
        out.append(_token_violation("tokens", a, b, diff))

    # Trailing whitespace inside a comment is not content, and stripping it is
    # something the formatter is expected to do. A `//` comment carries its own
    # newline, which rstrip takes off both sides alike.
    ca = [t.text.rstrip() for t in _comments(_tokens.tokenize(_normalize(original)))]
    cb = [t.text.rstrip() for t in _comments(_tokens.tokenize(_normalize(formatted)))]
    cdiff = _first_difference(ca, cb)
    if cdiff is not None:
        i = cdiff
        out.append(Violation(
            "comments",
            "comment %d changed: %s -> %s (input has %s, output %d)"
            % (i + 1,
               _show(ca[i] if i < len(ca) else None),
               _show(cb[i] if i < len(cb) else None),
               _plural(len(ca), "comment"), len(cb))))

    return tuple(out)


def check_parse_errors(original: str, formatted: str,
                       original_errors: Optional[int] = None
                       ) -> Tuple[Violation, ...]:
    """Check 3: the output parses at least as well as the input did.

    "At least as well" rather than "cleanly": a formatter is asked to format
    files that do not parse, and refusing to touch them is a separate policy
    decision. What it may never do is make a parsing file stop parsing.
    """
    before = (_cst.parse(original).num_syntax_errors
              if original_errors is None else original_errors)
    after = _cst.parse(formatted).num_syntax_errors
    if after > before:
        return (Violation(
            "parse-errors",
            "output has %d syntax error(s), input had %d" % (after, before)),)
    return ()


def verify(original: str, formatted: str,
           original_errors: Optional[int] = None) -> Tuple[Violation, ...]:
    """Runs checks 1 and 3. Idempotence needs the formatter, so it lives in
    :func:`format_safely`."""
    return (check_token_equivalence(original, formatted)
            + check_parse_errors(original, formatted, original_errors))


# ---------------------------------------------------------------------------
# The fail-safe
# ---------------------------------------------------------------------------

def _default_formatter(src: str) -> str:
    return _null.format_null(src).text


def format_safely(src: Any,
                  formatter: Callable[[str], str] = _default_formatter,
                  check_idempotence: bool = True) -> SafeResult:
    """Formats *src*, verifies the result, and falls back to *src* on failure.

    :param src: PSS source as :class:`str` or UTF-8 :class:`bytes`.
    :param formatter: takes source text, returns formatted text. Defaults to
        the ``P1-2`` null formatter.
    :param check_idempotence: run the formatter a second time and require the
        output to be stable. On by default -- verible ships the equivalent
        check on by default too, and it is the check that catches a rule
        oscillating between two layouts.
    :raises UnicodeDecodeError: if *src* is bytes that are not UTF-8. This is
        the one failure that is **not** caught, because there is no text to
        hand back and pretending otherwise would mean writing a guess to the
        user's file.

    Never raises anything else. An exception from *formatter* is caught and
    turned into a fail-safe result, because a crash must not lose the file
    either.
    """
    text = src.decode("utf-8") if isinstance(src, (bytes, bytearray)) \
        else src
    if not isinstance(text, str):
        raise TypeError("expecting str or bytes, not %s" % type(src).__name__)

    try:
        formatted = formatter(text)
    except BaseException as e:  # noqa: BLE001 -- deliberate; see docstring
        return SafeResult(text=text, ok=False, error=e, _original=text)

    if not isinstance(formatted, str):
        return SafeResult(
            text=text, ok=False, _original=text,
            violations=(Violation(
                "tokens", "formatter returned %s, not str"
                % type(formatted).__name__),))

    violations = list(verify(text, formatted))

    if check_idempotence:
        try:
            again = formatter(formatted)
        except BaseException as e:  # noqa: BLE001
            return SafeResult(text=text, ok=False, error=e,
                              rejected=formatted, _original=text)
        if again != formatted:
            violations.append(Violation(
                "idempotence",
                "formatting the output again changed it at %s"
                % _describe_text_difference(formatted, again),
                line=_line_of_first_difference(formatted, again)))

    if violations:
        return SafeResult(text=text, ok=False, violations=tuple(violations),
                          rejected=formatted, _original=text)
    return SafeResult(text=formatted, ok=True, _original=text)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def _first_difference(a: Sequence[Any], b: Sequence[Any]) -> Optional[int]:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    if len(a) != len(b):
        return min(len(a), len(b))
    return None


def _plural(n: int, noun: str) -> str:
    return "%d %s%s" % (n, noun, "" if n == 1 else "s")


def _show(value: Any) -> str:
    return "<end of file>" if value is None else repr(value)


def _token_violation(kind: str, a: List[Any], b: List[Any],
                     i: int) -> Violation:
    ta = a[i] if i < len(a) else None
    tb = b[i] if i < len(b) else None
    return Violation(
        kind,
        "token %d changed: %s -> %s (input has %s, output %d)"
        % (i + 1,
           _show(ta.text if ta is not None else None),
           _show(tb.text if tb is not None else None),
           _plural(len(a), "code token"), len(b)),
        line=tb.line if tb is not None else None)


def _line_of_first_difference(a: str, b: str) -> Optional[int]:
    i = _first_difference(a, b)
    return None if i is None else a[:i].count("\n") + 1


def _describe_text_difference(a: str, b: str) -> str:
    i = _first_difference(a, b)
    if i is None:
        return "no difference"
    return "offset %d: %s -> %s" % (
        i, _show(a[i:i + 20] or None), _show(b[i:i + 20] or None))

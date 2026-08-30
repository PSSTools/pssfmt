"""The emit boundary -- the last line of the file, which no rule owns.

Every other line of a formatted file is *composed*: a rule asked the style for
a gap, the engine decided a break, the alignment pass moved a column. The tail
of the file is different. Trivia after the last code token belongs to no CST
node, so no builder can emit it, and :func:`pssfmt.rules.build_tree` therefore
appends it verbatim. That is the correct default -- dropping it truncates the
file, usually by exactly the final newline -- but it means every *file-level*
property the formatter claims was true of every line except the last one:

* ``line_ending`` and ``insert_final_newline`` were declared options that
  nothing read. A CRLF file came out **mixed**: the engine emits ``\\n`` for
  the lines it composed, and the copied tail kept its ``\\r\\n``.
* The layout engine's no-trailing-whitespace property (asserted over generated
  IR by ``T-8``) held for the engine and not for the output, because
  ``}   \\n`` at EOF is copied rather than rendered.
* Six trailing blank lines survived a ``max_blank_lines`` of 1, since clamping
  happens in the trivia map and the tail bypasses it.

None of that was visible from the corpus: of 92 files, zero use CRLF, zero end
in trailing whitespace, zero end in a blank line, and the one file with no
final newline is a deliberately truncated pathological case. So this is the
familiar shape -- a defect the corpus cannot vote on -- with the unfamiliar
property that it needs no vote. A file with two different line terminators in
it is wrong under every style, so unlike ``**`` spacing or ``default``
alignment there is nothing here to defer for want of evidence.

The lesson generalises the same way ``P3-10``'s did: an invariant is audited
by enumerating the places output is *produced*, and "the text a rule emitted"
was never the only such place.

Why this is not a rule module
-----------------------------
It runs on finished text, after alignment, and it is the only part of the
pipeline whose input is a whole file rather than a node. Putting it behind the
rule registry would make it dispatchable, which is exactly wrong: a file that
reaches this function with no builder having fired at all -- the null-rule-set
case the whole architecture rests on -- still needs one consistent line
terminator.
"""

from __future__ import annotations

from typing import Any, Optional

from .style import DEFAULT_STYLE, LineEnding, Style

__all__ = ["finish", "detect_line_ending", "normalize", "apply_line_ending",
           "resolve_line_ending"]

_CRLF = "\r\n"
_LF = "\n"


def normalize(text: str) -> str:
    """*text* with every ``\\r\\n`` collapsed to ``\\n``.

    The formatter works in LF throughout and converts once, on the way out, so
    that no rule, no width measurement and no check ever has an opinion about
    line endings.

    The reason is worth stating carefully, because the plausible one is wrong.
    It is *not* that normalising the input is what keeps line-ending
    conversion from rewriting token text -- a line ending genuinely can live
    inside a token, since a multi-line ``/* */`` comment and a triple-quoted
    ``exec`` template are each one token whose text spans lines, but what
    makes converting them safe is the narrow exemption in
    :func:`pssfmt.verify.check_token_equivalence`. Removing this call changes
    no result on that path at all.

    The actual reason is that **the rule layer cannot handle CRLF.** A run of
    ``//`` comments is re-indented by splitting it on ``\\n``, which on CRLF
    input leaves a stray ``\\r`` at the end of every line, and the Layout IR's
    ``Text`` node rejects it -- so the builder raises and the fail-safe hands
    back the file. Every CRLF file with two adjacent comments in it was
    reaching that path.

    That correction is recorded rather than quietly applied because of how it
    was found: the first rationale was plausible, it sat above code that
    worked, and nothing but a mutation run disagreed with it. Same shape as
    ``P3-7c``, where a docstring correctly described a failure mode the code
    below it no longer prevented.

    A lone ``\\r`` is left alone -- see :func:`detect_line_ending`.
    """
    return text.replace(_CRLF, _LF)


def apply_line_ending(text: str, ending: str) -> str:
    """*text*, which must be LF, with *ending* as its terminator.

    The inverse of :func:`normalize`, and the only place ``\\r`` is written.
    Normalises first regardless, so that calling it on text that is already
    CRLF cannot produce ``\\r\\r\\n``.
    """
    if ending == _LF:
        return normalize(text)
    return normalize(text).replace(_LF, _CRLF)


def resolve_line_ending(style: Style, source: Any) -> str:
    """The concrete terminator *style* asks for, given the original *source*.

    Split out from :func:`finish` because ``auto`` has to be answered while
    the **original** text is still in hand. By the time a tree exists the
    input has been normalised, so a stream asked then reports LF for every
    file ever written.
    """
    if style.line_ending is LineEnding.CRLF:
        return _CRLF
    if style.line_ending is LineEnding.LF:
        return _LF
    return detect_line_ending(source)


def detect_line_ending(source: Any) -> str:
    """The dominant terminator in *source*.

    *source* is **the input**, as either the source text or the token stream
    it was lexed into -- whichever the caller happens to be holding. The two
    are the same measurement, and requiring one of them would mean every
    caller converting: :func:`pssfmt.rules.format_source` has the text and
    :func:`pssfmt.rules.build_tree` has only the stream.

    It must be the input and not the output, which is the part worth being
    careful about. The engine emits ``\\n`` unconditionally, so by the time
    there is output the only surviving evidence of the author's choice is
    whatever was copied verbatim -- the tail, an ``exec`` body, a
    ``pssfmt off`` region. A file with none of those would report LF however
    it was written.

    Ties go to LF, and so does a file with no line terminator at all. There is
    no third answer to give: a bare ``\\r`` is not treated as a terminator
    here, because a lone CR in a PSS file is far more likely to be a stray
    byte inside a literal than a Mac OS 9 line ending, and rewriting it would
    change a token rather than whitespace.
    """
    if isinstance(source, str):
        pieces: Any = (source,)
    else:
        pieces = (getattr(tok, "text", "") or "" for tok in source)

    crlf = lf = 0
    for text in pieces:
        if _LF not in text:
            continue
        n = text.count(_CRLF)
        crlf += n
        lf += text.count(_LF) - n
    return _CRLF if crlf > lf else _LF


def finish(text: str, style: Style = DEFAULT_STYLE,
           source: Optional[Any] = None) -> str:
    """Apply the file-level style options to finished *text*.

    :param text: the formatted file, as the engine and alignment pass left it.
    :param style: supplies ``insert_final_newline`` and ``line_ending``.
    :param source: the **input**, as text or as a token stream. Needed only to
        resolve ``line_ending: auto``, which without it falls back to *text*
        -- a defensible guess for a caller that has nothing else, and the
        reason every caller inside ``pssfmt`` passes the input explicitly.

    Idempotent by construction, which is not optional: the fail-safe formats
    twice and compares, so a non-idempotent step here would reject every file
    it touched rather than corrupt one. Both transformations are projections
    -- the tail is normalised to a canonical form, and re-normalising a
    canonical form is a no-op.

    Trailing blank lines are removed entirely rather than clamped to
    ``max_blank_lines``, and that is a different rule wearing a similar name.
    ``max_blank_lines`` is about *separation* -- how much air is allowed
    between two things -- and at the end of a file there is no second thing.
    Every formatter that has an opinion here (gofmt, black, prettier) removes
    them; none clamps them.
    """
    # An empty file stays empty. `insert_final_newline` promises that a file
    # ends with a newline, and a file with no content does not begin, so
    # writing one here would be the formatter inventing a byte.
    body = text.rstrip()
    if not body:
        return ""

    if style.insert_final_newline:
        body += _LF

    # EditorConfig's semantics for the key this option is named after: false
    # means "ensure it does *not* end with a newline", not "leave whatever was
    # there alone". Preserving the author's choice would be a third state, and
    # a bool cannot hold three. Said out loud because the destructive reading
    # is the surprising one, and it is the one the name implies elsewhere.

    return apply_line_ending(
        body, resolve_line_ending(style, text if source is None else source))

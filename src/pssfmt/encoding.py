"""``P4-1`` -- what encoding the bytes on disk are in, and how to put them back.

The formatter works on ``str``. Everything either side of it works on bytes,
and something has to decide what those bytes mean. That decision lives here,
in one place, because it is made three times -- source files, ``.pssfmt``
configuration, ``.pssfmtignore`` -- and three independent answers to the same
question is how a tool ends up formatting a file it cannot read back.

Why this is not just ``data.decode("utf-8")``
---------------------------------------------
Windows tooling writes UTF-16 by default. ``Set-Content`` and ``>`` in Windows
PowerShell 5.1 -- still the shell that ships in the box -- produce UTF-16 LE
with a byte-order mark, and Notepad wrote UTF-16 on request for decades. A
file created that way is perfectly good PSS source; it simply is not UTF-8,
and a formatter that answers *"not valid UTF-8"* is telling the user their
source code is broken when it is not.

So the encoding is *detected* rather than assumed, and -- this is the part
that matters more than the detection -- it is **carried through and written
back**. ``pssfmt`` is a formatter, not a transcoder. A UTF-16 LE file with a
BOM is still a UTF-16 LE file with a BOM after ``-i``, byte for byte outside
the reformatted text. Silently rewriting it as UTF-8 would be a change nobody
asked for, invisible in the diff the user reads, and quite capable of breaking
whatever produced the file in the first place.

How it is detected
------------------
By byte-order mark first, which is not a heuristic: the BOM is exactly the
"this is the encoding" marker, and every encoding under discussion has a
distinct one. UTF-32's marks are tested before UTF-16's because
``ff fe 00 00`` starts with ``ff fe``, and testing in the other order would
read every UTF-32 LE file as a UTF-16 LE file that begins with a NUL.

Only if there is no mark does a guess happen, and only one guess: ASCII-range
text in UTF-16 is half NUL bytes, all of them on the same side of each pair,
which nothing else produces. It is reached when UTF-8 has been ruled out --
either the bytes are not valid UTF-8, or they are but decode to a string
containing NUL, which is what ``c\\0o\\0m\\0`` does and what no real source
file does. Without that second condition the guess would be dead code, since
BOM-less UTF-16 LE of ASCII is *always* valid UTF-8.

UTF-8 without a BOM stays the default and the fallback. That is the
overwhelming majority of inputs, and nothing about them changes.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from typing import Optional, Tuple

__all__ = ["Encoding", "UTF_8", "detect", "decode", "encode"]


@dataclass(frozen=True)
class Encoding:
    """A codec plus the byte-order mark that introduced it, if any.

    The mark is kept separately from the codec name rather than folded into
    it (``"utf-8-sig"``, ``"utf-16"``) because the two facts are needed
    separately. Decoding must skip a mark it has already consumed; encoding
    must re-emit exactly the mark the input had and no other. Python's
    aggregate codecs make "had a BOM" and "which byte order" unrecoverable
    after the fact -- ``"utf-16"`` decodes either order and always encodes the
    platform's, which would turn a UTF-16 BE file into a UTF-16 LE one on the
    way through.
    """

    #: The codec used for the bytes *after* the mark. Always an explicit
    #: endianness for UTF-16/32, never the BOM-consuming aggregate.
    codec: str

    #: The literal mark to write back, or ``b""`` for none.
    bom: bytes = b""

    #: What to call it in a message to a human.
    label: str = "UTF-8"

    @property
    def is_utf8(self) -> bool:
        """True for plain UTF-8 with no mark -- the unremarkable case."""
        return self.codec == "utf-8" and not self.bom

    def decode(self, data: bytes) -> str:
        """Decode *data*, which may or may not still carry the mark."""
        if self.bom and data.startswith(self.bom):
            data = data[len(self.bom):]
        return data.decode(self.codec)

    def encode(self, text: str) -> bytes:
        """The bytes to write, mark included."""
        return self.bom + text.encode(self.codec)


UTF_8 = Encoding("utf-8", b"", "UTF-8")
UTF_8_SIG = Encoding("utf-8", codecs.BOM_UTF8, "UTF-8 with BOM")
UTF_16_LE = Encoding("utf-16-le", codecs.BOM_UTF16_LE, "UTF-16 LE")
UTF_16_BE = Encoding("utf-16-be", codecs.BOM_UTF16_BE, "UTF-16 BE")
UTF_32_LE = Encoding("utf-32-le", codecs.BOM_UTF32_LE, "UTF-32 LE")
UTF_32_BE = Encoding("utf-32-be", codecs.BOM_UTF32_BE, "UTF-32 BE")

#: The BOM-less siblings, used only by the fallback guess. They write nothing
#: back at the front, because there was nothing there to begin with.
UTF_16_LE_RAW = Encoding("utf-16-le", b"", "UTF-16 LE without BOM")
UTF_16_BE_RAW = Encoding("utf-16-be", b"", "UTF-16 BE without BOM")

#: Longest mark first: ``ff fe 00 00`` (UTF-32 LE) begins with ``ff fe``
#: (UTF-16 LE), so the shorter test would swallow it.
_BY_BOM: Tuple[Encoding, ...] = (
    UTF_32_LE, UTF_32_BE, UTF_8_SIG, UTF_16_LE, UTF_16_BE,
)

#: How much of the file the BOM-less guess looks at. Enough to be conclusive
#: on any real source file; bounded so a large input is not scanned twice.
_SNIFF_BYTES = 4096


def _guess_utf16(data: bytes) -> Optional[Encoding]:
    """UTF-16 with no mark, or ``None`` if the bytes do not look like it.

    Only ever consulted once UTF-8 has been ruled out -- either it failed
    outright, or it produced NUL characters, which no source file has.

    The signal is the NUL half of each code unit. PSS source is
    overwhelmingly ASCII, so in UTF-16 LE the odd-indexed byte of nearly every
    pair is ``00`` and the even-indexed byte of none of them is; UTF-16 BE is
    the mirror. Requiring the *opposite* side to be entirely NUL-free is what
    keeps this from firing on arbitrary binary, which has NULs on both sides.
    """
    sample = data[:_SNIFF_BYTES]
    if len(sample) % 2:
        sample = sample[:-1]
    pairs = len(sample) // 2
    if pairs < 2:
        return None
    lead = sum(1 for b in sample[0::2] if b == 0)
    trail = sum(1 for b in sample[1::2] if b == 0)
    if trail > pairs // 2 and lead == 0:
        return UTF_16_LE_RAW
    if lead > pairs // 2 and trail == 0:
        return UTF_16_BE_RAW
    return None


#: First bytes of every mark in :data:`_BY_BOM`. A single membership test
#: retires all five ``startswith`` calls for the overwhelming majority of
#: files, which begin with a letter or a comment slash.
_BOM_FIRST = frozenset(enc.bom[0] for enc in _BY_BOM)


def _by_bom(data: bytes) -> Optional[Encoding]:
    """The encoding *data*'s mark names, or ``None`` if it has no mark."""
    if not data or data[0] not in _BOM_FIRST:
        return None
    for enc in _BY_BOM:
        if data.startswith(enc.bom):
            return enc
    return None


def decode(data: bytes) -> Tuple[str, Encoding]:
    """*data* as text, with the encoding to write it back in.

    Decoding happens **once**. Detection and decoding are one pass rather than
    two functions called in sequence, because for the case that is almost
    every case -- UTF-8 with no mark -- deciding the encoding means decoding
    it, and doing that twice would make the common path pay for the rare one.

    :raises UnicodeDecodeError: when the bytes are not text in any encoding
        this module recognises. Propagated rather than papered over with
        ``errors="replace"``: a formatter that substitutes ``U+FFFD`` for the
        bytes it could not read and then writes the file back has silently
        corrupted it, and the fail-safe cannot catch that because the damage
        happened before it ever saw a token.
    """
    marked = _by_bom(data)
    if marked is not None:
        return marked.decode(data), marked

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        # Not UTF-8 at all. The guess is the last thing tried, and if it
        # declines the original error is what the caller gets.
        guess = _guess_utf16(data)
        if guess is None:
            raise
        return guess.decode(data), guess

    # Valid UTF-8 is the answer *unless* it decoded to NUL characters, and
    # that exception is the whole reason the guess exists rather than being
    # unreachable: ASCII text in UTF-16 LE is `c \0 o \0 m \0`, which is
    # entirely valid UTF-8 and decodes without a murmur into a string full of
    # NULs. There is no such thing as source with a NUL in it, so a file that
    # decodes to one is either UTF-16 or not source at all.
    if "\x00" not in text:
        return text, UTF_8
    guess = _guess_utf16(data)
    if guess is None:
        return text, UTF_8
    return guess.decode(data), guess


def detect(data: bytes) -> Encoding:
    """The encoding of *data*, defaulting to plain UTF-8. Never raises.

    A thin wrapper over :func:`decode` rather than a second implementation of
    the same decision. Two functions that must agree about which encoding a
    file is in are two functions that will eventually disagree, and the one
    that disagrees silently is the one that writes the file back.
    """
    try:
        return decode(data)[1]
    except UnicodeDecodeError:
        return UTF_8


def encode(text: str, enc: Encoding = UTF_8) -> bytes:
    """*text* as bytes in *enc*. The inverse of :func:`decode`."""
    return enc.encode(text)

"""``T-7`` -- encoding detection, and the round trip that is the actual point.

Detection on its own is the easy half and the less important one. What these
tests are really guarding is that the encoding *survives*: whatever came in
goes back out, byte for byte outside the reformatted text. A tool that reads
UTF-16 and writes UTF-8 has not added UTF-16 support, it has added a silent
transcoder to the middle of somebody's build.
"""

from __future__ import annotations

import codecs

import pytest

from pssfmt import encoding as enc

pytestmark = pytest.mark.unit

SRC = "component a {\n    int x;\n}\n"


class TestDetect:
    """What the bytes say they are."""

    def test_plain_ascii_is_utf8(self):
        assert enc.detect(SRC.encode("utf-8")) is enc.UTF_8

    def test_utf8_with_non_ascii_is_utf8(self):
        assert enc.detect("// café\n".encode("utf-8")) is enc.UTF_8

    def test_empty_input_is_utf8(self):
        """No bytes is not an error, and the default has to apply to it."""
        assert enc.detect(b"") is enc.UTF_8

    @pytest.mark.parametrize("codec,expected", [
        ("utf-8-sig", enc.UTF_8_SIG),
        ("utf-16-le", enc.UTF_16_LE),
        ("utf-16-be", enc.UTF_16_BE),
        ("utf-32-le", enc.UTF_32_LE),
        ("utf-32-be", enc.UTF_32_BE),
    ])
    def test_a_byte_order_mark_is_conclusive(self, codec, expected):
        data = _with_bom(SRC, codec)
        assert enc.detect(data) is expected

    def test_utf32_le_is_not_read_as_utf16_le(self):
        """``ff fe 00 00`` starts with ``ff fe``.

        Testing the short mark first would read every UTF-32 LE file as a
        UTF-16 LE file beginning with a NUL, which decodes without complaint
        and produces garbage -- the failure mode that has no error message.
        """
        assert enc.detect(_with_bom(SRC, "utf-32-le")) is enc.UTF_32_LE

    def test_bom_less_utf16_le_is_guessed(self):
        assert enc.detect(SRC.encode("utf-16-le")) is enc.UTF_16_LE_RAW

    def test_bom_less_utf16_be_is_guessed(self):
        assert enc.detect(SRC.encode("utf-16-be")) is enc.UTF_16_BE_RAW

    def test_invalid_utf8_that_is_not_utf16_stays_utf8(self):
        """The guess declines, so the caller gets a decode error and not a
        misread file. ``\\xe9`` is Latin-1 ``é`` -- a real thing to find in a
        comment, and not text this tool can read."""
        assert enc.detect(b"// caf\xe9\n") is enc.UTF_8

    def test_binary_with_nuls_on_both_sides_is_not_utf16(self):
        """Requiring one side to be entirely NUL-free is what keeps the guess
        off arbitrary binary."""
        assert enc.detect(bytes(range(256))) is enc.UTF_8

    def test_one_byte_of_junk_is_not_enough_to_guess(self):
        assert enc.detect(b"\xff") is enc.UTF_8


class TestDecode:

    @pytest.mark.parametrize("codec", [
        "utf-8", "utf-8-sig", "utf-16-le", "utf-16-be",
        "utf-32-le", "utf-32-be",
    ])
    def test_the_mark_is_not_part_of_the_text(self, codec):
        """A leading ``U+FEFF`` left in the string is a token the parser has
        never heard of, on line 1 of every file."""
        text, _ = enc.decode(_with_bom(SRC, codec))
        assert text == SRC

    def test_bom_less_utf16_decodes(self):
        assert enc.decode(SRC.encode("utf-16-le"))[0] == SRC

    def test_undecodable_bytes_raise(self):
        with pytest.raises(UnicodeDecodeError):
            enc.decode(b"// caf\xe9\n")


class TestRoundTrip:
    """Decode then encode is the identity on the bytes, not just the text."""

    @pytest.mark.parametrize("codec", [
        "utf-8", "utf-8-sig", "utf-16-le", "utf-16-be",
        "utf-32-le", "utf-32-be",
    ])
    def test_bytes_in_bytes_out(self, codec):
        data = _with_bom(SRC, codec)
        text, found = enc.decode(data)
        assert found.encode(text) == data

    def test_a_bom_less_file_gains_no_mark(self):
        """Adding one would be a change to the file the user cannot see in
        the diff, and one that some downstream readers reject."""
        data = SRC.encode("utf-16-le")
        text, found = enc.decode(data)
        assert found.encode(text) == data
        assert not found.encode(text).startswith(codecs.BOM_UTF16_LE)

    def test_byte_order_is_preserved(self):
        """``utf-16`` as a codec name would re-encode BE as the platform's
        order. Naming the endianness explicitly is what stops that."""
        data = _with_bom(SRC, "utf-16-be")
        text, found = enc.decode(data)
        assert found.encode(text) == data


def _with_bom(text: str, codec: str) -> bytes:
    """``text`` encoded with *codec*, including its mark where it has one.

    Python's ``utf-16``/``utf-32`` aggregates write a mark; the explicit-order
    codecs do not. Spelling the order out and prepending the mark by hand
    keeps the fixture from depending on which of those a name happens to be.
    """
    marks = {
        "utf-8-sig": codecs.BOM_UTF8,
        "utf-16-le": codecs.BOM_UTF16_LE,
        "utf-16-be": codecs.BOM_UTF16_BE,
        "utf-32-le": codecs.BOM_UTF32_LE,
        "utf-32-be": codecs.BOM_UTF32_BE,
    }
    if codec == "utf-8-sig":
        return codecs.BOM_UTF8 + text.encode("utf-8")
    return marks.get(codec, b"") + text.encode(codec)

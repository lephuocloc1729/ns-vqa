"""Incremental decoding of one string field ("answer") from a streaming JSON reply.

The writer replies with a JSON object such as
    {"verdict": "yes", "answer": "Có. Biển P.103a ...", "cited_signs": [...], "cited_rules": [...]}
optionally inside a ```json fence. While the reply streams in, `FieldStream.feed`
returns the newly decoded characters of the field's string value, so the text can be
shown as it is written. Escapes split across chunks (\\", \\n, \\uXXXX, surrogate
pairs) are held back until complete. The decoded text is display-only: the shipped
answer is still the parsed, guard-checked reply.
"""

from __future__ import annotations

import re

_SIMPLE = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


class FieldStream:
    def __init__(self, field: str = "answer") -> None:
        self._key = re.compile(r'"' + re.escape(field) + r'"\s*:\s*"')
        self._buf = ""
        self._pos: int | None = None      # index in _buf of the next undecoded value character
        self.done = False
        self.text = ""

    def feed(self, chunk: str) -> str:
        """The characters of the field's value that `chunk` completes ('' if none)."""
        if self.done:
            return ""
        self._buf += chunk
        if self._pos is None:
            m = self._key.search(self._buf)
            if not m:
                return ""
            self._pos = m.end()
        out = []
        buf, i = self._buf, self._pos
        while i < len(buf):
            c = buf[i]
            if c == '"':
                self.done = True
                i += 1
                break
            if c != "\\":
                out.append(c)
                i += 1
                continue
            if i + 1 >= len(buf):
                break                                   # escape not complete yet
            e = buf[i + 1]
            if e in _SIMPLE:
                out.append(_SIMPLE[e])
                i += 2
                continue
            if e != "u":
                out.append(e)                           # invalid escape: keep the character
                i += 2
                continue
            if i + 6 > len(buf):
                break
            cp = int(buf[i + 2:i + 6], 16) if re.fullmatch(r"[0-9a-fA-F]{4}", buf[i + 2:i + 6]) else 0xFFFD
            if 0xD800 <= cp < 0xDC00:                   # high surrogate: needs its pair
                if i + 12 > len(buf):
                    break
                low = buf[i + 8:i + 12] if buf[i + 6:i + 8] == "\\u" else ""
                if re.fullmatch(r"[0-9a-fA-F]{4}", low) and 0xDC00 <= int(low, 16) < 0xE000:
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (int(low, 16) - 0xDC00)
                    i += 12
                else:
                    cp, i = 0xFFFD, i + 6
            else:
                i += 6
            out.append(chr(cp))
        self._pos = i
        new = "".join(out)
        self.text += new
        return new

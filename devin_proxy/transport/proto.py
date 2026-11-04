"""Hand-rolled protobuf encode/decode for the Devin wire.

No generated code Ã¢â‚¬â€ the schema is reverse-engineered and the field numbers
are the contract. `Message` is a small helper that renders a field map back
to bytes for debugging/tests.
"""
from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def tag(field: int, wt: int) -> bytes:
    return varint((field << 3) | wt)


def f_str(field: int, s: str | None) -> bytes:
    if not s:
        return b""
    d = str(s).encode("utf-8")
    return tag(field, 2) + varint(len(d)) + d


def f_varint(field: int, n: int) -> bytes:
    return tag(field, 0) + varint(n)


def f_double(field: int, x: float) -> bytes:
    return tag(field, 1) + struct.pack("<d", x)


def f_msg(field: int, body: bytes) -> bytes:
    return tag(field, 2) + varint(len(body)) + body


def _rd_varint(b: bytes, i: int) -> tuple[int, int]:
    shift = r = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << shift
        if not x & 0x80:
            return r, i
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def fields(b: bytes) -> Iterator[tuple[int, int, Any]]:
    """Yield (field_no, wire_type, value). value is bytes for len-delim, int for varint."""
    i, n = 0, len(b)
    while i < n:
        k, i = _rd_varint(b, i)
        no, wt = k >> 3, k & 7
        if wt == 0:
            v, i = _rd_varint(b, i)
            yield no, wt, v
        elif wt == 1:
            if i + 8 > n:
                raise ValueError("truncated fixed64")
            yield no, wt, b[i:i + 8]
            i += 8
        elif wt == 2:
            ln, i = _rd_varint(b, i)
            if i + ln > n:
                raise ValueError("truncated len-delim")
            yield no, wt, b[i:i + ln]
            i += ln
        elif wt == 5:
            if i + 4 > n:
                raise ValueError("truncated fixed32")
            yield no, wt, b[i:i + 4]
            i += 4
        else:
            raise ValueError(f"unknown wiretype {wt}")


@dataclass
class Message:
    """Convenience builder for a nested field map -> bytes."""
    body: bytes = b""

    def str_(self, field: int, s: str | None) -> Message:
        self.body += f_str(field, s)
        return self

    def varint_(self, field: int, n: int) -> Message:
        self.body += f_varint(field, n)
        return self

    def double_(self, field: int, x: float) -> Message:
        self.body += f_double(field, x)
        return self

    def msg(self, field: int, m: Message) -> Message:
        self.body += f_msg(field, m.body)
        return self

    def bytes_(self) -> bytes:
        return self.body

"""Connect-RPC client for `server.codeium.com`.

Speaks the protocol the Devin CLI uses: unary+stream over HTTP, gzip-framed
envelopes, `application/connect+proto`. Request and response bodies are
protobuf; the envelope is a 5-byte header (flag + big-endian len).
"""
from __future__ import annotations

import gzip
import struct
from collections.abc import AsyncIterator, Iterator

import httpx

CONNECT_HEADERS = {
    "content-type": "application/connect+proto",
    "connect-protocol-version": "1",
    "connect-content-encoding": "gzip",
    "connect-accept-encoding": "gzip",
    "user-agent": "connect-go/1.18.1",
}
PROTO_HEADERS = {
    "content-type": "application/proto",
    "connect-protocol-version": "1",
}


class ConnectError(Exception):
    def __init__(self, code: str, message: str, status: int | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status = status


def envelope(body: bytes) -> bytes:
    gz = gzip.compress(body)
    return b"\x01" + struct.pack(">I", len(gz)) + gz


def deframe(buf: bytes) -> Iterator[tuple[int, bytes]]:
    """Yield (flag, payload) for every complete Connect frame in buf."""
    while len(buf) >= 5:
        flag, ln = buf[0], struct.unpack(">I", buf[1:5])[0]
        if len(buf) < 5 + ln:
            break
        payload = buf[5:5 + ln]
        buf = buf[5 + ln:]
        if flag & 1:
            payload = gzip.decompress(payload)
        yield flag, payload


async def adeframe(aiter) -> AsyncIterator[tuple[int, bytes]]:
    buf = b""
    async for chunk in aiter:
        buf += chunk
        while len(buf) >= 5:
            flag, ln = buf[0], struct.unpack(">I", buf[1:5])[0]
            if len(buf) < 5 + ln:
                break
            payload = buf[5:5 + ln]
            buf = buf[5 + ln:]
            if flag & 1:
                payload = gzip.decompress(payload)
            yield flag, payload


class ConnectClient:
    """One pooled HTTP client speaking Connect-RPC to the Devin gateway."""

    def __init__(self, base: str, *, timeout: float = 300.0):
        self.base = base.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base,
            timeout=httpx.Timeout(timeout, connect=30.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def call(self, path: str, body: bytes) -> AsyncIterator[tuple[int, bytes]]:
        """POST a Connect request; yields (flag, payload) for each stream frame."""
        req = self._client.build_request(
            "POST", path, content=envelope(body), headers=CONNECT_HEADERS)
        resp = await self._client.send(req, stream=True)
        try:
            if resp.status_code != 200:
                await resp.aread()
                raise ConnectError(
                    code=f"http_{resp.status_code}",
                    message=resp.text[:300],
                    status=resp.status_code)
            async for flag, payload in adeframe(resp.aiter_bytes(65536)):
                yield flag, payload
        finally:
            await resp.aclose()

    async def unary(self, path: str, body: bytes) -> bytes:
        """POST a unary Connect call (application/proto)."""
        resp = await self._client.post(path, content=body, headers=PROTO_HEADERS)
        resp.raise_for_status()
        return resp.content

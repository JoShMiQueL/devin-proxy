"""OAuth unit tests: PKCE shape, exchange wire format, response parsing."""
from __future__ import annotations

import re

import pytest

from devin_proxy.transport.oauth import (
    _exchange,
    _token_from_response,
    pkce_pair,
)
from devin_proxy.transport.proto import Message, fields


def test_pkce_pair_shape():
    verifier, challenge = pkce_pair()
    assert 43 <= len(verifier) <= 128  # RFC 7636
    assert len(challenge) == 43         # S256 = sha256 -> b64url, no pad
    assert re.fullmatch(r"[A-Za-z0-9_-]+", verifier)
    assert re.fullmatch(r"[A-Za-z0-9_-]+", challenge)


def test_exchange_wire_layout():
    """The real wire layout (verified E2E): code@1, verifier@2, bare."""
    captured = {}

    class FakeH:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url, content, headers):
            captured["url"] = url
            captured["body"] = content
            r = type("R", (), {})()
            r.status_code = 200
            r.content = Message().str_(1, "session-token!").body
            return r

    import devin_proxy.transport.oauth as oa
    oa._http = type("hx", (), {"AsyncClient": lambda *a, **k: FakeH()})
    import asyncio
    tok = asyncio.new_event_loop().run_until_complete(
        _exchange("https://b", "the-code", "the-verifier"))
    assert tok == "session-token!"
    body = captured["body"]
    seen = {no: v for no, wt, v in fields(body)}
    assert seen[1] == b"the-code"
    assert seen[2] == b"the-verifier"
    assert len(seen) == 2  # nothing else — no metadata, no redirect


def test_token_from_response():
    body = Message().str_(1, "tok").str_(2, "noise").body
    assert _token_from_response(body) == "tok"
    assert _token_from_response(b"") == ""


def test_exchange_error_propagates():
    class FakeH:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url, content, headers):
            r = type("R", (), {})()
            r.status_code = 400
            r.text = '{"message":"Invalid or expired code."}'
            return r

    import devin_proxy.transport.oauth as oa
    oa._http = type("hx", (), {"AsyncClient": lambda *a, **k: FakeH()})
    import asyncio
    with pytest.raises(RuntimeError, match="exchange failed"):
        asyncio.new_event_loop().run_until_complete(
            _exchange("https://b", "c", "v"))

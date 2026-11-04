"""Auth unit tests: key resolution, credentials.toml round-trip, JWT mint
against a mocked Connect endpoint."""
from __future__ import annotations

import pytest

from devin_proxy.transport.auth import Auth, read_key, write_credentials
from devin_proxy.transport.proto import Message


def _write_cred(tmp_path, key="devin-session-token$test"):
    p = tmp_path / "credentials.toml"
    p.write_text(f'windsurf_api_key = "{key}"\n'
                 'api_server_url = "https://server.codeium.com"\n')
    return p


def test_read_key(tmp_path):
    p = _write_cred(tmp_path)
    assert read_key(p) == "devin-session-token$test"


def test_write_credentials_roundtrip(tmp_path):
    p = write_credentials(tmp_path / "credentials.toml", "tok123",
                          "https://x")
    assert p.exists()
    assert read_key(p) == "tok123"
    body = p.read_text()
    assert 'api_server_url = "https://x"' in body
    assert 'devin_api_url = "https://api.devin.ai"' in body


def test_api_key_env_wins(tmp_path, monkeypatch):
    p = _write_cred(tmp_path, "file-key")
    monkeypatch.setenv(Auth.ENV_KEY, "env-key")
    a = Auth("https://x", credentials=p)
    assert a.api_key() == "env-key"


def test_api_key_file_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv(Auth.ENV_KEY, raising=False)
    p = _write_cred(tmp_path, "file-key")
    a = Auth("https://x", credentials=p)
    assert a.api_key() == "file-key"


def test_api_key_missing(tmp_path, monkeypatch):
    monkeypatch.delenv(Auth.ENV_KEY, raising=False)
    a = Auth("https://x", credentials=tmp_path / "nope.toml")
    with pytest.raises((OSError, RuntimeError)):
        a.api_key()


async def test_jwt_parses_field1(tmp_path, monkeypatch):
    """Auth.jwt() must pull the token out of a unary GetUserJwt reply."""
    monkeypatch.setenv(Auth.ENV_KEY, "k")
    a = Auth("https://x", credentials=tmp_path / "c.toml")
    reply = Message().str_(1, "jwt-token-xyz").body

    async def fake_unary(self, path, body):
        assert "GetUserJwt" in path
        return reply

    monkeypatch.setattr("devin_proxy.transport.wire.ConnectClient.unary",
                        fake_unary)
    assert await a.jwt() == "jwt-token-xyz"
    # cached
    assert await a.jwt() == "jwt-token-xyz"


async def test_jwt_empty_reply_fails(tmp_path, monkeypatch):
    monkeypatch.setenv(Auth.ENV_KEY, "k")
    a = Auth("https://x", credentials=tmp_path / "c.toml")

    async def fake_unary(self, path, body):
        return Message().str_(9, "other").body

    monkeypatch.setattr("devin_proxy.transport.wire.ConnectClient.unary",
                        fake_unary)
    with pytest.raises(RuntimeError, match="no token"):
        await a.jwt()

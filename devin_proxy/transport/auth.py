"""Credential loading and JWT minting for the Devin gateway."""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from .proto import f_msg, fields
from .wire import ConnectClient


def default_credentials_path() -> Path:
    env = os.environ.get("DEVIN_PROXY_CRED")
    if env:
        return Path(env)
    home = Path.home()
    appdata = os.environ.get("APPDATA")
    for p in (
        home / ".devin" / "credentials.toml",
        (Path(appdata) / "devin" / "credentials.toml") if appdata else None,
        home / ".config" / "devin" / "credentials.toml",
    ):
        if p and p.exists():
            return p
    return home / ".devin" / "credentials.toml"


def read_key(path: Path) -> str:
    """windsurf_api_key out of a credentials.toml (Devin CLI format)."""
    s = path.read_text(encoding="utf-8")
    m = re.search(r'windsurf_api_key\s*=\s*"([^"]+)"', s)
    if not m:
        raise RuntimeError(f"no windsurf_api_key in {path}")
    return m.group(1)


def write_credentials(path: Path, api_key: str,
                      api_server: str = "https://server.codeium.com") -> Path:
    """Persist a session token in the Devin CLI's own credentials.toml
    format so `devin auth status` and the proxy both pick it up."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'windsurf_api_key = "{api_key}"\n'
        f'api_server_url = "{api_server}"\n'
        'devin_webapp_host = "app.devin.ai"\n'
        'devin_api_url = "https://api.devin.ai"\n',
        encoding="utf-8")
    return path


class Auth:
    """Resolves the session token (env > credentials.toml) and caches the
    short-lived JWT (10 min)."""

    ENV_KEY = "DEVIN_PROXY_API_KEY"

    def __init__(self, base: str, credentials: Path | None = None,
                 client_version: str = "",
                 client_channel: str = "chisel"):
        self.base = base.rstrip("/")
        self.credentials = credentials or default_credentials_path()
        from .devincli import FALLBACK_VERSION
        self.client_version = client_version or FALLBACK_VERSION
        self.client_channel = client_channel
        self._jwt: str | None = None
        self._jwt_ts = 0.0
        self._client = ConnectClient(self.base, timeout=30)

    def api_key(self) -> str:
        k = os.environ.get(self.ENV_KEY)
        if k:
            return k.strip()
        return read_key(self.credentials)

    async def jwt(self) -> str:
        if self._jwt and time.time() - self._jwt_ts < 600:
            return self._jwt
        body = f_msg(1, self._metadata())
        raw = await self._client.unary(
            "/exa.auth_pb.AuthService/GetUserJwt", body)
        for no, _wt, v in fields(raw):
            if no == 1:
                self._jwt = v.decode()
                self._jwt_ts = time.time()
                return self._jwt
        raise RuntimeError("GetUserJwt returned no token")

    def _metadata(self) -> bytes:
        from ..models.catalog import metadata
        return metadata(self.api_key(), version=self.client_version,
                        channel=self.client_channel)

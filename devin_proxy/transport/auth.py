"""Credential loading and JWT minting for the Devin gateway."""
from __future__ import annotations

import re
import time
from pathlib import Path

from .proto import f_msg, fields
from .wire import ConnectClient


def default_credentials_path() -> Path:
    import os
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


class Auth:
    """Reads the Devin CLI key and caches the short-lived JWT (10 min)."""

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
        s = self.credentials.read_text(encoding="utf-8")
        m = re.search(r'windsurf_api_key\s*=\s*"([^"]+)"', s)
        if not m:
            raise RuntimeError(f"no windsurf_api_key in {self.credentials}")
        return m.group(1)

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

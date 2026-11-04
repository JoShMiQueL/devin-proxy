"""Live probes: hit the real backend, assert wire contract holds.

Requires a session token via DEVIN_PROXY_API_KEY env or a credentials.toml
in the standard search paths. Skips cleanly when neither exists — these
run locally and in CI only when DEVIN_CREDENTIALS_TOML (full file) or
DEVIN_PROXY_API_KEY (bare token) is provided as a secret.
"""
from __future__ import annotations

import os

import pytest

from devin_proxy.config import load_settings
from devin_proxy.transport.auth import Auth

CRED_PATHS = (
    __import__("pathlib").Path.home() / ".devin" / "credentials.toml",
    __import__("pathlib").Path(
        os.environ.get("APPDATA", "")) / "devin" / "credentials.toml",
    __import__("pathlib").Path.home() / ".config" / "devin" / "credentials.toml",
)
LIVE = bool(os.environ.get("DEVIN_PROXY_API_KEY")) or any(
    p.exists() for p in CRED_PATHS)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not LIVE, reason="no devin credentials"),
]


@pytest.fixture()
def settings():
    return load_settings()


@pytest.fixture()
def auth(settings):
    return Auth(settings.backend, settings.credentials,
                settings.client_version, settings.client_channel)


async def test_jwt_mints(auth):
    jwt = await auth.jwt()
    assert len(jwt) > 100


async def test_catalog_has_swe2(settings, auth):
    from devin_proxy.models.fetch import fetch_catalog
    cat = await fetch_catalog(settings.backend, auth.api_key(), "",
                              settings.client_version,
                              settings.client_channel, timeout=15)
    assert cat is not None
    uids = {c.uid for c in cat}
    assert {"swe-2-medium", "swe-2-high", "swe-2-max"} <= uids


async def test_user_status_profile(settings, auth):
    from devin_proxy.models.fetch import fetch_user_status
    me = await fetch_user_status(settings.backend, auth.api_key(), "",
                                 settings.client_version,
                                 settings.client_channel, timeout=15)
    assert me.get("name")


async def test_health_endpoint(settings, auth):
    """The full serve path: /health reports override + catalog."""
    from fastapi.testclient import TestClient

    from devin_proxy.api.routes import build_app
    from devin_proxy.jailbreak.override import OverridePrompt
    from devin_proxy.pipeline import Engine
    engine = Engine(settings, auth, OverridePrompt(settings.system_file))
    app = build_app(settings, auth, engine,
                    OverridePrompt(settings.system_file))
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

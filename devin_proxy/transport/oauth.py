"""Browser OAuth (PKCE) login for Devin — no Devin CLI required.

Mirrors the CLI's own flow (strings recovered from the binary):
  1. open {webapp}/auth/cli/continue?redirect_uri=<loopback>&state=<csrf>
     &prompt=select_account&code_challenge=<S256>&code_challenge_method=S256
  2. loopback HTTP server captures the authorization-code redirect
  3. exchange code+verifier via Connect-RPC
     SeatManagementService/ExchangeDevinCLIPKCECode -> session token
  4. token persisted in credentials.toml (Devin CLI format)

The webapp's /auth/cli/continue is SPA-served (the JS decides the real
OAuth provider redirect); we reproduce the parameters the CLI passes and
let their frontend drive the Google/GitHub sign-in as usual.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import httpx as _http

WEBAPP = "https://app.devin.ai"
EXCHANGE_PATH = ("/exa.seat_management_pb.SeatManagementService/"
                 "ExchangeDevinCLIPKCECode")
TIMEOUT_S = 300


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def pkce_pair() -> tuple[str, str]:
    """(verifier, S256 challenge)."""
    verifier = _b64url(secrets.token_bytes(64))[:96]
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def _token_from_response(content: bytes) -> str:
    """session token = field-1 string in the exchange response."""
    from .proto import fields
    for no, wt, v in fields(content):
        if no == 1 and wt == 2:
            try:
                return v.decode()
            except UnicodeDecodeError:
                break
    return ""


async def _exchange(backend: str, code: str, verifier: str) -> str:
    """code + verifier -> session token via SeatManagementService.

    Wire layout verified E2E against the live backend: **bare** request —
    authorization_code at field 1, code_verifier at field 2. No metadata
    sub-message (unlike the chat RPCs), no redirect_uri.
    """
    import json

    from .proto import Message

    body = Message().str_(1, code).str_(2, verifier).body
    async with _http.AsyncClient(timeout=30) as h:
        r = await h.post(
            backend.rstrip("/") + EXCHANGE_PATH, content=body,
            headers={"content-type": "application/proto",
                     "connect-protocol-version": "1",
                     "user-agent": "connect-go/1.18.1"})
    if r.status_code != 200:
        try:
            detail = json.loads(r.text).get("message", r.text)
        except Exception:
            detail = r.text
        raise RuntimeError(f"exchange failed ({r.status_code}): {detail}")
    tok = _token_from_response(r.content)
    if not tok:
        raise RuntimeError("exchange returned no session token")
    return tok


class _Callback(BaseHTTPRequestHandler):
    """Loopback receiver: the SPA redirects here with ?code=&state=."""

    code = state = error = ""

    def do_GET(self):
        q = urllib.parse.urlparse(self.path).query
        p = urllib.parse.parse_qs(q)
        type(self).code = p.get("code", [""])[0]
        type(self).state = p.get("state", [""])[0]
        type(self).error = p.get("error", [""])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        ok = bool(self.code)
        body = ("<h1>devin-proxy login — done, you can close this tab</h1>"
                if ok else
                "<h1>devin-proxy login — failed, check the terminal</h1>")
        self.wfile.write(f"<html><body>{body}</body></html>".encode())

    def log_message(self, *_):
        pass


async def browser_login(backend: str,
                        open_browser: bool = True,
                        timeout: float = TIMEOUT_S) -> str:
    """Run the full PKCE loopback flow; returns the session token."""
    import asyncio
    import time

    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)

    httpd = HTTPServer(("127.0.0.1", 0), _Callback)
    port = httpd.server_address[1]
    Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.2},
           daemon=True).start()

    redirect = f"http://127.0.0.1:{port}/callback"
    url = (f"{WEBAPP}/auth/cli/continue"
           f"?redirect_uri={urllib.parse.quote(redirect, safe='')}"
           f"&state={state}"
           f"&prompt=select_account"
           f"&code_challenge={challenge}"
           f"&code_challenge_method=S256")

    print(f"browser login: {url}")
    if open_browser:
        webbrowser.open(url)
    print(f"waiting for browser callback (timeout {int(timeout)}s)...")

    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            if _Callback.code or _Callback.error:
                break
            await asyncio.sleep(0.25)
    finally:
        httpd.shutdown()

    if _Callback.error:
        raise RuntimeError(f"auth server returned error: {_Callback.error}")
    if not _Callback.code:
        raise TimeoutError("no callback received — flow timed out")
    if _Callback.state != state:
        raise RuntimeError("state mismatch — possible CSRF, aborting")

    return await _exchange(backend, _Callback.code, verifier)

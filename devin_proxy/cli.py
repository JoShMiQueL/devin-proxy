"""devin-proxy CLI: serve (default), doctor, models, config, update."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import __version__
from .config import load_settings

REPO = "JoShMiQueL/devin-proxy"
API = f"https://api.github.com/repos/{REPO}"


def _gh_token() -> str | None:
    """GitHub token from env or `gh auth token` (private-repo releases)."""
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        r = subprocess.run(["gh", "auth", "token"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


def _latest_release() -> dict | None:
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": f"devin-proxy/{__version__}"}
    tok = _gh_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(f"{API}/releases/latest", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return None


def cmd_serve(args) -> int:
    from .server import serve
    return serve(host=args.host, port=args.port)


def cmd_doctor(_args) -> int:
    import asyncio
    ok = True
    s = load_settings()
    print(f"devin-proxy {__version__}")
    print(f"listen      : {s.host}:{s.port}")
    print(f"backend     : {s.backend}")
    print(f"models      : {', '.join(s.allowed_models)} "
          f"(default={s.default_model}, client sees '{s.client_model_id}')")

    # credentials
    try:
        from .transport.auth import Auth
        auth = Auth(s.backend, s.credentials,
                    s.client_version, s.client_channel)
        key = auth.api_key()
        print(f"credentials : ok ({s.credentials}, key …{key[-6:]})")
    except Exception as e:
        ok = False
        auth = None
        print(f"credentials : FAIL ({e})")

    # override
    from .jailbreak.override import OverridePrompt
    ov = OverridePrompt(s.system_file)
    text = ov.load()
    state = f"ok ({ov.path}, {len(text)} chars)" if text else f"none ({ov.path})"
    print(f"override    : {state}")

    # backend reachability + catalog
    if auth:
        try:
            from .models.fetch import fetch_catalog
            cat = asyncio.new_event_loop().run_until_complete(
                fetch_catalog(s.backend, auth.api_key(), "",
                              s.client_version, s.client_channel,
                              timeout=10))
            n = len(list(cat)) if cat else 0
            print(f"backend     : ok (catalog: {n} configs)" if cat
                  else "backend     : reachable, catalog empty")
            if not cat:
                ok = False
        except Exception as e:
            ok = False
            print(f"backend     : FAIL ({e})")
    else:
        print("backend     : skipped (no credentials)")
    return 0 if ok else 1


def cmd_models(_args) -> int:
    import asyncio
    s = load_settings()
    from .models.fetch import fetch_catalog
    from .transport.auth import Auth
    auth = Auth(s.backend, s.credentials, s.client_version, s.client_channel)
    cat = asyncio.new_event_loop().run_until_complete(
        fetch_catalog(s.backend, auth.api_key(), "",
                      s.client_version, s.client_channel))
    if not cat:
        print("catalog unavailable", file=sys.stderr)
        return 1
    print(f"client-facing model: {s.client_model_id} ({s.client_model_name})")
    print("allowed wire lanes:")
    for uid in s.allowed_models:
        cfg = cat.get(uid)
        if cfg:
            ctx = f"{cfg.context // 1024}k" if cfg.context else "?"
            print(f"  {uid:<16} name={cfg.name or '?':<12} ctx={ctx}")
        else:
            print(f"  {uid:<16} (not in upstream catalog)")
    n = len(list(cat))
    print(f"upstream catalog: {n} configs total")
    return 0


def cmd_config(_args) -> int:
    s = load_settings()
    for name in sorted(s.model_fields):
        v = getattr(s, name)
        if isinstance(v, Path):
            v = str(v)
        elif isinstance(v, tuple):
            v = ",".join(v)
        print(f"{name:<16} = {v}")
    print(f"{'system_file':<16} = {s.system_file or '(auto)'}")
    return 0


def cmd_update(args) -> int:
    rel = _latest_release()
    if not rel:
        print("cannot reach GitHub releases", file=sys.stderr)
        return 1
    tag = rel["tag_name"].lstrip("v")
    if args.check:
        state = "up to date" if tag == __version__ else f"update available: {tag}"
        print(f"installed {__version__}, latest {tag} — {state}")
        return 0 if tag == __version__ else 2
    if tag == __version__ and not args.dev:
        print(f"already at {__version__} (latest)")
        return 0
    if args.dev:
        spec = f"git+https://github.com/{REPO}@master"
    else:
        wheel = next((a["browser_download_url"] for a in rel.get("assets", [])
                      if a["name"].endswith(".whl")), None)
        spec = wheel or f"git+https://github.com/{REPO}@{rel['tag_name']}"
    print(f"installing {spec}")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-U", spec])
    return r.returncode


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="devin-proxy",
        description="Uncensored OpenAI-compatible proxy for the Devin SWE-2 backend.")
    p.add_argument("--version", action="version",
                   version=f"devin-proxy {__version__}")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("serve", help="run the proxy (default)")
    sp.add_argument("-H", "--host", default=None)
    sp.add_argument("-p", "--port", type=int, default=None)
    sp.set_defaults(fn=cmd_serve)

    sub.add_parser("doctor", help="check credentials, backend, override"
                   ).set_defaults(fn=cmd_doctor)
    sub.add_parser("models", help="list upstream model catalog"
                   ).set_defaults(fn=cmd_models)
    sub.add_parser("config", help="dump effective settings"
                   ).set_defaults(fn=cmd_config)

    up = sub.add_parser("update", help="self-update to latest release")
    up.add_argument("--check", action="store_true",
                    help="only report whether an update exists")
    up.add_argument("--dev", action="store_true",
                    help="install master instead of the latest release")
    up.set_defaults(fn=cmd_update)

    args = p.parse_args(argv)
    fn = getattr(args, "fn", None) or cmd_serve
    if fn is cmd_serve and not hasattr(args, "host"):
        args.host = args.port = None
    return fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

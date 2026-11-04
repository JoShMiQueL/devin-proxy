"""devin-proxy CLI: serve (default), service lifecycle, doctor, models,
config, update, login/logout."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import __version__
from .config import load_settings

REPO = "JoShMiQueL/devin-proxy"
API = f"https://api.github.com/repos/{REPO}"
DEFAULT_NAME = "default"


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


def _update_notice() -> str:
    """'update available: X.Y.Z' or '' — 400ms cap, never raises."""
    try:
        rel = _latest_release()
        if not rel:
            return ""
        tag = str(rel.get("tag_name", "")).lstrip("v")
        return f"update available: {tag}" if tag != __version__ else ""
    except Exception:
        return ""


def cmd_serve(args) -> int:
    """Foreground serve — but first ensure a registered background instance
    exists so other tooling can attach. The spawned one is announced."""
    if not getattr(args, "no_autostart", False):
        from .service import get, start
        if not get(DEFAULT_NAME):
            try:
                inst, spawned = start(DEFAULT_NAME)
                if spawned:
                    print(f"[devin-proxy] background service started "
                          f"(pid {inst.pid}) at {inst.url}",
                          file=sys.stderr)
            except Exception as e:
                print(f"[devin-proxy] autostart failed: {e}",
                      file=sys.stderr)
    from .server import serve
    return serve(host=args.host, port=args.port)


def cmd_service(args) -> int:
    from .service import get, instances, restart, start, stop
    act = args.svc_cmd or "status"
    name = args.name or DEFAULT_NAME

    if act == "start":
        inst, spawned = start(name, getattr(args, "host", None),
                              getattr(args, "port", None))
        if spawned:
            print(f"started {inst.name}: pid {inst.pid} at {inst.url}")
        else:
            print(f"{inst.name} already running at {inst.url}")
        return 0
    if act == "stop":
        stopped = stop(None if args.all else name, all_=args.all)
        if not stopped:
            print("no running instance")
            return 1
        for i in stopped:
            print(f"stopped {i.name} (pid {i.pid})")
        return 0
    if act == "restart":
        inst, _ = restart(name, getattr(args, "host", None),
                          getattr(args, "port", None))
        print(f"restarted {inst.name}: pid {inst.pid} at {inst.url}")
        return 0
    if act == "logs":
        inst = get(name, probe=False)
        if not inst or not inst.log_file.exists():
            print(f"no log for {name}", file=sys.stderr)
            return 1
        lines = inst.log_file.read_text(
            encoding="utf-8", errors="replace").splitlines()
        for ln in lines[-args.lines:]:
            sys.stdout.buffer.write(
                (ln + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
        return 0
    # status / list
    insts = instances()
    if not insts:
        print("no running instances")
        return 1
    print(f"{'name':<12} {'pid':>6} {'url':<24} {'version':<10} uptime")
    for i in insts:
        up = time.time() - i.started_at if i.started_at else 0
        h, m = int(up // 3600), int(up % 3600 // 60)
        print(f"{i.name:<12} {i.pid:>6} {i.url:<24} {i.version:<10} {h}h{m}m")
    return 0


def cmd_login(args) -> int:
    """Authenticate: browser PKCE flow (default) or paste a session token.

    The token is written to credentials.toml in the Devin CLI's own format —
    `devin auth status` will also see it. Alternatively keep it only in the
    DEVIN_PROXY_API_KEY env var (Auth reads env first).
    """
    import asyncio
    import getpass

    from .transport.auth import Auth, default_credentials_path, write_credentials

    s = load_settings()
    token = (args.token or "").strip()
    if not token and not args.token_only:
        try:
            from .transport.oauth import browser_login
            token = asyncio.new_event_loop().run_until_complete(
                browser_login(s.backend,
                              open_browser=not args.no_browser))
        except (RuntimeError, TimeoutError) as e:
            print(f"browser flow failed: {e}", file=sys.stderr)
            print("fall back to --token (paste a session token)",
                  file=sys.stderr)
            return 1
    elif not token:
        token = getpass.getpass(
            "devin session token (devin-session-token$...): ").strip()
    if not token:
        print("no token given", file=sys.stderr)
        return 1
    auth = Auth(s.backend, client_version=s.client_version,
                client_channel=s.client_channel)
    prev = os.environ.get(Auth.ENV_KEY)
    os.environ[Auth.ENV_KEY] = token
    try:
        jwt = asyncio.new_event_loop().run_until_complete(auth.jwt())
    except Exception as e:
        print(f"token rejected by backend: {e}", file=sys.stderr)
        return 1
    finally:
        if prev is None:
            os.environ.pop(Auth.ENV_KEY, None)
        else:
            os.environ[Auth.ENV_KEY] = prev
    print(f"token ok (jwt minted, {len(jwt)}B)")
    if args.env_only:
        print(f"set {Auth.ENV_KEY}=<token> in your environment — not stored")
        return 0
    path = write_credentials(default_credentials_path(), token, s.backend)
    print(f"written: {path}")
    return 0


def cmd_logout(_args) -> int:
    from .transport.auth import default_credentials_path
    p = default_credentials_path()
    if p.exists():
        p.unlink()
        print(f"removed {p}")
    else:
        print(f"nothing at {p}")
    return 0


def cmd_doctor(_args) -> int:
    import asyncio
    ok = True
    s = load_settings()
    print(f"devin-proxy {__version__}")
    print(f"listen      : {s.host}:{s.port}")
    print(f"backend     : {s.backend}")
    pinned = bool(os.environ.get("DEVIN_PROXY_CLIENT_VERSION"))
    src = "pinned" if pinned else "auto (devin CLI/fallback)"
    print(f"fingerprint : {s.client_version} / {s.client_channel} [{src}]")
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

    # backend reachability + catalog + account
    if auth:
        try:
            from .models.fetch import fetch_catalog, fetch_user_status
            loop = asyncio.new_event_loop()
            cat = loop.run_until_complete(
                fetch_catalog(s.backend, auth.api_key(), "",
                              s.client_version, s.client_channel,
                              timeout=10))
            n = len(list(cat)) if cat else 0
            print(f"backend     : ok (catalog: {n} configs)" if cat
                  else "backend     : reachable, catalog empty")
            if not cat:
                ok = False
            me = loop.run_until_complete(
                fetch_user_status(s.backend, auth.api_key(), "",
                                  s.client_version, s.client_channel,
                                  timeout=10))
            if me:
                who = f"{me['name']} <{me['email']}>" if me.get("email") \
                    else me.get("name", "?")
                print(f"account     : {who}")
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
        print(f"installing {spec}")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-U", spec])
        return r.returncode
    wheel = next((a["browser_download_url"] for a in rel.get("assets", [])
                  if a["name"].endswith(".whl")), None)
    if wheel:
        # wheel in place: never touches devin-proxy.exe, so a running
        # instance can't brick the install the way pip's uninstall does.
        from ._selfupdate import _site_packages, cleanup_stale, install_wheel
        sp = _site_packages()
        cleaned = cleanup_stale(sp)
        if cleaned:
            print(f"cleaned stale dirs: {cleaned}")
        tgt = install_wheel(wheel, tag)
        print(f"installed {tag} -> {tgt}")
        return 0
    spec = f"git+https://github.com/{REPO}@{rel['tag_name']}"
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
    sp.add_argument("--no-autostart", action="store_true",
                    help="don't auto-start the background service first")
    sp.set_defaults(fn=cmd_serve)

    svc = sub.add_parser("service",
                         help="manage background instances")
    svc.add_argument("svc_cmd", nargs="?",
                     choices=["start", "stop", "restart", "status",
                              "list", "logs"],
                     default="status")
    svc.add_argument("name", default=DEFAULT_NAME,
                     help="instance name (default 'default')")
    svc.add_argument("-H", "--host", default=None)
    svc.add_argument("-p", "--port", type=int, default=None)
    svc.add_argument("--all", action="store_true",
                     help="stop every running instance")
    svc.add_argument("-n", "--lines", type=int, default=40,
                     help="log lines to print (logs subcommand)")
    svc.set_defaults(fn=cmd_service)

    sub.add_parser("doctor", help="check credentials, backend, override"
                   ).set_defaults(fn=cmd_doctor)

    lg = sub.add_parser("login",
                        help="browser OAuth login or paste a session token")
    lg.add_argument("--token", default=None,
                    help="session token; skips the browser flow")
    lg.add_argument("--token-only", action="store_true",
                    help="prompt for a token, never open the browser")
    lg.add_argument("--no-browser", action="store_true",
                    help="print the auth URL instead of opening it")
    lg.add_argument("--env-only", action="store_true",
                    help="validate only; use DEVIN_PROXY_API_KEY at runtime")
    lg.set_defaults(fn=cmd_login)
    sub.add_parser("logout", help="remove stored credentials"
                   ).set_defaults(fn=cmd_logout)
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
    notice = _update_notice()
    if notice:
        print(f"[devin-proxy] {notice} — devin-proxy update", file=sys.stderr)
    return fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

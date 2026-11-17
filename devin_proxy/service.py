"""Background service registry — spawn/detach/discover devin-proxy instances.

opencode-style: each running instance registers itself under
``~/.devin-proxy/services/<name>.json`` (pid, host, port, url, version,
started_at). Discovery = read the files, probe ``/health``, drop stale
ones. No OS service manager — detached child processes; the registry is
the contract.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

REG_DIR = Path.home() / ".devin-proxy" / "services"
DEFAULT_NAME = "default"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8390


@dataclass
class Instance:
    name: str
    pid: int
    host: str
    port: int
    url: str
    version: str = ""
    started_at: float = 0.0
    alive: bool = False

    @property
    def file(self) -> Path:
        return REG_DIR / f"{self.name}.json"

    @property
    def log_file(self) -> Path:
        return REG_DIR / f"{self.name}.log"


def _version() -> str:
    from . import __version__
    return __version__


def _probe(url: str, timeout: float = 1.5) -> bool:
    # cheap TCP check first: uvicorn binds before the app is ready, so a
    # refused socket means "still importing" and we skip the HTTP round-trip
    import socket
    from urllib.parse import urlparse
    try:
        host, port = urlparse(url).hostname, urlparse(url).port
        with socket.socket() as s:
            s.settimeout(0.2)
            if s.connect_ex((host, port)) != 0:
                return False
    except OSError:
        return False
    try:
        with urllib.request.urlopen(url + "/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate(pid: int) -> None:
    """Graceful stop: SIGTERM on POSIX, taskkill /T on Windows."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True)
        return
    import contextlib
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGTERM)


def _read(name: str) -> Instance | None:
    try:
        d = json.loads((REG_DIR / f"{name}.json").read_text(encoding="utf-8"))
        return Instance(name=name, pid=int(d.get("pid") or 0),
                        host=str(d.get("host") or ""),
                        port=int(d.get("port") or 0),
                        url=str(d.get("url") or ""),
                        version=str(d.get("version") or ""),
                        started_at=float(d.get("started_at") or 0.0))
    except Exception:
        return None


def get(name: str = DEFAULT_NAME, probe: bool = True) -> Instance | None:
    """One registered instance, or None if absent/dead (stale file removed)."""
    inst = _read(name)
    if not inst or not inst.url:
        return None
    if probe:
        inst.alive = _pid_alive(inst.pid) and _probe(inst.url)
        if not inst.alive:
            inst.file.unlink(missing_ok=True)
            return None
    return inst


def instances() -> list[Instance]:
    """All registered instances that answer /health; stale files pruned."""
    out = []
    if not REG_DIR.is_dir():
        return out
    for f in sorted(REG_DIR.glob("*.json")):
        inst = get(f.stem)
        if inst:
            out.append(inst)
    return out


def _free_port(host: str, preferred: int, span: int = 20) -> int:
    """First connectable-free port at or after ``preferred``.

    If ``preferred`` itself is free it wins; otherwise we walk up to
    ``span`` ports looking for a closed socket. 0 lets the OS pick.
    """
    import socket
    if preferred == 0:
        with socket.socket() as s:
            s.bind((host, 0))
            return s.getsockname()[1]
    for p in range(preferred, preferred + span + 1):
        with socket.socket() as s:
            if s.connect_ex((host, p)) != 0:
                return p
    raise RuntimeError(
        f"no free port in {host}:{preferred}-{preferred + span} "
        "— everything is taken")


def start(name: str = DEFAULT_NAME, host: str | None = None,
          port: int | None = None, wait: float = 15.0,
          env_extra: dict | None = None,
          strict_port: bool = False) -> tuple[Instance, bool]:
    """Spawn a detached ``devin_proxy serve`` and register it.

    Returns (instance, spawned) — spawned=False when a healthy instance
    under that name already exists. ``port=None`` auto-picks the first
    free port at or after the default; ``strict_port`` refuses to fall
    back when the requested port is taken.
    """
    host = host or DEFAULT_HOST
    existing = get(name)
    if existing:
        return existing, False

    import socket
    if port is not None and strict_port:
        with socket.socket() as s:
            if s.connect_ex((host, port)) == 0:
                raise RuntimeError(
                    f"{host}:{port} already has a listener")
    port = _free_port(host, DEFAULT_PORT if port is None else port)

    REG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(REG_DIR / f"{name}.log", "ab")  # noqa: SIM115 — kept alive by
    # The spawned process is the SUPERVISOR (`devin_proxy supervise`), not
    # `serve` itself. The supervisor owns respawning the real serve child
    # whenever it dies — a bare `serve` leaving the port unbound is what
    # produced the client-visible ECONNREFUSED gaps. Its job is simple:
    # spawn serve, wait() on it, restart it if it exits (with a small
    # backoff so a crash-loop doesn't spin the CPU).
    cmd = [sys.executable, "-m", "devin_proxy", "supervise",
           "-H", host, "-p", str(port), "--name", name]
    kw: dict = {}
    if os.name == "nt":
        # console-free + detached — survives the parent shell closing, but
        # no DETACHED_PROCESS/CREATE_NEW_PROCESS_GROUP: those make uvicorn's
        # reloader spawn a zombie tree (parent re-parented to a dead pid).
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        kw["start_new_session"] = True
    env = dict(os.environ)
    env.update(env_extra or {})
    proc = subprocess.Popen(cmd, stdout=log, stderr=log,
                            stdin=subprocess.DEVNULL, env=env, **kw)

    url = f"http://{host}:{port}"
    deadline = time.time() + wait
    t0 = time.time()
    spin = "|/-\\"
    n = 0
    _verbose = not os.environ.get("DEVIN_PROXY_QUIET")
    while time.time() < deadline:
        if proc.poll() is not None:
            if _verbose:
                print()
            raise RuntimeError(
                f"service exited rc={proc.returncode} — see {log.name}")
        if _probe(url):
            inst = Instance(name, proc.pid, host, port, url,
                            version=_version(),
                            started_at=time.time(), alive=True)
            inst.file.write_text(json.dumps(asdict(inst), indent=2),
                                 encoding="utf-8")
            if _verbose:
                print(f"\r{' ' * 60}\r", end="", flush=True)
            return inst, True
        if _verbose:
            elapsed = time.time() - t0
            print(f"\r{spin[n % 4]} waiting for {url}/health "
                  f"({elapsed:.0f}s)…", end="", flush=True)
        n += 1
        time.sleep(0.25)
    proc.terminate()
    if _verbose:
        print()
    raise RuntimeError(f"service did not answer /health within {wait}s")


def stop(name: str | None = None, all_: bool = False,
         wait: float = 5.0) -> list[Instance]:
    """SIGTERM registered instances; returns the ones signalled."""
    if all_:
        targets = instances()
    else:
        inst = get(name or DEFAULT_NAME)
        targets = [inst] if inst else []
    stopped = []
    _verbose = not os.environ.get("DEVIN_PROXY_QUIET")
    for inst in targets:
        if _verbose:
            print(f"stopping {inst.name} (pid {inst.pid})…",
                  end=" ", flush=True)
        _terminate(inst.pid)
        inst.file.unlink(missing_ok=True)
        stopped.append(inst)
    for inst in stopped:
        # fresh budget per instance — a slow die shouldn't starve the rest
        deadline = time.time() + wait
        while time.time() < deadline and _pid_alive(inst.pid):
            time.sleep(0.1)
        if _verbose:
            print("ok" if not _pid_alive(inst.pid) else "still dying")
    return stopped


def restart(name: str = DEFAULT_NAME, host: str | None = None,
            port: int | None = None) -> tuple[Instance, bool]:
    old = get(name, probe=False)
    if old:
        host = host or old.host
        port = port or old.port
    stop(name)
    return start(name, host, port)

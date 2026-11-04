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
    port = _free_port(host, port or DEFAULT_PORT)

    REG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(REG_DIR / f"{name}.log", "ab")  # noqa: SIM115 — kept alive by
    cmd = [sys.executable, "-m", "devin_proxy", "serve",  #   the child proc
           "-H", host, "-p", str(port)]
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

    # The child may autospawn its own background instance on a free port
    # (serve's autostart). Watch the registry dir and adopt whatever it
    # writes so the process we spawned doesn't orphan its own proxy.
    url = f"http://{host}:{port}"
    deadline = time.time() + wait
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"service exited rc={proc.returncode} — see {log.name}")
        for jf in REG_DIR.glob("*.json"):
            if jf.stem == name:
                continue
            d = _read(jf.stem)
            if not (d and d.url):
                continue
            # adopt only fresh registrations (< wait s old) — older ones
            # are someone else's running services, not our child.
            if d.started_at and time.time() - d.started_at > wait:
                continue
            if _pid_alive(d.pid) and _probe(d.url):
                inst = Instance(name, d.pid, d.host, d.port, d.url,
                                version=d.version or _version(),
                                started_at=d.started_at, alive=True)
                inst.file.write_text(json.dumps(asdict(inst), indent=2),
                                     encoding="utf-8")
                jf.unlink(missing_ok=True)
                return inst, True
        if _probe(url):
            inst = Instance(name, proc.pid, host, port, url,
                            version=_version(),
                            started_at=time.time(), alive=True)
            inst.file.write_text(json.dumps(asdict(inst), indent=2),
                                 encoding="utf-8")
            return inst, True
        time.sleep(0.25)
    proc.terminate()
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
    for inst in targets:
        _terminate(inst.pid)
        inst.file.unlink(missing_ok=True)
        stopped.append(inst)
    deadline = time.time() + wait
    for inst in stopped:
        while time.time() < deadline and _pid_alive(inst.pid):
            time.sleep(0.1)
    return stopped


def restart(name: str = DEFAULT_NAME, host: str | None = None,
            port: int | None = None) -> tuple[Instance, bool]:
    old = get(name, probe=False)
    if old:
        host = host or old.host
        port = port or old.port
    stop(name)
    return start(name, host, port)

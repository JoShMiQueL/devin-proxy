"""Self-update: extract a release wheel over site-packages in place.

pip's uninstall-then-install breaks on Windows when a running
devin-proxy.exe holds the script shim — the module is removed first and
the new exe can't overwrite, leaving a dead install. Instead: download
the wheel, copy only ``devin_proxy/`` (the payload) onto the existing
site-packages tree, and write a minimal dist-info so pip sees the new
version. The shim exe never changes between releases, so it is left
alone.
"""
from __future__ import annotations

import io
import shutil
import site
import sys
import sysconfig
import tempfile
import urllib.request
import zipfile
from pathlib import Path

NAME = "devin-proxy"
PKG = "devin_proxy"


def _site_packages() -> Path:
    for p in (sysconfig.get_paths().get("purelib"),
              *(site.getsitepackages() or []),
              site.getusersitepackages()):
        if p and Path(p).is_dir():
            return Path(p)
    raise RuntimeError("cannot locate site-packages")


def _download(url: str) -> bytes:
    if not url.startswith(("http://", "https://")):
        return Path(url).read_bytes()  # local .whl file
    req = urllib.request.Request(
        url, headers={"User-Agent": "devin-proxy-updater"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _dist_info_name(version: str) -> str:
    # pip normalizes the project name: dashes -> underscores in the
    # dist-info dir (devin_proxy-0.6.0.dist-info), so pip show finds it.
    return f"{PKG}-{version}.dist-info"


def install_wheel(url: str, version: str) -> Path:
    """Extract ``devin_proxy/`` from the wheel at ``url`` into site-packages."""
    raw = _download(url)
    sp = _site_packages()
    target = sp / PKG

    with zipfile.ZipFile(io.BytesIO(raw)) as z, tempfile.TemporaryDirectory() as td:
        z.extractall(td)
        td_root = Path(td)
        root = td_root / PKG
        if not root.is_dir():
            raise RuntimeError(f"{PKG}/ missing in wheel")

        # wipe the old package tree (but not unrelated dirs)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(root, target)

        # copy the wheel's dist-info verbatim — pip's metadata parser
        # needs a real METADATA+RECORD; a stub crashes pip show.
        src_info = next(td_root.glob("*.dist-info"), None)
        info = target.parent / _dist_info_name(version)
        if info.exists():
            shutil.rmtree(info)
        if src_info and src_info.is_dir():
            shutil.copytree(src_info, info)
        else:
            info.mkdir(exist_ok=True)
            (info / "METADATA").write_text(
                f"Metadata-Version: 2.1\nName: {NAME}\nVersion: {version}\n",
                encoding="utf-8")
            (info / "RECORD").write_text(f"{PKG}/,,\n",
                                         encoding="utf-8")
    return target


def cleanup_stale(sp: Path) -> list[str]:
    """Remove ``~name`` leftovers pip leaves behind on failed uninstalls."""
    out = []
    for p in sp.glob("~evin*"):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            out.append(p.name)
    return out


def main(url: str, version: str) -> int:
    sp = _site_packages()
    print(f"site-packages: {sp}")
    stale = cleanup_stale(sp)
    if stale:
        print(f"cleaned stale dirs: {stale}")
    tgt = install_wheel(url, version)
    print(f"installed {version} -> {tgt}")
    # verify import
    sys.path.insert(0, str(sp))
    import importlib
    importlib.invalidate_caches()
    mod = importlib.import_module(PKG)
    print(f"import ok: {mod.__file__} v{mod.__version__}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python -m devin_proxy._selfupdate <wheel-url> <version>")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))

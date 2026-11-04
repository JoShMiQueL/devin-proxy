"""Cross-platform path-resolution tests: credentials + override search order."""
import os
from pathlib import Path

import pytest

from devin_proxy.jailbreak.override import default_system_file
from devin_proxy.transport.auth import default_credentials_path


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for k in list(os.environ):
        if k.startswith("DEVIN_PROXY_") or k in ("APPDATA", "XDG_CONFIG_HOME"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def test_cred_env_wins(monkeypatch, tmp_path):
    f = tmp_path / "custom.toml"
    f.write_text("x")
    monkeypatch.setenv("DEVIN_PROXY_CRED", str(f))
    assert default_credentials_path() == f


def test_cred_linux_xdg(tmp_path):
    (tmp_path / ".config" / "devin").mkdir(parents=True)
    f = tmp_path / ".config" / "devin" / "credentials.toml"
    f.write_text("x")
    # no APPDATA on linux/mac — the xdg path is hit
    assert default_credentials_path() == f


def test_cred_windows_appdata(monkeypatch, tmp_path):
    appdata = tmp_path / "Roaming"
    (appdata / "devin").mkdir(parents=True)
    f = appdata / "devin" / "credentials.toml"
    f.write_text("x")
    monkeypatch.setenv("APPDATA", str(appdata))
    assert default_credentials_path() == f


def test_cred_prefers_devin_dotdir(tmp_path):
    (tmp_path / ".devin").mkdir(parents=True)
    f = tmp_path / ".devin" / "credentials.toml"
    f.write_text("x")
    assert default_credentials_path() == f


def test_override_env_wins(monkeypatch, tmp_path):
    f = tmp_path / "mine.txt"
    f.write_text("x")
    monkeypatch.setenv("DEVIN_PROXY_SYSTEM_FILE", str(f))
    assert default_system_file() == f


def test_override_home_dir(tmp_path):
    d = tmp_path / ".devin-proxy"
    d.mkdir(parents=True)
    f = d / "override-compact.txt"
    f.write_text("x")
    assert default_system_file() == f


def test_override_packaged_prompts(tmp_path):
    # the packaged prompts/ dir ships the default override; it's found
    # after the home dir
    import devin_proxy.jailbreak.override as ov
    pkg_prompts = Path(ov.__file__).resolve().parent.parent / "prompts"
    shipped = [pkg_prompts / n for n in ov.NAMES if (pkg_prompts / n).exists()]
    if not shipped:
        pytest.skip("packaged prompts not shipped")
    p = default_system_file()
    assert p == shipped[0]


def test_override_fallback_default(tmp_path, monkeypatch):
    # with no repo prompts/ reachable, falls back to the home-dir path
    import devin_proxy.jailbreak.override as ov
    monkeypatch.setattr(ov, "NAMES", ("nonexistent-file.txt",))
    # also break the repo path
    monkeypatch.setattr(Path, "exists", lambda self: False)
    p = default_system_file()
    assert p == tmp_path / ".devin-proxy" / "nonexistent-file.txt"

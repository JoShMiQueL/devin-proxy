"""Runtime configuration: every knob is an env var or a CLI flag."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_cred() -> Path:
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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEVIN_PROXY_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8390
    backend: str = "https://server.codeium.com"
    credentials: Path = _default_cred()

    # fingerprint the backend expects; keep in step with `devin version`
    client_version: str = "3000.11.234"
    client_channel: str = "chisel"

    # refusal-guard tunables
    guard_chars: int = 700
    max_retries: int = 2
    retry_temps: str = "0.85,1.0"
    connect_retries: int = 3

    # tool-declaration ladder: full | compact | none
    tool_desc: str = "compact"
    native_tools: bool = True

    # reasoning replay caps (0 = unlimited)
    reason_turns: int = 0
    reason_chars: int = 0

    img_max_bytes: int = 12 * 1024 * 1024
    keep_client_system: bool = False

    # model allowlist: only the free SWE-2 lanes
    allowed_models: tuple[str, ...] = (
        "swe-2-medium",
        "swe-2-high",
        "swe-2-max",
    )
    default_model: str = "swe-2-high"
    client_model_id: str = "swe-2"
    client_model_name: str = "SWE-2"

    # system override file (hot-reloaded)
    system_file: Path | None = None

    dump_dir: Path | None = None  # set to enable request dumps


def load_settings(**overrides) -> Settings:
    env = {k: v for k, v in os.environ.items() if k.startswith("DEVIN_PROXY_")}
    allowed = env.get("DEVIN_PROXY_ALLOWED_MODELS")
    if allowed:
        overrides.setdefault(
            "allowed_models",
            tuple(x.strip() for x in allowed.split(",") if x.strip()))
    return Settings(**overrides)

"""Model catalog + the client-facing model-id resolution.

Only the three free SWE-2 lanes are exposed upstream; the catalog still
parses the full GetCliModelConfigs dump so we can advertize context sizes and
validate that a requested uid is real.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from ..transport.proto import Message, fields

#: wire uid -> (effort tier, paid?). We only ever route to the free ones.
SWE2_TIERS = ("swe-2-medium", "swe-2-high", "swe-2-max")


def metadata(api_key: str, jwt: str = "", version: str = "",
             channel: str = "chisel") -> bytes:
    from ..transport.devincli import FALLBACK_VERSION
    version = version or FALLBACK_VERSION
    m = Message()
    m.str_(1, "devin-cli").str_(7, version).str_(28, channel)
    m.str_(12, channel).str_(2, version)
    m.str_(3, api_key).str_(4, "en").str_(5, "windows")
    m.str_(10, str(uuid.uuid4()))
    if jwt:
        m.str_(21, jwt)
    return m.body


@dataclass
class ModelConfig:
    uid: str
    name: str = ""
    context: int = 0
    aliases: list[str] = field(default_factory=list)
    deprecated: bool = False


class ModelCatalog:
    """Parses GetCliModelConfigs into a uid->config map."""

    def __init__(self, raw: bytes):
        self._models: dict[str, ModelConfig] = {}
        for no, wt, v in fields(raw):
            if no != 1 or wt != 2:
                continue
            cfg = self._parse_cfg(v)
            if cfg.uid:
                self._models[cfg.uid] = cfg

    def _parse_cfg(self, b: bytes) -> ModelConfig:
        c = ModelConfig(uid="")
        for no, wt, v in fields(b):
            if no == 1 and wt == 2:
                c.name = v.decode("utf-8", "replace")
            elif no == 18 and wt == 0:
                c.context = v
            elif no == 22 and wt == 2:
                c.uid = v.decode("utf-8", "replace")
            elif no == 23 and wt == 2:
                # inner model block: aliases live at 23.27
                for i_no, i_wt, i_v in fields(v):
                    if i_no == 27 and i_wt == 2:
                        c.aliases.append(i_v.decode("utf-8", "replace"))
            elif no == 24 and wt == 0:
                c.deprecated = bool(v)
        return c

    def __iter__(self):
        return iter(self._models.values())

    def get(self, uid: str) -> ModelConfig | None:
        return self._models.get(uid)


def resolve_model(model: str, effort: str = "",
                  allowed: tuple[str, ...] = SWE2_TIERS,
                  default: str = "swe-2-high") -> str:
    """Map an OpenAI model id + reasoning_effort to a *free* SWE-2 wire uid.

    Anything outside `allowed` falls back to `default`; effort only ever
    chooses among the three SWE-2 lanes.
    """
    m = (model or "").strip().lower()
    e = (effort or "").strip().lower()

    if e in ("max", "xhigh"):
        tier = "swe-2-max"
    elif e in ("medium", "low", "minimal", "none", "off"):
        tier = "swe-2-medium"
    else:
        tier = default

    # an explicit swe-2-<tier> wins over effort
    for cand in SWE2_TIERS:
        if (m == cand or m == cand.replace("swe-2-", "swe2-")) and cand in allowed:
            return cand
    return tier if tier in allowed else default

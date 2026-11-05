"""Model catalog + the client-facing model-id resolution.

The base, Flash, and Lightning SWE-2 lanes are all routable; which ones are
exposed is governed by settings.allowed_models. The catalog still parses the
full GetCliModelConfigs dump so we can advertize context sizes and validate
that a requested uid is real.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from ..transport.proto import Message, fields

#: wire uids for the base SWE-2 lanes
SWE2_TIERS = ("swe-2-medium", "swe-2-high", "swe-2-max")
#: SWE-2 Flash lanes — the fast strawberry-pancake family.
SWE2_FLASH_TIERS = ("swe-2-flash-medium", "swe-2-flash-high", "swe-2-flash-max")

#: every lane we know how to route, in stable order.
# Lightning lanes are intentionally excluded: they bill fast-mode credits.
ALL_TIERS = SWE2_TIERS + SWE2_FLASH_TIERS


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
    credits: float = 0.0           # field 3: relative credit cost per run
    expires_at: int = 0            # field 19.2.1: promo/free window end (epoch)
    promo: str = ""                # field 19.3: promo label e.g. "83% off"
    aliases: list[str] = field(default_factory=list)

    @property
    def expiry_iso(self) -> str:
        import datetime
        return (datetime.datetime.fromtimestamp(
            self.expires_at, datetime.UTC).strftime("%Y-%m-%d")
                if self.expires_at else "")


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
            elif no == 3 and wt == 5:
                import struct
                c.credits = struct.unpack("<f", v)[0]
            elif no == 18 and wt == 0:
                c.context = v
            elif no == 19 and wt == 2:
                # availability/promo block: 19.2.1 = promo end epoch,
                # 19.3 = promo label ("83% off")
                for p_no, p_wt, p_v in fields(v):
                    if p_no == 2 and p_wt == 2:
                        for w_no, w_wt, w_v in fields(p_v):
                            if w_no == 1 and w_wt == 0:
                                c.expires_at = w_v
                    elif p_no == 3 and p_wt == 2:
                        c.promo = p_v.decode("utf-8", "replace")
            elif no == 22 and wt == 2:
                c.uid = v.decode("utf-8", "replace")
            elif no == 23 and wt == 2:
                # inner model block: aliases live at 23.27
                for i_no, i_wt, i_v in fields(v):
                    if i_no == 27 and i_wt == 2:
                        c.aliases.append(i_v.decode("utf-8", "replace"))
        return c

    def __iter__(self):
        return iter(self._models.values())

    def get(self, uid: str) -> ModelConfig | None:
        return self._models.get(uid)


def resolve_model(model: str, effort: str = "",
                  allowed: tuple[str, ...] = ALL_TIERS,
                  default: str = "swe-2-high") -> str:
    """Map an OpenAI model id + reasoning_effort to a wire uid.

    Anything outside `allowed` falls back to `default`. A bare "flash" /
    "swe-2-flash" id lands on the flash-high lane. Effort picks a tier
    inside whatever family the model id selected (default: the base
    family).
    """
    m = (model or "").strip().lower()
    e = (effort or "").strip().lower()

    # explicit lane always wins
    for cand in allowed:
        if m == cand or m == cand.replace("swe-2-", "swe2-"):
            return cand

    tiers = SWE2_FLASH_TIERS if "flash" in m else SWE2_TIERS

    if e in ("max", "xhigh"):
        tier = tiers[2]
    elif e in ("medium", "low", "minimal", "none", "off"):
        tier = tiers[0]
    else:
        tier = (default if default in tiers else tiers[1])

    return tier if tier in allowed else (
        default if default in allowed else allowed[0] if allowed else tier)

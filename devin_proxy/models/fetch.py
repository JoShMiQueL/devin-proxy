"""Fetch the live model catalog from GetCliModelConfigs at startup."""
from __future__ import annotations

import logging

from ..transport.proto import Message
from ..transport.wire import ConnectClient
from .catalog import ModelCatalog, metadata

log = logging.getLogger("devin-proxy")

CFG_PATH = "/exa.api_server_pb.ApiServerService/GetCliModelConfigs"


async def fetch_catalog(base: str, api_key: str, jwt: str,
                        client_version: str, client_channel: str,
                        timeout: float = 30.0) -> ModelCatalog | None:
    """Return a ModelCatalog from the live API, or None on failure."""
    body = Message().msg(1, Message(metadata(
        api_key, jwt, client_version, client_channel))).body
    client = ConnectClient(base, timeout=timeout)
    try:
        raw = await client.unary(CFG_PATH, body)
        cat = ModelCatalog(raw)
        log.info("model catalog: %d configs", len(list(cat)))
        return cat
    except Exception as e:
        log.warning("catalog fetch failed: %s", e)
        return None
    finally:
        await client.aclose()

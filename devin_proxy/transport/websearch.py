"""GetWebSearchResults wrapper: query -> structured results."""
from __future__ import annotations

from ..models.catalog import metadata
from ..transport.proto import Message, fields
from ..transport.wire import ConnectClient

WS_PATH = "/exa.api_server_pb.ApiServerService/GetWebSearchResults"


async def web_search(base: str, api_key: str, jwt: str, query: str,
                     client_version: str = "3000.11.234",
                     client_channel: str = "chisel",
                     timeout: float = 30.0) -> list[dict]:
    """Return [{'id','url','title','content'}] for a search query."""
    body = (Message()
            .msg(1, Message(metadata(api_key, jwt, client_version,
                                     client_channel)))
            .str_(2, query)
            .body)
    client = ConnectClient(base, timeout=timeout)
    try:
        raw = await client.unary(WS_PATH, body)
    finally:
        await client.aclose()
    results = []
    for no, wt, v in fields(raw):
        if no != 1 or wt != 2:
            continue
        item = {}
        for n2, w2, v2 in fields(v):
            if w2 != 2:
                continue
            s = v2.decode("utf-8", "replace")
            if n2 == 1:
                item["id"] = s
            elif n2 == 3:
                item["url"] = s
            elif n2 == 4:
                item["title"] = s
            elif n2 == 7:
                item["content"] = s
        if item:
            results.append(item)
    return results

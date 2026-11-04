"""GetImageCaption wrapper: image -> caption text."""
from __future__ import annotations

from ..models.catalog import metadata
from ..transport.proto import Message, fields
from ..transport.wire import ConnectClient

CAPTION_PATH = "/exa.api_server_pb.ApiServerService/GetImageCaption"


async def image_caption(base: str, api_key: str, jwt: str,
                        image_b64: str, mime: str = "image/png",
                        client_version: str = "",
                        client_channel: str = "chisel",
                        timeout: float = 30.0) -> str:
    """Return the model's caption/description for a base64 image."""
    img = Message().str_(1, image_b64).str_(2, mime)
    body = (Message()
            .msg(1, Message(metadata(api_key, jwt, client_version,
                                     client_channel)))
            .msg(2, img)
            .body)
    client = ConnectClient(base, timeout=timeout)
    try:
        raw = await client.unary(CAPTION_PATH, body)
    finally:
        await client.aclose()
    for no, wt, v in fields(raw):
        if no == 1 and wt == 2:
            return v.decode("utf-8", "replace")
    return ""

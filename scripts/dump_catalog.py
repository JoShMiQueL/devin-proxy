"""Debug helper: dump the raw GetCliModelConfigs proto tree for SWE-2 uids."""
import asyncio
import struct
import sys

from devin_proxy.config import load_settings
from devin_proxy.models.catalog import metadata
from devin_proxy.models.fetch import CFG_PATH
from devin_proxy.transport.auth import Auth
from devin_proxy.transport.proto import Message, fields
from devin_proxy.transport.wire import ConnectClient

only = sys.argv[1] if len(sys.argv) > 1 else "swe-2"


def dump(b, depth=0, max_depth=6):
    if depth > max_depth:
        return
    for no, wt, v in fields(b):
        pad = "  " * depth
        if wt == 0:
            print(f"{pad}{no}:varint {v}")
        elif wt == 1:
            print(f"{pad}{no}:f64 {struct.unpack('<d', v)[0]}")
        elif wt == 5:
            print(f"{pad}{no}:f32 {struct.unpack('<f', v)[0]}")
        elif wt == 2:
            try:
                t = v.decode("utf-8")
                if t and all(32 <= ord(c) < 127 for c in t):
                    print(f"{pad}{no}:str {t!r}")
                    continue
            except Exception:
                pass
            print(f"{pad}{no}:msg len={len(v)}")
            try:
                dump(v, depth + 1)
            except Exception:
                print(f"{pad}  <bytes {v[:48].hex()}>")


async def main():
    s = load_settings()
    auth = Auth(s.backend, s.credentials, s.client_version, s.client_channel)
    body = Message().msg(1, Message(metadata(
        auth.api_key(), "", s.client_version, s.client_channel))).body
    c = ConnectClient(s.backend, timeout=30)
    raw = await c.unary(CFG_PATH, body)
    await c.aclose()
    for no, wt, v in fields(raw):
        if no != 1 or wt != 2:
            continue
        uid = ""
        for n2, w2, v2 in fields(v):
            if n2 == 22 and w2 == 2:
                uid = v2.decode("utf-8", "replace")
        if only in uid:
            print("=" * 64)
            print("UID:", uid)
            dump(v)


asyncio.new_event_loop().run_until_complete(main())

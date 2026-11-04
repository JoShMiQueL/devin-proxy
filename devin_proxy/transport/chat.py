"""GetChatMessage request builder + streaming delta decoder."""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from .proto import Message, fields
from .wire import ConnectClient

CHAT_PATH = "/exa.api_server_pb.ApiServerService/GetChatMessage"
PROTOCOL_STOPS = (
    '<|user|>',
    '<|bot|>',
    '<|context_request|>',
    '<|endoftext|>',
    '<|end_of_turn|>',
)


@dataclass
class ToolCallAcc:
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class ChatEvent:
    kind: str
    value: object = None


def image_data(b64: str, mime: str, caption: str = "") -> bytes:
    return Message().str_(1, b64).str_(2, mime).str_(3, caption).body


def tool_call(cid: str, name: str, args_json: str) -> bytes:
    return Message().str_(1, cid).str_(2, name).str_(3, args_json or "{}").body


def prompt_msg(source: int, text: str, msg_id: str | None = None,
               thinking: str = "", signature: str = "",
               signature_type: str = "",
               images: list[tuple[str, str, str]] | None = None,
               tool_calls: list[tuple[str, str, str]] | None = None,
               tool_call_id: str = "", is_error: bool = False) -> bytes:
    m = Message()
    m.str_(1, msg_id or str(uuid.uuid4()))
    m.varint_(2, source)          # 1=USER 2=SYSTEM(assistant) 4=TOOL
    m.str_(3, text)
    for b64, mime, caption in images or ():
        m.msg(10, Message(image_data(b64, mime, caption)))
    for cid, cname, cargs in tool_calls or ():
        m.msg(6, Message(tool_call(cid, cname, cargs)))
    if tool_call_id:
        m.str_(7, tool_call_id)
    if is_error:
        m.varint_(9, 1)
    if thinking:
        m.str_(11, thinking)
    if signature:
        m.str_(12, signature)
    if signature_type:
        m.str_(18, signature_type)
    return m.body


def tool_definition(name: str, desc: str, params_json: str,
                    strict: bool = False) -> bytes:
    m = Message().str_(1, name).str_(2, desc).str_(3, params_json)
    if strict:
        m.varint_(12, 1)
    return m.body


def completion_cfg(temperature: float = 0.4, max_tokens: int = 8192,
                   first_temperature: float | None = None,
                   top_p: float | None = None, num_completions: int = 1,
                   stop: list[str] | None = None, seed: int | None = None,
                   service_tier: str | None = None) -> bytes:
    c = Message()
    c.varint_(1, num_completions)
    c.varint_(2, max_tokens)
    c.varint_(3, 200)
    c.double_(5, temperature)
    c.double_(6, temperature if first_temperature is None else first_temperature)
    c.varint_(7, 50)
    c.double_(8, 1.0 if top_p is None else top_p)
    seen: set[str] = set()
    for s in list(stop or []) + list(PROTOCOL_STOPS):
        if s and s not in seen:
            seen.add(s)
            c.str_(9, s)
    if seed is not None:
        c.varint_(10, seed & 0xFFFFFFFFFFFFFFFF)
    c.double_(11, 1.0)
    if service_tier:
        c.str_(17, service_tier)
    return c.body


def chat_request(api_key: str, jwt: str, model_uid: str,
                 prompt_msgs: list[bytes], system_prompt: str,
                 *, client_version: str, client_channel: str,
                 temperature: float = 0.4, max_tokens: int = 8192,
                 first_temperature: float | None = None,
                 tools: list[bytes] | None = None,
                 tool_choice: bytes | None = None,
                 disable_parallel: bool = False,
                 top_p: float | None = None,
                 stop: list[str] | None = None,
                 seed: int | None = None,
                 service_tier: str | None = None,
                 request_id: str | None = None) -> bytes:
    from ..models.catalog import metadata
    r = Message()
    r.msg(1, Message(metadata(api_key, jwt, client_version, client_channel)))
    r.str_(2, system_prompt or "You are a helpful coding assistant.")
    for p in prompt_msgs:
        r.msg(3, Message(p))
    r.varint_(7, 5)
    r.msg(8, Message(completion_cfg(temperature, max_tokens, first_temperature,
                                     top_p=top_p, stop=stop, seed=seed,
                                     service_tier=service_tier)))
    r.msg(13, Message().varint_(1, 1))
    r.varint_(20, 1)
    r.str_(21, model_uid)
    r.str_(16, request_id or str(uuid.uuid4()))
    r.str_(22, str(uuid.uuid4()))
    for t in tools or ():
        r.msg(10, Message(t))
    if disable_parallel:
        r.varint_(11, 1)
    if tool_choice:
        r.msg(12, Message(tool_choice))
    return r.body


def _err_from_trailer(payload: bytes) -> dict | None:
    text = payload.decode("utf-8", "replace").strip()
    if not text.startswith("{"):
        return None
    try:
        obj = json.loads(text)
    except Exception:
        return None
    err = obj.get("error") if isinstance(obj, dict) else None
    return err if isinstance(err, dict) else None


async def chat_stream(client: ConnectClient, api_key: str, jwt: str,
                      model_uid: str, prompt_msgs: list[bytes],
                      system_prompt: str, **kw) -> AsyncIterator[ChatEvent]:
    """Yield ChatEvents as the upstream stream decodes."""
    body = chat_request(api_key, jwt, model_uid, prompt_msgs, system_prompt, **kw)
    tool_acc: list[ToolCallAcc] = []
    sig_parts: list[str] = []
    sig_type_parts: list[str] = []

    async for flag, payload in client.call(CHAT_PATH, body):
        if flag & 2:
            err = _err_from_trailer(payload)
            if err:
                code = str(err.get("code") or "")
                yield ChatEvent("error", {"code": code,
                                         "message": str(err.get("message") or "")[:400],
                                         "blocked": code == "permission_denied"})
            continue
        for no, _wt, v in fields(payload):
            if no == 3:
                yield ChatEvent("text", v.decode("utf-8", "replace"))
            elif no == 9:
                yield ChatEvent("thinking", v.decode("utf-8", "replace"))
            elif no == 10:
                sig_parts.append(v.decode("utf-8", "replace"))
            elif no == 21:
                sig_type_parts.append(v.decode("utf-8", "replace"))
            elif no == 5:
                yield ChatEvent("stop", v)
            elif no == 6:
                tc = {n: x for n, w, x in fields(v)}
                def _s(x):
                    return x.decode("utf-8", "replace") if isinstance(x, (bytes, bytearray)) else (x if isinstance(x, str) else "")
                cid, cname, cargs = _s(tc.get(1)), _s(tc.get(2)), _s(tc.get(3))
                if cid or cname:
                    tool_acc.append(ToolCallAcc(cid, cname, cargs))
                elif tool_acc:
                    tool_acc[-1].arguments += cargs
                else:
                    tool_acc.append(ToolCallAcc("", "", cargs))
            elif no == 7:
                usage = {n: x for n, w, x in fields(v) if w == 0}
                yield ChatEvent("usage", usage)
    if tool_acc:
        yield ChatEvent("toolcalls", tool_acc)
    yield ChatEvent("reasoning_meta", {"signature": "".join(sig_parts),
                                      "signature_type": "".join(sig_type_parts)})


def usage_to_openai(wire: dict | None) -> dict:
    """Devin ModelUsageStats -> OpenAI usage block."""
    def num(f):
        try:
            return int((wire or {}).get(f) or 0)
        except (TypeError, ValueError):
            return 0
    if not wire:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    pin, pout, cwrite, cread = num(2), num(3), num(4), num(5)
    prompt = pin + cread + cwrite
    usage = {"prompt_tokens": prompt, "completion_tokens": pout,
             "total_tokens": prompt + pout}
    if cread:
        usage["prompt_tokens_details"] = {"cached_tokens": cread}
    return usage

"""OpenAI <-> Devin message translation."""
from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request

from .transport.chat import prompt_msg


def _b64_from_url(url: str, max_bytes: int):
    if not isinstance(url, str) or not url:
        return None
    if url.startswith("data:"):
        head, _, payload = url.partition(",")
        meta = head[5:]
        is_b64 = meta.endswith(";base64") or ";base64;" in meta
        mime = meta.split(";")[0] or "image/png"
        if is_b64:
            if len(payload.strip()) * 3 // 4 > max_bytes:
                return None
            return payload.strip(), mime
        raw = urllib.parse.unquote_to_bytes(payload)
        if len(raw) > max_bytes:
            return None
        return base64.b64encode(raw).decode("ascii"), mime
    if url.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                raw = r.read(max_bytes + 1)
                ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip()
        except Exception:
            return None
        if not raw or len(raw) > max_bytes:
            return None
        return base64.b64encode(raw).decode("ascii"), (ctype or "image/png")
    return None


def extract_images(part: dict, max_bytes: int):
    if not isinstance(part, dict):
        return []
    caption = str(part.get("caption") or "")
    if isinstance(part.get("data"), str) and part.get("mimeType"):
        return [(part["data"], str(part["mimeType"]), caption)]
    src = part.get("source")
    if isinstance(src, dict) and isinstance(src.get("data"), str):
        mime = str(src.get("media_type") or src.get("mime_type") or "image/png")
        return [(src["data"], mime, caption)]
    iu = part.get("image_url")
    url = iu.get("url") if isinstance(iu, dict) else iu
    got = _b64_from_url(url, max_bytes)
    return [(got[0], got[1], caption)] if got else []


def openai_to_wire(messages: list, frame_note: str | None = None,
                   native_tools: bool = False,
                   img_max_bytes: int = 12 * 1024 * 1024):
    """(system_prompt, [prompt_msg bytes]). Assistant -> source 2 (SYSTEM)."""
    system = "You are a helpful coding assistant."
    prompts = []
    last_user_idx = -1
    for i, m in enumerate(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            last_user_idx = i
    inserted = False
    for i, m in enumerate(messages):
        if i == last_user_idx and frame_note and not inserted:
            prompts.append(prompt_msg(2, frame_note))
            inserted = True
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        content_images = []
        if isinstance(content, list):
            texts = []
            for p in content:
                if not isinstance(p, dict):
                    continue
                if p.get("type") in (None, "text", "input_text"):
                    texts.append(p.get("text") or "")
                else:
                    content_images.extend(extract_images(p, img_max_bytes))
            content = " ".join(t for t in texts if t)
        content = content or ""
        if role in ("system", "developer"):
            system = content
        elif role == "user":
            prompts.append(prompt_msg(1, content, images=content_images))
        elif role == "assistant":
            sig = m.get("signature") or ""
            thinking = (m.get("thinking") or m.get("reasoning_content") or "") if sig else ""
            if m.get("tool_calls") and native_tools:
                calls = []
                for c in m["tool_calls"]:
                    fn = (c or {}).get("function") or {}
                    calls.append((str((c or {}).get("id") or ""),
                                  str(fn.get("name") or ""),
                                  fn.get("arguments") if isinstance(fn.get("arguments"), str)
                                  else json.dumps(fn.get("arguments") or {}, ensure_ascii=False)))
                prompts.append(prompt_msg(2, content, thinking=thinking, signature=sig,
                                          signature_type=m.get("signature_type") or "",
                                          tool_calls=calls))
            elif m.get("tool_calls"):
                rendered = []
                for c in m["tool_calls"]:
                    fn = (c or {}).get("function") or {}
                    rendered.append("<<TOOL_CALL>>" + json.dumps(
                        {"name": fn.get("name", ""),
                         "arguments": fn.get("arguments", "")},
                        ensure_ascii=False) + "<<END_TOOL_CALL>>")
                content = (content + "\n" if content.strip() else "") + "\n".join(rendered)
                prompts.append(prompt_msg(2, content, thinking=thinking, signature=sig,
                                          signature_type=m.get("signature_type") or ""))
            else:
                prompts.append(prompt_msg(2, content, thinking=thinking, signature=sig,
                                          signature_type=m.get("signature_type") or ""))
        elif role == "tool":
            if native_tools:
                prompts.append(prompt_msg(4, content,
                                          tool_call_id=m.get("tool_call_id") or "",
                                          is_error=bool(m.get("is_error")),
                                          images=content_images))
                continue
            label = m.get("name") or m.get("tool_call_id") or "tool"
            if m.get("is_error"):
                label += " ERROR"
            prompts.append(prompt_msg(1, f"Tool result ({label}): {content}",
                                      images=content_images))
    return system, prompts

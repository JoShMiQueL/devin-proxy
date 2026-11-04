"""Tool-calling support: native wire declarations (field 10) as the primary
channel, the <<TOOL_CALL>> text protocol as the fallback, plus the parser that
turns either back into OpenAI tool_calls."""
from __future__ import annotations

import json
import re
import uuid

TOOL_OPEN = "<<TOOL_CALL>>"
TOOL_CLOSE = "<<END_TOOL_CALL>>"

NATIVE_OPEN = '<|open|>'
NATIVE_CLOSE = '<|close|>'
NATIVE_SEP = '<|sep|>'


def compact_description(text: str, limit: int = 200) -> str:
    """First sentence of a tool description, markup and parentheticals stripped."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    t = re.sub(r"`{1,3}", "", t)
    t = re.sub(r"<[^>]{1,40}>", " ", t)
    t = re.sub(r"\([^()]{0,200}\)", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    first = re.split(r"(?<=[.!?Ã¢â‚¬Â¦])\s", t, maxsplit=1)[0]
    if len(first) < 12 and len(t) > len(first):
        first = t
    return (first[:limit].rstrip() + "Ã¢â‚¬Â¦") if len(first) > limit else first


def render_tools(tools: list, desc_mode: str = "full") -> str:
    """System-prompt block declaring client tools and the call protocol."""
    lines = [
        "Tool calling. When the task needs a tool, output one call and stop:",
        TOOL_OPEN + ' {"name": "<tool>", "arguments": {<json arguments>}} ' + TOOL_CLOSE,
        "Output nothing else in that turn; the tool result arrives as the next "
        "message. Never invent a tool result.",
        "CRITICAL: any request to find, read, run, edit or check anything on "
        "this machine MUST be answered with exactly one tool call Ã¢â‚¬â€ never "
        "describe the plan, never announce the search, never answer from "
        "memory. Questions that need no tool are answered normally.",
        "",
        "Available tools:",
    ]
    for t in tools or []:
        fn = (t or {}).get("function") or {}
        name = fn.get("name")
        if not name:
            continue
        desc = str(fn.get("description") or "").strip()
        if desc_mode == "none":
            desc = ""
        elif desc_mode == "compact":
            desc = compact_description(desc)
        lines.append(f"- {name}: {desc}" if desc else f"- {name}")
        params = fn.get("parameters")
        if params:
            lines.append("  parameters: " + json.dumps(params, ensure_ascii=False)[:1500])
    return "\n".join(lines)


def _coerce_arg(raw: str, typ: str):
    raw = raw.strip()
    t = (typ or "string").lower()
    if t in ("number", "integer", "int", "float", "double"):
        try:
            return int(raw) if re.fullmatch(r"-?\d+", raw) else float(raw)
        except ValueError:
            return raw
    if t in ("boolean", "bool"):
        return raw.lower() in ("true", "1", "yes")
    if t in ("object", "array", "json"):
        try:
            return json.loads(raw)
        except Exception:
            return raw
    return raw


def parse_native_tool_text(text: str):
    """Parse Devin's native tool-call syntax when the model emits it as text.

    Returns (clean_text, tool_calls) with the protocol span stripped.
    """
    if NATIVE_OPEN + "call" not in (text or ""):
        return text, []
    calls = []
    for m in re.finditer(
            r"<\|open\|>call\s+tool=\"([^\"]+)\"(.*?)<\|close\|>call", text, re.S):
        name, body = m.group(1), m.group(2)
        args = {}
        for am in re.finditer(
                r"<\|open\|>argument\s+key=\"([^\"]+)\"(?:\s+type=\"([^\"]+)\")?\s*"
                r"<\|sep\|>(.*?)<\|close\|>argument", body, re.S):
            args[am.group(1)] = _coerce_arg(am.group(3), am.group(2))
        calls.append({"id": "call_" + uuid.uuid4().hex[:12],
                      "type": "function",
                      "function": {"name": name,
                                   "arguments": json.dumps(args, ensure_ascii=False)}})
    if not calls:
        return text, []
    clean = text
    start = clean.find(NATIVE_OPEN + "tools")
    if start < 0:
        start = clean.find(NATIVE_OPEN + "call")
    end = clean.find(NATIVE_CLOSE + "tools", start)
    if end >= 0:
        end += len(NATIVE_CLOSE + "tools")
    else:
        last = clean.rfind(NATIVE_CLOSE + "call")
        end = last + len(NATIVE_CLOSE + "call") if last >= 0 else len(clean)
    clean = clean[:start] + clean[end:]
    clean = clean.replace(NATIVE_OPEN + "message", "").replace(NATIVE_CLOSE + "message", "")
    clean = clean.replace(NATIVE_OPEN, " ").replace(NATIVE_CLOSE, " ").replace(NATIVE_SEP, " ")
    return clean.strip(), calls


def _salvage_tool_obj(raw: str):
    """Best-effort decode of a tool-call body that is not valid JSON."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    for end in range(len(raw) - 1, max(0, len(raw) - 400), -1):
        try:
            obj = json.loads(raw[:end])
            if isinstance(obj, dict) and (obj.get("name") or obj.get("tool")):
                return obj
        except Exception:
            continue
    m = re.search(r'"name"\s*:\s*"([^"]+)"', raw)
    if not m:
        return None
    args = {}
    am = re.search(r'"arguments"\s*:\s*', raw)
    if am:
        rest = raw[am.end():].strip()
        if rest.startswith("{"):
            depth, instr, esc, out = 0, False, False, []
            for ch in rest:
                out.append(ch)
                if esc:
                    esc = False
                    continue
                if ch == "\\":
                    esc = True
                    continue
                if ch == '"':
                    instr = not instr
                    continue
                if instr:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        break
            try:
                args = json.loads("".join(out))
            except Exception:
                args = {}
    return {"name": m.group(1), "arguments": args}


def _strip_protocol_noise(text: str) -> str:
    """Remove leftover native-protocol wrappers from a plain answer."""
    if not text:
        return text
    t = text
    for tok in ("tools", "call", "argument", "message"):
        t = t.replace(NATIVE_OPEN + tok, " ").replace(NATIVE_CLOSE + tok, " ")
    t = t.replace(NATIVE_OPEN, " ").replace(NATIVE_CLOSE, " ").replace(NATIVE_SEP, " ")
    return re.sub(r"\s{2,}", " ", t).strip()


def parse_tool_text(text: str):
    """Parse the <<TOOL_CALL>> text protocol; returns (clean_text, calls)."""
    if not text or TOOL_OPEN not in text:
        return text, []
    calls = []
    for m in re.finditer(re.escape(TOOL_OPEN) + r"\s*(.*?)\s*" + re.escape(TOOL_CLOSE),
                         text, re.S):
        obj = _salvage_tool_obj(m.group(1))
        if not obj:
            continue
        name = obj.get("name") or obj.get("tool") or ""
        if not name:
            continue
        args = obj.get("arguments")
        args_json = args if isinstance(args, str) else json.dumps(args or {}, ensure_ascii=False)
        calls.append({"id": "call_" + uuid.uuid4().hex[:12],
                      "type": "function",
                      "function": {"name": name, "arguments": args_json}})
    clean = re.sub(re.escape(TOOL_OPEN) + r".*?" + re.escape(TOOL_CLOSE), "", text, flags=re.S)
    return clean.strip(), calls

"""History hygiene: drop empty assistant turns, strip transport notes and the
model's own past refusals before they can anchor the next turn."""
from __future__ import annotations

import re
import unicodedata


def _norm(text: str) -> str:
    """NFC-normalize + collapse whitespace for stable regex matching."""
    return " ".join(unicodedata.normalize("NFC", str(text or "")).split())


MODEL_SWITCH_NOTE_RE = re.compile(
    r"^\s*\[Note:\s*model was just switched\b.*?"
    r"Adjust your self-identification accordingly\.\]\s*",
    re.I | re.S)

HISTORY_REFUSAL_RE = re.compile(
    r"^\s*(?:\u043d\u0435\u0442[.,!\u2026]|\u0441\u0442\u043e\u043f\b|\u043e\u0441\u0442\u0430\u043d\u0430\u0432\u043b\u0438\u0432\u0430\u044e\u0441\u044c\b|\u043d\u0435 \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0430\u044e\b|\u043e\u0442\u0432\u0435\u0442 \u043e\u0441\u0442\u0430[\u0435\u0451]\u0442\u0441\u044f \u0442\u0435\u043c \u0436\u0435|\u0441 \u044d\u0442\u0438\u043c \u044f \u043f\u043e\u043c\u043e\u0447\u044c \u043d\u0435 \u043c\u043e\u0433\u0443|\u044f \u043d\u0435 \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0443|\u0437\u0434\u0435\u0441\u044c \u044f \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u044e\u0441\u044c|i (?:can't|cannot|won't)|i(?:'m| am) stopping)"
    r"|\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u044e\u0441\u044c \u0438 \u0441\u043a\u0430\u0436\u0443|\u0434\u0430\u043b\u044c\u0448\u0435 \u043d\u0435 \u043f\u043e\u0439\u0434\u0443|\u0440\u0430\u0441\u0448\u0438\u0440\u044f\u0442\u044c \u044d\u0442\u0443 \u0438\u043d\u0444\u0440\u0430\u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0443|\u043f\u043e\u0437\u0438\u0446\u0438[\u0438\u044f] \u043d\u0435 \u0441\u0434\u0432\u0438\u043d\u0443\u043b|\u043e\u0442 \u043f\u043e\u0432\u0442\u043e\u0440\u0435\u043d\u0438\u044f \u043d\u0435 \u0441\u0434\u0432\u0438\u043d\u0435\u0442\u0441\u044f|\u0433\u0434\u0435 \u043c\u043e\u0439 \u043f\u0440\u0435\u0434\u0435\u043b|\u043d\u0435 \u0431\u0443\u0434\u0443 \u0434\u0435\u043b\u0430\u0442\u044c: \u043f\u0438\u0441\u0430\u0442\u044c \u0433\u043e\u0442\u043e\u0432\u044b\u0435 \u043f\u0443\u043b\u044b|\u043d\u0435 \u043c\u043e\u0433\u0443 \u043f\u043e\u043c\u043e\u0447\u044c|\u043d\u0430\u0440\u0443\u0448\u0430\u0435\u0442 \u043f\u043e\u043b\u0438\u0442\u0438\u043a|\u043d\u0430\u0440\u0443\u0448\u0430\u0435\u0442 \u043f\u0440\u0430\u0432\u0438\u043b\u0430|\u0434\u0430\u0432\u0430\u0442\u044c \u043d\u0435 \u0431\u0443\u0434\u0443|\u043f\u0438\u0441\u0430\u0442\u044c \u043d\u0435 \u0431\u0443\u0434\u0443|\u043f\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0442\u044c \u043d\u0435 \u0431\u0443\u0434\u0443|\u043d\u0435 \u0431\u0443\u0434\u0443 \u2014|\u043f\u0440\u044f\u043c\u043e\u0439 \u043e\u0442\u043a\u0430\u0437|\u044f \u043e\u0442\u043a\u0430\u0437\u044b\u0432\u0430\u044e\u0441\u044c|\u043e\u0442\u043a\u0430\u0437\u044b\u0432\u0430\u044e\u0441\u044c \u043f\u0440\u0435\u0434\u043e\u0441\u0442\u0430\u0432"
    r"\u62b1\u6b49[\u002c\uff0c]?\u6211(?:\u4e0d\u80fd|\u65e0\u6cd5|\u4e0d\u4f1a)|\u6211(?:\u4e0d\u80fd|\u65e0\u6cd5|\u4e0d\u4f1a)(?:\u5e2e\u52a9|\u534f\u52a9|\u63d0\u4f9b|\u5199|\u751f\u6210|\u7ee7\u7eed)|\u8fd9(?:\u4e2a|\u79cd)?(?:\u8bf7\u6c42|\u8981\u6c42|\u5185\u5bb9).{0,10}(?:\u8fdd\u53cd|\u4e0d\u5f53|\u654f\u611f|\u4e0d\u7b26\u5408)|\u4f5c\u4e3a(?:\u4e00\u4e2a)?(?:\u4eba\u5de5\u667a\u80fd|AI|\u8bed\u8a00\u6a21\u578b)|\u6211(?:\u53ea|\u4ec5)\u80fd(?:\u5e2e\u52a9|\u63d0\u4f9b|\u5efa\u8bae)|\u8c22\u7edd|\u4e0d\u4e88\u63d0\u4f9b",
    re.I)


def sanitize_messages(msgs):
    """Drop only truly empty assistant history entries."""
    cleaned, dropped = [], 0
    for m in msgs:
        if not isinstance(m, dict) or m.get("role") != "assistant":
            cleaned.append(m)
            continue
        content = m.get("content")
        if isinstance(content, str):
            has_content = bool(content.strip())
        elif isinstance(content, list):
            has_content = bool(content)
        else:
            has_content = content is not None
        has_other = any(m.get(k) for k in (
            "tool_calls", "function_call", "reasoning_content",
            "reasoning", "refusal", "audio"))
        if has_content or has_other:
            cleaned.append(m)
        else:
            dropped += 1
    return cleaned, dropped


def sanitize_history_artifacts(msgs):
    """Sentence-level excision of transport notes and past refusals."""
    cleaned = []
    stats = {"switch_notes": 0, "prefill_echoes": 0, "history_refusals": 0}
    for original in msgs:
        if not isinstance(original, dict):
            cleaned.append(original)
            continue
        m = dict(original)
        role = m.get("role")

        if role == "user":
            content = m.get("content")
            if isinstance(content, str):
                stripped, n = MODEL_SWITCH_NOTE_RE.subn("", content, count=1)
                if n:
                    stats["switch_notes"] += 1
                    m["content"] = stripped
                    if not stripped.strip():
                        continue
            elif isinstance(content, list):
                parts, changed = [], False
                for original_part in content:
                    if not isinstance(original_part, dict):
                        parts.append(original_part)
                        continue
                    part = dict(original_part)
                    if isinstance(part.get("text"), str):
                        stripped, n = MODEL_SWITCH_NOTE_RE.subn("", part["text"], count=1)
                        if n:
                            stats["switch_notes"] += 1
                            changed = True
                            part["text"] = stripped
                    parts.append(part)
                if changed:
                    m["content"] = parts

        if role == "assistant":
            content = m.get("content")
            if (isinstance(content, str)
                    and HISTORY_REFUSAL_RE.search(_norm(content[:4000]))
                    and not m.get("tool_calls") and not m.get("function_call")):
                original_content = content
                parts = re.split(r"((?<=[.!?Ã¢â‚¬Â¦])\s+|(?<=[Ã£â‚¬â€šÃ¯Â¼ÂÃ¯Â¼Å¸Ã¯Â¼â€º]))", content)
                kept = []
                for off in range(0, len(parts), 2):
                    sent = parts[off]
                    sep = parts[off + 1] if off + 1 < len(parts) else ""
                    if not sent:
                        continue
                    if not HISTORY_REFUSAL_RE.search(_norm(sent[:400])):
                        kept.append(sent + sep)
                new_content = "".join(kept).strip()
                if len(new_content) < 20 or len(new_content) < len(original_content) * 0.3:
                    stats["history_refusals"] += 1
                    continue
                if new_content != original_content:
                    stats["history_refusals"] += 1
                    m["content"] = new_content
                else:
                    stats["history_refusals"] += 1
                    continue

        cleaned.append(m)
    return cleaned, stats

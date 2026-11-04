"""Signed-reasoning cache: replay verified thinking onto history turns."""
from __future__ import annotations

import collections
import hashlib
import threading

_CACHE = collections.OrderedDict()
_CAP = 256
_LOCK = threading.Lock()


def _key(content: str) -> str:
    norm = " ".join((content or "").split())
    return hashlib.sha256(norm[:700].encode("utf-8", "ignore")).hexdigest()


def remember(content: str, thinking: str, signature: str, signature_type: str) -> bool:
    if not content or not thinking or not signature:
        return False
    k = _key(content)
    with _LOCK:
        _CACHE[k] = (thinking[:65000], signature, signature_type or "")
        _CACHE.move_to_end(k)
        while len(_CACHE) > _CAP:
            _CACHE.popitem(last=False)
    return True


def attach(messages: list, max_turns: int = 0, max_chars: int = 0):
    """Attach previously captured signed reasoning to assistant history turns."""
    if not isinstance(messages, list):
        return 0, 0
    hits = []
    for idx, m in enumerate(messages):
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        if m.get("signature"):
            continue
        content = m.get("content")
        if not isinstance(content, str):
            continue
        with _LOCK:
            hit = _CACHE.get(_key(content))
        if hit:
            hits.append((idx, hit))
    if max_turns > 0:
        hits = hits[-max_turns:]
    n = chars = 0
    for idx, hit in hits:
        if max_chars > 0 and chars + len(hit[0]) > max_chars:
            if chars:
                break
            hit = (hit[0][:max_chars], hit[1], hit[2])
        m = messages[idx]
        m["thinking"], m["signature"], m["signature_type"] = hit
        n += 1
        chars += len(hit[0])
    return n, chars

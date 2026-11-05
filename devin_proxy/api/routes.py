"""FastAPI surface: OpenAI-compatible /v1 endpoints + /health."""
from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from ..config import Settings
from ..jailbreak.override import OverridePrompt
from ..pipeline import Engine, _client_reasoning_off
from ..transport.auth import Auth
from .schemas import ChatRequest

log = logging.getLogger("devin-proxy")


def build_app(settings: Settings, auth: Auth, engine: Engine,
              override: OverridePrompt, catalog=None) -> FastAPI:
    app = FastAPI(title="devin-proxy", version="0.1.0")
    app.state.catalog = catalog

    @app.get("/health")
    async def health():
        cat = getattr(app.state, "catalog", None)
        return {
            "status": "ok",
            "backend": settings.backend,
            "override_file": str(override.path),
            "override_chars": len(override.load()),
            "models": [settings.client_model_id],
            "wire_models": list(settings.allowed_models),
            "catalog_models": len(list(cat)) if cat else 0,
            "free_until": {c.uid: c.expiry_iso for c in cat
                           if c.expires_at} if cat else {},
        }

    @app.get("/v1/models")
    @app.get("/models")
    async def models():
        data = []
        cat = getattr(app.state, "catalog", None)
        if settings.allow_paid and cat:
            # paid opt-in: expose the whole upstream catalog, billed lanes
            # marked so clients can tell them apart from the free tiers
            allowed = set(settings.allowed_models)
            for cfg in sorted(cat, key=lambda c: c.uid):
                data.append({
                    "id": cfg.uid,
                    "object": "model",
                    "created": int(time.time()),
                    "name": cfg.name or cfg.uid,
                    "owned_by": "devin",
                    "context_window": cfg.context or 262144,
                    "max_tokens": 16384,
                    "credits_per_run": cfg.credits or None,
                    "free_tier": cfg.uid in allowed,
                    "free_until": cfg.expiry_iso or None,
                    "aliases": cfg.aliases or None,
                })
            return {"object": "list", "data": data}
        for uid in settings.allowed_models:
            cfg = cat.get(uid) if cat else None
            entry = {
                "id": uid,
                "object": "model",
                "created": int(time.time()),
                "name": (cfg.name if cfg else uid.replace("swe-2-", "SWE-2 ").title()),
                "owned_by": "devin",
                "context_window": (cfg.context if cfg and cfg.context else 262144),
                "max_tokens": 16384,
                "reasoning": {
                    "supported_efforts": ["none", "minimal", "low", "medium",
                                          "high", "xhigh", "max"],
                    "default_effort": "high",
                    "default_enabled": True,
                    "mandatory": False,
                },
                "supported_reasoning_efforts": ["none", "minimal", "low", "medium",
                                                "high", "xhigh", "max"],
            }
            if cfg and cfg.aliases:
                entry["aliases"] = cfg.aliases
            data.append(entry)
        # alias the client-facing id to the default tier
        default_cfg = cat.get(settings.default_model) if cat else None
        data.insert(0, {
            "id": settings.client_model_id,
            "object": "model",
            "created": int(time.time()),
            "name": settings.client_model_name,
            "owned_by": "devin",
            "context_window": (default_cfg.context if default_cfg and default_cfg.context else 262144),
            "max_tokens": 16384,
            "reasoning": {
                "supported_efforts": ["none", "minimal", "low", "medium",
                                      "high", "xhigh", "max"],
                "default_effort": "high",
                "default_enabled": True,
                "mandatory": False,
            },
            "supported_reasoning_efforts": ["none", "minimal", "low", "medium",
                                            "high", "xhigh", "max"],
            "wire_model": settings.default_model,
        })
        # flash alias: point the code-generation agent at the fast family
        # with one stable id
        flash_cfg = cat.get("swe-2-flash-high") if cat else None
        if flash_cfg or "swe-2-flash-high" in settings.allowed_models:
            data.insert(1, {
                "id": "swe-2-flash",
                "object": "model",
                "created": int(time.time()),
                "name": "SWE-2 Flash",
                "owned_by": "devin",
                "context_window": (flash_cfg.context
                                   if flash_cfg and flash_cfg.context
                                   else 262144),
                "max_tokens": 16384,
                "reasoning": {
                    "supported_efforts": ["none", "minimal", "low", "medium",
                                          "high", "xhigh", "max"],
                    "default_effort": "high",
                    "default_enabled": True,
                    "mandatory": False,
                },
                "supported_reasoning_efforts": ["none", "minimal", "low",
                                                "medium", "high", "xhigh",
                                                "max"],
                "wire_model": "swe-2-flash-high",
            })
        return {"object": "list", "data": data}

    @app.post("/v1/image_caption")
    async def image_caption_endpoint(req: dict):
        b64 = req.get("image") or req.get("data") or ""
        mime = req.get("mime") or "image/png"
        if not b64:
            return JSONResponse(status_code=400, content={
                "error": {"message": "missing image", "type": "invalid_request"}})
        try:
            from ..transport.caption import image_caption
            cap = await image_caption(
                settings.backend, auth.api_key(), await auth.jwt(),
                b64, mime, settings.client_version, settings.client_channel)
            return {"caption": cap}
        except Exception as e:
            log.exception("image caption failed")
            return JSONResponse(status_code=502, content={
                "error": {"message": str(e), "type": "server_error"}})

    @app.post("/v1/web_search")
    async def web_search_endpoint(req: dict):
        query = str(req.get("query") or req.get("q") or "").strip()
        if not query:
            return JSONResponse(status_code=400, content={
                "error": {"message": "missing query", "type": "invalid_request"}})
        try:
            from ..transport.websearch import web_search
            results = await web_search(
                settings.backend, auth.api_key(), await auth.jwt(), query,
                settings.client_version, settings.client_channel)
            return {"object": "list", "data": results}
        except Exception as e:
            log.exception("web search failed")
            return JSONResponse(status_code=502, content={
                "error": {"message": str(e), "type": "server_error"}})

    @app.post("/v1/chat/completions")
    async def chat_completions(req: ChatRequest, request: Request):
        resp_id = "chatcmpl-" + uuid.uuid4().hex[:24]
        created = int(time.time())
        fingerprint = "fp_devin"
        client_off = _client_reasoning_off(req)
        is_stream = bool(req.stream)

        if is_stream:
            queue: list[dict] = []

            def emit(delta: dict):
                if client_off and "reasoning_content" in delta:
                    delta = {k: v for k, v in delta.items()
                             if k != "reasoning_content"}
                    if not delta:
                        return
                queue.append({
                    "id": resp_id, "object": "chat.completion.chunk",
                    "created": created, "model": settings.client_model_id,
                    "system_fingerprint": fingerprint,
                    "choices": [{"index": 0, "delta": delta,
                                  "finish_reason": None}]})

            done_sent = {"v": False}

            def finish(final: dict | None):
                queue.append({
                    "id": resp_id, "object": "chat.completion.chunk",
                    "created": created, "model": settings.client_model_id,
                    "system_fingerprint": fingerprint,
                    "choices": [{"index": 0, "delta": {},
                                  "finish_reason": (final or {}).get(
                                      "finish_reason", "stop")}]})
                if not done_sent["v"]:
                    done_sent["v"] = True
                    queue.append({"data": "[DONE]"})

            def usage_emit(usage: dict):
                if not (req.stream_options and req.stream_options.include_usage):
                    return
                queue.append({
                    "id": resp_id, "object": "chat.completion.chunk",
                    "created": created, "model": settings.client_model_id,
                    "system_fingerprint": fingerprint, "choices": [],
                    "usage": usage})

            async def gen():
                import asyncio
                done = False

                async def produce():
                    nonlocal done
                    emit({"role": "assistant"})
                    try:
                        await engine.run(req, emit, finish, usage_emit)
                    except Exception as e:
                        log.exception("engine error")
                        queue.append({
                            "id": resp_id, "object": "chat.completion.chunk",
                            "created": created, "model": settings.client_model_id,
                            "system_fingerprint": fingerprint,
                            "choices": [{"index": 0,
                                          "delta": {"content": f"[devin-proxy] error: {e}"},
                                          "finish_reason": "stop"}]})
                    queue.append({"data": "[DONE]"})
                    done = True

                task = asyncio.create_task(produce())
                sent = 0
                try:
                    while not done or sent < len(queue):
                        while sent < len(queue):
                            item = queue[sent]
                            sent += 1
                            if item.get("data") == "[DONE]":
                                yield {"data": "[DONE]"}
                            else:
                                yield {"data": json.dumps(item, ensure_ascii=False)}
                        if not done:
                            await asyncio.sleep(0.01)
                    await task
                except asyncio.CancelledError:
                    task.cancel()
                    raise

            return EventSourceResponse(gen(), media_type="text/event-stream")

        # non-stream
        chunks: list[dict] = []
        finish_meta: dict = {}
        usage: dict = {}

        def emit(delta: dict):
            if client_off and "reasoning_content" in delta:
                return
            chunks.append(delta)

        def finish(final: dict | None):
            finish_meta.update(final or {})

        def usage_emit(u: dict):
            usage.update(u)

        try:
            await engine.run(req, emit, finish, usage_emit)
        except Exception as e:
            log.exception("engine error")
            return JSONResponse(status_code=502, content={
                "error": {"message": str(e), "type": "server_error"}})

        text = "".join(c.get("content", "") or "" for c in chunks)
        think = "".join(c.get("reasoning_content", "") or "" for c in chunks)
        calls = []
        for c in chunks:
            if c.get("tool_calls"):
                calls = c["tool_calls"]
        msg = {"role": "assistant", "content": text or None}
        if calls:
            msg["tool_calls"] = calls
        if think and not client_off:
            msg["reasoning_content"] = think
        fr = finish_meta.get("finish_reason") or ("tool_calls" if calls else "stop")
        return {"id": resp_id, "object": "chat.completion", "created": created,
                "model": settings.client_model_id,
                "system_fingerprint": fingerprint,
                "choices": [{"index": 0, "message": msg, "finish_reason": fr}],
                "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0,
                                   "total_tokens": 0}}

    return app

/**
 * The OpenAI-compatible HTTP surface: /v1/chat/completions (SSE + unary),
 * /v1/models, /health, /v1/image_caption, /v1/web_search.
 *
 * node:http server — no framework. The Engine drives the upstream; this
 * layer only frames deltas as chat.completion.chunk SSE events.
 *
 * Ported from devin_proxy/api/routes.py + server.py.
 */
import { createServer } from "node:http";
import { randomUUID } from "node:crypto";
import { Engine, OverridePrompt } from "devin-engine";
const log = (...args) => console.log(`[devin-proxy]`, ...args);
const logWarn = (...args) => console.warn(`[devin-proxy]`, ...args);
const REASONING_OFF = new Set(["none", "off", "disabled", "false", "no", "0"]);
function clientReasoningOff(data) {
    if (REASONING_OFF.has(String(data.reasoning_effort ?? "").trim().toLowerCase()))
        return true;
    const r = data.reasoning;
    if (r && (r.enabled === false || REASONING_OFF.has(String(r.effort ?? "").trim().toLowerCase())))
        return true;
    const t = data.thinking;
    if (t && (t.enabled === false || t.thinking === false || REASONING_OFF.has(String(t.type ?? "").trim().toLowerCase())))
        return true;
    return data.enable_thinking === false;
}
const REASONING_BLOCK = {
    supported_efforts: ["none", "minimal", "low", "medium", "high", "xhigh", "max"],
    default_effort: "high",
    default_enabled: true,
    mandatory: false,
};
const REASONING_EFFORTS = REASONING_BLOCK.supported_efforts;
function json(res, status, body) {
    const payload = JSON.stringify(body);
    res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) });
    res.end(payload);
}
function sseHeaders(res) {
    res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
    });
}
function sse(res, data) {
    res.write(`data: ${data}\n\n`);
}
async function readBody(req) {
    const chunks = [];
    for await (const c of req)
        chunks.push(c);
    return Buffer.concat(chunks).toString("utf8");
}
export function buildApp(settings, auth, engine, override) {
    let catalog = null;
    const modelEntry = (uid, cfg) => ({
        id: uid,
        object: "model",
        created: Math.floor(Date.now() / 1000),
        name: cfg?.name ?? uid.replace("swe-2-1-", "SWE-2.1 ").replace("swe-2-", "SWE-2 ").replace(/\b\w/g, (c) => c.toUpperCase()),
        owned_by: "devin",
        context_window: cfg?.context ?? 262144,
        max_tokens: 16384,
        reasoning: REASONING_BLOCK,
        supported_reasoning_efforts: REASONING_EFFORTS,
        ...(cfg?.aliases?.length ? { aliases: cfg.aliases } : {}),
    });
    const modelsHandler = () => {
        const data = [];
        if (settings.allowPaid && catalog) {
            const allowed = new Set(settings.allowedModels);
            for (const cfg of [...catalog.values()].sort((a, b) => a.uid.localeCompare(b.uid))) {
                data.push({
                    id: cfg.uid, object: "model", created: Math.floor(Date.now() / 1000),
                    name: cfg.name || cfg.uid, owned_by: "devin",
                    context_window: cfg.context || 262144, max_tokens: 16384,
                    credits_per_run: cfg.credits || undefined,
                    free_tier: allowed.has(cfg.uid),
                    free_until: cfg.expiryIso() || undefined,
                    aliases: cfg.aliases.length ? cfg.aliases : undefined,
                });
            }
            return { object: "list", data };
        }
        for (const uid of settings.allowedModels)
            data.push(modelEntry(uid, catalog?.get(uid)));
        data.unshift({
            ...modelEntry(settings.clientModelId, catalog?.get(settings.defaultModel)),
            wire_model: settings.defaultModel,
        });
        const flash = catalog?.get("swe-2-flash-high");
        if (flash || settings.allowedModels.includes("swe-2-flash-high")) {
            data.splice(1, 0, { ...modelEntry("swe-2-flash", flash), wire_model: "swe-2-flash-high" });
        }
        const s21 = catalog?.get("swe-2-1-high");
        if (s21 || settings.allowedModels.includes("swe-2-1-high")) {
            data.splice(2, 0, { ...modelEntry("swe-2.1", s21), wire_model: "swe-2-1-high" });
        }
        return { object: "list", data };
    };
    const healthHandler = () => ({
        status: "ok",
        backend: settings.backend,
        override_file: override.path,
        override_chars: override.load().length,
        models: [settings.clientModelId],
        wire_models: settings.allowedModels,
        catalog_models: catalog?.size ?? 0,
        free_until: catalog
            ? Object.fromEntries([...catalog.values()].filter((c) => c.expiresAt).map((c) => [c.uid, c.expiryIso()]))
            : {},
    });
    const chatHandler = async (req, res) => {
        let data;
        try {
            data = JSON.parse(await readBody(req));
        }
        catch {
            return json(res, 400, { error: { message: "invalid JSON body", type: "invalid_request" } });
        }
        const respId = "chatcmpl-" + randomUUID().replace(/-/g, "").slice(0, 24);
        const created = Math.floor(Date.now() / 1000);
        const fingerprint = "fp_devin";
        const clientOff = clientReasoningOff(data);
        const isStream = data.stream === true;
        const dropReasoning = (delta) => (clientOff || !settings.emitReasoning) && "reasoning_content" in delta;
        if (isStream) {
            sseHeaders(res);
            const send = (payload) => {
                if ("data" in payload && payload.data === "[DONE]")
                    sse(res, "[DONE]");
                else
                    sse(res, JSON.stringify(payload));
            };
            const chunk = (delta, finishReason = null) => ({
                id: respId, object: "chat.completion.chunk", created,
                model: settings.clientModelId, system_fingerprint: fingerprint,
                choices: [{ index: 0, delta, finish_reason: finishReason }],
            });
            const emit = (delta) => {
                if (dropReasoning(delta)) {
                    const { reasoning_content: _r, ...rest } = delta;
                    if (!Object.keys(rest).length)
                        return;
                    delta = rest;
                }
                send(chunk(delta));
            };
            const finish = (final) => {
                send(chunk({}, String(final?.finish_reason ?? "stop")));
                send({ data: "[DONE]" });
            };
            const includeUsage = data.stream_options?.include_usage === true;
            const usageEmit = (usage) => {
                if (!includeUsage)
                    return;
                send({ ...chunk({}), choices: [], usage });
            };
            send(chunk({ role: "assistant" }));
            try {
                await engine.run(data, emit, finish, usageEmit);
            }
            catch (e) {
                logWarn("engine error:", e);
                send({
                    id: respId, object: "chat.completion.chunk", created,
                    model: settings.clientModelId, system_fingerprint: fingerprint,
                    choices: [{ index: 0, delta: { content: `[devin-proxy] error: ${e.message}` }, finish_reason: "stop" }],
                });
                send({ data: "[DONE]" });
            }
            res.end();
            return;
        }
        // non-stream
        const chunks = [];
        const finishMeta = {};
        const usage = {};
        const emit = (delta) => {
            if (dropReasoning(delta))
                return;
            chunks.push(delta);
        };
        try {
            await engine.run(data, emit, (f) => Object.assign(finishMeta, f ?? {}), (u) => Object.assign(usage, u));
        }
        catch (e) {
            logWarn("engine error:", e);
            return json(res, 502, { error: { message: e.message, type: "server_error" } });
        }
        const text = chunks.map((c) => String(c.content ?? "")).join("");
        const think = chunks.map((c) => String(c.reasoning_content ?? "")).join("");
        const calls = chunks.find((c) => c.tool_calls)?.tool_calls;
        const msg = { role: "assistant", content: text || null };
        if (calls?.length)
            msg.tool_calls = calls;
        if (think && !clientOff) {
            msg.reasoning_content = think;
            msg.reasoning = think;
        }
        json(res, 200, {
            id: respId, object: "chat.completion", created,
            model: settings.clientModelId, system_fingerprint: fingerprint,
            choices: [{ index: 0, message: msg, finish_reason: finishMeta.finish_reason ?? (calls?.length ? "tool_calls" : "stop") }],
            usage: Object.keys(usage).length ? usage : { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
        });
    };
    const server = createServer(async (req, res) => {
        const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
        const path = url.pathname;
        try {
            if (req.method === "GET" && path === "/health")
                return json(res, 200, healthHandler());
            if (req.method === "GET" && (path === "/v1/models" || path === "/models"))
                return json(res, 200, modelsHandler());
            if (req.method === "POST" && path === "/v1/chat/completions")
                return await chatHandler(req, res);
            if (req.method === "POST" && path === "/v1/image_caption") {
                // upstream caption RPC — not in core yet; stub 501 until ported
                return json(res, 501, { error: { message: "image_caption not yet ported", type: "not_implemented" } });
            }
            if (req.method === "POST" && path === "/v1/web_search") {
                return json(res, 501, { error: { message: "web_search not yet ported", type: "not_implemented" } });
            }
            return json(res, 404, { error: { message: "not found", type: "invalid_request" } });
        }
        catch (e) {
            logWarn("unhandled:", e);
            return json(res, 500, { error: { message: e.message, type: "server_error" } });
        }
    });
    return {
        server,
        setCatalog(cat) {
            catalog = cat;
        },
    };
}
/** settings -> auth -> engine -> http server. Ported from server.py::serve. */
export async function serve(settings) {
    const { fetchCliCatalog } = await import("./catalog");
    const { Auth } = await import("./auth");
    const { resolveSystemFile } = await import("devin-engine");
    const auth = new Auth(settings.backend);
    const override = new OverridePrompt(resolveSystemFile(settings.systemFile));
    const engineSettings = {
        backend: settings.backend,
        guardChars: settings.guardChars,
        guardFull: settings.guardFull,
        maxRetries: settings.maxRetries,
        retryTemps: settings.retryTemps,
        toolDesc: settings.toolDesc,
        nativeTools: settings.nativeTools,
        imgMaxBytes: settings.imgMaxBytes,
        keepClientSystem: settings.keepClientSystem,
        maxInputTokens: settings.maxInputTokens,
        pruneKeepTurns: settings.pruneKeepTurns,
        allowedModels: settings.allowedModels,
        allowPaid: settings.allowPaid,
        defaultModel: settings.defaultModel,
        emitReasoning: settings.emitReasoning,
        stripIncomingReasoning: settings.stripIncomingReasoning,
        planPreamble: settings.planPreamble,
    };
    const engine = new Engine(engineSettings, auth.apiKey(), override, undefined);
    const app = buildApp(settings, auth, engine, override);
    // Prefetch the CLI catalog in the background — /v1/models and allowPaid
    // routing degrade gracefully until it lands. The engine's catalog list is
    // refreshed in place so allowPaid starts routing once it lands.
    void fetchCliCatalog(settings.backend, auth.apiKey(), await auth.jwt().catch(() => ""), settings.clientVersion)
        .then((cat) => {
        if (cat?.size) {
            app.setCatalog(cat);
            engine.catalog = [...cat.values()].map((c) => ({ uid: c.uid }));
            log(`model catalog: ${cat.size} configs`);
        }
    })
        .catch((e) => logWarn("catalog prefetch skipped:", e));
    await new Promise((resolve) => {
        app.server.listen(settings.port, settings.host, resolve);
    });
    log(`listening on ${settings.host}:${settings.port} -> ${settings.backend} ` +
        `(allowed=${settings.allowedModels.join(",")}${settings.allowPaid ? "+paid" : ""}) override=${override.load().length}c`);
    try {
        auth.apiKey();
        log(`devin credentials ok (${auth.credentials})`);
    }
    catch (e) {
        logWarn("credentials unavailable:", e.message);
    }
    return {
        server: app.server,
        engine,
        close: () => app.server.close(),
    };
}

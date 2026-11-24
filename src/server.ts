/**
 * The OpenAI-compatible HTTP surface: /v1/chat/completions (SSE + unary),
 * /v1/models, /health, /v1/image_caption, /v1/web_search.
 *
 * node:http server — no framework. The Engine drives the upstream; this
 * layer only frames deltas as chat.completion.chunk SSE events.
 *
 * Ported from devin_proxy/api/routes.py + server.py.
 */

import { createServer, type Server, type IncomingMessage, type ServerResponse } from "node:http"
import { randomUUID } from "node:crypto"
import { Engine, OverridePrompt, type EngineSettings } from "devin-engine"
import type { Auth } from "./auth.js"
import type { CliModelConfig } from "./catalog.js"
import type { Settings } from "./config.js"

const log = (...args: unknown[]) => console.log(`[devin-proxy]`, ...args)
const logWarn = (...args: unknown[]) => console.warn(`[devin-proxy]`, ...args)

const REASONING_OFF = new Set(["none", "off", "disabled", "false", "no", "0"])
function clientReasoningOff(data: Record<string, unknown>): boolean {
  if (REASONING_OFF.has(String(data.reasoning_effort ?? "").trim().toLowerCase())) return true
  const r = data.reasoning as Record<string, unknown> | undefined
  if (r && (r.enabled === false || REASONING_OFF.has(String(r.effort ?? "").trim().toLowerCase()))) return true
  const t = data.thinking as Record<string, unknown> | undefined
  if (t && (t.enabled === false || t.thinking === false || REASONING_OFF.has(String(t.type ?? "").trim().toLowerCase()))) return true
  return data.enable_thinking === false
}

const REASONING_BLOCK = {
  supported_efforts: ["none", "minimal", "low", "medium", "high", "xhigh", "max"],
  default_effort: "high",
  default_enabled: true,
  mandatory: false,
}
const REASONING_EFFORTS = REASONING_BLOCK.supported_efforts

function json(res: ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body)
  res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) })
  res.end(payload)
}

function sseHeaders(res: ServerResponse): void {
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  })
}

function sse(res: ServerResponse, data: string): void {
  res.write(`data: ${data}\n\n`)
}

async function readBody(req: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = []
  for await (const c of req) chunks.push(c as Buffer)
  return Buffer.concat(chunks).toString("utf8")
}

export interface App {
  server: Server
  /** Catalog lands after boot — routes degrade until it does. */
  setCatalog(cat: Map<string, CliModelConfig>): void
}

export function buildApp(settings: Settings, auth: Auth, engine: Engine, override: OverridePrompt): App {
  let catalog: Map<string, CliModelConfig> | null = null

  const modelEntry = (uid: string, cfg?: CliModelConfig) => ({
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
  })

  const modelsHandler = () => {
    const data: Array<Record<string, unknown>> = []
    if (settings.allowPaid && catalog) {
      const allowed = new Set(settings.allowedModels)
      for (const cfg of [...catalog.values()].sort((a, b) => a.uid.localeCompare(b.uid))) {
        data.push({
          id: cfg.uid, object: "model", created: Math.floor(Date.now() / 1000),
          name: cfg.name || cfg.uid, owned_by: "devin",
          context_window: cfg.context || 262144, max_tokens: 16384,
          credits_per_run: cfg.credits || undefined,
          free_tier: allowed.has(cfg.uid),
          free_until: cfg.expiryIso() || undefined,
          aliases: cfg.aliases.length ? cfg.aliases : undefined,
        })
      }
      return { object: "list", data }
    }
    for (const uid of settings.allowedModels) data.push(modelEntry(uid, catalog?.get(uid)))
    data.unshift({
      ...modelEntry(settings.clientModelId, catalog?.get(settings.defaultModel)),
      wire_model: settings.defaultModel,
    })
    const flash = catalog?.get("swe-2-flash-high")
    if (flash || settings.allowedModels.includes("swe-2-flash-high")) {
      data.splice(1, 0, { ...modelEntry("swe-2-flash", flash), wire_model: "swe-2-flash-high" })
    }
    const s21 = catalog?.get("swe-2-1-high")
    if (s21 || settings.allowedModels.includes("swe-2-1-high")) {
      data.splice(2, 0, { ...modelEntry("swe-2.1", s21), wire_model: "swe-2-1-high" })
    }
    return { object: "list", data }
  }

  const healthHandler = () => ({
    status: "ok",
    mode: settings.mode,
    backend: settings.backend,
    override_file: override.path,
    override_chars: override.load().length,
    models: [settings.clientModelId],
    wire_models: settings.allowedModels,
    catalog_models: catalog?.size ?? 0,
    free_until: catalog
      ? Object.fromEntries([...catalog.values()].filter((c) => c.expiresAt).map((c) => [c.uid, c.expiryIso()]))
      : {},
  })

  const chatHandler = async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
    let data: Record<string, unknown>
    try {
      data = JSON.parse(await readBody(req)) as Record<string, unknown>
    } catch {
      return json(res, 400, { error: { message: "invalid JSON body", type: "invalid_request" } })
    }

    const respId = "chatcmpl-" + randomUUID().replace(/-/g, "").slice(0, 24)
    const created = Math.floor(Date.now() / 1000)
    const fingerprint = "fp_devin"
    const clientOff = clientReasoningOff(data)
    const isStream = data.stream === true

    const dropReasoning = (delta: Record<string, unknown>) =>
      (clientOff || !settings.emitReasoning) && "reasoning_content" in delta

    if (isStream) {
      sseHeaders(res)
      const send = (payload: Record<string, unknown> | { data: string }) => {
        if ("data" in payload && payload.data === "[DONE]") sse(res, "[DONE]")
        else sse(res, JSON.stringify(payload))
      }
      const chunk = (delta: Record<string, unknown>, finishReason: string | null = null) => ({
        id: respId, object: "chat.completion.chunk", created,
        model: settings.clientModelId, system_fingerprint: fingerprint,
        choices: [{ index: 0, delta, finish_reason: finishReason }],
      })

      const emit = (delta: Record<string, unknown>) => {
        if (dropReasoning(delta)) {
          const { reasoning_content: _r, ...rest } = delta
          if (!Object.keys(rest).length) return
          delta = rest
        }
        send(chunk(delta))
      }
      const finish = (final: Record<string, unknown> | null) => {
        send(chunk({}, String(final?.finish_reason ?? "stop")))
        send({ data: "[DONE]" })
      }
      const includeUsage = (data.stream_options as Record<string, unknown> | undefined)?.include_usage === true
      const usageEmit = (usage: Record<string, unknown>) => {
        if (!includeUsage) return
        send({ ...chunk({}), choices: [], usage } as never)
      }

      send(chunk({ role: "assistant" }))
      try {
        await engine.run(data, emit, finish, usageEmit)
      } catch (e) {
        logWarn("engine error:", e)
        send({
          id: respId, object: "chat.completion.chunk", created,
          model: settings.clientModelId, system_fingerprint: fingerprint,
          choices: [{ index: 0, delta: { content: `[devin-proxy] error: ${(e as Error).message}` }, finish_reason: "stop" }],
        })
        send({ data: "[DONE]" })
      }
      res.end()
      return
    }

    // non-stream
    const chunks: Array<Record<string, unknown>> = []
    const finishMeta: Record<string, unknown> = {}
    const usage: Record<string, unknown> = {}
    const emit = (delta: Record<string, unknown>) => {
      if (dropReasoning(delta)) return
      chunks.push(delta)
    }
    try {
      await engine.run(data, emit, (f) => Object.assign(finishMeta, f ?? {}), (u) => Object.assign(usage, u))
    } catch (e) {
      logWarn("engine error:", e)
      return json(res, 502, { error: { message: (e as Error).message, type: "server_error" } })
    }

    const text = chunks.map((c) => String(c.content ?? "")).join("")
    const think = chunks.map((c) => String(c.reasoning_content ?? "")).join("")
    const calls = chunks.find((c) => c.tool_calls)?.tool_calls as unknown[] | undefined
    const msg: Record<string, unknown> = { role: "assistant", content: text || null }
    if (calls?.length) msg.tool_calls = calls
    if (think && !clientOff) {
      msg.reasoning_content = think
      msg.reasoning = think
    }
    json(res, 200, {
      id: respId, object: "chat.completion", created,
      model: settings.clientModelId, system_fingerprint: fingerprint,
      choices: [{ index: 0, message: msg, finish_reason: finishMeta.finish_reason ?? (calls?.length ? "tool_calls" : "stop") }],
      usage: Object.keys(usage).length ? usage : { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
    })
  }

  const server = createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`)
    const path = url.pathname
    try {
      if (req.method === "GET" && path === "/health") return json(res, 200, healthHandler())
      if (req.method === "GET" && (path === "/v1/models" || path === "/models")) return json(res, 200, modelsHandler())
      if (req.method === "POST" && path === "/v1/chat/completions") return await chatHandler(req, res)
      if (req.method === "POST" && path === "/v1/image_caption") {
        const body = JSON.parse(await readBody(req)) as Record<string, unknown>
        const b64 = String(body.image ?? body.data ?? "")
        const mime = String(body.mime ?? "image/png")
        if (!b64) return json(res, 400, { error: { message: "missing image", type: "invalid_request" } })
        try {
          const { imageCaption } = await import("./catalog.js")
          const caption = await imageCaption(settings.backend, auth.apiKey(), await auth.jwt(), b64, mime, settings.clientVersion)
          return json(res, 200, { caption })
        } catch (e) {
          logWarn("image caption failed:", e)
          return json(res, 502, { error: { message: (e as Error).message, type: "server_error" } })
        }
      }
      if (req.method === "POST" && path === "/v1/web_search") {
        const body = JSON.parse(await readBody(req)) as Record<string, unknown>
        const query = String(body.query ?? body.q ?? "").trim()
        if (!query) return json(res, 400, { error: { message: "missing query", type: "invalid_request" } })
        try {
          const { webSearch } = await import("./catalog.js")
          const results = await webSearch(settings.backend, auth.apiKey(), await auth.jwt(), query, settings.clientVersion)
          return json(res, 200, { object: "list", data: results })
        } catch (e) {
          logWarn("web search failed:", e)
          return json(res, 502, { error: { message: (e as Error).message, type: "server_error" } })
        }
      }
      return json(res, 404, { error: { message: "not found", type: "invalid_request" } })
    } catch (e) {
      logWarn("unhandled:", e)
      return json(res, 500, { error: { message: (e as Error).message, type: "server_error" } })
    }
  })

  return {
    server,
    setCatalog(cat) {
      catalog = cat
    },
  }
}

export interface ServeHandle {
  server: Server
  engine: Engine
  close(): void
}

/** settings -> auth -> engine -> http server. Ported from server.py::serve. */
export async function serve(settings: Settings): Promise<ServeHandle> {
  const { fetchCliCatalog } = await import("./catalog.js")
  const { Auth } = await import("./auth.js")
  const { resolveSystemFile } = await import("devin-engine")

  const auth = new Auth(settings.backend)
  const override = new OverridePrompt(resolveSystemFile(settings.systemFile))
  const engineSettings: EngineSettings = {
    backend: settings.backend,
    mode: settings.mode,
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
  }
  const engine = new Engine(engineSettings, auth.apiKey(), override, undefined)
  const app = buildApp(settings, auth, engine, override)

  // Prefetch the CLI catalog in the background — /v1/models and allowPaid
  // routing degrade gracefully until it lands. The engine's catalog list is
  // refreshed in place so allowPaid starts routing once it lands.
  void fetchCliCatalog(settings.backend, auth.apiKey(), await auth.jwt().catch(() => ""), settings.clientVersion)
    .then((cat) => {
      if (cat?.size) {
        app.setCatalog(cat)
        ;(engine as unknown as { catalog: Array<{ uid: string }> }).catalog = [...cat.values()].map((c) => ({ uid: c.uid }))
        log(`model catalog: ${cat.size} configs`)
      }
    })
    .catch((e) => logWarn("catalog prefetch skipped:", e))

  await new Promise<void>((resolve) => {
    app.server.listen(settings.port, settings.host, resolve)
  })
  log(
    `listening on ${settings.host}:${settings.port} -> ${settings.backend} ` +
      `mode=${settings.mode} ` +
      `(allowed=${settings.allowedModels.join(",")}${settings.allowPaid ? "+paid" : ""})` +
      (settings.mode === "uncensored" ? ` override=${override.load().length}c` : ""),
  )
  try {
    auth.apiKey()
    log(`devin credentials ok (${auth.credentials})`)
  } catch (e) {
    logWarn("credentials unavailable:", (e as Error).message)
  }

  return {
    server: app.server,
    engine,
    close: () => app.server.close(),
  }
}

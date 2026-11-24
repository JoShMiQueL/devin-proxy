/**
 * Fetch the live model catalog from GetCliModelConfigs.
 *
 * This is the *other* catalog RPC — the one that exposes per-model credit
 * cost, promo/free windows and aliases. devin-core's `getCachedCatalog`
 * reads GetCascadeModelConfigs for enabled/pricing; this reads the CLI
 * surface the Python proxy uses for billing tags.
 *
 * Ported from devin_proxy/models/fetch.py + the ModelCatalog half of
 * devin_proxy/models/catalog.py.
 */

import { encodeMessage, encodeString, iterFields } from "devin-core"
import { randomUUID } from "node:crypto"
import { CHANNEL, FALLBACK_VERSION } from "./config.js"

const CFG_PATH = "/exa.api_server_pb.ApiServerService/GetCliModelConfigs"

export interface CliModelConfig {
  uid: string
  name: string
  context: number
  /** Relative credit cost per run (field 3, float32). 0 = free lane. */
  credits: number
  /** Promo/free window end, epoch seconds (field 19.2.1). */
  expiresAt: number
  /** Promo label, e.g. "83% off" (field 19.3). */
  promo: string
  aliases: string[]
  expiryIso(): string
}

function metadata(apiKey: string, jwt: string, version: string, channel = CHANNEL): Buffer {
  const v = version || FALLBACK_VERSION
  const parts = [
    encodeString(1, "devin-cli"),
    encodeString(7, v),
    encodeString(28, channel),
    encodeString(12, channel),
    encodeString(2, v),
    encodeString(3, apiKey),
    encodeString(4, "en"),
    encodeString(5, "windows"),
    encodeString(10, randomUUID()),
  ]
  if (jwt) parts.push(encodeString(21, jwt))
  return Buffer.concat(parts)
}

function parseCfg(b: Buffer): CliModelConfig | null {
  let name = ""
  let uid = ""
  let context = 0
  let credits = 0
  let expiresAt = 0
  let promo = ""
  const aliases: string[] = []
  for (const f of iterFields(b)) {
    if (f.num === 1 && f.wire === 2 && Buffer.isBuffer(f.value)) name = f.value.toString("utf8")
    else if (f.num === 3 && f.wire === 5 && Buffer.isBuffer(f.value) && f.value.length === 4) {
      credits = f.value.readFloatLE(0)
    } else if (f.num === 18 && f.wire === 0) context = Number(f.value)
    else if (f.num === 19 && f.wire === 2 && Buffer.isBuffer(f.value)) {
      for (const p of iterFields(f.value)) {
        if (p.num === 2 && p.wire === 2 && Buffer.isBuffer(p.value)) {
          for (const w of iterFields(p.value)) {
            if (w.num === 1 && w.wire === 0) expiresAt = Number(w.value)
          }
        } else if (p.num === 3 && p.wire === 2 && Buffer.isBuffer(p.value)) {
          promo = p.value.toString("utf8")
        }
      }
    } else if (f.num === 22 && f.wire === 2 && Buffer.isBuffer(f.value)) {
      uid = f.value.toString("utf8")
    } else if (f.num === 23 && f.wire === 2 && Buffer.isBuffer(f.value)) {
      for (const i of iterFields(f.value)) {
        if (i.num === 27 && i.wire === 2 && Buffer.isBuffer(i.value)) {
          aliases.push(i.value.toString("utf8"))
        }
      }
    }
  }
  if (!uid) return null
  return {
    uid, name, context, credits, expiresAt, promo, aliases,
    expiryIso: () => (expiresAt ? new Date(expiresAt * 1000).toISOString().slice(0, 10) : ""),
  }
}

const CAPTION_PATH = "/exa.api_server_pb.ApiServerService/GetImageCaption"
const WS_PATH = "/exa.api_server_pb.ApiServerService/GetWebSearchResults"

async function unary(base: string, path: string, body: Buffer, timeoutMs: number): Promise<Buffer> {
  const res = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/proto", "Connect-Protocol-Version": "1" },
    body: new Uint8Array(body),
    signal: AbortSignal.timeout(timeoutMs),
  })
  if (!res.ok) throw new Error(`${path} HTTP ${res.status}`)
  return Buffer.from(await res.arrayBuffer())
}

/** GetImageCaption: base64 image -> caption text. Ported from transport/caption.py. */
export async function imageCaption(
  base: string, apiKey: string, jwt: string,
  imageB64: string, mime = "image/png", clientVersion = "", timeoutMs = 30_000,
): Promise<string> {
  const img = Buffer.concat([encodeString(1, imageB64), encodeString(2, mime)])
  const body = Buffer.concat([encodeMessage(1, metadata(apiKey, jwt, clientVersion)), encodeMessage(2, img)])
  const raw = await unary(base, CAPTION_PATH, body, timeoutMs)
  for (const f of iterFields(raw)) {
    if (f.num === 1 && f.wire === 2 && Buffer.isBuffer(f.value)) return f.value.toString("utf8")
  }
  return ""
}

/** GetWebSearchResults: query -> [{id,url,title,content}]. Ported from transport/websearch.py. */
export async function webSearch(
  base: string, apiKey: string, jwt: string, query: string,
  clientVersion = "", timeoutMs = 30_000,
): Promise<Array<Record<string, string>>> {
  const body = Buffer.concat([encodeMessage(1, metadata(apiKey, jwt, clientVersion)), encodeString(2, query)])
  const raw = await unary(base, WS_PATH, body, timeoutMs)
  const results: Array<Record<string, string>> = []
  for (const f of iterFields(raw)) {
    if (f.num !== 1 || f.wire !== 2 || !Buffer.isBuffer(f.value)) continue
    const item: Record<string, string> = {}
    for (const p of iterFields(f.value)) {
      if (p.wire !== 2 || !Buffer.isBuffer(p.value)) continue
      const s = p.value.toString("utf8")
      if (p.num === 1) item.id = s
      else if (p.num === 3) item.url = s
      else if (p.num === 4) item.title = s
      else if (p.num === 7) item.content = s
    }
    if (Object.keys(item).length) results.push(item)
  }
  return results
}

/** GetCliModelConfigs -> Map<uid, config>, or null on failure. */
export async function fetchCliCatalog(
  base: string,
  apiKey: string,
  jwt: string,
  clientVersion: string,
  timeoutMs = 30_000,
): Promise<Map<string, CliModelConfig> | null> {
  const body = encodeMessage(1, metadata(apiKey, jwt, clientVersion))
  try {
    const res = await fetch(`${base}${CFG_PATH}`, {
      method: "POST",
      headers: { "Content-Type": "application/proto", "Connect-Protocol-Version": "1" },
      body: new Uint8Array(body),
      signal: AbortSignal.timeout(timeoutMs),
    })
    if (!res.ok) return null
    const buf = Buffer.from(await res.arrayBuffer())
    const out = new Map<string, CliModelConfig>()
    for (const f of iterFields(buf)) {
      if (f.num !== 1 || f.wire !== 2 || !Buffer.isBuffer(f.value)) continue
      const cfg = parseCfg(f.value)
      if (cfg) out.set(cfg.uid, cfg)
    }
    return out
  } catch {
    return null
  }
}

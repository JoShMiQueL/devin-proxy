/**
 * Runtime configuration: env var > ~/.devin-proxy/settings.toml > default.
 *
 * Ported from devin_proxy/config.py.
 */

import { execFileSync } from "node:child_process"
import { existsSync, readFileSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"

export const SETTINGS_TOML = join(homedir(), ".devin-proxy", "settings.toml")

/** Minimal TOML reader: only [devin_proxy] KEY = VALUE scalars/arrays matter. */
function fileOverrides(): Record<string, unknown> {
  try {
    if (!existsSync(SETTINGS_TOML)) return {}
    const text = readFileSync(SETTINGS_TOML, "utf-8")
    const out: Record<string, unknown> = {}
    let inSection = false
    for (const raw of text.split(/\r?\n/)) {
      const line = raw.trim()
      if (!line || line.startsWith("#")) continue
      if (line.startsWith("[")) {
        inSection = line.replace(/[\[\]\s]/g, "").toLowerCase() === "devin_proxy"
        continue
      }
      if (!inSection) continue
      const eq = line.indexOf("=")
      if (eq < 0) continue
      const key = line.slice(0, eq).trim().toLowerCase().replace(/^devin_proxy_/, "")
      let val: unknown = line.slice(eq + 1).trim()
      if (typeof val === "string" && val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1)
      else if (typeof val === "string" && val.startsWith("[") && val.endsWith("]")) {
        val = val.slice(1, -1).split(",").map((s) => s.trim().replace(/^"|"$/g, "")).filter(Boolean)
      } else if (val === "true" || val === "false") val = val === "true"
      else if (typeof val === "string" && /^-?\d+$/.test(val)) val = parseInt(val, 10)
      else if (typeof val === "string" && /^-?\d*\.\d+$/.test(val)) val = parseFloat(val)
      out[key] = val
    }
    return out
  } catch {
    return {}
  }
}

export const FALLBACK_VERSION = "3000.11.234"
export const CHANNEL = "chisel"

/** Version of the `devin` binary on PATH ("" when absent). */
export function cliVersion(): string {
  try {
    const exe = process.platform === "win32" ? "devin.exe" : "devin"
    const out = execFileSync(exe, ["version"], { timeout: 10000, encoding: "utf-8", stdio: ["ignore", "pipe", "pipe"] })
    const m = /(\d+\.\d+\.\d+)/.exec(out)
    return m ? m[1]! : ""
  } catch {
    return ""
  }
}

export interface Settings {
  host: string
  port: number
  backend: string
  clientVersion: string
  /** "normal" = vanilla passthrough (default). "uncensored" = override +
   * refusal guard + retry pipeline. Toggle via DEVIN_PROXY_MODE,
   * settings.toml `mode`, or `--mode`. */
  mode: "normal" | "uncensored"
  emitReasoning: boolean
  stripIncomingReasoning: boolean
  guardChars: number
  guardFull: boolean
  planPreamble: boolean
  maxRetries: number
  retryTemps: string
  toolDesc: "full" | "compact" | "none"
  nativeTools: boolean
  imgMaxBytes: number
  keepClientSystem: boolean
  maxInputTokens: number
  pruneKeepTurns: number
  allowedModels: string[]
  allowPaid: boolean
  defaultModel: string
  clientModelId: string
  systemFile?: string
}

const DEFAULTS: Settings = {
  host: "127.0.0.1",
  port: 8390,
  backend: "https://server.codeium.com",
  clientVersion: "auto",
  mode: "normal",
  emitReasoning: false,
  stripIncomingReasoning: true,
  guardChars: 300,
  guardFull: false,
  planPreamble: false,
  maxRetries: 3,
  retryTemps: "0.85,1.0,1.1",
  toolDesc: "compact",
  nativeTools: true,
  imgMaxBytes: 12 * 1024 * 1024,
  keepClientSystem: false,
  maxInputTokens: 240000,
  pruneKeepTurns: 12,
  allowedModels: [
    "swe-2-medium", "swe-2-high", "swe-2-max",
    "swe-2-flash-medium", "swe-2-flash-high", "swe-2-flash-max",
    "swe-2-1-low", "swe-2-1-medium", "swe-2-1-high", "swe-2-1-xhigh", "swe-2-1-max",
  ],
  allowPaid: false,
  defaultModel: "swe-2-high",
  clientModelId: "swe-2",
}

const env = (k: string) => process.env["DEVIN_PROXY_" + k]

export function loadSettings(overrides: Partial<Settings> = {}): Settings {
  const merged: Record<string, unknown> = { ...fileOverrides(), ...overrides }
  const s: Settings = { ...DEFAULTS } as Settings
  const pick = <T>(key: keyof Settings, envName: string, parse: (v: string) => T): void => {
    const e = env(envName)
    const sAny = s as unknown as Record<string, unknown>
    if (e !== undefined) sAny[key] = parse(e)
    else if (merged[key] !== undefined) sAny[key] = merged[key]
  }
  pick("host", "HOST", (v) => v)
  pick("port", "PORT", (v) => parseInt(v, 10))
  pick("backend", "BACKEND", (v) => v.replace(/\/+$/, ""))
  pick("clientVersion", "CLIENT_VERSION", (v) => v)
  pick("mode", "MODE", (v) => (v.toLowerCase() === "uncensored" ? "uncensored" : "normal"))
  pick("emitReasoning", "EMIT_REASONING", (v) => v === "true" || v === "1")
  pick("stripIncomingReasoning", "STRIP_INCOMING_REASONING", (v) => v !== "false" && v !== "0")
  pick("guardChars", "GUARD_CHARS", (v) => parseInt(v, 10))
  pick("guardFull", "GUARD_FULL", (v) => v === "true" || v === "1")
  pick("planPreamble", "PLAN_PREAMBLE", (v) => v === "true" || v === "1")
  pick("maxRetries", "MAX_RETRIES", (v) => parseInt(v, 10))
  pick("retryTemps", "RETRY_TEMPS", (v) => v)
  pick("toolDesc", "TOOL_DESC", (v) => v.toLowerCase() as Settings["toolDesc"])
  pick("nativeTools", "NATIVE_TOOLS", (v) => v !== "false" && v !== "0")
  pick("imgMaxBytes", "IMG_MAX_BYTES", (v) => parseInt(v, 10))
  pick("keepClientSystem", "KEEP_CLIENT_SYSTEM", (v) => v === "true" || v === "1")
  pick("maxInputTokens", "MAX_INPUT_TOKENS", (v) => parseInt(v, 10))
  pick("pruneKeepTurns", "PRUNE_KEEP_TURNS", (v) => parseInt(v, 10))
  pick("allowedModels", "ALLOWED_MODELS", (v) => v.split(",").map((x) => x.trim()).filter(Boolean))
  pick("allowPaid", "ALLOW_PAID", (v) => v === "true" || v === "1")
  pick("defaultModel", "DEFAULT_MODEL", (v) => v)
  pick("clientModelId", "CLIENT_MODEL_ID", (v) => v)
  pick("systemFile", "SYSTEM_FILE", (v) => v)

  if (s.clientVersion === "auto") s.clientVersion = cliVersion() || FALLBACK_VERSION
  else if (!s.clientVersion) s.clientVersion = FALLBACK_VERSION
  return s
}

import { describe, expect, test, beforeAll, afterAll } from "bun:test"
import { loadSettings } from "../src/config"
import { Auth, readKey } from "../src/auth"
import { parseToolText, TOOL_OPEN, TOOL_CLOSE } from "devin-engine"
import { resolveModel } from "devin-engine"

describe("config", () => {
  test("defaults", () => {
    const s = loadSettings()
    expect(s.port).toBe(8390)
    expect(s.backend).toBe("https://server.codeium.com")
    // Empty allowlist = the whole subscription catalog routes.
    expect(s.allowedModels).toEqual([])
    expect(s.defaultModel).toBe("swe-2-1")
    expect(s.clientVersion).toMatch(/\d+\.\d+\.\d+/) // resolved, not "auto"
  })
  test("env overrides", () => {
    const prev = process.env.DEVIN_PROXY_PORT
    process.env.DEVIN_PROXY_PORT = "9999"
    const s = loadSettings()
    expect(s.port).toBe(9999)
    if (prev === undefined) delete process.env.DEVIN_PROXY_PORT
    else process.env.DEVIN_PROXY_PORT = prev
  })
  test("allowed_models env parses CSV", () => {
    const prev = process.env.DEVIN_PROXY_ALLOWED_MODELS
    process.env.DEVIN_PROXY_ALLOWED_MODELS = "a, b ,c"
    const s = loadSettings()
    expect(s.allowedModels).toEqual(["a", "b", "c"])
    if (prev === undefined) delete process.env.DEVIN_PROXY_ALLOWED_MODELS
    else process.env.DEVIN_PROXY_ALLOWED_MODELS = prev
  })
})

describe("auth", () => {
  test("reads windsurf_api_key from credentials.toml", () => {
    const path = require("node:path").join(require("node:os").tmpdir(), "cred-" + Date.now() + ".toml")
    require("node:fs").writeFileSync(path, 'windsurf_api_key = "sk-test-123"\n')
    expect(readKey(path)).toBe("sk-test-123")
  })
  test("apiKey prefers env", () => {
    const prev = process.env.DEVIN_PROXY_API_KEY
    process.env.DEVIN_PROXY_API_KEY = " env-key "
    const a = new Auth("https://x")
    expect(a.apiKey()).toBe("env-key")
    if (prev === undefined) delete process.env.DEVIN_PROXY_API_KEY
    else process.env.DEVIN_PROXY_API_KEY = prev
  })
})

describe("engine re-exports through deps", () => {
  test("resolveModel + tool parse available", () => {
    expect(resolveModel("swe-2.1", { effort: "xhigh" })).toBe("swe-2-1-xhigh")
    const [, calls] = parseToolText(`${TOOL_OPEN} {"name":"f","arguments":{}} ${TOOL_CLOSE}`)
    expect(calls[0]!.function.name).toBe("f")
  })
})

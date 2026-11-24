#!/usr/bin/env node
/**
 * `devin-proxy` CLI — serve | login | version.
 *
 * Ported from devin_proxy/cli.py (the serve path; login reuses devin-core's
 * PKCE flow).
 */

import { loadSettings } from "./config"
import { serve } from "./server"

const USAGE = `devin-proxy — OpenAI-compatible proxy over the Devin backend

Usage:
  devin-proxy serve [--host H] [--port P] [--backend URL]
  devin-proxy login [--api-key TOKEN]   # PKCE browser flow, or write token
  devin-proxy version
`

async function main(argv: string[]): Promise<number> {
  const args = argv.slice(2)
  const cmd = args[0] ?? "serve"
  const flag = (name: string) => {
    const i = args.indexOf(`--${name}`)
    return i >= 0 ? args[i + 1] : undefined
  }

  if (cmd === "version" || cmd === "--version" || cmd === "-V") {
    const { version } = await import("../package.json", { with: { type: "json" } }).catch(() => ({ version: "0.1.0" }))
    console.log(version)
    return 0
  }
  if (cmd === "help" || cmd === "--help" || cmd === "-h") {
    process.stdout.write(USAGE)
    return 0
  }
  if (cmd === "login") {
    const apiKey = flag("api-key")
    const { Auth, writeCredentials, defaultCredentialsPath } = await import("./auth")
    if (apiKey) {
      writeCredentials(defaultCredentialsPath(), apiKey)
      console.log(`credentials written to ${defaultCredentialsPath()}`)
      return 0
    }
    // PKCE browser flow via devin-core
    const { loginAuto, openBrowser } = await import("devin-core")
    const flow = await loginAuto()
    openBrowser(flow.url)
    console.log(`opened ${flow.url} — finish the login in the browser`)
    const token = await flow.finish()
    if (token) {
      writeCredentials(defaultCredentialsPath(), token)
      console.log(`credentials written to ${defaultCredentialsPath()}`)
      return 0
    }
    console.error("login produced no token")
    return 1
  }
  if (cmd === "serve" || cmd === undefined) {
    const settings = loadSettings({
      ...(flag("host") ? { host: flag("host") } : {}),
      ...(flag("port") ? { port: parseInt(flag("port")!, 10) } : {}),
      ...(flag("backend") ? { backend: flag("backend") } : {}),
    })
    await serve(settings)
    // Block forever — the server keeps the event loop alive; exiting main
    // would process.exit() and kill it. Signal handlers let Ctrl+C through.
    await new Promise<never>(() => {})
    return 0
  }
  process.stderr.write(USAGE)
  return 1
}

main(process.argv).then(
  (code) => process.exit(code),
  (e) => {
    console.error("[devin-proxy]", e)
    process.exit(1)
  },
)

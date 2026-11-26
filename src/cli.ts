#!/usr/bin/env node
/**
 * `devin-proxy` CLI — serve | login | version.
 *
 * Ported from devin_proxy/cli.py (the serve path; login reuses devin-core's
 * PKCE flow).
 */

import { createRequire } from "node:module"
import { loadSettings } from "./config.js"
import { serve } from "./server.js"
import { ensureInstance, listInstances, logPath, readInstance, registerSelf, restartInstance, runningInstance, stopInstance } from "./service.js"
import { existsSync, readFileSync } from "node:fs"

const { version: PKG_VERSION } = createRequire(import.meta.url)("../package.json") as { version: string }

const USAGE = `devin-proxy — OpenAI-compatible proxy over the Devin backend

Usage:
  devin-proxy                           same as "service start"
  devin-proxy service start [--name N] [--port P] [--host H] [--mode normal|uncensored] [--backend URL]
                                        start the instance in the background, or reuse it
  devin-proxy service run   [--name N] [same flags]
                                        run the instance in this terminal (foreground)
  devin-proxy service status|stop|restart|logs [--name N]
  devin-proxy service list              every known instance and its state
  devin-proxy login [--api-key TOKEN]   PKCE browser flow, or write a token
  devin-proxy version
`

const SERVICE_COMMANDS = new Set(["status", "stop", "restart", "logs", "list"])

async function main(argv: string[]): Promise<number> {
  const args = argv.slice(2)
  const first = args[0]
  const cmd = first === undefined || first.startsWith("--") ? "service" : first
  const sub = cmd === "service" ? (first === "service" ? args[1] ?? "start" : "start") : cmd
  const flag = (name: string) => {
    const i = args.indexOf(`--${name}`)
    return i >= 0 ? args[i + 1] : undefined
  }
  const name = flag("name") ?? "default"
  const portFlag = flag("port")
  const serviceOptions = {
    name,
    ...(flag("host") ? { host: flag("host") } : {}),
    ...(portFlag ? { port: parseInt(portFlag, 10) } : {}),
    ...(flag("mode") ? { mode: flag("mode") } : {}),
    ...(flag("backend") ? { backend: flag("backend") } : {}),
  }

  if (cmd === "version" || cmd === "--version" || cmd === "-V") {
    console.log(PKG_VERSION)
    return 0
  }
  if (cmd === "help" || cmd === "--help" || cmd === "-h") {
    process.stdout.write(USAGE)
    return 0
  }
  if (cmd === "login") {
    const apiKey = flag("api-key")
    const { Auth, writeCredentials, defaultCredentialsPath } = await import("./auth.js")
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
  if (cmd === "service" && sub === "run") {
    const settings = loadSettings({
      ...(flag("host") ? { host: flag("host") } : {}),
      ...(portFlag ? { port: parseInt(portFlag, 10) } : {}),
      ...(flag("backend") ? { backend: flag("backend") } : {}),
      ...(flag("mode") ? { mode: flag("mode") === "uncensored" ? "uncensored" : "normal" } : {}),
    })
    await serve(settings)
    registerSelf({ name, host: settings.host, port: settings.port, mode: settings.mode, backend: settings.backend, version: PKG_VERSION })
    await new Promise<never>(() => {})
  }
  if (cmd === "service" && sub === "start") {
    const { instance, reused } = await ensureInstance(serviceOptions)
    console.log(
      reused
        ? `devin-proxy: "${instance.name}" already running at ${instance.url} (pid ${instance.pid})`
        : `devin-proxy: "${instance.name}" ready at ${instance.url} (pid ${instance.pid}); logs: ${logPath(instance.name)}`,
    )
    return 0
  }
  if (cmd === "service" && SERVICE_COMMANDS.has(sub)) return serviceCommand(sub, name, args)
  process.stderr.write(USAGE)
  return 1
}

async function serviceCommand(cmd: string, name: string, args: string[]): Promise<number> {
  if (cmd === "list") {
    const instances = listInstances()
    if (!instances.length) console.log("no instances")
    for (const instance of instances) {
      const alive = await runningInstance(instance.name)
      console.log(`${instance.name.padEnd(12)} ${(alive ? "running" : "stopped").padEnd(9)} ${instance.url}  mode=${instance.mode}`)
    }
    return 0
  }
  if (cmd === "status") {
    const instance = await runningInstance(name)
    if (!instance) return console.log(`"${name}" is not running`), 1
    console.log(`"${name}" running at ${instance.url} (pid ${instance.pid}, mode=${instance.mode}, since ${instance.startedAt})`)
    return 0
  }
  if (cmd === "stop") {
    const stopped = await stopInstance(name)
    console.log(stopped ? `"${name}" stopped` : `"${name}" was not running`)
    return 0
  }
  if (cmd === "restart") {
    const portFlag = args.indexOf("--port")
    const instance = await restartInstance(name, {
      ...(portFlag >= 0 ? { port: parseInt(args[portFlag + 1]!, 10) } : {}),
      ...(args.includes("--mode") ? { mode: args[args.indexOf("--mode") + 1] } : {}),
    })
    console.log(`"${name}" restarted at ${instance.url} (pid ${instance.pid})`)
    return 0
  }
  if (cmd === "logs") {
    const path = logPath(name)
    if (!readInstance(name) && !existsSync(path)) return console.log(`no logs for "${name}"`), 1
    const lines = existsSync(path) ? readFileSync(path, "utf-8").split(/\r?\n/) : []
    console.log(lines.slice(-50).join("\n"))
    return 0
  }
  return 1
}

main(process.argv).then(
  (code) => process.exit(code),
  (e) => {
    console.error(e instanceof Error ? `devin-proxy: ${e.message}` : e)
    process.exit(1)
  },
)

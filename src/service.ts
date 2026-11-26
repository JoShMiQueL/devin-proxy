/**
 * Background instances of the proxy. A named instance is a detached
 * `devin-proxy serve --foreground` process, recorded in a small state file
 * so later invocations can reuse it, report on it, or stop it.
 */

import { spawn } from "node:child_process"
import { closeSync, existsSync, mkdirSync, openSync, readdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"

export interface Instance {
  name: string
  pid: number
  host: string
  port: number
  url: string
  mode: string
  backend: string
  version: string
  startedAt: string
}

export interface InstanceOptions {
  name: string
  host?: string
  port?: number
  mode?: string
  backend?: string
}

const ROOT = process.env.DEVIN_PROXY_HOME ?? join(homedir(), ".devin-proxy")
const STATE_DIR = join(ROOT, "services")
const LOG_DIR = join(ROOT, "logs")
const START_TIMEOUT_MS = 90_000

export const logPath = (name: string) => join(LOG_DIR, `${name}.log`)
const statePath = (name: string) => join(STATE_DIR, `${name}.json`)
const lockPath = (name: string) => join(STATE_DIR, `${name}.lock`)
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export function readInstance(name: string): Instance | undefined {
  try {
    return JSON.parse(readFileSync(statePath(name), "utf-8")) as Instance
  } catch {
    return undefined
  }
}

export function writeInstance(instance: Instance): void {
  mkdirSync(STATE_DIR, { recursive: true })
  writeFileSync(statePath(instance.name), JSON.stringify(instance, null, 2))
}

export function removeInstance(name: string): void {
  if (existsSync(statePath(name))) unlinkSync(statePath(name))
}

export function listInstances(): Instance[] {
  if (!existsSync(STATE_DIR)) return []
  return readdirSync(STATE_DIR)
    .filter((file) => file.endsWith(".json"))
    .map((file) => readInstance(file.slice(0, -".json".length)))
    .filter((instance): instance is Instance => instance !== undefined)
}

export function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch (e) {
    return (e as NodeJS.ErrnoException).code === "EPERM"
  }
}

async function isHealthy(url: string): Promise<boolean> {
  try {
    return (await fetch(`${url}/v1/models`, { signal: AbortSignal.timeout(1000) })).ok
  } catch {
    return false
  }
}

/** The instance when its process is alive and answering; otherwise undefined (stale state is cleared). */
export async function runningInstance(name: string): Promise<Instance | undefined> {
  const instance = readInstance(name)
  if (!instance) return undefined
  if (isAlive(instance.pid) && (await isHealthy(instance.url))) return instance
  removeInstance(name)
  return undefined
}

function assertPortFree(name: string, port: number): void {
  const other = listInstances().find((instance) => instance.name !== name && instance.port === port && isAlive(instance.pid))
  if (other) throw new Error(`port ${port} is already used by the "${other.name}" instance`)
}

/** Start the named instance in the background, or reuse it when it is already running. */
export async function ensureInstance(options: InstanceOptions): Promise<{ instance: Instance; reused: boolean }> {
  const existing = await runningInstance(options.name)
  if (existing) {
    if (options.port !== undefined && options.port !== existing.port) {
      throw new Error(`"${options.name}" is running on port ${existing.port}; use: devin-proxy restart --name ${options.name} --port ${options.port}`)
    }
    return { instance: existing, reused: true }
  }

  const host = options.host ?? "127.0.0.1"
  const port = options.port ?? 8390
  assertPortFree(options.name, port)

  mkdirSync(STATE_DIR, { recursive: true })
  let lock: number
  try {
    lock = openSync(lockPath(options.name), "wx")
  } catch {
    const deadline = Date.now() + START_TIMEOUT_MS
    while (Date.now() < deadline) {
      await sleep(300)
      const started = await runningInstance(options.name)
      if (started) return { instance: started, reused: true }
    }
    throw new Error(`another start of "${options.name}" is stuck; remove ${lockPath(options.name)} if no start is running`)
  }

  try {
    mkdirSync(LOG_DIR, { recursive: true })
    const out = openSync(logPath(options.name), "a")
    const args = [process.argv[1]!, "service", "run", "--name", options.name, "--host", host, "--port", String(port)]
    if (options.mode) args.push("--mode", options.mode)
    if (options.backend) args.push("--backend", options.backend)
    const child = spawn(process.execPath, args, { detached: true, stdio: ["ignore", out, out], windowsHide: true })
    child.unref()
    closeSync(out)

    const deadline = Date.now() + START_TIMEOUT_MS
    while (Date.now() < deadline) {
      const started = await runningInstance(options.name)
      if (started && started.pid === child.pid) return { instance: started, reused: false }
      if (child.pid === undefined || !isAlive(child.pid)) break
      await sleep(300)
    }
    throw new Error(`"${options.name}" did not become ready; see ${logPath(options.name)}`)
  } finally {
    closeSync(lock)
    unlinkSync(lockPath(options.name))
  }
}

/** Record the current process as the named instance (called by a foreground service once it listens). */
export function registerSelf(options: Omit<Instance, "pid" | "url" | "startedAt"> & { port: number; host: string }): void {
  const url = `http://${options.host}:${options.port}`
  writeInstance({ ...options, pid: process.pid, url, startedAt: new Date().toISOString() })
  process.on("exit", () => {
    if (readInstance(options.name)?.pid === process.pid) removeInstance(options.name)
  })
}

/** Stop the named instance. Returns false when there was nothing to stop. */
export async function stopInstance(name: string): Promise<boolean> {
  const instance = readInstance(name)
  if (!instance) return false
  if (isAlive(instance.pid)) {
    process.kill(instance.pid)
    const deadline = Date.now() + 5000
    while (isAlive(instance.pid) && Date.now() < deadline) await sleep(100)
  }
  removeInstance(name)
  return true
}

export async function restartInstance(name: string, overrides: Partial<InstanceOptions> = {}): Promise<Instance> {
  const current = readInstance(name)
  if (!current) throw new Error(`no "${name}" instance to restart; start it with: devin-proxy --name ${name}`)
  await stopInstance(name)
  const { instance } = await ensureInstance({
    name,
    host: overrides.host ?? current.host,
    port: overrides.port ?? current.port,
    mode: overrides.mode ?? current.mode,
    backend: overrides.backend ?? current.backend,
  })
  return instance
}

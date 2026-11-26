import { afterAll, beforeAll, describe, expect, test } from "bun:test"
import { mkdtempSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

const home = mkdtempSync(join(tmpdir(), "devin-proxy-service-"))
process.env.DEVIN_PROXY_HOME = home
const service = await import("../src/service")

const base = (name: string, url: string, pid: number) => ({
  name,
  pid,
  host: "127.0.0.1",
  port: Number(new URL(url).port),
  url,
  mode: "normal",
  backend: "https://server.codeium.com",
  version: "0.0.0",
  startedAt: new Date().toISOString(),
})

let server: ReturnType<typeof Bun.serve>

beforeAll(() => {
  server = Bun.serve({ port: 0, hostname: "127.0.0.1", fetch: () => Response.json({ data: [] }) })
})
afterAll(() => server.stop(true))

describe("service instances", () => {
  test("a live, answering instance is reported as running", async () => {
    const url = `http://127.0.0.1:${server.port}`
    service.writeInstance(base("live", url, process.pid))
    const running = await service.runningInstance("live")
    expect(running?.url).toBe(url)
    service.removeInstance("live")
  })

  test("state whose process is gone is cleared", async () => {
    service.writeInstance(base("dead", `http://127.0.0.1:${server.port}`, 2 ** 22 - 3))
    expect(await service.runningInstance("dead")).toBeUndefined()
    expect(service.readInstance("dead")).toBeUndefined()
  })

  test("state whose port does not answer is cleared even if the pid lives", async () => {
    service.writeInstance(base("silent", "http://127.0.0.1:1", process.pid))
    expect(await service.runningInstance("silent")).toBeUndefined()
  })

  test("list reports every recorded instance", async () => {
    service.writeInstance(base("one", `http://127.0.0.1:${server.port}`, process.pid))
    service.writeInstance(base("two", `http://127.0.0.1:${server.port}`, process.pid))
    expect(service.listInstances().map((i) => i.name).sort()).toEqual(["one", "two"])
    service.removeInstance("one")
    service.removeInstance("two")
  })

  test("stopping a missing instance reports nothing to stop", async () => {
    expect(await service.stopInstance("never-started")).toBe(false)
  })
})

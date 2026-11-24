/**
 * devin-proxy — the standalone OpenAI-compatible proxy over devin-engine.
 *
 * Library exports; the `devin-proxy` bin runs `cli.ts`.
 */

export { loadSettings, SETTINGS_TOML, FALLBACK_VERSION, CHANNEL, cliVersion, type Settings } from "./config.js"
export { Auth, defaultCredentialsPath, readKey, writeCredentials } from "./auth.js"
export { fetchCliCatalog, type CliModelConfig } from "./catalog.js"
export { buildApp, serve, type App, type ServeHandle } from "./server.js"

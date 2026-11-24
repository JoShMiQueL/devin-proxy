/**
 * devin-proxy — the standalone OpenAI-compatible proxy over devin-engine.
 *
 * Library exports; the `devin-proxy` bin runs `cli.ts`.
 */
export { loadSettings, SETTINGS_TOML, FALLBACK_VERSION, CHANNEL, cliVersion } from "./config";
export { Auth, defaultCredentialsPath, readKey, writeCredentials } from "./auth";
export { fetchCliCatalog } from "./catalog";
export { buildApp, serve } from "./server";

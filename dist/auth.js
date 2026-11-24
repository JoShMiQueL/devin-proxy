/**
 * Credential loading and JWT minting for the Devin gateway.
 *
 * Resolves the session token (env > credentials.toml) and caches the
 * short-lived JWT (10 min) via devin-core's getCachedUserJwt.
 *
 * Ported from devin_proxy/transport/auth.py.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { getCachedUserJwt } from "devin-core";
export function defaultCredentialsPath() {
    const envPath = process.env.DEVIN_PROXY_CRED;
    if (envPath)
        return envPath;
    const home = homedir();
    const appdata = process.env.APPDATA;
    const candidates = [
        join(home, ".devin", "credentials.toml"),
        ...(appdata ? [join(appdata, "devin", "credentials.toml")] : []),
        join(home, ".config", "devin", "credentials.toml"),
    ];
    for (const p of candidates)
        if (existsSync(p))
            return p;
    return candidates[0];
}
/** windsurf_api_key out of a credentials.toml (Devin CLI format). */
export function readKey(path) {
    const s = readFileSync(path, "utf-8");
    const m = /windsurf_api_key\s*=\s*"([^"]+)"/.exec(s);
    if (!m)
        throw new Error(`no windsurf_api_key in ${path}`);
    return m[1];
}
/** Persist a session token in the Devin CLI's own credentials.toml format. */
export function writeCredentials(path, apiKey, apiServer = "https://server.codeium.com") {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, `windsurf_api_key = "${apiKey}"\napi_server_url = "${apiServer}"\ndevin_webapp_host = "app.devin.ai"\ndevin_api_url = "https://api.devin.ai"\n`, "utf-8");
    return path;
}
/** Session token + cached JWT. */
export class Auth {
    base;
    credentials;
    constructor(base, credentials) {
        this.base = base;
        this.base = base.replace(/\/+$/, "");
        this.credentials = credentials ?? defaultCredentialsPath();
    }
    apiKey() {
        const k = process.env.DEVIN_PROXY_API_KEY;
        if (k)
            return k.trim();
        return readKey(this.credentials);
    }
    jwt() {
        return getCachedUserJwt(this.apiKey(), this.base);
    }
}

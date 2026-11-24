/**
 * Credential loading and JWT minting for the Devin gateway.
 *
 * Resolves the session token (env > credentials.toml) and caches the
 * short-lived JWT (10 min) via devin-core's getCachedUserJwt.
 *
 * Ported from devin_proxy/transport/auth.py.
 */
export declare function defaultCredentialsPath(): string;
/** windsurf_api_key out of a credentials.toml (Devin CLI format). */
export declare function readKey(path: string): string;
/** Persist a session token in the Devin CLI's own credentials.toml format. */
export declare function writeCredentials(path: string, apiKey: string, apiServer?: string): string;
/** Session token + cached JWT. */
export declare class Auth {
    readonly base: string;
    readonly credentials: string;
    constructor(base: string, credentials?: string);
    apiKey(): string;
    jwt(): Promise<string>;
}

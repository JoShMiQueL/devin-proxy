/**
 * The OpenAI-compatible HTTP surface: /v1/chat/completions (SSE + unary),
 * /v1/models, /health, /v1/image_caption, /v1/web_search.
 *
 * node:http server — no framework. The Engine drives the upstream; this
 * layer only frames deltas as chat.completion.chunk SSE events.
 *
 * Ported from devin_proxy/api/routes.py + server.py.
 */
import { type Server } from "node:http";
import { Engine, OverridePrompt } from "devin-engine";
import type { Auth } from "./auth";
import type { CliModelConfig } from "./catalog";
import type { Settings } from "./config";
export interface App {
    server: Server;
    /** Catalog lands after boot — routes degrade until it does. */
    setCatalog(cat: Map<string, CliModelConfig>): void;
}
export declare function buildApp(settings: Settings, auth: Auth, engine: Engine, override: OverridePrompt): App;
export interface ServeHandle {
    server: Server;
    engine: Engine;
    close(): void;
}
/** settings -> auth -> engine -> http server. Ported from server.py::serve. */
export declare function serve(settings: Settings): Promise<ServeHandle>;

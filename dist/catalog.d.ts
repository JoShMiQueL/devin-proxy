/**
 * Fetch the live model catalog from GetCliModelConfigs.
 *
 * This is the *other* catalog RPC — the one that exposes per-model credit
 * cost, promo/free windows and aliases. devin-core's `getCachedCatalog`
 * reads GetCascadeModelConfigs for enabled/pricing; this reads the CLI
 * surface the Python proxy uses for billing tags.
 *
 * Ported from devin_proxy/models/fetch.py + the ModelCatalog half of
 * devin_proxy/models/catalog.py.
 */
export interface CliModelConfig {
    uid: string;
    name: string;
    context: number;
    /** Relative credit cost per run (field 3, float32). 0 = free lane. */
    credits: number;
    /** Promo/free window end, epoch seconds (field 19.2.1). */
    expiresAt: number;
    /** Promo label, e.g. "83% off" (field 19.3). */
    promo: string;
    aliases: string[];
    expiryIso(): string;
}
/** GetCliModelConfigs -> Map<uid, config>, or null on failure. */
export declare function fetchCliCatalog(base: string, apiKey: string, jwt: string, clientVersion: string, timeoutMs?: number): Promise<Map<string, CliModelConfig> | null>;

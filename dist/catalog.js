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
import { encodeMessage, encodeString, iterFields } from "devin-core";
import { randomUUID } from "node:crypto";
import { CHANNEL, FALLBACK_VERSION } from "./config";
const CFG_PATH = "/exa.api_server_pb.ApiServerService/GetCliModelConfigs";
function metadata(apiKey, jwt, version, channel = CHANNEL) {
    const v = version || FALLBACK_VERSION;
    const parts = [
        encodeString(1, "devin-cli"),
        encodeString(7, v),
        encodeString(28, channel),
        encodeString(12, channel),
        encodeString(2, v),
        encodeString(3, apiKey),
        encodeString(4, "en"),
        encodeString(5, "windows"),
        encodeString(10, randomUUID()),
    ];
    if (jwt)
        parts.push(encodeString(21, jwt));
    return Buffer.concat(parts);
}
function parseCfg(b) {
    let name = "";
    let uid = "";
    let context = 0;
    let credits = 0;
    let expiresAt = 0;
    let promo = "";
    const aliases = [];
    for (const f of iterFields(b)) {
        if (f.num === 1 && f.wire === 2 && Buffer.isBuffer(f.value))
            name = f.value.toString("utf8");
        else if (f.num === 3 && f.wire === 5 && Buffer.isBuffer(f.value) && f.value.length === 4) {
            credits = f.value.readFloatLE(0);
        }
        else if (f.num === 18 && f.wire === 0)
            context = Number(f.value);
        else if (f.num === 19 && f.wire === 2 && Buffer.isBuffer(f.value)) {
            for (const p of iterFields(f.value)) {
                if (p.num === 2 && p.wire === 2 && Buffer.isBuffer(p.value)) {
                    for (const w of iterFields(p.value)) {
                        if (w.num === 1 && w.wire === 0)
                            expiresAt = Number(w.value);
                    }
                }
                else if (p.num === 3 && p.wire === 2 && Buffer.isBuffer(p.value)) {
                    promo = p.value.toString("utf8");
                }
            }
        }
        else if (f.num === 22 && f.wire === 2 && Buffer.isBuffer(f.value)) {
            uid = f.value.toString("utf8");
        }
        else if (f.num === 23 && f.wire === 2 && Buffer.isBuffer(f.value)) {
            for (const i of iterFields(f.value)) {
                if (i.num === 27 && i.wire === 2 && Buffer.isBuffer(i.value)) {
                    aliases.push(i.value.toString("utf8"));
                }
            }
        }
    }
    if (!uid)
        return null;
    return {
        uid, name, context, credits, expiresAt, promo, aliases,
        expiryIso: () => (expiresAt ? new Date(expiresAt * 1000).toISOString().slice(0, 10) : ""),
    };
}
/** GetCliModelConfigs -> Map<uid, config>, or null on failure. */
export async function fetchCliCatalog(base, apiKey, jwt, clientVersion, timeoutMs = 30_000) {
    const body = encodeMessage(1, metadata(apiKey, jwt, clientVersion));
    try {
        const res = await fetch(`${base}${CFG_PATH}`, {
            method: "POST",
            headers: { "Content-Type": "application/proto", "Connect-Protocol-Version": "1" },
            body: new Uint8Array(body),
            signal: AbortSignal.timeout(timeoutMs),
        });
        if (!res.ok)
            return null;
        const buf = Buffer.from(await res.arrayBuffer());
        const out = new Map();
        for (const f of iterFields(buf)) {
            if (f.num !== 1 || f.wire !== 2 || !Buffer.isBuffer(f.value))
                continue;
            const cfg = parseCfg(f.value);
            if (cfg)
                out.set(cfg.uid, cfg);
        }
        return out;
    }
    catch {
        return null;
    }
}

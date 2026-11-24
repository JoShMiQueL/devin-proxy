/**
 * Runtime configuration: env var > ~/.devin-proxy/settings.toml > default.
 *
 * Ported from devin_proxy/config.py.
 */
export declare const SETTINGS_TOML: string;
export declare const FALLBACK_VERSION = "3000.11.234";
export declare const CHANNEL = "chisel";
/** Version of the `devin` binary on PATH ("" when absent). */
export declare function cliVersion(): string;
export interface Settings {
    host: string;
    port: number;
    backend: string;
    clientVersion: string;
    emitReasoning: boolean;
    stripIncomingReasoning: boolean;
    guardChars: number;
    guardFull: boolean;
    planPreamble: boolean;
    maxRetries: number;
    retryTemps: string;
    toolDesc: "full" | "compact" | "none";
    nativeTools: boolean;
    imgMaxBytes: number;
    keepClientSystem: boolean;
    maxInputTokens: number;
    pruneKeepTurns: number;
    allowedModels: string[];
    allowPaid: boolean;
    defaultModel: string;
    clientModelId: string;
    systemFile?: string;
}
export declare function loadSettings(overrides?: Partial<Settings>): Settings;

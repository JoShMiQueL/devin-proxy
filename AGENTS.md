# AGENTS.md — working in devin-proxy

The OpenAI-compatible standalone proxy — a drop-in `OPENAI_BASE_URL` for any client that speaks `/v1/chat/completions`. Thin HTTP layer over devin-engine's `Engine` class; the pipeline logic lives there, not here.

## Hard rules

- **Streaming is load-bearing**: SSE deltas must flow as they arrive from the upstream — the original Python proxy buffered everything and users felt it. `res.write` per delta, never accumulate-then-flush. The only hold allowed is the engine's refusal-guard head window, which is the price of invisible retries.
- **`allowedModels` empty means everything in the catalog** — resolution is catalog-driven through devin-core's `resolveModelUid`. No hardcoded tier tables here.
- One `/v1/models` entry per family with effort lanes as `supported_reasoning_efforts` — clients pick lanes with `reasoning_effort`, not model ids per tier. Speed modifiers (`-fast`, `-lightning`) are their own families.
- `system_file` in settings is just a path to a custom override — it does NOT control injection language (the engine detects that per-conversation now).
- The catalog prefetch can fail or lag — the engine's legacy tier-table fallback keeps SWE lanes routable in that window. Don't remove it.

## Versioning & releases

- devin-core and devin-engine are pinned **exactly** in package.json — no carets. What you test is what installs. When upstream publishes, bump manually: `npm pkg set dependencies.devin-engine=X.Y.Z && npm install && gh pr create --fill`.
- release-please + trusted publishing via the shared `gh-actions` reusables; see the ecosystem root AGENTS.md for the protection-drop merge dance.

## Testing against it

`node dist/cli.js service run --port 8390 --mode uncensored` (foreground) or `devin-proxy service start` (background) with the devin credentials at `~/AppData/Roaming/devin/credentials.toml` (auto-detected). The user's opencode.json already carries a `devin-proxy` provider pointing at 127.0.0.1:8390 — `opencode run "..." --model devin-proxy/swe-2-high` is the end-to-end check.

## Ecosystem

| Repo | Role |
|---|---|
| `devin-core` | wire + auth + PKCE + catalog |
| `devin-engine` | guarded-retry pipeline (Engine class embedded here) |
| **`devin-proxy`** (this) | OpenAI-compatible standalone proxy |
| `opencode-devin` | OpenCode v2 plugin |
| `claude-devin` | Claude-compatible surface |

# devin-proxy — design notes

TypeScript OpenAI-compatible proxy over the Devin/Cascade backend. Ported
from the Python `devin-proxy` (now `devin-proxy-py`) to run on
`devin-core` + `devin-engine` — one pipeline implementation, three
deliveries (this standalone server is one of them).

## Layers

```
config.ts   env > ~/.devin-proxy/settings.toml > defaults
            fingerprints the installed `devin` CLI version (fallback const)
auth.ts     DEVIN_PROXY_API_KEY > credentials.toml windsurf_api_key
            JWT via devin-core's getCachedUserJwt (10-min cache)
catalog.ts  GetCliModelConfigs — the *other* catalog RPC, exposes
            credits_per_run / promo windows / aliases that
            devin-core's GetCascadeModelConfigs does not.
            Also GetImageCaption + GetWebSearchResults.
server.ts   node:http — no framework. SSE chat + /v1/models + /health.
            Engine.run() drives upstream; this layer only frames deltas
            as chat.completion.chunk.
cli.ts      serve | login (PKCE via devin-core) | version
```

The whole compliance pipeline (guard, override injection, refusal retry,
sanitize, prune, model resolve, tool translation) lives in
**devin-engine** — the `Engine` class — which this package wraps in an
HTTP listener.

## Endpoints

| Route | Notes |
| --- | --- |
| `POST /v1/chat/completions` | `stream:true`→SSE, `false`→unary |
| `GET /v1/models`, `/models` | allowed lanes + swe-2/-flash/-2.1 aliases; `free_until`, `credits_per_run`, `free_tier` under `ALLOW_PAID` |
| `GET /health` | backend, override file/chars, catalog count, promo windows |
| `POST /v1/web_search` | GetWebSearchResults -> {id,url,title,content} |
| `POST /v1/image_caption` | GetImageCaption -> {caption} |

## Settings

`DEVIN_PROXY_*` env, `~/.devin-proxy/settings.toml` `[devin_proxy]`, or
CLI flags. See `config.ts` for the full list and defaults.

## Publish

`devin-proxy` on npm. OIDC Trusted Publishing
(`.github/workflows/publish.yml`) — `git tag v* && git push --tags` or
`workflow_dispatch` publishes without a token.

Sibling pieces: `devin-core` (protocol), `devin-engine` (pipeline),
`devin-proxy-py` (the Python original this ports). The ecosystem-wide
refactor plan lives in [`DESIGN-ecosystem.md`](./DESIGN-ecosystem.md).

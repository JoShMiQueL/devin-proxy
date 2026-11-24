# devin-proxy

An **OpenAI-compatible local proxy** that serves the Devin/Cascade backend's SWE-2 / SWE-2.1 lanes through the [`devin-engine`](../devin-engine) guarded-retry pipeline — a drop-in `OPENAI_BASE_URL` for any client that speaks `/v1/chat/completions`.

TypeScript port of the Python `devin-proxy`. Sits on [`devin-core`](../devin-core) (wire + auth + catalog) and [`devin-engine`](../devin-engine) (guard, override, retry, sanitize, resolve).

## Run

```bash
bun install
bun src/cli.ts serve            # 127.0.0.1:8390
# or, after build:
node dist/cli.js serve --port 8390
```

Credentials come from `DEVIN_PROXY_API_KEY` or the Devin CLI's `credentials.toml` (`windsurf_api_key`). `devin-proxy login` runs the PKCE browser flow and writes it.

## Client

```python
from openai import OpenAI
c = OpenAI(base_url="http://127.0.0.1:8391/v1", api_key="unused")
c.chat.completions.create(model="swe-2", messages=[...])
```

Point `ANTHROPIC_BASE_URL`/`OPENAI_BASE_URL`, Cursor, aider, continue.dev, Cline — anything OpenAI-shaped — at it.

## Endpoints

| Route | What |
| --- | --- |
| `POST /v1/chat/completions` | OpenAI chat, `stream: true`→SSE, `stream:false`→unary |
| `GET /v1/models`, `/models` | allowed lanes + `swe-2`/`swe-2-flash`/`swe-2.1` aliases; `free_until`, `credits_per_run`, `free_tier` when `--allow-paid` |
| `GET /health` | backend, override file, catalog count, promo windows |

## Models

`model` resolves by family + `reasoning_effort`:

- `swe-2` → `swe-2-{medium,high,max}` (default `high`)
- `swe-2-flash` → `swe-2-flash-{medium,high,max}`
- `swe-2.1` → `swe-2-1-{low,medium,high,xhigh,max}` — free promo until **2026-12-09**
- `reasoning_effort` picks the tier inside whichever family the id selected, clamping to the nearest defined level.

`*-lightning` lanes are never routed — they bill fast-mode credits. `allow_paid` opens the full live catalog; every non-SWE uid bills credits.

## Settings

Env `DEVIN_PROXY_*`, `~/.devin-proxy/settings.toml` `[devin_proxy]`, or flags. Notables: `ALLOW_PAID`, `ALLOWED_MODELS` (CSV), `GUARD_CHARS`, `GUARD_FULL`, `MAX_RETRIES`, `EMIT_REASONING`, `MAX_INPUT_TOKENS`, `SYSTEM_FILE` (`es`/`english`/`spanish` picks a bundled override).

## What the engine does per request

Sanitize history → inject the system override → resolve model → stream upstream → hold the first N chars behind a multilingual refusal guard → on a refusal, resample inside the same downstream stream with an escalated frame (invisible to the client) → translate tool calls back to OpenAI shape. See [devin-engine](../devin-engine).

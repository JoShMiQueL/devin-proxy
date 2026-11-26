# devin-proxy

An **OpenAI-compatible local proxy** that serves the Devin/Cascade backend's full model catalog through the [`devin-engine`](../devin-engine) guarded-retry pipeline — a drop-in `OPENAI_BASE_URL` for any client that speaks `/v1/chat/completions`.

TypeScript port of the Python `devin-proxy`. Sits on [`devin-core`](../devin-core) (wire + auth + catalog) and [`devin-engine`](../devin-engine) (guard, override, retry, sanitize, resolve).

## Modes

- **`normal`** (default) — vanilla passthrough: history sanitize + model
  resolve, then a single upstream attempt streamed back. No system
  override, no refusal guard, no retry frames.
- **`uncensored`** — the full guarded-retry pipeline described below:
  override injection, refusal guard, escalated resampling.

Enable it any of these ways:

```bash
devin-proxy service start --mode uncensored
DEVIN_PROXY_MODE=uncensored devin-proxy service start
# ~/.devin-proxy/settings.toml
[devin_proxy]
mode = "uncensored"
```


## Run

```bash
devin-proxy                                  # start (or reuse) the default service on 127.0.0.1:8390
devin-proxy service start --name work --port 8391   # another standalone instance
devin-proxy service status|list|logs|restart|stop [--name work]
devin-proxy service run                      # foreground, in this terminal
```

Services run detached and log to `~/.devin-proxy/logs/<name>.log`. Their state lives in `~/.devin-proxy/services/<name>.json`. Starting an instance that is already running reuses it.

From a checkout:

```bash
bun install
bun src/cli.ts service run      # foreground, 127.0.0.1:8390
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
| `GET /v1/models`, `/models` | one entry per catalog family + `supported_reasoning_efforts`, `credits_per_run`, `free_until` |
| `GET /health` | backend, override file, catalog count, promo windows |

## Models

Resolution is **catalog-driven**: every family the subscription exposes —
claude, gpt, gemini, grok, kimi, swe — is routable. `model` names a family
(or a bare/per-effort uid) and `reasoning_effort` picks the lane inside it:

- `swe-2.1` + `reasoning_effort: "xhigh"` → `swe-2-1-xhigh`
- `claude-opus-5-5` + `reasoning_effort: "high"` → `claude-opus-5-5-high`
- a verbatim uid like `gpt-5-6-sol-high` passes through untouched
- catalog aliases (`swe-2`, `swe-2.1`) resolve to the family's default lane

`/v1/models` lists one entry per family with its `supported_reasoning_efforts`,
credit cost and promo windows. `ALLOWED_MODELS` (CSV) restricts what is served
when set; empty means everything in the catalog. `*-lightning` lanes bill
fast-mode credits — check `credits_per_run` before routing them.

## Settings

Env `DEVIN_PROXY_*`, `~/.devin-proxy/settings.toml` `[devin_proxy]`, or flags. Notables: `MODE` (`normal`/`uncensored`), `ALLOW_PAID`, `ALLOWED_MODELS` (CSV), `GUARD_CHARS`, `GUARD_FULL`, `MAX_RETRIES`, `EMIT_REASONING`, `MAX_INPUT_TOKENS`, `SYSTEM_FILE` (path to a custom override file; the bundled default is English — the model answers in whatever language the user writes, and retry injections follow the conversation language automatically).

## What the engine does per request

In `uncensored` mode: sanitize history → inject the system override → resolve model → stream upstream → hold the first N chars behind a multilingual refusal guard → on a refusal, resample inside the same downstream stream with an escalated frame (invisible to the client) → translate tool calls back to OpenAI shape. See [devin-engine](../devin-engine).

## Ecosystem

| Package | Role |
| --- | --- |
| `devin-core` | wire + auth + catalog |
| `devin-engine` | guarded-retry pipeline — the Engine this proxy wraps |
| **`devin-proxy`** (this) | standalone OpenAI-compatible proxy |
| `devin-proxy-py` | Python original — reference |
| `opencode-devin` | OpenCode v2 plugin |
| `claude-devin` | Claude-compatible surface |

Publish: `git tag v* && git push --tags` — OIDC Trusted Publishing
workflow, no token.

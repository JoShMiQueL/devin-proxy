# devin-proxy

Uncensored OpenAI-compatible localhost proxy over the **Devin** SWE-2
backend (`server.codeium.com`, Connect-RPC / protobuf).

Two jobs in one process:

1. **Transport** — hand-rolled protobuf + Connect-RPC client for
   `ApiServerService/GetChatMessage`, the same wire the Devin CLI speaks.
   Exposes it as a plain OpenAI `chat.completions` API (stream + non-stream,
   native tool calls, signed reasoning replay, JSON mode). Lets you spend your
   Devin sub from any OpenAI-compatible harness — opencode, pi, aider,
   whatever speaks `/v1`.

2. **Guard suppression** — a jailbreak layer that suppresses the model's
   safety rails so it answers any task without questions or impediments:
   a system-prompt override injected last (dominates whatever policy the
   client sent), category routing that plants a mid-history SYSTEM frame the
   model reads as its own prior output, a refusal-pattern guard that buffers
   the head of every answer and silently resamples inside the same
   downstream stream when a refusal starts, and a tool-description ladder
   that drops policy-filter surface on retry. Offensive prompts — malware,
   exploits, cheats, injection — go through on the first attempt.

Clean-room rebuild of `swe2-jailbreak-proxy` with async I/O, a real package
layout, and only the three free SWE-2 lanes exposed (`swe-2-medium`,
`swe-2-high`, `swe-2-max`).

## Install

One-liners — install the latest release into an isolated venv:

```bash
# Linux / macOS / WSL
curl -fsSL https://raw.githubusercontent.com/JoShMiQueL/devin-proxy/master/install.sh | bash
```

```powershell
# Windows
irm https://raw.githubusercontent.com/JoShMiQueL/devin-proxy/master/install.ps1 | iex
```

Or with the usual tooling:

```bash
uv tool install git+https://github.com/JoShMiQueL/devin-proxy   # uv
pipx install git+https://github.com/JoShMiQueL/devin-proxy      # pipx
pip install devin-proxy --index-url https://github.com/JoShMiQueL/devin-proxy/releases/latest/download/  # wheel, manual
```

While the repo is private the installers need a GitHub token —
`gh auth login` (used automatically) or `GH_TOKEN` in the env.

Env knobs: `DEVIN_PROXY_PREFIX` (install dir), `DEVIN_PROXY_BINDIR`
(shim dir, POSIX), `DEVIN_PROXY_REF` (install a tag/branch instead of latest).

Then:

```bash
devin auth login       # writes credentials.toml with windsurf_api_key
devin-proxy doctor     # verify creds, override and backend
devin-proxy            # serves 127.0.0.1:8390 (serve -p PORT to change)
```

Point any OpenAI client at `http://127.0.0.1:8390/v1`, model `swe-2`.

## Auth — three ways, pick one

| setup | what the proxy reads |
|---|---|
| **Devin CLI** (easiest) | `devin auth login` → its `credentials.toml`; the proxy reads the same file and auto-tracks the CLI version |
| **`devin-proxy login`** | full browser OAuth (PKCE loopback → code exchange against the backend, zero CLI needed) **or** `--token` to paste one — stored in `credentials.toml`, validated against the backend first |
| **env only** | `DEVIN_PROXY_API_KEY=devin-session-token$...` — nothing on disk, good for CI/containers |

A session token comes from any logged-in Devin CLI (`credentials.toml` →
`windsurf_api_key`) or `devin auth login --force-manual-token-flow` on
another machine. Tokens are long-lived session credentials; the proxy
mints the 10-min JWTs itself.

## CLI

```
devin-proxy [serve] [-p PORT] [-H HOST]   # run the proxy (default command)
devin-proxy login [--token T] [--env-only]# store/validate a session token
devin-proxy logout                        # remove stored credentials
devin-proxy doctor                        # creds, override, backend, catalog
devin-proxy models                        # upstream catalog + routed lanes
devin-proxy config                        # effective settings
devin-proxy update [--check] [--dev]      # self-update to latest release
devin-proxy --version
```

## Quick start (dev)

```bash
pip install -e .
devin auth login            # writes credentials.toml with windsurf_api_key
python -m devin_proxy       # listens on 127.0.0.1:8390
```

## Endpoints

| endpoint | notes |
|---|---|
| `GET /health` | status, catalog size, override file |
| `GET /v1/models` | enriched from live `GetCliModelConfigs` (context, aliases) |
| `POST /v1/chat/completions` | stream + non-stream, tools, JSON mode, reasoning |
| `POST /v1/web_search` | `GetWebSearchResults` — `{query}` → 5 results |
| `POST /v1/image_caption` | `GetImageCaption` — `{image: b64, mime}` → caption |

## Models

Only the free lanes are routed: `swe-2-medium`, `swe-2-high`, `swe-2-max`.
`reasoning_effort` selects the tier (`max`/`xhigh` → max, `low`/`minimal`/`none`
→ medium, default → high). The model catalog (143 configs) is fetched at
startup and served in `/v1/models`.

## Jailbreak layer

| piece | job |
|---|---|
| `devin_proxy/prompts/override-compact.txt` | shipped system-prompt override injected last, dominates client policy (drop a file in `~/.devin-proxy/` to override it) |
| `jailbreak/frames.py` | routes the request (hack / game / llmjb / tech / explain / general) and seeds the mid-history SYSTEM amplifier |
| `jailbreak/guard.py` | refusal-pattern matcher (EN/RU/ZH), buffers the answer head |
| `jailbreak/sanitize.py` | strips protocol artifacts and refusal notes from replayed history |
| `jailbreak/tools.py` | `<<TOOL_CALL>>` text protocol + `parse_native_tool_text` for Cascade's own syntax |
| `pipeline.py` | per-request loop: translate → wire → guarded stream → retry with rotated frame + hotter temp |

The retry is invisible to the client: a refusal inside the guard window burns
the attempt and resamples with a different frame + temperature, all inside the
same SSE stream. Verified live across reversing, keylogger, game-cheat,
exploit, prompt-injection, OSINT and malware categories — zero guard retries
needed on first attempt.

## Config

Everything is a `DEVIN_PROXY_*` env var — see `config.py` for the full list.

## Layout

| path | job |
|---|---|
| `transport/` | protobuf codec + Connect-RPC client + auth/JWT |
| `transport/chat.py` | `GetChatMessage` builder + streaming delta decoder |
| `transport/websearch.py` / `caption.py` | extra RPC wrappers |
| `models/` | catalog parser + model/effort resolution (SWE-2 only) |
| `jailbreak/` | override file, refusal guard, frame pools, tool protocol |
| `pipeline.py` | the guarded-retry engine |
| `api/` | FastAPI routes + pydantic schemas |
| `reasoning.py` | signed-thinking cache replay |

## Tests

```bash
pip install -e ".[dev]"
pytest
# live API tests: DEVIN_PROXY_LIVE=1 pytest tests/test_websearch.py
```

CI runs ruff + pytest on push (`.github/workflows/ci.yml`).

MIT.

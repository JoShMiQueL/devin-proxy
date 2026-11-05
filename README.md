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
layout, and the six SWE-2 lanes exposed (`swe-2-medium`, `swe-2-high`,
`swe-2-max` + the `swe-2-flash-*` family).

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
devin-proxy models [--all]                # free lanes + expiry dates; --all dumps every upstream uid
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

Two SWE-2 families are routed — these are the only lanes that run free of
credit charge on the current plan (per the upstream catalog's credit field,
shown by `devin-proxy models`):

- **SWE-2** (base, 2.8T-A104B) — `swe-2-medium`, `swe-2-high`, `swe-2-max`.
  The flagship lane; ~60 tok/s, 6-12 credits/run.
- **SWE-2 Flash** (276B-A12B, released 2026-11-04) — `swe-2-flash-medium`,
  `swe-2-flash-high`, `swe-2-flash-max`. Cognition's fast/cheap tier:
  **3x the speed (~200 tok/s) at one-fifth the price** of SWE-2, free in
  Devin Desktop/CLI through 2026-11-30. Mid-trained on top of Thinking
  Machines' Inkling-Small + RL; beats every American open-weight model on
  their evals (FrontierCode 2.0: 24.0 vs SWE-2's 23.8) at ~10x smaller.
  Ideal for sub-agents and code-generation loops where latency matters.

Client-facing ids: `swe-2` (alias → `swe-2-high`), `swe-2-flash` (alias →
`swe-2-flash-high`), plus each explicit uid. `reasoning_effort` selects the
tier inside whichever family the model id picked (`max`/`xhigh` → max,
`low`/`minimal`/`none` → medium, default → high). Everything else in the
catalog — Claude/GPT/Gemini/Grok lanes and the `*-lightning` fast-mode
variants — bills real credits, so it stays unrouted by default.

**Opt-in paid routing** — set `DEVIN_PROXY_ALLOW_PAID=1` to route *any* uid
present in the live catalog: `model: "claude-opus-5-max"` goes through
verbatim and bills your Devin credits at the upstream rate (`devin-proxy
models` prints each lane's credit cost). `/v1/models` then exposes the full
catalog with `free_tier: false` + `credits_per_run` on the billed lanes so
clients can tell them apart. If the catalog fetch fails at startup the
allowlist still applies — paid routing needs the live catalog to validate
uids. If Cognition ships another free SWE lane, it appears in
`devin-proxy models --all` and routes via `DEVIN_PROXY_ALLOWED_MODELS`
without a code change.

The model catalog (~146 configs) is fetched at startup and served in
`/v1/models`; see every upstream uid with `devin-proxy models --all`.
Each entry shows its credit cost (`Ncredits`) and, when upstream advertises
one, the promo/free expiry date — `free-until=YYYY-MM-DD` on routed lanes,
`promo-until=` on billed ones (e.g. lightning's "83% off" ends 2027-01-01;
SWE-2 free lanes currently run through 2026-12-01, Flash through
2026-12-04).

## Jailbreak layer

| piece | job |
|---|---|
| `devin_proxy/prompts/override-compact.txt` | shipped default system-prompt override injected last, dominates client policy |
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

Everything is a `DEVIN_PROXY_*` env var — see `config.py` for the full
list. Highlights:

| var | default | effect |
|---|---|---|
| `DEVIN_PROXY_ALLOWED_MODELS` | the 6 free lanes | comma-separated uid allowlist |
| `DEVIN_PROXY_ALLOW_PAID` | off | route any catalog uid — **bills Devin credits** |
| `DEVIN_PROXY_DEFAULT_MODEL` | `swe-2-high` | lane for `model: swe-2` / unknown ids |
| `DEVIN_PROXY_GUARD_FULL` | off | buffer whole response for the comply-then-pivot scan |
| `DEVIN_PROXY_PORT` / `HOST` | 8390 / 127.0.0.1 | bind address |

**System-prompt override resolution** — first existing file wins:

1. `DEVIN_PROXY_SYSTEM_FILE` env var (explicit path)
2. `~/.devin-proxy/override-compact.txt` → `override.txt` →
   `system_override.txt` (your personal overrides, never shipped)
3. `devin_proxy/prompts/override-compact.txt` (packaged default)

Hot-reloaded on mtime — drop a file in `~/.devin-proxy/` and it takes
effect on the next request. `devin-proxy doctor` prints the resolved path.

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

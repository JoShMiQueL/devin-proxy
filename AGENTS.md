# AGENTS.md — devin-proxy project rules

OpenAI-compatible localhost proxy over the Devin SWE-2 backend
(`server.codeium.com`, Connect-RPC/protobuf). Async FastAPI; guard suppression:
system-override injection + refusal guard with temperature-ladder retries.
Only the free SWE-2 lanes are routed: `swe-2-medium`, `swe-2-high`, `swe-2-max`.

## Layout

```
devin_proxy/            <- THE package (flat layout, at repo root)
├── __init__.py         <- __version__ — single source of truth
├── __main__.py         <- python -m devin_proxy -> cli:main
├── cli.py              <- argparse: serve (default) / doctor / models / config / update
├── server.py           <- uvicorn bootstrap (serve())
├── pipeline.py         <- guarded-retry engine, tool-call delivery
├── translate.py        <- OpenAI <-> wire message translation
├── reasoning.py        <- reasoning replay across turns
├── config.py           <- Settings (all knobs are DEVIN_PROXY_* env vars)
├── api/                <- FastAPI routes + schemas
├── jailbreak/          <- override loading, guard, sanitize, tool rendering
├── models/             <- live catalog fetch + tier resolution
└── transport/          <- Connect-RPC wire, auth/JWT, proto codec, chat/websearch/caption
tests/                  <- pytest, imports devin_proxy.*
scripts/                <- dev tooling: run.cmd/sh, devin.cmd/sh, bump.py,
                           changelog.py, regen_changelog.py
devin_proxy/prompts/    <- shipped default override (override-compact.txt)
.github/workflows/
├── ci.yml              <- ruff + pytest on windows-latest + ubuntu-latest
└── release.yml         <- tag push OR workflow_dispatch -> build + GitHub release
```

## Hard rules

- **Never commit credentials or personal overrides.** `devin_proxy/prompts/`
  ships the product default `override-compact.txt` (generic, no personas).
  User overrides resolve first from `~/.devin-proxy/` (order:
  `override-compact.txt` > `override.txt` > `system_override.txt`);
  `DEVIN_PROXY_SYSTEM_FILE` beats everything. Credentials come from the Devin
  CLI's own `credentials.toml` (see `transport/auth.py` search order).
- **No personal strings in code, prompts, commits, or docs** — no real names,
  handles, personas, or machine paths. The repo is headed for public.
- **Conventional commits**, author `JoShMiQueL <joshmiquel.cs@gmail.com>`.
- **CHANGELOG.md is generated** by `scripts/changelog.py` from conventional
  commits — never hand-edit version sections.
- Python 3.11+ target; ruff clean (`ruff check devin_proxy tests`) and
  `pytest -q` green before every push. Stdlib-only in `scripts/`.
- Internal imports are relative (`from .x`, `from ..x`); tests import
  `devin_proxy.*` — never `src.*`.
- Commits to `master`; PRs only for large changes.

## Dev commands

```
pip install -e ".[dev]"
lefthook install                            # once — wires git hooks
ruff check devin_proxy tests
pytest -q                                   # all (unit + live w/ creds)
pytest -q -m "not live"                     # unit only — CI-safe
python -m devin_proxy [serve] [-p PORT]     # run the proxy
python -m devin_proxy doctor                # creds + backend + override check
scripts/run.cmd | scripts/run.sh            # dev launchers (port 8390)
```

Pre-commit hook (lefthook.yml): ruff --fix staged + unit tests. Pre-push:
full unit suite + lint. Live tests (`tests/test_live.py`, mark `live`)
only run when `DEVIN_PROXY_API_KEY` or a credentials.toml exists — CI
runs them on push when the repo secret is set.

The repo `.venv` is the dev env (`-e` editable). A stable, non-editable install
for daily use lives outside the repo (see scripts/devin.cmd) — they must not
share a venv.

## Release flow — two ways

**Autonomous (preferred):** Actions -> `release` workflow -> Run workflow ->
`kind: suggest|patch|minor|major`. The `cut` job bumps `__version__` +
`pyproject.toml`, regenerates the CHANGELOG section, commits `release: X.Y.Z`,
tags `vX.Y.Z`, and pushes; the tag push triggers `gate` (lint+tests) and
`release` (build wheel+sdist, generate notes, publish GitHub release).

**Manual:** `python scripts/bump.py [patch|minor|major] --push`.

- `kind` defaults to `suggest` — `changelog.py` infers patch/minor/major from
  conventional commits since the last tag (`feat` -> minor, `!`/`BREAKING
  CHANGE` -> major, else patch). `docs`/`ci`/`chore`/`test` commits alone never
  warrant a release, but they DO appear in the next release's notes.
- `release:` commits are bookkeeping — filtered out of changelog/notes.
- Release notes are release-please style: `[version](compare-link)` heading,
  linked commit shas, `#N` -> PR links, `[@user]` contributors and
  first-contribution detection (via `gh api`).
- `release.yml` asserts tag == `__version__` and that CHANGELOG has the
  section — it will fail fast if either is missing.
- **`secrets.RELEASE_TOKEN` must exist** (a PAT): pushes made with the default
  `GITHUB_TOKEN` cannot re-trigger workflows, so a dispatch-created tag would
  silently never build.
- `devin-proxy update` installs the newest release wheel; `update --check`
  reports; `update --dev` installs master. Release-asset API calls use
  `GH_TOKEN`/`GITHUB_TOKEN`/`gh auth token` while the repo is private.

## CI notes

- `ci.yml`: `pip install -e ".[dev]"`, `ruff check devin_proxy tests`,
  `pytest -q` on windows-latest + ubuntu-latest x py3.11/3.13. **No macos
  runners** — they starve the free-tier queue; the code stays cross-platform
  via tests, not via CI runners.
- `release.yml` needs `fetch-depth: 0` wherever changelog/git history is used.
- `gh release create` flags go on separate lines inside `run: |` blocks —
  a trailing `\` line-continuation swallowed the flags once already.

## Devin CLI drift

The wire fingerprint (`client_version`/`client_channel` in the request
metadata) **tracks the installed `devin` CLI automatically** —
`transport/devincli.py` shells `devin version` once per `load_settings()`
call and falls back to `FALLBACK_VERSION` when no CLI is on PATH. Pin with
`DEVIN_PROXY_CLIENT_VERSION` env or `Settings(client_version=...)`.
`devin-proxy doctor` shows the resolved fingerprint and its source. If the
backend ever hard-rejects old client versions, check `devin version` first
— the proxy is only as fresh as the installed CLI.

## Auth without the CLI

The session token is all the proxy needs — credential resolution order:
`DEVIN_PROXY_API_KEY` env > `credentials.toml` (CLI-format search paths).
`devin-proxy login` does the full browser PKCE flow itself
(`transport/oauth.py`): opens `{webapp}/auth/cli/continue` with the same
query params the CLI sends, captures the loopback redirect, then exchanges
code+verifier via `SeatManagementService/ExchangeDevinCLIPKCECode` on the
Connect-RPC backend. `--token`/`--token-only` paste a token instead;
`logout` removes credentials.toml. The exchange request layout
(metadata@1, code@2, verifier@3, redirect_uri@4) is verified against
the backend's protobuf unmarshal errors — if it ever drifts, probe with a
malformed body and read the field number out of the `invalid_argument`
message.

## Wire facts (don't rediscover)

- `GetChatMessage` = `application/connect+proto` + gzip envelope; other RPCs
  are `application/proto`.
- Tool defs ride field 10 (`ChatToolDefinition`: 1=name, 2=desc, 3=schema-json,
  12=strict). The model answers with field 6 `deltaToolCalls` (id/name once,
  then `argumentsJson` fragments). `tool_choice`: field 12 -> `f_str(2, fname)`
  for function, `f_str(1, "auto")` for auto.
- Catalog prefetch = `GetCliModelConfigs` (~140 configs upstream).
- `/health` and `/v1/models` are public endpoints; `/v1/chat/completions`,
  `/v1/web_search`, `/v1/image_caption` go through the engine.

## ROADMAP.md

Live status doc — update the checkboxes and status log when a workstream
item lands; it is the source of truth for "where are we".

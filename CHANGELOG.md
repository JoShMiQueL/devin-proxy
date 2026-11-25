# Changelog

## [0.2.1](https://github.com/JoShMiQueL/devin-proxy/compare/v0.2.0...v0.2.1) (2026-11-25)


### Features

* catalog-driven model exposure and resolution — every subscription family routable through the live catalog, one /v1/models entry per family with effort lanes, credits and aliases; empty allowlist means everything; legacy tier table only as prefetch fallback ([#2](https://github.com/JoShMiQueL/devin-proxy/issues/2)) ([187a6c0](https://github.com/JoShMiQueL/devin-proxy/commit/187a6c08ef6924a07c9ad5e5f0bfb47faac9bfe0))

## [0.2.0] — 2026-11-24

### Added
- `mode` setting — `"normal"` (default) vanilla passthrough vs
  `"uncensored"` full pipeline. Toggle via `--mode`,
  `DEVIN_PROXY_MODE`, or `settings.toml`. `/health` reports the mode.
- `/v1/image_caption` + `/v1/web_search` — full parity with the Python
  proxy (GetImageCaption / GetWebSearchResults RPCs).
- Bumps `devin-engine` to `^0.0.4`.

## [0.1.1] — 2026-11-24

### Fixed
- `version` command — `package.json` isn't in `dist/`, so the import
  failed; version is now a build constant.

## [0.1.0] — 2026-11-24

### Added
- Initial release — TypeScript port of the Python `devin-proxy`
  (now `devin-proxy-py`) over `devin-core` + `devin-engine`.
  `POST /v1/chat/completions` (SSE + unary), `/v1/models`, `/health`,
  `serve`/`login`/`version` CLI, TOML settings, catalog via
  `GetCliModelConfigs`.

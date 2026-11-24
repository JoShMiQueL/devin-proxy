# Changelog

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

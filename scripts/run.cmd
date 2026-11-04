@echo off
rem devin-proxy - Windows dev launcher (runs the repo checkout in editable mode)
setlocal
set DEVIN_PROXY_HOST=127.0.0.1
set DEVIN_PROXY_PORT=8390
rem set DEVIN_PROXY_SYSTEM_FILE=%~dp0..\prompts\override-compact.txt
rem set DEVIN_PROXY_CRED=%APPDATA%\devin\credentials.toml
cd /d %~dp0..
python -m devin_proxy %*

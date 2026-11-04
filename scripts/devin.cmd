@echo off
rem devin-proxy launcher — stable copy in %USERPROFILE%\venvs\devin-proxy
rem Usage: devin.cmd [PORT] [--install]
rem   devin.cmd            -> starts on 127.0.0.1:8390
rem   devin.cmd 8400       -> starts on 127.0.0.1:8400
rem   devin.cmd --install  -> (re)builds the stable copy from this repo
setlocal EnableDelayedExpansion

set "REPO=%~dp0.."
set "VENV=%USERPROFILE%\venvs\devin-proxy"
set "PORT=8390"

if /i "%~1"=="--install" goto install
if /i "%~1"=="--update"  goto install
if not "%~1"=="" set "PORT=%~1"

if not exist "%VENV%\Scripts\python.exe" (
    echo [devin] stable venv missing, building from %REPO% ...
    goto install
)

set "DEVIN_PROXY_HOST=127.0.0.1"
set "DEVIN_PROXY_PORT=%PORT%"
echo [devin] starting on 127.0.0.1:%PORT% (venv: %VENV%)
"%VENV%\Scripts\python.exe" -m devin_proxy %*
goto :eof

:install
echo [devin] creating %VENV% ...
if not exist "%VENV%" (
    python -m venv "%VENV%" || (echo [devin] venv failed & exit /b 1)
)
echo [devin] installing stable copy ...
"%VENV%\Scripts\python.exe" -m pip install -q --upgrade pip
"%VENV%\Scripts\python.exe" -m pip install -q --force-reinstall --no-deps "%REPO%"
"%VENV%\Scripts\python.exe" -m pip install -q "fastapi>=0.128" "uvicorn[standard]>=0.40" "httpx[http2]>=0.28" "pydantic>=2.13" "pydantic-settings>=2.12" "sse-starlette>=3.3" "anyio>=4.12"
echo [devin] done. Run: devin.cmd [PORT]

# devin-proxy installer — Windows
#   irm https://raw.githubusercontent.com/JoShMiQueL/devin-proxy/master/install.ps1 | iex
# Env knobs: DEVIN_PROXY_PREFIX, DEVIN_PROXY_REF (default: latest release)
$ErrorActionPreference = 'Stop'
$repo   = 'JoShMiQueL/devin-proxy'
$prefix = if ($env:DEVIN_PROXY_PREFIX) { $env:DEVIN_PROXY_PREFIX } else { "$env:LOCALAPPDATA\devin-proxy" }
$bindir = "$prefix\bin"
$ref    = $env:DEVIN_PROXY_REF

function Say($m) { Write-Host "[devin-proxy] $m" }

# --- auth (needed while the repo is private) ---
$headers = @{ 'User-Agent' = 'devin-proxy-installer' }
$token = if ($env:GH_TOKEN) { $env:GH_TOKEN } elseif ($env:GITHUB_TOKEN) { $env:GITHUB_TOKEN } else {
    try { (gh auth token 2>$null) } catch { $null }
}
if ($token) { $headers['Authorization'] = "Bearer $token" }

# --- python ---
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw 'python not found on PATH (need >= 3.11)' }
& python -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>$null
if ($LASTEXITCODE) { throw 'python >= 3.11 required' }

# --- resolve ---
$tmp = Join-Path $env:TEMP ("devinproxy-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    if (-not $ref) {
        Say 'resolving latest release...'
        $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest" -Headers $headers
        $tag = $rel.tag_name
        $wheel = ($rel.assets | Where-Object { $_.name -like '*.whl' } | Select-Object -First 1).browser_download_url
        if (-not $wheel) { throw "no wheel asset on release $tag" }
        $whl = Join-Path $tmp 'pkg.whl'
        # asset URLs redirect to signed storage — gh downloads with auth cleanly,
        # Invoke-WebRequest often dies on the redirect chain
        if (Get-Command gh -ErrorAction SilentlyContinue) {
            $assetName = ($rel.assets | Where-Object { $_.name -like '*.whl' } | Select-Object -First 1).name
            gh release download $tag --repo $repo --pattern $assetName --dir $tmp --clobber
            $whl = Join-Path $tmp $assetName
        } else {
            Invoke-WebRequest -Uri $wheel -Headers $headers -OutFile $whl -UseBasicParsing
        }
        $pkg = $whl
    } else {
        $tag = $ref
        $pkg = "git+https://github.com/$repo@$ref"
    }

    # --- install ---
    Say "installing $tag -> $prefix"
    $venv = "$prefix\venv"
    if (-not (Test-Path "$venv\Scripts\python.exe")) { python -m venv $venv }
    & "$venv\Scripts\python.exe" -m pip install -q --upgrade pip
    & "$venv\Scripts\python.exe" -m pip install -q --force-reinstall $pkg
    if ($LASTEXITCODE) { throw 'pip install failed' }

    # --- shim on PATH ---
    New-Item -ItemType Directory -Path $bindir -Force | Out-Null
    $cmd = Join-Path $bindir 'devin-proxy.cmd'
    Set-Content $cmd "@echo off`n`"$venv\Scripts\python.exe`" -m devin_proxy %*"
    $upath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($upath -notlike "*$bindir*") {
        [Environment]::SetEnvironmentVariable('Path', "$upath;$bindir", 'User')
        $env:Path = "$env:Path;$bindir"
        Say "added $bindir to user PATH (reopen shells)"
    }

    Say "done: $(& $venv\Scripts\python.exe -m devin_proxy --version)"
    Say 'run: devin-proxy doctor'
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

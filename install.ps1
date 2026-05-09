# ═══════════════════════════════════════════════════════════════
# Biosensor MCP — One-Click Installer (Windows)
# Usage: irm https://raw.githubusercontent.com/saahasmuthineni/biosensor-to-llm-middleware/main/install.ps1 | iex
# ═══════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"

$policy = Get-ExecutionPolicy
if ($policy -eq "Restricted" -or $policy -eq "AllSigned") {
    Write-Host "  PowerShell execution policy ($policy) blocks this script." -ForegroundColor Red
    Write-Host "  Run once: Set-ExecutionPolicy RemoteSigned -Scope CurrentUser" -ForegroundColor Cyan
    exit 1
}

$REPO = "saahasmuthineni/biosensor-to-llm-middleware"

$INSTALL_DIR = Join-Path $env:USERPROFILE ".tailor"
$VENV_DIR = Join-Path $INSTALL_DIR "venv"
$SRC_DIR = Join-Path $INSTALL_DIR "src"

Write-Host ""
Write-Host "  Biosensor MCP - Installer v6.0" -ForegroundColor Cyan
Write-Host "  ================================" -ForegroundColor Cyan
Write-Host ""

# --- Check Python ---
$PYTHON = $null
foreach ($cmd in @("python3", "python", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            if ([int]$Matches[1] -ge 10) {
                $PYTHON = $cmd
                Write-Host "  Python found: $ver" -ForegroundColor Green
                break
            }
        }
    } catch {}
}

if (-not $PYTHON) {
    Write-Host "  Python 3.10+ not found." -ForegroundColor Red
    Write-Host "  Install from: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# --- Backup ---
if (Test-Path $INSTALL_DIR) {
    $backup = "$INSTALL_DIR.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Write-Host "  Backing up existing installation..." -ForegroundColor Yellow
    Copy-Item -Path $INSTALL_DIR -Destination $backup -Recurse
}

New-Item -ItemType Directory -Force -Path $INSTALL_DIR, "$INSTALL_DIR\data", "$INSTALL_DIR\logs" | Out-Null

# --- Download ---
Write-Host "  Downloading latest source..." -ForegroundColor Cyan
$zipUrl = "https://github.com/$REPO/archive/main.zip"
$zipPath = Join-Path $env:TEMP "tailor.zip"
$extractPath = Join-Path $env:TEMP "tailor-extract"

Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
if (Test-Path $extractPath) { Remove-Item $extractPath -Recurse -Force }
Expand-Archive -Path $zipPath -DestinationPath $extractPath
if (Test-Path $SRC_DIR) { Remove-Item $SRC_DIR -Recurse -Force }
Move-Item -Path (Join-Path $extractPath "biosensor-to-llm-middleware-main") -Destination $SRC_DIR
Remove-Item $zipPath -Force
Remove-Item $extractPath -Recurse -Force
Write-Host "  Source downloaded" -ForegroundColor Green

# --- Venv ---
Write-Host "  Setting up Python environment..." -ForegroundColor Cyan
& $PYTHON -m venv $VENV_DIR
$venvPython = Join-Path $VENV_DIR "Scripts\python.exe"
$venvPip = Join-Path $VENV_DIR "Scripts\pip.exe"
& $venvPip install --quiet --upgrade pip
& $venvPip install --quiet $SRC_DIR
Write-Host "  Dependencies installed" -ForegroundColor Green

# --- OAuth ---
$tokenFile = Join-Path $INSTALL_DIR "tokens.json"
if (-not (Test-Path $tokenFile)) {
    Write-Host ""
    Write-Host "  Strava OAuth Setup" -ForegroundColor Cyan
    Write-Host "  1. Go to https://www.strava.com/settings/api"
    Write-Host "  2. Create an app ('localhost' as callback)"
    Write-Host "  3. Note your Client ID and Client Secret"
    Write-Host ""
    & $venvPython -m tailor setup
} else {
    Write-Host "  Existing tokens found" -ForegroundColor Green
}

# --- Claude Desktop (handles both standard and Windows Store paths) ---
Write-Host "  Registering with Claude Desktop..." -ForegroundColor Cyan

$configPaths = @((Join-Path $env:APPDATA "Claude\claude_desktop_config.json"))
$storePaths = Get-ChildItem -Path "$env:LOCALAPPDATA\Packages" -Filter "AnthropicPBC.Claude*" -Directory -ErrorAction SilentlyContinue
foreach ($sp in $storePaths) {
    $configPaths += Join-Path $sp.FullName "LocalCache\Roaming\Claude\claude_desktop_config.json"
}

$claudeConfig = $null
foreach ($cp in $configPaths) {
    if (Test-Path $cp) { $claudeConfig = $cp; break }
}
if (-not $claudeConfig) { $claudeConfig = $configPaths[0] }

$claudeDir = Split-Path $claudeConfig
if (-not (Test-Path $claudeDir)) { New-Item -ItemType Directory -Force -Path $claudeDir | Out-Null }

$mcpEntry = @{
    command = $venvPython
    args = @("-m", "tailor", "serve")
    env = @{
        TAILOR_CONFIG_DIR = $INSTALL_DIR
        TAILOR_DATA_DIR = "$INSTALL_DIR\data"
    }
}

if (Test-Path $claudeConfig) {
    Copy-Item $claudeConfig "$claudeConfig.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    $raw = [System.IO.File]::ReadAllText($claudeConfig, [System.Text.Encoding]::UTF8)
    $config = $raw | ConvertFrom-Json
    if (-not $config.mcpServers) {
        $config | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue @{}
    }
    $config.mcpServers | Add-Member -NotePropertyName "tailor" -NotePropertyValue $mcpEntry -Force
} else {
    $config = @{ mcpServers = @{ "tailor" = $mcpEntry } }
}

$config | ConvertTo-Json -Depth 10 | Set-Content $claudeConfig -Encoding UTF8
Write-Host "  Claude Desktop config updated" -ForegroundColor Green

Write-Host ""
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:"
Write-Host "    1. Restart Claude Desktop"
Write-Host "    2. Ask Claude: 'Sync my Strava data and analyze my last run'"
Write-Host ""

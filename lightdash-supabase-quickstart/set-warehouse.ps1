#Requires -Version 5.1
$ErrorActionPreference = 'Stop'

# Sets the warehouse connection credentials on an existing Lightdash project
# via the API -- no UI required.
#
# Prerequisites:
#   - lightdash deploy --create has been run (project exists)
#   - .env exists with DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME, DB_SSL_MODE

function Write-Info    { param([string]$Msg) Write-Host "[>] $Msg" -ForegroundColor Cyan }
function Write-Success { param([string]$Msg) Write-Host "[+] $Msg" -ForegroundColor Green }
function Write-Warn    { param([string]$Msg) Write-Host "[!] $Msg" -ForegroundColor Yellow }
function Write-Die     { param([string]$Msg) Write-Host "[x] $Msg" -ForegroundColor Red; exit 1 }

$LIGHTDASH_URL = "https://app.lightdash.cloud"

Write-Host ""
Write-Host "Set Lightdash Warehouse Connection" -ForegroundColor White
Write-Host "========================================="
Write-Host ""

# ── load .env ─────────────────────────────────────────────────────────────────
$DB_HOST  = ""
$DB_PORT  = ""
$DB_USER  = ""
$DB_PASS  = ""
$DB_NAME  = ""
$SSL_MODE = ""

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
            $key   = $Matches[1].Trim()
            $value = $Matches[2].Trim().Trim('"').Trim("'")
            switch ($key) {
                'DB_HOST'    { $DB_HOST  = $value }
                'DB_PORT'    { $DB_PORT  = $value }
                'DB_USER'    { $DB_USER  = $value }
                'DB_PASS'    { $DB_PASS  = $value }
                'DB_NAME'    { $DB_NAME  = $value }
                'DB_SSL_MODE'{ $SSL_MODE = $value }
            }
        }
    }
    Write-Success ".env loaded"
} else {
    Write-Warn ".env not found — enter values manually below."
}

# ── prompt for any missing DB values ──────────────────────────────────────────
if ([string]::IsNullOrWhiteSpace($DB_HOST)) { $DB_HOST = Read-Host "  DB Host (e.g. aws-0-eu-west-1.pooler.supabase.com)" }
if ([string]::IsNullOrWhiteSpace($DB_PORT)) { $DB_PORT = Read-Host "  DB Port [5432]"; if (-not $DB_PORT) { $DB_PORT = "5432" } }
if ([string]::IsNullOrWhiteSpace($DB_USER)) { $DB_USER = Read-Host "  DB User (e.g. postgres.xxxxxxxxxxxx)" }
if ([string]::IsNullOrWhiteSpace($DB_PASS)) {
    $secPass  = Read-Host "  DB Password" -AsSecureString
    $DB_PASS  = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secPass))
}
if ([string]::IsNullOrWhiteSpace($DB_NAME)) { $DB_NAME = "postgres" }
if ([string]::IsNullOrWhiteSpace($SSL_MODE)) { $SSL_MODE = "no-verify" }

Write-Host ""

# ── project UUID ──────────────────────────────────────────────────────────────
Write-Info "Lightdash project UUID"

$PROJECT_UUID = $env:LIGHTDASH_PROJECT

if ([string]::IsNullOrWhiteSpace($PROJECT_UUID)) {
    Write-Host "  Find it in your Lightdash URL:"
    Write-Host "  $LIGHTDASH_URL/projects/YOUR-UUID/tables"
    Write-Host ""
    $PROJECT_UUID = Read-Host "  Paste project UUID"
    if ([string]::IsNullOrWhiteSpace($PROJECT_UUID)) { Write-Die "Project UUID required." }
}

Write-Success "Project UUID: $PROJECT_UUID"
Write-Host ""

# ── auth token ────────────────────────────────────────────────────────────────
Write-Info "Lightdash personal access token"

$LIGHTDASH_TOKEN = $env:LIGHTDASH_API_KEY

# Try config.yaml written by 'lightdash login'
if ([string]::IsNullOrWhiteSpace($LIGHTDASH_TOKEN)) {
    $configCandidates = @(
        (Join-Path $HOME ".config\lightdash\config.yaml"),
        (Join-Path $env:APPDATA "lightdash\config.yaml")
    )
    foreach ($cliCfg in $configCandidates) {
        if (Test-Path $cliCfg) {
            $yamlContent = Get-Content $cliCfg -Raw
            if ($yamlContent -match '(?m)^\s*apiKey:\s*"?([^"\s]+)"?') {
                $LIGHTDASH_TOKEN = $Matches[1]
                Write-Success "Token found in $cliCfg"
                break
            }
        }
    }
}

# Try JSON config (older CLI)
if ([string]::IsNullOrWhiteSpace($LIGHTDASH_TOKEN)) {
    $configPaths = @(
        (Join-Path $HOME ".config\lightdash-cli\config.json"),
        (Join-Path $env:APPDATA "lightdash-cli\config.json")
    )
    foreach ($cfg in $configPaths) {
        if (Test-Path $cfg) {
            $jsonContent = Get-Content $cfg -Raw
            if ($jsonContent -match '"(?:token|apiKey)"\s*:\s*"([^"]+)"') {
                $LIGHTDASH_TOKEN = $Matches[1]
                Write-Success "Token found in $cfg"
                break
            }
        }
    }
}

if ([string]::IsNullOrWhiteSpace($LIGHTDASH_TOKEN)) {
    Write-Warn "No token found automatically."
    Write-Host "  Create one at: $LIGHTDASH_URL/settings/personal-access-tokens"
    Write-Host ""
    $LIGHTDASH_TOKEN = Read-Host "  Paste token"
    if ([string]::IsNullOrWhiteSpace($LIGHTDASH_TOKEN)) { Write-Die "Token required." }
}

Write-Host ""

# ── api call ──────────────────────────────────────────────────────────────────
Write-Info "Setting warehouse credentials on project $PROJECT_UUID..."
Write-Host "  Host:    ${DB_HOST}:${DB_PORT}"
Write-Host "  DB:      $DB_NAME"
Write-Host "  User:    $DB_USER"
Write-Host "  SSL:     $SSL_MODE"
Write-Host ""

$body = @{
    warehouseConnection = @{
        type     = "postgres"
        host     = $DB_HOST
        user     = $DB_USER
        password = $DB_PASS
        port     = [int]$DB_PORT
        dbname   = $DB_NAME
        schema   = "public"
        sslmode  = $SSL_MODE
    }
} | ConvertTo-Json -Depth 3

$headers = @{
    "Authorization" = "ApiKey $LIGHTDASH_TOKEN"
    "Content-Type"  = "application/json"
}

try {
    $response = Invoke-RestMethod `
        -Uri "$LIGHTDASH_URL/api/v1/projects/$PROJECT_UUID/warehouse-credentials" `
        -Method Put `
        -Headers $headers `
        -Body $body `
        -TimeoutSec 30

    if ($response.status -eq "ok") {
        Write-Success "Done! Warehouse credentials set."
        Write-Host ""
        Write-Host "  Open your project: $LIGHTDASH_URL/projects/$PROJECT_UUID/tables"
    } else {
        throw "Unexpected response status: $($response.status)"
    }
} catch {
    $errMsg = $_.Exception.Message
    $statusCode = ""
    if ($_.Exception.Response) {
        $statusCode = [int]$_.Exception.Response.StatusCode
    }

    Write-Host ""
    if ($statusCode) {
        Write-Warn "API returned HTTP $statusCode."
    } else {
        Write-Warn "API request failed: $errMsg"
    }
    Write-Host ""
    Write-Host "  Common causes:"
    Write-Host "    401 - token is wrong or expired (regenerate at /settings/personal-access-tokens)"
    Write-Host "    403 - token does not have project admin permissions"
    Write-Host "    404 - project UUID is wrong"
    Write-Host ""
    Write-Host "  Set credentials manually instead:"
    Write-Host "  Lightdash > gear > Project Settings > warehouse connection form"
    Write-Host "    Host:     $DB_HOST"
    Write-Host "    Port:     $DB_PORT"
    Write-Host "    Database: $DB_NAME"
    Write-Host "    User:     $DB_USER"
    Write-Host "    Password: (from .env)"
    Write-Host "    Advanced > SSL mode: $SSL_MODE"
    Write-Host ""
    Write-Host "  Note: use the Session Pooler host from Supabase > Connect"
    Write-Host "  NOT the Direct connection host (db.xxxx.supabase.co)"
    exit 1
}

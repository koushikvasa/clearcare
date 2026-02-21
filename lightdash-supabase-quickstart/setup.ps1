#Requires -Version 5.1
$ErrorActionPreference = 'Stop'

function Write-Info    { param([string]$Msg) Write-Host "[>] $Msg" -ForegroundColor Cyan }
function Write-Success { param([string]$Msg) Write-Host "[+] $Msg" -ForegroundColor Green }
function Write-Warn    { param([string]$Msg) Write-Host "[!] $Msg" -ForegroundColor Yellow }
function Write-Die     { param([string]$Msg) Write-Host "[x] $Msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "Lightdash Bare Starter - Setup" -ForegroundColor White
Write-Host "========================================="
Write-Host ""

# -- credentials ---------------------------------------------------------------
Write-Info "Supabase connection details"
Write-Host "  Supabase > Connect > Connection String tab"
Write-Host "  > Method dropdown > 'Session Pooler' > View parameters"
Write-Host "  [!] Do NOT use 'Direct connection'"
Write-Host ""

$DB_HOST = Read-Host "  Host   (e.g. aws-1-eu-west-1.pooler.supabase.com)"
$DB_PORT = Read-Host "  Port   [5432]"
if ([string]::IsNullOrWhiteSpace($DB_PORT)) { $DB_PORT = "5432" }
$DB_USER = Read-Host "  User   (e.g. postgres.xxxxxxxxxxxx)"
$DB_PASS_SECURE = Read-Host "  Password" -AsSecureString
$DB_PASS = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DB_PASS_SECURE)
)

$DB_NAME   = "postgres"
$SSL_MODE  = "no-verify"

# -- write .env ----------------------------------------------------------------
@"
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASS=$DB_PASS
DB_SSL_MODE=$SSL_MODE
"@ | Set-Content -Path ".env" -Encoding UTF8 -NoNewline

Write-Success ".env written (gitignored)"
Write-Host ""

# -- connection test ------------------------------------------------------------
$psqlPath = Get-Command psql -ErrorAction SilentlyContinue
if (-not $psqlPath) {
    Write-Warn "psql not found - skipping connection test"
    Write-Warn "Install: https://www.postgresql.org/download/windows/ or  winget install PostgreSQL.PostgreSQL"
    Write-Host ""
    Write-Host "Next: lightdash lint; lightdash deploy --create --no-warehouse-credentials"
    exit 0
}

Write-Info "Testing connection to ${DB_HOST}:${DB_PORT}..."

$env:PGPASSWORD = $DB_PASS
try {
    $null = & psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME `
        --set=sslmode=require -c "SELECT 1;" -q --no-psqlrc 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "psql returned exit code $LASTEXITCODE"
    }
    Write-Success "Connection OK"
} catch {
    Write-Die (
        "Could not connect.`n" +
        "  Check:`n" +
        "    - Password: reset it in Supabase > Database Settings if unsure`n" +
        "    - Host: must be the Session Pooler host, not db.xxxx.supabase.co`n" +
        "    - Port: 5432 for Session Pooler, 6543 for Transaction Pooler"
    )
} finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "========================================="
Write-Host "Next steps" -ForegroundColor White
Write-Host ""
Write-Host "  1. Generate models (Cursor / Claude Code / Codex):"
Write-Host "     Ask AI: 'Look at my Supabase tables and generate Lightdash models'"
Write-Host ""
Write-Host "  2. Deploy:"
Write-Host "     lightdash lint"
Write-Host "     lightdash deploy --create 'My Project' --no-warehouse-credentials"
Write-Host ""
Write-Host "  3. Set warehouse credentials:"
Write-Host "     Once your project is created, run this to connect it to your warehouse:"
Write-Host "     powershell ./set-warehouse.ps1"
Write-Host ""

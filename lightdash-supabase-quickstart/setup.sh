#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}▶ $*${RESET}"; }
success() { echo -e "${GREEN}✓ $*${RESET}"; }
warn()    { echo -e "${YELLOW}⚠ $*${RESET}"; }
die()     { echo -e "${RED}✗ $*${RESET}" >&2; exit 1; }

echo ""
echo -e "${BOLD}Lightdash Bare Starter — Setup${RESET}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── credentials ───────────────────────────────────────────────────────────────
info "Supabase connection details"
echo "  Supabase → Connect → Connection String tab"
echo "  → Method dropdown → 'Session Pooler' → View parameters"
echo "  ⚠ Do NOT use 'Direct connection'"
echo ""

read -rp  "  Host   (e.g. aws-1-eu-west-1.pooler.supabase.com): " DB_HOST
read -rp  "  Port   [5432]: " DB_PORT;   DB_PORT="${DB_PORT:-5432}"
read -rp  "  User   (e.g. postgres.xxxxxxxxxxxx): " DB_USER
read -rsp "  Password: " DB_PASS; echo ""

DB_NAME="postgres"
SSL_MODE="no-verify"

# ── write .env ────────────────────────────────────────────────────────────────
cat > .env <<EOF
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASS=${DB_PASS}
DB_SSL_MODE=${SSL_MODE}
EOF

success ".env written (gitignored)"
echo ""

# ── connection test ───────────────────────────────────────────────────────────
if ! command -v psql &>/dev/null; then
  warn "psql not found — skipping connection test"
  warn "Install: brew install libpq && brew link --force libpq"
  echo ""
  echo "Next: lightdash lint && lightdash deploy --create --no-warehouse-credentials"
  exit 0
fi

info "Testing connection to ${DB_HOST}:${DB_PORT}..."

PGPASSWORD="${DB_PASS}" \
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
       --set=sslmode=require \
       -c "SELECT 1;" -q --no-psqlrc &>/dev/null \
  && success "Connection OK" \
  || die "Could not connect.
  Check:
    • Password — reset it in Supabase → Database Settings if unsure
    • Host — must be the Session Pooler host, not db.xxxx.supabase.co
    • Port — 5432 for Session Pooler, 6543 for Transaction Pooler"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BOLD}Next steps${RESET}"
echo ""
echo "  1. Generate models (Cursor / Claude Code / Codex):"
echo "     Ask AI: 'Look at my Supabase tables and generate Lightdash models'"
echo ""
echo "  2. Deploy:"
echo "     lightdash lint"
echo "     lightdash deploy --create 'My Project' --no-warehouse-credentials"
echo ""
echo "  3. Set warehouse credentials:"
echo "     Once your project is created, run this to connect it to your warehouse:"
echo "     bash set-warehouse.sh"
echo ""

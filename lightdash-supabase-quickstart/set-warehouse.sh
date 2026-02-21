#!/usr/bin/env bash
set -euo pipefail

# Sets the warehouse connection credentials on an existing Lightdash project
# via the API — no UI required.
#
# Prerequisites:
#   - lightdash login has been run (or LIGHTDASH_API_KEY is set)
#   - lightdash deploy --create has been run (project exists)
#   - .env exists with DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME, DB_SSL_MODE

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}▶ $*${RESET}"; }
success() { echo -e "${GREEN}✓ $*${RESET}"; }
warn()    { echo -e "${YELLOW}⚠ $*${RESET}"; }
die()     { echo -e "${RED}✗ $*${RESET}" >&2; exit 1; }

LIGHTDASH_URL="https://app.lightdash.cloud"

echo ""
echo -e "${BOLD}Set Lightdash Warehouse Connection${RESET}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── load .env ─────────────────────────────────────────────────────────────────
if [[ -f .env ]]; then
  DB_HOST=$(grep -E '^DB_HOST=' .env | cut -d= -f2-)
  DB_PORT=$(grep -E '^DB_PORT=' .env | cut -d= -f2-)
  DB_USER=$(grep -E '^DB_USER=' .env | cut -d= -f2-)
  DB_PASS=$(grep -E '^DB_PASS=' .env | cut -d= -f2-)
  DB_NAME=$(grep -E '^DB_NAME=' .env | cut -d= -f2-)
  SSL_MODE=$(grep -E '^DB_SSL_MODE=' .env | cut -d= -f2-)
  success ".env loaded"
else
  die ".env not found. Run setup.sh first."
fi

DB_HOST="${DB_HOST:?DB_HOST not set in .env}"
DB_PORT="${DB_PORT:?DB_PORT not set in .env}"
DB_USER="${DB_USER:?DB_USER not set in .env}"
DB_PASS="${DB_PASS:?DB_PASS not set in .env}"
DB_NAME="${DB_NAME:?DB_NAME not set in .env}"
SSL_MODE="${SSL_MODE:-no-verify}"

echo ""

# ── project uuid ──────────────────────────────────────────────────────────────
info "Reading active Lightdash project..."

PROJECT_UUID="${LIGHTDASH_PROJECT:-}"

if [[ -z "$PROJECT_UUID" ]] && command -v lightdash &>/dev/null; then
  PROJECT_OUTPUT=$(lightdash config get-project 2>/dev/null || true)
  PROJECT_UUID=$(echo "$PROJECT_OUTPUT" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1 || true)
fi

if [[ -z "$PROJECT_UUID" ]]; then
  warn "Could not detect project UUID automatically."
  echo "  Find it in your Lightdash URL: ${LIGHTDASH_URL}/projects/YOUR-UUID/..."
  echo ""
  read -rp "  Paste project UUID: " PROJECT_UUID
  [[ -z "$PROJECT_UUID" ]] && die "Project UUID required."
fi

success "Project UUID: ${PROJECT_UUID}"
echo ""

# ── auth token ────────────────────────────────────────────────────────────────
info "Looking for Lightdash auth token..."

LIGHTDASH_TOKEN="${LIGHTDASH_API_KEY:-}"

# Try ~/.config/lightdash/config.yaml first (written by lightdash login)
if [[ -z "$LIGHTDASH_TOKEN" ]]; then
  CLI_CFG="$HOME/.config/lightdash/config.yaml"
  if [[ -f "$CLI_CFG" ]]; then
    LIGHTDASH_TOKEN=$(grep -E '^\s*apiKey:' "$CLI_CFG" | awk '{print $2}' | tr -d '"' || true)
    [[ -n "$LIGHTDASH_TOKEN" ]] && success "Token found in ${CLI_CFG}"
  fi
fi

# Fallback: JSON config locations (older CLI versions)
if [[ -z "$LIGHTDASH_TOKEN" ]]; then
  for cfg in \
    "$HOME/.config/lightdash-cli/config.json" \
    "$HOME/Library/Preferences/lightdash-cli/config.json"
  do
    if [[ -f "$cfg" ]]; then
      LIGHTDASH_TOKEN=$(grep -oE '"(token|apiKey)"\s*:\s*"[^"]+"' "$cfg" | grep -oE '"[^"]+"$' | tr -d '"' || true)
      [[ -n "$LIGHTDASH_TOKEN" ]] && { success "Token found in ${cfg}"; break; }
    fi
  done
fi

if [[ -z "$LIGHTDASH_TOKEN" ]]; then
  warn "No token found automatically."
  echo "  Create one at: ${LIGHTDASH_URL}/settings/personal-access-tokens"
  echo ""
  read -rsp "  Paste token: " LIGHTDASH_TOKEN; echo ""
  [[ -z "$LIGHTDASH_TOKEN" ]] && die "Token required."
fi

echo ""

# ── api call ──────────────────────────────────────────────────────────────────
info "Setting warehouse credentials on project ${PROJECT_UUID}..."
echo "  Host:    ${DB_HOST}:${DB_PORT}"
echo "  DB:      ${DB_NAME}"
echo "  User:    ${DB_USER}"
echo "  SSL:     ${SSL_MODE}"
echo ""

RESPONSE_FILE=$(mktemp)
trap 'rm -f "$RESPONSE_FILE"' EXIT

if command -v jq &>/dev/null; then
  API_BODY=$(jq -n \
    --arg host    "$DB_HOST" \
    --arg user    "$DB_USER" \
    --arg pass    "$DB_PASS" \
    --argjson port "$DB_PORT" \
    --arg dbname  "$DB_NAME" \
    --arg ssl     "$SSL_MODE" \
    '{"warehouseConnection":{"type":"postgres","host":$host,"user":$user,"password":$pass,"port":$port,"dbname":$dbname,"schema":"public","sslmode":$ssl}}')
else
  # Escape backslashes and double-quotes in the password before embedding in JSON
  ESCAPED_PASS="${DB_PASS//\\/\\\\}"
  ESCAPED_PASS="${ESCAPED_PASS//\"/\\\"}"
  API_BODY=$(printf '{"warehouseConnection":{"type":"postgres","host":"%s","user":"%s","password":"%s","port":%s,"dbname":"%s","schema":"public","sslmode":"%s"}}' \
    "$DB_HOST" "$DB_USER" "$ESCAPED_PASS" "$DB_PORT" "$DB_NAME" "$SSL_MODE")
fi

HTTP_STATUS=$(curl -s -o "$RESPONSE_FILE" -w "%{http_code}" \
  -X PUT "${LIGHTDASH_URL}/api/v1/projects/${PROJECT_UUID}/warehouse-credentials" \
  -H "Authorization: ApiKey ${LIGHTDASH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$API_BODY")

API_RESPONSE=$(cat "$RESPONSE_FILE" 2>/dev/null || true)

if [[ "$HTTP_STATUS" == "200" ]] && echo "$API_RESPONSE" | grep -q '"status":"ok"'; then
  success "Done! Warehouse credentials set — no UI step needed."
  echo ""
  echo "  Run a query in Lightdash to verify the connection:"
  echo "  → ${LIGHTDASH_URL}/projects/${PROJECT_UUID}/tables"
else
  echo ""
  warn "API returned HTTP ${HTTP_STATUS}."
  [[ -n "$API_RESPONSE" ]] && echo "  Response: $API_RESPONSE"
  echo ""
  echo "  Common causes:"
  echo "    401 — token is wrong or expired (regenerate at /settings/personal-access-tokens)"
  echo "    403 — token doesn't have project admin permissions"
  echo "    404 — project UUID is wrong"
  echo ""
  echo "  Set credentials manually instead:"
  echo "  → ${LIGHTDASH_URL} → gear → Project Settings → warehouse connection form"
  echo "    Host:     ${DB_HOST}"
  echo "    Port:     ${DB_PORT}"
  echo "    Database: ${DB_NAME}"
  echo "    User:     ${DB_USER}"
  echo "    Password: (from .env)"
  echo "    → Advanced → SSL mode: ${SSL_MODE}"
  echo ""
  echo "  Note: use the Session/Transaction Pooler host from Supabase → Connect"
  echo "  NOT the Direct connection host (db.xxxx.supabase.co)"
  exit 1
fi

#!/usr/bin/env bash
# Get MCP Gateway access token using Cognito client credentials.
# Reads MCP_COGNITO_CLIENT_ID, MCP_COGNITO_CLIENT_SECRET, MCP_COGNITO_TOKEN_ENDPOINT
# from .env (default: customer-support-agent/.env relative to repo root).

set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
ENV_FILE="${ENV_FILE:-$REPO_ROOT/customer-support-agent/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: .env not found at $ENV_FILE. Set ENV_FILE to override." >&2
  exit 1
fi

# Load MCP Cognito vars from .env (no export of other vars)
while IFS= read -r line; do
  case "$line" in
    MCP_COGNITO_CLIENT_ID=*)    MCP_COGNITO_CLIENT_ID="${line#*=}" ;;
    MCP_COGNITO_CLIENT_SECRET=*) MCP_COGNITO_CLIENT_SECRET="${line#*=}" ;;
    MCP_COGNITO_TOKEN_ENDPOINT=*) MCP_COGNITO_TOKEN_ENDPOINT="${line#*=}" ;;
    MCP_RESOURCE_SERVER_ID=*)   MCP_RESOURCE_SERVER_ID="${line#*=}" ;;
  esac
done < <(grep -E '^MCP_COGNITO_|^MCP_RESOURCE_SERVER_ID=' "$ENV_FILE" 2>/dev/null || true)

if [[ -z "$MCP_COGNITO_CLIENT_ID" || -z "$MCP_COGNITO_CLIENT_SECRET" || -z "$MCP_COGNITO_TOKEN_ENDPOINT" ]]; then
  echo "Error: MCP_COGNITO_CLIENT_ID, MCP_COGNITO_CLIENT_SECRET, and MCP_COGNITO_TOKEN_ENDPOINT must be set in $ENV_FILE" >&2
  exit 1
fi

# Optional scope (matches Python client when MCP_RESOURCE_SERVER_ID is set)
SCOPE_ARG=()
if [[ -n "$MCP_RESOURCE_SERVER_ID" ]]; then
  SCOPE_ARG=(--data-urlencode "scope=${MCP_RESOURCE_SERVER_ID}/gateway.access")
fi

curl --http1.1 -sS -X POST "$MCP_COGNITO_TOKEN_ENDPOINT" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "client_id=$MCP_COGNITO_CLIENT_ID" \
  --data-urlencode "client_secret=$MCP_COGNITO_CLIENT_SECRET" \
  "${SCOPE_ARG[@]}"

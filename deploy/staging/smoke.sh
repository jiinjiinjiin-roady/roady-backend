#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

get_url() {
  local path="$1"
  local output="$2"
  curl --silent --show-error --fail --output "${output}" "${BASE_URL}${path}"
}

require_command curl
require_command python3

health_json="${TMP_DIR}/health.json"
bootstrap_json="${TMP_DIR}/bootstrap.json"
openapi_json="${TMP_DIR}/openapi.json"
docs_html="${TMP_DIR}/docs.html"

get_url "/api/v1/health" "${health_json}"
python3 - "${health_json}" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as file:
    payload = json.load(file)

if payload.get("status") not in {"UP", "DEGRADED"}:
    raise SystemExit(f"Unexpected health status: {payload.get('status')}")

services = payload.get("services", {})
if services.get("database") != "UP":
    raise SystemExit(f"Database is not UP: {services.get('database')}")
PY

get_url "/api/v1/bootstrap" "${bootstrap_json}"
get_url "/openapi.json" "${openapi_json}"
get_url "/docs" "${docs_html}"

python3 - "${openapi_json}" <<'PY'
import json
import sys

required_paths = {
    "/api/v1/health",
    "/api/v1/bootstrap",
    "/api/v1/profiles",
    "/api/v1/driving-sessions",
    "/api/v1/agent/conversations/{conversationId}",
    "/api/v1/profiles/{profileId}/reports/summary",
}

with open(sys.argv[1], "r", encoding="utf-8") as file:
    spec = json.load(file)

paths = set(spec.get("paths", {}))
missing = sorted(required_paths - paths)
if missing:
    raise SystemExit(f"Missing OpenAPI paths: {missing}")

if "/ws/v1/driving-sessions/{sessionId}" in paths:
    raise SystemExit("WebSocket path must not be exposed as an OpenAPI REST path")
PY

echo "Smoke checks passed for ${BASE_URL}"

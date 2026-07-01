#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

TARGET_TAG="${1:-}"
ENV_FILE="${ENV_FILE:-.env}"
COMPOSE_FILE="${COMPOSE_FILE:-compose.yaml}"
STATE_DIR="${STATE_DIR:-.deploy-state}"
BACKEND_HEALTH_TIMEOUT_SECONDS="${BACKEND_HEALTH_TIMEOUT_SECONDS:-180}"

if [[ -z "${TARGET_TAG}" ]]; then
  echo "Usage: ./rollback.sh sha-abcdef1" >&2
  exit 1
fi

if [[ ! "${TARGET_TAG}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]]; then
  echo "Invalid image tag: ${TARGET_TAG}" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Create it from .env.staging.example and fill staging values." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
. "${ENV_FILE}"
set +a

if [[ -z "${BACKEND_IMAGE:-}" ]]; then
  echo "Missing BACKEND_IMAGE in ${ENV_FILE}" >&2
  exit 1
fi

export BACKEND_IMAGE_TAG="${TARGET_TAG}"
COMPOSE=(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")

wait_for_health() {
  local service="$1"
  local timeout_seconds="$2"
  local deadline=$((SECONDS + timeout_seconds))
  local container_id=""
  local status=""

  while (( SECONDS < deadline )); do
    container_id="$("${COMPOSE[@]}" ps -q "${service}")"
    if [[ -n "${container_id}" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container_id}")"
      if [[ "${status}" == "healthy" ]]; then
        echo "${service} is healthy"
        return 0
      fi
    fi
    sleep 5
  done

  echo "${service} did not become healthy. Last status: ${status:-missing}" >&2
  "${COMPOSE[@]}" logs --no-color "${service}" >&2 || true
  exit 1
}

mkdir -p "${STATE_DIR}"
if [[ -f "${STATE_DIR}/current_image_tag" ]]; then
  cp "${STATE_DIR}/current_image_tag" "${STATE_DIR}/previous_image_tag"
fi

echo "Rolling backend image to ${BACKEND_IMAGE}:${BACKEND_IMAGE_TAG}"
"${COMPOSE[@]}" config >/dev/null
"${COMPOSE[@]}" pull backend
"${COMPOSE[@]}" up -d backend
wait_for_health backend "${BACKEND_HEALTH_TIMEOUT_SECONDS}"

ENV_FILE="${ENV_FILE}" ./smoke.sh
printf '%s\n' "${BACKEND_IMAGE_TAG}" > "${STATE_DIR}/current_image_tag"

echo "Rollback completed for ${BACKEND_IMAGE}:${BACKEND_IMAGE_TAG}"

#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

ENV_FILE="${ENV_FILE:-.env}"
COMPOSE_FILE="${COMPOSE_FILE:-compose.yaml}"
STATE_DIR="${STATE_DIR:-.deploy-state}"
BACKEND_HEALTH_TIMEOUT_SECONDS="${BACKEND_HEALTH_TIMEOUT_SECONDS:-180}"
MYSQL_HEALTH_TIMEOUT_SECONDS="${MYSQL_HEALTH_TIMEOUT_SECONDS:-180}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

load_env_file() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing ${ENV_FILE}. Create it from .env.staging.example and fill staging values." >&2
    exit 1
  fi

  local override_backend_image_tag="${BACKEND_IMAGE_TAG:-}"
  set -a
  # shellcheck disable=SC1090
  . "${ENV_FILE}"
  set +a

  if [[ -n "${override_backend_image_tag}" ]]; then
    export BACKEND_IMAGE_TAG="${override_backend_image_tag}"
  fi
}

require_env() {
  local missing=0
  for name in "$@"; do
    if [[ -z "${!name:-}" ]]; then
      echo "Missing required environment variable: ${name}" >&2
      missing=1
    fi
  done
  if [[ "${missing}" -ne 0 ]]; then
    exit 1
  fi
}

reject_placeholder_secret() {
  for name in MYSQL_PASSWORD MYSQL_ROOT_PASSWORD DATABASE_URL; do
    if [[ "${!name:-}" == *CHANGE_ME* ]]; then
      echo "Refusing deploy because ${name} still contains CHANGE_ME." >&2
      exit 1
    fi
  done
}

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
  "${COMPOSE[@]}" ps >&2 || true
  "${COMPOSE[@]}" logs --no-color "${service}" >&2 || true
  exit 1
}

record_previous_tag() {
  mkdir -p "${STATE_DIR}"

  local backend_container=""
  local current_image=""
  local current_tag=""

  backend_container="$("${COMPOSE[@]}" ps -q backend || true)"
  if [[ -n "${backend_container}" ]]; then
    current_image="$(docker inspect --format '{{.Config.Image}}' "${backend_container}" 2>/dev/null || true)"
    if [[ "${current_image}" == *:* ]]; then
      current_tag="${current_image##*:}"
      printf '%s\n' "${current_tag}" > "${STATE_DIR}/previous_image_tag"
    fi
  elif [[ -f "${STATE_DIR}/current_image_tag" ]]; then
    cp "${STATE_DIR}/current_image_tag" "${STATE_DIR}/previous_image_tag"
  fi
}

require_command docker
load_env_file

require_env \
  BACKEND_IMAGE \
  BACKEND_IMAGE_TAG \
  MYSQL_DATABASE \
  MYSQL_USER \
  MYSQL_PASSWORD \
  MYSQL_ROOT_PASSWORD \
  DATABASE_URL

reject_placeholder_secret

COMPOSE=(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")

echo "Validating Compose config"
"${COMPOSE[@]}" config >/dev/null

record_previous_tag

echo "Pulling backend image ${BACKEND_IMAGE}:${BACKEND_IMAGE_TAG}"
"${COMPOSE[@]}" pull backend

echo "Starting MySQL"
"${COMPOSE[@]}" up -d mysql
wait_for_health mysql "${MYSQL_HEALTH_TIMEOUT_SECONDS}"

echo "Running Alembic migrations"
"${COMPOSE[@]}" run --rm --no-deps backend alembic upgrade head

echo "Starting backend"
"${COMPOSE[@]}" up -d backend
wait_for_health backend "${BACKEND_HEALTH_TIMEOUT_SECONDS}"

echo "Running smoke checks"
ENV_FILE="${ENV_FILE}" ./smoke.sh

mkdir -p "${STATE_DIR}"
printf '%s\n' "${BACKEND_IMAGE_TAG}" > "${STATE_DIR}/current_image_tag"

echo "Deploy completed for ${BACKEND_IMAGE}:${BACKEND_IMAGE_TAG}"

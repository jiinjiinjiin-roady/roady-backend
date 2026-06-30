# driving-agent backend

FastAPI backend for the `driving-agent` project.

The backend stores data in MySQL 8.4 with InnoDB, `utf8mb4`, and
`utf8mb4_0900_ai_ci`. Schema changes are managed only through Alembic migrations.
Do not use `Base.metadata.create_all()` for application schema management.

## Current Scope

- FastAPI application factory with lifespan startup/shutdown
- Pydantic Settings and `.env` support
- Async SQLAlchemy engine and `AsyncSession`
- Async Alembic migration environment
- SQLAlchemy models and Alembic migrations through phase 2:
  - accounts
  - driver profiles, saved places, and search histories
  - driving sessions, location samples, safety behavior events, interventions, and driver responses
  - agent conversations, agent messages, tool executions, and report exports
- Default admin account seed command
- `GET /api/v1/health`
- MVP `current_account` dependency backed by `DEFAULT_ADMIN_ACCOUNT_ID`
- `GET /api/v1/bootstrap`
- Driver Profile REST API:
  - `GET /api/v1/profiles`
  - `POST /api/v1/profiles`
  - `GET /api/v1/profiles/{profileId}`
  - `PATCH /api/v1/profiles/{profileId}`
  - `DELETE /api/v1/profiles/{profileId}`
  - `POST /api/v1/profiles/{profileId}/select`
- Docker Compose stack for backend and MySQL
- Ruff, pytest, compileall, OpenAPI, and smoke checks

## Not Implemented Yet

- Login, JWT, passwords, roles, or authority management
- Account CRUD API
- Saved Place, Search History, Driving Session, Agent, Report, and Report Export APIs
- WebSocket
- ViT inference, Gemini calls, email delivery, report file generation, and risk policy services

The default admin account is only seed data for early development. It is not a
login account, has no password, and must not be treated as production
authentication. Never use development passwords in production.

## Requirements

- Python 3.12
- Docker Desktop
- Docker Compose
- Project dependencies managed by `pyproject.toml`

## Local Setup

```bash
python -m pip install -e ".[dev]"
```

Copy the example environment file before running Docker Compose:

```bash
cp .env.example .env
```

Do not commit `.env`.

## Docker Compose

Run from the project root, one directory above this backend folder:

```bash
docker compose config
docker compose up --build -d
docker compose ps
```

The backend waits for MySQL to become healthy. The backend container then runs:

```text
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If migration fails, seed and Uvicorn do not run. If seed fails, Uvicorn does not run.

## URLs

- Swagger: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`
- Health API: `http://localhost:8000/api/v1/health`
- Bootstrap API: `http://localhost:8000/api/v1/bootstrap`
- Profile API: `http://localhost:8000/api/v1/profiles`

## Profile API Example

```powershell
$body = @{
    displayName = "Codex Smoke"
    agentCallName = "Codex"
    reportEmail = "codex-smoke@example.com"
    agentPersonality = "FRIENDLY"
    warningSensitivity = "MEDIUM"
    ttsVoiceId = $null
    ttsSpeed = 1.0
    guidanceVolume = 70
    theme = "SYSTEM"
} | ConvertTo-Json

$profile = Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/profiles" `
    -ContentType "application/json" `
    -Body $body

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/api/v1/profiles/$($profile.id)/select"
```

## Logs And Status

```bash
docker compose ps
docker compose logs --no-color mysql
docker compose logs --no-color backend
```

## Alembic

Upgrade to the latest revision:

```bash
docker compose exec backend alembic upgrade head
```

Show current revision:

```bash
docker compose exec backend alembic current
```

Create a new revision in later schema work:

```bash
docker compose exec backend alembic revision -m "describe change"
```

The first revision is `0001_create_accounts`.

Current migration chain:

```text
0001_create_accounts
0002_profile_place_tables
0003_driving_safety_tables
0004_agent_report_tables
```

`report_exports` is intentionally linked only to `driver_profiles`; there is no
direct report-to-driving-session join table in the current ERD. The active
driving session uniqueness rule uses a MySQL generated column and unique index.

## Seed

Run the seed manually:

```bash
docker compose exec backend python -m app.db.seed
```

The seed command:

- looks up `DEFAULT_ADMIN_ACCOUNT_ID`
- creates the account if it does not exist
- updates the email if the same ID already exists with a different email
- fails if the configured email is already used by another account
- can be run repeatedly without creating duplicate accounts

## Verification

```bash
docker compose exec backend ruff check .
docker compose exec backend pytest -ra
docker compose exec backend python -m compileall app
curl -i http://localhost:8000/api/v1/health
curl -i http://localhost:8000/api/v1/bootstrap
curl -i http://localhost:8000/api/v1/profiles
curl -i http://localhost:8000/docs
curl -i http://localhost:8000/openapi.json
```

Latest verified result on 2026-06-30:

```text
ruff check . -> passed
pytest -ra -> 113 passed
python -m compileall app -> passed
PowerShell smoke test -> passed
OpenAPI path/schema check -> passed
Alembic current/head -> 0004_agent_report_tables
```

## Stop Containers

```bash
docker compose down
```

Remove containers and the named MySQL volume only when it is safe to delete local
development data:

```bash
docker compose down -v
```

## Configuration

Settings are loaded from environment variables and `.env`.

- `APP_ENV`
- `APP_NAME`
- `API_V1_PREFIX`
- `WS_V1_PREFIX`
- `LOG_LEVEL`
- `SQL_ECHO`
- `DEMO_MODE`
- `CORS_ORIGINS`
- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_DATABASE`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_ROOT_PASSWORD`
- `DEFAULT_ADMIN_ACCOUNT_ID`
- `DEFAULT_ADMIN_EMAIL`
- `MODEL_PATH`
- `MODEL_VERSION`
- `POLICY_VERSION`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `EMAIL_PROVIDER`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_USERNAME`
- `EMAIL_PASSWORD`
- `EMAIL_FROM`
- `REPORT_STORAGE_PATH`

`CORS_ORIGINS` accepts either a comma-separated string or a JSON array string.

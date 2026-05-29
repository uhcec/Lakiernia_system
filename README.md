# Factory Work Order System

This repository contains a full-stack work-order system for a paint-shop production workflow. It covers office intake, manager planning, production-stage execution, packing, correction orders, attachments, completed-history views, and hardening around operator-visible truth.

The backend owns business semantics. The frontend displays backend-provided workflow state and labels; it must not infer correction, READY, queue, or quantity meaning from local UI guesses.

## Truth And Evidence

Read these first when changing the system:

1. `docs/WORKFLOW.md` defines workflow behavior and business semantics.
2. `docs/WORKING_CONTRACT.md` defines how we work on the system together.
3. `HARDENING_BACKLOG.md` tracks risk and hardening work, but verify each item against current code before treating it as open.
4. Tests and Alembic migrations describe implemented behavior and durable schema history.

If business behavior is unclear, clarify it before implementation. Existing docs and tests are useful evidence, but they can preserve old assumptions and do not prove that the real factory workflow is correct.

## Current Scope

Implemented areas include:

- office intake with validation for customer, coating, quantity, profiles, accessories, dates, notes, and incomplete-on-arrival handling
- manager queue planning, queue reordering, stale queue revision protection, and global queue-position uniqueness
- process stages for surface preparation, hanging, production, packing, and decoral production
- manual and automatic production paths, including automatic-line resource locking
- packing quantity validation using persisted surface-preparation counted quantity
- correction child work orders, recursive correction chains, merge/finalization behavior, and historical correction display markers
- local PDF attachment storage for work orders
- backend tests, API tests, migration tests, frontend tests, and chaos-style API scenarios

## Technology

Backend:

- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- Alembic
- Pydantic 2
- pytest
- SQLite for local development

Frontend:

- React 18
- TypeScript
- Vite
- Vitest
- Testing Library
- Tailwind CSS

## Repository Map

```text
app/
  api/                  FastAPI route aggregation and health route
  core/                 Settings and configuration
  database/             SQLAlchemy base, model registry, and sessions
  manager/              Planning queue API, repository, schemas, service
  process/              Production workflow API, models, schemas, service
  shared/               Shared enums, exceptions, cross-module helpers
  work_orders/          Intake, order detail, attachments, numbering
alembic/                Database migration history
docs/
  WORKFLOW.md           Business workflow source of truth
  WORKING_CONTRACT.md   Collaboration and quality rules
frontend/               React/Vite operator UI
scripts/                Local database repair, reset, and seed utilities
tests/                  Backend, API, migration, contract, and chaos tests
```

## Backend Setup

Create and activate a virtual environment, then install development dependencies:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Optional `.env` in the repository root:

```env
APP_NAME=Work Order Backend
APP_ENV=development
DEBUG=false
BACKEND_CORS_ORIGINS=["http://127.0.0.1:5173","http://localhost:5173"]
DATABASE_URL=sqlite:///./local.db
WORK_ORDER_ATTACHMENTS_DIR=./storage/work_order_attachments
WORK_ORDER_ATTACHMENT_MAX_SIZE_BYTES=10485760
```

Apply migrations:

```powershell
python -m alembic upgrade head
python -m alembic check
```

Start the API server:

```powershell
uvicorn app.main:app --reload
```

Local backend URL:

```text
http://127.0.0.1:8000
```

Health check:

```text
GET /health
```

## Local Development Database

The default local database is `local.db` in the repository root.

For a clean seeded development state:

```powershell
python scripts/reset_and_seed_dev_db.py
```

The seed script:

- runs `alembic upgrade head`
- deletes application data from local SQLite only
- keeps migration tables intact
- recreates local attachment storage files
- seeds representative intake, planning, process, packing, correction, attachment, and queue scenarios

Safety guardrails:

- runs only when `APP_ENV=development`
- runs only against local SQLite `local.db`
- does not create a backup

If a local SQLite database is inconsistent after old migration experiments or reverted work, prefer recreating it from migrations:

```powershell
Remove-Item .\local.db -ErrorAction SilentlyContinue
python -m alembic upgrade head
python -m alembic check
```

The legacy repair script still exists for older local databases that were partially migrated around correction-order migration `20260525_0007`:

```powershell
python scripts/repair_sqlite_migration_0007.py
python -m alembic upgrade head
```

## Frontend Setup

Install dependencies:

```powershell
Push-Location frontend
npm install
Pop-Location
```

Optional frontend `.env`:

```powershell
Copy-Item frontend\.env.example frontend\.env
```

If `VITE_API_BASE_URL` is not set, frontend API calls use same-origin paths. In local Vite development, `/health`, `/manager`, `/process`, and `/work-orders` are proxied to `http://127.0.0.1:8000`.

Start the frontend:

```powershell
Push-Location frontend
npm run dev
Pop-Location
```

Local frontend URL:

```text
http://127.0.0.1:5173
```

## Quality Checks

Backend tests:

```powershell
python -m pytest
```

Alembic schema/model drift check:

```powershell
python -m alembic check
```

Frontend tests and build:

```powershell
Push-Location frontend
npm run test
npm run build
Pop-Location
```

The GitHub Actions quality gate runs backend tests, upgrades/checks Alembic schema drift, and builds the frontend.

## Database Migrations

Create a migration after intentional SQLAlchemy model changes:

```powershell
python -m alembic revision --autogenerate -m "describe change"
```

Apply migrations:

```powershell
python -m alembic upgrade head
```

Check whether model metadata and migration head are aligned:

```powershell
python -m alembic check
```

Rules:

- Do not generate migrations just to match stale local SQLite artifacts.
- If `alembic check` reports unexpected changes, classify whether the model or migration history is the real source of truth before editing.
- For SQLite table rewrites, keep migrations narrow and test dirty-data failure paths when constraints are involved.

## Attachments

Work-order attachments are stored on the local filesystem under `WORK_ORDER_ATTACHMENTS_DIR`. File binaries are not stored in the database. Uploads are currently limited by `WORK_ORDER_ATTACHMENT_MAX_SIZE_BYTES` and PDF validation rules in the backend service.

## Development Notes

- `process_status` and backend read models are the source of truth for workflow display.
- `status` remains as a compatibility/read-model field and should not drive new workflow logic.
- Completed/history views must not display active batch progress or misleading live quantities.
- Queue positions are globally unique for planned work orders.
- Correction orders are child work orders and join the same queue only after planning.
- State-changing process actions must remain safe under retries, double clicks, and parallel users.

## Current Cleanup Path

Near-term cleanup priorities are tracked in `docs/WORKING_CONTRACT.md` and `HARDENING_BACKLOG.md`. The current sequence is:

1. Refactor Copilot instructions into a shorter always-on contract plus targeted workflow aids.
2. Audit multi-worker concurrency, remaining DB invariants, historical UI semantics, auth/roles, audit logging, and attachment lifecycle safety.
3. Add traceability between workflow scenarios, tests, and unresolved business assumptions.
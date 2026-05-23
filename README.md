# Work Order Backend Foundation

This repository contains a modular FastAPI backend foundation for a generic work order workflow engine. The current scope is intentionally narrow: application bootstrap, configuration, database wiring, migration scaffolding, and test setup.

The foundation keeps internal workflow identifiers in English while reserving Polish labels for future UI-facing responses.

## Project structure

```text
app/
  api/
    routes/
  core/
  database/
  shared/
  work_orders/
tests/
alembic/
```

Key structure notes:

- `api` contains HTTP routing only.
- `core` contains centralized configuration.
- `database` contains SQLAlchemy base, model registry, and session setup.
- `shared` contains cross-module enums and exceptions.
- `work_orders` is the first bounded module, already split into model/schema/repository/service/router layers.

## Run the application

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install -e .[dev]
```

3. Optionally create a `.env` file in the repository root:

```env
APP_NAME=Work Order Backend
APP_ENV=development
DEBUG=false
BACKEND_CORS_ORIGINS=["http://127.0.0.1:5173","http://localhost:5173"]
DATABASE_URL=sqlite:///./local.db
```

Local development database note:

- The default local SQLite database file is `local.db` in the repository root.
- After reverting domain modules or migrations during development, an existing local database may still contain stale tables that are no longer present in the current source code.
- Treat the current source code and Alembic history in this repository as the source of truth.
- If local schema state looks inconsistent, delete `local.db` and recreate it with Alembic instead of generating migrations for stale local tables.

Reset the local development database:

```bash
Remove-Item .\local.db -ErrorAction SilentlyContinue
python -m alembic upgrade head
python -m alembic check
```

4. Start the API server:

```bash
uvicorn app.main:app --reload
```

5. Verify the health endpoint:

```bash
GET /health
```

Local backend URL:

```text
http://127.0.0.1:8000
```

## Run the frontend

1. Go to the frontend directory:

```bash
cd frontend
```

2. Install dependencies:

```bash
npm install
```

3. Optionally copy `.env.example` to `.env` and adjust the API URL when the frontend should talk to a non-default backend origin:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

If `VITE_API_BASE_URL` is not set, the frontend uses same-origin requests. In local development, Vite proxies `/work-orders` and `/health` to `http://127.0.0.1:8000`.

4. Start the Vite development server:

```bash
npm run dev
```

5. Open the frontend in the browser:

```text
http://127.0.0.1:5173
```

The work order list view is fully in Polish and uses the backend-provided `status.label` for display instead of raw enum values.

## Run tests

```bash
pytest
```

Build the frontend for a production-like check:

```bash
cd frontend
npm run build
```

## Prepare database migrations

Create a new migration after model changes:

```bash
alembic revision --autogenerate -m "create work orders table"
```

Apply migrations:

```bash
alembic upgrade head
```

Check pending model changes without creating a revision:

```bash
alembic check
```

If `alembic check` reports removed local tables after a revert, reset `local.db` and rerun the commands above. Do not create new migrations just to match stale local development tables.

## Workflow status changes

- Workflow status changes are explicit actions through a dedicated transition endpoint and service function.
- Normal `PATCH /work-orders/{id}` updates business fields only: `title`, `description`, `customer_name`, `due_date`, and `notes`.
- Normal field updates must not change workflow status.
- Invalid transitions return `409 Conflict` because the request conflicts with the current workflow state of the work order.
- The current order number generator is intentionally simple and should be replaced with a database-backed strategy before real multi-user production usage.

## What to build next

1. Add initial work order create/read/update endpoints through dedicated repository and service layers.
2. Replace the string-backed status column with a typed SQLAlchemy enum strategy once the first migration is created.
3. Introduce structured domain exceptions, validation rules, and response models for workflow transitions.
4. Add the first API response models that expose workflow status as `{ value, label }` instead of treating raw enum values as UI text.
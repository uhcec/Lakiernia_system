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

3. Optionally copy `.env.example` to `.env` and adjust the API URL:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

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
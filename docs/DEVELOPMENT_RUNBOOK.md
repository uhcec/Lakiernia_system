# Development Runbook

This runbook keeps local setup and verification commands in one place. It does not define workflow semantics; use `docs/WORKFLOW.md` for business behavior.

## First Setup

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

Push-Location frontend
npm install
Pop-Location
```

## Local Database

Apply current migrations:

```powershell
python -m alembic upgrade head
python -m alembic check
```

Reset and seed the local SQLite database with representative scenarios:

```powershell
python scripts/reset_and_seed_dev_db.py
```

Print the seeded scenario list without resetting the database:

```powershell
python scripts/print_seed_scenarios.py
```

## Run The App

Backend:

```powershell
uvicorn app.main:app --reload
```

> **Deploy with a single backend worker (NA8).** Cross-request safety relies on in-process
> locks (`_PROCESS_MUTATION_LOCKS` / `_RESOURCE_MUTATION_LOCKS` in `app/process/service.py`,
> `_QUEUE_MUTATION_LOCK` in `app/manager/service.py`) in addition to DB constraints. The
> DB-level guards (queue position, one-active-batch, resource-lock PK) survive multiple
> workers, but the "no duplicate correction child per packing split" guarantee does **not** —
> it holds only within one process. Run exactly one worker (do **not** pass `--workers N` to
> uvicorn/gunicorn) until a durable cross-process idempotency strategy exists.

Frontend:

```powershell
Push-Location frontend
npm run dev
Pop-Location
```

Local URLs:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

## Login

All business endpoints require a logged-in user (JWT). `scripts/reset_and_seed_dev_db.py` seeds one
account per station plus an admin. The full local credential table is in `README.md` (Login section);
the most common are `biuro`/`bi1` (office), `kierownik`/`ki1` (manager), and `admin`/`adm1` (admin).
Set `JWT_SECRET` in `.env` for anything beyond local use (it has an insecure default).

## Verification

Focused backend run:

```powershell
python -m pytest tests/test_process_api.py
```

Full local quality gate:

```powershell
.\scripts\run_quality_gate.ps1
```

Equivalent manual commands:

```powershell
python -m pytest
python -m alembic upgrade head
python -m alembic check
Push-Location frontend
npm run test
npm run build
Pop-Location
```

## Local Notes

- Keep `VITE_API_BASE_URL` unset for same-origin Vite proxy behavior, or set it to `http://127.0.0.1:8000` in `frontend/.env`.
- Set `VITE_QUEUE_DEBUG=true` only when actively debugging manager queue ordering in the browser.
- Generated Python bytecode is ignored and should not appear in `git status`.
- Treat passing tests as implementation evidence, not factory-policy validation.
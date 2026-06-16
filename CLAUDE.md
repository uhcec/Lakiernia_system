# Agent Entry Point

A full-stack factory work-order system for a paint shop / powder-coating line (office intake →
manager planning → production stages → packing → corrections → completed history). Preserve operator
truth, workflow consistency, and data integrity over speed or convenience.

Stack: FastAPI + SQLAlchemy 2 + Alembic + Pydantic 2 (Python 3.12), SQLite for local dev; React 18 +
TypeScript + Vite + Tailwind frontend. Polish operator UI.

## Read these first, every session

1. **`IMMEDIATE_NEXT_ACTIONS.md`** — the living list of OPEN, actionable work. Start here; pick the
   highest-severity open item unless the user says otherwise, and keep it current.
2. `docs/WORKFLOW.md` — business workflow semantics (strongest source of truth; ask the user when
   real factory policy is unclear). This is the volatile-but-authoritative doc — prefer it over the
   summaries below if they ever disagree.
3. `docs/WORKING_CONTRACT.md` — how we work (problem → risks → docs impact → solution → tests).
4. `docs/DEVELOPMENT_RUNBOOK.md` — setup, run, seed, and verify commands.
5. `HARDENING_BACKLOG.md` — *closed* hardening evidence (verify currency before trusting an item).

The sections below are a durable mental map so you don't have to re-derive the architecture each time.
They change slowly; semantics live in `docs/WORKFLOW.md`.

## Architecture map (`app/`)

- `work_orders/` — office intake (create/update/list), attachments, work-order numbering
  (`number_allocator.py`, atomic via a counter table), QC Excel→PDF document generation, and the
  `WorkOrderRead` read model. Models: `WorkOrder`, `WorkOrderNumberCounter`, `WorkOrderAttachment`.
- `process/` — **the workflow engine**. `service.py` (large) owns stage transitions, quantity
  batches, packing, decoral, correction creation/merge, resource locks, and display-status
  derivation. Models: `WorkOrderStageState`, `WorkOrderQuantityBatch`, `ProcessResourceLock`.
  `enums.py`: `ProcessStage`, `StageStatus`, `CoatingType`, `ProductionType`, `QuantityBatchType`,
  `ProcessDisplayStatus`.
- `manager/` — planning queue (`assign_plan`, `update_queue_position`, `update_production_type`,
  `reorder_queue` with stale-revision protection), correction-reason report, throughput stats.
- `paints/` — paint inventory (kg), intake stock snapshots, automatic-production consumption.
- `clients/` — client registry + per-client order history.
- `audit/` — `audit_events` table, `StationContext` (from the `X-Station-Id` header), audit console API.
- `auth/` — users table, `/auth/login`, JWT, `get_current_user`. Applied as a **global** dependency
  on all business routers in `api/router.py`.
- `shared/` — cross-cutting enums (`StationId`, `WorkOrderStatus`, `QueueNamespace`,
  `WorkOrderKind`), exceptions (mapped to HTTP in `main.py`), request-id context.
- `database/` — `base` (declarative base), `models` (import registry), `session` (engine/sessionmaker).

Frontend mirrors the stations: one page per station under `frontend/src/pages`, shared station tables
in `frontend/src/components`, typed API clients in `frontend/src/api`. The frontend **displays**
backend state and must not infer correction/READY/queue/quantity meaning locally.

## Core domain model (the part that's easy to get wrong)

- A `WorkOrder` has one `WorkOrderStageState` per configured stage and one or more
  `WorkOrderQuantityBatch` rows. Creation seeds a MAIN batch with the full `total_quantity`.
- Quantities: `total_quantity` is fixed; `completed_quantity` accumulates OK pieces;
  `current_active_quantity` = sum of **active** batches. Quantity is conserved across parent/child
  correction chains. One active batch per work order (DB-enforced partial unique index).
- **`process_status` (`ProcessDisplayStatus`) is DERIVED at read time** in
  `ProcessService.get_display_status` — it is never a stored column. `WorkOrder.status` is a legacy
  compatibility field; do not drive workflow from it.
- Stage sequence depends on coating + production type:
  `SURFACE_PREPARATION → [HANGING if AUTOMATIC] → PRODUCTION → PACKING → [DECORAL_PRODUCTION if DECORAL]`.
  For AUTOMATIC, `PRODUCTION` has no manual start/finish (it's a preview); the line finishes from
  PACKING, and `HANGING` / `AUTOMATIC_LINE` are exclusive resources backed by `ProcessResourceLock`.
- **Corrections use two models — do not unify without checking `docs/WORKFLOW.md`:**
  - RAL: resets the *same* order back to planning with a `CORRECTION` batch (no child order).
  - DECORAL: spins off a child "P{root}" work order; the OK part stays on the root's single Decoral
    pass; the parent shows the "N" (decoral-incomplete) marker until corrections return.
  - Corrections skip `SURFACE_PREPARATION`. Reason/category is recorded at packing.
- READY rules and the S01–S12 scenario matrix live in `docs/WORKFLOW.md` — consult it before touching
  completion/merge logic.

## Gotchas (these burn fresh sessions)

- **Excel/QC is Windows+Excel only, now lazy:** the Excel COM worker is built on first
  `convert()` (`_get_excel_pdf_converter`), not at import (fixed in NA5), so importing
  `app/work_orders/service.py` has no side effects. Off-Windows / missing pywin32, QC document
  generation fails fast with a clear error instead of hanging.
- **`pywin32` is Windows-only** (`pyproject.toml`: `pywin32>=306; sys_platform == 'win32'`, fixed in
  NA2) — `pip install` works on Linux/CI.
- **Authorization is derived from the authenticated user (JWT `station_id`/`is_admin`), not the
  `X-Station-Id` header** (fixed in NA1). `get_station_context` depends on `get_current_user`;
  `ensure_station_allowed` bypasses for admins, trusts only `None`/`SYSTEM` (internal/seed) callers, and
  denies anything else not in the allowed set. The `X-Station-Id` header is inert server-side (the
  frontend still sends it, but no code reads it). Manager statistics require manager/admin.
- **Single backend worker assumed:** concurrency safety uses in-process `RLock`s plus DB constraints;
  the "no duplicate correction child" guarantee depends on one process. (NA8.)
- **Local DB is `local.db` (SQLite).** Reset/seed with `python scripts/reset_and_seed_dev_db.py`
  (guarded to `APP_ENV=development` only). Keep `alembic check` clean — models and migrations must agree.

## Working rules

- Backend services/read models own business meaning; keep frontend a faithful renderer.
- Completed/history views must never show active batch progress, misleading `0 / X`, or stale labels.
- Keep changes narrow; preserve unrelated user work.
- Schema changes: update SQLAlchemy model + Alembic migration together and keep `alembic check` clean.
- Add regression/chaos coverage when touching retries, parallel users, queues, corrections, READY
  state, or durable invariants.
- If a change affects workflow meaning, update `docs/WORKFLOW.md` in the same change.

## When you finish or discover work

Update `IMMEDIATE_NEXT_ACTIONS.md`: move finished items to its "Done" section with an evidence note;
add newly discovered work with severity + `file:line` + required fix + acceptance criteria. For
durable hardening, also record closure in `HARDENING_BACKLOG.md`.

## Quality gate (run before claiming done)

```powershell
python -m pytest
python -m alembic check
Push-Location frontend; npm run test; npm run build; Pop-Location
```

Full setup/run/seed details: `docs/DEVELOPMENT_RUNBOOK.md`.

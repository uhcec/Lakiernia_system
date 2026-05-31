# Hardening Backlog

## Release Rule

No new features until all CRITICAL and HIGH items are closed.

Current implementation evidence marks all CRITICAL, HIGH, and LOW backlog items as closed. That means the current code and tests address the listed acceptance criteria; it does not prove that the real factory workflow is complete or conceptually correct. Remaining hardening work is chaos scenario expansion under newly validated business rules and broader production-readiness audits.

Workflow-policy questions that need factory validation are tracked in `docs/WORKFLOW_VALIDATION_CHECKLIST.md`.

This backlog is derived from the production-readiness audit. It is focused on hardening, failure containment, validation, concurrency safety, and test coverage. It does not authorize business logic changes without explicit clarification against `docs/WORKFLOW.md`.

Baseline check snapshot after backlog/doc cleanup: full backend suite passed with `227 passed`, frontend tests passed with `21 passed`, frontend build passed, and `python -m alembic check` reported no new upgrade operations. After Phase 2 DB invariant work, full backend validation passed with `236 passed`. Incomplete-order service/query hardening passed focused regression and chaos coverage with `15 passed`. After attachment lifecycle hardening, full backend validation passed with `238 passed`; frontend tests passed with `21 passed`; frontend build passed; `python -m alembic check` reported no new upgrade operations. After correction reason capture/storage, full quality gate passed with backend `285 passed`, Alembic clean, frontend `41 passed`, and frontend build passed. After optional external-number capture/display, full quality gate passed with backend `286 passed`, Alembic clean, frontend `42 passed`, and frontend build passed. After manager blocked-resource warning read models, full quality gate passed with backend `288 passed`, Alembic clean, frontend `43 passed`, and frontend build passed. After completed-order release status, full quality gate passed with backend `291 passed`, Alembic clean, frontend `45 passed`, frontend build passed, and `git diff --check` clean. After automatic-production hanging queue visibility, full quality gate passed with backend `291 passed`, Alembic clean, frontend `46 passed`, and frontend build passed. After packing visibility into active automatic hanging, full quality gate passed with backend `291 passed`, Alembic clean, frontend `47 passed`, and frontend build passed. After station-list readability work, full quality gate passed with backend `291 passed`, Alembic clean, frontend `49 passed`, and frontend build passed. After office/manager bucket UX work, full quality gate passed with backend `291 passed`, Alembic clean, frontend `50 passed`, and frontend build passed. After office/manager discrepancy visibility work, full quality gate passed with backend `292 passed`, Alembic clean, frontend `54 passed`, and frontend build passed. After packing card UX work, full quality gate passed with backend `292 passed`, Alembic clean, frontend `55 passed`, and frontend build passed. After generic station card UX work, full quality gate passed with backend `292 passed`, Alembic clean, frontend `55 passed`, and frontend build passed. After station-action authorization hardening, full quality gate passed with backend `294 passed`, Alembic clean, frontend `55 passed`, and frontend build passed. After `Przemalowanka`/`Ocynk` work-type modeling, full quality gate passed with backend `297 passed`, Alembic clean, frontend `56 passed`, and frontend build passed. After manager correction-planning context work, full quality gate passed with backend `297 passed`, Alembic clean, frontend `57 passed`, and frontend build passed. These checks are regression evidence, not business validation.

Latest check snapshot after profile/accessory quantity semantics: full quality gate passed with backend `306 passed`, Alembic clean, frontend `57 passed`, and frontend build passed.

## CRITICAL

### 1. Reopening finished tracked batches can corrupt quantities and READY state

- Status: CLOSED
- Implementation summary: `docs/WORKFLOW.md` was updated first to make the tracked-batch reopen rule explicit. Backend reopen paths were then hardened in `app/process/service.py` to reject reopening finished tracked batches with a controlled 409 instead of allowing quantity/state corruption.
- Tests added: service and API coverage for reopening finished tracked batches in `tests/test_process_service.py` and `tests/test_process_api.py`.
- Pytest result: focused reopen tests passed, then full `python -m pytest` passed with `154 passed`.

- Risk: reopening a finished tracked batch can reactivate quantity that has already been counted into `completed_quantity` and may already have propagated completion to parent orders. This can break quantity conservation, READY derivation, and parent/child integrity.
- Affected files: `app/process/service.py`, `app/process/router.py`, `tests/test_process_service.py`, `tests/test_process_api.py`
- Required fix: forbid unsupported tracked-batch reopen paths or implement a full reversible rollback path that restores quantities, stage state, and correction-chain state consistently.
- Required tests: service and API tests covering reopen of finished DECORAL batches, reopen of finished correction-child batches, and reopen after completion propagation to a parent.
- Acceptance criteria: reopening a finished tracked batch either returns a controlled conflict or performs a complete reversible rollback with `completed_quantity`, active quantity, stage states, and parent/correction status all remaining consistent.

### 2. State-changing process actions are not concurrency-safe or idempotent

- Status: CLOSED
- Implementation summary: process mutations in `app/process/service.py` were hardened for duplicate execution and parallel requests. Stage finish and packing completion now behave idempotently where appropriate, duplicate correction child creation is prevented, and competing operations resolve as controlled success-or-conflict instead of double-applying side effects.
- Tests added: duplicate finish, duplicate packing completion, duplicate correction creation, and related process/API hardening coverage in `tests/test_process_service.py` and `tests/test_process_api.py`.
- Pytest result: focused idempotency/concurrency tests passed, then full `python -m pytest` passed with `160 passed`.

- Risk: duplicate requests, retries, double clicks, or parallel operators can finish the same stage twice, complete packing twice, create duplicate correction orders, or double-count completion.
- Affected files: `app/process/service.py`, `app/process/repository.py`, `app/process/router.py`, `app/database/session.py`, `tests/test_process_service.py`, `tests/test_process_api.py`
- Required fix: add backend-side protection for state-changing process operations with transaction-safe concurrency control and idempotent handling for duplicate execution.
- Required tests: parallel-request tests for duplicate `finish`, duplicate `packing/complete`, duplicate correction creation, and conflicting reopen/finish operations across separate sessions.
- Acceptance criteria: repeating the same state-changing request or running competing requests in parallel cannot create duplicate side effects, cannot corrupt quantities, and always resolves to a controlled success-or-conflict outcome.

## HIGH

### 3. Queue write conflicts can escape as raw 500 errors instead of controlled 409 conflicts

- Status: CLOSED
- Implementation summary: queue writes in `app/manager/service.py` and related manager layers now normalize queue uniqueness collisions into controlled 409 conflicts instead of leaking raw integrity failures as 500 responses.
- Tests added: manager API coverage for queue write conflict handling in `tests/test_manager_api.py`.
- Pytest result: focused manager tests passed, then full `python -m pytest` passed with `164 passed`.

- Risk: planning and reorder operations rely on pre-checks before commit, but database uniqueness races can still happen and may surface as unhandled integrity failures.
- Affected files: `app/manager/service.py`, `app/manager/repository.py`, `app/main.py`, `alembic/versions/20260526_0010_shared_queue_position.py`, `tests/test_manager_api.py`
- Required fix: normalize database uniqueness failures from queue writes into controlled domain conflicts with stable error messages.
- Required tests: tests that simulate uniqueness failures during `assign_plan`, `update_queue_position`, and `reorder_queue` commit paths.
- Acceptance criteria: queue conflicts always return controlled conflict responses and never leak as generic 500 errors.

### 4. Queue reorder accepts stale client state and can overwrite another planner's newer order

- Status: CLOSED
- Implementation summary: stale-write protection was added to queue reorder with a backend `queue_revision` freshness check and frontend handling that discards stale optimistic order, shows a controlled error, and refetches authoritative queue state.
- Tests added: stale reorder backend tests in `tests/test_manager_api.py` and frontend reorder handling coverage in `frontend/tests/queueReorder.test.ts`.
- Pytest result: focused manager tests passed, then full `python -m pytest` passed with `164 passed`.

- Risk: a stale reorder payload can fully overwrite a more recent queue arrangement from another user because the backend has no version or freshness check.
- Affected files: `app/manager/service.py`, `app/manager/router.py`, `frontend/src/pages/ManagerPanelPage.tsx`, `frontend/src/utils/queueReorder.ts`, `tests/test_manager_api.py`
- Required fix: add stale-write protection for queue reorder requests and reject reorders built from outdated queue state.
- Required tests: stale-snapshot reorder tests showing that an out-of-date client receives a controlled conflict instead of silently overwriting a newer queue.
- Acceptance criteria: reorder requests based on stale queue state are rejected with a controlled conflict, and concurrent planners cannot unknowingly undo each other.

### 5. Work order number generation is race-prone for normal and correction orders

- Status: CLOSED
- Implementation summary: scan-based number generation was replaced with a shared DB-owned yearly allocator backed by `work_order_number_counters`. Normal work-order creation and correction-child creation now use the same atomic allocator path, eliminating read-the-latest-number races.
- Tests added: allocator and migration coverage in `tests/test_work_order_number_allocation.py`, `tests/test_work_order_number_counter_migration.py`, and updated migration-head coverage in `tests/test_repair_sqlite_migration_0007.py`.
- Pytest result: focused allocator and migration tests passed, then full `python -m pytest` passed with `170 passed`.

- Risk: two concurrent creates can read the same latest order number and generate the same next sequence, causing collisions during create or during correction creation inside packing.
- Affected files: `app/work_orders/service.py`, `app/work_orders/repository.py`, `app/process/service.py`, `app/process/repository.py`, `tests/test_work_orders_api.py`, `tests/test_process_service.py`
- Required fix: make work order numbering transaction-safe under concurrency and ensure correction creation cannot fail due to duplicate generated numbers.
- Required tests: concurrent creation tests for normal work orders and concurrent correction-creation tests during packing.
- Acceptance criteria: concurrent work-order creation never produces duplicate order numbers and never leaves a partially applied packing/correction flow.

### 6. Update validation is weaker than create validation for intake fields

- Status: CLOSED
- Implementation summary: `app/work_orders/service.py` now validates PATCH requests against the merged persisted work-order state before any ORM mutation is applied, so update-time validation matches create-time intake validation, including blank `customer_name` rejection after normalization.
- Tests added: invalid merged-state PATCH cases, valid partial PATCH coverage, and unchanged-on-rejection assertions in `tests/test_work_orders_api.py`.
- Pytest result: focused PATCH validation tests passed, then full `python -m pytest` passed with `181 passed`.

- Risk: PATCH can persist contradictory `profiles_*` and `accessories_*` states that create-time validation already rejects, allowing bad office data to slip into planning and production.
- Affected files: `app/work_orders/schemas.py`, `app/work_orders/service.py`, `app/work_orders/router.py`, `tests/test_work_orders_api.py`
- Required fix: validate update payloads against the merged persisted state so update-time rules match create-time consistency rules.
- Required tests: PATCH tests for invalid profile/accessory combinations and PATCH tests proving valid partial updates still work.
- Acceptance criteria: a work order cannot be updated into a contradictory intake state, and partial updates preserve valid existing state.

## MEDIUM

### 7. Incomplete orders can be marked complete without full state revalidation

- Status: CLOSED
- Implementation summary: `WorkOrderService.mark_complete_arrival()` now revalidates the full persisted work-order state with create-level intake rules before clearing `is_incomplete_on_arrival`; invalid persisted profiles, accessories, or customer data raises `InvalidWorkOrderDataError` and leaves the order unchanged.
- Tests added: service coverage in `tests/test_work_orders_service.py` for invalid profiles, invalid accessories, blank persisted customer name, successful completion, and unchanged-on-rejection behavior; API coverage in `tests/test_work_orders_api.py` verifies detail/list process status after completion.
- Validation: full `python -m pytest` passed with `227 passed` during backlog reconciliation.

- Risk: an order can leave the incomplete-on-arrival quarantine path even if its editable intake data is still inconsistent.
- Affected files: `app/work_orders/service.py`, `app/work_orders/router.py`, `tests/test_work_orders_api.py`
- Required fix: revalidate the full current work-order state before allowing `mark_complete_arrival`.
- Required tests: mark-complete-arrival tests for inconsistent office data and successful completion tests for valid data.
- Acceptance criteria: only work orders with internally consistent intake data can leave incomplete-on-arrival status.

### 8. Core business invariants are not enforced at the database level

- Status: CLOSED
- Implementation summary: safe row-local DB CHECK constraints were added in `app/work_orders/models.py` and `app/process/models.py`, and Alembic migration `20260527_0012_phase1_core_invariant_checks.py` adds them with fail-fast dirty-row prechecks before SQLite table rewrites. Phase 2 then added `20260529_0015_phase2_db_invariants.py` for correction parent requirements, one active batch per work order, and inactive batch requires `DONE` status.
- Tests added: direct DB constraint coverage in `tests/test_db_constraints_phase1.py` and `tests/test_db_constraints_phase2.py`, migration safety coverage in `tests/test_phase1_core_invariant_checks_migration.py` and `tests/test_phase2_db_invariant_migration.py`, and updated head coverage in `tests/test_repair_sqlite_migration_0007.py`.
- Validation: focused Phase 2 DB tests passed with `13 passed`; combined Phase 1/Phase 2 DB invariant tests passed with `27 passed`; full backend validation passed with `236 passed`; incomplete-order service/query regression and chaos coverage passed with `15 passed`; `python -m alembic upgrade head && python -m alembic check` reported no new upgrade operations.
- Phase 2/3 decisions:
	- Incomplete orders not planned at DB level: CLOSED. Enforced by `ck_work_orders_incomplete_requires_unplanned`, which keeps any row with `is_incomplete_on_arrival = true` or legacy `status = INCOMPLETE` out of planned queues.
	- Correction must have parent: CLOSED. Enforced by `ck_work_orders_correction_requires_parent`.
	- One active batch per work order: CLOSED. Enforced by `uq_work_order_quantity_batches_one_active_per_work_order`.
	- `current_active_batch_id` integrity: CLOSED / not needed. Treat this as a legacy/cache pointer rather than a production DB invariant.
	- Inactive batch implies `DONE`: CLOSED. Enforced by `ck_work_order_quantity_batches_inactive_batch_requires_done_status`.
	- Invalid `IN_PROGRESS` workflow shapes: CLOSED / not DB layer. These rules belong in workflow services and tests, not declarative DB constraints.

- Risk: a bug, migration issue, manual SQL change, or partial failure can leave durable invalid rows such as negative quantities, `completed_quantity > total_quantity`, invalid correction links, or invalid planning state.
- Affected files: `app/work_orders/models.py`, `app/process/models.py`, `alembic/versions/20260523_0001_initial_work_orders.py`, `alembic/versions/20260524_0002_quantity_batches.py`, `alembic/versions/20260525_0007_correction_orders.py`, `alembic/versions/20260526_0010_shared_queue_position.py`, `tests/test_repair_sqlite_migration_0007.py`
- Required fix: add database constraints for core invariants, with safe migration/backfill handling for existing data.
- Required tests: migration tests showing invalid rows are rejected and valid existing rows migrate cleanly.
- Acceptance criteria: core quantity, correction-link, and planning invariants are enforceable even if application code regresses.
- Final note: Current implementation evidence is strong enough to continue controlled cleanup and planning work. This is not a statement that the full production process has been independently validated.

### 9. Queue UI keeps optimistic order after save failure

- Status: CLOSED
- Implementation summary: manager reorder now discards optimistic queue state on any API failure and reloads authoritative backend data. Frontend API error handling was centralized so reorder failures distinguish conflicts, validation errors, and generic failures with Polish messages while always restoring server truth.
- Tests added: focused UI rollback coverage in `frontend/tests/uiStateConsistency.test.tsx` and existing queue payload coverage retained in `frontend/tests/queueReorder.test.ts`.
- Validation: focused frontend tests passed; `cd frontend && npm run build` passed; backend `python -m pytest` passed with `195 passed`.

- Risk: the manager UI can continue showing a locally reordered queue even when the backend rejected the save, creating a false view of the real production plan.
- Affected files: `frontend/src/pages/ManagerPanelPage.tsx`, `frontend/src/api/managerApi.ts`, `frontend/src/utils/queueReorder.ts`
- Required fix: restore server truth after reorder failure or explicitly roll back the optimistic local state.
- Required tests: frontend tests where reorder save fails and the rendered queue resets to authoritative backend state.
- Acceptance criteria: after a failed reorder save, the UI does not continue to display an unsaved queue as if it were committed.

### 10. Stage screens fail hard when secondary correction-detail lookups fail

- Status: CLOSED
- Implementation summary: stage and packing views now load correction-context details with fault tolerance. A failed secondary correction lookup no longer breaks the entire list; the page stays usable, falls back to generic correction context, and shows a non-blocking Polish warning.
- Tests added: partial correction-detail failure coverage in `frontend/tests/uiStateConsistency.test.tsx`.
- Validation: focused frontend tests passed; `cd frontend && npm run build` passed; backend `python -m pytest` passed with `195 passed`.

- Risk: one failed correction-detail fetch can break the entire station view even if the primary stage list loaded successfully.
- Affected files: `frontend/src/components/StageWorkOrdersPage.tsx`, `frontend/src/components/PackingWorkOrdersPage.tsx`, `frontend/src/api/processApi.ts`, `frontend/src/api/workOrdersApi.ts`
- Required fix: make secondary correction-context lookups fault-tolerant or move the required parent context into the primary stage-list response.
- Required tests: component tests where one correction detail request fails while the rest of the stage list remains usable.
- Acceptance criteria: partial data failure in correction context does not blank the whole station screen.

### 11. API error parsing is inconsistent across frontend modules

- Status: CLOSED
- Implementation summary: frontend API wrappers now use a shared status-aware error layer, and stage/packing mutations reload authoritative backend state after failures instead of leaving stale local state or partial drafts on screen. The UI now shows clear Polish messages for `409`, `422`, and generic failures while preventing unsaved client state from persisting visually.
- Tests added: stage-action reload and packing reload-on-error coverage in `frontend/tests/uiStateConsistency.test.tsx`.
- Validation: focused frontend tests passed; `cd frontend && npm run build` passed; backend `python -m pytest` passed with `195 passed`.

- Risk: validation and conflict responses can degrade into generic UI messages because some frontend API wrappers only handle string `detail` responses.
- Affected files: `frontend/src/api/processApi.ts`, `frontend/src/api/managerApi.ts`, `frontend/src/api/workOrdersApi.ts`
- Required fix: unify frontend error parsing across API modules so structured FastAPI validation responses are surfaced predictably.
- Required tests: frontend unit tests for string and array-shaped `detail` payloads across all API wrappers.
- Acceptance criteria: validation and conflict errors are rendered consistently and do not collapse into generic fallback messages when structured details are available.

## LOW

### 12. Attachment upload trusts declared MIME type without verifying PDF content

- Status: CLOSED
- Implementation summary: attachment upload now checks the file header against PDF magic bytes before persistence, rejects empty or fake PDFs even when the declared content type is `application/pdf`, and removes any partially written file on failure.
- Tests added: `tests/test_work_order_attachments_api.py` covers valid PDF upload, non-PDF MIME rejection, fake `application/pdf` rejection, valid `%PDF-` header acceptance, listing, download, delete, and cross-order access protection.
- Validation: full `python -m pytest` passed with `227 passed` during backlog reconciliation.

- Risk: a client can upload non-PDF content while claiming `application/pdf`, leading to invalid or unsafe attachment storage.
- Affected files: `app/work_orders/service.py`, `app/work_orders/router.py`, `tests/test_work_order_attachments_api.py`
- Required fix: validate stored attachment content as PDF before persistence.
- Required tests: attachment upload tests with fake `application/pdf` content and valid PDF content.
- Acceptance criteria: non-PDF payloads are rejected even when the client sends a PDF MIME type.

### 13. Historical merged-correction display depends on frontend inference instead of an explicit API marker

- Status: CLOSED
- Implementation summary: backend read models expose `is_historical_correction` for stage and work-order responses, and frontend completed/history views consume that explicit marker instead of inferring merged correction state from quantities or status combinations.
- Tests added: frontend state-consistency coverage verifies completed correction wording and guards against using historical correction wording for active correction cards.
- Acceptance criteria: completed merged corrections are displayed as historical delta summaries without active batch progress or misleading `0 / X` progress.

## Current Open Hardening Work

Open item-level work:

- None under currently validated implementation rules.
- Factory workflow validation: 2026-05-30 factory answers confirmed automatic hanging overlap, correction planning without approval, correction reason/category as statistical data with initial values `niedomalowanie`, `za grubo`, `wtrącenia`, `inne`, station-action blocking, office/manager discrepancy visibility, discrepancy confirmation at surface preparation without blocking, one global queue, manager blocked-work warnings, standalone `Przemalowanka`, and `Ocynk` as a strong station-visible type/marker combinable with RAL or Decoral. Additional 2026-05-30 notes confirmed practical office/manager tabs, station-specific list columns, external work-order number, quality-control production document generation from the factory template, paint stock/state entry at intake, automatic-production paint-consumption entry, completed-order issued/released tracking, automatic-production visibility into the hanging queue/day flow, and packing visibility into active automatic hanging before completion is allowed. Automatic resource-lock alignment, backend station-action blocking, flexible correction-reason capture/storage, optional external-number capture, first-slice manager blocked-resource warnings, completed-order release status, automatic-production hanging queue visibility, packing active-hanging visibility, and first-slice `Przemalowanka`/`Ocynk` modeling were implemented by 2026-05-31. Remaining implementation-design questions are correction-reason reporting/export surfaces, broader station/resource warning model beyond `HANGING`/`AUTOMATIC_LINE`, office/manager tab UX, external-number uniqueness/search behavior, QC document template mapping/storage, and paint inventory/stock movement model.

Open audit work:

- Multi-worker/process concurrency assumptions beyond in-process Python locks. Current evidence: queue/process actions use in-process `RLock`s plus selected DB constraints/resource-lock rows; this is not a complete durable multi-worker concurrency design for stale queue overwrites or duplicate same-order side effects. User decision 2026-05-29: single backend process is acceptable for near-term deployment. Future multi-worker support needs a durable idempotency/revision strategy before claiming multi-worker safety.
- Auth, roles, audit logging, and request traceability. Current evidence: shared station identity and `audit_events` now exist; frontend mutating API calls send `X-Station-Id`; backend records audit events for work-order creation/update, incomplete-arrival completion, attachment upload/delete, manager planning/reorder, process stage transitions, packing completion, and packing-created correction orders. `GET /audit/work-orders/{work_order_id}/events` exposes work-order-scoped audit history, and the work-order detail view displays it as non-blocking history. HTTP responses now include `X-Request-Id`, valid incoming request IDs are echoed, audit events persist the active request ID, and request logs include request ID, method, path, status, and duration. `GET /audit/events` and `GET /audit/events/export.csv` provide backend search/export by work order, event type, station, request ID, target, and created-at range; `/audyt` provides the matching read-only frontend console and CSV export link. User decision 2026-05-29: station devices should have shared station identity without personal login in the near term; personal operator login is deferred. User decision 2026-05-30: station actions should be blocked when attempted from the wrong station, and normal production does not require cross-station action overrides. Backend now rejects explicit wrong-station mutations while keeping `UNKNOWN`/`SYSTEM` as rollout compatibility identities. Remaining work: future personal actor model and permission updates for new capabilities.
- Attachment lifecycle safety under upload/delete/detail reload races. Current evidence: upload rejects spoofed PDFs and cleans failed writes; download/delete now constrain stored paths to the configured attachment root, missing files delete cleanly, and escaped stored paths cannot read/delete outside files. Remaining audit work is true concurrent upload/delete/download interleaving under deployment load.
- Historical/completed UI semantics regression audit as new UI surfaces are added. Current evidence: frontend tests cover READY work-order tables/details, manager completed rows, completed stage/packing tabs, active correction cards, historical correction delta summaries, manager correction-planning context, station attachment headers, work-order audit history rendering, correction-reason capture in packing, work-type badges, create-form work-type submission, and the audit console; frontend tests passed with `57 passed` and production build passed.

## Chaos Testing Status

- Status: IMPLEMENTED as an API-level multi-agent chaos harness in `tests/chaos/harness.py`, `tests/chaos/actors.py`, `tests/chaos/scenarios.py`, `tests/chaos/invariants.py`, and `tests/test_chaos_api.py`.
- Agents implemented:
	- `ManagerAgent`
	- `StageOperatorAgent`
	- `PackingAgent`
	- `OfficeAgent`
	- `ChaosAgent`
- Scenarios covered:
	- two managers reorder the same queue snapshot
	- stale queue payload submit after a competing reorder
	- double finish of the same stage by parallel operators
	- double-click packing completion
	- packing creates a correction while manager reorder runs in parallel
	- repeated correction split does not duplicate child creation
	- office edits an order while manager plans it
	- office marks complete-on-arrival while manager plans
	- invalid PATCH during planning
	- attachment upload/delete/detail reload race
	- manager queue-position patch collides with bulk reorder
	- office PATCH races `mark-complete-arrival` on an intake-incomplete order
	- parallel normal work-order creation and correction-child creation under API load
	- correction child planning collides with parent completion/merge-back
	- correction-child completion races another packing completion on the same parent chain
- Invariants checked:
	- no raw `500`s or other unexpected HTTP statuses
	- no duplicate work-order numbers
	- no duplicate planned `queue_position`
	- incomplete orders cannot enter the queue
	- planned orders still satisfy intake validation rules
	- rejected invalid PATCH leaves persisted office data unchanged
	- `completed_quantity <= total_quantity`
	- `READY` only when fully complete
	- correction parent/child links remain structurally valid
	- no duplicate direct correction children from the same parent
	- parent/child quantities remain conserved after packing/correction races
	- `READY` is not set while a correction child remains open
- Result: `python -m pytest tests/test_chaos_api.py` passed with `18 passed`.
- Remaining recommended chaos scenarios: none pending under the currently validated business rules.

## Closure Expectations

- A backlog item is closed only when the required fix is implemented, the required tests exist and pass, and the acceptance criteria are demonstrably true.
- Closure is based on current implementation evidence. If user/business review later changes the intended behavior, reopen or replace the item.
- Any hardening change that touches workflow, quantities, corrections, READY rules, queue behavior, or incomplete-order behavior must be checked against `docs/WORKFLOW.md` before implementation.
- Hardening work must fail invalid business actions with controlled errors rather than allowing silent corruption.

# Hardening Backlog

## Release Rule

No new features until all CRITICAL and HIGH items are closed.

This backlog is derived from the production-readiness audit. It is focused on hardening, failure containment, validation, concurrency safety, and test coverage. It does not authorize business logic changes without explicit clarification against `docs/WORKFLOW.md`.

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

- Risk: an order can leave the incomplete-on-arrival quarantine path even if its editable intake data is still inconsistent.
- Affected files: `app/work_orders/service.py`, `app/work_orders/router.py`, `tests/test_work_orders_api.py`
- Required fix: revalidate the full current work-order state before allowing `mark_complete_arrival`.
- Required tests: mark-complete-arrival tests for inconsistent office data and successful completion tests for valid data.
- Acceptance criteria: only work orders with internally consistent intake data can leave incomplete-on-arrival status.

### 8. Core business invariants are not enforced at the database level

- Status: CLOSED for Phase 1 only
- Implementation summary: safe row-local DB CHECK constraints were added in `app/work_orders/models.py` and `app/process/models.py`, and Alembic migration `20260527_0012_phase1_core_invariant_checks.py` adds them with fail-fast dirty-row prechecks before SQLite table rewrites. This closes the approved Phase 1 scope only and does not include the deferred wait-class constraints.
- Tests added: direct DB constraint coverage in `tests/test_db_constraints_phase1.py`, migration safety coverage in `tests/test_phase1_core_invariant_checks_migration.py`, and updated head coverage in `tests/test_repair_sqlite_migration_0007.py`.
- Pytest result: focused phase-1 constraint tests passed, then full `python -m pytest` passed with `195 passed`.
- Phase 2 decisions:
	- Incomplete orders not planned at DB level: DEFERRED. Keep this in service logic until incomplete-state canonicalization is simplified enough for a clean DB invariant.
	- Correction must have parent: OPEN. Still worth enforcing at the DB layer because correction orders are defined as child orders.
	- One active batch per work order: OPEN. Still worth enforcing as defense-in-depth for tracked-batch integrity.
	- `current_active_batch_id` integrity: CLOSED / not needed. Treat this as a legacy/cache pointer rather than a production DB invariant.
	- Inactive batch implies `DONE`: OPEN. Still worth enforcing to prevent invalid tracked-batch states.
	- Invalid `IN_PROGRESS` workflow shapes: CLOSED / not DB layer. These rules belong in workflow services and tests, not declarative DB constraints.

- Risk: a bug, migration issue, manual SQL change, or partial failure can leave durable invalid rows such as negative quantities, `completed_quantity > total_quantity`, invalid correction links, or invalid planning state.
- Affected files: `app/work_orders/models.py`, `app/process/models.py`, `alembic/versions/20260523_0001_initial_work_orders.py`, `alembic/versions/20260524_0002_quantity_batches.py`, `alembic/versions/20260525_0007_correction_orders.py`, `alembic/versions/20260526_0010_shared_queue_position.py`, `tests/test_repair_sqlite_migration_0007.py`
- Required fix: add database constraints for core invariants, with safe migration/backfill handling for existing data.
- Required tests: migration tests that prove invalid rows are rejected and valid existing rows migrate cleanly.
- Acceptance criteria: core quantity, correction-link, and planning invariants are enforceable even if application code regresses.
- Final note: Current state is production-hardened enough to continue feature work, but remaining OPEN Phase 2 DB constraints should be handled before broad rollout.

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

- Risk: a client can upload non-PDF content while claiming `application/pdf`, leading to invalid or unsafe attachment storage.
- Affected files: `app/work_orders/service.py`, `app/work_orders/router.py`, `tests/test_work_order_attachments_api.py`
- Required fix: validate stored attachment content as PDF before persistence.
- Required tests: attachment upload tests with fake `application/pdf` content and valid PDF content.
- Acceptance criteria: non-PDF payloads are rejected even when the client sends a PDF MIME type.

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
- Invariants checked:
	- no raw `500`s or other unexpected HTTP statuses
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
- Result: `python -m pytest tests/test_chaos_api.py` passed with `9 passed`.
- Remaining recommended chaos scenarios:
	- correction child planning collides with parent completion/merge-back
	- manager queue-position patch collides with bulk reorder on the same order set
	- correction-child completion races another packing completion on the same parent chain
	- office PATCH races `mark-complete-arrival` on an intake-invalid order
	- attachment upload/delete races against office PATCH or order detail reload
	- parallel normal work-order creation and correction-child creation mixed under load to keep allocator and numbering coverage exercised at the API level

## Closure Expectations

- A backlog item is closed only when the required fix is implemented, the required tests exist and pass, and the acceptance criteria are demonstrably true.
- Any hardening change that touches workflow, quantities, corrections, READY rules, queue behavior, or incomplete-order behavior must be checked against `docs/WORKFLOW.md` before implementation.
- Hardening work must fail invalid business actions with controlled errors rather than allowing silent corruption.

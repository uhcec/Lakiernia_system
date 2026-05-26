# Hardening Backlog

## Release Rule

No new features until all CRITICAL and HIGH items are closed.

This backlog is derived from the production-readiness audit. It is focused on hardening, failure containment, validation, concurrency safety, and test coverage. It does not authorize business logic changes without explicit clarification against `docs/WORKFLOW.md`.

## CRITICAL

### 1. Reopening finished tracked batches can corrupt quantities and READY state

- Risk: reopening a finished tracked batch can reactivate quantity that has already been counted into `completed_quantity` and may already have propagated completion to parent orders. This can break quantity conservation, READY derivation, and parent/child integrity.
- Affected files: `app/process/service.py`, `app/process/router.py`, `tests/test_process_service.py`, `tests/test_process_api.py`
- Required fix: forbid unsupported tracked-batch reopen paths or implement a full reversible rollback path that restores quantities, stage state, and correction-chain state consistently.
- Required tests: service and API tests covering reopen of finished DECORAL batches, reopen of finished correction-child batches, and reopen after completion propagation to a parent.
- Acceptance criteria: reopening a finished tracked batch either returns a controlled conflict or performs a complete reversible rollback with `completed_quantity`, active quantity, stage states, and parent/correction status all remaining consistent.

### 2. State-changing process actions are not concurrency-safe or idempotent

- Risk: duplicate requests, retries, double clicks, or parallel operators can finish the same stage twice, complete packing twice, create duplicate correction orders, or double-count completion.
- Affected files: `app/process/service.py`, `app/process/repository.py`, `app/process/router.py`, `app/database/session.py`, `tests/test_process_service.py`, `tests/test_process_api.py`
- Required fix: add backend-side protection for state-changing process operations with transaction-safe concurrency control and idempotent handling for duplicate execution.
- Required tests: parallel-request tests for duplicate `finish`, duplicate `packing/complete`, duplicate correction creation, and conflicting reopen/finish operations across separate sessions.
- Acceptance criteria: repeating the same state-changing request or running competing requests in parallel cannot create duplicate side effects, cannot corrupt quantities, and always resolves to a controlled success-or-conflict outcome.

## HIGH

### 3. Queue write conflicts can escape as raw 500 errors instead of controlled 409 conflicts

- Risk: planning and reorder operations rely on pre-checks before commit, but database uniqueness races can still happen and may surface as unhandled integrity failures.
- Affected files: `app/manager/service.py`, `app/manager/repository.py`, `app/main.py`, `alembic/versions/20260526_0010_shared_queue_position.py`, `tests/test_manager_api.py`
- Required fix: normalize database uniqueness failures from queue writes into controlled domain conflicts with stable error messages.
- Required tests: tests that simulate uniqueness failures during `assign_plan`, `update_queue_position`, and `reorder_queue` commit paths.
- Acceptance criteria: queue conflicts always return controlled conflict responses and never leak as generic 500 errors.

### 4. Queue reorder accepts stale client state and can overwrite another planner's newer order

- Risk: a stale reorder payload can fully overwrite a more recent queue arrangement from another user because the backend has no version or freshness check.
- Affected files: `app/manager/service.py`, `app/manager/router.py`, `frontend/src/pages/ManagerPanelPage.tsx`, `frontend/src/utils/queueReorder.ts`, `tests/test_manager_api.py`
- Required fix: add stale-write protection for queue reorder requests and reject reorders built from outdated queue state.
- Required tests: stale-snapshot reorder tests showing that an out-of-date client receives a controlled conflict instead of silently overwriting a newer queue.
- Acceptance criteria: reorder requests based on stale queue state are rejected with a controlled conflict, and concurrent planners cannot unknowingly undo each other.

### 5. Work order number generation is race-prone for normal and correction orders

- Risk: two concurrent creates can read the same latest order number and generate the same next sequence, causing collisions during create or during correction creation inside packing.
- Affected files: `app/work_orders/service.py`, `app/work_orders/repository.py`, `app/process/service.py`, `app/process/repository.py`, `tests/test_work_orders_api.py`, `tests/test_process_service.py`
- Required fix: make work order numbering transaction-safe under concurrency and ensure correction creation cannot fail due to duplicate generated numbers.
- Required tests: concurrent creation tests for normal work orders and concurrent correction-creation tests during packing.
- Acceptance criteria: concurrent work-order creation never produces duplicate order numbers and never leaves a partially applied packing/correction flow.

### 6. Update validation is weaker than create validation for intake fields

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

- Risk: a bug, migration issue, manual SQL change, or partial failure can leave durable invalid rows such as negative quantities, `completed_quantity > total_quantity`, invalid correction links, or invalid planning state.
- Affected files: `app/work_orders/models.py`, `app/process/models.py`, `alembic/versions/20260523_0001_initial_work_orders.py`, `alembic/versions/20260524_0002_quantity_batches.py`, `alembic/versions/20260525_0007_correction_orders.py`, `alembic/versions/20260526_0010_shared_queue_position.py`, `tests/test_repair_sqlite_migration_0007.py`
- Required fix: add database constraints for core invariants, with safe migration/backfill handling for existing data.
- Required tests: migration tests that prove invalid rows are rejected and valid existing rows migrate cleanly.
- Acceptance criteria: core quantity, correction-link, and planning invariants are enforceable even if application code regresses.

### 9. Queue UI keeps optimistic order after save failure

- Risk: the manager UI can continue showing a locally reordered queue even when the backend rejected the save, creating a false view of the real production plan.
- Affected files: `frontend/src/pages/ManagerPanelPage.tsx`, `frontend/src/api/managerApi.ts`, `frontend/src/utils/queueReorder.ts`
- Required fix: restore server truth after reorder failure or explicitly roll back the optimistic local state.
- Required tests: frontend tests where reorder save fails and the rendered queue resets to authoritative backend state.
- Acceptance criteria: after a failed reorder save, the UI does not continue to display an unsaved queue as if it were committed.

### 10. Stage screens fail hard when secondary correction-detail lookups fail

- Risk: one failed correction-detail fetch can break the entire station view even if the primary stage list loaded successfully.
- Affected files: `frontend/src/components/StageWorkOrdersPage.tsx`, `frontend/src/components/PackingWorkOrdersPage.tsx`, `frontend/src/api/processApi.ts`, `frontend/src/api/workOrdersApi.ts`
- Required fix: make secondary correction-context lookups fault-tolerant or move the required parent context into the primary stage-list response.
- Required tests: component tests where one correction detail request fails while the rest of the stage list remains usable.
- Acceptance criteria: partial data failure in correction context does not blank the whole station screen.

### 11. API error parsing is inconsistent across frontend modules

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

## Closure Expectations

- A backlog item is closed only when the required fix is implemented, the required tests exist and pass, and the acceptance criteria are demonstrably true.
- Any hardening change that touches workflow, quantities, corrections, READY rules, queue behavior, or incomplete-order behavior must be checked against `docs/WORKFLOW.md` before implementation.
- Hardening work must fail invalid business actions with controlled errors rather than allowing silent corruption.

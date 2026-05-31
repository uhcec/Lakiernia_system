# Workflow Validation Checklist

This checklist is for confirming real factory policy before changing workflow semantics. Repository docs, tests, and current code are evidence, not proof of business correctness.

Use this document as an interview guide with factory stakeholders. Do not treat unchecked assumptions as approved rules.

## Current Goal

Validate the business decisions that would affect station behavior, queueing, corrections, visibility, and future permission enforcement.

## Decision Status Legend

- `CONFIRMED`: factory policy is known and can be encoded in docs/tests/code.
- `WORKING ASSUMPTION`: current implementation or temporary policy used until confirmed.
- `OPEN`: needs user or factory decision before semantic changes.

## Questions To Answer

### 1. Automatic Line Overlap

Status: `CONFIRMED`

Confirmed factory policy from 2026-05-30:

- The next automatic order may start `HANGING` while the previous automatic order is still in automatic production or waiting for packing.
- No physical station may process multiple work orders at the same time.
- `HANGING` capacity is released when the previous order's hanging stage is finished.
- The earlier conservative assumption that one automatic order blocks the whole path until packing completion is not correct.

Current repository behavior/evidence:

- Automatic orders flow through `SURFACE_PREPARATION -> HANGING -> PACKING`.
- Automatic `PRODUCTION` currently does not use manual start/finish clicks.
- Backend resource locks allow only one active hanging job and one active automatic-line job.
- Implementation evidence from 2026-05-30 now models `HANGING` capacity separately from `AUTOMATIC_LINE` capacity: `HANGING/start` occupies hanging, `HANGING/finish` releases hanging and occupies the automatic line until packing completion.

Implementation decision needed:

- Done in the 2026-05-30 automatic-line implementation slice.
- Continue preserving one-active-work-order-at-a-time per physical station/resource as new automatic-production actions, such as paint consumption, are added.

Why this matters:

- This decides whether current resource locks are correct or too strict.
- It affects station availability, queue fairness, and whether operators see blocked work that could actually proceed.

### 2. Correction Review And Planning

Status: `CONFIRMED`

Confirmed factory policy from 2026-05-30:

- Packing with correction quantity should automatically create an unplanned correction work order.
- No defect type requires office, manager, quality-control, or customer approval before planning.
- Packing should record a correction reason/category.
- Initial coating-defect reason/category list: `niedomalowanie`, `za grubo`, `wtrącenia`, `inne`. This is not final and should remain easy to change.
- Correction reason/category is statistical/audit data only and does not affect the workflow path.
- Correction orders use the same manager planning and queue workflow as normal orders.
- Correction orders do not go through `SURFACE_PREPARATION`; manual corrections start at production, automatic corrections start at hanging.

Current repository behavior/evidence:

- Packing with `correction_quantity > 0` automatically creates an unplanned correction work order.
- Packing completion now requires `correction_reason_category` when `correction_quantity > 0`, rejects correction reasons when no correction is created, and stores the optional correction note on the child correction work order.
- Manager later assigns manual or automatic production and queue position.
- Correction children may themselves create further correction children.
- Correction orders do not go through surface preparation; after manager planning, manual corrections start at production and automatic corrections start at hanging.
- Correction orders use the same manager planning and queue-position workflow as normal orders.
- Simultaneous parent/correction completion should reconcile or behave idempotently when the final state is already valid; otherwise it should fail with a controlled conflict.

Implementation decision needed:

- Done for storage/capture: use flexible nullable text fields for category and note rather than a strict enum, because the category list is not final.
- Still open: decide where the statistical reason/category is displayed beyond work-order/read-model data and how it is exported for reporting.

Why this matters:

- This decides whether correction creation needs extra fields, approval states, or blocking rules.
- It affects audit meaning: `work_order.correction_created` may be enough now, or may need defect/approval context.

### 3. Quantity Discrepancy Visibility

Status: `CONFIRMED`

Confirmed factory policy from 2026-05-30:

- Office and manager should have the same broad process visibility.
- Office and manager should see declared-versus-counted quantity discrepancies.
- Production/station operators should not see discrepancy context; they should see only the current operational quantity.
- Quantity discrepancies should be recorded and shown to office/manager, but should not block the work order for now.
- Surface-preparation operators record the counted quantity; no separate discrepancy confirmation step is required for now.
- Starting `SURFACE_PREPARATION` must not require a counted quantity.
- Finishing `SURFACE_PREPARATION` must require the counted quantity.

Current repository behavior/evidence:

- Office enters declared client quantity.
- Surface preparation enters counted received quantity.
- Downstream validation uses the surface-preparation counted quantity as operational truth.
- Work-order and manager read models expose surface-preparation counted quantity and declared-versus-counted difference.
- Office list/detail and manager active queue show discrepancy signals when the difference is non-zero.
- Station rows keep operational quantities and do not show declared-versus-counted discrepancy context.

Implementation decision needed:

- No extra station discrepancy-confirmation UI is needed beyond counted quantity entry for now.
- No dedicated discrepancy-confirmation audit event is required unless future factory review asks for it; existing process/count audit evidence remains the current path.

Why this matters:

- This affects frontend read models, station UI copy, and audit/statistical evidence.
- It must preserve the rule that discrepancy recording is visible to office/manager without blocking the workflow for now.

### 3a. Profile And Accessory Quantity Semantics

Status: `OPEN; docs do not contradict, implementation currently differs`

Working requirement raised on 2026-05-31:

- Profile quantity and accessory quantity should not behave as independent arbitrary counts.
- A known profile/accessory quantity should be allowed to be `0` when that category is absent.
- When the category is present, the displayed quantity should match the applicable order/operational quantity instead of accepting a separate value.
- For office intake this likely means matching `total_quantity`.
- For station/correction/batch displays this may need to follow the current operational quantity for the active work context, so correction children and split batches do not show stale parent totals.
- `current_active_quantity == 0` on completed/READY orders must not be used to rewrite historical profile/accessory quantities to `0`; completed views still follow completed-state display rules.

Current repository behavior/evidence:

- Documentation only says station lists should show profile/accessory pieces to verify; it does not currently define equality with total or active quantity.
- API, Pydantic schemas, frontend validation, and DB constraints currently reject `0` for profile/accessory quantities when a value is provided.
- Existing tests and fixtures currently allow profile/accessory quantities that differ from `total_quantity`.
- Correction children currently copy profile/accessory quantities from the parent, which can make child correction quantities disagree with the child order quantity.

Implementation decision needed:

- Confirm whether the persisted intake value should be exactly `0`, `total_quantity`, or unknown/to-count.
- Confirm whether station read models should derive profile/accessory pieces from active batch/current operational quantity when the category is present.
- Confirm how correction children should inherit category presence while deriving the displayed quantity from the child correction quantity.
- Decide whether `profiles_quantity`/`accessories_quantity` remain stored quantities or become derived read-model values backed by category presence/to-count fields.

Why this matters:

- It affects intake validation, DB constraints, Alembic migrations, station read models, correction-child creation, frontend form behavior, and regression tests.
- It prevents misleading station rows such as a correction child with quantity `8` showing parent profile/accessory quantity `100`, or an order with no accessories being impossible to enter as `0`.

### 4. Station Permissions

Status: `IMPLEMENTED for current mutating workflow actions; future paint-consumption permissions pending`

Confirmed factory policy from 2026-05-30:

- Station identity should be used for audit.
- Stations should not be able to perform another station's actions.
- The UI generally should not present actions that belong to another station.
- If an invalid station action reaches the backend, it should be blocked rather than only warned/logged.
- There are no expected real cases where a station needs to perform another station's action due to staffing or device placement.

Current repository behavior/evidence:

- Shared station identity is sent with mutating frontend requests via `X-Station-Id`.
- Backend audit records the station identity for workflow-visible mutations.
- Backend rejects wrong-station mutating requests with `403` for office work-order actions, manager planning/queue actions, process stage transitions, packing completion, and completed-order release updates.
- Current regression coverage checks wrong-station rejection across surface preparation, hanging, manual production, Decoral production, packing, office, manager, and release-marker actions.
- `SYSTEM` and `UNKNOWN` station identities remain compatibility identities for legacy/system paths.

Implementation decision needed:

- Add explicit authorization for future paint-consumption actions when the paint inventory/consumption model is designed.

Expected permission direction to validate:

- `OFFICE`: create/update intake, view discrepancies, manage attachments
- `MANAGER`: assign production type, queue/reorder, view global queue
- `SURFACE_PREPARATION`: enter counted quantity, start/finish surface prep
- `HANGING`: start/finish hanging
- `AUTOMATIC_PRODUCTION`: enter paint consumption once paint inventory exists; no manual start/finish for automatic production unless separately decided
- `MANUAL_PRODUCTION`: start/finish manual production
- `PACKING`: enter counted/OK/correction quantities, complete packing
- `DECORAL_PRODUCTION`: start/finish Decoral production

Why this matters:

- Permissions turn operational habits into hard system constraints.
- Blocking the wrong action can stop production; allowing the wrong action can corrupt operator truth.

### 5. Global Queue Semantics

Status: `CONFIRMED; completed rows trail out of active planning range`

Confirmed factory policy from 2026-05-30:

- Use one shared global queue for all planned work.
- Do not split queues by manual, automatic, decoral, corrections, or stations.
- Corrections should not automatically receive higher priority than normal work orders.
- Manager queue UI should warn when a high-priority work order is blocked by a resource or station state.

Current repository behavior/evidence:

- Planned work orders share one global queue position namespace.
- Corrections start unplanned and join the global queue when manager-planned.
- Station panels filter the global queue to work actionable at that station.
- Manager planned-queue read models now expose current resource-block warnings for the exclusive resources already modeled by the backend: `HANGING` and `AUTOMATIC_LINE`.
- Manager planning should propose the next free active queue position after currently active planned work.
- Completed/READY rows stay visible in manager history but should trail after active planned work instead of permanently occupying active planning slots.

Implementation decision needed:

- Extend manager-facing blocked-work warnings if/when additional station/resource locks are modeled beyond `HANGING` and `AUTOMATIC_LINE`.
- Keep historical/audit meaning separate from active queue ergonomics: if the factory later needs immutable original priority evidence, add a dedicated history/audit field instead of overloading current `queue_position`.

Why this matters:

- The active queue remains useful for daily manager planning.
- Completed work stays visible without blocking new work from using low active positions.
- The current `queue_position` value is a live manager ordering aid, not a permanent historical priority field after completion.

### 6. Additional Work Types

Status: `IMPLEMENTED first model slice; remaining UI/reporting refinements open`

Confirmed factory policy from 2026-05-30:

- `Przemalowanka` is always a separate customer work order, not a child correction of an existing work order.
- `Przemalowanka` stays independent and does not need an original/parent work-order relationship.
- `Przemalowanka` behaves like a correction operationally: it skips `SURFACE_PREPARATION`.
- `Ocynk` is a separate work-order type/marker like a production-relevant order type, while still combinable with RAL or Decoral (`Ocynk RAL`, `Ocynk Decoral`).
- `Ocynk` follows the same stage path as other work orders, but station screens must strongly mark it as `OCYNK` because station work differs.
- Both new work types can follow RAL or Decoral paths.

Current repository behavior/evidence:

- `work_order_kind` represents independent `STANDARD` and `PRZEMALOWANKA` orders separately from packing-created corrections.
- `PRZEMALOWANKA` remains `is_correction = false`, has no parent order, stays in the main queue namespace, and skips `SURFACE_PREPARATION` after planning.
- `is_ocynk` is an independent marker that can combine with either RAL or Decoral and preserves existing route semantics.
- Office/manager/station shared badge helpers expose `PRZEMALOWANKA` and `OCYNK` labels in frontend read models.
- API, workflow-contract, migration, and frontend regression tests cover the first model slice.

Implementation decision needed:

- Extend search/report/export surfaces for `Przemalowanka` and `Ocynk` once office/manager reporting needs are clearer.
- Decide whether any dedicated `Przemalowanka` or `Ocynk` production documents/fields are needed beyond the current marker fields.

Why this matters:

- Queue semantics shape what operators believe they should do next.
- If the global queue is only a manager priority model, station panels must remain explicit about what is actionable now.

### 7. Office/Manager Tabs And Completed Release

Status: `IMPLEMENTED for office buckets; manager panel aligned with bucket counters`

Confirmed direction from 2026-05-30:

- Office/manager navigation should be organized around practical work buckets:
	- `Zlecenia`: unplanned work orders and incomplete deliveries.
	- `Na produkcji`: all active work orders currently on the factory floor.
	- `Gotowe`: completed/READY work orders.
- Completed/READY work orders should have an additional marker for whether the order was issued/released to the client.
- Issued/released state is logistics/dispatch state and should not change the production meaning of READY.

Current repository behavior/evidence:

- Completed release is stored as nullable `released_to_client_at` and exposed as `is_released_to_client` in read models.
- Release status can be marked or cleared only while `process_status = READY`.
- Office and manager station identities may update release status; production station identities are rejected.
- Release-status changes create audit events.

Implemented in session B on 2026-05-31:

- Office `/zlecenia` groups work orders into `Zlecenia`, `Na produkcji`, and `Gotowe` using backend `process_status` only.
- Manager planning keeps its planning-specific layout, but header counters now use the same practical buckets: `Zlecenia`, `Na produkcji`, and `Gotowe`.
- `READY` display remains historical/completed and release state remains separate logistics state.

Remaining design option:

- If manager and office later need different small-screen workflows, split the shared bucket labels into role-specific layouts without changing backend workflow semantics.

### 7a. Manager Planning Ergonomics And Correction Traceability

Status: `CONFIRMED for production-type assignment and correction context`

Confirmed direction from 2026-05-31:

- The manager's production-type control is for assigning manual versus automatic production during planning.
- Correction planning should expose a link to the parent/original work-order detail.
- Parent work-order detail should clearly expose linked correction orders and their current location/status.
- While planning a correction, show the original order's planned pickup date.
- Correction orders mirror the original order's planned pickup date for now.

Implementation decision needed:

- No separate correction deadline field unless the factory later wants correction deadlines to diverge from the original order.
- Keep the production-type control as assignment UI only; do not split the global queue by production type.

### 8. Station List Information Architecture

Status: `IMPLEMENTED for station table columns; details drawer still optional`

Confirmed direction from 2026-05-30:

- Station lists should show only the most operationally useful columns and move less-used data into details.
- Surface preparation: work-order number, profile pieces to verify, accessory pieces to verify, company/customer, queue position.
- Manual production: work-order number, square meters, paint, company/customer, queue position, details access for drawings.
- Hanging: work-order number, square meters, paint, company/customer, queue position, details access for drawings.
- Automatic production: work-order number, square meters, paint, company/customer, queue position, details access for drawings; it also needs visibility into automatic work that is ready for or currently in hanging, so the operator sees the day's flow before the automatic line is occupied.
- Packing: work-order number, profile pieces to verify, accessory pieces to verify, paint, company/customer, queue position; it also needs read-only visibility into active automatic hanging rows, while completion stays blocked until hanging is finished.
- Decoral production: work-order number, profile pieces to verify, accessory pieces to verify, paint, company/customer, queue position.

Implemented in session A on 2026-05-30:

- Process stage read models expose paint producer, profile/accessory quantities, and profile/accessory count flags for station lists.
- Station tables use narrower operational columns per station family instead of broad generic metadata columns.
- Station rows link to work-order details so drawings and attachments remain reachable without putting them into the main list.
- Frontend regression coverage checks station-specific columns and completed/history display safeguards.
- Packing uses per-order cards instead of a wide action table, with order facts separated from counted/OK/correction entry and read-only active hanging rows preserved.
- General station views also use per-order cards, preserving station-specific facts, read-only automatic visibility, and completed/history safeguards without the wide table layout.

Remaining design option:

- A dedicated station-side details drawer could still replace the details link if operators need faster attachment access from tablets.

### 9. Packing Station Exclusivity

Status: `OPEN`

User note from 2026-05-31:

- Packing may need to allow only one physically started work order at a time.
- The user wants to clarify this with a factory friend before implementation.

Current repository behavior/evidence:

- Packing actions are station-authorized, but there is no dedicated `PACKING` resource lock.
- Automatic orders can be visible in packing while hanging is still in progress, but those rows are read-only and cannot be completed until hanging is finished.

Implementation decision needed:

- Decide whether a `PACKING` resource lock should be added.
- Decide whether automatic rows shown in packing before completion eligibility count as occupying packing, automatic line, neither, or a separate waiting state.

Why this matters:

- Treating packing as an exclusive resource would change backend conflicts, station UI availability, and chaos/concurrency coverage.
- Implementing it before clarifying automatic waiting visibility could block legitimate work or hide useful station context.

### 10. Quality-Control Production Document

Status: `CONFIRMED with template/design needed`

Confirmed direction from 2026-05-30:

- The system should automatically generate a production quality-control document.
- The factory already has a ready document template that should be filled by the program.

Implementation decision needed:

- Obtain and store the actual template format.
- Map each template field to backend work-order/process data or mark it as manually entered.
- Decide when the document is generated and whether generated copies are stored as attachments/audit evidence.

### 11. Paint Inventory And Consumption

Status: `CONFIRMED with implementation design needed`

Confirmed direction from 2026-05-30:

- Work-order intake should force paint stock/state entry once inventory exists.
- Paint usage should be recorded so stock can be deducted.
- Automatic production is no longer display-only; the first confirmed station input is paint used/consumed, with room for additional fields after factory clarification.
- This does not automatically mean automatic production gains manual start/finish stage actions.

Implementation decision needed:

- Design paint inventory entities, stock movements, audit events, and correction/undo behavior before implementation.
- Define station permissions for paint-stock entry and paint-consumption entry.
- Clarify stock units, container/batch tracking, deduction timing, and any non-paint fields before implementing inventory semantics.

### 12. External Work-Order Number

Status: `PARTIALLY IMPLEMENTED; search/uniqueness policy still needed`

Confirmed direction from 2026-05-30:

- Add an external client/order number field separate from the system-generated internal work-order number.

Current repository behavior/evidence:

- Office intake accepts optional `external_order_number` and stores it on work orders.
- Work-order list/detail read models expose the field.
- Packing-created correction work orders inherit the parent's external number.
- No uniqueness or search/filter behavior is enforced yet.

Implementation decision needed:

- Decide uniqueness rules and search/filter behavior.
- Decide whether the external number should remain optional or become required for all office-created orders.

## Recommended Validation Session

1. Walk through one normal RAL manual order.
2. Walk through one normal RAL automatic order and decide automatic-line overlap.
3. Walk through one Decoral order.
4. Walk through one packing correction and one repeated correction.
5. Review which station can perform each action.
6. Review which users/stations should see quantity discrepancies.
7. Walk through `Przemalowanka` and `Ocynk` examples before extending their reporting/document surfaces.
8. Clarify packing station exclusivity and automatic waiting visibility.
9. Review paint inventory/consumption data model and automatic-production paint-consumption screen flow.
10. Review the quality-control document template and field mapping.

## After Decisions Are Confirmed

For each confirmed decision:

1. Update `docs/WORKFLOW.md` and `docs/FACTORY_USAGE_NOTES.md`.
2. Add or update backend service/API tests for the confirmed invariant.
3. Add frontend tests if station visibility, action availability, or completed/history display changes.
4. Implement the smallest code change that enforces the confirmed rule.
5. Run focused tests first, then the broader backend/frontend checks based on risk.
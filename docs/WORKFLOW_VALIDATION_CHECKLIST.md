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
- Surface-preparation operator confirms the discrepancy at the station where counting happens.
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

- Define the exact station UI wording for confirming a discrepancy without blocking the workflow.
- Define the audit event/details for discrepancy confirmation.

Why this matters:

- This affects frontend read models, station UI copy, and audit/statistical evidence.
- It must preserve the rule that discrepancy recording is visible to office/manager without blocking the workflow for now.

### 4. Station Permissions

Status: `CONFIRMED`

Confirmed factory policy from 2026-05-30:

- Station identity should be used for audit.
- Stations should not be able to perform another station's actions.
- The UI generally should not present actions that belong to another station.
- If an invalid station action reaches the backend, it should be blocked rather than only warned/logged.
- There are no expected real cases where a station needs to perform another station's action due to staffing or device placement.

Current repository behavior/evidence:

- Shared station identity is sent with mutating frontend requests via `X-Station-Id`.
- Backend audit records the station identity for workflow-visible mutations.
- Full permission enforcement is not enabled yet.

Implementation decision needed:

- Add backend station-action authorization and frontend action visibility rules in a focused permission hardening change.

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

Status: `CONFIRMED; resource-warning first slice implemented`

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

Implementation decision needed:

- Extend manager-facing blocked-work warnings if/when additional station/resource locks are modeled beyond `HANGING` and `AUTOMATIC_LINE`.

### 6. Additional Work Types

Status: `CONFIRMED with implementation design needed`

Confirmed factory policy from 2026-05-30:

- `Przemalowanka` is always a separate customer work order, not a child correction of an existing work order.
- `Przemalowanka` behaves like a correction operationally: it skips `SURFACE_PREPARATION`.
- `Ocynk` is a separate work-order type/marker like a production-relevant order type, while still combinable with RAL or Decoral (`Ocynk RAL`, `Ocynk Decoral`).
- `Ocynk` follows the same stage path as other work orders, but station screens must strongly mark it as `OCYNK` because station work differs.
- Both new work types can follow RAL or Decoral paths.

Implementation decision needed:

- Define the data model for a standalone work-order kind/type that can represent `Przemalowanka` and `Ocynk` without breaking existing RAL/Decoral route semantics.
- Define which station and manager/office screens show the strong `OCYNK` marker.

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

Remaining design option:

- A dedicated station-side details drawer could still replace the details link if operators need faster attachment access from tablets.

### 9. Quality-Control Production Document

Status: `CONFIRMED with template/design needed`

Confirmed direction from 2026-05-30:

- The system should automatically generate a production quality-control document.
- The factory already has a ready document template that should be filled by the program.

Implementation decision needed:

- Obtain and store the actual template format.
- Map each template field to backend work-order/process data or mark it as manually entered.
- Decide when the document is generated and whether generated copies are stored as attachments/audit evidence.

### 10. Paint Inventory And Consumption

Status: `CONFIRMED with implementation design needed`

Confirmed direction from 2026-05-30:

- Work-order intake should force paint stock/state entry once inventory exists.
- Paint usage should be recorded so stock can be deducted.
- Automatic production is no longer display-only; it should be able to enter paint consumption.
- This does not automatically mean automatic production gains manual start/finish stage actions.

Implementation decision needed:

- Design paint inventory entities, stock movements, audit events, and correction/undo behavior before implementation.
- Define station permissions for paint-stock entry and paint-consumption entry.

### 11. External Work-Order Number

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
7. Walk through `Przemalowanka` and `Ocynk` examples before implementing their data model.
8. Review paint inventory/consumption data model and automatic-production paint-consumption screen flow.
9. Review the quality-control document template and field mapping.

## After Decisions Are Confirmed

For each confirmed decision:

1. Update `docs/WORKFLOW.md` and `docs/FACTORY_USAGE_NOTES.md`.
2. Add or update backend service/API tests for the confirmed invariant.
3. Add frontend tests if station visibility, action availability, or completed/history display changes.
4. Implement the smallest code change that enforces the confirmed rule.
5. Run focused tests first, then the broader backend/frontend checks based on risk.
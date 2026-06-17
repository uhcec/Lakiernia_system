# Workflow Validation Checklist

This checklist is for confirming real factory policy before changing workflow semantics. Repository docs, tests, and current code are evidence, not proof of business correctness.

Use this document as an interview guide with factory stakeholders. Do not treat unchecked assumptions as approved rules.

## Current Goal

Validate the business decisions that would affect station behavior, queueing, corrections, visibility, and future permission enforcement.

Supporting planning notes while waiting for stakeholder answers:

- `docs/OPERATOR_USABILITY_AUDIT_PL.md` summarizes current screens by role and likely usability risks.
- `docs/FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md` maps expected factory answers to implementation, migration, UI, and test work.

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
- Initial coating-defect reason/category list: `niedomalowanie`, `za grubo`, `wtrącenia`, `inne`. The list is acceptable for now and should remain easy to change later.
- Correction reason/category is statistical/audit data only and does not affect the workflow path.
- Correction reason UI should stay simple and list-based; operators should not create arbitrary custom categories.
- Correction orders use the same manager planning and queue workflow as normal orders.
- Correction orders do not go through `SURFACE_PREPARATION`; manual corrections start at production, automatic corrections start at hanging.

Current repository behavior/evidence:

- Packing with `correction_quantity > 0` automatically creates an unplanned correction work order.
- Packing completion now requires `correction_reason_category` when `correction_quantity > 0`, rejects correction reasons when no correction is created, and stores the optional correction note on the child correction work order.
- Manager correction-reason reporting aggregates correction child orders by stored reason/category and exports the same aggregate as CSV; uncategorized legacy rows remain visible.
- Manager later assigns manual or automatic production and queue position.
- Correction children may themselves create further correction children.
- Correction orders do not go through surface preparation; after manager planning, manual corrections start at production and automatic corrections start at hanging.
- Correction orders use the same manager planning and queue-position workflow as normal orders.
- Simultaneous parent/correction completion should reconcile or behave idempotently when the final state is already valid; otherwise it should fail with a controlled conflict.

Implementation decision needed:

- Done for storage/capture: use flexible nullable text fields for category and note rather than a strict enum, because the category list may change later.
- Done for current reporting surface: manager panel displays and exports the aggregate correction-reason statistics.
- Confirmed on 2026-06-01: the current report focus by reason is enough for now; no extra percentage metric is needed now; both on-screen panel and export are desired.
- Future optional: additional report filters can be added later if the factory asks, but they are not required by the current answer.

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

Status: `IMPLEMENTED`

Requirement raised on 2026-05-31 and implemented as current system policy:

- Profile quantity and accessory quantity should not behave as independent arbitrary counts.
- A known profile/accessory quantity should be allowed to be `0` when that category is absent.
- At office intake, known profile/accessory quantities partition the order; when both are known, their sum must match `total_quantity`.
- No other quantity categories besides profiles and accessories are expected to participate in `total_quantity`.
- If the split is not known at office intake, `do policzenia na produkcji` is enough.
- Packing correction entry should capture exactly how many corrected pieces are profiles and how many are accessories; those values must sum to the total correction quantity.
- Until that is implemented, mixed profile/accessory partial contexts must not guess a category distribution.
- `current_active_quantity == 0` on completed/READY orders must not be used to rewrite historical profile/accessory quantities to `0`; completed views still follow completed-state display rules.

Implemented behavior:

- API, Pydantic schemas, frontend validation, and DB constraints now allow partitioned values such as `8 + 2 = 10`, reject known sums that do not equal `total_quantity`, and reject individual known values above `total_quantity`.
- Existing invalid known pairs are migrated to `NULL` plus `*_to_count=True` rather than preserving a false split.
- Packing completion now requires an explicit profile/accessory correction split when `correction_quantity > 0`; those values must sum to the correction quantity.
- Packing-created correction children store the exact correction split and clear both category `*_to_count` flags.
- Process/station read models show stored category counts for full-order contexts, derive binary category splits for partial contexts, and mark mixed-category partial contexts as to-count.

Implementation decision needed:

- Done for current policy: the packing UI always asks for profile/accessory correction quantities when a correction quantity is entered, regardless of the parent category mix. This avoids hidden category inference and keeps the backend contract uniform.

Why this matters:

- It affects intake validation, DB constraints, station read models, correction-child creation, frontend form behavior, and regression tests.
- It prevents misleading station rows such as a correction child with quantity `8` showing parent profile/accessory quantity `100`, or a mixed `8 profile + 2 accessory` order showing an inferred split after a partial correction.

### 4. Station Permissions

Status: `IMPLEMENTED for current station actions; auth/login redesign needed`

Confirmed factory policy from 2026-05-30:

- Station identity should be used for audit.
- Stations should not be able to perform another station's actions.
- The UI generally should not present actions that belong to another station.
- If an invalid station action reaches the backend, it should be blocked rather than only warned/logged.
- There are no expected real cases where a station needs to perform another station's action due to staffing or device placement.
- Production users should not edit work-order intake/business data; production gets station workflow actions plus read-only detail/attachment access.
- Statistics should be manager-only, not office-visible.
- Shared station identity is not enough for the target product: production should log into station contexts, while office users should have individual accounts.

Current repository behavior/evidence:

- Shared station identity is sent with mutating frontend requests via `X-Station-Id`.
- Backend audit records the station identity for workflow-visible mutations.
- Backend rejects wrong-station mutating requests with `403` for office work-order actions, manager planning/queue actions, process stage transitions, packing completion, and completed-order release updates.
- Current regression coverage checks wrong-station rejection across surface preparation, hanging, manual production, Decoral production, packing, office, manager, and release-marker actions.
- `SYSTEM` and `UNKNOWN` station identities remain compatibility identities for legacy/system paths.

Implementation decision needed:

- Extend authorization design for future shared-inventory actions such as stock receipt, stock correction, or broader paint-ledger operations.
- Design users, login/session handling, roles, manager-only statistics checks, and audit actor fields.
- Decide whether production station login identifies only the station, the operator, or both.

Expected permission direction to validate:

- `OFFICE`: individual login; create/update intake, view discrepancies, manage attachments, mark completed order as released, generate WZ when implemented
- `MANAGER`: assign production type, queue/reorder, view global queue and manager-only statistics
- `SURFACE_PREPARATION`: enter counted quantity, start/finish surface prep
- `HANGING`: start/finish hanging
- `AUTOMATIC_PRODUCTION`: enter paint consumption for automatic work in the current paint slice implementation; no manual start/finish for automatic production unless separately decided
- `MANUAL_PRODUCTION`: start/finish manual production
- `PACKING`: enter counted/OK/correction quantities, enter profile/accessory correction split, complete packing
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

Status: `PARTIALLY IMPLEMENTED; WZ generation pending`

Confirmed direction from 2026-05-30:

- Office/manager navigation should be organized around practical work buckets:
	- `Zlecenia`: unplanned work orders and incomplete deliveries.
	- `Na produkcji`: all active work orders currently on the factory floor.
	- `Gotowe`: completed/READY work orders.
- Completed/READY work orders should have an additional marker for whether the order was issued/released to the client.
- Issued/released state is logistics/dispatch state and should not change the production meaning of READY.
- Factory clarification from 2026-06-01: office marks completed orders as released to the client.
- Release marking can be undone if clicked by mistake.
- Future target: generate a WZ / issue document for completed orders.

Current repository behavior/evidence:

- Completed release is stored as nullable `released_to_client_at` and exposed as `is_released_to_client` in read models.
- Release status can be marked or cleared only while `process_status = READY`.
- Office station identity may update release status; manager and production station identities are rejected.
- Release-status changes create audit events.

Implemented in session B on 2026-05-31:

- Office `/zlecenia` groups work orders into `Zlecenia`, `Na produkcji`, and `Gotowe` using backend `process_status` only.
- Manager planning keeps its planning-specific layout, but header counters now use the same practical buckets: `Zlecenia`, `Na produkcji`, and `Gotowe`.
- `READY` display remains historical/completed and release state remains separate logistics state.
- Office-only release update is enforced by the current station-identity layer; manager can view completed/released state but cannot change it.

Implementation decision needed:

- Obtain/design WZ template and decide whether generated WZ documents are printed only or persisted.

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

Status: `IMPLEMENTED (2026-06-17)`

User note from 2026-05-31:

- Packing may need to allow only one physically started work order at a time.
- The user wants to clarify this with a factory friend before implementation.

Implementation direction confirmed on 2026-06-02:

- Add a `PACKING` resource lock in a later implementation slice.
- Treat automatic rows shown in packing before completion eligibility as visible waiting context, not as actively occupying started packing.

Implemented on 2026-06-17 (explicit-claim model, chosen by the user):

- A `PACKING` resource lock (same `ProcessResourceLock` machinery as `HANGING`/`AUTOMATIC_LINE`) holds the claim; it is the single source of truth for "which order is being packed", so the constraint survives across requests and is not frontend-inferred.
- New `start_packing` service method + `POST /process/work-orders/{id}/packing/start` (and the batch variant) acquires the claim; a second order trying to start while the station is claimed gets a controlled `409`. `complete_packing` defensively takes/confirms the claim, blocking completion of a different order while one is claimed. The claim releases automatically once packing leaves `IN_PROGRESS` (completion, or correction reset), with stale-claim recovery.
- Automatic orders only **waiting** at packing do not hold the claim (they are `IN_PROGRESS` implicitly / shown as read-only `HANGING` rows); they take it only on an explicit start. Read models expose `is_being_packed`; the packing UI shows the form only for the claimed order, a "Zajęte: pakowanie {order}" notice on others, and a "Rozpocznij pakowanie" claim button on free, packing-eligible cards.
- An explicit **release/cancel claim** action also exists: `release_packing` + `POST /process/work-orders/{id}/packing/release` (and batch variant) lets an operator who claimed the wrong order free the station without completing. It only drops the claim (no stage-status change), is idempotent, and cannot release another order's claim. UI: a "Zwolnij stanowisko" control on the claimed order's card.
- Coverage: `tests/test_packing_station_lock.py` (claim, 409 on second claim, completion blocked by another claim, release on completion, idempotent re-claim, stale recovery, automatic-waiting does-not-claim, release frees station, release idempotent / cannot steal another claim), API tests in `tests/test_process_api.py`, frontend tests in `uiStateConsistency.test.tsx` (release button, busy/claim states), and chaos scenario `two_operators_claim_same_packing_station` (exactly one 200, one 409). Docs: WORKFLOW.md "Packing station exclusivity".

Refinement CONFIRMED 2026-06-17 (factory chat) — automatic reserves packing at HANGING start:

- New rule: when an **AUTOMATIC** work order **starts HANGING**, it must **automatically reserve the packing station** and hold that reservation until its own packing completes. Rationale: the automatic line cannot be paused, so a manual order must not be able to grab packing and block an automatic order that is already on the line. Scenario given: two orders both finished surface prep (one manual, one automatic); starting hanging on the automatic one reserves packing immediately.
- Manual orders keep the **explicit "start packing" button** (already implemented) and may claim packing only when it is free; they start "when convenient" after the automatic order releases it.
- **This revises the 2026-06-02 note** ("treat automatic waiting rows as not occupying packing") and the as-built NA16 line ("automatic waiting rows do not hold the claim"; "only one physically started at a time"): for the automatic path the reservation is taken at hanging start, and (see below) packing is no longer strictly single-slot.
- **Decision 2026-06-17 — manual second-slot override:** packing is **not strictly one-at-a-time**. A manual operator may **override** and open a **second concurrent packing** when two orders can be packed at once. This turns NA16's single-station rule into a small **capacity** model (default 1, manual can open a 2nd slot). The automatic reservation still guarantees the line a slot; the manual override lets a manual order pack alongside instead of waiting.
- **Decision 2026-06-17 — second automatic:** a second automatic starting hanging while packing is reserved by another automatic **may start/finish hanging but queues for packing** (reservation in arrival order); it completes packing only after the prior automatic releases.
- Open design questions for implementation (tracked as NA22 in `IMMEDIATE_NEXT_ACTIONS.md`):
  - Max concurrent packings — cap at 2, or configurable N? (factory said "two orders").
  - Override authorization/UX — manual (`PACKING`) only; explicit button vs automatic; audit event?
  - Reservation lifecycle for the multi-slot model: automatic holds its slot from `HANGING` start through its packing completion (requires extending the packing-claim retention so an automatic reservation is kept even before packing is `IN_PROGRESS`); stale recovery per slot.
  - Frontend: manual cards show occupancy/reservation state and an explicit override action to open a second slot; a reserving automatic shows its slot as reserved.

Why this matters:

- Packing exclusivity changes backend conflicts, station UI availability, and chaos/concurrency coverage, so it needed focused implementation and regression coverage.

### 10. Quality-Control Production Document

Status: `CONFIRMED with Excel template needed before implementation`

Confirmed direction from 2026-05-30:

- The system should automatically generate a production quality-control document.
- The factory already has a ready document template that should be filled by the program.
- The template is Excel.
- Office generates the document before production.
- System-filled fields confirmed so far: internal work-order number, paint, and company/customer only.
- Generated output is for printing only; no persistence requirement is confirmed yet.

Implementation decision needed:

- Obtain the actual Excel template before implementation.
- Map exact cells to system data or mark them as manual/blank-for-print fields.
- Decide storage/update path for the template file.

### 11. Paint Inventory And Consumption

Status: `TARGET CONFIRMED for app-owned paint inventory + automatic consumption + historical work-order snapshot`

Confirmed direction from 2026-05-30:

- Work-order intake should keep paint identity on the work order.
- The application-owned paint inventory is the source of truth for current stock.
- Work-order creation should only show current stock for the selected paint; it must not reserve stock.
- Work-order intake should store a historical stock snapshot for that paint, not a live mutable balance.
- Paint usage should be recorded so stock is deducted automatically.
- Automatic production is no longer display-only; the first confirmed station input is paint used/consumed, with room for additional fields after factory clarification.
- This does not automatically mean automatic production gains manual start/finish stage actions.
- Stock unit is kilograms.
- Stock balance is aggregate per paint card, not separate tracked stock per paint batch.
- Paint receipt data should include amount, date, and optional note in the first slice.
- The first slice does not detect or report insufficient paint for an order yet.
- Stock should never be allowed to go below zero.
- Manual office adjustments are part of the first slice.
- Automatic production enters actual paint consumption manually.
- Automatic correction work should use the same paint logic as other automatic work.
- Packing should not be completable for automatic work until paint consumption is entered.

Current repository behavior/evidence:

- Current implementation stores `paint_code`, `paint_producer`, and `paint_stock_snapshot_quantity_kg` on the work order.
- The current intake form still reflects the old snapshot-only flow and must be updated to read from the app-owned paint inventory.
- Automatic-production paint consumption is recordable only by `AUTOMATIC_PRODUCTION`, once `HANGING` has started.
- The frontend records paint usage through `20 kg` / `25 kg` carton selection plus remainder in the last carton; backend stores the resulting net consumed kg.
- Standard automatic work is blocked in packing until `consumed_paint_quantity_kg > 0`.
- Automatic correction orders copy paint identity from the parent and are included in the same paint-consumption requirement before packing completion.
- Recorded consumption is not capped by the historical intake snapshot.

Remaining decisions:

- Confirm whether `ral_code + paint_producer + paint_code` is always a sufficient business identifier for one paint card.
- Confirm the operational correction path for wrongly entered automatic consumption beyond manual office stock adjustment.

### 12. External Work-Order Number

Status: `CONFIRMED and implemented for current policy`

Confirmed direction from 2026-05-30:

- Add an external client/order number field separate from the system-generated internal work-order number.
- Factory clarification from 2026-06-01: the external number is optional, not unique, may be empty, and duplicate values should simply be allowed.

Current repository behavior/evidence:

- Office intake accepts optional `external_order_number` and stores it on work orders.
- Work-order list/detail read models expose the field.
- Office work-order list supports non-unique substring search/filter by external number.
- Packing-created correction work orders inherit the parent's external number.
- No uniqueness behavior is enforced by design.

Implementation decision needed:

- None for the current policy. Future duplicate reports/search tools would be optional office ergonomics, not validation rules.

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
# Workflow Source of Truth

This document defines the current intended business workflow behavior reflected by backend services and tests. Tests are implementation evidence; they do not replace business review when requirements are unclear.

Scope:
- Work order flow by coating type and production type
- Packing, corrections, parent/child merge behavior
- Shared queue behavior
- READY status rules
- Full scenario matrix S01-S12

## Core Principles

1. `process_status` is the backend-owned authoritative workflow display value exposed by read models. It is derived from persisted quantities, stage states, correction state, planning state, and incomplete-on-arrival markers; it is not a manually edited database column.
2. `status` is a compatibility/read model field, not manually controlled workflow truth.
3. Quantity must be conserved across parent/child correction chains.
4. Packing split rules:
- `ok_quantity + correction_quantity == counted_quantity`
5. `SURFACE_PREPARATION.counted_quantity` is the persisted actual received quantity and becomes the source of truth for downstream quantity validation.
6. `PACKING.planned_quantity` remains the original expected batch quantity for audit visibility, but packing validation must use the persisted actual received quantity from surface preparation.
- `counted_quantity == actual_received_quantity` for the active batch/order at packing
- `planned_quantity - actual_received_quantity` must remain visible for audit/read models
7. When packing creates a correction child, the correction quantity is split from the actual received quantity validated at packing, not from the original expected quantity.
8. Correction is represented as a new child work order (`is_correction=true`, `parent_order_id` set).
9. Parent waits for open corrections; merge/finalization propagates upward when descendants close.

## Work Order Intake Fields

Office intake should support operational and traceability fields needed later by production, manager, and documents.

Confirmed needs:
- client-facing/external work-order number (`external_order_number`) should be captured separately from the internal system work-order number
- paint identity and paint stock state should be captured or selected at intake before planning/production
- paint stock data must not be free-floating display text only; it needs a future inventory model so production consumption can be audited and deducted safely

Open implementation design:
- `external_order_number` is optional and not unique; office list search supports non-unique substring filtering by this field
- whether `external_order_number` should become unique or required remains a factory-policy decision
- whether paint stock is stored as a snapshot on the work order, a link to an inventory batch/item, or both
- how to handle intake when the required paint exists physically but is not yet represented in the inventory module

## Stage Model

Configured stages:
- Base: `SURFACE_PREPARATION` -> `HANGING` -> `PRODUCTION` -> `PACKING`
- `DECORAL` adds: `DECORAL_PRODUCTION`

Actionable stage sequence depends on production type:
- `MANUAL`: all configured stages are actionable
- `AUTOMATIC`: `PRODUCTION` does not use manual start/finish stage actions, but the automatic production station is allowed to record paint consumption once paint inventory exists

Automatic constraints:
- Cannot start/finish `PRODUCTION` directly for `AUTOMATIC`
- Automatic production is no longer display-only: it should allow paint-consumption entry as a separate audited inventory action.
- `HANGING` start transitions automatic flow forward
- The automatic production panel must show upcoming and active automatic flow from the moment a work order is ready for `HANGING`, including `HANGING` not-started/in-progress rows, so the automatic operator sees the day's workflow before the line is occupied.
- The packing panel must show active automatic work while `HANGING` is still in progress, but as a read-only `HANGING` row. Packing completion remains blocked until `HANGING` is `DONE`.
- Finish for automatic path is performed from `PACKING`
- Physical resource exclusivity is enforced in the backend with persisted resource locks and controlled `409` responses.
- Only one `HANGING` job may be active at a time.
- Only one automatic-production job may be active at a time.
- `HANGING` capacity is released when the hanging stage is finished, so the next automatic work order may start hanging while the previous automatic order is still in automatic production or waiting for packing.
- No physical station/resource may process multiple work orders at the same time.
- Implementation note: if backend resource-lock behavior is stricter than this, it should be changed with focused tests before claiming policy alignment.

## Main Flows

### RAL + MANUAL
Flow:
- `SURFACE_PREPARATION` -> `PRODUCTION` -> `PACKING`

No correction outcome:
- `PACKING` full OK finalizes order
- Final `process_status = READY`

### RAL + AUTOMATIC
Flow:
- `SURFACE_PREPARATION` -> `HANGING` -> `PACKING`
- `PRODUCTION` is not manually started/finished during automatic flow, but the automatic production station may record paint consumption

No correction outcome:
- `PACKING` full OK finalizes order
- Final `process_status = READY`

### DECORAL + MANUAL
Flow:
- `SURFACE_PREPARATION` -> `PRODUCTION` -> `PACKING` -> `DECORAL_PRODUCTION`

No correction outcome:
- After `PACKING`, quantity moves to Decoral stage
- Order is READY only after `DECORAL_PRODUCTION` completes

### DECORAL + AUTOMATIC
Flow:
- `SURFACE_PREPARATION` -> `HANGING` -> `PACKING` -> `DECORAL_PRODUCTION`
- `PRODUCTION` is not manually started/finished during automatic flow, but the automatic production station may record paint consumption

No correction outcome:
- READY only after Decoral stage completion

## Corrections Behavior

When packing has correction quantity (`correction_quantity > 0`):
1. Parent active batch is closed at packing.
2. New child correction order is created:
- `is_correction = true`
- `parent_order_id = parent.id`
- `queue_namespace = CORRECTIONS`
- `production_type = null`, `queue_position = null` (unplanned)
3. Parent enters waiting state until all open correction descendants are completed.
4. Packing must record a correction reason/category when a correction child is created. The optional note can hold additional context from packing.
5. The reason/category is stored on the child correction work order for statistics, read models, and audit; it does not change the workflow path and does not require approval before planning.
6. Manager reporting aggregates correction child orders by stored reason/category, counting correction orders and summing their correction quantities. Legacy/uncategorized correction children remain visible as an uncategorized reporting row rather than being hidden.
7. Initial coating-defect reason/category values are `niedomalowanie`, `za grubo`, `wtrącenia`, and `inne`; the list is not final, so storage remains flexible rather than a strict database enum.

Correction planning return stage:
- Correction orders do not go through `SURFACE_PREPARATION`.
- When a correction is manager-planned, its `SURFACE_PREPARATION` stage is treated as already done.
- Child planned as `MANUAL`: first actionable station is `PRODUCTION`.
- Child planned as `AUTOMATIC`: first actionable station is `HANGING`.

Decoral split behavior:
- Parent OK part continues on `DECORAL_PRODUCTION`
- Correction quantity goes to child
- Parent is not READY while any correction child/descendant remains open

Multi-round corrections:
- Child can itself split again and create another child
- Every correction descendant follows the same rule: skip `SURFACE_PREPARATION`, then start from the manager-assigned manual or automatic route.
- Finalization/merge propagates up chain when deepest open correction closes
- After a correction is completed and merged back into its parent, it is no longer shown as an active work order.
- In completed/history views, merged corrections are shown as a historical delta (`X corrected out of Y`), not as active batch progress.

## Display & Semantics Rules

Completed/history views are historical views.

Rules:
- `COMPLETED` means historical display only.
- Work-order detail pages are historical views when `process_status = READY`.
- Display correctness requires both correct labels and correct authoritative numbers.
- Never show `Postęp partii` in completed/history views.
- Never show `Postęp`, `Aktywne`, or `current_active_quantity` summaries in READY work-order detail views.
- Never show active batch progress in completed/history views.
- Never use `current_active_quantity` as a historical progress surrogate.
- Completed/history rows must show persisted historical planned and final quantities for that stage and must never replace them with zeroed live quantities.
- Never render misleading `0 / X` progress in completed/history views.

Completed normal work orders:
- Show final completed result only.
- Do not render active-process progress language.

Completed merged corrections:
- Show only the historical delta summary.
- Use the display form `Poprawiono X z Y szt.` when parent quantity is known.
- Do not render batch progress, `current_active_quantity`, or `0 / X` summaries.
- Backend read models, including correction relation summaries, must expose `is_historical_correction`; frontend must not infer historical correction state from quantities or statuses.

Active views:
- Continue to show in-progress batch progress while the backend still marks the row as active/in-progress.
- A correction row may still show batch progress in a completed tab until the backend marks it as historical via `is_historical_correction`.

Office/manager list grouping:
- `Zlecenia`: unplanned work orders and incomplete deliveries.
- `Na produkcji`: all work orders currently active/on the factory floor.
- `Gotowe`: completed/READY work orders.
- Completed work orders have an issued/released marker showing whether the completed order has been handed over/released to the client.
- The marker is stored as `released_to_client_at`; `is_released_to_client` is derived for read models.
- Release can be marked or cleared only for `READY` work orders. This is logistics/dispatch state and must not change the production meaning of READY.
- Office and manager station identities may update the marker; production station identities may not.

Manager planning ergonomics:
- Manager planning assigns `production_type` explicitly as manual or automatic production. A switch/segmented control is a UI affordance for that assignment; it must not create separate queues.
- Correction work orders in manager planning must make the original/parent order easy to open.
- Parent work-order details must make it easy to see which correction orders belong to the parent and where each correction currently is.
- While planning a correction, the manager should see the original order's planned pickup date. Current correction orders mirror the original order's `planned_pickup_date`; if future policy allows separate correction deadlines, that must be a separate workflow decision.

Station list display should be tailored to the station and move lower-priority data into details.

Surface preparation list columns:
- work-order number
- profile pieces to verify
- accessory pieces to verify
- company/customer
- queue position

Manual production list columns:
- work-order number
- square meters
- paint
- company/customer
- queue position
- details access for drawings/attachments

Hanging list columns:
- work-order number
- square meters
- paint
- company/customer
- queue position
- details access for drawings/attachments

Automatic production list columns:
- work-order number
- square meters
- paint
- company/customer
- queue position
- details access for drawings/attachments

Packing list columns:
- work-order number
- profile pieces to verify
- accessory pieces to verify
- paint
- company/customer
- queue position
- active automatic `HANGING` rows as read-only waiting-for-packing visibility

Open packing resource decision:
- The factory may want only one physically started packing work order at a time.
- This is not yet encoded as a backend `PACKING` resource lock because it needs clarification, especially for automatic orders that are visible in packing while hanging or automatic flow is still active.

Decoral production list columns:
- work-order number
- profile pieces to verify
- accessory pieces to verify
- paint
- company/customer
- queue position

## Shared Queue Rule (Global)

Queue position is global for all planned work orders.

Rules:
1. Planned order requires unique `queue_position` globally.
2. This uniqueness is not namespace-scoped.
3. Correction orders start unplanned (`queue_position = null`), then when planned they join the same global queue uniqueness rule.
4. Reorder payload must also preserve unique positions.
5. Reorder payload must include the queue revision from the manager snapshot it was built from.
6. If the queue revision is stale, reorder must fail with a controlled `409` error.
7. Queue uniqueness conflicts, including database-level uniqueness collisions during concurrent writes, must fail with a controlled `409` error and must never surface as a raw `500`.
8. Two managers must not be able to silently overwrite each other's queue reorder using stale data.
9. Corrections do not receive automatic priority over normal work orders.
10. Manager views should warn when a globally high-priority item is blocked by resource or station state, without splitting the global queue.
11. Current manager queue warnings cover the exclusive resources currently modeled by backend locks/conflict checks: `HANGING` and `AUTOMATIC_LINE`. They are read-only visibility and do not change queue order or station-action authorization.
12. Manager planning should default a new order's proposed queue position to the next slot after active planned work. This is an ergonomics/defaulting rule, not permission to split the global queue.
13. Completed/READY orders are historical in manager queue views and must not permanently block active planning slots.
14. When manager planning or queue-position updates need active slots, completed/READY rows should move to trailing queue positions after active planned work.
15. A completed/READY row may keep a `queue_position` for manager sorting and historical visibility, but that value is not an immutable record of the row's original active priority.

## Station Permissions

Shared station identity is both audit context and an authorization input.

Rules:
- Frontend station panels should not show actions belonging to other stations.
- Backend must reject state-changing actions sent from a station that is not allowed to perform them.
- Station-action restrictions should be explicit and tested before rollout.
- There are no expected normal-production cases where one station needs to perform another station's action.

Current enforcement:
- Wrong-station mutating requests return `403` for current office, manager, process, packing, and completed-release actions.
- `SYSTEM` and `UNKNOWN` remain compatibility station identities for legacy/system paths.
- Station-origin links to work-order details preserve the source station identity. Detail pages reached from production stations are read-only for office/manager mutations while keeping drawings/attachments downloadable.
- Future paint-consumption actions must define their own allowed station rules when the paint inventory model is added.

## Quantity Discrepancy Visibility

Rules:
- Office and manager should see declared client quantity, surface-preparation counted quantity, and their difference.
- Production/station operators should see only the current operational quantity they need to process.
- Quantity discrepancies should be recorded and visible to office/manager, but should not block the work order for now.
- Surface-preparation operators record the counted quantity where counting happens; no separate discrepancy confirmation step is required for now.
- Starting `SURFACE_PREPARATION` does not require counted quantity.
- Finishing `SURFACE_PREPARATION` requires counted quantity.

## Profile And Accessory Quantity Semantics

Rules:
- Profile quantity and accessory quantity are category quantities, not arbitrary independent counts.
- At office intake, a known profile/accessory quantity must be either `0` when that category is absent or equal to `total_quantity` when that category is present.
- A category that still needs counting uses the existing `*_to_count` flag with a `NULL` quantity; it must not also carry a numeric quantity.
- Station read models must display the applicable operational quantity for present categories, using active batch/current stage quantity rather than stale parent totals.
- Correction children inherit category presence from the parent, but their known present category quantity is derived from the correction child quantity.
- Completed/READY rows must not derive category quantities from `current_active_quantity == 0`; historical display remains governed by completed-state display rules.

Current enforcement:
- API and frontend intake validation reject known profile/accessory values other than `0` or `total_quantity`.
- DB constraints allow only `NULL`, `0`, or `total_quantity` for persisted profile/accessory quantities.
- Packing-created correction children convert present parent category quantities to the child correction quantity and preserve absent categories as `0`.
- Process/station read models derive displayed profile/accessory quantities from the active stage or batch quantity when the category is present.

## Additional Work Types

Confirmed concepts:
- `Przemalowanka` is always a separate independent customer work order, not a child or parent-linked order. It behaves like a correction operationally and skips `SURFACE_PREPARATION`.
- `Ocynk` is a separate production-relevant work-order type/marker that can combine with RAL or Decoral. It follows the normal stage path but must be strongly marked as `OCYNK` because station work differs.
- Both may follow RAL or Decoral downstream paths.

Current enforcement:
- `work_order_kind` distinguishes normal independent work orders from `PRZEMALOWANKA` without using `is_correction` or parent links.
- `PRZEMALOWANKA` work orders stay in the main queue namespace and omit `SURFACE_PREPARATION` from their workflow sequence.
- `is_ocynk` is an independent marker and does not change RAL/Decoral routing.
- Packing-created correction orders remain correction children and retain existing correction semantics; they are not modeled as `PRZEMALOWANKA`.

Remaining design work: reporting/search/document surfaces for these work types are still open beyond current model fields and frontend markers.

## Quality Control Production Document

The system should generate a production quality-control document from a provided factory template.

Confirmed need:
- the document should be generated automatically from work-order/process data where possible
- the factory already has a document template that should drive the generated output instead of inventing a new format

Open implementation design:
- template file format and storage location
- exact data fields to fill from the system
- whether generation happens at intake, production start, completion, or on demand
- whether generated documents are stored as attachments/audit evidence or regenerated from current data

## Paint Inventory And Consumption

Paint stock management is a required future workflow area, but it needs a dedicated data model before implementation.

Confirmed non-conflicting needs:
- paint stock state should be required during order intake/planning
- production paint consumption should reduce paint stock through an audited system action
- automatic production is allowed to enter paint used/consumed; it is no longer a display-only panel

Open implementation design:
- define paint inventory entities, stock movement rules, audit events, and correction/undo behavior before code changes
- clarify stock units, container/batch tracking, deduction timing, and any additional automatic-production fields before implementing inventory semantics
- keep the automatic `PRODUCTION` stage transition model separate from paint consumption: automatic production should not gain manual production start/finish unless separately decided

## Process Action Safety

### Idempotency

State-changing process actions must be idempotent.

Rules:
1. Repeating the same action, including packing completion and stage finish, must not apply effects twice.
2. If the requested action has already been completed, the system must return either success or another controlled response without changing state again.
3. Repeated packing completion must not create duplicate correction orders.

### Concurrency

State-changing process actions must be safe under parallel requests.

Assume:
- multiple operators
- double clicks
- client retries
- overlapping requests for the same stage or batch

Rules:
1. Only one request can successfully mutate a given stage or tracked batch at a time.
2. Other concurrent requests for the same mutation must either be ignored as idempotent repeats or be rejected with a controlled `409` error.
3. Parallel requests must never leave partially duplicated side effects.
4. For correction-chain completion races, prefer idempotent success or automatic reconciliation when the final persisted parent/child quantities and READY state are already equivalent and valid. Use a controlled conflict only when the requested action cannot be safely applied to the current state.

### Guarantees

The system must guarantee all of the following for duplicate or parallel process actions:
- quantities can never be applied twice
- a stage cannot transition twice from the same logical action
- a correction child cannot be created twice for the same packing split
- READY state must not be changed by duplicate actions

## READY Rules

A work order is READY only when all are true:
1. `completed_quantity == total_quantity`
2. `current_active_quantity == 0`
3. No open correction children/descendants remain
4. The order is not marked incomplete on arrival

Tracked batch reopen rule:
- Finished/DONE tracked batches can never be reopened.
- Any reopen attempt for a finished tracked batch must fail with a controlled `409` error.
- A rejected reopen attempt must not change quantities, READY state, parent/child state, or completed progress.

Additional completion behavior:
- If correction descendants are completed and no active quantity remains, completion can finalize upward through parent chain.
- Parent remains non-READY while any correction descendant is still open.
- Parent and correction completion actions may overlap; the backend must either reconcile to the same valid final state or reject stale impossible actions with a controlled response.

## Scenario Matrix S01-S12

| Scenario | Coating | Production | Correction mode | Expected stage path | Final status | Final quantities | Parent/child behavior |
|---|---|---|---|---|---|---|---|
| S01 | RAL | MANUAL | none | SURFACE_PREPARATION -> PRODUCTION -> PACKING | READY | parent completed=Q, active=0 | no child |
| S02 | RAL | AUTOMATIC | none | SURFACE_PREPARATION -> HANGING -> PACKING (PRODUCTION preview) | READY | parent completed=Q, active=0 | no child |
| S03 | DECORAL | MANUAL | none | SURFACE_PREPARATION -> PRODUCTION -> PACKING -> DECORAL_PRODUCTION | READY | parent completed=Q, active=0 | no child |
| S04 | DECORAL | AUTOMATIC | none | SURFACE_PREPARATION -> HANGING -> PACKING -> DECORAL_PRODUCTION (PRODUCTION preview) | READY | parent completed=Q, active=0 | no child |
| S05 | RAL | MANUAL | correction after packing | parent: ... -> PACKING, child: PRODUCTION -> PACKING | READY after child closes | parent final completed=Q; child completed=C | parent waits for child; child created unplanned |
| S06 | RAL | AUTOMATIC | correction after packing | parent: ... -> PACKING, child: HANGING -> PACKING | READY after child closes | parent final completed=Q; child completed=C | automatic return via HANGING |
| S07 | DECORAL | MANUAL | correction after packing | parent: ... -> PACKING -> DECORAL_PRODUCTION(ok); child: PRODUCTION -> PACKING -> DECORAL_PRODUCTION | READY after parent ok-part and child close | parent final completed=Q | parent keeps Decoral OK batch; child handles correction qty |
| S08 | DECORAL | AUTOMATIC | correction after packing | parent: ... -> PACKING -> DECORAL_PRODUCTION(ok); child: HANGING -> PACKING -> DECORAL_PRODUCTION | READY after both close | parent final completed=Q | same as S07 + automatic child path |
| S09 | RAL | MANUAL | multi-round correction | parent split -> child split -> deeper child close | READY after chain closes | root parent completed=Q | recursive merge propagation upward |
| S10 | RAL | AUTOMATIC | multi-round correction | automatic variant of S09 (child return via HANGING) | READY after chain closes | root parent completed=Q | recursive merge with automatic return behavior |
| S11 | DECORAL | MANUAL | multi-round correction | dec + manual multi-round: each open branch requires Decoral completion | READY after all descendants close | root parent completed=Q | parent blocked until full descendant closure |
| S12 | DECORAL | AUTOMATIC | multi-round correction | dec + automatic multi-round with HANGING return and Decoral completion | READY after all descendants close | root parent completed=Q | combines automatic rules + dec + recursive merge |

## Test Alignment

The behavior above is exercised by existing and newly added tests in:
- `tests/test_process_service.py`
- `tests/test_process_api.py`
- `tests/test_manager_api.py`
- `tests/test_work_orders_api.py`

These tests are regression evidence, not a substitute for business validation. This document should be updated whenever workflow behavior changes in services or tests.

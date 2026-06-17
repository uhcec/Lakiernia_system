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
8. Correction representation depends on coating type (see Corrections Behavior): RAL resets the same order back to planning with a `CORRECTION` quantity batch; DECORAL creates a child correction work order (`is_correction=true`, `parent_order_id` set).
9. Parent waits for open corrections; merge/finalization propagates upward when descendants close.

## Work Order Intake Fields

Office intake should support operational and traceability fields needed later by production, manager, and documents.

Confirmed needs:
- client-facing/external work-order number (`external_order_number`) is captured separately from the internal system work-order number
- `external_order_number` is optional, not unique, and duplicate values should be allowed without warning or blocking
- paint identity and a paint stock snapshot or stock reference should be captured at intake before planning/production
- the office-entered paint quantity currently means only the stock snapshot seen at intake, not work-order demand and not a live warehouse balance

Open implementation design:
- whether the work-order stock snapshot later links to a shared inventory batch/item model if this app ever grows into real warehouse tracking
- how to handle intake when the required paint exists physically but is not yet represented in the future inventory module

## Stage Model

Configured stages:
- Base: `SURFACE_PREPARATION` -> `HANGING` -> `PRODUCTION` -> `PACKING`
- `DECORAL` adds: `DECORAL_PRODUCTION`

Actionable stage sequence depends on production type:
- `MANUAL`: all configured stages are actionable
- `AUTOMATIC`: `PRODUCTION` does not use manual start/finish stage actions, but the automatic production station is allowed to record paint consumption through the current paint-allocation slice

Automatic constraints:
- Cannot start/finish `PRODUCTION` directly for `AUTOMATIC`
- Automatic production is no longer display-only: it should allow paint-consumption entry as a separate audited paint-consumption action.
- `HANGING` start transitions automatic flow forward
- The automatic production panel must show upcoming and active automatic flow from the moment a work order is ready for `HANGING`, including `HANGING` not-started/in-progress rows, so the automatic operator sees the day's workflow before the line is occupied.
- The packing panel must show active automatic work while `HANGING` is still in progress, but as a read-only `HANGING` row. Packing completion remains blocked until `HANGING` is `DONE`.
- Finish for automatic path is performed from `PACKING`
- Physical resource exclusivity is enforced in the backend with persisted resource locks and controlled `409` responses.
- Only one `HANGING` job may be active at a time.
- Only one automatic-production job may be active at a time.
- Only one work order may be physically started at the packing station at a time (`PACKING` lock; see "Packing station exclusivity" below).
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

When packing has correction quantity (`correction_quantity > 0`), the representation depends on coating
type. Both paths conserve quantity, skip `SURFACE_PREPARATION`, and rejoin the global queue only after
manager planning.

RAL (packing is the last stage):
1. The OK quantity is added to `completed_quantity` and the active batch is closed.
2. The same work order is reset to planning (`production_type = null`, `queue_position = null`) with a new
`CORRECTION` quantity batch (`parent_batch_id` set) carrying the correction quantity. No child work order
is created. The correction reason/category and profile/accessory split are stored on that `CORRECTION` batch.

DECORAL (a Decoral stage still follows packing):
1. The OK quantity continues on the root order's single Decoral pass (as a tracked batch).
2. A child correction work order is created:
- `is_correction = true`
- `parent_order_id = root.id`
- `queue_namespace = CORRECTIONS`
- `production_type = null`, `queue_position = null` (unplanned)
The correction reason/category and profile/accessory split are stored on the child work order, and the
parent shows the `N` (decoral-incomplete) marker until corrections return.

Common rules:
3. Parent/root enters a waiting state until all open correction descendants are completed.
4. Packing must record a correction reason/category whenever `correction_quantity > 0`. The optional note can hold additional context from packing.
5. The reason/category does not change the workflow path and does not require approval before planning.
6. Manager reporting aggregates corrections by stored reason/category from both sources — `CORRECTION` batches (RAL) and child correction orders (DECORAL) — counting correction events and summing their quantities. Legacy/uncategorized corrections remain visible as an uncategorized reporting row rather than being hidden.
7. Initial coating-defect reason/category values are `niedomalowanie`, `za grubo`, `wtrącenia`, and `inne`; the list is acceptable for now, should remain simple in the UI, and may change later.
8. The correction reason UI should not allow arbitrary custom categories. Storage may remain flexible for compatibility and future category changes, but operator entry should stay list-based.
9. Packing correction entry should capture how many corrected pieces are profiles and how many are accessories. Those category correction quantities must sum to `correction_quantity` and must not introduce categories beyond profiles/accessories.

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
- RAL repeats the in-place batch reset on the same order for each round (a new `CORRECTION` batch per round); DECORAL children can themselves split again and create another child
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
- Office marks or clears completed-order release. Manager and production station identities may not update the marker.
- Future release flow should generate a WZ / issue document for completed orders; the WZ template, fields, storage, and print/download behavior still need separate design.

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

Packing station exclusivity (`PACKING` resource lock):
- Only one work order may be physically *started* at packing at a time. This is enforced by a backend `PACKING` resource lock (same machinery as `HANGING`/`AUTOMATIC_LINE`), so the claim survives across requests and is not frontend-inferred.
- An operator claims the station with an explicit **start packing** action (`POST /process/work-orders/{id}/packing/start`). It acquires the lock; a second order attempting to start while the station is claimed gets a controlled `409`.
- Completion (`/packing/complete`) also defensively takes/confirms the claim, so a different order cannot be completed while the station is claimed by another. The claim is released automatically once packing leaves `IN_PROGRESS` (completed, or reset to planning by a correction). An operator who claimed the wrong order can free the station without completing via **release** (`POST /process/work-orders/{id}/packing/release`); it only drops the claim (no stage-status change) and is idempotent and cannot release another order's claim. Stale claims (owner no longer packing) are recovered on the next claim.
- The claim is distinct from the `PACKING` stage status: automatic orders that are only **waiting** at packing (already `IN_PROGRESS` implicitly after `HANGING` finishes, or shown as read-only `HANGING` rows) do **not** hold the lock — they are visible waiting context, not actively occupying packing. They hold the lock only after an explicit start.
- Read models expose `is_being_packed` for the work order that currently holds the claim; the packing UI shows the entry form (plus a "Zwolnij stanowisko" release control) only for that order, a "Zajęte: pakowanie {order}" notice on the others, and a "Rozpocznij pakowanie" claim button on free, packing-eligible cards.

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

Authorization is derived from the authenticated user's role (`station_id`/`is_admin`). Station identity remains the audit context for "where/who performed the action".

Rules:
- Frontend station panels should not show actions belonging to other stations.
- Backend must reject state-changing actions sent from a station that is not allowed to perform them.
- Station-action restrictions should be explicit and tested before rollout.
- There are no expected normal-production cases where one station needs to perform another station's action.
- Production users should not edit work-order intake/business data; production access is limited to station workflow actions and read-only detail/attachment access.
- Statistics should be manager-only.
- The current shared station identity model is not the final access model. Factory policy now requires login: production logs into station contexts, while office users need individual accounts.

Current enforcement:
- Wrong-role mutating requests return `403` for current office, manager, process, packing, and completed-release actions, **derived from the authenticated user's role** (NA1).
- Statistics (`/manager/stats/throughput`, `/manager/corrections/reason-report[/export.csv]`) require manager/admin.
- `SYSTEM` (internal/seed callers, passed as no station context) remains the trusted identity; admins bypass station checks. `UNKNOWN` is no longer an allow-bypass — a request with an unknown/unauthorized role is denied.
- Station-origin links to work-order details preserve the source station identity. Detail pages reached from production stations are read-only for office/manager mutations while keeping drawings/attachments downloadable.
- Current automatic paint-consumption action is restricted to `AUTOMATIC_PRODUCTION`; future shared inventory or stock-receipt actions still need their own allowed-station rules.
- Authentication and authorization now both come from the JWT-authenticated user: user accounts, login sessions, and JWTs are required on all business endpoints, and authorization is derived from the user's `station_id`/`is_admin`, not the `X-Station-Id` header (NA1 closed; the header is now inert server-side). Open auth follow-ups: token expiry (NA6) and audit actor fields — see `IMMEDIATE_NEXT_ACTIONS.md`.

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
- At office intake, known profile/accessory quantities partition the order: `profiles_quantity + accessories_quantity` must equal `total_quantity` when both quantities are known.
- A known individual category quantity may be `0`, but it must not exceed `total_quantity`.
- A category that still needs counting uses the existing `*_to_count` flag with a `NULL` quantity; it must not also carry a numeric quantity.
- Station read models must display known category quantities for full-order contexts, and must not invent a category split for partial active batches/corrections when both categories are present.
- Packing explicitly collects profile/accessory correction quantities when `correction_quantity > 0`, so correction children preserve the exact corrected category split instead of guessing.
- Completed/READY rows must not derive category quantities from `current_active_quantity == 0`; historical display remains governed by completed-state display rules.

Current enforcement:
- API and frontend intake validation reject known profile/accessory sums that do not match `total_quantity`, and reject individual known values above `total_quantity`.
- DB constraints allow only `NULL` or values from `0` through `total_quantity`, and require known profile/accessory pairs to sum to `total_quantity`.
- Packing completion requests require `correction_profiles_quantity + correction_accessories_quantity == correction_quantity` when correction quantity is greater than zero, and reject category correction quantities when no correction is created.
- Packing-created correction children store the explicit profile/accessory correction split with both category `*_to_count` flags cleared.
- Process/station read models show stored category counts for full-order contexts, derive binary category splits for partial contexts, and mark mixed-category partial contexts as to-count.

## Throughput Reporting (Statystyki / Przepustowość)

Manager statistics (`/manager/stats/throughput`, station MANAGER/admin only) report processed area
and corrections per period (day/week/month), keyed by the date a stage event occurs:

**Two coats, two separate work events (the Decoral model).** A RAL order receives one coat of RAL
paint, runs through the stages, and ends at `PACKING` — that packing event is the RAL coat. A DECORAL
order receives a **RAL base coat first** (it goes through the *same* stages as a RAL order and also
ends at `PACKING`), and **then** a **separate Decoral coating** is applied on the `DECORAL_PRODUCTION`
stage *after* packing. Because both coats cover the *same physical parts*, the area in m² is **identical
for both coats** — but they are **two distinct processing events** (different stage, different date,
possibly a different line) and must be counted separately. The Decoral pass is an **additional**
counter, never a re-slice of the base throughput.

- **m² by production type (base coat).** Base-production throughput is split purely by `production_type`:
  `m2_manual` = all orders with `production_type = MANUAL`, `m2_automatic` = all with `AUTOMATIC`,
  regardless of coating. A DECORAL order's RAL base coat therefore counts toward manual/automatic
  exactly like a RAL order — this is intended (confirmed 2026-06-17) — so
  `m2_manual + m2_automatic = m2_total` (every produced order has one production type).
- **Base-coat m² is attributed at PACKING completion** (`PACKING` stage `DONE` date), using
  `total_area_m2`. Orders without a filled `total_area_m2` are excluded from m² and surfaced as a
  separate count. The completion date comes from the append-only **stage-transition log**
  (`stage_transition_events`, latest `PACKING`→`DONE` `occurred_at`) — a durable timestamp that is
  never overwritten — falling back to the `PACKING` stage state's `updated_at` for orders packed
  before the log existed.
- **Decoral-pass throughput is a separate, additional counter** (confirmed 2026-06-17), keyed on the
  `DECORAL_PRODUCTION` stage `DONE` date and using the same `total_area_m2` (same parts → same area as
  the base coat). It is never added into manual/automatic and is not a subset of them — it is its own
  series for the Decoral line's daily output, and it does **not** add into `m2_total` (which is the
  base-coat total). `m2_decoral` is computed from the stage-transition log (latest
  `DECORAL_PRODUCTION`→`DONE` `occurred_at`) for non-correction orders, exactly like the base-coat
  attribution but at the pass moment. There is no `updated_at` fallback for this series — the pass date
  is only reliable from the log, so passes completed before the log existed do not appear (this
  intentionally replaced the earlier packing-time approximation). The Statystyki page renders it as its
  own "Przejazd Decoral — m² / dzień" bar chart and the "m² Decoral (przejazd)" table column.
- **Corrections** are counted from **both** correction sources of the hybrid model (same as
  `list_correction_reason_report`, so the chart and the reason report agree): `CORRECTION` quantity
  batches (RAL packing / DECORAL decoral-stage resets) **plus** child correction work orders
  (`is_correction = true`, DECORAL packing). Each is keyed by its own `created_at`; `correction_pieces`
  sums batch `quantity` + child `total_quantity`, `correction_orders_count` counts the correction
  events. The two sources are disjoint, so there is no double counting. (Counting only child orders
  would undercount RAL corrections — historical bug NA4.)
- The frontend renders per-day bar charts (automatic m², manual m², correction pieces) plus a detail
  table; it must not re-derive these buckets locally beyond zero-filling missing days in the range.

### Stage-transition log (analytics foundation)

`stage_transition_events` is an **append-only** record of every meaningful stage transition: stage,
new status, `occurred_at`, work order, batch, counted quantity, station, and (nullable) user. It
exists because `work_order_stage_states` keeps only the latest `updated_at`, which is overwritten on
every change and cannot reconstruct history. Rows are written wherever audit events are emitted for
transitions (stage start/finish/reopen, packing completion, decoral-pass completion), plus the
automatic implicit transitions (PRODUCTION/PACKING set to IN_PROGRESS when automatic HANGING finishes,
and the automatic PRODUCTION→DONE at packing). Internal correction-reset/merge state changes (e.g.
reopening the root Decoral pass when a correction child returns) are not individually logged; the
following normal finish re-logs the DONE, so analytics stay correct. The log is the source for
time-based statistics (cycle time per stage, queue wait,
bottlenecks, per-day throughput) and lets new metrics be added without changing the workflow. The
`user_id` column is populated only once stations have personal operator login (today it records the
shared station account, or NULL for internal/seed actions).

### Stage cycle-time / bottleneck stats

`ManagerService.get_cycle_time_stats` (manager/admin only, `GET /manager/stats/cycle-time`) is the
first time-in-stage read off the log. Definitions:

- **Cohort:** non-correction work orders whose latest `PACKING`→`DONE` falls in `[date_from, date_to]`
  — the same "completed in window" cohort as throughput.
- **Per-stage active time:** for each order and stage, the gap from the latest `IN_PROGRESS` to the
  latest `DONE` (at or after it) of that stage — i.e. the **most recent completed pass**, so a
  correction re-run reports the final pass rather than a sum. Reported per stage as an average across
  the cohort orders that have that stage, with the contributing `orders_count`.
- **Queue wait before a stage** (`average_wait_before_seconds`, `wait_orders_count`): per order, the gap
  from the most recent stage that **finished before this stage started** to this stage's start. Keying off
  "the last stage that actually completed before the start" (rather than the workflow's nominal order)
  keeps it well-defined for automatic flows, where `PRODUCTION`/`PACKING` start implicitly at hanging
  finish. The first stage has no wait (`null`). Averaged across the cohort orders that have a wait.
- **Overall lead time** (`overall_average_seconds`): per order, the earliest stage `IN_PROGRESS` to the
  packing `DONE`, averaged across the cohort.
- Stages are returned in canonical workflow order with Polish labels. The Statystyki page renders a
  "Czasy etapów" section (average work-time-per-stage and wait-before-stage bar charts, a headline
  lead-time figure, and a table). This is bottleneck visibility only; it never changes workflow or queue
  behavior.

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
- the template format is Excel
- office generates the document before production
- the generated document should contain only the internal work-order number, paint, and company/customer from the system unless the provided template proves otherwise
- generated copies are for printing only; the system does not need to persist every filled copy as an attachment unless a later audit/storage rule changes this

Open implementation design:
- obtain the real Excel template and map concrete cells/fields before implementation
- decide where the template file is stored and who may update it
- confirm how manual/signature fields in the template should remain blank for printing

## Paint Inventory And Consumption

The target paint slice uses an application-owned paint inventory plus historical work-order snapshots.

Confirmed non-conflicting needs:
- paint stock unit is kilograms
- paint identity belongs on the work order
- the paint inventory inside this application becomes the source of truth for current stock balance
- office intake stores a historical snapshot of the current paint stock seen at the moment the work order is entered
- office intake requires `total_area_m2`; work-order creation should be blocked until area is provided
- work-order read models expose a predicted paint demand derived from `total_area_m2` for planning visibility only; it does not reserve stock and does not replace real consumed paint
- predicted paint demand formula is `total_area_m2 / 4` when the order is below `100 m2`, and `total_area_m2 / 6` when the order is at least `100 m2`; the displayed planning value is rounded to whole kilograms
- office intake should warn when the rounded predicted paint demand is greater than the current paint stock, so the operator knows the paint will not be enough and must be ordered
- work-order creation only shows current stock for the selected paint; it does not reserve stock
- automatic production records actual paint consumption manually; manual production is not currently confirmed to record paint consumption
- automatic paint corrections consume stock the same way as standard automatic work
- automatic production enters paint usage in carton workflow terms: the operator chooses carton size (`20 kg` or `25 kg`), adds how many cartons were taken, and enters how much remained in the final carton
- the carton workflow is converted into net consumed paint for the work order as `taken cartons * carton size - remaining paint in the final carton`
- automatic production may start entering paint consumption once `HANGING` has started; it does not need to wait for `HANGING` to finish
- packing completion for automatic work should be blocked until required paint consumption has been entered, so departments remind each other to complete the required production data
- automatic correction work follows the same consumption requirement as standard automatic work
- recorded consumption stays audited and updates live stock balance when saved
- current stock must not be allowed to go below zero
- work-order detail must preserve historical paint identity and intake snapshot even if the paint card changes later
- the first inventory slice supports deliveries, automatic-production consumption, and manual office adjustments
- the first inventory slice does not support batch/lot accounting, reservations, or shortage alerts based on work-order demand
- automatic production is allowed to enter paint used/consumed; it is no longer a display-only panel

Open implementation design:
- whether `ral_code + paint_producer + paint_code` is always a sufficient business identifier for one paint card, or whether an additional business attribute is needed
- whether future stock receipts should ever grow batch/lot metadata beyond the aggregate-per-paint model
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
| S05 | RAL | MANUAL | correction after packing | order: ... -> PACKING, then replanned: PRODUCTION -> PACKING | READY after correction round closes | order final completed=Q | same order reset to planning with a CORRECTION batch; no child order |
| S06 | RAL | AUTOMATIC | correction after packing | order: ... -> PACKING, then replanned: HANGING -> PACKING | READY after correction round closes | order final completed=Q | same order reset to planning with a CORRECTION batch; automatic return via HANGING; no child order |
| S07 | DECORAL | MANUAL | correction after packing | parent: ... -> PACKING -> DECORAL_PRODUCTION(ok); child: PRODUCTION -> PACKING -> DECORAL_PRODUCTION | READY after parent ok-part and child close | parent final completed=Q | parent keeps Decoral OK batch; child handles correction qty |
| S08 | DECORAL | AUTOMATIC | correction after packing | parent: ... -> PACKING -> DECORAL_PRODUCTION(ok); child: HANGING -> PACKING -> DECORAL_PRODUCTION | READY after both close | parent final completed=Q | same as S07 + automatic child path |
| S09 | RAL | MANUAL | multi-round correction | same order repeats PRODUCTION -> PACKING each round | READY after all rounds close | order completed=Q | each round is a new CORRECTION batch on the same order; no child orders |
| S10 | RAL | AUTOMATIC | multi-round correction | automatic variant of S09 (rounds return via HANGING) | READY after all rounds close | order completed=Q | each round is a new CORRECTION batch on the same order; no child orders |
| S11 | DECORAL | MANUAL | multi-round correction | dec + manual multi-round: each open branch requires Decoral completion | READY after all descendants close | root parent completed=Q | parent blocked until full descendant closure |
| S12 | DECORAL | AUTOMATIC | multi-round correction | dec + automatic multi-round with HANGING return and Decoral completion | READY after all descendants close | root parent completed=Q | combines automatic rules + dec + recursive merge |

## Test Alignment

The behavior above is exercised by existing and newly added tests in:
- `tests/test_process_service.py`
- `tests/test_process_api.py`
- `tests/test_manager_api.py`
- `tests/test_work_orders_api.py`

These tests are regression evidence, not a substitute for business validation. This document should be updated whenever workflow behavior changes in services or tests.

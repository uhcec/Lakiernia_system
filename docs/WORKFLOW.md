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

## Stage Model

Configured stages:
- Base: `SURFACE_PREPARATION` -> `HANGING` -> `PRODUCTION` -> `PACKING`
- `DECORAL` adds: `DECORAL_PRODUCTION`

Actionable stage sequence depends on production type:
- `MANUAL`: all configured stages are actionable
- `AUTOMATIC`: `PRODUCTION` is preview-only (not actionable)

Automatic constraints:
- Cannot start/finish `PRODUCTION` directly for `AUTOMATIC`
- `HANGING` start transitions automatic flow forward
- Finish for automatic path is performed from `PACKING`
- Physical resource exclusivity is enforced in the backend with persisted resource locks and controlled `409` responses.
- Only one `HANGING` job may be active at a time.
- Only one automatic-line job may be active at a time; in the current workflow this resource is occupied from automatic `HANGING` start until that path is completed from `PACKING`.
- Completing the job that holds the resource releases that resource so another queued job can start.

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
- `PRODUCTION` is preview-only during automatic flow

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
- `PRODUCTION` remains preview-only

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

Correction planning return stage:
- Child planned as `MANUAL`: returns to painting flow from `PRODUCTION`
- Child planned as `AUTOMATIC`: returns to painting flow from `HANGING`

Decoral split behavior:
- Parent OK part continues on `DECORAL_PRODUCTION`
- Correction quantity goes to child
- Parent is not READY while any correction child/descendant remains open

Multi-round corrections:
- Child can itself split again and create another child
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

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
- a **Decoral foil** may be selected at intake from the foil registry (`foils` lookup table), at most one per order (`WorkOrder.decoral_foil_id`); it is allowed only on `DECORAL`-coating orders (DB CHECK `decoral_foil_requires_decoral_coating`) and is optional. Today the foil is stored and displayed only (work-order detail + Decoral station); it does not yet feed Decoral-pass consumption or foil-usage stats (deferred, NA38)

Open implementation design:
- whether the work-order stock snapshot later links to a shared inventory batch/item model if this app ever grows into real warehouse tracking
- how to handle intake when the required paint exists physically but is not yet represented in the future inventory module

## Stage Model

> Physical context: a work order has two **independent** axes — production method (`MANUAL`/`AUTOMATIC`)
> and coating (`RAL`/`DECORAL`). See `docs/FACTORY_DOMAIN_MODEL.md` §1 for what they physically mean.

Configured stages:
- Base: `SURFACE_PREPARATION` -> `HANGING` -> `PRODUCTION` -> `PACKING`
- `DECORAL` adds: `DECORAL_PRODUCTION`

Note: physically the decoral coat is applied at a separate Decoral station after base-coat packing and
has its own packing, but the system intentionally does **not** model a separate decoral-packing stage —
that packing is folded into `DECORAL_PRODUCTION` completion (confirmed out of scope; see
`docs/FACTORY_DOMAIN_MODEL.md` §1).

Actionable stage sequence depends on production type:
- `MANUAL`: route is `SURFACE_PREPARATION → PRODUCTION → PACKING [→ DECORAL_PRODUCTION]`; there is **no
  `HANGING`** (manual parts are painted by hand, not hung).
- `AUTOMATIC`: route is `SURFACE_PREPARATION → HANGING → PACKING [→ DECORAL_PRODUCTION]`; there is **no
  `PRODUCTION` stage** — the line paints automatically, so there is no manual production step. The
  automatic production *station* still has its panel (a view over the line + paint-consumption entry),
  but it is not a `PRODUCTION` stage in the route.

> **NA42 — no phantom stages.** Stage-state rows are created as a method-agnostic superset at intake
> (the method isn't chosen until planning) and then **reconciled to the real route at planning**
> (`reconcile_stage_states_to_route`): an AUTOMATIC order has no `PRODUCTION` row, a MANUAL order has no
> `HANGING` row. The automatic-production panel/visibility and paint entry are unchanged for the operator;
> they are keyed off `HANGING` + the line state, not a `PRODUCTION` row.

Automatic constraints:
- There is no `PRODUCTION` stage to start/finish for `AUTOMATIC` (NA42).
- The automatic production station is not display-only: it records paint consumption as a separate
  audited paint-consumption action (gated off `HANGING`, not `PRODUCTION`).
- `HANGING` start transitions automatic flow forward
- The automatic production panel must show upcoming and active automatic flow from the moment a work order is ready for `HANGING`, including `HANGING` not-started/in-progress rows, so the automatic operator sees the day's workflow before the line is occupied.
- An automatic order **starts packing the moment `HANGING` starts** (its `PACKING` stage goes `IN_PROGRESS` immediately, not merely a slot reservation), so packing is active end-to-end as the line runs. The packing panel shows it as an **active packing row (the count form), not a read-only "waiting for hanging" row**, so the packing operator can work it in parallel with the line. Packing **completion stays blocked until `HANGING` is `DONE` and automatic paint consumption is recorded** — "Zakończ pakowanie" is disabled with a Polish reason (`packing_blocked_reason`) until both hold. Start now, finish after hanging + paint.
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

The choice of representation (the *correction kind*) is selected and dispatched at a single seam in the
backend — `ProcessService._select_correction_kind` / `_dispatch_packing_correction` (NA40) — rather than
branched inline at each packing path. There are three kinds: `REPLAN_IN_PLACE` (RAL, and any
tracked-batch packing), `SPIN_OFF_CHILD` (a DECORAL root being packed), and `STAT_ONLY` (NA34, below).

Stat-only correction — "fixed on the spot" (od razu poprawiona, NA34):
- When the packing operator marks a correction as fixed-on-the-spot (`stat_only_correction = true`), the
  defect was corrected immediately, so the pieces are good and **the order completes as-is**: the
  corrected pieces fold into OK (`completed_quantity` counts the full counted quantity), and the order
  does **not** return to planning and does **not** spin off a child. Applies to both RAL (closes to
  READY) and DECORAL (the pieces continue the single Decoral pass; no `N` marker).
- The correction is recorded **only as a statistic** in `stat_only_corrections` (quantity + required
  reason/category + profiles/accessories split) — never as a `CORRECTION` batch or child order — and the
  shared correction-event source unions it in, so the reason report and throughput count it like the
  other kinds. A reason/category is required (same as a re-planned correction).
- "To be re-planned" (do zaplanowania) is the default: the existing RAL/DECORAL flows above.

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
- active automatic orders as live packing rows from `HANGING` start (count form active, completion gated)

Packing capacity / slots (`PACKING:1..N` resource locks — NA16 + NA22):
- Packing has **N configurable slots** (`packing_max_concurrent_slots`, default 2), each a backend resource lock `PACKING:i` (same machinery as `HANGING`/`AUTOMATIC_LINE`), so occupancy survives across requests and is not frontend-inferred. The default behavior is single-station exclusivity; the extra slots are opened only by an explicit manual override.
- **Only manual orders may open a second slot.** An **automatic** order always uses the *single* station: it claims the one free slot **and starts its packing (`PACKING`→`IN_PROGRESS`) at HANGING start** (NA22a), then holds the slot until its own packing completes; a **second automatic queues** — it never reserves or takes a 2nd slot, and waits for the station to free (also enforced upstream by the `AUTOMATIC_LINE` lock). The un-pausable automatic line must not be blocked by a manual order taking the slot. (Packing *completion* still waits for `HANGING` to be `DONE`.)
- **Manual start is the exclusivity gate.** A manual **start packing** (`POST /process/work-orders/{id}/packing/start`) succeeds only when the station is completely free; if a slot is occupied/reserved it returns `409`, and the operator may retry with **`?override=true`** to open an additional slot up to N (NA22b). The override is audited and is the *only* way to run two packings at once (manual escape hatch). A manual completion is capacity-bound (it may finish into any free slot); automatic completion is single-station.
- The override surfaces a warning **only when the operator chooses to open the second station** (a confirm on click, not a persistent banner), because an automatic reserves packing **before parts physically arrive** (at hanging start) — the area can look free but is not. The warning shows the reserving automatic order's piece count.
- Completion (`/packing/complete`) takes/confirms a slot and releases it once packing leaves `IN_PROGRESS` (completed, or reset to planning by a correction). An operator who claimed the wrong order can free its slot without completing via **release** (`POST /process/work-orders/{id}/packing/release`); idempotent, cannot release another order's slot. Stale slots (owner no longer packing) are recovered on the next acquisition.
- Read models expose `holds_packing_slot` (this order holds a slot, including an automatic order that reserved one at hanging start), `is_being_packed` (holds a slot and is at the packing stage), `packing_slots_total` (N), and `can_complete_packing` / `packing_blocked_reason` (whether "Zakończ pakowanie" is allowed and, if not, the Polish reason — used to gate automatic orders until `HANGING` is `DONE` and paint consumption is recorded). The packing UI shows the entry form (+ "Zwolnij stanowisko") for an order that holds a slot, a "Rozpocznij pakowanie" button when the station is free, and an "Otwórz drugie stanowisko" override (with the warning) when occupied but capacity remains.

Decoral production list columns:
- work-order number
- profile pieces to verify
- accessory pieces to verify
- paint
- company/customer
- queue position

## Per-Line Queue Rule (MANUAL / AUTOMATIC numbered independently)

Queue position is scoped to the **production line**. The manual plan and the automatic plan are two
**independent** queues, each numbered from 1; the same `queue_position` may exist once on each line
(e.g. there is an automatic "position 1" and a separate manual "position 1"). This matches the physical
factory, which runs the two lines in parallel. The manager UI presents the two plans as separate boards
and edits one line at a time (a top-of-screen `Automat / Ręczna` switch).

Rules:
1. A planned order requires a `queue_position` unique **within its `production_type`** — enforced by a DB
   partial unique index on `(production_type, queue_position)`.
2. This uniqueness is per production line. It is not global and not namespace-scoped.
3. Correction orders start unplanned (`queue_position = null`); when planned they join **their line's**
   queue under the same per-line uniqueness rule.
4. A reorder reorders **one line at a time**: the payload carries the `production_type`, must contain only
   orders from that line, and positions within it must be unique.
5. Reorder payload must include the queue revision from the manager snapshot it was built from; the
   revision is computed **per line** (editing one line does not invalidate the other).
6. If the (per-line) queue revision is stale, reorder must fail with a controlled `409` error.
7. Queue uniqueness conflicts, including database-level uniqueness collisions during concurrent writes, must fail with a controlled `409` error and must never surface as a raw `500`.
8. Two managers must not be able to silently overwrite each other's queue reorder using stale data.
9. Corrections do not receive automatic priority over normal work orders.
10. Manager views should warn when a high-priority item is blocked by resource or station state, without reordering the line automatically.
11. Current manager queue warnings cover the exclusive resources currently modeled by backend locks/conflict checks: `HANGING` and `AUTOMATIC_LINE`. They are read-only visibility and do not change queue order or station-action authorization.
12. Planning a new order **appends it to the end of its line's active queue** — the position is computed by the backend, the manager no longer types one. Changing an order's production type re-slots it to the **end of the target line**. Reordering within a line is by drag-and-drop.
13. Completed/READY orders are historical in manager queue views and must not permanently block active planning slots.
14. When manager planning or queue-position updates need active slots, completed/READY rows should move to trailing queue positions after active planned work **on the same line**.
15. A completed/READY row may keep a `queue_position` for manager sorting and historical visibility, but that value is not an immutable record of the row's original active priority.

### Painting auto-scheduler (AUTOMATIC line — NA33, the painting-plan sub-part of NA49)

The manager can ask the system to **propose** a painting order for the automatic line. The proposal is
advisory and **never auto-applied**: the queue only changes when the manager commits it through the
normal queue-reorder flow, so operators can always trust the posted order.

- **Scope (v1):** the AUTOMATIC line only (it carries the throughput/cost/changeover majority — see
  `docs/FACTORY_DOMAIN_MODEL.md` §1–§2). MANUAL reuses the same mechanism when needed later.
- **Rules + priority:** the proposal is a lexicographic sort along a manager-configured, ordered list of
  *enabled* rules. The catalog (with default order, owner decision 2026-06-23):
  1. **Grupowanie kolorami (`colour`)** — keep identical colours adjacent (fewer colour changes).
  2. **Termin odbioru (`deadline`)** — earliest planned pickup date first.
  3. **Maksymalny przerób (`changeover`)** — "maximise m²/day": do the largest single-colour runs first,
     so the booth spends more time painting and less time being cleaned between colours.
  The priority order is **user-configurable** (the manager reorders/toggles the rules); it is stored per
  line in `auto_schedule_configs` and defaults to colour → deadline → changeover, all enabled. Absence of
  a row means the default.
- **Suggestion (no nagging):** new orders still **append to the end** of the line (nothing reshuffles on
  arrival). While the manager is on the automatic plan, the system computes the proposal in the
  background and shows a non-intrusive *"Lepsze ułożenie dostępne (−N zmian koloru)"* banner only when it
  would reduce colour changeovers. Acting on it is always the manager's explicit choice.
- **Apply path:** "Ułóż automatycznie" previews the proposed order as an editable draft (the manager may
  still drag to tweak); committing goes through the existing per-line `reorder_queue` (same stale-revision
  protection). Only *active* (non-READY) planned orders are scheduled; completed rows keep trailing.
- The optimisation core is a pure function (`app/manager/scheduler.py`); the metric behind the banner is
  the count of colour changes between consecutive orders.

> **Known limitation + planned evolution (NA49, agreed with owner 2026-06-23).** The per-line split is
> correct for *planning* the two parallel painting lines, but the two **shared** stages —
> `SURFACE_PREPARATION` (entry) and `PACKING` (drain) — still list both lines merged and ordered by
> `queue_position` (which is no longer globally unique), so they show duplicate "Poz. N" labels and an
> arbitrary cross-line interleave (verified live 2026-06-23). The agreed target model is **"schedule the
> painting bottleneck, derive the rest"**: the manager schedules only the two painting sequences
> (auto-arranged, manually overridable); surface-preparation order is *derived from the plan*
> (plan-driven feeder), and packing order is *derived from physical readiness* plus the existing
> packing-slot reservation model. Shared stages stop using the per-line position as a global rank. Full
> design + acceptance criteria: **NA49** in `IMMEDIATE_NEXT_ACTIONS.md`; physical grounding in
> `docs/FACTORY_DOMAIN_MODEL.md` §1. Not yet implemented — this section still documents current behavior.

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
- Statistics require manager/admin: **all** `/manager/stats/*` endpoints (`throughput`, `cycle-time`, `wip-aging`) and `/manager/corrections/reason-report[/export.csv]`, gated by `_ensure_stats_viewer`.
- `SYSTEM` (internal/seed callers, passed as no station context) remains the trusted identity; admins bypass station checks. `UNKNOWN` is no longer an allow-bypass — a request with an unknown/unauthorized role is denied.
- Station-origin links to work-order details preserve the source station identity. Detail pages reached from production stations are read-only for office/manager mutations while keeping drawings/attachments downloadable.
- Current automatic paint-consumption action is restricted to `AUTOMATIC_PRODUCTION`; future shared inventory or stock-receipt actions still need their own allowed-station rules.
- Authentication and authorization now both come from the JWT-authenticated user: user accounts, login sessions, and JWTs are required on all business endpoints, and authorization is derived from the user's `station_id`/`is_admin`, not the `X-Station-Id` header (NA1 closed; the header is now inert server-side). Open auth follow-ups: token expiry (NA6) and audit actor fields — see `IMMEDIATE_NEXT_ACTIONS.md`.

## Station Presence & Per-Operator Attribution

Operators are tracked as a **presence roster**, separate from login accounts (the personal-operator
foundation, slice 1 = attribution only):

- `employees` are factory workers (name + active); they do **not** authenticate. Login accounts
  (`users`) still carry the station role for authorization (NA1) — the tablet stays logged in as the
  station, and workers mark presence on top of that.
- Each station shows the employee list; workers **check in / out** (`station_presence`, append-only;
  "present now" = `checked_out_at IS NULL`). Several may be present at once. Check-in/out are idempotent.
- **Attribution:** every audit event for a station action is stamped with the employees currently
  present at that station (`audit_event_actors`), written centrally in `AuditRepository.add`.
  `SYSTEM`/`UNKNOWN` (internal/seed) actions get none. Because a roster can hold several people, an action
  is attributed to the **whole present set**, not a single person (a constraint future per-operator stats
  must handle).
- **Employee administration** (office/manager/admin only): create, rename, and deactivate/reactivate
  employees in-app (`POST /employees`, `PATCH /employees/{id}`, `GET /employees?include_inactive=true`).
  Deactivating a worker also ends any open presence. The "Pracownicy" page hosts this.
- **Check-out-all** (`POST /stations/{id}/presence/check-out-all`) ends a whole station's shift at once
  (widget button "Wymelduj wszystkich").
- **Per-operator statistics** (`GET /employees/stats`, office/manager/admin): for a period, per employee —
  `hours_present` (clamped presence sessions), `orders_count` + `pieces_credited` + `m2_credited`
  (from completion audit events — `process.stage.finished` / `process.packing.completed` /
  `process.decoral_production.completed` — joined to the order), and `actions` (all attributed events).
  **Crediting rule:** each present operator gets **full credit**, and an order is counted **once per
  operator** (so cross-operator sums overlap and may exceed the factory total — by design, since
  attribution is the whole present set, not a single person).
- **Presence history** (`GET /employees/presence/history`, office/manager/admin): per session — employee,
  station, check-in/out, and hours clamped to the window.
- API also: `GET /employees`, `GET /stations/{id}/presence`, `POST .../presence/check-in|check-out`.
  Station pages render a presence widget; the audit console and work-order audit history show the
  attributed operators.

## Quantity Discrepancy Visibility

Rules:
- Office and manager should see declared client quantity, surface-preparation counted quantity, and their difference.
- Production/station operators should see only the current operational quantity they need to process.
- **The station-facing operational quantity is the actual received (surface-preparation counted) quantity once it has been counted, not the ordered `total_quantity`** (NA26). Station read models expose it as `operational_quantity` (= the active batch quantity for tracked batches; otherwise the surface-preparation counted quantity when available, else `total_quantity` before counting). The profile/accessory "to verify" counts derive from this operational quantity. `planned_quantity` stays the **original expected** quantity for audit/office-manager visibility (principle 6) and is not the operator-facing count.
- Quantity discrepancies should be recorded and visible to office/manager, but should not block the work order for now.
- Surface-preparation operators record the counted quantity where counting happens; no separate discrepancy confirmation step is required for now.
- Starting `SURFACE_PREPARATION` does not require counted quantity.
- Finishing `SURFACE_PREPARATION` requires counted quantity.

### Quantity model — the five quantities and the single display rule (NA43)

A work order carries several distinct quantity notions. Confusing them is the root of NA26-class
bugs, so they have one documented meaning and **one resolver** owns the display rule.

The five notions:
1. **ordered** (`total_quantity`) — the fixed client-ordered count. Never changes.
2. **counted** — the actual received count from `SURFACE_PREPARATION` (and the count recorded at
   `PACKING`). The source of truth for validation/READY once counted.
3. **current active** (`current_active_quantity`) — the sum of the order's active batches (the live
   work-in-progress count; one active batch per order).
4. **operational** — the count an operator physically handles at a station (NA26): a tracked batch's
   own size, else the surface-prep actual received once counted, else the ordered total.
5. **per-stage planned** — the expected count for a stage (the ordered total, or a tracked/correction
   batch's own size).

**Single display rule:** the four *display* quantities a station card shows for a given
`(work order, stage, batch)` — `batch_quantity` (display), `planned_quantity`, `counted_quantity`,
`operational_quantity` — are computed in exactly one place, `ProcessService._resolve_stage_quantities`
(returning a `StageQuantities` value object). These are **display-only**: validation, READY, and
quantity conservation use `total_quantity` / counted directly and never the resolver. `counted_quantity`
is non-`None` only at `SURFACE_PREPARATION` / `PACKING`; `planned_quantity` stays the original expected
quantity for audit/office-manager visibility (principle 6).

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

> Canonical measurement model: `docs/FACTORY_DOMAIN_MODEL.md` §4. Total production = m² of product that
> passed through the factory, counted **once** per order; `manual + automatic` and `RAL-only + decoral`
> are two independent cuts of that same total. The decoral **pass** ("przejazd Decoral") is a separate
> line-workload counter (it overlaps the base coat) and is **never** added into the total.

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
- **m² by order coating type (NA23).** The same base-coat total is *also* partitioned by the order's
  coating: `m2_ral_only` = orders coated `RAL` only, `m2_decoral` = orders coated `DECORAL`, each
  counted **once** at base-coat packing (`total_area_m2`), so `m2_ral_only + m2_decoral = m2_total`.
  This is the **decoral product** (one product through the factory), distinct from the decoral *pass*
  below. The method split and the coating split are two independent cuts of the same total; do not add
  them together.
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
  base-coat total). `m2_decoral_pass` is computed from the stage-transition log (latest
  `DECORAL_PRODUCTION`→`DONE` `occurred_at`) for non-correction orders, exactly like the base-coat
  attribution but at the pass moment. There is no `updated_at` fallback for this series — the pass date
  is only reliable from the log, so passes completed before the log existed do not appear (this
  intentionally replaced the earlier packing-time approximation). The Statystyki page renders it as its
  own "Przejazd Decoral — m² / dzień" bar chart and the "Przejazd Decoral*" table column, flagged as
  not part of `m2_total`. (Field renamed from `m2_decoral` to `m2_decoral_pass` in NA23, freeing
  `m2_decoral` for the coating-partition product above.)
- **Corrections** are counted from **both** correction sources of the hybrid model (same as
  `list_correction_reason_report`, so the chart and the reason report agree): `CORRECTION` quantity
  batches (RAL packing / DECORAL decoral-stage resets) **plus** child correction work orders
  (`is_correction = true`, DECORAL packing). Each is keyed by its own `created_at`; `correction_pieces`
  sums batch `quantity` + child `total_quantity`, `correction_orders_count` counts the correction
  events. The two sources are disjoint, so there is no double counting. (Counting only child orders
  would undercount RAL corrections — historical bug NA4.)
- The frontend (Statystyki "Przepustowość") renders, for the selected month: a headline total
  ("Przez fabrykę"), two equal-width composition bars (the same total cut by method and by coating), a
  daily **stacked** m² chart with a Metoda/Powłoka cross-section toggle (bar height = `m2_total`,
  unchanged by the toggle), a separate "Przejazd Decoral" chart, a corrections chart, and a detail
  table with grouped columns (method + coating, each summing to `m2_total`, plus the przejazd column).
  It must not re-derive these buckets locally beyond zero-filling missing days in the range.
  (Unit is m²; a pieces toggle is deferred.)

### Stage-transition log (analytics foundation)

`stage_transition_events` is an **append-only** record of every meaningful stage transition: stage,
new status, `occurred_at`, work order, batch, counted quantity, station, and (nullable) user. It
exists because `work_order_stage_states` keeps only the latest `updated_at`, which is overwritten on
every change and cannot reconstruct history. Rows are written wherever audit events are emitted for
transitions (stage start/finish/reopen, packing completion, decoral-pass completion), plus the
automatic implicit transitions (PRODUCTION/PACKING set to IN_PROGRESS when automatic HANGING **starts**,
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
  start. The first stage has no wait (`null`). Averaged across the cohort orders that have a wait.
- **Overall lead time** (`overall_average_seconds`): per order, the earliest stage `IN_PROGRESS` to the
  packing `DONE`, averaged across the cohort.
- **Production breakdown (NA23):** every per-stage average and the overall lead time also carry a
  `breakdown` / `overall_breakdown` cutting the same cohort two independent ways — `by_method`
  (Ręczna/Automat) and `by_coating` (Czysty RAL/Decoral). Each `StageCycleTime`/`CycleTimeSegment` also
  carries `total_seconds` (sum of active time), so two views are possible:
  - **Suma** (total time): the segment **totals sum** to the stage total — this is the one that can be
    drawn as a single stacked bar splitting into parts that add up to the whole.
  - **Średnia** (average per order): the parts do **not** sum to the headline; the headline is the
    **count-weighted mean** of either partition, with each segment's `orders_count` making the
    reconciliation auditable.
  Empty segments are omitted. An order contributes to exactly one method and one coating segment (see
  `FACTORY_DOMAIN_MODEL` §4.1: the two axes are independent — "manual + automatic + decoral" is **not** a
  valid three-way split because a decoral order is already counted inside manual/automatic).
- Stages are returned in canonical workflow order with Polish labels. The Statystyki page renders a
  "Czasy etapów" section with a **Suma/Średnia view toggle** × a **Metoda/Powłoka cross-section toggle**:
  the stage chart is a stacked total-time bar (Suma) or side-by-side per-group average bars (Średnia),
  plus a wait-before-stage chart, a headline lead-time figure, and a table whose per-segment columns
  follow the chosen view. This is bottleneck visibility only; it never changes workflow or queue behavior.

### Live WIP-aging ("stuck orders")

`ManagerService.get_work_in_progress_aging` (manager/admin only, `GET /manager/stats/wip-aging`) is a
**live** "what's stuck right now" view, independent of any date window. Cohort is taken from the **live**
`WorkOrderStageState` rows that are actually `IN_PROGRESS` (one entry per order at its furthest-advanced
in-progress stage — automatic orders have `PRODUCTION` + `PACKING` both in progress, so `PACKING` wins),
so a correction reset can never leave a stale "stuck" row. Each item's age is `now -` the durable latest
`IN_PROGRESS` event for that order+stage from the transition log (falling back to the stage state's
`updated_at`). Items are sorted oldest-first. Each item carries `production_type` + `coating_type`, and
the response includes a `breakdown` counting the live cohort the same two independent ways as the other
production stats (NA23): `by_method` and `by_coating`, each a full partition whose segment counts sum to
the number of items. The Statystyki page renders it as a "Zlecenia w toku" table at the top (with a
Powłoka column and a composition line), highlighting rows older than 24h. Read-only; it never changes
workflow or queue behavior.

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

## Work Order Attachments (incl. technical drawings)

The office attaches files (PDF or PNG/JPG images) to a work order. Every attachment carries a structured
**category** (`WorkOrderAttachmentCategory`): `DOCUMENT` (the default — any general file, e.g. a spec) or
`TECHNICAL_DRAWING` (NA36). The category is the discriminator that distinguishes a technical drawing from
other attachments; an optional free-text `attachment_type` may still carry a human sub-label.

- **Upload/delete is office-only**; **viewing/downloading is open to every authenticated station** (the
  download endpoint is not station-gated). Uploads are validated by content type **and** magic bytes
  (`%PDF-`, the PNG signature, or the JPEG `\xff\xd8\xff` prefix) and capped by the configured max size; a
  mismatch is rejected (`415` wrong type, `400` bad signature, `413` too large, `422` bad category).
- **Technical drawings are surfaced on the production station cards** (surface preparation, production,
  hanging, packing, decoral) as a "Rysunki techniczne" list of download links, so the operator can open the
  drawing where they work — in addition to the work-order detail page. The station read model
  (`ProcessStageWorkOrderRead.technical_drawings`) only includes attachments whose category is
  `TECHNICAL_DRAWING`; plain documents are not listed on station cards.
- One work order may hold many attachments (one drawing or several); there is no per-product/template model.

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
- the **displayed** consumed-paint total on read models is the **cumulative** kg across the whole
  correction chain (the order plus its correction descendants), computed from the durable
  `paint_stock_movements` log rather than the per-round `consumed_paint_quantity_kg` field (NA32). That
  field remains the per-round "paint registered before packing?" gate and is reset between correction
  rounds; only the displayed total is rolled up, so a corrected order shows the sum of all rounds (and a
  parent shows parent + children) while stock stays correct
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

Completion invariant (no backwards transitions) — NA30:
- Once a work order is complete (READY by the rules above — all quantity accounted for and no open
  corrections), it must not be sent backwards. A stage start/finish/transition that would move any
  stage to `IN_PROGRESS` or `DONE` on a completed order is rejected with a controlled error, even for
  an admin (the invariant is independent of station permission).
- Without this guard a forward transition on a fully-packed order (e.g. re-opening `HANGING` or
  `PRODUCTION`) succeeded and left a contradictory state — an earlier stage `IN_PROGRESS` while the
  terminal stage was already `DONE`.
- The legitimate way to re-touch a finished colour is the correction flow (RAL batch reset / DECORAL
  child), not a raw stage transition. A rejected transition must not change any stage status,
  quantity, or READY state.

Additional completion behavior:
- If correction descendants are completed and no active quantity remains, completion can finalize upward through parent chain.
- Parent remains non-READY while any correction descendant is still open.
- Parent and correction completion actions may overlap; the backend must either reconcile to the same valid final state or reject stale impossible actions with a controlled response.

## Scenario Matrix S01-S12

| Scenario | Coating | Production | Correction mode | Expected stage path | Final status | Final quantities | Parent/child behavior |
|---|---|---|---|---|---|---|---|
| S01 | RAL | MANUAL | none | SURFACE_PREPARATION -> PRODUCTION -> PACKING | READY | parent completed=Q, active=0 | no child |
| S02 | RAL | AUTOMATIC | none | SURFACE_PREPARATION -> HANGING -> PACKING (no PRODUCTION stage) | READY | parent completed=Q, active=0 | no child |
| S03 | DECORAL | MANUAL | none | SURFACE_PREPARATION -> PRODUCTION -> PACKING -> DECORAL_PRODUCTION | READY | parent completed=Q, active=0 | no child |
| S04 | DECORAL | AUTOMATIC | none | SURFACE_PREPARATION -> HANGING -> PACKING -> DECORAL_PRODUCTION (no PRODUCTION stage) | READY | parent completed=Q, active=0 | no child |
| S05 | RAL | MANUAL | correction after packing | order: ... -> PACKING, then replanned: PRODUCTION -> PACKING | READY after correction round closes | order final completed=Q | same order reset to planning with a CORRECTION batch; no child order |
| S06 | RAL | AUTOMATIC | correction after packing | order: ... -> PACKING, then replanned: HANGING -> PACKING | READY after correction round closes | order final completed=Q | same order reset to planning with a CORRECTION batch; automatic return via HANGING; no child order |
| S07 | DECORAL | MANUAL | correction after packing | parent: ... -> PACKING -> DECORAL_PRODUCTION(ok); child: PRODUCTION -> PACKING (then OK returns to root's Decoral; child does NOT run its own Decoral) | READY after parent ok-part and all returned pieces finish the root's single Decoral pass | parent final completed=Q | one Decoral pass on the root; child closes at packing and its OK pieces rejoin the root's Decoral (merge if still open, else a fresh root Decoral batch) |
| S08 | DECORAL | AUTOMATIC | correction after packing | parent: ... -> PACKING -> DECORAL_PRODUCTION(ok); child: HANGING -> PACKING (then OK returns to root's Decoral; no own Decoral) | READY after both close | parent final completed=Q | same single-Decoral-pass-on-root model as S07, with the automatic child route to packing |
| S09 | RAL | MANUAL | multi-round correction | same order repeats PRODUCTION -> PACKING each round | READY after all rounds close | order completed=Q | each round is a new CORRECTION batch on the same order; no child orders |
| S10 | RAL | AUTOMATIC | multi-round correction | automatic variant of S09 (rounds return via HANGING) | READY after all rounds close | order completed=Q | each round is a new CORRECTION batch on the same order; no child orders |
| S11 | DECORAL | MANUAL | multi-round correction | dec + manual multi-round: each child closes at packing and returns OK to the root's single Decoral pass; only the root runs Decoral | READY after all descendants close and the root's Decoral pass finishes the returned pieces | root parent completed=Q | corrections are flat children of the root; parent blocked until full descendant closure |
| S12 | DECORAL | AUTOMATIC | multi-round correction | automatic variant of S11 (children return via HANGING -> PACKING); still one Decoral pass on the root | READY after all descendants close and the root's Decoral finishes | root parent completed=Q | combines automatic child routing with the flat-child, single-root-Decoral merge |

## Test Alignment

The behavior above is exercised by existing and newly added tests in:
- `tests/test_process_service.py`
- `tests/test_process_api.py`
- `tests/test_manager_api.py`
- `tests/test_work_orders_api.py`

These tests are regression evidence, not a substitute for business validation. This document should be updated whenever workflow behavior changes in services or tests.

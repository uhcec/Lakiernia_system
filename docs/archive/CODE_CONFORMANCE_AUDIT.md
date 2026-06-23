> ARCHIVED — frozen historical snapshot as of 2026-06-17. Living truth lives in docs/WORKFLOW.md / docs/FACTORY_DOMAIN_MODEL.md.

# Code Conformance Audit (NA25)

Status: **DONE — 2026-06-17.** Full read-only pass auditing the **code** against the reconciled
documentation (the NA24 "coherent whole"). For each documented topic: a verdict + `file:line`
evidence. No code was changed. Divergences are logged as actionable items (here + `IMMEDIATE_NEXT_ACTIONS.md`).

Verdict legend: **CONFORMS** (code matches docs, read directly) · **DIVERGES** (code contradicts docs)
· **DOC-UNDERSTATES** (code is correct/broader; a doc is narrower/stale) · **RELIED-ON-EVIDENCE**
(not re-read line-by-line this pass; trusted closed HARDENING items + tests, noted as such).

## Summary

- **1 real divergence: NA26** — downstream stations displayed the **ordered** quantity, not the
  **actual received (counted)** quantity (operator-truth gap). Confirmed in code below.
  **FIXED 2026-06-17** (added `operational_quantity` to the station read model; stations now show the
  counted operational quantity, validation/READY untouched).
- **1 doc-understatement: NA27** — WORKFLOW "Station Permissions" listed only 2 stats endpoints as
  manager-gated; code gates all 4. **FIXED 2026-06-17** (WORKFLOW line broadened).
- Everything else audited **conforms**.

## Topic-by-topic

### Stage model & sequences — CONFORMS
`get_stage_sequence_for_configuration` (`app/process/service.py:64-77`): MANUAL = SP→PRODUCTION→PACKING,
AUTOMATIC adds HANGING, DECORAL adds DECORAL_PRODUCTION; PRODUCTION present for automatic only as a
non-actionable preview (`_is_automatic_production_preview_stage`, `get_actionable_stage_sequence…:1295`).
Matches `WORKFLOW.md` "Stage Model" / Main Flows. Enums match docs (`app/process/enums.py`).

### `process_status` derivation & READY — CONFORMS
`get_display_status` (`:988-1020`) derives at read time (incomplete → READY → to-be-planned → tracked
batches → waiting-for-corrections → stage); never stored. READY via `_is_complete_for_display`
(`:2306-2311`: completed==total, active==0, no open corrections) + `_has_incomplete_marker` (`:2303`).
Matches `WORKFLOW.md` "READY Rules". Finalize chain `_finalize_completion_chain_if_ready` (`:2244-2279`)
with the NA19 quantity-gap warning (`:2258-2264`).

### Reopen finished tracked batch → 409 — CONFORMS
`_reopen_tracked_batch_stage` (`:1565-1566`) raises on DONE batches; `reopen_stage` rejects when no
active quantity (`:363`). Matches `WORKFLOW.md` "Tracked batch reopen rule".

### Corrections (RAL batch reset vs DECORAL child) — CONFORMS
Reason required + category split enforced in the request model (`app/process/schemas.py:76-93`,
`:106-125`) and service (`_validate_correction_reason`, `_validate_correction_category_split`).
RAL in-place reset (`_reset_to_correction_planning:1890`), DECORAL child + flat-root model
(`_create_correction_work_order:1821`, `_place_returned_pieces_on_root_decoral:1754`,
`_resolve_root_order:1745`). Matches `WORKFLOW.md` "Corrections Behavior" + S01–S12.

### Resource locks & packing capacity — CONFORMS
HANGING/AUTOMATIC_LINE exclusivity + PACKING N-slot model; automatic reserves a slot at HANGING start
(`_reserve_packing_for_automatic_hanging`, called `:170`); `packing_max_concurrent_slots` default **2**,
`ge=1` (`app/core/config.py:45-53`). Manual override + `start_packing`/`release_packing` present
(`:379`, `:459`). Matches `WORKFLOW.md` "Packing capacity / slots" (NA22).

### Authorization (NA1) — CONFORMS
`ensure_station_allowed` (`app/audit/context.py:49-67`): trusts `None`/`SYSTEM`, admin bypass, no
`UNKNOWN` allow-bypass; context derived from JWT user (`get_station_context:39-46`), not the header.
Matches `WORKFLOW.md` "Station Permissions", `AUTHZ_DESIGN_PROPOSAL.md`, `STATION_IDENTITY_AND_AUDIT.md`.

### Manager statistics gating — DOC-UNDERSTATES (code is correct/broader)
`_ensure_stats_viewer` gates **all** stats: throughput (`app/manager/service.py:112`), corrections
report (`:356`), cycle-time (`:129`), wip-aging (`:508`). `WORKFLOW.md` "Station Permissions → Current
enforcement" names only `/stats/throughput` + `/corrections/reason-report` as gated — it predates
cycle-time/wip-aging. **Fix:** broaden that WORKFLOW line to "all `/manager/stats/*`". (Low severity;
code is safe.)

### Global queue (uniqueness + stale-revision) — CONFORMS
`reorder_queue` checks `queue_revision` and rejects stale payloads (`app/manager/service.py:733-735`);
uniqueness collisions normalized to controlled conflicts (HARDENING #3/#4, closed). Matches
`WORKFLOW.md` "Shared Queue Rule".

### Throughput / cycle-time / WIP-aging — CONFORMS
m² split by production type with `m2_manual + m2_automatic = m2_total` (`:183-201`), decoral pass a
separate non-summed series (`decoral_by_period`, `:293-318`), corrections from both sources
(`:214-256`), ISO weeks `%G-%V` (`:134`). Cycle-time/WIP off the stage-transition log. Matches
`WORKFLOW.md` "Throughput Reporting" (and the canonical model in `FACTORY_DOMAIN_MODEL.md` §4).

### Paint inventory & consumption — CONFORMS
Predicted demand `/4` below **100 m²**, `/6` from 100 (`app/work_orders/schemas.py:315`) — confirms the
threshold is 100 (NA24 A1). Intake shortage warning present (`calculate_paint_shortage_quantity_kg:319`,
read-model fields `service.py:755-797`). Automatic packing blocked until consumption recorded
(`_ensure_automatic_paint_consumption_recorded_before_packing`, `app/process/service.py:1192-1196`).
Stock cannot go below zero (`PaintService._apply_movement` raises `InvalidPaintInventoryError`,
`app/paints/service.py:198`). Consumption is one-shot, not editable (`:723`). Matches `WORKFLOW.md`
"Paint Inventory And Consumption".

### Additional work types (Przemalowanka / Ocynk) — CONFORMS
`work_order_kind` enum + `is_ocynk` + `released_to_client_at` columns
(`app/work_orders/models.py:114-130`); `is_ocynk` is a non-routing marker; PRZEMALOWANKA skips surface
prep (`_omits_surface_preparation_stage`/`_skips_surface_preparation`, `app/process/service.py:1306-1313`).
Matches `WORKFLOW.md` "Additional Work Types" + `FACTORY_DOMAIN_MODEL.md` §5.

### External order number — CONFORMS
`external_order_number` nullable, no unique constraint (`app/work_orders/models.py:96`). Matches
`WORKFLOW.md` intake (optional, non-unique, duplicates allowed).

### Completed release — CONFORMS (column + office-only per docs)
`released_to_client_at` nullable (`app/work_orders/models.py:130`); office-only / READY-only enforcement
per `WORKFLOW.md` "Office/manager list grouping". (Enforcement path relied on station-action checks +
existing tests.)

### JWT secret / expiry, bcrypt, SQLite pragmas, number allocator — CONFORMS / RELIED-ON-EVIDENCE
JWT default rejected outside dev (`app/core/config.py:61-67`, NA12 verified). `jwt_expiry_minutes`
default 12h (`:39-43`, NA6). bcrypt 72-byte (NA10), SQLite pragmas (NA9), atomic number allocator
(HARDENING #5) — **RELIED-ON-EVIDENCE** (closed items + tests; not re-read this pass).

### Idempotency / concurrency, attachments, audit, frontend historical display — RELIED-ON-EVIDENCE
Idempotency/concurrency (HARDENING #1/#2 + chaos suite), attachment PDF magic-byte + path containment
(HARDENING #12), audit events (`STATION_IDENTITY_AND_AUDIT.md` "Current Implementation"), and
historical-correction display via `is_historical_correction` (field present, `process/schemas.py:22`;
frontend consumes it) — trusted from closed evidence/tests, not line-audited here.

### QC document generation — RELIED-ON-EVIDENCE
Excel template → fill (order no `A4`, customer `D5`, paint `D6`) → PDF, lazy COM worker, print-only
(`WORKFLOW_VALIDATION_CHECKLIST.md` #10, README). Cell mapping not re-verified against the template
this pass.

## Divergences (actionable)

### NA26 — stations display ordered quantity, not actual received (CONFIRMED) — see `IMMEDIATE_NEXT_ACTIONS.md` NA26
Evidence:
- Surface-prep counting stores `counted_quantity` **only** on the SP stage state; it does **not** update
  the active batch / `current_active_quantity` (`_store_surface_preparation_counted_quantity`,
  `app/process/service.py:2339-2355`).
- The operational display quantity therefore stays at the ordered value: `_get_stage_display_quantity`
  returns `current_active_quantity` (=`total_quantity`) / `total_quantity` (`:2479-2492`);
  `_get_stage_planned_quantity` returns `total_quantity` for the active main batch (`:2495-2511`).
- Station cards render `planned_quantity` and category "to verify" counts derived from the operational
  quantity (`frontend/.../StageWorkOrdersPage.tsx:524`, `PackingWorkOrdersPage.tsx:560`;
  `_derive_category_fields_for_operational_quantity:2190`).
- By contrast, **validation** correctly uses the actual received quantity
  (`_get_surface_preparation_actual_quantity:2821`, used at packing `:576-578`), and the read model does
  expose `counted_quantity`/`quantity_difference` — just not as the primary station display.

So packing's "did anything go missing?" check is right, but the displayed piece counts at
HANGING/PRODUCTION/PACKING are the ordered total, not the counted truth — exactly as the owner reported.
- **Tension to resolve with the owner:** `WORKFLOW.md` principle 6 says `planned_quantity` *stays* the
  original expected quantity for audit, while "Quantity Discrepancy Visibility" says station operators
  should see the **operational** quantity. The fix should show the actual received quantity as the
  station-facing operational count once surface prep has counted it, while keeping declared + difference
  for office/manager (and preserving the audit `planned_quantity`). Confirm desired display, then fix.

## Notes / non-divergences worth recording

- Manager stats doc-understatement (above) — propose a one-line WORKFLOW fix; logged here, not a defect.
- No code change was made under this audit (read-only, per the task).

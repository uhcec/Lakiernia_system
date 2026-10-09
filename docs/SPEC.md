# Paint Shop System — Domain Specification (rebuilt)

**Status:** rebuilt from the code and adjudicated item-by-item with the owner on **2026-06-26**.
**Method (per `CLAUDE.md`):** every line is grounded in the code (`file:line`) **and** confirmed by the
owner. `✅` = owner-confirmed as matching the factory. `⚠️ CHANGE #n` = the code currently does this,
but the owner wants it changed — see `docs/CHANGES.md`; **do not treat the current behavior as desired.**

This file describes **what the code does today**. It is the new ground truth, replacing the deleted docs.

---

## 1. Data model & invariants

- ✅ An order must have a positive quantity; completed quantity is between 0 and total. `app/work_orders/models.py:52-54`
- ✅ An order is "planned" exactly when it has a **queue position**; a queue position requires a production line, but a line may exist **without** a position — a completed order leaves the active queue (position → NULL) yet keeps its line (CHANGE #3). `app/work_orders/models.py:60-63`
- ✅ An order marked incomplete-on-arrival cannot be planned. `app/work_orders/models.py:64-67`
- ✅ Queue position is unique **per production line** (MANUAL vs AUTOMATIC); position 1 exists on both lines independently. `app/work_orders/models.py:96-104`
- ✅ A planning lock (pin/urgent) can only exist on a planned order. `app/work_orders/models.py:70-73`
- ✅ When profiles & accessories quantities are both known, they must sum to the total. `app/work_orders/models.py:74-85`
- ✅ A Decoral foil may only be set on a DECORAL order. `app/work_orders/models.py:86-89`
- ✅ A correction order must have a parent and lives in the CORRECTIONS queue namespace. `app/work_orders/models.py:90-95`
- ✅ An order has at most one active quantity batch at a time. `app/process/models.py:69-75`
- ✅ Five process stages (SURFACE_PREPARATION, HANGING, PRODUCTION, DECORAL_PRODUCTION, PACKING); three statuses (NOT_STARTED, IN_PROGRESS, DONE). `app/process/enums.py:82-97`
- ✅ Coating = RAL/DECORAL; production = MANUAL/AUTOMATIC; kind = STANDARD/PRZEMALOWANKA. `app/process/enums.py:47-62`, `app/shared/enums.py:69-71`
- ✅ Stage transitions are recorded to a permanent append-only history (feeds statistics). Today every action is under a **shared station identity** — there is no per-operator login; the "who" field is reserved for the future. `app/process/models.py:95-126`

## 2. Intake (office)

- ✅ Order number = one **global 4-digit counter** (`0001`, `0002`, …), **not** reset per year. `app/work_orders/number_allocator.py:11-39`
- ✅ Required at create: customer, RAL + paint code + producer, coating, received date, **pickup date**, area (>0). `app/work_orders/schemas.py:154-177`
- ✅ Quantity defaults to 1. `app/work_orders/schemas.py:157`
- ✅ For profiles & accessories you give **either** a quantity **or** "to count on production", never both/neither. `app/work_orders/schemas.py:128-132`
- ✅ Creating an order captures a **paint stock snapshot** (kg at that moment). `app/work_orders/service.py:230@capture_work_order_snapshot`
- ✅ Only OFFICE creates orders / manages attachments / marks "complete on arrival"; OFFICE or MANAGER edits an order. `app/work_orders/service.py:872@_ensure_office_station_action`, `288@aktualizacja zlecenia`
- ✅ The office order list **excludes** correction ("P…") orders. `app/work_orders/service.py:401@not item.is_correction`
- ✅ Work-order status is **derived** from progress, never set manually. `app/work_orders/service.py:195@def derive_status`
- ✅ "Overdue" = pickup date is before today AND the order is not yet READY. `app/work_orders/service.py:1031@work_order.planned_pickup_date < date.today()`
- ✅ "Released to client" can only be set on a READY order. `app/work_orders/service.py:486@Only READY work orders`
- ✅ Attachments: PDF / PNG / JPG only, size-capped by config. `app/work_orders/service.py:170@ALLOWED_ATTACHMENT_TYPES`
- ✅ **(CHANGE #18 done 2026-07-11) WZ (wydanie z magazynu):** OFFICE generates a warehouse-issue PDF for a group of READY orders of **one** client — rows are each order's profile/accessory counts + RAL (an order with neither known collapses to one "Elementy" line), plus an optional manual "Kosze dłużycowe" line; the recipient address is left blank (handwritten). Mixed customers or non-READY orders are rejected; on a host without Excel it answers a controlled Polish **503** like the QC card. `app/work_orders/service.py:654@def generate_wz_document`, `746@różnych klientów`, `779@Kosze dłużycowe`
- ✅ WZ numbers run per-year "kolejny/rok" (e.g. 1/2026); a number is consumed only once the PDF renders (a failed render rolls it back). The WZ document is **not** persisted (no stored register / same-number reprint) and generating it does **not** mark orders released — that stays a separate step. `app/work_orders/wz_number_allocator.py:23@def allocate`, `app/work_orders/service.py:679@wz_number_allocator.allocate`
- ✅ **(CHANGE #17 done 2026-07-11)** the office downloads a **quality-control card (karta kontroli jakości)** as a PDF: the repo's Excel template (`app/static/templates/karta_kontroli_jakosci.xlsx`) filled with order number / customer / paint, rendered to PDF by **driving Excel over COM** — a deliberate hosting constraint (owner D1/D6: the Excel-formatted card is required and production runs on a **Windows host with Excel**; a persistent worker keeps one Excel instance alive). On a host without Excel (e.g. the Linux dev VPS) the endpoint answers a controlled Polish **503**, never a raw 500. `app/work_orders/service.py:615@def generate_quality_control_document`, `app/work_orders/service.py:64@class _ExcelPdfConverter`, `app/work_orders/router.py:109-116@quality-control-document`, `app/shared/exceptions.py:50-57@DocumentGenerationUnavailableError`

## 3. Stage flow & routing

- ✅ Route is derived from coating + line: SURFACE_PREPARATION → (HANGING unless MANUAL) → PRODUCTION → PACKING → (DECORAL_PRODUCTION if DECORAL). `app/process/service.py:88-103`
- ✅ MANUAL has no HANGING; AUTOMATIC has no PRODUCTION (the line paints itself). `app/process/service.py:97-99`, `1470-1474`
- ✅ PRZEMALOWANKA skips SURFACE_PREPARATION; corrections skip SURFACE_PREPARATION. `app/process/service.py:1477-1479`, `1474-1475`
- ✅ Allowed status moves: NOT_STARTED→IN_PROGRESS; IN_PROGRESS→{DONE, NOT_STARTED}; DONE→{IN_PROGRESS, NOT_STARTED}. `app/process/service.py:1310-1319`
- ✅ A stage won't start until the previous stage is DONE. `app/process/service.py:1321-1328`
- ✅ A fully-ready order can't be sent backward by reopening an earlier stage — that requires the correction flow. `app/process/service.py:1304-1308`
- ✅ **(CHANGE #14 done 2026-07-11)** a **DONE stage refuses start/reopen while any downstream stage is IN_PROGRESS or DONE** (409, Polish operator message) — its recorded count already feeds downstream validation, so a mid-flight restart would rewrite the "actual received" ground truth. A recount **before** downstream starts stays allowed. `app/process/service.py:1399-1416@Nie można cofnąć zakończonego etapu`
- ✅ **(CHANGE #14 done 2026-07-11)** the escape hatch: an **administrative reset** (owner-decided roles: office/manager, admins bypass) returns a genuinely stuck order to the start of its route — stage rows NOT_STARTED, counts cleared, fresh active MAIN batch at the ordered total, leak flag cleared, plan (line+position) kept, audited `work_order.administrative_reset`. Refused for correction-entangled orders (parent with children, or a correction itself). `app/process/service.py:542-627@def administrative_reset`, `app/work_orders/router.py:89-96@administrative-reset`
- ✅ "Reopen" steps a stage down one level; blocked when there is no active quantity left. `app/process/service.py:516-532`
- ✅ AUTOMATIC: at HANGING start, PACKING immediately goes IN_PROGRESS — packing runs in parallel with the line. `app/process/service.py:232-242`
- ✅ **(CHANGE #22 done 2026-10-09)** AUTOMATIC packing can be worked while hanging is in progress but completed only once hanging is DONE; paint consumption is **not** a packing gate any more (it is entered per paint run, §10). `app/process/service.py:796@Trzeba zakończyć zawieszanie automatu przed pakowaniem`, `1652-1667@def _packing_completion_block_reason`
- ✅ Each stage action is restricted to its station. `app/process/service.py:1433-1447`
- ✅ SURFACE_PREPARATION and PACKING are **physically shared** across both lines; their order is derived separately (not from the per-line queue position) and line-labelled. `app/process/service.py:288-367`
- ✅ Surface-prep order: feed the line with the **smaller** "prepared-but-not-yet-painted" buffer (in pieces); ties → AUTOMATIC. `app/process/shared_stage.py:49-89`

## 4. Quantities & counting

- ✅ Finishing surface preparation **requires** a counted quantity; >0 and ≤ active quantity. `app/process/service.py:2673-2676@def _ensure_surface_preparation_counted_quantity`, `app/process/service.py:2655-2671@def _store_surface_preparation_counted_quantity`
- ✅ The surface-prep count becomes the **"actual received"** quantity that packing must match. `app/process/service.py:2850-2877@actual received`
- ✅ **(CHANGE #12 done 2026-07-11, owner decision D5; category split fixed 2026-07-11)** an **intake undercount** (prep counts fewer than ordered) is a legitimate completion: at finalization the order is **redefined to the counted amount** ("becomes a 3-piece order") and the original ordered quantity (including its declared profile/accessory split) is preserved in the `work_order.total_quantity_redefined` audit event — ordered-vs-arrived lives in the audit trail, not on the order. The declared **profile/accessory split is redefined together with the total** (the DB CHECK ties their sum to it): a single-category order keeps its category (10 profiles counted at 8 → 8 profiles), a mixed split falls back to **to-count** — the same policy correction batches use. `app/process/service.py:2467-2503@total_quantity_redefined`, `app/process/service.py:2598-2607@def _is_settled_intake_undercount`, `app/process/service.py:2399-2424@def _derive_category_fields_for_operational_quantity`
- ✅ Packing count must equal the surface-prep actual (or, in a correction round, the correction batch size). `app/process/service.py:731-742`
- ✅ At packing: good + to-correct = counted. `app/process/service.py:723-729`
- ✅ Paint consumption shown on an order is the cumulative kg across the whole correction chain — since CHANGE #22 the sum of the order's m²-shares of closed paint runs (0 while its run is still open). `app/process/service.py:2788@get_consumed_paint_kg_for_work_orders`, `app/paints/repository.py:69@def sum_allocated_consumption_kg`

## 5. Corrections & Decoral

There are two quality checkpoints on a DECORAL order, because two things can go wrong:

- **Paint defect — caught at PACKING (before Decoral).** The bad pieces become a separate **child "P…"** order (which goes back to be **re-painted**); the root gets the **"N" marker**; the root's **good pieces proceed to Decoral immediately**. ✅ `app/process/service.py:1995-2058`
- **Foil defect — caught at/after DECORAL.** **No child** — only the bad pieces return as the **same order** (RAL-style replan-in-place, base coat re-painted), no "P" number. ✅ `app/process/service.py:982-1004`

Details:
- ✅ Three correction kinds, chosen at one seam: fixed-on-the-spot (stat only), same-order replan, spin-off child. `app/process/enums.py:113-123`, `app/process/service.py:1873-1888`
- ✅ "Fixed on the spot" records only a statistic — no child, no batch; pieces count as good, order completes as-is. `app/process/service.py:1890-1918`
- ✅ **(CHANGE #1 done 2026-06-26)** same-order replan still clears the *live* lock (it can't sit on an unplanned order) but now **remembers** the pin/urgent intent in `pending_planning_priority` and **re-applies** it when the order is re-planned. `app/process/service.py:2246-2254`, `app/manager/service.py:1404-1409@pending_planning_priority`
- ✅ Correction numbers come from the **root**: `P{root}`, then `P{root}-2`, `P{root}-3`… regardless of nesting. `app/process/service.py:2110-2132`
- ✅ A correction child inherits paint/colour/customer/dates/area and is always STANDARD kind. (Kind is irrelevant to the prep-skip — that comes from being a correction.) `app/process/service.py:2134-2178`, `1474-1475`
- ✅ There is exactly **one Decoral pass, on the root**; a fully-fixed child's good pieces return to the root's Decoral and the child closes without its own Decoral. `app/process/service.py:2010-2030`, `2102-2108`
- ✅ Returned pieces **grow** the root's ongoing Decoral batch (case 1); if the root's Decoral was already done, they start a **fresh** Decoral batch and Decoral re-opens (case 2). `app/process/service.py:2069-2100`
  - ⚠️ **CHANGE #2** — case 2 (a second, separate Decoral pass) is correct but should be made **clearly visible** to the operator.
- ✅ Planning a correction pre-marks every stage before its return stage as DONE (so it doesn't restart from scratch). `app/process/service.py:1861-1866`, `1458-1468`
- ✅ Return stage: AUTOMATIC → HANGING; otherwise PRODUCTION. `app/process/service.py:1449-1456`
- ✅ "N" marker = a DECORAL order with open correction children (can't close until they return). It clears when the child returns. `app/process/service.py:2407-2414`
- ✅ Reason: category ≤64 chars, note ≤500; required when there are bad pieces, forbidden otherwise; profile/accessory split must sum to the bad count. `app/process/service.py:1376-1424`

## 6. Completion

- ✅ RAL packing with no correction: order credits the good pieces and the main batch closes. `app/process/service.py:798-802`
- ✅ DECORAL packing with no correction does **not** complete the order — pieces move on to Decoral. `app/process/service.py:813-818`
- ✅ DECORAL completion (no correction) credits the good pieces. `app/process/service.py:1004-1006`
- ✅ READY = all pieces credited (completed = total) AND no active pieces AND all correction children complete. `app/process/service.py:2622-2627@def _is_complete_for_display`
- ✅ Finalization walks up the parent chain — closing the last child closes the root. `app/process/service.py:2448-2557@def _finalize_completion_chain_if_ready`
- ✅ **(CHANGE #12 done 2026-07-11)** a **settled intake undercount** (all counted pieces credited, fewer than ordered) finalizes like any completion: redefined to the counted amount (see §4), queue slot released, **no leak flag** — it is the owner-blessed path, not a leak. `app/process/service.py:2598-2607@def _is_settled_intake_undercount`
- ✅ **(CHANGE #10 done 2026-06-26)** if pieces "leak" (credited ≠ total at close, and the gap is **not** a settled intake undercount) the order is still forced to total so it can close, but it is now **human-visible**: a persisted `quantity_leak_flagged` flag on the order (surfaced in the read models) + a SYSTEM audit event `work_order.quantity_leak_detected`, not just a technical log line. `app/process/service.py:2505-2532@quantity_leak_flagged = True`, `app/work_orders/models.py:148-152`
- ✅ A completed correction child is marked a "historical correction". `app/process/service.py:2629-2630@def is_historical_correction`
- ✅ Display-status precedence: incomplete → ready → to-plan → (batch status) → waiting-for-corrections → first unfinished stage. `app/process/service.py:1152-1184`

## 7. Packing slots & resource locks

- ✅ N packing slots (configurable); **default N = 2**. `app/process/resource_locks.py:154-158`, `app/core/config.py:45`
- ✅ Single-station by default; only a **manual** order opens a 2nd slot (via override or completion); an automatic order always uses the single station. `app/process/resource_locks.py:177-230`
- ✅ An automatic order **reserves a packing slot at HANGING start** (so a manual order can't block the un-pausable line). `app/process/resource_locks.py:237-247`
- ✅ A 2nd automatic order **queues silently** (no 2nd slot). `app/process/resource_locks.py:188-216`
- ✅ An order can release its packing claim without completing (wrong order picked); can't release another's. `app/process/service.py:616-652`
- ✅ HANGING is a single-holder resource; the AUTOMATIC line is a single-holder resource (from hanging-done to packing-done). `app/process/resource_locks.py:88-103`, `321-338`
- ✅ The manager sees these as block reasons ("Zawieszanie zajęte" / "Linia automatyczna zajęta"). `app/process/service.py:1209-1231`
- ✅ Stale locks are auto-recovered when the owner no longer occupies the resource. `app/process/resource_locks.py:169-175`, `251-273`
- ✅ The model assumes a single backend worker. `app/process/resource_locks.py:1-20`

## 8. Planning queue

- ✅ Only the MANAGER plans / views statistics. `app/manager/service.py:1922-1935@allowed_station_ids={StationId.MANAGER}`
- ✅ Planning requires the order to be unplanned and not incomplete-on-arrival. `app/manager/service.py:1377-1380@Cannot plan incomplete order`
- ✅ The manager **picks the line at plan time**; planning an order **as AUTOMATIC** is hard-blocked if its metered colour is out of stock / insufficient (MANUAL is not checked). `app/manager/service.py:1382-1397@_assert_paint_available_for_automatic`, `1324-1366@def _assert_paint_available_for_automatic`
- ✅ Planning with no explicit position appends to the **end of the line's active queue**. `app/manager/service.py:1387-1393@_next_active_queue_position_for_line`
- ✅ **(CHANGE #3 done 2026-06-26)** on completion an order **leaves the line's active queue and releases its position** (keeping its line); the trailing/shuffle machinery was removed. Completed correction children release their slots too when the root finalizes. `app/process/service.py:2517-2549@release_queue_slot`
- ✅ **(CHANGE #13 done 2026-07-11; append/line-switch coverage fixed 2026-07-11)** a position is "taken" only by a non-READY order; a READY order still holding a position (legacy data from before CHANGE #12) is **released on the spot** by the availability check (audited `manager.stale_queue_slot_released`) instead of colliding on the unique index. The heal covers **every** path that lands on a position: an explicitly chosen position, the computed append slot of a no-position plan, and the line-switch re-append (the append slot is computed by *skipping* READY holders, so it lands exactly on a zombie's position). `app/manager/service.py:1969-2004@stale_queue_slot_released`, `app/manager/service.py:1393-1398@_next_active_queue_position_for_line`, `app/manager/service.py:1576-1579@same zombie heal as assign_plan`
- ✅ **(CHANGE #13 done 2026-07-11)** a queue-position collision at flush time returns a controlled **409** ("position already taken"), not a raw 500 — on plan, queue-position update and line switch alike. `app/manager/service.py:1413-1426@except IntegrityError`
- ✅ A line switch is blocked once hanging/production started; switching re-appends at the end and clears the pin. `app/manager/service.py:1562-1585@work_order.planning_priority = None`
- ✅ Drag-reorder uses staleness protection and must include all active orders of that line, that line only, no duplicates. `app/manager/service.py:1639-1676@must include all active planned work orders`
- ✅ PIN = lock to slot; URGENT = force to front; none = freely re-orderable. `app/shared/enums.py:78-92`
- ✅ "Arrange automatically" only **proposes**; the manager applies it. `app/manager/service.py:1867-1879@without committing anything`

## 9. Planner numbers

- ✅ Profitable **floor**: 800 m² (long day) / 500 m² (short day). `app/manager/capacity.py:33-36`
- ✅ Shifts: long = 07:00–21:00 (14 h), short = 07:00–15:00 (8 h). `app/manager/capacity.py:32-38`
- ✅ Booth physical rate band 60–100 m²/h, midpoint **80** used. `app/manager/capacity.py:41-43`
- ✅ **(CHANGE #4 done 2026-06-26; frontend wired 2026-06-27)** the manager **sets** the shift length **per day** (LONG/SHORT) from the capacity board; it is persisted in `day_shift_lengths` and read per-day to drive the plan — both the day's floor/hours **and** the fill (a SHORT day's smaller net ceiling holds less and pushes overflow forward). An unset day defaults to LONG; the m²-based advising (incl. the old load-derived per-day `display_shift_for`) was removed. `app/manager/service.py:1102-1106@shift_by_day` (per-day plan shift), `855-861@shift_by_day` (good-day per-day shift), `app/manager/placement.py:134-198`
- ✅ Colour-change cost by **size only**: next order ≤100 m² → 15 min; >100 m² → 30 min. `app/manager/capacity.py:48-52`, `app/manager/capacity.py:82-97`
  - ✅ **(CHANGE #5 done 2026-06-26)** the colour-**direction** factor (light→dark cheaper) was removed — a colour change costs its size band regardless of direction.
- ✅ The 100 m² threshold equals the paint/odzysk threshold. `app/manager/capacity.py:48`
- ✅ Planning horizon = **3 working days** (today + next two), default and hard cap. `app/manager/service.py:173-177@_MAX_PLAN_HORIZON_WORKING_DAYS`
- ✅ Calendar: Mon–Fri working, Sat/Sun off, no holiday list. `app/manager/placement.py:40-45`
- ✅ Day 0 is pro-rated to hours left in today's shift. `app/manager/placement.py:205-216`
- ✅ Placement is earliest-deadline-first into net-ceiling days; an order bigger than a day stands alone and is flagged over-ceiling; an order past its deadline / horizon is flagged "won't make it". `app/manager/placement.py:134-284`
- ✅ **(CHANGE #6 done 2026-06-26)** Two scheduling rules only — **deadline → colour** (default order); the "max-throughput" rule was removed. `app/manager/enums.py:4-43`, `app/manager/scheduler.py:42-57`
- ✅ **(CHANGE #7 done 2026-06-26)** colour-"lightness" guessing from the RAL code (and the light→dark sweep) was **removed**; within-day colour planning is now just **grouping identical colours** (groups ordered alphabetically by colour identity), cost = number of changes × the size band. `app/manager/colour.py:48-69`
- ✅ Line suggestion: small (≤100 m²) **and** colour-orphan → manual; else automatic; manager-overridable. `app/manager/colour.py:129-151`
- ✅ Paint feasibility: BLOCKED (metered colour out / insufficient for first order), WARNING (runs short later, or manual-used low-confidence), OK otherwise. `app/manager/paint_feasibility.py:85-98`
  - ✅ **(CHANGE #8 done 2026-06-26)** an **untracked** coloured order (no stock entered — no row or only the 0-kg placeholder) is now a distinct **STOCK_NOT_ENTERED** state (surfaced via `stock_not_entered_order_ids`), not a silent OK; it is never hard-blocked. A truly colourless order stays OK. `app/manager/paint_feasibility.py:29-37`, `116-175`

## 10. Paint inventory

- ✅ Predicted demand = area ÷ 4 if area < 100 m², else area ÷ 6, rounded to whole kg. `app/work_orders/schemas.py:327@total_area_m2 < 100`
- ✅ Shortage = predicted − current stock (rounded up), shown when predicted exceeds stock. `app/work_orders/schemas.py:331-344@ROUND_CEILING`
- ✅ **(CHANGE #22 done 2026-10-09)** Automatic paint consumption is entered **once per paint run**, not per order. A paint run = automatic-line orders with the **same paint** (RAL + producer + paint code) hung **one after another**: an order joins the newest run at its HANGING start if that run is still open and has the same paint, otherwise it opens a new run — so a paint change ends a run, and the same paint after a closed run starts a new one. Correction rounds / children join like ordinary orders. Undoing a hanging start takes the order back out of its open run (an emptied run is deleted). `app/process/service.py:216@CHANGES #22: automatic hanging drives`, `app/process/paint_runs.py:95-130@def join_on_hanging_start`, `102@latest.closed_at is None`, `132@def leave_on_hanging_undo`
- ✅ **(CHANGE #22)** The run's consumption is entered at the automatic-production station (cartons taken − remainder) once none of its orders is still hanging; **write-once** (a mistake is fixed by a manual office stock adjustment). It decrements stock with **one** movement for the whole run and is split onto the member orders **by m²** (per-piece area of the original order × pieces hung in that pass; grams, last order takes the remainder). Not enough stock → a Polish refusal, nothing recorded. `app/process/paint_runs.py:155-209@def record_consumption`, `168@RUN_HANGING_IN_PROGRESS_ERROR`, `166@RUN_ALREADY_RECORDED_ERROR`, `181@Za mało farby`, `66-80@def allocate_by_area`, `224-236@def _pass_area_m2`, `app/paints/service.py:133@def record_paint_run_consumption`
- ✅ **(CHANGE #22)** An open run **blocks nothing** on the floor (owner decision 2026-10-09). A run whose paint has already changed (not the newest run) is flagged red on the automatic-production station and on the manager panel until its consumption is entered. `frontend/src/components/PaintRunsPanel.tsx:24@!run.is_current`, `125-126@mode === "alarm"`, `frontend/src/pages/ManagerPanelPage.tsx:1329@PaintRunsPanel mode="alarm"`
- ✅ A colour is "tracked" only with real movement history (not the 0-kg auto-placeholder). `app/paints/service.py:154-158`
- ✅ Movement types: opening balance, delivery, automatic consumption, manual adjustment; deliveries/adjustments are office-only. `app/shared/enums.py:95-99`

## 11. Statistics

- ✅ Throughput m² is attributed to the **packing-completion day**; correction orders are **excluded** (their pieces were already counted on the parent — avoids double-counting). `app/manager/service.py:253-346@WorkOrder.is_correction == False`
- ✅ The Decoral pass is a **separate, additional** m² series at its own completion day. `app/manager/service.py:387-421@decoral_done_events`
- ✅ Every production stat is cut two ways at once: by method (manual/automatic) and by coating (RAL-only/decoral). `app/manager/service.py:149-156@_COATING_SEGMENTS`
- ✅ A "correction event" has one shared definition unioning correction batches + child "P" orders + fixed-on-the-spot. `app/manager/repository.py:105-128`
- ✅ Cycle time = most-recent completed pass per stage; lead time = first start → packing done. `app/manager/service.py:454-671@def get_cycle_time_stats`
- ✅ WIP aging = orders currently IN_PROGRESS, aged from the last entry into progress. `app/manager/service.py:672-763@def get_work_in_progress_aging`
- ✅ **(CHANGE #9 done 2026-06-26)** the shift length per day is **persisted** (`day_shift_lengths`, set by the manager) and judges each day against its floor 800/500 + hours 14/8 — used by **both** the "good day" measure **and** the forward plan (CHANGE #4); a day with no stored length falls back to LONG. `app/manager/service.py:884-898@floor_m2(day_shift)`, `app/manager/models.py` (`DayShiftLength`)

# Paint Shop System — Domain Specification (rebuilt)

**Status:** rebuilt from the code and adjudicated item-by-item with the owner on **2026-06-26**.
**Method (per `CLAUDE.md`):** every line is grounded in the code (`file:line`) **and** confirmed by the
owner. `✅` = owner-confirmed as matching the factory. `⚠️ CHANGE #n` = the code currently does this,
but the owner wants it changed — see `docs/CHANGES.md`; **do not treat the current behavior as desired.**

This file describes **what the code does today**. It is the new ground truth, replacing the deleted docs.

---

## 1. Data model & invariants

- ✅ An order must have a positive quantity; completed quantity is between 0 and total. `app/work_orders/models.py:52-54`
- ✅ An order is "planned" exactly when it has a **queue position**; a queue position requires a production line, but a line may exist **without** a position — a completed order leaves the active queue (position → NULL) yet keeps its line (CHANGE #3). `app/work_orders/models.py:61-64`
- ✅ An order marked incomplete-on-arrival cannot be planned. `app/work_orders/models.py:65-68`
- ✅ Queue position is unique **per production line** (MANUAL vs AUTOMATIC); position 1 exists on both lines independently. `app/work_orders/models.py:97-105`
- ✅ A planning lock (pin/urgent) can only exist on a planned order. `app/work_orders/models.py:71-74`
- ✅ When profiles & accessories quantities are both known, they must sum to the total. `app/work_orders/models.py:75-86`
- ✅ A Decoral foil may only be set on a DECORAL order. `app/work_orders/models.py:87-90`
- ✅ A correction order must have a parent and lives in the CORRECTIONS queue namespace. `app/work_orders/models.py:91-96`
- ✅ An order has at most one active quantity batch at a time. `app/process/models.py:69-75`
- ✅ Five process stages (SURFACE_PREPARATION, HANGING, PRODUCTION, DECORAL_PRODUCTION, PACKING); three statuses (NOT_STARTED, IN_PROGRESS, DONE). `app/process/enums.py:82-97`
- ✅ Coating = RAL/DECORAL; production = MANUAL/AUTOMATIC; kind = STANDARD/PRZEMALOWANKA. `app/process/enums.py:47-62`, `app/shared/enums.py:69-71`
- ✅ Stage transitions are recorded to a permanent append-only history (feeds statistics). Today every action is under a **shared station identity** — there is no per-operator login; the "who" field is reserved for the future. `app/process/models.py:95-126`

## 2. Intake (office)

- ✅ Order number = one **global 4-digit counter** (`0001`, `0002`, …), **not** reset per year. `app/work_orders/number_allocator.py:11-39`
- ✅ Required at create: customer, RAL + paint code + producer, coating, received date, **pickup date**, area (>0). `app/work_orders/schemas.py:154-177`
- ✅ Quantity defaults to 1. `app/work_orders/schemas.py:157`
- ✅ For profiles & accessories you give **either** a quantity **or** "to count on production", never both/neither. `app/work_orders/schemas.py:128-132`
- ✅ Creating an order captures a **paint stock snapshot** (kg at that moment). `app/work_orders/service.py:202-206`
- ✅ Only OFFICE creates orders / manages attachments / marks "complete on arrival"; OFFICE or MANAGER edits an order. `app/work_orders/service.py:637-642`, `258-262`
- ✅ The office order list **excludes** correction ("P…") orders. `app/work_orders/service.py:371-374`
- ✅ Work-order status is **derived** from progress, never set manually. `app/work_orders/service.py:166-174`
- ✅ "Overdue" = pickup date is before today AND the order is not yet READY. `app/work_orders/service.py:793-797`
- ✅ "Released to client" can only be set on a READY order. `app/work_orders/service.py:447-457`
- ✅ Attachments: PDF / PNG / JPG only, size-capped by config. `app/work_orders/service.py:150-154`

## 3. Stage flow & routing

- ✅ Route is derived from coating + line: SURFACE_PREPARATION → (HANGING unless MANUAL) → PRODUCTION → PACKING → (DECORAL_PRODUCTION if DECORAL). `app/process/service.py:88-102`
- ✅ MANUAL has no HANGING; AUTOMATIC has no PRODUCTION (the line paints itself). `app/process/service.py:96-98`, `1450-1454`
- ✅ PRZEMALOWANKA skips SURFACE_PREPARATION; corrections skip SURFACE_PREPARATION. `app/process/service.py:1467-1469`, `1461-1465`
- ✅ Allowed status moves: NOT_STARTED→IN_PROGRESS; IN_PROGRESS→{DONE, NOT_STARTED}; DONE→{IN_PROGRESS, NOT_STARTED}. `app/process/service.py:1290-1299`
- ✅ A stage won't start until the previous stage is DONE. `app/process/service.py:1301-1308`
- ✅ A fully-ready order can't be sent backward by reopening an earlier stage — that requires the correction flow. `app/process/service.py:1284-1288`
- ✅ "Reopen" steps a stage down one level; blocked when there is no active quantity left. `app/process/service.py:507-523`
- ✅ AUTOMATIC: at HANGING start, PACKING immediately goes IN_PROGRESS — packing runs in parallel with the line. `app/process/service.py:223-233`
- ✅ AUTOMATIC packing can be worked while hanging is in progress but completed only once hanging is DONE and paint consumption is recorded. `app/process/service.py:1524-1548`, `697-700`
- ✅ Each stage action is restricted to its station. `app/process/service.py:1413-1427`
- ✅ SURFACE_PREPARATION and PACKING are **physically shared** across both lines; their order is derived separately (not from the per-line queue position) and line-labelled. `app/process/service.py:279-358`
- ✅ Surface-prep order: feed the line with the **smaller** "prepared-but-not-yet-painted" buffer (in pieces); ties → AUTOMATIC. `app/process/shared_stage.py:49-89`

## 4. Quantities & counting

- ✅ Finishing surface preparation **requires** a counted quantity; >0 and ≤ active quantity. `app/process/service.py:2547-2550@def _ensure_surface_preparation_counted_quantity`, `2529-2545@def _store_surface_preparation_counted_quantity`
- ✅ The surface-prep count becomes the **"actual received"** quantity that packing must match. `app/process/service.py:2724-2751@actual received`
- ✅ **(CHANGE #12 done 2026-07-11, owner decision D5)** an **intake undercount** (prep counts fewer than ordered) is a legitimate completion: at finalization the order is **redefined to the counted amount** ("becomes a 3-piece order") and the original ordered quantity is preserved in the `work_order.total_quantity_redefined` audit event — ordered-vs-arrived lives in the audit trail, not on the order. `app/process/service.py:2358-2377@total_quantity_redefined`, `2452-2481@def _is_settled_intake_undercount`
- ✅ Packing count must equal the surface-prep actual (or, in a correction round, the correction batch size). `app/process/service.py:722-733`
- ✅ At packing: good + to-correct = counted. `app/process/service.py:714-720`
- ✅ Paint consumption shown on an order is the cumulative kg across the whole correction chain. `app/process/service.py:2556`

## 5. Corrections & Decoral

There are two quality checkpoints on a DECORAL order, because two things can go wrong:

- **Paint defect — caught at PACKING (before Decoral).** The bad pieces become a separate **child "P…"** order (which goes back to be **re-painted**); the root gets the **"N" marker**; the root's **good pieces proceed to Decoral immediately**. ✅ `app/process/service.py:1986-2049`
- **Foil defect — caught at/after DECORAL.** **No child** — only the bad pieces return as the **same order** (RAL-style replan-in-place, base coat re-painted), no "P" number. ✅ `app/process/service.py:954-967`

Details:
- ✅ Three correction kinds, chosen at one seam: fixed-on-the-spot (stat only), same-order replan, spin-off child. `app/process/enums.py:113-123`, `app/process/service.py:1864-1879`
- ✅ "Fixed on the spot" records only a statistic — no child, no batch; pieces count as good, order completes as-is. `app/process/service.py:1881-1909`
- ✅ **(CHANGE #1 done 2026-06-26)** same-order replan still clears the *live* lock (it can't sit on an unplanned order) but now **remembers** the pin/urgent intent in `pending_planning_priority` and **re-applies** it when the order is re-planned. `app/process/service.py:2237-2245`, `app/manager/service.py:1399-1404@pending_planning_priority`
- ✅ Correction numbers come from the **root**: `P{root}`, then `P{root}-2`, `P{root}-3`… regardless of nesting. `app/process/service.py:2101-2123`
- ✅ A correction child inherits paint/colour/customer/dates/area and is always STANDARD kind. (Kind is irrelevant to the prep-skip — that comes from being a correction.) `app/process/service.py:2125-2169`, `1461-1465`
- ✅ There is exactly **one Decoral pass, on the root**; a fully-fixed child's good pieces return to the root's Decoral and the child closes without its own Decoral. `app/process/service.py:2001-2021`, `2093-2099`
- ✅ Returned pieces **grow** the root's ongoing Decoral batch (case 1); if the root's Decoral was already done, they start a **fresh** Decoral batch and Decoral re-opens (case 2). `app/process/service.py:2060-2091`
  - ⚠️ **CHANGE #2** — case 2 (a second, separate Decoral pass) is correct but should be made **clearly visible** to the operator.
- ✅ Planning a correction pre-marks every stage before its return stage as DONE (so it doesn't restart from scratch). `app/process/service.py:1852-1857`, `1438-1448`
- ✅ Return stage: AUTOMATIC → HANGING; otherwise PRODUCTION. `app/process/service.py:1429-1436`
- ✅ "N" marker = a DECORAL order with open correction children (can't close until they return). It clears when the child returns. `app/process/service.py:2400-2407`
- ✅ Reason: category ≤64 chars, note ≤500; required when there are bad pieces, forbidden otherwise; profile/accessory split must sum to the bad count. `app/process/service.py:1356-1404`

## 6. Completion

- ✅ RAL packing with no correction: order credits the good pieces and the main batch closes. `app/process/service.py:790-795`
- ✅ DECORAL packing with no correction does **not** complete the order — pieces move on to Decoral. `app/process/service.py:806-811`
- ✅ DECORAL completion (no correction) credits the good pieces. `app/process/service.py:980-986`
- ✅ READY = all pieces credited (completed = total) AND no active pieces AND all correction children complete. `app/process/service.py:2496-2501@def _is_complete_for_display`
- ✅ Finalization walks up the parent chain — closing the last child closes the root. `app/process/service.py:2339-2431@def _finalize_completion_chain_if_ready`
- ✅ **(CHANGE #12 done 2026-07-11)** a **settled intake undercount** (all counted pieces credited, fewer than ordered) finalizes like any completion: redefined to the counted amount (see §4), queue slot released, **no leak flag** — it is the owner-blessed path, not a leak. `app/process/service.py:2452-2481@def _is_settled_intake_undercount`
- ✅ **(CHANGE #10 done 2026-06-26)** if pieces "leak" (credited ≠ total at close, and the gap is **not** a settled intake undercount) the order is still forced to total so it can close, but it is now **human-visible**: a persisted `quantity_leak_flagged` flag on the order (surfaced in the read models) + a SYSTEM audit event `work_order.quantity_leak_detected`, not just a technical log line. `app/process/service.py:2379-2406@quantity_leak_flagged = True`, `app/work_orders/models.py:150-154`
- ✅ A completed correction child is marked a "historical correction". `app/process/service.py:2503-2504@def is_historical_correction`
- ✅ Display-status precedence: incomplete → ready → to-plan → (batch status) → waiting-for-corrections → first unfinished stage. `app/process/service.py:1132-1164`

## 7. Packing slots & resource locks

- ✅ N packing slots (configurable); **default N = 2**. `app/process/resource_locks.py:154-158`, `app/core/config.py:45`
- ✅ Single-station by default; only a **manual** order opens a 2nd slot (via override or completion); an automatic order always uses the single station. `app/process/resource_locks.py:177-230`
- ✅ An automatic order **reserves a packing slot at HANGING start** (so a manual order can't block the un-pausable line). `app/process/resource_locks.py:237-247`
- ✅ A 2nd automatic order **queues silently** (no 2nd slot). `app/process/resource_locks.py:188-216`
- ✅ An order can release its packing claim without completing (wrong order picked); can't release another's. `app/process/service.py:607-643`
- ✅ HANGING is a single-holder resource; the AUTOMATIC line is a single-holder resource (from hanging-done to packing-done). `app/process/resource_locks.py:88-103`, `321-338`
- ✅ The manager sees these as block reasons ("Zawieszanie zajęte" / "Linia automatyczna zajęta"). `app/process/service.py:1189-1211`
- ✅ Stale locks are auto-recovered when the owner no longer occupies the resource. `app/process/resource_locks.py:169-175`, `251-273`
- ✅ The model assumes a single backend worker. `app/process/resource_locks.py:1-20`

## 8. Planning queue

- ✅ Only the MANAGER plans / views statistics. `app/manager/service.py:1922-1935@allowed_station_ids={StationId.MANAGER}`
- ✅ Planning requires the order to be unplanned and not incomplete-on-arrival. `app/manager/service.py:1377-1380@Cannot plan incomplete order`
- ✅ The manager **picks the line at plan time**; planning an order **as AUTOMATIC** is hard-blocked if its metered colour is out of stock / insufficient (MANUAL is not checked). `app/manager/service.py:1382-1397@_assert_paint_available_for_automatic`, `1324-1366@def _assert_paint_available_for_automatic`
- ✅ Planning with no explicit position appends to the **end of the line's active queue**. `app/manager/service.py:1387-1393@_next_active_queue_position_for_line`
- ✅ **(CHANGE #3 done 2026-06-26)** on completion an order **leaves the line's active queue and releases its position** (keeping its line); the trailing/shuffle machinery was removed. Completed correction children release their slots too when the root finalizes. `app/process/service.py:2408-2440@release_queue_slot`
- ✅ **(CHANGE #13 done 2026-07-11)** a position is "taken" only by a non-READY order; a READY order still holding a position (legacy data from before CHANGE #12) is **released on the spot** by the availability check (audited `manager.stale_queue_slot_released`) instead of colliding on the unique index. `app/manager/service.py:1961-1996@stale_queue_slot_released`
- ✅ **(CHANGE #13 done 2026-07-11)** a queue-position collision at flush time returns a controlled **409** ("position already taken"), not a raw 500 — on plan, queue-position update and line switch alike. `app/manager/service.py:1408-1421@except IntegrityError`
- ✅ A line switch is blocked once hanging/production started; switching re-appends at the end and clears the pin. `app/manager/service.py:1557-1577@work_order.planning_priority = None`
- ✅ Drag-reorder uses staleness protection and must include all active orders of that line, that line only, no duplicates. `app/manager/service.py:1631-1668@must include all active planned work orders`
- ✅ PIN = lock to slot; URGENT = force to front; none = freely re-orderable. `app/shared/enums.py:78-92`
- ✅ "Arrange automatically" only **proposes**; the manager applies it. `app/manager/service.py:1859-1871@without committing anything`

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

- ✅ Predicted demand = area ÷ 4 if area < 100 m², else area ÷ 6, rounded to whole kg. `app/work_orders/schemas.py:308-312`
- ✅ Shortage = predicted − current stock (rounded up), shown when predicted exceeds stock. `app/work_orders/schemas.py:315-328`
- ✅ Automatic paint consumption: AUTOMATIC only, after hanging start, needs paint code, **write-once** (no edit after save; correct via a manual office adjustment). `app/process/service.py:847-864`
- ✅ Recording consumption decrements stock; errors if insufficient. `app/paints/service.py:130-153`
- ✅ A colour is "tracked" only with real movement history (not the 0-kg auto-placeholder). `app/paints/service.py:155-159`
- ✅ Movement types: opening balance, delivery, automatic consumption, manual adjustment; deliveries/adjustments are office-only. `app/shared/enums.py:95-99`

## 11. Statistics

- ✅ Throughput m² is attributed to the **packing-completion day**; correction orders are **excluded** (their pieces were already counted on the parent — avoids double-counting). `app/manager/service.py:253-346@WorkOrder.is_correction == False`
- ✅ The Decoral pass is a **separate, additional** m² series at its own completion day. `app/manager/service.py:387-421@decoral_done_events`
- ✅ Every production stat is cut two ways at once: by method (manual/automatic) and by coating (RAL-only/decoral). `app/manager/service.py:149-156@_COATING_SEGMENTS`
- ✅ A "correction event" has one shared definition unioning correction batches + child "P" orders + fixed-on-the-spot. `app/manager/repository.py:105-128`
- ✅ Cycle time = most-recent completed pass per stage; lead time = first start → packing done. `app/manager/service.py:454-671@def get_cycle_time_stats`
- ✅ WIP aging = orders currently IN_PROGRESS, aged from the last entry into progress. `app/manager/service.py:672-763@def get_work_in_progress_aging`
- ✅ **(CHANGE #9 done 2026-06-26)** the shift length per day is **persisted** (`day_shift_lengths`, set by the manager) and judges each day against its floor 800/500 + hours 14/8 — used by **both** the "good day" measure **and** the forward plan (CHANGE #4); a day with no stored length falls back to LONG. `app/manager/service.py:884-898@floor_m2(day_shift)`, `app/manager/models.py` (`DayShiftLength`)

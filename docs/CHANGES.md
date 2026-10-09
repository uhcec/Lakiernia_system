# Change List — code vs. how the factory should work

Found during the code-grounded adjudication pass with the owner on **2026-06-26**. Each item: what the
code does now (`file:line`), what the owner wants, and why. See `docs/SPEC.md` for confirmed behavior.

| # | Type | Title |
|---|------|-------|
| 1 | bug | A correction must not lose its pin/urgent lock ✅ |
| 2 | UX | Make the second, separate Decoral pass visible ✅ |
| 3 | change | Completed orders leave the queue (release their position) ✅ |
| 4 | change | Manager sets the shift length (drop auto-advising) ✅ |
| 5 | change | Colour-change cost by size only (drop direction) ✅ |
| 6 | change | Two scheduling rules (deadline → colour) ✅ |
| 7 | change | Drop RAL-lightness guessing ✅ |
| 8 | change | Flag untracked colours instead of silent OK ✅ |
| 9 | change | Persist the actual shift length for "good day" ✅ |
| 10 | change | Make the quantity-leak tripwire human-visible ✅ |
| 11 | bug | Enforce SQLite foreign keys (order creation 500 on reused id) ✅ |
| 12 | bug | Undercount completion never finalizes — "Gotowe" at 3/5, queue slot never released ✅ |
| 13 | bug | Planning into a slot held by a READY order → raw 500 (flush outside the 409 handler) ✅ |
| 14 | bug | A DONE stage can restart while downstream is active — count rewritten mid-flight ✅ |
| 15 | bug | Office list silently caps at 50 orders (no pagination) ✅ |
| 16 | debt | Frontend floor-robustness batch (JSON.parse, stale-response guards, EN errors, 401 drafts) ✅ |
| 17 | debt | QC document requires Windows + Excel COM — 500 on Linux; absent from SPEC ✅ |
| 18 | feature | Generate WZ (wydanie z magazynu) for a group of ready orders ✅ |
| 22 | change | Automatic paint consumption per paint run (same-paint group), split by m² ✅ |

---

### #1 — A correction must not lose its pin/urgent lock  *(bug)* — ✅ DONE 2026-06-26
- **Now:** when a packing correction sends an order back to planning (replan-in-place), it clears `planning_priority` (pin/urgent) along with the line and position. `app/process/service.py:2237-2240`
- **Want:** the order should keep its pin/urgent intent through the correction round.
- **Note:** the DB allows a planning lock only on a planned order (`app/work_orders/models.py:71-74`), so a returned (unplanned) order can't literally hold one — the intended priority likely needs to be remembered and re-applied when the order is re-planned.
- **Done:** added `work_orders.pending_planning_priority` (migration `20260626_0042`, unconstrained). The replan-in-place parks the live `planning_priority` there before clearing it; `assign_plan` re-applies it (and clears the parked value) when the order is re-planned. Regression test `test_correction_round_remembers_and_restores_pin_NA_CHANGES1`. `app/process/service.py`, `app/manager/service.py`, `app/work_orders/models.py`.

### #2 — Make the second, separate Decoral pass visible  *(UX)* — ✅ DONE 2026-06-27
- **Now:** when corrected pieces return after the root's Decoral was already done, they start a fresh Decoral batch — a correct but easy-to-miss "second pass". `app/process/service.py:2060-2091`
- **Want:** show the operator clearly that this is a separate, second Decoral pass on the returned pieces. Backend logic stays; this is presentation.
- **Done:** the Decoral station now shows a distinct **"DRUGI PRZEBIEG · poprawione sztuki"** badge on exactly that card. Signal (no backend change): a partial Decoral batch (`batch_is_partial`) with no open corrections left (`!is_decoral_incomplete`) on the root order — the returned pieces. The *first* pass (OK pieces while a correction is still open) is deliberately left unmarked. Owner-decided 2026-06-27 (narrow badge, second pass only). New pure predicate `isReturnedDecoralPass` + tests. `frontend/src/utils/workOrderDisplay.ts`, `frontend/src/components/DecoralWorkOrdersPage.tsx`. See `docs/DECISIONS.md` (2026-06-27 — #2).

### #3 — Completed orders leave the queue  *(change)* — ✅ DONE 2026-06-26
- **Now:** a completed (READY) order keeps its line + queue position and stays in the queue as a trailing block; elaborate "trailing/shuffle" logic manages it. `app/manager/service.py:1498-1519`, `2094-2176`
- **Want:** on completion the order **leaves the line's active queue and releases its position**. This makes the trailing/shuffle machinery unnecessary.
- **Before implementing:** check what relies on completed orders staying planned (e.g. the manager board, any statistics).
- **Done:** loosened the planned invariant to "queue_position requires production_type" (a line may exist without a position) — migration `20260626_0043`. On finalize, an order releases its queue position + planning lock but keeps its line (so throughput stats split by line still work); completed correction children release their slots too. Deleted the whole trailing/shuffle machinery (`_get_completed_work_orders_requiring_trailing`, `_temporarily_move_queue_rows_out_of_the_way`, `_trail_completed_work_orders`, `_sort_queue_rows`) and its three call sites. **Owner-decided** (2026-06-26): completed orders also drop off the operator station views (they're done; stations work the active queue). `app/process/service.py`, `app/manager/service.py`, `app/work_orders/models.py`.

### #4 — Manager sets the shift length  *(change)* — ✅ DONE 2026-06-26
- **Now:** when shift length is omitted the system advises long/short from available ready m². `app/manager/capacity.py:165-171`
- **Want:** remove the advising; the manager sets the day length (long/short) explicitly.
- **Done:** deleted `advise_shift_length`; `get_day_capacity`/`get_multi_day_plan` default an omitted shift to LONG instead of advising from m². Dropped the now-meaningless `shift_advised` field from `DayCapacityRead`/`MultiDayPlanRead` (and the unused `manager.ts` type field). `app/manager/capacity.py`, `app/manager/service.py`, `app/manager/schemas.py`.
- **Default note:** LONG was chosen as the unset default (the full day); the manager toggles SHORT explicitly via the `shift_length` query param. See `docs/DECISIONS.md`.

### #5 — Colour-change cost by size only  *(change)* — ✅ DONE 2026-06-26
- **Now:** changeover cost = size band (≤100 m² → 15 min, >100 m² → 30 min) scaled by colour **direction** (light→dark pays half, dark→light full). `app/manager/capacity.py:127-147`, `app/manager/colour.py:157-175`
- **Want:** drop the direction factor; a colour change costs its size band regardless of direction.
- **Done:** removed `CHANGEOVER_LIGHT_TO_DARK_FACTOR` and the `light_to_dark` parameter from `changeover_minutes_for_transition`; `sequence_changeover_minutes` no longer computes direction. Cost is now the next order's size band only. Shipped together with #7. `app/manager/capacity.py`, `app/manager/colour.py`.

### #6 — Two scheduling rules (deadline → colour)  *(change)* — ✅ DONE 2026-06-26
- **Now:** three rules — COLOUR, DEADLINE, "max throughput" (largest single-colour run first) — default order colour → deadline → max-throughput. `app/manager/enums.py:4-51`
- **Want:** only **two** rules (deadline, colour), default order **deadline → colour**; remove "max throughput".
- **Done:** removed `ScheduleRuleKey.CHANGEOVER` + its catalog entry and the `_colour_group_totals`/CHANGEOVER sort branch; default order is now deadline → colour. Stored configs holding the old `"changeover"` key degrade gracefully (unknown keys are dropped in `_resolve_rule_config`). `app/manager/enums.py`, `app/manager/scheduler.py`.

### #7 — Drop RAL-lightness guessing  *(change)* — ✅ DONE 2026-06-26
- **Now:** colour lightness is approximated from the RAL code (first digit + hand-set overrides) to order a light→dark sweep. `app/manager/colour.py:43-102`
- **Want:** remove it. Together with #5, within-day colour planning reduces to **grouping identical colours** (cost = number of changes × 15/30 min by size).
- **Done:** deleted `ral_lightness` + the `_RAL_*` lightness tables; `light_to_dark_order` → `group_identical_colours` (groups ordered alphabetically by colour identity, "no colour" last). `ColourOrderable`/`SequencedOrder`/`AutomaticPassObservation` lost their now-dead `ral_code` field. Within-day colour planning is now pure grouping. `app/manager/colour.py`, `app/manager/measurement.py`, `app/manager/service.py`.

### #8 — Flag untracked colours instead of silent OK  *(change)* — ✅ DONE 2026-06-26
- **Now:** a colour with no stock history (only the 0-kg auto-placeholder) is treated as silently "OK" — the planner makes no claim. `app/manager/paint_feasibility.py:120-133`
- **Want:** surface it as a distinct visible state ("stock not entered — enter it") rather than silent OK. (Can't hard-block on unknown — but should not be invisible.)
- **Done:** added `PaintFeasibilityStatus.STOCK_NOT_ENTERED`. A coloured order with no stock row, or only the untracked 0-kg placeholder, now gets that status (collected in `PaintForwardView.stock_not_entered_order_ids` / `PaintForwardViewRead`); it is never hard-blocked. A truly colourless order stays OK. `app/manager/paint_feasibility.py`, `app/manager/schemas.py`, `app/manager/service.py`.

### #9 — Persist the actual shift length for "good day"  *(change)* — ✅ DONE 2026-06-26
- **Now:** every past day is measured against the long-day bar (800 m² / 14 h) because the actual shift length run that day isn't stored. `app/manager/service.py:805-818`
- **Want:** persist the actual shift length per day and measure "good day" against it. (Connects to #4.)
- **Done:** new `day_shift_lengths` table + model (migration `20260626_0044`); manager endpoints `GET/PUT /manager/day-shift-length?day=…` to read/record the day's shift length (audited). `get_good_day_stats` now measures each day against its persisted shift (floor 800/500, hours 14/8), defaulting to LONG when unset. `app/manager/models.py`, `app/manager/repository.py`, `app/manager/service.py`, `app/manager/router.py`, `app/manager/schemas.py`.

### #10 — Make the quantity-leak tripwire human-visible  *(change)* — ✅ DONE 2026-06-26
- **Now:** at finalization, if credited pieces ≠ total, the order is forced to total and a warning is written **only to the technical server log**; no human sees it. Verified live 2026-06-26: a 7/10 leak was silently completed to 10/10 with only a log warning. `app/process/service.py:2343-2350`
- **Want:** the leak is a sign of an upstream bug — keep the tripwire but make it **visible to a human** (e.g. a flag on the order) so it gets investigated, instead of a silent auto-complete. The quantity model should prevent leaks in the first place; this is the safety net.
- **Done:** added a persisted `work_orders.quantity_leak_flagged` boolean (migration `20260626_0041`), set in the finalize tripwire, exposed in `WorkOrderRead` (office + manager read models), plus a SYSTEM audit event `work_order.quantity_leak_detected`. The order still force-closes to total (so work isn't stuck) but the leak is no longer silent. `app/process/service.py`, `app/work_orders/models.py`, `app/work_orders/schemas.py`.

### #11 — Enforce SQLite foreign keys  *(bug, found 2026-06-29)* — ✅ DONE 2026-06-29
- **Now:** order creation returned HTTP 500 (UI: "Nie udało się utworzyć zlecenia"). SQLite ignores `ON DELETE CASCADE`/`SET NULL` unless `PRAGMA foreign_keys = ON` per connection, and the pragma helper never set it (`app/database/session.py`). Earlier work-order deletions silently orphaned their batches/stage-states/transition-events; a new order reused a freed id (ids aren't AUTOINCREMENT) and its active `MAIN` batch collided with the orphan active batch on `uq_work_order_quantity_batches_one_active_per_work_order` → IntegrityError → 500.
- **Want:** foreign keys enforced so deleting an order removes its child rows; order creation never collides on a reused id.
- **Done:** added `PRAGMA foreign_keys = ON` to `_apply_sqlite_pragmas` and mirrored it in the test engines (`tests/conftest.py::_make_test_engine`; teardown drops the now-redundant `drop_all`). Regression tests `test_foreign_keys_pragma_is_enabled` + `test_deleting_work_order_cascades_to_child_rows` (`tests/test_db_constraints_phase1.py`). Cleaned existing orphan rows from the dev `local.db` (backed up). See `docs/DECISIONS.md` (2026-06-29).

### #12 — Undercount completion never finalizes  *(bug, found 2026-07-11)* — ✅ DONE 2026-07-11
- **Now:** an order whose surface-prep count is below the ordered total (owner-confirmed intended path,
  `docs/DECISIONS.md` 2026-06-30) completes packing and shows **READY ("Gotowe")** via the
  all-stages-DONE fall-through (`app/process/service.py:1170`) — but `_can_finalize_work_order`
  (`app/process/service.py:2422`) requires `completed == total` or correction children, so finalize
  never runs: `total_quantity` is never redefined to the counted amount (the ADR's "becomes a 3-piece
  order" is not implemented), the queue position is **never released** (CHANGES #3 fails on this path),
  and the CHANGES #10 leak tripwire never fires. Verified live 2026-07-11 (order 5 planned / 3 counted
  / 3 packed → "Gotowe" 3/5, slot still held). See `docs/INDEPENDENT_REVIEW_2026-07-11.md` §1.1.
- **Want:** one definition of "complete". On a quantity-short completion the order finalizes per the
  owner's 2026-06-30 intent — releases its queue slot, records ordered-vs-arrived in an audit event —
  with the presentation decided by the owner (**GO_LIVE D5**: redefine `total_quantity` to the counted
  amount vs. keep the shortfall visible as ordered-vs-arrived). Regression tests for the 3-of-5 path
  and for planning into the released slot.
- **Done:** per D5 (owner 2026-07-11): a **settled intake undercount** (prep counted < ordered, all
  counted pieces credited — `_is_settled_intake_undercount`) now finalizes: `total_quantity` is
  **redefined to the counted amount** with the original preserved in a `work_order.total_quantity_redefined`
  audit event, the queue slot is released (CHANGES #3 machinery), and the redefinition runs **before**
  the #10 leak tripwire so the legitimate undercount is never false-flagged (the DECORAL-child path
  used to flag it and force-close 3 → 5). Pinned-before + fixed-after tests
  `tests/test_undercount_completion_changes12_13.py` (clean RAL, RAL correction round, DECORAL child).
  `app/process/service.py` (`_can_finalize_work_order`, `_finalize_completion_chain_if_ready`).
  SPEC §4/§6 updated; DECISIONS erratum Review-by closed.

### #13 — Planning into a slot held by a READY order → raw 500  *(bug, found 2026-07-11)* — ✅ DONE 2026-07-11
- **Now:** `_ensure_queue_position_available_or_releasable` treats a READY holder's position as free
  (`app/manager/service.py:1938-1951`) but nothing ever releases it, and the partial unique index
  still holds the row — so the commit path dies. Worse, `session.flush()` sits **outside** the
  `IntegrityError → 409` handler in `assign_plan` (`app/manager/service.py:1409`; same pattern at
  `:1460`, `:1567`), so the manager gets a raw **500**, not the intended 409. Verified live
  2026-07-11. Reachable today only via #12's zombies (post-CHANGES-#3, clean completions release
  their slot), so fix together with #12.
- **Want:** flushes moved inside the IntegrityError handling (or the handler widened to cover them);
  the "or releasable" semantics either implemented (actually release the READY holder's slot) or the
  helper renamed/simplified once #12 removes the only source of READY-position holders.
- **Done:** both halves. (a) The three flushes (`assign_plan`, `update_queue_position`,
  `update_production_type`) got their own `IntegrityError → 409` handling — a position collision at
  flush time is now a controlled "position already taken", never a raw 500. (b) The "or releasable"
  semantics is now real: `_ensure_queue_position_available_or_releasable` **releases** a READY
  holder's slot on the spot (via the now-public `ProcessService.release_queue_slot`, flushed before
  the caller's own write, audited as `manager.stale_queue_slot_released`) — self-heals legacy zombie
  rows written before #12; new ones can no longer arise. Tests: slot-reusable end-to-end + fabricated
  legacy-zombie self-heal for plan and queue-position PATCH
  (`tests/test_undercount_completion_changes12_13.py`). `app/manager/service.py`. SPEC §8 updated.

### #14 — A DONE stage can restart while downstream is active  *(bug, found 2026-07-11)* — ✅ DONE 2026-07-11
- **Now:** the transition table allows DONE→IN_PROGRESS on any stage
  (`app/process/service.py:1296-1304`) and the only backward guard fires when the whole order is
  display-complete (`:1283-1294`). With packing IN_PROGRESS, restarting the DONE surface prep
  **overwrites the counted quantity** (the "actual received" ground truth); packing then validates
  against the new count and closes the order terminally inconsistent: 2/5 completed, batch
  deactivated, no leak flag, queue slot held, unfixable from the UI. Verified live 2026-07-11
  (`docs/INDEPENDENT_REVIEW_2026-07-11.md` §1.2).
- **Want:** refuse `start`/`reopen` on a DONE stage while any downstream stage is IN_PROGRESS or DONE
  (SPEC §3 already names the correction flow as the legitimate re-entry), plus one office-only
  administrative reset action for genuinely stuck orders. Extend `tests/chaos/` with a lifecycle
  fuzzer asserting global invariants (no READY order holds a queue position; no all-stages-DONE order
  has `completed < total` unflagged).
- **Done:** guard in `_validate_transition` — a DONE stage rejects `start`/`reopen` (409, Polish
  message) while any downstream stage of the actionable route is IN_PROGRESS/DONE; a recount before
  downstream starts stays allowed (pinned by test). Escape hatch: `POST
  /work-orders/{id}/administrative-reset` — roles per owner decision 2026-07-11 (**office/manager,
  admin bypass**, wider than the review's office-only proposal), resets the route from scratch
  (fresh MAIN batch, counts cleared, plan kept), audited `work_order.administrative_reset`, refused
  for correction-entangled orders; danger-styled button on the office/manager order detail page.
  Tests `tests/test_done_stage_restart_changes14.py` (guard both routes, permissions, re-run after
  reset, correction refusal). The lifecycle fuzzer shipped as its own change (2026-07-11):
  `tests/chaos/lifecycle_fuzzer.py` — seeded state-aware random walks over the real HTTP API
  (undercounts, correction rounds, Decoral merges, hostile pokes at the guards), asserting every
  global invariant after every step, plus two new invariants (*no READY order holds a queue
  position*; *no all-stages-DONE order has an unexplained quantity gap*). First find: the
  duplicate-position invariant itself was over-tight (positions are per-line, SPEC §1) — fixed.
  `app/process/service.py`, `app/work_orders/{service,router}.py`,
  `frontend/src/pages/WorkOrderDetailPage.tsx`, `frontend/src/api/workOrdersApi.ts`. SPEC §3 updated.

### #15 — Office list silently caps at 50 orders  *(bug, found 2026-07-11)* — ✅ DONE 2026-07-11
- **Now:** the office list fetch sends no pagination params (`frontend/src/api/workOrdersApi.ts:56-62`),
  the backend defaults `limit=50` (`app/work_orders/router.py:59`), and the page stores only
  `response.items`, ignoring `response.total` (`frontend/src/pages/WorkOrdersListPage.tsx:89-94`).
  Tiles/tabs are computed from the truncated page; there is no pagination UI. With 64 orders in the
  dev DB the dashboard reports "Wszystkie zlecenia: 50". Verified live 2026-07-11.
- **Want:** send `limit`/`offset`, render `total`, add a pager (or "load more"). Frontend-only —
  the backend response shape is already paginated.
- **Done:** frontend-only, but as **fetch-all paging** rather than a pager UI: the office view's
  tiles/tabs/overdue counts are computed client-side and *depend* on having every order — a pager
  would have kept them wrong per page. `fetchAllWorkOrders` loops `limit=100` (the backend cap)
  advancing `offset` until `total` is covered (empty-page backstop against a pathological loop);
  the list page + its polling refresh use it, so "Wszystkie zlecenia" now shows the true count.
  Unit tests for multi-page, single-page and backstop paths (`workOrdersApi.test.ts`). A real pager
  becomes worth revisiting only if the order archive grows enough to make fetch-all slow (thousands
  of orders — years away at shop volume). `frontend/src/api/workOrdersApi.ts`,
  `frontend/src/pages/WorkOrdersListPage.tsx`.

### #16 — Frontend floor-robustness batch  *(debt, found 2026-07-11)* — ✅ DONE 2026-07-11
- **Now:** (a) unguarded `JSON.parse` of localStorage in a `useState` initializer white-screens the
  app on one corrupt value (`frontend/src/context/AuthContext.tsx:25-28`; `ProtectedRoute` guards the
  same read); (b) the three polling boards (`StageWorkOrdersPage`, `PackingWorkOrdersPage`,
  `DecoralWorkOrdersPage`) lack the stale-response guards other pages have; (c) backend-unreachable
  errors surface as raw English "Failed to fetch" in the Polish operator UI; (d) any 401
  hard-redirects to `/login` discarding unsaved counts mid-packing (12h JWT vs. shift-shared tablets
  is a policy question → session policy decided with D4).
- **Want:** guard the parse; add the stale-response guards; Polish network-failure message with a
  retry affordance. Item (d) **resolved by owner 2026-07-11** (`DECISIONS.md` — session policy):
  shared station login per shift, losing unsaved counts on expiry is acceptable — no
  draft-preservation work. Scope is (a)+(b)+(c) only.
- **Done:** (a) the guarded storage read now lives at the **source** — `readStoredAuthUser` in
  `AuthContext` (clears the corrupt key), reused by `ProtectedRoute` (its private duplicate deleted);
  a corrupt value can no longer white-screen the app from the `useState` initializer. (b) the three
  polling boards (`StageWorkOrdersPage`, `PackingWorkOrdersPage`, `DecoralWorkOrdersPage`) take a
  **request ticket** per load; only the latest ticket may apply state or set an error — a slow
  response resolving after a fresher one is dropped (race pinned by `tests/staleResponseGuard.test.tsx`,
  resolving mocked requests out of order). (c) new `getLoadErrorMessage` (`utils/loadError.ts`):
  ApiError → its controlled Polish message; browser-level fetch rejection (`TypeError` "Failed to
  fetch") → Polish network message; else the caller's generic Polish text — **swept all 37**
  `error.message`-verbatim catch sites across 13 files, so no English browser string ever reaches
  the operator. Frontend build clean; 144/144 tests.

### #17 — QC document requires Windows + Excel COM  *(debt, found 2026-07-11)* — ✅ DONE 2026-07-11
- **Now:** `GET /work-orders/{id}/quality-control-document` drives Microsoft Excel over COM
  (`app/work_orders/service.py:56-98`, pywin32) — works only on a Windows host with Excel installed;
  on Linux it returns a raw 500 (`ModuleNotFoundError: pythoncom`). Verified live 2026-07-11. The
  feature is absent from `SPEC.md`, and it silently couples the GO_LIVE D1 hosting decision to a
  Windows box.
- **Want:** **decided 2026-07-11** (`DECISIONS.md` — D6 + D1): the Excel-formatted card **is
  required** and production runs on a **Windows host with Excel** — so the COM → PDF path **stays**
  (it is the only component rendering the template's exact formatting to PDF; openpyxl cannot
  export PDF). Remaining scope: add the feature to `SPEC.md`; return a clean Polish error (not a
  raw 500) when Excel/COM is unavailable (the dev VPS is Linux); record the Windows+Excel hosting
  constraint in `GO_LIVE.md` §1 (done 2026-07-11).
- **Done:** the feature is now inventoried in `SPEC.md`/`SPECYFIKACJA.md` §2 with the hosting
  constraint spelled out. New `DocumentGenerationUnavailableError` (**503**): the converter's
  Windows/Excel/timeout `RuntimeError`s surface their operator-ready Polish message; a raw COM
  crash mid-conversion is wrapped in a generic Polish message (English internals never reach the
  operator). Regression tests `tests/test_quality_control_document_changes17.py` (converter
  monkeypatched — no Excel needed in CI). The COM → PDF path itself is unchanged per D1/D6.
  `app/work_orders/service.py`, `app/shared/exceptions.py`.

### #18 — Generate WZ (wydanie z magazynu)  *(feature, 2026-07-11)* — ✅ DONE 2026-07-11
- **Want:** the office wants a "Generuj WZ" button that, at any moment, produces a warehouse-issue PDF for a chosen group of ready orders of one client (closes the long-open "WZ + wydanie klientowi" to-do).
- **Owner decisions (2026-07-11):** pick client → tick that client's READY, not-yet-released orders; rows are auto from each order's profile/accessory counts + RAL (an order with neither known → one "Elementy" line); the **only** manual field is the loaded "Kosze dłużycowe" count; NR ZAMÓWIENIA shows **both** the client's and our number; recipient address left blank (handwritten); WZ number auto per-year "kolejny/rok" (1/2026…); **no** stored register (one-off printout, gaps on reprint accepted); generating a WZ does **not** mark orders released (separate step).
- **Done:** template `app/static/templates/wydanie_z_magazynu.xlsx` (built from the owner's file, fonts/borders 1:1, by `scripts/build_wz_template.py`); `WorkOrderService.generate_wz_document` + `WzNumberAllocator` + `wz_number_counters` table (migration `20260711_0045`); OFFICE-gated `POST /work-orders/wz-document`; frontend `GenerateWzModal` + "Generuj WZ" button on the office list. The shared Excel→PDF converter was parametrised (QC-card D6 emphasis behind `emphasize_cell=`) so both documents reuse it; a failed render surfaces as the same controlled Polish 503 as the QC card (#17) and rolls the WZ number back. Tests in `tests/test_wz_document.py`; layout eyeballed against a real render. See `docs/DECISIONS.md` (2026-07-11 — #18) and `docs/REVIEW_LEDGER.md` #8. `app/work_orders/service.py`, `app/work_orders/wz_number_allocator.py`, `app/work_orders/models.py`, `app/work_orders/schemas.py`, `app/work_orders/router.py`, `frontend/src/components/GenerateWzModal.tsx`, `frontend/src/pages/WorkOrdersListPage.tsx`, `frontend/src/api/workOrdersApi.ts`.

### #19 — Undercount finalize dies on the category CHECK; zombie heal misses the append paths  *(bugs in #12/#13, found live 2026-07-11)* — ✅ DONE 2026-07-11
- **Now:** (a) finalizing a settled intake undercount (D5) redefined `total_quantity` alone; on an
  order with a **declared** profile/accessory split (the owner's normal shape — e.g. 10 profiles +
  0 accessories counted at 8) the DB CHECK (`profiles + accessories == total` when both known)
  killed the finalize commit: `packing/complete` returned **500 after the packing part had already
  committed**, stranding a fresh zombie (total 10 / completed 8 / slot held / no audit event). The
  #12 tests missed it because they declare `*_to_count: true` (unknown quantities → CHECK vacuous).
  (b) the #13 zombie self-heal was wired only into the **explicit-position** branch; the default UI
  path (plan with no position → append) and the line-switch re-append compute their slot by
  *skipping* READY holders, so they land exactly on a zombie's held position → 409 "Queue position
  1 is already taken" with nothing visible for the manager to release. Both surfaced by replaying
  the owner's live walkthrough of order 0001 on fixed code (his own walk had raced the #12 commit
  by 14 minutes and ran pre-fix, leaving the zombie that then blocked all MANUAL planning).
- **Done:** finalize now derives the category split **with** the total via the existing
  `_derive_category_fields_for_operational_quantity` policy (single-category order keeps its
  category: 10/0 counted at 8 → 8/0; mixed split falls back to to-count), and preserves the
  ordered split in the `total_quantity_redefined` audit event. The heal call was added to
  `assign_plan`'s append branch and to `update_production_type`. 4 new regression tests in
  `tests/test_undercount_completion_changes12_13.py` (category test verified red on pre-fix code).
  SPEC §4/§6/§8 updated in both languages; verified live end-to-end on the running backend.

### #20 — Line switch to AUTOMATIC dodges the paint hard-block  *(debt, found 2026-07-11, owner decision pending)*
- **Now:** `assign_plan` hard-blocks planning **as AUTOMATIC** when the metered colour is out of
  stock (`_assert_paint_available_for_automatic`, SPEC §8 / N49-7), but `update_production_type`
  (MANUAL→AUTOMATIC line switch) performs **no paint check** — the block is dodgeable by planning
  MANUAL first and switching lines.
- **Want:** owner decision — should the line switch enforce the same hard block? (Recommendation:
  yes; same rationale as N49-7 — an out-of-stock colour on the automat is a leading cause of a
  missed daily norm.)

### #21 — Administrative reset of a completed order leaves it invisible in both planning lists  *(bug, found live 2026-07-11, fix deferred — owner asked to only record it)*
- **Now:** `ProcessService.administrative_reset` (`app/process/service.py:537-594`) resets stage rows,
  batches, `completed_quantity` and the leak flag, but deliberately **keeps the plan**
  (`production_type` + `queue_position` untouched) — its docstring assumes the order is therefore
  "planned again" (`app/process/service.py:543-544`). That only holds if the order still held a queue
  position. When an order is reset **after completion**, finalization has already released the slot
  (`queue_position` → NULL, line kept — CHANGES #3/#12), so after the reset it sits with
  `production_type` set but `queue_position` NULL. `get_display_status` then reports `TO_BE_PLANNED`
  (`_is_planned` requires **both** non-null, `app/process/service.py:1218-1219`), yet **neither**
  planning list returns it: the unplanned query requires `production_type IS NULL`
  (`app/manager/repository.py:80-81`) and the planned query requires `queue_position IS NOT NULL`
  (`app/manager/repository.py:98-99`). Net effect: the order vanishes from both "Do zaplanowania" and
  the planned queue — exactly the owner's live symptom on **order 0001** (admin reset 2026-07-11 ~21:20,
  after it had run through to PACKING DONE at ~21:16). The order is not lost (still readable at
  `GET /work-orders/1`), only unplannable from the manager board.
- **Want:** owner decision on the fix shape (NOT done — owner asked to only record it). Candidates:
  (a) on reset, if the order has a line but no position, also clear `production_type` (and any
  `planning_priority`) so it returns to the genuine unplanned pool and shows in "Do zaplanowania"
  — matches what the owner expected here; or (b) re-append it to its line's queue (restore a
  `queue_position`) so it lands back in the planned queue, matching the docstring's "keeps its plan"
  intent. Either way, consider closing the line-set/position-NULL/not-complete limbo so no order can
  fall between the two list queries.

### #22 — Automatic paint consumption per paint run, split by m²  *(change, owner request 2026-10-09)* — ✅ DONE 2026-10-09
- **Was:** the automatic-production station entered paint consumption **per order** (cartons − remainder)
  after hanging started; write-once; packing could not complete until it was entered
  (`AUTOMATIC_PAINT_CONSUMPTION_REQUIRED_ERROR`, `work_orders.consumed_paint_quantity_kg` as the gate).
- **Want (owner):** orders with the same paint form a group; consumption is entered once after the whole
  group, not per order — the per-order figure cannot be measured (cartons are not swapped between orders of
  one paint). Details and every sub-decision in `docs/DECISIONS.md` (2026-10-09 — #22).
- **Done:** paint runs formed automatically from the automatic hanging sequence; one write-once entry per
  run at the automatic-production station once its orders finished hanging; one stock movement per run;
  kg split onto orders by m²; packing no longer gated on paint; open runs block nothing and are flagged red
  (station + manager panel) once the paint changed. Migration `20261009_0046` (new `paint_runs`,
  `paint_run_members`, `paint_stock_movements.paint_run_id`; dropped `work_orders.consumed_paint_quantity_kg`).
  Tests `tests/test_paint_runs_changes22.py` (+ updated process/manager tests, fuzzer invariant
  `assert_paint_runs_consistent`), frontend `PaintRunsPanel` + `utils/paintCartons.test.ts`. Verified live
  on the running backend as the real station logins. SPEC §3/§4/§10 updated in both languages.
  `app/process/paint_runs.py`, `app/process/service.py`, `app/paints/*`, `app/process/{router,schemas}.py`,
  `frontend/src/components/{PaintRunsPanel,StageWorkOrdersPage}.tsx`, `frontend/src/pages/ManagerPanelPage.tsx`.

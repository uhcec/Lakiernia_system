# Immediate Next Actions

This file is the **single living list of open, actionable work** for this repository. It is
separate from `HARDENING_BACKLOG.md` (which records *closed* hardening evidence) and from
`docs/WORKFLOW.md` (business semantics). Every agent/session should read this file before starting
work and keep it current.

## How to use this file

- Pick the highest-severity OPEN item unless the user directs otherwise.
- Before implementing, follow `docs/WORKING_CONTRACT.md` (problem → risks → docs impact → solution → tests).
- When an item is finished: move it to the "Done" section with a one-line evidence note
  (tests run, files touched), or, if it is durable hardening, also record closure in
  `HARDENING_BACKLOG.md`. Do not silently delete items.
- If you discover new work, add it here with severity, evidence (`file:line`), required fix, and
  acceptance criteria — match the format below.
- Severity: **HIGH** = correctness/security/CI-breaking; **MEDIUM** = real defect or truth/doc drift;
  **LOW** = robustness/cleanup.

Source: extensive system review on 2026-06-16. Items are findings that were **open** at that time;
they are not yet validated against live factory policy where noted.

## Recommended execution order (proposed 2026-06-19)

A suggested sequencing of the currently-open items, grouped by dependency rather than raw severity.
This is a recommendation, not a hard rule — the "highest open severity" guidance above still applies if
no one directs otherwise.

**Phase 1 — quick wins & correctness bugs (small, isolated):**
1. **NA35** — wheel-to-fractional number-field fix. Trivial, no open questions; shared `NumberInput`
   with `step=1`. Good warm-up; immediate operator relief.
2. **NA30** — completion invariant (a completed order can be sent backwards). Real correctness defect,
   well-contained (guard in `start_stage`/`finish_stage` + regression test + `WORKFLOW.md`).
3. **NA31** — manager panel offers a stale queue slot after a correction return. Frontend-only (backend
   already correct); reconcile plan-draft state on the planned→unplanned transition.

**Phase 2 — correction cluster (do together; they interact):**
4. **NA32** — paint consumption doesn't roll up across correction rounds.
5. **NA34** — distinguish "fixed on the spot" (stat-only) vs "to be re-planned" corrections.
   Both touch the correction model (`process/service.py`, RAL/DECORAL paths) and correction stats, so
   doing them separately would mean reworking the same code twice. **Resolve NA34's open owner questions
   first** (stat-only for RAL+DECORAL or RAL only; is the reason required). **NA19** (force-finalize masks
   a quantity gap) can ride along here — it also touches finalize/quantity.

**Phase 3 — new features (independent; ordered by value/effort):**
6. **NA38** — Decoral foil registry + one foil per order. Self-contained lookup table + intake field.
7. **NA36** — technical drawings as a new attachment type. Extends `WorkOrderAttachment`; low risk.
8. **NA37** — WZ document via the QC Excel→PDF mechanism. Reuses the existing pipeline; confirm its open
   questions (template, numbering, trigger) first.
9. **NA33** — auto work-scheduling + colour grouping + stats tidy. Largest of the batch; the stats
   sub-part is **blocked** on the owner's colleague's wishlist. Sequence last, but the scheduler design
   (configurable ordered rule list) is worth sketching earlier.

**Parallel, non-code — NA21:** guided S01–S12 walkthrough with the factory (`docs/SCENARIO_WALKTHROUGH.md`
is ready). Needs the owner/shop floor, not code — run it whenever the owner is available.

Before starting Phase 3, resolve the open owner questions on NA34/NA36/NA37/NA38.

---

## HIGH

### NA1. Authorization is decoupled from authentication — any logged-in user can act as any station
- Status: DONE (2026-06-16) — see Done section. Implemented per the approved
  `docs/AUTHZ_DESIGN_PROPOSAL.md` defaults.

### NA2. `pywin32` is an unconditional dependency — breaks `pip install` on Linux / CI
- Status: DONE (2026-06-16) — see Done section.
- Problem: `pyproject.toml:20` declares `pywin32>=306` for all platforms, but the documented quality
  gate runs on `ubuntu-latest` (`.github/workflows/quality-gate.yml:10,21-22`). pywin32 has no
  Linux-installable distribution, so `pip install -e ".[dev]"` fails on Linux and the backend-tests
  job cannot run as written. It also hard-couples the backend to Windows+Excel for every deployment.
- Required fix: Make it conditional — `pywin32>=306; sys_platform == 'win32'` — and guard the Excel
  code path (see NA5) so its absence degrades gracefully instead of breaking install/import. Document
  the Windows+Excel requirement for the QC-document feature explicitly.
- Acceptance: `pip install -e ".[dev]"` succeeds on Linux and Windows; CI quality gate installs and
  runs; QC document generation still works on Windows.

### NA12. Hardcoded default `JWT_SECRET` allows token forgery
- Status: DONE (2026-06-16) — see Done section. (Note: tokens still have no expiry — NA6 remains open.)
- Problem: `app/core/config.py:29-32` ships a committed default `jwt_secret`. If deployed without
  overriding `JWT_SECRET`, anyone who reads the repo can forge a valid JWT for any user — including
  admin — which is a full authentication bypass. Compounded by tokens having no expiry (NA6).
- Required fix: Remove the usable default — require `JWT_SECRET` from the environment with no committed
  fallback, and fail fast (refuse to start, or refuse to issue/verify tokens) when it is unset/default
  outside development. README/runbook already document the requirement.
- Acceptance: The app will not issue or accept tokens signed with the default/empty secret outside
  development; a real deployment must set `JWT_SECRET`.

### NA13. Frontend test suite is red (7 tests) — CI frontend job fails
- Status: DONE (2026-06-16) — see Done section.
- Evidence (2026-06-16): `npm --prefix frontend run test` → 7 failed / 63 passed in
  `frontend/tests/uiStateConsistency.test.tsx`; `npm run build` passes; backend 347 + Alembic green.
  This is a pre-existing red state on `main` (no frontend source was changed this session).
- Root-cause breakdown (diagnosed 2026-06-16):
  - **Stale tests — old `WO :: Customer` title format (5 tests).** The manager panel and packing page now
    render the primary line via `WorkOrderPrimaryInfoLine` / `formatWorkOrderPrimaryInfo` using ` · `
    separators (and `RalColorDot`), so `findByText("WO-1 :: Alpha")` etc. no longer matches. Affects:
    "resets manager reorder UI…", "does not use historical correction wording…", "shows original pickup
    context…", "shows paint shortage warning in manager planner cards", "shows automatic active hanging in
    packing…". Fix = update the queries (e.g., match the order-number span and customer separately, or a
    flexible matcher). Test-only, no behavior change. Note: after re-locating each card, the test's later
    assertions still need to pass — fix iteratively.
  - **Real UI defect — duplicate discrepancy line (1 test).** `WorkOrdersTable` renders
    `getWorkOrderDiscrepancyText` twice (quantity column `src/components/WorkOrdersTable.tsx:159-161` and
    status column `:257-259`), so the office table shows the same amber line twice for active orders and
    `getByText` throws "found multiple". Recommended fix = remove one render (keep the status-column one,
    which also covers READY). This is a behavior/UX change — confirm placement preference.
  - **Real UI defect — stray `::` span.** `src/pages/ManagerPanelPage.tsx:632` renders a lone
    `<span>::</span>` in every active queue card (leftover from the title refactor). Recommended fix =
    delete it.
  - **Office "ready" bucket result text (1 test).** "groups office work orders into intake/production/ready"
    fails to find `Wynik końcowy: 10 szt.` after switching to the Gotowe bucket — needs a quick check of
    `WorkOrdersListPage` ready rendering to classify as stale-test vs real.
- Decision needed: fix tests-only to match current UI, OR also fix the 2 real UI defects (duplicate
  discrepancy + stray `::`). The latter changes rendered output.
- Acceptance: `npm run test` passes; CI frontend job green; no duplicate discrepancy line; no stray `::`.

---

## MEDIUM

### NA3. `docs/WORKFLOW.md` no longer matches RAL correction behavior (source-of-truth drift)
- Status: DONE (2026-06-16) — see Done section.
- Problem: `docs/WORKFLOW.md` (principle #8; scenario matrix S05/S06/S09/S10) states corrections are
  always a new child work order. The code now has two models: RAL resets the *same* order to planning
  with an in-place `CORRECTION` batch and no child (`app/process/service.py:458-471`, commit 27090fb),
  while DECORAL still spins off a child "P" order (`app/process/service.py:1517+`).
- Impact: The declared source of truth contradicts behavior; a future agent may "fix" working code to
  match a stale spec.
- Required fix: Update `docs/WORKFLOW.md` (principles and the S0x matrix) to describe the hybrid
  correction model accurately.
- Acceptance: `WORKFLOW.md` describes RAL (batch reset) vs DECORAL (child order) correction paths and
  the scenario matrix reflects current behavior.

### NA4. Throughput stats undercount corrections (inconsistent with the reason report)
- Status: DONE (2026-06-16) — see Done section.

### NA5. Excel COM worker is spawned at module import (side-effectful import)
- Status: DONE (2026-06-16) — see Done section.
- Problem: `_excel_pdf_converter = _ExcelPdfConverter()` runs at import of
  `app/work_orders/service.py:110`, starting a daemon thread that `CoInitialize()`s and dispatches
  Excel. Importing the module anywhere (tests, tooling, a worker that never makes a PDF) launches
  Excel on Windows; on Linux the thread dies silently so any QC call hangs to the 60s timeout.
- Required fix: Make the converter lazy (construct on first `convert()`), and raise a clear error when
  the platform/tooling is unavailable instead of timing out.
- Acceptance: Importing `app.work_orders.service` has no side effects; QC generation still works on
  Windows; missing Excel/pywin32 produces an immediate, clear error.

### NA30. A completed order can be sent backwards by re-opening an earlier stage (no completion invariant)
- Status: **DONE (2026-06-22)**. Reproduced first (the bug was real): after a manual RAL order reached
  READY (PACKING=DONE, 10/10, active=0), `transition_stage(PRODUCTION, IN_PROGRESS)` succeeded and left
  `PRODUCTION=IN_PROGRESS` while `PACKING=DONE`. Fix: a completion invariant in `_validate_transition`
  (`app/process/service.py` ~1150) — any transition to `IN_PROGRESS`/`DONE` on a `_is_complete_for_display`
  order is rejected with a controlled `InvalidProcessStageTransitionError`, independent of station
  permission. Safe because the *completing* transitions don't hit this path (`complete_packing` sets
  PACKING `DONE` directly; DECORAL's `finish_stage` runs before completion is recorded). `reopen_stage`
  was already blocked (active==0 guard); this closes the raw `start_stage`/`transition_stage` hole. Tests:
  `test_completed_order_cannot_be_sent_backwards_manual_NA30` and `..._automatic_hanging_NA30` (the
  original report scenario). `docs/WORKFLOW.md` READY Rules now states the invariant. Full backend suite
  green; `alembic check` clean (no schema change).
- Status (original): OPEN (discovered 2026-06-18).
- Problem: An admin (who bypasses `ensure_station_allowed`) could call `start_stage`/`finish_stage` for
  `HANGING` on an order whose terminal `PACKING` stage was already `DONE`, flipping `HANGING` back to
  `IN_PROGRESS` and leaving a contradictory state (`HANG=IN_PROGRESS` while `PACK=DONE`), which then
  misrendered the packing card. Reproduced live on seed order 0002 (audit events 20–22, OFFICE/admin):
  `process.stage.started/finished HANGING` fired after the order was fully packed. `start_stage`
  (`app/process/service.py:243`) has no guard that the order isn't already completed.
- Required fix: Treat completion as a workflow invariant independent of station permission — reject a
  start/finish transition on a stage when the order's terminal stage (`PACKING`, or `DECORAL_PRODUCTION`
  for decoral) is already `DONE`, unless it goes through the proper correction/reopen flow. Decide and
  document (per `docs/WORKFLOW.md`) whether a deliberate admin "reopen completed order" path should exist
  at all, and if so what it resets.
- Acceptance: A `start`/`finish` on an already-completed order returns a controlled error (not a silent
  contradictory state); regression test covers it; `docs/WORKFLOW.md` states the completion invariant.

### NA32. Order's recorded paint consumption under-counts across correction rounds (stock is correct)
- Status: **DONE (2026-06-20)** — commit `59241a1`. The displayed consumed-paint total is now computed
  **cumulatively from the durable `paint_stock_movements` log** across the whole correction chain (order +
  correction descendants, via `WorkOrder.correction_chain_ids` + `PaintRepository.sum_automatic_consumption_kg`),
  wired into all three read models (process / work_orders / manager). The overloaded
  `consumed_paint_quantity_kg` field stays the per-round "paint registered before packing?" gate (still
  reset between rounds); only the display is rolled up, so RAL same-order rounds and DECORAL parent+child
  both report the true total while stock stays correct. No schema change. Tests: updated automatic-correction
  paint assertion to cumulative (13.75), new `test_corrected_order_reports_cumulative_paint_across_chain_NA32`;
  `docs/WORKFLOW.md` paint section updated. 433 backend tests pass; `alembic check` clean.
- Status (original): OPEN (discovered 2026-06-19 during the S06 walkthrough).
- Problem: for an automatic order that goes through a correction round, `WorkOrder.consumed_paint_quantity_kg`
  ends up showing only the **last** round's kg, not the cumulative total. `record_automatic_paint_consumption`
  **sets** (not accumulates) the field (`app/process/service.py:747`), and `_reset_to_correction_planning`
  zeroes it (`app/process/service.py:1967`) to force re-registration for the next round's packing gate. Paint
  **stock is correct** — each registration deducts via its own `paint_stock_movement` — so e.g. 20 kg + 20 kg
  correctly reduces stock by 40 kg, but the order detail (`/work-orders/{id}`) reports 20 kg. The field is
  overloaded: it serves both the per-round "paint registered?" packing gate and the order's total-consumption
  display, and those two needs conflict.
- Two manifestations (both confirmed in the walkthrough):
  - **RAL correction (same order) — data loss (S06):** the field is overwritten/zeroed, so the order shows
    only the last round's kg (e.g. 20 of an actual 40).
  - **Decoral correction (parent + child "P…") — no roll-up (S08):** each order shows its own consumption
    correctly (parent ~20 kg, child ~6 kg — no data loss), but the parent/chain total does not aggregate the
    correction child's kg, so the order chain's true total (≈26 kg) is shown nowhere.
- Required fix: report the order's **cumulative** paint consumption across its whole correction chain (e.g. sum
  of the chain's `paint_stock_movements`, or aggregate parent + children) while keeping a separate per-round
  signal for the packing completion gate. Confirm with the owner that the displayed number should be the
  cumulative total (per order and rolled up for the parent+children chain).
- Acceptance: a corrected automatic order (RAL same-order rounds, and Decoral parent+child) shows total kg =
  sum of all rounds/children; order detail and stock agree; regression tests cover both manifestations.

### NA6. JWT has no expiry
- Status: DONE (2026-06-17) — see Done section.
- Problem: `create_access_token` (`app/auth/service.py:17-23`) issues tokens with no `exp` claim;
  tokens are valid forever and are stored in `localStorage` (`frontend/src/context/AuthContext.tsx:40`).
- Required fix: Add an `exp` claim and verify it in `decode_token`; decide a session lifetime.
- Acceptance: Expired tokens are rejected with `401`; tests cover expiry.

---

## LOW

### NA31. Manager panel suggests/blocks a wrong queue position after a correction returns to planning
- Status: **DONE (2026-06-22).** Frontend-only, as diagnosed. Root cause: `loadManagerData` skipped
  `setPlanDrafts` entirely on the background-poll path (to avoid clobbering an actively-typed position),
  but that's also where the suggested default position (`activeCount + 1`) is computed — so a
  planned→unplanned correction return left a stale suggested position until F5. Fix: new
  `reconcilePlanDrafts(current, unplanned, nextPos)` helper (`frontend/src/pages/ManagerPanelPage.tsx`)
  that the background path now uses — it preserves drafts the manager is typing (keyed by id), drops
  drafts for orders that left the unplanned list, and seeds a fresh default (derived from the
  freshly-polled planned list → 1 when empty) for orders that just reappeared. Foreground path unchanged;
  no correction/queue meaning invented client-side. New test `frontend/tests/managerPlanDraftReconcile.test.tsx`
  (fails before / passes after): a background poll returning the order unplanned with an empty queue now
  offers/accepts position 1 with no refresh. 83 frontend tests pass + build clean.
- Status (original): OPEN (discovered 2026-06-19 during the S05 walkthrough).
- Problem: when a RAL order is sent back to planning by a packing correction, the manager panel
  transiently offers a queue position > 1 and treats position 1 as taken, even when the queue is
  otherwise empty — until the user refreshes (F5). **Backend is correct** (verified): `_reset_to_correction_planning`
  (`app/process/service.py:1966`) sets `queue_position = None`, `get_planned_by_queue_position(1)` returns
  `None`, and `assign_plan(..., queue_position=1)` is accepted. The stale state is frontend-only: after the
  correction the panel keeps showing the order's old position-1 planned row (polling refreshes data but the
  background path does not rebuild plan drafts — `frontend/src/pages/ManagerPanelPage.tsx:306-307`), so the
  suggested default (`normalizedActivePlanned.length + 1`, line 307) and the local "taken" view are based on
  the stale planned list.
- Required fix: ensure the manager queue/plan-draft state reconciles immediately when an order moves from
  planned → unplanned (correction return), so position 1 is offered/accepted without a manual refresh.
- Acceptance: right after a packing correction, planning the returned order at position 1 works in the UI
  with no F5; regression/UI test covers the planned→unplanned transition.
- Observation (2026-06-19, S09 multi-round): **intermittent** — recurred at the 1st correction round but not
  the 2nd (the panel had refreshed by then). Reinforces that this is a stale-view / refresh-coherence issue,
  not a deterministic logic error in position freeing.

### NA7. Weekly throughput dates computed inconsistently
- Status: DONE (2026-06-17) — see Done section.
- Problem: `func.strftime('%Y-%W')` (non-ISO weeks `00`–`53`) is grouped, then `_parse_period_start`
  converts with `date.fromisocalendar(year, week+1, 1)` plus a `<52` special case
  (`app/manager/service.py:95,762-771`). The conventions don't line up; week starts/labels drift,
  especially near year boundaries.
- Required fix: Use one consistent week convention end-to-end (prefer ISO `%G-%V` with
  `fromisocalendar`).
- Acceptance: Weekly period start dates and labels are correct across year boundaries; covered by a test.

### NA8. Multi-worker concurrency relies on in-process locks (deployment constraint)
- Status: DONE (2026-06-17) — documented in runbook; see Done section.
- Problem: `_PROCESS_MUTATION_LOCKS`/`_RESOURCE_MUTATION_LOCKS` (`app/process/service.py:26-29`) and
  `_QUEUE_MUTATION_LOCK` (`app/manager/service.py:53`) only serialize within one process. DB-level
  guards (queue position, one-active-batch, resource-lock PK) survive multi-worker, but the
  "no duplicate correction child per packing split" guarantee depends on the in-process lock.
- Required fix (near-term): Document and enforce a single-worker deployment (e.g., README/runbook +
  a startup note). Longer-term: a durable idempotency/revision strategy before claiming multi-worker
  safety.
- Acceptance: Deployment docs state the single-worker constraint and why; or a durable dedup guard exists.

### NA9. SQLite engine has no `busy_timeout`/WAL
- Status: DONE (2026-06-17) — see Done section.
- Problem: `get_engine` (`app/database/session.py:13-17`) sets `check_same_thread=False` but no
  `busy_timeout` or WAL pragma. Under the documented multi-operator assumption, concurrent writers can
  surface raw `database is locked` errors.
- Required fix: Set `PRAGMA busy_timeout` and WAL via a connection event for SQLite URLs.
- Acceptance: Concurrent writes wait/retry instead of erroring; dev runbook unaffected.

### NA10. bcrypt 72-byte truncation not guarded
- Status: DONE (2026-06-17) — see Done section.
- Problem: `hash_password` (`app/auth/service.py:9-14`) silently truncates passwords >72 bytes.
- Required fix: Validate password byte length at registration/change, or pre-hash.
- Acceptance: Over-long passwords are rejected or handled deterministically.

### NA15. Dedicated Decoral-pass (`DECORAL_PRODUCTION`) throughput chart
- Status: DONE (2026-06-17) — see Done section.
- Still open (minor, optional): whether the Decoral chart should also show **pieces** (m² shipped as the
  confirmed default), per the Polish question set sent 2026-06-17.

### NA14. `WorkOrdersTable` is dead code (kept alive only by tests)
- Status: DONE (2026-06-17) — see Done section.
- Problem: `frontend/src/components/WorkOrdersTable.tsx` is imported only by `uiStateConsistency.test.tsx`;
  the office list page uses `OfficeWorkOrdersTable`. Discovered during NA13. It keeps drifting from the
  real UI (it still carried a duplicate discrepancy render, now removed).
- Required fix: Either delete `WorkOrdersTable.tsx` and its 3 dedicated tests, or repurpose it if it is
  meant to return. Confirm intent before deleting.
- Acceptance: No dead component-under-test; the office table has a single source of truth.

---

## Verification / follow-up (not a defect, but pending)

### NA11. Confirm current test-suite state
- Status: DONE (2026-06-16)
- Result (after the NA5 lazy-Excel fix, so importing no longer launches Excel):
  - `python -m pytest` → **347 passed**.
  - `python -m alembic check` → clean ("No new upgrade operations detected").
  - `npm --prefix frontend run build` → passes.
  - `npm --prefix frontend run test` → **7 failed / 63 passed** (pre-existing — tracked as NA13).

---

## Open (from the 2026-06-17 workflow audit)

### NA19. Finalize force-sets `completed_quantity = total_quantity` without surfacing a mismatch
- Status: **DONE — verified already implemented (2026-06-22).** This was already fixed and committed but
  the backlog never marked it. `_finalize_completion_chain_if_ready` (`app/process/service.py:2304-2313`)
  logs a `logger.warning` with order number + completed + total when `completed_quantity != total_quantity`
  before force-setting to total (it surfaces the gap, does not crash). Module logger at `service.py:28`.
  Regression tests present: `test_finalize_does_not_warn_when_quantities_match` and
  `test_finalize_warns_and_forces_total_when_quantity_gap` (`tests/test_process_service.py:1577,1600`).
  Verified by an NA19 subagent (2026-06-22): 71 tests pass; no new code change needed.
- Severity: LOW. `ProcessService._can_finalize_work_order` finalizes when correction children exist,
  no open corrections remain, and `current_active_quantity == 0` — then sets `completed = total` even
  if `completed < total`. Quantity conservation should make them equal, so this is a safety net, but it
  would *mask* a hypothetical leak rather than surface it.
- Fix: assert/log when `completed != total` at force-finalize instead of silently overwriting.
- Acceptance: a finalize with an unexpected quantity gap is observable (log/raised), normal cases
  unchanged.

### NA20. Multi-worker durability for "no duplicate correction child" (carried from NA8)
- Severity: known/accepted. The guarantee relies on the in-process lock; documented single-worker
  deploy. Durable cross-process idempotency remains future work.

### NA23. Every production stat should also expose a manual / automatic / decoral breakdown that sums to the whole
- Status: **DONE (2026-06-18)** — throughput (2026-06-17) + cycle-time & WIP-aging (2026-06-18) all carry
  the two cross-sections; see Done section. Remaining unit work (m²→pieces toggle) split out as **NA29**
  so it is tracked as its own open item rather than a parenthetical.
- Severity: MEDIUM (truth/visibility — managers can't see what composes a production total).
- Problem: the Statystyki stats currently surface production figures (pieces, m², cycle-time,
  WIP-aging, etc.) without a consistent, drill-down split into the three production kinds. Some series
  are already split (base-coat m² by `production_type`, the dedicated Decoral-pass chart), but the rest
  of the production stats show only an aggregate.
- Required fix: for **every** stat that reports production, also offer a more detailed view broken down
  into **manual**, **automatic**, and **decoral** production, where the parts sum to the displayed
  whole. Decide whether this is a per-stat expandable detail or columns; keep `manual + automatic
  (+ decoral as documented)` reconciling to the total so the breakdown is auditable.
- Acceptance: each production stat on the Statystyki page can show the manual/automatic/decoral split;
  the parts visibly sum to the aggregate; covered by tests.
- **Reconciliation RESOLVED (2026-06-17, owner interview → `docs/FACTORY_DOMAIN_MODEL.md` §4.1):**
  production method and coating are two *independent axes*; a decoral order is ONE product counted
  ONCE (m² through the factory). So "manual + automatic + decoral" is NOT a valid single sum (it would
  double-count decoral orders, which already sit inside manual/automatic). Instead the detailed view is
  **two independent partitions of the same total**, each of which sums to the whole:
  (1) by production method `manual + automatic = total`, (2) by order coating type
  `RAL-only ("czysty RAL") + decoral = total` — the RAL bucket is RAL-*only* orders, NOT "all RAL
  coats" (a decoral order counts once, on the decoral side; mislabeling it "RAL" breaks the sum).
  "manual + automatic + decoral" is NOT a valid single sum. The existing "Przejazd Decoral" m² is a
  *separate line-workload counter* (coats applied, overlaps base coat) and must stay out of the total.
  m² is the primary unit; pieces secondary but should be supported.
- Still to confirm before building: exactly which stats beyond throughput get it (cycle-time,
  WIP-aging) — deferred. m² first; pieces later via the same pattern.

#### Proposed visualization (agreed with owner 2026-06-17, NOT yet implemented)
Theme: **one total, shown in two cross-sections** — makes it obvious it's the same whole cut twice,
not three separate slices. Scope of this first pass = the **Przepustowość** (throughput) section, m²
only. Five elements, top to bottom:
1. **Headline** — "PRZEZ FABRYKĘ · {miesiąc}: {m2_total} m² · {orders_count} zleceń".
2. **"Skład produkcji" — two equal-width horizontal 100% bars** (same total length), cut differently:
   one by method (Ręczna / Automat), one by coating (Czysty RAL / Decoral). The equal length visually
   asserts both partitions equal the same whole. Cheap to build (flex-width divs), highest "wow".
3. **Daily stacked bar chart with a cross-section toggle** `[ Metoda ] ( Powłoka )` — bar segments
   switch between Ręczna/Automat and Czysty RAL/Decoral; **total bar height stays constant** when
   toggling (reinforces "two cuts of one whole"). Extends the existing `BarChart` to stacked.
4. **Przejazd Decoral** — keep the existing separate small chart, explicitly labelled "obciążenie
   linii decoral — nie wlicza się do sumy" (this is coats-applied workload, overlaps base coat).
5. **Detail table with grouped columns** — `Okres | Razem | (Ręczna, Automat) | (Czysty RAL, Decoral)
   | Przejazd Decoral*`, where each group sums to Razem (visually verifiable), przejazd flagged with
   `*osobny licznik, nie wlicza się do „Razem"`.
- Backend shape when built: add to `ThroughputPeriod` the coating-of-order split, e.g.
  `m2_ral_only` + `m2_decoral_product` (decoral order counted ONCE at base-coat packing) so that
  `m2_ral_only + m2_decoral_product == m2_total`. **Naming trap:** the existing field `m2_decoral` is
  the *przejazd* (decoral pass / coats workload); rename it to `m2_decoral_pass` to free `m2_decoral`
  / avoid confusion with the new product-side decoral. Touches frontend + tests.

### NA21. Factory-policy validation of S01–S12 (esp. the single-Decoral-pass correction model)
- Severity: policy, not code. Tests prove internal consistency, not shop-floor correctness.
- Code coverage DONE (2026-06-17): every matrix row S01–S12 now has an explicit end-to-end regression
  test in `tests/test_scenario_matrix.py` that drives the path to READY and asserts the documented
  final state — so the matrix is pinned to code and can't silently drift.
- Still OPEN (human): a guided walkthrough of each scenario in the running app with the factory to
  confirm the modeled policy matches the shop floor (especially the single-Decoral-pass correction
  model). This needs the factory, not code.
- **Field guide READY (2026-06-18):** `docs/SCENARIO_WALKTHROUGH.md` turns this into a concrete
  checklist — per scenario: seeded setup + dev logins/routes, reusable step primitives, the exact
  click-path, the expected final state to confirm, and an OK/MISMATCH line, plus cross-cutting checks
  (NA26 operational qty, packing capacity, presence attribution, przemalowanka/ocynk, throughput).
  Remaining is the human pass with the factory; record outcomes + confirmation date here.

### NA24. Whole-repo documentation coherence audit (factory + system expectations, into one consistent whole)
- Severity: MEDIUM (foundational — every future plan/implementation rests on the docs being a single,
  consistent, complete source of truth). Do this **before** NA25 (NA25 audits code *against* the
  result of this).
- Goal: read **all** documentation across the repository and reconcile it into **one coherent whole**
  that explains (a) how the factory physically works, (b) what we expect the system to do, and
  (c) surfaces topics that *should* be documented but currently are not (the owner explicitly expects
  gaps he hasn't named yet to be found and raised).
- Scope: at least `CLAUDE.md`, `README.md`, `docs/FACTORY_DOMAIN_MODEL.md`, `docs/WORKFLOW.md`,
  `docs/WORKFLOW_VALIDATION_CHECKLIST.md`, `docs/FACTORY_USAGE_NOTES.md`,
  `docs/archive/FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md`, `docs/archive/PAINT_SYSTEM_DEFINITION_DRAFT_PL.md`,
  `docs/STATION_IDENTITY_AND_AUDIT.md`, `docs/archive/OPERATOR_USABILITY_AUDIT_PL.md`,
  `docs/archive/UI_PASSIVE_REVIEW_PL.md`, `docs/AUTHZ_DESIGN_PROPOSAL.md`, `docs/WORKING_CONTRACT.md`,
  `docs/DEVELOPMENT_RUNBOOK.md`, `HARDENING_BACKLOG.md`, this file. (Code is NOT in scope here — that
  is NA25.)
- Method: build a topic map; for each topic check the docs agree with each other; record every
  (1) contradiction between docs, (2) duplicate/overlapping statement that should have one owner,
  (3) stale claim, and (4) **missing topic** that the coherent whole needs. Respect the doc hierarchy
  (physical truth → `WORKFLOW.md` → implementation) and the rule that workflow meaning lives in
  `WORKFLOW.md`. Confirm factory-policy questions with the owner rather than guessing.
- Output: a written reconciliation (gaps + conflicts list with proposed resolution per item), and the
  doc edits that bring everything into one consistent whole (or, where policy is unclear, questions
  for the owner). Do not change code.
- Acceptance: a single pass exists where the docs no longer contradict each other; each topic has one
  authoritative home; the list of "should be documented but isn't" is raised with the owner; no code
  changes made under this item.
- Progress (2026-06-17): **findings pass DONE + safe edits APPLIED** → `docs/archive/DOC_COHERENCE_AUDIT.md`.
  Owner decisions: paint threshold = **100 m²** (code right); dated snapshots **frozen as history**
  (banners); safe edits applied now. Applied: historical banners on the 3 snapshot docs; A2 shortage-
  warning currency (paint draft / usage notes / checklist #11); A3–A5 README + runbook (auth/Excel/JWT);
  A8 checklist #9 default-slots; A9 STATION_IDENTITY (NA1 note + dropped stale discrepancy-confirm line);
  D1 domain-model wired into README + WORKING_CONTRACT hierarchy; D2–D4 WORKFLOW cross-refs (two axes,
  decoral-packing-folded, canonical measurement model).
- **D5/D6/D7 DONE (2026-06-17):** interviewed the owner and documented the four physical concepts in
  `FACTORY_DOMAIN_MODEL.md` — ocynk (system-neutral marker), przemalowanka (repaint of already-coated
  parts, skips surface prep), surface preparation (cleaning/acid wash; real-quantity count point),
  incomplete-on-arrival (fewer arrived than ordered, may still produce). Added a **Glossary** (§6, D5)
  and a canonical **`docs/DOCUMENTATION_MAP.md`** (D7, referenced from `CLAUDE.md`). The interview also
  surfaced **NA26** (ordered- vs real-counted quantity display).
- **Still open under NA24:** optional **C** single-owner refactor of duplicated topics (station columns
  / permission matrix / correction categories) — currently consistent, convert restatements to
  references when next touched. NA24 otherwise complete; proceed to NA25.
- **Regularized (2026-06-17):** the audit is now a repeatable command — **`/doc-audit`**
  (`.claude/commands/doc-audit.md`), intended cadence **weekly**. Run it to re-reconcile the docs and
  refresh `docs/archive/DOC_COHERENCE_AUDIT.md`. (Auto-running it on a schedule would need the billable
  scheduled-agent path; not set up.)

### NA25. Conformance audit — documented "coherent whole" (NA24) vs. what is actually coded
- Severity: MEDIUM. Depends on NA24 (audits against its result).
- Goal: with the reconciled documentation as the spec, audit the **codebase** (backend services/read
  models, frontend renderers, tests, migrations) for where implementation **diverges** from the
  documented intent — both directions: behavior the docs require but code lacks/contradicts, and
  behavior the code has that the docs don't describe.
- Method: walk topic-by-topic from the NA24 map; for each, cite `file:line` evidence of agreement or
  divergence; classify each divergence as doc-wrong (update docs) vs. code-wrong (fix code) vs.
  needs-owner-decision. Read-only audit first — do not fix as you go.
- Output: a divergence report (per item: doc says X, code does Y at `file:line`, proposed direction +
  severity), feeding concrete follow-up items back into this file.
- Acceptance: every major documented topic has an explicit conformance verdict with evidence;
  divergences are logged as actionable items; no silent fixes bundled into the audit.
- **DONE (2026-06-17): full read-only pass → `docs/archive/CODE_CONFORMANCE_AUDIT.md`.** Per-topic verdicts with
  `file:line` evidence. Result: code conforms to the reconciled docs across stage model, READY/finalize,
  reopen, corrections, resource locks/packing slots, auth (NA1), queue stale-revision, throughput,
  paint (demand 100 m² + shortage warning + packing block + no-negative-stock), work types, external
  number, completed release, JWT/config. **One real divergence: NA26** (confirmed in code). One
  doc-understatement: NA27. No code changed.

### NA26. Most screens display the ordered quantity instead of the real counted (actual received) quantity
- Status: **DONE (2026-06-17)** — see Done section.
- Severity: MEDIUM (operator-visible truth — but reported as "almost everything works"; verify before fixing).
- Reported by owner (2026-06-17): surface preparation counts the **real received** pieces, and packing
  correctly validates "did anything go missing?" against that real value — but **almost everywhere the
  displayed piece count is the *ordered* quantity (`total_quantity`), not the real counted one**.
- Why it matters: `WORKFLOW.md` "Quantity Discrepancy Visibility" says production/station operators
  should see the **operational** quantity (the real counted value); office/manager additionally see
  declared vs counted + the difference. Showing the ordered quantity at stations contradicts that and
  can mislead operators about how many pieces they actually handle.
- Required fix (after verification): audit each station/list/detail read model + frontend surface and
  use the actual-received quantity as the operational display where the workflow rule says so (keep
  declared + difference for office/manager). Likely surfaces: station tables/cards, packing, work-order
  detail, manager queue.
- Acceptance: station-facing piece counts show the real counted (actual received) quantity once surface
  prep has counted it; office/manager still see declared, counted, and the difference; covered by tests.
- Note: this is exactly the kind of doc-vs-code divergence **NA25** will sweep for — confirm scope there,
  but it is logged here because the owner surfaced the concrete symptom.
- **NA25 update (2026-06-17): CONFIRMED in code.** `_store_surface_preparation_counted_quantity`
  (`app/process/service.py:2339-2355`) stores the count only on the SP stage state and does not update
  `current_active_quantity`; `_get_stage_display_quantity` (`:2479-2492`) and `_get_stage_planned_quantity`
  (`:2495-2511`) therefore return the ordered `total_quantity`, which station cards render. Validation
  uses the actual received value (`:2821`, `:576-578`), so packing's missing-piece check is correct.
  Resolve the WORKFLOW principle-6 (planned stays original) vs discrepancy-visibility tension with the
  owner before fixing.

### NA27. WORKFLOW "Station Permissions" understates which stats endpoints are manager-gated
- Status: **DONE (2026-06-17)** — see Done section.
- Severity: LOW (doc-understatement, not a defect — code is safe/broader).
- `WORKFLOW.md` "Station Permissions → Current enforcement" lists only `/manager/stats/throughput` and
  `/manager/corrections/reason-report` as manager/admin-gated, but `_ensure_stats_viewer` also gates
  `/stats/cycle-time` and `/stats/wip-aging` (`app/manager/service.py:112,129,356,508`).
- Fix: broaden that WORKFLOW line to "all `/manager/stats/*` (and the corrections reason report)".
- Acceptance: the doc matches the code; no behaviour change.

### NA28. Per-operator foundation — phase 2 (stats + employee admin UI)
- Status: **DONE (2026-06-18)** — see Done section. Crediting rule chosen by owner: each present operator
  gets full credit, order counted once per operator (documented in WORKFLOW.md).
- Remaining/optional (not blocking): richer attribution directly in the stage-transition log
  (`user_id` is still the shared station account; per-action attribution lives in `audit_event_actors`),
  and auto-checkout at end of day (deliberately skipped as low-value).

### NA29. Pieces (szt.) cross-section breakdown across production stats — phase 2 of NA23
- Severity: LOW (visibility — m² is the primary unit and already split; pieces is the secondary unit).
- Background: NA23 mandated that **every** production stat expose the two cross-sections (by method,
  by coating). As of 2026-06-18 this is done for **m²** (throughput) and for **time** (cycle-time) and
  **counts** (WIP-aging). What is still aggregate-only is the **pieces (szt.)** unit: throughput shows
  `correction_pieces` and `orders_count` without a manual/automatic/RAL-only/decoral split, and there is
  no pieces equivalent of the m² composition bars.
- Required fix: add a pieces partition to `ThroughputPeriod` (e.g. `pieces_manual`/`pieces_automatic`
  and `pieces_ral_only`/`pieces_decoral`, each summing to a `pieces_total`), surface a m²↔szt. unit
  toggle on the throughput composition bars / stacked chart / table — same "one total, two
  cross-sections" pattern. `app/manager/service.py::get_throughput_stats` + `schemas.py::ThroughputPeriod`,
  frontend `StatystykiPage.tsx`.
- Acceptance: throughput can show pieces split by both cross-sections, each partition summing to the
  pieces total; covered by tests.

## New owner requests (2026-06-19) — scoped from owner chat

Source: owner chat 2026-06-19 (screenshot) + clarification Q&A same day. Core decisions captured below;
remaining open questions are flagged per item. Each needs a `docs/WORKFLOW.md` update if it changes
workflow meaning. Severities are first-pass estimates.

### NA33. Configurable auto work-scheduling + colour grouping + (basic) statistics tidy
- Severity: MEDIUM (planning/throughput feature). Largest of this batch.
- Request (verbatim): "Grupowanie kolorami, statystyki uporządkować, logika automatycznego układania
  pracy (po kolorze, po terminie, minimalny przerób)."
- Three parts:
  - **Group the planning queue by colour** so same-colour orders cluster (fewer colour changes on the line).
  - **Auto work-ordering logic — a one-click *suggestion* the manager accepts or edits** (NOT fully
    automatic; owner decision 2026-06-19). An "Ułóż automatycznie" action proposes a queue order; the
    manager can apply it as-is or tweak before committing. Likely on the manager planning queue
    (`app/manager/service.py` reorder/assign + `ManagerPanelPage`).
  - **Configurable rule priority (key owner requirement):** the optimisation criteria are colour grouping,
    due date (po terminie), and minimal changeover/rework (minimalny przerób), but the **priority order of
    these rules must be settable, not hardcoded**. Default order = **colour → deadline → changeover**, yet
    the manager must be able to reorder the rules (we are not locked into today's definition). Design the
    scheduler around an ordered, configurable list of rules rather than a fixed comparator.
  - **Statistics tidy — deferred / minimal for now:** the owner will ask his colleague what stats he
    actually wants; until then ship only a *very basic* tidy and expand once requirements are defined. Do
    NOT over-build this sub-part now (coordinate with NA23/NA29 when the wishlist arrives).
- Open questions (still): exact set of configurable rules + how the priority UI works; what "minimalny
  przerób" precisely measures (assume colour-changeover minimisation until told otherwise); the colleague's
  statistics wishlist (blocks the stats sub-part).
- Acceptance: queue can be grouped/sorted by colour; an "Ułóż automatycznie" action proposes an order the
  manager can accept or edit; the rule priority is user-configurable (reorderable), defaulting to
  colour → deadline → changeover; basic stats tidy only; covered by tests.

### NA34. Distinguish two correction kinds — "fixed on the spot" (stat-only) vs "to be re-planned"
- Status: **DONE (2026-06-22).** Owner answers: stat-only applies to **both RAL and DECORAL**; a reason
  is **required**. Built on the NA40 seam: new `CorrectionKind.STAT_ONLY` + `_select_correction_kind`
  branch (driven by the operator's `stat_only_correction` flag). A stat-only correction records a row in
  the new **`stat_only_corrections`** table (quantity + required reason/category + profiles/accessories
  split) and an audit event, then folds the corrected pieces into OK so the order completes **as-is** —
  no replan, no child: RAL closes READY, DECORAL pieces continue the single Decoral pass (no `N` marker).
  The shared `correction_events_select` unions the table in, so the reason report + throughput count it.
  API: `stat_only_correction` on `PackingCompleteRequest` (both packing endpoints). Frontend: a "Rodzaj
  poprawki" radio (Do zaplanowania / Od razu poprawiona) in the packing correction block. Schema +
  migration `20260622_0033`; `alembic check` clean. Tests: 3 backend (RAL as-is + reported; DECORAL keeps
  single Decoral, no child; schema rejects stat-only w/ 0 qty) + 1 frontend (toggle → `stat_only_correction=true`).
  Full backend + frontend suites green. `docs/WORKFLOW.md` Corrections Behavior documents the third kind.
  Follow-up (not built): stat-only at the **Decoral-pass** completion (`DecoralProductionCompleteRequest`)
  if the owner wants it there too — currently only at packing.
- Severity: MEDIUM (changes correction semantics — touches the correction model + stats; coordinate with
  NA32 paint-consumption and the RAL/DECORAL correction paths).
- Request (verbatim): "rozróżnienie poprawek na poprawki od razu poprawione i do zaplanowania. Poprawka
  od razu poprawiona w logice jest tylko daną statystyczną, nie wraca nigdzie z powrotem. Poprawka do
  zaplanowania jest poprawką która powoduje że musi zostać ten kolor jeszcze raz zaplanowany i pomalowany."
- Two correction categories:
  - **Fixed on the spot ("od razu poprawiona") — stat-only.** Recorded **only as a statistic**; it does
    NOT re-enter the workflow (no return to planning, no child order, no re-paint). **The order is
    considered fully done as-is** (owner decision 2026-06-19): `completed_quantity` = counted, the order
    closes normally, and the correction is logged purely as a number (quantity + reason) in the stats. Today
    every correction returns (RAL → planning batch reset; DECORAL → child order), so this is a genuinely new
    path — the correction is captured for reporting but the order is not sent back.
  - **To be re-planned ("do zaplanowania")** — the existing behaviour: the colour must be planned and
    painted again (the current RAL/DECORAL correction flow).
- Impact: the packing correction-capture UI needs to ask which kind; the stat-only kind must feed the
  corrections reason report / throughput correction counters **without** creating a `CORRECTION` batch or
  child work order, and **without** sending the order back; the re-plan kind keeps current behaviour.
- Open questions (owner left these open 2026-06-19, decide before building): does the stat-only kind apply
  to **both RAL and DECORAL** or RAL only? Is the reason/category **required** for a stat-only correction or
  optional? (Quantity-vs-completion is settled: order is done as-is.)
- Acceptance: at packing, an operator can mark a correction as "od razu poprawiona" (stat-only — no
  re-plan, no child/batch, order completes as-is) or "do zaplanowania" (current flow); statistics count
  both; covered by tests; `docs/WORKFLOW.md` correction model updated.

### NA35. Mouse-wheel on number fields produces fractional amounts (UX defect)
- Status: **DONE (2026-06-22)** — new shared `frontend/src/components/NumberInput.tsx` owns the rule:
  keyboard entry is native (decimals still typable where `step` allows — m²/paint kg), but the mouse
  wheel always moves the value by **whole units** (default `wheelStep=1`) and only while the field is
  focused, so scrolling the page over it can't silently change it. React registers `onWheel` as a passive
  root listener (so `preventDefault` is ignored there), so the component attaches its own non-passive
  native `wheel` listener. Every `type="number"` input in the app (18 sites across `CreateWorkOrderPage`,
  `WorkOrderDetailPage`, `PaintInventoryPage`, `StageWorkOrdersPage`, `PackingWorkOrdersPage`,
  `DecoralWorkOrdersPage`, `ManagerPanelPage`) now routes through it — the fractional-step fields
  (`total_area_m2` ×2, paint `quantity_kg`/`quantity_delta_kg`, automatic `finalCartonRemainingKg`) were
  the actual offenders. Tests: new `frontend/tests/numberInput.test.tsx` (4 cases: whole-unit wheel on a
  `0.01`-step field, no-change-when-unfocused, decimal typing still works, min clamp). **82 frontend tests
  pass + build green.** Frontend-only; no backend/docs/workflow change.
- Severity: LOW (UX defect, but annoying/error-prone — easy fix; no open questions).
- Request (verbatim): "Gówno ze scrollem w polach z wpisywaniem liczby."
- Problem (clarified 2026-06-19): the wheel itself is **fine and wanted** — the issue is that scrolling
  produces **fractional values (e.g. tenths of a kilogram, 20.3 instead of 20)**. The step is too fine, so
  a scroll lands on an odd non-round number.
- Required fix: **keep wheel-to-change, but make the increment whole numbers** — set an integer `step`
  (`step=1`) on the affected numeric inputs so the wheel moves the value by whole units and never creates a
  fraction. Apply across the quantity-entry surfaces (packing count, surface-prep count, office quantities,
  paint kg, etc.). (If any field legitimately needs fractions, pick an appropriate round step for it — but
  the default must not yield stray tenths.) Best done via a shared `NumberInput` so the step is consistent.
- Acceptance: scrolling the wheel over a number field changes it by whole units only (no fractional values);
  the wheel still works; keyboard entry unaffected.

### NA36. Technical drawings on a work order — new attachment type
- Severity: MEDIUM (feature).
- Request (verbatim): "Rysunki techniczne."
- Decision (2026-06-19): implement as a **new attachment type extending the existing
  `WorkOrderAttachment`** mechanism (not a separate subsystem). A technical drawing (PDF/image) is attached
  to a work order in the office and is viewable on the stations. Reuse the existing attachment storage/API;
  add a type/category discriminator so drawings are distinguishable from other attachments and the QC doc.
- Open questions (minor, confirm before building): allowed file types (PDF + images assumed; CAD?); exactly
  which stations should see drawings; per work order vs per product/template (assume per work order).
- Acceptance: office can attach technical drawing(s) to a work order via the existing attachment mechanism
  (typed as "drawing"); stations can view them; covered by tests.

### NA37. WZ document (Wydanie Zewnętrzne — goods-issue / delivery note)
- Severity: MEDIUM (feature).
- Request (verbatim): "Wz."
- Decision (2026-06-19): generate WZ as a **PDF at order release/completion, using the same mechanism as
  the QC document** (Excel→PDF generation in `app/work_orders/`), with a WZ numbering scheme. Windows+Excel
  constraint applies exactly like the QC doc (see NA5 gotcha).
- Open questions (confirm before building): the WZ template/fields; numbering scheme (separate counter like
  the work-order number allocator?); who may issue it (office/manager?); exact trigger (at completion vs an
  explicit "release/ship" action).
- Acceptance: a WZ PDF can be generated for a released/completed order via the QC-doc mechanism, with WZ
  numbering; covered by tests (mechanism-level; Excel rendering is Windows-only like QC).

### NA38. Enter the Decoral foil when adding an order — foil registry, one per order
- Severity: MEDIUM (feature — office intake).
- Request (verbatim): "Folie decoral do wprowadzenia przy dodaniu zlecenia."
- Decision (2026-06-19): add a **Decoral foil registry** (a lookup table like paints/clients) and let the
  office pick **one foil per work order** at intake for a decoral order (`app/work_orders/` create/update +
  intake form). One foil per order (owner decision) — model it as a nullable FK from the work order to the
  foil registry.
- Open questions (confirm before building): registry fields (name + code? supplier?); whether the chosen
  foil should feed the Decoral pass / consumption / foil-usage stats (likely yes, later); who manages the
  registry (office/manager/admin).
- Acceptance: a foil registry exists and is manageable; office can select one foil per order at intake;
  the chosen foil is stored on the work order and shown where relevant; covered by tests.

## Architecture & design audit findings (2026-06-19)

Source: critical design review on 2026-06-19 (owner-requested — "things we built without sense or that
are sub-optimal"), full report in **`docs/ARCHITECTURE_AUDIT.md`**. These are **debt/shape** items, not
correctness defects. Severities reflect maintainability risk, not user-visible breakage.

### NA39. `app/process/service.py` is a 2937-line god class
- Status: **IN PROGRESS.** Cut 1 (audit/transition-log writing) **DONE (2026-06-22)** — extracted the seven
  audit + stage-transition writers into `ProcessAuditWriter` (`app/process/audit_writer.py`), instantiated as
  `self.audit` on `ProcessService`. Cleanest seam (deps were only session + `AuditRepository`); also closes
  **NA46 §A6** (the dual write to `audit_events` + `stage_transition_events` now lives in one place and cannot
  diverge). Behavior-preserving: 438 backend tests pass, `alembic check` clean; `service.py` 3119 → 2906 lines.
  Commit `921c577`.
  - **Remaining cuts (each is a deliberate pass — do NOT rush; the entanglement below is the reason):**
    - **Resource-lock + packing-slot manager** (`_acquire_packing_slot` & co., ~`service.py:2516-2824`):
      the lock orchestration reaches `self.repository` **and** the occupancy predicates
      (`_occupies_packing` / `_has_active_hanging_work` / `_occupies_automatic_line`), which read stage state
      via `_get_stage_state`. Decide whether those domain predicates move with it or stay. **NA46 §A5 (bound
      the lock maps) is the risky sub-part** — evicting an in-use `RLock` could hand two threads different
      locks for one id; design eviction carefully (only evict provably-unheld locks) before touching it.
    - **Correction subsystem** → `CorrectionService` (already half-seamed by NA40's `_select_correction_kind`
      / `_dispatch_packing_correction`): entangled with stage-state reset, batch creation, number allocation,
      finalize, and the audit writer. Largest self-contained chunk per the audit.
    - **Read-model serializer** (`_to_stage_work_order_read` + quantity/category helpers): widest dependency
      surface (display-status, quantity, packing-slot, paint, correction-state). **Couple with NA43** (single
      `quantity_for(context)` resolver) so the quantity rule lands once. Do last.
- Severity: MEDIUM (maintainability). See `docs/ARCHITECTURE_AUDIT.md` §A1.
- Problem: `ProcessService` (`app/process/service.py`, ~120 methods) mixes transition logic, resource-lock
  + packing-slot management (`_PROCESS_MUTATION_LOCKS` at `:30-33`), correction creation/merge,
  display-status derivation, read-model serialization, and audit/transition-log writing (now extracted).
  Every workflow change lands in this one file.
- Required fix: extract along existing seams — `ProcessAuditWriter` (done), `ResourceLockManager`,
  `CorrectionService`, `ProcessReadModel`/serializer. Behavior-preserving, incremental, test suite as net.
- Acceptance: `service.py` materially smaller; concerns in separate modules; full suite still green.

### NA40. Abstract the correction subsystem BEFORE adding NA34's third correction kind
- Status: **DONE (2026-06-22).** Behaviour-preserving refactor. New `CorrectionKind` enum
  (`app/process/enums.py`: `REPLAN_IN_PLACE`, `SPIN_OFF_CHILD`; STAT_ONLY reserved for NA34) plus a single
  seam in `ProcessService`: `_select_correction_kind(work_order, *, tracked_batch)` classifies, and
  `_dispatch_packing_correction(...)` runs the matching strategy (`_reset_to_correction_planning` /
  `_complete_packing_with_correction_order`). Both `correction_quantity > 0` branches — the plain packing
  path (`complete_packing`) and the tracked-batch path (`_complete_tracked_batch_packing`) — now route
  through the one seam instead of inline RAL/DECORAL `if`s. Quantity-conservation + reason capture stay
  shared in the caller (validated once before dispatch). **NA34 now adds STAT_ONLY as one enum value + one
  classifier branch + one handler, not a parallel flow.** Tests: new `test_select_correction_kind_seam_NA40`
  pins the classifier; full backend suite + scenario matrix S01–S12 green; `alembic check` clean (no schema
  change). `docs/WORKFLOW.md` Corrections Behavior documents the seam.
- Severity: MEDIUM (debt that becomes risk). See `docs/ARCHITECTURE_AUDIT.md` §A2. **Blocks/precedes NA34.**
- Problem: RAL (in-place batch reset, `_reset_to_correction_planning` `:1919`) and DECORAL (child order,
  `_create_correction_work_order` `:1850`) corrections share no common abstraction. NA34 wants a third
  ("od razu poprawiona" stat-only) path; bolting it onto two un-abstracted flows multiplies the
  RAL/DECORAL × replan/stat-only × single/multi-round matrix.
- Required fix: introduce one entry point `record_correction(work_order, qty, category, kind)` dispatching
  to `{replan_in_place, spin_off_child, stat_only}`, with quantity-conservation + reason-capture shared.
- Acceptance: a single correction seam exists; NA34 adds a strategy, not a parallel flow; scenario matrix
  still green. Sequence: do this, then NA34/NA32 (avoids reworking the same code twice).

### NA41. Collapse the duplicated "incomplete / status" truth
- Status: **DONE (2026-06-22).** Full deletion (owner chose delete over freeze). `is_incomplete_on_arrival`
  is now the single source of truth: the `incomplete_requires_unplanned` CHECK references only it, all three
  `_has_incomplete_marker` copies (process/work_orders/manager) collapse to the boolean, and the 5 planning-queue
  filters (`manager/repository.py` ×4 incl. `get_planned_queue_revision`, `process/repository.py` ×1) drop the
  redundant `status` clause. The stored `WorkOrder.status` column + `work_order_status_enum` were removed
  (migration `20260622_0034`, batch table-rebuild; `alembic check` clean). The read-model `status` field stays
  but is now **always derived** from `process_status` (`WorkOrderService.build_status_view`) — including the
  client-history view (`clients/service.py`), which previously read the stored column and was the lone
  inconsistency. Removed dead code surfaced en route: `app/work_orders/workflow.py` (uncalled transition map),
  `get_status_options`/`WorkOrderStatusOption`, `WorkOrderStatusTransitionRequest`. Status writes removed from
  `create_work_order`, `mark_complete_arrival` (+ its audit detail), and correction-child creation. Tests:
  updated `test_work_orders_service`, `test_process_service` (deleted the stored-status-drift test; rewrote the
  two legacy-only-marker tests to the boolean), `test_db_constraints_phase1/2` (raw inserts; deleted the
  legacy-status-blocks-queue test); migration tests pinned to old revisions keep the historical column.
  **Full backend suite green; `alembic check` clean; frontend untouched.** CLAUDE.md note updated.
- Severity: MEDIUM (truth drift — a CHECK constraint depends on the legacy field). See §A3.
- Problem: "incomplete" lives in two places kept in sync by hand — `is_incomplete_on_arrival` (real) and
  the legacy `WorkOrder.status == INCOMPLETE`, both checked in `_has_incomplete_marker`
  (`app/process/service.py:2333`, mirrored `app/work_orders/service.py:469`). The legacy `status` is still
  written (`work_orders/service.py:404`, `process/service.py:1883`) and load-bearing in CHECK
  `incomplete_requires_unplanned` (`work_orders/models.py:64`).
- Required fix: make `is_incomplete_on_arrival` the single source; migrate the CHECK off `status`; delete
  or write-once-freeze `WorkOrder.status`; collapse `_has_incomplete_marker` to one field.
- Acceptance: one source of truth for incomplete; CHECK constraint no longer references `status`; tests cover it.

### NA42. Review the automatic PRODUCTION-as-preview stage (most special-cased, most-churned area)
- Severity: LOW–MEDIUM (maintainability / churn risk). See §B1.
- Problem: AUTOMATIC keeps `PRODUCTION` as a no-op "preview" stage and starts `PACKING` at hanging-start,
  requiring a family of special cases (`_is_automatic_production_preview_stage`,
  `_get_automatic_packing_display_stage`, `_packing_completion_block_reason`,
  `can_complete_packing`/`packing_blocked_reason`). The Done log shows this area was reversed 3× + caused a
  seed bug — it fights the stage-state abstraction.
- Required fix: spike whether **omitting `PRODUCTION` from the automatic stage sequence** (like
  PRZEMALOWANKA omits SURFACE_PREPARATION) is simpler than special-casing a phantom stage everywhere. Keep
  the "live-but-uncompletable packing" state. Decide before more automatic-flow features land.
- Acceptance: a written decision (remove phantom stage vs keep) with the special-case count it removes/keeps.
- **Scope guardrail (owner, 2026-06-20): the automatic-station operator's view must stay exactly as it is
  today** — same screen, same paint-consumption (carton) entry, same upcoming/active line preview, same
  endpoint. This is a purely **internal** re-homing of where the paint-consumption action and the
  "show automatic panel" read-model flag hang (they currently key off the PRODUCTION preview stage); the
  frontend stays 1:1. Any change that alters what the automatic operator sees is out of scope.
- Status: **DONE (2026-06-20)** — branch `experiment/automatic-no-phantom-production`. Spike verdict:
  the phantom stems from creating stage-state rows as a method-agnostic superset at intake (the method
  isn't known until planning). Fix (Option A): a new `ProcessService.reconcile_stage_states_to_route`
  runs at planning (`assign_plan` / `update_production_type`, before correction replanning) and trims the
  rows to the real route — AUTOMATIC loses `PRODUCTION`, MANUAL loses `HANGING`, re-adding on a method
  switch. Removed the phantom implicit `PRODUCTION` transitions and the automatic-`PRODUCTION`-DONE block;
  re-expressed `_occupies_automatic_line` (hanging DONE & packing not DONE, equivalent to the old
  PRODUCTION-in-progress window); `is_visible_in_stage` decides the automatic preview before fetching a
  stage row and walks the actionable route for the predecessor; the production-panel repo query anchors on
  `PRODUCTION`∨`HANGING`; read models synthesize the "in production" presentation so the **operator view is
  unchanged**. Real regressions found & fixed during the change: automatic production panel listing, and a
  method-switch-on-correction-replan 409. Tests: new
  `test_reconcile_stage_states_drops_phantom_rows_per_route_NA42`; phantom-asserting tests updated to the
  new model (no PRODUCTION row for automatic / no HANGING row for manual). **433 backend + 78 frontend
  tests pass, alembic clean, frontend build green.** `WORKFLOW.md` updated. Frontend untouched.

### NA43. Consolidate the over-faceted quantity vocabulary
- Severity: LOW–MEDIUM (clarity; root of NA26-class bugs). See §B3.
- Problem: five quantity notions (ordered / counted / `current_active` / operational / per-stage planned)
  with which-shows-where wrong almost everywhere (NA26), resolved via four scattered helpers
  (`_get_stage_display_quantity`/`_get_stage_planned_quantity`/`_get_operational_quantity`/
  `_get_stage_counted_quantity`, `app/process/service.py:2518-2906`).
- Required fix: document the five quantities + the single display rule in `WORKFLOW.md`; collapse the four
  helpers behind one `quantity_for(context)` resolver so the rule lives once.
- Acceptance: one resolver owns quantity-for-display; WORKFLOW.md states the rule; tests cover each context.

### NA44. Frontend: decompose monolithic pages + move business semantics off the renderer
- Severity: LOW–MEDIUM. See §C1, §C2.
- Problem (structure): `WorkOrderDetailPage.tsx` (1353), `ManagerPanelPage.tsx` (1053),
  `PackingWorkOrdersPage.tsx` (908), `StageWorkOrdersPage.tsx` (876) are monoliths; known frontend defects
  (NA13 stray `::`, NA31 stale plan-draft, NA14 dead table) are churn residue.
- Problem (rule break): the renderer computes business meaning, contradicting "faithful renderer"
  (`CLAUDE.md`) — "PO TERMINIE"/overdue is computed client-side from `new Date()`
  (`frontend/src/utils/workOrderDisplay.ts:142,162`); Polish status labels are duplicated between the
  frontend switch (`workOrderDisplay.ts:28-50`) and backend `ProcessDisplayStatus.polish_label`
  (`process/service.py:1051`).
- Required fix: decompose Detail + Manager into section components with a data hook (do it when next
  touched); expose an `is_overdue` read-model boolean; render the backend `polish_label` (or make the
  frontend the single label owner) — not both.
- Acceptance: the two worst pages are split; overdue + labels have one owner; tests updated.

### NA45. Archive frozen documentation snapshots; trim the living set
- Status: **DONE — first pass (2026-06-22).** Moved 6 frozen snapshots to `docs/archive/` (each banner-
  flagged): `DOC_COHERENCE_AUDIT`, `CODE_CONFORMANCE_AUDIT`, `OPERATOR_USABILITY_AUDIT_PL`,
  `UI_PASSIVE_REVIEW_PL`, `FACTORY_DECISION_IMPLEMENTATION_MAP_PL`, `PAINT_SYSTEM_DEFINITION_DRAFT_PL`.
  `DOCUMENTATION_MAP.md` restructured into Living / Active-reference / Archive sections (precedence intact).
  Conservatively KEPT (still referenced by docs/code/open items, would break links): `FACTORY_USAGE_NOTES`
  (WORKING_CONTRACT), `WORKFLOW_VALIDATION_CHECKLIST` (HARDENING_BACKLOG), `STATION_IDENTITY_AND_AUDIT`,
  `AUTHZ_DESIGN_PROPOSAL` (README), `ARCHITECTURE_AUDIT` (NA39–47), `SCENARIO_WALKTHROUGH` (NA21 + seed
  script). Stale links repointed to `docs/archive/` in this file + `WORKFLOW_VALIDATION_CHECKLIST.md`.
  **Still open (deferred):** shorten this file's Done section to one-line + commit refs; collapse the
  S01–S12 four-way representation; repoint the `/doc-audit` + `/code-audit` skills' output paths/cadence
  (tied to NA47 owner confirmation).
- Severity: MEDIUM (every session is told to read the docs; sprawl hides the truth). See §D1, §D2, §D3.
- Problem: ~5,150 lines across 20 docs; many are dated, frozen-as-history audit snapshots overlapping the
  two living docs (`DOC_COHERENCE_AUDIT`, `CODE_CONFORMANCE_AUDIT`, `OPERATOR_USABILITY_AUDIT_PL`,
  `UI_PASSIVE_REVIEW_PL`, `FACTORY_USAGE_NOTES`, `FACTORY_DECISION_IMPLEMENTATION_MAP_PL`,
  `PAINT_SYSTEM_DEFINITION_DRAFT_PL`, `WORKFLOW_VALIDATION_CHECKLIST` 35 KB). Plus `IMMEDIATE_NEXT_ACTIONS`
  Done section (~350 lines) duplicates HARDENING_BACKLOG + git; S01–S12 has 4 parallel representations.
- Required fix: move frozen snapshots to `docs/archive/` (or delete fully-superseded ones); keep the
  living set small (`WORKFLOW`, `FACTORY_DOMAIN_MODEL`, `WORKING_CONTRACT`, `DEVELOPMENT_RUNBOOK`,
  `DOCUMENTATION_MAP`); shorten Done entries to one line + commit ref; let `test_scenario_matrix.py` +
  the WORKFLOW matrix be the canonical scenario truth. Update `DOCUMENTATION_MAP.md` to match.
- Acceptance: active docs/ contains only living docs; archive holds the snapshots; DOCUMENTATION_MAP is accurate.

### NA46. Backend cleanup: derive `current_active_batch_id`; bound the in-process lock maps
- Status: **PARTIAL.** §A6 (single write path for the `audit_events` + `stage_transition_events` double-write)
  **DONE (2026-06-22)** as a side effect of NA39 cut 1 — both writes now live in `ProcessAuditWriter`
  (`app/process/audit_writer.py`), so they cannot diverge. **Still open:** §A4 (derive `current_active_batch_id`
  from `active_batches` instead of the hand-synced stored pointer) and §A5 (bound/evict the in-process lock
  maps — design eviction carefully; only evict provably-unheld `RLock`s).
- Severity: LOW (robustness). See §A4, §A5, §A6.
- Problem: `current_active_batch_id` is a stored pointer hand-synced at 8+ sites
  (`_sync_legacy_current_active_batch`) with a heuristic fallback (`models.py:176-186`) — a forgotten sync
  desyncs it. `_PROCESS_MUTATION_LOCKS`/`_RESOURCE_MUTATION_LOCKS` (`:30-33`) grow unbounded (one RLock per
  id forever). Transitions double-write `audit_events` + `stage_transition_events` (coupling that can drift).
- Required fix: drop the stored pointer and derive `active_batch` from `active_batches` (the partial-unique
  index makes it unambiguous); cap/evict the lock maps for a long-lived process; add a single helper that
  writes both logs so they cannot diverge.
- Acceptance: no `_sync_legacy_current_active_batch` calls remain; lock maps bounded; one write path per transition.

### NA47. Decide how much audit-process cadence to keep (audit-generating-audit overhead)
- Status: **DONE — owner-confirmed & adopted (2026-06-22).** Cadence policy adopted in
  `docs/DOCUMENTATION_MAP.md` ("Audit cadence policy"): `/doc-audit` + `/code-audit` run **on-demand only**
  (not weekly), their generated docs are disposable scratch (durable findings folded into the living docs,
  snapshot then archived/deleted), and the deterministic `tests/test_documented_invariants.py` fast loop
  carries routine drift detection. Both skill files (`.claude/commands/doc-audit.md`, `code-audit.md`)
  updated: on-demand cadence wording + snapshot output repointed to `docs/archive/`.
- Severity: LOW (process, not code). See `docs/ARCHITECTURE_AUDIT.md` §D4.
- Problem: the repo accumulates audits-of-itself — NA24 produced `docs/archive/DOC_COHERENCE_AUDIT.md`, NA25
  produced `docs/archive/CODE_CONFORMANCE_AUDIT.md`, this review produced `docs/ARCHITECTURE_AUDIT.md`, and the
  `/doc-audit` + `/code-audit` skills regenerate the first two on a weekly cadence. For a single-developer
  factory tool that is a lot of meta-process whose outputs themselves go stale and then need reconciling
  (this is the same sprawl NA45 cleans up — the two findings reinforce each other).
- Required fix: make a conscious decision on the cadence rather than letting it run by default. Options to
  weigh: (a) keep the skills but run them **on-demand only** (before a big change), not weekly; (b) fold the
  durable signal each audit produces directly into `WORKFLOW.md` / `FACTORY_DOMAIN_MODEL.md` and treat the
  audit docs as disposable scratch (delete after acting); (c) keep a single periodic audit instead of three
  separate doc/code/architecture passes. Pick one, write the chosen cadence into `docs/DOCUMENTATION_MAP.md`
  or `WORKING_CONTRACT.md`, and stop producing standing audit documents that outlive their usefulness.
- Acceptance: a stated, written policy on which audits run, how often, and whether their output is durable
  or disposable; the doc set reflects that choice (coordinate with NA45).

## Done

- **Automatic packing card is now an ACTIVE packing row from hanging-start, not a read-only "waiting for hanging" row (2026-06-18)** —
  follow-up to the NA22a change below; user-requested. Previously `_get_automatic_packing_display_stage`
  returned `HANGING` (so the packing panel showed a read-only "Czeka na koniec zawieszania" row) until
  hanging finished. Now it returns `PACKING` the moment hanging is `IN_PROGRESS`
  (`app/process/service.py` ~1382), so the packing operator gets the live count form and works the order
  in parallel with the line. Completion is still blocked until `HANGING` `DONE` **and** automatic paint
  consumption is recorded (existing `complete_packing` guards); the gate is now surfaced to the UI via new
  read-model fields `can_complete_packing` / `packing_blocked_reason` (`app/process/schemas.py`,
  `_packing_completion_block_reason` helper), and the frontend disables "Zakończ pakowanie" with the Polish
  reason (`frontend/src/components/PackingWorkOrdersPage.tsx`). Docs: `docs/WORKFLOW.md` (automatic
  constraints + packing-slot read-model notes). Tests: updated
  `test_automatic_active_hanging_is_visible_in_packing_before_finish` (now expects PACKING + blocked) and the
  frontend "packs an automatic order in parallel with hanging…" test; full backend suite, `alembic check`
  (no schema change), frontend tests (77) + build all green.

- **Automatic orders now start packing at hanging-start, not just reserve a slot (2026-06-18)** —
  user-requested workflow change. Previously an AUTOMATIC order only took a packing-slot *reservation*
  when `HANGING` started; `PRODUCTION`/`PACKING` flipped to `IN_PROGRESS` only when hanging *finished*.
  Now the implicit PRODUCTION+PACKING start fires when automatic `HANGING` goes `IN_PROGRESS`
  (`app/process/service.py` transition_stage, ~line 172), so the order is in packing immediately
  (office/list display shows "Pakowanie"; stage-transition log records the line start at hanging-start).
  Packing **completion** still requires `HANGING` `DONE` (existing guard `complete_packing` line 547),
  and the packing card stays a read-only "waiting for hanging" row until then
  (`_get_automatic_packing_display_stage` gates `is_being_packed` on hanging done) — operator-confirmed
  scope "start now, finish after hanging." The `HANGING`-`DONE` branch remains an idempotent fallback
  for orders whose hanging started before this change. Docs updated (`docs/WORKFLOW.md` automatic
  constraints, packing-slot NA22a, stage-transition-log notes). Tests: rewrote
  `test_automatic_hanging_start_starts_production_and_packing` (was `..._finish_makes_production_visible`)
  to assert both stages start at hanging-start, display=PACKING, and completion blocked until hanging
  done; full backend suite + `alembic check` green.

- **Seed bug — statistics demo created an impossible second HANGING-in-progress order (2026-06-18)** —
  `seed_statistics_demo` writes WIP-aging rows as stage state **directly** (bypassing `ProcessService`),
  and one spec parked a second AUTOMATIC order at `HANGING / IN_PROGRESS`. HANGING is a single-holder
  resource lock at runtime, and scenario E2 already legitimately holds it, so the seed rendered an
  impossible "two orders hanging at once" state — and that directly-written order reserved no packing
  slot, which also read as "automatic hanging didn't lock packing." Fix: that stuck automatic order now
  ages at `SURFACE_PREPARATION` (non-exclusive) instead (reset_and_seed_dev_db.py wip_specs, with a
  comment warning future edits not to direct-write an exclusive-resource stage). Verified after reseed:
  exactly one HANGING-in-progress order (E2/0023); the reservation-at-hanging is confirmed working
  (scenario N/0018 holds `PACKING:1` purely from its hanging-start reservation, never having started
  packing). `tests/test_packing_station_lock.py` green (13). Note: the NA22a/NA22b packing
  reserve+override logic itself was **not** a bug — both reported symptoms were this one seed artifact.

- **NA28 phase 2 — employee admin + per-operator stats + presence history (2026-06-18)** — Made the
  employee mechanism fully usable in-app (was seed-only). Backend (`app/employees/`): employee **CRUD**
  (`POST /employees`, `PATCH /employees/{id}`, `GET /employees?include_inactive=`) gated to
  office/manager/admin (deactivating also checks the worker out everywhere); **per-operator stats**
  (`GET /employees/stats`) — per employee hours_present, orders_count, pieces/m²_credited (from
  `process.stage.finished`/`packing.completed`/`decoral_production.completed` audit events joined to the
  order) and actions, with the owner's crediting rule (each present operator full credit, order counted
  once per operator); **presence history** (`GET /employees/presence/history`); **check-out-all**
  (`POST /stations/{id}/presence/check-out-all`). Frontend: new **"Pracownicy"** page (admin table +
  operator-stats table + presence-history table, month picker) in the Biuro nav (office/manager/admin
  only), plus "Wymelduj wszystkich" on the station presence widget. Seed now creates attributed
  completion audit events per station operator so the stats are populated. Skipped as low-value:
  simultaneous multi-station presence, auto-checkout scheduler. Tests: `tests/test_employee_admin.py`
  (11 — gating, CRUD, deactivate-checks-out, credit-in-full, count-once-per-operator, history). Docs:
  WORKFLOW.md "Station Presence & Per-Operator Attribution". Verified: backend `pytest` green, frontend
  build + tests, `alembic check` clean (no schema change).

- **NA23 phase 2 — cycle-time + WIP-aging production breakdown (2026-06-18)** — Closed the gap the
  owner flagged: "Czasy etapów" (and WIP-aging) showed only an aggregate, while NA23 required every
  production stat to expose the two independent cross-sections. Backend: `get_cycle_time_stats` now
  attaches a `breakdown` (by_method Ręczna/Automat + by_coating Czysty RAL/Decoral) to each
  `StageCycleTime` and an `overall_breakdown` to the lead time; because cycle time is an **average** the
  headline is the **count-weighted mean** of either partition (each segment carries `orders_count`), not
  a sum. `get_work_in_progress_aging` adds `coating_type` per item and a `breakdown` counting the live
  cohort by method and by coating (each partition summing to the item count). Schemas: new
  `CycleTimeSegment`/`CycleTimeBreakdown`, `WipAgingSegment`/`WipAgingBreakdown`; shared `_METHOD_SEGMENTS`
  / `_COATING_SEGMENTS` + `_order_segment_keys` in `app/manager/service.py`. Frontend `StatystykiPage`:
  a Metoda/Powłoka toggle on "Czasy etapów" adds per-segment average columns + an overall-breakdown line;
  the "Zlecenia w toku" table gains a Powłoka column and a composition line. Tests:
  `test_cycle_time_breakdown_splits_each_stage_by_method_and_coating`,
  `test_wip_aging_breakdown_counts_by_method_and_coating`, + API assertions in `test_manager_api.py`.
  Docs: WORKFLOW.md cycle-time + WIP sections. Remaining pieces-unit work tracked as **NA29**. Verified:
  backend `pytest` green, `alembic check` clean, frontend build passes.

- **Per-operator foundation — station presence + audit attribution (2026-06-18, slice 1)** — Operators
  are now a **presence roster** separate from login accounts. New `employees/` module: `Employee`
  (name + active, no login) and `StationPresence` (append-only check-in/out; "present" =
  `checked_out_at IS NULL`). Workers check in/out per station; **audit events are attributed to the
  currently-present employees** at the action's station via a new `audit_event_actors` table, written
  centrally in `AuditRepository.add` (SYSTEM/UNKNOWN get none). API: `GET /employees`,
  `GET /stations/{id}/presence`, `POST .../presence/check-in|check-out`. Frontend: a presence widget on
  every station page (derives its station from the route), and the audit console + work-order history
  show the attributed operators. Migration `491d1bfa0b62`; seed adds 5 employees. Tests:
  `tests/test_employee_presence.py` (roster idempotency, per-station, attribution, no-presence/SYSTEM).
  Owner-chosen model: a station shows a worker list and present people tick themselves in; attribution =
  the whole present set. Docs: WORKFLOW.md "Station Presence & Per-Operator Attribution", CLAUDE.md map.
  Verified: full backend `pytest` green, `alembic check` clean, frontend 73 + build. See NA28 for phase 2.

- **Self-check loop foundation (2026-06-18)** — Closed the repo's two-loop self-policing of truth.
  Slow loop (LLM): added **`/code-audit`** (`.claude/commands/code-audit.md`, repeatable NA25) to pair
  with the existing **`/doc-audit`**. Fast loop (deterministic CI): added
  `tests/test_documented_invariants.py` pinning the documented business constants (paint threshold 100
  + /4,/6 divisors, packing slot default 2, JWT expiry 12h, bcrypt 72-byte, JWT-secret guard) so code↔doc
  drift on a pinned value fails CI immediately (the NA24 A1 "70 vs 100" class). Docs:
  `DOCUMENTATION_MAP.md` "Maintenance — the self-check loop". Verified: `pytest` green (5 new).

- **NA23 — Throughput stats: one total, two cross-sections (2026-06-17)** — The Statystyki
  "Przepustowość" section now shows the production total cut two independent ways that each sum to it.
  Backend (`ManagerService.get_throughput_stats` + `ThroughputPeriod`): renamed the decoral *pass*
  workload `m2_decoral` → **`m2_decoral_pass`** and added the coating-of-order partition
  **`m2_ral_only` + `m2_decoral`** (decoral product counted once at base packing), so
  `m2_ral_only + m2_decoral == m2_total` (alongside `m2_manual + m2_automatic == m2_total`). Frontend:
  headline ("Przez fabrykę"), two equal-width composition bars (by method, by coating), a daily
  **stacked** chart with a Metoda/Powłoka toggle (extended `BarChart` with `segments` + `legend`),
  the separate "Przejazd Decoral" chart (now `m2_decoral_pass`, flagged not-in-total), corrections
  chart, and a grouped detail table (method + coating columns each summing to Razem, plus przejazd*).
  m² only; pieces toggle deferred; cycle-time/WIP breakdown deferred (phase 2). Tests:
  `tests/test_manager_api.py` updated (coating partition sums + `m2_decoral_pass`). Docs:
  WORKFLOW.md "Throughput Reporting". Verified: full backend `pytest` green, `alembic check` clean,
  frontend 73 + build.
- **NA26 — Stations now display the actual received (counted) operational quantity (2026-06-17)** —
  Added `operational_quantity` to the station read model (`ProcessStageWorkOrderRead`):
  `ProcessService._get_operational_quantity` returns a tracked batch's own quantity, else the
  surface-prep actual received quantity once counted, else `total_quantity`. It now feeds the
  profile/accessory category derivation, and the three station cards (`StageWorkOrdersPage`,
  `PackingWorkOrdersPage`, `DecoralWorkOrdersPage`) render it (label "Sztuki") instead of the ordered
  `planned_quantity`. Validation/READY/quantity-conservation are untouched (still use
  `total_quantity`/counted); `planned_quantity` stays the original expected for audit + office/manager
  see declared/counted/difference. Docs: `WORKFLOW.md` "Quantity Discrepancy Visibility". Test:
  `tests/test_process_service.py::test_operational_quantity_reflects_actual_received_after_surface_preparation`
  + frontend factory updated. Verified: full backend `pytest` green, `alembic check` clean, frontend
  73 + build.
- **NA27 — WORKFLOW stats-gating line broadened (2026-06-17)** — "Station Permissions → Current
  enforcement" now states all `/manager/stats/*` (throughput, cycle-time, wip-aging) + the corrections
  reason report are manager/admin-gated via `_ensure_stats_viewer`. Doc-only.

- **NA22 — Packing capacity model: automatic reserves at HANGING start + manual second-slot override
  (2026-06-17)** — Replaced the single `PACKING` lock with **N configurable slots** (`PACKING:1..N`,
  `packing_max_concurrent_slots`, default 2). NA22a: an AUTOMATIC order reserves a slot the moment
  `HANGING` starts and holds it through its packing; a second automatic queues. NA22b: manual
  `start_packing` is the single-station exclusivity gate (409 when occupied) and `?override=true` opens
  an additional slot up to N, audited. Completion is capacity-bound (the start action is the gate). Read
  models add `holds_packing_slot` + `packing_slots_total`; the packing UI shows "Otwórz drugie
  stanowisko" with a warning that surfaces the reserving automatic order's piece count. Tests: rewrote
  `tests/test_packing_station_lock.py` (12), updated API + parallel-hanging tests, chaos
  `automatic_reserves_packing_then_manual_overrides`, frontend override test; base seed reordered +
  demo seed frees slots. Verified: backend `pytest` green, `alembic` clean, frontend 70 + build. Docs:
  WORKFLOW.md "Packing capacity / slots", checklist #9 IMPLEMENTED.

- **Workflow audit (2026-06-17)** — Full read-only audit of the process engine (display-status/READY
  derivation, finalize/merge chain, both correction paths, reopen guards, resource-lock lifecycle,
  auto/manual separation). Verdict: no critical code defect; corrections use a robust *flat-child*
  model (all descendants are children of the root, avoiding deep recursion) and auto/manual cannot be
  tangled mid-flow (`_ensure_production_not_started` guards `update_production_type`). Fixed: the
  **S07/S08 (and tightened S11/S12) scenario-matrix drift** — the matrix claimed correction children run
  their own `DECORAL_PRODUCTION`, but the code (and the Corrections-Behavior section) implement one
  Decoral pass on the root with the child closing at packing. Closed audit test gaps: added
  `test_cannot_change_production_type_after_production_started` (D1), `…_S08` automatic DECORAL
  correction to READY, and `…_S11` correction-of-a-correction to READY (D2). Remaining items logged
  above as NA19 (LOW), NA20 (known), NA21 (policy). Verified: full backend `pytest` green, `alembic`
  clean.

- **NA18 — Live WIP-aging / "stuck orders" view (2026-06-17)** — A live manager view of work currently
  in progress, ordered by how long it has sat in its current stage. New
  `ManagerService.get_work_in_progress_aging` + `GET /manager/stats/wip-aging` (manager/admin only).
  Cohort comes from **live** `WorkOrderStageState` rows that are `IN_PROGRESS` (one per order at its
  furthest-advanced in-progress stage; automatic → `PACKING` over `PRODUCTION`), so a correction reset
  can't leave a stale row; age = `now` − the durable latest `IN_PROGRESS` event from the transition log
  (fallback stage-state `updated_at`). `_as_naive_utc` normalizes log vs `now()` timestamps (SQLite
  returns naive). Statystyki page shows a "Zlecenia w toku" table at the top (oldest first, rows >24h
  highlighted), fetched live independent of the month anchor. Tests: `tests/test_wip_aging.py` (4: sort
  by age, furthest-advanced stage for automatic, excludes not-started, manager gating) + API test in
  `tests/test_manager_api.py`. Docs: WORKFLOW.md "Live WIP-aging". Verified: backend `pytest` green,
  `alembic check` clean, frontend tests + build. Read-only; no workflow/queue change.

- **NA17 — Stage cycle-time / bottleneck stats (2026-06-17)** — First time-in-stage analytics read off
  the `stage_transition_events` log (built as the analytics backbone but previously only feeding packing
  throughput + Decoral-pass m²). New `ManagerService.get_cycle_time_stats` + `GET /manager/stats/cycle-time`
  (manager/admin only): for non-correction orders packed in the window, reports average active time per
  stage (latest `IN_PROGRESS`→latest `DONE`, i.e. the most recent completed pass, so corrections report
  the final pass) and the overall production lead time (first stage `IN_PROGRESS` → packing `DONE`).
  Frontend: new "Czasy etapów" section on the Statystyki page (per-stage average-minutes bar chart,
  headline lead-time figure, table). Tests: `tests/test_cycle_time_stats.py` (4: per-stage averages +
  lead time, most-recent-pass for corrections, out-of-window exclusion, manager gating), API test in
  `tests/test_manager_api.py`. Docs: WORKFLOW.md "Stage cycle-time / bottleneck stats". Verified: full
  backend `pytest` green, `alembic check` clean, frontend tests + build. Read-only analytics — no
  workflow/queue behavior change.
  Extended (2026-06-17): added **queue-wait before each stage** (`average_wait_before_seconds` /
  `wait_orders_count`) — per order, the gap from the most recent stage that finished before this stage
  started to its start (robust for automatic implicit transitions). Statystyki shows a second
  "Średnie oczekiwanie przed etapem" bar chart + an "Oczekiwanie przed" table column. Covered by the
  existing cycle-time tests (wait assertions added). Future: per-operator splits once personal login
  populates `user_id`.

- **NA16 — Packing station exclusivity (2026-06-17)** — Implemented the confirmed single-packing-station
  rule (validation-checklist #9) using the explicit-claim model the user chose. A `PACKING`
  `ProcessResourceLock` (same machinery as `HANGING`/`AUTOMATIC_LINE`, no schema change) is the
  durable claim. New `ProcessService.start_packing` + `POST /process/work-orders/{id}/packing/start`
  (and batch variant) acquires it; `complete_packing` and the tracked-batch path defensively
  take/confirm it, so a different order cannot be started or completed while one is claimed (controlled
  `409`). The claim auto-releases when packing leaves `IN_PROGRESS` (via `_release_inactive_resource_locks`
  / `_occupies_packing`), with stale-claim recovery. Automatic orders merely waiting at packing never
  hold the claim. Read model exposes `is_being_packed`; the packing page shows the entry form only for
  the claimed order, "Zajęte: pakowanie {order}" on others, and a "Rozpocznij pakowanie" claim button on
  free, packing-eligible cards (completion button relabelled "Zakończ pakowanie"). Tests:
  `tests/test_packing_station_lock.py` (8), two API tests in `tests/test_process_api.py`, chaos scenario
  `two_operators_claim_same_packing_station`. Docs: WORKFLOW.md "Packing station exclusivity",
  WORKFLOW_VALIDATION_CHECKLIST.md #9 → IMPLEMENTED. Verified: full backend `pytest` green, `alembic check`
  clean, frontend + build.
  Follow-up DONE (2026-06-17): explicit **release/cancel claim** — `release_packing` +
  `POST .../packing/release` (and batch variant) frees the station without completing (drops the claim
  only, idempotent, cannot release another order's claim); UI "Zwolnij stanowisko" control on the claimed
  card. Covered by service tests (release frees station, idempotent/no-steal), an API test, and frontend
  tests (release button + busy/claim states).

- **NA15 (2026-06-17)** — Dedicated Decoral-pass throughput, built on the new stage-transition log.
  `m2_decoral` is now a separate, additional series attributed at the actual Decoral pass (latest
  `DECORAL_PRODUCTION`→`DONE` `occurred_at`) for non-correction orders, using `total_area_m2` — no
  longer the packing-time approximation, and it does not add into `m2_total`. Backend:
  `ManagerService.get_throughput_stats` drops the packing-time `m2_decoral` case and adds a
  `decoral_by_period` query (no `updated_at` fallback — pass date is only reliable from the log).
  Frontend: new "Przejazd Decoral — m² / dzień" bar chart and the "m² Decoral (przejazd)" table column
  (tooltip clarifies it's an additional counter, not part of m² Razem). Base-coat manual/automatic
  accounting unchanged. Tests: updated `test_throughput_splits_base_production_by_production_type_including_decoral`
  to run the pass, plus new `test_decoral_pass_m2_attributed_at_pass_not_at_packing` (0 before the pass,
  area after). Docs: WORKFLOW.md "Throughput Reporting". Verified: backend `pytest` green, Alembic clean,
  frontend 67 + build. (Open/optional: pieces series for the Decoral chart.)
- **NA-tracking foundation (2026-06-17)** — Added `stage_transition_events`, an append-only log of
  every meaningful stage transition (stage, new status, `occurred_at`, work order, batch, counted
  quantity, station, nullable user) — the durable analytics backbone, since `work_order_stage_states`
  keeps only the latest `updated_at`. Writers mirror the audit choke points (`_record_stage_transition`
  called from `_record_stage_audit_event` / `_record_packing_audit_event` / `_record_decoral_audit_event`
  in `app/process/service.py`), plus the automatic implicit transitions (PRODUCTION/PACKING→IN_PROGRESS
  when automatic HANGING finishes, and automatic PRODUCTION→DONE at packing — added 2026-06-17). Only
  internal correction-reset/merge state changes remain unlogged (the following normal finish re-logs the
  DONE, so analytics stay correct). `StationContext` now carries `user_id` (`app/audit/context.py`) so the column populates
  the day personal operator login exists (NULL today; stations share an identity). Throughput
  (`ManagerService.get_throughput_stats`) is repointed onto the log's latest `PACKING`→`DONE`
  `occurred_at`, with a COALESCE fallback to stage-state `updated_at` for pre-log/historical rows.
  Migration `20260617_0032_stage_transition_events.py`. Docs: WORKFLOW.md "Stage-transition log"
  subsection + attribution note; CLAUDE.md architecture map. New `tests/test_stage_transition_log.py`
  (transitions logged with timestamp/station/user; throughput attributes from the log; COALESCE
  fallback). Verified: full backend `pytest` green, `alembic check` clean. Scope chosen by user:
  foundation only (per-operator stats deferred — collect `user_id` now, decide login later).
- **NA14 (2026-06-17)** — Deleted the dead `frontend/src/components/WorkOrdersTable.tsx`; it was
  imported only by `uiStateConsistency.test.tsx` (the office list uses `OfficeWorkOrdersTable`).
  Removed its three dedicated tests (READY-as-historical, active-progress, office-discrepancy — all
  covered for the real component via the `WorkOrdersListPage`/`OfficeWorkOrdersTable` bucket test)
  and the now-unused import. The office table now has a single source of truth. Verified: frontend
  **67 passed** (was 70), build passes.
- **NA6 (2026-06-17)** — JWT tokens now expire. `create_access_token` (`app/auth/service.py`) adds
  `iat`/`exp` claims; lifetime is configurable via `jwt_expiry_minutes` (`app/core/config.py`,
  default 12h ≈ one operator shift). `decode_token` already returned `{}` on any decode failure
  (including `ExpiredSignatureError`), so an expired token yields no `sub` and `get_current_user`
  returns 401 — verified by `tests/test_auth_service.py`
  (`test_access_token_includes_expiry_claim`, `test_decode_token_rejects_expired_token`). Verified:
  full backend `pytest` green, Alembic clean.
- **NA7 (2026-06-17)** — Weekly throughput now uses one ISO convention end-to-end. Grouping switched
  to `strftime('%G-%V')` (ISO year + ISO week) and `_parse_period_start` parses with
  `date.fromisocalendar(year, week, 1)` (`app/manager/service.py`); removed the old `%Y-%W` /
  `week+1` / `<52` special-casing so week starts land on the ISO Monday and stay correct across year
  boundaries. New `tests/test_throughput_periods.py` covers ISO Monday, year-boundary weeks
  (2026-W01 → 2025-12-29, 2026-W53 → 2026-12-28), labels, and unchanged day/month periods. Verified
  SQLite 3.50.4 supports `%G/%V`; full backend `pytest` green.
- **NA8 (2026-06-17)** — Documented the single-worker deployment constraint in
  `docs/DEVELOPMENT_RUNBOOK.md` (Run The App → backend): cross-request safety relies on in-process
  locks (`_PROCESS_MUTATION_LOCKS`/`_RESOURCE_MUTATION_LOCKS`, `_QUEUE_MUTATION_LOCK`) plus DB
  constraints; the "no duplicate correction child per packing split" guarantee holds only within one
  process, so deploy with exactly one worker (no `--workers N`) until a durable cross-process
  idempotency strategy exists. Accepted near-term; longer-term durable dedup remains future work.
- **NA9 (2026-06-17)** — SQLite engine now applies connection PRAGMAs via a `connect` event
  (`app/database/session.py` `_apply_sqlite_pragmas`): `busy_timeout=5000`, `journal_mode=WAL`,
  `synchronous=NORMAL`, registered only for SQLite URLs. Concurrent writers now wait up to the busy
  timeout instead of surfacing raw `database is locked`. Verified on the app engine
  (`journal_mode=wal`, `busy_timeout=5000`, `synchronous=1`); `.gitignore` already covers the
  `local.db-*` WAL/SHM sidecars. Full backend `pytest` green, Alembic clean.
- **NA10 (2026-06-17)** — bcrypt's 72-byte limit is now handled deterministically
  (`app/auth/service.py`): `MAX_PASSWORD_BYTES = 72`; `hash_password` raises `ValueError` for
  over-long passwords and `verify_password` returns `False` (no silent truncation to a 72-byte
  prefix). Note: bcrypt 5.0.0 already *raises* on >72 bytes (the backlog's "silent truncation" was
  outdated), so the real win is turning a would-be 500 on login into a clean, deterministic outcome.
  Covered by `tests/test_auth_service.py` (reject-on-hash, reject-on-verify, round-trip at limit).
  Full backend `pytest` green.
- **NA4 (2026-06-16)** — Throughput corrections now count both sources of the hybrid model, matching
  the reason report. `ManagerService.get_throughput_stats` (`app/manager/service.py`) aggregates
  `CORRECTION` quantity batches (RAL packing / DECORAL decoral-stage resets) **plus** child correction
  work orders (`is_correction=true`, DECORAL packing), each keyed by its own `created_at`, merged per
  period without double counting (the two sources are disjoint). Previously only child orders were
  counted, so RAL batch corrections were invisible on the "Poprawki" chart/table and disagreed with the
  reason report. Added regression
  `test_throughput_corrections_count_both_ral_batch_and_decoral_child` (RAL batch 7 szt + DECORAL child
  5 szt = 12, asserted equal to the reason-report total). WORKFLOW.md "Throughput Reporting" updated.
  Verified: full backend `pytest` green, Alembic clean. (m² accounting was already correct and is
  unaffected.)
- **Statystyki bar charts (2026-06-16)** — Added per-day bar charts to the Statystyki page: automatic
  m², manual m², and correction pieces, above the existing detail table. Backend change: base-production
  m² is now split purely by `production_type` (`app/manager/service.py`), so a DECORAL order's base coat
  counts toward `m2_manual`/`m2_automatic` exactly like RAL (`m2_manual + m2_automatic = m2_total`);
  `m2_decoral` stays as an overlapping "of which Decoral" subset. Frontend: new reusable
  `frontend/src/components/BarChart.tsx` (custom SVG/Tailwind, no new dependency) and
  `StatystykiPage.tsx` builds series with zero-filled days across the loaded range; the table's Decoral
  column is relabelled "m² z tego Decoral". Docs: new WORKFLOW.md "Throughput Reporting" section.
  Follow-ups logged: NA15 (dedicated Decoral-pass chart, deferred) and NA4 note (correction undercount
  now also affects the chart). Verified: backend `pytest` green incl. new
  `test_throughput_splits_base_production_by_production_type_including_decoral`, frontend 70 passed,
  build passes.
- **NA1 (2026-06-16)** — Authorization now derives from the authenticated user, not the spoofable
  `X-Station-Id` header. `StationContext` carries `station_id` + `is_admin` from the JWT user, and
  `get_station_context` depends on `get_current_user` (`app/audit/context.py`). `ensure_station_allowed`
  now: trusts `None`/`SYSTEM` (internal/seed callers only), bypasses for `is_admin`, and **removed the
  `UNKNOWN` early-allow** so a missing header no longer bypasses anything. Manager statistics
  (`/manager/stats/throughput`, `/manager/corrections/reason-report[/export.csv]`) are now gated to
  manager/admin (`app/manager/service.py` `_ensure_stats_viewer` + router wiring). No backend code reads
  `X-Station-Id` anymore; the frontend already sends `Authorization: Bearer` on every request
  (`frontend/src/main.tsx` interceptor) and the header is now inert (audit context records the
  authenticated user's station). Tests reworked: `tests/conftest.py` authenticates as the station named
  in `X-Station-Id` (non-admin) or admin when absent, so existing per-request station semantics hold;
  added unit tests for the new `ensure_station_allowed` semantics and an API test that statistics
  require manager/admin. Verified: backend **352 passed**, Alembic clean, frontend **70 passed**, build
  passes. (Token expiry — NA6 — remains open.)
- **NA12 (2026-06-16)** — Removed the usable default JWT secret. `app/core/config.py` now rejects the
  committed default (or empty) `JWT_SECRET` when `APP_ENV` is not a local/development env, failing fast at
  startup. Verified: dev allows the default, `production` with the default is blocked, a real secret is
  accepted, backend 347 passed. (Token expiry — NA6 — still open.)
- **NA13 (2026-06-16)** — Frontend suite green again (70 passed, build passes). Fixed two real UI
  defects — a duplicate discrepancy line in `WorkOrdersTable` and a stray `::` span in
  `ManagerPanelPage` — and a real packing bug: a `HANGING` preview row in `PackingWorkOrdersPage` now
  renders read-only (no form/inputs/buttons) instead of the full packing form, matching WORKFLOW.md
  "read-only waiting visibility". The rest were stale assertions in `uiStateConsistency.test.tsx`: the
  manager panel renders the title via the un-mocked `WorkOrderPrimaryInfoLine` (`·`-separated, order
  number shown twice as eyebrow + title), so `findByText("WO :: Customer")` locates were updated to
  `findAllByText("WO-…")`; the office buckets test was updated to `OfficeWorkOrdersTable`'s wording
  (`10 / 10 szt.`, `Wydane`); and the correction-planning "Automat" click is now scoped with `within`.
- **NA2 + NA5 (2026-06-16)** — Made `pywin32` a Windows-only dependency
  (`pyproject.toml`: `pywin32>=306; sys_platform == 'win32'`) and made the Excel→PDF converter lazy
  with fail-fast behavior (`app/work_orders/service.py`): importing the module no longer launches Excel
  (verified), and a missing Excel/pywin32 now raises a clear error instead of hanging to the timeout.
  Verified: backend 347 passed, Alembic clean, frontend build passes.
- **NA11 (2026-06-16)** — Ran the suite (see NA11 above): backend green, Alembic clean, frontend build
  green, frontend tests revealed a pre-existing red state now tracked as NA13.
- **NA3 (2026-06-16)** — Reconciled `docs/WORKFLOW.md` with the hybrid correction model: RAL resets the
  same order to planning with a `CORRECTION` batch (no child); DECORAL creates a child "P" order. Updated
  principle #8, the Corrections Behavior section, the multi-round note, the S05/S06/S09/S10 scenario-matrix
  rows, and the Station Permissions auth wording.
- **Doc sweep (2026-06-16)** — Reconciled docs vs code across the repo:
  - `README.md`: added `audit/auth/clients/paints` to the module map, expanded Current Scope (auth/login,
    clients, paint inventory, statistics, audit console, QC doc), added `JWT_SECRET` to `.env`, corrected
    the seed description, and added a Login section with dev credentials.
  - `docs/DEVELOPMENT_RUNBOOK.md`: added a Login section (auth is required; where to find credentials).
  - `docs/STATION_IDENTITY_AND_AUDIT.md` and `HARDENING_BACKLOG.md`: noted that authentication is now
    implemented and that the open gap is role-based authorization (NA1).
  - New finding logged from the sweep: NA12 (hardcoded default `JWT_SECRET`).

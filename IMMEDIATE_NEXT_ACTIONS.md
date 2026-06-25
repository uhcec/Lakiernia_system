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

### NA60. `assign_plan` trailing-completed shuffle collides → unhandled HTTP 500 when planning onto a line that holds completed orders
- Status: **FIXED (2026-06-24) — see Done section.** Root cause: the temporary parking range overlapped the
  final trailed range, so the PK-ordered flush transiently violated the unique index. Fix: offset the temp
  base by `len(work_orders)` so the temp range is strictly above every final position (one line in the shared
  `_temporarily_move_queue_rows_out_of_the_way`, fixing all three callers). Regression test added; reproduced
  the exact 500 (red) then green; full `pytest` + `alembic check` clean; live-verified the original plan now
  returns 200.
- Problem: planning a work order onto a production line where one or more **completed (READY)** orders still
  occupy queue positions raises `sqlite3.IntegrityError: UNIQUE constraint failed:
  work_orders.production_type, work_orders.queue_position` during the trailing-completed shuffle, and it
  surfaces as a raw **HTTP 500**. `assign_plan` (`app/manager/service.py:1470`) does a two-phase shuffle —
  `_temporarily_move_queue_rows_out_of_the_way` → set the new order's `queue_position` → `flush()`
  (line 1516) → `_trail_completed_work_orders` (line 1517) — and wraps only the **final** `repository.commit()`
  in `IntegrityError → InvalidManagerPlanningError` (lines 1533-1539). The collision fires during an
  intermediate **flush** (the trail step, executed as an `UPDATE work_orders SET queue_position=? WHERE id=?`
  executemany), which is **outside** that try/except, so it escapes unmapped. Same class as the closed NA48
  (which fixed `update_production_type`), but in `assign_plan` itself and only triggered once several completed
  orders have piled up on a line — which normal multi-day use produces.
- Reproduction: with MANUAL holding 1 active + 5 READY orders (positions 1-6), `POST /manager/work-orders/{id}/plan {"production_type":"MANUAL"}`
  on a fresh order returns 500. The empty AUTOMATIC line accepted plans fine — it is specific to a line with
  trailing completed orders. (Two defects: (1) the shuffle reaches a transiently-colliding intermediate state;
  (2) the `IntegrityError` guard doesn't cover the intermediate flush where the collision actually occurs.)
- Required fix: make the trailing/temporary-move shuffle collision-free (e.g. park rows at guaranteed-unique
  temporary positions and apply final moves in a non-colliding order, or order the executemany so no
  intermediate state violates the unique index), AND extend the `IntegrityError → InvalidManagerPlanningError`
  mapping to cover the whole mutation (the intermediate flush, not just the final commit) so a queue collision
  can never be a 500. Regression test: plan onto a line carrying several completed orders.
- Acceptance: planning onto a line with any number of trailing completed orders succeeds (appends past them)
  or fails with a clean 4xx; never a 500. Test pins the multi-completed-order case.

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

### NA59. DECORAL correction at the Decoral pass uses the RAL in-place reset, not the documented child spin-off
- Status: **RESOLVED by documentation (2026-06-25) — the code is correct; the docs were the gap.** Owner
  confirmed the observed behavior is the intended one: a DECORAL defect found **at the Decoral pass** (the foil
  work itself) is corrected with the RAL-style same-order in-place reset (a `CORRECTION` batch on the same
  order, no child, no `N`), whereas the child/`N` model is specifically for defects found **at packing**
  (base coat, before foil). Documented in `docs/WORKFLOW.md` (Corrections Behavior — new "Decoral pass" block +
  qualified invariant #8 + a note under the S01–S12 matrix) and the CLAUDE.md core-domain summary. No code
  change. See Done section.
- Original finding (kept for context) — surfaced by the workflow simulation (Phase 1, 2026-06-24), code-verified.
- Problem: completing a DECORAL pass with a correction via the **plain** per-order endpoint
  `POST /process/work-orders/{id}/decoral-production/complete` (no batch id) routes through
  `_reset_to_correction_planning(..., completed_stage=DECORAL_PRODUCTION)` (`app/process/service.py:954-967`),
  i.e. the **RAL same-order** model: the root order itself bounces back to `TO_BE_PLANNED` with a CORRECTION
  batch on itself, `is_decoral_incomplete=false`, **no child order**. The documented DECORAL correction model
  (`docs/WORKFLOW.md` ~L24/L957, CLAUDE.md "Core domain model") is a **child `P{root}` spin-off** while the OK
  part stays on the root's single Decoral pass and the root shows the "N" marker. The child path only fires on
  the **tracked-batch** variant (`.../batches/{batch_id}/decoral-production/complete`, line 929), which the
  operator UI / a plain completion does not use. Sim evidence: order 0003 (DECORAL qty 12), 11 OK / 1 correction
  → root 0003 went to `TO_BE_PLANNED` with a self CORRECTION batch (qty 1), 0 correction_orders,
  `is_decoral_incomplete=false`; downstream it will presumably re-run surface prep/production rather than just
  re-doing the Decoral pass.
- Required fix (pending semantics): either route the plain decoral-completion correction through the same
  DECORAL spin-off seam as packing (`_select_correction_kind`/`_dispatch_packing_correction`, NA40) so a child
  `P{root}` carries the rework, or — if same-order reset at the Decoral pass is intended — document that
  explicitly and reconcile `docs/WORKFLOW.md`/CLAUDE.md. Add regression coverage for a correction raised at the
  Decoral pass (both endpoint variants).
- Acceptance: a DECORAL correction raised at the Decoral pass behaves per the (decided) model consistently
  across the plain and batch endpoints; docs and code agree; regression test pins it.

---

## LOW

### NA31. Manager panel suggests/blocks a wrong queue position after a correction returns to planning
- Status: **RESOLVED (2026-06-23) by the per-line queue rebuild — supersedes the earlier reconcile fix.**
  The colleague's 2026-06-22 fix added a `reconcilePlanDrafts` helper so the background poll re-seeded the
  suggested queue position. The per-line rebuild then removed queue-position picking from planning entirely:
  planning is now a single "Zaplanuj" button that appends to the end of the selected line (server-computed
  position), so `planDrafts` / the `activeCount + 1` suggestion logic — and with it the bug — no longer exist
  in `ManagerPanelPage.tsx`. Consequence of the merge: the reconcile helper and its test
  `frontend/tests/managerPlanDraftReconcile.test.tsx` cover behavior the per-line UI no longer has; the test
  was removed during the merge (see Done note). Confirm in a walkthrough, then close.
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

### NA58. Surface-prep `counted_quantity` collapses the profiles/accessories split (fidelity gap)
- Status: OPEN — surfaced by the workflow simulation (Phase 0, 2026-06-24); needs owner confirmation that
  it matters before any work.
- Problem: an order carries `profiles_quantity` + `accessories_quantity` separately
  (`app/work_orders/schemas.py` `WorkOrderCreate`), but the surface-preparation start records only a single
  `counted_quantity` (`StageTransitionRequest`, `app/process/schemas.py:87`; `start_stage`,
  `app/process/router.py:38`). When the physical count is short, the operator cannot record *which* group was
  short — the shortfall total is captured, its attribution is lost, so downstream nobody knows whether
  profiles or accessories were missing. (Sim friction note: prep counted 118 vs planned 120 on a
  100-profile/20-accessory order with no way to say the 2 missing were profiles.)
- Required fix (if owner wants it): allow an optional per-group counted split at surface preparation that sums
  to `counted_quantity`, mirroring how packing corrections already split profiles/accessories; otherwise
  document that surface-prep counting is intentionally aggregate.
- Acceptance: either the operator can attribute a short count to profiles vs accessories, or `docs/WORKFLOW.md`
  states the aggregate count is by design. No silent loss of which group was short.

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
  (`.claude/commands/doc-audit.md`), intended cadence **on-demand** (NA47, 2026-06-22 — superseded the
  earlier "weekly"; not a standing schedule). Run it to re-reconcile the docs and
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

### NA50. Statystyki measure volume/composition but are blind to the redefined "good day"
- Status: **DONE (2026-06-24).** New read-side of the capacity model: pure DB-free core
  `app/manager/good_day.py` (`summarize_day` / `summarize_period`) + `ManagerService.get_good_day_stats`
  (manager-gated, `GET /manager/stats/good-day`, AUTOMATIC default) computes, **per day off the
  stage-transition log**, the headline trio — **m² vs the profitable floor** (`met_floor` + shortfall),
  **on-time %** (PACKING-done ≤ the hard `planned_pickup_date` from N49-1), and **colour-changeover
  loss** (the day's change count × the learned N49-2 per-change cost → m² of booth capacity, the shared
  `changeover_loss_m2`) — plus the two diagnostics, **effective booth rate** (m²/h from the day's
  bracketed passes) and **utilisation / idle** ("fabryka nie stała"). Period totals roll up days-met-floor,
  overall on-time %, total loss, avg utilisation. Frontend: a "Dobry dzień" section on `StatystykiPage`
  (headline cards + per-day table, below-floor days highlighted). **Assumption flagged:** historical shift
  length isn't persisted, so every day is measured against the long-day full-shift bar (800 m² / 14 h);
  on-time + booth metrics are line-scoped. No schema change (read-only over existing tables); `alembic
  check` clean. Tests: `tests/test_good_day.py` (5 pure: floor/on-time/changeover-loss/idle, period
  roll-up, empty) + `tests/test_good_day_service.py` (4 service/DB: floor+on-time, below-floor flag,
  changeover loss counts colour changes, manager gating). 576 backend + 90 frontend pass; both builds green.
  Owner to confirm: the headline set, whether on-time should be **factory-wide** (both lines) rather than
  per-line, and whether the floor should use a recorded per-day shift length once that is captured.

### N49-11. Planner zero-capacity day-0 edge + 3-day board polish (2026-06-24, owner-driven, live-verified)
- Status: **DONE (2026-06-24).** Follow-ups from the live-app verification (`/verify`) of the NA5x planner
  work: (1) **zero-capacity today** — when a plan is built after the shift ends, today's pro-rated capacity
  is 0; the first order was stranded on it flagged `over_ceiling` ("ponad limit na 0 m² dziś"). Now
  `place_orders` keeps today as an **empty closed column** and starts the work tomorrow when today can't
  take the first order (a genuinely > full-day order still lands + flags). (2) **Owner: "only plan 3 days —
  today, tomorrow, the day after tomorrow."** The horizon was already 3 working days; the board now renders
  **only the in-horizon dated days** (`scheduled_date != null`), so overflow no longer appears as a 4th
  dateless column — those orders stay in the "won't make it" banner (and remain in the NA51 apply payload,
  verified end-to-end: a 19-order reorder incl. overflow is accepted). (3) Frontend shows a closed today as
  "Po godzinach — planowanie od jutra". Tests: pure placement (shift-over → empty today + work next day;
  partial-today takes-what-fits) + frontend (closed-today + dateless-overflow-hidden); ~3 service tests
  pinned a pre-shift `now` for determinism. **Live re-verified at 23:02:** today `gross/net/placed=0,
  over=False`, board renders 3 dated days, 2 overflow buckets dateless → infeasible, apply still accepts all
  19. 596 backend + 94 frontend pass; both builds green; `alembic check` clean. `docs/WORKFLOW.md` updated.
  - Original framing — verification finding (clean-slate process session, 2026-06-23), confirmed in code.
- Severity: **MEDIUM** (manager-facing truth — the stats answer the *old* question, not the one the
  multi-day capacity model now defines as a good day).
- Finding: `ThroughputPeriod` (`app/manager/schemas.py:54-67`) reports m² split by method + coating, the
  decoral pass, and orders/correction counts; cycle-time + WIP-aging cover time-in-stage and stuck
  orders. **None** of these expose what NA49 / `docs/FACTORY_DOMAIN_MODEL.md` §7 make the *definition* of
  a good day:
  1. **Daily m² vs the FLOOR (800/500)** — profitability; did we clear the minimum? (needs the day's
     shift length → couples to N49-3.) MISSING.
  2. **Automatic booth m²/h rate** — MISSING (this is also the N49-2 measurement engine; build once,
     surface here).
  3. **Colour-changeover loss** (count / time / m² of capacity lost) — exists only as a *planning
     preview* (`app/manager/schemas.py:205-208`, scheduler proposal), **not** a historical stat. MISSING.
  4. **On-time deadline %** (deadlines are hard) — MISSING entirely (no shipped-on-time vs late series).
  5. **Booth idle / utilisation** ("fabryka nie stała") — MISSING.
- Direction: the headline trio — **profitability vs floor, on-time %, changeover loss** — is
  definitionally what the model calls a good day; add those. m²/h and idle are diagnostics. The long-tail
  "what other stats does the colleague want" stays deferred (the NA33 stats sub-part), but these five are
  **model-derived, not wishlist**, so they should not wait on him.
- Depends on: N49-1 (deadline required → on-time), N49-2 (measurement engine → rate/changeover), N49-3
  (shift length → the floor line). Build these stats as the read-side of those.
- Acceptance: Statystyki can show, per day, m² vs the profitable floor, on-time %, and changeover loss,
  each derivable from the stage-transition log; covered by tests; owner confirms the headline set.

### NA51. The multi-day board and the real queue are two decoupled orderings, with no way to reconcile them
- **Owner decision (2026-06-24): BLEND (show both)** — the board shows the manager's *actual* queue order
  AND the system's *suggested* (EDF + light→dark) order side by side, with an **"Zastosuj" (Apply to queue)**
  action that writes the suggested order back to `queue_position`. Resolves the confusion (the manager can
  always see what the line really runs) while keeping the optimisation available on demand. Pin/urgent stays
  the deferred NA49.K.
- Status: **DONE (2026-06-24).** No new mutate/schema — the apply **reuses `POST /manager/queue/reorder`**.
  Backend: `OrderPlacementRead` gained the order's live `queue_position` and `MultiDayPlanRead` gained the
  line's `queue_revision` (`app/manager/{schemas,service}.py`), so the board has both orderings + the
  stale-write token from one payload. Frontend (`CapacityBoard.tsx`): the day columns remain the
  *suggested* order; a comparison strip shows **Twoja kolejność** (placements by `queue_position`) vs
  **Sugerowana** (by `day_index`, `sequence_position`) and a **"Zastosuj plan"** button that rebuilds the
  reorder payload (suggested ids → positions 1..n) with the plan's `queue_revision` and calls
  `reorderWorkOrderQueue`, then refetches; when the live order already equals the suggestion it shows
  "Kolejność na linii jest zgodna z planem" and hides the button. Works for either line via the NA55
  toggle. Tests: backend `test_plan_carries_queue_position_and_revision_for_the_blend` +
  `test_suggested_order_applies_back_via_reorder_queue` (drives a real plan's suggested order through
  `reorder_queue` and asserts the live queue is rewritten); frontend capacityBoard "applies the suggested
  order…" (asserts the reorder payload) + the matching-order "zgodna z planem / no button" case. 589
  backend + 93 frontend pass; both builds green; `alembic check` clean (no schema change). `docs/WORKFLOW.md`
  capacity-board section updated. NA49.K (drag / pin / urgent) stays deferred (needs a persisted flag).
- Status (original): **OPEN — owner-surfaced 2026-06-24** while looking at the live planner: the multi-day board
  showed orders 0114/0115 "today", but those two are **not** the first orders worked today per the actual
  line queue. Owner: "trochę nie rozumiem czy to tak specjalnie czy co." It is partly intentional (the
  board sorts by deadline, see below) but exposes a real half-built state, hence this item.
- Severity: **MEDIUM** (manager-facing coherence/truth — the planning surface contradicts what the line
  actually does, with no way to act on it; not data corruption).
- Problem: there are **two independent orderings** that do not know about each other:
  1. **The real, executable queue** — `WorkOrder.queue_position` per line (what the stations consume).
     The manager owns it via `assign_plan` (append to end) / `update_queue_position` / `reorder_queue`.
  2. **The multi-day board** (`GET /manager/planner/multi-day`, `frontend/src/components/CapacityBoard.tsx`)
     — a **read-only projection** that **ignores `queue_position` entirely** and sorts strictly by hard
     deadline: `place_orders` does `sorted(orders, key=lambda o: (o.planned_pickup_date, o.work_order_id))`
     (`app/manager/placement.py:158`), then applies a within-day light→dark colour sweep (N49-5) on top.
  So the board shows the system's *opinion* of what should run today (earliest deadline first), while the
  line runs the manager's `queue_position` order — and **nothing reconciles them**. The board has no
  "apply to queue" action (the only mutate is `reorder_queue`; the one applyable proposal is the NA33
  lexicographic `propose_auto_schedule`, which is a *different* algorithm from the board's EDF + light→dark
  — see NA49.H/I). This is the deferred **NA49.K** (drag/pin/apply) seen from the user's side.
- Why it's confusing: 0114/0115 almost certainly carry the earliest `planned_pickup_date` of the planned
  set, so the board is "correct" by its own rule — but a manager reasonably reads the board as "what's next
  on the line", which it is not. The board is a forecast/recommendation, not a mirror of the plan and not a
  driver of it.
- Decision needed (owner) — what should the board *be*?
  - **Option A — faithful forecast:** the board respects `queue_position` (shows the manager's actual
    order spread across days) and *flags* where that order breaks a deadline / the floor. Less "clever",
    but consistent with what the line actually does.
  - **Option B — optimal recommendation + apply:** keep the EDF + light→dark recommendation, but add an
    **"Apply to queue"** action (and ideally pin/urgent — NA49.K) so the line can adopt the board order.
    Without it the board will always drift from reality and mislead.
  - A blend is possible (show both: "your order" vs "suggested order", with an apply button).
- Required fix: once the owner picks A/B, either (A) re-base the board projection on `queue_position`
  within each capacity day, or (B) add a mutate that writes the board's derived order back to
  `queue_position` (respecting pins), and resolve the NA33-vs-light→dark two-algorithm split (NA49.H/I) so
  "what you see" equals "what you apply".
- Acceptance: the manager can tell, without confusion, the difference between the planned order and any
  suggested order; if a suggestion is shown, there is a way to apply it; the board no longer silently
  contradicts the executable queue. Covered by tests; `docs/WORKFLOW.md` "Target planning model" updated.
- Related: **NA49.K** (drag/pin/urgent — deferred), **NA49.H/I** (NA33 scheduler is a crude lexicographic
  proxy, distinct from the board's light→dark sweep), **N49-9** (the read-only board first cut).

### NA52. Learned colour-changeover cost is wildly inflated (≈254 min/change) — it absorbs idle/overnight gaps, collapsing the capacity plan
- Status: **DONE (2026-06-24).** Applied the "cleanest fix": the **bounded N49-6 size+direction** cost now
  drives the capacity model on **both** planner endpoints, and the N49-2 statistical estimate is demoted to
  a diagnostic (`GET /manager/stats/line-measurements` only). Changes (`app/manager/service.py`):
  `get_multi_day_plan` feeds `place_orders` the average N49-6 changeover minutes of the whole line's
  light→dark sweep (not `changeover.estimated_changeover_minutes`) to size each day's net ceiling, and
  surfaces that bounded figure as the top-level `changeover_minutes` (`changeover_is_measured=True` — the
  size+direction cost is always determinate). `get_good_day_stats` now values each day's changeover loss
  with the day's own bounded N49-6 per-change cost (`average_changeover_minutes` over the day's run) and
  rolls the **already-computed** per-day metrics up directly (no re-summarise with one period-wide cost),
  fixing the **#2 NA50 inheritance** in the same change. `AutomaticPassObservation` gained `ral_code` so
  good-day can derive the direction cost. `get_day_capacity` already used the bounded cost — unchanged. No
  schema change; `alembic check` clean. Tests: new `tests/test_planner_changeover_bound_na52.py` (2 — a
  contaminated spread-across-days log produces an inflated N49-2 estimate, yet the multi-day plan's cost
  stays ≤ the 30-min band and a long day isn't collapsed; a good-day's changeover loss stays bounded and
  below the day's output). 578 backend + 91 frontend pass; both builds green. `docs/WORKFLOW.md` "Target
  planning model" + good-day section updated.
- Status (original): **OPEN — found 2026-06-24** while explaining NA51 on the live planner walkthrough DB.
  Confirmed in code + data: the planner's day-capacity math is being driven by a changeover cost an order
  of magnitude above the confirmed 15/30-min bands.
- Severity: **MEDIUM–HIGH** (it makes the headline planner feature — the multi-day board, day-floor, and
  the "won't make it" set — misleading; not data corruption since the planner is still advisory/read-only).
- Evidence (live, AUTOMATIC line, `seed_n49_planner_walkthrough` DB, today 2026-06-24):
  - `get_multi_day_plan(...).changeover_minutes = 254.2`, `changeover_is_measured = True` (so it's the
    *learned* value, not the 20-min seed).
  - `capacity.changeover_loss_m2` turns that into **338.9 m² of booth ceiling lost per single colour
    change** (gross ceiling LONG = 80 m²/h × 14 h = 1120 m²; net after 1 change = 781, after 2 = 442,
    after 3 = **103**). So ~3 colours nearly zero out a 14-hour day.
  - Consequence: the board fragments and **every day reads below the 800 m² floor** — e.g. day 0 = 540 m²
    (2 orders), day 1 = **43 m²** (3 tiny orders, 2 changes), day 2 = 480 m². EDF can't fill a day to the
    ceiling because adding any new colour collapses the net ceiling below what's already placed.
- Root cause (hypothesis, strong): the N49-2 measurement engine estimates the changeover cost as the
  *extra* average inter-start gap when the colour changes vs. when it stays the same
  (`app/manager/measurement.py`, HANGING-start → next HANGING-start residual). When automatic passes are
  spread across days (as in any realistic log / this seed), the inter-start gap for a colour change is
  dominated by **overnight / idle time**, not the actual booth wash — so the engine learns idle time as
  "changeover cost". The residual is only clamped ≥ 0, never bounded to a plausible within-shift wash
  window, and never sanity-capped against the confirmed 15/30-min bands.
- Required fix (decide with owner): bound the changeover measurement to **consecutive same-shift/same-day
  passes** (exclude gaps that cross an idle threshold / a day boundary) so it measures wash time, not
  downtime; and/or **clamp the learned value to a sane band** (e.g. ≤ the 30-min "z odzysku" band, or the
  N49-6 size-aware band) so a contaminated estimate can't dominate the capacity model; fall back to the
  seed (20 min) until enough *clean* same-shift colour-change samples exist. Add a regression test with a
  spread-across-days log asserting the estimate stays within the band.
- Acceptance: the learned changeover cost stays within a physically plausible band regardless of idle gaps
  in the log; a day's net ceiling is no longer collapsed by 1–3 colour changes; the multi-day board fills
  days toward the floor instead of fragmenting. Covered by tests; `docs/WORKFLOW.md` "Target planning
  model" / `FACTORY_DOMAIN_MODEL.md` §7 updated if the measurement definition changes.
- Related: **N49-2** (the measurement engine that produces the figure), **N49-3/N49-4** (the capacity /
  placement consumers it distorts), **NA50** (good-day stats also surface a `changeover_loss_m2` from the
  same source — likely inflated there too; check when fixing).
- **Sharpened 2026-06-24 (code review of the N49 series) — the two planner endpoints cost a colour change
  from two DIFFERENT sources, which both pinpoints the root cause and reveals an internal inconsistency:**
  - `get_day_capacity` (single-day view) costs changeovers with the **N49-6 size+direction model**
    (`ManagerService._day_changeover_minutes` → bounded 15/30-min bands), passed as `changeover_minutes`
    to `compute_day_capacity` (`app/manager/service.py:1071,1078`). This view is sane.
  - `get_multi_day_plan` (the board) instead feeds `place_orders` the **N49-2 statistical learned**
    estimate `changeover.estimated_changeover_minutes` (the contaminated ≈254 min) to size each day's
    *net ceiling* (`app/manager/service.py:1163`), and surfaces that same inflated number as the
    top-level `MultiDayPlanRead.changeover_minutes` (`:1258`) — while the **per-day** `changeover_minutes`
    it displays uses the bounded N49-6 value (`:1199,1244`). So the board fragments days as if each change
    cost ≈254 min but shows "~20 min" per day: a self-contradiction the manager sees directly. The
    `capacity.py` / `placement.py` docstrings claim the two "never drift" because they share
    `changeover_loss_m2` — true only for the *formula*, NOT for the *minutes input*, which is exactly where
    they drift.
  - **Cleanest fix (supersedes the "bound/clamp the statistical estimate" option above):** feed
    `place_orders` the same bounded **N49-6 size+direction cost** the single-day view already uses, and
    demote the N49-2 statistical estimate to a *diagnostic* (do not let it drive the capacity model or the
    headline figure). This removes the idle/overnight contamination from the model entirely instead of
    trying to clean it, and makes "what you see" (per-day cost) equal "what placed the orders" (net
    ceiling).
- **#2 RESOLVED 2026-06-24 (in the NA52 fix) — the good-day stats no longer inherit the inflation (NA50).**
  `get_good_day_stats` previously multiplied each day's colour-change count by the period-wide learned
  `changeover.estimated_changeover_minutes`, so a 3-change day reported ≈1000 m² of "changeover loss" that
  could exceed the day's actual output. It now values each day's loss with the day's own **bounded N49-6**
  per-change cost (`average_changeover_minutes` over that day's run) and rolls the per-day metrics up
  directly. Covered by `tests/test_planner_changeover_bound_na52.py`.

### NA53. Good-day per-day "effective booth rate" is almost always the seed (dead diagnostic)
- **Owner decision (2026-06-24): PERIOD FIGURE ONLY** — drop the per-day rate; show booth rate as a
  period total (where ≥3 passes is realistic). Don't show a seed dressed as a per-day measurement.
- Status: **DONE (2026-06-24).** Removed the per-day `rate_m2_per_h` / `rate_is_measured` from
  `GoodDayMetricsRead` (they were declared but never even rendered) and added them to `GoodDayTotalsRead`
  as a **period** figure: `get_good_day_stats` computes `measure_automatic_rate(observations)` once over
  the whole window (idle gaps fall out of the union) — measured once ≥ 3 passes are bracketed, else the
  57 m²/h seed flagged `rate_is_measured=False`. Per-day `active_hours` (for utilisation/idle) is still
  derived per day. Frontend: dropped the unused per-day fields from the `GoodDayMetrics` type, added a
  "Tempo kabiny (okres)" headline card on `StatystykiPage` with a zmierzone / "szacunkowo (za mało
  przejazdów)" marker (grid widened to 5). Tests: `tests/test_good_day_service.py` gains
  measured-with-≥3-passes (600 m²/h) and seed-when-sparse cases. 580 backend + 92 frontend pass; both
  builds green; `alembic check` clean (no schema change). `docs/WORKFLOW.md` good-day diagnostics updated.
- Status (original): **OPEN — found 2026-06-24 (code review of the N49 series).**
- Severity: **LOW** (a diagnostic that silently shows a constant, not a defect in the headline metrics).
- Problem: `get_good_day_stats` computes the per-day rate with `measure_automatic_rate(day_passes)`
  (`app/manager/service.py:885`), which only reports a *measured* rate once it has `MIN_RATE_SAMPLE_ORDERS = 3`
  bracketed passes (`app/manager/measurement.py:37,106`). A single day rarely has ≥3 completed automatic
  passes, so `rate_is_measured` is almost always `False` and the "effective booth rate" column shows the
  57.0 m²/h seed regardless of what the line actually did that day. The diagnostic is effectively constant
  per-day.
- Required fix (decide with owner): either drop the per-day rate and surface it only as a *period* figure
  (where ≥3 passes is realistic), or lower the per-day sample floor with an explicit "low confidence"
  marker. Don't show a seed dressed as a measurement.
- Acceptance: the rate shown per day is either genuinely measured or clearly flagged as the seed; covered
  by a test asserting a low-volume day is not presented as measured.

### NA54. Paint hard-block is binary on starting stock, not demand-aware
- **Owner decision (2026-06-24): DEMAND-AWARE BLOCK** — hard-block when the *first* planned order's
  predicted demand already exceeds available stock (the "myśleli że jest, a jej nie ma" case), not only
  when the colour is already at ≤ 0 kg. Keep the manual-used-colour low-confidence caveat (warn, never
  hard-block there).
- Status: **DONE (2026-06-24).** `colour_series_blocked` (`app/manager/paint_feasibility.py`) gained a
  keyword `first_order_demand_kg`: a tracked, metered colour is BLOCKED when it's out of stock (≤ 0)
  **or** the first order's demand exceeds the available stock. `build_forward_view` passes the demand only
  for the **first** order on each colour series (a later overrun stays a WARNING — deliver before the line
  reaches it). The plan-time gate `_assert_paint_available_for_automatic` mirrors this: it blocks an
  AUTOMATIC order when no already-planned automatic order shares its colour (so it's the series' first) and
  its predicted demand exceeds stock; the error now reads "out of stock or insufficient". Manual-used /
  untracked escapes unchanged. Tests: pure (first-order demand>stock → BLOCKED; first fits then second
  overruns → WARNING; predicate truth-table incl. demand-aware + manual/untracked escapes) +
  service (`test_plan_blocked_when_first_order_demand_exceeds_stock`). 583 backend tests pass; `alembic
  check` clean (no schema change). `docs/WORKFLOW.md` "Target planning model" paint section updated.
- Status (original): **OPEN — found 2026-06-24 (code review of the N49 series).** Possibly intentional — confirm with
  owner.
- Severity: **LOW** (the WARNING still fires; this is about which signal the gate trusts as *hard*).
- Problem: `colour_series_blocked` hard-blocks a colour series only when `current_stock_kg <= 0`
  (`app/manager/paint_feasibility.py:88`). A tracked, metered colour with e.g. 5 kg in stock but 100 kg of
  planned demand is only **WARNING**, never **BLOCKED** — so the "hard block" that exists to stop the
  missed-norm "myśleli że jest, a jej nie ma" case will *not* refuse an order that plainly cannot be
  painted from the existing stock; it only refuses a colour already at zero.
- Required fix (decide with owner): confirm whether the hard block should fire when the *first* order's
  demand already exceeds available stock (demand-aware block) or stay a pure out-of-stock (≤0) gate with
  the shortfall left as a WARNING. Document the decision in `docs/WORKFLOW.md` "Target planning model".
- Acceptance: the block/warn boundary matches the agreed rule; covered by a test for the
  "some stock, not enough for the first order" case.

### NA55. CapacityBoard is AUTOMATIC-only and fetches once on mount (no line toggle, no refresh)
- Status: **DONE (2026-06-24).** `frontend/src/components/CapacityBoard.tsx` now has a **MANUAL / AUTOMATIC
  line toggle** (segmented control, AUTOMATIC default) and **refreshes on the station poll cadence**
  (`usePolling` @ `STATION_POLL_INTERVAL_MS`) so it tracks work planned on other devices. The loader
  guards against a late response for a previously-selected line (`lineRef` compare), drops the old plan on
  a line switch, and the error/empty states render inside the section so the toggle stays visible. Eyebrow
  label + empty/description copy are line-agnostic. Frontend-only; no backend change (the
  `/manager/planner/multi-day` endpoint already accepts `production_type`). Tests:
  `frontend/tests/capacityBoard.test.tsx` gains a toggle case (pressing "Ręczna" refetches with `MANUAL`
  and flips `aria-pressed`); the default case now asserts the initial `AUTOMATIC` fetch. 92 frontend tests
  pass; build (+tsc) green. The board's deeper *nature* (forecast vs recommendation+apply) is still the
  NA51 owner decision — this only gave the existing read-only board its missing reach.
- Status (original): **OPEN — found 2026-06-24 (code review of the N49 series).** Documented as a "first cut"
  (N49-9), logged so it isn't lost; partly subsumed by NA51.
- Severity: **LOW** (the read-only board is correct for what it shows; this is missing reach).
- Problem: `CapacityBoard.tsx` hardcodes `fetchMultiDayPlan("AUTOMATIC", 10)` in a mount-only effect
  (`frontend/src/components/CapacityBoard.tsx:109`) — no line toggle (the MANUAL line is never shown) and
  no polling/refresh, so the board can drift from the live queue between page loads. Reinforces NA51: the
  board can't even display the manual line the manager also plans.
- Required fix: add a line toggle (MANUAL / AUTOMATIC) and refresh the board on the manager panel's
  existing poll cadence; fold into the NA51 decision (what the board *is*).
- Acceptance: the board can show either line and stays current with the planning queue; covered by a UI
  test.

### NA56. Planner working-day calendar is a hardcoded Mon–Fri assumption, and day 0 is always treated as a full day
- **Owner decision (2026-06-24): keep Mon–Fri (make the weekend set configurable, no holiday list yet) and
  PRO-RATE today** — day 0's capacity is shrunk to the shift hours left when the plan is computed (a plan
  built at 16:00 of a shift ending 21:00 has ~5 h of day-0 capacity), instead of always assuming a full day.
- Status: **DONE (2026-06-24).** New pure `remaining_shift_hours(now, shift_length)` in
  `app/manager/capacity.py` (shift starts 07:00; clamps to `[0, full shift]`). `place_orders` gained
  `first_day_hours` which pro-rates **day 0 only** — its gross ceiling *and* floor scale by
  `first_day_hours / full`, so a mid-shift plan doesn't promise a whole day today and the pro-rated floor
  isn't spuriously failed; `None` = full day 0 (identical to before). `get_multi_day_plan` gained an
  injectable `now` (defaults to the server clock) and passes the pro-rated day-0 hours. The Mon–Fri weekend
  set is **confirmed** (no longer an open ASSUMPTION) and documented as the single configurable point via
  `working_days_from`'s `weekend_weekdays` (holidays deferred). Tests: pure `remaining_shift_hours`
  (pre-shift/mid/after, short shift), `place_orders` day-0 proration (ceiling+floor scale, later days full),
  service mid-shift spill (`now=16:00` → second order spills to day 1); existing placement service tests
  pass a fixed pre-shift `now` so they stay deterministic. 587 backend + 92 frontend pass; both builds
  green; `alembic check` clean (no schema change). `docs/WORKFLOW.md` "Target planning model" updated.
- Status (original): **OPEN — found 2026-06-24 (code review of the N49 series).** Flagged as an ASSUMPTION in code;
  needs owner confirmation.
- Severity: **LOW** (placement is advisory/read-only; mis-dating only affects the forecast).
- Problem: `working_days_from` skips Sat/Sun via the hardcoded `DEFAULT_WEEKEND_WEEKDAYS = {5, 6}`
  (`app/manager/placement.py:43,105`) — no holidays, no shop-specific schedule — and always starts the
  calendar at `datetime.now(UTC).date()` with a *full* day-0 capacity (`app/manager/service.py:1152`), so
  a plan computed at 16:00 still assumes a whole long-day's net ceiling remains today. Both inflate
  near-term feasibility.
- Required fix (decide with owner): confirm the real working calendar (weekend days + holidays) and
  whether day 0 should be pro-rated by the remaining shift hours (or simply start the horizon at the next
  full working day). Make the weekend set configurable rather than a module constant.
- Acceptance: the calendar matches the shop's real working days; day-0 capacity reflects the time left in
  the shift (or starts next day); covered by a test.

### NA57. Multi-day plan applies one advised shift length uniformly to every day
- **Owner decision (2026-06-24): judge each day against its own sensible shift (option (a)).** The reality
  — not enough m² to fill every day above the floor — isn't hidden; the fix only stops measuring an
  under-filled day against the *wrong* bar (the long-day 800 floor) when it's plainly a short day.
- Status: **DONE (2026-06-24).** `place_orders` (`app/manager/placement.py`) now derives each **later**
  day's display shift/floor/ceiling from that day's own placed m² via `display_shift_for`: a later day is
  SHORT (floor 500) when its m² fit a short day's net ceiling (≈640) **and** are below the long floor —
  else LONG (floor 800). The **fill** still uses the plan-level full-day ceiling to decide day boundaries
  (unchanged membership); only the per-day *label + floor + ceiling* change. Day 0 keeps its NA56 hours
  proration. Because SHORT is assigned only when the work fits, a day is **never** flagged `over_ceiling`
  against a ceiling smaller than what was packed — the contradiction the naive "advise per day" fix would
  cause. Result: a 550 m² overflow day reads as a fine short day (not below floor), a 200 m² day is SHORT
  + below the *short* floor (500, not 800), and a 700 m² day stays LONG + correctly below the long floor.
  Frontend needs no change (the board already renders per-day `shift_length` → "krót."/"dług."). Tests:
  pure placement (short-not-below / tiny-short-below / long-under-target, each asserting no `over_ceiling`)
  + service read-model case; two NA56 tests updated (a 400 m² later day is now correctly SHORT, so they use
  a 700 m² day-1 to keep asserting a LONG later day). 593 backend + 93 frontend pass; both builds green;
  `alembic check` clean (no schema change). `docs/WORKFLOW.md` "Target planning model" updated.
  - **Deferred follow-up (option (b)):** a *tiny* overflow day could carry **no** floor flag at all
    ("not a working day you'd open"), rather than being below the short floor — only if the small-day flag
    proves bothersome on the real board (it adds a "not a real working day" state across the board + good-day
    stats; out of scope for this LOW item).
- Status (original): **OPEN — found 2026-06-24 (code review of the N49 series).**
- Severity: **LOW** (cosmetic/labelling; interacts with the below-floor flag).
- Problem: `get_multi_day_plan` advises the shift length once from the *total* available m²
  (`advise_shift_length(available_m2)`, `app/manager/service.py:1140`) and `place_orders` stamps that one
  `shift_length` onto every placed day (`app/manager/placement.py:150,183-195`). With e.g. 900 m² total,
  every day is labelled LONG (and carries the 800 m² floor) even though only day 0 holds real work — so
  near-empty later days are flagged `below_floor` against a floor they were never meant to clear.
- Required fix: advise the shift length **per day** from that day's placed m² (a near-empty day is a short
  day, or simply not a working day), so the floor flag is meaningful per day.
- Acceptance: each planned day's shift length + floor reflect that day's own load; later near-empty days
  aren't spuriously flagged below the long-day floor; covered by a test.

## System-wide ordering / scheduling model (owner design session 2026-06-23)

### NA49. Multi-day capacity planner ("schedule the painting bottleneck, derive the rest")
- Status: **OPEN — refined & re-scoped 2026-06-23** in a clean-slate process session with the owner +
  a process-knowledgeable colleague. The **NA33 painting auto-scheduler is DONE** (the within-day
  ordering core). What is open is the **bulk of the real planner** below: the session re-grounded the
  system's core job as *hit the daily m² floor + keep the automatic booth fed + offload the manager* — a
  **multi-day capacity planner**, not a queue-orderer. Authoritative model now in `docs/WORKFLOW.md`
  ("Target planning model") + `docs/FACTORY_DOMAIN_MODEL.md` §7. The original 2026-06-23 framing, the
  confirmed shared-stage defect, and sub-items A–M remain **below as detail/history** (several are now
  superseded or dropped — see the closing notes).
- Severity: **MEDIUM–HIGH** (this is the core value of the system, not a side feature).

#### Refined build plan (dependency-ordered — supersedes the framing further below)

**Foundation (do first):**
- **N49-1 — Make `planned_pickup_date` a hard, required deadline. DONE (2026-06-24).** The pickup deadline
  is now **required at intake and NOT NULL** in the schema/DB, so the planner can rely on every active order
  carrying one. Changes: `WorkOrderCreate.planned_pickup_date` is now `date` (required, no default,
  `app/work_orders/schemas.py`); the model column is `nullable=False` (`app/work_orders/models.py`);
  migration `20260624_0039` backfills legacy NULLs → `received_date` then sets NOT NULL (batch rebuild,
  `alembic check` clean). Frontend: the "Termin odbioru *" field is JS-validated as required (no native
  `required` attr — matches the other fields) and always submitted (`CreateWorkOrderPage.tsx`); the
  `CreateWorkOrderRequest` type now requires it. Docs: `docs/WORKFLOW.md` "Work Order Intake Fields".
  Tests: new `test_creating_without_planned_pickup_date_fails_N49_1` (422); ~16 backend create-helpers +
  raw-insert constraint helpers + 3 frontend form-submit tests updated to supply a pickup date; the NA44
  overdue test dropped its now-unconstructible `no_date` case. **474 backend + 89 frontend tests pass;
  alembic check clean; frontend build green.** The "hard feasibility constraint in the planner" half lands
  with the planner itself (N49-3/N49-4) — this item delivered the data-foundation guarantee.
  - Original framing — It IS the hard "Termin odbioru" (always set at intake — owner confirmed), but the
    schema allowed NULL and the scheduler treated it as a soft sort key. **Verified 2026-06-23:**
    `WorkOrderCreate` had `planned_pickup_date: date | None = None` (optional), while `total_area_m2`
    (`Field(gt=0)`) and `ral_code` were already required — so only the deadline wasn't. Acceptance: intake
    requires a pickup date; the planner can rely on every active order having one.
- **N49-2 — Measurement engine ("learn the numbers"). DONE (2026-06-24).** A read-only engine derives
  the planner's two real numbers from the existing `StageTransitionEvent` log — **no booth tap**. The
  pure, DB-free core `app/manager/measurement.py` (mirrors `scheduler.py`) takes per-order
  `AutomaticPassObservation`s (HANGING `IN_PROGRESS` start → PACKING `DONE`, which bracket the whole
  automatic pass) and computes: (1) **effective m²/h** = total observed m² ÷ the **union** of the
  bracketed intervals (overlaps counted once, overnight idle gaps fall out automatically → the
  *effective* line rate the day-capacity model multiplies by shift length, ≈ floor ÷ shift, not the
  60–100 instantaneous ceiling); (2) a **statistical colour-changeover cost** = avg inter-start gap when
  the colour changed − when it stayed the same (clamped ≥ 0). Both **seed** when sparse: rate seed
  `57.0` m²/h (≈ 800 m² / 14 h), changeover seed `20.0` min (midpoint of the confirmed 15/30-min bands,
  which are exposed as structural `band_*` reference fields for the later N49-6 size-aware cost). Wired
  as `ManagerService.get_line_measurements(date_from, date_to, production_type)` +
  `GET /manager/stats/line-measurements` (manager-gated), defaulting to AUTOMATIC; MANUAL has no HANGING
  stage so it yields no brackets and always reports the seed (the unmeasured overflow valve — exactly
  right). Schemas `LineRateMeasurement` / `ColourChangeoverMeasurement` / `LineMeasurementStats` flag
  measured-vs-seed (`is_measured`) so the planner/UI know the confidence; figures refine as passes
  accrue. Tests: `tests/test_measurement.py` (9 pure: union vs sum, idle-gap exclusion, seed fallback,
  bad-bracket/no-area skip, changeover residual + clamp) + `tests/test_line_measurements.py` (5
  service/DB: rate from logged brackets, manual seed-only, changeover residual, manager gating). No
  schema change (read-only over existing tables); `alembic check` stays clean. The two
  hard-feasibility/capacity *consumers* land with the planner (N49-3/N49-4/N49-6); this delivered the
  measurement foundation. Acceptance met: per-line rate + changeover estimate computed from the log,
  refining over time.
  - Original framing — Derive real automatic **m²/h** and a **statistical colour-changeover cost** from
    `StageTransitionEvent` (HANGING-start → PACKING-done brackets the automatic pass — **no booth tap**,
    owner: "na kabinie nie tapnie"). Seed ~55–60 m²/h. Manual line stays unmeasured (overflow valve).
    Acceptance: per-line rate + changeover estimate computed from the log and refining over time.

**Core planner (the heart — depends on the foundation):**
- **N49-3 — Day capacity model: floor + ceiling. DONE (2026-06-24).** A DB-free model
  `app/manager/capacity.py` (mirrors `scheduler.py` / `measurement.py`) treats one working day as a
  bucket: a **floor** (800 long / 500 short m² — fixed economic constants, `FLOOR_LONG_M2`/`FLOOR_SHORT_M2`)
  and a **ceiling** = a **gross** booth rate (`CEILING_BOOTH_RATE_M2_PER_H = 80`, midpoint of the confirmed
  60–100 band — deliberately distinct from N49-2's *effective* ~57, which already folds idle/changeover in)
  × shift hours (14 long / 8 short). A **colour change consumes capacity**: `changeover_count ×
  changeover_minutes` of booth time → m² of ceiling lost → a *net* ceiling, so "fill vs ceiling" already
  accounts for the day's changes. `advise_shift_length(available_m2)` advises long iff ≥ the long-day floor.
  Wired as `ManagerService.get_day_capacity(production_type, shift_length=None)` +
  `GET /manager/planner/day-capacity` (manager-gated): buckets a line's active planned orders (queue order),
  counts colour changeovers via `scheduler.colour_changeovers_for_order_ids`, pulls the per-change cost from
  the N49-2 learned estimate over a 90-day trailing window (extracted `_automatic_pass_observations` helper,
  shared with `get_line_measurements`), and returns `DayCapacityRead` flagging `below_floor` + `over_ceiling`
  (spill). Shift length is **advised** from the available ready m² when the caller omits it (`shift_advised`).
  Tests: `tests/test_capacity.py` (8 pure: floor/ceiling per shift, changeover loss, spill, clamps, advice,
  seed) + `tests/test_day_capacity_service.py` (6 service/DB: empty→short, ≥floor→long, changeover count,
  forced shift, per-line buckets, manager gating). No schema change (read-only); `alembic check` clean.
  `docs/WORKFLOW.md` "Target planning model" updated. The deadline-feasible **placement** that consumes this
  bucket is N49-4. Acceptance met: a day shows fill vs floor/ceiling; below-floor + over-ceiling flagged.
- **N49-4 — Deadline-feasible multi-day placement. DONE (2026-06-24).** A DB-free model
  `app/manager/placement.py` (mirrors `scheduler.py` / `capacity.py` / `measurement.py`) lays a line's
  active planned orders across a working-day calendar **earliest-deadline-first** into day buckets bounded
  by each day's **net** ceiling (gross booth capacity minus the m² lost to that day's colour changes —
  `changeover_loss_m2` was extracted from `capacity.py` and is now shared, so the single-day and multi-day
  models never drift). Packing against the *net* ceiling keeps the deadline promise conservative; an order
  larger than a whole day is still placed alone and flagged `over_ceiling` (a real signal, not an error).
  Per order it returns whether the day it lands on still meets the hard pickup deadline (required since
  N49-1) plus `days_late`, and the **"won't make it" set** `infeasible_order_ids` (scheduled past the
  deadline *or* beyond the horizon). Within a day the EDF order is kept — the light→dark colour sweep and
  line assignment are N49-5/N49-8 by design. The working-day calendar `working_days_from` skips Sat/Sun
  (**Mon–Fri ASSUMPTION, revisit with owner**). Wired as
  `ManagerService.get_multi_day_plan(production_type, horizon_working_days=10, shift_length=None)` +
  `GET /manager/planner/multi-day` (manager-gated); shift length is advised from the available ready work
  when omitted; the learned changeover cost (N49-2, 90-day window) feeds each day's net ceiling (the
  trailing-window estimate was extracted into a shared `_learned_changeover` helper used by both
  planner endpoints). No schema change (read-only over existing tables); `alembic check` clean. Tests:
  `tests/test_placement.py` (10 pure: net-ceiling fill, EDF order, overflow split, missed-deadline +
  beyond-horizon infeasibility, colour-change capacity loss, oversized order, weekend calendar) +
  `tests/test_multi_day_plan_service.py` (6 service/DB: empty→short, ≥floor→long one-day, overflow→two
  days, past-deadline infeasible, manager gating). `docs/WORKFLOW.md` "Target planning model" updated.
  Acceptance met: orders land on days respecting deadlines; infeasible deadlines warn. The remaining
  objective levels (N49-5 light→dark within-day, N49-6 size-aware changeover cost, N49-8 line assignment)
  refine the *within-day* and *cost* model on top of this placement.
  - Original framing — Place orders across day-buckets in deadline order so no hard pickup date is missed;
    surface a "won't make it" warning. Objective hierarchy: **deadline > floor > grouping.** Acceptance:
    orders land on days respecting deadlines; infeasible deadlines warn.
- **N49-5 — Light→dark colour ordering. DONE (2026-06-24).** A DB-free `app/manager/colour.py` reorders
  each placed day into a **light → dark colour sweep**: `light_to_dark_order` groups identical colours
  (zero-changeover runs) then sweeps the remaining changes lightest → darkest by a shared, documented
  `ral_lightness` helper (RAL-code group/anchor map — white 9010/9016 = 1.0 lightest, black 9005 = 0.0
  darkest, greys in between; the single point to revisit the open colour-family question, flagged in the
  module + `FACTORY_DOMAIN_MODEL.md` §7). The EDF day-to-day placement (N49-4) is unchanged; the sweep is
  **within** each day only. Wired into `ManagerService.get_multi_day_plan` (per-order `sequence_position`)
  and `get_day_capacity` (the day's changeover count/cost now reflect the grouped sweep, not raw queue
  order). **Supersedes NA49.H** + the exact-identity COLOUR rule. Tests: `tests/test_colour.py` (lightness
  ordering, grouping, no-colour-last, empty) + `tests/test_within_day_plan_service.py` (white→grey→black
  sweep, grouping drops the changeover count) + updated `test_day_capacity_service.py` (interleaved A,B,A
  groups to 1 change). No schema change; `alembic check` clean. Acceptance met: within-day order is a
  light→dark sweep; the grouped sweep cuts the estimated changeover vs the raw queue order.
- **N49-6 — 100 m² changeover-cost model. DONE (2026-06-24).** `app/manager/capacity.py`
  `changeover_minutes_for_transition` costs a colour change by the **next order's size vs the 100 m²
  odzysk threshold** (≤ 100 → 15 min "bez odzysku"; > 100 → 30 min "z odzysku") **and colour direction**
  (light → dark = a fraction of the band; dark → light = the full band — the residue-shows reset). It
  reuses the confirmed `band_*` structural figures (one source with `measurement.py`).
  `app/manager/colour.py::sequence_changeover_minutes` / `average_changeover_minutes` walk a day's swept
  sequence (same-colour adjacency = 0) into a per-day total + per-change average; the average feeds
  `compute_day_capacity`'s `changeover_minutes`, so the **same shared `changeover_loss_m2`** turns it into
  m² of ceiling lost for both single-day and multi-day (no drift). `get_multi_day_plan` surfaces the
  per-day size+direction `changeover_minutes`. Tests: `tests/test_colour.py` + `tests/test_capacity.py`
  (size band, light→dark < dark→light, missing-size = large band) + service assertions. No schema change;
  `alembic check` clean. Acceptance met: changeover cost reflects size + direction, not a flat count.
- **N49-7 — Paint-stock HARD block. DONE (2026-06-24).** Pure DB-free core
  `app/manager/paint_feasibility.py` (`build_forward_view` / `colour_series_blocked`) decides per planned
  order, in execution order: **BLOCKED** = a *metered* colour (not also on the manual line) that is
  *known-depleted* (a paint with real stock-movement history at ≤ 0 kg); **WARNING** = runs short partway
  down the sequence, or a manual-used low-confidence balance; **OK** otherwise. `assign_plan` calls a
  focused gate (`_assert_paint_available_for_automatic`) that **refuses to plan an out-of-stock metered
  colour on the AUTOMATIC line** with a "deliver or recount at the booth" error. The block is deliberately
  narrow to avoid breaking real planning: a never-stocked new colour is the 0-kg placeholder row that work
  order creation auto-snapshots, so it has **no movement history** → not blocked (the new
  `PaintRepository.has_stock_movements` / `PaintService.has_stock_history` distinguishes known-depleted
  from never-stocked); a manual-used colour is **warned, never blocked** (manual consumption is unmetered,
  owner "niewykrywalne"). Forward view `GET /manager/planner/paint-forward` (manager-gated) gives the
  "suffices / runs out at order X" walk; the same `paint_status` + `paint_remaining_kg` ride on each
  `multi-day` placement, so an order planned while in stock surfaces BLOCKED once its colour later depletes.
  No schema change (read-only over the existing balance + ledger); `alembic check` clean. Tests:
  `tests/test_paint_feasibility.py` (8 pure: OK/WARNING/BLOCKED, partial shortfall runs-out point,
  untracked no-claim, manual-used warn, two-series independence, predicate truth table) +
  `tests/test_paint_forward_service.py` (7 service/DB: hard block at plan time, in-stock allowed, untracked
  allowed, manual-used warns-not-blocks, forward runs-out, deplete-after-planning → BLOCKED in multi-day,
  manager gating). `docs/WORKFLOW.md` "Target planning model" updated. 567 backend tests pass.
  Follow-up (not built, out of scope): gating `update_production_type` (manual→automatic) on the same rule;
  a stock-recount prompt at the booth.
  - Original framing — A colour series whose paint is not in stock **cannot be planned** (hard block,
  not just a warning); show a forward "paint suffices / runs out at order X" view. Acceptance: the planner
  refuses an out-of-stock colour series; forward paint view available.
  - **Verified 2026-06-23 (data foundation is sound, accuracy is the risk):** `Paint.current_quantity_kg`
    is a live balance with a `>= 0` CHECK (`app/paints/models.py:22`) backed by an append-only ledger
    `PaintStockMovement` (resulting qty `>= 0`); per-order predicted demand exists
    (`calculate_predicted_paint_quantity_kg`, m²/4 or /6 by the 100 m² threshold). So the planner has both
    a stock number and a demand number. **But the number drifts from reality:** only
    `record_automatic_consumption` (`app/paints/service.py:130`) deducts stock — **manual-line consumption
    is not metered** (owner: "niewykrywalne"), so any colour also used on manual reads high; and the balance
    is only as good as disciplined entry (exactly the "myśleli że jest a jej nie ma" failure). **Design
    refinement:** hard-block on the **automatic** planned series (metered, trustworthy); pair with a quick
    **stock recount at the booth**; treat colours heavily used on manual as lower-confidence (warn, don't
    hard-block). Do not hard-block purely on a possibly-stale balance.
- **N49-8 — Line-assignment lever. DONE (2026-06-24).** `app/manager/colour.py::suggest_line` proposes a
  line per order: a **small-m² colour-orphan** (no same-colour neighbour to group with, ≤ the 100 m²
  threshold) → **manual**; everything else → **automatic** (join a colour run / keep the booth fed). A
  missing m² is treated as not-small (safe automatic default). `get_multi_day_plan` decides orphan-ness
  across the whole line's planned set (`colour_neighbour_counts`) and returns
  `suggested_production_type` + the reason flags (`suggested_line_is_colour_orphan` /
  `suggested_line_is_small`) per order — a **suggestion only**; the manager still assigns/overrides the
  line through the existing planning endpoints. Tests: `tests/test_colour.py` (the four rule branches) +
  `tests/test_within_day_plan_service.py` (small orphan → manual, grouped/large → automatic). No schema
  change; `alembic check` clean. Acceptance met: planner proposes a line per order by the rule; manager
  can override.

**UI:**
- **N49-9 — Multi-day capacity board. DONE (2026-06-24, read-only first cut).** `frontend/src/components/
  CapacityBoard.tsx` renders `GET /manager/planner/multi-day` for the AUTOMATIC line on the manager panel:
  a horizontally-scrolling column per working day, each filling toward its floor/net-ceiling (a fill bar
  with the floor marked, green/amber/red by below-floor/over-ceiling), orders listed in the backend's
  light→dark sweep order with the derived flags surfaced — per-day **poniżej progu / ponad limit** + the
  changeover count, per-order **po terminie (+N dn.)** and the N49-7 **brak farby / farba na wyczerpaniu**
  paint markers — plus a banner for the "won't make it" `infeasible_order_ids` set. The board only
  **renders** what the planner derives (no local recompute of capacity/deadline/paint). Frontend-only:
  new `MultiDayPlan` types + `fetchMultiDayPlan` client + mount in `ManagerPanelPage`. Tests:
  `frontend/tests/capacityBoard.test.tsx` (renders the column + below-floor / at-risk / paint-blocked /
  infeasible flags) + the manager-tab mock updated. 91 frontend tests pass; build green. `docs/WORKFLOW.md`
  "Target planning model" updated.
  - **Deferred (NA49.K):** drag-between-days + pin/urgent — they need a backend mutate + schema (a pinned/
    urgent flag the re-optimise respects), so the first cut is the read-only board; the lever lands when the
    persistence is added.
  - Original framing — Rolling ~week board; each day a column filling toward floor/ceiling, segments
    coloured light→dark, below-floor + at-risk-deadline flags, drag between days, **pin/urgent** (delivers
    the deferred **NA49.K**). Becomes the manager's planning surface.

**Shared-stage derivation (the original NA49 defect):**
- **N49-10 — Derive shared-stage order; kill duplicate "Poz." DONE (2026-06-24).** Backend owns the
  shared-stage order: new pure `app/process/shared_stage.py` (surface-prep interleave by the
  smaller-buffer rule — feed the line closest to starving its booth, tie → automatic, buffer in pieces)
  wired into `ProcessService.list_stage_work_orders`; packing ordered by physical readiness + the slot
  model (no position numbering). Read model gains `shared_stage_line_label` + `is_next_at_shared_stage`;
  `StageWorkOrdersPage`/`PackingWorkOrdersPage` render the line label + "NASTĘPNE" instead of the
  colliding `Poz.`. No schema change. Tests: `tests/test_shared_stage.py` (6),
  `tests/test_shared_stage_derivation_service.py` (4), updated `test_process_api` ordering, + a frontend
  no-duplicate-Poz case. Integrated to main via cherry-pick `0e17d41` (built in parallel with N49-5/6/8;
  one doc conflict reconciled). Assumptions flagged: buffer-in-pieces, live re-order, przemalowanka
  (NA49.D) not yet counted; the manager's exceptional packing bump not implemented (out of scope).
  - Original framing — Surface-prep order derived from the
  painting plan (one line-labelled list + "NASTĘPNE"); packing order derived from physical readiness +
  the slot model. Shared stages stop using the per-line `queue_position` as a global rank. Fixes
  `app/process/repository.py:58`, `frontend/src/components/StageWorkOrdersPage.tsx`,
  `frontend/src/components/PackingWorkOrdersPage.tsx`. Acceptance: no ambiguous duplicate "Poz."; shared
  stages show a line label + a meaningful derived order.

**Rollout:** ship behind the **3-phase trust model** (observer → suggester → trusted); NA33 is the
reusable within-day ordering core.

**Dropped / simplified after the session (do NOT build):**
- **NA49.B (decoral as a second bottleneck) — DROPPED.** Decoral coat is aesthetic, foil change costs no
  time, no clogging (owner + colleague). Decoral is a trailing appended stage; the scheduler ignores it.
- **NA49.D / NA49.M (prep buffer balancing) — SIMPLIFIED OUT.** Prep usually keeps up and buffer size is
  unimportant; prep is a plain plan-driven feeder (N49-10), not a buffer optimiser.
- **NA49.F / NA49.G (shared packing under load / manual auto-scheduler) — keep LOW/deferred.** Packing is
  "git" as-is; manual stays a fuzzy overflow valve.

**Open questions (mostly answered 2026-06-23; remaining gate full optimisation, not the foundation):**
- **Deadline horizon — ANSWERED:** "definitely not for tomorrow" → comfortable, so the planner has real
  freedom to reorder for colour grouping; tight deadlines are the exception. (Exact typical slack still
  worth confirming.)
- **Changeover — ANSWERED:** the **15/30-min bands are confirmed**; the *frequency* of colour changes is
  day-mix-dependent (not a fixed number) and is learned from production data.
- **Colour-similarity — STILL OPEN:** RAL-lightness light→dark is the working model (white→grey example);
  owner couldn't confirm whether colour "families" override it — confirm with the colleague.
- **Przemalowanka skips surface prep — reason unknown** ("bo tak"); parked, low priority.

---

_Original 2026-06-23 design + confirmed defect + sub-items A–M (history/detail; read in light of the
refined plan above):_

**Confirmed defect (verified live 2026-06-23 by two sub-agents driving a seeded app):**
The per-line queue split (`queue_position` unique only within `production_type`) is correct for planning
the two parallel lines, but the two **shared** stages — `SURFACE_PREPARATION` (entry) and `PACKING`
(drain) — still list both lines merged and ordered by `queue_position ASC, id ASC` with **no
`production_type` filter**:
- `app/process/repository.py:58` — merged ordering by `(queue_position, id)`.
- `frontend/src/components/StageWorkOrdersPage.tsx:173` (surface-prep fetch, no `production_type`) and
  `:487` (renders `Poz. {queue_position}`).
- `frontend/src/components/PackingWorkOrdersPage.tsx:227` (packing fetch, no `production_type`) and
  `:541` (renders `Poz.`).
Result: two physically different orders (one MANUAL, one AUTOMATIC) both show "Poz. 1" / "Poz. 2"; the
cross-line interleave is decided by `id ASC` (insertion order) — no deliberate factory priority. At
realistic scale nearly the whole shared-stage list shows duplicate position labels.

**Confirmed NOT a defect (verified live 2026-06-23):** cross-line reassignment
(`ManagerService.update_production_type`) is coherent across scenarios A–D — including reassigning
**after** `SURFACE_PREPARATION` is DONE (counted quantity + route preserved; `HANGING` added/removed
correctly), the production-started block (`409`, not `500`), and the NA48 completed-order trailing. No
change needed there.

**Physical grounding (owner-confirmed 2026-06-23 — see `docs/FACTORY_DOMAIN_MODEL.md` §1–§2):**
- Exactly ONE manual painting station and ONE automatic spray booth → exactly two parallel painting
  resources (one each); "two lists" is the right cardinality.
- The automatic line carries the large majority of throughput, cost, and profit; colour-changeover cost
  is highest on the automatic booth → automatic is the primary resource to optimise.
- Surface preparation always ran in the manager's planned order (plan-driven feeder) and stays ahead of
  painting (not a bottleneck).
- Historically the manager kept an Excel of all orders, hand-sequenced + line-assigned, printed and
  posted; reordering meant reprint + walk. Goal: the system auto-arranges well but preserves the
  manager's expert override, and ordering changes are instant/live (no print).

**Target model — "schedule the painting bottleneck, derive the rest":**
The only stage the manager schedules is PAINTING (two sequences, one per physical resource). Every other
stage's order is derived.
- **Painting:** two ordered sequences (Automat / Ręczna). The auto-scheduler (NA33) proposes the order,
  optimising the **AUTOMATIC** line first by colour grouping → deadline → changeover, with a
  **configurable rule priority**. The manager overrides by drag / pin / "urgent"; re-running "Ułóż"
  re-optimises *around* pinned items. Live on screens — replaces the printed sheet.
- **Surface preparation (feeder):** ONE shared prep station feeds the TWO parallel booths, so prep is a
  **single interleaved sequence** across both lines — two per-line lists do NOT answer "what's next"
  (owner caught this 2026-06-23). The cross-line order is **derived by buffer** (owner decision
  2026-06-23): prep next the line with the **smaller prepared-but-not-yet-painted buffer** (closest to
  starving its booth); tie → automatic. Within a line, the candidate is the next un-prepped order in that
  line's painting plan. Display = one list, each row line-labelled, top = do next (a "NASTĘPNE" marker).
  Assumptions taken (revisit): buffer measured in **pieces** (not m²); the list may re-order live as
  painting consumes. ⚠️ Does NOT yet account for przemalowanka (skips prep but still loads the booth) —
  see sub-item below.
- **Packing (drain):** order **derived from physical readiness** + the existing packing-slot model
  (automatic reserves packing at hanging start; manual may exceptionally open a second slot with the
  "X pieces incoming from automatic" warning). No manual position numbering; the manager may
  exceptionally bump one order.
- **Decoral:** derived/arrival from base-coat packing, optionally grouped by foil.

**Acceptance:**
- No ambiguous duplicate "Poz." at shared stages; shared stages show a line label + a meaningful
  (derived) order.
- The manager schedules only the two painting sequences; surface-prep + packing order is system-derived.
- Auto-suggest + manual override (drag / pin / urgent) on the painting plan; re-optimise respects pins.
- Covered by tests; `docs/WORKFLOW.md` (scheduling/queue semantics) and `docs/FACTORY_DOMAIN_MODEL.md`
  (physical grounding) updated when built.
- NA33 is folded in as the painting-plan auto-scheduler sub-part (do not build it as a separate model).

**Sub-items discovered in the 2026-06-23 logic review (gaps + convenience shortcuts).** Recorded so
nothing is lost; severities are first-pass. The two headline gaps are NA49.A (time/capacity) and NA49.B
(decoral as a second bottleneck).

*Not addressed at all (gaps):*
- **NA49.A — No notion of time / daily capacity (biggest gap).** What we built orders the queue; it is
  **not** a capacity planner. We do not model per-order paint duration, daily m² capacity, working
  hours, or day boundaries. Consequence: we cannot answer "will this make its deadline?", "is the day
  full?", or honour the owner's original "don't drop below a daily m² floor" intent. Deadline is only a
  sort key, never checked against capacity. Severity: **MEDIUM–HIGH** (it is the core of real planning).
  Acceptance (when built): per-order time/throughput estimate + daily capacity, a "won't make deadline"
  warning, and a day-fill view; decide unit (m²/day) with the owner.
- **NA49.B — Decoral is a second bottleneck, ignored by the scheduler.** The decoral coat station has its
  own changeover cost (**foil changes**, `WorkOrder.decoral_foil_id` from NA38) and its own packing.
  Optimising only the base-coat automatic booth can just **push the bottleneck** to decoral. Severity:
  **MEDIUM**. Acceptance: decoral sequence considered (group/limit foil changes), or an explicit decision
  that decoral is not a constraint, with evidence.
- **NA49.C — Scheduler ignores paint stock.** Colour grouping can propose a large run of a colour that is
  **not in stock** (shortage warnings exist elsewhere but don't influence ordering). Severity: LOW–MEDIUM.
  Acceptance: the proposal accounts for / flags paint availability for the colour it front-loads.
- **NA49.D — Przemalowanka bypasses surface prep but still loads the booth.** The prep buffer rule (above)
  won't "see" przemalowanka demand, so a line's booth load is under-counted. Severity: LOW. Acceptance:
  the buffer/feed logic accounts for booth demand that skips prep.
- **NA49.E — Where do returning corrections land in the auto-arranged plan?** A RAL correction resets to
  planning; interplay with colour grouping/append is unspecified (does it rejoin its colour group?).
  Severity: LOW. Acceptance: defined + tested placement of a returned correction in the scheduled line.
- **NA49.F — Shared packing under simultaneous two-line load.** Both booths drain into one packing; the
  slot model covers automatic reservation, but the manual+automatic interleave at packing under load is
  not dialled in. Severity: LOW–MEDIUM (part of the packing-derivation build).
- **NA49.G — Manual line has no auto-scheduler** (deliberately deferred). The hand painter also has
  colour-changeover cost; the same mechanism should extend to MANUAL. Severity: LOW.

*Done sub-optimally for speed (revisit when it matters):*
- **NA49.H — "Maks. przerób" is a crude proxy, not real changeover optimisation.** "Largest colour run
  first" (key `-group_m2`) does not minimise actual transition cost (e.g. light→dark sequencing, true
  changeover count) and is near-inert at the default priority. A real optimiser would sequence colour
  groups to minimise total changeover.
- **NA49.I — Lexicographic independent sort keys, not multi-objective.** `colour` and `changeover` both
  key on colour, so the configurable priority is partly illusory; chosen for a clean sort + simple UI.
- **NA49.J — Suggestion banner counts only colour changeovers**, not deadline/m²-day improvement.
- **NA49.K — Pin / urgent. DONE (2026-06-24, pin+urgent; drag-between-days still deferred).** Owner
  decisions: pin = **lock to the queue slot** (optimiser arranges others around it); build **pin + urgent**
  now. A persisted `WorkOrder.planning_priority` (`PlanningPriority` enum PINNED/URGENT, nullable, partial
  CHECK `planning_priority_requires_planned`, migration `20260624_0040`) the painting auto-scheduler
  respects: pure `scheduler.arrange_with_locks` re-arranges the `propose_sequence` order so URGENT leads
  (optimiser order among urgents), PINNED holds its index among the non-urgent current queue, and the rest
  fill the remaining slots in optimiser order — so re-running "Ułóż" no longer overwrites the manager's
  tweaks. Mutate `PATCH /manager/work-orders/{id}/planning-priority` (`ManagerService.set_planning_priority`,
  manager-gated, audited, planned+active only); the lock is **cleared automatically** on leaving the queue
  (`_reset_to_correction_planning`) and on a line move (`update_production_type`). Surfaced on `WorkOrderRead`
  + `OrderPlacementRead`; manager queue cards get "Przypnij"/"Pilne" toggles + a badge, the capacity board
  shows a przypięte/pilne badge. Tests: pure `arrange_with_locks` (5 in `test_scheduler.py`), service
  `test_planning_priority_na49k.py` (6: pin keeps slot, urgent to front, set/clear+audit, requires planned,
  manager gating, line-move clears), frontend pin/unpin toggle case. Full backend + frontend suites green;
  `alembic check` clean. `docs/WORKFLOW.md` "Planning locks" added. **Still deferred:** drag-between-days on
  the board (needs a board-level cross-day mutate) — the only remaining piece of the old NA49.K.
- **NA49.L — Prep order reuses the painting plan's `queue_position`** rather than its own model, so prep
  cannot deliberately diverge from the painting plan (e.g. prep a different order first because paint
  isn't ready) — couples to NA49.C/D.
- **NA49.M — Buffer measured in pieces, not m²** (m² would track booth consumption more faithfully since
  automatic eats m² faster); config stored as a JSON blob with no per-rule parameters.

## New owner requests (2026-06-19) — scoped from owner chat

Source: owner chat 2026-06-19 (screenshot) + clarification Q&A same day. Core decisions captured below;
remaining open questions are flagged per item. Each needs a `docs/WORKFLOW.md` update if it changes
workflow meaning. Severities are first-pass estimates.

### NA33. Configurable auto work-scheduling + colour grouping + (basic) statistics tidy
- Status: **DONE — painting auto-scheduler shipped (2026-06-23).** Owner decisions captured this session:
  AUTOMATIC line only (v1), configurable rule priority from v1, "minimalny przerób" = maximise m²/day, and
  a propose-don't-auto-apply model with a non-nagging suggestion banner. Built:
  - **Pure scheduler core** `app/manager/scheduler.py` (`propose_sequence` = lexicographic sort over the
    enabled rules in priority order + `count_colour_changeovers`) and the rule catalog
    `app/manager/enums.py` (`ScheduleRuleKey` COLOUR/DEADLINE/CHANGEOVER, default order colour→deadline→
    changeover, Polish labels/descriptions). Fully unit-tested (`tests/test_scheduler.py`).
  - **Per-line config** `auto_schedule_configs` table (`app/manager/models.py`, migration
    `20260623_0038`) storing the manager's ordered/toggled rule list as JSON; absence = default.
  - **Service + API** `ManagerService.get_schedule_config` / `update_schedule_config` /
    `propose_auto_schedule` (manager-gated, audit event on config change); router
    `GET/PUT /manager/scheduler/config`, `GET /manager/scheduler/proposal`. Apply reuses the existing
    `POST /manager/queue/reorder` (no new mutate path; same stale-revision protection).
  - **Frontend** (`ManagerPanelPage`, AUTOMATIC plan only): "Ułóż automatycznie" previews the proposal as
    an editable draft (commit via the normal Save), a configurable "Reguły układania" panel (reorder +
    enable/disable), and a "Lepsze ułożenie dostępne (−N zmian koloru)" banner shown only when it would
    cut changeovers. New orders still append to the end (nothing reshuffles on arrival).
  - Tests: `tests/test_scheduler.py` (7) + `tests/test_auto_scheduler_service.py` (config CRUD, validation,
    proposal reduction, manager gating, off-line exclusion) + a frontend case in `uiStateConsistency.test.tsx`
    (banner → preview → reorder payload colour-grouped). Full backend + frontend suites green; `alembic
    check` clean; both builds green. Docs: `docs/WORKFLOW.md` "Painting auto-scheduler" section.
  - **Deferred (not built, by design):** the statistics-tidy sub-part stays blocked on the colleague's
    wishlist; MANUAL-line auto-scheduling reuses the same mechanism when wanted; surface-prep/packing
    *derived* order is the remaining NA49 work (shared-stage display defect — see NA49).
- **Now scoped under NA49** (the system-wide ordering model agreed 2026-06-23): this is the
  *painting-plan auto-scheduler* sub-part. Build it as the "Painting" piece of NA49 (optimise the
  automatic line first; surface-prep + packing order are derived, not separately scheduled).
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
- Status: **DONE (2026-06-23).** Owner decisions: file types = **PDF + images (PNG/JPG)**; viewing surface =
  **station cards + detail page**; visibility = **all stations** (upload/delete stays office-only). Built on
  the existing `WorkOrderAttachment` mechanism. New structured discriminator `WorkOrderAttachmentCategory`
  (`app/work_orders/enums.py`: `DOCUMENT` default / `TECHNICAL_DRAWING`) stored as a plain `category` string
  column (validated at the app layer, beside the legacy free-text `attachment_type`); migration
  `20260623_0037` backfills existing rows to DOCUMENT. `upload_attachment` now accepts `category` and any of
  PDF/PNG/JPEG — per-type magic-byte validation (`%PDF-`, PNG signature, JPEG `\xff\xd8\xff`) + stored
  extension by type (`415` wrong type, `400` bad signature, `413` too large, `422` bad category). The station
  read model gains `technical_drawings: list[WorkOrderAttachmentSummaryRead]` (only `TECHNICAL_DRAWING`
  attachments), surfaced on all four production station cards via a shared `TechnicalDrawingLinks` component
  (download links — the download endpoint is already open to every station). Office intake detail page: a
  category `<select>` + PDF/image file picker + a "Kategoria" table column. Tests: backend
  `tests/test_work_order_attachments_api.py` (PNG/JPEG accepted, default DOCUMENT, invalid category 422, image
  bad-signature 400, drawing surfaced on the SP station card / document not); frontend (station-card drawing
  link + category label on detail). Seed adds a sample drawing. `docs/WORKFLOW.md` new "Work Order Attachments
  (incl. technical drawings)" section. **Full backend suite green; alembic check clean; 87 frontend tests +
  both builds green.** Follow-up (deferred, not requested): CAD formats; feeding the drawing into any
  per-product/template model.
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
- Status: **DONE (2026-06-22).** Owner decisions: foil fields = name + code (unique) + supplier + notes;
  registry managed by the **same actors as the paint/RAL registry** (`StationId.OFFICE`, admin bypass);
  scope = **store + display only** (foil-usage stats/consumption deferred). Built a new `app/foils/`
  module (model/schema/repository/service/router) mirroring `clients/` — full CRUD with OFFICE-gated
  writes + audit events (`foil.created/updated/deleted`) and a `usage_count` rollup. `WorkOrder` gains a
  nullable `decoral_foil_id` FK (`ON DELETE SET NULL`, like `paint_id`) plus a CHECK
  `decoral_foil_requires_decoral_coating` (a foil can only sit on a DECORAL order). Office intake accepts
  `decoral_foil_id` on create/update (validated: foil must exist and the order must be Decoral — else
  422); the chosen foil is surfaced as a compact `FoilSummaryRead` on `WorkOrderRead` **and** the
  decoral-station read model (`ProcessStageWorkOrderRead`). Frontend: a `/folie` registry page (mirrors
  Klienci, with topbar "Dodaj folię"), a foil `<select>` in the create form shown **only** when
  technology = Decoral, and foil display on the work-order detail + the Decoral station card. Migration
  `20260622_0036` (foils table + FK + CHECK via work_orders batch rebuild); `alembic check` clean. Seed
  script seeds 3 foils and assigns one to the decoral-manual order. Tests: `tests/test_foils_api.py`
  (registry CRUD, dup-code 409, wrong-station 403, search by name/code, decoral order stores+shows foil +
  usage rollup, foil-on-RAL 422, unknown-foil 422) + a frontend intake test (picker only for Decoral,
  submits `decoral_foil_id`). Full backend + frontend suites green; both builds clean. Follow-up (not
  built, deferred per owner): feed the chosen foil into Decoral-pass consumption / foil-usage stats.
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
  - Cut 2 (resource-lock + packing-slot manager) **DONE (2026-06-22)** — extracted `ResourceLockManager`
    (`app/process/resource_locks.py`, instantiated as `self.resource_locks`): the HANGING/AUTOMATIC_LINE
    single-holder locks, the N-slot PACKING capacity model (NA22), the in-process resource-mutation `RLock`s,
    and the three occupancy predicates (which turned out to be **cluster-local** — used only to decide
    acquisition/reservation/stale-recovery, so they moved cleanly; the manager keeps a private `_stage_state`
    copy as its one cross-dependency). The per-work-order *process*-mutation lock stays on `ProcessService`
    (separate concern). Behavior-preserving: 438 backend tests pass, `alembic check` clean; `service.py`
    2906 → 2596 lines (3119 → 2596 across both NA39 cuts so far). **NA46 §A5 deliberately left out** — see below.
    Commit `cc33845`.
  - **FINDING (2026-06-22): the last two suggested seams do NOT factor cleanly — stop the class-extraction
    approach here (owner-confirmed pivot to NA43).** On inspection, a `CorrectionService` would have to call
    **back into 8+ `ProcessService` methods** mid-transaction (`get_correction_return_stage`,
    `_reset_stage_states_for_active_batch`, `_get_stage_state`, `_sync_legacy_current_active_batch`,
    `_mark_all_stage_states_done`, `get_work_order_process`, `initialize_stage_states`,
    `initialize_quantity_tracking`) while the packing-completion flow on `ProcessService` calls **into**
    corrections — i.e. **bidirectional coupling**. The serializer (`_to_stage_work_order_read`) has the same
    problem (~15 display-status/quantity/correction-state callbacks). Forcing either extraction would relocate
    ~400 lines but trade a big-file smell for a circular-dependency smell in the most data-integrity-sensitive
    code (quantity conservation, the RAL/DECORAL/stat-only model). Verdict: **the two clean seams (audit,
    resource-locks) are done; what remains in `ProcessService` is the genuinely-coupled workflow core, partly
    inherent to the domain.** Instead of forcing the bad cuts, pivoted to **NA43** (in-file quantity-resolver
    consolidation — DONE). Net NA39 result: `service.py` 3119 → 2606 lines across the two clean extractions +
    NA43.
  - **Still genuinely available (clean, narrow-dependency, opportunistic):** move the leaf
    `_allocate_correction_order_number` into `WorkOrderNumberAllocator` (its natural home; deps are only
    `repository.session` + the WorkOrder model). Small; do when next touching correction numbering.
    - **NA46 §A5 (bound the in-process lock maps)** still open and risky — evicting an in-use `RLock` could
      hand two threads different locks for one id; design eviction carefully (only evict provably-unheld
      locks). `_RESOURCE_MUTATION_LOCKS` now lives in `ResourceLockManager`; `_PROCESS_MUTATION_LOCKS` stays
      on `ProcessService`.
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
- Status: **DONE (2026-06-22).** Collapsed the four scattered display helpers
  (`_get_stage_display_quantity` / `_get_stage_planned_quantity` / `_get_operational_quantity` /
  `_get_stage_counted_quantity`) into one resolver `ProcessService._resolve_stage_quantities` returning a
  frozen `StageQuantities(display, planned, counted, operational)` value object — the read-model serializer
  now makes one call instead of four, so the "which quantity shows where" rule lives once (and the
  surface-prep-actual fetch is deduped). Behaviour-preserving (the four computations are transcribed exactly;
  the read-model fields are byte-identical, so the frontend is untouched). `_get_surface_preparation_actual_quantity`
  stays shared (also used by the packing path). Documented the **five quantities + the single display rule**
  in `docs/WORKFLOW.md` → "Quantity model". Test: `test_resolve_stage_quantities_covers_each_context_NA43`
  pins each context (display DONE vs live, planned, operational pre/post SP count, counted at SP / off-stage /
  PACKING fallback). **439 backend tests pass; alembic check clean; no schema/frontend change.** Done as the
  pivot from NA39's coupled-core finding (see NA39) — an in-file consolidation, not a class extraction.
- Severity: LOW–MEDIUM (clarity; root of NA26-class bugs). See §B3.
- Problem: five quantity notions (ordered / counted / `current_active` / operational / per-stage planned)
  with which-shows-where wrong almost everywhere (NA26), resolved via four scattered helpers.
- Required fix: document the five quantities + the single display rule in `WORKFLOW.md`; collapse the four
  helpers behind one resolver so the rule lives once.
- Acceptance: one resolver owns quantity-for-display; WORKFLOW.md states the rule; tests cover each context.

### NA44. Frontend: decompose monolithic pages + move business semantics off the renderer
- Status: **§C2 (business semantics off the renderer) DONE (2026-06-22); §C1 (page decomposition) still open.**
  - **Overdue is now backend-owned (`is_overdue`).** Added `is_overdue` to `WorkOrderRead`
    (`app/work_orders/schemas.py` + computed in `WorkOrderService._to_read_model`: planned pickup day
    passed and not READY; date-only, server-local, strictly before today). Removed **both** client-side
    `new Date()` computations — `workOrderDisplay.ts` `getWorkOrderAttentionBadges` and
    `WorkOrdersListPage.tsx` `delayedCount`. (Minor behaviour refinement: an order due *today* is no longer
    flagged "PO TERMINIE"; no test pinned the old edge.)
  - **Status label has one owner (the backend).** Owner chose "backend label everywhere": deleted the
    frontend `getWorkOrderStatusSummary` switch (`workOrderDisplay.ts`) and render `process_status.label`
    in `ManagerPanelPage` (×2) and `WorkOrderDetailPage` (×2); removed the redundant stacked summary line
    in the detail "Status procesu" section (the chip already shows the label). Operators now see the precise
    backend wording (e.g. "Produkcja ręczna" / "Produkcja automat", "Pakowanie"), distinguishing
    manual/automatic, instead of the collapsed "W produkcji".
  - Tests: backend `test_read_model_is_overdue_is_backend_owned_NA44`; frontend overdue-from-`is_overdue`
    case in `workOrderDisplay.test.ts` + `is_overdue` added to the three `buildWorkOrder` mock helpers and the
    stale `getWorkOrderStatusSummary` stub dropped from two module mocks. **440 backend + 85 frontend tests
    pass; both builds clean; alembic clean (read-model-only, no schema change).**
  - **Still open — §C1 (structure):** decompose the monolith pages (`WorkOrderDetailPage` 1353,
    `ManagerPanelPage` 1053, `PackingWorkOrdersPage` 908, `StageWorkOrdersPage` 876) into section components
    with a data hook. Bulky churn; the backlog's own guidance is "do it when next touched", so it is left for
    when those pages are next edited rather than a standalone churn pass.
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
- Status: **PARTIAL — §A6 + §A4 DONE; §A5 open.**
  - **§A6 DONE (2026-06-22)** (side effect of NA39 cut 1): both the `audit_events` + `stage_transition_events`
    writes live in `ProcessAuditWriter` (`app/process/audit_writer.py`), so they cannot diverge.
  - **§A4 DONE (2026-06-22):** dropped the stored `current_active_batch_id` pointer. `WorkOrder.active_batch`
    now derives purely from `active_batches` (the partial-unique index
    `uq_work_order_quantity_batches_one_active_per_work_order` guarantees ≤1 active batch, so the single
    active batch *is* the active batch). Removed `_sync_legacy_current_active_batch` + its 8 call sites and
    all 8 direct pointer writes; `audit_writer` derives the paint-consumption `target_id` from `active_batch`.
    Migration `20260622_0035` drops the column (batch table-rebuild; `alembic check` clean). The derivation is
    safe because every flow deactivates the prior batch before/while activating the next (verified in
    `_reset_to_correction_planning` & co.), so no in-memory pre-flush window holds two active batches. Tests:
    rewrote the raw-SQL INSERTs in `test_db_constraints_phase1/2` (dropped the column), removed the now-dead
    pointer writes in `test_process_service` + the seed; migration tests pinned to old revisions keep the
    historical column. **440 backend tests pass; alembic check clean.**
  - **Still open: §A5** (bound/evict the in-process lock maps — design eviction carefully; only evict
    provably-unheld `RLock`s).
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

- **NA60 — queue trailing-shuffle 500 fixed (2026-06-24)** — planning onto a line holding completed (READY)
  orders raised `UNIQUE constraint failed: (production_type, queue_position)` and surfaced as HTTP 500.
  Root cause: `_temporarily_move_queue_rows_out_of_the_way` (`app/manager/service.py`) parked completed rows at
  a temporary range starting `max(positions)+1`, which **overlapped** the final trailed range; because the
  flush applies `UPDATE queue_position` in primary-key order (not the safe move order), the overlap transiently
  violated the unique index. Fix: offset the temporary base by `len(work_orders)` so the parking range is
  strictly above every possible final position (provably disjoint, since trailing only occurs when the top
  position is a completed row, bounding the final block at `max(all)+len`). One line in the shared helper →
  fixes `assign_plan`, `update_queue_position`, and `update_production_type`. Regression test
  `test_assign_plan_appends_onto_line_with_several_completed_orders_without_500` in `tests/test_manager_api.py`
  arranges the completed orders in reverse PK/position order to force the collision (red before, green after).
  Full `pytest` green + `alembic check` clean (no schema change); live-verified the original 500'ing plan now
  returns 200 and the queue stays collision-free. Surfaced by the Phase 2 multi-day simulation (needs
  accumulated completed orders to trigger).

- **NA59 — DECORAL decoral-pass correction documented (2026-06-25)** — the sim surfaced that a correction
  raised at the Decoral pass (`POST /process/work-orders/{id}/decoral-production/complete` with
  `correction_quantity > 0`) routes through the RAL-style same-order reset (`_reset_to_correction_planning`,
  `app/process/service.py:954-967`) rather than the documented DECORAL child spin-off. Reproduced in the real
  frontend with the owner; **owner confirmed the behavior is correct** — the child/`N` model is for base-coat
  defects found at *packing*, while a defect in the *foil* (at the Decoral pass) is a same-order correction
  round. The docs were the gap, not the code. Updated `docs/WORKFLOW.md` (invariant #8 now stage-aware; a new
  "DECORAL correction raised at the Decoral pass" block under Corrections Behavior; a note under the S01–S12
  matrix that the matrix's DECORAL rows are all packing-stage) and CLAUDE.md (core-domain DECORAL bullet now
  splits the two loci). No code change; no tests affected.

- **Workflow simulation — Phase 1 (full light day, all stations, 2026-06-24)** — ran one simulated working
  day with all eight live station personas on the API-driven harness. Office brought in 3 orders (RAL 420 →
  AUTOMATIC, RAL 48 → MANUAL, DECORAL 12 → MANUAL); every station acted (prep counting with a −2 short,
  hanging, automatic paint consumption, manual coating, packing with emergent OK/correction splits, the Decoral
  pass). Auditor clean every tick — including correctly NOT false-flagging 0002's short count (43 OK + 3
  correction = 46 received of 48 planned). Three findings captured: NA58 recurred independently (profiles/
  accessories count attribution); a **harness gap** fixed in-flight (office personas invented un-stocked paint
  triples → an AUTOMATIC order couldn't record consumption; tightened `personas/biuro.md` to pick `paint_code`/
  `paint_producer` from `GET /paints`, and the system correctly rejected consumption against zero stock — not a
  bug); and **NA59**, a code-verified DECORAL-correction divergence (plain decoral-completion uses the RAL
  in-place reset, not the documented child spin-off). Day ended with the three orders mid-correction at planning
  — a realistic Day-1→Day-2 carryover and a natural Phase 2 hook. The `consumed_paint_quantity_kg` "−0.0 on a
  fresh order" the office flagged triaged out as a cosmetic negative-zero, not a bug.

- **Workflow simulation harness + dev virtual clock — Phase 0 (2026-06-24)** — built `scripts/sim/`: a
  multi-day, multi-station simulation where one autonomous LLM persona per station (`personas/*.md`,
  driven through `scripts/sim_client.py`) pulls real work from the running backend and decides for itself,
  so emergent flow surfaces UX gaps + realistic data + invariant breaks. Mechanical half: `controller.py`
  (clock/snapshot/audit/timeline, owns no decisions) + `auditor.py` (quantity conservation, one-active-batch,
  queue-position uniqueness, packing slots) + `seed_sim_baseline.py` (clean DB, zero orders). To make 3
  simulated days produce real timestamps *and* drive the planner's shift/day logic, added a dev-only virtual
  clock: `app/shared/clock.py` chokepoint (now routes the model column defaults + ~14 service `datetime.now`
  sites), the dev-only `PUT /dev/clock` router (`app/api/routes/dev_clock.py`, mounted only in local envs),
  and `tests/test_clock.py`. **Python-side defaults only → no migration; `alembic check` clean.** Auth tokens
  deliberately kept on real wall-clock time (`app/auth/service.py`) because JWT `exp` is validated against real
  time — issuing them on simulated time made them born-expired (caught during Phase 0). `sim_client.py` got a
  reusable `call()` + UTF-8 stdout (Polish), and the Vite-proxy coverage test ignores the dev-only `/dev`
  prefix. Phase 0 result: live `biuro`/`kierownik`/`przygotowanie`/`produkcja-reczna`/`pakowanie` personas ran
  both lines end-to-end; the packing persona independently found 3 under-coated pieces → a RAL correction
  (33 OK + 3 CORRECTION batch back to planning) with quantity conserved (auditor clean every tick); virtual
  clock advanced 07:00→09:45 with real-shaped durations; one friction finding captured (now NA58). Gate: full
  backend `pytest` green + `alembic check` clean. Next: Phase 1 (full light day, all stations) then Phase 2
  (3 days); see `scripts/sim/README.md`.

- **Planning horizon capped at 3 working days (owner policy, 2026-06-24)** — the manager cannot plan
  more than 3 working days ahead (today + the next two working days). Applied as both the default and the
  hard cap on `GET /manager/planner/multi-day`: `_DEFAULT_PLAN_HORIZON_WORKING_DAYS = 3` +
  `_MAX_PLAN_HORIZON_WORKING_DAYS = 3` (`app/manager/service.py`), the router `Query(ge=1, le=3) = 3`
  bound now sourced from those constants (`app/manager/router.py`), and the board/API default dropped
  10 → 3 (`frontend/src/api/managerApi.ts`, `CapacityBoard.tsx`). Docs: `docs/WORKFLOW.md` "Target
  planning model" (rolling board + multi-day endpoint notes) and `docs/FACTORY_DOMAIN_MODEL.md` §7
  (Deadlines are HARD) now state the 3-working-day cap. Tests: planner backend suite + alembic clean
  (no schema change); frontend mocks updated to `horizon_working_days: 3`; 91 frontend tests + build
  green. Note for NA56 (hardcoded Mon–Fri calendar / day-0-full): the smaller horizon makes day-0
  pro-rating more material, but that fix stays under NA56.

- **NA48. `update_production_type` collided with a trailing completed order on the target line (2026-06-23)** —
  Follow-up review of the colleague's per-line-queue merge (`c97d029`). `ManagerService.update_production_type`
  (`app/manager/service.py`) re-slotted a moved order to `_next_active_queue_position_for_line(target)` but,
  unlike `assign_plan`/`update_queue_position`, did **not** trail completed (READY) orders out of the way and
  did **not** map `IntegrityError` → `InvalidManagerPlanningError`. So moving an order onto a line whose append
  slot was occupied by a completed order parked there raised a raw `UNIQUE constraint failed` (HTTP 500) instead
  of trailing the completed order. Fix: mirrored the `assign_plan` pattern — resolve the trailing-completed
  shuffle (`_get_completed_work_orders_requiring_trailing` + `_temporarily_move_queue_rows_out_of_the_way`
  before mutating, `_trail_completed_work_orders` after) and wrap the commit in the same
  `IntegrityError → InvalidManagerPlanningError` guard. Regression test
  `test_change_production_type_trails_completed_order_on_target_line` in `tests/test_manager_api.py` (red before
  the fix with the IntegrityError, green after). Verified: `pytest tests/test_manager_api.py
  tests/test_manager_service.py` green (47), `alembic check` clean.

- **Two independent planning queues (Automat / Ręczna) + simpler manager planning flow (2026-06-20)** —
  owner-requested. The manager planning queue is now **per production line**: `queue_position` is unique
  within `production_type` (DB partial unique index swapped from `uq_work_orders_queue_position` on
  `(queue_position)` to `uq_work_orders_line_queue_position` on `(production_type, queue_position)`,
  migration `20260620_0033`, with per-line renumbering + downgrade). MANUAL and AUTOMATIC are numbered
  independently (position 1 exists on both). Backend: the queue helpers in `app/manager/service.py`
  (`assign_plan`, `update_queue_position`, `update_production_type`, `reorder_queue`, completed-trailing,
  revision) now operate within a single line; **`assign_plan` appends to the end of the chosen line**
  (server-computed position, `queue_position` is now optional in `WorkOrderPlanAssignRequest`);
  **`update_production_type` re-slots the order to the end of the target line**; `reorder_queue` carries a
  `production_type` and reorders only that line (per-line stale revision via
  `get_planned_queue_revision(production_type)`). Frontend (`ManagerPanelPage.tsx`): rebuilt into an entry
  screen with an **"Edytuj plan"** button + two read-only boards (Automat / Ręczna), opening a full-screen
  editor with a top-right line switch, the unplanned list (existing filters) on the left, and the selected
  line's queue (drag-and-drop) on the right; planning is now a single **"Zaplanuj"** button that appends to
  the selected line (no position field, no per-card type picker). Tests: 4 new per-line API tests
  (independent positions, append, one-line-reorder isolation, type-move re-slot, cross-line reject) in
  `tests/test_manager_api.py`; updated `test_manager_service.py`, `test_db_constraints_phase2` index name,
  `test_alembic_schema_drift`, and 7 manager UI tests in `frontend/tests/uiStateConsistency.test.tsx`.
  Docs: `docs/WORKFLOW.md` "Per-Line Queue Rule" (replaces "Shared Queue Rule (Global)") + `CLAUDE.md`.
  Verified: `pytest` green, `alembic check` clean + upgrade/downgrade roundtrip, frontend `npm run test`
  (78) + `npm run build` green. Sets up **NA33** (an "Ułóż automatycznie" / colour-grouping action now lives
  naturally per line).

- **Manual-test pass of the post-20.06 features + 3 bug fixes found and fixed (2026-06-23)** — Owner walked
  through the new features (curated seeder `scripts/seed_new_features_walkthrough.py` + `WALKTHROUGH_NOWOSCI.md`,
  commit `a1e2752`). Confirmed working: NA35 wheel, NA38 foil picker, NA36 attachment upload, NA44 labels,
  NA34 "do zaplanowania" correction, NA32 cumulative paint. Three defects surfaced and were fixed:
  - **Attachment view/download returned 401 "Nie jesteś zalogowany"** (commit `810d00e`). A bare `<a href>`
    navigation bypasses the token-injecting `window.fetch` interceptor, so no `Authorization` header was sent.
    Fix: `openWorkOrderAttachment` fetches the file as a blob (carrying the JWT) and opens it in a new tab;
    used by the detail-page "Otwórz" button and the station-card drawing links. **Affected ALL attachment
    downloads, not just NA36.**
  - **Adding paint failed silently with an empty "Kod farby"** (commit `810d00e`). `paint_code` is required
    (min_length=1, part of the paint identity) but the form sent `""` and showed a raw 422. Fix: client-side
    validation of RAL + producer + code on the delivery/adjustment forms.
  - **Adding/fetching foils failed with a generic "nie udało się… folii" — ROOT CAUSE: Vite dev proxy was
    missing `/foils`** (commit `136f16a`). In dev the browser talks to the backend through
    `frontend/vite.config.ts`'s per-prefix proxy allowlist; `/foils` was never added, so the browser hit
    Vite's HTML 404, `response.json()` threw, and the UI showed its fallback. **NOT a DB/migration problem**
    (direct backend/TestClient calls always worked — which is why it looked DB-shaped). Fix: add `/foils` to
    the proxy **and** a guard test `tests/test_vite_proxy_covers_api.py` that fails if any backend router
    prefix is missing from the proxy, so this class of "new feature breaks in dev" cannot silently recur.
    Requires a Vite restart to take effect.
  - **NA34 stat-only correction — owner decision: leave as is.** Verified it IS recorded (audit event on the
    order + `stat_only_corrections` row) and IS counted in stats (reason report + throughput). Owner chose not
    to add extra prominence (no separate stat counter, no order-detail badge). No further work.

- **NA36 — Technical drawings as a typed attachment (2026-06-23, commit `6e4d27a`)** — see the NA36 entry above
  for full detail (DONE note). PDF + PNG/JPG, structured `category` discriminator, surfaced on station cards +
  detail page; migration `20260623_0037`.

- **Removed `managerPlanDraftReconcile.test.tsx` during the per-line merge (2026-06-23)** — the per-line
  rebuild removed queue-position picking from manager planning, so the reconcile helper and its test (NA31's
  2026-06-22 fix) cover behavior that no longer exists. See NA31 for the supersession note.

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

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
- Status: OPEN (discovered 2026-06-18).
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
- Status: OPEN (discovered 2026-06-19 during the S06 walkthrough).
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
- Status: OPEN (discovered 2026-06-19 during the S05 walkthrough).
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
  `docs/FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md`, `docs/PAINT_SYSTEM_DEFINITION_DRAFT_PL.md`,
  `docs/STATION_IDENTITY_AND_AUDIT.md`, `docs/OPERATOR_USABILITY_AUDIT_PL.md`,
  `docs/UI_PASSIVE_REVIEW_PL.md`, `docs/AUTHZ_DESIGN_PROPOSAL.md`, `docs/WORKING_CONTRACT.md`,
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
- Progress (2026-06-17): **findings pass DONE + safe edits APPLIED** → `docs/DOC_COHERENCE_AUDIT.md`.
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
  refresh `docs/DOC_COHERENCE_AUDIT.md`. (Auto-running it on a schedule would need the billable
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
- **DONE (2026-06-17): full read-only pass → `docs/CODE_CONFORMANCE_AUDIT.md`.** Per-topic verdicts with
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

## New owner requests (2026-06-19) — need scoping before implementation

Source: owner chat 2026-06-19 (screenshot). These are raw feature requests, not yet fully specified.
Each needs an owner-confirmation pass (and a `docs/WORKFLOW.md` update if it changes workflow meaning)
before building. Severities are first-pass estimates.

### NA33. Automatic work-scheduling logic + colour grouping + tidy statistics
- Severity: MEDIUM (planning/throughput feature). Largest of this batch.
- Request (verbatim): "Grupowanie kolorami, statystyki uporządkować, logika automatycznego układania
  pracy (po kolorze, po terminie, minimalny przerób)."
- Three parts:
  - **Group the planning queue by colour** so same-colour orders cluster (fewer colour changes on the line).
  - **Tidy up the statistics** (Statystyki page) — unspecified clean-up; needs the owner to point at what
    is messy now (likely follow-on from NA23/NA29 work).
  - **Automatic work-ordering logic** that proposes a queue order optimising for: same colour, then due
    date (po terminie), then **minimal changeover/rework** (minimalny przerób). Likely a suggested
    ordering on the manager planning queue (`app/manager/service.py` reorder/assign + `ManagerPanelPage`).
- Open questions for owner: is auto-ordering a one-click *suggestion* the manager can accept/override, or
  fully automatic? Priority weighting between colour vs deadline vs changeover? Does "minimalny przerób"
  mean colour-changeover minimisation specifically, or something else?
- Acceptance: TBD after scoping. At minimum: queue can be grouped/sorted by colour; an auto-arrange
  action proposes an order by (colour, deadline, changeover); covered by tests.

### NA34. Distinguish two correction kinds — "fixed on the spot" (stat-only) vs "to be re-planned"
- Severity: MEDIUM (changes correction semantics — touches the correction model + stats; coordinate with
  NA32 paint-consumption and the RAL/DECORAL correction paths).
- Request (verbatim): "rozróżnienie poprawek na poprawki od razu poprawione i do zaplanowania. Poprawka
  od razu poprawiona w logice jest tylko daną statystyczną, nie wraca nigdzie z powrotem. Poprawka do
  zaplanowania jest poprawką która powoduje że musi zostać ten kolor jeszcze raz zaplanowany i pomalowany."
- Two correction categories:
  - **Fixed on the spot ("od razu poprawiona")** — recorded **only as a statistic**; it does NOT re-enter
    the workflow (no return to planning, no child order, no re-paint). Today every correction returns
    (RAL → planning batch reset; DECORAL → child order), so this is a genuinely new "stat-only" path.
  - **To be re-planned ("do zaplanowania")** — the existing behaviour: the colour must be planned and
    painted again (the current RAL/DECORAL correction flow).
- Impact: the packing correction-capture UI needs to ask which kind; the stat-only kind must feed the
  corrections reason report / throughput correction counters **without** creating a `CORRECTION` batch or
  child work order; the re-plan kind keeps current behaviour.
- Open questions for owner: does stat-only still record reason/category + quantity? Does it apply to both
  RAL and DECORAL? Does a stat-only correction affect completed/total quantity at all, or is the order
  considered fully done as-is?
- Acceptance: at packing, an operator can mark a correction as "fixed on the spot" (stat-only, no
  re-plan, no child/batch) or "to be re-planned" (current flow); statistics count both; covered by tests;
  `docs/WORKFLOW.md` correction model updated.

### NA35. Number-entry fields change value on mouse-wheel scroll (UX defect)
- Severity: LOW (UX defect, but annoying/error-prone — easy fix).
- Request (verbatim): "Gówno ze scrollem w polach z wpisywaniem liczby."
- Problem: native `<input type="number">` fields change their value when the wheel scrolls over a focused
  field, so operators accidentally alter counts while scrolling the page.
- Required fix: disable wheel-to-change on numeric inputs (e.g. blur on wheel, `onWheel` preventDefault,
  or a shared `NumberInput` component) across the quantity-entry surfaces (packing count, surface-prep
  count, office quantities, paint kg, etc.).
- Acceptance: scrolling the wheel over a number field no longer changes its value anywhere; keyboard entry
  unaffected.

### NA36. Technical drawings on a work order
- Severity: MEDIUM (feature). Needs scoping.
- Request (verbatim): "Rysunki techniczne."
- Likely: attach/display technical drawings for an order (a kind of attachment beyond the existing QC
  doc + `WorkOrderAttachment`?). Confirm with owner.
- Open questions: who uploads (office at intake?), who views (which stations?), file types (PDF/image/CAD?),
  is it per work order or per product/template? Is this distinct from the existing attachment mechanism?
- Acceptance: TBD after scoping.

### NA37. WZ document (Wydanie Zewnętrzne — goods-issue / delivery note)
- Severity: MEDIUM (feature). Needs scoping.
- Request (verbatim): "Wz."
- Likely: generate a WZ goods-issue document when an order is released/shipped (analogous to the existing
  QC Excel→PDF generation). Confirm with owner.
- Open questions: what fields/template, when is it generated (at completion/release?), numbering scheme,
  PDF like the QC doc, who can issue it?
- Acceptance: TBD after scoping.

### NA38. Enter Decoral foils when adding an order
- Severity: MEDIUM (feature — office intake). Needs scoping.
- Request (verbatim): "Folie decoral do wprowadzenia przy dodaniu zlecenia."
- Likely: at office intake (create work order), capture the Decoral foil(s) used for a decoral order
  (`app/work_orders/` create/update + intake form). Confirm with owner.
- Open questions: is there a fixed list of foils to pick from (a registry, like paints/clients) or free
  text? One foil per order or several? Does it feed the Decoral pass / consumption / stats?
- Acceptance: TBD after scoping.

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

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

### NA6. JWT has no expiry
- Status: DONE (2026-06-17) — see Done section.
- Problem: `create_access_token` (`app/auth/service.py:17-23`) issues tokens with no `exp` claim;
  tokens are valid forever and are stored in `localStorage` (`frontend/src/context/AuthContext.tsx:40`).
- Required fix: Add an `exp` claim and verify it in `decode_token`; decide a session lifetime.
- Acceptance: Expired tokens are rejected with `401`; tests cover expiry.

---

## LOW

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

## Done

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

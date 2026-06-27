# Frontend Triage — sourced inventory (awaiting owner adjudication)

**Status:** first triage pass of the **unreviewed** frontend (React + TypeScript, ~13.7k LOC / 60 files),
started **2026-06-27**. Method mirrors the backend rebuild (`CLAUDE.md`): every finding is grounded in the
code (`file:line`); **nothing here is a decision yet** — the owner adjudicates which items become work, the
same way `docs/CHANGES.md` was built. Severity is the engineer's estimate, not a priority ruling.

> The backend changes #1–#10 (`docs/CHANGES.md`) shipped on the backend. This pass checks, among other
> things, whether the frontend kept up. **Good news first:** the front is **not** runtime-broken by those
> changes — e.g. the scheduler rule list is rendered from whatever the server returns
> (`ManagerPanelPage.tsx:1062`), so the removed `changeover` rule simply never arrives. The drift is in
> *missing surfacing* and *stale copy*, not crashes.

## Coverage map (be honest about what was actually read)

- **Deep-read (2026-06-27):** `main.tsx`, `AuthContext`, `ProtectedRoute`, `stationContext`, all three
  `api/*` clients, `types/workOrders|process|manager`, `utils/*`, `hooks/usePolling`, `NumberInput`,
  `CapacityBoard`, `WorkOrderDetailPage`, `ManagerPanelPage` (core logic), `PackingWorkOrdersPage`,
  `DecoralWorkOrdersPage`, `StageWorkOrdersPage` (the three triplicated stage-completion pages — C3) and
  its thin intake wrappers (`Hanging`/`SurfacePreparation`/`Manual`/`AutomaticProductionPage`),
  `CreateWorkOrderPage`, `StatystykiPage`, `PaintInventoryPage`, `WorkOrdersListPage`,
  `OfficeWorkOrdersTable`, `AppLayout`.
- **Light / not yet deep-read:** the remaining CRUD/display pages — `ClientsPage`, `FoilsPage`,
  `EmployeesPage`, `AuditEventsPage` — plus the small presentational components (`BarChart`, `RalColorDot`,
  `StationPresenceWidget`, `TechnicalDrawingLinks`, `WorkOrderPrimaryInfoLine`) and the thin
  clients/foils/employees/audit/paints API wrappers. Standard CRUD; lower risk. The core flows above are
  now verified.
- **Resolved non-findings (read, then cleared):** `AutomaticProductionPage` using `stage="PRODUCTION"` is
  intentional (the backend aggregates HANGING+PRODUCTION for the automat operator + paint consumption, not
  a missing-stage drift); `StatystykiPage`'s coating split correctly excludes `m2_decoral_pass` (backend:
  it overlaps the base coat and is NOT part of `m2_total`, shown as its own chart/column).

---

## Bucket A — Drift vs the backend changes #1–#10

### A1 — Manager can't actually set the shift length (#4 / #9 half-shipped) — ✅ DONE 2026-06-27
- **Was:** there was **no UI to set it**. The front only *displayed* the value; the
  `/manager/day-shift-length` endpoints were called nowhere, and the plan ignored the persisted table —
  so the shift was always the LONG default.
- **Done:** the capacity board now has a per-day LONG/SHORT toggle (`ShiftToggle`) that PUTs
  `/manager/day-shift-length` and refetches. The planner reads the persisted per-day shift as the single
  source of truth (drives both the plan fill/judging and good-day stats); the old load-derived
  `display_shift_for` advisory was removed; an unset day defaults LONG. Owner-decided 2026-06-27 (per-day
  shift drives plan + stats; unset day = LONG). See `docs/DECISIONS.md` (2026-06-27 — A1) and `SPEC.md`
  §capacity. `frontend/src/components/CapacityBoard.tsx`, `frontend/src/api/managerApi.ts`,
  `app/manager/placement.py`, `app/manager/service.py`, `app/manager/router.py`.

### A2 — `STOCK_NOT_ENTERED` is invisible on the board (#8) — ✅ DONE 2026-06-27
- **Was:** `PaintFeasibilityStatus` lacked the status and the board only chipped `BLOCKED`/`WARNING`, so a
  `STOCK_NOT_ENTERED` placement showed no chip → looked OK (the "silent OK" #8 set out to kill).
- **Done:** added `STOCK_NOT_ENTERED` to the type (`types/manager.ts`) and a "wpisz stan farby" chip on the
  board placement row (`CapacityBoard.tsx`).

### A3 — False on-screen copy: "od jasnych do ciemnych kolorów" (#7) — ✅ DONE 2026-06-27
- **Was:** the board told the manager it sorts "w kolejności od jasnych do ciemnych kolorów"; #7 dropped
  that — within-day planning is pure colour grouping.
- **Done:** copy now reads "grupując zlecenia w tym samym kolorze obok siebie"; the stale module comment
  was corrected too. `CapacityBoard.tsx`.

### A4 — Quantity-leak flag never surfaced (#10) — ✅ DONE 2026-06-27
- **Was:** `quantity_leak_flagged` wasn't in the type and was rendered nowhere.
- **Done:** added the field to the `WorkOrder` type; a "WYCIEK ILOŚCI" attention badge (shows on the detail
  page + manager panel) plus an explanatory banner on `WorkOrderDetailPage` so the leak is investigated
  rather than invisible. `types/workOrders.ts`, `utils/workOrderDisplay.ts`, `pages/WorkOrderDetailPage.tsx`.

### A5 — Second, separate Decoral pass only hinted by a cryptic `N` prefix (#2, already open)  *(severity: medium)*
- #2 (still open on CHANGES) wants the returned-pieces "second Decoral pass" made obvious. On the front the
  only signal is the order number silently rendered as `N{number}` when `is_decoral_incomplete`
  (`DecoralWorkOrdersPage.tsx:358`), plus the generic `POPRAWKA`/`DECORAL` badges — no plain-language "this
  is a separate, second Decoral round on the returned pieces" callout. Note the `N`/`P` prefix rule is
  duplicated verbatim in 4 files (see C4), so #2's surfacing touches all of them.

### A6 — Stale type: `ScheduleRuleKey` still lists `"changeover"` (#6)  *(severity: low)*
- `types/manager.ts:121` keeps the removed rule key. Harmless at runtime (list is server-driven) — pure
  type cleanup.

---

## Bucket B — Correctness risks in the unverified frontend

### B1 — Global `window.fetch` monkey-patch for auth  *(severity: medium)*
- `main.tsx:10-27` overwrites `window.fetch` to inject `Authorization: Bearer` on **every** request and to
  hard-redirect on any 401. Two concerns: (a) the Bearer token is attached even to cross-origin requests, so
  if `VITE_API_BASE_URL` ever points at another origin the token leaks there; (b) a single 401 anywhere does
  `window.location.href = "/login"` (full reload, loses SPA state). Works today; fragile by design.

### B2 — Auth storage keys duplicated in three places  *(severity: low)*
- `"auth_token"`/`"auth_user"` are defined as constants in `AuthContext.tsx:3-4` but re-hardcoded as string
  literals in `main.tsx:12,22-23` and `ProtectedRoute.tsx:16`. Drift risk if the key ever changes.

### B3 — Queue revision via lexicographic `updated_at` compare  *(severity: low-med)*
- `utils/queueReorder.ts:77-86` derives the optimistic-concurrency revision by string-`>`-comparing
  `updated_at` ISO strings. Correct only while the backend always emits the same format/zone; worth pinning
  with a test against a real payload.

### B4 — Rule config loaded for AUTOMATIC, saved to `editLine`  *(severity: low, latent)*
- `ManagerPanelPage.tsx:426` fetches the rule config hardcoded as `"AUTOMATIC"`, but `handleSaveRules`
  (`:502`) saves to `editLine`. Today the rules effect is gated to AUTOMATIC (`:419`), so it can't misfire —
  but the mismatch is a latent bug if the rules UI is ever exposed on the MANUAL line.

### B5 — Packing/Decoral draft key mixes two ID spaces  *(severity: low)*
- Both `PackingWorkOrdersPage.tsx:200` and `DecoralWorkOrdersPage.tsx:146` key the per-card draft by
  `batch_id ?? id`. `batch_id` (quantity-batch IDs) and `id` (work-order IDs) come from different sequences,
  so a batch and a batchless order sharing the same integer would collide into one draft. Low probability,
  but the key isn't provably unique; a namespaced key (`b{batch_id}` / `w{id}`) would remove the risk.

### B6 — Office list recomputes "overdue" client-side, ignoring the not-READY rule  *(severity: low-med)*
- The backend exposes `is_overdue` = "pickup before today **AND** not yet READY" (SPEC §2). The office list
  row instead recomputes its own `isOverdue = planned_pickup_date < now` (`OfficeWorkOrdersTable.tsx:53-55`)
  and `getDaysLabel` does the same (`:40-48`), so a **completed (READY)** order picked up after its date
  still shows a red "Po terminie" on the date column. The list's own delayed counter correctly uses
  `workOrder.is_overdue` (`WorkOrdersListPage.tsx:72`) — only the row drifted. Use `workOrder.is_overdue`.

---

## Bucket C — Dead code / duplication

### C1 — Identical dead ternary branch  *(severity: low)*
- `api/managerApi.ts:263-265`: `base.startsWith("http") ? \`${base}?…\` : \`${base}?…\`` — both branches are
  byte-identical. Collapse to one expression.

### C2 — `createApiUrl` triplicated  *(severity: low)*
- The same `createApiUrl` helper + the `.startsWith("http")` absolute/relative dance is copy-pasted across
  `workOrdersApi.ts:11-23`, `processApi.ts:8-20`, `managerApi.ts:23-35` (and repeated inline ~6×). One shared
  helper would remove it.

### C3 — Stage-completion pages are a triplicated copy  *(severity: medium)* — 🟡 IN PROGRESS
- `StageWorkOrdersPage`, `PackingWorkOrdersPage`, `DecoralWorkOrdersPage` share ~80% of their code as
  copy-paste. **C3a done 2026-06-27:** the *pure* duplicated helpers (`buildCorrectionReference` /
  `buildCorrectionQuantityContext` / `buildMergedCorrectionDeltaText`, `badgeClasses`, `balanceClasses`,
  `parseQuantity`) are now single definitions in `utils/workOrderDisplay.ts`, imported by all three pages
  (and `badgeClasses` also de-duplicated from `WorkOrderDetailPage`), pinned by a new unit test
  (`utils/workOrderDisplay.test.ts`) and the existing component suite (111 green).
- **C3b done 2026-06-27:** the **correction-split sub-form** (profiles/accessories + balance + reason +
  optional note, byte-identical in Packing/Decoral, incl. the duplicated `correctionReasonOptions`) is now
  one component `components/CorrectionSplitFields.tsx`, used by both pages; the packing-only "Rodzaj
  poprawki" disposition stays in the packing card. Pinned by `CorrectionSplitFields.test.tsx` + the existing
  component suite (116 green). Behaviour-preserving.
- **Remaining (C3c):** the **card header** block (line label / N-P number / status badge / primary info /
  badges / technical-drawings / correction-context) is still copy-pasted across the three pages. Unifying it
  is what lets **A5** (#2) land in one place — and is where the divergence below gets fixed.
- **Concrete divergence to fix in C3c (a deliberate behaviour change, with a test):**
  `StageWorkOrdersPage` gates the correction card on `is_correction` only, while Packing/Decoral use
  `is_correction || is_correction_round` — so a correction-**round** order on a stage page silently loses the
  "runda" label the other two give it.

### C4 — `N`/`P` order-number prefix rule duplicated in 4 files — ✅ DONE 2026-06-27
- The ternary that rebuilds the displayed order number (`is_decoral_incomplete → N…`, partial → `P…`) was
  copy-pasted byte-for-byte in 4 files plus a restructured variant in `WorkOrderPrimaryInfoLine`. Now one
  `formatDisplayOrderNumber()` (+ `isPartiallyComplete`) in `utils/workOrderDisplay.ts`, used by all five
  (`StageWorkOrdersPage`, `PackingWorkOrdersPage`, `DecoralWorkOrdersPage`, `OfficeWorkOrdersTable`,
  `WorkOrderPrimaryInfoLine`), pinned by `utils/workOrderDisplay.test.ts`. Still client-reconstructed (a
  backend-supplied display number remains the cleaner long-term fix) but no longer duplicated.

### C5 — Predicted-paint formula re-derived client-side  *(severity: low)*
- `CreateWorkOrderPage.tsx:126-132` reimplements the backend's paint prediction (`area < 100 ? /4 : /6`) to
  show a live hint at create time (before an order exists). Fine as a hint, but it's backend math duplicated
  on the client — if the divisor/threshold ever changes server-side, the create-form hint drifts silently.

### C6 — Cross-component "add" triggers via global DOM CustomEvents  *(severity: low)*
- The header's "Dodaj klienta" / "Dodaj folię" buttons fire `document.dispatchEvent(new CustomEvent(
  "clients:open-add-form"))` / `"foils:open-add-form"` (`AppLayout.tsx:230,240`) which `ClientsPage` /
  `FoilsPage` listen for. A global DOM event bus for parent→page comms is unidiomatic in React (vs context /
  router state / a shared store) and easy to break silently (string-keyed, untyped). Low risk, real smell.
- Minor sibling: `AppLayout.getSectionTitle` (`:85-102`) re-maps every route→title, duplicating the nav
  label list a few lines above.

### D1 — Inconsistent error surface: `alert()` vs inline banners  *(severity: low)*
- The QC-document download failure uses a native `alert()` (`WorkOrderDetailPage.tsx:277`); the rest of the
  app uses inline rose banners. Jarring and easy to miss on a shop tablet.

### D2 — Native `window.confirm` for destructive actions  *(severity: low)*
- Delete/confirm flows use the browser `confirm` dialog (`ClientsPage.tsx:355`, `FoilsPage.tsx:153`,
  `PackingWorkOrdersPage.tsx:382`, `WorkOrderDetailPage.tsx:446,472,551`) instead of the app's own modal
  styling. Functional, but off-brand and unstyleable on kiosk browsers.

### D3 — Work-order detail has no auto-refresh  *(severity: info)*
- Station boards poll (`usePolling`), but `WorkOrderDetailPage` is a one-shot fetch. Acceptable for an
  office detail view; noted so it's a conscious choice, not an oversight.

### D4 — Create form: "Data przyjęcia" required but unmarked  *(severity: trivial)*
- `received_date` is validated as required (`CreateWorkOrderPage.tsx:385-388`) but its label has no `*`,
  while "Termin odbioru *" does (`:630`). Cosmetic label inconsistency.

---

## Suggested adjudication order (engineer's recommendation, owner decides)

- ✅ **A1** (shift length unsettable) — done 2026-06-27.
- ✅ **A2 / A3 / A4** (#8 / #7 / #10 surfaced) — done 2026-06-27.

Remaining, recommended order:

1. **C3 (+ C4)** — de-duplicate the triplicated stage-completion pages *before* more correction-flow work,
   so **A5** (#2 second Decoral pass) and any future correction change land in one place, not three. The
   `is_correction_round` divergence under C3 is a live symptom. This is the one medium-weight item left.
2. **A5** (#2) — make the second Decoral pass legible; cleanest to do on top of C3/C4's shared helper.
3. **B6** — small correctness fix (office list use `is_overdue`), and **B1** (auth `window.fetch` patch) if
   you want the security hardening.
4. **A6 / C1 / C2 / C5 / B2 / B5 / C6 / D1–D4** — trivial cleanups + UX polish, batchable.

Deep read is essentially complete (see coverage map); only standard CRUD pages remain light-read. Items the
owner confirms become entries in `docs/CHANGES.md` (frontend section) and carry a `file:line` + confirmation
marker, exactly like the backend list.

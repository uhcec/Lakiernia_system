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

### A5 — Second, separate Decoral pass made visible (#2) — ✅ DONE 2026-06-27
- **Was:** the only hint that returned corrected pieces were a separate "second Decoral pass" was the
  cryptic `N` prefix (which actually marks "open corrections", not the second pass) — easy to miss.
- **Done:** the Decoral station shows a distinct **"DRUGI PRZEBIEG · poprawione sztuki"** badge on the
  returned-pieces card. The precise signal (verified against the backend's scenario-2 test): a partial
  Decoral batch with no open corrections left on the root — `isReturnedDecoralPass` in
  `utils/workOrderDisplay.ts`, pinned by tests; rendered in `DecoralWorkOrdersPage.tsx`. Owner chose the
  narrow form (badge on the second pass only). See `docs/DECISIONS.md` (2026-06-27 — #2) and `CHANGES.md #2`.

### A6 — Stale type: `ScheduleRuleKey` still listed `"changeover"` (#6) — ✅ DONE 2026-06-27
- Removed; now `ScheduleRuleKey = "colour" | "deadline"` (`types/manager.ts`). Harmless at runtime (the list
  is server-driven), pure type cleanup.

---

## Bucket B — Correctness risks in the unverified frontend

### B1 — Global `window.fetch` monkey-patch for auth — ✅ DONE (hardened) 2026-06-27
- **Was:** `main.tsx` overwrote `window.fetch` to inject `Authorization: Bearer` on **every** request and to
  hard-redirect on any 401. Concern (a): the Bearer token was attached even to cross-origin requests, so a
  third-party fetch (or an absolute `VITE_API_BASE_URL` pointing elsewhere) could leak the token off-site.
  Concern (b): a 401 from *any* origin did `window.location.href = "/login"`.
- **Done:** the interceptor now attaches the token **and** acts on 401s only when the request targets our own
  API origin (`isApiRequest` / `API_ORIGIN` in `api/workOrdersApi.ts` — the configured absolute base origin,
  else the app's own origin). A third-party origin gets neither the token nor the redirect. Pinned by
  `api/workOrdersApi.test.ts`. `frontend/src/main.tsx`, `frontend/src/api/workOrdersApi.ts`.
- **Deliberately not done:** the interceptor is *still a global monkey-patch* and the 401 path is *still a
  full reload* (loses SPA state). Replacing the patch with a threaded `apiFetch` wrapper across ~30 call
  sites, and doing SPA-router logout instead of a reload, is a larger non-self-contained change left for
  later — the security leak (the actual risk) is closed; the reload is cosmetic.

### B2 — Auth storage keys duplicated in several places — ✅ DONE 2026-06-27
- **Was:** `"auth_token"`/`"auth_user"` were defined as constants in `AuthContext.tsx` but re-hardcoded as
  string literals in `main.tsx`, `ProtectedRoute.tsx` **and** `LoginPage.tsx` (four spots, not three).
- **Done:** `TOKEN_KEY`/`USER_KEY` are now exported from `AuthContext.tsx` and imported by all three other
  readers; no literal copies remain (verified by grep). `frontend/src/{main.tsx, context/AuthContext.tsx,
  components/ProtectedRoute.tsx, pages/LoginPage.tsx}`.

### B3 — Queue revision via lexicographic `updated_at` compare — ✅ DONE (fixed) 2026-06-27
- **Was:** `utils/queueReorder.ts` derived the optimistic-concurrency revision by string-`>`-comparing
  `updated_at` ISO strings. Verified against the real serialiser (Pydantic v2 + `datetime.now(UTC)`): it
  emits UTC `Z` and **omits the fractional part when microseconds are exactly zero** — so a whole-second
  stamp (`...08:35:00Z`) is chronologically *earlier* than `...08:35:00.5Z` but sorts *later* as a string
  (`'Z'` 0x5A > `'.'` 0x2E). The frontend would then send a stale revision → backend rejects the reorder
  (the backend compares it as a parsed datetime against `func.max(updated_at)`, `manager/service.py:1762`,
  `repository.py:148-156`). Near-impossible with real wall-clock micros, but the dev/virtual clock sets
  whole-second times, so it bites in sim/tests.
- **Done:** compare chronologically via `Date.parse` and return the exact original string of the latest
  order. Pinned by `tests/queueReorder.test.ts` (zero-microsecond edge + array-order independence).
  `frontend/src/utils/queueReorder.ts`. (Residual: `Date` is millisecond-precision; two planned orders
  updated within the same millisecond isn't reachable at the shop's human queue pace — noted in-code.)

### B4 — Rule config loaded for AUTOMATIC, saved to `editLine` — ✅ DONE 2026-06-27
- **Was:** `ManagerPanelPage.tsx` fetched the rule config hardcoded as `"AUTOMATIC"`, but `handleSaveRules`
  saved to `editLine`. The effect is gated to `editLine === "AUTOMATIC"`, so it couldn't misfire today — but
  the read/write asymmetry was a latent bug if the rules UI is ever exposed on the MANUAL line.
- **Done:** the effect now fetches `fetchScheduleConfig(editLine)` / `fetchAutoScheduleProposal(editLine)`
  (symmetric with the save). Behaviour-preserving today (`editLine` is `"AUTOMATIC"` inside the gated effect).
  `frontend/src/pages/ManagerPanelPage.tsx`.

### B5 — Packing/Decoral draft key mixes two ID spaces — ✅ DONE 2026-06-27
- **Was:** both `PackingWorkOrdersPage` and `DecoralWorkOrdersPage` keyed the per-card draft by
  `batch_id ?? id`. `batch_id` (quantity-batch IDs) and `id` (work-order IDs) come from different sequences,
  so a batch and a batchless order sharing the same integer could collide into one draft.
- **Done:** `getDraftKey` now returns a namespaced string (`b{batch_id}` / `w{id}`), provably unique across
  the two ID spaces; `drafts` / `activeWorkOrderId` / `updateDraft` are threaded as `string`. (`activeWorkOrderId`
  was already a draft-key marker, never a real work-order id sent to the backend.) Behaviour-preserving; the
  existing draft-flow suite (122 green) covers it. `frontend/src/components/{Packing,Decoral}WorkOrdersPage.tsx`.

### B6 — Office list recomputed "overdue" client-side, ignoring the not-READY rule — ✅ DONE 2026-06-27
- **Was:** the office list row recomputed its own `isOverdue = planned_pickup_date < now` (and `getDaysLabel`
  did the same), so a **completed (READY)** order picked up after its date showed a false red "Po terminie".
- **Done:** the row now uses the backend `workOrder.is_overdue` ("pickup past AND not yet READY") and
  `getDaysLabel` only says "Po terminie" when overdue (past-date-but-done → "—"). Pinned by
  `OfficeWorkOrdersTable.test.tsx`. `frontend/src/components/OfficeWorkOrdersTable.tsx`.

---

## Bucket C — Dead code / duplication

### C1 — Identical dead ternary branch — ✅ DONE 2026-06-27
- `schedulerConfigUrl` in `api/managerApi.ts` had a ternary whose two branches were byte-identical; collapsed
  to one expression.

### C2 — `createApiUrl` triplicated — ✅ DONE 2026-06-27
- `createApiUrl` was already exported from `workOrdersApi` and imported by 5 helper API files; only
  `processApi` and `managerApi` kept their own copies. Both now import the shared one (3 copies → 1). The
  inline `.startsWith("http")` URL-building repetitions were left as-is (separate, lower-value pattern).

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
- **Concrete divergence — ✅ FIXED 2026-06-27 (ahead of C3c):** `StageWorkOrdersPage` gated the correction
  card (amber border + "runda" text) on `is_correction` only, while Packing/Decoral use
  `is_correction || is_correction_round` — so a correction-**round** order on a stage page lost the "runda"
  label. The stage page now uses the same `isCorrection = is_correction || is_correction_round` gate. (Pure
  card-header *dedup* C3c — folding the three headers into one component — remains optional/low-value.)

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

### D1 — Inconsistent error surface: `alert()` vs inline banners — ✅ DONE 2026-06-27
- **Was:** the QC-document download failure used a native `alert()`; the rest of the app uses inline rose
  banners. **Done:** a dedicated `qcDocErrorMessage` state renders a rose banner under the action-button row
  (matching the existing `uploadErrorMessage`/`attachmentsErrorMessage` pattern; not reusing the page-level
  `errorMessage`, which replaces the whole detail view). `frontend/src/pages/WorkOrderDetailPage.tsx`.

### D2 — Native `window.confirm` for destructive actions — ✅ DONE 2026-06-27
- **Was:** delete/confirm flows used the browser `confirm` dialog (6 call sites across `ClientsPage`,
  `FoilsPage`, `PackingWorkOrdersPage`, `WorkOrderDetailPage`) — off-brand and unstyleable on kiosk browsers.
- **Done:** new `components/ConfirmDialog.tsx` exposes a promise-based `useConfirm()` under a `ConfirmProvider`
  (mounted in `main.tsx`), so call sites stay one-liners (`if (!(await confirm({...}))) return;`). The modal
  matches the app's styling, supports a `danger` tone (rose confirm button for deletes), multi-line messages
  (the packing-override occupant list), Escape-to-cancel, backdrop-cancel and confirm-button autofocus
  (Enter = confirm, parity with native). All 6 sites migrated; no `window.confirm` remains. Pinned by
  `components/ConfirmDialog.test.tsx`; the two tests that spied on `window.confirm` now drive the modal, and
  a shared `render` wrapper injects `ConfirmProvider` in `tests/uiStateConsistency.test.tsx`. 132 tests green,
  `vite build` clean.

### D3 — Work-order detail has no auto-refresh  *(severity: info)*
- Station boards poll (`usePolling`), but `WorkOrderDetailPage` is a one-shot fetch. Acceptable for an
  office detail view; noted so it's a conscious choice, not an oversight.

### D4 — Create form: "Data przyjęcia" required but unmarked — ✅ DONE 2026-06-27
- `received_date` is validated as required but its label lacked the `*` that "Termin odbioru *" has. Added
  the `*` (label now "Data przyjęcia *"); the three create-form tests that select it by label were updated.
  `frontend/src/pages/CreateWorkOrderPage.tsx`, `frontend/tests/uiStateConsistency.test.tsx`.

---

## Suggested adjudication order (engineer's recommendation, owner decides)

- ✅ **A1** (shift length unsettable) — done 2026-06-27.
- ✅ **A2 / A3 / A4** (#8 / #7 / #10 surfaced) — done 2026-06-27.

Remaining, recommended order:

1. **C3 (+ C4)** — de-duplicate the triplicated stage-completion pages *before* more correction-flow work,
   so **A5** (#2 second Decoral pass) and any future correction change land in one place, not three. The
   `is_correction_round` divergence under C3 is a live symptom. This is the one medium-weight item left.
2. **A5** (#2) — make the second Decoral pass legible; cleanest to do on top of C3/C4's shared helper.
3. ✅ **B4 / B5** — latent correctness fixes (rule-config line symmetry; namespaced draft key) — done 2026-06-27.
4. ✅ **B1** — auth token/401 scoped to our API origin (security leak closed) — done 2026-06-27.
5. ✅ **B3** — queue-revision compare now chronological (zero-microsecond edge fixed) — done 2026-06-27.
6. ✅ **B2 / D1 / D4** — trivial cleanups (auth-key dedup, alert→banner, required-label asterisk) — done 2026-06-27.

### Deliberately deferred (logged, not done — engineer's call 2026-06-27)
- **C5** (predicted-paint formula re-derived in the create form): the "proper" fix is a backend preview
  endpoint round-tripped on every keystroke — over-engineering for a pre-submit *hint*. Accepted as-is;
  the divisor/threshold drift risk is documented. Revisit only if the backend formula actually changes.
- **C6** (cross-component "add" via global DOM CustomEvents): works; replacing it with context/router state
  touches `AppLayout` + `ClientsPage` + `FoilsPage` for no behaviour gain. The "sibling" `getSectionTitle`
  is **not** a true duplicate — several titles intentionally differ from the nav labels ("Dodaj zlecenie" vs
  "Nowe zlecenie", "Przygotowanie powierzchni"), so folding it into the nav list would change on-screen copy.
  Left as a documented smell.
- **D3** (no auto-refresh on the detail page): explicitly a conscious choice for an office view; no action.
- **C3c** (card-header dedup across the three stage pages): optional/low-value — the live divergence it
  guarded against is already fixed; folding the headers is pure churn.

Deep read is essentially complete (see coverage map); only standard CRUD pages remain light-read. Items the
owner confirms become entries in `docs/CHANGES.md` (frontend section) and carry a `file:line` + confirmation
marker, exactly like the backend list.

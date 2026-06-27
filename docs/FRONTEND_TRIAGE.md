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

- **Deep-read:** `main.tsx`, `AuthContext`, `ProtectedRoute`, `stationContext`, all three `api/*` clients,
  `types/workOrders|process|manager`, `utils/*`, `hooks/usePolling`, `CapacityBoard`, `WorkOrderDetailPage`,
  `ManagerPanelPage` (core logic), `PackingWorkOrdersPage`, `DecoralWorkOrdersPage` (the subtle
  correction/packing/Decoral flows). `StageWorkOrdersPage` confirmed (grep) as a third copy of the same
  machinery — see C3.
- **Grep-swept only (deep read pending):** `StatystykiPage`, `CreateWorkOrderPage`, `ClientsPage`,
  `FoilsPage`, `EmployeesPage`, `AuditEventsPage`, `PaintInventoryPage`, `HangingPage`,
  `SurfacePreparationPage`, `Manual/AutomaticProductionPage`, presence/number/chart components.
  **These likely hold more findings.** Treat bucket A/B below as the verified core, not the full set.

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

---

## Bucket C — Dead code / duplication

### C1 — Identical dead ternary branch  *(severity: low)*
- `api/managerApi.ts:263-265`: `base.startsWith("http") ? \`${base}?…\` : \`${base}?…\`` — both branches are
  byte-identical. Collapse to one expression.

### C2 — `createApiUrl` triplicated  *(severity: low)*
- The same `createApiUrl` helper + the `.startsWith("http")` absolute/relative dance is copy-pasted across
  `workOrdersApi.ts:11-23`, `processApi.ts:8-20`, `managerApi.ts:23-35` (and repeated inline ~6×). One shared
  helper would remove it.

### C3 — Stage-completion pages are a triplicated copy  *(severity: medium)*
- `StageWorkOrdersPage`, `PackingWorkOrdersPage`, `DecoralWorkOrdersPage` share ~80% of their code as
  copy-paste: the correction helpers (`buildCorrectionReference` / `buildCorrectionQuantityContext` /
  `buildMergedCorrectionDeltaText` exist verbatim in all three — e.g. `StageWorkOrdersPage.tsx:75,101`,
  `DecoralWorkOrdersPage.tsx:110,126`), `badgeClasses`, `balanceClasses`, `parseQuantity`, `getActionLabel`,
  and the whole draft/poll/correction-split card machinery. A change to the correction flow currently has to
  be made in three places — and the backend marks corrections as the subtle, regression-prone path. Strong
  candidate to factor into one shared stage-completion component/hook.

### C4 — `N`/`P` order-number prefix rule duplicated in 4 files  *(severity: low-med)*
- The exact ternary that rebuilds the displayed order number (`is_decoral_incomplete → N…`, partial → `P…`)
  is copy-pasted byte-for-byte in `StageWorkOrdersPage.tsx:503`, `DecoralWorkOrdersPage.tsx:358`,
  `PackingWorkOrdersPage.tsx:545`, `OfficeWorkOrdersTable.tsx:65` (with a further variant of the `P`-logic in
  `WorkOrderPrimaryInfoLine.tsx:28`). The prefix meaning is *reconstructed on the client* rather than
  supplied by the backend. One `formatDisplayOrderNumber()` helper (ideally a backend-supplied field) would
  both de-duplicate and give #2 (A5) a single place to make the second Decoral pass legible.

---

## Bucket D — UX / visual (full-pass scope per owner)

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

---

## Suggested adjudication order (engineer's recommendation, owner decides)

1. **A1** (shift length unsettable) — the only item that leaves an agreed change non-functional.
2. **A2 / A3 / A4** — three small surfacing/copy fixes that make #8, #7, #10 actually land for the user.
3. **C3** — de-duplicate the triplicated stage-completion pages *before* doing more correction-flow work,
   so #2 (A5) and any future correction change land in one place, not three. **C4** rides along with it.
4. Finish the **deep read** of the remaining grep-swept pages (stats / create / clients / intake stages)
   before committing to the rest of the cleanup sweep.
5. **A6 / C1 / C2 / B2 / B5** — trivial cleanups, batchable.

Items the owner confirms become entries in `docs/CHANGES.md` (frontend section) and carry a `file:line` +
confirmation marker, exactly like the backend list.

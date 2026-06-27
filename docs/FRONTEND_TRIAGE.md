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
  `ManagerPanelPage` (core logic).
- **Grep-swept only (deep read pending):** `StageWorkOrdersPage`, `PackingWorkOrdersPage`,
  `DecoralWorkOrdersPage`, `StatystykiPage`, `CreateWorkOrderPage`, `ClientsPage`, `FoilsPage`,
  `EmployeesPage`, `AuditEventsPage`, `PaintInventoryPage`, `OfficeWorkOrdersTable`, presence/number/chart
  components. **These almost certainly hold more findings** (esp. the packing/correction/Decoral flows the
  backend flags as subtle). Treat bucket A/B below as the verified core, not the full set.

---

## Bucket A — Drift vs the backend changes #1–#10

### A1 — Manager can't actually set the shift length (#4 / #9 half-shipped)  *(severity: high)*
- **Backend done:** the manager is meant to set the day length explicitly (CHANGE #4), and #9 added
  `GET/PUT /manager/day-shift-length` to persist it. The capacity model reads `shift_length` and defaults to
  LONG when unset.
- **Frontend gap:** there is **no UI to set it**. The front only *displays* the value
  (`components/CapacityBoard.tsx:133`); `fetchMultiDayPlan` never sends a `shift_length` param
  (`api/managerApi.ts:122-142`); the `/manager/day-shift-length` endpoints are called **nowhere** (grep: 0).
- **Effect:** in practice the shift is always the LONG default — the agreed "manager sets the shift" change
  has no operator-facing half. **This is the biggest functional gap found.**

### A2 — `STOCK_NOT_ENTERED` is invisible on the board (#8 defeated on the frontend)  *(severity: medium)*
- #8 added a distinct `STOCK_NOT_ENTERED` paint status precisely so an un-entered stock is **not** silently OK.
- **Frontend gap:** `types/manager.ts:154` `PaintFeasibilityStatus = "OK" | "WARNING" | "BLOCKED"` — the new
  status is missing from the type. `CapacityBoard.tsx:100-105` only renders a chip for `BLOCKED` / `WARNING`,
  so a `STOCK_NOT_ENTERED` placement shows **no chip → looks OK**. The new `stock_not_entered_order_ids`
  (PaintForwardView) is surfaced nowhere (grep: 0).
- **Effect:** exactly the "silent OK" #8 set out to kill.

### A3 — False on-screen copy: "od jasnych do ciemnych kolorów" (#7)  *(severity: medium)*
- #7 dropped RAL-lightness; within-day colour planning is now **pure grouping**, not a light→dark sweep.
- **Frontend gap:** the capacity board still *tells the manager* it sorts "w kolejności od jasnych do
  ciemnych kolorów" (`CapacityBoard.tsx:268-269`), and the module comment repeats it (`:11`, `:20`).
- **Effect:** user-visible copy describes behaviour the system no longer has.

### A4 — Quantity-leak flag never surfaced (#10)  *(severity: medium)*
- #10 added `work_orders.quantity_leak_flagged` to make the leak **human-visible** (exposed in `WorkOrderRead`).
- **Frontend gap:** the field isn't even in the type (`types/workOrders.ts` `WorkOrder` has no
  `quantity_leak_flagged`), and is rendered nowhere (grep: 0). `WorkOrderDetailPage` shows the prep
  *discrepancy* (`:732-739`) but not the leak flag.
- **Effect:** the leak is back to invisible on the surface the human actually looks at.

### A5 — Second, separate Decoral pass not called out (#2, already open)  *(severity: medium)*
- #2 (still open on CHANGES) wants the returned-pieces "second Decoral pass" made obvious. No dedicated
  treatment exists on the front (grep across Decoral views shows only the generic `POPRAWKA`/`DECORAL`
  badges). Logged here so the frontend end of #2 is tracked alongside A1–A4.

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

---

## Bucket C — Dead code / duplication

### C1 — Identical dead ternary branch  *(severity: low)*
- `api/managerApi.ts:263-265`: `base.startsWith("http") ? \`${base}?…\` : \`${base}?…\`` — both branches are
  byte-identical. Collapse to one expression.

### C2 — `createApiUrl` triplicated  *(severity: low)*
- The same `createApiUrl` helper + the `.startsWith("http")` absolute/relative dance is copy-pasted across
  `workOrdersApi.ts:11-23`, `processApi.ts:8-20`, `managerApi.ts:23-35` (and repeated inline ~6×). One shared
  helper would remove it.

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
3. Finish the **deep read** of the grep-swept pages (packing / correction / Decoral flows first — the
   backend marks those subtle) before committing to a B/C/D cleanup sweep.
4. **A6 / C1 / C2 / B2** — trivial cleanups, batchable.

Items the owner confirms become entries in `docs/CHANGES.md` (frontend section) and carry a `file:line` +
confirmation marker, exactly like the backend list.

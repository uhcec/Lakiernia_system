# Independent review — 2026-07-11 (fresh eyes, execution-first)

**What this is:** a two-phase independent review run at the owner's request. Phase 1 was done
**blind** — a fresh clone with `CLAUDE.md` and `docs/` deliberately withheld, everything verified by
*running* the system (full test suites, live HTTP flows, Playwright through the real UI). Phase 2 read
the docs and reconciled their claims against the phase-1 evidence. This file records the findings;
the actionable items are registered as `CHANGES.md` **#12–#17** and folded into `GO_LIVE.md`.

**Evidence basis (all verified 2026-07-11):** 598/598 backend tests pass (2m10s); 134/134 frontend
tests pass; `npm run build` clean; 45 migrations apply cleanly; full happy path exercised over HTTP
(create → plan → prep → production → packing → 5/5 READY, queue exit correct); station-permission and
auth negative tests all reject correctly; UI toured in Chromium with zero console errors.
The overall verdict is **positive** — the architecture is right-sized, the invariant discipline is
real, and nothing warrants a rebuild. The findings below are the gap between that state and "safe to
run a shop day on".

Labels: **[verified]** = reproduced/read this session; **[inference]** = deduced, not executed;
**[owner]** = needs an owner decision.

---

## 1. Verified pre-live bugs

### 1.1 The undercount chain: "Gotowe" at 3/5, poisoned queue slot, then a 500 → CHANGES #12, #13

The owner-confirmed undercount decision (`DECISIONS.md` 2026-06-30: the prep count is ground truth;
an undercounted order completes) is **not what the code implements**. Repro against a seeded dev
backend [verified]:

1. Create an order with `total_quantity=5`, plan it MANUAL, finish surface prep with
   `counted_quantity=3`, run production, complete packing with counted 3 / OK 3.
2. Result: `status_view` says **READY ("Gotowe")** — via the all-stages-DONE fall-through
   (`app/process/service.py:1170`) — but `total_quantity` stays 5, `completed_quantity` is 3, and
   **no redefinition to a 3-piece order happens** (the ADR's "becomes a 3-piece order" describes
   nothing in the code; the only quantity write is finalize's force-to-total).
3. Finalization never runs: `_can_finalize_work_order` (`app/process/service.py:2422`) requires
   `completed == total` or correction children, so the order **never releases its queue position**
   (CHANGES #3's "completed orders leave the queue" fails on exactly this path) and the CHANGES #10
   leak tripwire never sees it.
4. The zombie row still holds `(production_type, queue_position)` under the DB unique index, but the
   app's availability checks skip READY orders (`app/manager/service.py:1938-1951`, `:1928-1936`).
   Planning another order into that slot passes the check and dies on the index with a **raw HTTP
   500** — `session.flush()` sits *outside* the `IntegrityError → 409` handler in `assign_plan`
   (`app/manager/service.py:1409`; same pattern at `:1460` and `:1567`). A full-line drag-reorder
   renumbering 1..N hits the same wall whenever the zombie slot ≤ N [verified for the explicit-plan
   path; reorder collision is inference from the same index].

Net effect: **the first real undercounted order permanently poisons its queue slot**, and the
manager's later planning actions fail with an error naming a position held by an order that no board
shows. This sits on the owner-blessed happy path, not on an abuse path.

### 1.2 A DONE stage can be restarted while downstream is active — count rewritten mid-flight → CHANGES #14

[verified] With packing IN_PROGRESS, `start` on the already-DONE SURFACE_PREPARATION succeeds
(transition table allows DONE→IN_PROGRESS, `app/process/service.py:1296-1304`; the only backward
guard fires when the *whole order* is display-complete, `:1283-1294`) and **overwrites the counted
quantity** (5 → 2). Packing then validates against the new count and closes the order at 2/5:
batch deactivated, no leak flag, queue slot held forever, unfixable from the UI. SPEC §3 already
says re-touching a finished order is the correction flow's job — the code just doesn't enforce it
for this composite. Fix direction: refuse `start`/`reopen` on a DONE stage while any downstream
stage is IN_PROGRESS/DONE, plus one office-only administrative reset for whatever reality invents.

### 1.3 Office list silently caps at 50 orders → CHANGES #15

[verified] `fetchWorkOrders` sends no pagination params (`frontend/src/api/workOrdersApi.ts:56-62`),
the backend defaults `limit=50` (`app/work_orders/router.py:59`), and the page stores only
`response.items`, ignoring `response.total` (`frontend/src/pages/WorkOrdersListPage.tsx:89-94`).
With 64 orders in the DB the office dashboard reports "Wszystkie zlecenia: 50" and the tiles/tabs
are computed from the truncated page. No pagination UI exists. At real volume, orders simply vanish
from the office view with no indicator. (The backend already returns `total/limit/offset` — the fix
is frontend-only.)

### 1.4 Frontend floor-robustness gaps → CHANGES #16

- [verified] Unguarded `JSON.parse` of localStorage inside a `useState` initializer
  (`frontend/src/context/AuthContext.tsx:25-28`): one corrupt value white-screens the whole app.
  `ProtectedRoute.readUserFromStorage` guards the same read — the fix exists, just not at the source.
- [verified] The three highest-traffic polling boards (`StageWorkOrdersPage`, `PackingWorkOrdersPage`,
  `DecoralWorkOrdersPage`) have **no stale-response guard**; `WorkOrdersListPage`, `WorkOrderDetailPage`
  and `CapacityBoard` do. A slow foreground reload racing a background poll can present stale data.
- [verified] Backend-unreachable errors surface as the browser's raw English `"Failed to fetch"` in a
  Polish operator UI (the `catch` blocks show `error.message` verbatim); the backend i18n sweep fixed
  server messages but not this browser-level leak.
- [verified] Any 401 hard-redirects to `/login` (`frontend/src/main.tsx`), discarding unsaved counts
  mid-packing. Triage B1 called the reload "cosmetic" — on a shift-shared tablet it is silent data
  loss. Related: 12h JWT vs. real shift/tablet patterns is a policy question → GO_LIVE D-item.

### 1.5 Quality-control document requires Windows + licensed Excel → CHANGES #17

[verified] `GET /work-orders/{id}/quality-control-document` drives Excel over COM
(`app/work_orders/service.py:56-98`, pywin32). On Linux it returns a raw 500
(`ModuleNotFoundError: pythoncom` in the worker). This silently couples the GO_LIVE **D1** hosting
decision to a Windows box with Excel installed — or the feature breaks. The feature is also **absent
from SPEC.md** (the rebuilt spec never inventoried it). Cheapest fix: fill the existing xlsx template
with openpyxl (already a dependency, cross-platform) and return the file; or an HTML print view.

---

## 2. Docs vs. code — reconciliation

**Where the docs were right (and phase-1 fresh eyes wrong or incomplete):**

- Order numbering is a **global** counter (`app/work_orders/number_allocator.py:11`); the per-year
  table key is legacy. SPEC §2 had it right; the phase-1 inference from the model shape was wrong.
- The strict counting model is an **owner decision with recorded rationale** (`DECISIONS.md`
  2026-06-30), not over-modeling — phase 1's concept-level criticism withdrawn (the *implementation*
  gap is finding 1.1).
- The planner's over-build was already diagnosed and walked back **with the owner on the record**
  (learned estimators removed, 3 rules → 2, direction factor dropped) — the docs were ahead of the
  reviewer here.
- Several phase-1 "risks" are documented conscious choices: the permissive transition table (SPEC §3),
  the single-worker assumption (SPEC §7), detail-page no-poll (triage D3), the C5/C6/C3c deferrals.

**Where the code/execution contradicts the docs:**

- `DECISIONS.md` 2026-06-30 (undercount): the *intent* stands, but the recorded behaviour claim
  ("its quantity is redefined to the counted amount — becomes a 3-piece order") is **false** —
  see 1.1. An erratum entry has been appended to `DECISIONS.md`; the fix is CHANGES #12.
- `CHANGES.md` #3 "Done": completed-orders-leave-the-queue **fails on the undercount path** (1.1).
  `REVIEW_LEDGER.md` row 7 — which correctly queued this exact confirmation — is hereby answered
  early: **refuted** for undercounted completions, confirmed for quantity-clean ones [verified].
- `FRONTEND_TRIAGE.md` "coverage is now complete — every page/component has been deep-read"
  overclaims: the deep-read pages contained the 50-cap truncation (1.3), the unguarded `JSON.parse`
  (1.4 — B2 edited that very file), and the missing stale-response guards (1.4 — adjacent to B3/B5).
  The triage's fixes are real and good; its completeness claim should not be trusted as "verified".
- `GO_LIVE.md` scope note ("what remains is not feature work — it is verification, deployment, and
  real-use confirmation") is refuted by 1.1–1.5: there is a **bug-fix lane before cutover**. GO_LIVE
  has been amended accordingly (section 1a, owner decisions D5/D6).
- SPEC.md omits the quality-control document feature entirely (1.5) — a load-bearing operational
  constraint lived outside the inventory.
- Minor drift: `app/process/service.py:45` and `:2672` still cite the deleted `docs/WORKFLOW.md`
  (the exact class of drift two ADRs already swept elsewhere).

**A note on the method itself [inference, recommendation]:** the spec-with-citations + owner-adjudication
loop is genuinely strong — but findings 1.1/1.2 show its blind spot: every *individual* rule involved
is owner-confirmed and correctly cited, and the **composite** still breaks. The citation guard proves
lines exist; nothing proves behaviours compose. Recommendation: extend `tests/chaos/` with a
lifecycle fuzzer that drives random *legal* action sequences and asserts global invariants after each
step — e.g. *no READY order holds a queue position*, *no order with all stages DONE has
`completed < total` unflagged*, *every 4xx/5xx is an allowed status*. That is the test class that
catches what citations cannot.

---

## 3. What this changes in the plan

`GO_LIVE.md` remains the burn-down. Deltas applied by this review:

1. New **section 1a — pre-live bug fixes** (#12–#15 blocking, #16 strongly recommended, #17 gated on
   D1/D6): fixing the undercount chain and the rewind hole *before* cutover is non-negotiable — both
   produce states the office cannot repair, on paths a real shop day will hit.
2. New owner decisions: **D5** (undercount presentation: redefine the order to the counted amount
   with an audit trail, vs. keep ordered-vs-arrived visible as a shortfall) and **D6** (is the
   Excel-formatted QC card required, or is a printable page acceptable?).
3. Everything else in GO_LIVE (D1–D4, prod config, serving, backups, data readiness, cutover,
   ledger sweep) is confirmed as the right list — phase 1 independently arrived at the same items.

**Explicitly not proposed** (unchanged): no Postgres, no Docker/K8s, no multi-worker, no offline
PWA, no personal operator logins, no C3c-style refactors, no new planner/statistics features until
the manager has lived with the current ones.

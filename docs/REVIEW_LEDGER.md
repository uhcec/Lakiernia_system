# Review ledger — decision outcomes awaiting confirmation

The missing half of the architectural-memory loop. Each ADR in `docs/DECISIONS.md` states an **Expected**
outcome and a **Review-by** trigger. This file is the single place that collects the `Review-by` triggers
that are **still open** — so a decision's effect is actually *measured*, not just *predicted*.

How to use: when one of the triggers below happens (the owner is on the floor, or the named production
event occurs), confirm the row's *Expected* held, then move it to "Confirmed" with the date. If it did
**not** hold, that is a finding — open it in `docs/CHANGES.md` and trace back to the ADR.

Scope: this lists only outcomes that genuinely **cannot** be checked from code/tests/sim — they need the
owner's eyes on the running shop or a first real production event. Decisions whose effect is already pinned
by a test or is "none required" are not here (they are closed by construction). Dormant *code* triggers
("revisit if a third caller appears") are not outcomes to measure and are not listed either — they live in
their ADR's `Review-by` and fire on a future code change, not on production.

Last swept: **2026-06-30**.

---

## Awaiting confirmation (owner on the floor / first real production event)

| # | Decision (ADR in `DECISIONS.md`) | What to confirm | Trigger | Already pinned in code? |
|---|---|---|---|---|
| 1 | **#2 / A5 — Decoral second-pass badge** (2026-06-27) | "DRUGI PRZEBIEG · poprawione sztuki" appears on the **returned-pieces** card (not the first pass), and the wording reads clearly on the shop tablet | owner's next real correction round at the Decoral station | Logic pinned: `workOrderDisplay.test.ts` + backend scenario-2 test. Only the on-tablet read + right-card-in-a-real-round is unverifiable from here. |
| 2 | **A1 — per-day shift drives the plan** (2026-06-27) | A day no longer reads "poniżej progu" once marked SHORT, overflow lands on later days as expected, **and** sharing one shift across both lines matches the floor reality | owner's next look at the capacity board | Mechanics live-verified over HTTP (LONG→SHORT flip, floor 800→500) + `test_placement.py`. The "matches floor reality" is a domain-truth call only the owner can make. |
| 3 | **#6 — two scheduling rules (deadline → colour)** (2026-06-26) | The proposed order matches the deadline→colour intent **and** nobody misses the removed max-throughput lever | first real auto-schedule the manager runs | Ordering pinned by scheduler tests; "nobody misses the lever" is owner/operator feedback. |
| 4 | **#4 — manager sets shift length** (2026-06-26) | The planning shift and the recorded run shift stay consistent and the manager isn't entering the same fact twice | once #9 (persisted actual shift) is in **real use** | Defaults/honouring pinned by tests; the two-facts-consistency only shows in real use. |
| 5 | **#9 — persist actual shift, "good day"** (2026-06-26) | With recording live, a legitimately-short day is judged against 500/8 and no longer reads "bad" | once managers actually record day shifts in production | Control shipped (`ShiftToggle`) + `summarize_day` unit-tested. The measure-on-real-days outcome waits on usage. |
| 6 | **#10 — quantity-leak tripwire** (2026-06-26) | A real leak both flags + audits + force-closes, and is then **investigated** as an upstream-model bug (the decision is the alarm, not the fix) | first leak flagged in real production | Flag+audit+force-close pinned + live-verified on the 7/10→10/10 case. The "is it acted on as a tripwire" is a process outcome. |
| 7 | **#3 — completed orders leave the queue** (2026-06-26) | On a real completion, no completed order lingers on any board / station view; throughput-by-line stats stay intact | first real completion in production (after a fresh sim-verify of the live completion+queue path) | `list_planned_work_orders` filter + finalize slot-release covered by tests. A fresh confirming sim run + the first prod completion are still open. |

## Confirmed / resolved

| # | Decision | Confirmed | Evidence |
|---|---|---|---|
| #8 | `STOCK_NOT_ENTERED` surfaced on the board (frontend-review trigger) | 2026-06-30 | Chip "wpisz stan farby" `frontend/src/components/CapacityBoard.tsx:109`; type `frontend/src/types/manager.ts:157`. The 2026-06-27 frontend triage (A2) shipped it. |
| #9 (control) | Manager has a control to record the day's shift | 2026-06-30 | `ShiftToggle` `frontend/src/components/CapacityBoard.tsx:116` → `PUT /manager/day-shift-length` (`frontend/src/api/managerApi.ts:300`). The 2026-06-27 triage (A1) shipped it. (The *measure-on-real-days* outcome stays open — row 5 above.) |

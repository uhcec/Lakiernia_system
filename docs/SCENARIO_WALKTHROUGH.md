# Scenario Walkthrough — validate the workflow against the real factory (NA21)

Purpose: turn the **S01–S12 scenario matrix** from internal-consistency-only (proven by tests) into
**shop-floor-confirmed** policy. Walk each scenario in the running app with someone who knows the
process, and tick whether the modeled behaviour matches reality. Tests prove the code is consistent;
this proves it is *correct*.

> When a scenario does **not** match the shop floor, do not change code on the spot — note it here and
> raise it with the owner; the fix flows back through `docs/WORKFLOW.md` first (see `WORKING_CONTRACT.md`).
> The authoritative behaviour is `docs/WORKFLOW.md` "Scenario Matrix S01-S12"; this is the field guide.

## Setup

```powershell
python scripts/reset_and_seed_dev_db.py     # clean seeded state (APP_ENV=development)
uvicorn app.main:app --reload               # backend
# in frontend/: npm run dev                 # http://127.0.0.1:5173
```

Dev logins (full table in `README.md` → Login). Each station panel is its own login/route:

| Station | Login / pass | Route |
|---|---|---|
| Office | `biuro` / `bi1` | `/zlecenia` |
| Manager | `kierownik` / `ki1` | `/kierownik` |
| Surface prep | `przygotowanie` / `prz1` | `/przygotowanie` |
| Hanging | `zawieszanie` / `zaw1` | `/zawieszanie` |
| Manual production | `produkcja-reczna` / `rec1` | `/produkcja-reczna` |
| Automatic production | `produkcja-automat` / `aut1` | `/produkcja-automat` |
| Packing | `pakowanie` / `pak1` | `/pakowanie` |
| Decoral | `decoral` / `dec1` | `/produkcja-decoral` |

## Reusable steps (referenced below)

- **CREATE(coating, prod?, qty, m²):** Office `/zlecenia/nowe` → fill customer, coating (RAL/Decoral),
  paint, `total_quantity`, `total_area_m2`, profiles/accessories. (Mark Ocynk/Przemalowanka if testing
  those.) Save.
- **PLAN(manual|automatic):** Manager `/kierownik` → assign production type + queue position.
- **PREP(counted):** Surface prep `/przygotowanie` → start, then finish with the **counted** quantity
  (this becomes the operational quantity — confirm the station now shows the counted number, NA26).
- **HANG:** Hanging `/zawieszanie` → start, finish (automatic only).
- **PRODUCE:** Manual production `/produkcja-reczna` → start, finish (manual only; automatic has no
  manual production action).
- **PACK_OK(qty):** Packing `/pakowanie` → "Rozpocznij pakowanie", enter counted = OK, 0 corrections,
  complete.
- **PACK_CORR(ok, corr, reason, profiles/acc split):** Packing → counted = ok+corr, enter correction
  quantity + reason category + profile/accessory split, complete (creates the correction representation).
- **DECORAL:** Decoral `/produkcja-decoral` → start, finish.
- **PLAN_CORR:** Manager plans the correction (RAL: the same order is back in planning; Decoral: the
  child "P…" order) — it skips surface prep; manual starts at production, automatic at hanging.

## The scenarios (confirm each)

For each: drive it, then confirm the **Expected final state** matches reality. Mark `OK` / `MISMATCH`
+ notes. Expected states are from `docs/WORKFLOW.md`.

### S01 — RAL · MANUAL · no correction
Steps: CREATE(RAL, qty Q) → PLAN(manual) → PREP(Q) → PRODUCE → PACK_OK(Q).
Expected: `process_status = READY`; completed = Q, active = 0; no child.
Confirmed on shop floor? ☐ OK ☐ MISMATCH — notes: …

### S02 — RAL · AUTOMATIC · no correction
Steps: CREATE(RAL) → PLAN(automatic) → PREP(Q) → HANG → PACK_OK(Q). (PRODUCTION is a preview, no manual action.)
Expected: READY; completed = Q, active = 0; no child.
Confirmed? ☐ OK ☐ MISMATCH — notes: …

### S03 — DECORAL · MANUAL · no correction
Steps: CREATE(Decoral) → PLAN(manual) → PREP(Q) → PRODUCE → PACK_OK(Q) → DECORAL.
Expected: READY only after the Decoral pass; completed = Q, active = 0; no child.
Confirmed? ☐ OK ☐ MISMATCH — notes: …

### S04 — DECORAL · AUTOMATIC · no correction
Steps: CREATE(Decoral) → PLAN(automatic) → PREP(Q) → HANG → PACK_OK(Q) → DECORAL.
Expected: READY only after Decoral; completed = Q, active = 0; no child.
Confirmed? ☐ OK ☐ MISMATCH — notes: …

### S05 — RAL · MANUAL · correction after packing
Steps: CREATE(RAL) → PLAN(manual) → PREP(Q) → PRODUCE → PACK_CORR(ok, corr) → PLAN_CORR(manual) →
PRODUCE → PACK_OK(corr).
Expected: **same order** reset to planning with a `CORRECTION` batch (no child order); READY after the
correction round closes; final completed = Q.
Confirmed? ☐ OK ☐ MISMATCH — notes: …

### S06 — RAL · AUTOMATIC · correction after packing
As S05 but automatic; the correction returns via HANG (not production).
Expected: same-order `CORRECTION` batch, no child; READY after the round; completed = Q.
Confirmed? ☐ OK ☐ MISMATCH — notes: …

### S07 — DECORAL · MANUAL · correction after packing
Steps: CREATE(Decoral) → PLAN(manual) → PREP → PRODUCE → PACK_CORR(ok, corr). The OK part continues on
the root's single Decoral pass; a **child "P…" order** is created for the corrected pieces →
PLAN_CORR(manual) → PRODUCE → PACK (child) → its OK returns to the **root's** Decoral pass → DECORAL.
Expected: one Decoral pass **on the root**; child closes at packing and rejoins the root's Decoral;
parent shows "N" (decoral-incomplete) until corrections return; READY after all returned pieces finish
the root Decoral; parent completed = Q.
Confirmed? ☐ OK ☐ MISMATCH — notes: …

### S08 — DECORAL · AUTOMATIC · correction after packing
As S07; the child routes automatic (HANG → PACK). Still **one Decoral pass on the root**.
Expected: as S07, automatic child route; READY after both close; parent completed = Q.
Confirmed? ☐ OK ☐ MISMATCH — notes: …

### S09 — RAL · MANUAL · multi-round correction
As S05 but run **two+ correction rounds** on the same order (each a new `CORRECTION` batch).
Expected: no child orders; READY after all rounds close; completed = Q.
Confirmed? ☐ OK ☐ MISMATCH — notes: …

### S10 — RAL · AUTOMATIC · multi-round correction
Automatic variant of S09 (rounds return via HANG).
Expected: no child orders; READY after all rounds; completed = Q.
Confirmed? ☐ OK ☐ MISMATCH — notes: …

### S11 — DECORAL · MANUAL · multi-round correction
As S07 but multiple rounds: each child closes at packing and returns OK to the root's single Decoral
pass; only the root runs Decoral; corrections are **flat children of the root**.
Expected: parent blocked until all descendants close; READY after the root Decoral finishes the
returned pieces; root completed = Q.
Confirmed? ☐ OK ☐ MISMATCH — notes: …

### S12 — DECORAL · AUTOMATIC · multi-round correction
Automatic variant of S11 (children return via HANG → PACK); still one Decoral pass on the root.
Expected: as S11 with automatic child routing.
Confirmed? ☐ OK ☐ MISMATCH — notes: …

## Cross-cutting checks (confirm once)

- **Operational quantity (NA26):** when PREP counts fewer than ordered, downstream stations show the
  **counted** quantity as "Sztuki", while office/manager see declared + counted + difference. ☐ OK ☐ MISMATCH
- **Packing capacity:** an automatic order reserves packing at HANG start; a manual operator can open a
  2nd slot via override (warning shows the reserving automatic's piece count); a 2nd automatic queues. ☐ OK ☐ MISMATCH
- **Station presence / attribution:** check yourself in on a station ("Obsada stanowiska"), perform an
  action, then confirm the work-order audit history shows you as the operator. ☐ OK ☐ MISMATCH
- **Przemalowanka:** skips surface preparation, standalone order. ☐ OK ☐ MISMATCH
- **Ocynk:** behaves like a normal order, just marked OCYNK. ☐ OK ☐ MISMATCH
- **Throughput stats:** Statystyki shows the total and the two cross-sections (method, coating) summing
  to it; Przejazd Decoral is separate. ☐ OK ☐ MISMATCH

## After the walkthrough

- Record any MISMATCH with the owner; update `docs/WORKFLOW.md` first if policy differs, then code +
  tests. Update `IMMEDIATE_NEXT_ACTIONS.md` (NA21) with the confirmation date and outcomes.

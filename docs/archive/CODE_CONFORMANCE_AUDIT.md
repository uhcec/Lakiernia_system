> ARCHIVED — frozen historical snapshot as of 2026-06-24. Living truth lives in docs/WORKFLOW.md /
> docs/FACTORY_DOMAIN_MODEL.md. This is a disposable scratch artifact (cadence policy:
> docs/DOCUMENTATION_MAP.md "Audit cadence policy"). Actionable divergences live in
> IMMEDIATE_NEXT_ACTIONS.md as NA* items, not here.

# Code Conformance Audit (the NA25 process)

Run date: **2026-06-24.** Read-only pass auditing the **code** against the reconciled documentation.
Per documented topic: a verdict + `file:line` evidence. **No code was changed.**

This run deliberately focuses on everything the docs gained **since the prior snapshot (2026-06-17)** —
the entire **NA49 multi-day capacity planner family** (N49-1…N49-10) and the **NA50 "good day" stats** —
because the stable pre-planner core was already audited in the 2026-06-17 pass and is now pinned by the
deterministic guardian + the scenario-matrix tests (see "Relied-on-evidence" below).

Verdict legend: **CONFORMS** (code matches docs, read directly) · **DIVERGES** (code contradicts docs)
· **DOC-UNDERSTATES / DOC-STALE** (code correct/broader; a doc narrower/stale) · **RELIED-ON-EVIDENCE**
(not re-read line-by-line this pass; trusted closed items + green tests, noted as such).

## Baseline (this run)

- `tests/test_documented_invariants.py` (fast guardian) — **5 passed.** No pinned constant has drifted
  (paint threshold/divisors, packing slot default, JWT expiry, bcrypt limit, JWT-secret guard).
- Full backend suite — **576 passed** (~5m19s). `alembic check` — clean ("No new upgrade operations").

## Summary

- **No NEW actionable divergences.** Every documented planner/measurement topic the code implements
  **conforms** to its owning doc; the divergences that exist were already found by the 2026-06-24 N49
  code review and are logged as **NA51–NA57** (and confirmed again in code below — not re-logged).
- The pure planner core (`measurement.py`, `capacity.py`, `colour.py`, `placement.py`, `good_day.py`,
  `paint_feasibility.py`, `shared_stage.py`) is DB-free and matches `docs/WORKFLOW.md` "Target planning
  model" + `docs/FACTORY_DOMAIN_MODEL.md` §7 line-for-line.
- **NA42** (AUTOMATIC has no `PRODUCTION` stage row, reconciled at planning) is implemented as the doc
  now describes — this *reverses* the prior snapshot's "PRODUCTION present as a non-actionable preview"
  wording, which predated NA42.
- One **minor, non-actionable observation** (residual NA42 preview-stage guards) recorded below; not
  worth an NA item.

## Topic-by-topic (this run's focus: the planner family)

### N49-2 measurement engine — CONFORMS
`app/manager/measurement.py`: effective rate = total m² ÷ **union** of `[hanging_start, packing_done]`
intervals (`_union_seconds:66`, `measure_automatic_rate:86`), seed `57.0` m²/h until
`MIN_RATE_SAMPLE_ORDERS = 3` passes (`:35-37`); statistical changeover = avg changed-colour inter-start
gap − same-colour gap, clamped ≥ 0, seed `20.0` min, confirmed `15/30`-min bands exposed as `band_*`
(`estimate_colour_changeover:121`, `:39-47`). Matches WORKFLOW "Target planning model" (N49-2) +
FACTORY_DOMAIN_MODEL §7 "Measurement signals".

### N49-3 day capacity (floor + ceiling) — CONFORMS
`app/manager/capacity.py`: floors `800/500` (`FLOOR_LONG/SHORT_M2:32-33`), **gross** booth ceiling
`80` m²/h × `14/8` h (`CEILING_BOOTH_RATE_M2_PER_H:40`), colour change → m² of net ceiling lost
(`changeover_loss_m2:107`, `compute_day_capacity:156`), `advise_shift_length:147` long iff ≥ long floor.
The gross-vs-effective-rate distinction (80 here vs ≈57 in measurement) is documented in both the code
docstring and WORKFLOW. Matches FACTORY_DOMAIN_MODEL §7 "daily norm is a FLOOR".

### N49-4 deadline-feasible placement — CONFORMS
`app/manager/placement.py`: EDF `sorted((planned_pickup_date, work_order_id)):158`, greedy fill to the
day's **net** ceiling (`net_ceiling:154`), oversized order placed alone + `over_ceiling`, per-order
`meets_deadline`/`days_late` + `infeasible_order_ids` (`:200-227`). Working-day calendar skips Sat/Sun
(`DEFAULT_WEEKEND_WEEKDAYS:43`, flagged ASSUMPTION). Matches WORKFLOW (N49-4). *(Mon–Fri assumption =
already-logged NA56.)*

### N49-5 light→dark sweep + N49-6 size+direction changeover cost — CONFORMS
`app/manager/colour.py`: `ral_lightness:88` (single documented helper, group map + full-code anchors;
the flagged open colour-family question), `light_to_dark_order:118` groups identical colours then sweeps
lightest→darkest, `sequence_changeover_minutes:157` / `average_changeover_minutes:178` walk the swept
sequence (same colour = 0). N49-6 `changeover_minutes_for_transition` (`capacity.py:124`): ≤100 m² → 15
min band, >100 → 30 min, `light_to_dark_factor 0.5` else full band. Matches FACTORY_DOMAIN_MODEL §7
"Colour-changeover economics".

### N49-7 paint-stock hard block + forward view — CONFORMS (block boundary = logged NA54)
`app/manager/paint_feasibility.py`: `colour_series_blocked:82` = tracked **and** not manual-used **and**
`current_stock_kg <= 0`; `build_forward_view:91` walks demand down per colour series → OK / WARNING
(partial shortfall or manual-used low-confidence) / BLOCKED. Plan-time gate
`_assert_paint_available_for_automatic` refuses an out-of-stock metered colour on AUTOMATIC; never-stocked
placeholder (no movement history) not blocked (`_paint_has_stock_history:1300`). Matches WORKFLOW (N49-7).
The "block is binary on starting stock, not demand-aware" design choice is already raised as **NA54**.

### N49-8 line-assignment lever — CONFORMS
`app/manager/colour.py::suggest_line:214`: small (≤100 m²) **and** colour-orphan → MANUAL, else
AUTOMATIC; missing m² → not-small (AUTOMATIC default). Orphan decided across the whole line
(`colour_neighbour_counts:194`, wired `service.py:1170-1181`). Suggestion only; manager overrides via
the existing planning endpoints. Matches FACTORY_DOMAIN_MODEL §7 "Line choice".

### N49-10 shared-stage derivation (surface prep / packing) — CONFORMS
`app/process/shared_stage.py::derive_surface_preparation_order:49`: interleave by **smaller
prepared-but-not-yet-painted buffer**, tie → AUTOMATIC (`min(... line is not AUTOMATIC):80-83`), buffer
in pieces (flagged assumption). Read model exposes `shared_stage_line_label` + `is_next_at_shared_stage`
(`app/process/schemas.py`), rendered as the line label + "NASTĘPNE" (frontend `StageWorkOrdersPage.tsx`
/ `PackingWorkOrdersPage.tsx`) instead of a colliding `Poz.`. Matches WORKFLOW "Shared-stage ordering".

### NA50 "good day" stats — CONFORMS to its own spec; inherits the logged NA52/NA53 cost defects
`app/manager/good_day.py` (`summarize_day:73` / `summarize_period:119`) computes m² vs floor + `met_floor`
+ shortfall, on-time %, changeover loss (shared `changeover_loss_m2`), utilisation/idle, period roll-up —
all matching WORKFLOW "Good day stats". Two **already-logged** wiring defects confirmed in the service:
the per-day rate uses `measure_automatic_rate(day_passes)` which almost always falls back to the seed
(**NA53**, `service.py:885`), and the changeover loss is valued with the inflated learned
`estimated_changeover_minutes` (**NA52 #2**, `service.py:898,936`).

### NA42 — AUTOMATIC has no PRODUCTION stage row — CONFORMS (reverses the 2026-06-17 wording)
`reconcile_stage_states_to_route` (`app/process/service.py:136`) trims rows to the actionable route once
the method is known (AUTOMATIC drops `PRODUCTION`, MANUAL drops `HANGING`); called at planning
(`manager/service.py:1441,1579`). `get_actionable_stage_sequence_for_work_order:1449` excludes
`PRODUCTION` for AUTOMATIC. Matches the WORKFLOW NA42 note. The prior snapshot's "PRODUCTION present as a
non-actionable preview" was pre-NA42 and is now superseded.

## Divergences (this run)

**None newly found.** The planner's known divergences were swept by the 2026-06-24 N49 code review and
are confirmed in code above; they remain open as already-logged items — do **not** double-log:

- **NA52** — the multi-day board sizes day net-ceilings with the contaminated *learned* changeover
  estimate (`service.py:1163`, surfaced `:1258`) while displaying the bounded N49-6 per-day value
  (`:1199,1244`); good-day stats inherit the same inflation (`:898,936`). CONFIRMED.
- **NA53** — good-day per-day "effective booth rate" almost always shows the seed (`service.py:885`,
  `MIN_RATE_SAMPLE_ORDERS = 3` rarely met within one day). CONFIRMED.
- **NA54** — paint hard-block is binary on `current_stock_kg <= 0`, not demand-aware
  (`paint_feasibility.py:88`). CONFIRMED.
- **NA55/NA56/NA57** — CapacityBoard AUTOMATIC-only + mount-only fetch; Mon–Fri + full day-0 calendar
  assumption (`placement.py:43`, `service.py:1152`); one advised shift length stamped on every day
  (`service.py:1140`, `placement.py:150`). CONFIRMED in code.
- **NA51** — the multi-day board (EDF + light→dark) and the executable per-line `queue_position` are two
  decoupled orderings with no apply path. CONFIRMED (board ignores `queue_position`).

## Notes / non-divergences worth recording

- **Residual NA42 preview-stage guards (minor, non-actionable).** `_is_automatic_production_preview_stage`
  (`app/process/service.py:1456`) still returns `True` for AUTOMATIC + `PRODUCTION` and is referenced in
  ~6 places (`:410,444,500,1098,1269,2472`). After `reconcile_stage_states_to_route` an AUTOMATIC order
  has **no** `PRODUCTION` row, so these guards are now defensive/legacy belt-and-suspenders rather than
  load-bearing. The NA42 doc note's "removes the phantom stage special-cased everywhere" slightly
  overstates the cleanup. Harmless; fold the guards out opportunistically when next touching those paths
  — not worth its own NA item.
- No code change was made under this audit (read-only, per the task).

## Relied-on-evidence (not re-read this pass)

The stable pre-planner core was audited line-by-line on 2026-06-17 and has not been the subject of the
intervening work; it is trusted here from that pass + the green guardian + the 576-test suite +
`alembic check` clean:

- Stage model & sequences, `process_status`/READY derivation, reopen-409, the RAL/DECORAL correction
  split + S01–S12 matrix, resource locks / packing N-slot model, authorization (NA1), queue
  stale-revision (per-line), throughput / cycle-time / WIP-aging, paint inventory & consumption,
  additional work types, external number, completed release, JWT/config/bcrypt/SQLite pragmas,
  idempotency/concurrency, attachments, audit, QC document generation, frontend historical display.
- NA26 (operational quantity at stations) — fixed 2026-06-17, `operational_quantity` present on the
  station read model; trusted from that closure + tests.

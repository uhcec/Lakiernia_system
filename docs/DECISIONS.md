# Domain decisions log (append-only)

*Why* a domain decision was made. New entries at the bottom. Each entry cites the change it
implements (`CHANGES.md #n`) and the owner confirmation behind it. Method per `CLAUDE.md`.

## Entry template

Every entry carries these fields (a field may say "none" but is never silently dropped):

- **Decision** — what we settled on, concretely.
- **Why** — the owner-confirmed rationale (the factory *why* you cannot read from code). Cite the
  confirmation date + `CHANGES.md #n`.
- **Rejected** — the alternative(s) we considered and did **not** take, and why. This is what stops a
  future reader (human or a fresh session) from silently undoing a deliberate trade-off.
- **Implementation notes** — how it lands in code (`file:line`, migrations, compatibility).
- **Expected** — the observable consequence we expect, stated so it can later be checked. Turns the
  ADR from a record of the past into a feedback loop (per the architectural-memory method).
- **Review-by** — the date or trigger at which we look back to confirm the decision actually worked.

> Fields **Rejected / Expected / Review-by** were added to the template on **2026-06-27**. Entries
> below from 2026-06-26 were backfilled the same day — *only* from rationale already grounded in their
> own Why/notes or in code; nothing new about the factory was invented in the backfill.

---

## 2026-06-27 — #2 / A5: make the second, separate Decoral pass visible

**Decision:** on the Decoral station, a card that is the **returned-pieces second Decoral pass** gets a
distinct badge **"DRUGI PRZEBIEG · poprawione sztuki"**. The signal (no backend change) is a *partial*
Decoral batch (`batch_is_partial`) on the root order with **no open corrections left**
(`!is_decoral_incomplete`, `!is_correction`) — encoded as the pure predicate `isReturnedDecoralPass`. The
**first** pass (OK pieces painted while a correction is still out) is deliberately **not** badged.

**Why** — owner-confirmed **2026-06-27** (completing `CHANGES.md #2`, triage **A5**). Factory why: when
corrected pieces come back after the root's Decoral was already finished, they form a fresh Decoral batch
(`app/process/service.py:2060-2091`) — a correct but easy-to-miss "second pass". A Decoral operator could
mistake the returned pieces for the original run. The owner wanted exactly that returned-pieces card called
out, and chose the **narrowest** form (one badge, second pass only) over also labelling the first pass.

**Rejected:**
- *Use the `N` / `is_decoral_incomplete` marker as the signal* — rejected: `N` means "root still has open
  corrections" (the **first** pass while pieces are out), not the returned second pass; after the pieces
  return the correction closes and `is_decoral_incomplete` goes false. Using it would badge the wrong card.
- *Badge both passes differently* (e.g. "Sztuki OK · część w poprawce" + "Drugi przebieg") — considered and
  rejected by the owner as more UI than #2 asks for.
- *`batch_is_partial` alone* — insufficient: the first pass's OK batch is also partial
  (`app/process/service.py:2031`), so partiality alone can't tell first from second pass; the
  `!is_decoral_incomplete` clause is what distinguishes the returned pieces.

**Implementation notes:**
- `isReturnedDecoralPass(workOrder)` in `frontend/src/utils/workOrderDisplay.ts`, unit-tested
  (`workOrderDisplay.test.ts`); badge rendered in `frontend/src/components/DecoralWorkOrdersPage.tsx`.
- Signal verified against the backend's authoritative scenario-2 test
  (`tests/test_process_service.py::test_decoral_correction_returns_to_root_decoral_scenario2_park`): the
  returned batch is the root's active partial Decoral batch, created only after the correction closed.
- Pure presentation; no backend or API change.

**Expected:** the Decoral operator sees "DRUGI PRZEBIEG · poprawione sztuki" only on returned-pieces cards;
a normal Decoral order and the first (corrections-pending) pass show no such badge.

**Review-by:** the owner's next look at a real correction round at the Decoral station — confirm the badge
appears on the right card and the wording reads clearly on the shop tablet.

---

## 2026-06-27 — A1: per-day shift length drives the plan (frontend + planner)

**Decision:** the manager sets each day's shift length (LONG/SHORT) from the capacity board; the value
is persisted per day (`day_shift_lengths`) and is the **single source of truth** read by **both** the
forward multi-day plan and the "good day" stats. A day's shift drives its floor/hours **and** the fill —
a SHORT day's smaller net ceiling holds less and pushes overflow onto later days. A day with no stored
value defaults to **LONG** (judged against 800). The old load-derived per-day advisory
(`display_shift_for`, NA57) is removed.

**Why** — owner-confirmed **2026-06-27** (this session, completing `CHANGES.md #4/#9` and triage item
**A1** in `docs/FRONTEND_TRIAGE.md`). Two questions were put to the owner: *what should setting a day's
shift affect?* → **the plan and the stats, persisted** (one coherent control, not an ephemeral toggle);
and *how to judge a day the manager hasn't set yet?* → **default LONG / 800**, no guessing. Factory why:
a short day physically runs fewer booth hours, so the plan must hold less and shift work forward to stay
truthful; and an unset day must not be silently shrunk to "look OK" — the manager declares the day's
length as an explicit operational fact (consistent with #4 dropping all advising).

**Rejected:**
- *Plan-only, ephemeral* (pass `shift_length` as a query param to the plan): the board would react but
  nothing persists and good-day stats stay blind — rejected as a second, drifting mechanism.
- *Stats-only, persisted* (PUT day-shift-length but the plan ignores it): the plan would keep showing
  LONG regardless of what the manager set — rejected as a board that lies.
- *Keep `display_shift_for`'s load-derived SHORT relabel*: rejected — it is exactly the kind of advising
  #4 removed, and it silently re-judged under-filled days as short, hiding genuine below-floor days.

**Implementation notes:**
- `place_orders` gains `day_shifts: Sequence[ShiftLength] | None` aligned to `working_days`; per-day
  effective shift sizes each day's gross ceiling/floor in the FILL and labels it. `display_shift_for`
  deleted. `app/manager/placement.py:134-198`.
- `get_multi_day_plan` builds the per-day map from `list_day_shift_lengths(...)` (default LONG) and drops
  its `shift_length` param; `get_day_capacity` reads `get_day_shift_length(today)`. The `shift_length`
  query param is removed from `/manager/planner/multi-day` and `/planner/day-capacity`.
  `app/manager/service.py:1123-1124`, `1248-1252`; `app/manager/router.py`.
- Frontend: `ShiftToggle` on each capacity-board day column → `PUT /manager/day-shift-length?day=…` →
  refetch. `frontend/src/components/CapacityBoard.tsx`, `frontend/src/api/managerApi.ts`.
- Tests: `tests/test_placement.py` (per-day shift drives fill + judging), `test_multi_day_plan_service.py`
  ::`test_plan_honours_the_manager_set_shift_for_a_day`, `test_day_capacity_service.py`
  ::`test_day_capacity_reads_the_persisted_shift`. Verified live over HTTP: setting day 0 SHORT flipped
  the plan's day shift LONG→SHORT and floor 800→500.

**Expected:** marking a day SHORT re-sizes its column (holds less, overflow forward) and judges it
against 500/8; unset days read LONG/800; the value is per-day and **shop-wide** (the table is keyed by
day only), so both lines share a day's shift.

**Review-by:** the owner's next look at the board — confirm a day no longer reads "poniżej progu" once
marked short, and that overflow lands where expected; also confirm sharing one shift across both lines
matches the floor reality.

---

## 2026-06-26 — CHANGE #6: two scheduling rules (deadline → colour)

**Decision:** the painting auto-scheduler keeps only two ordering rules — `DEADLINE` and `COLOUR` —
with the default priority **deadline → colour**. The third rule, "maksymalny przerób" / max-throughput
(`ScheduleRuleKey.CHANGEOVER`, largest single-colour run first), was removed.

**Why:** owner-confirmed 2026-06-26 (CHANGES #6). Max-throughput optimised for booth m²/day but the
owner plans by promise dates first and colour-grouping second; the third rule added a lever nobody
tuned and competed with the deadline intent.

**Rejected:** keeping CHANGEOVER as an optional third rule the manager could switch on — rejected
because it was an untuned lever that actively competed with the deadline intent (the owner plans by
promise dates first), so it could only ever pull the schedule away from what the owner wanted.

**Implementation notes:**
- `ScheduleRuleKey.CHANGEOVER` and its catalog row removed; `DEFAULT_RULE_ORDER` is now
  `(DEADLINE, COLOUR)` (catalog tuple order = default order).
- `_colour_group_totals` and the CHANGEOVER sort branch dropped from `scheduler.py`;
  `SchedulableOrder.total_area_m2` removed (it only fed that rule).
- **Backward compatibility:** a stored auto-schedule config that still lists `"changeover"` degrades
  gracefully — `_resolve_rule_config` already drops unknown keys, so no DB migration is needed.
- **Frontend (unreviewed):** `frontend/src/types/manager.ts` may still type a `'changeover'` rule key;
  it sends back whatever GET returns (now only deadline/colour), so it works at runtime. Clean up the
  type when the frontend is reviewed.

**Expected:** scheduler proposals order by deadline then colour and never by single-colour run length;
a stored config naming `"changeover"` loads without error (the key is silently dropped).

**Review-by:** the first real auto-schedule the manager runs after this — confirm the proposed order
matches the deadline→colour intent and nobody misses the throughput lever.

## 2026-06-26 — CHANGE #5 + #7: colour planning = grouping identical colours

**Decision:** within-day colour planning is just **grouping identical colours**. A colour change costs
the **size band only** (≤100 m² → 15 min, >100 m² → 30 min); the **light→dark direction discount** and
the **RAL-code-derived lightness sweep** are both removed. Group order is deterministic (alphabetical
by colour identity, "no colour" last) — it does not affect the colour-change count.

**Why:** owner-confirmed 2026-06-26 (CHANGES #5, #7). The factory does not pay a cheaper changeover for
a light→dark move (the direction factor was an unvalidated model assumption), and the per-colour
"lightness" was *guessed* from the RAL code — a guess dressed as data, exactly the kind of invented
domain fact `CLAUDE.md` forbids. Without lightness there is nothing to sweep, so colour planning
collapses to grouping identical colours, which is all the owner wanted.

**Rejected:** keeping the light→dark direction discount and the RAL-code lightness sweep (even
"corrected" with better lightness data) — rejected because the factory pays no such direction
discount (unvalidated assumption) and the lightness was guessed from the RAL code, not measured.
Keeping either would dress invented data as fact.

**Implementation notes:**
- Shipped together because they are coupled: `sequence_changeover_minutes` fed the direction factor
  with `ral_lightness`, so neither could go alone.
- `capacity.py`: dropped `CHANGEOVER_LIGHT_TO_DARK_FACTOR` and the `light_to_dark` parameter of
  `changeover_minutes_for_transition`.
- `colour.py`: deleted `ral_lightness` + the `_RAL_GROUP_LIGHTNESS` / `_RAL_CODE_LIGHTNESS` tables;
  renamed `light_to_dark_order` → `group_identical_colours`; `ColourOrderable` / `SequencedOrder` lost
  their `ral_code` field.
- `measurement.py`: `AutomaticPassObservation.ral_code` removed (it only fed the deleted lightness).
- The line-assignment lever (N49-8) and the paint-feasibility colour identity are unchanged — they use
  the colour *key*, not lightness.
- **Possible future cleanup:** `scheduler.py`'s COLOUR rule and `colour.group_identical_colours` now
  implement the same "group identical colours alphabetically" idea for two different callers (the
  manager's rule-based proposal vs. the capacity-costing sweep). Not unified now to keep the change
  targeted; worth revisiting if a third caller appears.

**Expected:** a colour change costs 15/30 min purely by size band, identical in both directions; no
code path reads a per-colour lightness; colour planning output is just identical colours grouped.

**Review-by:** when a **third** caller of "group identical colours" appears — revisit unifying
`scheduler.py`'s COLOUR rule with `colour.group_identical_colours` (the noted duplication).

## 2026-06-26 — CHANGE #4: manager sets the shift length (no advising)

**Decision:** the day-capacity / multi-day planner no longer advises LONG vs SHORT from the available
ready m². The **manager sets** the shift length explicitly (the `shift_length` query param). When the
caller omits it, the planner defaults to **LONG** (the full 07:00–21:00 day).

**Why:** owner-confirmed 2026-06-26 (CHANGES #4). The m²-based advice second-guessed a decision the
manager makes from real-world context (staffing, urgency) the system can't see; it was a guess the
manager just overrode. LONG is the safe default because it shows the most capacity/headroom — the
manager narrows to SHORT when they decide to run a short day.

**Rejected:** keeping the m²-based LONG/SHORT advice (even as a non-binding hint) — rejected because
it second-guessed a call the manager makes from staffing/urgency context the system can't see, so it
was a guess the manager just overrode. A default of SHORT was also rejected: LONG shows the most
headroom, so the manager narrows down rather than discovering hidden capacity.

**Implementation notes:**
- `advise_shift_length` deleted from `capacity.py`.
- `shift_advised` removed from `DayCapacityRead` / `MultiDayPlanRead` and the (unused) `manager.ts`
  type — the flag only existed to mark an advised shift, which no longer happens.
- Connects to CHANGE #9 (persist the *actual* shift length run, for the "good day" measure).

**Expected:** an omitted `shift_length` yields a LONG-day plan; the manager's explicit LONG/SHORT is
always honoured unchanged; no payload carries a `shift_advised` flag.

**Review-by:** once CHANGE #9 (persisted actual shift) is in real use — confirm the planning shift and
the recorded run shift stay consistent and the manager isn't entering the same fact twice.

## 2026-06-26 — CHANGE #10: quantity-leak tripwire made human-visible

**Decision:** when finalization detects a quantity-conservation leak (credited pieces ≠ total at
close), the order still force-closes to total (so work is never stuck), but the leak is now surfaced
to a human: a persisted `work_orders.quantity_leak_flagged` boolean (shown in the office + manager read
models) plus a SYSTEM audit event `work_order.quantity_leak_detected`. The technical log warning stays.

**Why:** owner-confirmed 2026-06-26 (CHANGES #10). A leak signals an upstream bug; the old behaviour
wrote it only to the server log, so a 7/10 → 10/10 silent auto-complete (verified live 2026-06-26) was
invisible to the shop. Force-closing is kept (don't trap the order) but it must be investigable.

**Rejected:** (a) leaving the leak in the server log only — rejected, it kept a real bug invisible to
the shop; (b) hard-blocking / refusing to close a leaking order — rejected, it would trap legitimate
work over a symptom. So: force-close **and** flag.

**Implementation notes:**
- Migration `20260626_0041` adds the column with `server_default 0`; the model also carries
  `server_default=text("0")` so raw-SQL inserts (the DB-constraint tests) and metadata-built schemas
  backfill existing/legacy rows.
- The flag is set inside `_finalize_completion_chain_if_ready`; `record_audit_event` is called with
  `station_context=None` → recorded under `StationId.SYSTEM` (no operator triggered it).
- This is a safety net, not the fix: the quantity model should prevent leaks in the first place. The
  flag is the tripwire that makes a model bug visible.

**Expected:** a leak both sets `quantity_leak_flagged` and emits the SYSTEM audit event while still
force-closing to total; the verified 7/10 → 10/10 case now shows the flag instead of closing silently.

**Review-by:** the first leak flagged in real production — treat it as a tripwire and investigate the
upstream quantity model (this decision is the alarm, not the fix).

## 2026-06-26 — CHANGE #1: a correction round must not lose pin/urgent

**Decision:** when a packing correction sends an order back to planning (replan-in-place), the live
`planning_priority` lock is still cleared (it can't sit on an unplanned order — DB constraint
`planning_priority_requires_planned`), but the manager's pin/urgent **intent is remembered** in a new
`pending_planning_priority` column and **re-applied** when the order is re-planned.

**Why:** owner-confirmed 2026-06-26 (CHANGES #1, a bug). A pinned/urgent order silently lost its
priority every time it bounced through a correction round, so the manager's intent evaporated exactly
when the order most needed to keep its place.

**Rejected:** relaxing the `planning_priority_requires_planned` constraint so an unplanned order could
hold its lock directly — rejected because the constraint encodes a real invariant (a priority is a
position in a queue the order isn't currently in). Parking the intent in a separate, unconstrained
column keeps the invariant intact.

**Implementation notes:**
- `pending_planning_priority` (migration `20260626_0042`) is deliberately NOT bound by
  `planning_priority_requires_planned`, so it can hold the intent through the unplanned window.
- Set in `_reset_to_correction_planning` (parks the live value before clearing it); consumed in
  `assign_plan` (re-applies, then clears the parked value). It is single-use per round.
- A deliberate **line switch** still clears the lock and does not restore (that path doesn't touch
  `pending_planning_priority`, which is only set by the correction round) — switching lines is an
  explicit "give up the slot" action, distinct from a correction bounce.

**Expected:** a pinned/urgent order that bounces through a correction round comes back re-pinned on
replan; a deliberate line switch does **not** restore the old lock.

**Review-by:** covered by regression test `test_correction_round_remembers_and_restores_pin`
(`tests/test_process_service.py`) — revisit if a second path ever parks into
`pending_planning_priority` (today only the correction round does).

## 2026-06-26 — CHANGE #8: flag untracked colours (STOCK_NOT_ENTERED)

**Decision:** a coloured order whose paint stock is not entered — no stock row, or only the 0-kg
auto-placeholder with no movement history — gets a distinct `PaintFeasibilityStatus.STOCK_NOT_ENTERED`
instead of a silent OK. It is surfaced (`stock_not_entered_order_ids`) but **never hard-blocked**. A
truly colourless order still reports OK (it makes no paint claim).

**Why:** owner-confirmed 2026-06-26 (CHANGES #8). Treating "we have no idea about this paint" as OK
hid exactly the gap the manager needs to act on ("enter the stock"); but we can't hard-block on the
unknown (the paint may well be there), so it's a visible-but-non-blocking state.

**Rejected:** (a) the status quo of reporting untracked colour as a silent OK — rejected, it hid the
exact gap the manager must act on; (b) hard-blocking the order on untracked colour — rejected, the
paint may physically be there, so blocking on the unknown would stop good work. Hence visible but
non-blocking.

**Implementation notes:**
- New enum value (string `"STOCK_NOT_ENTERED"`); the schema reuses the same enum, so it serialises
  automatically. **Frontend (unreviewed)** likely enumerates only OK/WARNING/BLOCKED — it will receive
  the new string and should add a badge for it when the frontend is reviewed.
- Two untracked situations both map to it: no stock row (`stock is None` with a non-null colour) and a
  present-but-untracked placeholder (`is_tracked False`). The hard-block predicate already excludes
  untracked colours, so nothing that was OK and safe becomes blocked.

**Expected:** an untracked coloured order reports `STOCK_NOT_ENTERED` and appears in
`stock_not_entered_order_ids` but is never blocked; a colourless order still reports OK; nothing
previously OK-and-safe becomes blocked.

**Review-by:** ✅ **resolved 2026-06-30** — the 2026-06-27 frontend triage (A2) added the "wpisz stan
farby" chip (`frontend/src/components/CapacityBoard.tsx:109`) and the enum value to the type
(`frontend/src/types/manager.ts:157`). The new string now renders distinctly. (Was: frontend review — add
a distinct badge.) See `docs/REVIEW_LEDGER.md`.

## 2026-06-26 — CHANGE #3: completed orders leave the queue

**Decision:** on completion (READY) an order leaves the line's **active queue and releases its
position**, but keeps the **line** it ran on. The planned invariant is loosened from "line and position
both set or both unset" to "a position requires a line (a line may exist without a position)". The
trailing/shuffle machinery that parked completed rows is deleted. Completed orders also drop off the
operator station views (manager + station both work the active queue only).

**Why:** owner-confirmed 2026-06-26 (CHANGES #3). Completed orders piled up as a trailing block, forcing
elaborate shuffle logic just to keep their positions valid while new orders were inserted (a recent NA60
500 came straight from that). Releasing the position removes the whole problem.

**Rejected:** (a) keeping completed orders parked in the queue and merely hiding them in the UI —
rejected, it kept two sources of truth about a queue position and preserved the trailing/shuffle
machinery; (b) nulling the line on completion — rejected, statistics split throughput by
`production_type`, so the line must survive. Hence: release the position, keep the line.

**Two dependencies the owner flagged, resolved:**
- **Statistics** split throughput by `WorkOrder.production_type`, so we could NOT null the line.
  Resolution: release only `queue_position` (+ planning lock), keep `production_type`. Stats untouched.
- **Operator stage views** keyed visibility off "is planned" (needs a position). Owner decided
  (2026-06-26) completed orders should disappear from station screens too — which the position release
  already produces, so no extra change.

**Implementation notes:**
- Migration `20260626_0043` swaps the check constraint (batch `recreate="always"`, full `ck_…` names).
- `_finalize_completion_chain_if_ready` releases the finalized order's slot AND every complete-for-display
  correction descendant's slot — a correction child completes by merging back into the parent (finalize
  runs on the PARENT), so the child would otherwise keep its position as a closed historical correction.
- `list_planned_work_orders` already filters `queue_position IS NOT NULL`, so completed orders fall out
  of the manager board and the scheduler set automatically once their position is released.
- **MUST sim-verify** the live completion+queue path before this is considered shippable (CLAUDE.md).

**Expected:** on completion the order releases `queue_position` + planning lock but keeps
`production_type`; the trailing/shuffle code is gone; completed orders are absent from the manager
board, the scheduler set, and the station views, while throughput-by-line stats stay intact.

**Review-by:** sim-verify the live completion+queue path (already required above) before shipping, then
confirm on the first real completion in production that no completed order lingers on any board.

## 2026-06-26 — CHANGE #9: persist the actual shift length per day for "good day"

**Decision:** the shift length the manager actually ran on a day is **persisted explicitly** (a new
`day_shift_lengths` row the manager sets, owner-chosen over deriving it from booth hours). The "good
day" measure judges each day against its persisted shift (floor 800/500 m², hours 14/8); a day with no
stored length falls back to LONG (the prior conservative bar).

**Why:** owner-confirmed 2026-06-26 (CHANGES #9). Measuring every past day against the long-day bar
unfairly marked legitimately-short days as "bad". The owner chose to record the run shift explicitly
(a deliberate operational fact) rather than infer it from worked hours, which can be noisy. Connects to
CHANGE #4 (the manager already sets the planning shift length).

**Rejected:** deriving the day's run shift from booth/worked hours — rejected as noisy (hours fluctuate
for reasons unrelated to whether it was a planned short day). The owner chose to record the shift as an
explicit operational fact instead.

**Implementation notes:**
- `day_shift_lengths` (migration `20260626_0044`): one row per day, `shift_length` as the enum value.
- `GET/PUT /manager/day-shift-length?day=…` read/record it (PUT is manager-gated + audited
  `manager.day_shift_length_set`); GET defaults unset days to LONG.
- `get_good_day_stats` loads the day→shift map once for the range and passes per-day floor/hours into
  the pure `summarize_day`.
- **Frontend (unreviewed):** needs a control for the manager to record the day's shift length; the
  backend endpoint is ready. Until then, all days default to LONG (current behaviour preserved).

**Expected:** a day with a recorded shift is judged against that shift's floor/hours (800/14 LONG,
500/8 SHORT); an unrecorded day falls back to the LONG bar; recording is manager-gated and audited.

**Review-by:** ⏳ **partially resolved 2026-06-30** — the control now exists (`ShiftToggle`,
`frontend/src/components/CapacityBoard.tsx:116`, shipped by the 2026-06-27 triage A1), so the manager *can*
record a day's shift. The remaining open half — confirm a legitimately-short day stops reading "bad" once
shifts are actually recorded in production — is tracked in `docs/REVIEW_LEDGER.md` (awaiting real use).

## 2026-06-27 — Remove the learned colour-changeover estimate (planner review)

**Decision:** delete the statistical "learned colour-changeover cost" (`estimate_colour_changeover`,
N49-2) entirely — the function, its `ColourChangeoverMeasurement` schema/seed constants, the
`changeover` field on `GET /manager/stats/line-measurements`, and the `_learned_changeover` helper. The
day-capacity `changeover_is_measured` flag is now `True` by construction (the shown figure is the
bounded size-band cost). Only the union-based **effective rate** is still learned in `measurement.py`.

**Why:** owner-decided 2026-06-27 during a planner correctness review. The estimate (avg inter-start
gap when colour changes − when it stays) summed gaps **across overnight/weekend boundaries** (only
negative gaps were filtered, `measurement.py`), so it learned idle time as "changeover" and inflated to
hundreds of minutes. Crucially it **drove nothing**: since NA52 both the multi-day plan and the
single-day capacity view size changeovers from the bounded N49-6 size bands
(`capacity.changeover_minutes_for_transition`); the learned estimate survived only as a diagnostic on
`/manager/stats/line-measurements` — an endpoint **no frontend view consumes**. So it was a misleading
number with no consumer. Given the choice (remove / fix the overnight contamination / leave), the owner
chose remove: the bounded figure that actually plans is the honest one to show.

**Rejected:** (a) *fix the method* — filter overnight/weekend gaps — rejected as polishing a metric
nothing reads and nothing plans on; (b) *leave it* — rejected as a live, misleading number.

**Implementation notes:**
- Deleted from `app/manager/{measurement.py, schemas.py, service.py}`; tests in
  `tests/test_measurement.py` + `tests/test_line_measurements.py` dropped; `tests/test_planner_
  changeover_bound_na52.py` reworked to pin "plan uses the bounded cost on a contaminated log" without
  asserting on the removed estimate.
- `GET /manager/stats/line-measurements` now returns `{production_type, date_from, date_to, rate}` —
  the `changeover` object is gone (no frontend consumer, so no UI change).

**Expected:** the planner is unchanged (it already used the bounded cost); the line-measurements
endpoint no longer exposes the inflated learned changeover; `changeover_is_measured` is always True.

**Review-by:** none required — pure removal of an unconsumed diagnostic; covered by the reworked NA52
regression + the full backend suite.

## 2026-06-27 — Remove the learned effective line rate too (planner review, part 2)

**Decision:** delete the last learned number in the planner — the "effective automatic line rate"
(`measure_automatic_rate`, seed 57 m²/h, ≥3-pass threshold), its `LineRateMeasurement` /
`LineMeasurementStats` schemas, the whole `app/manager/measurement.py` module, the `GET /manager/stats/
line-measurements` route, and the `rate_m2_per_h` / `rate_is_measured` fields on the good-day totals
(plus the "Tempo kabiny" tile in `StatystykiPage`). The honest wall-clock **occupancy** measurement the
idle/utilisation diagnostic needs (`union_active_hours`, the union of each pass's hanging→packing
interval) is kept and moved into `good_day.py` — that is a plain measurement, not learning (no seed,
no threshold).

**Why:** owner-decided 2026-06-27, continuing the planner review that removed the learned changeover
(above). The owner's concern: the "it learns" features feel **premature and possibly unnecessary** for
where the shop is. Verified on the code: the learned rate **drives no planning decision** — the
multi-day plan and single-day capacity ceilings use the fixed gross booth constant (80 m²/h,
`CEILING_BOOTH_RATE_M2_PER_H`), the floors (800/500), the manager-set shift, and the size-band
changeover (15/30 min). The learned rate surfaced in exactly two read-only places: a "zmierzone /
szacunkowo" badge in the Statystyki panel, and `/manager/stats/line-measurements` — a route **no
frontend consumes** (already noted above). So it was a second informational-only learned number with a
seed/threshold whose only effect was a stats badge that could mislead ("szacunkowo, za mało
przejazdów") about a figure that changes nothing. Given remove / keep-in-stats / show-a-fixed-number,
the owner chose remove: don't carry an adaptive estimate the factory doesn't yet need.

**Rejected:** (a) *keep it in the good-day panel* — rejected; the owner doesn't want a learned
throughput readout yet, and it never fed a decision. (b) *replace with a raw observed rate (no seed/
threshold)* — rejected as the same thing in lighter clothing; if a measured throughput is wanted
later it can be reintroduced deliberately, against a real need.

**Implementation notes:**
- `app/manager/measurement.py` deleted; `AutomaticPassObservation` + `union_active_hours` (the union
  arithmetic) moved into `good_day.py`, its only consumer. `get_good_day_stats` now computes the day's
  `active_hours` via `union_active_hours`; utilisation / idle are unchanged.
- Dropped tests `test_measurement.py`, `test_line_measurements.py`, and the two `rate_*` cases in
  `test_good_day_service.py`; added `union_active_hours` overlap/idle/empty cases to `test_good_day.py`
  (the moved subtle path).
- SPEC unchanged: the learned rate was never confirmed into `SPEC.md` (it lived only in code + the
  stats panel), so there is no spec line to retract. `§9` line 125 ("60–100 m²/h, midpoint 80") is the
  fixed ceiling and stays true.
- Doc-drift swept in the same PR: stale `docs/FACTORY_DOMAIN_MODEL.md §7` citations (a deleted doc) and
  the now-false "the changeover cost is learned in measurement.py" claims in `capacity.py` / `service.py`
  / `placement.py` / `good_day.py` / `schemas.py` were corrected to point at `docs/SPEC.md §9/§11` and
  to describe the bounded size-band cost.

**Expected:** the planner is byte-for-byte unchanged (it never read the learned rate); the Statystyki
panel loses the booth-rate tile; the dead line-measurements route is gone. 601 backend tests + 134
frontend tests green, `tsc -b` clean.

**Review-by:** none required — removal of an unconsumed/stats-only learned number; the kept occupancy
measurement is pinned by new unit tests and the full suite.

## 2026-06-29 — Drop the per-change changeover surface + the always-true "measured" flag (planner review)

**Decision:** stop carrying the per-change changeover **minutes** as a model parameter and a read-model
field, and delete the always-`True` `changeover_is_measured` flag. The day-capacity and good-day models
now take the **total** changeover minutes directly (`changeover_loss_m2` is a pure `minutes → m²`
function); the read models expose only the two numbers any UI actually shows — `changeover_count` (how
many colour changes) and `changeover_loss_m2` (the m² of net ceiling they burn). Removed fields:
`DayCapacityRead.changeover_minutes` / `changeover_minutes_total` / `changeover_is_measured`,
`GoodDayMetricsRead.changeover_minutes_total`, `GoodDayStats.changeover_minutes_each` /
`changeover_is_measured`, `PlannedDayRead.changeover_minutes`, `MultiDayPlanRead.changeover_minutes` /
`changeover_is_measured` (and the matching TS types).

**Why:** owner-decided 2026-06-29, continuing the planner review that removed the two learned estimates
(above). Two leftovers from before the changeover cost became a real size-dependent **total** (CHANGES
#5/#6): (a) the size-aware total was being divided by the change count into a per-change *average*, then
handed to a model that multiplied it back by the count to recover the total — a pure round-trip
(`count × average ≡ total`); (b) `changeover_is_measured` was the last vestige of the old learned-vs-seed
distinction and was hardcoded `True` everywhere. Verified on the frontend: none of the per-change /
total minute fields nor the flag are rendered anywhere — the board shows `changeover_count`, Statystyki
shows `changeover_loss_m2`. So they were dead API weight whose only effect was inviting future drift.
Given remove-the-dead-fields-too / internal-round-trip-only, the owner chose full removal — same stance
as the learned-rate and line-measurements removals: don't carry a number the factory doesn't use.

**Rejected:** *internal round-trip only* (collapse the arithmetic but keep the read fields) — rejected;
it would leave dead, never-rendered fields in the API as drift bait, which is the thing the review is
clearing.

**Kept deliberately:** `colour.average_changeover_minutes` survives — the **multi-day placement** still
needs a *per-change* rate, because each day's changeover count is only known mid-fill (it can't be
handed a precomputed total). That is a legitimate, distinct use, not the round-trip. `place_orders` now
computes its own per-day total (`count × per-change`) and calls the pure `changeover_loss_m2(total)`.

**Implementation notes:**
- `capacity.changeover_loss_m2(changeover_minutes_total, rate)` (was `(count, minutes, rate)`);
  `compute_day_capacity(..., changeover_minutes_total=...)` keeps `changeover_count` only for display;
  `DayCapacity` / `GoodDayMetrics` drop their minute fields. `summarize_day(..., changeover_minutes_total=...)`.
- Service feeds the **total** (`sequence_changeover_minutes`) into the two fixed-sequence read paths
  (single-day capacity, good-day); the multi-day path keeps the line average for `place_orders`.
- Swept the same-vintage doc drift while here: the `placement.py` docstring's deleted-`docs/WORKFLOW.md`
  citation + "light→dark sweep" (removed in CHANGES #7) and the "light → dark / direction-aware" prose
  in `schemas.py` were corrected to "group identical colours".
- No domain behaviour changed (the m² loss is identical — `count × average ≡ total`), so `SPEC.md` §9/§11
  stay true and need no edit. Tests retargeted to the new signatures / observable
  (`tests/test_capacity.py`, `test_good_day.py`, `test_good_day_service.py`, `test_day_capacity_service.py`,
  `test_within_day_plan_service.py`, `test_planner_changeover_bound_na52.py`); the exact size-band minutes
  stay unit-pinned in `test_colour.py`.

**Expected:** the board / Statystyki render identically (`changeover_count`, `changeover_loss_m2`
unchanged); the API sheds 8 never-rendered fields + an always-true flag; one fewer sequence walk in the
two read paths. 601 backend + 134 frontend tests green, `tsc -b` + `vite build` + citation check clean.

**Review-by:** none required — behaviour-preserving internal simplification + removal of unrendered API
fields (frontend grepped clean); pinned by the retargeted suites.

---

## 2026-06-30 — undercount at surface prep silently redefines the order quantity is INTENDED

**Decision:** when an operator finishes surface preparation with a counted quantity **below** the planned
quantity (e.g. counts 3 of a planned 5), the order completes and its quantity is **redefined to the
counted amount** (becomes a 3-piece order) with no warning. Overcount stays hard-blocked. This is
**confirmed intended behaviour — not a bug.** No change to make.

**Why** — owner-confirmed **2026-06-30**, full rationale given. The count the prep operator enters is the
number of pieces that **physically arrived** at the station, which can differ from the quantity the
client/office stated when the order was created. The factory must run the rest of the production chain
(hanging, paint, packing) on **what is actually in the building**, not on the client's stated number — so
the counted (physical) quantity *replaces* the ordered quantity and propagates downstream from that point.
The client's figure was an expectation; the prep count is ground truth, and a shortfall is simply "fewer
pieces showed up than ordered" — a normal fact to record, not an error to warn about. (This is why
undercount silently shrinks the order and no warning is wanted; overcount is still blocked because you
cannot prepare more pieces than the order is for.)

**How this surfaced:** two independent zero-context UI-sim personas (2026-06-29/30 black-box run) flagged
it as "[POSSIBLE BUG] undercount silently shrinks the order"; the simulation correctly observed the
*behaviour*, and the owner's confirmation settles the *intent*. This is exactly the split the method
expects: the sim surfaces, the owner adjudicates.

**Rejected (by the owner's confirmation):** adding a shortfall warning, or splitting off the
counted-short remainder as a separate quantity — both rejected as intended-away; the count *is* the order.

**Implementation notes:** behaviour lives in the surface-prep finish path (`app/process/service.py`,
`finish_stage` counted-quantity handling — the same method whose *overcount* guard at `:2486` raises the
English string noted as a separate i18n issue). No code change from this decision; recorded so a future
reader/session does not "fix" the intended shrink.

**Expected:** undercount continues to redefine the order to the counted amount silently; overcount stays
blocked. If a future change adds a shortfall warning, it must trace back to a *new* owner decision, not a
silent reversal of this one.

**Review-by:** none outstanding — the factory *why* is now captured (the physical prep count is ground
truth and must propagate downstream in place of the client-stated quantity). Revisit only if a future
requirement asks to surface the shortfall (e.g. notify the office that fewer pieces arrived), which would
be an *addition* on top of this decision, not a reversal of the silent-shrink itself.

---

## 2026-06-30 — "Zastosuj plan" overriding a pin is INTENDED (explicit manager override)

**Decision:** the multi-day "Zastosuj plan" (apply suggested order) **may move a PINNED order** — this is
accepted behaviour, not a bug. Only the *other* arrangement action, "Ułóż automatycznie", honours pins.

**Why** — owner-confirmed **2026-06-30**. "Zastosuj plan" is an **explicit** manager action: the board
first shows "Twoja kolejność" vs "Sugerowana" side by side, and the manager deliberately chooses to apply
the suggestion. An explicit, eyes-open apply is allowed to override a pin; the pin only protects against
*implicit* auto-arrangement.

**Code reality (traced 2026-06-30):** the suggested order comes from `place_orders`
(`app/manager/placement.py:134`), pure earliest-deadline-first with no pin awareness, applied verbatim by
`reorder_queue` (`app/manager/service.py:1596`). Pin-honouring lives only in `arrange_with_locks` /
`scheduler.py:87-98` ("Ułóż automatycznie"). This asymmetry is now **intended**, not accidental.

**Rejected:** making the suggested-order/apply path pin-aware like auto-arrange — rejected; the owner wants
the explicit apply to be a genuine override.

**Residual (NOT a logic change):** the pin badge copy over-promises — "Zlecenie przypięte — układanie
automatyczne nie ruszy go z miejsca" / "układanie automatyczne nie ruszy go z miejsca"
(`frontend/src/pages/ManagerPanelPage.tsx:626`) reads as if *all* automatic arrangement is blocked. A
future copy tweak should scope it to "Ułóż automatycznie" so it doesn't imply protection from "Zastosuj
plan". Pure wording; no behaviour change. Not done now (owner has not greenlit fixes).

**Expected:** "Zastosuj plan" continues to apply the deadline-ordered suggestion even over pinned orders;
"Ułóż automatycznie" continues to hold pins at their index. If anyone later makes the suggested apply
pin-aware, it must trace to a new owner decision, not a silent reversal of this one.

**Review-by:** none required — confirmed-intended behaviour; revisit only if the badge wording is corrected.

---

## 2026-06-29 — found debt: enforce SQLite foreign keys (cascade was inert)

**Decision:** turn on `PRAGMA foreign_keys = ON` for every app connection (added to
`_apply_sqlite_pragmas`, `app/database/session.py`), and mirror it in the test engines
(`tests/conftest.py::_make_test_engine`). Clean up the orphan child rows already left in the dev
`local.db`.

**Why** — engineering decision (mine to own per `CLAUDE.md`; no factory *why* involved). Order creation
was returning HTTP 500 ("Nie udało się utworzyć zlecenia" in the UI). Root cause: SQLite ignores
`ON DELETE CASCADE`/`SET NULL` unless `foreign_keys` is ON per connection, and the pragma helper set
`busy_timeout`/`journal_mode`/`synchronous` but never `foreign_keys`. So earlier work-order deletions
(seeds/resets) silently orphaned their `work_order_quantity_batches` / `work_order_stage_states` /
`stage_transition_events`. Work-order ids are not AUTOINCREMENT, so a new order reused a freed id (12);
its `MAIN` batch insert then collided with the leftover **active** orphan batch on
`uq_work_order_quantity_batches_one_active_per_work_order` (one active batch per order) → IntegrityError
→ 500. Reproduced against the live backend via `scripts/sim_client` creds and in-process.

**Rejected:**
- *Only delete the orphan rows* — treats the symptom; the next deletion re-orphans and the 500 returns.
- *Drop the partial unique index* — wrong: "one active batch per order" is a real, owner-aligned
  invariant (`SPEC.md` §1). The bug was unenforced cascade, not the index.
- *Make ids AUTOINCREMENT so freed ids aren't reused* — hides the orphans rather than removing them;
  the dangling rows are still wrong data and would still violate `(work_order_id, stage)` uniqueness on
  other paths.

**Implementation notes:**
- `app/database/session.py:_apply_sqlite_pragmas` adds `PRAGMA foreign_keys = ON`.
- `tests/conftest.py`: new `_make_test_engine` attaches `_apply_sqlite_pragmas` to both fixtures, so
  tests enforce FKs like prod. Teardown drops `Base.metadata.drop_all` (redundant for an in-memory
  StaticPool DB — `dispose()` discards it — and it fails under `foreign_keys=ON` because dropping
  `work_orders` fires the self-referential `parent_order_id` SET NULL and violates the
  `correction_requires_parent` CHECK on correction children).
- Regression tests in `tests/test_db_constraints_phase1.py`:
  `test_foreign_keys_pragma_is_enabled`, `test_deleting_work_order_cascades_to_child_rows`.
- Dev-DB cleanup (one-off, backed up to `local.db.bak-*`): deleted CASCADE orphans
  (batches/stage-states/transition-events for missing orders), nulled the SET-NULL orphan refs in
  `audit_events` — mirroring exactly what enforced FKs would have done.

**Expected:** deleting a work order removes its child rows; creating orders no longer 500s on a reused
id; the dev DB has no orphan child rows. Full backend suite green.

**Review-by:** none — latent persistence bug fixed and pinned by regression tests.

---

## 2026-07-11 — ERRATUM to "2026-06-30 — undercount at surface prep" (behaviour claim, not the decision)

**What this is:** a correction of the *recorded behaviour description* in the 2026-06-30 undercount
entry — appended (log is append-only), the original entry is left untouched. **The owner's decision
and rationale stand unchanged:** the prep count is ground truth; an undercounted order completes;
no shortfall warning.

**What the 2026-06-30 entry got wrong:** it states the order's "quantity is **redefined to the
counted amount** (becomes a 3-piece order)". Verified live 2026-07-11: **no redefinition exists in
the code.** A 5-ordered / 3-counted / 3-packed order keeps `total_quantity=5`, shows READY
("Gotowe") at 3/5 via the all-stages-DONE fall-through (`app/process/service.py`, display-status
walk), never runs finalization (`_can_finalize_work_order` requires completed == total or correction
children), and therefore **never releases its queue position** — contradicting CHANGES #3 on exactly
this owner-blessed path, and later causing a raw 500 when the held slot is planned into. Full trace:
`docs/INDEPENDENT_REVIEW_2026-07-11.md` §1.1; opened as `CHANGES.md` #12/#13; presentation choice is
GO_LIVE **D5**.

**Why the erratum matters:** a future session reading only the 2026-06-30 entry would believe the
redefinition is implemented and "fix" discrepancies in the wrong direction. Per the method, a wrongly
documented *what* is as dangerous as an undocumented *why*.

**Review-by:** closes when CHANGES #12 ships and the implemented behaviour (per D5) is written back
into `SPEC.md` §6 with a fresh confirmation marker.

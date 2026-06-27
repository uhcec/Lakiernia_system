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

**Review-by:** frontend review — add a distinct badge for `STOCK_NOT_ENTERED` (today the new string
arrives at a UI that knows only OK/WARNING/BLOCKED).

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

**Review-by:** frontend review — give the manager a control to record the day's shift; until then the
LONG fallback means short days can still read as "bad", so confirm the measure once recording is live.

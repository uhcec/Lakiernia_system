# Domain decisions log (append-only)

*Why* a domain decision was made. New entries at the bottom. Each entry cites the change it
implements (`CHANGES.md #n`) and the owner confirmation behind it. Method per `CLAUDE.md`.

---

## 2026-06-26 — CHANGE #6: two scheduling rules (deadline → colour)

**Decision:** the painting auto-scheduler keeps only two ordering rules — `DEADLINE` and `COLOUR` —
with the default priority **deadline → colour**. The third rule, "maksymalny przerób" / max-throughput
(`ScheduleRuleKey.CHANGEOVER`, largest single-colour run first), was removed.

**Why:** owner-confirmed 2026-06-26 (CHANGES #6). Max-throughput optimised for booth m²/day but the
owner plans by promise dates first and colour-grouping second; the third rule added a lever nobody
tuned and competed with the deadline intent.

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

## 2026-06-26 — CHANGE #4: manager sets the shift length (no advising)

**Decision:** the day-capacity / multi-day planner no longer advises LONG vs SHORT from the available
ready m². The **manager sets** the shift length explicitly (the `shift_length` query param). When the
caller omits it, the planner defaults to **LONG** (the full 07:00–21:00 day).

**Why:** owner-confirmed 2026-06-26 (CHANGES #4). The m²-based advice second-guessed a decision the
manager makes from real-world context (staffing, urgency) the system can't see; it was a guess the
manager just overrode. LONG is the safe default because it shows the most capacity/headroom — the
manager narrows to SHORT when they decide to run a short day.

**Implementation notes:**
- `advise_shift_length` deleted from `capacity.py`.
- `shift_advised` removed from `DayCapacityRead` / `MultiDayPlanRead` and the (unused) `manager.ts`
  type — the flag only existed to mark an advised shift, which no longer happens.
- Connects to CHANGE #9 (persist the *actual* shift length run, for the "good day" measure).

## 2026-06-26 — CHANGE #10: quantity-leak tripwire made human-visible

**Decision:** when finalization detects a quantity-conservation leak (credited pieces ≠ total at
close), the order still force-closes to total (so work is never stuck), but the leak is now surfaced
to a human: a persisted `work_orders.quantity_leak_flagged` boolean (shown in the office + manager read
models) plus a SYSTEM audit event `work_order.quantity_leak_detected`. The technical log warning stays.

**Why:** owner-confirmed 2026-06-26 (CHANGES #10). A leak signals an upstream bug; the old behaviour
wrote it only to the server log, so a 7/10 → 10/10 silent auto-complete (verified live 2026-06-26) was
invisible to the shop. Force-closing is kept (don't trap the order) but it must be investigable.

**Implementation notes:**
- Migration `20260626_0041` adds the column with `server_default 0`; the model also carries
  `server_default=text("0")` so raw-SQL inserts (the DB-constraint tests) and metadata-built schemas
  backfill existing/legacy rows.
- The flag is set inside `_finalize_completion_chain_if_ready`; `record_audit_event` is called with
  `station_context=None` → recorded under `StationId.SYSTEM` (no operator triggered it).
- This is a safety net, not the fix: the quantity model should prevent leaks in the first place. The
  flag is the tripwire that makes a model bug visible.

## 2026-06-26 — CHANGE #1: a correction round must not lose pin/urgent

**Decision:** when a packing correction sends an order back to planning (replan-in-place), the live
`planning_priority` lock is still cleared (it can't sit on an unplanned order — DB constraint
`planning_priority_requires_planned`), but the manager's pin/urgent **intent is remembered** in a new
`pending_planning_priority` column and **re-applied** when the order is re-planned.

**Why:** owner-confirmed 2026-06-26 (CHANGES #1, a bug). A pinned/urgent order silently lost its
priority every time it bounced through a correction round, so the manager's intent evaporated exactly
when the order most needed to keep its place.

**Implementation notes:**
- `pending_planning_priority` (migration `20260626_0042`) is deliberately NOT bound by
  `planning_priority_requires_planned`, so it can hold the intent through the unplanned window.
- Set in `_reset_to_correction_planning` (parks the live value before clearing it); consumed in
  `assign_plan` (re-applies, then clears the parked value). It is single-use per round.
- A deliberate **line switch** still clears the lock and does not restore (that path doesn't touch
  `pending_planning_priority`, which is only set by the correction round) — switching lines is an
  explicit "give up the slot" action, distinct from a correction bounce.

## 2026-06-26 — CHANGE #8: flag untracked colours (STOCK_NOT_ENTERED)

**Decision:** a coloured order whose paint stock is not entered — no stock row, or only the 0-kg
auto-placeholder with no movement history — gets a distinct `PaintFeasibilityStatus.STOCK_NOT_ENTERED`
instead of a silent OK. It is surfaced (`stock_not_entered_order_ids`) but **never hard-blocked**. A
truly colourless order still reports OK (it makes no paint claim).

**Why:** owner-confirmed 2026-06-26 (CHANGES #8). Treating "we have no idea about this paint" as OK
hid exactly the gap the manager needs to act on ("enter the stock"); but we can't hard-block on the
unknown (the paint may well be there), so it's a visible-but-non-blocking state.

**Implementation notes:**
- New enum value (string `"STOCK_NOT_ENTERED"`); the schema reuses the same enum, so it serialises
  automatically. **Frontend (unreviewed)** likely enumerates only OK/WARNING/BLOCKED — it will receive
  the new string and should add a badge for it when the frontend is reviewed.
- Two untracked situations both map to it: no stock row (`stock is None` with a non-null colour) and a
  present-but-untracked placeholder (`is_tracked False`). The hard-block predicate already excludes
  untracked colours, so nothing that was OK and safe becomes blocked.

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

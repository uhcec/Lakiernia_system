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

# Change List — code vs. how the factory should work

Found during the code-grounded adjudication pass with the owner on **2026-06-26**. Each item: what the
code does now (`file:line`), what the owner wants, and why. See `docs/SPEC.md` for confirmed behavior.

| # | Type | Title |
|---|------|-------|
| 1 | bug | A correction must not lose its pin/urgent lock |
| 2 | UX | Make the second, separate Decoral pass visible |
| 3 | change | Completed orders leave the queue (release their position) |
| 4 | change | Manager sets the shift length (drop auto-advising) |
| 5 | change | Colour-change cost by size only (drop direction) |
| 6 | change | Two scheduling rules (deadline → colour) |
| 7 | change | Drop RAL-lightness guessing |
| 8 | change | Flag untracked colours instead of silent OK |
| 9 | change | Persist the actual shift length for "good day" |
| 10 | change | Make the quantity-leak tripwire human-visible |

---

### #1 — A correction must not lose its pin/urgent lock  *(bug)*
- **Now:** when a packing correction sends an order back to planning (replan-in-place), it clears `planning_priority` (pin/urgent) along with the line and position. `app/process/service.py:2237-2240`
- **Want:** the order should keep its pin/urgent intent through the correction round.
- **Note:** the DB allows a planning lock only on a planned order (`app/work_orders/models.py:71-74`), so a returned (unplanned) order can't literally hold one — the intended priority likely needs to be remembered and re-applied when the order is re-planned.

### #2 — Make the second, separate Decoral pass visible  *(UX)*
- **Now:** when corrected pieces return after the root's Decoral was already done, they start a fresh Decoral batch — a correct but easy-to-miss "second pass". `app/process/service.py:2060-2091`
- **Want:** show the operator clearly that this is a separate, second Decoral pass on the returned pieces. Backend logic stays; this is presentation.

### #3 — Completed orders leave the queue  *(change)*
- **Now:** a completed (READY) order keeps its line + queue position and stays in the queue as a trailing block; elaborate "trailing/shuffle" logic manages it. `app/manager/service.py:1498-1519`, `2094-2176`
- **Want:** on completion the order **leaves the line's active queue and releases its position**. This makes the trailing/shuffle machinery unnecessary.
- **Before implementing:** check what relies on completed orders staying planned (e.g. the manager board, any statistics).

### #4 — Manager sets the shift length  *(change)*
- **Now:** when shift length is omitted the system advises long/short from available ready m². `app/manager/capacity.py:165-171`
- **Want:** remove the advising; the manager sets the day length (long/short) explicitly.

### #5 — Colour-change cost by size only  *(change)*
- **Now:** changeover cost = size band (≤100 m² → 15 min, >100 m² → 30 min) scaled by colour **direction** (light→dark pays half, dark→light full). `app/manager/capacity.py:127-147`, `app/manager/colour.py:157-175`
- **Want:** drop the direction factor; a colour change costs its size band regardless of direction.

### #6 — Two scheduling rules (deadline → colour)  *(change)*
- **Now:** three rules — COLOUR, DEADLINE, "max throughput" (largest single-colour run first) — default order colour → deadline → max-throughput. `app/manager/enums.py:4-51`
- **Want:** only **two** rules (deadline, colour), default order **deadline → colour**; remove "max throughput".

### #7 — Drop RAL-lightness guessing  *(change)*
- **Now:** colour lightness is approximated from the RAL code (first digit + hand-set overrides) to order a light→dark sweep. `app/manager/colour.py:43-102`
- **Want:** remove it. Together with #5, within-day colour planning reduces to **grouping identical colours** (cost = number of changes × 15/30 min by size).

### #8 — Flag untracked colours instead of silent OK  *(change)*
- **Now:** a colour with no stock history (only the 0-kg auto-placeholder) is treated as silently "OK" — the planner makes no claim. `app/manager/paint_feasibility.py:120-133`
- **Want:** surface it as a distinct visible state ("stock not entered — enter it") rather than silent OK. (Can't hard-block on unknown — but should not be invisible.)

### #9 — Persist the actual shift length for "good day"  *(change)*
- **Now:** every past day is measured against the long-day bar (800 m² / 14 h) because the actual shift length run that day isn't stored. `app/manager/service.py:805-818`
- **Want:** persist the actual shift length per day and measure "good day" against it. (Connects to #4.)

### #10 — Make the quantity-leak tripwire human-visible  *(change)*
- **Now:** at finalization, if credited pieces ≠ total, the order is forced to total and a warning is written **only to the technical server log**; no human sees it. Verified live 2026-06-26: a 7/10 leak was silently completed to 10/10 with only a log warning. `app/process/service.py:2343-2350`
- **Want:** the leak is a sign of an upstream bug — keep the tripwire but make it **visible to a human** (e.g. a flag on the order) so it gets investigated, instead of a silent auto-complete. The quantity model should prevent leaks in the first place; this is the safety net.

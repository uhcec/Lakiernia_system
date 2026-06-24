# Workflow simulation (`scripts/sim/`)

A living, multi-day simulation of the whole factory. Instead of a scripted end-to-end test, **one
autonomous LLM persona per station** pulls whatever work is actually in its queue from the real running
backend and decides — in character — what to do with it. Over a few simulated factory-days this produces
*emergent* flow (an order hits corrections while another is on the line and the manager reshuffles the
queue), surfacing workflow/UX gaps, realistic data for the stats dashboards, and emergent backend bugs.

It is a **discovery** instrument, not a regression gate: live personas are nondeterministic, so a finding
is reconstructed from `timeline.jsonl` into a deterministic test afterward. It does **not** cover races
(serialized, single worker — NA8), the frontend (it drives the HTTP API), performance, or ground-truth
factory policy (the personas guess from the docs).

## Pieces

| Piece | Role |
|---|---|
| `seed_sim_baseline.py` | Clean dev DB: station users / clients / foils / employees, **zero work orders**. |
| `controller.py` | The mechanical clock + bookkeeping. Owns no decisions. Advances the dev virtual clock, snapshots queues, runs the auditor, writes the timeline. |
| `auditor.py` | Pure invariant checks (quantity conservation, one active batch, queue uniqueness, packing slots). |
| `personas/*.md` | The eight station briefs the live persona agents read. `_common.md` first, then one per login. |
| `runs/<ts>/` | Per-run output: `timeline.jsonl`, `friction.md`, `invariants.md`, `known_orders.json`. `runs/LATEST` points at the current run. |

## Time

A **dev-only virtual clock** (`app/shared/clock.py`, controlled via the dev-only `PUT /dev/clock`) makes
the backend stamp simulated time and run the planner's shift/day logic on it. Auth tokens are the one
deliberate exception — they stay on real wall-clock time, because JWT `exp` is validated against real
time (a token issued on simulated time would be born expired). The controller freezes the clock at the
shift start (default Mon 07:00) and advances it as work happens.

## Running (orchestrated by the main Claude session)

The personas are live agents; the **main session is the clock/controller**, waking only the personas
that have work each tick and keeping each one alive (with its memory) across the whole run.

```bash
# 1. Clean baseline + single-worker backend (NA8: never use --workers).
APP_ENV=development python scripts/sim/seed_sim_baseline.py
APP_ENV=development python -m uvicorn app.main:app --port 8000   # background; wait on /health

# 2. Start a run (creates runs/<ts>/, freezes the clock at the shift start).
python scripts/sim/controller.py init-run

# 3. Per tick the controller advances time and reports who has work:
python scripts/sim/controller.py clock advance --minutes 30
python scripts/sim/controller.py snapshot
#    -> the orchestrator wakes each station persona that has work; each acts once via sim_client.py
python scripts/sim/controller.py audit          # invariants -> runs/<ts>/invariants.md
python scripts/sim/controller.py event --json '{"station":"pakowanie","action":"complete","order":"0007"}'
```

Personas call the backend as their station with (the `MSYS_NO_PATHCONV=1` prefix matters on Git Bash):

```bash
MSYS_NO_PATHCONV=1 python scripts/sim_client.py --as <login> <METHOD> <path> '<json-body>'
```

Logins: `biuro`, `kierownik`, `przygotowanie`, `zawieszanie`, `produkcja-reczna`, `produkcja-automat`,
`pakowanie`, `decoral`, `admin`.

## Phases

- **Phase 0** — one short day, 1–2 orders: prove the seed → clock → tick → audit → friction loop.
- **Phase 1** — one full light day (~3–5 orders), all stations live.
- **Phase 2** — the full three days.
- **Later** — a browser-driven persona layer that acts through the React UI while the backend stays the
  oracle (catches the "faithful renderer" bug class the API-only sim can't see); automatic/decoral phases
  need paint stock seeded into the baseline.

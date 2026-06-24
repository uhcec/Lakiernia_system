> ARCHIVED — disposable scratch from the /doc-audit run dated **2026-06-24**. Living truth lives in
> `docs/WORKFLOW.md` / `docs/FACTORY_DOMAIN_MODEL.md`. Durable conclusions from this run were folded into
> the owning living docs (see "Applied" below); this snapshot is the spent artifact.

# Documentation Coherence Audit — run 2026-06-24

Scope: `CLAUDE.md`, `README.md`, `IMMEDIATE_NEXT_ACTIONS.md`, `HARDENING_BACKLOG.md`, and everything
under `docs/` (incl. `docs/archive/`). Method: topic map across docs → record contradictions, duplicates,
stale claims, missing topics → ground numeric/behavioural claims against code before judging. Doc-scope
only; no code changed. Precedence: `FACTORY_DOMAIN_MODEL.md` → `WORKFLOW.md` → code → snapshots.

## Headline since the last run (2026-06-17)

The last audit reconciled the docs around a **single global queue** (its §C named the queue topic as
consistent). Since then the system was **rebuilt to a per-line queue** (owner-confirmed 2026-06-23
clean-slate process session: two parallel physical painting resources → two independently numbered plans;
code: DB partial unique index `(production_type, queue_position)` = `uq_work_orders_line_queue_position`,
`_next_active_queue_position_for_line`, `reorder_queue` carries a `production_type`). That rebuild updated
`CLAUDE.md` and added `WORKFLOW.md` "Per-Line Queue Rule", **but the older "one global queue / do not
split by production type" language was left untouched in five places** — including a self-contradiction
inside `WORKFLOW.md` itself. This is the dominant drift this run; it is **safe to fix** (the per-line model
is both owner-confirmed and code-confirmed, so no new owner question).

The N49 multi-day planner (N49-1…N49-10), NA50 good-day stats, and NA51–NA57 are all newly landed since
the last run; their cross-references between `WORKFLOW.md` "Target planning model" and
`FACTORY_DOMAIN_MODEL.md` §7 were checked and are coherent.

## A. Contradictions (incl. one internal)

### A1. Single global queue vs. per-line queue — STALE, SAFE TO FIX (code-grounded) — APPLIED
The current model is **per-line** (`CLAUDE.md` "manager/", `WORKFLOW.md` "Per-Line Queue Rule"; code
`app/work_orders/models.py:86` `uq_work_orders_line_queue_position`, `app/manager/service.py:1927`).
Stale "global queue / do not split" claims found at:
- **`WORKFLOW.md:232` — internal contradiction.** "A switch/segmented control … must not create separate
  queues" directly contradicts the same doc's "Per-Line Queue Rule" ("two **independent** queues … the
  manager UI presents the two plans as separate boards"). **Reworded** (the switch selects which line's
  plan to edit; the lines are independently numbered).
- `README.md:27` ("global queue-position uniqueness") and `README.md:307` ("Queue positions are globally
  unique"). **Fixed → per-line.**
- `WORKFLOW_VALIDATION_CHECKLIST.md` §5 ("one shared global queue … do not split by manual, automatic")
  and §7a ("do not split the global queue by production type"). **Annotated SUPERSEDED** (historical
  2026-05-30 capture retained, per the owner's standing choice for dated captures).
- `FACTORY_USAGE_NOTES.md:37-38` ("one global queue for all planned work. Do not split it by manual,
  automatic …"). **Annotated SUPERSEDED.**
- `STATION_IDENTITY_AND_AUDIT.md:164` (MANAGER "view global queue"). **Reworded → per-line planning queues.**
- `HARDENING_BACKLOG.md:201` mentions "one global queue" as a 2026-05-30 confirmed answer. Left as-is: it
  is explicitly framed as a dated historical confirmation, not current policy (closed-evidence doc).
- `docs/archive/CODE_CONFORMANCE_AUDIT.md:67` ("Global queue … CONFORMS") — frozen 2026-06-17 snapshot,
  predates the rebuild; left frozen (carries an archive banner).

### A2. Manager "types/inserts a queue position" vs. append-to-end — STALE, SAFE — APPLIED (partial)
Per-line rule 12 (`WORKFLOW.md:343`) and the per-line UI: planning is a single "Zaplanuj" that **appends
to the end of the line** (server-computed); the manager no longer types a position; reordering is
drag-and-drop. Stale "propose/insert the next queue position" language remains at
`FACTORY_USAGE_NOTES.md:42` and `WORKFLOW_VALIDATION_CHECKLIST.md` §5 bullet ("Manager planning should
propose the next free active queue position"). **Folded into the FACTORY_USAGE_NOTES superseding note**
(added an explicit "appends to the end / drag-and-drop" line); the checklist §5 bullet sits under the new
SUPERSEDED banner so it reads as historical.

## B. Stale claims (non-queue)

### B1. Shared-stage station columns still say "queue position" — STALE (N49-10), SAFE — APPLIED
N49-10 replaced the per-line "Poz." at the two **shared** stages (surface preparation, packing) with a
derived line label + "NASTĘPNE" (`WORKFLOW.md` "Shared-stage ordering"; read model
`shared_stage_line_label` / `is_next_at_shared_stage`). The 2026-05-30 column lists in
`WORKFLOW_VALIDATION_CHECKLIST.md` §8 and `FACTORY_USAGE_NOTES.md` (surface-prep + packing) still list
"queue position" for those two stages. **Annotated** §8 with an N49-10 note (the painting stations still
show the per-line position; only the two shared stages changed).

### B2. `/doc-audit` cadence "weekly" vs "on-demand" — STALE, SAFE — APPLIED
`DOCUMENTATION_MAP.md` "Audit cadence policy" + the `/doc-audit` skill state **on-demand** (NA47,
2026-06-22, owner-confirmed; explicitly not a standing weekly schedule). Two docs still say weekly:
`IMMEDIATE_NEXT_ACTIONS.md:440` (NA24 closure note, "intended cadence weekly") — **fixed → on-demand**;
and `ARCHITECTURE_AUDIT.md:233` (D4, "regenerate them weekly") — left as-is (it is a dated 2026-06-19
review snapshot, and D4's own point was *questioning* the cadence that NA47 then resolved).

### B3. `ARCHITECTURE_AUDIT.md` D1 ("move snapshots to docs/archive/") — already actioned, not stale-harmful
D1 (2026-06-19) recommended archiving the frozen snapshots; that was done (NA45 — the six snapshots now
live under `docs/archive/`, and `DOCUMENTATION_MAP.md`'s archive table matches the folder). The audit body
still lists them as "in the active doc set", but it is a dated review snapshot and the NA39–NA47 items it
seeds are tracked live. No edit (would be rewriting a historical snapshot); noted for awareness.

## C. Duplication / single-owner (drift risk, currently consistent)

- **Per-line queue rule** now has a clear owner (`WORKFLOW.md` "Per-Line Queue Rule"); the capture docs
  were converted to references/superseding notes this run rather than restating it.
- **Station columns** (`WORKFLOW.md` owner) are still restated in `FACTORY_USAGE_NOTES.md`,
  `WORKFLOW_VALIDATION_CHECKLIST.md` §8, `STATION_IDENTITY_AND_AUDIT.md`. Consistent after the N49-10 note;
  the standing recommendation (last run's §C, ARCHITECTURE_AUDIT D3) to convert restatements to references
  when next touched still applies.
- **Correction reason categories** / **permission matrix** — unchanged, still consistent, owner =
  `WORKFLOW.md`.

## D. Missing topics — none new blocking

The big new subsystems (multi-day planner, good-day stats) are documented in the two living docs and the
NA backlog. The known open *decisions* (NA51 board-vs-queue reconciliation; NA52 inflated changeover cost;
NA54 demand-aware paint block; NA56 working calendar) are already logged as NA items with owner questions —
they are open *work*, not doc gaps. No new "should-be-documented-but-isn't" topic surfaced this run.

## Applied this run (safe edits)

- `WORKFLOW.md:232` — reworded to the per-line model (kills the internal contradiction with "Per-Line
  Queue Rule").
- `README.md:27,307` — "global" queue uniqueness → **per-line**.
- `WORKFLOW_VALIDATION_CHECKLIST.md` — §5 SUPERSEDED banner (per-line); §7a inline SUPERSEDED note; §8
  N49-10 shared-stage-columns note.
- `FACTORY_USAGE_NOTES.md` — global-queue capture struck through + SUPERSEDED note; added the
  append-to-end / drag-and-drop planning line.
- `STATION_IDENTITY_AND_AUDIT.md:164` — "view global queue" → per-line planning queues.
- `IMMEDIATE_NEXT_ACTIONS.md:440` — `/doc-audit` cadence "weekly" → on-demand (NA47).

## Owner questions

None new from this run. The per-line rebuild is owner-confirmed (2026-06-23) and code-confirmed, so the
edits above are reconciliation, not policy. The open planner decisions remain tracked as NA51/NA52/NA54/
NA56 (with their own owner questions) — out of scope for a doc-coherence pass.

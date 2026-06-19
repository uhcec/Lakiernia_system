# Architecture & Design Audit — 2026-06-19

> A **critical design review**, not a bug hunt. The question this audit answers is: *where did we build
> something over-engineered, internally inconsistent, or sub-optimal — and what would the simpler shape
> be?* Findings feed `IMMEDIATE_NEXT_ACTIONS.md` as NA39+ items. Nothing here is a correctness defect
> (those live as their own NA items); these are **debt and shape** problems.

Scope (per owner, 2026-06-19): backend/architecture, workflow/domain model, frontend, docs/process —
all four. Output: this report + NA entries.

Method: read the reconciled docs (`WORKFLOW.md`, `FACTORY_DOMAIN_MODEL.md`, `CLAUDE.md`,
`IMMEDIATE_NEXT_ACTIONS.md`) and the code, then look for structures that cost more than they earn.
Evidence is cited as `file:line`.

---

## Executive summary

The system is **correct and well-tested** (401 backend tests, 33 migrations, green scenario matrix).
The problems are not "does it work" but "is the shape sustainable." Four themes:

1. **One god class.** `app/process/service.py` is 2937 lines / ~120 methods and owns transitions,
   locks, packing slots, corrections, paint, display derivation, read-model serialization, **and**
   audit writing. Every workflow change lands in this one file.
2. **The correction subsystem forked into two shapes and is about to fork into a third.** RAL (in-place
   batch reset) vs DECORAL (child order) already carry a "do not unify without checking" warning;
   NA34 (stat-only corrections) adds a third path on top of an un-abstracted base.
3. **Several "legacy/compatibility" fields are still load-bearing** and maintained in parallel with their
   replacements — two sources of truth for the same fact.
4. **Documentation outweighs its value.** ~5,150 lines across 20 docs, many of them frozen dated audit
   snapshots that overlap the two living docs, plus an audit-generating-audit process loop.

None of these block shipping the open features. But **NA34/NA32 (corrections) should not be built on the
current correction code without first abstracting it** (Finding A2), and that is the one place where debt
turns into risk.

---

## A. Backend / architecture

### A1 — `process/service.py` is a god class (MEDIUM, maintainability)
`ProcessService` is 2937 lines and ~120 methods (`app/process/service.py`). In one class it mixes:
- **mutation/transition logic** (`start_stage`, `finish_stage`, `complete_packing`, …)
- **resource-lock + packing-slot management** (`_acquire_packing_slot`, `_release_stale_resource_lock`,
  `_get_resource_mutation_lock`, the module-level `_PROCESS_MUTATION_LOCKS` dicts at `:30-33`)
- **correction creation/merge** (`_complete_packing_with_correction_order`,
  `_reset_to_correction_planning`, `_place_returned_pieces_on_root_decoral`, …)
- **display-status derivation** (`get_display_status` + 6 helper variants, `:997-1121`)
- **read-model serialization** (`_to_stage_work_order_read`, `:2408-2516`)
- **audit + transition-log writing** (`_record_stage_audit_event`, `_record_stage_transition`, …)

Consequence: every workflow change touches the same file; reasoning requires holding all concerns at
once; the file is the single biggest merge-conflict and review surface. The natural seams are already
visible in the method grouping — they are just not separated into modules.

**Recommendation:** extract along the existing seams (a `ResourceLockManager`, a `CorrectionService`, a
`ProcessReadModel`/serializer, an `AuditWriter` already half-exists in `_record_*`). No behavior change,
pure structure; do it incrementally and keep the test suite as the safety net. Highest leverage is
splitting **read-model serialization** and **corrections** out first — they are the two largest,
most-self-contained chunks.

### A2 — Correction model is bifurcated and about to trifurcate (MEDIUM, risk before NA34)
The single most-repeated warning in the codebase ("do not unify without checking `WORKFLOW.md`") is the
RAL-vs-DECORAL correction split: RAL resets the same order with a `CORRECTION` batch
(`_reset_to_correction_planning`, `:1919`); DECORAL spins off a child "P" order
(`_create_correction_work_order`, `:1850`; `_place_returned_pieces_on_root_decoral`, `:1783`). The
asymmetry has a real physical cause (DECORAL has a stage *after* packing, so the OK part must keep
flowing while corrections rejoin the root's single decoral pass; RAL ends at packing). But the two paths
share **no common abstraction** — they are two parallel hand-written flows.

**NA34** now wants a *third* kind ("od razu poprawiona" = stat-only, never returns). Bolting a third
branch onto two un-abstracted flows multiplies the combinations (RAL/DECORAL × replan/stat-only × single/
multi-round) and the test matrix with them.

**Recommendation:** before NA34/NA32, introduce a thin **correction strategy** seam — one entry point
(`record_correction(work_order, qty, category, kind)`) dispatching to `{replan_in_place, spin_off_child,
stat_only}`, with quantity-conservation and reason-capture handled once in the shared part. This is the
one finding where the order of operations matters: refactor first, then add NA34, or you rework the same
code twice (the NA backlog already half-notices this by telling you to "do NA32 + NA34 together").

### A3 — Three overlapping "status / incomplete" concepts (MEDIUM, truth drift risk)
There are **three** notions of order state living side by side:
- `process_status` — the real, derived, backend-owned display status (correct design).
- `WorkOrder.status` (`WorkOrderStatus` enum) — labelled "legacy compatibility, do not drive workflow
  from it" (`CLAUDE.md`), yet it is **still written** (`work_orders/service.py:404`,
  `process/service.py:1883`) and **still load-bearing in a DB CHECK constraint**
  (`incomplete_requires_unplanned`: `status != 'INCOMPLETE'`, `work_orders/models.py:64`).
- `is_incomplete_on_arrival` (boolean) — the *real* incomplete marker.

`_has_incomplete_marker` must check **both** the boolean and the legacy enum
(`is_incomplete_on_arrival or status == WorkOrderStatus.INCOMPLETE`, `process/service.py:2333`; mirrored
in `work_orders/service.py:469`). So "is this order incomplete?" has **two sources of truth that must be
kept in agreement by hand**, and a CHECK constraint depends on the legacy one. That is exactly the kind
of duplicated truth that drifts.

**Recommendation:** pick `is_incomplete_on_arrival` as the single source, migrate the CHECK constraint
off `status`, and either delete `WorkOrder.status` or freeze it write-once with a comment that nothing
reads it for workflow. Collapse `_has_incomplete_marker` to one field.

### A4 — `current_active_batch_id` is a denormalized pointer that must be hand-synced (LOW)
`current_active_quantity` is cleanly derived (`models.py:189` sums active batches), but
`current_active_batch_id` is a **stored** pointer that `_sync_legacy_current_active_batch` has to refresh
at **8+ call sites** (`process/service.py:909,1489,1552,1568,1599,1674,1771,1815`), and `active_batch`
needs a 3-way heuristic fallback when it is stale (`models.py:176-186`). A forgotten sync call silently
desynchronizes it.

**Recommendation:** drop the stored column and derive `active_batch` from `active_batches` (there is a
DB partial-unique index guaranteeing one active batch, so the derivation is unambiguous). Removes 8 sync
calls and the fallback heuristic.

### A5 — Unbounded in-process lock dictionaries (LOW)
`_PROCESS_MUTATION_LOCKS: dict[int, RLock]` and `_RESOURCE_MUTATION_LOCKS: dict[str, RLock]`
(`process/service.py:30-33`) grow one entry per work-order-id / resource-key and are **never evicted** —
a slow unbounded growth over the process lifetime. Combined with the documented single-worker constraint
(NA8/NA20), this is the architectural ceiling: correctness of "no duplicate correction child" depends on
one process. For a paint shop with a handful of tablets this is fine, but it is worth restating as a
hard limit and capping/evicting the lock maps if the process is long-lived.

### A6 — Two parallel append-only logs, double-written per transition (LOW)
Every meaningful transition writes to **both** `audit_events` (+ `audit_event_actors`) and
`stage_transition_events`. The second log is justified (the stage-state row keeps only the latest
`updated_at` and cannot reconstruct history — `WORKFLOW.md` "Stage-transition log"), but the two are
written at the same choke points and can diverge if one write is added without the other. Acceptable, but
note the coupling; if analytics ever need actor attribution they will want these joined, not duplicated.

---

## B. Workflow / domain model

### B1 — The automatic "PRODUCTION-as-preview + packing-starts-at-hanging" model is the most special-cased, most-churned area (MEDIUM)
For AUTOMATIC orders, `PRODUCTION` exists as a stage but has no manual start/finish (it's a "preview"),
and `PACKING` flips to `IN_PROGRESS` the moment `HANGING` starts but **cannot complete** until hanging is
`DONE` + paint recorded. Encoding this costs a whole family of special-case methods:
`_is_automatic_production_preview_stage`, `_get_automatic_production_preview_display_stage`,
`_is_visible_in_automatic_packing`, `_get_automatic_packing_display_stage`,
`_packing_completion_block_reason`, plus `can_complete_packing` / `packing_blocked_reason` read-model
plumbing. The Done log shows this exact area was reversed **three times** (reserve-slot → start-packing →
active-row-not-readonly) and produced a seed bug — the strongest signal that the model fights the
stage-state abstraction.

**Recommendation:** not a rewrite, but a deliberate review: is keeping `PRODUCTION` as a stage for
AUTOMATIC (then special-casing it as a no-op preview everywhere) actually simpler than **omitting it from
the automatic stage sequence** (as DECORAL omits nothing and PRZEMALOWANKA already omits
`SURFACE_PREPARATION`)? The "automatic packing is live but uncompletable" state is inherent and should
stay, but the phantom PRODUCTION stage may be removable. Worth a focused spike before more automatic-flow
features land.

### B2 — `consumed_paint_quantity_kg` is one field doing two conflicting jobs (MEDIUM — already NA32)
Already tracked as **NA32**, listed here because it is a textbook "designed without sense": the field is
both the per-round "was paint registered for this packing?" gate **and** the order's cumulative
consumption display, and the two needs conflict (the gate wants it zeroed per correction round; the
display wants it summed). Resolve by separating the gate signal from the displayed cumulative total — see
NA32 for the concrete fix.

### B3 — The quantity vocabulary is over-faceted (LOW–MEDIUM)
An order carries at least five quantity notions: `total_quantity` (ordered), surface-prep counted
(actual received), `current_active_quantity` (sum of active batches), `operational_quantity` (NA26), and
per-stage `planned_quantity`. Which one is shown where is subtle enough that it was wrong **almost
everywhere** (NA26), and the resolution needed four helpers:
`_get_stage_display_quantity` / `_get_stage_planned_quantity` / `_get_operational_quantity` /
`_get_stage_counted_quantity` (`process/service.py:2518-2906`).

**Recommendation:** document the five quantities and their display rule in one place in `WORKFLOW.md`
(there is a partial "Quantity Discrepancy Visibility" section), and collapse the four helpers behind one
`quantity_for(context)` resolver so the rule lives once, not scattered across read-model code.

---

## C. Frontend

### C1 — Monolithic page components (MEDIUM, maintainability)
`WorkOrderDetailPage.tsx` 1353 lines, `ManagerPanelPage.tsx` 1053, `PackingWorkOrdersPage.tsx` 908,
`StageWorkOrdersPage.tsx` 876, `StatystykiPage.tsx` 826. These are the frontend equivalent of A1, and the
known frontend defects are symptoms of editing them under churn: the stray `<span>::</span>` (NA13), the
stale plan-draft after a correction return (NA31), the dead `WorkOrdersTable.tsx` kept alive only by its
tests (NA14). Big components accumulate residue.

**Recommendation:** decompose the two worst (Detail, Manager) into section components with the data
fetching lifted to a hook. Pure structure; do it when next touching each page rather than as a big-bang.

### C2 — Business semantics computed in the renderer (LOW–MEDIUM, contradicts the stated rule)
`CLAUDE.md` is explicit that the frontend "must not infer correction/READY/queue/quantity meaning
locally" and is "a faithful renderer." Two places break that:
- **"PO TERMINIE" (overdue) is computed client-side** by comparing `planned_pickup_date` to
  `new Date()` (`utils/workOrderDisplay.ts:142,162`). Overdue is a business judgement; the backend should
  own it (consistent clock, testable, single definition).
- **Polish status labels are duplicated.** `getWorkOrderStatusSummary` re-maps every `process_status`
  value to a Polish string in a frontend switch (`workOrderDisplay.ts:28-50`), while the backend already
  exposes `ProcessDisplayStatus.polish_label` (`get_display_status_label`, `process/service.py:1051`). Two
  copies of the same label table that must be kept in sync.

**Recommendation:** move the overdue flag into a read-model boolean, and either render the backend's
`polish_label` directly or accept the frontend table as the single owner — but not both.

---

## D. Documentation & process

### D1 — Documentation sprawl, much of it frozen snapshots (MEDIUM)
20 markdown docs totaling ~5,150 lines for a ~22k-LOC codebase. Two are genuinely living and
authoritative (`WORKFLOW.md`, `FACTORY_DOMAIN_MODEL.md`). Many others are **dated point-in-time audit
snapshots** that now overlap the living docs and each other:
`DOC_COHERENCE_AUDIT.md`, `CODE_CONFORMANCE_AUDIT.md`, `OPERATOR_USABILITY_AUDIT_PL.md`,
`UI_PASSIVE_REVIEW_PL.md`, `FACTORY_USAGE_NOTES.md`, `FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md`,
`PAINT_SYSTEM_DEFINITION_DRAFT_PL.md`, and `WORKFLOW_VALIDATION_CHECKLIST.md` (**35 KB alone**). Several
already carry "frozen as history" banners — which is the tell that they should live in an `docs/archive/`
folder, not in the active doc set a new session is told to read.

**Recommendation:** move frozen snapshots into `docs/archive/` (or delete the ones fully superseded),
leaving the living set small: `WORKFLOW.md`, `FACTORY_DOMAIN_MODEL.md`, `WORKING_CONTRACT.md`,
`DEVELOPMENT_RUNBOOK.md`, `DOCUMENTATION_MAP.md`. The `DOCUMENTATION_MAP.md` then honestly reflects what
is current.

### D2 — `IMMEDIATE_NEXT_ACTIONS.md` is half changelog (LOW)
The file is 941 lines; the "Done" section (~350 lines, `:593` onward) is full prose evidence paragraphs
that duplicate `HARDENING_BACKLOG.md` and git history. A backlog that is mostly a changelog is harder to
scan for the *open* work it exists to surface.

**Recommendation:** keep Done entries to one line + commit ref, and let `HARDENING_BACKLOG.md` / git hold
the evidence.

### D3 — Four parallel representations of the S01–S12 scenarios (LOW)
The same scenario validation exists as: the matrix in `WORKFLOW.md`, `WORKFLOW_VALIDATION_CHECKLIST.md`,
`SCENARIO_WALKTHROUGH.md`, and `tests/test_scenario_matrix.py`. The tests are the durable, executable
truth; the three prose copies drift independently.

**Recommendation:** treat `test_scenario_matrix.py` + the `WORKFLOW.md` matrix as canonical; fold the
walkthrough into one operational checklist and retire the validation checklist once its unique content is
merged.

### D4 — Process observation: the audit-generating-audit loop (NA47)
NA24 produced `DOC_COHERENCE_AUDIT.md`; NA25 produced `CODE_CONFORMANCE_AUDIT.md`; this is a third audit;
`/doc-audit` and `/code-audit` skills regenerate them weekly. For a single-developer factory tool this is
a lot of meta-process whose outputs themselves become stale and need reconciling (D1). Worth a conscious
decision about how much of this cadence to keep versus folding the signal directly into `WORKFLOW.md`.

---

## Priority

If only a few are actioned, in order:
1. **A2** — abstract corrections **before** NA34/NA32 (the one debt that becomes risk).
2. **A3** — collapse the duplicated "incomplete/status" truth (drift hazard with a CHECK constraint on it).
3. **D1** — archive frozen doc snapshots (cheap, immediately clarifies what to trust).
4. **A1 / C1** — split the two god files incrementally, as they are next touched.
5. The rest (A4–A6, B1, B3, C2, D2–D3) as opportunistic cleanup.

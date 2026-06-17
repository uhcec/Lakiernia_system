# Documentation Map

The single canonical index of the project's docs: what each one is for, and which wins when they
disagree. Keep this current when adding or retiring a doc. (Referenced from `CLAUDE.md` and `README.md`.)

## Precedence (when sources disagree)

1. **`docs/FACTORY_DOMAIN_MODEL.md`** — physical factory reality (the "why").
2. **`docs/WORKFLOW.md`** — system workflow semantics (what the system does).
3. **Code + Alembic migrations + tests** — implemented behaviour.
4. **`IMMEDIATE_NEXT_ACTIONS.md`** (live open work) and **`HARDENING_BACKLOG.md`** (closed evidence).
5. **Capture / snapshot docs** — historical evidence; never override 1–2.
6. **`README.md` / `docs/DEVELOPMENT_RUNBOOK.md`** — setup only.

Remember (per `WORKING_CONTRACT.md`): repo artifacts can preserve old assumptions. When factory policy
is unclear, ask the owner rather than trusting a doc or the code.

## Living sources of truth

| Doc | Purpose |
|---|---|
| `docs/FACTORY_DOMAIN_MODEL.md` | Physical reality: the two axes (method × coating), the line, measurement, ocynk/przemalowanka, glossary. |
| `docs/WORKFLOW.md` | Workflow/business semantics: stages, quantities, corrections, READY, queue, throughput, scenario matrix S01–S12. |
| `CLAUDE.md` | Agent entry point: architecture map, read-first order, working rules, quality gate. |
| `docs/WORKING_CONTRACT.md` | How we collaborate; source-of-truth order; decision rules. |
| `IMMEDIATE_NEXT_ACTIONS.md` | The live queue of open, actionable work (start here each session). |

## Closed evidence / setup

| Doc | Purpose |
|---|---|
| `HARDENING_BACKLOG.md` | *Closed* hardening items (verify currency before trusting). |
| `docs/AUTHZ_DESIGN_PROPOSAL.md` | NA1 authorization design record (IMPLEMENTED). |
| `docs/STATION_IDENTITY_AND_AUDIT.md` | Station identity + audit layer (updated post-NA1). |
| `README.md` | Project overview + setup. |
| `docs/DEVELOPMENT_RUNBOOK.md` | Setup / run / seed / verify commands. |

## Historical snapshots (do not override current truth)

| Doc | Snapshot date | Note |
|---|---|---|
| `docs/FACTORY_USAGE_NOTES.md` | 2026-05-30 | Factory-stakeholder capture by station panel. |
| `docs/FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md` | 2026-06-01 | Decisions→tasks; banner-flagged stale points. |
| `docs/OPERATOR_USABILITY_AUDIT_PL.md` | 2026-05-31 | Working usability audit (banner-flagged). |
| `docs/UI_PASSIVE_REVIEW_PL.md` | 2026-05-31 | Passive UI review (banner-flagged). |
| `docs/PAINT_SYSTEM_DEFINITION_DRAFT_PL.md` | 2026-06-02 | Paint slice definition (shortage-warning note updated). |
| `docs/WORKFLOW_VALIDATION_CHECKLIST.md` | living interview log | Factory-policy questions; status per item. |
| `docs/DOC_COHERENCE_AUDIT.md` | 2026-06-17 | NA24 reconciliation report (point-in-time). |

## Convention

- Durable docs are written in **English**; live discussion/interviews may be in Polish (PL-suffixed
  capture docs are Polish by origin).
- A topic should have **one owning doc**; other docs reference it rather than restating it.

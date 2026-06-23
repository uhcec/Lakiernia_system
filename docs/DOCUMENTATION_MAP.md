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

## Living docs (the small set every session reads)

These stay in `docs/` root (plus the two root-level operational files). Keep this set small.

| Doc | Purpose |
|---|---|
| `docs/FACTORY_DOMAIN_MODEL.md` | Physical reality: the two axes (method × coating), the line, measurement, ocynk/przemalowanka, glossary. |
| `docs/WORKFLOW.md` | Workflow/business semantics: stages, quantities, corrections, READY, queue, throughput, scenario matrix S01–S12. |
| `CLAUDE.md` | Agent entry point: architecture map, read-first order, working rules, quality gate. |
| `docs/WORKING_CONTRACT.md` | How we collaborate; source-of-truth order; decision rules. |
| `IMMEDIATE_NEXT_ACTIONS.md` | The live queue of open, actionable work (start here each session). |

## Active reference / setup (live, but not read every session)

These remain in `docs/` root because they are still referenced by open work, root docs, or setup.

| Doc | Purpose |
|---|---|
| `HARDENING_BACKLOG.md` | *Closed* hardening items (verify currency before trusting). |
| `docs/DEVELOPMENT_RUNBOOK.md` | Setup / run / seed / verify commands. |
| `README.md` | Project overview + setup. |
| `docs/AUTHZ_DESIGN_PROPOSAL.md` | NA1 authorization design record (IMPLEMENTED); referenced by `README.md`. |
| `docs/STATION_IDENTITY_AND_AUDIT.md` | Station identity + audit layer (updated post-NA1); referenced by `WORKING_CONTRACT.md`. |
| `docs/FACTORY_USAGE_NOTES.md` | Factory-stakeholder capture (2026-05-30); referenced by `WORKING_CONTRACT.md`. |
| `docs/WORKFLOW_VALIDATION_CHECKLIST.md` | Living factory-policy interview log; referenced by `HARDENING_BACKLOG.md` and the `/doc-audit` skill. |
| `docs/SCENARIO_WALKTHROUGH.md` | Field guide to validate S01–S12 in the running app (NA21, OPEN); referenced by `scripts/seed_walkthrough_scenario.py`. |
| `docs/ARCHITECTURE_AUDIT.md` | 2026-06-19 design review; the live source of open items NA39–NA47. |

## Archive (frozen snapshots) — `docs/archive/`

Point-in-time captures, frozen as history. They never override current truth (precedence rank 5
above). Each carries an `ARCHIVED — frozen historical snapshot` banner at the top.

| Doc | Snapshot date | Note |
|---|---|---|
| `docs/archive/FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md` | 2026-06-01 | Decisions→tasks; banner-flagged stale points. |
| `docs/archive/OPERATOR_USABILITY_AUDIT_PL.md` | 2026-05-31 | Working usability audit. |
| `docs/archive/UI_PASSIVE_REVIEW_PL.md` | 2026-05-31 | Passive UI review. |
| `docs/archive/PAINT_SYSTEM_DEFINITION_DRAFT_PL.md` | 2026-06-02 | Paint slice definition. |
| `docs/archive/DOC_COHERENCE_AUDIT.md` | 2026-06-17 | NA24 reconciliation report (point-in-time). |
| `docs/archive/CODE_CONFORMANCE_AUDIT.md` | 2026-06-17 | NA25 docs-vs-code conformance report (point-in-time). |

## Convention

- Durable docs are written in **English**; live discussion/interviews may be in Polish (PL-suffixed
  capture docs are Polish by origin).
- A topic should have **one owning doc**; other docs reference it rather than restating it.

## Maintenance — the self-check loop

The repo polices its own truth on two loops:

- **Slow (LLM, on demand — see the cadence policy below):**
  - **`/doc-audit`** (`.claude/commands/doc-audit.md`) — docs↔docs coherence; emits a coherence
    snapshot (its last run is archived at `docs/archive/DOC_COHERENCE_AUDIT.md`).
  - **`/code-audit`** (`.claude/commands/code-audit.md`) — docs↔code conformance (NA25); emits a
    conformance snapshot (its last run is archived at `docs/archive/CODE_CONFORMANCE_AUDIT.md`). Both
    are doc-scope; code divergences become `NA*` items in `IMMEDIATE_NEXT_ACTIONS.md`.
- **Fast (deterministic, every CI run):** `tests/test_documented_invariants.py` pins the business
  constants the docs commit to (paint threshold/divisors, packing slot default, JWT expiry, bcrypt
  limit, JWT-secret guard). It fails the moment code and docs disagree on a pinned value — change the
  code, its owning doc, and that test together.

## Audit cadence policy

> Adopted 2026-06-22 (NA47, owner-confirmed). The `/doc-audit` and `/code-audit` skills are wired to it.

For a single-developer factory tool, running three separate self-audits (`/doc-audit`, `/code-audit`,
plus the periodic architecture review) on a standing schedule produces audit documents that themselves
go stale and then need reconciling — the same sprawl NA45 just cleaned up. The policy:

- **Run `/doc-audit` and `/code-audit` ON-DEMAND only** — before a significant change, when docs and
  code are suspected to have drifted — **not on a standing weekly schedule.**
- **Treat their generated audit documents as DISPOSABLE scratch.** Fold each durable conclusion
  directly into its owning living doc (`docs/WORKFLOW.md` / `docs/FACTORY_DOMAIN_MODEL.md`), then
  archive or delete the snapshot rather than carrying it as a standing document. The frozen snapshots
  now under `docs/archive/` are exactly such spent outputs.
- The deterministic fast loop (`tests/test_documented_invariants.py`) stays — it is cheap and runs
  every CI build, so it carries the routine drift-detection load instead of a periodic LLM pass.

(Adopted: the `/doc-audit` and `/code-audit` skills now state on-demand cadence and write their snapshots
to `docs/archive/`.)

---
description: Documentation-coherence audit (NA24) — reconcile all repo docs into one consistent whole, grounded against code. Run on-demand before a significant change (not on a standing schedule).
---

# Documentation coherence audit (the NA24 process, made repeatable)

Run a full documentation-coherence audit of this repository — the same process that produced
`docs/archive/DOC_COHERENCE_AUDIT.md`. **Run on-demand** (before a significant change, or when docs are
suspected to have drifted), **not on a standing weekly schedule** — the deterministic
`tests/test_documented_invariants.py` fast loop carries routine drift detection (cadence policy: see
`docs/DOCUMENTATION_MAP.md`). This is doc-scope work: read code only to *ground* a claim (decide which
doc is right); never change code under this command.

## Scope (read all of these)

`CLAUDE.md`, `README.md`, `IMMEDIATE_NEXT_ACTIONS.md`, `HARDENING_BACKLOG.md`, and everything under
`docs/` (and the frozen snapshots under `docs/archive/`) — especially the living set
`FACTORY_DOMAIN_MODEL.md`, `WORKFLOW.md`, `WORKING_CONTRACT.md`, `DEVELOPMENT_RUNBOOK.md`,
`DOCUMENTATION_MAP.md`, the active-reference docs `WORKFLOW_VALIDATION_CHECKLIST.md`,
`FACTORY_USAGE_NOTES.md`, `STATION_IDENTITY_AND_AUDIT.md`, `AUTHZ_DESIGN_PROPOSAL.md`, and the archived
snapshots `docs/archive/FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md`,
`docs/archive/PAINT_SYSTEM_DEFINITION_DRAFT_PL.md`, and the `docs/archive/*_AUDIT_PL` / `*_REVIEW_PL`
files. Use `DOCUMENTATION_MAP.md` for each doc's role and the precedence order.

## Method

1. Build a topic map across the docs.
2. For each topic, record every:
   - **contradiction** between docs,
   - **duplicate / overlapping** statement that should have one owning doc,
   - **stale** claim (verify against the current code/tests — e.g. grep the implementing function,
     confirm a constant/threshold, check a closed `NA*` item), and
   - **missing** topic the coherent whole still needs.
3. **Ground numeric/behavioral claims against code** before declaring a doc right or wrong (e.g. paint
   thresholds, gated endpoints, field names). Cite `file:line`.
4. Respect the hierarchy: physical truth (`FACTORY_DOMAIN_MODEL.md`) → `WORKFLOW.md` → code → snapshots.
   Dated snapshot docs must not override current truth; they carry a "MIGAWKA HISTORYCZNA" banner.

## Output

- Write the run to `docs/archive/DOC_COHERENCE_AUDIT.md` (disposable scratch — date the run, list
  findings with proposed resolution and whether each is safe-to-fix vs needs-owner-decision).
- **Fold durable conclusions into the owning living doc** (`WORKFLOW.md` / `FACTORY_DOMAIN_MODEL.md`)
  rather than leaving them only in the snapshot; the snapshot is then a spent artifact (cadence policy in
  `DOCUMENTATION_MAP.md`).
- Summarize in chat: new drift since the last run, and the owner questions (if any).

## Rules

- **No code changes.** Divergences that require code go to `IMMEDIATE_NEXT_ACTIONS.md` as `NA*` items
  (this is where NA25/NA26 came from).
- **Confirm factory policy with the owner** rather than guessing; apply only clearly-safe doc edits, and
  for dated snapshots prefer a historical banner over rewriting the body (owner's standing choice).
- Keep durable docs in English (interview/discussion may be Polish).
- Commit the refreshed audit (finished work on `main`).

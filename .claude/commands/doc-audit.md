---
description: Documentation-coherence audit (NA24) — reconcile all repo docs into one consistent whole, grounded against code. Intended cadence weekly.
---

# Documentation coherence audit (the NA24 process, made repeatable)

Run a full documentation-coherence audit of this repository — the same process that produced
`docs/DOC_COHERENCE_AUDIT.md`. **Intended cadence: weekly.** This is doc-scope work: read code only to
*ground* a claim (decide which doc is right); never change code under this command.

## Scope (read all of these)

`CLAUDE.md`, `README.md`, `IMMEDIATE_NEXT_ACTIONS.md`, `HARDENING_BACKLOG.md`, and everything under
`docs/` — especially `FACTORY_DOMAIN_MODEL.md`, `WORKFLOW.md`, `WORKFLOW_VALIDATION_CHECKLIST.md`,
`FACTORY_USAGE_NOTES.md`, `FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md`,
`PAINT_SYSTEM_DEFINITION_DRAFT_PL.md`, `STATION_IDENTITY_AND_AUDIT.md`, `AUTHZ_DESIGN_PROPOSAL.md`,
the two `*_AUDIT_PL` / `*_REVIEW_PL` files, `WORKING_CONTRACT.md`, `DEVELOPMENT_RUNBOOK.md`,
`DOCUMENTATION_MAP.md`. Use `DOCUMENTATION_MAP.md` for each doc's role and the precedence order.

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

- Refresh `docs/DOC_COHERENCE_AUDIT.md`: date the run, list findings with proposed resolution and
  whether each is safe-to-fix vs needs-owner-decision.
- Summarize in chat: new drift since the last run, and the owner questions (if any).

## Rules

- **No code changes.** Divergences that require code go to `IMMEDIATE_NEXT_ACTIONS.md` as `NA*` items
  (this is where NA25/NA26 came from).
- **Confirm factory policy with the owner** rather than guessing; apply only clearly-safe doc edits, and
  for dated snapshots prefer a historical banner over rewriting the body (owner's standing choice).
- Keep durable docs in English (interview/discussion may be Polish).
- Commit the refreshed audit (finished work on `main`).

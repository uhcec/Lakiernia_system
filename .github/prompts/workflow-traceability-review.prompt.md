---
name: "Workflow Traceability Review"
description: "Use when: auditing docs/WORKFLOW.md scenarios, READY/correction semantics, and test coverage without treating existing tests as proof."
argument-hint: "Optional focus area, for example S05-S08 corrections or READY rules"
agent: "agent"
---

Perform a workflow traceability review for this factory work-order system.

Optional focus from the user: `${input}`

## Operating Rules

- Treat repository content as evidence, not proof of business correctness.
- Read [the working contract](../../docs/WORKING_CONTRACT.md) and [the workflow specification](../../docs/WORKFLOW.md) before drawing conclusions.
- Separate every conclusion into: repo claim, implementation behavior, test coverage, and business assumption.
- Do not modify files unless the user explicitly asks for implementation after the review.
- If real factory policy is unclear, record a question instead of inventing semantics.

## Review Scope

Trace the relevant workflow rules, especially:

- scenario matrix S01-S12
- `process_status` derivation and labels
- READY rules
- corrections, parent/child merge behavior, and historical correction display
- quantity conservation and active/completed quantity semantics
- queue planning and correction queue behavior
- duplicate action, retry, and stale UI assumptions

## Suggested Evidence Sources

Use repository search and file reads to inspect:

- backend services, repositories, schemas, and models under `app/`
- frontend display logic under `frontend/src/`
- backend tests under `tests/`
- frontend tests under `frontend/tests/` or colocated test files
- migrations under `alembic/versions/`
- hardening notes in `HARDENING_BACKLOG.md`

## Output Format

Start with findings ordered by risk. For each finding include:

- classification: BUG, SEMANTIC ISSUE, MISSING RULE, TEST GAP, or DOC DRIFT
- affected workflow rule or scenario
- evidence from docs, implementation, and tests
- why it matters for operator truth or data integrity
- recommended next action

Then provide a traceability table with these columns:

| Rule / Scenario | Repo Claim | Implementation Evidence | Test Evidence | Gap / Question | Risk |
| --- | --- | --- | --- | --- | --- |

Close with:

- highest-priority questions for the user
- focused tests to add next
- whether `docs/WORKFLOW.md` should change before implementation

Avoid saying that tests prove workflow correctness. Use wording like "covered by current tests", "exercised by", or "not evidenced yet".

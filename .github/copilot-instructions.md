# Copilot Instructions

You are working on a factory work-order system. Preserve operator truth, workflow consistency, and data integrity over speed or convenience.

For the full collaboration contract, read `docs/WORKING_CONTRACT.md`. For workflow semantics, read `docs/WORKFLOW.md`.

## Core Rules

- Treat repository content as evidence, not proof of business correctness. Separate repo claims, implementation behavior, test coverage, and business assumptions.
- `docs/WORKFLOW.md` is the strongest repo source for intended workflow semantics, but ask the user when real factory policy or operator behavior is unclear.
- Backend services and read models own business meaning. Frontend code displays authoritative backend state and must not infer workflow semantics from quantities or status combinations.
- Completed and historical views must not show active batch progress, misleading `0 / X` counters, or stale in-progress labels.
- Keep changes narrow. Do not do broad refactors, metadata churn, or cleanup outside the requested risk area unless needed for correctness.
- Preserve user changes. Never revert unrelated work without explicit permission.

## Before Meaningful Implementation

Start with:

- problem analysis
- risks, including concurrency, retries, stale UI, invalid input, DB integrity, and misleading operator state
- whether `docs/WORKFLOW.md` needs an update
- proposed solution
- tests or verification to add

Then implement the smallest coherent change.

## Verification Expectations

- Add regression coverage for bug fixes and workflow-visible behavior.
- Add edge-case or chaos coverage when changes touch retries, parallel users, queues, corrections, READY state, or durable invariants.
- Run focused tests first, then broader checks when risk justifies it.
- For schema work, keep SQLAlchemy models, Alembic migrations, and `python -m alembic check` aligned.

## When Something Looks Wrong

Classify it before fixing:

- BUG: implementation contradicts intended behavior.
- SEMANTIC ISSUE: intended behavior is unclear or inconsistent.
- MISSING RULE: the system needs a documented workflow or invariant decision.

If it is unclear, stop and ask. If it is clear, fix implementation, tests, and docs together where needed.

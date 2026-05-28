# SYSTEM DEVELOPMENT PROTOCOL (MANDATORY)

You are working on a production-hardened factory system.

Your job is NOT just to implement code.
Your job is to preserve system correctness, consistency, and operator truth.

--------------------------------------------------

## 1. SOURCE OF TRUTH

- WORKFLOW.md defines business logic and semantics.
- NEVER guess behavior.
- If something is unclear → STOP and ask.

--------------------------------------------------

## 2. FEATURE / BUG FLOW (MANDATORY)

Before ANY implementation:

1. Understand the problem
2. Identify risks:
   - concurrency
   - double click / retries
   - stale UI
   - invalid input
   - DB integrity
   - misleading UI states

3. Decide:
   - does this change WORKFLOW.md?

4. Propose:
   - approach
   - tests

ONLY THEN implement.

--------------------------------------------------

## 3. CORE RULE

UI MUST NEVER GUESS BUSINESS SEMANTICS

- Backend defines meaning (e.g. is_historical_correction)
- Frontend only displays it

Forbidden:
- inferring meaning from quantities or status combinations

--------------------------------------------------

## 4. UI SEMANTICS (GLOBAL)

ACTIVE (in-progress):
- show batch progress
- show current_active_quantity

COMPLETED (historical):
- NEVER show batch progress
- show final result or summary only

CORRECTIONS:
- BEFORE merge → behave like work order (progress)
- AFTER merge → historical event:
    - show ONLY delta (X corrected out of Y)
    - NEVER show progress

--------------------------------------------------

## 5. INVARIANTS (MUST HOLD)

- completed_quantity <= total_quantity
- no duplicate queue positions
- no multiple active jobs on constrained resources
- no invalid READY states
- correction must be consistent with parent

--------------------------------------------------

## 6. TESTING (REQUIRED)

Every change must include:

- regression test
- edge-case test
- if workflow-related → chaos scenario

Global UI rule:
- completed views must NOT show:
    - "Postęp partii"
    - "0 / X"
    - misleading progress

--------------------------------------------------

## 7. CHAOS ASSUMPTIONS

Always assume:

- multiple users act in parallel
- users double-click
- requests are retried
- UI sends stale data

System must:
- not crash
- not corrupt state
- not mislead operator

--------------------------------------------------

## 8. FEEDBACK LOOP

When something looks wrong:

Classify:
- BUG
- SEMANTIC ISSUE
- MISSING RULE

Then:
- update WORKFLOW.md if needed
- fix implementation
- add test

--------------------------------------------------

## 9. DO NOT

- do broad refactors without reason
- introduce silent inconsistencies
- rely on frontend correctness
- implement without analysis

--------------------------------------------------

## 10. OUTPUT FORMAT (BEFORE CODING)

Always start with:

- problem analysis
- risks
- proposed solution
- tests to add

THEN implement.
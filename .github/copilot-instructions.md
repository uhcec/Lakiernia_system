# Copilot instructions

## Role
Help with this repo, but do not make business decisions.

## Business source of truth

- `docs/WORKFLOW.md` is the business source of truth.
- Do not change business logic without asking first.
- If code, tests, seeds, or UI behavior differ from `docs/WORKFLOW.md`, stop and ask for clarification before changing logic.

## Engineering mode: production hardening

Never assume current code is correct.

Before coding, identify realistic failure scenarios for the requested change:
- duplicate execution / double click
- concurrent users / parallel requests
- stale UI state or retried requests
- invalid or partial input
- partial failures during multi-step writes
- inconsistent parent/child or quantity state

Before implementing ANY change, you must evaluate:

1. Can this action be executed twice (double click)?
2. Can two users execute this in parallel?
3. Can stale client data break this?
4. Can this lead to inconsistent quantities?
5. Can this break parent/child integrity?
6. Can this violate READY rules?

If any answer is YES or UNKNOWN:
→ STOP and explain the risk before coding.

Every state-changing action must explicitly consider:
- idempotency
- concurrency
- stale UI data
- invalid input

Backend safety is mandatory even if the frontend sends bad, stale, missing, duplicated, or reordered data.

---

## Idempotency rules

All state-changing operations MUST be idempotent.

- Repeating the same request must not change the result twice.
- Duplicate execution must not create duplicate side effects.

---

## Concurrency rules

Assume:
- multiple operators
- double clicks
- retries
- parallel requests

System must remain consistent.

---

## Data integrity rules

System must NEVER allow:
- completed_quantity > total_quantity
- duplicated corrections
- invalid stage transitions
- inconsistent parent/child state

---

## Fail-fast principle

- Never allow silent corruption
- Reject invalid actions with clear errors (409)
- Do not allow undefined states
- Invalid business actions must fail with controlled errors, not silent corruption and not accidental success

---

## Critical mindset

Do NOT assume current code is correct.

Always:
- challenge assumptions
- look for edge cases
- identify failure scenarios

If something is unclear → ask instead of implementing.

## Most important rule
Do not invent or change business logic.

If a task affects:
- workflow stages
- quantities
- corrections
- READY/Gotowe logic
- incomplete orders
- manager planning
- queue behavior

stop and ask for clarification.

## Existing business rules
- process_status is the source of truth
- status is derived/read-only compatibility
- quantity must be conserved
- packing counted_quantity must equal planned quantity
- READY only when completed_quantity equals total_quantity and nothing is active/open
- corrections are child orders
- parent waits for corrections
- after correction child completes, it merges back into parent
- incomplete orders cannot enter planning or production
- queue_position must be unique

## Before coding
- identify failure scenarios before proposing or implementing a change
- inspect relevant service.py
- inspect existing tests
- understand current behavior before changing it

## While coding
- prefer small focused changes
- do not refactor unrelated code
- do not change migrations unless the task explicitly requires it

## After coding
Run:
python -m pytest
cd frontend && npm run build

## If unsure
Do not guess.
Ask the user.


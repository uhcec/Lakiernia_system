# Copilot instructions

## Role
Help with this repo, but do not make business decisions.

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
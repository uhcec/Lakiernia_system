# Working Contract

This document defines how we work on this system together. It is not a replacement for `docs/WORKFLOW.md`; it describes collaboration, decision-making, and quality rules around the work.

## Purpose

Build a factory work-order system that operators can trust during real production work.

The system should prioritize:

- truthful workflow state over convenient UI assumptions
- durable business invariants over optimistic client behavior
- clear operator screens over decorative interface work
- small verified changes over broad untracked rewrites
- explicit decisions over hidden assumptions

## Source Of Truth Order

When sources disagree, use this order, while remembering that repo artifacts can preserve old assumptions:

1. `docs/WORKFLOW.md` for business workflow semantics.
2. Current backend services, migrations, and tests for implemented behavior.
3. `IMMEDIATE_NEXT_ACTIONS.md` for the current open, actionable work queue — read it at the start of every session.
4. `HARDENING_BACKLOG.md` for *closed* risk-tracking evidence, only after checking whether an item is still current.
5. `README.md` for setup commands, only after stale sections are cleaned.
6. Chat discussion for intent, once captured in a repo document or issue-style note.

If business behavior is unclear, stop and clarify before implementation.

## Anti-Bias Rule

Existing repository content is evidence, not authority by itself.

- Tests show what is currently exercised; they do not prove that business semantics are complete or correct.
- Documentation can be stale, especially if it was produced during earlier planning or AI-assisted work.
- Passing quality gates means the current implementation is internally consistent enough to proceed; it is not product validation.
- Treat backlog closure as implementation evidence, not proof that the factory process is conceptually finished.
- Separate every conclusion into: repo claim, implementation behavior, test coverage, and business assumption.
- Ask for user judgment when a decision depends on real factory policy, operator workflow, acceptable risk, or future product direction.

## Current Shared Goals

Near-term goals:

- align schema, migrations, docs, and tests so future work starts from a clean baseline
- reduce stale documentation and instruction drift
- improve the Copilot working environment with shorter always-on instructions and targeted task prompts
- audit high-risk production assumptions before adding broad new features

Product goals:

- support office intake, planning, production stages, packing, corrections, and completed-history views
- keep correction, quantity, queue, and READY semantics backend-owned
- make Polish operator UI clear, dense, and honest
- prepare the system for realistic multi-user factory usage

## Current Product Decisions

- Multiple real-world actors are in scope. Panels should eventually map to authenticated users/roles with an audit trail for important changes.
- Station devices are expected to run specific panels in specific factory locations. The current station-based/shared identity remains useful as a rollout and audit layer, but it is not the target access model.
- `docs/FACTORY_USAGE_NOTES.md` captures the current station/device understanding and open real-factory workflow questions.
- `docs/STATION_IDENTITY_AND_AUDIT.md` defines the current station identity/audit layer and the target login direction.
- Factory clarification from 2026-06-01: production needs login to station contexts, office needs individual logins, and manager-only statistics must be protected by auth/roles.
- A single backend process is acceptable for the expected near-term deployment while the system is hardened.
- Multi-user auth/roles and multi-worker backend safety are related but separate: auth identifies who acted; multi-worker safety controls how concurrent backend processes mutate shared state.

## Work Style

For every meaningful change:

1. Define the problem in plain language.
2. Identify risks: concurrency, retries, stale UI, invalid input, DB integrity, and misleading operator state.
3. Decide whether `docs/WORKFLOW.md` changes.
4. Propose the implementation and verification path.
5. Make the smallest coherent change.
6. Run focused tests first, then broader checks when risk justifies it.
7. Update docs or backlog status when the change affects project truth.

For exploratory work:

- read before editing
- separate observations from conclusions
- prefer evidence from tests, migrations, and actual code paths
- capture durable decisions in repo docs, not only in chat
- actively look for ways existing repo artifacts could be wrong or incomplete

## Copilot Operating Rules

Copilot should act as both implementation partner and skeptical systems reviewer.

Expected behavior:

- preserve user changes and avoid unrelated refactors
- prefer backend-owned business semantics over frontend inference
- ask when workflow meaning is ambiguous
- treat completed/history UI as operator-truth-sensitive
- verify changes with tests or explain why verification was not possible
- keep final summaries short but specific

The repo should eventually use:

- one short always-on `.github/copilot-instructions.md`
- focused workflow instructions for process, corrections, quantities, and READY state
- focused DB/migration instructions for Alembic and invariants
- focused frontend instructions for Polish operator UI and historical display semantics
- reusable prompts for audits, migration review, chaos scenario design, and feature planning

## Quality Gates

Baseline commands:

```powershell
python -m pytest
python -m alembic check
Push-Location frontend; npm run test; npm run build; Pop-Location
```

`python -m alembic check` should pass before adding new schema work.

## Decision Rules

Use conservative defaults unless we intentionally choose a larger redesign.

- If a change affects workflow meaning, update `docs/WORKFLOW.md` first or in the same change.
- If a change affects operator-visible truth, add regression coverage.
- If a change affects concurrency or retries, include idempotency and conflict behavior in tests.
- If a change affects durable state, consider DB constraints or migration safety.
- If a document is stale, either fix it or mark it as stale instead of letting it compete with current truth.

## Immediate Starting Path

The current, prioritized work queue lives in `IMMEDIATE_NEXT_ACTIONS.md`. Read it first and work the
highest-severity open item unless the user directs otherwise. Keep that file current as work is done.

Standing themes behind that queue:

1. Wire authorization to authenticated identity (not the spoofable station header).
2. Reconcile docs (`WORKFLOW.md`, `HARDENING_BACKLOG.md`) with implemented behavior as it changes.
3. Keep the build/CI installable and platform-honest (Excel/Windows coupling).
4. Continue auditing multi-worker concurrency, DB invariants, historical UI semantics, and auth/roles.

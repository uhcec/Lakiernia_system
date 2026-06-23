---
description: Code-vs-docs conformance audit (NA25) — verify the code matches the reconciled docs, topic by topic, with file:line evidence. Read-only; divergences become NA* items.
---

# Code conformance audit (the NA25 process, made repeatable)

Audit the **code** against the reconciled documentation — the same process that produced
`docs/archive/CODE_CONFORMANCE_AUDIT.md`. This is the docs↔code half of the repo's self-check loop; pair
it with `/doc-audit` (which does docs↔docs). **Run on-demand** (before a significant change), not on a
standing schedule — the deterministic `tests/test_documented_invariants.py` fast loop carries routine
drift detection (cadence policy: `docs/DOCUMENTATION_MAP.md`). **Read-only audit: do not fix code as you
go** — log divergences as `NA*` items in `IMMEDIATE_NEXT_ACTIONS.md` (that is where NA25/NA26 came from).

## First: run the fast guardian

Run `python -m pytest tests/test_documented_invariants.py` — the deterministic pin of documented
constants (paint threshold/divisors, packing slot default, JWT expiry, bcrypt limit, JWT-secret guard).
If it fails, code and docs have drifted on a pinned constant; record it before the broader pass.

## Method

1. Take the documented topics from `WORKFLOW.md` + `FACTORY_DOMAIN_MODEL.md` (build the topic list; use
   `DOCUMENTATION_MAP.md` for ownership/precedence).
2. For **each** topic, locate the implementing code (`app/`), read it, and give a verdict with
   `file:line` evidence:
   - **CONFORMS** — code matches the doc.
   - **DIVERGES** — code contradicts the doc (classify: doc-wrong → fix doc later; code-wrong → fix code
     later; needs-owner-decision → ask).
   - **DOC-UNDERSTATES / DOC-STALE** — code is correct/broader; a doc is narrower or out of date.
   - **RELIED-ON-EVIDENCE** — not re-read this pass; trusted closed `HARDENING` items + tests (say so).
3. Check both directions: behavior the docs require but code lacks/contradicts, **and** behavior the code
   has that the docs don't describe.
4. Spot-check the frontend where the doc is about operator-visible truth (e.g. which quantity a station
   shows — that is how NA26 was found).

## Output

- Write the run to `docs/archive/CODE_CONFORMANCE_AUDIT.md` (disposable scratch): date the run, per-topic
  verdicts + evidence, and a summary of divergences. The actionable divergences live in the backlog below;
  the snapshot is a spent artifact (cadence policy in `DOCUMENTATION_MAP.md`).
- Add each actionable divergence to `IMMEDIATE_NEXT_ACTIONS.md` as a new `NA*` item (severity, `file:line`,
  required fix, acceptance).

## Rules

- **No code changes under this command.** Verdicts + logged items only.
- Confirm factory policy with the owner before calling code "wrong" on a policy question.
- Commit the refreshed audit (finished work on `main`).

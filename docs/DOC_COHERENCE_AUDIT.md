# Documentation Coherence Audit (NA24)

Status: **DRAFT — findings pass complete 2026-06-17.** This is the written reconciliation deliverable
for NA24 (`IMMEDIATE_NEXT_ACTIONS.md`). It reviews **all** repository documentation for internal
consistency, single-ownership of each topic, staleness, and missing topics. It is doc-scope only;
auditing the docs against the *code* is the separate task NA25 (a few code constants were checked here
only to decide which doc is right).

Method: read every doc in scope, build the topic map below, and record each (1) contradiction between
docs, (2) duplicate/overlapping statement without a single owner, (3) stale claim, and (4) topic that
the coherent whole still lacks. Each item carries a proposed resolution and whether it needs an owner
decision or is safe to apply.

## Doc inventory and intended role

| Doc | Role | Currency |
|---|---|---|
| `CLAUDE.md` | Agent entry point + architecture map + read-first hierarchy | Current (references FACTORY_DOMAIN_MODEL) |
| `README.md` | Project overview, setup, scope | **Stale spots** (auth, Excel import, JWT default) |
| `docs/FACTORY_DOMAIN_MODEL.md` | **Physical ground truth** (axes, line, measurement) | New (2026-06-17), DRAFT with `[TBD]`s |
| `docs/WORKFLOW.md` | System workflow semantics (strongest behavioural SoT) | Mostly current |
| `docs/WORKFLOW_VALIDATION_CHECKLIST.md` | Factory-policy interview/decision log | Current except #9 internal slip |
| `docs/FACTORY_USAGE_NOTES.md` | 2026-05-30 factory-stakeholder capture, by panel | Dated capture; some items now superseded |
| `docs/FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md` | 2026-06-01 decisions→tasks snapshot | **Materially stale** (QC, packing, paint) |
| `docs/PAINT_SYSTEM_DEFINITION_DRAFT_PL.md` | Paint slice definition | Stale on shortage warning |
| `docs/STATION_IDENTITY_AND_AUDIT.md` | Station identity + audit layer | Updated for NA1; 2 internal slips |
| `docs/AUTHZ_DESIGN_PROPOSAL.md` | NA1 design record | Current (marked IMPLEMENTED) |
| `docs/OPERATOR_USABILITY_AUDIT_PL.md` | 2026-05-31 working usability audit | Dated; several "open/missing" now done |
| `docs/UI_PASSIVE_REVIEW_PL.md` | 2026-05-31 passive UI review | Dated; several "open/missing" now done |
| `docs/WORKING_CONTRACT.md` | How we collaborate; source-of-truth order | Current except hierarchy omits domain model |
| `docs/DEVELOPMENT_RUNBOOK.md` | Setup/run/seed/verify | Current except JWT-default note |
| `HARDENING_BACKLOG.md` | Closed hardening evidence | Current |
| `IMMEDIATE_NEXT_ACTIONS.md` | Live open-work queue | Current |

## A. Contradictions between documents

### A1. Paint-demand formula threshold: 100 m² vs 70 m² — NEEDS OWNER DECISION
- `WORKFLOW.md:461`: `/4` below **100 m²**, `/6` at ≥100 m².
- `FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md:113`: below **70 m²** → `/4`, above 70 → `/6`.
- `UI_PASSIVE_REVIEW_PL.md:125` and the paint open-questions repeatedly call out "dokładnie 70 m2 w formule".
- **Code check:** `app/work_orders/schemas.py:315` uses `< 100`. So code + WORKFLOW agree on **100**.
- *But* the decision map's 70 is a captured 2026-06-01 factory answer, so this may be a real policy gap
  rather than a typo (anti-bias rule: code is not proof of correct policy).
- **Resolution:** confirm the real threshold with the owner. If 100 is correct, fix the decision map
  and UI-review mentions; if 70 is correct, this becomes an NA25 code defect. **Open question Q1.**

### A2. Paint shortage warning: "required/works" vs "not in first slice" — SAFE TO FIX (code-verified)
- Says it warns / is needed: `WORKFLOW.md:462`, `FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md:112`.
- Says it is deferred / not in first slice: `PAINT_SYSTEM_DEFINITION_DRAFT_PL.md:11`,
  `FACTORY_USAGE_NOTES.md:25`, `WORKFLOW_VALIDATION_CHECKLIST.md:431`.
- **Code check:** `calculate_paint_shortage_quantity_kg` + read-model fields
  `paint_inventory_insufficient_for_prediction` / `paint_inventory_shortage_quantity_kg`
  (`app/work_orders/schemas.py:319`, `service.py:757`) — the warning **is implemented**.
- **Resolution:** the three "deferred" docs are stale. Update them to state the intake shortage warning
  is implemented (predicted demand vs current stock). WORKFLOW is correct.

### A3. README auth model is pre-NA1 (header-based) — SAFE TO FIX
- `README.md:231-233`: "today the backend authorizes station actions from the `X-Station-Id` header …
  not from the logged-in account's role — see NA1."
- Contradicts `WORKFLOW.md:288-293`, `AUTHZ_DESIGN_PROPOSAL.md` (IMPLEMENTED),
  `STATION_IDENTITY_AND_AUDIT.md:5`, `HARDENING_BACKLOG.md:206`, and NA1 (Done).
- **Resolution:** rewrite the README login note: authorization is derived from the JWT user's role;
  `X-Station-Id` is inert/audit-only.

### A4. README Excel-import side-effect note is pre-NA5 — SAFE TO FIX
- `README.md:308`: "importing `app/work_orders/service.py` currently starts an Excel worker thread."
- Contradicts CLAUDE.md gotchas and NA5 (Done): the converter is lazy; import has no side effects.
- **Resolution:** update to the lazy/fail-fast description.

### A5. JWT default-secret note is pre-NA12 — SAFE TO FIX
- `README.md:113-114` and `DEVELOPMENT_RUNBOOK.md:74` say `JWT_SECRET` "has an insecure built-in
  default" without qualification.
- Post-NA12, the usable default is rejected outside development (fails fast). The note is misleading.
- **Resolution:** qualify: a dev-only default exists; non-dev refuses to start with it.

### A6. QC document status: "not implemented" vs "implemented" — SAFE TO FIX
- "Not implemented": `FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md:78`,
  `OPERATOR_USABILITY_AUDIT_PL.md:51`, `UI_PASSIVE_REVIEW_PL.md:129`.
- Implemented: `WORKFLOW_VALIDATION_CHECKLIST.md` #10 (corrected 2026-06-17), `README.md:36`, code.
- **Resolution:** update the three stale docs (it ships: Excel template → fill → PDF).

### A7. Packing exclusivity: "no lock / open question" vs N-slot capacity — SAFE TO FIX
- "Open / no lock / single exclusive resource": `FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md:229`,
  `UI_PASSIVE_REVIEW_PL.md:116-119`, `OPERATOR_USABILITY_AUDIT_PL.md:172`, `FACTORY_USAGE_NOTES.md:147`.
- Implemented as **N configurable slots** (default 2, automatic reserves at HANGING start, manual
  override): `WORKFLOW.md:237-243`, `WORKFLOW_VALIDATION_CHECKLIST.md` #9 (NA22), code.
- **Resolution:** update the stale docs; note the model is now capacity (N slots), not strict single.

### A8. Checklist #9 internal contradiction: default capacity 1 vs 2 — SAFE TO FIX
- `WORKFLOW_VALIDATION_CHECKLIST.md:371`: "small **capacity** model (default **1**, manual can open a
  2nd slot)."
- Same doc `:373,:380` and `WORKFLOW.md:238`: `packing_max_concurrent_slots` **default 2**.
- **Resolution:** correct line 371 to "default 2" (or describe behaviour as single-station exclusivity
  by default with up to N via override), matching the implemented setting.

### A9. STATION_IDENTITY internal slips — SAFE TO FIX
- `STATION_IDENTITY_AND_AUDIT.md:58-59` still describes accepting missing station as `UNKNOWN` during
  rollout, while `:134` (and NA1) say the `UNKNOWN` allow-bypass was removed. Internal drift.
- `:160` lists `SURFACE_PREPARATION: … confirm quantity discrepancy`, but the confirmed policy
  (`WORKFLOW.md`, `FACTORY_USAGE_NOTES.md:55`, checklist #3) is **no separate discrepancy-confirmation
  step**. Stale permission line.
- **Resolution:** align both spots with the confirmed/closed state.

## B. Stale dated snapshots (whole-doc currency) — NEEDS OWNER STEER (mark-historical vs update)

These docs are explicitly dated working captures and self-declare as non-source-of-truth, but they now
contain claims that contradict current truth (see A6/A7 above). They "compete with current truth"
(WORKING_CONTRACT decision rule: fix or mark stale).

- **`FACTORY_DECISION_IMPLEMENTATION_MAP_PL.md`** (2026-06-01): sections 3 (QC not implemented), 4
  (paint demand 70 / "system ma wykrywać" already done), 8 (no PACKING lock) are outdated. Either add a
  prominent "HISTORICAL SNAPSHOT — verify against WORKFLOW.md" banner, or update the few hard conflicts.
- **`OPERATOR_USABILITY_AUDIT_PL.md`** & **`UI_PASSIVE_REVIEW_PL.md`** (2026-05-31): several "missing /
  open" items now implemented (QC doc, packing exclusivity, automatic paint-consumption UI). Lower
  priority (clearly dated audits); add a short "since this audit, X/Y/Z shipped" note or refresh lines.

**Open question Q2:** for the dated snapshot docs, prefer (a) edit in place to current truth, or
(b) keep them frozen as history with a clear "superseded — see current docs" banner?

## C. Duplication without a single owner (drift risk)

- **Station list columns** are specified in `WORKFLOW.md:197-251`, `FACTORY_USAGE_NOTES.md` (per panel),
  `WORKFLOW_VALIDATION_CHECKLIST.md` #8, and `STATION_IDENTITY_AND_AUDIT.md`. Currently consistent.
  **Owner = `WORKFLOW.md`;** others should reference it, not restate.
- **Role/permission matrix** appears in `WORKFLOW.md` (Station Permissions), `STATION_IDENTITY` (Permission
  Direction), `AUTHZ_DESIGN_PROPOSAL` (table), checklist #4. Already drifted once (A9 `:160`).
  **Owner = `WORKFLOW.md` Station Permissions** (+ AUTHZ as the closed design record); others reference.
- **Correction reason categories** (`niedomalowanie`, `za grubo`, `wtrącenia`, `inne`) copied into ≥5
  docs. Keep the canonical list in `WORKFLOW.md`; others reference.

## D. Missing topics the coherent whole still needs

### D1. The new physical-truth doc is not wired into every entry-point hierarchy
- `CLAUDE.md` lists `FACTORY_DOMAIN_MODEL.md` as read-first, but `README.md` "Truth And Evidence" and
  `WORKING_CONTRACT.md:21` "Source Of Truth Order" do **not** mention it. **Resolution:** add it to both
  (physical truth → `WORKFLOW.md` → code), so all three entry points agree on one hierarchy.

### D2. Throughput/decoral measurement is split and framed two ways
- `WORKFLOW.md` "Throughput Reporting" frames decoral as "two coats, two separate work events";
  `FACTORY_DOMAIN_MODEL.md` §4 frames the total as "one product, counted once, two cross-sections".
  They are reconcilable but currently read as different stories. **Resolution:** make WORKFLOW's
  Throughput section reference §4 as the canonical measurement model (NA23 will touch this section).

### D3. Two-axis model not stated in WORKFLOW.md
- WORKFLOW jumps to stage flows without stating production-method × coating as independent axes (now in
  `FACTORY_DOMAIN_MODEL.md` §1). **Resolution:** add a one-line cross-reference at the top of WORKFLOW's
  Stage Model.

### D4. Decoral packing not noted as intentionally folded into DECORAL_PRODUCTION
- `FACTORY_USAGE_NOTES.md:109` ("operators … pack the elements, then finish") and the physical reality
  (separate decoral packing station) aren't reconciled in WORKFLOW's stage model, which ends DECORAL at
  `DECORAL_PRODUCTION`. **Resolution:** note in WORKFLOW that decoral packing is folded into the
  `DECORAL_PRODUCTION` completion (no separate tracked stage), per `FACTORY_DOMAIN_MODEL.md` §1.

### D5. No glossary / single terminology table
- Terms are scattered: element vs work order, profile vs accessory, RAL vs decoral, decoral *pass*
  (przejazd) vs decoral *product*, przemalowanka, ocynk, incomplete-on-arrival, READY. **Resolution:**
  add a single Glossary (likely in `FACTORY_DOMAIN_MODEL.md` or a new short `docs/GLOSSARY.md`).

### D6. Physical meaning of several first-class concepts is undocumented
- **Ocynk** — defined only as "a marker; station work differs"; never explained (galvanizing? where in
  the line? why station work differs).
- **Przemalowanka** — operational behaviour is documented; its physical meaning (repaint of existing
  coated parts?) is not.
- **Surface preparation** — `FACTORY_DOMAIN_MODEL.md` §2 leaves it as "shared entry"; usage notes imply
  washing. What it physically is (wash? blast? degrease?) is undocumented.
- **Incomplete-on-arrival** — used throughout code/WORKFLOW but never explained as a factory concept
  (what it means operationally, who clears it, why).
- **Resolution:** capture these in `FACTORY_DOMAIN_MODEL.md` (interview items; some already `[TBD]`).

### D7. No documentation map / precedence page, and the two existing hierarchies disagree
- `CLAUDE.md` and `WORKING_CONTRACT.md` each give a partial, now-divergent source-of-truth order (D1).
  **Resolution:** one canonical "documentation map + precedence" (this audit's inventory table can seed
  it), referenced from both entry points.

## E. Proposed canonical hierarchy (to make explicit everywhere)

1. `FACTORY_DOMAIN_MODEL.md` — physical reality (why).
2. `WORKFLOW.md` — system behaviour/semantics (what the system does).
3. Code + migrations + tests — implemented behaviour.
4. `IMMEDIATE_NEXT_ACTIONS.md` — live open work; `HARDENING_BACKLOG.md` — closed evidence.
5. Capture/snapshot docs (`FACTORY_USAGE_NOTES`, `FACTORY_DECISION_*`, audits) — historical evidence,
   never override 1–2.
6. `README.md` / `DEVELOPMENT_RUNBOOK.md` — setup only.

## Open questions for the owner

- **Q1 (A1):** Paint-demand threshold — is the correct split **100 m²** (code + WORKFLOW) or **70 m²**
  (2026-06-01 decision capture)? This decides whether the decision-map/UI-review get corrected, or
  whether the code is wrong (→ NA25 defect).
- **Q2 (B):** For the dated snapshot docs (decision map, the two PL audits) — edit them to current truth,
  or freeze them as history with a "superseded" banner?
- **Q3 (scope):** Apply the SAFE-TO-FIX edits (A2–A9, D1–D4) now as part of NA24, or after you review
  this report?

## Status / next steps

- Findings pass: **done**.
- Pending owner input: Q1, Q2, Q3.
- After answers: apply agreed doc edits, add the glossary/missing-concept interview items, then proceed
  to NA25 (docs-vs-code conformance) using the reconciled docs as the spec.

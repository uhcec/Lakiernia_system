# Workflow Validation Checklist

This checklist is for confirming real factory policy before changing workflow semantics. Repository docs, tests, and current code are evidence, not proof of business correctness.

Use this document as an interview guide with factory stakeholders. Do not treat unchecked assumptions as approved rules.

## Current Goal

Validate the business decisions that would affect station behavior, queueing, corrections, visibility, and future permission enforcement.

## Decision Status Legend

- `CONFIRMED`: factory policy is known and can be encoded in docs/tests/code.
- `WORKING ASSUMPTION`: current implementation or temporary policy used until confirmed.
- `OPEN`: needs user or factory decision before semantic changes.

## Questions To Answer

### 1. Automatic Line Overlap

Status: `OPEN`

Current repository behavior/evidence:

- Automatic orders flow through `SURFACE_PREPARATION -> HANGING -> PACKING`.
- Automatic `PRODUCTION` is preview-only.
- Backend resource locks currently allow only one active hanging job and one active automatic-line job.
- Current conservative assumption blocks starting the next automatic hanging job until the previous automatic path is completed from packing.

Factory decision needed:

- Can hanging start preparing the next automatic order while the previous order is still physically moving through automatic production?
- If yes, how many jobs can be in each physical segment at once: hanging area, crane/line, automatic production, exit/packing handoff?
- Which operator action should release hanging capacity: hanging finish, automatic display state, packing receipt, or packing completion?

Why this matters:

- This decides whether current resource locks are correct or too strict.
- It affects station availability, queue fairness, and whether operators see blocked work that could actually proceed.

### 2. Correction Review And Planning

Status: `PARTLY VALIDATED`

Current repository behavior/evidence:

- Packing with `correction_quantity > 0` automatically creates an unplanned correction work order.
- Manager later assigns manual or automatic production and queue position.
- Correction children may themselves create further correction children.
- Correction orders do not go through surface preparation; after manager planning, manual corrections start at production and automatic corrections start at hanging.
- Correction orders use the same manager planning and queue-position workflow as normal orders.

Factory decision needed:

- Do any defect types require office, manager, quality-control, or customer review before planning?
- Should the packing operator choose a defect category/reason when creating a correction?
- For simultaneous parent/correction completion, should stale duplicate actions return refresh-required conflicts or should the system reconcile automatically when invariants are still satisfied?

Why this matters:

- This decides whether correction creation needs extra fields, approval states, or blocking rules.
- It affects audit meaning: `work_order.correction_created` may be enough now, or may need defect/approval context.

### 3. Quantity Discrepancy Visibility

Status: `WORKING ASSUMPTION`

Current repository behavior/evidence:

- Office enters declared client quantity.
- Surface preparation enters counted received quantity.
- Current policy keeps declared-vs-counted discrepancy visibility office-only.
- Downstream validation uses the surface-preparation counted quantity as operational truth.

Factory decision needed:

- Should managers see declared-vs-counted discrepancies?
- Should station operators see discrepancies, or only the current operational quantity they must handle?
- Should large discrepancies require office acknowledgement before the order can continue?

Why this matters:

- This affects frontend read models and station UI copy.
- It may introduce a new hold/acknowledgement workflow if discrepancy approval is required.

### 4. Station Permissions

Status: `OPEN`

Current repository behavior/evidence:

- Shared station identity is sent with mutating frontend requests via `X-Station-Id`.
- Backend audit records the station identity for workflow-visible mutations.
- Full permission enforcement is not enabled yet.

Factory decision needed:

- Should station identity remain audit-only for now?
- If permissions are enforced, should invalid station actions be blocked immediately, or warned/logged during a rollout period?
- Are there real cases where a station needs to perform another station's action due to staffing or device placement?

Expected permission direction to validate:

- `OFFICE`: create/update intake, view discrepancies, manage attachments
- `MANAGER`: assign production type, queue/reorder, view global queue
- `SURFACE_PREPARATION`: enter counted quantity, start/finish surface prep
- `HANGING`: start/finish hanging
- `AUTOMATIC_PRODUCTION`: display-only unless future policy changes
- `MANUAL_PRODUCTION`: start/finish manual production
- `PACKING`: enter counted/OK/correction quantities, complete packing
- `DECORAL_PRODUCTION`: start/finish Decoral production

Why this matters:

- Permissions turn operational habits into hard system constraints.
- Blocking the wrong action can stop production; allowing the wrong action can corrupt operator truth.

### 5. Global Queue Semantics

Status: `WORKING ASSUMPTION`

Current repository behavior/evidence:

- Planned work orders share one global queue position namespace.
- Corrections start unplanned and join the global queue when manager-planned.
- Station panels filter the global queue to work actionable at that station.

Factory decision needed:

- Should there be one global priority list for all planned work, or separate priority lists by route/station/resource?
- Should corrections receive special queue priority by default?
- Should manager reorder show capacity/resource warnings when a high-priority item is blocked by station/resource state?

Why this matters:

- Queue semantics shape what operators believe they should do next.
- If the global queue is only a manager priority model, station panels must remain explicit about what is actionable now.

## Recommended Validation Session

1. Walk through one normal RAL manual order.
2. Walk through one normal RAL automatic order and decide automatic-line overlap.
3. Walk through one Decoral order.
4. Walk through one packing correction and one repeated correction.
5. Review which station can perform each action.
6. Review which users/stations should see quantity discrepancies.

## After Decisions Are Confirmed

For each confirmed decision:

1. Update `docs/WORKFLOW.md` and `docs/FACTORY_USAGE_NOTES.md`.
2. Add or update backend service/API tests for the confirmed invariant.
3. Add frontend tests if station visibility, action availability, or completed/history display changes.
4. Implement the smallest code change that enforces the confirmed rule.
5. Run focused tests first, then the broader backend/frontend checks based on risk.
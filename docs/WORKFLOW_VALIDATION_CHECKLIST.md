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

Status: `CONFIRMED`

Confirmed factory policy from 2026-05-30:

- The next automatic order may start `HANGING` while the previous automatic order is still in automatic production or waiting for packing.
- No physical station may process multiple work orders at the same time.
- `HANGING` capacity is released when the previous order's hanging stage is finished.
- The earlier conservative assumption that one automatic order blocks the whole path until packing completion is not correct.

Current repository behavior/evidence:

- Automatic orders flow through `SURFACE_PREPARATION -> HANGING -> PACKING`.
- Automatic `PRODUCTION` is preview-only.
- Backend resource locks currently allow only one active hanging job and one active automatic-line job.
- Current implementation evidence may still be stricter than confirmed factory policy because it historically blocked the automatic path until packing completion.

Implementation decision needed:

- Model hanging capacity separately from automatic-production capacity so a work order can leave hanging without incorrectly blocking the next hanging job.
- Preserve one-active-work-order-at-a-time per physical station/resource.

Why this matters:

- This decides whether current resource locks are correct or too strict.
- It affects station availability, queue fairness, and whether operators see blocked work that could actually proceed.

### 2. Correction Review And Planning

Status: `CONFIRMED with follow-up data field`

Confirmed factory policy from 2026-05-30:

- Packing with correction quantity should automatically create an unplanned correction work order.
- No defect type requires office, manager, quality-control, or customer approval before planning.
- Packing should record a correction reason/category.
- Correction reason/category is statistical/audit data only and does not affect the workflow path.
- Correction orders use the same manager planning and queue workflow as normal orders.
- Correction orders do not go through `SURFACE_PREPARATION`; manual corrections start at production, automatic corrections start at hanging.

Current repository behavior/evidence:

- Packing with `correction_quantity > 0` automatically creates an unplanned correction work order.
- Manager later assigns manual or automatic production and queue position.
- Correction children may themselves create further correction children.
- Correction orders do not go through surface preparation; after manager planning, manual corrections start at production and automatic corrections start at hanging.
- Correction orders use the same manager planning and queue-position workflow as normal orders.
- Simultaneous parent/correction completion should reconcile or behave idempotently when the final state is already valid; otherwise it should fail with a controlled conflict.

Implementation decision needed:

- Define the allowed correction reason/category list and where it is stored/displayed.

Why this matters:

- This decides whether correction creation needs extra fields, approval states, or blocking rules.
- It affects audit meaning: `work_order.correction_created` may be enough now, or may need defect/approval context.

### 3. Quantity Discrepancy Visibility

Status: `CONFIRMED with threshold follow-up`

Confirmed factory policy from 2026-05-30:

- Office and manager should have the same broad process visibility.
- Office and manager should see declared-versus-counted quantity discrepancies.
- Production/station operators should not see discrepancy context; they should see only the current operational quantity.
- Large discrepancies should stop the work order and require office/manager confirmation before continuing.

Current repository behavior/evidence:

- Office enters declared client quantity.
- Surface preparation enters counted received quantity.
- Current implementation may not yet enforce an acknowledgement/hold workflow for large discrepancies.
- Downstream validation uses the surface-preparation counted quantity as operational truth.

Implementation decision needed:

- Define what counts as a large discrepancy: any difference, absolute threshold, percentage threshold, or manager-configured threshold.
- Define the acknowledgement action and audit event.

Why this matters:

- This affects frontend read models and station UI copy.
- It may introduce a new hold/acknowledgement workflow if discrepancy approval is required.

### 4. Station Permissions

Status: `CONFIRMED`

Confirmed factory policy from 2026-05-30:

- Station identity should be used for audit.
- Stations should not be able to perform another station's actions.
- The UI generally should not present actions that belong to another station.
- If an invalid station action reaches the backend, it should be blocked rather than only warned/logged.
- There are no expected real cases where a station needs to perform another station's action due to staffing or device placement.

Current repository behavior/evidence:

- Shared station identity is sent with mutating frontend requests via `X-Station-Id`.
- Backend audit records the station identity for workflow-visible mutations.
- Full permission enforcement is not enabled yet.

Implementation decision needed:

- Add backend station-action authorization and frontend action visibility rules in a focused permission hardening change.

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

Status: `CONFIRMED`

Confirmed factory policy from 2026-05-30:

- Use one shared global queue for all planned work.
- Do not split queues by manual, automatic, decoral, corrections, or stations.
- Corrections should not automatically receive higher priority than normal work orders.
- Manager queue UI should warn when a high-priority work order is blocked by a resource or station state.

Current repository behavior/evidence:

- Planned work orders share one global queue position namespace.
- Corrections start unplanned and join the global queue when manager-planned.
- Station panels filter the global queue to work actionable at that station.

Implementation decision needed:

- Add manager-facing blocked-work warnings without changing the single global queue rule.

### 6. Additional Work Types

Status: `NEW CONFIRMED CONCEPTS, DETAILS OPEN`

Confirmed factory policy from 2026-05-30:

- `Przemalowanka` behaves like a correction: it skips `SURFACE_PREPARATION`.
- `Ocynk` follows the same stage path as other work orders, but it must be visibly marked because station work differs.
- Both new work types can follow RAL or Decoral paths.

Implementation decision needed:

- Define whether `Przemalowanka` is created as a child of an existing work order, a standalone work order type, or both.
- Define whether `Ocynk` is a coating/process flag, intake field, route modifier, or separate work-order category.
- Define which station screens need different labels/instructions for `Ocynk`.

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
7. Walk through `Przemalowanka` and `Ocynk` examples before implementing their data model.

## After Decisions Are Confirmed

For each confirmed decision:

1. Update `docs/WORKFLOW.md` and `docs/FACTORY_USAGE_NOTES.md`.
2. Add or update backend service/API tests for the confirmed invariant.
3. Add frontend tests if station visibility, action availability, or completed/history display changes.
4. Implement the smallest code change that enforces the confirmed rule.
5. Run focused tests first, then the broader backend/frontend checks based on risk.
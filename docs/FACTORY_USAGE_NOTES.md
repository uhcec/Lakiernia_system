# Factory Usage Notes

Captured from user discussion on 2026-05-29 and factory-stakeholder answers on 2026-05-30. These notes describe expected real-life use in the factory. They are business evidence to validate against `docs/WORKFLOW.md`, not a replacement for final factory-policy review.

Use `docs/WORKFLOW_VALIDATION_CHECKLIST.md` as the active checklist before changing workflow semantics based on these notes.

## Terminology

- Elements are physical objects handled in the factory.
- Work orders are system records that track a client's ordered work.
- Be careful not to confuse element quantities with work-order records.

## Physical Station Panels

### Office Computer / Zlecenia

- Used by an office worker who communicates with clients.
- Creates new work orders using declared client quantities.
- Needs a fast/easy overview and a more detailed work-order view.
- Should see whether surface-preparation counted quantity differs from the declared client quantity.
- Office and manager should generally have the same broad access to process information.

### Manager Computer / Kierownik

- Used by a manager.
- Assigns new work orders and correction work orders to manual or automatic production.
- Inserts work orders into the queue.
- Manages a global queue containing work from different completion stages and production areas.
- Confirmed policy: there is one global queue for all planned work. Do not split it by manual, automatic, Decoral, corrections, or station.
- Corrections do not automatically receive higher priority than normal work orders.
- Manager should see whether queued work is blocked by a resource or station state.
- Manager should see declared-versus-counted quantity discrepancies.

### Przygotowanie Powierzchni Tablet

- Used by washing/surface-preparation operators; there may be multiple operators in the area.
- Operators count elements received from the client and compare them to the office-entered declared amount.
- The counted amount becomes the real received amount used by all following stations.
- Operators start washing, then finish washing to pass the work order onward.
- Confirmed policy: surface-preparation operators should enter the counted quantity only. Declared client quantity and declared-versus-counted difference should be visible to office and manager, not station operators.
- Large quantity discrepancies should stop the work order until office/manager acknowledgement; the threshold and acknowledgement flow still need definition.

### Hanging Area Tablet / Zawieszanie

- Used by hanging area operators; there may be multiple operators in the area.
- Automatic production work orders go here first after surface preparation.
- Manual work orders do not go through hanging.
- Operators hang elements on the overhead crane.
- Confirmed policy: operators start hanging, then finish hanging. After hanging finish, hanging capacity is released and the next automatic work order may start hanging even if the previous one is still in automatic production or waiting for packing.
- Only one work order can be in hanging at a time.
- No physical station may process multiple work orders at the same time.
- Implementation note: this differs from the earlier conservative implementation assumption, where one automatic job could block the path until packing completion.

### Automatic Production Tablet

- Automatic production work orders appear here.
- Current working policy: the automatic production tablet is display-only and does not require operator clicks.
- Only one work order can be in automatic production at a time.
- Packing later handles completion of the automatic path.

### Manual Production Tablet

- Used by manual production operators.
- Manual production work orders appear here.
- Operators start varnishing, then finish varnishing to pass the work order onward.

### Packing Tablet

- Used by packing operators; there may be multiple operators in the area.
- Both automatic and manual production elements arrive here, including where the overhead crane runway ends.
- Operators count elements again and compare against the real received amount from surface preparation.
- Operators perform quality check and split quantity into OK amount and correction amount.
- When corrections are created, packing should record a correction reason/category for statistics and audit. The reason does not affect the workflow path.
- RAL OK elements are packed here; RAL/manual work orders end their journey here when no further correction/decoral work remains.
- Decoral elements are not packed here; they continue to Decoral production.

### Decoral Production Tablet

- Used by Decoral operators; there may be multiple operators in the area.
- Decoral work orders arrive here after packing split/quality check.
- Operators start Decoral work, perform the additional Decoral layer/process, pack the elements, then finish the work order.
- Decoral type work orders end their journey here when no further correction work remains.

## Known Gaps To Clarify

- Confirmed correction policy: when packing marks `corrections > 0`, the system automatically creates a correction work order. The manager later assigns that correction to manual or automatic production and inserts it into the global queue.
- Correction work orders do not go through surface preparation. After manager planning, manual corrections start at production and automatic corrections start at hanging.
- Defect/correction type does not require office, manager, quality-control, or customer approval before planning.
- Correction reason/category is needed for statistics/audit, not for workflow routing.
- Correction-chain completion races should reconcile or behave idempotently when the final persisted state is already valid; otherwise the stale action should fail with a controlled conflict.
- Remaining correction implementation detail: define the allowed correction reason/category list.
- Confirmed quantity visibility: counted quantity entry belongs on the surface-preparation tablet; declared quantity and discrepancy visibility belong to office and manager; production/station operators see only operational quantity.
- Remaining discrepancy detail: define what counts as a large discrepancy and the office/manager acknowledgement action.
- Confirmed station permissions: station identity should remain audited, but invalid station actions should be impossible in the UI and rejected by the backend if attempted.
- Confirmed automatic overlap: hanging can start the next automatic order after the previous hanging stage is finished, while preserving one active work order per physical station/resource.

## Additional Work Types

- `Przemalowanka`: behaves like a correction and skips surface preparation. It may follow RAL or Decoral downstream paths.
- `Ocynk`: follows the same stage path as normal work but must be visibly marked because station work differs. It may follow RAL or Decoral downstream paths.
- Open implementation details: decide whether these are separate work-order categories, intake flags, child-order types, or route modifiers before adding code.

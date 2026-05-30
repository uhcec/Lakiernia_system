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
- Proposed tab/order grouping from 2026-05-30:
	- `Zlecenia`: unplanned work orders and incomplete deliveries.
	- `Na produkcji`: all work orders currently on the factory floor.
	- `Gotowe`: completed work orders, with the ability to mark whether the order has been issued/released. Current implementation allows office/manager to mark or clear release only for READY orders.
- Needs an additional external client/order number field separate from the internal system work-order number. Current implementation captures it as optional text; uniqueness/search rules still need factory policy.
- Should require paint stock/state information when entering a work order, once the paint inventory model exists.
- Should see whether surface-preparation counted quantity differs from the declared client quantity.
- Office and manager should generally have the same broad access to process information.

### Manager Computer / Kierownik

- Used by a manager.
- Assigns new work orders and correction work orders to manual or automatic production.
- Inserts work orders into the queue.
- Manages a global queue containing work from different completion stages and production areas.
- Confirmed policy: there is one global queue for all planned work. Do not split it by manual, automatic, Decoral, corrections, or station.
- Corrections do not automatically receive higher priority than normal work orders.
- Manager should see whether queued work is blocked by a resource or station state. Current implementation shows warnings for the modeled exclusive resources `HANGING` and `AUTOMATIC_LINE`.
- Manager should see declared-versus-counted quantity discrepancies.

### Przygotowanie Powierzchni Tablet

- Used by washing/surface-preparation operators; there may be multiple operators in the area.
- Operators count elements received from the client and compare them to the office-entered declared amount.
- The counted amount becomes the real received amount used by all following stations.
- Operators start washing, then finish washing to pass the work order onward.
- Confirmed policy: surface-preparation operators should enter the counted quantity only. Declared client quantity and declared-versus-counted difference should be visible to office and manager, not station operators.
- Quantity discrepancies should be recorded and visible to office/manager, but should not block the work order for now.
- The surface-preparation operator confirms the discrepancy where counting happens.
- Surface preparation may be started before the counted quantity is entered, but it cannot be finished without the counted quantity.

### Hanging Area Tablet / Zawieszanie

- Used by hanging area operators; there may be multiple operators in the area.
- Automatic production work orders go here first after surface preparation.
- Manual work orders do not go through hanging.
- Operators hang elements on the overhead crane.
- Confirmed policy: operators start hanging, then finish hanging. After hanging finish, hanging capacity is released and the next automatic work order may start hanging even if the previous one is still in automatic production or waiting for packing.
- Only one work order can be in hanging at a time.
- No physical station may process multiple work orders at the same time.
- Implementation note: this differs from the earlier conservative implementation assumption, where one automatic job could block the path until packing completion.
- Station list should primarily show: work-order number, square meters, paint, company/customer, and queue position. Drawings/attachments should remain accessible from details.

### Automatic Production Tablet

- Automatic production work orders appear here.
- Confirmed update from 2026-05-30: the automatic production tablet is no longer display-only.
- Automatic production should be able to enter paint consumption so stock is deducted from inventory once the paint inventory model exists.
- Automatic production still does not need manual start/finish clicks for the automatic `PRODUCTION` stage unless that is separately decided.
- Only one work order can be in automatic production at a time.
- Packing later handles completion of the automatic path.
- Station list should primarily show: work-order number, square meters, paint, company/customer, and queue position. Drawings/attachments should remain accessible from details.

### Manual Production Tablet

- Used by manual production operators.
- Manual production work orders appear here.
- Operators start varnishing, then finish varnishing to pass the work order onward.
- Station list should primarily show: work-order number, square meters, paint, company/customer, and queue position. Drawings/attachments should remain accessible from details.

### Packing Tablet

- Used by packing operators; there may be multiple operators in the area.
- Both automatic and manual production elements arrive here, including where the overhead crane runway ends.
- Operators count elements again and compare against the real received amount from surface preparation.
- Operators perform quality check and split quantity into OK amount and correction amount.
- When corrections are created, packing should record a correction reason/category for statistics and audit. The reason does not affect the workflow path.
- Initial coating-defect reason/category list: `niedomalowanie`, `za grubo`, `wtrącenia`, `inne`. This list is not final.
- RAL OK elements are packed here; RAL/manual work orders end their journey here when no further correction/decoral work remains.
- Decoral elements are not packed here; they continue to Decoral production.
- Station list should primarily show: work-order number, profile pieces to verify, accessory pieces to verify, paint, company/customer, and queue position.

### Decoral Production Tablet

- Used by Decoral operators; there may be multiple operators in the area.
- Decoral work orders arrive here after packing split/quality check.
- Operators start Decoral work, perform the additional Decoral layer/process, pack the elements, then finish the work order.
- Decoral type work orders end their journey here when no further correction work remains.
- Station list should primarily show: work-order number, profile pieces to verify, accessory pieces to verify, paint, company/customer, and queue position.

## Station List Display Notes

- Surface preparation list should primarily show: work-order number, profile pieces to verify, accessory pieces to verify, company/customer, and queue position.
- Production-oriented station lists should prioritize the data needed to decide and execute work at that station, with less-used data moved into work-order details.
- Drawings and attachments must remain reachable from details on production and hanging/automatic screens.

## Known Gaps To Clarify

- Confirmed correction policy: when packing marks `corrections > 0`, the system automatically creates a correction work order. The manager later assigns that correction to manual or automatic production and inserts it into the global queue.
- Correction work orders do not go through surface preparation. After manager planning, manual corrections start at production and automatic corrections start at hanging.
- Defect/correction type does not require office, manager, quality-control, or customer approval before planning.
- Correction reason/category is needed for statistics/audit, not for workflow routing.
- Correction-chain completion races should reconcile or behave idempotently when the final persisted state is already valid; otherwise the stale action should fail with a controlled conflict.
- Implemented correction detail: packing-created correction work orders store a flexible reason/category and optional note because the category list is not final. Remaining reporting/export surfaces can be designed later.
- Confirmed quantity visibility: counted quantity entry belongs on the surface-preparation tablet; declared quantity and discrepancy visibility belong to office and manager; production/station operators see only operational quantity.
- Confirmed discrepancy handling: discrepancy is recorded and confirmed by surface preparation, but does not block the work order for now. Surface preparation start does not require counted quantity; finish does require counted quantity.
- Confirmed station permissions: station identity should remain audited, but invalid station actions should be impossible in the UI and rejected by the backend if attempted.
- Confirmed automatic overlap: hanging can start the next automatic order after the previous hanging stage is finished, while preserving one active work order per physical station/resource.
- Quality-control production document generation: the factory has a ready template to be filled by the program. The template and field mapping still need to be provided/checked before implementation.
- Paint inventory: intake should require paint stock/state data and production consumption should deduct stock, but this needs a paint inventory model. Automatic production is confirmed as allowed to enter paint consumption and is no longer display-only.
- Completed-order issue/release marker: completed work orders are markable as issued/released, separate from production READY state.

## Additional Work Types

- `Przemalowanka`: always a separate customer work order. It behaves like a correction operationally and skips surface preparation. It may follow RAL or Decoral downstream paths.
- `Ocynk`: a separate production-relevant work-order type/marker that can combine with RAL or Decoral (`Ocynk RAL`, `Ocynk Decoral`). It follows the same stage path as normal work but must be strongly marked as `OCYNK` on station screens because station work differs.
- Open implementation detail: design the work-order kind/type model so `Przemalowanka` and `Ocynk` can coexist with existing RAL/Decoral route semantics.

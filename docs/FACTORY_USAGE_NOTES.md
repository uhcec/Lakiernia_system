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
	- `Gotowe`: completed work orders, with the ability for office to mark whether the READY order has been issued/released.
- Needs an additional external client/order number field separate from the internal system work-order number. Confirmed on 2026-06-01: this field is optional, not unique, may be empty, and duplicate values should be allowed.
- Current first paint slice requires paint identity on the work order at intake, reads live stock from the app-owned inventory, and warns at intake when predicted paint demand exceeds current stock (update 2026-06-17 — the intake shortage warning is implemented). Shared/global-inventory reservation and demand-based stock accounting remain future work.
- Should see whether surface-preparation counted quantity differs from the declared client quantity.
- Office and manager should generally have the same broad access to process information.
- Office generates the Excel-based production quality-control document before production once the factory template is provided.
- Office marks completed orders as released to the client. Future target: generate a WZ / issue document for completed orders.

### Manager Computer / Kierownik

- Used by a manager.
- Assigns new work orders and correction work orders to manual or automatic production.
- The manual/automatic control in planning is an assignment control, not a separate queue selector.
- Inserts work orders into the queue.
- Manages the planning queue containing work from different completion stages and production areas.
- ~~Confirmed policy: there is one global queue for all planned work. Do not split it by manual, automatic, Decoral, corrections, or station.~~ **SUPERSEDED 2026-06-23:** the queue is now **per production line** — two independently numbered plans (MANUAL / AUTOMATIC), matching the two parallel physical painting resources. The manual/automatic control selects which line's plan to edit. Current truth: `docs/WORKFLOW.md` "Per-Line Queue Rule"; physical grounding: `docs/FACTORY_DOMAIN_MODEL.md` §1.
- Planning no longer asks the manager to type a position: a new order **appends to the end of its line's plan** (server-computed), and reordering within a line is drag-and-drop.
- Corrections do not automatically receive higher priority than normal work orders.
- When planning a correction, the manager should be able to open the original work order and see the original planned pickup date. Correction orders currently mirror that original planned pickup date.
- Parent work-order details should make linked correction orders and their current status/location easy to see.
- New planning should propose the next queue position after currently active planned work. Completed/READY rows stay visible but should move to trailing positions instead of permanently blocking active planning slots.
- Manager should see whether queued work is blocked by a resource or station state. Current implementation shows warnings for the modeled exclusive resources `HANGING` and `AUTOMATIC_LINE`.
- Manager should see declared-versus-counted quantity discrepancies.
- Correction statistics should be manager-only.

### Przygotowanie Powierzchni Tablet

- Used by washing/surface-preparation operators; there may be multiple operators in the area.
- Operators count elements received from the client and compare them to the office-entered declared amount.
- The counted amount becomes the real received amount used by all following stations.
- Operators start washing, then finish washing to pass the work order onward.
- Confirmed policy: surface-preparation operators should enter the counted quantity only. Declared client quantity and declared-versus-counted difference should be visible to office and manager, not station operators.
- Quantity discrepancies should be recorded and visible to office/manager, but should not block the work order for now.
- The surface-preparation operator records the counted quantity only; there is no separate discrepancy-confirmation action for now.
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
- Confirmed update from 2026-05-30: this tablet should also show the automatic hanging queue from the moment work is ready for hanging, so the automatic operator can see the day's workflow before the line is physically occupied.
- Automatic production can now enter paint consumption against the work-order paint allocation. Shared stock deduction remains future inventory work.
- Automatic production is the confirmed production station for manual paint-consumption entry. Automatic correction work is still expected to need paint consumption later, but the current first slice does not yet allocate paint to correction orders.
- Packing should not be completable for standard automatic work until paint consumption has been entered. Automatic correction work remains a later extension.
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
- Confirmed update from 2026-05-30: packing should see active automatic orders while hanging is still in progress, but only as waiting visibility. Packing must not be completable until hanging is finished.
- Operators count elements again and compare against the real received amount from surface preparation.
- Operators perform quality check and split quantity into OK amount and correction amount.
- When corrections are created, packing should record a correction reason/category for statistics and audit. The reason does not affect the workflow path.
- When corrections are created, packing should also record how many corrected pieces are profiles and how many are accessories; the two values must sum to the correction quantity.
- Current implementation presents packing as per-order cards with a dedicated action panel and split balance feedback, while active automatic hanging rows remain read-only.
- Initial coating-defect reason/category list: `niedomalowanie`, `za grubo`, `wtrącenia`, `inne`. This list is acceptable for now, should stay simple in the UI, and may change later.
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
- Details opened from production stations preserve the source station identity and remain read-only for office/manager mutations. Attachment downloads stay available; upload/delete remains an office action.
- Current implementation presents general station lists as per-order cards with station-specific facts and a separated action area, rather than wide action tables.

## Access And Login Direction

- The current shared station identity model is useful as a rollout/audit layer, but it is not enough for the target product.
- Production should log into station contexts; details still need design on whether this identifies a station account, an operator, or both.
- Office should use individual logins.
- Production should not edit work-order intake/business data; production access remains station actions plus read-only details and attachment download.
- Manager-only statistics must not be available to office/production users once real auth is implemented.

## Known Gaps To Clarify

- Confirmed correction policy: when packing marks `corrections > 0`, the system automatically creates a correction work order. The manager later assigns that correction to manual or automatic production and inserts it into the global queue.
- Correction work orders do not go through surface preparation. After manager planning, manual corrections start at production and automatic corrections start at hanging.
- Defect/correction type does not require office, manager, quality-control, or customer approval before planning.
- Correction reason/category is needed for statistics/audit, not for workflow routing.
- Correction-chain completion races should reconcile or behave idempotently when the final persisted state is already valid; otherwise the stale action should fail with a controlled conflict.
- Implemented correction detail: packing-created correction work orders store a flexible reason/category and optional note because categories may change later. Manager correction statistics aggregate stored categories, keep uncategorized legacy rows visible, are visible in the manager panel, and can be exported as CSV. The current category list is acceptable for now and custom operator-created categories should not be introduced in the UI.
- Confirmed quantity visibility: counted quantity entry belongs on the surface-preparation tablet; declared quantity and discrepancy visibility belong to office and manager; production/station operators see only operational quantity.
- Confirmed discrepancy handling: discrepancy is recorded through the surface-preparation counted quantity, but does not block the work order for now. Surface preparation start does not require counted quantity; finish does require counted quantity. No separate discrepancy-confirmation action or dedicated audit event is required unless future factory review asks for one.
- Current implementation exposes surface-preparation counted quantity and declared-versus-counted difference to office and manager read models/UI, while station lists keep discrepancy context out of the operational rows.
- Implemented profile/accessory quantity rule: known office-intake values partition the work order, so profile quantity plus accessory quantity must equal `total_quantity`; there are no other expected item categories. Packing corrections now collect the profile/accessory correction split explicitly and store that split on the correction child.
- Confirmed station permissions: station identity should remain audited, invalid station actions should be impossible in the UI, and current backend enforcement rejects wrong-station mutating requests for office, manager, process, packing, and release-marker actions.
- Confirmed automatic overlap: hanging can start the next automatic order after the previous hanging stage is finished, while preserving one active work order per physical station/resource.
- Quality-control production document generation: the factory has a ready Excel template to be filled by the program. Office generates it before production. Confirmed system-filled fields so far are internal work-order number, paint, and company/customer; the real template still needs to be provided/checked before implementation.
- Paint inventory: the target workflow is app-owned stock per paint card. Office maintains deliveries and manual adjustments in the app, sees current stock when creating the work order, and the system stores that value as a historical snapshot on the order without making a reservation. Automatic production records actual paint consumption for the work order, and that save reduces stock immediately. Automatic corrections follow the same consumption requirement before packing completes.
- Completed-order issue/release marker: completed work orders are markable as issued/released by office only, separate from production READY state. Future WZ document generation is desired but needs template/design.
- Manager queue history: completed/READY work orders should trail out of the active planning range when manager planning or queue updates need active slots. If immutable original priority evidence is needed later, add a dedicated history/audit field instead of overloading live `queue_position`.
- Packing exclusivity: confirmed. Packing should be treated as one physical exclusive resource; automatic work visible there while hanging/automatic flow is still active does not remove that exclusivity requirement for actually started packing work.

## Additional Work Types

- `Przemalowanka`: always a separate independent customer work order, not parent-linked to an original order. It behaves like a correction operationally and skips surface preparation. It may follow RAL or Decoral downstream paths. Current implementation models it as `work_order_kind = PRZEMALOWANKA`, not as `is_correction`.
- `Ocynk`: a separate production-relevant work-order type/marker that can combine with RAL or Decoral (`Ocynk RAL`, `Ocynk Decoral`). It follows the same stage path as normal work but must be strongly marked as `OCYNK` on station screens because station work differs. Current implementation models it as an independent `is_ocynk` marker.
- Open implementation detail: reporting/search/document needs for `Przemalowanka` and `Ocynk` are still open beyond the current model and station-visible markers.

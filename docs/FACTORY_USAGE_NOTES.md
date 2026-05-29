# Factory Usage Notes

Captured from user discussion on 2026-05-29. These notes describe expected real-life use in the factory. They are business evidence to validate against `docs/WORKFLOW.md`, not a replacement for final factory-policy review.

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

### Manager Computer / Kierownik

- Used by a manager.
- Assigns new work orders and correction work orders to manual or automatic production.
- Inserts work orders into the queue.
- Manages a global queue containing work from different completion stages and production areas.
- Current assessment: a global queue can make sense as a manager priority model, but station panels must make it clear which globally queued items are actionable at that physical station now.

### Przygotowanie Powierzchni Tablet

- Used by washing/surface-preparation operators; there may be multiple operators in the area.
- Operators count elements received from the client and compare them to the office-entered declared amount.
- The counted amount becomes the real received amount used by all following stations.
- Operators start washing, then finish washing to pass the work order onward.
- Current working policy: surface-preparation operators should enter the counted quantity only. Declared client quantity and declared-versus-counted difference should be office-only for now, with possible tweaks after factory review.

### Hanging Area Tablet / Zawieszanie

- Used by hanging area operators; there may be multiple operators in the area.
- Automatic production work orders go here first after surface preparation.
- Manual work orders do not go through hanging.
- Operators hang elements on the overhead crane.
- Current working policy: operators start hanging, then finish hanging. After hanging finish, the work order appears on the automatic production display.
- Only one work order can be in hanging at a time.
- Current conservative assumption: do not allow starting the next hanging order while the previous order is still in automatic production. This needs factory-knowledge validation.
- Business note to validate: this differs from current implementation, where automatic hanging start advances/occupies the automatic line and finishing the automatic path is performed from packing.

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
- RAL OK elements are packed here; RAL/manual work orders end their journey here when no further correction/decoral work remains.
- Decoral elements are not packed here; they continue to Decoral production.

### Decoral Production Tablet

- Used by Decoral operators; there may be multiple operators in the area.
- Decoral work orders arrive here after packing split/quality check.
- Operators start Decoral work, perform the additional Decoral layer/process, pack the elements, then finish the work order.
- Decoral type work orders end their journey here when no further correction work remains.

## Known Gaps To Clarify

- Current working correction policy: when packing marks `corrections > 0`, the system automatically creates a correction work order. The manager later assigns that correction to manual or automatic production and inserts it into the global queue.
- Correction work orders do not go through surface preparation. After manager planning, manual corrections start at production and automatic corrections start at hanging.
- Remaining correction clarification: validate whether any defect types require a different review/approval path and how simultaneous parent/correction completion should respond to stale duplicate actions.
- Surface-preparation quantity difference visibility is mostly clarified for now: counted quantity entry belongs on the surface-preparation tablet, while declared quantity and discrepancy visibility should be office-only unless later factory review changes this.
- Need factory-knowledge validation on automatic-line overlap: can hanging start the next order while the previous order is still in automatic production, or does the whole hanging/automatic-line path stay blocked until packing?

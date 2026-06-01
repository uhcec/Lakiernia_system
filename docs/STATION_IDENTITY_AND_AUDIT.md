# Station Identity And Audit Design

This document defines the current station identity and audit layer for physical factory station panels. It is based on `docs/FACTORY_USAGE_NOTES.md` and the current working contract. The current implementation is station-context based, but factory clarification from 2026-06-01 says the target product also needs login and role design.

## Problem

The application is used from physical devices in specific factory areas. A screen action is not just a generic API request; it comes from an office computer, manager computer, surface-preparation tablet, hanging tablet, packing tablet, Decoral tablet, or another station device.

Near-term requirements:

- identify which station/device context performed important actions
- keep the first implementation low-friction for factory devices
- preserve operator truth and workflow integrity
- avoid pretending that station identity solves multi-worker backend concurrency

Target access requirements from 2026-06-01:

- production logs into station contexts
- office uses individual logins
- manager-only statistics are protected from office/production access
- production cannot edit work-order intake/business data

## Current Decisions

- Station identity is shared by device/panel for now.
- Shared station identity is current implementation, not the final access model.
- A single backend process is acceptable for near-term deployment.
- Station identity and audit remain necessary even after personal accounts, because actions still happen from physical station contexts.
- Factory decision from 2026-05-30: station actions should be blocked when attempted from the wrong station; normal production does not need cross-station action overrides.
- Factory decision from 2026-06-01: auth/login work is required for production station login, individual office login, and manager-only statistics.
- Audit records are implementation evidence and operational traceability, not business validation by themselves.

## Station Identities

Initial station identity values:

- `OFFICE`
- `MANAGER`
- `SURFACE_PREPARATION`
- `HANGING`
- `AUTOMATIC_PRODUCTION`
- `MANUAL_PRODUCTION`
- `PACKING`
- `DECORAL_PRODUCTION`
- `SYSTEM`
- `UNKNOWN`

`SYSTEM` is for backend-created/maintenance events when no physical station is the actor. `UNKNOWN` is a compatibility fallback while station headers are rolled out. The long-term target is that normal frontend station requests are not `UNKNOWN`.

## Station Context Transport

Near-term API transport:

- frontend sends `X-Station-Id` with station identity
- backend parses the header into a station context
- invalid station values are rejected with a controlled client error once enforcement is enabled for audited mutations
- during rollout, missing station values may be accepted as `UNKNOWN` to avoid breaking existing clients/tests

Frontend mapping should be route/panel based, not user-entered on every action:

- `/zlecenia` -> `OFFICE`
- `/kierownik` -> `MANAGER`
- `/przygotowanie-powierzchni` -> `SURFACE_PREPARATION`
- `/zawieszanie` -> `HANGING`
- `/produkcja-automatyczna` -> `AUTOMATIC_PRODUCTION`
- `/produkcja-reczna` -> `MANUAL_PRODUCTION`
- `/pakowanie` -> `PACKING`
- `/dekoracja` or Decoral route -> `DECORAL_PRODUCTION`

Exact route names should be checked against the current frontend before implementation.

## Audit Event Shape

Audit events should be append-only records.

Proposed fields:

- `id`
- `event_type`
- `station_id`
- `work_order_id` nullable
- `target_type` nullable
- `target_id` nullable
- `summary`
- `details_json` nullable text/JSON
- `created_at`

Future personal-login fields can be added later:

- `actor_user_id`
- `actor_display_name`

Do not require those fields in the existing station identity slice, but add them as part of the future auth/login project.

## Events To Audit First

Start with workflow-visible mutations:

- work order created
- work order intake updated
- incomplete-on-arrival marked complete
- manager assigns production type and queue position
- manager reorders queue
- stage started
- stage finished
- packing completed with counted/OK/correction quantities
- correction work order auto-created
- attachment uploaded/deleted

Audit should be recorded only after a successful business mutation, ideally in the same transaction as the mutation.

## Current Implementation

Implemented backend audit coverage:

- `POST /work-orders` records `work_order.created`
- work-order intake updates record `work_order.updated`
- incomplete-arrival completion records `work_order.arrival_completed`
- manager plan assignment records `manager.plan_assigned`
- manager queue-position update records `manager.queue_position_updated`
- manager bulk queue reorder records `manager.queue_reordered`
- process stage start/finish/reopen records `process.stage.started`, `process.stage.finished`, or `process.stage.reopened`
- packing completion records `process.packing.completed`
- packing-created correction work orders record `work_order.correction_created`
- attachment upload/delete records `work_order.attachment_uploaded` and `work_order.attachment_deleted`
- every HTTP response includes `X-Request-Id`; a valid incoming `X-Request-Id` is echoed, otherwise the backend generates one
- audit events created during an HTTP request persist that request ID for traceability
- request logs include the request ID, method, path, status, and duration for log/event correlation
- `GET /audit/work-orders/{work_order_id}/events` returns chronological audit history for a work order
- `GET /audit/events` searches audit events by work order, event type, station, request ID, target, and created-at range
- `GET /audit/events/export.csv` exports the same filtered audit events as CSV
- mutating work-order, manager, process-stage, and packing endpoints reject explicit wrong-station actions with `403`; `UNKNOWN` and `SYSTEM` remain compatibility identities during rollout

Implemented frontend propagation:

- mutating work-orders, manager, and process API calls send `X-Station-Id`
- station identity is derived from the current panel route
- work-order detail view displays `GET /audit/work-orders/{work_order_id}/events` as a non-blocking history section
- `/audyt` provides a read-only audit console with backend search filters and CSV export link

Still open:

- hide or reshape any future frontend actions that might cross station boundaries as new station capabilities are added, especially automatic-production paint consumption
- add user login/session/role checks and audit actor fields
- protect manager-only statistics with auth/roles, not only route naming

## Permission Direction

Confirmed permission direction:

- `OFFICE`: individual login; create/update intake, enter external work-order number, enter/select paint stock state once inventory exists, view discrepancies, manage attachments, mark completed order as issued/released, generate WZ when implemented
- `MANAGER`: assign production type, queue/reorder, view global queue and discrepancies, view paint/inventory warnings, view manager-only statistics
- `SURFACE_PREPARATION`: start surface prep, enter counted quantity, confirm quantity discrepancy, finish surface prep after counted quantity exists
- `HANGING`: start/finish hanging
- `AUTOMATIC_PRODUCTION`: enter paint consumption once paint inventory exists; no manual start/finish for automatic production unless separately decided
- `MANUAL_PRODUCTION`: start/finish manual production
- `PACKING`: enter counted/OK/correction quantities, profile/accessory correction split, correction reason/category, complete packing
- `DECORAL_PRODUCTION`: start/finish Decoral production

Invalid station actions should be rejected by the backend and should not be visible in normal frontend station panels.

## Known Workflow Validation Points

Confirmed decisions from `docs/FACTORY_USAGE_NOTES.md`:

- Hanging can start the next automatic order after the previous hanging stage is finished, while automatic production remains one work order at a time.
- Correction defect types do not need special review/approval before manager planning.
- Office and manager should see quantity discrepancies; station operators should see only operational quantities.
- Quantity discrepancies should be recorded and confirmed at surface preparation, but should not block work orders for now. Surface-preparation finish requires counted quantity; start does not.
- `Przemalowanka` is a standalone customer work order that skips surface preparation; `Ocynk` is a strong station-visible type/marker combinable with RAL or Decoral.
- Office completed views support an issued/released marker for READY orders, separate from production READY state. The current station-identity layer restricts release marking to `OFFICE`; future individual logins still need a separate auth design.
- Paint inventory/consumption needs station permission decisions. Intake paint-stock entry is needed, and automatic production is confirmed as an action-capable station for paint-consumption entry.
- Quality-control production document generation should use the factory-provided template and may need audit/attachment rules depending on whether generated copies are persisted.

Track these decisions in `docs/WORKFLOW_VALIDATION_CHECKLIST.md` before changing workflow semantics.

These decisions unblock station permission design. Automatic-flow resource changes, backend station permission enforcement, manager warnings for currently modeled exclusive resources, and completed-order release status were implemented on 2026-05-30; discrepancy recording, new work types, paint inventory, and quality-document generation still need focused implementation design before code changes.

## Implementation Plan

1. Add backend station enum/context parsing and audit event model.
2. Add Alembic migration for audit events.
3. Add focused tests for station parsing and audit event persistence.
4. Integrate audit recording into one or two low-risk successful mutations first.
5. Add frontend `X-Station-Id` propagation by panel route.
6. Expand audit coverage across workflow-visible mutations.
7. Display work-order-scoped audit history on the work-order detail view.
8. Add station permission enforcement for confirmed station-action boundaries.

## Verification

For each implementation slice:

- focused backend tests for audit persistence and failure behavior
- route/API tests for station header handling
- frontend tests for station header propagation and audit history rendering where applicable
- full backend suite after service-level audit integration
- frontend tests/build after frontend propagation

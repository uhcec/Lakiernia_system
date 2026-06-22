"""Audit + stage-transition log writing for the process workflow engine.

Extracted from ``ProcessService`` (NA39). This collaborator owns the **dual write** to
the two append-only logs that every meaningful process event produces:

- ``audit_events`` (operational/security audit; see ``app/audit/``), and
- ``stage_transition_events`` (the analytics backbone for time-based stats; see
  ``StageTransitionEvent``).

Centralizing both writes here makes the "the two logs cannot diverge" guarantee
structural rather than convention (NA46 §A6): the stage/packing/decoral helpers record
both in one call, so a future change cannot add an audit event without its matching
transition row (or vice versa) by forgetting one line at a scattered call site.
"""

import json

from app.audit.context import StationContext
from app.audit.models import AuditEvent
from app.audit.repository import AuditRepository
from app.process.enums import ProcessStage, StageStatus
from app.process.models import StageTransitionEvent
from app.shared.enums import StationId
from app.work_orders.models import WorkOrder


class ProcessAuditWriter:
    """Writes process audit events and the mirrored stage-transition log rows."""

    def __init__(self, session, audit_repository: AuditRepository) -> None:
        self._session = session
        self._audit_repository = audit_repository

    def record_stage_audit_event(
        self,
        *,
        work_order: WorkOrder,
        stage: ProcessStage,
        target_status: StageStatus,
        station_context: StationContext | None,
        batch_id: int | None,
    ) -> None:
        action_by_status = {
            StageStatus.IN_PROGRESS: ("process.stage.started", "Started"),
            StageStatus.DONE: ("process.stage.finished", "Finished"),
            StageStatus.NOT_STARTED: ("process.stage.reopened", "Reopened"),
        }
        event_type, action_label = action_by_status[target_status]
        self.record_audit_event(
            event_type=event_type,
            station_context=station_context,
            work_order=work_order,
            target_type="process_stage",
            target_id=batch_id,
            summary=f"{action_label} {stage.value} for work order {work_order.order_number}.",
            details={
                "stage": stage.value,
                "target_status": target_status.value,
                "batch_id": batch_id,
            },
        )
        self.record_stage_transition(
            work_order=work_order,
            stage=stage,
            status=target_status,
            station_context=station_context,
            batch_id=batch_id,
        )

    def record_packing_override_audit_event(
        self,
        work_order: WorkOrder,
        station_context: StationContext | None,
        *,
        batch_id: int | None,
    ) -> None:
        # NA22b: a manual operator opened an additional packing slot. Audited for traceability.
        self.record_audit_event(
            event_type="process.packing.slot_override_opened",
            station_context=station_context,
            work_order=work_order,
            target_type="process_stage",
            target_id=batch_id,
            summary=f"Opened an additional packing slot (override) for work order {work_order.order_number}.",
            details={"stage": ProcessStage.PACKING.value, "batch_id": batch_id},
        )

    def record_packing_audit_event(
        self,
        *,
        work_order: WorkOrder,
        station_context: StationContext | None,
        batch_id: int | None,
        counted_quantity: int,
        ok_quantity: int,
        correction_quantity: int,
        correction_category_fields: dict[str, int | bool | None],
    ) -> None:
        details = {
            "stage": ProcessStage.PACKING.value,
            "batch_id": batch_id,
            "counted_quantity": counted_quantity,
            "ok_quantity": ok_quantity,
            "correction_quantity": correction_quantity,
        }
        if correction_quantity > 0:
            details.update(
                {
                    "correction_profiles_quantity": correction_category_fields["profiles_quantity"],
                    "correction_accessories_quantity": correction_category_fields["accessories_quantity"],
                }
            )
        self.record_audit_event(
            event_type="process.packing.completed",
            station_context=station_context,
            work_order=work_order,
            target_type="process_stage",
            target_id=batch_id,
            summary=f"Completed packing for work order {work_order.order_number}.",
            details=details,
        )
        self.record_stage_transition(
            work_order=work_order,
            stage=ProcessStage.PACKING,
            status=StageStatus.DONE,
            station_context=station_context,
            batch_id=batch_id,
            counted_quantity=counted_quantity,
        )

    def record_decoral_audit_event(
        self,
        *,
        work_order: WorkOrder,
        station_context: StationContext | None,
        batch_id: int | None,
        ok_quantity: int,
        correction_quantity: int,
        correction_category_fields: dict[str, int | bool | None],
    ) -> None:
        details: dict[str, object] = {
            "stage": ProcessStage.DECORAL_PRODUCTION.value,
            "batch_id": batch_id,
            "ok_quantity": ok_quantity,
            "correction_quantity": correction_quantity,
        }
        if correction_quantity > 0:
            details.update(
                {
                    "correction_profiles_quantity": correction_category_fields["profiles_quantity"],
                    "correction_accessories_quantity": correction_category_fields["accessories_quantity"],
                }
            )
        self.record_audit_event(
            event_type="process.decoral_production.completed",
            station_context=station_context,
            work_order=work_order,
            target_type="process_stage",
            target_id=batch_id,
            summary=f"Completed decoral production for work order {work_order.order_number}.",
            details=details,
        )
        self.record_stage_transition(
            work_order=work_order,
            stage=ProcessStage.DECORAL_PRODUCTION,
            status=StageStatus.DONE,
            station_context=station_context,
            batch_id=batch_id,
            counted_quantity=ok_quantity,
        )

    def record_automatic_paint_consumption_audit_event(
        self,
        *,
        work_order: WorkOrder,
        station_context: StationContext | None,
        previous_value: float,
        consumed_paint_quantity_kg: float,
    ) -> None:
        self.record_audit_event(
            event_type="process.automatic_paint_consumption.recorded",
            station_context=station_context,
            work_order=work_order,
            target_type="process_stage",
            target_id=work_order.active_batch.id if work_order.active_batch is not None else None,
            summary=f"Recorded automatic paint consumption for work order {work_order.order_number}.",
            details={
                "stage": ProcessStage.PRODUCTION.value,
                "paint_code": work_order.paint_code,
                "paint_stock_snapshot_quantity_kg": work_order.paint_stock_snapshot_quantity_kg,
                "previous_consumed_paint_quantity_kg": previous_value,
                "consumed_paint_quantity_kg": consumed_paint_quantity_kg,
            },
        )

    def record_stage_transition(
        self,
        *,
        work_order: WorkOrder,
        stage: ProcessStage,
        status: StageStatus,
        station_context: StationContext | None,
        batch_id: int | None,
        counted_quantity: int | None = None,
    ) -> None:
        """Append a row to the analytics stage-transition log (see ``StageTransitionEvent``).

        Mirrors the audit choke points so coverage matches the audit log. ``occurred_at`` defaults
        to now and is never updated, giving a durable timestamp for cycle-time/throughput stats.
        """
        self._session.add(
            StageTransitionEvent(
                work_order_id=work_order.id,
                batch_id=batch_id,
                stage=stage,
                status=status,
                counted_quantity=counted_quantity,
                station_id=station_context.station_id if station_context is not None else StationId.SYSTEM,
                user_id=station_context.user_id if station_context is not None else None,
            )
        )

    def record_audit_event(
        self,
        *,
        event_type: str,
        station_context: StationContext | None,
        work_order: WorkOrder,
        target_type: str,
        target_id: int | None,
        summary: str,
        details: dict[str, object],
    ) -> None:
        station_id = station_context.station_id if station_context is not None else StationId.SYSTEM
        self._audit_repository.add(
            AuditEvent(
                event_type=event_type,
                station_id=station_id,
                work_order_id=work_order.id,
                target_type=target_type,
                target_id=target_id,
                summary=summary,
                details_json=json.dumps(details, separators=(",", ":")),
            )
        )

import json
from datetime import UTC, datetime

from threading import RLock

from sqlalchemy.exc import IntegrityError

from app.audit.context import StationContext, ensure_station_allowed
from app.audit.models import AuditEvent
from app.audit.repository import AuditRepository
from app.paints.repository import PaintRepository
from app.paints.service import PaintService
from app.process.enums import ProcessDisplayStatus
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.manager.repository import ManagerRepository
from app.manager.schemas import (
    CorrectionReasonReportItem,
    WorkOrderPlanAssignRequest,
    WorkOrderProductionTypeUpdateRequest,
    WorkOrderQueuePositionUpdateRequest,
    WorkOrderQueueReorderBatchRequest,
    WorkOrderQueueReorderRequest,
)
from app.process.enums import ProcessStage, StageStatus
from app.shared.enums import StationId, WorkOrderStatus
from app.shared.exceptions import InvalidManagerPlanningError, ResourceNotFoundError
from app.work_orders.models import WorkOrder
from app.work_orders.schemas import WorkOrderRead
from app.work_orders.schemas import (
    WorkOrderQuantityBatchRead,
    WorkOrderRelationSummaryRead,
    WorkOrderStageStateRead,
    calculate_paint_shortage_quantity_kg,
    calculate_predicted_paint_quantity_kg,
    build_coating_type_view,
    build_queue_namespace_view,
    build_process_stage_view,
    build_process_status_view,
    build_production_type_view,
    build_quantity_batch_type_view,
    build_stage_status_info_view,
    build_work_order_relation_summary,
    build_work_order_kind_view,
)
from app.work_orders.service import WorkOrderService


_QUEUE_MUTATION_LOCK = RLock()


class ManagerService:
    def __init__(self, repository: ManagerRepository) -> None:
        self.repository = repository
        self.process_service = ProcessService(ProcessRepository(repository.session))
        self.paint_service = PaintService(PaintRepository(repository.session))
        self.audit_repository = AuditRepository(repository.session)

    def _get_current_paint_stock_quantity_kg(self, work_order: WorkOrder) -> float | None:
        if not work_order.ral_code or not work_order.paint_producer or not work_order.paint_code:
            return None
        return self.paint_service.lookup_current_stock(
            ral_code=work_order.ral_code,
            paint_producer=work_order.paint_producer,
            paint_code=work_order.paint_code,
        ).current_quantity_kg

    def list_unplanned_work_orders(self) -> list[WorkOrderRead]:
        return [self._to_read_model(work_order) for work_order in self.repository.list_unplanned_work_orders()]

    def list_planned_work_orders(self) -> list[WorkOrderRead]:
        return [self._to_read_model(work_order) for work_order in self.repository.list_planned_work_orders()]

    def get_correction_reason_report(self) -> list[CorrectionReasonReportItem]:
        return [
            CorrectionReasonReportItem(
                correction_reason_category=category,
                work_order_count=work_order_count,
                total_correction_quantity=total_correction_quantity,
            )
            for category, work_order_count, total_correction_quantity in self.repository.list_correction_reason_report()
        ]

    def assign_plan(
        self,
        work_order_id: int,
        payload: WorkOrderPlanAssignRequest,
        station_context: StationContext | None = None,
    ) -> WorkOrderRead:
        self._ensure_manager_station_action(station_context)
        with _QUEUE_MUTATION_LOCK:
            work_order = self._get_existing_work_order(work_order_id)
            if self._is_planned(work_order):
                raise InvalidManagerPlanningError(f"Work order {work_order_id} is already planned.")
            if self._has_incomplete_marker(work_order):
                raise InvalidManagerPlanningError("Cannot plan incomplete order. Mark as complete first.")
            self._ensure_queue_position_available_or_releasable(payload.queue_position)

            now = datetime.now(UTC)
            completed_work_orders_to_trail = self._get_completed_work_orders_requiring_trailing(
                reserved_queue_positions=[payload.queue_position],
            )
            self._temporarily_move_queue_rows_out_of_the_way(
                completed_work_orders_to_trail,
                reserved_queue_positions=[payload.queue_position],
                now=now,
            )

            work_order.production_type = payload.production_type
            work_order.queue_position = payload.queue_position
            work_order.updated_at = now
            self.process_service.prepare_correction_work_order_for_planning(work_order)
            self.repository.session.flush()
            self._trail_completed_work_orders(completed_work_orders_to_trail, now=now)
            self._record_audit_event(
                event_type="manager.plan_assigned",
                station_context=station_context,
                work_order=work_order,
                target_type="work_order",
                target_id=work_order.id,
                summary=f"Assigned plan for work order {work_order.order_number}.",
                details={
                    "production_type": payload.production_type.value,
                    "queue_position": payload.queue_position,
                },
            )

            try:
                self.repository.commit()
            except IntegrityError as exc:
                self.repository.rollback()
                raise InvalidManagerPlanningError(
                    f"Queue position {payload.queue_position} is already taken."
                ) from exc
            except Exception:
                self.repository.rollback()
                raise

            return self._to_read_model(work_order)

    def update_queue_position(
        self,
        work_order_id: int,
        payload: WorkOrderQueuePositionUpdateRequest,
        station_context: StationContext | None = None,
    ) -> WorkOrderRead:
        self._ensure_manager_station_action(station_context)
        with _QUEUE_MUTATION_LOCK:
            work_order = self._get_existing_work_order(work_order_id)
            if not self._is_planned(work_order):
                raise InvalidManagerPlanningError(f"Work order {work_order_id} must be planned before updating queue position.")
            if self.process_service.get_display_status(work_order) == ProcessDisplayStatus.READY:
                raise InvalidManagerPlanningError("Completed work orders cannot be moved in the active queue.")
            self._ensure_queue_position_available_or_releasable(
                payload.queue_position,
                exclude_work_order_id=work_order_id,
            )

            now = datetime.now(UTC)
            completed_work_orders_to_trail = self._get_completed_work_orders_requiring_trailing(
                reserved_queue_positions=[payload.queue_position],
                exclude_work_order_id=work_order_id,
            )
            self._temporarily_move_queue_rows_out_of_the_way(
                completed_work_orders_to_trail,
                reserved_queue_positions=[payload.queue_position],
                now=now,
            )

            previous_queue_position = work_order.queue_position
            work_order.queue_position = payload.queue_position
            work_order.updated_at = now
            self.repository.session.flush()
            self._trail_completed_work_orders(completed_work_orders_to_trail, now=now)
            self._record_audit_event(
                event_type="manager.queue_position_updated",
                station_context=station_context,
                work_order=work_order,
                target_type="work_order",
                target_id=work_order.id,
                summary=f"Updated queue position for work order {work_order.order_number}.",
                details={
                    "previous_queue_position": previous_queue_position,
                    "queue_position": payload.queue_position,
                },
            )

            try:
                self.repository.commit()
            except IntegrityError as exc:
                self.repository.rollback()
                raise InvalidManagerPlanningError(
                    f"Queue position {payload.queue_position} is already taken."
                ) from exc
            except Exception:
                self.repository.rollback()
                raise

            return self._to_read_model(work_order)

    def update_production_type(
        self,
        work_order_id: int,
        payload: WorkOrderProductionTypeUpdateRequest,
        station_context: StationContext | None = None,
    ) -> WorkOrderRead:
        self._ensure_manager_station_action(station_context)
        with _QUEUE_MUTATION_LOCK:
            work_order = self._get_existing_work_order(work_order_id)
            if not self._is_planned(work_order):
                raise InvalidManagerPlanningError(f"Work order {work_order_id} must be planned before changing production type.")
            if work_order.production_type == payload.production_type:
                return self._to_read_model(work_order)
            self._ensure_production_not_started(work_order)

            previous_production_type = work_order.production_type
            now = datetime.now(UTC)
            work_order.production_type = payload.production_type
            work_order.updated_at = now
            self.process_service.prepare_correction_work_order_for_planning(work_order)
            self._record_audit_event(
                event_type="manager.production_type_changed",
                station_context=station_context,
                work_order=work_order,
                target_type="work_order",
                target_id=work_order.id,
                summary=f"Changed production type for work order {work_order.order_number}.",
                details={
                    "previous_production_type": previous_production_type.value if previous_production_type else None,
                    "production_type": payload.production_type.value,
                },
            )

            self.repository.commit()
            return self._to_read_model(work_order)

    def reorder_queue(
        self,
        payload: WorkOrderQueueReorderBatchRequest,
        station_context: StationContext | None = None,
    ) -> list[WorkOrderRead]:
        self._ensure_manager_station_action(station_context)
        items = payload.items
        if not items:
            return self.list_planned_work_orders()

        with _QUEUE_MUTATION_LOCK:
            current_revision = self.repository.get_planned_queue_revision()
            if current_revision is not None and payload.queue_revision != current_revision:
                raise InvalidManagerPlanningError("Queue reorder payload is stale. Refresh the manager queue and try again.")

            work_order_ids = [item.work_order_id for item in items]
            queue_positions = [item.queue_position for item in items]

            if len(set(work_order_ids)) != len(work_order_ids):
                raise InvalidManagerPlanningError("Queue reorder payload cannot contain duplicate work order IDs.")
            if len(set(queue_positions)) != len(queue_positions):
                raise InvalidManagerPlanningError("Queue reorder payload cannot contain duplicate queue positions.")

            existing_work_orders = {work_order.id: work_order for work_order in self.repository.list_by_ids(work_order_ids)}
            missing_ids = [work_order_id for work_order_id in work_order_ids if work_order_id not in existing_work_orders]
            if missing_ids:
                missing_id = missing_ids[0]
                raise ResourceNotFoundError(f"Work order {missing_id} not found.")

            planned_work_orders = list(self.repository.list_planned_work_orders())
            omitted_work_orders = [work_order for work_order in planned_work_orders if work_order.id not in existing_work_orders]
            omitted_active_work_orders = [
                work_order
                for work_order in omitted_work_orders
                if self.process_service.get_display_status(work_order) != ProcessDisplayStatus.READY
            ]
            if omitted_active_work_orders:
                raise InvalidManagerPlanningError("Queue reorder payload must include all active planned work orders.")

            omitted_completed_work_orders = [
                work_order
                for work_order in omitted_work_orders
                if self.process_service.get_display_status(work_order) == ProcessDisplayStatus.READY
            ]

            now = datetime.now(UTC)
            temporarily_repositioned_work_orders = [
                existing_work_orders[item.work_order_id]
                for item in items
            ] + omitted_completed_work_orders
            temporary_queue_position = max(
                [work_order.queue_position or 0 for work_order in planned_work_orders] + queue_positions,
                default=0,
            ) + 1

            for work_order in temporarily_repositioned_work_orders:
                work_order.queue_position = temporary_queue_position
                work_order.updated_at = now
                temporary_queue_position += 1

            self.repository.session.flush()

            for item in items:
                work_order = existing_work_orders[item.work_order_id]
                if not self._is_planned(work_order):
                    raise InvalidManagerPlanningError(
                        f"Work order {item.work_order_id} must be planned before reordering the queue."
                    )

                work_order.queue_position = item.queue_position
                work_order.updated_at = now

            next_queue_position = max(queue_positions, default=0) + 1
            for work_order in omitted_completed_work_orders:
                work_order.queue_position = next_queue_position
                work_order.updated_at = now
                next_queue_position += 1

            self._record_audit_event(
                event_type="manager.queue_reordered",
                station_context=station_context,
                work_order=None,
                target_type="manager_queue",
                target_id=None,
                summary="Reordered manager queue.",
                details={
                    "queue_revision": payload.queue_revision.isoformat(),
                    "items": [
                        {
                            "work_order_id": item.work_order_id,
                            "queue_position": item.queue_position,
                        }
                        for item in items
                    ],
                },
            )

            try:
                self.repository.commit()
            except IntegrityError as exc:
                self.repository.rollback()
                raise InvalidManagerPlanningError("Queue reorder conflicts with current queue state.") from exc
            except Exception:
                self.repository.rollback()
                raise

            return self.list_planned_work_orders()

    @staticmethod
    def _ensure_manager_station_action(station_context: StationContext | None) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids={StationId.MANAGER},
            action="manager planning actions",
        )

    def _get_existing_work_order(self, work_order_id: int) -> WorkOrder:
        work_order = self.repository.get_by_id(work_order_id)
        if work_order is None:
            raise ResourceNotFoundError(f"Work order {work_order_id} not found.")
        return work_order

    def _ensure_queue_position_available_or_releasable(
        self,
        queue_position: int,
        *,
        exclude_work_order_id: int | None = None,
    ) -> None:
        existing_work_order = self.repository.get_planned_by_queue_position(
            queue_position,
            exclude_work_order_id=exclude_work_order_id,
        )
        if existing_work_order is not None and self.process_service.get_display_status(existing_work_order) != ProcessDisplayStatus.READY:
            raise InvalidManagerPlanningError(f"Queue position {queue_position} is already taken.")

    def _get_completed_work_orders_requiring_trailing(
        self,
        *,
        reserved_queue_positions: list[int],
        exclude_work_order_id: int | None = None,
    ) -> list[WorkOrder]:
        planned_work_orders = list(self.repository.list_planned_work_orders())
        completed_work_orders = [
            work_order
            for work_order in planned_work_orders
            if work_order.id != exclude_work_order_id
            and self.process_service.get_display_status(work_order) == ProcessDisplayStatus.READY
        ]
        if not completed_work_orders:
            return []

        active_queue_positions = [
            work_order.queue_position or 0
            for work_order in planned_work_orders
            if work_order.id != exclude_work_order_id
            and self.process_service.get_display_status(work_order) != ProcessDisplayStatus.READY
        ]
        next_completed_position = max(active_queue_positions + reserved_queue_positions, default=0) + 1

        ordered_completed_work_orders = self._sort_queue_rows(completed_work_orders)
        for work_order in ordered_completed_work_orders:
            if work_order.queue_position != next_completed_position:
                return ordered_completed_work_orders
            next_completed_position += 1

        return []

    def _temporarily_move_queue_rows_out_of_the_way(
        self,
        work_orders: list[WorkOrder],
        *,
        reserved_queue_positions: list[int],
        now: datetime,
    ) -> None:
        if not work_orders:
            return

        planned_work_orders = list(self.repository.list_planned_work_orders())
        temporary_queue_position = max(
            [work_order.queue_position or 0 for work_order in planned_work_orders] + reserved_queue_positions,
            default=0,
        ) + 1
        for work_order in work_orders:
            work_order.queue_position = temporary_queue_position
            work_order.updated_at = now
            temporary_queue_position += 1

        self.repository.session.flush()

    def _trail_completed_work_orders(
        self,
        work_orders: list[WorkOrder],
        *,
        now: datetime,
    ) -> None:
        if not work_orders:
            return

        planned_work_orders = list(self.repository.list_planned_work_orders())
        active_queue_positions = [
            work_order.queue_position or 0
            for work_order in planned_work_orders
            if self.process_service.get_display_status(work_order) != ProcessDisplayStatus.READY
        ]
        next_completed_position = max(active_queue_positions, default=0) + 1
        for work_order in self._sort_queue_rows(work_orders):
            work_order.queue_position = next_completed_position
            work_order.updated_at = now
            next_completed_position += 1

    @staticmethod
    def _sort_queue_rows(work_orders: list[WorkOrder]) -> list[WorkOrder]:
        return sorted(work_orders, key=lambda work_order: (work_order.queue_position or 0, work_order.id))

    @staticmethod
    def _ensure_production_not_started(work_order: WorkOrder) -> None:
        blocking_stages = {ProcessStage.HANGING, ProcessStage.PRODUCTION}
        blocking_statuses = {StageStatus.IN_PROGRESS, StageStatus.DONE}
        for stage_state in work_order.stage_states:
            if stage_state.stage in blocking_stages and stage_state.status in blocking_statuses:
                raise InvalidManagerPlanningError(
                    f"Cannot change production type: stage {stage_state.stage.value} has already started."
                )

    @staticmethod
    def _is_planned(work_order: WorkOrder) -> bool:
        return work_order.production_type is not None and work_order.queue_position is not None

    @staticmethod
    def _has_incomplete_marker(work_order: WorkOrder) -> bool:
        return work_order.is_incomplete_on_arrival or work_order.status == WorkOrderStatus.INCOMPLETE

    def _record_audit_event(
        self,
        *,
        event_type: str,
        station_context: StationContext | None,
        work_order: WorkOrder | None,
        target_type: str,
        target_id: int | None,
        summary: str,
        details: dict[str, object],
    ) -> None:
        station_id = station_context.station_id if station_context is not None else StationId.SYSTEM
        self.audit_repository.add(
            AuditEvent(
                event_type=event_type,
                station_id=station_id,
                work_order_id=work_order.id if work_order is not None else None,
                target_type=target_type,
                target_id=target_id,
                summary=summary,
                details_json=json.dumps(details, separators=(",", ":")),
            )
        )

    def _to_read_model(self, work_order: WorkOrder) -> WorkOrderRead:
        waiting_ok_quantity = self.process_service.get_waiting_ok_quantity(work_order)
        pending_correction_quantity = self.process_service.get_pending_correction_quantity(work_order)
        total_progress_quantity = self.process_service.get_total_progress_quantity(work_order)
        queue_resource_block = self.process_service.get_queue_resource_block(work_order)
        predicted_paint_quantity_kg = calculate_predicted_paint_quantity_kg(work_order.total_area_m2)
        current_paint_stock_quantity_kg = self._get_current_paint_stock_quantity_kg(work_order)
        paint_inventory_shortage_quantity_kg = calculate_paint_shortage_quantity_kg(
            predicted_paint_quantity_kg,
            current_paint_stock_quantity_kg,
        )

        return WorkOrderRead(
            id=work_order.id,
            order_number=work_order.order_number,
            external_order_number=work_order.external_order_number,
            title=work_order.title,
            total_quantity=work_order.total_quantity,
            completed_quantity=work_order.completed_quantity,
            current_active_quantity=work_order.current_active_quantity,
            waiting_ok_quantity=waiting_ok_quantity,
            pending_correction_quantity=pending_correction_quantity,
            total_progress_quantity=total_progress_quantity,
            is_correction=work_order.is_correction,
            is_historical_correction=self.process_service.is_historical_correction(work_order),
            work_order_kind=build_work_order_kind_view(work_order.work_order_kind),
            is_ocynk=work_order.is_ocynk,
            correction_reason_category=work_order.correction_reason_category,
            correction_reason_note=work_order.correction_reason_note,
            parent_order=(
                self._build_relation_summary(work_order.parent_order)
                if work_order.parent_order is not None
                else None
            ),
            correction_orders=[
                self._build_relation_summary(correction_order)
                for correction_order in self._get_ordered_correction_orders(work_order)
            ],
            description=work_order.description,
            customer_name=work_order.customer_name,
            ral_code=work_order.ral_code,
            paint_code=work_order.paint_code,
            paint_producer=work_order.paint_producer,
            predicted_paint_quantity_kg=predicted_paint_quantity_kg,
            current_paint_stock_quantity_kg=current_paint_stock_quantity_kg,
            paint_inventory_insufficient_for_prediction=paint_inventory_shortage_quantity_kg is not None,
            paint_inventory_shortage_quantity_kg=paint_inventory_shortage_quantity_kg,
            paint_stock_snapshot_quantity_kg=work_order.paint_stock_snapshot_quantity_kg,
            consumed_paint_quantity_kg=work_order.consumed_paint_quantity_kg,
            status=WorkOrderService.build_status_view(self.process_service.get_display_status(work_order)),
            process_status=build_process_status_view(self.process_service.get_display_status(work_order)),
            queue_blocked_by_resource=(queue_resource_block[0] if queue_resource_block is not None else None),
            queue_blocked_reason=(queue_resource_block[1] if queue_resource_block is not None else None),
            coating_type=build_coating_type_view(work_order.coating_type),
            production_type=(
                build_production_type_view(work_order.production_type)
                if work_order.production_type is not None
                else None
            ),
            queue_namespace=build_queue_namespace_view(work_order.queue_namespace),
            queue_position=work_order.queue_position,
            stage_states=[
                WorkOrderStageStateRead(
                    stage=build_process_stage_view(stage_state.stage),
                    status=build_stage_status_info_view(stage_state.status),
                )
                for stage_state in self._get_ordered_stage_states(work_order)
            ],
            batches=[
                WorkOrderQuantityBatchRead(
                    id=batch.id,
                    quantity=batch.quantity,
                    type=build_quantity_batch_type_view(batch.type),
                    parent_batch_id=batch.parent_batch_id,
                    is_active=batch.is_active,
                    is_finished=not batch.is_active,
                    current_stage=(build_process_stage_view(batch.current_stage) if batch.current_stage is not None else None),
                    current_stage_status=(
                        build_stage_status_info_view(batch.current_stage_status)
                        if batch.current_stage_status is not None
                        else None
                    ),
                    is_partial=batch.is_partial,
                    created_at=batch.created_at,
                )
                for batch in self._get_ordered_batches(work_order)
            ],
            received_date=work_order.received_date,
            planned_pickup_date=work_order.planned_pickup_date,
            is_released_to_client=work_order.released_to_client_at is not None,
            released_to_client_at=work_order.released_to_client_at,
            total_area_m2=work_order.total_area_m2,
            is_incomplete_on_arrival=work_order.is_incomplete_on_arrival,
            surface_preparation_counted_quantity=self.process_service.get_surface_preparation_counted_quantity(work_order),
            surface_preparation_quantity_difference=self.process_service.get_surface_preparation_quantity_difference(work_order),
            profiles_quantity=work_order.profiles_quantity,
            profiles_to_count=work_order.profiles_to_count,
            accessories_quantity=work_order.accessories_quantity,
            accessories_to_count=work_order.accessories_to_count,
            notes=work_order.notes,
            created_at=work_order.created_at,
            updated_at=work_order.updated_at,
        )

    def _get_ordered_stage_states(self, work_order: WorkOrder):
        stage_order = {
            stage: index
            for index, stage in enumerate(self.process_service.get_stage_sequence_for_work_order(work_order))
        }
        return sorted(
            [stage_state for stage_state in work_order.stage_states if stage_state.stage in stage_order],
            key=lambda stage_state: stage_order[stage_state.stage],
        )

    @staticmethod
    def _get_ordered_batches(work_order: WorkOrder):
        return sorted(work_order.quantity_batches, key=lambda batch: (batch.created_at, batch.id))

    @staticmethod
    def _get_ordered_correction_orders(work_order: WorkOrder) -> list[WorkOrder]:
        return sorted(work_order.correction_orders, key=lambda correction_order: (correction_order.created_at, correction_order.id))

    def _build_relation_summary(self, work_order: WorkOrder):
        summary = build_work_order_relation_summary(work_order)
        summary.process_status = build_process_status_view(self.process_service.get_display_status(work_order))
        summary.is_historical_correction = self.process_service.is_historical_correction(work_order)
        return summary
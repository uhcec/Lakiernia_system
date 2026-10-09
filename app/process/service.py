from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import logging
from threading import RLock

from sqlalchemy import func, or_, select

from app.audit.context import StationContext, ensure_station_allowed
from app.audit.repository import AuditRepository
from app.process.audit_writer import ProcessAuditWriter
from app.process.paint_runs import PaintRunTracker, paint_identity_of
from app.process.resource_locks import ResourceLockManager
from app.paints.repository import PaintRepository
from app.paints.service import PaintService
from app.process.enums import CoatingType, CorrectionKind, ProcessDisplayStatus, ProcessStage, ProductionType, QuantityBatchType, StageStatus, get_production_type_label
from app.process.models import StatOnlyCorrection, WorkOrderQuantityBatch, WorkOrderStageState
from app.process.repository import ProcessRepository
from app.process.shared_stage import PrepCandidate, derive_surface_preparation_order
from app.foils.schemas import FoilSummaryRead
from app.process.schemas import (
    PaintRunMemberRead,
    PaintRunRead,
    PaintRunsOverviewRead,
    ProcessStageStatusRead,
    ProcessStageWorkOrderRead,
    StageStatusView,
    WorkOrderAttachmentSummaryRead,
)
from app.work_orders.enums import WorkOrderAttachmentCategory
from app.shared.enums import QueueNamespace, StationId, WorkOrderKind
from app.shared.exceptions import InvalidProcessStageTransitionError, ResourceNotFoundError
from app.work_orders.number_allocator import WorkOrderNumberAllocator
from app.work_orders.models import WorkOrder
from app.work_orders.schemas import build_coating_type_view, build_production_type_view, build_queue_namespace_view, build_work_order_kind_view
from app.shared import clock


logger = logging.getLogger(__name__)

_PROCESS_MUTATION_LOCKS: dict[int, RLock] = {}
_PROCESS_MUTATION_LOCKS_GUARD = RLock()


@dataclass(frozen=True)
class StageQuantities:
    """The quantities a station card shows for one (work order, stage, batch), resolved in one
    place (NA43). See ``docs/SPEC.md`` §4 (Quantities & counting) for what each means and when it
    applies. These are **display-only**: validation/READY use ``total_quantity`` / counted directly.

    - ``display`` — ``batch_quantity``: the headline count on the card.
    - ``planned`` — ``planned_quantity``: the expected count for the stage (the ordered total, or a
      tracked/correction batch's own size).
    - ``counted`` — ``counted_quantity``: actually counted at SURFACE_PREPARATION / PACKING; ``None``
      at every other stage.
    - ``operational`` — ``operational_quantity``: pieces the operator physically handles (NA26).
    """

    display: int | None
    planned: int
    counted: int | None
    operational: int


class ProcessService:
    # i18n convention for InvalidProcessStageTransitionError messages: the frontend surfaces a 4xx
    # `detail` verbatim to the operator (see frontend getMutationErrorMessage), so **operator-facing
    # reasons are written in Polish** (a rejection the operator can act on — wrong count, wrong state,
    # missing paint, etc.). The remaining English messages are **internal state-machine guards** for
    # illegal transitions the UI cannot produce (e.g. "Cannot transition stage X from A to B", "... is
    # not configured for work order Y") — developer diagnostics, not operator copy, so they stay English.
    DEFAULT_CORRECTION_RETURN_STAGE = ProcessStage.PRODUCTION
    AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR = (
        "Produkcja automatyczna nie korzysta z ręcznego rozpoczęcia/zakończenia. Zakończ ZAWIESZANIE, aby wejść na produkcję automatyczną, a zlecenie zakończ z poziomu PAKOWANIA."
    )
    # Operator-facing (Polish) reason surfaced on the packing card when an automatic order is being
    # packed in parallel with the line but cannot be *completed* yet (mirrors the complete_packing guard).
    # Paint consumption no longer gates packing — it is entered per paint run (CHANGES #22).
    PACKING_COMPLETION_BLOCKED_HANGING_PL = "Nie można zakończyć pakowania, dopóki nie zakończy się zawieszanie."
    QUEUE_RESOURCE_BLOCK_REASONS = {
        "HANGING": "Zawieszanie zajęte",
        "AUTOMATIC_LINE": "Linia automatyczna zajęta",
    }

    def __init__(self, repository: ProcessRepository) -> None:
        self.repository = repository
        self.paint_service = PaintService(PaintRepository(repository.session))
        self.number_allocator = WorkOrderNumberAllocator(repository.session)
        self.audit_repository = AuditRepository(repository.session)
        self.audit = ProcessAuditWriter(repository.session, self.audit_repository)
        self.resource_locks = ResourceLockManager(repository)
        self.paint_runs = PaintRunTracker(self.paint_service.repository, self.paint_service, self.audit)

    @staticmethod
    def get_stage_sequence_for_configuration(
        coating_type: CoatingType,
        production_type: ProductionType | None,
        *,
        skips_surface_preparation: bool = False,
    ) -> list[ProcessStage]:
        stages = [] if skips_surface_preparation else [ProcessStage.SURFACE_PREPARATION]
        if production_type != ProductionType.MANUAL:
            stages.append(ProcessStage.HANGING)
        stages.append(ProcessStage.PRODUCTION)
        stages.append(ProcessStage.PACKING)
        if coating_type == CoatingType.DECORAL:
            stages.append(ProcessStage.DECORAL_PRODUCTION)
        return stages

    def get_stage_sequence_for_work_order(self, work_order: WorkOrder) -> list[ProcessStage]:
        return self.get_stage_sequence_for_configuration(
            work_order.coating_type,
            work_order.production_type,
            skips_surface_preparation=self._omits_surface_preparation_stage(work_order),
        )

    @staticmethod
    def get_configured_stage_states_sequence(
        coating_type: CoatingType,
        *,
        skips_surface_preparation: bool = False,
    ) -> list[ProcessStage]:
        stages = [] if skips_surface_preparation else [ProcessStage.SURFACE_PREPARATION]
        stages.extend([ProcessStage.HANGING, ProcessStage.PRODUCTION, ProcessStage.PACKING])
        if coating_type == CoatingType.DECORAL:
            stages.append(ProcessStage.DECORAL_PRODUCTION)
        return stages

    def initialize_stage_states(self, work_order: WorkOrder) -> None:
        stage_states = [
            WorkOrderStageState(
                work_order_id=work_order.id,
                stage=stage,
                status=StageStatus.NOT_STARTED,
            )
            for stage in self.get_configured_stage_states_sequence(
                work_order.coating_type,
                skips_surface_preparation=self._omits_surface_preparation_stage(work_order),
            )
        ]
        self.repository.add_stage_states(stage_states)

    def reconcile_stage_states_to_route(self, work_order: WorkOrder) -> None:
        # NA42: stage-state rows are created as a method-agnostic superset at intake because the
        # production method (MANUAL/AUTOMATIC) isn't chosen until manager planning. Once it IS known,
        # trim the rows to the order's real route — AUTOMATIC has no PRODUCTION (the line paints
        # automatically; there is no manual production step), MANUAL has no HANGING — and add any the
        # route now needs if the method is later switched. This removes the "phantom" stage that used
        # to be special-cased everywhere. Idempotent.
        if work_order.production_type is None:
            return  # route still unknown until planned; keep the superset
        target_stages = set(self.get_actionable_stage_sequence_for_work_order(work_order))
        existing_stages = {stage_state.stage for stage_state in work_order.stage_states}
        for stage_state in list(work_order.stage_states):
            if stage_state.stage not in target_stages:
                work_order.stage_states.remove(stage_state)
        for stage in target_stages:
            if stage not in existing_stages:
                work_order.stage_states.append(
                    WorkOrderStageState(work_order_id=work_order.id, stage=stage, status=StageStatus.NOT_STARTED)
                )

    def initialize_quantity_tracking(self, work_order: WorkOrder) -> None:
        main_batch = WorkOrderQuantityBatch(
            work_order_id=work_order.id,
            quantity=work_order.total_quantity,
            type=QuantityBatchType.MAIN,
            parent_batch_id=None,
            is_active=True,
            current_stage=None,
            current_stage_status=None,
            is_partial=False,
        )
        self.repository.add_quantity_batch(main_batch)

    def list_stage_states(self, work_order_id: int) -> Sequence[WorkOrderStageState]:
        return self.repository.list_stage_states(work_order_id)

    @staticmethod
    def get_surface_preparation_counted_quantity(work_order: WorkOrder) -> int | None:
        for stage_state in work_order.stage_states:
            if stage_state.stage == ProcessStage.SURFACE_PREPARATION:
                return stage_state.counted_quantity
        return None

    def get_surface_preparation_quantity_difference(self, work_order: WorkOrder) -> int | None:
        counted_quantity = self.get_surface_preparation_counted_quantity(work_order)
        if counted_quantity is None:
            return None
        return counted_quantity - work_order.total_quantity

    def get_work_order_process(self, work_order_id: int) -> WorkOrder:
        work_order = self.repository.get_work_order_with_stage_states(work_order_id)
        if work_order is None:
            raise ResourceNotFoundError(f"Work order {work_order_id} not found.")
        return work_order

    def transition_stage(
        self,
        work_order_id: int,
        stage: ProcessStage,
        target_status: StageStatus,
        station_context: StationContext | None = None,
    ) -> WorkOrderStageState:
        with self._serialize_process_mutation(work_order_id):
            work_order = self.get_work_order_process(work_order_id)
            self._ensure_stage_station_action(work_order, stage, station_context)
            resource_keys = self.resource_locks.get_stage_resource_keys(work_order, stage, target_status)
            with self.resource_locks.serialize_stage_resources(resource_keys):
                if resource_keys:
                    self.resource_locks.ensure_stage_resources_available(work_order, stage, target_status)

                stage_state = self._get_stage_state(work_order, stage)
                self._validate_transition(work_order, stage_state, target_status)
                # CHANGES #22: automatic hanging drives paint-run membership — a hanging start joins the
                # current same-paint run (or opens a new one); undoing the start takes the order back out.
                if stage == ProcessStage.HANGING and work_order.production_type == ProductionType.AUTOMATIC:
                    with self.resource_locks.serialize_resource_mutation(self.PAINT_RUN_RESOURCE_KEY):
                        if stage_state.status == StageStatus.NOT_STARTED and target_status == StageStatus.IN_PROGRESS:
                            self.paint_runs.join_on_hanging_start(work_order, station_context=station_context)
                        elif stage_state.status == StageStatus.IN_PROGRESS and target_status == StageStatus.NOT_STARTED:
                            self.paint_runs.leave_on_hanging_undo(work_order, station_context=station_context)
                if resource_keys:
                    self.resource_locks.acquire_stage_resource_locks(work_order, stage, target_status)
                stage_state.status = target_status
                stage_state.updated_at = clock.now()
                # NA22a: automatic orders reserve a packing slot the moment hanging starts.
                self.resource_locks.reserve_packing_for_automatic_hanging(work_order, stage, target_status)

                # The automatic line runs without a manual production step (NA42: AUTOMATIC has no
                # PRODUCTION stage), so PACKING moves into progress as soon as automatic HANGING
                # *starts* (not only when it finishes): an automatic order begins packing immediately
                # instead of merely holding a slot reservation. Packing *completion* still waits for
                # HANGING to be DONE (see complete_packing). The DONE branch remains an idempotent
                # fallback for orders whose hanging started before this behavior existed. Log the
                # implicit transition so cycle-time/throughput stats see when the line started.
                implicit_in_progress: list[ProcessStage] = []
                if (
                    stage == ProcessStage.HANGING
                    and target_status in {StageStatus.IN_PROGRESS, StageStatus.DONE}
                    and work_order.production_type == ProductionType.AUTOMATIC
                ):
                    packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)
                    if packing_state.status == StageStatus.NOT_STARTED:
                        packing_state.status = StageStatus.IN_PROGRESS
                        packing_state.updated_at = stage_state.updated_at
                        implicit_in_progress.append(ProcessStage.PACKING)

                if target_status != StageStatus.IN_PROGRESS:
                    self.resource_locks.release_inactive_resource_locks(work_order)

                self.audit.record_stage_audit_event(
                    work_order=work_order,
                    stage=stage,
                    target_status=target_status,
                    station_context=station_context,
                    batch_id=None,
                )
                for implicit_stage in implicit_in_progress:
                    self.audit.record_stage_transition(
                        work_order=work_order,
                        stage=implicit_stage,
                        status=StageStatus.IN_PROGRESS,
                        station_context=station_context,
                        batch_id=None,
                    )

                try:
                    self.repository.commit()
                except Exception:
                    self.repository.rollback()
                    raise

                return stage_state

    def list_stage_work_orders(
        self,
        stage: ProcessStage,
        production_type: ProductionType | None = None,
        queue_namespace: QueueNamespace | None = None,
    ) -> list[ProcessStageWorkOrderRead]:
        work_orders = self.repository.list_work_orders_with_stage(stage, production_type, queue_namespace)
        items: list[ProcessStageWorkOrderRead] = []
        for work_order in work_orders:
            tracked_batches = self._get_batches_visible_in_stage(work_order, stage, include_done=True)
            if tracked_batches:
                items.extend(self._to_stage_work_order_read(work_order, stage, batch=batch) for batch in tracked_batches)
                continue

            if self.is_visible_in_stage(work_order, stage, production_type, include_done=True):
                items.append(self._to_stage_work_order_read(work_order, stage))

        # N49-10: the two physically shared stages must NOT use the per-line `queue_position` as a global
        # rank (it makes a MANUAL and an AUTOMATIC order collide on the same "Poz. N"). Re-derive a single
        # cross-line order and stamp a line label so the frontend renders the label, not the position.
        if stage == ProcessStage.SURFACE_PREPARATION:
            return self._apply_surface_preparation_derivation(items)
        if stage == ProcessStage.PACKING:
            return self._apply_packing_derivation(items)

        return items

    def _apply_surface_preparation_derivation(
        self,
        items: list[ProcessStageWorkOrderRead],
    ) -> list[ProcessStageWorkOrderRead]:
        """Re-order + label the SURFACE_PREPARATION feeder (N49-10).

        One shared prep station feeds both booths, so the order is a single interleaved sequence derived
        by the smaller-buffer rule (see ``app/process/shared_stage.py``). The active (not-yet-prepped)
        rows are interleaved and the head is marked "NASTĘPNE"; rows already DONE keep their relative
        order at the tail. Every row is line-labelled; nothing reads its per-line ``queue_position``.
        """
        active_items = [item for item in items if item.stage_status.status.value != StageStatus.DONE]
        done_items = [item for item in items if item.stage_status.status.value == StageStatus.DONE]

        candidates = [
            PrepCandidate(
                work_order_id=item.id,
                production_type=ProductionType(item.production_type.value),
                plan_rank=(item.queue_position is None, item.queue_position or 0),
                pieces=item.operational_quantity,
            )
            for item in active_items
            if item.production_type is not None
        ]
        initial_buffer_pieces = self._prepared_not_yet_painted_buffer_pieces()
        ordered_ids = derive_surface_preparation_order(candidates, initial_buffer_pieces)

        by_id = {item.id: item for item in active_items}
        # Rows without a production line (should not happen for planned orders) keep their original order
        # at the tail so nothing is dropped.
        ordered_active = [by_id[order_id] for order_id in ordered_ids if order_id in by_id]
        ordered_active += [item for item in active_items if item.id not in set(ordered_ids)]

        for position, item in enumerate(ordered_active):
            item.shared_stage_line_label = self._shared_stage_line_label(item)
            item.is_next_at_shared_stage = position == 0
        for item in done_items:
            item.shared_stage_line_label = self._shared_stage_line_label(item)

        return ordered_active + done_items

    def _apply_packing_derivation(
        self,
        items: list[ProcessStageWorkOrderRead],
    ) -> list[ProcessStageWorkOrderRead]:
        """Re-order + label the PACKING drain by physical readiness (N49-10).

        Packing has no manual position numbering: the order follows physical readiness plus the existing
        packing-slot reservation. Active rows sort by (1) currently being packed / holding a slot, (2)
        already at the packing station vs still waiting on the line (HANGING), (3) the order can actually
        be completed now; a stable id tie-break keeps it deterministic. Every row is line-labelled so the
        frontend never shows an ambiguous "Poz.".
        """
        active_items = [item for item in items if item.stage_status.status.value != StageStatus.DONE]
        done_items = [item for item in items if item.stage_status.status.value == StageStatus.DONE]

        def readiness_key(item: ProcessStageWorkOrderRead) -> tuple:
            at_packing = item.stage_status.stage == ProcessStage.PACKING
            return (
                not item.holds_packing_slot,  # slot holders (incl. being packed) first
                not at_packing,               # physically at packing before still-on-line (HANGING)
                not item.can_complete_packing,  # ready-to-finish before blocked
                item.id,                       # deterministic tie-break
            )

        ordered_active = sorted(active_items, key=readiness_key)
        for item in ordered_active + done_items:
            item.shared_stage_line_label = self._shared_stage_line_label(item)

        return ordered_active + done_items

    @staticmethod
    def _shared_stage_line_label(item: ProcessStageWorkOrderRead) -> str | None:
        if item.production_type is None:
            return None
        return get_production_type_label(ProductionType(item.production_type.value))

    def _prepared_not_yet_painted_buffer_pieces(self) -> dict[ProductionType, int]:
        """Per-line buffer (pieces) of orders already prepped but not yet painted — seeds the surface-prep
        interleave so the line closest to starving its booth is fed first.

        An order visible at the painting stage (PRODUCTION for MANUAL, the HANGING/line view for
        AUTOMATIC) has passed surface prep and not yet finished painting — exactly the prepared-but-not-
        yet-painted buffer. Buffer is measured in pieces (owner assumption, N49-10).
        """
        buffer: dict[ProductionType, int] = {}
        for line in (ProductionType.MANUAL, ProductionType.AUTOMATIC):
            painting_orders = self.list_visible_work_orders(
                ProcessStage.PRODUCTION,
                production_type=line,
                include_done=False,
            )
            buffer[line] = sum(
                (self._get_surface_preparation_actual_quantity(work_order) or work_order.current_active_quantity)
                for work_order in painting_orders
            )
        return buffer

    def start_stage(
        self,
        work_order_id: int,
        stage: ProcessStage,
        batch_id: int | None = None,
        counted_quantity: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        with self._serialize_process_mutation(work_order_id):
            work_order = self.get_work_order_process(work_order_id)
            self._ensure_stage_station_action(work_order, stage, station_context)
            target_batch = self._resolve_batch_for_stage(work_order, stage, batch_id)
            if target_batch is not None:
                resource_keys = self.resource_locks.get_stage_resource_keys(work_order, stage, StageStatus.IN_PROGRESS)
                with self.resource_locks.serialize_stage_resources(resource_keys):
                    self.resource_locks.ensure_stage_resources_available(work_order, stage, StageStatus.IN_PROGRESS)
                    return self._start_tracked_batch_stage(
                        work_order,
                        target_batch,
                        stage,
                        counted_quantity=counted_quantity,
                        station_context=station_context,
                    )

            if self._is_automatic_production_preview_stage(work_order, stage):
                raise InvalidProcessStageTransitionError(self.AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR)

            if self._is_skipped_surface_preparation(work_order, stage):
                raise InvalidProcessStageTransitionError(self._get_surface_preparation_skipped_message(work_order))

            self._store_stage_start_data(work_order, stage, counted_quantity)

            self.transition_stage(work_order_id, stage, StageStatus.IN_PROGRESS, station_context=station_context)
            work_order = self.get_work_order_process(work_order_id)

            return self._to_stage_work_order_read(work_order, stage)

    def finish_stage(
        self,
        work_order_id: int,
        stage: ProcessStage,
        batch_id: int | None = None,
        counted_quantity: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        with self._serialize_process_mutation(work_order_id):
            work_order = self.get_work_order_process(work_order_id)
            self._ensure_stage_station_action(work_order, stage, station_context)
            target_batch = self._resolve_batch_for_stage(work_order, stage, batch_id)
            if target_batch is not None:
                return self._finish_tracked_batch_stage(
                    work_order,
                    target_batch,
                    stage,
                    counted_quantity=counted_quantity,
                    station_context=station_context,
                )

            if self._is_automatic_production_preview_stage(work_order, stage):
                raise InvalidProcessStageTransitionError(self.AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR)

            stage_state = self._get_stage_state(work_order, stage)
            if stage_state.status == StageStatus.DONE:
                return self._to_stage_work_order_read(work_order, stage)

            if stage == ProcessStage.SURFACE_PREPARATION:
                self._store_surface_preparation_counted_quantity(work_order, counted_quantity)
                self._ensure_surface_preparation_counted_quantity(work_order)

            if stage == ProcessStage.PACKING:
                return self.complete_packing(
                    work_order_id,
                    counted_quantity=work_order.current_active_quantity,
                    ok_quantity=work_order.current_active_quantity,
                    correction_quantity=0,
                    station_context=station_context,
                )

            self.transition_stage(work_order_id, stage, StageStatus.DONE, station_context=station_context)
            work_order = self.get_work_order_process(work_order_id)

            if stage == ProcessStage.DECORAL_PRODUCTION:
                active_quantity = work_order.current_active_quantity
                if active_quantity > 0:
                    work_order.completed_quantity += active_quantity
                    active_batch = work_order.active_batch
                    if active_batch is not None:
                        active_batch.is_active = False
                    try:
                        self.repository.commit()
                    except Exception:
                        self.repository.rollback()
                        raise
                    work_order = self.get_work_order_process(work_order_id)

                    finalized_work_order = self._finalize_completion_chain_if_ready(work_order)
                    if finalized_work_order is not None:
                        work_order = self.get_work_order_process(work_order_id)

            return self._to_stage_work_order_read(work_order, stage)

    def reopen_stage(
        self,
        work_order_id: int,
        stage: ProcessStage,
        batch_id: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        work_order = self.get_work_order_process(work_order_id)
        self._ensure_stage_station_action(work_order, stage, station_context)
        target_batch = self._resolve_batch_for_stage(work_order, stage, batch_id)
        if target_batch is not None:
            return self._reopen_tracked_batch_stage(work_order, target_batch, stage, station_context=station_context)

        if self._is_automatic_production_preview_stage(work_order, stage):
            raise InvalidProcessStageTransitionError(self.AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR)

        if self._is_skipped_surface_preparation(work_order, stage):
            raise InvalidProcessStageTransitionError(self._get_surface_preparation_skipped_message(work_order))

        stage_state = self._get_stage_state(work_order, stage)

        if work_order.current_active_quantity == 0:
            raise InvalidProcessStageTransitionError(
                "Nie można ponownie otworzyć etapów, ponieważ w zleceniu nie pozostała żadna aktywna ilość."
            )

        if stage_state.status == StageStatus.DONE:
            target_status = StageStatus.IN_PROGRESS
        elif stage_state.status == StageStatus.IN_PROGRESS:
            target_status = StageStatus.NOT_STARTED
        else:
            raise InvalidProcessStageTransitionError(
                f"Cannot reopen stage {stage.value} from {stage_state.status.value}."
            )

        self.transition_stage(work_order_id, stage, target_status, station_context=station_context)
        work_order = self.get_work_order_process(work_order_id)
        return self._to_stage_work_order_read(work_order, stage)

    # Owner decision 2026-07-11 (DECISIONS.md): manager, admin AND office may reset — wider than
    # the review's office-only proposal. Admins bypass via the standard station check.
    ADMIN_RESET_ALLOWED_STATIONS = {StationId.MANAGER, StationId.OFFICE}

    def administrative_reset(self, work_order_id: int, station_context: StationContext | None = None) -> WorkOrder:
        """Reset a genuinely stuck order back to the start of its route (CHANGES #14).

        The escape hatch that pairs with the #14 downstream guard: when reality invents a state the
        stage flow cannot legally leave, the office/manager resets the order to "planned, nothing
        started" — all stage rows NOT_STARTED, counts cleared, one fresh active MAIN batch at the
        ordered total, completed 0, leak flag cleared — and the floor runs it again. The order keeps
        its plan (line + position) if it still holds one. Deliberately refuses orders entangled in a
        correction chain (parent or child): their quantity is split across related orders and a blind
        reset would break conservation — the correction flow itself is the recovery path there.
        Physical facts are kept: recorded paint consumption stays (correct stock manually if needed);
        a held packing slot is reclaimed by the stale-lock auto-recovery once the stage is reset.
        """
        with self._serialize_process_mutation(work_order_id):
            ensure_station_allowed(
                station_context,
                allowed_station_ids=self.ADMIN_RESET_ALLOWED_STATIONS,
                action="administracyjny reset zlecenia",
            )
            work_order = self.get_work_order_process(work_order_id)
            if work_order.is_correction or work_order.correction_orders:
                raise InvalidProcessStageTransitionError(
                    "Reset administracyjny nie obsługuje zleceń powiązanych z poprawkami "
                    "(rodzica z dziećmi-poprawkami ani samej poprawki). Użyj przepływu poprawek."
                )

            before_stage_statuses = {stage_state.stage.value: stage_state.status.value for stage_state in work_order.stage_states}
            before_completed_quantity = work_order.completed_quantity
            before_active_quantity = work_order.current_active_quantity

            now = clock.now()
            for batch in work_order.quantity_batches:
                batch.is_active = False
                batch.current_stage = None
                batch.current_stage_status = None
            # Flush the deactivations BEFORE inserting the fresh MAIN batch: the unit of work emits
            # INSERTs before UPDATEs, so without this the new active batch would transiently collide
            # with the old one on the one-active-batch-per-order partial unique index.
            self.repository.session.flush()
            self.repository.add_quantity_batch(
                WorkOrderQuantityBatch(
                    work_order_id=work_order.id,
                    quantity=work_order.total_quantity,
                    type=QuantityBatchType.MAIN,
                    parent_batch_id=None,
                    is_active=True,
                    current_stage=None,
                    current_stage_status=None,
                    is_partial=False,
                )
            )
            for stage_state in work_order.stage_states:
                stage_state.status = StageStatus.NOT_STARTED
                stage_state.counted_quantity = None
                stage_state.updated_at = now
            work_order.completed_quantity = 0
            work_order.quantity_leak_flagged = False
            work_order.updated_at = now

            self.audit.record_audit_event(
                event_type="work_order.administrative_reset",
                station_context=station_context,
                work_order=work_order,
                target_type="work_order",
                target_id=work_order.id,
                summary=(
                    f"Administrative reset of work order {work_order.order_number}: "
                    f"route restarted from scratch (was completed {before_completed_quantity}, "
                    f"active {before_active_quantity})."
                ),
                details={
                    "before_stage_statuses": before_stage_statuses,
                    "before_completed_quantity": before_completed_quantity,
                    "before_active_quantity": before_active_quantity,
                },
            )
            self._commit_process_changes()
            return self.get_work_order_process(work_order_id)

    def start_packing(
        self,
        work_order_id: int,
        batch_id: int | None = None,
        station_context: StationContext | None = None,
        override: bool = False,
    ) -> ProcessStageWorkOrderRead:
        """Claim a packing slot for this work order (NA22).

        Takes one of the N configured packing slots. By default a claim succeeds only when the station
        is completely free (single-station exclusivity); when packing is occupied — e.g. reserved by an
        automatic order at hanging start — a manual operator may pass ``override=True`` to open an
        additional slot up to the configured cap. Automatic orders reserve their slot automatically at
        hanging start, not here. Idempotent for an order that already holds a slot.
        """
        with self._serialize_process_mutation(work_order_id):
            work_order = self.get_work_order_process(work_order_id)
            self._ensure_packing_station_action(station_context)
            already_held = self.resource_locks.work_order_packing_slot_key(work_order.id) is not None
            target_batch = self._resolve_batch_for_stage(work_order, ProcessStage.PACKING, batch_id)

            if target_batch is not None:
                if self._has_tracked_batch_already_finished_stage(work_order, target_batch, ProcessStage.PACKING):
                    return self._to_stage_work_order_read(work_order, ProcessStage.PACKING, batch=target_batch)
                if target_batch.current_stage != ProcessStage.PACKING:
                    raise InvalidProcessStageTransitionError("Partia nie jest gotowa do pakowania.")
                self.resource_locks.acquire_packing_slot(work_order, override=override)
                if override and not already_held:
                    self.audit.record_packing_override_audit_event(work_order, station_context, batch_id=target_batch.id)
                if target_batch.current_stage_status == StageStatus.NOT_STARTED:
                    target_batch.current_stage_status = StageStatus.IN_PROGRESS
                    self.audit.record_stage_audit_event(
                        work_order=work_order,
                        stage=ProcessStage.PACKING,
                        target_status=StageStatus.IN_PROGRESS,
                        station_context=station_context,
                        batch_id=target_batch.id,
                    )
                self._commit_process_changes()
                refreshed_work_order = self.get_work_order_process(work_order_id)
                refreshed_batch = self._get_batch(refreshed_work_order, target_batch.id)
                return self._to_stage_work_order_read(refreshed_work_order, ProcessStage.PACKING, batch=refreshed_batch)

            packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)
            hanging_state = self._find_stage_state(work_order, ProcessStage.HANGING)  # None for MANUAL (NA42)

            if packing_state.status == StageStatus.DONE:
                return self._to_idempotent_packing_response(work_order)

            if work_order.production_type == ProductionType.AUTOMATIC and hanging_state.status != StageStatus.DONE:
                raise InvalidProcessStageTransitionError("Trzeba zakończyć zawieszanie automatu przed pakowaniem.")

            if packing_state.status == StageStatus.NOT_STARTED:
                # Validates prerequisites (previous stage DONE, workflow membership) before claiming.
                self._validate_transition(work_order, packing_state, StageStatus.IN_PROGRESS)

            self.resource_locks.acquire_packing_slot(work_order, override=override)
            if override and not already_held:
                self.audit.record_packing_override_audit_event(work_order, station_context, batch_id=None)

            if packing_state.status == StageStatus.NOT_STARTED:
                packing_state.status = StageStatus.IN_PROGRESS
                packing_state.updated_at = clock.now()
                self.audit.record_stage_audit_event(
                    work_order=work_order,
                    stage=ProcessStage.PACKING,
                    target_status=StageStatus.IN_PROGRESS,
                    station_context=station_context,
                    batch_id=None,
                )

            try:
                self.repository.commit()
            except Exception:
                self.repository.rollback()
                raise

            refreshed_work_order = self.get_work_order_process(work_order_id)
            return self._to_stage_work_order_read(refreshed_work_order, ProcessStage.PACKING)

    def release_packing(
        self,
        work_order_id: int,
        batch_id: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        """Release this work order's claim on the packing station without completing it.

        For when an operator claimed the wrong order. Only frees the claim (drops the ``PACKING``
        lock if this order holds it); it does not change packing stage status, so the card simply
        returns to the unclaimed "ready to start" state. Idempotent and cannot release another
        order's claim (the repository only deletes a lock owned by this work order).
        """
        with self._serialize_process_mutation(work_order_id):
            work_order = self.get_work_order_process(work_order_id)
            self._ensure_packing_station_action(station_context)
            held_claim = self.resource_locks.work_order_packing_slot_key(work_order.id) is not None
            with self.resource_locks.serialize_resource_mutation(self.resource_locks.PACKING_SLOT_PREFIX):
                self.resource_locks.release_packing_slot(work_order)
            if held_claim:
                self.audit.record_audit_event(
                    event_type="process.packing.claim_released",
                    station_context=station_context,
                    work_order=work_order,
                    target_type="process_stage",
                    target_id=batch_id,
                    summary=f"Released packing-station claim for work order {work_order.order_number}.",
                    details={"stage": ProcessStage.PACKING.value, "batch_id": batch_id},
                )
            try:
                self.repository.commit()
            except Exception:
                self.repository.rollback()
                raise
            refreshed_work_order = self.get_work_order_process(work_order_id)
            target_batch = self._resolve_batch_for_stage(refreshed_work_order, ProcessStage.PACKING, batch_id)
            return self._to_stage_work_order_read(refreshed_work_order, ProcessStage.PACKING, batch=target_batch)

    def complete_packing(
        self,
        work_order_id: int,
        *,
        counted_quantity: int,
        ok_quantity: int,
        correction_quantity: int,
        correction_profiles_quantity: int | None = None,
        correction_accessories_quantity: int | None = None,
        correction_reason_category: str | None = None,
        correction_reason_note: str | None = None,
        stat_only_correction: bool = False,
        batch_id: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        with self._serialize_process_mutation(work_order_id):
            work_order = self.get_work_order_process(work_order_id)
            self._ensure_packing_station_action(station_context)
            normalized_correction_reason_category, normalized_correction_reason_note = self._validate_correction_reason(
                correction_quantity,
                correction_reason_category,
                correction_reason_note,
            )
            correction_category_fields = self._validate_correction_category_split(
                correction_quantity,
                correction_profiles_quantity,
                correction_accessories_quantity,
            )
            target_batch = self._resolve_batch_for_stage(work_order, ProcessStage.PACKING, batch_id)
            if target_batch is not None:
                return self._complete_tracked_batch_packing(
                    work_order,
                    target_batch,
                    counted_quantity=counted_quantity,
                    ok_quantity=ok_quantity,
                    correction_quantity=correction_quantity,
                    correction_category_fields=correction_category_fields,
                    correction_reason_category=normalized_correction_reason_category,
                    correction_reason_note=normalized_correction_reason_note,
                    stat_only_correction=stat_only_correction,
                    station_context=station_context,
                )

            packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)
            hanging_state = self._find_stage_state(work_order, ProcessStage.HANGING)  # None for MANUAL (NA42)

            if packing_state.status == StageStatus.DONE:
                return self._to_idempotent_packing_response(work_order)

            if self._is_in_correction_round(work_order) and packing_state.status == StageStatus.NOT_STARTED:
                return self._to_idempotent_packing_response(work_order)

            if work_order.production_type == ProductionType.AUTOMATIC and hanging_state.status == StageStatus.IN_PROGRESS:
                raise InvalidProcessStageTransitionError("Trzeba zakończyć zawieszanie automatu przed pakowaniem.")

            if packing_state.status != StageStatus.IN_PROGRESS:
                raise InvalidProcessStageTransitionError("Pakowanie można zakończyć tylko ze stanu W TRAKCIE.")

            # Confirm a packing slot before mutating: idempotent if this order started packing, else
            # take any free slot (completion is capacity-bound — the start action is the gate). 409
            # only when all slots are genuinely full.
            self.resource_locks.acquire_packing_slot(work_order, for_completion=True)

            active_batch = work_order.active_batch
            if active_batch is None:
                raise InvalidProcessStageTransitionError("Brak aktywnej partii ilościowej do pakowania.")

            if ok_quantity + correction_quantity != counted_quantity:
                raise InvalidProcessStageTransitionError(
                    "Ilości pakowania muszą sumować się do policzonej ilości."
                )

            if ok_quantity < 0 or correction_quantity < 0:
                raise InvalidProcessStageTransitionError("Ilości pakowania nie mogą być ujemne.")

            planned_quantity = active_batch.quantity
            if self._is_in_correction_round(work_order):
                required_counted_quantity = planned_quantity
            else:
                actual_received_quantity = self._get_surface_preparation_actual_quantity(work_order)
                required_counted_quantity = actual_received_quantity if actual_received_quantity is not None else planned_quantity
            if counted_quantity != required_counted_quantity:
                raise InvalidProcessStageTransitionError(
                    "Policzona ilość musi odpowiadać rzeczywistej ilości z przygotowania powierzchni."
                    if not self._is_in_correction_round(work_order) and self._get_surface_preparation_actual_quantity(work_order) is not None
                    else "Policzona ilość różni się od planowanej. Wyjaśnij brakujące sztuki."
                )

            packing_state.counted_quantity = counted_quantity
            packing_state.updated_at = clock.now()

            # AUTOMATIC orders have no PRODUCTION stage (NA42); only MANUAL ones do.
            production_state = self._find_stage_state(work_order, ProcessStage.PRODUCTION)

            # Stat-only correction (NA34): the pieces were fixed on the spot, so the order completes
            # as-is — record the statistic, then fold the corrected pieces into OK and fall through the
            # normal no-correction completion below (RAL closes READY; DECORAL pieces continue Decoral).
            if correction_quantity > 0 and self._select_correction_kind(
                work_order, tracked_batch=False, stat_only=stat_only_correction
            ) == CorrectionKind.STAT_ONLY:
                self._record_stat_only_correction(
                    work_order,
                    correction_quantity=correction_quantity,
                    correction_category_fields=correction_category_fields,
                    correction_reason_category=normalized_correction_reason_category,
                    correction_reason_note=normalized_correction_reason_note,
                    station_context=station_context,
                )
                ok_quantity = counted_quantity
                correction_quantity = 0

            if correction_quantity > 0:
                # Single correction seam (NA40): the kind (DECORAL spin-off child vs RAL in-place
                # replan) is selected and dispatched in one place rather than branched inline here.
                response_stage, response_batch = self._dispatch_packing_correction(
                    work_order,
                    active_batch,
                    tracked_batch=False,
                    ok_quantity=ok_quantity,
                    correction_quantity=correction_quantity,
                    correction_category_fields=correction_category_fields,
                    correction_reason_category=normalized_correction_reason_category,
                    correction_reason_note=normalized_correction_reason_note,
                    packing_state=packing_state,
                    production_state=production_state,
                    station_context=station_context,
                )
                self.resource_locks.release_inactive_resource_locks(work_order)
                self.audit.record_packing_audit_event(
                    work_order=work_order,
                    station_context=station_context,
                    batch_id=active_batch.id,
                    counted_quantity=counted_quantity,
                    ok_quantity=ok_quantity,
                    correction_quantity=correction_quantity,
                    correction_category_fields=correction_category_fields,
                )
                self._commit_process_changes()
                refreshed_work_order = self.get_work_order_process(work_order_id)
                if response_batch is not None:
                    refreshed_batch = self._get_batch(refreshed_work_order, response_batch.id)
                    return self._to_stage_work_order_read(refreshed_work_order, response_stage, batch=refreshed_batch)
                return self._to_stage_work_order_read(refreshed_work_order, ProcessStage.PACKING)
            else:
                packing_state.status = StageStatus.DONE
                packing_state.updated_at = clock.now()
                if work_order.coating_type == CoatingType.RAL:
                    work_order.completed_quantity += ok_quantity
                    active_batch.is_active = False
                elif work_order.is_correction:
                    # Fully-fixed correction child of a DECORAL root: its OK pieces return to the
                    # root's single Decoral pass and the child closes here (no own Decoral).
                    root = self._resolve_root_order(work_order)
                    self._place_returned_pieces_on_root_decoral(root, ok_quantity)
                    self._close_returned_correction_child(work_order)

            # NA42: AUTOMATIC orders have no PRODUCTION stage, so there is nothing to implicitly
            # finish here — the line's output is realized at PACKING completion above.

            if (
                work_order.coating_type == CoatingType.DECORAL
                and correction_quantity == 0
                and not work_order.is_correction
            ):
                active_batch.is_active = True

            self.resource_locks.release_inactive_resource_locks(work_order)
            self.audit.record_packing_audit_event(
                work_order=work_order,
                station_context=station_context,
                batch_id=active_batch.id,
                counted_quantity=counted_quantity,
                ok_quantity=ok_quantity,
                correction_quantity=correction_quantity,
                correction_category_fields=correction_category_fields,
            )

            try:
                self.repository.commit()
            except Exception:
                self.repository.rollback()
                raise

            refreshed_work_order = self.get_work_order_process(work_order_id)
            finalized_work_order = self._finalize_completion_chain_if_ready(refreshed_work_order)
            if finalized_work_order is not None:
                refreshed_work_order = self.get_work_order_process(work_order_id)
            return self._to_idempotent_packing_response(refreshed_work_order)

    # --- Paint runs on the automatic line (CHANGES #22) -------------------------------------------

    PAINT_RUN_RESOURCE_KEY = "PAINT_RUNS"

    def record_paint_run_consumption(
        self,
        paint_run_id: int,
        *,
        consumed_kg: float,
        station_context: StationContext | None = None,
    ) -> PaintRunRead:
        """Enter the paint consumed by a whole run; the kg is split onto its orders by m²."""
        self._ensure_automatic_production_station_action(station_context)
        with self.resource_locks.serialize_resource_mutation(self.PAINT_RUN_RESOURCE_KEY):
            run = self.paint_runs.record_consumption(
                paint_run_id, consumed_kg=consumed_kg, station_context=station_context
            )
            self._commit_process_changes()
            return self._to_paint_run_read(run, latest_run_id=self.paint_service.repository.get_latest_paint_run().id)

    def list_open_paint_runs(self) -> PaintRunsOverviewRead:
        """Runs whose consumption is still missing, oldest first, plus a hint for the current one."""
        open_runs = self.paint_service.repository.list_open_paint_runs()
        latest = self.paint_service.repository.get_latest_paint_run()
        latest_run_id = latest.id if latest is not None else None
        return PaintRunsOverviewRead(
            runs=[self._to_paint_run_read(run, latest_run_id=latest_run_id) for run in open_runs],
        )

    def _next_automatic_order_to_hang(self) -> WorkOrder | None:
        for work_order in self.repository.list_work_orders_with_stage(ProcessStage.HANGING, ProductionType.AUTOMATIC):
            if work_order.queue_position is None:
                continue
            hanging_state = self._find_stage_state(work_order, ProcessStage.HANGING)
            if hanging_state is not None and hanging_state.status == StageStatus.NOT_STARTED:
                return work_order
        return None

    def _to_paint_run_read(self, run, *, latest_run_id: int | None) -> PaintRunRead:
        is_current = run.id == latest_run_id
        hanging_in_progress = any(
            self.paint_runs.member_hanging_status(member) == StageStatus.IN_PROGRESS for member in run.members
        )
        next_in_queue_same_paint = False
        if is_current and run.closed_at is None:
            next_order = self._next_automatic_order_to_hang()
            next_in_queue_same_paint = (
                next_order is not None and paint_identity_of(next_order) == self.paint_runs.identity_of_run(run)
            )
        return PaintRunRead(
            id=run.id,
            ral_code=run.paint.ral_code,
            paint_producer=run.paint.paint_producer,
            paint_code=run.paint.paint_code,
            created_at=run.created_at,
            closed_at=run.closed_at,
            consumed_kg=run.consumed_kg,
            total_area_m2=round(sum(member.area_m2 for member in run.members), 3),
            is_current=is_current,
            hanging_in_progress=hanging_in_progress,
            next_in_queue_same_paint=next_in_queue_same_paint,
            members=[
                PaintRunMemberRead(
                    work_order_id=member.work_order_id,
                    order_number=member.work_order.order_number,
                    customer_name=member.work_order.customer_name,
                    area_m2=member.area_m2,
                    allocated_kg=member.allocated_kg,
                    is_hanging=self.paint_runs.member_hanging_status(member) == StageStatus.IN_PROGRESS,
                )
                for member in run.members
            ],
        )

    def complete_decoral_production(
        self,
        work_order_id: int,
        *,
        ok_quantity: int,
        correction_quantity: int,
        correction_profiles_quantity: int | None = None,
        correction_accessories_quantity: int | None = None,
        correction_reason_category: str | None = None,
        correction_reason_note: str | None = None,
        batch_id: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        with self._serialize_process_mutation(work_order_id):
            work_order = self.get_work_order_process(work_order_id)
            self._ensure_decoral_production_station_action(station_context)
            normalized_reason_category, normalized_reason_note = self._validate_correction_reason(
                correction_quantity,
                correction_reason_category,
                correction_reason_note,
            )
            correction_category_fields = self._validate_correction_category_split(
                correction_quantity,
                correction_profiles_quantity,
                correction_accessories_quantity,
            )

            if work_order.coating_type != CoatingType.DECORAL:
                raise InvalidProcessStageTransitionError("Zakończenie produkcji Decoral dotyczy tylko zleceń DECORAL.")

            target_batch = self._resolve_batch_for_stage(work_order, ProcessStage.DECORAL_PRODUCTION, batch_id)

            if target_batch is not None:
                return self._complete_tracked_batch_decoral_production(
                    work_order,
                    target_batch,
                    ok_quantity=ok_quantity,
                    correction_quantity=correction_quantity,
                    correction_category_fields=correction_category_fields,
                    correction_reason_category=normalized_reason_category,
                    correction_reason_note=normalized_reason_note,
                    station_context=station_context,
                )

            decoral_state = self._get_stage_state(work_order, ProcessStage.DECORAL_PRODUCTION)

            if decoral_state.status == StageStatus.DONE:
                return self._to_stage_work_order_read(work_order, ProcessStage.DECORAL_PRODUCTION)

            if decoral_state.status != StageStatus.IN_PROGRESS:
                raise InvalidProcessStageTransitionError("Produkcję Decoral można zakończyć tylko ze stanu W TRAKCIE.")

            active_batch = work_order.active_batch
            total = ok_quantity + correction_quantity
            if total <= 0:
                raise InvalidProcessStageTransitionError("Łączna ilość musi być większa od zera.")

            if correction_quantity > 0:
                packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)
                packing_state.counted_quantity = None
                packing_state.updated_at = clock.now()
                self._reset_to_correction_planning(
                    work_order,
                    active_batch,
                    ok_quantity=ok_quantity,
                    correction_quantity=correction_quantity,
                    correction_reason_category=normalized_reason_category,
                    correction_reason_note=normalized_reason_note,
                    station_context=station_context,
                    completed_stage=ProcessStage.DECORAL_PRODUCTION,
                )
                self.resource_locks.release_inactive_resource_locks(work_order)
                self.audit.record_decoral_audit_event(
                    work_order=work_order,
                    station_context=station_context,
                    batch_id=None,
                    ok_quantity=ok_quantity,
                    correction_quantity=correction_quantity,
                    correction_category_fields=correction_category_fields,
                )
                self._commit_process_changes()
                refreshed_work_order = self.get_work_order_process(work_order_id)
                return self._to_stage_work_order_read(refreshed_work_order, ProcessStage.DECORAL_PRODUCTION)
            else:
                decoral_state.status = StageStatus.DONE
                decoral_state.updated_at = clock.now()
                work_order.completed_quantity += ok_quantity
                if active_batch is not None:
                    active_batch.is_active = False
                self.resource_locks.release_inactive_resource_locks(work_order)
                self.audit.record_decoral_audit_event(
                    work_order=work_order,
                    station_context=station_context,
                    batch_id=None,
                    ok_quantity=ok_quantity,
                    correction_quantity=correction_quantity,
                    correction_category_fields=correction_category_fields,
                )
                self._commit_process_changes()
                refreshed_work_order = self.get_work_order_process(work_order_id)
                finalized_work_order = self._finalize_completion_chain_if_ready(refreshed_work_order)
                if finalized_work_order is not None:
                    refreshed_work_order = self.get_work_order_process(work_order_id)
                return self._to_stage_work_order_read(refreshed_work_order, ProcessStage.DECORAL_PRODUCTION)

    def _complete_tracked_batch_decoral_production(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        *,
        ok_quantity: int,
        correction_quantity: int,
        correction_category_fields: dict[str, int | bool | None],
        correction_reason_category: str | None,
        correction_reason_note: str | None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        if batch.current_stage == ProcessStage.DECORAL_PRODUCTION and batch.current_stage_status == StageStatus.DONE:
            return self._to_stage_work_order_read(work_order, ProcessStage.DECORAL_PRODUCTION, batch=batch)

        if batch.current_stage != ProcessStage.DECORAL_PRODUCTION or batch.current_stage_status != StageStatus.IN_PROGRESS:
            raise InvalidProcessStageTransitionError("Produkcję Decoral można zakończyć tylko ze stanu W TRAKCIE.")

        total = ok_quantity + correction_quantity
        if total <= 0 or total != batch.quantity:
            raise InvalidProcessStageTransitionError("Ilości muszą być większe od zera i zgodne z ilością partii.")

        if correction_quantity > 0:
            self._reset_to_correction_planning(
                work_order,
                batch,
                ok_quantity=ok_quantity,
                correction_quantity=correction_quantity,
                correction_reason_category=correction_reason_category,
                correction_reason_note=correction_reason_note,
                station_context=station_context,
                completed_stage=ProcessStage.DECORAL_PRODUCTION,
            )
        else:
            batch.current_stage_status = StageStatus.DONE
            batch.is_active = False
            work_order.completed_quantity += ok_quantity

        self.resource_locks.release_inactive_resource_locks(work_order)
        self.audit.record_decoral_audit_event(
            work_order=work_order,
            station_context=station_context,
            batch_id=batch.id,
            ok_quantity=ok_quantity,
            correction_quantity=correction_quantity,
            correction_category_fields=correction_category_fields,
        )
        self._commit_process_changes()
        refreshed_work_order = self.get_work_order_process(work_order.id)
        finalized_work_order = self._finalize_completion_chain_if_ready(refreshed_work_order)
        if finalized_work_order is not None:
            refreshed_work_order = self.get_work_order_process(work_order.id)
        refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
        response_stage = refreshed_batch.current_stage or ProcessStage.DECORAL_PRODUCTION
        return self._to_stage_work_order_read(refreshed_work_order, response_stage, batch=refreshed_batch)

    def list_visible_work_orders(
        self,
        stage: ProcessStage,
        production_type: ProductionType | None = None,
        include_done: bool = False,
        queue_namespace: QueueNamespace | None = None,
    ) -> list[WorkOrder]:
        work_orders = self.repository.list_work_orders_with_stage(stage, production_type, queue_namespace)
        return [
            work_order
            for work_order in work_orders
            if self.is_visible_in_stage(work_order, stage, production_type, include_done=include_done)
        ]

    def is_visible_in_stage(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        production_type: ProductionType | None = None,
        include_done: bool = False,
    ) -> bool:
        if self._has_incomplete_marker(work_order):
            return False

        if not self._is_planned(work_order):
            return False

        if self._is_skipped_surface_preparation(work_order, stage):
            return False

        if self._uses_batch_tracking(work_order):
            if stage == ProcessStage.PRODUCTION and production_type is not None and work_order.production_type != production_type:
                return False
            return bool(self._get_batches_visible_in_stage(work_order, stage, include_done=include_done))

        stage_sequence = self.get_stage_sequence_for_work_order(work_order)
        if stage not in stage_sequence:
            return False

        # AUTOMATIC PRODUCTION is a preview panel with no stage row (NA42); decide it from the line
        # state before touching a stage state that does not exist on this route.
        if self._is_automatic_production_preview_stage(work_order, stage):
            return self._is_visible_in_automatic_production_preview(work_order, production_type)

        stage_state = self._get_stage_state(work_order, stage)
        allowed_statuses = {StageStatus.NOT_STARTED, StageStatus.IN_PROGRESS}
        if include_done:
            allowed_statuses.add(StageStatus.DONE)

        if self._is_visible_in_automatic_packing(work_order, stage, stage_state.status):
            return True

        if stage_state.status not in allowed_statuses:
            return False

        # Walk the ACTUAL route (actionable sequence) so the previous stage is well-defined when the
        # phantom PRODUCTION/HANGING rows are absent — e.g. an automatic PACKING's predecessor is HANGING.
        actionable_sequence = self.get_actionable_stage_sequence_for_work_order(work_order)
        previous_stage = self._get_previous_stage(actionable_sequence, stage)
        if previous_stage is not None:
            previous_state = self._get_stage_state(work_order, previous_stage)
            if previous_state.status != StageStatus.DONE:
                return False

        if stage == ProcessStage.PRODUCTION:
            if production_type is not None and work_order.production_type != production_type:
                return False

        return True

    @staticmethod
    def _is_planned(work_order: WorkOrder) -> bool:
        return work_order.production_type is not None and work_order.queue_position is not None

    def get_display_status(self, work_order: WorkOrder) -> ProcessDisplayStatus:
        if self._has_incomplete_marker(work_order):
            return ProcessDisplayStatus.INCOMPLETE

        if self._is_complete_for_display(work_order):
            return ProcessDisplayStatus.READY

        if not self._is_planned(work_order):
            return ProcessDisplayStatus.TO_BE_PLANNED

        if self._uses_batch_tracking(work_order):
            active_batches = [batch for batch in work_order.active_batches if batch.current_stage is not None]
            if active_batches:
                return self._get_display_status_for_tracked_batches(work_order)

        if self._has_open_corrections(work_order):
            return ProcessDisplayStatus.WAITING_FOR_CORRECTIONS

        if self._uses_batch_tracking(work_order):
            return self._get_display_status_for_tracked_batches(work_order)

        if work_order.production_type == ProductionType.AUTOMATIC:
            packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)
            if packing_state.status == StageStatus.IN_PROGRESS:
                return ProcessDisplayStatus.PACKING

        stage_sequence = self.get_actionable_stage_sequence_for_work_order(work_order)
        for stage in stage_sequence:
            stage_state = self._get_stage_state(work_order, stage)
            if stage_state.status != StageStatus.DONE:
                return self._get_display_status_for_stage(work_order, stage)

        return ProcessDisplayStatus.READY

    def get_waiting_ok_quantity(self, work_order: WorkOrder) -> int:
        if not self._has_open_corrections(work_order):
            return 0

        pending_correction_quantity = self.get_pending_correction_quantity(work_order)
        return max(0, work_order.total_quantity - work_order.completed_quantity - pending_correction_quantity)

    def get_pending_correction_quantity(self, work_order: WorkOrder) -> int:
        pending_quantity = 0
        for correction_order in work_order.correction_orders:
            if self._is_complete_for_display(correction_order):
                continue
            pending_quantity += max(0, correction_order.total_quantity - correction_order.completed_quantity)
        return pending_quantity

    def get_total_progress_quantity(self, work_order: WorkOrder) -> int:
        progress_quantity = work_order.completed_quantity + self.get_waiting_ok_quantity(work_order)
        progress_quantity += sum(correction_order.completed_quantity for correction_order in work_order.correction_orders)
        return min(work_order.total_quantity, progress_quantity)

    def get_display_status_label(self, work_order: WorkOrder) -> str:
        return self.get_display_status(work_order).polish_label

    def get_queue_resource_block(self, work_order: WorkOrder) -> tuple[str, str] | None:
        if (
            self._has_incomplete_marker(work_order)
            or self._is_complete_for_display(work_order)
            or not self._is_planned(work_order)
        ):
            return None
        if work_order.production_type != ProductionType.AUTOMATIC:
            return None

        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
        if hanging_state.status == StageStatus.NOT_STARTED and self._is_stage_ready_for_next_action(
            work_order,
            ProcessStage.HANGING,
        ):
            if self.resource_locks.find_active_hanging_conflict(work_order.id) is not None:
                return "HANGING", self.QUEUE_RESOURCE_BLOCK_REASONS["HANGING"]

        if hanging_state.status == StageStatus.IN_PROGRESS:
            if self.resource_locks.find_active_automatic_line_conflict(work_order.id) is not None:
                return "AUTOMATIC_LINE", self.QUEUE_RESOURCE_BLOCK_REASONS["AUTOMATIC_LINE"]

        return None

    def _is_stage_ready_for_next_action(self, work_order: WorkOrder, stage: ProcessStage) -> bool:
        stage_sequence = self.get_actionable_stage_sequence_for_work_order(work_order)
        previous_stage = self._get_previous_stage(stage_sequence, stage)
        if previous_stage is None:
            return True
        previous_state = self._get_stage_state(work_order, previous_stage)
        return previous_state.status == StageStatus.DONE

    @staticmethod
    def build_stage_status_view(status: StageStatus) -> StageStatusView:
        return StageStatusView(value=status, label=status.polish_label)

    @staticmethod
    def _get_display_status_for_stage(work_order: WorkOrder, stage: ProcessStage) -> ProcessDisplayStatus:
        if stage == ProcessStage.SURFACE_PREPARATION:
            return ProcessDisplayStatus.SURFACE_PREPARATION

        if stage == ProcessStage.HANGING:
            return ProcessDisplayStatus.HANGING

        if stage == ProcessStage.PRODUCTION:
            if work_order.production_type == ProductionType.AUTOMATIC:
                return ProcessDisplayStatus.PRODUCTION_AUTOMATIC
            return ProcessDisplayStatus.PRODUCTION_MANUAL

        if stage == ProcessStage.DECORAL_PRODUCTION:
            return ProcessDisplayStatus.DECORAL_PRODUCTION

        return ProcessDisplayStatus.PACKING

    def _get_display_status_for_tracked_batches(self, work_order: WorkOrder) -> ProcessDisplayStatus:
        active_batches = [batch for batch in work_order.active_batches if batch.current_stage is not None]
        if not active_batches:
            return ProcessDisplayStatus.READY if work_order.completed_quantity == work_order.total_quantity else ProcessDisplayStatus.PACKING

        if any(batch.current_stage == ProcessStage.HANGING for batch in active_batches):
            return ProcessDisplayStatus.HANGING
        if any(batch.current_stage == ProcessStage.PRODUCTION for batch in active_batches):
            return ProcessDisplayStatus.PRODUCTION_MANUAL
        if any(batch.current_stage == ProcessStage.PACKING for batch in active_batches):
            return ProcessDisplayStatus.PACKING
        if any(batch.current_stage == ProcessStage.DECORAL_PRODUCTION for batch in active_batches):
            return ProcessDisplayStatus.DECORAL_PRODUCTION
        return ProcessDisplayStatus.READY

    def _validate_transition(
        self,
        work_order: WorkOrder,
        stage_state: WorkOrderStageState,
        target_status: StageStatus,
    ) -> None:
        stage_sequence = self.get_stage_sequence_for_work_order(work_order)
        if stage_state.stage not in stage_sequence:
            raise InvalidProcessStageTransitionError(
                f"Stage {stage_state.stage.value} is not part of the workflow for work order {work_order.id}."
            )

        if self._is_automatic_production_preview_stage(work_order, stage_state.stage):
            raise InvalidProcessStageTransitionError(self.AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR)

        if self._is_skipped_surface_preparation(work_order, stage_state.stage):
            raise InvalidProcessStageTransitionError(self._get_surface_preparation_skipped_message(work_order))

        # Completion invariant (NA30): a work order that is already complete (READY — all quantity
        # accounted for, no open corrections) must not be sent backwards by re-opening an earlier
        # stage. Without this, a forward transition (e.g. HANGING/PRODUCTION -> IN_PROGRESS) on a
        # fully-packed order would succeed and leave a contradictory state (an earlier stage
        # IN_PROGRESS while the terminal stage is DONE). The legitimate way to re-touch a finished
        # colour is the correction flow, not a raw stage transition. Only guards forward moves;
        # the completing transition itself does not hit this path (complete_packing sets PACKING
        # DONE directly, and DECORAL's finish runs before completion is recorded).
        if target_status in {StageStatus.IN_PROGRESS, StageStatus.DONE} and self._is_complete_for_display(work_order):
            raise InvalidProcessStageTransitionError(
                f"Cannot transition stage {stage_state.stage.value}: work order {work_order.id} is already "
                "completed. Re-opening a finished order requires the correction flow."
            )

        # CHANGES #14: a DONE stage must not be restarted/reset once any downstream stage has
        # progressed. The stage's recorded data is already feeding downstream validation — e.g. a
        # surface-prep restart rewrites the "actual received" count mid-flight and packing then
        # closes the order against the rewritten number (verified 2026-07-11, independent review
        # §1.2). Re-touching a finished stage past this point is the correction flow's job
        # (SPEC §3); a genuinely stuck order has the office/manager administrative reset.
        if stage_state.status == StageStatus.DONE and target_status in {StageStatus.IN_PROGRESS, StageStatus.NOT_STARTED}:
            actionable_sequence = self.get_actionable_stage_sequence_for_work_order(work_order)
            if stage_state.stage in actionable_sequence:
                stage_index = actionable_sequence.index(stage_state.stage)
                for downstream_stage in actionable_sequence[stage_index + 1 :]:
                    downstream_state = self._find_stage_state(work_order, downstream_stage)
                    if downstream_state is not None and downstream_state.status in {StageStatus.IN_PROGRESS, StageStatus.DONE}:
                        raise InvalidProcessStageTransitionError(
                            f"Nie można cofnąć zakończonego etapu {stage_state.stage.polish_label}: "
                            f"etap {downstream_state.stage.polish_label} jest już rozpoczęty lub zakończony. "
                            "Zmiany na tym etapie obsługuje przepływ poprawek lub reset administracyjny (biuro/kierownik)."
                        )

        allowed_transitions = {
            StageStatus.NOT_STARTED: {StageStatus.IN_PROGRESS},
            StageStatus.IN_PROGRESS: {StageStatus.DONE, StageStatus.NOT_STARTED},
            StageStatus.DONE: {StageStatus.IN_PROGRESS, StageStatus.NOT_STARTED},
        }
        current_status = stage_state.status
        if target_status not in allowed_transitions[current_status]:
            raise InvalidProcessStageTransitionError(
                f"Cannot transition stage {stage_state.stage.value} from {current_status.value} to {target_status.value}."
            )

        if target_status in {StageStatus.IN_PROGRESS, StageStatus.DONE}:
            previous_stage = self._get_previous_stage(self.get_actionable_stage_sequence_for_work_order(work_order), stage_state.stage)
            if previous_stage is not None:
                previous_state = self._get_stage_state(work_order, previous_stage)
                if previous_state.status != StageStatus.DONE:
                    raise InvalidProcessStageTransitionError(
                        f"Stage {stage_state.stage.value} requires {previous_stage.value} to be DONE first."
                    )

    def _ensure_stage_station_action(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        station_context: StationContext | None,
    ) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids=self._get_allowed_stage_station_ids(work_order, stage),
            action=f"operacje etapu {stage.value}",
        )

    @staticmethod
    def _ensure_packing_station_action(station_context: StationContext | None) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids={StationId.PACKING},
            action="operacje pakowania",
        )

    @staticmethod
    def _ensure_automatic_production_station_action(station_context: StationContext | None) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids={StationId.AUTOMATIC_PRODUCTION},
            action="operacje produkcji automatycznej",
        )

    @staticmethod
    def _ensure_decoral_production_station_action(station_context: StationContext | None) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids={StationId.DECORAL_PRODUCTION},
            action="operacje produkcji Decoral",
        )

    @classmethod
    def _validate_correction_reason(
        cls,
        correction_quantity: int,
        correction_reason_category: str | None,
        correction_reason_note: str | None,
    ) -> tuple[str | None, str | None]:
        normalized_category = cls._normalize_optional_text(correction_reason_category)
        normalized_note = cls._normalize_optional_text(correction_reason_note)
        if normalized_category is not None and len(normalized_category) > 64:
            raise InvalidProcessStageTransitionError("Kategoria przyczyny poprawki może mieć najwyżej 64 znaki.")
        if normalized_note is not None and len(normalized_note) > 500:
            raise InvalidProcessStageTransitionError("Notatka przyczyny poprawki może mieć najwyżej 500 znaków.")
        if correction_quantity > 0 and normalized_category is None:
            raise InvalidProcessStageTransitionError("Przyczyna poprawki jest wymagana, gdy ilość poprawki jest większa od zera.")
        if correction_quantity == 0 and (normalized_category is not None or normalized_note is not None):
            raise InvalidProcessStageTransitionError("Przyczynę poprawki można podać tylko, gdy ilość poprawki jest większa od zera.")
        return normalized_category, normalized_note

    @staticmethod
    def _validate_correction_category_split(
        correction_quantity: int,
        correction_profiles_quantity: int | None,
        correction_accessories_quantity: int | None,
    ) -> dict[str, int | bool | None]:
        if correction_quantity == 0:
            if correction_profiles_quantity is not None or correction_accessories_quantity is not None:
                raise InvalidProcessStageTransitionError(
                    "Ilości w kategoriach poprawki można podać tylko, gdy ilość poprawki jest większa od zera."
                )
            return {}

        if correction_profiles_quantity is None or correction_accessories_quantity is None:
            raise InvalidProcessStageTransitionError(
                "Ilości profili i akcesoriów w poprawce są wymagane, gdy ilość poprawki jest większa od zera."
            )
        if correction_profiles_quantity < 0 or correction_accessories_quantity < 0:
            raise InvalidProcessStageTransitionError("Ilości w kategoriach poprawki nie mogą być ujemne.")
        if correction_profiles_quantity + correction_accessories_quantity != correction_quantity:
            raise InvalidProcessStageTransitionError(
                "Ilości profili i akcesoriów w poprawce muszą sumować się do ilości poprawki."
            )

        return {
            "profiles_quantity": correction_profiles_quantity,
            "profiles_to_count": False,
            "accessories_quantity": correction_accessories_quantity,
            "accessories_to_count": False,
        }

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized_value = value.strip()
        return normalized_value or None

    @staticmethod
    def _get_allowed_stage_station_ids(work_order: WorkOrder, stage: ProcessStage) -> set[StationId]:
        if stage == ProcessStage.SURFACE_PREPARATION:
            return {StationId.SURFACE_PREPARATION}
        if stage == ProcessStage.HANGING:
            return {StationId.HANGING}
        if stage == ProcessStage.PRODUCTION:
            if work_order.production_type == ProductionType.AUTOMATIC:
                return {StationId.AUTOMATIC_PRODUCTION}
            return {StationId.MANUAL_PRODUCTION}
        if stage == ProcessStage.PACKING:
            return {StationId.PACKING}
        if stage == ProcessStage.DECORAL_PRODUCTION:
            return {StationId.DECORAL_PRODUCTION}
        return {StationId.SYSTEM}

    def get_correction_return_stage(self, work_order: WorkOrder) -> ProcessStage:
        if work_order.production_type == ProductionType.AUTOMATIC:
            return ProcessStage.HANGING

        stage_sequence = self.get_stage_sequence_for_work_order(work_order)
        if self.DEFAULT_CORRECTION_RETURN_STAGE in stage_sequence:
            return self.DEFAULT_CORRECTION_RETURN_STAGE
        return stage_sequence[0]

    def _reset_stage_states_for_active_batch(self, work_order: WorkOrder, return_stage: ProcessStage) -> None:
        stage_sequence = self.get_actionable_stage_sequence_for_work_order(work_order)
        return_stage_index = stage_sequence.index(return_stage)
        current_timestamp = clock.now()

        for index, stage in enumerate(stage_sequence):
            stage_state = self._get_stage_state(work_order, stage)
            stage_state.status = StageStatus.DONE if index < return_stage_index else StageStatus.NOT_STARTED
            stage_state.updated_at = current_timestamp
        # NA42: AUTOMATIC has no PRODUCTION stage row to reset; the actionable sequence above already
        # excludes it.

    def get_actionable_stage_sequence_for_work_order(self, work_order: WorkOrder) -> list[ProcessStage]:
        stage_sequence = self.get_stage_sequence_for_work_order(work_order)
        if work_order.production_type == ProductionType.AUTOMATIC:
            return [stage for stage in stage_sequence if stage != ProcessStage.PRODUCTION]
        return stage_sequence

    @staticmethod
    def _is_automatic_production_preview_stage(work_order: WorkOrder, stage: ProcessStage) -> bool:
        return work_order.production_type == ProductionType.AUTOMATIC and stage == ProcessStage.PRODUCTION

    @staticmethod
    def _skips_surface_preparation(work_order: WorkOrder) -> bool:
        if work_order.is_correction or work_order.work_order_kind == WorkOrderKind.PRZEMALOWANKA:
            return True
        active_batch = work_order.active_batch
        return active_batch is not None and active_batch.parent_batch_id is not None

    @staticmethod
    def _omits_surface_preparation_stage(work_order: WorkOrder) -> bool:
        return work_order.work_order_kind == WorkOrderKind.PRZEMALOWANKA

    def _is_skipped_surface_preparation(self, work_order: WorkOrder, stage: ProcessStage) -> bool:
        return stage == ProcessStage.SURFACE_PREPARATION and self._skips_surface_preparation(work_order)

    @staticmethod
    def _get_surface_preparation_skipped_message(work_order: WorkOrder) -> str:
        if work_order.is_correction:
            return "Zlecenia poprawkowe nie przechodzą przez przygotowanie powierzchni."
        if work_order.work_order_kind == WorkOrderKind.PRZEMALOWANKA:
            return "Przemalowanki nie przechodzą przez przygotowanie powierzchni."
        return "Rundy poprawkowe nie przechodzą przez przygotowanie powierzchni."

    def _is_visible_in_automatic_production_preview(
        self,
        work_order: WorkOrder,
        production_type: ProductionType | None,
    ) -> bool:
        if production_type is not None and work_order.production_type != production_type:
            return False

        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
        packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)

        if packing_state.status == StageStatus.DONE:
            return False

        if hanging_state.status == StageStatus.NOT_STARTED:
            return self._is_stage_ready_for_next_action(work_order, ProcessStage.HANGING)

        # Hanging in progress, or hanging done and the parts are on the line not yet packed (NA42: this
        # last case used to be PRODUCTION==IN_PROGRESS). Packing-done already returned False above.
        return True

    def _get_automatic_production_preview_display_stage(self, work_order: WorkOrder) -> ProcessStage:
        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
        if hanging_state.status != StageStatus.DONE:
            return ProcessStage.HANGING
        return ProcessStage.PRODUCTION

    def _is_visible_in_automatic_packing(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        stage_status: StageStatus,
    ) -> bool:
        if stage != ProcessStage.PACKING or work_order.production_type != ProductionType.AUTOMATIC:
            return False

        if stage_status not in {StageStatus.NOT_STARTED, StageStatus.IN_PROGRESS}:
            return False

        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
        return hanging_state.status in {StageStatus.IN_PROGRESS, StageStatus.DONE}

    def _get_automatic_packing_display_stage(self, work_order: WorkOrder) -> ProcessStage:
        # An automatic order is packable the moment HANGING *starts* (owner policy): the packing
        # station works it in parallel with the line instead of waiting as a read-only row. Packing
        # *completion* stays blocked until HANGING is DONE and paint consumption is recorded — that
        # gate lives in complete_packing and is surfaced to the UI via _packing_completion_block_reason.
        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
        if hanging_state.status in {StageStatus.IN_PROGRESS, StageStatus.DONE}:
            return ProcessStage.PACKING
        return ProcessStage.HANGING

    def _packing_completion_block_reason(self, work_order: WorkOrder) -> str | None:
        """Polish reason why an automatic packing card cannot be *completed* yet, or None.

        Mirrors the guard enforced in ``complete_packing`` (hanging must be DONE) so the packing UI can
        disable "Zakończ pakowanie" with a clear message instead of letting the operator submit and hit
        a server-side rejection. Paint consumption is not a gate — it is entered per paint run
        (CHANGES #22).
        """
        if work_order.production_type != ProductionType.AUTOMATIC:
            return None
        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
        if hanging_state.status != StageStatus.DONE:
            return self.PACKING_COMPLETION_BLOCKED_HANGING_PL
        return None

    def _get_batches_visible_in_stage(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        *,
        include_done: bool,
    ) -> list[WorkOrderQuantityBatch]:
        if not self._uses_batch_tracking(work_order):
            return []

        visible_batches: list[WorkOrderQuantityBatch] = []
        for batch in self._get_ordered_batches(work_order):
            status = self._get_tracked_batch_stage_status(work_order, batch, stage)
            if status is None:
                continue
            if status == StageStatus.DONE and not include_done:
                continue
            if status != StageStatus.DONE and not batch.is_active:
                continue
            visible_batches.append(batch)
        return visible_batches

    def _get_tracked_batch_stage_status(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        stage: ProcessStage,
    ) -> StageStatus | None:
        if batch.current_stage is None:
            return None

        if stage == ProcessStage.PRODUCTION and work_order.production_type == ProductionType.AUTOMATIC:
            if batch.current_stage == ProcessStage.HANGING and batch.current_stage_status in {StageStatus.IN_PROGRESS, StageStatus.DONE}:
                return StageStatus.IN_PROGRESS
            if batch.current_stage == ProcessStage.PACKING and batch.current_stage_status in {StageStatus.NOT_STARTED, StageStatus.IN_PROGRESS}:
                return StageStatus.IN_PROGRESS
            return None

        if stage == ProcessStage.PACKING and work_order.production_type == ProductionType.AUTOMATIC:
            if batch.current_stage == ProcessStage.HANGING:
                return None

        if batch.current_stage != stage:
            return None

        return batch.current_stage_status

    def _resolve_batch_for_stage(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        batch_id: int | None,
    ) -> WorkOrderQuantityBatch | None:
        if batch_id is not None:
            batch = self._get_batch(work_order, batch_id)
            return batch if batch.current_stage is not None else None

        if not self._uses_batch_tracking(work_order):
            return None

        candidate_batches = [batch for batch in work_order.active_batches if batch.current_stage == stage]
        if len(candidate_batches) == 1:
            return candidate_batches[0]
        return None

    def _start_tracked_batch_stage(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        stage: ProcessStage,
        counted_quantity: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        if stage == ProcessStage.PRODUCTION and work_order.production_type == ProductionType.AUTOMATIC:
            raise InvalidProcessStageTransitionError(self.AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR)
        if batch.current_stage != stage or batch.current_stage_status != StageStatus.NOT_STARTED:
            raise InvalidProcessStageTransitionError(
                f"Cannot transition stage {stage.value} from {batch.current_stage_status.value if batch.current_stage_status else 'UNKNOWN'} to IN_PROGRESS."
            )

        self._store_stage_start_data(work_order, stage, counted_quantity)
        self.resource_locks.acquire_stage_resource_locks(work_order, stage, StageStatus.IN_PROGRESS)
        batch.current_stage_status = StageStatus.IN_PROGRESS
        self.audit.record_stage_audit_event(
            work_order=work_order,
            stage=stage,
            target_status=StageStatus.IN_PROGRESS,
            station_context=station_context,
            batch_id=batch.id,
        )
        self._commit_process_changes()
        refreshed_work_order = self.get_work_order_process(work_order.id)
        refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
        return self._to_stage_work_order_read(refreshed_work_order, stage, batch=refreshed_batch)

    def _finish_tracked_batch_stage(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        stage: ProcessStage,
        counted_quantity: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        if stage == ProcessStage.PACKING:
            raise InvalidProcessStageTransitionError(
                "Tracked batch packing must be completed with explicit counted quantity."
            )
        if stage == ProcessStage.PRODUCTION and work_order.production_type == ProductionType.AUTOMATIC:
            raise InvalidProcessStageTransitionError(self.AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR)
        if self._has_tracked_batch_already_finished_stage(work_order, batch, stage):
            response_stage = batch.current_stage or stage
            return self._to_stage_work_order_read(work_order, response_stage, batch=batch)
        if batch.current_stage != stage or batch.current_stage_status != StageStatus.IN_PROGRESS:
            raise InvalidProcessStageTransitionError(
                f"Cannot transition stage {stage.value} from {batch.current_stage_status.value if batch.current_stage_status else 'UNKNOWN'} to DONE."
            )

        if stage == ProcessStage.SURFACE_PREPARATION:
            self._store_surface_preparation_counted_quantity(work_order, counted_quantity)
            self._ensure_surface_preparation_counted_quantity(work_order)

        response_stage = stage
        if stage == ProcessStage.SURFACE_PREPARATION:
            batch.current_stage = ProcessStage.HANGING if work_order.production_type == ProductionType.AUTOMATIC else ProcessStage.PRODUCTION
            batch.current_stage_status = StageStatus.NOT_STARTED
            response_stage = batch.current_stage
        elif stage == ProcessStage.HANGING:
            if work_order.production_type == ProductionType.AUTOMATIC:
                resource_keys = self.resource_locks.get_stage_resource_keys(work_order, stage, StageStatus.DONE)
                with self.resource_locks.serialize_stage_resources(resource_keys):
                    self.resource_locks.ensure_stage_resources_available(work_order, stage, StageStatus.DONE)
                    self.resource_locks.acquire_stage_resource_locks(work_order, stage, StageStatus.DONE)
            batch.current_stage = ProcessStage.PACKING if work_order.production_type == ProductionType.AUTOMATIC else ProcessStage.PRODUCTION
            batch.current_stage_status = (
                StageStatus.IN_PROGRESS if work_order.production_type == ProductionType.AUTOMATIC else StageStatus.NOT_STARTED
            )
            response_stage = batch.current_stage
        elif stage == ProcessStage.PRODUCTION:
            batch.current_stage = ProcessStage.PACKING
            batch.current_stage_status = StageStatus.NOT_STARTED
            response_stage = ProcessStage.PACKING
        elif stage == ProcessStage.DECORAL_PRODUCTION:
            batch.current_stage_status = StageStatus.DONE
            batch.is_active = False
            work_order.completed_quantity += batch.quantity
            self.audit.record_stage_audit_event(
                work_order=work_order,
                stage=stage,
                target_status=StageStatus.DONE,
                station_context=station_context,
                batch_id=batch.id,
            )
            self._commit_process_changes()
            refreshed_work_order = self.get_work_order_process(work_order.id)
            finalized_work_order = self._finalize_completion_chain_if_ready(refreshed_work_order)
            if finalized_work_order is not None:
                refreshed_work_order = self.get_work_order_process(work_order.id)
            refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
            return self._to_stage_work_order_read(refreshed_work_order, stage, batch=refreshed_batch)

        self.resource_locks.release_inactive_resource_locks(work_order)
        self.audit.record_stage_audit_event(
            work_order=work_order,
            stage=stage,
            target_status=StageStatus.DONE,
            station_context=station_context,
            batch_id=batch.id,
        )
        self._commit_process_changes()
        refreshed_work_order = self.get_work_order_process(work_order.id)
        refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
        return self._to_stage_work_order_read(refreshed_work_order, response_stage, batch=refreshed_batch)

    def _reopen_tracked_batch_stage(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        stage: ProcessStage,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        if batch.current_stage != stage or batch.current_stage_status not in {StageStatus.IN_PROGRESS, StageStatus.DONE}:
            raise InvalidProcessStageTransitionError(
                f"Cannot reopen stage {stage.value} from {batch.current_stage_status.value if batch.current_stage_status else 'UNKNOWN'}."
            )

        if batch.current_stage_status == StageStatus.DONE:
            raise InvalidProcessStageTransitionError("Zakończonych śledzonych partii nie można ponownie otworzyć.")

        batch.current_stage_status = StageStatus.NOT_STARTED
        batch.is_active = True
        self.resource_locks.release_inactive_resource_locks(work_order)
        self.audit.record_stage_audit_event(
            work_order=work_order,
            stage=stage,
            target_status=StageStatus.NOT_STARTED,
            station_context=station_context,
            batch_id=batch.id,
        )
        self._commit_process_changes()
        refreshed_work_order = self.get_work_order_process(work_order.id)
        refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
        return self._to_stage_work_order_read(refreshed_work_order, stage, batch=refreshed_batch)

    def _complete_tracked_batch_packing(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        *,
        counted_quantity: int,
        ok_quantity: int,
        correction_quantity: int,
        correction_category_fields: dict[str, int | bool | None],
        correction_reason_category: str | None,
        correction_reason_note: str | None,
        stat_only_correction: bool = False,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        if batch.current_stage == ProcessStage.PACKING and batch.current_stage_status == StageStatus.DONE:
            return self._to_stage_work_order_read(work_order, ProcessStage.PACKING, batch=batch)

        if batch.current_stage != ProcessStage.PACKING or batch.current_stage_status != StageStatus.IN_PROGRESS:
            raise InvalidProcessStageTransitionError("Pakowanie można zakończyć tylko ze stanu W TRAKCIE.")
        if ok_quantity < 0 or correction_quantity < 0:
            raise InvalidProcessStageTransitionError("Ilości pakowania nie mogą być ujemne.")
        if ok_quantity + correction_quantity != counted_quantity:
            raise InvalidProcessStageTransitionError("Ilości pakowania muszą sumować się do policzonej ilości.")

        planned_quantity = batch.quantity
        if counted_quantity != planned_quantity:
            raise InvalidProcessStageTransitionError(
                "Policzona ilość różni się od planowanej. Wyjaśnij brakujące sztuki."
            )

        # Packing-slot exclusivity also covers tracked-batch (DECORAL) packing (capacity-bound at completion).
        self.resource_locks.acquire_packing_slot(work_order, for_completion=True)

        packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)
        packing_state.counted_quantity = counted_quantity
        packing_state.updated_at = clock.now()

        # Stat-only correction (NA34): fixed on the spot — record the statistic and fold the corrected
        # pieces into OK so the batch completes normally (DECORAL continues Decoral; RAL closes).
        if correction_quantity > 0 and self._select_correction_kind(
            work_order, tracked_batch=True, stat_only=stat_only_correction
        ) == CorrectionKind.STAT_ONLY:
            self._record_stat_only_correction(
                work_order,
                correction_quantity=correction_quantity,
                correction_category_fields=correction_category_fields,
                correction_reason_category=correction_reason_category,
                correction_reason_note=correction_reason_note,
                station_context=station_context,
            )
            ok_quantity = counted_quantity
            correction_quantity = 0

        if correction_quantity > 0:
            # Single correction seam (NA40): a tracked-batch packing correction always replans in
            # place today; dispatch keeps the kind selection in one place for NA34's STAT_ONLY.
            self._dispatch_packing_correction(
                work_order,
                batch,
                tracked_batch=True,
                ok_quantity=ok_quantity,
                correction_quantity=correction_quantity,
                correction_category_fields=correction_category_fields,
                correction_reason_category=correction_reason_category,
                correction_reason_note=correction_reason_note,
                station_context=station_context,
            )
        elif work_order.coating_type == CoatingType.DECORAL:
            batch.current_stage = ProcessStage.DECORAL_PRODUCTION
            batch.current_stage_status = StageStatus.NOT_STARTED
            batch.is_partial = False
        else:
            batch.is_active = False
            batch.current_stage = ProcessStage.PACKING
            batch.current_stage_status = StageStatus.DONE
            batch.is_partial = False
            work_order.completed_quantity += ok_quantity

        self.resource_locks.release_inactive_resource_locks(work_order)
        self.audit.record_packing_audit_event(
            work_order=work_order,
            station_context=station_context,
            batch_id=batch.id,
            counted_quantity=counted_quantity,
            ok_quantity=ok_quantity,
            correction_quantity=correction_quantity,
            correction_category_fields=correction_category_fields,
        )
        self._commit_process_changes()

        refreshed_work_order = self.get_work_order_process(work_order.id)
        finalized_work_order = self._finalize_completion_chain_if_ready(refreshed_work_order)
        if finalized_work_order is not None:
            refreshed_work_order = self.get_work_order_process(work_order.id)

        refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
        response_stage = refreshed_batch.current_stage or ProcessStage.PACKING
        return self._to_stage_work_order_read(refreshed_work_order, response_stage, batch=refreshed_batch)

    def prepare_correction_work_order_for_planning(self, work_order: WorkOrder) -> None:
        if not work_order.is_correction and not self._is_in_correction_round(work_order):
            return

        return_stage = self.get_correction_return_stage(work_order)
        self._reset_stage_states_for_active_batch(work_order, return_stage)

    @staticmethod
    def _is_in_correction_round(work_order: WorkOrder) -> bool:
        active_batch = work_order.active_batch
        return active_batch is not None and active_batch.parent_batch_id is not None

    def _select_correction_kind(
        self, work_order: WorkOrder, *, tracked_batch: bool, stat_only: bool = False
    ) -> CorrectionKind:
        """The single decision point for how a packing correction re-enters the workflow (NA40/NA34).

        When the operator marks the correction "fixed on the spot" (od razu poprawiona) it is
        ``STAT_ONLY`` for any order (RAL or DECORAL): logged as a statistic, the order completes as-is,
        nothing returns. Otherwise a DECORAL root being packed on the plain (non-tracked) path spins off
        a child "P" order and keeps its OK pieces on the root's single Decoral pass; every other case
        (RAL, and any tracked-batch packing such as returned Decoral pieces) returns the same order to
        planning with a CORRECTION batch."""
        if stat_only:
            return CorrectionKind.STAT_ONLY
        if not tracked_batch and work_order.coating_type == CoatingType.DECORAL:
            return CorrectionKind.SPIN_OFF_CHILD
        return CorrectionKind.REPLAN_IN_PLACE

    def _record_stat_only_correction(
        self,
        work_order: WorkOrder,
        *,
        correction_quantity: int,
        correction_category_fields: dict[str, int | bool | None],
        correction_reason_category: str | None,
        correction_reason_note: str | None,
        station_context: StationContext | None = None,
    ) -> None:
        """Record a "fixed on the spot" correction as a pure statistic (NA34).

        No CORRECTION batch and no child order: the corrected pieces are good and the order completes
        as-is. Only this stat row (+ an audit event) captures the reason/quantity so the corrections
        report and throughput counters can count it via the shared correction-event source."""
        profiles_quantity = correction_category_fields.get("profiles_quantity") if correction_category_fields else None
        accessories_quantity = (
            correction_category_fields.get("accessories_quantity") if correction_category_fields else None
        )
        self.repository.add_stat_only_correction(
            StatOnlyCorrection(
                work_order_id=work_order.id,
                correction_quantity=correction_quantity,
                correction_reason_category=correction_reason_category,
                correction_reason_note=correction_reason_note,
                correction_profiles_quantity=profiles_quantity,
                correction_accessories_quantity=accessories_quantity,
            )
        )
        self.audit.record_audit_event(
            event_type="work_order.stat_only_correction",
            station_context=station_context,
            work_order=work_order,
            target_type="work_order",
            target_id=work_order.id,
            summary=(
                f"Recorded fixed-on-the-spot correction on {work_order.order_number} "
                f"({correction_quantity} pcs, {correction_reason_category})."
            ),
            details={
                "correction_quantity": correction_quantity,
                "correction_reason_category": correction_reason_category,
                "correction_reason_note": correction_reason_note,
                "correction_profiles_quantity": profiles_quantity,
                "correction_accessories_quantity": accessories_quantity,
            },
        )

    def _dispatch_packing_correction(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        *,
        tracked_batch: bool,
        ok_quantity: int,
        correction_quantity: int,
        correction_category_fields: dict[str, int | bool | None],
        correction_reason_category: str | None,
        correction_reason_note: str | None,
        packing_state: WorkOrderStageState | None = None,
        production_state: WorkOrderStageState | None = None,
        station_context: StationContext | None = None,
    ) -> tuple[ProcessStage, WorkOrderQuantityBatch | None]:
        """The single correction seam (NA40): classify the correction kind, then run its strategy.

        Quantity conservation and reason capture are already validated by the caller; this owns only the
        "which model re-enters the workflow" decision, so a new kind (NA34's STAT_ONLY) is one branch
        here rather than a parallel flow scattered across the packing paths. Returns the
        ``(stage, batch)`` the caller should render."""
        kind = self._select_correction_kind(work_order, tracked_batch=tracked_batch)

        if kind == CorrectionKind.SPIN_OFF_CHILD:
            return self._complete_packing_with_correction_order(
                work_order,
                batch,
                packing_state,
                production_state,
                planned_quantity=batch.quantity,
                ok_quantity=ok_quantity,
                correction_quantity=correction_quantity,
                correction_category_fields=correction_category_fields,
                correction_reason_category=correction_reason_category,
                correction_reason_note=correction_reason_note,
                station_context=station_context,
            )

        # REPLAN_IN_PLACE — the same order returns to planning with a CORRECTION batch. A tracked batch
        # carried partial state, so close it first (the plain RAL path hands its active batch straight to
        # the reset, which closes it there).
        if tracked_batch:
            batch.is_active = False
            batch.current_stage = ProcessStage.PACKING
            batch.current_stage_status = StageStatus.DONE
            batch.is_partial = False
        self._reset_to_correction_planning(
            work_order,
            batch,
            ok_quantity=ok_quantity,
            correction_quantity=correction_quantity,
            correction_reason_category=correction_reason_category,
            correction_reason_note=correction_reason_note,
            station_context=station_context,
        )
        return ProcessStage.PACKING, None

    def _complete_packing_with_correction_order(
        self,
        work_order: WorkOrder,
        active_batch: WorkOrderQuantityBatch,
        packing_state: WorkOrderStageState,
        production_state: WorkOrderStageState | None,
        *,
        planned_quantity: int,
        ok_quantity: int,
        correction_quantity: int,
        correction_category_fields: dict[str, int | bool | None],
        correction_reason_category: str | None,
        correction_reason_note: str | None,
        station_context: StationContext | None = None,
    ) -> tuple[ProcessStage, WorkOrderQuantityBatch | None]:
        # DECORAL packing with a correction. There is exactly ONE Decoral pass, on the ROOT order:
        #  - if the ROOT is being packed, its OK pieces continue on the root's tracked Decoral batch;
        #  - if a correction CHILD is being packed, its OK pieces RETURN to the root's Decoral and the
        #    child closes here (it never does its own Decoral).
        # The bad pieces always become a new correction work order that is a flat child of the ROOT.
        _ = planned_quantity
        response_stage = ProcessStage.PACKING
        response_batch: WorkOrderQuantityBatch | None = None

        packing_state.status = StageStatus.DONE
        packing_state.updated_at = clock.now()
        active_batch.is_active = False
        active_batch.current_stage = ProcessStage.PACKING
        active_batch.current_stage_status = StageStatus.DONE

        root = self._resolve_root_order(work_order)

        if work_order.is_correction:
            if ok_quantity > 0:
                self._place_returned_pieces_on_root_decoral(root, ok_quantity)
            self._close_returned_correction_child(work_order)
        elif ok_quantity > 0:
            response_batch = WorkOrderQuantityBatch(
                work_order_id=work_order.id,
                quantity=ok_quantity,
                type=QuantityBatchType.MAIN,
                parent_batch_id=active_batch.id,
                is_active=True,
                current_stage=ProcessStage.DECORAL_PRODUCTION,
                current_stage_status=StageStatus.NOT_STARTED,
                is_partial=True,
            )
            self.repository.add_quantity_batch(response_batch)
            response_stage = ProcessStage.DECORAL_PRODUCTION

        self._create_correction_work_order(
            root,
            correction_quantity,
            correction_category_fields=correction_category_fields,
            correction_reason_category=correction_reason_category,
            correction_reason_note=correction_reason_note,
            station_context=station_context,
        )

        # NA42: AUTOMATIC orders have no PRODUCTION stage to finish here. (production_state is set only
        # for MANUAL DECORAL orders; it is intentionally unused now and kept for signature stability.)
        _ = production_state

        return response_stage, response_batch

    def _resolve_root_order(self, work_order: WorkOrder) -> WorkOrder:
        root = work_order
        while root.parent_order_id is not None:
            ancestor = self.get_work_order_process(root.parent_order_id)
            if ancestor is None:
                break
            root = ancestor
        return root

    def _place_returned_pieces_on_root_decoral(self, root: WorkOrder, quantity: int) -> None:
        # Corrected pieces re-join the root's single Decoral pass. If the root's Decoral batch is
        # still in progress (operator has not finished it yet) we grow it (scenario 1); otherwise the
        # OK part already finished Decoral, so the returned pieces start a fresh Decoral batch
        # (scenario 2). Only one active batch exists at a time, preserving the one-active invariant.
        ongoing_decoral_batch = next(
            (
                batch
                for batch in root.active_batches
                if batch.current_stage == ProcessStage.DECORAL_PRODUCTION and batch.current_stage_status != StageStatus.DONE
            ),
            None,
        )
        if ongoing_decoral_batch is not None:
            ongoing_decoral_batch.quantity += quantity
        else:
            self.repository.add_quantity_batch(
                WorkOrderQuantityBatch(
                    work_order_id=root.id,
                    quantity=quantity,
                    type=QuantityBatchType.MAIN,
                    parent_batch_id=None,
                    is_active=True,
                    current_stage=ProcessStage.DECORAL_PRODUCTION,
                    current_stage_status=StageStatus.NOT_STARTED,
                    is_partial=True,
                )
            )
            decoral_state = self._get_stage_state(root, ProcessStage.DECORAL_PRODUCTION)
            if decoral_state.status == StageStatus.DONE:
                decoral_state.status = StageStatus.IN_PROGRESS
                decoral_state.updated_at = clock.now()

    def _close_returned_correction_child(self, child: WorkOrder) -> None:
        for batch in list(child.active_batches):
            batch.current_stage = ProcessStage.PACKING
            batch.current_stage_status = StageStatus.DONE
            batch.is_active = False
        child.completed_quantity = child.total_quantity
        self._mark_all_stage_states_done(child)

    def _allocate_correction_order_number(self, parent_work_order: WorkOrder) -> str:
        # Correction orders do not consume the main client work-order sequence. They are numbered
        # relative to the ROOT order: first correction in the tree -> "P{root}", subsequent rounds
        # -> "P{root}-2", "P{root}-3", ... regardless of nesting depth.
        root = parent_work_order
        while root.parent_order_id is not None:
            ancestor = self.repository.session.get(WorkOrder, root.parent_order_id)
            if ancestor is None:
                break
            root = ancestor
        prefix = f"P{root.order_number}"

        existing = (
            self.repository.session.scalar(
                select(func.count(WorkOrder.id)).where(
                    WorkOrder.is_correction.is_(True),
                    or_(WorkOrder.order_number == prefix, WorkOrder.order_number.like(f"{prefix}-%")),
                )
            )
            or 0
        )
        index = existing + 1
        return prefix if index == 1 else f"{prefix}-{index}"

    def _create_correction_work_order(
        self,
        parent_work_order: WorkOrder,
        correction_quantity: int,
        *,
        correction_category_fields: dict[str, int | bool | None],
        correction_reason_category: str | None,
        correction_reason_note: str | None,
        station_context: StationContext | None = None,
    ) -> WorkOrder:
        correction_order = WorkOrder(
            paint_id=parent_work_order.paint_id,
            order_number=self._allocate_correction_order_number(parent_work_order),
            external_order_number=parent_work_order.external_order_number,
            title=parent_work_order.title,
            total_quantity=correction_quantity,
            completed_quantity=0,
            parent_order_id=parent_work_order.id,
            is_correction=True,
            correction_reason_category=correction_reason_category,
            correction_reason_note=correction_reason_note,
            description=parent_work_order.description,
            customer_name=parent_work_order.customer_name,
            ral_code=parent_work_order.ral_code,
            paint_code=parent_work_order.paint_code,
            paint_producer=parent_work_order.paint_producer,
            paint_stock_snapshot_quantity_kg=self.paint_service.lookup_current_stock(
                ral_code=parent_work_order.ral_code,
                paint_producer=parent_work_order.paint_producer,
                paint_code=parent_work_order.paint_code,
            ).current_quantity_kg,
            coating_type=parent_work_order.coating_type,
            work_order_kind=WorkOrderKind.STANDARD,
            is_ocynk=parent_work_order.is_ocynk,
            production_type=None,
            queue_namespace=QueueNamespace.CORRECTIONS,
            queue_position=None,
            received_date=parent_work_order.received_date,
            planned_pickup_date=parent_work_order.planned_pickup_date,
            total_area_m2=parent_work_order.total_area_m2,
            is_incomplete_on_arrival=False,
            **correction_category_fields,
            notes=parent_work_order.notes,
        )
        persisted_correction_order = self.repository.add_work_order(correction_order)
        self.initialize_quantity_tracking(persisted_correction_order)
        self.initialize_stage_states(persisted_correction_order)
        self.audit.record_audit_event(
            event_type="work_order.correction_created",
            station_context=station_context,
            work_order=persisted_correction_order,
            target_type="work_order",
            target_id=persisted_correction_order.id,
            summary=f"Created correction work order {persisted_correction_order.order_number}.",
            details={
                "parent_work_order_id": parent_work_order.id,
                "parent_order_number": parent_work_order.order_number,
                "correction_quantity": correction_quantity,
                "correction_profiles_quantity": correction_category_fields["profiles_quantity"],
                "correction_accessories_quantity": correction_category_fields["accessories_quantity"],
                "correction_reason_category": correction_reason_category,
                "correction_reason_note": correction_reason_note,
            },
        )
        return persisted_correction_order

    def _reset_to_correction_planning(
        self,
        work_order: WorkOrder,
        active_batch: WorkOrderQuantityBatch,
        ok_quantity: int,
        correction_quantity: int,
        correction_reason_category: str | None,
        correction_reason_note: str | None,
        station_context: StationContext | None = None,
        completed_stage: ProcessStage = ProcessStage.PACKING,
    ) -> None:
        work_order.completed_quantity += ok_quantity

        active_batch.is_active = False
        active_batch.current_stage = completed_stage
        active_batch.current_stage_status = StageStatus.DONE

        correction_batch = WorkOrderQuantityBatch(
            work_order_id=work_order.id,
            quantity=correction_quantity,
            type=QuantityBatchType.CORRECTION,
            parent_batch_id=active_batch.id,
            is_active=True,
            current_stage=None,
            current_stage_status=None,
            is_partial=True,
            correction_reason_category=correction_reason_category,
            correction_reason_note=correction_reason_note,
        )
        self.repository.add_quantity_batch(correction_batch)

        work_order.correction_reason_category = correction_reason_category
        work_order.correction_reason_note = correction_reason_note

        current_timestamp = clock.now()
        for stage_state in work_order.stage_states:
            if stage_state.stage == ProcessStage.SURFACE_PREPARATION:
                stage_state.status = StageStatus.DONE
            elif stage_state.stage == ProcessStage.PACKING:
                stage_state.status = StageStatus.NOT_STARTED
                stage_state.counted_quantity = None
            else:
                stage_state.status = StageStatus.NOT_STARTED
            stage_state.updated_at = current_timestamp

        work_order.production_type = None
        work_order.queue_position = None
        # Leaving the queue clears the live planning lock (the slot is gone), but we REMEMBER the
        # manager's pin/urgent intent (CHANGES #1) so re-planning this order after the correction round
        # restores it instead of silently dropping it.
        if work_order.planning_priority is not None:
            work_order.pending_planning_priority = work_order.planning_priority
        work_order.planning_priority = None

        self.audit.record_audit_event(
            event_type="work_order.returned_to_correction_planning",
            station_context=station_context,
            work_order=work_order,
            target_type="work_order",
            target_id=work_order.id,
            summary=f"Returned work order {work_order.order_number} to planning for correction ({correction_quantity} pcs, {ok_quantity} ok so far).",
            details={
                "ok_quantity": ok_quantity,
                "correction_quantity": correction_quantity,
                "accumulated_completed_quantity": work_order.completed_quantity,
                "total_quantity": work_order.total_quantity,
                "correction_reason_category": correction_reason_category,
            },
        )

    @staticmethod
    def _persisted_category_fields(work_order: WorkOrder) -> dict[str, int | bool | None]:
        return {
            "profiles_quantity": work_order.profiles_quantity,
            "profiles_to_count": work_order.profiles_to_count,
            "accessories_quantity": work_order.accessories_quantity,
            "accessories_to_count": work_order.accessories_to_count,
        }

    @staticmethod
    def _unknown_category_fields(work_order: WorkOrder) -> dict[str, int | bool | None]:
        profiles_known_absent = work_order.profiles_quantity == 0 and not work_order.profiles_to_count
        accessories_known_absent = work_order.accessories_quantity == 0 and not work_order.accessories_to_count
        return {
            "profiles_quantity": 0 if profiles_known_absent else None,
            "profiles_to_count": False if profiles_known_absent else True,
            "accessories_quantity": 0 if accessories_known_absent else None,
            "accessories_to_count": False if accessories_known_absent else True,
        }

    @staticmethod
    def _derive_category_fields_for_operational_quantity(
        work_order: WorkOrder,
        operational_quantity: int,
    ) -> dict[str, int | bool | None]:
        if operational_quantity == work_order.total_quantity:
            return ProcessService._persisted_category_fields(work_order)

        profiles_known = not work_order.profiles_to_count and work_order.profiles_quantity is not None
        accessories_known = not work_order.accessories_to_count and work_order.accessories_quantity is not None
        if profiles_known and accessories_known:
            if work_order.profiles_quantity == 0:
                return {
                    "profiles_quantity": 0,
                    "profiles_to_count": False,
                    "accessories_quantity": operational_quantity,
                    "accessories_to_count": False,
                }
            if work_order.accessories_quantity == 0:
                return {
                    "profiles_quantity": operational_quantity,
                    "profiles_to_count": False,
                    "accessories_quantity": 0,
                    "accessories_to_count": False,
                }

        return ProcessService._unknown_category_fields(work_order)

    @staticmethod
    def _uses_batch_tracking(work_order: WorkOrder) -> bool:
        return any(batch.current_stage is not None for batch in work_order.active_batches)

    @staticmethod
    def _get_batch(work_order: WorkOrder, batch_id: int) -> WorkOrderQuantityBatch:
        for batch in work_order.quantity_batches:
            if batch.id == batch_id:
                return batch
        raise InvalidProcessStageTransitionError(f"Batch {batch_id} is not configured for work order {work_order.id}.")

    @staticmethod
    def _get_ordered_batches(work_order: WorkOrder) -> list[WorkOrderQuantityBatch]:
        return sorted(work_order.quantity_batches, key=lambda batch: (batch.created_at, batch.id))

    def _commit_process_changes(self) -> None:
        try:
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

    def _finalize_completion_chain_if_ready(self, work_order: WorkOrder) -> WorkOrder | None:
        current_work_order: WorkOrder | None
        if work_order.is_correction and work_order.parent_order_id is not None:
            current_work_order = self.repository.get_work_order_with_stage_states(work_order.parent_order_id)
        else:
            current_work_order = work_order

        finalized_work_order: WorkOrder | None = None
        while current_work_order is not None:
            if not self._can_finalize_work_order(current_work_order):
                break

            # CHANGES #12 (owner decision D5, DECISIONS.md 2026-07-11): when the quantity gap is a
            # settled intake undercount (prep counted 3 of the ordered 5 and all 3 are credited),
            # the order is REDEFINED to the counted amount — it becomes a 3-piece order — with the
            # original ordered quantity preserved in an audit event (ordered-vs-arrived lives in
            # the audit trail, not on the order). This must run BEFORE the leak tripwire below:
            # a redefined order has no gap left, so the legitimate undercount is never
            # false-flagged as a leak.
            if self._is_settled_intake_undercount(current_work_order):
                ordered_quantity = current_work_order.total_quantity
                arrived_quantity = current_work_order.completed_quantity
                ordered_profiles_quantity = current_work_order.profiles_quantity
                ordered_accessories_quantity = current_work_order.accessories_quantity
                # The declared profile/accessory split must be redefined WITH the total — the DB
                # CHECK (profiles + accessories == total when both known) otherwise kills this
                # commit and strands the order half-finalized (verified live 2026-07-11 on a
                # 10-profile order counted at 8). Same policy as the read model / correction
                # batches: a single-category order keeps its category, a mixed one falls back to
                # "to count". Derive BEFORE mutating total_quantity (the helper short-circuits
                # on operational == total).
                category_fields = self._derive_category_fields_for_operational_quantity(
                    current_work_order,
                    arrived_quantity,
                )
                current_work_order.total_quantity = arrived_quantity
                for category_field_name, category_field_value in category_fields.items():
                    setattr(current_work_order, category_field_name, category_field_value)
                self.audit.record_audit_event(
                    event_type="work_order.total_quantity_redefined",
                    station_context=None,
                    work_order=current_work_order,
                    target_type="work_order",
                    target_id=current_work_order.id,
                    summary=(
                        f"Intake undercount on work order {current_work_order.order_number}: "
                        f"ordered {ordered_quantity}, arrived {arrived_quantity} — "
                        f"order redefined to the counted amount (D5)."
                    ),
                    details={
                        "ordered_quantity": ordered_quantity,
                        "arrived_quantity": arrived_quantity,
                        "ordered_profiles_quantity": ordered_profiles_quantity,
                        "ordered_accessories_quantity": ordered_accessories_quantity,
                    },
                )

            # Quantity conservation should already make these equal; if not, finalizing would mask a
            # leak — surface it (NA19, CHANGES #10) rather than silently overwriting. We still force the
            # total so the order can close, but we flag it on the order AND write an audit event so a
            # human sees it (a silent log line nobody reads is not "surfaced").
            if current_work_order.completed_quantity != current_work_order.total_quantity:
                gap_before = current_work_order.completed_quantity
                logger.warning(
                    "Finalizing work order %s with a quantity gap: completed=%s total=%s (forcing to total).",
                    current_work_order.order_number,
                    gap_before,
                    current_work_order.total_quantity,
                )
                current_work_order.quantity_leak_flagged = True
                self.audit.record_audit_event(
                    event_type="work_order.quantity_leak_detected",
                    station_context=None,
                    work_order=current_work_order,
                    target_type="work_order",
                    target_id=current_work_order.id,
                    summary=(
                        f"Quantity leak on work order {current_work_order.order_number}: "
                        f"credited {gap_before} of {current_work_order.total_quantity} at close (forced to total)."
                    ),
                    details={
                        "completed_quantity": gap_before,
                        "total_quantity": current_work_order.total_quantity,
                    },
                )
            current_work_order.completed_quantity = current_work_order.total_quantity
            self._mark_all_stage_states_done(current_work_order)
            # CHANGES #3: a completed order leaves the line's active queue — release its queue position
            # (and any planning lock; the slot is gone) but KEEP the line it ran on, so throughput stats
            # that split by line still work. "Planned" = has a position, so this drops it out of the
            # planning queue without losing the line. Finalizing an order means its whole correction
            # subtree is complete, so release the completed children's slots too — a correction child
            # completes by merging back into the parent (which calls finalize on the PARENT), so the
            # child would otherwise keep its position despite being a closed historical correction.
            self.release_queue_slot(current_work_order)
            for descendant in self._completed_correction_descendants(current_work_order):
                self.release_queue_slot(descendant)
            finalized_work_order = current_work_order

            if not current_work_order.is_correction or current_work_order.parent_order_id is None:
                break

            current_work_order = self.repository.get_work_order_with_stage_states(current_work_order.parent_order_id)

        if finalized_work_order is None:
            return None

        self._commit_process_changes()
        return finalized_work_order

    @staticmethod
    def release_queue_slot(work_order: WorkOrder) -> None:
        """Drop an order out of the active queue (CHANGES #3): release its position + any planning lock,
        keeping the line it ran on. Idempotent. Public: the manager's availability check also uses it
        to self-heal a legacy zombie (a READY order still holding a position, written before the
        CHANGES #12 fix)."""
        work_order.queue_position = None
        work_order.planning_priority = None
        work_order.pending_planning_priority = None

    def _completed_correction_descendants(self, work_order: WorkOrder) -> list[WorkOrder]:
        """All correction descendants (recursively) that are complete-for-display — closed historical
        corrections that should also leave the queue when their root finalizes."""
        descendants: list[WorkOrder] = []
        for child in work_order.correction_orders:
            if self._is_complete_for_display(child):
                descendants.append(child)
            descendants.extend(self._completed_correction_descendants(child))
        return descendants

    def _can_finalize_work_order(self, work_order: WorkOrder) -> bool:
        if self._has_open_corrections(work_order):
            return False

        if work_order.current_active_quantity != 0:
            return False

        if work_order.completed_quantity == work_order.total_quantity:
            return True

        # CHANGES #12 (owner decision D5, DECISIONS.md 2026-07-11): an intake undercount is a
        # legitimate completion — fewer pieces arrived than ordered, and every piece that DID
        # arrive (the surface-prep count) has been credited. Without this arm the order shows
        # "Gotowe" via the all-stages-DONE display fall-through but never finalizes, holding its
        # queue slot forever.
        if self._is_settled_intake_undercount(work_order):
            return True

        return bool(work_order.correction_orders)

    def _is_settled_intake_undercount(self, work_order: WorkOrder) -> bool:
        """True when the order's only quantity gap is the intake undercount: surface prep counted
        fewer pieces than ordered and exactly that counted amount has been credited. This is the
        owner-blessed path (DECISIONS.md 2026-06-30 + D5 2026-07-11) — NOT a leak."""
        counted_quantity = self.get_surface_preparation_counted_quantity(work_order)
        return (
            counted_quantity is not None
            and counted_quantity < work_order.total_quantity
            and work_order.completed_quantity == counted_quantity
        )

    def _mark_all_stage_states_done(self, work_order: WorkOrder) -> None:
        current_timestamp = clock.now()
        for stage_state in work_order.stage_states:
            stage_state.status = StageStatus.DONE
            stage_state.updated_at = current_timestamp

    def _has_open_corrections(self, work_order: WorkOrder) -> bool:
        return any(not self._is_complete_for_display(correction_order) for correction_order in work_order.correction_orders)

    @staticmethod
    def _has_incomplete_marker(work_order: WorkOrder) -> bool:
        return work_order.is_incomplete_on_arrival

    def _is_complete_for_display(self, work_order: WorkOrder) -> bool:
        return (
            work_order.completed_quantity == work_order.total_quantity
            and work_order.current_active_quantity == 0
            and not any(not self._is_complete_for_display(correction_order) for correction_order in work_order.correction_orders)
        )

    def is_historical_correction(self, work_order: WorkOrder) -> bool:
        return work_order.is_correction and self._is_complete_for_display(work_order)

    def is_decoral_incomplete(self, work_order: WorkOrder) -> bool:
        # "N" marker: a DECORAL order that still has open correction children. Its OK pieces can be
        # worked on Decoral, but the order cannot be closed until the corrected pieces return.
        return (
            work_order.coating_type == CoatingType.DECORAL
            and not work_order.is_correction
            and self._has_open_corrections(work_order)
        )

    def _store_stage_start_data(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        counted_quantity: int | None,
    ) -> None:
        if stage != ProcessStage.SURFACE_PREPARATION:
            return

        if counted_quantity is None:
            return

        self._store_surface_preparation_counted_quantity(work_order, counted_quantity)

    def _store_surface_preparation_counted_quantity(
        self,
        work_order: WorkOrder,
        counted_quantity: int | None,
    ) -> None:
        if counted_quantity is None:
            return

        if counted_quantity <= 0:
            raise InvalidProcessStageTransitionError("Policzona ilość musi być większa od zera.")

        if counted_quantity > work_order.current_active_quantity:
            raise InvalidProcessStageTransitionError("Policzona ilość nie może przekraczać oczekiwanej aktywnej ilości.")

        stage_state = self._get_stage_state(work_order, ProcessStage.SURFACE_PREPARATION)
        stage_state.counted_quantity = counted_quantity
        stage_state.updated_at = clock.now()

    def _ensure_surface_preparation_counted_quantity(self, work_order: WorkOrder) -> None:
        stage_state = self._get_stage_state(work_order, ProcessStage.SURFACE_PREPARATION)
        if stage_state.counted_quantity is None:
            raise InvalidProcessStageTransitionError("Policzona ilość jest wymagana, aby zakończyć przygotowanie powierzchni.")

    @staticmethod
    def _get_previous_stage(
        stage_sequence: Sequence[ProcessStage],
        stage: ProcessStage,
    ) -> ProcessStage | None:
        stage_index = stage_sequence.index(stage)
        if stage_index == 0:
            return None
        return stage_sequence[stage_index - 1]

    @staticmethod
    def _get_stage_state(work_order: WorkOrder, stage: ProcessStage) -> WorkOrderStageState:
        for stage_state in work_order.stage_states:
            if stage_state.stage == stage:
                return stage_state
        raise InvalidProcessStageTransitionError(f"Stage {stage.value} is not configured for work order {work_order.id}.")

    @staticmethod
    def _find_stage_state(work_order: WorkOrder, stage: ProcessStage) -> WorkOrderStageState | None:
        # Like _get_stage_state but returns None instead of raising when the stage is not part of the
        # order's route (NA42: AUTOMATIC has no PRODUCTION row, MANUAL has no HANGING row).
        return next((stage_state for stage_state in work_order.stage_states if stage_state.stage == stage), None)

    def _to_stage_work_order_read(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        batch: WorkOrderQuantityBatch | None = None,
    ) -> ProcessStageWorkOrderRead:
        if batch is None and self._is_automatic_production_preview_stage(work_order, stage):
            stage = self._get_automatic_production_preview_display_stage(work_order)
        elif batch is None and stage == ProcessStage.PACKING and work_order.production_type == ProductionType.AUTOMATIC:
            stage = self._get_automatic_packing_display_stage(work_order)

        stage_state = self._find_stage_state(work_order, stage)
        if stage_state is None:
            # NA42: an AUTOMATIC order has no PRODUCTION stage row, but the automatic-production panel
            # still presents it as "in production" once it is on the line (display unchanged for the
            # operator). Synthesize a transient stage state mirroring the old phantom: IN_PROGRESS
            # while on the line (hanging done, not yet packed), else DONE.
            synthetic_status = (
                StageStatus.DONE
                if self._get_stage_state(work_order, ProcessStage.PACKING).status == StageStatus.DONE
                else StageStatus.IN_PROGRESS
            )
            stage_state = WorkOrderStageState(work_order_id=work_order.id, stage=stage, status=synthetic_status)
        if batch is None:
            current_active_quantity = work_order.current_active_quantity
            batch_type = None
            batch_is_partial = False
            batch_id = None
            stage_status = self.build_stage_status_view(stage_state.status)
        else:
            batch_status = self._get_tracked_batch_stage_status(work_order, batch, stage)
            if batch_status is None:
                batch_status = batch.current_stage_status or StageStatus.NOT_STARTED
            current_active_quantity = batch.quantity
            batch_type = batch.type
            batch_is_partial = batch.is_partial
            batch_id = batch.id
            stage_status = self.build_stage_status_view(batch_status)

        quantities = self._resolve_stage_quantities(work_order, stage, stage_state, batch=batch)
        batch_quantity = quantities.display
        planned_quantity = quantities.planned
        counted_quantity = quantities.counted
        operational_quantity = quantities.operational
        quantity_difference = counted_quantity - planned_quantity if counted_quantity is not None else None

        category_fields = self._derive_category_fields_for_operational_quantity(
            work_order,
            operational_quantity,
        )
        current_paint_stock_quantity_kg = self.paint_service.lookup_current_stock(
            ral_code=work_order.ral_code,
            paint_producer=work_order.paint_producer,
            paint_code=work_order.paint_code,
        ).current_quantity_kg

        # Packing occupancy (NA22): a work order "holds a slot" if it owns any PACKING:i lock — this
        # includes an automatic order that reserved a slot at hanging start but has not reached packing
        # yet. `is_being_packed` (show the packing form) additionally requires the resolved stage to be
        # PACKING. `packing_slots_total` is the configured capacity N.
        holds_packing_slot = self.resource_locks.work_order_packing_slot_key(work_order.id) is not None
        is_being_packed = holds_packing_slot and stage == ProcessStage.PACKING
        packing_slots_total = self.resource_locks.packing_slot_count()

        # Whether "Zakończ pakowanie" is allowed for this card (automatic orders pack in parallel with
        # the line but can only finish once HANGING is DONE and paint consumption is recorded).
        packing_blocked_reason: str | None = None
        if stage == ProcessStage.PACKING and stage_status.value != StageStatus.DONE:
            packing_blocked_reason = self._packing_completion_block_reason(work_order)

        return ProcessStageWorkOrderRead(
            id=work_order.id,
            batch_id=batch_id,
            is_correction=work_order.is_correction,
            is_correction_round=self._is_in_correction_round(work_order),
            completed_quantity=work_order.completed_quantity,
            is_historical_correction=self.is_historical_correction(work_order),
            is_decoral_incomplete=self.is_decoral_incomplete(work_order),
            work_order_kind=build_work_order_kind_view(work_order.work_order_kind),
            is_ocynk=work_order.is_ocynk,
            order_number=work_order.order_number,
            title=work_order.title,
            ral_code=work_order.ral_code,
            paint_code=work_order.paint_code,
            paint_producer=work_order.paint_producer,
            current_paint_stock_quantity_kg=current_paint_stock_quantity_kg,
            paint_stock_snapshot_quantity_kg=work_order.paint_stock_snapshot_quantity_kg,
            consumed_paint_quantity_kg=self.paint_service.get_consumed_paint_kg_for_work_orders(work_order.correction_chain_ids),
            total_area_m2=work_order.total_area_m2,
            total_quantity=work_order.total_quantity,
            current_active_quantity=current_active_quantity,
            operational_quantity=operational_quantity,
            batch_quantity=batch_quantity,
            planned_quantity=planned_quantity,
            counted_quantity=counted_quantity,
            quantity_difference=quantity_difference,
            customer_name=work_order.customer_name,
            **category_fields,
            queue_position=work_order.queue_position,
            queue_namespace=build_queue_namespace_view(work_order.queue_namespace),
            production_type=(
                build_production_type_view(work_order.production_type)
                if work_order.production_type is not None
                else None
            ),
            coating_type=build_coating_type_view(work_order.coating_type),
            decoral_foil=(
                FoilSummaryRead(id=work_order.decoral_foil.id, name=work_order.decoral_foil.name, code=work_order.decoral_foil.code)
                if work_order.decoral_foil is not None
                else None
            ),
            technical_drawings=[
                WorkOrderAttachmentSummaryRead(
                    id=attachment.id,
                    original_filename=attachment.original_filename,
                    content_type=attachment.content_type,
                )
                for attachment in work_order.attachments
                if attachment.category == WorkOrderAttachmentCategory.TECHNICAL_DRAWING.value
            ],
            batch_type=batch_type,
            batch_is_partial=batch_is_partial,
            is_being_packed=is_being_packed,
            holds_packing_slot=holds_packing_slot,
            packing_slots_total=packing_slots_total,
            can_complete_packing=packing_blocked_reason is None,
            packing_blocked_reason=packing_blocked_reason,
            stage_status=ProcessStageStatusRead(
                stage=stage,
                status=stage_status,
            ),
        )

    def _resolve_stage_quantities(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        stage_state: WorkOrderStageState,
        *,
        batch: WorkOrderQuantityBatch | None,
    ) -> StageQuantities:
        """Single source of the per-stage display quantities (NA43).

        Folds the four former helpers (display / planned / counted / operational) into one place so
        the "which quantity shows where" rule lives once. **Display-only** — validation, READY, and
        quantity conservation use ``total_quantity`` / counted directly, never these. See
        ``docs/SPEC.md`` §4 (Quantities & counting).
        """
        active_batch = work_order.active_batch
        # Surface-prep actual received (NA26) feeds both `operational` and the PACKING `counted`
        # fallback; computed once here (it is a pure function of the work order).
        surface_prep_actual = self._get_surface_preparation_actual_quantity(work_order)

        # display: a tracked batch shows its own size; a finished stage shows the full order;
        # otherwise the live active quantity.
        if batch is not None:
            display: int | None = batch.quantity
        elif stage_state.status == StageStatus.DONE:
            display = work_order.total_quantity
        else:
            display = work_order.current_active_quantity

        # planned (expected for the stage): a tracked batch — or a correction batch (an active batch
        # with a parent) — shows that batch's size; otherwise the ordered total.
        if batch is not None:
            planned = batch.quantity
        elif active_batch is not None and active_batch.parent_batch_id is not None:
            planned = active_batch.quantity
        else:
            planned = work_order.total_quantity

        # operational (NA26): pieces the operator physically handles — a tracked batch's own quantity,
        # else the surface-prep actual received once counted, else the ordered total before counting.
        if batch is not None:
            operational = batch.quantity
        elif surface_prep_actual is not None:
            operational = surface_prep_actual
        else:
            operational = work_order.current_active_quantity

        # counted: only SURFACE_PREPARATION and PACKING carry a counted quantity (both rows exist on
        # every route, incl. the now-absent AUTOMATIC PRODUCTION — NA42). PACKING falls back to the
        # surface-prep actual only on the plain (non-batch, non-correction) path.
        counted: int | None
        if stage not in (ProcessStage.SURFACE_PREPARATION, ProcessStage.PACKING):
            counted = None
        elif stage == ProcessStage.SURFACE_PREPARATION:
            counted = self._get_stage_state(work_order, ProcessStage.SURFACE_PREPARATION).counted_quantity
        else:
            packing_counted = self._get_stage_state(work_order, ProcessStage.PACKING).counted_quantity
            if packing_counted is not None:
                counted = packing_counted
            elif batch is None and not self._is_in_correction_round(work_order):
                counted = surface_prep_actual
            else:
                counted = None

        return StageQuantities(display=display, planned=planned, counted=counted, operational=operational)

    @staticmethod
    def _get_process_mutation_lock(work_order_id: int) -> RLock:
        with _PROCESS_MUTATION_LOCKS_GUARD:
            lock = _PROCESS_MUTATION_LOCKS.get(work_order_id)
            if lock is None:
                lock = RLock()
                _PROCESS_MUTATION_LOCKS[work_order_id] = lock
            return lock

    def _get_surface_preparation_actual_quantity(self, work_order: WorkOrder) -> int | None:
        if self._skips_surface_preparation(work_order):
            return None

        surface_preparation_state = self._get_stage_state(work_order, ProcessStage.SURFACE_PREPARATION)
        return surface_preparation_state.counted_quantity


    @contextmanager
    def _serialize_process_mutation(self, work_order_id: int):
        lock = self._get_process_mutation_lock(work_order_id)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    def _to_idempotent_packing_response(self, work_order: WorkOrder) -> ProcessStageWorkOrderRead:
        if self._is_in_correction_round(work_order):
            return self._to_stage_work_order_read(work_order, ProcessStage.PACKING)
        return_stage = ProcessStage.DECORAL_PRODUCTION if work_order.coating_type == CoatingType.DECORAL else ProcessStage.PACKING
        return self._to_stage_work_order_read(work_order, return_stage)

    def _has_tracked_batch_already_finished_stage(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        stage: ProcessStage,
    ) -> bool:
        if batch.current_stage == stage and batch.current_stage_status == StageStatus.DONE:
            return True

        if batch.current_stage is None:
            return False

        stage_sequence = self.get_actionable_stage_sequence_for_work_order(work_order)
        if stage not in stage_sequence or batch.current_stage not in stage_sequence:
            return False

        return stage_sequence.index(batch.current_stage) > stage_sequence.index(stage)

"""Paint runs on the automatic line (CHANGES #22).

Automatic paint consumption is entered **once per run of consecutively hung orders sharing one
paint**, not per order: the operator cannot weigh paint per order because cartons are not swapped
between orders of the same paint (owner, 2026-10-09). The entered kg is split onto the member orders
by painted m².

Rules (owner-confirmed 2026-10-09):

* An order **joins** a run when its HANGING starts on the automatic line: it joins the newest run if
  that run is still open and has the same paint (RAL + producer + paint code); otherwise it opens a new
  run. A paint change in the queue therefore ends a run; a closed run is never re-opened — the same
  paint after a closed run starts a new run.
* Correction rounds / correction children are ordinary members — they join whatever run is current.
* Consumption is entered after the run's orders finished hanging. Entry is write-once, like before; a
  mistake is fixed by an office stock adjustment. An open run is **flagged** (automatic-line and
  manager screens) until someone enters it.
* CHANGES #23 (owner, 2026-10-09): only the **last** order of an open run waits — when its packing is
  submitted it is parked (not completed) until the run's consumption is entered, then the system
  completes it with the operator's numbers. Every other order packs freely, and the parked order frees
  the packing station and the automatic line, so the floor keeps moving.
* Undoing a hanging start (IN_PROGRESS → NOT_STARTED) takes the order back out of its still-open run.

Kept DB-light and separate from ``ProcessService`` (same pattern as ``ResourceLockManager``) so the
run rules live in one place.
"""

from dataclasses import dataclass
import json

from app.audit.context import StationContext
from app.paints.models import Paint, PaintRun, PaintRunMember
from app.paints.repository import PaintRepository
from app.paints.service import PaintService
from app.process.audit_writer import ProcessAuditWriter
from app.process.enums import ProcessStage, StageStatus
from app.shared import clock
from app.shared.exceptions import InvalidPaintInventoryError, InvalidProcessStageTransitionError
from app.work_orders.models import WorkOrder


PAINT_CODE_MISSING_ERROR = "Zlecenie nie ma kodu farby — uzupełnij go w biurze, zanim zaczniesz zawieszanie na automacie."
RUN_NOT_FOUND_ERROR = "Nie znaleziono tej grupy farby."
RUN_ALREADY_RECORDED_ERROR = (
    "Zużycie farby dla tej grupy jest już zapisane i nie można go edytować. Jeśli potrzebna jest korekta, "
    "wykonaj ręczną korektę stanu magazynu w biurze."
)
RUN_HANGING_IN_PROGRESS_ERROR = "Najpierw zakończ zawieszanie wszystkich zleceń z tej grupy, potem wpisz zużycie farby."


def packing_parked_message(run: PaintRun) -> str:
    paint = run.paint
    return (
        f"Spakowane — ostatnie zlecenie grupy farby {paint.ral_code} ({paint.paint_producer}, "
        f"{paint.paint_code}). Zamknie się samo, gdy Produkcja automat wpisze zużycie farby całej grupy."
    )
_ALLOCATION_DECIMALS = 3


@dataclass(frozen=True)
class PaintIdentity:
    ral_code: str
    paint_producer: str
    paint_code: str


def paint_identity_of(work_order: WorkOrder) -> PaintIdentity | None:
    """The paint an order is painted with, or None when its paint code is missing."""
    if not work_order.paint_code:
        return None
    return PaintIdentity(work_order.ral_code, work_order.paint_producer, work_order.paint_code)


def _stage_status(work_order: WorkOrder, stage: ProcessStage) -> StageStatus | None:
    for stage_state in work_order.stage_states:
        if stage_state.stage == stage:
            return stage_state.status
    return None


def _is_in_flow(work_order: WorkOrder) -> bool:
    """Hanging started and packing not done — the order's pieces are on their way through the line.
    (A member whose packing is parked counts as packed — see ``holding_run_for``.)"""
    return (
        _stage_status(work_order, ProcessStage.HANGING) in {StageStatus.IN_PROGRESS, StageStatus.DONE}
        and _stage_status(work_order, ProcessStage.PACKING) != StageStatus.DONE
    )


def _is_between_hanging_done_and_packed(work_order: WorkOrder) -> bool:
    return (
        _stage_status(work_order, ProcessStage.HANGING) == StageStatus.DONE
        and _stage_status(work_order, ProcessStage.PACKING) != StageStatus.DONE
    )


def _identity_of_paint(paint: Paint) -> PaintIdentity:
    return PaintIdentity(paint.ral_code, paint.paint_producer, paint.paint_code)


def allocate_by_area(consumed_kg: float, areas: list[float]) -> list[float]:
    """Split ``consumed_kg`` over members proportionally to their m² (owner: "wg m²").

    Shares are rounded to grams; the last member takes the unrounded remainder so the shares sum to the
    entered kg. With no usable m² at all the kg is split evenly.
    """
    if not areas:
        return []
    total_area = sum(areas)
    weights = areas if total_area > 0 else [1.0] * len(areas)
    total_weight = sum(weights)
    shares = [round(consumed_kg * weight / total_weight, _ALLOCATION_DECIMALS) for weight in weights[:-1]]
    shares.append(max(consumed_kg - sum(shares), 0.0))
    return shares


class PaintRunTracker:
    def __init__(
        self,
        paint_repository: PaintRepository,
        paint_service: PaintService,
        audit: ProcessAuditWriter,
    ) -> None:
        self._repository = paint_repository
        self._paint_service = paint_service
        self._audit = audit

    # --- membership, driven by automatic HANGING transitions --------------------------------------

    def join_on_hanging_start(self, work_order: WorkOrder, *, station_context: StationContext | None) -> PaintRun:
        identity = paint_identity_of(work_order)
        if identity is None:
            raise InvalidProcessStageTransitionError(PAINT_CODE_MISSING_ERROR)

        area_m2 = self._pass_area_m2(work_order)
        latest = self._repository.get_latest_paint_run()
        if latest is not None and latest.closed_at is None and _identity_of_paint(latest.paint) == identity:
            run = latest
        else:
            paint = self._paint_service.get_or_create_paint(
                ral_code=identity.ral_code,
                paint_producer=identity.paint_producer,
                paint_code=identity.paint_code,
            )
            run = self._repository.add_paint_run(PaintRun(paint_id=paint.id))

        existing = next((member for member in run.members if member.work_order_id == work_order.id), None)
        if existing is not None:
            # The same order hung again inside the still-open run (e.g. a fast correction round of the
            # same paint): its pieces add to its weight instead of a second membership.
            existing.area_m2 += area_m2
        else:
            run.members.append(PaintRunMember(work_order_id=work_order.id, area_m2=area_m2))
        self._repository.session.flush()

        self._audit.record_audit_event(
            event_type="process.paint_run.joined",
            station_context=station_context,
            work_order=work_order,
            target_type="paint_run",
            target_id=run.id,
            summary=f"Work order {work_order.order_number} joined paint run {run.id}.",
            details={"paint_run_id": run.id, "area_m2": area_m2},
        )
        return run

    def leave_on_hanging_undo(self, work_order: WorkOrder, *, station_context: StationContext | None) -> None:
        """An undone hanging start takes the order back out of its still-open run (a closed run is a
        recorded physical fact and is left as is)."""
        for run in self._repository.list_open_paint_runs():
            member = next((member for member in run.members if member.work_order_id == work_order.id), None)
            if member is None:
                continue
            run.members.remove(member)
            self._repository.session.flush()
            self._audit.record_audit_event(
                event_type="process.paint_run.left",
                station_context=station_context,
                work_order=work_order,
                target_type="paint_run",
                target_id=run.id,
                summary=f"Work order {work_order.order_number} left paint run {run.id} (hanging undone).",
                details={"paint_run_id": run.id},
            )
            if not run.members:
                self._repository.delete_paint_run(run)

    # --- recording consumption ---------------------------------------------------------------------

    def record_consumption(
        self,
        paint_run_id: int,
        *,
        consumed_kg: float,
        station_context: StationContext | None,
    ) -> PaintRun:
        run = self._repository.get_paint_run(paint_run_id)
        if run is None:
            raise InvalidProcessStageTransitionError(RUN_NOT_FOUND_ERROR)
        if run.closed_at is not None:
            raise InvalidProcessStageTransitionError(RUN_ALREADY_RECORDED_ERROR)
        if any(self.member_hanging_status(member) == StageStatus.IN_PROGRESS for member in run.members):
            raise InvalidProcessStageTransitionError(RUN_HANGING_IN_PROGRESS_ERROR)

        order_numbers = ", ".join(member.work_order.order_number for member in run.members)
        try:
            self._paint_service.record_paint_run_consumption(
                paint=run.paint,
                quantity_kg=consumed_kg,
                paint_run_id=run.id,
                note=f"Grupa farby nr {run.id}: zlecenia {order_numbers}",
                station_context=station_context,
            )
        except InvalidPaintInventoryError as exc:
            raise InvalidProcessStageTransitionError(
                f"Za mało farby na stanie magazynu (stan: {run.paint.current_quantity_kg:g} kg, wpisano: "
                f"{consumed_kg:g} kg). Biuro musi najpierw poprawić stan tej farby."
            ) from exc

        shares = allocate_by_area(consumed_kg, [member.area_m2 for member in run.members])
        for member, share in zip(run.members, shares):
            member.allocated_kg = share
        run.consumed_kg = consumed_kg
        run.closed_at = clock.now()
        self._repository.session.flush()

        self._audit.record_audit_event(
            event_type="process.paint_run.consumption_recorded",
            station_context=station_context,
            work_order=None,
            target_type="paint_run",
            target_id=run.id,
            summary=f"Recorded automatic paint consumption {consumed_kg:g} kg for paint run {run.id}.",
            details={
                "paint_run_id": run.id,
                "consumed_kg": consumed_kg,
                "allocations": [
                    {"work_order_id": member.work_order_id, "area_m2": member.area_m2, "allocated_kg": member.allocated_kg}
                    for member in run.members
                ],
            },
        )
        return run

    # --- packing hold on the last order of an open run (CHANGES #23) ---------------------------------

    def holding_run_for(self, work_order: WorkOrder) -> PaintRun | None:
        """The open run that holds this order's packing completion, or None.

        Owner, 2026-10-09: the **last** order of a paint group does not complete until the group's
        consumption is entered, so the entry is never skipped. "Last" = the only order of the open run
        still physically on its way (hanging started, packing not done): once the next same-paint order
        starts hanging it joins the run and the previous one packs normally.
        """
        if not _is_between_hanging_done_and_packed(work_order):
            return None
        for run in self._repository.list_open_paint_runs():
            if not any(member.work_order_id == work_order.id for member in run.members):
                continue
            others_in_flow = any(
                member.work_order_id != work_order.id
                and not member.pending_packing_json
                and _is_in_flow(member.work_order)
                for member in run.members
            )
            return None if others_in_flow else run
        return None

    def park_packing(
        self,
        run: PaintRun,
        work_order: WorkOrder,
        payload: dict,
        *,
        station_context: StationContext | None,
    ) -> None:
        """Keep the operator's validated packing of the run's last order until the run is closed."""
        member = next(member for member in run.members if member.work_order_id == work_order.id)
        member.pending_packing_json = json.dumps(payload, separators=(",", ":"))
        self._repository.session.flush()
        self._audit.record_audit_event(
            event_type="process.packing.parked_for_paint_run",
            station_context=station_context,
            work_order=work_order,
            target_type="paint_run",
            target_id=run.id,
            summary=(
                f"Packing of work order {work_order.order_number} parked until paint run {run.id} "
                "consumption is entered (last order of the run)."
            ),
            details={"paint_run_id": run.id, **payload},
        )

    def parked_run_for(self, work_order: WorkOrder) -> PaintRun | None:
        """The open run on which this order's submitted packing waits, or None."""
        for run in self._repository.list_open_paint_runs():
            if any(member.work_order_id == work_order.id and member.pending_packing_json for member in run.members):
                return run
        return None

    def is_parked(self, work_order: WorkOrder) -> bool:
        return self.parked_run_for(work_order) is not None

    # --- helpers -------------------------------------------------------------------------------------

    @staticmethod
    def identity_of_run(run: PaintRun) -> PaintIdentity:
        return _identity_of_paint(run.paint)

    @staticmethod
    def member_hanging_status(member: PaintRunMember) -> StageStatus | None:
        return _stage_status(member.work_order, ProcessStage.HANGING)

    @staticmethod
    def _pass_area_m2(work_order: WorkOrder) -> float:
        """m² painted in this hanging pass: the per-piece area of the original order × pieces in the
        pass. A correction round / child paints only its returned pieces, so it weighs only those
        (a correction child carries its root's whole-order area, hence the per-piece root area)."""
        root = work_order
        while root.is_correction and root.parent_order is not None:
            root = root.parent_order
        if not root.total_area_m2 or root.total_quantity <= 0:
            return 0.0
        active_batch = work_order.active_batch
        pieces = active_batch.quantity if active_batch is not None else work_order.total_quantity
        return round(root.total_area_m2 / root.total_quantity * pieces, 3)

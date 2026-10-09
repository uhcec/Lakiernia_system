"""Physical-resource contention model for the process workflow engine.

Extracted from ``ProcessService`` (NA39). This collaborator owns:

- the single-holder ``HANGING`` / ``AUTOMATIC_LINE`` resource locks,
- the N-slot ``PACKING`` capacity model (NA22), and
- the in-process resource-mutation ``RLock``s that serialize lock acquisition within one
  worker (the documented single-worker deployment, NA8).

It deliberately does NOT own the per-work-order *process*-mutation lock
(``_serialize_process_mutation`` on ``ProcessService``), which serializes all mutations to
one work order and is a separate concern.

The occupancy predicates (``_has_active_hanging_work`` / ``_occupies_automatic_line`` /
``_occupies_packing``) live here because they are used only to decide lock acquisition,
reservation, and stale-lock recovery.

NA46 §A5 (bounding/evicting the in-process lock map) is intentionally left for a careful
pass: evicting an in-use ``RLock`` could hand two threads different locks for one key.
"""

from collections.abc import Callable, Sequence
from contextlib import ExitStack, contextmanager
from threading import RLock

from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.process.enums import ProcessStage, ProductionType, StageStatus
from app.process.models import WorkOrderStageState
from app.process.repository import ProcessRepository
from app.shared.exceptions import InvalidProcessStageTransitionError
from app.work_orders.models import WorkOrder


_RESOURCE_MUTATION_LOCKS: dict[str, RLock] = {}
_RESOURCE_MUTATION_LOCKS_GUARD = RLock()


class ResourceLockManager:
    # Packing capacity model (NA22). Packing has N configurable slots (PACKING:1..N). By default only
    # one work order packs at a time; an automatic order reserves a slot when HANGING starts (so it
    # cannot be blocked by a manual order), and a manual operator may *override* to open an additional
    # slot up to N when two orders can be packed at once. The lock row per slot is the claim/reservation.
    PACKING_SLOT_PREFIX = "PACKING:"
    PACKING_OCCUPIED_ERROR = "Stanowisko pakowania jest zajęte przez inne zlecenie."
    PACKING_ALL_SLOTS_FULL_ERROR = "Wszystkie stanowiska pakowania są zajęte."
    AUTOMATIC_LINE_OCCUPIED_ERROR = (
        "Linia automatu jest zajęta: poprzednie zlecenie nie zostało jeszcze spakowane. "
        "Zawieszanie zakończysz, gdy pakowanie je zamknie."
    )
    HANGING_OCCUPIED_ERROR = "Zawieszanie jest zajęte przez inne zlecenie."

    def __init__(self, repository: ProcessRepository) -> None:
        self._repository = repository
        # CHANGES #23: the packing of an open paint run's last order is parked until the run's
        # consumption is entered. While parked the order must not hold the packing station or the
        # automatic line (owner: the line keeps running). ProcessService wires the real predicate in.
        self.is_held_for_paint: Callable[[WorkOrder], bool] = lambda work_order: False

    @staticmethod
    def _stage_state(work_order: WorkOrder, stage: ProcessStage) -> WorkOrderStageState:
        for stage_state in work_order.stage_states:
            if stage_state.stage == stage:
                return stage_state
        raise InvalidProcessStageTransitionError(f"Stage {stage.value} is not configured for work order {work_order.id}.")

    # --- in-process resource-mutation serialization --------------------------------------------

    @staticmethod
    def _get_resource_mutation_lock(resource_key: str) -> RLock:
        with _RESOURCE_MUTATION_LOCKS_GUARD:
            lock = _RESOURCE_MUTATION_LOCKS.get(resource_key)
            if lock is None:
                lock = RLock()
                _RESOURCE_MUTATION_LOCKS[resource_key] = lock
            return lock

    @contextmanager
    def serialize_stage_resources(self, resource_keys: Sequence[str]):
        with ExitStack() as stack:
            for resource_key in sorted(set(resource_keys)):
                stack.enter_context(self.serialize_resource_mutation(resource_key))
            yield

    @contextmanager
    def serialize_resource_mutation(self, resource_key: str):
        lock = self._get_resource_mutation_lock(resource_key)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    # --- HANGING / AUTOMATIC_LINE resource locks -----------------------------------------------

    @staticmethod
    def get_stage_resource_keys(
        work_order: WorkOrder,
        stage: ProcessStage,
        target_status: StageStatus,
    ) -> tuple[str, ...]:
        if stage != ProcessStage.HANGING:
            return ()

        if target_status == StageStatus.IN_PROGRESS:
            return ("HANGING",)

        if target_status == StageStatus.DONE and work_order.production_type == ProductionType.AUTOMATIC:
            return ("AUTOMATIC_LINE",)

        return ()

    def ensure_stage_resources_available(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        target_status: StageStatus,
    ) -> None:
        if stage != ProcessStage.HANGING:
            return

        if target_status == StageStatus.DONE and work_order.production_type == ProductionType.AUTOMATIC:
            automatic_line_conflict = self.find_active_automatic_line_conflict(work_order.id)
            if automatic_line_conflict is not None:
                raise InvalidProcessStageTransitionError(self.AUTOMATIC_LINE_OCCUPIED_ERROR)
            return

        if target_status != StageStatus.IN_PROGRESS:
            return

        hanging_conflict = self.find_active_hanging_conflict(work_order.id)
        if hanging_conflict is not None:
            raise InvalidProcessStageTransitionError(self.HANGING_OCCUPIED_ERROR)

    def acquire_stage_resource_locks(self, work_order: WorkOrder, stage: ProcessStage, target_status: StageStatus) -> None:
        resource_keys = self.get_stage_resource_keys(work_order, stage, target_status)
        for resource_key in resource_keys:
            self._acquire_resource_lock_with_stale_recovery(resource_key, work_order)

    def _acquire_resource_lock_with_stale_recovery(self, resource_key: str, work_order: WorkOrder) -> None:
        try:
            self._repository.acquire_resource_lock(resource_key, work_order.id)
            return
        except ValueError:
            if not self._release_stale_resource_lock(resource_key):
                raise self._build_resource_conflict_error(resource_key)
        except IntegrityError:
            self._repository.rollback()
            if not self._release_stale_resource_lock(resource_key):
                raise self._build_resource_conflict_error(resource_key)

        try:
            self._repository.acquire_resource_lock(resource_key, work_order.id)
        except ValueError as exc:
            raise self._build_resource_conflict_error(resource_key) from exc
        except IntegrityError as exc:
            self._repository.rollback()
            raise self._build_resource_conflict_error(resource_key) from exc

    # --- Packing capacity / slots (NA22) -------------------------------------------------------

    def packing_slot_count(self) -> int:
        return max(1, int(get_settings().packing_max_concurrent_slots))

    def _packing_slot_keys(self) -> list[str]:
        return [f"{self.PACKING_SLOT_PREFIX}{index}" for index in range(1, self.packing_slot_count() + 1)]

    def _packing_slot_locks(self):
        return self._repository.list_resource_locks_with_prefix(self.PACKING_SLOT_PREFIX)

    def work_order_packing_slot_key(self, work_order_id: int) -> str | None:
        return next(
            (lock.resource_key for lock in self._packing_slot_locks() if lock.work_order_id == work_order_id),
            None,
        )

    def _cleanup_stale_packing_slots(self) -> None:
        # A slot is stale when its owner no longer occupies packing (completed, reset, or — for an
        # automatic reservation — its packing finished). Releasing keeps occupancy counts honest.
        for lock in list(self._packing_slot_locks()):
            owner = self._repository.get_work_order_with_stage_states(lock.work_order_id)
            if owner is None or not self._occupies_packing(owner):
                self._repository.release_resource_lock(lock.resource_key, lock.work_order_id)
        self._hand_free_station_to_waiting_automatic()

    def _hand_free_station_to_waiting_automatic(self) -> None:
        """When the station is free, give it to the automatic order that has waited longest (owner,
        2026-10-09: pieces reach packing in the order they were hung).

        A 2nd automatic order queues without a slot (NA22a). Before this, a slot freed by the first
        order went to whichever automatic order *started hanging next* — jumping the one already waiting
        at packing, which then blocked the newcomer's hanging finish (automatic line held) while the
        newcomer blocked its packing: a deadlock only an override broke (seen live 2026-10-09).
        """
        if self._packing_slot_locks():
            return
        waiting = [
            candidate
            for candidate in self._repository.list_work_orders_with_stage(ProcessStage.HANGING)
            if candidate.production_type == ProductionType.AUTOMATIC
            and self._occupies_packing(candidate)
            and self.work_order_packing_slot_key(candidate.id) is None
        ]
        if not waiting:
            return

        def arrival_key(candidate: WorkOrder):
            hanging_state = self._stage_state(candidate, ProcessStage.HANGING)
            # Finished hanging first = first at packing; then by when that happened.
            return (hanging_state.status != StageStatus.DONE, hanging_state.updated_at, candidate.id)

        first = min(waiting, key=arrival_key)
        self._repository.acquire_resource_lock(self._packing_slot_keys()[0], first.id)

    def acquire_packing_slot(
        self,
        work_order: WorkOrder,
        *,
        override: bool = False,
        reserve_only: bool = False,
        for_completion: bool = False,
    ) -> bool:
        """Acquire a packing slot for this work order. Returns True if a slot is now held.

        Capacity is N (``packing_max_concurrent_slots``). **Only manual orders may use a second slot**
        — an automatic order always uses the single station, never opening a 2nd packing:

        - **Capacity-bound** (occupied < N): a manual ``override`` start, or a manual completion. This
          is the only way to open slots 2..N.
        - **Single-station** (slot held, or station completely free): automatic hanging-start
          reservation (``reserve_only`` — a 2nd automatic queues silently), automatic completion (a
          queued 2nd automatic waits, raising "occupied" rather than taking a 2nd slot), and a manual
          default start (so two manual operators don't accidentally start at once).
        """
        is_automatic = work_order.production_type == ProductionType.AUTOMATIC
        capacity_bound = override or (for_completion and not is_automatic)
        with self.serialize_resource_mutation(self.PACKING_SLOT_PREFIX):
            self._cleanup_stale_packing_slots()
            if self.work_order_packing_slot_key(work_order.id) is not None:
                return True  # idempotent — already holds a slot

            slot_keys = self._packing_slot_keys()
            occupied_keys = {lock.resource_key for lock in self._packing_slot_locks()}
            occupied = len(occupied_keys)
            capacity = len(slot_keys)

            if capacity_bound:
                if occupied >= capacity:
                    raise InvalidProcessStageTransitionError(self.PACKING_ALL_SLOTS_FULL_ERROR)
            elif occupied != 0:
                # Single-station: automatic reservation/completion and manual default start.
                if reserve_only:
                    return False  # 2nd automatic queues; it does not reserve a second slot
                raise InvalidProcessStageTransitionError(self.PACKING_OCCUPIED_ERROR)

            free_key = next((key for key in slot_keys if key not in occupied_keys), None)
            if free_key is None:
                if reserve_only:
                    return False
                raise InvalidProcessStageTransitionError(self.PACKING_ALL_SLOTS_FULL_ERROR)

            try:
                self._repository.acquire_resource_lock(free_key, work_order.id)
            except ValueError:
                if reserve_only:
                    return False
                raise self._build_resource_conflict_error(free_key)
            return True

    def release_packing_slot(self, work_order: WorkOrder) -> None:
        slot_key = self.work_order_packing_slot_key(work_order.id)
        if slot_key is not None:
            self._repository.release_resource_lock(slot_key, work_order.id)
            self._hand_free_station_to_waiting_automatic()

    def reserve_packing_for_automatic_hanging(
        self, work_order: WorkOrder, stage: ProcessStage, target_status: StageStatus
    ) -> None:
        # NA22a: an automatic order reserves a packing slot the moment HANGING starts, so a manual
        # order cannot take the (default single) slot and block the un-pausable automatic line.
        if (
            stage == ProcessStage.HANGING
            and target_status == StageStatus.IN_PROGRESS
            and work_order.production_type == ProductionType.AUTOMATIC
        ):
            self.acquire_packing_slot(work_order, reserve_only=True)

    # --- stale-lock recovery + conflict detection ----------------------------------------------

    def _release_stale_resource_lock(self, resource_key: str) -> bool:
        existing_lock = self._repository.get_resource_lock(resource_key)
        if existing_lock is None:
            return False

        lock_owner = self._repository.get_work_order_with_stage_states(existing_lock.work_order_id)
        if lock_owner is None:
            self._repository.release_resource_lock(resource_key, existing_lock.work_order_id)
            return True

        if resource_key == "HANGING" and not self._has_active_hanging_work(lock_owner):
            self._repository.release_resource_lock(resource_key, existing_lock.work_order_id)
            return True

        if resource_key == "AUTOMATIC_LINE" and not self._occupies_automatic_line(lock_owner):
            self._repository.release_resource_lock(resource_key, existing_lock.work_order_id)
            return True

        if resource_key.startswith(self.PACKING_SLOT_PREFIX) and not self._occupies_packing(lock_owner):
            self._repository.release_resource_lock(resource_key, existing_lock.work_order_id)
            return True

        return False

    def release_inactive_resource_locks(self, work_order: WorkOrder) -> None:
        for resource_lock in self._repository.list_resource_locks_for_work_order(work_order.id):
            if resource_lock.resource_key == "HANGING" and not self._has_active_hanging_work(work_order):
                self._repository.release_resource_lock(resource_lock.resource_key, work_order.id)
            elif resource_lock.resource_key == "AUTOMATIC_LINE" and not self._occupies_automatic_line(work_order):
                self._repository.release_resource_lock(resource_lock.resource_key, work_order.id)
            elif resource_lock.resource_key.startswith(self.PACKING_SLOT_PREFIX) and not self._occupies_packing(work_order):
                self._repository.release_resource_lock(resource_lock.resource_key, work_order.id)
                self._hand_free_station_to_waiting_automatic()

    def _build_resource_conflict_error(self, resource_key: str) -> InvalidProcessStageTransitionError:
        if resource_key == "AUTOMATIC_LINE":
            return InvalidProcessStageTransitionError(self.AUTOMATIC_LINE_OCCUPIED_ERROR)
        if resource_key.startswith(self.PACKING_SLOT_PREFIX):
            return InvalidProcessStageTransitionError(self.PACKING_OCCUPIED_ERROR)
        return InvalidProcessStageTransitionError(self.HANGING_OCCUPIED_ERROR)

    def find_active_hanging_conflict(self, work_order_id: int) -> WorkOrder | None:
        for candidate in self._repository.list_work_orders_with_stage(ProcessStage.HANGING):
            if candidate.id == work_order_id:
                continue
            if self._has_active_hanging_work(candidate):
                return candidate
        return None

    def find_active_automatic_line_conflict(self, work_order_id: int) -> WorkOrder | None:
        for candidate in self._repository.list_work_orders_with_stage(ProcessStage.HANGING):
            if candidate.id == work_order_id:
                continue
            if self._occupies_automatic_line(candidate):
                return candidate
        return None

    # --- occupancy predicates (drive acquisition / reservation / stale recovery) ----------------

    def _has_active_hanging_work(self, work_order: WorkOrder) -> bool:
        hanging_state = self._stage_state(work_order, ProcessStage.HANGING)
        if hanging_state.status == StageStatus.IN_PROGRESS:
            return True

        return any(
            batch.is_active
            and batch.current_stage == ProcessStage.HANGING
            and batch.current_stage_status == StageStatus.IN_PROGRESS
            for batch in work_order.quantity_batches
        )

    def _occupies_automatic_line(self, work_order: WorkOrder) -> bool:
        if work_order.production_type != ProductionType.AUTOMATIC:
            return False
        if self.is_held_for_paint(work_order):
            return False  # CHANGES #23: waiting for the paint run's consumption — the line runs on

        # On the automatic line = parts hung and entered the spray booth, not yet packed. NA42: this
        # used to read PRODUCTION==IN_PROGRESS (which spanned exactly hanging-done→packing-done); with
        # no PRODUCTION stage the equivalent window is simply hanging DONE and packing not DONE.
        hanging_state = self._stage_state(work_order, ProcessStage.HANGING)
        packing_state = self._stage_state(work_order, ProcessStage.PACKING)
        if hanging_state.status == StageStatus.DONE and packing_state.status != StageStatus.DONE:
            return True

        return any(
            batch.is_active
            and batch.current_stage == ProcessStage.PACKING
            and batch.current_stage_status == StageStatus.IN_PROGRESS
            for batch in work_order.quantity_batches
        )

    def _occupies_packing(self, work_order: WorkOrder) -> bool:
        """Whether this work order should keep a held packing slot.

        True while the full-order packing stage is IN_PROGRESS, or an active tracked batch is
        IN_PROGRESS at packing (DECORAL). For an AUTOMATIC order it is also true from HANGING start
        through packing completion (NA22a reservation): the order reserves its slot when hanging
        starts and holds it until its own packing finishes. Used to keep slots and to recover stale
        ones once the owner's packing has finished or reset.
        """
        if self.is_held_for_paint(work_order):
            return False  # CHANGES #23: waiting for the paint run's consumption — frees the station

        packing_state = self._stage_state(work_order, ProcessStage.PACKING)
        if packing_state.status == StageStatus.IN_PROGRESS:
            return True

        if any(
            batch.is_active
            and batch.current_stage == ProcessStage.PACKING
            and batch.current_stage_status == StageStatus.IN_PROGRESS
            for batch in work_order.quantity_batches
        ):
            return True

        if work_order.production_type == ProductionType.AUTOMATIC:
            hanging_state = self._stage_state(work_order, ProcessStage.HANGING)
            if hanging_state.status in {StageStatus.IN_PROGRESS, StageStatus.DONE} and packing_state.status != StageStatus.DONE:
                return True

        return False

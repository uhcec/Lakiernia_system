from app.shared.enums import WorkOrderStatus
from app.shared.exceptions import InvalidStatusTransitionError


ALLOWED_TRANSITIONS = {
    WorkOrderStatus.ENTERED: {WorkOrderStatus.ASSIGNED},
    WorkOrderStatus.ASSIGNED: {WorkOrderStatus.IN_PROGRESS},
    WorkOrderStatus.IN_PROGRESS: {WorkOrderStatus.FINISHED},
    WorkOrderStatus.FINISHED: set(),
}


def is_transition_allowed(
    current_status: WorkOrderStatus,
    target_status: WorkOrderStatus,
) -> bool:
    return target_status in ALLOWED_TRANSITIONS[current_status]


def validate_transition(
    current_status: WorkOrderStatus,
    target_status: WorkOrderStatus,
) -> None:
    if not is_transition_allowed(current_status, target_status):
        raise InvalidStatusTransitionError(
            f"Cannot transition work order from {current_status.value} to {target_status.value}."
        )


def get_allowed_next_statuses(current_status: WorkOrderStatus) -> list[WorkOrderStatus]:
    return sorted(ALLOWED_TRANSITIONS[current_status], key=lambda status: status.value)
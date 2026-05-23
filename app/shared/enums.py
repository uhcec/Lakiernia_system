from enum import StrEnum


WORK_ORDER_STATUS_LABELS_PL = {
    "ENTERED": "Wprowadzone",
    "ASSIGNED": "Przypisane",
    "IN_PROGRESS": "W trakcie",
    "FINISHED": "Skończone",
}

WORK_ORDER_ALLOWED_TRANSITIONS = {
    "ENTERED": {"ASSIGNED"},
    "ASSIGNED": {"IN_PROGRESS"},
    "IN_PROGRESS": {"FINISHED"},
    "FINISHED": set(),
}


class WorkOrderStatus(StrEnum):
    ENTERED = "ENTERED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"

    @property
    def polish_label(self) -> str:
        return WORK_ORDER_STATUS_LABELS_PL[self.value]


def get_work_order_status_label(status: WorkOrderStatus) -> str:
    return WORK_ORDER_STATUS_LABELS_PL[status.value]


def can_transition_work_order_status(
    current_status: WorkOrderStatus,
    target_status: WorkOrderStatus,
) -> bool:
    return target_status.value in WORK_ORDER_ALLOWED_TRANSITIONS[current_status.value]
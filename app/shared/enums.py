from enum import StrEnum


WORK_ORDER_STATUS_LABELS_PL = {
    "ENTERED": "Wprowadzone",
    "INCOMPLETE": "Nie kompletne",
    "ASSIGNED": "Przypisane",
    "IN_PROGRESS": "W trakcie",
    "FINISHED": "Skończone",
}

QUEUE_NAMESPACE_LABELS_PL = {
    "MAIN": "Main",
    "CORRECTIONS": "Corrections",
}


class WorkOrderStatus(StrEnum):
    ENTERED = "ENTERED"
    INCOMPLETE = "INCOMPLETE"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"

    @property
    def polish_label(self) -> str:
        return WORK_ORDER_STATUS_LABELS_PL[self.value]


class QueueNamespace(StrEnum):
    MAIN = "MAIN"
    CORRECTIONS = "CORRECTIONS"

    @property
    def polish_label(self) -> str:
        return QUEUE_NAMESPACE_LABELS_PL[self.value]


def get_work_order_status_label(status: WorkOrderStatus) -> str:
    return WORK_ORDER_STATUS_LABELS_PL[status.value]


def get_queue_namespace_label(queue_namespace: QueueNamespace) -> str:
    return QUEUE_NAMESPACE_LABELS_PL[queue_namespace.value]

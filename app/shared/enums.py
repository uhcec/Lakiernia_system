from enum import StrEnum


class WorkOrderStatus(StrEnum):
    ENTERED = "ENTERED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"

    @property
    def polish_label(self) -> str:
        return {
            WorkOrderStatus.ENTERED: "Wprowadzone",
            WorkOrderStatus.ASSIGNED: "Przypisane",
            WorkOrderStatus.IN_PROGRESS: "W trakcie",
            WorkOrderStatus.FINISHED: "Skończone",
        }[self]
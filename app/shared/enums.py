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

WORK_ORDER_KIND_LABELS_PL = {
    "STANDARD": "Standardowe",
    "PRZEMALOWANKA": "Przemalowanka",
}

PAINT_STOCK_MOVEMENT_TYPE_LABELS_PL = {
    "OPENING_BALANCE": "Saldo otwarcia",
    "DELIVERY": "Dostawa",
    "AUTOMATIC_CONSUMPTION": "Zużycie automatu",
    "MANUAL_ADJUSTMENT": "Korekta ręczna",
}

STATION_ID_LABELS_PL = {
    "OFFICE": "Biuro",
    "MANAGER": "Kierownik",
    "SURFACE_PREPARATION": "Przygotowanie powierzchni",
    "HANGING": "Zawieszanie",
    "AUTOMATIC_PRODUCTION": "Produkcja automatyczna",
    "MANUAL_PRODUCTION": "Produkcja ręczna",
    "PACKING": "Pakowanie",
    "DECORAL_PRODUCTION": "Produkcja Decoral",
    "SYSTEM": "System",
    "UNKNOWN": "Nieznana stacja",
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


class WorkOrderKind(StrEnum):
    STANDARD = "STANDARD"
    PRZEMALOWANKA = "PRZEMALOWANKA"

    @property
    def polish_label(self) -> str:
        return WORK_ORDER_KIND_LABELS_PL[self.value]


class PaintStockMovementType(StrEnum):
    OPENING_BALANCE = "OPENING_BALANCE"
    DELIVERY = "DELIVERY"
    AUTOMATIC_CONSUMPTION = "AUTOMATIC_CONSUMPTION"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"

    @property
    def polish_label(self) -> str:
        return PAINT_STOCK_MOVEMENT_TYPE_LABELS_PL[self.value]


class StationId(StrEnum):
    OFFICE = "OFFICE"
    MANAGER = "MANAGER"
    SURFACE_PREPARATION = "SURFACE_PREPARATION"
    HANGING = "HANGING"
    AUTOMATIC_PRODUCTION = "AUTOMATIC_PRODUCTION"
    MANUAL_PRODUCTION = "MANUAL_PRODUCTION"
    PACKING = "PACKING"
    DECORAL_PRODUCTION = "DECORAL_PRODUCTION"
    SYSTEM = "SYSTEM"
    UNKNOWN = "UNKNOWN"

    @property
    def polish_label(self) -> str:
        return STATION_ID_LABELS_PL[self.value]


def get_work_order_status_label(status: WorkOrderStatus) -> str:
    return WORK_ORDER_STATUS_LABELS_PL[status.value]


def get_queue_namespace_label(queue_namespace: QueueNamespace) -> str:
    return QUEUE_NAMESPACE_LABELS_PL[queue_namespace.value]


def get_work_order_kind_label(work_order_kind: WorkOrderKind) -> str:
    return WORK_ORDER_KIND_LABELS_PL[work_order_kind.value]


def get_paint_stock_movement_type_label(movement_type: PaintStockMovementType) -> str:
    return PAINT_STOCK_MOVEMENT_TYPE_LABELS_PL[movement_type.value]


def get_station_id_label(station_id: StationId) -> str:
    return STATION_ID_LABELS_PL[station_id.value]

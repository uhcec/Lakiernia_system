from enum import StrEnum


PROCESS_STAGE_LABELS_PL = {
    "SURFACE_PREPARATION": "Przygotowanie powierzchni",
    "HANGING": "Zawieszanie",
    "PRODUCTION": "Produkcja",
    "DECORAL_PRODUCTION": "Produkcja Decoral",
    "PACKING": "Pakowanie",
}

STAGE_STATUS_LABELS_PL = {
    "NOT_STARTED": "Nie rozpoczęte",
    "IN_PROGRESS": "W trakcie",
    "DONE": "Zakończone",
}

COATING_TYPE_LABELS_PL = {
    "RAL": "RAL",
    "DECORAL": "Decoral",
}

PRODUCTION_TYPE_LABELS_PL = {
    "MANUAL": "Manualna",
    "AUTOMATIC": "Automatyczna",
}

PROCESS_DISPLAY_STATUS_LABELS_PL = {
    "TO_BE_PLANNED": "Do zaplanowania",
    "INCOMPLETE": "Nie kompletne",
    "SURFACE_PREPARATION": "Przygotowanie",
    "HANGING": "Zawieszanie",
    "PRODUCTION_MANUAL": "Produkcja ręczna",
    "PRODUCTION_AUTOMATIC": "Produkcja automat",
    "DECORAL_PRODUCTION": "Produkcja Decoral",
    "PACKING": "Pakowanie",
    "WAITING_FOR_CORRECTIONS": "Czeka na poprawki",
    "READY": "Gotowe",
}

QUANTITY_BATCH_TYPE_LABELS_PL = {
    "MAIN": "Partia główna",
    "CORRECTION": "Partia poprawkowa",
}


class CoatingType(StrEnum):
    RAL = "RAL"
    DECORAL = "DECORAL"

    @property
    def polish_label(self) -> str:
        return COATING_TYPE_LABELS_PL[self.value]


class ProductionType(StrEnum):
    MANUAL = "MANUAL"
    AUTOMATIC = "AUTOMATIC"

    @property
    def polish_label(self) -> str:
        return PRODUCTION_TYPE_LABELS_PL[self.value]


class ProcessDisplayStatus(StrEnum):
    TO_BE_PLANNED = "TO_BE_PLANNED"
    INCOMPLETE = "INCOMPLETE"
    SURFACE_PREPARATION = "SURFACE_PREPARATION"
    HANGING = "HANGING"
    PRODUCTION_MANUAL = "PRODUCTION_MANUAL"
    PRODUCTION_AUTOMATIC = "PRODUCTION_AUTOMATIC"
    DECORAL_PRODUCTION = "DECORAL_PRODUCTION"
    PACKING = "PACKING"
    WAITING_FOR_CORRECTIONS = "WAITING_FOR_CORRECTIONS"
    READY = "READY"

    @property
    def polish_label(self) -> str:
        return PROCESS_DISPLAY_STATUS_LABELS_PL[self.value]


class ProcessStage(StrEnum):
    SURFACE_PREPARATION = "SURFACE_PREPARATION"
    HANGING = "HANGING"
    PRODUCTION = "PRODUCTION"
    DECORAL_PRODUCTION = "DECORAL_PRODUCTION"
    PACKING = "PACKING"

    @property
    def polish_label(self) -> str:
        return PROCESS_STAGE_LABELS_PL[self.value]


class StageStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"

    @property
    def polish_label(self) -> str:
        return STAGE_STATUS_LABELS_PL[self.value]


class QuantityBatchType(StrEnum):
    MAIN = "MAIN"
    CORRECTION = "CORRECTION"

    @property
    def polish_label(self) -> str:
        return QUANTITY_BATCH_TYPE_LABELS_PL[self.value]


def get_coating_type_label(coating_type: CoatingType) -> str:
    return COATING_TYPE_LABELS_PL[coating_type.value]


def get_production_type_label(production_type: ProductionType) -> str:
    return PRODUCTION_TYPE_LABELS_PL[production_type.value]


def get_process_stage_label(stage: ProcessStage) -> str:
    return PROCESS_STAGE_LABELS_PL[stage.value]


def get_stage_status_label(status: StageStatus) -> str:
    return STAGE_STATUS_LABELS_PL[status.value]


def get_process_display_status_label(status: ProcessDisplayStatus) -> str:
    return PROCESS_DISPLAY_STATUS_LABELS_PL[status.value]


def get_quantity_batch_type_label(batch_type: QuantityBatchType) -> str:
    return QUANTITY_BATCH_TYPE_LABELS_PL[batch_type.value]

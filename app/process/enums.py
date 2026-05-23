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


def get_coating_type_label(coating_type: CoatingType) -> str:
    return COATING_TYPE_LABELS_PL[coating_type.value]


def get_production_type_label(production_type: ProductionType) -> str:
    return PRODUCTION_TYPE_LABELS_PL[production_type.value]


def get_process_stage_label(stage: ProcessStage) -> str:
    return PROCESS_STAGE_LABELS_PL[stage.value]


def get_stage_status_label(status: StageStatus) -> str:
    return STAGE_STATUS_LABELS_PL[status.value]

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.process.enums import ProcessStage, QuantityBatchType, StageStatus
from app.work_orders.schemas import CoatingTypeView, ProductionTypeView, QueueNamespaceView


class StageStatusView(BaseModel):
    value: StageStatus
    label: str


class ProcessStageStatusRead(BaseModel):
    stage: ProcessStage
    status: StageStatusView


class ProcessStageWorkOrderRead(BaseModel):
    id: int
    batch_id: int | None = None
    is_correction: bool
    is_historical_correction: bool = False
    order_number: str
    title: str
    ral_code: str
    total_area_m2: float | None = None
    total_quantity: int
    current_active_quantity: int
    batch_quantity: int | None = None
    planned_quantity: int
    counted_quantity: int | None = None
    quantity_difference: int | None = None
    customer_name: str | None
    queue_position: int | None
    queue_namespace: QueueNamespaceView
    production_type: ProductionTypeView | None
    coating_type: CoatingTypeView
    batch_type: QuantityBatchType | None = None
    batch_is_partial: bool = False
    stage_status: ProcessStageStatusRead


class StageTransitionRequest(BaseModel):
    counted_quantity: int | None = None

    model_config = ConfigDict(extra="forbid")


class PackingCompleteRequest(BaseModel):
    counted_quantity: int = Field(gt=0)
    ok_quantity: int = Field(ge=0)
    correction_quantity: int = Field(ge=0)
    correction_reason_category: str | None = Field(default=None, min_length=1, max_length=64)
    correction_reason_note: str | None = Field(default=None, max_length=500)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_correction_reason(self) -> "PackingCompleteRequest":
        has_reason = self.correction_reason_category is not None
        has_note = self.correction_reason_note is not None
        if self.correction_quantity > 0 and not has_reason:
            raise ValueError("Correction reason is required when correction quantity is greater than zero.")
        if self.correction_quantity == 0 and (has_reason or has_note):
            raise ValueError("Correction reason can only be set when correction quantity is greater than zero.")
        return self
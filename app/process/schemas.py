from pydantic import BaseModel, ConfigDict, Field

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


class StageStartRequest(BaseModel):
    counted_quantity: int | None = None

    model_config = ConfigDict(extra="forbid")


class PackingCompleteRequest(BaseModel):
    counted_quantity: int = Field(gt=0)
    ok_quantity: int = Field(ge=0)
    correction_quantity: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")
from pydantic import BaseModel, ConfigDict, Field

from app.process.enums import ProcessStage, StageStatus
from app.work_orders.schemas import CoatingTypeView, ProductionTypeView


class StageStatusView(BaseModel):
    value: StageStatus
    label: str


class ProcessStageStatusRead(BaseModel):
    stage: ProcessStage
    status: StageStatusView


class ProcessStageWorkOrderRead(BaseModel):
    id: int
    order_number: str
    title: str
    total_quantity: int
    current_active_quantity: int
    customer_name: str | None
    queue_position: int | None
    production_type: ProductionTypeView | None
    coating_type: CoatingTypeView
    stage_status: ProcessStageStatusRead


class PackingCompleteRequest(BaseModel):
    ok_quantity: int = Field(ge=0)
    correction_quantity: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")
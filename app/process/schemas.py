from pydantic import BaseModel

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
    customer_name: str | None
    queue_position: int | None
    production_type: ProductionTypeView | None
    coating_type: CoatingTypeView
    stage_status: ProcessStageStatusRead
from pydantic import BaseModel

from app.shared.enums import WorkOrderStatus


class WorkOrderStatusOption(BaseModel):
    value: WorkOrderStatus
    label: str
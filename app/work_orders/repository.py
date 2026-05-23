from sqlalchemy import select
from sqlalchemy.orm import Session

from app.work_orders.models import WorkOrder


class WorkOrderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_reference(self, reference: str) -> WorkOrder | None:
        statement = select(WorkOrder).where(WorkOrder.reference == reference)
        return self.session.scalar(statement)
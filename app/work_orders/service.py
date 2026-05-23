from app.shared.enums import WorkOrderStatus
from app.work_orders.schemas import WorkOrderStatusOption


class WorkOrderService:
    @staticmethod
    def get_status_options() -> list[WorkOrderStatusOption]:
        return [
            WorkOrderStatusOption(value=status, label=status.polish_label)
            for status in WorkOrderStatus
        ]
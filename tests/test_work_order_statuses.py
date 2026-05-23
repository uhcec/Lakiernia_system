from app.shared.enums import WorkOrderStatus
from app.work_orders.service import WorkOrderService


def test_status_view_uses_polish_label_without_losing_internal_value() -> None:
    status_view = WorkOrderService.build_status_view(WorkOrderStatus.IN_PROGRESS)

    assert status_view.value == WorkOrderStatus.IN_PROGRESS
    assert status_view.label == "W trakcie"
from app.process.enums import ProcessDisplayStatus
from app.shared.enums import WorkOrderStatus
from app.work_orders.service import WorkOrderService


def test_status_view_is_derived_from_process_status() -> None:
    status_view = WorkOrderService.build_status_view(ProcessDisplayStatus.PRODUCTION_MANUAL)

    assert status_view.value == WorkOrderStatus.IN_PROGRESS
    assert status_view.label == "W trakcie"

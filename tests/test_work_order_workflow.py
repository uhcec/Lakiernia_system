from app.shared.enums import WorkOrderStatus
from app.work_orders.workflow import get_allowed_next_statuses


def test_get_allowed_next_statuses_returns_single_valid_next_step() -> None:
    allowed_statuses = get_allowed_next_statuses(WorkOrderStatus.ASSIGNED)

    assert allowed_statuses == [WorkOrderStatus.IN_PROGRESS]
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.work_orders.models import WorkOrder
from scripts.reset_and_seed_dev_db import seed_all_use_cases


def test_seed_scenarios_respect_profile_accessory_sum_invariant(db_session: Session) -> None:
    scenarios = seed_all_use_cases(db_session)
    work_orders = db_session.scalars(select(WorkOrder)).all()

    invalid_known_pairs = [
        work_order.order_number
        for work_order in work_orders
        if work_order.profiles_quantity is not None
        and work_order.accessories_quantity is not None
        and work_order.profiles_quantity + work_order.accessories_quantity != work_order.total_quantity
    ]
    mixed_known_pairs = [
        work_order
        for work_order in work_orders
        if work_order.profiles_quantity is not None
        and work_order.accessories_quantity is not None
        and work_order.profiles_quantity > 0
        and work_order.accessories_quantity > 0
    ]

    assert scenarios
    assert not invalid_known_pairs
    assert mixed_known_pairs
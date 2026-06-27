from datetime import date

import sqlite3
from contextlib import nullcontext

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.process.enums import CoatingType, ProcessStage, QuantityBatchType, StageStatus
from app.shared.enums import QueueNamespace
from app.work_orders.models import WorkOrder


def _insert_valid_work_order(db_session: Session, *, order_number: str = "WO-2026-9000") -> int:
    work_order = WorkOrder(
        order_number=order_number,
        title=order_number,
        total_quantity=10,
        completed_quantity=0,
        parent_order_id=None,
        is_correction=False,
        description=None,
        customer_name="Customer",
        ral_code="RAL 9005",
        paint_producer="Producer",
        coating_type=CoatingType.RAL,
        production_type=None,
        queue_namespace=QueueNamespace.MAIN,
        queue_position=None,
        received_date=date(2026, 5, 25),
        planned_pickup_date=date(2026, 6, 1),
        total_area_m2=None,
        is_incomplete_on_arrival=False,
        profiles_quantity=None,
        profiles_to_count=True,
        accessories_quantity=None,
        accessories_to_count=True,
        notes=None,
    )
    db_session.add(work_order)
    db_session.flush()
    return work_order.id


def test_valid_direct_db_inserts_still_pass(db_session: Session) -> None:
    work_order_id = _insert_valid_work_order(db_session)

    db_session.execute(
        text(
            """
            INSERT INTO work_order_quantity_batches (
                work_order_id, quantity, type, parent_batch_id, is_active, current_stage, current_stage_status, is_partial, created_at
            ) VALUES (
                :work_order_id, :quantity, :type, NULL, :is_active, :current_stage, :current_stage_status, :is_partial, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "work_order_id": work_order_id,
            "quantity": 10,
            "type": QuantityBatchType.MAIN.value,
            "is_active": True,
            "current_stage": ProcessStage.SURFACE_PREPARATION.value,
            "current_stage_status": StageStatus.NOT_STARTED.value,
            "is_partial": False,
        },
    )
    db_session.execute(
        text(
            """
            INSERT INTO work_order_stage_states (
                work_order_id, stage, status, counted_quantity, created_at, updated_at
            ) VALUES (
                :work_order_id, :stage, :status, :counted_quantity, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "work_order_id": work_order_id,
            "stage": ProcessStage.SURFACE_PREPARATION.value,
            "status": StageStatus.NOT_STARTED.value,
            "counted_quantity": None,
        },
    )
    db_session.commit()


def test_profile_accessory_quantities_must_sum_to_total_when_known(db_session: Session) -> None:
    valid_work_order = WorkOrder(
        order_number="WO-2026-9001",
        title="valid-category-quantities",
        total_quantity=10,
        completed_quantity=0,
        parent_order_id=None,
        is_correction=False,
        description=None,
        customer_name="Customer",
        ral_code="RAL 9005",
        paint_producer="Producer",
        coating_type=CoatingType.RAL,
        production_type=None,
        queue_namespace=QueueNamespace.MAIN,
        queue_position=None,
        received_date=date(2026, 5, 25),
        planned_pickup_date=date(2026, 6, 1),
        total_area_m2=None,
        is_incomplete_on_arrival=False,
        profiles_quantity=4,
        profiles_to_count=False,
        accessories_quantity=6,
        accessories_to_count=False,
        notes=None,
    )
    db_session.add(valid_work_order)
    db_session.commit()

    invalid_work_order = WorkOrder(
        order_number="WO-2026-9002",
        title="invalid-category-quantities",
        total_quantity=10,
        completed_quantity=0,
        parent_order_id=None,
        is_correction=False,
        description=None,
        customer_name="Customer",
        ral_code="RAL 9005",
        paint_producer="Producer",
        coating_type=CoatingType.RAL,
        production_type=None,
        queue_namespace=QueueNamespace.MAIN,
        queue_position=None,
        received_date=date(2026, 5, 25),
        planned_pickup_date=date(2026, 6, 1),
        total_area_m2=None,
        is_incomplete_on_arrival=False,
        profiles_quantity=5,
        profiles_to_count=False,
        accessories_quantity=10,
        accessories_to_count=False,
        notes=None,
    )
    db_session.add(invalid_work_order)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize(
    ("statement", "params"),
    [
        (
            """
            INSERT INTO work_orders (
                order_number, title, total_quantity, completed_quantity, parent_order_id,
                is_correction, description, customer_name, ral_code, paint_producer, coating_type,
                production_type, queue_namespace, queue_position, received_date, planned_pickup_date, total_area_m2,
                is_incomplete_on_arrival, profiles_quantity, profiles_to_count, accessories_quantity, accessories_to_count,
                notes, created_at, updated_at
            ) VALUES (
                :order_number, :title, :total_quantity, :completed_quantity, NULL,
                :is_correction, NULL, 'Customer', 'RAL 9005', 'Producer', 'RAL',
                :production_type, :queue_namespace, :queue_position, '2026-05-25', '2026-06-01', NULL,
                0, :profiles_quantity, 1, :accessories_quantity, 1,
                NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            {
                "order_number": "WO-2026-9100",
                "title": "invalid-total",
                "total_quantity": 0,
                "completed_quantity": 0,
                "is_correction": 0,
                "production_type": None,
                "queue_namespace": QueueNamespace.MAIN.value,
                "queue_position": None,
                "profiles_quantity": None,
                "accessories_quantity": None,
            },
        ),
        (
            """
            INSERT INTO work_orders (
                order_number, title, total_quantity, completed_quantity, parent_order_id,
                is_correction, description, customer_name, ral_code, paint_producer, coating_type,
                production_type, queue_namespace, queue_position, received_date, planned_pickup_date, total_area_m2,
                is_incomplete_on_arrival, profiles_quantity, profiles_to_count, accessories_quantity, accessories_to_count,
                notes, created_at, updated_at
            ) VALUES (
                :order_number, :title, 10, 11, NULL,
                0, NULL, 'Customer', 'RAL 9005', 'Producer', 'RAL',
                NULL, 'MAIN', NULL, '2026-05-25', '2026-06-01', NULL,
                0, NULL, 1, NULL, 1,
                NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            {"order_number": "WO-2026-9101", "title": "invalid-completed"},
        ),
        (
            """
            INSERT INTO work_orders (
                order_number, title, total_quantity, completed_quantity, parent_order_id,
                is_correction, description, customer_name, ral_code, paint_producer, coating_type,
                production_type, queue_namespace, queue_position, received_date, planned_pickup_date, total_area_m2,
                is_incomplete_on_arrival, profiles_quantity, profiles_to_count, accessories_quantity, accessories_to_count,
                notes, created_at, updated_at
            ) VALUES (
                :order_number, :title, 10, 0, NULL,
                0, NULL, 'Customer', 'RAL 9005', 'Producer', 'RAL',
                NULL, 'MAIN', 0, '2026-05-25', '2026-06-01', NULL,
                0, NULL, 1, NULL, 1,
                NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            {"order_number": "WO-2026-9102", "title": "invalid-queue"},
        ),
        (
            """
            INSERT INTO work_orders (
                order_number, title, total_quantity, completed_quantity, parent_order_id,
                is_correction, description, customer_name, ral_code, paint_producer, coating_type,
                production_type, queue_namespace, queue_position, received_date, planned_pickup_date, total_area_m2,
                is_incomplete_on_arrival, profiles_quantity, profiles_to_count, accessories_quantity, accessories_to_count,
                notes, created_at, updated_at
            ) VALUES (
                :order_number, :title, 10, 0, NULL,
                0, NULL, 'Customer', 'RAL 9005', 'Producer', 'RAL',
                'MANUAL', 'MAIN', NULL, '2026-05-25', '2026-06-01', NULL,
                0, NULL, 1, NULL, 1,
                NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            {"order_number": "WO-2026-9103", "title": "invalid-planned-parity"},
        ),
        (
            """
            INSERT INTO work_orders (
                id, order_number, title, total_quantity, completed_quantity, parent_order_id,
                is_correction, description, customer_name, ral_code, paint_producer, coating_type,
                production_type, queue_namespace, queue_position, received_date, planned_pickup_date, total_area_m2,
                is_incomplete_on_arrival, profiles_quantity, profiles_to_count, accessories_quantity, accessories_to_count,
                notes, created_at, updated_at
            ) VALUES (
                9910, :order_number, :title, 10, 0, 9910,
                0, NULL, 'Customer', 'RAL 9005', 'Producer', 'RAL',
                NULL, 'MAIN', NULL, '2026-05-25', '2026-06-01', NULL,
                0, NULL, 1, NULL, 1,
                NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            {"order_number": "WO-2026-9104", "title": "invalid-parent-self"},
        ),
        (
            """
            INSERT INTO work_orders (
                order_number, title, total_quantity, completed_quantity, parent_order_id,
                is_correction, description, customer_name, ral_code, paint_producer, coating_type,
                production_type, queue_namespace, queue_position, received_date, planned_pickup_date, total_area_m2,
                is_incomplete_on_arrival, profiles_quantity, profiles_to_count, accessories_quantity, accessories_to_count,
                notes, created_at, updated_at
            ) VALUES (
                :order_number, :title, 10, 0, NULL,
                1, NULL, 'Customer', 'RAL 9005', 'Producer', 'RAL',
                NULL, 'MAIN', NULL, '2026-05-25', '2026-06-01', NULL,
                0, NULL, 1, NULL, 1,
                NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            {"order_number": "WO-2026-9105", "title": "invalid-correction-namespace"},
        ),
    ],
)
def test_invalid_work_order_direct_db_writes_fail(db_session: Session, statement: str, params: dict[str, object]) -> None:
    with pytest.raises(IntegrityError):
        db_session.execute(text(statement), params)
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize(
    ("statement", "params"),
    [
        (
            """
            INSERT INTO work_order_quantity_batches (
                work_order_id, quantity, type, parent_batch_id, is_active, current_stage, current_stage_status, is_partial, created_at
            ) VALUES (
                :work_order_id, 0, :type, NULL, 1, NULL, NULL, 0, CURRENT_TIMESTAMP
            )
            """,
            {"work_order_id": 1, "type": QuantityBatchType.MAIN.value},
        ),
        (
            """
            INSERT INTO work_order_quantity_batches (
                work_order_id, quantity, type, parent_batch_id, is_active, current_stage, current_stage_status, is_partial, created_at
            ) VALUES (
                :work_order_id, 5, :type, NULL, 1, :current_stage, NULL, 0, CURRENT_TIMESTAMP
            )
            """,
            {"work_order_id": 1, "type": QuantityBatchType.MAIN.value, "current_stage": ProcessStage.PACKING.value},
        ),
    ],
)
def test_invalid_batch_direct_db_writes_fail(db_session: Session, statement: str, params: dict[str, object]) -> None:
    _insert_valid_work_order(db_session, order_number="WO-2026-9200")

    with pytest.raises(IntegrityError):
        db_session.execute(text(statement), params)
        db_session.commit()
    db_session.rollback()


def test_invalid_stage_state_direct_db_write_fails(db_session: Session) -> None:
    work_order_id = _insert_valid_work_order(db_session, order_number="WO-2026-9300")

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                """
                INSERT INTO work_order_stage_states (
                    work_order_id, stage, status, counted_quantity, created_at, updated_at
                ) VALUES (
                    :work_order_id, :stage, :status, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "work_order_id": work_order_id,
                "stage": ProcessStage.SURFACE_PREPARATION.value,
                "status": StageStatus.NOT_STARTED.value,
            },
        )
        db_session.commit()
    db_session.rollback()

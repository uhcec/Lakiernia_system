from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import pytest

from app.process.enums import ProcessStage, QuantityBatchType, StageStatus


def _insert_work_order(
    db_session: Session,
    *,
    order_number: str,
    is_correction: int = 0,
    parent_order_id: int | None = None,
    is_incomplete_on_arrival: int = 0,
    production_type: str | None = None,
    queue_position: int | None = None,
) -> int:
    result = db_session.execute(
        text(
            """
            INSERT INTO work_orders (
                order_number, title, total_quantity, completed_quantity, parent_order_id,
                is_correction, description, customer_name, ral_code, paint_producer, coating_type,
                work_order_kind, is_ocynk, production_type, queue_namespace, queue_position, received_date, planned_pickup_date, total_area_m2,
                is_incomplete_on_arrival, profiles_quantity, profiles_to_count, accessories_quantity, accessories_to_count,
                notes, consumed_paint_quantity_kg, created_at, updated_at
            ) VALUES (
                :order_number, :order_number, 10, 0, :parent_order_id,
                :is_correction, NULL, 'Customer', 'RAL 9005', 'Producer', 'RAL',
                'STANDARD', 0, :production_type, :queue_namespace, :queue_position, '2026-05-25', '2026-06-01', NULL,
                :is_incomplete_on_arrival, NULL, 1, NULL, 1,
                NULL, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "order_number": order_number,
            "is_correction": is_correction,
            "parent_order_id": parent_order_id,
            "queue_namespace": "CORRECTIONS" if is_correction else "MAIN",
            "is_incomplete_on_arrival": is_incomplete_on_arrival,
            "production_type": production_type,
            "queue_position": queue_position,
        },
    )
    db_session.flush()
    return int(result.lastrowid)


def _insert_batch(
    db_session: Session,
    *,
    work_order_id: int,
    quantity: int = 10,
    is_active: int,
    current_stage: str | None,
    current_stage_status: str | None,
) -> None:
    db_session.execute(
        text(
            """
            INSERT INTO work_order_quantity_batches (
                work_order_id, quantity, type, parent_batch_id, is_active, current_stage, current_stage_status, is_partial, created_at
            ) VALUES (
                :work_order_id, :quantity, :type, NULL, :is_active, :current_stage, :current_stage_status, 0, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "work_order_id": work_order_id,
            "quantity": quantity,
            "type": QuantityBatchType.MAIN.value,
            "is_active": is_active,
            "current_stage": current_stage,
            "current_stage_status": current_stage_status,
        },
    )


def test_phase2_valid_direct_db_inserts_still_pass(db_session: Session) -> None:
    parent_id = _insert_work_order(db_session, order_number="WO-2026-9700")
    _insert_work_order(
        db_session,
        order_number="WO-2026-9701",
        is_correction=1,
        parent_order_id=parent_id,
    )
    _insert_batch(
        db_session,
        work_order_id=parent_id,
        is_active=1,
        current_stage=ProcessStage.PRODUCTION.value,
        current_stage_status=StageStatus.IN_PROGRESS.value,
    )
    _insert_batch(
        db_session,
        work_order_id=parent_id,
        quantity=3,
        is_active=0,
        current_stage=ProcessStage.PACKING.value,
        current_stage_status=StageStatus.DONE.value,
    )

    db_session.commit()


def test_correction_direct_db_write_without_parent_fails(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        _insert_work_order(db_session, order_number="WO-2026-9702", is_correction=1, parent_order_id=None)
        db_session.commit()
    db_session.rollback()


def test_second_active_batch_for_same_work_order_fails(db_session: Session) -> None:
    work_order_id = _insert_work_order(db_session, order_number="WO-2026-9703")
    _insert_batch(
        db_session,
        work_order_id=work_order_id,
        is_active=1,
        current_stage=ProcessStage.PRODUCTION.value,
        current_stage_status=StageStatus.IN_PROGRESS.value,
    )
    db_session.commit()

    with pytest.raises(IntegrityError):
        _insert_batch(
            db_session,
            work_order_id=work_order_id,
            quantity=2,
            is_active=1,
            current_stage=ProcessStage.PACKING.value,
            current_stage_status=StageStatus.NOT_STARTED.value,
        )
        db_session.commit()
    db_session.rollback()



def test_inactive_batch_without_done_status_fails(db_session: Session) -> None:
    work_order_id = _insert_work_order(db_session, order_number="WO-2026-9704")

    with pytest.raises(IntegrityError):
        _insert_batch(
            db_session,
            work_order_id=work_order_id,
            is_active=0,
            current_stage=ProcessStage.PACKING.value,
            current_stage_status=StageStatus.IN_PROGRESS.value,
        )
        db_session.commit()
    db_session.rollback()


def test_incomplete_arrival_work_order_cannot_be_queued_by_direct_db_write(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        _insert_work_order(
            db_session,
            order_number="WO-2026-9705",
            is_incomplete_on_arrival=1,
            production_type="MANUAL",
            queue_position=3,
        )
        db_session.commit()
    db_session.rollback()

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database.base import Base
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.work_orders.models import WorkOrder, WorkOrderNumberCounter
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService


def build_work_order_create(title: str, *, total_quantity: int = 100) -> WorkOrderCreate:
    return WorkOrderCreate(
        title=title,
        coating_type=CoatingType.RAL,
        total_quantity=total_quantity,
        customer_name="ACME",
        ral_code="RAL 7016",
        paint_code="P-7016",
        paint_producer="AkzoNobel",
        received_date="2026-05-25",
        total_area_m2=24.0,
        profiles_to_count=True,
        accessories_to_count=True,
    )


def build_services(
    db_session: Session,
) -> tuple[WorkOrderService, ProcessService, ManagerService, WorkOrderRepository, ProcessRepository]:
    work_order_repository = WorkOrderRepository(db_session)
    process_repository = ProcessRepository(db_session)
    manager_repository = ManagerRepository(db_session)
    return (
        WorkOrderService(work_order_repository),
        ProcessService(process_repository),
        ManagerService(manager_repository),
        work_order_repository,
        process_repository,
    )


def move_to_packing(process_service: ProcessService, manager_service: ManagerService, work_order_id: int) -> None:
    manager_service.assign_plan(
        work_order_id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    process_service.start_stage(
        work_order_id,
        ProcessStage.SURFACE_PREPARATION,
        counted_quantity=process_service.get_work_order_process(work_order_id).current_active_quantity,
    )
    process_service.finish_stage(work_order_id, ProcessStage.SURFACE_PREPARATION)
    process_service.start_stage(work_order_id, ProcessStage.PRODUCTION)
    process_service.finish_stage(work_order_id, ProcessStage.PRODUCTION)
    process_service.start_stage(work_order_id, ProcessStage.PACKING)


def test_normal_creation_increments_counter(db_session: Session) -> None:
    work_order_service, _, _, _, _ = build_services(db_session)

    first = work_order_service.create_work_order(build_work_order_create("Counter 1"))
    second = work_order_service.create_work_order(build_work_order_create("Counter 2"))
    counter = db_session.get(WorkOrderNumberCounter, int(first.order_number.split("-")[1]))

    assert first.order_number.endswith("0001")
    assert second.order_number.endswith("0002")
    assert counter is not None
    assert counter.last_value == 2


def test_correction_child_uses_same_yearly_sequence(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, _ = build_services(db_session)

    parent = work_order_service.create_work_order(build_work_order_create("Parent order"))
    move_to_packing(process_service, manager_service, parent.id)
    process_service.complete_packing(
        parent.id,
        counted_quantity=100,
        ok_quantity=80,
        correction_quantity=20,
        correction_profiles_quantity=20,
        correction_accessories_quantity=0,
        correction_reason_category="niedomalowanie",
    )
    correction_orders = [order for order in work_order_repository.list(limit=20, offset=0) if order.parent_order_id == parent.id]

    assert parent.order_number.endswith("0001")
    assert len(correction_orders) == 1
    assert correction_orders[0].order_number.endswith("0002")


def test_concurrent_normal_creation_produces_unique_numbers(tmp_path) -> None:
    database_path = tmp_path / "parallel_number_allocation.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)

    try:
        def create_order(index: int) -> str:
            session = session_factory()
            try:
                service = WorkOrderService(WorkOrderRepository(session))
                return service.create_work_order(build_work_order_create(f"Parallel {index}")).order_number
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=5) as executor:
            order_numbers = list(executor.map(create_order, range(1, 6)))

        verify_session = session_factory()
        try:
            persisted_numbers = verify_session.scalars(select(WorkOrder.order_number).order_by(WorkOrder.id.asc())).all()
        finally:
            verify_session.close()
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    assert len(order_numbers) == 5
    assert len(set(order_numbers)) == 5
    assert sorted(persisted_numbers) == sorted(order_numbers)


def test_mixed_normal_and_correction_creation_produces_unique_numbers(tmp_path) -> None:
    database_path = tmp_path / "mixed_number_allocation.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)

    try:
        setup_session = session_factory()
        try:
            work_order_service, process_service, manager_service, _, _ = build_services(setup_session)
            parent = work_order_service.create_work_order(build_work_order_create("Correction parent"))
            move_to_packing(process_service, manager_service, parent.id)
        finally:
            setup_session.close()

        def create_normal_order() -> str:
            session = session_factory()
            try:
                service = WorkOrderService(WorkOrderRepository(session))
                return service.create_work_order(build_work_order_create("Concurrent normal")).order_number
            finally:
                session.close()

        def create_correction_child() -> str:
            session = session_factory()
            try:
                process_service = ProcessService(ProcessRepository(session))
                process_service.complete_packing(
                    parent.id,
                    counted_quantity=100,
                    ok_quantity=85,
                    correction_quantity=15,
                    correction_profiles_quantity=15,
                    correction_accessories_quantity=0,
                    correction_reason_category="niedomalowanie",
                )
                correction_order = session.scalars(
                    select(WorkOrder).where(WorkOrder.parent_order_id == parent.id).order_by(WorkOrder.id.desc())
                ).first()
                assert correction_order is not None
                return correction_order.order_number
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            normal_future = executor.submit(create_normal_order)
            correction_future = executor.submit(create_correction_child)
            normal_number = normal_future.result()
            correction_number = correction_future.result()

        verify_session = session_factory()
        try:
            persisted_numbers = verify_session.scalars(select(WorkOrder.order_number).order_by(WorkOrder.id.asc())).all()
        finally:
            verify_session.close()
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    assert len(set([normal_number, correction_number, *persisted_numbers])) == len(persisted_numbers)
    assert len(persisted_numbers) == 3


def test_failure_rolls_back_counter_and_work_order(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> None:
    work_order_service, _, _, work_order_repository, _ = build_services(db_session)

    def fail_stage_initialization(*args, **kwargs):
        raise RuntimeError("forced failure after number allocation")

    monkeypatch.setattr(work_order_service.process_service, "initialize_stage_states", fail_stage_initialization)

    with pytest.raises(RuntimeError, match="forced failure"):
        work_order_service.create_work_order(build_work_order_create("Rollback order"))

    assert work_order_repository.count() == 0
    assert db_session.scalars(select(WorkOrderNumberCounter)).all() == []

    monkeypatch.undo()

    created = work_order_service.create_work_order(build_work_order_create("Retry after rollback"))

    assert created.order_number.endswith("0001")
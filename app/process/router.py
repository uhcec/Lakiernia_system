from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db_session
from app.process.enums import ProcessStage, ProductionType
from app.process.repository import ProcessRepository
from app.process.schemas import PackingCompleteRequest, ProcessStageWorkOrderRead, StageStartRequest
from app.process.service import ProcessService

router = APIRouter(prefix="/process", tags=["process"])


def get_process_service(session: Annotated[Session, Depends(get_db_session)]) -> ProcessService:
    repository = ProcessRepository(session)
    return ProcessService(repository)


@router.get("/stages/{stage}/work-orders", response_model=list[ProcessStageWorkOrderRead])
def list_stage_work_orders(
    stage: ProcessStage,
    service: Annotated[ProcessService, Depends(get_process_service)],
    production_type: Annotated[ProductionType | None, Query()] = None,
) -> list[ProcessStageWorkOrderRead]:
    return service.list_stage_work_orders(stage, production_type)


@router.post("/work-orders/{work_order_id}/stages/{stage}/start", response_model=ProcessStageWorkOrderRead)
def start_stage(
    work_order_id: int,
    stage: ProcessStage,
    service: Annotated[ProcessService, Depends(get_process_service)],
    payload: StageStartRequest | None = None,
) -> ProcessStageWorkOrderRead:
    return service.start_stage(work_order_id, stage, counted_quantity=payload.counted_quantity if payload else None)


@router.post("/work-orders/{work_order_id}/batches/{batch_id}/stages/{stage}/start", response_model=ProcessStageWorkOrderRead)
def start_stage_for_batch(
    work_order_id: int,
    batch_id: int,
    stage: ProcessStage,
    service: Annotated[ProcessService, Depends(get_process_service)],
    payload: StageStartRequest | None = None,
) -> ProcessStageWorkOrderRead:
    return service.start_stage(
        work_order_id,
        stage,
        batch_id=batch_id,
        counted_quantity=payload.counted_quantity if payload else None,
    )


@router.post("/work-orders/{work_order_id}/stages/{stage}/finish", response_model=ProcessStageWorkOrderRead)
def finish_stage(
    work_order_id: int,
    stage: ProcessStage,
    service: Annotated[ProcessService, Depends(get_process_service)],
) -> ProcessStageWorkOrderRead:
    return service.finish_stage(work_order_id, stage)


@router.post("/work-orders/{work_order_id}/batches/{batch_id}/stages/{stage}/finish", response_model=ProcessStageWorkOrderRead)
def finish_stage_for_batch(
    work_order_id: int,
    batch_id: int,
    stage: ProcessStage,
    service: Annotated[ProcessService, Depends(get_process_service)],
) -> ProcessStageWorkOrderRead:
    return service.finish_stage(work_order_id, stage, batch_id=batch_id)


@router.post("/work-orders/{work_order_id}/stages/{stage}/reopen", response_model=ProcessStageWorkOrderRead)
def reopen_stage(
    work_order_id: int,
    stage: ProcessStage,
    service: Annotated[ProcessService, Depends(get_process_service)],
) -> ProcessStageWorkOrderRead:
    return service.reopen_stage(work_order_id, stage)


@router.post("/work-orders/{work_order_id}/batches/{batch_id}/stages/{stage}/reopen", response_model=ProcessStageWorkOrderRead)
def reopen_stage_for_batch(
    work_order_id: int,
    batch_id: int,
    stage: ProcessStage,
    service: Annotated[ProcessService, Depends(get_process_service)],
) -> ProcessStageWorkOrderRead:
    return service.reopen_stage(work_order_id, stage, batch_id=batch_id)


@router.post("/work-orders/{work_order_id}/packing/complete", response_model=ProcessStageWorkOrderRead)
def complete_packing(
    work_order_id: int,
    payload: PackingCompleteRequest,
    service: Annotated[ProcessService, Depends(get_process_service)],
) -> ProcessStageWorkOrderRead:
    return service.complete_packing(
        work_order_id,
        ok_quantity=payload.ok_quantity,
        correction_quantity=payload.correction_quantity,
    )


@router.post("/work-orders/{work_order_id}/batches/{batch_id}/packing/complete", response_model=ProcessStageWorkOrderRead)
def complete_packing_for_batch(
    work_order_id: int,
    batch_id: int,
    payload: PackingCompleteRequest,
    service: Annotated[ProcessService, Depends(get_process_service)],
) -> ProcessStageWorkOrderRead:
    return service.complete_packing(
        work_order_id,
        ok_quantity=payload.ok_quantity,
        correction_quantity=payload.correction_quantity,
        batch_id=batch_id,
    )
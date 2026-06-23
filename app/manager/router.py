import csv
from datetime import date
from io import StringIO
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.audit.context import StationContext, get_station_context
from app.database.session import get_db_session
from app.manager.repository import ManagerRepository
from app.manager.capacity import ShiftLength
from app.manager.schemas import (
    AutoScheduleProposal,
    CorrectionReasonReportItem,
    CycleTimeStats,
    DayCapacityRead,
    LineMeasurementStats,
    MultiDayPlanRead,
    ScheduleRuleConfigRead,
    ScheduleRuleConfigUpdate,
    ThroughputStats,
    WipAgingStats,
    WorkOrderPlanAssignRequest,
    WorkOrderProductionTypeUpdateRequest,
    WorkOrderQueuePositionUpdateRequest,
    WorkOrderQueueReorderBatchRequest,
)
from app.manager.service import ManagerService
from app.process.enums import ProductionType
from app.work_orders.schemas import WorkOrderRead

router = APIRouter(prefix="/manager", tags=["manager-work-orders"])


def get_manager_service(session: Annotated[Session, Depends(get_db_session)]) -> ManagerService:
    repository = ManagerRepository(session)
    return ManagerService(repository)


@router.get("/work-orders/unplanned", response_model=list[WorkOrderRead])
def list_unplanned_work_orders(
    service: Annotated[ManagerService, Depends(get_manager_service)],
) -> list[WorkOrderRead]:
    return service.list_unplanned_work_orders()


@router.get("/work-orders", response_model=list[WorkOrderRead])
def list_planned_work_orders(
    service: Annotated[ManagerService, Depends(get_manager_service)],
) -> list[WorkOrderRead]:
    return service.list_planned_work_orders()


@router.get("/stats/throughput", response_model=ThroughputStats)
def get_throughput_stats(
    date_from: Annotated[date, Query()],
    date_to: Annotated[date, Query()],
    station_context: Annotated[StationContext, Depends(get_station_context)],
    group_by: Annotated[Literal["day", "week", "month"], Query()] = "day",
    service: Annotated[ManagerService, Depends(get_manager_service)] = ...,
) -> ThroughputStats:
    return service.get_throughput_stats(date_from, date_to, group_by, station_context=station_context)


@router.get("/stats/cycle-time", response_model=CycleTimeStats)
def get_cycle_time_stats(
    date_from: Annotated[date, Query()],
    date_to: Annotated[date, Query()],
    station_context: Annotated[StationContext, Depends(get_station_context)],
    service: Annotated[ManagerService, Depends(get_manager_service)] = ...,
) -> CycleTimeStats:
    return service.get_cycle_time_stats(date_from, date_to, station_context=station_context)


@router.get("/stats/wip-aging", response_model=WipAgingStats)
def get_work_in_progress_aging(
    station_context: Annotated[StationContext, Depends(get_station_context)],
    service: Annotated[ManagerService, Depends(get_manager_service)] = ...,
) -> WipAgingStats:
    return service.get_work_in_progress_aging(station_context=station_context)


@router.get("/stats/line-measurements", response_model=LineMeasurementStats)
def get_line_measurements(
    date_from: Annotated[date, Query()],
    date_to: Annotated[date, Query()],
    station_context: Annotated[StationContext, Depends(get_station_context)],
    production_type: Annotated[ProductionType, Query()] = ProductionType.AUTOMATIC,
    service: Annotated[ManagerService, Depends(get_manager_service)] = ...,
) -> LineMeasurementStats:
    return service.get_line_measurements(
        date_from, date_to, production_type, station_context=station_context
    )


@router.get("/planner/day-capacity", response_model=DayCapacityRead)
def get_day_capacity(
    station_context: Annotated[StationContext, Depends(get_station_context)],
    production_type: Annotated[ProductionType, Query()] = ProductionType.AUTOMATIC,
    shift_length: Annotated[ShiftLength | None, Query()] = None,
    service: Annotated[ManagerService, Depends(get_manager_service)] = ...,
) -> DayCapacityRead:
    return service.get_day_capacity(
        production_type, shift_length, station_context=station_context
    )


@router.get("/planner/multi-day", response_model=MultiDayPlanRead)
def get_multi_day_plan(
    station_context: Annotated[StationContext, Depends(get_station_context)],
    production_type: Annotated[ProductionType, Query()] = ProductionType.AUTOMATIC,
    horizon_working_days: Annotated[int, Query(ge=1, le=60)] = 10,
    shift_length: Annotated[ShiftLength | None, Query()] = None,
    service: Annotated[ManagerService, Depends(get_manager_service)] = ...,
) -> MultiDayPlanRead:
    return service.get_multi_day_plan(
        production_type, horizon_working_days, shift_length, station_context=station_context
    )


@router.get("/corrections/reason-report", response_model=list[CorrectionReasonReportItem])
def get_correction_reason_report(
    service: Annotated[ManagerService, Depends(get_manager_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> list[CorrectionReasonReportItem]:
    return service.get_correction_reason_report(station_context=station_context)


@router.get("/corrections/reason-report/export.csv")
def export_correction_reason_report_csv(
    service: Annotated[ManagerService, Depends(get_manager_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> Response:
    return Response(
        content=_build_correction_reason_report_csv(
            service.get_correction_reason_report(station_context=station_context)
        ),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="correction-reason-report.csv"'},
    )


@router.post("/work-orders/{work_order_id}/plan", response_model=WorkOrderRead)
def assign_plan(
    work_order_id: int,
    payload: WorkOrderPlanAssignRequest,
    service: Annotated[ManagerService, Depends(get_manager_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> WorkOrderRead:
    return service.assign_plan(work_order_id, payload, station_context=station_context)


@router.patch("/work-orders/{work_order_id}/production-type", response_model=WorkOrderRead)
def update_production_type(
    work_order_id: int,
    payload: WorkOrderProductionTypeUpdateRequest,
    service: Annotated[ManagerService, Depends(get_manager_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> WorkOrderRead:
    return service.update_production_type(work_order_id, payload, station_context=station_context)


@router.patch("/work-orders/{work_order_id}/queue-position", response_model=WorkOrderRead)
def update_queue_position(
    work_order_id: int,
    payload: WorkOrderQueuePositionUpdateRequest,
    service: Annotated[ManagerService, Depends(get_manager_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> WorkOrderRead:
    return service.update_queue_position(work_order_id, payload, station_context=station_context)


@router.get("/scheduler/config", response_model=ScheduleRuleConfigRead)
def get_schedule_config(
    service: Annotated[ManagerService, Depends(get_manager_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
    production_type: Annotated[ProductionType, Query()] = ProductionType.AUTOMATIC,
) -> ScheduleRuleConfigRead:
    return service.get_schedule_config(production_type, station_context=station_context)


@router.put("/scheduler/config", response_model=ScheduleRuleConfigRead)
def update_schedule_config(
    payload: ScheduleRuleConfigUpdate,
    service: Annotated[ManagerService, Depends(get_manager_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
    production_type: Annotated[ProductionType, Query()] = ProductionType.AUTOMATIC,
) -> ScheduleRuleConfigRead:
    return service.update_schedule_config(production_type, payload, station_context=station_context)


@router.get("/scheduler/proposal", response_model=AutoScheduleProposal)
def get_auto_schedule_proposal(
    service: Annotated[ManagerService, Depends(get_manager_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
    production_type: Annotated[ProductionType, Query()] = ProductionType.AUTOMATIC,
) -> AutoScheduleProposal:
    return service.propose_auto_schedule(production_type, station_context=station_context)


@router.post("/queue/reorder", response_model=list[WorkOrderRead])
def reorder_queue(
    payload: WorkOrderQueueReorderBatchRequest,
    service: Annotated[ManagerService, Depends(get_manager_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> list[WorkOrderRead]:
    return service.reorder_queue(payload, station_context=station_context)


def _build_correction_reason_report_csv(report_items: list[CorrectionReasonReportItem]) -> str:
    output = StringIO()
    fieldnames = ["correction_reason_category", "work_order_count", "total_correction_quantity"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for item in report_items:
        writer.writerow(
            {
                "correction_reason_category": item.correction_reason_category or "",
                "work_order_count": item.work_order_count,
                "total_correction_quantity": item.total_correction_quantity,
            }
        )
    return output.getvalue()

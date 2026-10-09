from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.paints.models import Paint, PaintRun, PaintRunMember, PaintStockMovement
from app.shared import clock


class PaintRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, paint: Paint) -> Paint:
        self.session.add(paint)
        self.session.flush()
        self.session.refresh(paint)
        return paint

    def get_by_id(self, paint_id: int) -> Paint | None:
        return self.session.get(Paint, paint_id)

    def get_by_identity(self, *, ral_code: str, paint_producer: str, paint_code: str) -> Paint | None:
        statement = select(Paint).where(
            Paint.ral_code == ral_code,
            Paint.paint_producer == paint_producer,
            Paint.paint_code == paint_code,
        )
        return self.session.scalar(statement)

    def list(self, *, limit: int, offset: int) -> Sequence[Paint]:
        statement: Select[tuple[Paint]] = (
            select(Paint)
            .order_by(Paint.paint_producer.asc(), Paint.ral_code.asc(), Paint.paint_code.asc(), Paint.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return self.session.scalars(statement).all()

    def count(self) -> int:
        statement = select(func.count()).select_from(Paint)
        return self.session.scalar(statement) or 0

    def add_movement(self, movement: PaintStockMovement) -> PaintStockMovement:
        self.session.add(movement)
        self.session.flush()
        self.session.refresh(movement)
        return movement

    def list_movements(self, *, paint_id: int, limit: int, offset: int) -> Sequence[PaintStockMovement]:
        statement = (
            select(PaintStockMovement)
            .where(PaintStockMovement.paint_id == paint_id)
            .order_by(PaintStockMovement.created_at.desc(), PaintStockMovement.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return self.session.scalars(statement).all()

    def has_stock_movements(self, paint_id: int) -> bool:
        # Whether a paint has any stock movement history. A paint row is auto-created at 0 kg when a work
        # order snapshots its colour, so mere existence is not "stocked"; a real delivery/adjustment/
        # consumption movement is. The planner's hard block uses this to tell a *known-depleted* colour
        # from a never-stocked placeholder (N49-7).
        statement = select(PaintStockMovement.id).where(PaintStockMovement.paint_id == paint_id).limit(1)
        return self.session.scalar(statement) is not None

    def sum_allocated_consumption_kg(self, work_order_ids: Sequence[int]) -> float:
        # Cumulative automatic paint consumption (kg) across the given work orders: the sum of their
        # m²-shares of closed paint runs (CHANGES #22). An order in a still-open run contributes 0 until
        # the run's consumption is entered.
        if not work_order_ids:
            return 0.0
        total = self.session.scalar(
            select(func.coalesce(func.sum(PaintRunMember.allocated_kg), 0.0)).where(
                PaintRunMember.work_order_id.in_(work_order_ids),
            )
        )
        return float(total or 0.0)

    # --- Paint runs (CHANGES #22) ------------------------------------------------------------------

    def add_paint_run(self, paint_run: PaintRun) -> PaintRun:
        self.session.add(paint_run)
        self.session.flush()
        return paint_run

    def get_paint_run(self, paint_run_id: int) -> PaintRun | None:
        return self.session.get(PaintRun, paint_run_id)

    def get_latest_paint_run(self) -> PaintRun | None:
        # The newest run is the one the automatic line is currently painting (or last painted).
        return self.session.scalar(select(PaintRun).order_by(PaintRun.id.desc()).limit(1))

    def list_open_paint_runs(self) -> Sequence[PaintRun]:
        return self.session.scalars(
            select(PaintRun).where(PaintRun.closed_at.is_(None)).order_by(PaintRun.id.asc())
        ).all()

    def delete_paint_run(self, paint_run: PaintRun) -> None:
        self.session.delete(paint_run)
        self.session.flush()

    def apply_quantity_delta(self, *, paint_id: int, quantity_delta_kg: float) -> Paint | None:
        now = clock.now()
        statement = (
            update(Paint)
            .where(
                Paint.id == paint_id,
                Paint.current_quantity_kg + quantity_delta_kg >= 0,
            )
            .values(
                current_quantity_kg=Paint.current_quantity_kg + quantity_delta_kg,
                updated_at=now,
            )
        )
        result = self.session.execute(statement)
        if result.rowcount != 1:
            return None
        self.session.flush()
        return self.get_by_id(paint_id)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

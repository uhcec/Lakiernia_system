from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.work_orders.models import WorkOrderNumberCounter

_GLOBAL_COUNTER_KEY = 0


class WorkOrderNumberAllocator:
    def __init__(self, session: Session) -> None:
        self.session = session

    def allocate(self) -> str:
        allocation_time = datetime.now(UTC)
        next_value = self._increment_counter(allocation_time)
        return f"{next_value:04d}"

    def _increment_counter(self, allocation_time: datetime) -> int:
        for _ in range(2):
            next_value = self.session.execute(
                update(WorkOrderNumberCounter)
                .where(WorkOrderNumberCounter.year == _GLOBAL_COUNTER_KEY)
                .values(
                    last_value=WorkOrderNumberCounter.last_value + 1,
                    updated_at=allocation_time,
                )
                .returning(WorkOrderNumberCounter.last_value)
            ).scalar_one_or_none()
            if next_value is not None:
                return int(next_value)

            self._ensure_counter_row(allocation_time)

        raise RuntimeError("Unable to allocate work order number.")

    def _ensure_counter_row(self, allocation_time: datetime) -> None:
        dialect_name = self.session.get_bind().dialect.name
        values = {
            "year": _GLOBAL_COUNTER_KEY,
            "last_value": 0,
            "created_at": allocation_time,
            "updated_at": allocation_time,
        }

        if dialect_name == "sqlite":
            statement = sqlite_insert(WorkOrderNumberCounter).values(**values).on_conflict_do_nothing(
                index_elements=[WorkOrderNumberCounter.year]
            )
        elif dialect_name == "postgresql":
            statement = postgresql_insert(WorkOrderNumberCounter).values(**values).on_conflict_do_nothing(
                index_elements=[WorkOrderNumberCounter.year]
            )
        else:
            raise NotImplementedError(f"Unsupported database dialect for work order number allocation: {dialect_name}")

        self.session.execute(statement)
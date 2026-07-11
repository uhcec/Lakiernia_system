from datetime import datetime

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.shared import clock
from app.work_orders.models import WzNumberCounter


class WzNumberAllocator:
    """Allocates the next WZ document number as ``"{n}/{year}"`` (owner format "kolejny / rok").

    Mirrors ``WorkOrderNumberAllocator`` but keys the counter on the real calendar year, so the
    sequence resets to 1 each year. Atomic increment via ``UPDATE ... RETURNING`` with a lazy
    insert of the year row on first use.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def allocate(self) -> str:
        allocation_time = clock.now()
        year = allocation_time.year
        next_value = self._increment_counter(year, allocation_time)
        return f"{next_value}/{year}"

    def _increment_counter(self, year: int, allocation_time: datetime) -> int:
        for _ in range(2):
            next_value = self.session.execute(
                update(WzNumberCounter)
                .where(WzNumberCounter.year == year)
                .values(
                    last_value=WzNumberCounter.last_value + 1,
                    updated_at=allocation_time,
                )
                .returning(WzNumberCounter.last_value)
            ).scalar_one_or_none()
            if next_value is not None:
                return int(next_value)

            self._ensure_counter_row(year, allocation_time)

        raise RuntimeError("Unable to allocate WZ document number.")

    def _ensure_counter_row(self, year: int, allocation_time: datetime) -> None:
        dialect_name = self.session.get_bind().dialect.name
        values = {
            "year": year,
            "last_value": 0,
            "created_at": allocation_time,
            "updated_at": allocation_time,
        }

        if dialect_name == "sqlite":
            statement = sqlite_insert(WzNumberCounter).values(**values).on_conflict_do_nothing(
                index_elements=[WzNumberCounter.year]
            )
        elif dialect_name == "postgresql":
            statement = postgresql_insert(WzNumberCounter).values(**values).on_conflict_do_nothing(
                index_elements=[WzNumberCounter.year]
            )
        else:
            raise NotImplementedError(f"Unsupported database dialect for WZ number allocation: {dialect_name}")

        self.session.execute(statement)

from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.foils.models import Foil
from app.work_orders.models import WorkOrder


class FoilRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, foil: Foil) -> Foil:
        self.session.add(foil)
        self.session.flush()
        self.session.refresh(foil)
        return foil

    def get_by_id(self, foil_id: int) -> Foil | None:
        return self.session.get(Foil, foil_id)

    def get_by_code(self, code: str) -> Foil | None:
        statement = select(Foil).where(func.lower(Foil.code) == func.lower(code.strip()))
        return self.session.scalar(statement)

    def list(self, *, limit: int, offset: int, search: str | None = None) -> Sequence[Foil]:
        statement: Select[tuple[Foil]] = select(Foil).order_by(Foil.name.asc(), Foil.id.asc())
        statement = self._filter_by_search(statement, search)
        statement = statement.offset(offset).limit(limit)
        return self.session.scalars(statement).all()

    def count(self, *, search: str | None = None) -> int:
        statement = select(func.count()).select_from(Foil)
        statement = self._filter_by_search(statement, search)
        return self.session.scalar(statement) or 0

    def count_orders_for_foil(self, foil_id: int) -> int:
        statement = select(func.count()).select_from(WorkOrder).where(WorkOrder.decoral_foil_id == foil_id)
        return self.session.scalar(statement) or 0

    def delete(self, foil: Foil) -> None:
        self.session.delete(foil)

    @staticmethod
    def _filter_by_search(statement, search: str | None):
        if search is None:
            return statement
        normalized_query = search.strip()
        if not normalized_query:
            return statement
        return statement.where(Foil.name.ilike(f"%{normalized_query}%") | Foil.code.ilike(f"%{normalized_query}%"))

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

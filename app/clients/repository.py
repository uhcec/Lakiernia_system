from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.clients.models import Client
from app.work_orders.models import WorkOrder


class ClientRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, client: Client) -> Client:
        self.session.add(client)
        self.session.flush()
        self.session.refresh(client)
        return client

    def get_by_id(self, client_id: int) -> Client | None:
        return self.session.get(Client, client_id)

    def get_by_company_name(self, company_name: str) -> Client | None:
        statement = select(Client).where(func.lower(Client.company_name) == func.lower(company_name.strip()))
        return self.session.scalar(statement)

    def list(self, *, limit: int, offset: int, search: str | None = None) -> Sequence[Client]:
        statement: Select[tuple[Client]] = select(Client).order_by(Client.company_name.asc(), Client.id.asc())
        statement = self._filter_by_search(statement, search)
        statement = statement.offset(offset).limit(limit)
        return self.session.scalars(statement).all()

    def count(self, *, search: str | None = None) -> int:
        statement = select(func.count()).select_from(Client)
        statement = self._filter_by_search(statement, search)
        return self.session.scalar(statement) or 0

    def count_orders_for_company(self, company_name: str) -> int:
        statement = (
            select(func.count())
            .select_from(WorkOrder)
            .where(WorkOrder.customer_name.ilike(company_name.strip()))
        )
        return self.session.scalar(statement) or 0

    def list_orders_for_company(self, company_name: str) -> Sequence[WorkOrder]:
        statement = (
            select(WorkOrder)
            .where(WorkOrder.customer_name.ilike(company_name.strip()))
            .order_by(WorkOrder.received_date.desc(), WorkOrder.id.desc())
        )
        return self.session.scalars(statement).all()

    def delete(self, client: Client) -> None:
        self.session.delete(client)

    @staticmethod
    def _filter_by_search(statement, search: str | None):
        if search is None:
            return statement
        normalized_query = search.strip()
        if not normalized_query:
            return statement
        return statement.where(Client.company_name.ilike(f"%{normalized_query}%"))

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

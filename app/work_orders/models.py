from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.shared.enums import WorkOrderStatus


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    reference: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=WorkOrderStatus.ENTERED.value, nullable=False)
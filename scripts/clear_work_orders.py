"""Remove all work orders and related data. Keeps users, paints, and stock movements."""
from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import delete

from app.audit.models import AuditEvent
from app.core.config import get_work_order_attachments_path
from app.database import models as _models  # noqa: F401
from app.database.session import get_session_factory
from app.process.models import ProcessResourceLock, WorkOrderQuantityBatch, WorkOrderStageState
from app.work_orders.models import WorkOrder, WorkOrderAttachment, WorkOrderNumberCounter


def main() -> None:
    session_factory = get_session_factory()

    with session_factory() as session:
        session.execute(delete(AuditEvent))
        session.execute(delete(WorkOrderQuantityBatch))
        session.execute(delete(WorkOrderStageState))
        session.execute(delete(ProcessResourceLock))
        session.execute(delete(WorkOrderAttachment))
        session.execute(delete(WorkOrder))
        session.execute(delete(WorkOrderNumberCounter))
        session.commit()

    attachments_path = get_work_order_attachments_path()
    if attachments_path.exists():
        shutil.rmtree(attachments_path)
        attachments_path.mkdir(parents=True, exist_ok=True)

    print("Wszystkie zlecenia zostały usunięte.")


if __name__ == "__main__":
    main()

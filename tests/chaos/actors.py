from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from threading import Barrier

from tests.chaos.harness import LoggedApiClient


@dataclass(slots=True)
class ManagerAgent:
    client: LoggedApiClient

    def list_planned(self):
        response = self.client.get("/manager/work-orders")
        return response, response.json()

    def get_queue_revision(self) -> str:
        response, planned = self.list_planned()
        assert response.status_code == 200
        return max(item["updated_at"] for item in planned)

    def reorder(self, *, queue_revision: str, items: list[dict]):
        return self.client.post(
            "/manager/queue/reorder",
            json={"queue_revision": queue_revision, "items": items},
        )

    def update_queue_position(self, work_order_id: int, *, queue_position: int):
        return self.client.patch(
            f"/manager/work-orders/{work_order_id}/queue-position",
            json={"queue_position": queue_position},
        )

    def synchronized_reorder(self, barrier: Barrier, *, queue_revision: str, items: list[dict]):
        barrier.wait()
        return self.reorder(queue_revision=queue_revision, items=items)

    def synchronized_update_queue_position(self, barrier: Barrier, work_order_id: int, *, queue_position: int):
        barrier.wait()
        return self.update_queue_position(work_order_id, queue_position=queue_position)

    def plan(self, work_order_id: int, *, production_type: str, queue_position: int):
        return self.client.post(
            f"/manager/work-orders/{work_order_id}/plan",
            json={"production_type": production_type, "queue_position": queue_position},
        )

    def synchronized_plan(self, barrier: Barrier, work_order_id: int, *, production_type: str, queue_position: int):
        barrier.wait()
        return self.plan(work_order_id, production_type=production_type, queue_position=queue_position)


@dataclass(slots=True)
class StageOperatorAgent:
    client: LoggedApiClient

    def start_surface_preparation(self, work_order_id: int, counted_quantity: int):
        return self.client.post(
            f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/start",
            json={"counted_quantity": counted_quantity},
        )

    def finish_surface_preparation(self, work_order_id: int):
        return self.client.post(f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/finish")

    def start_hanging(self, work_order_id: int):
        return self.client.post(f"/process/work-orders/{work_order_id}/stages/HANGING/start")

    def synchronized_finish_surface_preparation(self, barrier: Barrier, work_order_id: int):
        barrier.wait()
        return self.finish_surface_preparation(work_order_id)

    def synchronized_start_hanging(self, barrier: Barrier, work_order_id: int):
        barrier.wait()
        return self.start_hanging(work_order_id)


@dataclass(slots=True)
class ChaosAgent:
    client: LoggedApiClient

    def reorder_with_stale_payload_after_barrier(self, barrier: Barrier, *, queue_revision: str, items: list[dict]):
        barrier.wait()
        return self.client.post(
            "/manager/queue/reorder",
            json={"queue_revision": queue_revision, "items": items},
        )


@dataclass(slots=True)
class OfficeAgent:
    client: LoggedApiClient

    def patch_work_order(self, work_order_id: int, payload: dict):
        return self.client.patch(f"/work-orders/{work_order_id}", json=payload)

    def synchronized_patch_work_order(self, barrier: Barrier, work_order_id: int, payload: dict):
        barrier.wait()
        return self.patch_work_order(work_order_id, payload)

    def mark_complete_arrival(self, work_order_id: int):
        return self.client.post(f"/work-orders/{work_order_id}/mark-complete-arrival")

    def synchronized_mark_complete_arrival(self, barrier: Barrier, work_order_id: int):
        barrier.wait()
        return self.mark_complete_arrival(work_order_id)

    def get_work_order(self, work_order_id: int):
        return self.client.get(f"/work-orders/{work_order_id}")

    def synchronized_get_work_order(self, barrier: Barrier, work_order_id: int):
        barrier.wait()
        return self.get_work_order(work_order_id)


@dataclass(slots=True)
class AttachmentAgent:
    client: LoggedApiClient

    def upload_pdf(self, work_order_id: int, *, filename: str):
        return self.client.post(
            f"/work-orders/{work_order_id}/attachments",
            files={"file": (filename, BytesIO(b"%PDF-1.4\n%%EOF"), "application/pdf")},
        )

    def synchronized_upload_pdf(self, barrier: Barrier, work_order_id: int, *, filename: str):
        barrier.wait()
        return self.upload_pdf(work_order_id, filename=filename)

    def delete_attachment(self, work_order_id: int, attachment_id: int):
        return self.client.delete(f"/work-orders/{work_order_id}/attachments/{attachment_id}")

    def synchronized_delete_attachment(self, barrier: Barrier, work_order_id: int, attachment_id: int):
        barrier.wait()
        return self.delete_attachment(work_order_id, attachment_id)

    def list_attachments(self, work_order_id: int):
        return self.client.get(f"/work-orders/{work_order_id}/attachments")


@dataclass(slots=True)
class PackingAgent:
    client: LoggedApiClient

    def start_packing(self, work_order_id: int):
        return self.client.post(f"/process/work-orders/{work_order_id}/stages/PACKING/start")

    def complete_packing(
        self,
        work_order_id: int,
        *,
        counted_quantity: int,
        ok_quantity: int,
        correction_quantity: int,
        batch_id: int | None = None,
        correction_reason_category: str | None = None,
    ):
        path = (
            f"/process/work-orders/{work_order_id}/batches/{batch_id}/packing/complete"
            if batch_id is not None
            else f"/process/work-orders/{work_order_id}/packing/complete"
        )
        payload = {
            "counted_quantity": counted_quantity,
            "ok_quantity": ok_quantity,
            "correction_quantity": correction_quantity,
        }
        if correction_quantity > 0:
            payload["correction_reason_category"] = correction_reason_category or "niedomalowanie"
        return self.client.post(path, json=payload)

    def synchronized_complete_packing(
        self,
        barrier: Barrier,
        work_order_id: int,
        *,
        counted_quantity: int,
        ok_quantity: int,
        correction_quantity: int,
        batch_id: int | None = None,
        correction_reason_category: str | None = None,
    ):
        barrier.wait()
        return self.complete_packing(
            work_order_id,
            counted_quantity=counted_quantity,
            ok_quantity=ok_quantity,
            correction_quantity=correction_quantity,
            batch_id=batch_id,
            correction_reason_category=correction_reason_category,
        )

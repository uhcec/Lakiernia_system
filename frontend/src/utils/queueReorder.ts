import type { ReorderQueueItemRequest, ReorderQueueRequest } from "../types/manager";
import type { ProductionTypeValue, WorkOrder } from "../types/workOrders";

interface QueueOrderedItem {
  id: number;
  queue_position: number | null;
}

function getQueuePositions(items: QueueOrderedItem[]): number[] {
  return items
    .map((item) => item.queue_position)
    .filter((queuePosition): queuePosition is number => queuePosition !== null)
    .sort((left, right) => left - right);
}

function assignQueuePositions<T extends QueueOrderedItem>(items: T[], queuePositions: number[]): T[] {
  if (items.length !== queuePositions.length) {
    return items;
  }

  return items.map((item, index) => ({
    ...item,
    queue_position: queuePositions[index],
  }));
}

export function assignSequentialQueuePositions<T extends QueueOrderedItem>(items: T[], startPosition = 1): T[] {
  return items.map((item, index) => ({
    ...item,
    queue_position: startPosition + index,
  }));
}

export function moveWorkOrderWithinQueueSlots<T extends QueueOrderedItem>(
  items: T[],
  draggedWorkOrderId: number,
  targetWorkOrderId: number,
): T[] {
  const draggedIndex = items.findIndex((item) => item.id === draggedWorkOrderId);
  const targetIndex = items.findIndex((item) => item.id === targetWorkOrderId);

  if (draggedIndex === -1 || targetIndex === -1 || draggedIndex === targetIndex) {
    return items;
  }

  const nextItems = [...items];
  const [draggedItem] = nextItems.splice(draggedIndex, 1);
  nextItems.splice(targetIndex, 0, draggedItem);

  return assignQueuePositions(nextItems, getQueuePositions(items));
}

export function buildQueueReorderPayload(
  activeItems: QueueOrderedItem[],
): ReorderQueueItemRequest[] {
  return [...activeItems]
    .filter((item): item is QueueOrderedItem & { queue_position: number } => item.queue_position !== null)
    .sort((left, right) => left.queue_position - right.queue_position)
    .map((item) => ({
      work_order_id: item.id,
      queue_position: item.queue_position,
    }));
}

export function buildQueueReorderRequest(
  activeItems: QueueOrderedItem[],
  queueRevision: string,
  productionType: ProductionTypeValue,
): ReorderQueueRequest {
  return {
    production_type: productionType,
    queue_revision: queueRevision,
    items: buildQueueReorderPayload(activeItems),
  };
}

// The queue revision is the latest planned-order updated_at, echoed verbatim so the backend can
// compare it (as a parsed datetime) against its own func.max(updated_at) for optimistic concurrency
// (manager/service.py + repository.get_planned_queue_revision). The backend serialises UTC timestamps
// and OMITS the fractional part when microseconds are zero ("...10:00:00Z" vs "...10:00:00.5Z"), so a
// plain string compare is wrong: 'Z' (0x5A) > '.' (0x2E) would rank the earlier, whole-second stamp as
// later and we'd send a stale revision (spurious 409). Compare chronologically and return the exact
// original string of the latest order. (Date precision is milliseconds; two planned orders updated
// inside the same millisecond is not reachable at this shop's human queue pace.)
export function getQueueRevisionFromPlannedOrders(workOrders: WorkOrder[]): string | null {
  if (workOrders.length === 0) {
    return null;
  }

  return workOrders.reduce(
    (latest, workOrder) => (Date.parse(workOrder.updated_at) > Date.parse(latest.updated_at) ? workOrder : latest),
    workOrders[0],
  ).updated_at;
}

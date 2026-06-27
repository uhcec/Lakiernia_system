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

export function getQueueRevisionFromPlannedOrders(workOrders: WorkOrder[]): string | null {
  if (workOrders.length === 0) {
    return null;
  }

  return workOrders.reduce(
    (latestRevision, workOrder) => (workOrder.updated_at > latestRevision ? workOrder.updated_at : latestRevision),
    workOrders[0].updated_at,
  );
}

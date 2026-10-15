import type { StageWorkOrder } from "../types/process";

// CHANGES #27 (owner 2026-10-15): the hanging station lists its queue grouped by paint. A group is a
// stretch of orders that stand one after another in the manager's queue and share the same paint —
// the same identity a paint run uses (RAL + producer + paint code, `app/process/paint_runs.py:67`).
// Owner chose (a): the groups follow the queue, so the same colour split by another one is two groups;
// the hanging station never reorders the manager's plan.
export interface HangingPaintGroup {
  key: string;
  ralCode: string;
  paintProducer: string;
  paintCode: string | null;
  workOrders: StageWorkOrder[];
}

function paintKey(workOrder: StageWorkOrder): string | null {
  // An order without a paint code never joins a paint run, so it never shares a group either.
  if (!workOrder.paint_code) {
    return null;
  }
  return [workOrder.ral_code, workOrder.paint_producer, workOrder.paint_code].join("\u0000");
}

function samePaint(left: StageWorkOrder, right: StageWorkOrder): boolean {
  return (
    left.ral_code === right.ral_code &&
    left.paint_producer === right.paint_producer &&
    left.paint_code === right.paint_code
  );
}

// CHANGES #29: why "Rozpocznij" is greyed for a not-started order, or null when it may start. Mirrors
// the backend (`app/process/resource_locks.py` hanging_start_block), which still refuses on its own:
// up to `limit` orders hang at once, and only with the same paint as the ones already hanging.
export function getHangingStartBlock(
  workOrder: StageWorkOrder,
  hangingNow: StageWorkOrder[],
  limit: number,
): string | null {
  const others = hangingNow.filter((other) => other.id !== workOrder.id);
  if (others.length >= limit) {
    return limit === 1 ? "Zawieszanie zajęte" : `Zawieszanie pełne (${others.length}/${limit})`;
  }
  if (others.some((other) => !samePaint(other, workOrder))) {
    return "Na zawieszaniu inna farba";
  }
  return null;
}

export function groupHangingQueue(workOrders: StageWorkOrder[]): HangingPaintGroup[] {
  const groups: HangingPaintGroup[] = [];
  let previousKey: string | null = null;

  for (const workOrder of workOrders) {
    const key = paintKey(workOrder);
    const currentGroup = groups[groups.length - 1];
    if (currentGroup && key !== null && key === previousKey) {
      currentGroup.workOrders.push(workOrder);
    } else {
      groups.push({
        key: `${groups.length}-${workOrder.id}-${workOrder.batch_id ?? workOrder.id}`,
        ralCode: workOrder.ral_code,
        paintProducer: workOrder.paint_producer,
        paintCode: workOrder.paint_code,
        workOrders: [workOrder],
      });
    }
    previousKey = key;
  }

  return groups;
}

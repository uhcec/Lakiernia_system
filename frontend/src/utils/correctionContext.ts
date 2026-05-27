import { fetchWorkOrder } from "../api/workOrdersApi";

export interface CorrectionContext {
  parentOrderNumber: string | null;
  parentTotalQuantity: number | null;
}

interface CorrectionContextCarrier {
  id: number;
  is_correction: boolean;
}

export async function loadCorrectionContexts(
  items: CorrectionContextCarrier[],
): Promise<{ contexts: Record<number, CorrectionContext>; failedCount: number }> {
  const correctionIds = [...new Set(items.filter((item) => item.is_correction).map((item) => item.id))];

  if (correctionIds.length === 0) {
    return { contexts: {}, failedCount: 0 };
  }

  const results = await Promise.allSettled(
    correctionIds.map(async (workOrderId) => {
      const detail = await fetchWorkOrder(workOrderId);
      return {
        workOrderId,
        parentOrderNumber: detail.parent_order?.order_number ?? null,
        parentTotalQuantity: detail.parent_order?.total_quantity ?? null,
      };
    }),
  );

  return results.reduce(
    (acc, result) => {
      if (result.status === "fulfilled") {
        acc.contexts[result.value.workOrderId] = {
          parentOrderNumber: result.value.parentOrderNumber,
          parentTotalQuantity: result.value.parentTotalQuantity,
        };
      } else {
        acc.failedCount += 1;
      }

      return acc;
    },
    { contexts: {} as Record<number, CorrectionContext>, failedCount: 0 },
  );
}
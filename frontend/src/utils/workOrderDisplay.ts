import type { StageWorkOrder } from "../types/process";
import type { WorkOrder, WorkOrderRelationSummary } from "../types/workOrders";

type DisplayableWorkOrder = Pick<WorkOrder, "order_number" | "ral_code" | "total_area_m2" | "customer_name">;
type DisplayableStageWorkOrder = Pick<StageWorkOrder, "order_number" | "customer_name"> & {
  ral_code?: string | null;
  total_area_m2?: number | null;
};
type DisplayableRelationSummary = Pick<WorkOrderRelationSummary, "order_number" | "customer_name" | "ral_code" | "total_area_m2">;

function formatArea(totalAreaM2: number | null | undefined): string {
  if (totalAreaM2 === null || totalAreaM2 === undefined) {
    return "-";
  }

  return `${totalAreaM2.toLocaleString("pl-PL")} m2`;
}

export function formatWorkOrderPrimaryInfo(workOrder: DisplayableWorkOrder | DisplayableStageWorkOrder | DisplayableRelationSummary): string {
  return [
    workOrder.order_number,
    workOrder.ral_code ?? "-",
    formatArea(workOrder.total_area_m2),
    workOrder.customer_name || "Brak firmy",
  ].join(" · ");
}

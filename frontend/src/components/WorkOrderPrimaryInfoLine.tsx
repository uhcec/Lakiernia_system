import type { StageWorkOrder } from "../types/process";
import type { WorkOrder, WorkOrderRelationSummary } from "../types/workOrders";
import { RalColorDot } from "./RalColorDot";

type DisplayableWorkOrder =
  | Pick<WorkOrder, "order_number" | "ral_code" | "total_area_m2" | "customer_name" | "completed_quantity" | "total_quantity">
  | (Pick<StageWorkOrder, "order_number" | "customer_name" | "total_quantity" | "completed_quantity"> & {
      ral_code?: string | null;
      total_area_m2?: number | null;
    })
  | Pick<WorkOrderRelationSummary, "order_number" | "customer_name" | "ral_code" | "total_area_m2" | "completed_quantity" | "total_quantity">;

function formatArea(totalAreaM2: number | null | undefined): string {
  if (totalAreaM2 == null) return "-";
  return `${totalAreaM2.toLocaleString("pl-PL")} m2`;
}

function hasPendingCorrections(wo: DisplayableWorkOrder): boolean {
  return wo.completed_quantity > 0 && wo.completed_quantity < wo.total_quantity;
}

export function WorkOrderPrimaryInfoLine({ workOrder }: { workOrder: DisplayableWorkOrder }) {
  const ralCode = "ral_code" in workOrder ? workOrder.ral_code : null;
  const pending = hasPendingCorrections(workOrder);
  const displayNumber = pending ? `P${workOrder.order_number}` : workOrder.order_number;

  return (
    <>
      <span className={pending ? "font-semibold text-amber-700" : undefined}>
        {displayNumber}
      </span>
      {pending && (
        <span className="ml-1 text-xs font-medium text-amber-600">
          ({workOrder.completed_quantity}/{workOrder.total_quantity})
        </span>
      )}
      {" · "}
      <span className="inline-flex items-center gap-1.5">
        <RalColorDot ralCode={ralCode} />
        {ralCode ?? "-"}
      </span>
      {" · "}
      {formatArea("total_area_m2" in workOrder ? workOrder.total_area_m2 : null)}
      {" · "}
      {workOrder.customer_name || "Brak firmy"}
    </>
  );
}

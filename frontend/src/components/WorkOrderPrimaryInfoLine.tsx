import type { StageWorkOrder } from "../types/process";
import type { WorkOrder, WorkOrderRelationSummary } from "../types/workOrders";
import { formatDisplayOrderNumber, isPartiallyComplete } from "../utils/workOrderDisplay";
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

export function WorkOrderPrimaryInfoLine({ workOrder }: { workOrder: DisplayableWorkOrder }) {
  const ralCode = "ral_code" in workOrder ? workOrder.ral_code : null;
  const pending = isPartiallyComplete(workOrder);
  const displayNumber = formatDisplayOrderNumber({
    order_number: workOrder.order_number,
    completed_quantity: workOrder.completed_quantity,
    total_quantity: workOrder.total_quantity,
    is_decoral_incomplete: (workOrder as { is_decoral_incomplete?: boolean }).is_decoral_incomplete,
  });

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

import type { StageWorkOrder } from "../types/process";
import type { WorkOrder, WorkOrderRelationSummary } from "../types/workOrders";
import { RalColorDot } from "./RalColorDot";

type DisplayableWorkOrder =
  | Pick<WorkOrder, "order_number" | "ral_code" | "total_area_m2" | "customer_name">
  | (Pick<StageWorkOrder, "order_number" | "customer_name"> & {
      ral_code?: string | null;
      total_area_m2?: number | null;
    })
  | Pick<WorkOrderRelationSummary, "order_number" | "customer_name" | "ral_code" | "total_area_m2">;

function formatArea(totalAreaM2: number | null | undefined): string {
  if (totalAreaM2 == null) return "-";
  return `${totalAreaM2.toLocaleString("pl-PL")} m2`;
}

export function WorkOrderPrimaryInfoLine({ workOrder }: { workOrder: DisplayableWorkOrder }) {
  const ralCode = "ral_code" in workOrder ? workOrder.ral_code : null;

  return (
    <>
      {workOrder.order_number}
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

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

export function getWorkOrderStatusSummary(workOrder: WorkOrder): string {
  switch (workOrder.process_status.value) {
    case "TO_BE_PLANNED":
      return "Do zaplanowania";
    case "INCOMPLETE":
      return "Niekompletne";
    case "SURFACE_PREPARATION":
      return "W przygotowaniu";
    case "HANGING":
      return "W zawieszaniu";
    case "PRODUCTION_MANUAL":
    case "PRODUCTION_AUTOMATIC":
      return "W produkcji";
    case "DECORAL_PRODUCTION":
      return "W Decoralu";
    case "PACKING":
      return "W pakowaniu";
    case "WAITING_FOR_CORRECTIONS":
      return "Czeka na poprawki";
    case "READY":
      return "Gotowe";
  }
}

export function getWorkOrderProgressText(workOrder: WorkOrder): string {
  return `${workOrder.total_progress_quantity} / ${workOrder.total_quantity} szt.`;
}

export function getHistoricalWorkOrderResultText(workOrder: WorkOrder): string {
  return `Wynik końcowy: ${workOrder.completed_quantity} szt.`;
}

export function formatQuantityDifference(quantityDifference: number): string {
  return quantityDifference > 0 ? `+${quantityDifference}` : String(quantityDifference);
}

export function getWorkOrderDiscrepancyText(workOrder: WorkOrder): string | null {
  if (workOrder.surface_preparation_counted_quantity === null || workOrder.surface_preparation_quantity_difference === null) {
    return null;
  }

  if (workOrder.surface_preparation_quantity_difference === 0) {
    return null;
  }

  return `Przygotowanie: zadeklarowano ${workOrder.total_quantity}, policzono ${workOrder.surface_preparation_counted_quantity} (${formatQuantityDifference(workOrder.surface_preparation_quantity_difference)} szt.)`;
}

export function getWorkOrderActiveCorrectionsText(workOrder: WorkOrder): string | null {
  if (workOrder.pending_correction_quantity <= 0) {
    return null;
  }

  return `Poprawki: ${workOrder.pending_correction_quantity} szt. w toku`;
}

export function getWorkOrderCorrectionContextText(workOrder: WorkOrder): string | null {
  if (!workOrder.is_correction) {
    return null;
  }

  if (workOrder.parent_order) {
    return `Poprawka do ${workOrder.parent_order.order_number} · ${workOrder.total_quantity} szt. z ${workOrder.parent_order.total_quantity}`;
  }

  return `Poprawka · ${workOrder.total_quantity} szt.`;
}

export type DisplayBadgeTone = "neutral" | "info" | "warning" | "success" | "accent" | "danger";

export interface DisplayBadge {
  label: string;
  tone: DisplayBadgeTone;
}

export function getWorkOrderBadgeStack(workOrder: WorkOrder): DisplayBadge[] {
  const badges: DisplayBadge[] = [];

  if (workOrder.is_correction) {
    badges.push({ label: "POPRAWKA", tone: "warning" });
  }

  if (workOrder.coating_type.value === "DECORAL") {
    badges.push({ label: "DECORAL", tone: "accent" });
  }

  if (workOrder.production_type?.value === "AUTOMATIC") {
    badges.push({ label: "AUTOMAT", tone: "info" });
  }

  if (workOrder.production_type?.value === "MANUAL") {
    badges.push({ label: "RĘCZNA", tone: "neutral" });
  }

  if (workOrder.process_status.value === "READY") {
    badges.push({
      label: workOrder.is_released_to_client ? "WYDANE" : "DO WYDANIA",
      tone: workOrder.is_released_to_client ? "success" : "warning",
    });
  }

  return badges;
}

export function getWorkOrderAttentionBadges(workOrder: WorkOrder): DisplayBadge[] {
  const badges: DisplayBadge[] = [];
  const today = new Date();

  if (workOrder.process_status.value === "INCOMPLETE") {
    badges.push({ label: "NIEKOMPLETNE", tone: "danger" });
  }

  if (workOrder.process_status.value === "WAITING_FOR_CORRECTIONS") {
    badges.push({ label: "WYMAGA UWAGI", tone: "warning" });
  }

  if (workOrder.queue_blocked_reason) {
    badges.push({ label: `CZEKA: ${workOrder.queue_blocked_reason}`, tone: "warning" });
  }

  if (workOrder.surface_preparation_quantity_difference !== null && workOrder.surface_preparation_quantity_difference !== 0) {
    badges.push({ label: `RÓŻNICA: ${formatQuantityDifference(workOrder.surface_preparation_quantity_difference)} SZT.`, tone: "warning" });
  }

  if (workOrder.planned_pickup_date && workOrder.process_status.value !== "READY") {
    const pickupDate = new Date(workOrder.planned_pickup_date);
    if (pickupDate < today) {
      badges.push({ label: "PO TERMINIE", tone: "danger" });
    }
  }

  return badges;
}

export function getStageWorkOrderBadgeStack(workOrder: StageWorkOrder): DisplayBadge[] {
  const badges: DisplayBadge[] = [];

  if (workOrder.is_correction) {
    badges.push({ label: "POPRAWKA", tone: "warning" });
  }

  if (workOrder.coating_type.value === "DECORAL") {
    badges.push({ label: "DECORAL", tone: "accent" });
  }

  if (workOrder.production_type?.value === "AUTOMATIC") {
    badges.push({ label: "AUTOMAT", tone: "info" });
  }

  if (workOrder.production_type?.value === "MANUAL") {
    badges.push({ label: "RĘCZNA", tone: "neutral" });
  }

  return badges;
}

export function getStageWorkOrderProgressText(workOrder: StageWorkOrder): string {
  const current = workOrder.batch_quantity ?? workOrder.current_active_quantity;
  return `${current} / ${workOrder.total_quantity} szt.`;
}

export function getHistoricalStageWorkOrderResultText(workOrder: StageWorkOrder): string {
  const finalQuantity = workOrder.counted_quantity ?? workOrder.batch_quantity ?? workOrder.planned_quantity;
  return `Wynik końcowy: ${finalQuantity} szt.`;
}

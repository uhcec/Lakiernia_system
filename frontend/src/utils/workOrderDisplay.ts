import type { StageWorkOrder } from "../types/process";
import type { WorkOrder, WorkOrderRelationSummary } from "../types/workOrders";
import type { CorrectionContext } from "./correctionContext";

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

  if (workOrder.work_order_kind.value === "PRZEMALOWANKA") {
    badges.push({ label: "PRZEMALOWANKA", tone: "danger" });
  }

  if (workOrder.is_ocynk) {
    badges.push({ label: "OCYNK", tone: "info" });
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

  if (workOrder.is_overdue) {
    badges.push({ label: "PO TERMINIE", tone: "danger" });
  }

  if (workOrder.quantity_leak_flagged) {
    badges.push({ label: "WYCIEK ILOŚCI", tone: "danger" });
  }

  return badges;
}

export function getStageWorkOrderBadgeStack(workOrder: StageWorkOrder): DisplayBadge[] {
  const badges: DisplayBadge[] = [];

  if (workOrder.is_correction) {
    badges.push({ label: "POPRAWKA", tone: "warning" });
  }

  if (workOrder.work_order_kind.value === "PRZEMALOWANKA") {
    badges.push({ label: "PRZEMALOWANKA", tone: "danger" });
  }

  if (workOrder.is_ocynk) {
    badges.push({ label: "OCYNK", tone: "info" });
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

// ── Shared display helpers (de-duplicated from the stage-completion pages — FRONTEND_TRIAGE C3/C4) ──

interface PartiallyCompletable {
  completed_quantity: number;
  total_quantity: number;
}

/** An order with some — but not all — of its pieces credited (a partial / correction-in-flight state). */
export function isPartiallyComplete(workOrder: PartiallyCompletable): boolean {
  return workOrder.completed_quantity > 0 && workOrder.completed_quantity < workOrder.total_quantity;
}

interface DisplayOrderNumber extends PartiallyCompletable {
  order_number: string;
  is_decoral_incomplete?: boolean | null;
}

/**
 * The order number as the boards show it: `N…` for a Decoral-incomplete root, `P…` for a partially-done
 * order not already P-prefixed, else the raw number. One definition for all boards (was copy-pasted in 5
 * places). The prefix meaning is reconstructed here, not supplied by the backend.
 */
export function formatDisplayOrderNumber(workOrder: DisplayOrderNumber): string {
  if (workOrder.is_decoral_incomplete) {
    return `N${workOrder.order_number}`;
  }
  if (!workOrder.order_number.startsWith("P") && isPartiallyComplete(workOrder)) {
    return `P${workOrder.order_number}`;
  }
  return workOrder.order_number;
}

interface CorrectionDisplayable {
  is_correction: boolean;
  is_correction_round: boolean;
  order_number: string;
  total_quantity: number;
}

export function buildCorrectionReference(workOrder: CorrectionDisplayable, context: CorrectionContext | undefined): string {
  if (workOrder.is_correction_round) {
    return `Poprawka — runda ${workOrder.order_number}`;
  }
  if (!workOrder.is_correction) {
    return "";
  }
  if (context?.parentOrderNumber) {
    return `Poprawka do ${context.parentOrderNumber}`;
  }
  return "Poprawka do zlecenia nadrzędnego";
}

export function buildCorrectionQuantityContext(workOrder: CorrectionDisplayable, context: CorrectionContext | undefined): string {
  if (workOrder.is_correction_round) {
    return `${workOrder.total_quantity} szt. poprawki`;
  }
  if (!workOrder.is_correction) {
    return "";
  }
  if (typeof context?.parentTotalQuantity === "number") {
    return `${workOrder.total_quantity} szt. poprawki z ${context.parentTotalQuantity}`;
  }
  return `${workOrder.total_quantity} szt. poprawki`;
}

export function buildMergedCorrectionDeltaText(workOrder: CorrectionDisplayable, context: CorrectionContext | undefined): string {
  if (typeof context?.parentTotalQuantity === "number") {
    return `Poprawiono ${workOrder.total_quantity} z ${context.parentTotalQuantity} szt.`;
  }
  return `Poprawiono ${workOrder.total_quantity} szt.`;
}

/** Tailwind classes for a DisplayBadge tone (the badge stacks on every board). */
export function badgeClasses(tone: DisplayBadgeTone): string {
  switch (tone) {
    case "info":
      return "bg-sky-100 text-sky-800";
    case "warning":
      return "bg-amber-100 text-amber-800";
    case "success":
      return "bg-emerald-100 text-emerald-700";
    case "accent":
      return "bg-violet-100 text-violet-800";
    case "danger":
      return "bg-rose-100 text-rose-700";
    case "neutral":
      return "bg-slate-100 text-slate-700";
  }
}

export type BalanceTone = "neutral" | "success" | "warning";

/** Tailwind classes for a quantity-balance box tone (packing / Decoral correction split). */
export function balanceClasses(tone: BalanceTone): string {
  switch (tone) {
    case "success":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "warning":
      return "border-amber-200 bg-amber-50 text-amber-800";
    case "neutral":
      return "border-line bg-mist text-steel";
  }
}

/** Parse a quantity draft string: blank → 0, otherwise the numeric value (validation happens at submit). */
export function parseQuantity(value: string): number {
  if (value.trim() === "") {
    return 0;
  }
  return Number(value);
}

import type { QueueNamespaceValue, WorkOrderKindValue, WorkOrderOption, ProductionTypeValue, WorkOrderAttachmentSummary } from "./workOrders";
import type { FoilSummary } from "./foils";

export type ProcessStageValue =
  | "SURFACE_PREPARATION"
  | "HANGING"
  | "PRODUCTION"
  | "DECORAL_PRODUCTION"
  | "PACKING";

export type StageStatusValue = "NOT_STARTED" | "IN_PROGRESS" | "DONE";

export interface StageStatusView {
  value: StageStatusValue;
  label: string;
}

export interface ProcessStageStatus {
  stage: ProcessStageValue;
  status: StageStatusView;
}

export interface StageWorkOrder {
  id: number;
  batch_id: number | null;
  is_correction: boolean;
  is_correction_round: boolean;
  is_historical_correction: boolean;
  is_decoral_incomplete?: boolean;
  work_order_kind: WorkOrderOption<WorkOrderKindValue>;
  is_ocynk: boolean;
  order_number: string;
  title: string;
  ral_code: string;
  paint_code: string | null;
  paint_producer: string;
  current_paint_stock_quantity_kg?: number | null;
  paint_stock_snapshot_quantity_kg?: number | null;
  consumed_paint_quantity_kg: number;
  total_area_m2: number | null;
  total_quantity: number;
  completed_quantity: number;
  current_active_quantity: number;
  operational_quantity: number;
  batch_quantity: number | null;
  planned_quantity: number;
  counted_quantity: number | null;
  quantity_difference: number | null;
  customer_name: string | null;
  profiles_quantity: number | null;
  profiles_to_count: boolean;
  accessories_quantity: number | null;
  accessories_to_count: boolean;
  queue_position: number | null;
  // Shared-stage derivation (N49-10): at SURFACE_PREPARATION and PACKING the backend supplies a line
  // label + derived order, so the frontend renders the label instead of the ambiguous per-line `Poz.`.
  shared_stage_line_label: string | null;
  is_next_at_shared_stage: boolean;
  queue_namespace: WorkOrderOption<QueueNamespaceValue>;
  production_type: WorkOrderOption<ProductionTypeValue> | null;
  coating_type: WorkOrderOption<"RAL" | "DECORAL">;
  decoral_foil?: FoilSummary | null;
  technical_drawings: WorkOrderAttachmentSummary[];
  batch_type: "MAIN" | "CORRECTION" | null;
  batch_is_partial: boolean;
  is_being_packed: boolean;
  holds_packing_slot: boolean;
  packing_slots_total: number;
  can_complete_packing: boolean;
  packing_blocked_reason: string | null;
  stage_status: ProcessStageStatus;
}

// CHANGES #22: same-paint orders hung back-to-back on the automatic line form one paint run; its
// consumption is entered once and split onto the orders by m².
export interface PaintRunMember {
  work_order_id: number;
  order_number: string;
  customer_name: string;
  area_m2: number;
  allocated_kg: number | null;
  is_hanging: boolean;
}

export interface PaintRun {
  id: number;
  ral_code: string;
  paint_producer: string;
  paint_code: string;
  created_at: string;
  closed_at: string | null;
  consumed_kg: number | null;
  total_area_m2: number;
  paint_stock_kg: number;
  // The newest run = the paint the line is on now. An open run that is not current is overdue.
  is_current: boolean;
  hanging_in_progress: boolean;
  next_in_queue_same_paint: boolean;
  members: PaintRunMember[];
}

export interface PaintRunsOverview {
  runs: PaintRun[];
}

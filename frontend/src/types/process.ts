import type { WorkOrderOption, ProductionTypeValue } from "./workOrders";

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
  order_number: string;
  title: string;
  total_quantity: number;
  current_active_quantity: number;
  customer_name: string | null;
  queue_position: number | null;
  production_type: WorkOrderOption<ProductionTypeValue> | null;
  coating_type: WorkOrderOption<"RAL" | "DECORAL">;
  stage_status: ProcessStageStatus;
}
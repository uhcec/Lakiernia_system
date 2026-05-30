import type { QueueNamespaceValue, WorkOrderOption, ProductionTypeValue } from "./workOrders";

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
  is_historical_correction: boolean;
  order_number: string;
  title: string;
  ral_code: string;
  paint_producer: string;
  total_area_m2: number | null;
  total_quantity: number;
  current_active_quantity: number;
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
  queue_namespace: WorkOrderOption<QueueNamespaceValue>;
  production_type: WorkOrderOption<ProductionTypeValue> | null;
  coating_type: WorkOrderOption<"RAL" | "DECORAL">;
  batch_type: "MAIN" | "CORRECTION" | null;
  batch_is_partial: boolean;
  stage_status: ProcessStageStatus;
}
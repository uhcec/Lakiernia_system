export type WorkOrderStatusValue = "ENTERED" | "ASSIGNED" | "IN_PROGRESS" | "FINISHED";
export type ProductionTypeValue = "MANUAL" | "AUTOMATIC";
export type CoatingTypeValue = "RAL" | "DECORAL";
export type QuantityBatchTypeValue = "MAIN" | "CORRECTION";
export type ProcessStatusValue =
  | "TO_BE_PLANNED"
  | "SURFACE_PREPARATION"
  | "HANGING"
  | "PRODUCTION_MANUAL"
  | "PRODUCTION_AUTOMATIC"
  | "DECORAL_PRODUCTION"
  | "PACKING"
  | "READY";
export type ProcessStageValue =
  | "SURFACE_PREPARATION"
  | "HANGING"
  | "PRODUCTION"
  | "DECORAL_PRODUCTION"
  | "PACKING";
export type StageStatusValue = "NOT_STARTED" | "IN_PROGRESS" | "DONE";

export interface WorkOrderStatus {
  value: WorkOrderStatusValue;
  label: string;
}

export interface ProcessStatus {
  value: ProcessStatusValue;
  label: string;
}

export interface ProcessStageInfo {
  value: ProcessStageValue;
  label: string;
}

export interface StageStatusInfo {
  value: StageStatusValue;
  label: string;
}

export interface WorkOrderStageState {
  stage: ProcessStageInfo;
  status: StageStatusInfo;
}

export interface WorkOrderOption<TValue extends string> {
  value: TValue;
  label: string;
}

export interface WorkOrderQuantityBatch {
  id: number;
  quantity: number;
  type: WorkOrderOption<QuantityBatchTypeValue>;
  parent_batch_id: number | null;
  is_active: boolean;
  is_finished: boolean;
  created_at: string;
}

export interface WorkOrder {
  id: number;
  order_number: string;
  title: string;
  total_quantity: number;
  current_active_quantity: number;
  description: string | null;
  customer_name: string | null;
  // Legacy backend field kept only for compatibility; active UI uses process_status and stage_states.
  status: WorkOrderStatus;
  process_status: ProcessStatus;
  coating_type: WorkOrderOption<CoatingTypeValue>;
  production_type: WorkOrderOption<ProductionTypeValue> | null;
  queue_position: number | null;
  stage_states: WorkOrderStageState[];
  batches: WorkOrderQuantityBatch[];
  due_date: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkOrdersListResponse {
  items: WorkOrder[];
  total: number;
  limit: number;
  offset: number;
}

export interface CreateWorkOrderRequest {
  title: string;
  coating_type: CoatingTypeValue;
  total_quantity?: number;
  description?: string;
  customer_name?: string;
  due_date?: string;
  notes?: string;
}
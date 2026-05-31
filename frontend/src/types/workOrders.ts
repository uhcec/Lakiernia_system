export type WorkOrderStatusValue = "ENTERED" | "INCOMPLETE" | "ASSIGNED" | "IN_PROGRESS" | "FINISHED";
export type ProductionTypeValue = "MANUAL" | "AUTOMATIC";
export type CoatingTypeValue = "RAL" | "DECORAL";
export type QuantityBatchTypeValue = "MAIN" | "CORRECTION";
export type QueueNamespaceValue = "MAIN" | "CORRECTIONS";
export type ProcessStatusValue =
  | "TO_BE_PLANNED"
  | "INCOMPLETE"
  | "SURFACE_PREPARATION"
  | "HANGING"
  | "PRODUCTION_MANUAL"
  | "PRODUCTION_AUTOMATIC"
  | "DECORAL_PRODUCTION"
  | "PACKING"
  | "WAITING_FOR_CORRECTIONS"
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

export interface WorkOrderAttachment {
  id: number;
  work_order_id: number;
  original_filename: string;
  stored_filename: string;
  storage_path: string;
  content_type: string;
  file_size: number;
  attachment_type: string | null;
  description: string | null;
  uploaded_at: string;
}

export interface WorkOrderRelationSummary {
  id: number;
  order_number: string;
  external_order_number: string | null;
  title: string;
  customer_name: string;
  ral_code: string;
  total_area_m2: number | null;
  total_quantity: number;
  completed_quantity: number;
  current_active_quantity: number;
  is_correction: boolean;
  is_historical_correction: boolean;
  correction_reason_category: string | null;
  correction_reason_note: string | null;
  process_status: ProcessStatus;
}

export interface WorkOrder {
  id: number;
  order_number: string;
  external_order_number: string | null;
  title: string;
  total_quantity: number;
  completed_quantity: number;
  current_active_quantity: number;
  waiting_ok_quantity: number;
  pending_correction_quantity: number;
  total_progress_quantity: number;
  is_correction: boolean;
  is_historical_correction: boolean;
  correction_reason_category: string | null;
  correction_reason_note: string | null;
  parent_order: WorkOrderRelationSummary | null;
  correction_orders: WorkOrderRelationSummary[];
  description: string | null;
  customer_name: string;
  ral_code: string;
  paint_producer: string;
  status: WorkOrderStatus;
  process_status: ProcessStatus;
  queue_blocked_by_resource: string | null;
  queue_blocked_reason: string | null;
  coating_type: WorkOrderOption<CoatingTypeValue>;
  production_type: WorkOrderOption<ProductionTypeValue> | null;
  queue_namespace: WorkOrderOption<QueueNamespaceValue>;
  queue_position: number | null;
  stage_states: WorkOrderStageState[];
  batches: WorkOrderQuantityBatch[];
  received_date: string;
  planned_pickup_date: string | null;
  is_released_to_client: boolean;
  released_to_client_at: string | null;
  total_area_m2: number | null;
  is_incomplete_on_arrival: boolean;
  surface_preparation_counted_quantity: number | null;
  surface_preparation_quantity_difference: number | null;
  profiles_quantity: number | null;
  profiles_to_count: boolean;
  accessories_quantity: number | null;
  accessories_to_count: boolean;
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
  title?: string;
  external_order_number?: string;
  coating_type: CoatingTypeValue;
  total_quantity?: number;
  customer_name: string;
  ral_code: string;
  paint_producer: string;
  received_date: string;
  planned_pickup_date?: string;
  total_area_m2?: number;
  is_incomplete_on_arrival?: boolean;
  profiles_quantity?: number;
  profiles_to_count: boolean;
  accessories_quantity?: number;
  accessories_to_count: boolean;
  description?: string;
  notes?: string;
}
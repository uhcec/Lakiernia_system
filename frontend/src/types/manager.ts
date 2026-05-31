import type { ProductionTypeValue } from "./workOrders";

export interface AssignWorkOrderPlanRequest {
  production_type: ProductionTypeValue;
  queue_position: number;
}

export interface UpdateQueuePositionRequest {
  queue_position: number;
}

export interface ReorderQueueItemRequest {
  work_order_id: number;
  queue_position: number;
}

export interface ReorderQueueRequest {
  queue_revision: string;
  items: ReorderQueueItemRequest[];
}

export interface CorrectionReasonReportItem {
  correction_reason_category: string | null;
  work_order_count: number;
  total_correction_quantity: number;
}
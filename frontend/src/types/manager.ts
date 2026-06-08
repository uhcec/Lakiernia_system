import type { ProductionTypeValue } from "./workOrders";

export interface AssignWorkOrderPlanRequest {
  production_type: ProductionTypeValue;
  queue_position: number;
}

export interface UpdateQueuePositionRequest {
  queue_position: number;
}

export interface UpdateProductionTypeRequest {
  production_type: ProductionTypeValue;
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

export interface ThroughputPeriod {
  period_start: string;
  period_label: string;
  m2_manual: number;
  m2_automatic: number;
  m2_decoral: number;
  m2_total: number;
  orders_count: number;
  correction_pieces: number;
  correction_orders_count: number;
}

export interface ThroughputStats {
  periods: ThroughputPeriod[];
  totals: ThroughputPeriod;
  orders_without_m2_count: number;
}
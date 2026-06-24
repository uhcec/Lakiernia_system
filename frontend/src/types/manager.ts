import type { ProductionTypeValue, WorkOrder } from "./workOrders";

export interface AssignWorkOrderPlanRequest {
  production_type: ProductionTypeValue;
  // Omitted → the order is appended to the end of the selected line's queue.
  queue_position?: number;
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
  production_type: ProductionTypeValue;
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
  m2_ral_only: number;
  m2_decoral: number;
  m2_decoral_pass: number;
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

export interface CycleTimeSegment {
  key: string;
  label: string;
  average_seconds: number;
  total_seconds: number;
  orders_count: number;
}

export interface CycleTimeBreakdown {
  by_method: CycleTimeSegment[];
  by_coating: CycleTimeSegment[];
}

export interface StageCycleTime {
  stage: string;
  stage_label: string;
  average_seconds: number;
  total_seconds: number;
  orders_count: number;
  average_wait_before_seconds: number | null;
  wait_orders_count: number;
  breakdown: CycleTimeBreakdown;
}

export interface CycleTimeStats {
  date_from: string;
  date_to: string;
  orders_count: number;
  overall_average_seconds: number | null;
  stages: StageCycleTime[];
  overall_breakdown: CycleTimeBreakdown;
}

export interface WipAgingItem {
  work_order_id: number;
  order_number: string;
  customer_name: string | null;
  stage: string;
  stage_label: string;
  production_type: string | null;
  coating_type: string | null;
  queue_position: number | null;
  age_seconds: number;
}

export interface WipAgingSegment {
  key: string;
  label: string;
  orders_count: number;
}

export interface WipAgingBreakdown {
  by_method: WipAgingSegment[];
  by_coating: WipAgingSegment[];
}

export interface WipAgingStats {
  generated_at: string;
  items: WipAgingItem[];
  breakdown: WipAgingBreakdown;
}

export type ScheduleRuleKey = "colour" | "deadline" | "changeover";

export interface ScheduleRuleConfigItem {
  key: ScheduleRuleKey;
  label: string;
  description: string;
  enabled: boolean;
}

export interface ScheduleRuleConfigRead {
  production_type: ProductionTypeValue;
  rules: ScheduleRuleConfigItem[];
}

export interface ScheduleRuleConfigUpdateItem {
  key: ScheduleRuleKey;
  enabled: boolean;
}

export interface ScheduleRuleConfigUpdate {
  rules: ScheduleRuleConfigUpdateItem[];
}

export interface AutoScheduleProposal {
  production_type: ProductionTypeValue;
  queue_revision: string | null;
  current_colour_changeovers: number;
  proposed_colour_changeovers: number;
  colour_changeover_reduction: number;
  proposed_order: WorkOrder[];
}

// Multi-day capacity plan (N49-4..N49-8) rendered by the capacity board (N49-9).
export type PaintFeasibilityStatus = "OK" | "WARNING" | "BLOCKED";

export interface OrderPlacement {
  work_order_id: number;
  order_number: string;
  customer_name: string;
  ral_code: string | null;
  total_area_m2: number | null;
  day_index: number;
  sequence_position: number;
  scheduled_date: string | null;
  planned_pickup_date: string;
  meets_deadline: boolean;
  days_late: number;
  suggested_production_type: ProductionTypeValue;
  suggested_line_is_colour_orphan: boolean;
  suggested_line_is_small: boolean;
  paint_status: PaintFeasibilityStatus;
  paint_remaining_kg: number | null;
}

export interface PlannedDay {
  day_index: number;
  scheduled_date: string | null;
  shift_length: "LONG" | "SHORT";
  floor_m2: number;
  gross_ceiling_m2: number;
  net_ceiling_m2: number;
  changeover_count: number;
  changeover_minutes: number;
  placed_order_count: number;
  placed_m2: number;
  below_floor: boolean;
  over_ceiling: boolean;
  placements: OrderPlacement[];
}

export interface MultiDayPlan {
  production_type: ProductionTypeValue;
  shift_length: "LONG" | "SHORT";
  shift_advised: boolean;
  horizon_working_days: number;
  changeover_minutes: number;
  changeover_is_measured: boolean;
  days: PlannedDay[];
  infeasible_order_ids: number[];
}

// Good-day stats (NA50): the capacity model's definition of a good day.
export interface GoodDayMetrics {
  day: string;
  output_m2: number;
  floor_m2: number;
  met_floor: boolean;
  floor_shortfall_m2: number;
  orders_completed: number;
  orders_on_time: number;
  on_time_pct: number | null;
  changeover_count: number;
  changeover_minutes_total: number;
  changeover_loss_m2: number;
  shift_hours: number;
  active_hours: number;
  idle_hours: number;
  utilisation_pct: number | null;
  rate_m2_per_h: number;
  rate_is_measured: boolean;
}

export interface GoodDayTotals {
  days_count: number;
  days_met_floor: number;
  total_output_m2: number;
  orders_completed: number;
  orders_on_time: number;
  on_time_pct: number | null;
  total_changeover_count: number;
  total_changeover_loss_m2: number;
  avg_utilisation_pct: number | null;
}

export interface GoodDayStats {
  production_type: ProductionTypeValue;
  date_from: string;
  date_to: string;
  floor_m2: number;
  shift_hours: number;
  changeover_minutes_each: number;
  changeover_is_measured: boolean;
  days: GoodDayMetrics[];
  totals: GoodDayTotals;
}
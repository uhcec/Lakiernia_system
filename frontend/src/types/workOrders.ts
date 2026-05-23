export type WorkOrderStatusValue = "ENTERED" | "ASSIGNED" | "IN_PROGRESS" | "FINISHED";
export type ProductionTypeValue = "MANUAL" | "AUTOMATIC";

export interface WorkOrderStatus {
  value: WorkOrderStatusValue;
  label: string;
}

export interface WorkOrderOption<TValue extends string> {
  value: TValue;
  label: string;
}

export interface WorkOrder {
  id: number;
  order_number: string;
  title: string;
  description: string | null;
  customer_name: string | null;
  status: WorkOrderStatus;
  coating_type: WorkOrderOption<"RAL" | "DECORAL">;
  production_type: WorkOrderOption<ProductionTypeValue> | null;
  queue_position: number | null;
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
  description?: string;
  customer_name?: string;
  due_date?: string;
  notes?: string;
}
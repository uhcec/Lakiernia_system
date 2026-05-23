import type { ProductionTypeValue } from "./workOrders";

export interface AssignWorkOrderPlanRequest {
  production_type: ProductionTypeValue;
  queue_position: number;
}

export interface UpdateQueuePositionRequest {
  queue_position: number;
}
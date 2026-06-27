export type PaintStockMovementTypeValue = "OPENING_BALANCE" | "DELIVERY" | "AUTOMATIC_CONSUMPTION" | "MANUAL_ADJUSTMENT";

export interface Paint {
  id: number;
  ral_code: string;
  paint_producer: string;
  paint_code: string;
  current_quantity_kg: number;
  created_at: string;
  updated_at: string;
}

export interface PaintLookup {
  paint_id: number | null;
  ral_code: string;
  paint_producer: string;
  paint_code: string;
  current_quantity_kg: number;
  exists_in_inventory: boolean;
}

export interface PaintListResponse {
  items: Paint[];
  total: number;
  limit: number;
  offset: number;
}

export interface PaintStockMovementType {
  value: PaintStockMovementTypeValue;
  label: string;
}

export interface PaintStockMovement {
  id: number;
  paint_id: number;
  work_order_id: number | null;
  movement_type: PaintStockMovementType;
  quantity_delta_kg: number;
  resulting_quantity_kg: number;
  movement_date: string;
  note: string | null;
  created_at: string;
}

export interface PaintStockMovementListResponse {
  items: PaintStockMovement[];
  total: number;
  limit: number;
  offset: number;
}

export interface PaintLookupParams {
  ralCode: string;
  paintProducer: string;
  paintCode: string;
}

export interface PaintDeliveryRequest {
  ral_code: string;
  paint_producer: string;
  paint_code: string;
  quantity_kg: number;
  movement_date?: string;
  note?: string;
}

export interface PaintManualAdjustmentRequest {
  ral_code: string;
  paint_producer: string;
  paint_code: string;
  quantity_delta_kg: number;
  movement_date?: string;
  note: string;
}

import { createApiError } from "./apiError";
import { getCurrentStationHeaders } from "./stationContext";
import { createApiUrl } from "./workOrdersApi";
import type { ProcessStageValue, StageWorkOrder } from "../types/process";
import type { ProductionTypeValue } from "../types/workOrders";

export async function fetchSurfacePreparationWorkOrders(): Promise<StageWorkOrder[]> {
  return fetchStageWorkOrders("SURFACE_PREPARATION");
}

export async function fetchStageWorkOrders(
  stage: ProcessStageValue,
  productionType?: ProductionTypeValue,
): Promise<StageWorkOrder[]> {
  const url = new URL(createApiUrl(`/process/stages/${stage}/work-orders`), window.location.origin);

  if (productionType) {
    url.searchParams.set("production_type", productionType);
  }

  const response = await fetch(url.toString(), {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać zleceń");
  }

  return response.json() as Promise<StageWorkOrder[]>;
}

export async function startSurfacePreparation(workOrderId: number): Promise<StageWorkOrder> {
  return transitionStage(workOrderId, "SURFACE_PREPARATION", "start");
}

type StageAction = "start" | "finish" | "reopen";

interface StageStartPayload {
  counted_quantity?: number;
}

interface CompletePackingPayload {
  counted_quantity: number;
  ok_quantity: number;
  correction_quantity: number;
  correction_profiles_quantity?: number;
  correction_accessories_quantity?: number;
  correction_reason_category?: string;
  correction_reason_note?: string;
  stat_only_correction?: boolean;
}

interface AutomaticPaintConsumptionPayload {
  consumed_paint_quantity_kg: number;
}

interface CompleteDecoralProductionPayload {
  ok_quantity: number;
  correction_quantity: number;
  correction_profiles_quantity?: number;
  correction_accessories_quantity?: number;
  correction_reason_category?: string;
  correction_reason_note?: string;
}

export async function transitionStage(
  workOrderId: number,
  stage: ProcessStageValue,
  action: StageAction,
  batchId?: number,
  payload?: StageStartPayload,
): Promise<StageWorkOrder> {
  const pathname = batchId
    ? `/process/work-orders/${workOrderId}/batches/${batchId}/stages/${stage}/${action}`
    : `/process/work-orders/${workOrderId}/stages/${stage}/${action}`;

  const response = await fetch(createApiUrl(pathname), {
    method: "POST",
    headers: {
      Accept: "application/json",
      ...(payload ? { "Content-Type": "application/json" } : {}),
      ...getCurrentStationHeaders(),
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zmienić statusu");
  }

  return response.json() as Promise<StageWorkOrder>;
}

export async function startPacking(
  workOrderId: number,
  batchId?: number,
  override = false,
): Promise<StageWorkOrder> {
  const base = batchId
    ? `/process/work-orders/${workOrderId}/batches/${batchId}/packing/start`
    : `/process/work-orders/${workOrderId}/packing/start`;
  const pathname = override ? `${base}?override=true` : base;

  const response = await fetch(createApiUrl(pathname), {
    method: "POST",
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się rozpocząć pakowania");
  }

  return response.json() as Promise<StageWorkOrder>;
}

export async function releasePacking(workOrderId: number, batchId?: number): Promise<StageWorkOrder> {
  const pathname = batchId
    ? `/process/work-orders/${workOrderId}/batches/${batchId}/packing/release`
    : `/process/work-orders/${workOrderId}/packing/release`;

  const response = await fetch(createApiUrl(pathname), {
    method: "POST",
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zwolnić stanowiska pakowania");
  }

  return response.json() as Promise<StageWorkOrder>;
}

export async function completePacking(
  workOrderId: number,
  payload: CompletePackingPayload,
  batchId?: number,
): Promise<StageWorkOrder> {
  const pathname = batchId
    ? `/process/work-orders/${workOrderId}/batches/${batchId}/packing/complete`
    : `/process/work-orders/${workOrderId}/packing/complete`;

  const response = await fetch(createApiUrl(pathname), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zakończyć pakowania");
  }

  return response.json() as Promise<StageWorkOrder>;
}

export async function recordAutomaticPaintConsumption(
  workOrderId: number,
  payload: AutomaticPaintConsumptionPayload,
): Promise<StageWorkOrder> {
  const response = await fetch(createApiUrl(`/process/work-orders/${workOrderId}/automatic-production/paint-consumption`), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zapisać zużycia farby");
  }

  return response.json() as Promise<StageWorkOrder>;
}

export async function completeDecoralProduction(
  workOrderId: number,
  payload: CompleteDecoralProductionPayload,
  batchId?: number,
): Promise<StageWorkOrder> {
  const pathname = batchId
    ? `/process/work-orders/${workOrderId}/batches/${batchId}/decoral-production/complete`
    : `/process/work-orders/${workOrderId}/decoral-production/complete`;

  const response = await fetch(createApiUrl(pathname), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zakończyć produkcji Decoral");
  }

  return response.json() as Promise<StageWorkOrder>;
}

export async function finishSurfacePreparation(workOrderId: number, countedQuantity: number): Promise<StageWorkOrder> {
  return transitionStage(workOrderId, "SURFACE_PREPARATION", "finish", undefined, {
    counted_quantity: countedQuantity,
  });
}

export async function reopenSurfacePreparation(workOrderId: number): Promise<StageWorkOrder> {
  return transitionStage(workOrderId, "SURFACE_PREPARATION", "reopen");
}

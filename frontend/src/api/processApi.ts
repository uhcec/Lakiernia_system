import { createApiError } from "./apiError";
import { getCurrentStationHeaders } from "./stationContext";
import type { ProcessStageValue, StageWorkOrder } from "../types/process";
import type { ProductionTypeValue } from "../types/workOrders";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim();

function createApiUrl(pathname: string): string {
  const normalizedPath = pathname.startsWith("/") ? pathname : `/${pathname}`;

  if (!API_BASE_URL) {
    return normalizedPath;
  }

  if (API_BASE_URL.startsWith("http://") || API_BASE_URL.startsWith("https://")) {
    return new URL(normalizedPath, API_BASE_URL).toString();
  }

  return `${API_BASE_URL.replace(/\/$/, "")}${normalizedPath}`;
}

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

export async function finishSurfacePreparation(workOrderId: number, countedQuantity: number): Promise<StageWorkOrder> {
  return transitionStage(workOrderId, "SURFACE_PREPARATION", "finish", undefined, {
    counted_quantity: countedQuantity,
  });
}

export async function reopenSurfacePreparation(workOrderId: number): Promise<StageWorkOrder> {
  return transitionStage(workOrderId, "SURFACE_PREPARATION", "reopen");
}
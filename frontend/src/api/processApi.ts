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

async function readErrorMessage(response: Response, fallbackMessage: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return typeof body.detail === "string" && body.detail.trim() ? body.detail : fallbackMessage;
  } catch {
    return fallbackMessage;
  }
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
    throw new Error(await readErrorMessage(response, "Nie udało się pobrać zleceń"));
  }

  return response.json() as Promise<StageWorkOrder[]>;
}

export async function startSurfacePreparation(workOrderId: number): Promise<StageWorkOrder> {
  return transitionStage(workOrderId, "SURFACE_PREPARATION", "start");
}

type StageAction = "start" | "finish" | "reopen";

export async function transitionStage(
  workOrderId: number,
  stage: ProcessStageValue,
  action: StageAction,
): Promise<StageWorkOrder> {
  const response = await fetch(createApiUrl(`/process/work-orders/${workOrderId}/stages/${stage}/${action}`), {
    method: "POST",
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Nie udało się zmienić statusu"));
  }

  return response.json() as Promise<StageWorkOrder>;
}

export async function finishSurfacePreparation(workOrderId: number): Promise<StageWorkOrder> {
  return transitionStage(workOrderId, "SURFACE_PREPARATION", "finish");
}

export async function reopenSurfacePreparation(workOrderId: number): Promise<StageWorkOrder> {
  return transitionStage(workOrderId, "SURFACE_PREPARATION", "reopen");
}
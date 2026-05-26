import type { AssignWorkOrderPlanRequest, ReorderQueueItemRequest, UpdateQueuePositionRequest } from "../types/manager";
import type { WorkOrder } from "../types/workOrders";

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

export async function fetchUnplannedWorkOrders(): Promise<WorkOrder[]> {
  const response = await fetch(createApiUrl("/manager/work-orders/unplanned"), {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Nie udało się pobrać zleceń do zaplanowania"));
  }

  return response.json() as Promise<WorkOrder[]>;
}

export async function fetchPlannedWorkOrders(): Promise<WorkOrder[]> {
  const response = await fetch(createApiUrl("/manager/work-orders"), {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Nie udało się pobrać zaplanowanych zleceń"));
  }

  return response.json() as Promise<WorkOrder[]>;
}

export async function assignWorkOrderPlan(workOrderId: number, payload: AssignWorkOrderPlanRequest): Promise<WorkOrder> {
  const response = await fetch(createApiUrl(`/manager/work-orders/${workOrderId}/plan`), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Nie udało się zaplanować zlecenia"));
  }

  return response.json() as Promise<WorkOrder>;
}

export async function updateWorkOrderQueuePosition(
  workOrderId: number,
  payload: UpdateQueuePositionRequest,
): Promise<WorkOrder> {
  const response = await fetch(createApiUrl(`/manager/work-orders/${workOrderId}/queue-position`), {
    method: "PATCH",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Nie udało się zmienić kolejności"));
  }

  return response.json() as Promise<WorkOrder>;
}

export async function reorderWorkOrderQueue(
  payload: ReorderQueueItemRequest[],
): Promise<WorkOrder[]> {
  const response = await fetch(createApiUrl("/manager/queue/reorder"), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Nie udało się zapisać kolejności"));
  }

  return response.json() as Promise<WorkOrder[]>;
}
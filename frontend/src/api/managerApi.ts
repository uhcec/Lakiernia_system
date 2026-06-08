import { createApiError } from "./apiError";
import { getCurrentStationHeaders } from "./stationContext";
import type {
  AssignWorkOrderPlanRequest,
  CorrectionReasonReportItem,
  ReorderQueueRequest,
  ThroughputStats,
  UpdateProductionTypeRequest,
  UpdateQueuePositionRequest,
} from "../types/manager";
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

export async function fetchUnplannedWorkOrders(): Promise<WorkOrder[]> {
  const response = await fetch(createApiUrl("/manager/work-orders/unplanned"), {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać zleceń do zaplanowania");
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
    throw await createApiError(response, "Nie udało się pobrać zaplanowanych zleceń");
  }

  return response.json() as Promise<WorkOrder[]>;
}

export async function fetchCorrectionReasonReport(): Promise<CorrectionReasonReportItem[]> {
  const response = await fetch(createApiUrl("/manager/corrections/reason-report"), {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać statystyki poprawek");
  }

  return response.json() as Promise<CorrectionReasonReportItem[]>;
}

export async function fetchThroughputStats(
  dateFrom: string,
  dateTo: string,
  groupBy: "day" | "week" | "month",
): Promise<ThroughputStats> {
  const url = new URL(createApiUrl("/manager/stats/throughput"), window.location.origin);
  url.searchParams.set("date_from", dateFrom);
  url.searchParams.set("date_to", dateTo);
  url.searchParams.set("group_by", groupBy);
  const finalUrl = createApiUrl("/manager/stats/throughput").startsWith("http")
    ? url.toString()
    : `${url.pathname}${url.search}`;

  const response = await fetch(finalUrl, {
    headers: { Accept: "application/json", ...getCurrentStationHeaders() },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać statystyk przepustowości");
  }

  return response.json() as Promise<ThroughputStats>;
}

export function getCorrectionReasonReportExportUrl(): string {
  return createApiUrl("/manager/corrections/reason-report/export.csv");
}

export async function assignWorkOrderPlan(workOrderId: number, payload: AssignWorkOrderPlanRequest): Promise<WorkOrder> {
  const response = await fetch(createApiUrl(`/manager/work-orders/${workOrderId}/plan`), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zaplanować zlecenia");
  }

  return response.json() as Promise<WorkOrder>;
}

export async function updateWorkOrderProductionType(
  workOrderId: number,
  payload: UpdateProductionTypeRequest,
): Promise<WorkOrder> {
  const response = await fetch(createApiUrl(`/manager/work-orders/${workOrderId}/production-type`), {
    method: "PATCH",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zmienić typu produkcji");
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
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zmienić kolejności");
  }

  return response.json() as Promise<WorkOrder>;
}

export async function reorderWorkOrderQueue(
  payload: ReorderQueueRequest,
): Promise<WorkOrder[]> {
  const response = await fetch(createApiUrl("/manager/queue/reorder"), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zapisać kolejności");
  }

  return response.json() as Promise<WorkOrder[]>;
}
import { createApiError } from "./apiError";
import { getCurrentStationHeaders } from "./stationContext";
import type {
  AssignWorkOrderPlanRequest,
  AutoScheduleProposal,
  CorrectionReasonReportItem,
  CycleTimeStats,
  GoodDayStats,
  MultiDayPlan,
  ReorderQueueRequest,
  ScheduleRuleConfigRead,
  ScheduleRuleConfigUpdate,
  ThroughputStats,
  UpdateProductionTypeRequest,
  UpdateQueuePositionRequest,
  WipAgingStats,
} from "../types/manager";
import type { ProductionTypeValue, WorkOrder } from "../types/workOrders";

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

export async function fetchCycleTimeStats(dateFrom: string, dateTo: string): Promise<CycleTimeStats> {
  const url = new URL(createApiUrl("/manager/stats/cycle-time"), window.location.origin);
  url.searchParams.set("date_from", dateFrom);
  url.searchParams.set("date_to", dateTo);
  const finalUrl = createApiUrl("/manager/stats/cycle-time").startsWith("http")
    ? url.toString()
    : `${url.pathname}${url.search}`;

  const response = await fetch(finalUrl, {
    headers: { Accept: "application/json", ...getCurrentStationHeaders() },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać statystyk czasów etapów");
  }

  return response.json() as Promise<CycleTimeStats>;
}

export async function fetchMultiDayPlan(
  productionType: ProductionTypeValue,
  horizonWorkingDays = 3,
): Promise<MultiDayPlan> {
  const url = new URL(createApiUrl("/manager/planner/multi-day"), window.location.origin);
  url.searchParams.set("production_type", productionType);
  url.searchParams.set("horizon_working_days", String(horizonWorkingDays));
  const finalUrl = createApiUrl("/manager/planner/multi-day").startsWith("http")
    ? url.toString()
    : `${url.pathname}${url.search}`;

  const response = await fetch(finalUrl, {
    headers: { Accept: "application/json", ...getCurrentStationHeaders() },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać planu wielodniowego");
  }

  return response.json() as Promise<MultiDayPlan>;
}

export async function fetchGoodDayStats(dateFrom: string, dateTo: string): Promise<GoodDayStats> {
  const url = new URL(createApiUrl("/manager/stats/good-day"), window.location.origin);
  url.searchParams.set("date_from", dateFrom);
  url.searchParams.set("date_to", dateTo);
  const finalUrl = createApiUrl("/manager/stats/good-day").startsWith("http")
    ? url.toString()
    : `${url.pathname}${url.search}`;

  const response = await fetch(finalUrl, {
    headers: { Accept: "application/json", ...getCurrentStationHeaders() },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać statystyk dobrego dnia");
  }

  return response.json() as Promise<GoodDayStats>;
}

export async function fetchWipAging(): Promise<WipAgingStats> {
  const finalUrl = createApiUrl("/manager/stats/wip-aging");
  const response = await fetch(finalUrl, {
    headers: { Accept: "application/json", ...getCurrentStationHeaders() },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać zleceń w toku");
  }

  return response.json() as Promise<WipAgingStats>;
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

function schedulerConfigUrl(productionType: ProductionTypeValue): string {
  const base = createApiUrl("/manager/scheduler/config");
  return base.startsWith("http")
    ? `${base}?production_type=${productionType}`
    : `${base}?production_type=${productionType}`;
}

export async function fetchScheduleConfig(productionType: ProductionTypeValue): Promise<ScheduleRuleConfigRead> {
  const response = await fetch(schedulerConfigUrl(productionType), {
    headers: { Accept: "application/json", ...getCurrentStationHeaders() },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać reguł układania");
  }

  return response.json() as Promise<ScheduleRuleConfigRead>;
}

export async function updateScheduleConfig(
  productionType: ProductionTypeValue,
  payload: ScheduleRuleConfigUpdate,
): Promise<ScheduleRuleConfigRead> {
  const response = await fetch(schedulerConfigUrl(productionType), {
    method: "PUT",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zapisać reguł układania");
  }

  return response.json() as Promise<ScheduleRuleConfigRead>;
}

export async function fetchAutoScheduleProposal(productionType: ProductionTypeValue): Promise<AutoScheduleProposal> {
  const base = createApiUrl("/manager/scheduler/proposal");
  const finalUrl = `${base}?production_type=${productionType}`;
  const response = await fetch(finalUrl, {
    headers: { Accept: "application/json", ...getCurrentStationHeaders() },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się ułożyć kolejności automatycznie");
  }

  return response.json() as Promise<AutoScheduleProposal>;
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
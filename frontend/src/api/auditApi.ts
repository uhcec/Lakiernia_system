import { createApiError } from "./apiError";
import { createApiUrl } from "./workOrdersApi";
import type { AuditEvent, AuditEventListResponse, AuditStationId } from "../types/audit";

export interface AuditEventSearchParams {
  workOrderId?: string;
  eventType?: string;
  stationId?: AuditStationId | "";
  requestId?: string;
  targetType?: string;
  targetId?: string;
  createdFrom?: string;
  createdTo?: string;
  limit?: number;
  offset?: number;
}

export async function fetchWorkOrderAuditEvents(workOrderId: number): Promise<AuditEvent[]> {
  const response = await fetch(createApiUrl(`/audit/work-orders/${workOrderId}/events`), {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać historii zmian");
  }

  return response.json() as Promise<AuditEvent[]>;
}

export async function fetchAuditEvents(params: AuditEventSearchParams = {}): Promise<AuditEventListResponse> {
  const response = await fetch(buildAuditEventsUrl("/audit/events", params), {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać historii audytu");
  }

  return response.json() as Promise<AuditEventListResponse>;
}

export function getAuditEventsExportUrl(params: AuditEventSearchParams = {}): string {
  return buildAuditEventsUrl("/audit/events/export.csv", params).toString();
}

function buildAuditEventsUrl(pathname: string, params: AuditEventSearchParams): string {
  const apiUrl = createApiUrl(pathname);
  const url = new URL(apiUrl, window.location.origin);
  appendParam(url, "work_order_id", params.workOrderId);
  appendParam(url, "event_type", params.eventType);
  appendParam(url, "station_id", params.stationId);
  appendParam(url, "request_id", params.requestId);
  appendParam(url, "target_type", params.targetType);
  appendParam(url, "target_id", params.targetId);
  appendParam(url, "created_from", params.createdFrom);
  appendParam(url, "created_to", params.createdTo);
  appendParam(url, "limit", params.limit ? String(params.limit) : undefined);
  appendParam(url, "offset", params.offset ? String(params.offset) : undefined);
  return apiUrl.startsWith("http://") || apiUrl.startsWith("https://") ? url.toString() : `${url.pathname}${url.search}`;
}

function appendParam(url: URL, name: string, value: string | undefined): void {
  const normalizedValue = value?.trim();
  if (normalizedValue) {
    url.searchParams.set(name, normalizedValue);
  }
}

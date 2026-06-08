import { createApiError } from "./apiError";
import { getCurrentStationHeaders } from "./stationContext";
import type { CreateWorkOrderRequest, UpdateWorkOrderRequest, WorkOrder, WorkOrderAttachment, WorkOrdersListResponse } from "../types/workOrders";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim();

export interface WorkOrderSearchParams {
  externalOrderNumber?: string;
}

export function createApiUrl(pathname: string): string {
  const normalizedPath = pathname.startsWith("/") ? pathname : `/${pathname}`;

  if (!API_BASE_URL) {
    return normalizedPath;
  }

  if (API_BASE_URL.startsWith("http://") || API_BASE_URL.startsWith("https://")) {
    return new URL(normalizedPath, API_BASE_URL).toString();
  }

  return `${API_BASE_URL.replace(/\/$/, "")}${normalizedPath}`;
}

export async function fetchWorkOrders(params: WorkOrderSearchParams = {}): Promise<WorkOrdersListResponse> {
  const response = await fetch(buildWorkOrdersUrl(params), {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać zleceń");
  }

  return response.json() as Promise<WorkOrdersListResponse>;
}

function buildWorkOrdersUrl(params: WorkOrderSearchParams): string {
  const apiUrl = createApiUrl("/work-orders");
  const url = new URL(apiUrl, window.location.origin);
  appendSearchParam(url, "external_order_number", params.externalOrderNumber);

  return apiUrl.startsWith("http://") || apiUrl.startsWith("https://") ? url.toString() : `${url.pathname}${url.search}`;
}

function appendSearchParam(url: URL, name: string, value: string | undefined): void {
  const normalizedValue = value?.trim();
  if (!normalizedValue) {
    return;
  }

  url.searchParams.set(name, normalizedValue);
}

export async function createWorkOrder(payload: CreateWorkOrderRequest): Promise<WorkOrder> {
  const url = createApiUrl("/work-orders");

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się utworzyć zlecenia");
  }

  return response.json() as Promise<WorkOrder>;
}

export async function fetchWorkOrder(workOrderId: number): Promise<WorkOrder> {
  const url = createApiUrl(`/work-orders/${workOrderId}`);

  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać zlecenia");
  }

  return response.json() as Promise<WorkOrder>;
}

export async function updateWorkOrder(workOrderId: number, payload: UpdateWorkOrderRequest): Promise<WorkOrder> {
  const url = createApiUrl(`/work-orders/${workOrderId}`);

  const response = await fetch(url, {
    method: "PATCH",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zaktualizować zlecenia");
  }

  return response.json() as Promise<WorkOrder>;
}

export async function markWorkOrderCompleteArrival(workOrderId: number): Promise<WorkOrder> {
  const url = createApiUrl(`/work-orders/${workOrderId}/mark-complete-arrival`);

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się oznaczyć zlecenia jako kompletne");
  }

  return response.json() as Promise<WorkOrder>;
}

export async function updateWorkOrderReleaseStatus(workOrderId: number, isReleasedToClient: boolean): Promise<WorkOrder> {
  const url = createApiUrl(`/work-orders/${workOrderId}/release-status`);

  const response = await fetch(url, {
    method: "PATCH",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify({ is_released_to_client: isReleasedToClient }),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zmienić statusu wydania");
  }

  return response.json() as Promise<WorkOrder>;
}

export async function fetchWorkOrderAttachments(workOrderId: number): Promise<WorkOrderAttachment[]> {
  const response = await fetch(createApiUrl(`/work-orders/${workOrderId}/attachments`), {
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać załączników");
  }

  return response.json() as Promise<WorkOrderAttachment[]>;
}

export async function uploadWorkOrderAttachment(
  workOrderId: number,
  payload: { file: File; attachmentType?: string; description?: string },
): Promise<WorkOrderAttachment> {
  const formData = new FormData();
  formData.append("file", payload.file);
  if (payload.attachmentType?.trim()) {
    formData.append("attachment_type", payload.attachmentType.trim());
  }
  if (payload.description?.trim()) {
    formData.append("description", payload.description.trim());
  }

  const response = await fetch(createApiUrl(`/work-orders/${workOrderId}/attachments`), {
    method: "POST",
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
    body: formData,
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się przesłać załącznika");
  }

  return response.json() as Promise<WorkOrderAttachment>;
}

export async function deleteWorkOrderAttachment(workOrderId: number, attachmentId: number): Promise<void> {
  const response = await fetch(createApiUrl(`/work-orders/${workOrderId}/attachments/${attachmentId}`), {
    method: "DELETE",
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się usunąć załącznika");
  }
}

export function getWorkOrderAttachmentDownloadUrl(workOrderId: number, attachmentId: number): string {
  return createApiUrl(`/work-orders/${workOrderId}/attachments/${attachmentId}/download`);
}

export function getQualityControlDocumentUrl(workOrderId: number): string {
  return createApiUrl(`/work-orders/${workOrderId}/quality-control-document`);
}
import { createApiError } from "./apiError";
import { getCurrentStationHeaders } from "./stationContext";
import type { CreateWorkOrderRequest, UpdateWorkOrderRequest, WorkOrder, WorkOrderAttachment, WorkOrderAttachmentCategory, WorkOrdersListResponse } from "../types/workOrders";

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

// The single origin our auth token may be sent to: the configured API base origin when it is
// absolute, otherwise the app's own origin (relative paths are same-origin). Used to scope the
// global fetch interceptor so the Bearer token and 401 redirect never leak to a third-party origin.
export const API_ORIGIN =
  API_BASE_URL && (API_BASE_URL.startsWith("http://") || API_BASE_URL.startsWith("https://"))
    ? new URL(API_BASE_URL).origin
    : window.location.origin;

export function isApiRequest(input: RequestInfo | URL): boolean {
  try {
    const href = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    return new URL(href, window.location.origin).origin === API_ORIGIN;
  } catch {
    return false;
  }
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
  payload: { file: File; category?: WorkOrderAttachmentCategory; attachmentType?: string; description?: string },
): Promise<WorkOrderAttachment> {
  const formData = new FormData();
  formData.append("file", payload.file);
  if (payload.category) {
    formData.append("category", payload.category);
  }
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

// Attachment download is auth-protected, but a plain <a href> browser navigation does not carry the
// Authorization header (it bypasses the fetch interceptor) → 401 "Nie jesteś zalogowany". Fetch the
// file as a blob (this fetch goes through the token-injecting window.fetch) and open it in a new tab so
// PDFs/images are viewable. The tab is opened synchronously inside the click gesture to avoid popup
// blockers, then pointed at the blob once it arrives.
export async function openWorkOrderAttachment(workOrderId: number, attachmentId: number): Promise<void> {
  const newTab = window.open("about:blank", "_blank");
  try {
    const response = await fetch(getWorkOrderAttachmentDownloadUrl(workOrderId, attachmentId), {
      headers: { Accept: "*/*" },
    });
    if (!response.ok) {
      newTab?.close();
      throw await createApiError(response, "Nie udało się otworzyć załącznika");
    }
    const blobUrl = URL.createObjectURL(await response.blob());
    if (newTab) {
      newTab.location.href = blobUrl;
    } else {
      // Popup blocked — fall back to a direct download.
      const anchor = document.createElement("a");
      anchor.href = blobUrl;
      anchor.download = "";
      anchor.click();
    }
    setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
  } catch (error) {
    newTab?.close();
    throw error;
  }
}

export function getQualityControlDocumentUrl(workOrderId: number): string {
  return createApiUrl(`/work-orders/${workOrderId}/quality-control-document`);
}

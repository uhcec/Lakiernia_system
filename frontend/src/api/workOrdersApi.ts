import { createApiError } from "./apiError";
import { getCurrentStationHeaders } from "./stationContext";
import type { CreateWorkOrderRequest, UpdateWorkOrderRequest, WorkOrder, WorkOrderAttachment, WorkOrderAttachmentCategory, WorkOrdersListResponse } from "../types/workOrders";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim();

export interface WorkOrderSearchParams {
  externalOrderNumber?: string;
  limit?: number;
  offset?: number;
}

// CHANGES #15: the backend caps `limit` at 100 (app/work_orders/router.py) and used to silently
// default to 50 — the office list then computed its tiles/tabs from a truncated page. The office
// view is designed around having EVERY order client-side (buckets, overdue count), so we page
// through until `total` is covered. The page cap is a runaway backstop, not an expected bound.
const WORK_ORDERS_PAGE_LIMIT = 100;
const WORK_ORDERS_MAX_PAGES = 100;

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

export async function fetchAllWorkOrders(
  params: Omit<WorkOrderSearchParams, "limit" | "offset"> = {},
): Promise<WorkOrdersListResponse> {
  const items: WorkOrder[] = [];
  let total = 0;

  for (let page = 0; page < WORK_ORDERS_MAX_PAGES; page += 1) {
    const response = await fetchWorkOrders({
      ...params,
      limit: WORK_ORDERS_PAGE_LIMIT,
      offset: page * WORK_ORDERS_PAGE_LIMIT,
    });
    items.push(...response.items);
    total = response.total;
    if (items.length >= total || response.items.length === 0) {
      break;
    }
  }

  return { items, total, limit: items.length, offset: 0 };
}

function buildWorkOrdersUrl(params: WorkOrderSearchParams): string {
  const apiUrl = createApiUrl("/work-orders");
  const url = new URL(apiUrl, window.location.origin);
  appendSearchParam(url, "external_order_number", params.externalOrderNumber);
  if (params.limit != null) {
    url.searchParams.set("limit", String(params.limit));
  }
  if (params.offset != null) {
    url.searchParams.set("offset", String(params.offset));
  }

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

export async function administrativeResetWorkOrder(workOrderId: number): Promise<WorkOrder> {
  const url = createApiUrl(`/work-orders/${workOrderId}/administrative-reset`);

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zresetować zlecenia");
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

export async function updateWorkOrderQuantityDiscrepancy(workOrderId: number, isResolved: boolean): Promise<WorkOrder> {
  const url = createApiUrl(`/work-orders/${workOrderId}/quantity-discrepancy`);

  const response = await fetch(url, {
    method: "PATCH",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify({ is_resolved: isResolved }),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zapisać wyjaśnienia różnicy ilości");
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

export interface GenerateWzDocumentRequest {
  work_order_ids: number[];
  baskets_count: number | null;
}

// Generate a WZ (wydanie z magazynu) PDF for a group of ready orders of one client and save it. This
// is a POST that streams a PDF back, so — like the QC document — we fetch it as a blob (the global
// interceptor adds the Bearer token) and trigger a download from the returned filename.
export async function generateWzDocument(payload: GenerateWzDocumentRequest): Promise<void> {
  const response = await fetch(createApiUrl("/work-orders/wz-document"), {
    method: "POST",
    headers: {
      Accept: "application/pdf",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się wygenerować WZ");
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  const filename = match?.[1] ?? "WZ.pdf";

  const objectUrl = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

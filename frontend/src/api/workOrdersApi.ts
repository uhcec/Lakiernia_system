import type { CreateWorkOrderRequest, WorkOrder, WorkOrderAttachment, WorkOrdersListResponse } from "../types/workOrders";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim();

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

async function readErrorMessage(response: Response, fallbackMessage: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string | { msg?: string }[] };
    if (typeof body.detail === "string" && body.detail.trim()) {
      return body.detail;
    }
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      const firstMessage = body.detail[0]?.msg;
      if (typeof firstMessage === "string" && firstMessage.trim()) {
        return firstMessage;
      }
    }
  } catch {
    return fallbackMessage;
  }

  return fallbackMessage;
}

export async function fetchWorkOrders(): Promise<WorkOrdersListResponse> {
  const response = await fetch(createApiUrl("/work-orders"), {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error("Nie udało się pobrać zleceń");
  }

  return response.json() as Promise<WorkOrdersListResponse>;
}

export async function createWorkOrder(payload: CreateWorkOrderRequest): Promise<WorkOrder> {
  const url = createApiUrl("/work-orders");

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Nie udało się utworzyć zlecenia"));
  }

  return response.json() as Promise<WorkOrder>;
}

export async function fetchWorkOrder(workOrderId: number): Promise<WorkOrder> {
  const url = createApiUrl(`/work-orders/${workOrderId}`);

  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error("Nie udało się pobrać zlecenia");
  }

  return response.json() as Promise<WorkOrder>;
}

export async function markWorkOrderCompleteArrival(workOrderId: number): Promise<WorkOrder> {
  const url = createApiUrl(`/work-orders/${workOrderId}/mark-complete-arrival`);

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Nie udało się oznaczyć zlecenia jako kompletne"));
  }

  return response.json() as Promise<WorkOrder>;
}

export async function fetchWorkOrderAttachments(workOrderId: number): Promise<WorkOrderAttachment[]> {
  const response = await fetch(createApiUrl(`/work-orders/${workOrderId}/attachments`), {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Nie udało się pobrać załączników"));
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
    },
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Nie udało się przesłać załącznika"));
  }

  return response.json() as Promise<WorkOrderAttachment>;
}

export async function deleteWorkOrderAttachment(workOrderId: number, attachmentId: number): Promise<void> {
  const response = await fetch(createApiUrl(`/work-orders/${workOrderId}/attachments/${attachmentId}`), {
    method: "DELETE",
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Nie udało się usunąć załącznika"));
  }
}

export function getWorkOrderAttachmentDownloadUrl(workOrderId: number, attachmentId: number): string {
  return createApiUrl(`/work-orders/${workOrderId}/attachments/${attachmentId}/download`);
}
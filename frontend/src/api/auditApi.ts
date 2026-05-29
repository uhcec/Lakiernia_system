import { createApiError } from "./apiError";
import { createApiUrl } from "./workOrdersApi";
import type { AuditEvent } from "../types/audit";

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

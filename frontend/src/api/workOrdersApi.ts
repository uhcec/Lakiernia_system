import type { CreateWorkOrderRequest, WorkOrder, WorkOrderStatusValue, WorkOrdersListResponse } from "../types/workOrders";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function fetchWorkOrders(status?: WorkOrderStatusValue): Promise<WorkOrdersListResponse> {
  const url = new URL("/work-orders", API_BASE_URL);

  if (status) {
    url.searchParams.set("status", status);
  }

  const response = await fetch(url.toString(), {
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
  const url = new URL("/work-orders", API_BASE_URL);

  const response = await fetch(url.toString(), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error("Nie udało się utworzyć zlecenia");
  }

  return response.json() as Promise<WorkOrder>;
}
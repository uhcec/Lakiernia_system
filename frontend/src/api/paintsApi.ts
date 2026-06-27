import { createApiError } from "./apiError";
import { createApiUrl } from "./workOrdersApi";
import { getCurrentStationHeaders } from "./stationContext";
import type {
  Paint,
  PaintDeliveryRequest,
  PaintListResponse,
  PaintLookup,
  PaintLookupParams,
  PaintManualAdjustmentRequest,
  PaintStockMovementListResponse,
} from "../types/paints";

export async function fetchPaints(): Promise<PaintListResponse> {
  const response = await fetch(createApiUrl("/paints"), {
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać farb");
  }

  return response.json() as Promise<PaintListResponse>;
}

export async function lookupPaintStock(params: PaintLookupParams): Promise<PaintLookup> {
  const apiUrl = createApiUrl("/paints/lookup");
  const url = new URL(apiUrl, window.location.origin);
  url.searchParams.set("ral_code", params.ralCode.trim());
  url.searchParams.set("paint_producer", params.paintProducer.trim());
  url.searchParams.set("paint_code", params.paintCode.trim());

  const response = await fetch(apiUrl.startsWith("http://") || apiUrl.startsWith("https://") ? url.toString() : `${url.pathname}${url.search}`, {
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać stanu farby");
  }

  return response.json() as Promise<PaintLookup>;
}

export async function fetchPaintMovements(paintId: number): Promise<PaintStockMovementListResponse> {
  const response = await fetch(createApiUrl(`/paints/${paintId}/movements`), {
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać historii ruchów farby");
  }

  return response.json() as Promise<PaintStockMovementListResponse>;
}

export async function recordPaintDelivery(payload: PaintDeliveryRequest): Promise<Paint> {
  const response = await fetch(createApiUrl("/paints/deliveries"), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zapisać dostawy farby");
  }

  return response.json() as Promise<Paint>;
}

export async function recordPaintAdjustment(payload: PaintManualAdjustmentRequest): Promise<Paint> {
  const response = await fetch(createApiUrl("/paints/adjustments"), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zapisać korekty farby");
  }

  return response.json() as Promise<Paint>;
}

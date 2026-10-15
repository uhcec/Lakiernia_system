import { createApiError } from "./apiError";
import { getCurrentStationHeaders } from "./stationContext";
import { createApiUrl } from "./workOrdersApi";

// CHANGES #29: shop-floor parameters the manager calibrates from "Ustawienia".
export interface ShopSettings {
  hanging_max_active_orders: number;
}

export const HANGING_MAX_ACTIVE_ORDERS_LIMIT = 20;

export async function fetchShopSettings(): Promise<ShopSettings> {
  const response = await fetch(createApiUrl("/shop-settings"), {
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać ustawień");
  }

  return response.json() as Promise<ShopSettings>;
}

export async function updateShopSettings(settings: ShopSettings): Promise<ShopSettings> {
  const response = await fetch(createApiUrl("/shop-settings"), {
    method: "PUT",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(settings),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zapisać ustawień");
  }

  return response.json() as Promise<ShopSettings>;
}

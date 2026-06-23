import { createApiError } from "./apiError";
import { getCurrentStationHeaders } from "./stationContext";
import { createApiUrl } from "./workOrdersApi";
import type { Foil, FoilCreateRequest, FoilListResponse, FoilUpdateRequest } from "../types/foils";

export async function fetchFoils(search?: string): Promise<FoilListResponse> {
  const apiUrl = createApiUrl("/foils");
  const url = new URL(apiUrl, window.location.origin);
  const normalizedSearch = search?.trim();
  if (normalizedSearch) {
    url.searchParams.set("search", normalizedSearch);
  }
  const target = apiUrl.startsWith("http://") || apiUrl.startsWith("https://") ? url.toString() : `${url.pathname}${url.search}`;

  const response = await fetch(target, {
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać folii");
  }

  return response.json() as Promise<FoilListResponse>;
}

export async function createFoil(payload: FoilCreateRequest): Promise<Foil> {
  const response = await fetch(createApiUrl("/foils"), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zapisać folii");
  }

  return response.json() as Promise<Foil>;
}

export async function updateFoil(foilId: number, payload: FoilUpdateRequest): Promise<Foil> {
  const response = await fetch(createApiUrl(`/foils/${foilId}`), {
    method: "PATCH",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zaktualizować folii");
  }

  return response.json() as Promise<Foil>;
}

export async function deleteFoil(foilId: number): Promise<void> {
  const response = await fetch(createApiUrl(`/foils/${foilId}`), {
    method: "DELETE",
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się usunąć folii");
  }
}

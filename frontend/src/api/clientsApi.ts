import { createApiError } from "./apiError";
import { getCurrentStationHeaders } from "./stationContext";
import { createApiUrl } from "./workOrdersApi";
import type {
  Client,
  ClientCreateRequest,
  ClientDetail,
  ClientListResponse,
  ClientUpdateRequest,
} from "../types/clients";

export async function fetchClients(search?: string): Promise<ClientListResponse> {
  const apiUrl = createApiUrl("/clients");
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
    throw await createApiError(response, "Nie udało się pobrać klientów");
  }

  return response.json() as Promise<ClientListResponse>;
}

export async function fetchClientDetail(clientId: number): Promise<ClientDetail> {
  const response = await fetch(createApiUrl(`/clients/${clientId}`), {
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać danych klienta");
  }

  return response.json() as Promise<ClientDetail>;
}

export async function createClient(payload: ClientCreateRequest): Promise<Client> {
  const response = await fetch(createApiUrl("/clients"), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zapisać klienta");
  }

  return response.json() as Promise<Client>;
}

export async function updateClient(clientId: number, payload: ClientUpdateRequest): Promise<Client> {
  const response = await fetch(createApiUrl(`/clients/${clientId}`), {
    method: "PATCH",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getCurrentStationHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zaktualizować klienta");
  }

  return response.json() as Promise<Client>;
}

export async function deleteClient(clientId: number): Promise<void> {
  const response = await fetch(createApiUrl(`/clients/${clientId}`), {
    method: "DELETE",
    headers: {
      Accept: "application/json",
      ...getCurrentStationHeaders(),
    },
  });

  if (!response.ok) {
    throw await createApiError(response, "Nie udało się usunąć klienta");
  }
}

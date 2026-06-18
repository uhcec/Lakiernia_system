import { createApiError } from "./apiError";
import { createApiUrl } from "./workOrdersApi";
import type {
  Employee,
  OperatorStats,
  PresenceHistory,
  StationPresenceRoster,
} from "../types/employees";

export async function fetchStationPresence(stationId: string): Promise<StationPresenceRoster> {
  const response = await fetch(createApiUrl(`/stations/${stationId}/presence`), {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać obsady stanowiska");
  }
  return response.json() as Promise<StationPresenceRoster>;
}

async function mutatePresence(
  stationId: string,
  action: "check-in" | "check-out",
  employeeId: number,
): Promise<StationPresenceRoster> {
  const response = await fetch(createApiUrl(`/stations/${stationId}/presence/${action}`), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ employee_id: employeeId }),
  });
  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zaktualizować obsady stanowiska");
  }
  return response.json() as Promise<StationPresenceRoster>;
}

export const checkInEmployee = (stationId: string, employeeId: number) =>
  mutatePresence(stationId, "check-in", employeeId);

export const checkOutEmployee = (stationId: string, employeeId: number) =>
  mutatePresence(stationId, "check-out", employeeId);

export async function checkOutAllAtStation(stationId: string): Promise<StationPresenceRoster> {
  const response = await fetch(createApiUrl(`/stations/${stationId}/presence/check-out-all`), {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await createApiError(response, "Nie udało się wymeldować obsady");
  }
  return response.json() as Promise<StationPresenceRoster>;
}

export async function fetchEmployees(includeInactive = false): Promise<Employee[]> {
  const url = createApiUrl(`/employees${includeInactive ? "?include_inactive=true" : ""}`);
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać listy pracowników");
  }
  return response.json() as Promise<Employee[]>;
}

export async function createEmployee(fullName: string): Promise<Employee> {
  const response = await fetch(createApiUrl("/employees"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ full_name: fullName }),
  });
  if (!response.ok) {
    throw await createApiError(response, "Nie udało się dodać pracownika");
  }
  return response.json() as Promise<Employee>;
}

export async function updateEmployee(
  employeeId: number,
  payload: { full_name?: string; is_active?: boolean },
): Promise<Employee> {
  const response = await fetch(createApiUrl(`/employees/${employeeId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await createApiError(response, "Nie udało się zaktualizować pracownika");
  }
  return response.json() as Promise<Employee>;
}

export async function fetchOperatorStats(dateFrom: string, dateTo: string): Promise<OperatorStats> {
  const url = createApiUrl(`/employees/stats?date_from=${dateFrom}&date_to=${dateTo}`);
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać statystyk operatorów");
  }
  return response.json() as Promise<OperatorStats>;
}

export async function fetchPresenceHistory(dateFrom: string, dateTo: string): Promise<PresenceHistory> {
  const url = createApiUrl(`/employees/presence/history?date_from=${dateFrom}&date_to=${dateTo}`);
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać historii obecności");
  }
  return response.json() as Promise<PresenceHistory>;
}

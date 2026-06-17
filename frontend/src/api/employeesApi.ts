import { createApiError } from "./apiError";
import { createApiUrl } from "./workOrdersApi";
import type { StationPresenceRoster } from "../types/employees";

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

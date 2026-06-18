import { useEffect, useState } from "react";

import { checkInEmployee, checkOutAllAtStation, checkOutEmployee, fetchStationPresence } from "../api/employeesApi";
import { getStationIdForLocation } from "../api/stationContext";
import type { StationPresenceRoster } from "../types/employees";

// Stations where a worker roster makes sense (production floor). Office/manager/unknown have no roster.
const ROSTER_STATIONS = new Set([
  "SURFACE_PREPARATION",
  "HANGING",
  "AUTOMATIC_PRODUCTION",
  "MANUAL_PRODUCTION",
  "PACKING",
  "DECORAL_PRODUCTION",
]);

export function StationPresenceWidget() {
  // Derive the station from the current route via window.location (same approach as
  // getCurrentStationHeaders) so the widget needs no Router context and stays test-friendly.
  const stationId = getStationIdForLocation(window.location.pathname, window.location.search);
  const enabled = ROSTER_STATIONS.has(stationId);

  const [roster, setRoster] = useState<StationPresenceRoster | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [checkingOutAll, setCheckingOutAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    fetchStationPresence(stationId)
      .then((data) => {
        if (!cancelled) setRoster(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Nie udało się pobrać obsady");
      });
    return () => {
      cancelled = true;
    };
  }, [stationId, enabled]);

  if (!enabled) return null;

  const presentIds = new Set((roster?.present ?? []).map((entry) => entry.employee_id));

  async function toggle(employeeId: number, isPresent: boolean) {
    setBusyId(employeeId);
    setError(null);
    try {
      const next = isPresent
        ? await checkOutEmployee(stationId, employeeId)
        : await checkInEmployee(stationId, employeeId);
      setRoster(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się zaktualizować obsady");
    } finally {
      setBusyId(null);
    }
  }

  async function checkOutEveryone() {
    setCheckingOutAll(true);
    setError(null);
    try {
      setRoster(await checkOutAllAtStation(stationId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się wymeldować obsady");
    } finally {
      setCheckingOutAll(false);
    }
  }

  return (
    <section className="rounded-3xl border border-line bg-white/80 p-5">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-[0.1em] text-steel">Obsada stanowiska</h3>
        <div className="flex items-center gap-3">
          <span className="text-xs text-steel">
            {presentIds.size > 0 ? `Na stanowisku: ${presentIds.size}` : "Nikt nie zaznaczony"}
          </span>
          {presentIds.size > 0 ? (
            <button
              type="button"
              onClick={checkOutEveryone}
              disabled={checkingOutAll}
              className="rounded-full border border-line px-2.5 py-1 text-xs font-medium text-steel transition hover:border-rose-400 hover:text-rose-600 disabled:opacity-50"
            >
              Wymelduj wszystkich
            </button>
          ) : null}
        </div>
      </div>
      <p className="mb-3 text-xs text-steel">
        Zaznacz, kto jest teraz na stanowisku — akcje będą przypisane obecnym osobom.
      </p>
      {error ? (
        <div className="mb-3 rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {(roster?.employees ?? []).map((employee) => {
          const isPresent = presentIds.has(employee.id);
          return (
            <button
              key={employee.id}
              type="button"
              disabled={busyId === employee.id}
              onClick={() => toggle(employee.id, isPresent)}
              className={[
                "rounded-full border px-3 py-1.5 text-sm font-medium transition disabled:opacity-50",
                isPresent
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-line bg-white text-steel hover:border-accent hover:text-accent",
              ].join(" ")}
              aria-pressed={isPresent}
            >
              {isPresent ? "✓ " : ""}
              {employee.full_name}
            </button>
          );
        })}
        {roster && roster.employees.length === 0 ? (
          <span className="text-sm text-steel">Brak pracowników na liście (dodaj w danych/seed).</span>
        ) : null}
      </div>
    </section>
  );
}
